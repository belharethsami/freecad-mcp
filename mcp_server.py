# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Main server implementation

Uses a simple JSON-RPC server over TCP for communication with LLM clients.
Includes automatic screenshot capture after every tool call for visual feedback.
"""

import asyncio
import threading
import json
import socket
import base64
import tempfile
import os
from typing import Optional, Tuple, List

import FreeCAD

from .bridge import get_bridge, reset_bridge, MainThreadBridge


# Global instances
_server: Optional['SimpleMCPServer'] = None
_bridge: Optional[MainThreadBridge] = None
_server_thread: Optional[threading.Thread] = None

DEFAULT_PORT = 9876

# Screenshot settings
_auto_screenshot_enabled = True
_screenshot_width = 800
_screenshot_height = 600

# Dual document state for split-screen view
_target_doc_name: Optional[str] = None
_work_doc_name: Optional[str] = None
_dual_mode_enabled: bool = False

# Measurement mode state
_measurement_mode: bool = False
_grid_config = {
    "enabled": False,
    "columns": 8,
    "rows": 6,
    # Zoom region (normalized 0-1 screen coordinates)
    "region": {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
}

# Point selection state
_pending_points = {}    # Points selected but not yet confirmed
_confirmed_points = {}  # Points locked in after confirmation
_point_counter = 0      # For generating point_1, point_2, etc.

# Measurement visualization
_measurement_objects = []  # Track measurement lines for cleanup

# High-contrast marker colors (cycle through these)
_marker_colors = [
    (1.0, 0.0, 1.0),   # Magenta
    (0.0, 1.0, 1.0),   # Cyan
    (1.0, 1.0, 0.0),   # Yellow
    (0.0, 1.0, 0.0),   # Green
    (1.0, 0.5, 0.0),   # Orange
]


def is_dual_mode() -> bool:
    """Check if dual document mode is active."""
    return _dual_mode_enabled and _target_doc_name is not None and _work_doc_name is not None


def get_target_doc():
    """Get the target document (contains reference STL)."""
    if _target_doc_name:
        return FreeCAD.getDocument(_target_doc_name)
    return None


def get_work_doc():
    """Get the work document (where agent creates objects)."""
    if _work_doc_name:
        return FreeCAD.getDocument(_work_doc_name)
    return FreeCAD.ActiveDocument


def activate_document(doc_name: str) -> bool:
    """Activate a document by name, returns True if successful."""
    try:
        import FreeCADGui
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            FreeCAD.setActiveDocument(doc_name)
            if FreeCADGui.ActiveDocument is None or FreeCADGui.ActiveDocument.Document.Name != doc_name:
                FreeCADGui.setActiveDocument(doc_name)
            return True
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Failed to activate document {doc_name}: {e}\n")
    return False


def reset_dual_mode():
    """Reset dual document mode state."""
    global _target_doc_name, _work_doc_name, _dual_mode_enabled
    _target_doc_name = None
    _work_doc_name = None
    _dual_mode_enabled = False


def has_gui() -> bool:
    """Check if FreeCAD GUI is available."""
    try:
        import FreeCADGui
        return FreeCADGui.ActiveDocument is not None or FreeCAD.ActiveDocument is not None
    except (ImportError, AttributeError):
        return False


def capture_viewport_base64(width: int = None, height: int = None, background: str = "White") -> Optional[str]:
    """
    Capture current viewport as base64-encoded PNG.
    
    Args:
        width: Image width in pixels (default: 800)
        height: Image height in pixels (default: 600)
        background: Background color ("White", "Black", "Transparent")
    
    Returns:
        Base64-encoded PNG string, or None if capture fails
    """
    if width is None:
        width = _screenshot_width
    if height is None:
        height = _screenshot_height
    
    try:
        import FreeCADGui
        from PySide2 import QtCore, QtWidgets
        
        # Ensure there's an active view
        if FreeCADGui.ActiveDocument is None:
            FreeCAD.Console.PrintWarning("Screenshot: No active GUI document\n")
            return None
        
        view = FreeCADGui.ActiveDocument.ActiveView
        if view is None:
            FreeCAD.Console.PrintWarning("Screenshot: No active view\n")
            return None
        
        # Force GUI update before capturing (do not change camera/zoom)
        QtWidgets.QApplication.processEvents()
        
        # Create temp file for screenshot
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        try:
            # Save screenshot to file
            # Use "Current" to capture exactly what's on screen
            view.saveImage(path, width, height, "Current")
            
            # Verify file was created and has content
            if os.path.exists(path) and os.path.getsize(path) > 100:
                with open(path, "rb") as f:
                    image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
            else:
                FreeCAD.Console.PrintWarning(f"Screenshot: File empty or not created\n")
                return None
        finally:
            # Clean up temp file
            if os.path.exists(path):
                os.remove(path)
                
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Screenshot capture failed: {e}\n")
        return None


def capture_document_viewport(doc_name: str, width: int = None, height: int = None) -> Optional[str]:
    """
    Capture viewport of a specific document as base64-encoded PNG.
    
    Args:
        doc_name: Name of the document to capture
        width: Image width in pixels
        height: Image height in pixels
    
    Returns:
        Base64-encoded PNG string, or None if capture fails
    """
    if width is None:
        width = _screenshot_width
    if height is None:
        height = _screenshot_height
    
    try:
        import FreeCADGui
        from PySide2 import QtWidgets
        
        # Activate the target document
        if not activate_document(doc_name):
            FreeCAD.Console.PrintWarning(f"Screenshot: Cannot activate document {doc_name}\n")
            return None
        
        QtWidgets.QApplication.processEvents()
        
        gui_doc = FreeCADGui.getDocument(doc_name)
        if gui_doc is None:
            FreeCAD.Console.PrintWarning(f"Screenshot: No GUI document for {doc_name}\n")
            return None
        
        view = gui_doc.ActiveView
        if view is None:
            FreeCAD.Console.PrintWarning(f"Screenshot: No active view for {doc_name}\n")
            return None
        
        # Force GUI update before capturing (do not change camera/zoom)
        QtWidgets.QApplication.processEvents()
        
        # Create temp file for screenshot
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        try:
            view.saveImage(path, width, height, "Current")
            
            if os.path.exists(path) and os.path.getsize(path) > 100:
                with open(path, "rb") as f:
                    image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
            else:
                return None
        finally:
            if os.path.exists(path):
                os.remove(path)
                
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Screenshot capture for {doc_name} failed: {e}\n")
        return None


def capture_split_view(width: int = None, height: int = None, label_height: int = 30) -> Optional[str]:
    """
    Capture both target and work documents and merge them side-by-side with labels.
    
    Args:
        width: Width of each individual image (total will be 2x this + gap)
        height: Height of each individual image
        label_height: Height of the label bar at the top of each image
    
    Returns:
        Base64-encoded PNG of the merged side-by-side image, or None if capture fails
    """
    if not is_dual_mode():
        # Fall back to single viewport capture
        return capture_viewport_base64(width, height)
    
    if width is None:
        width = _screenshot_width // 2  # Each panel is half width
    if height is None:
        height = _screenshot_height
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # Remember current active document
        original_active = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        
        # Capture target document
        target_b64 = capture_document_viewport(_target_doc_name, width, height)
        
        # Capture work document
        work_b64 = capture_document_viewport(_work_doc_name, width, height)
        
        # Restore original active document
        if original_active:
            activate_document(original_active)
        
        if not target_b64 and not work_b64:
            return None
        
        # Create placeholder images if one capture failed
        def create_placeholder(w, h, text):
            img = Image.new('RGB', (w, h), color=(200, 200, 200))
            draw = ImageDraw.Draw(img)
            try:
                # Try to center the text
                bbox = draw.textbbox((0, 0), text)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                x = (w - text_w) // 2
                y = (h - text_h) // 2
                draw.text((x, y), text, fill=(100, 100, 100))
            except:
                draw.text((10, h // 2), text, fill=(100, 100, 100))
            return img
        
        # Decode images
        if target_b64:
            target_img = Image.open(io.BytesIO(base64.b64decode(target_b64)))
        else:
            target_img = create_placeholder(width, height, "Target: No view")
        
        if work_b64:
            work_img = Image.open(io.BytesIO(base64.b64decode(work_b64)))
        else:
            work_img = create_placeholder(width, height, "Work: No view")
        
        # Ensure both images have the same size
        target_img = target_img.resize((width, height))
        work_img = work_img.resize((width, height))
        
        # Create combined image with labels
        gap = 4  # Gap between images
        total_width = width * 2 + gap
        total_height = height + label_height
        
        combined = Image.new('RGB', (total_width, total_height), color=(40, 40, 40))
        draw = ImageDraw.Draw(combined)
        
        # Draw labels
        target_label = "TARGET (Reference)"
        work_label = "YOUR CREATION"
        
        # Target label (left side)
        try:
            bbox = draw.textbbox((0, 0), target_label)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2
        except:
            x = 10
        draw.text((x, 5), target_label, fill=(255, 200, 100))
        
        # Work label (right side)
        try:
            bbox = draw.textbbox((0, 0), work_label)
            text_w = bbox[2] - bbox[0]
            x = width + gap + (width - text_w) // 2
        except:
            x = width + gap + 10
        draw.text((x, 5), work_label, fill=(100, 200, 255))
        
        # Paste images
        combined.paste(target_img, (0, label_height))
        combined.paste(work_img, (width + gap, label_height))
        
        # Encode to base64
        buffer = io.BytesIO()
        combined.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode('utf-8')
        
    except ImportError:
        FreeCAD.Console.PrintWarning("PIL/Pillow not available for split view. Install with: pip install Pillow\n")
        # Fall back to work document view only
        return capture_document_viewport(_work_doc_name, width, height) if _work_doc_name else capture_viewport_base64(width, height)
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Split view capture failed: {e}\n")
        return capture_viewport_base64(width, height)


def set_auto_screenshot(enabled: bool, width: int = 800, height: int = 600):
    """Configure automatic screenshot settings."""
    global _auto_screenshot_enabled, _screenshot_width, _screenshot_height
    _auto_screenshot_enabled = enabled
    _screenshot_width = width
    _screenshot_height = height


def parse_grid_cell(cell: str) -> Tuple[int, int]:
    """
    Parse a grid cell string like 'C2' into column and row indices.
    
    Args:
        cell: Grid cell string (e.g., 'A1', 'C2', 'H6')
    
    Returns:
        Tuple of (column_index, row_index), both 0-based
    """
    cell = cell.upper().strip()
    if len(cell) < 2:
        raise ValueError(f"Invalid grid cell: {cell}")
    
    col_char = cell[0]
    row_str = cell[1:]
    
    if not col_char.isalpha():
        raise ValueError(f"Invalid column letter: {col_char}")
    
    col = ord(col_char) - ord('A')
    try:
        row = int(row_str) - 1  # Convert to 0-based
    except ValueError:
        raise ValueError(f"Invalid row number: {row_str}")
    
    return col, row


def render_grid_overlay(image_data: bytes, columns: int = 8, rows: int = 6) -> bytes:
    """
    Render a grid overlay onto an image.
    
    Args:
        image_data: PNG image data as bytes
        columns: Number of columns (default 8 for A-H)
        rows: Number of rows (default 6 for 1-6)
    
    Returns:
        PNG image data with grid overlay as bytes
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # Load image
        img = Image.open(io.BytesIO(image_data))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Create overlay
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        w, h = img.size
        cell_w = w / columns
        cell_h = h / rows
        
        # Grid line color (semi-transparent white)
        line_color = (255, 255, 255, 180)
        text_color = (255, 255, 255, 220)
        bg_color = (0, 0, 0, 100)  # Semi-transparent background for labels
        
        # Try to use a readable font size
        font_size = max(12, min(20, int(cell_h / 4)))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except:
                font = ImageFont.load_default()
        
        # Draw vertical lines and column labels (A-H)
        for i in range(columns + 1):
            x = int(i * cell_w)
            draw.line([(x, 0), (x, h)], fill=line_color, width=1)
            
            if i < columns:
                label = chr(ord('A') + i)
                # Get text size
                try:
                    bbox = draw.textbbox((0, 0), label, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                except:
                    text_w, text_h = 10, 12
                
                label_x = int(i * cell_w + cell_w / 2 - text_w / 2)
                label_y = 5
                
                # Draw background for label
                draw.rectangle([label_x - 2, label_y - 1, label_x + text_w + 2, label_y + text_h + 1], 
                              fill=bg_color)
                draw.text((label_x, label_y), label, fill=text_color, font=font)
        
        # Draw horizontal lines and row labels (1-6)
        for j in range(rows + 1):
            y = int(j * cell_h)
            draw.line([(0, y), (w, y)], fill=line_color, width=1)
            
            if j < rows:
                label = str(j + 1)
                try:
                    bbox = draw.textbbox((0, 0), label, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                except:
                    text_w, text_h = 10, 12
                
                label_x = 5
                label_y = int(j * cell_h + cell_h / 2 - text_h / 2)
                
                # Draw background for label
                draw.rectangle([label_x - 2, label_y - 1, label_x + text_w + 2, label_y + text_h + 1],
                              fill=bg_color)
                draw.text((label_x, label_y), label, fill=text_color, font=font)
        
        # Composite overlay onto image
        img = Image.alpha_composite(img, overlay)
        
        # Convert back to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.read()
        
    except ImportError:
        FreeCAD.Console.PrintWarning("PIL not available for grid overlay\n")
        return image_data
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Grid overlay failed: {e}\n")
        return image_data


def add_point_labels_overlay(image_data: bytes, points: dict, view) -> bytes:
    """
    Add coordinate labels for point markers onto an image.
    
    Args:
        image_data: PNG image data as bytes
        points: Dictionary of point_id -> point info
        view: FreeCAD view for 3D to 2D coordinate conversion
    
    Returns:
        PNG image data with labels as bytes
    """
    if not points:
        return image_data
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        img = Image.open(io.BytesIO(image_data))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        draw = ImageDraw.Draw(img)
        
        # Font setup
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
            except:
                font = ImageFont.load_default()
        
        for point_id, info in points.items():
            coords = info.get("coords")
            if coords is None:
                continue
            
            # Try to get 2D screen position
            try:
                screen_pos = view.getPointOnViewport(coords)
                if screen_pos:
                    x, y = int(screen_pos[0]), int(screen_pos[1])
                else:
                    continue
            except:
                # Fallback: just place label at a fixed offset
                continue
            
            # Create label text
            status = "✓" if info.get("confirmed", False) else "?"
            label = f"{point_id}{status}: ({coords.x:.1f}, {coords.y:.1f}, {coords.z:.1f})"
            
            # Draw background
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except:
                text_w, text_h = len(label) * 7, 14
            
            label_x = x + 10
            label_y = y - 5
            
            # Keep label on screen
            label_x = min(label_x, img.width - text_w - 5)
            label_y = max(label_y, 5)
            
            bg_color = (0, 0, 0, 180)
            text_color = (255, 255, 0, 255) if info.get("confirmed") else (255, 200, 100, 255)
            
            draw.rectangle([label_x - 2, label_y - 1, label_x + text_w + 2, label_y + text_h + 1],
                          fill=bg_color)
            draw.text((label_x, label_y), label, fill=text_color, font=font)
        
        # Convert back to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.read()
        
    except ImportError:
        return image_data
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Point label overlay failed: {e}\n")
        return image_data


def capture_with_grid_and_labels(width: int = None, height: int = None) -> Optional[str]:
    """
    Capture viewport with grid overlay and point labels if measurement mode is active.
    
    Returns:
        Base64-encoded PNG string with overlays
    """
    global _grid_config, _pending_points, _confirmed_points
    
    if width is None:
        width = _screenshot_width
    if height is None:
        height = _screenshot_height
    
    try:
        import FreeCADGui
        from PySide2 import QtWidgets
        
        # Force GUI update
        QtWidgets.QApplication.processEvents()
        
        if FreeCADGui.ActiveDocument is None:
            return None
        
        view = FreeCADGui.ActiveDocument.ActiveView
        if view is None:
            return None
        
        # Capture base screenshot
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        try:
            view.saveImage(path, width, height, "Current")
            
            if not os.path.exists(path) or os.path.getsize(path) < 100:
                return None
            
            with open(path, "rb") as f:
                image_data = f.read()
            
            # Add grid overlay if measurement mode is active
            if _measurement_mode and _grid_config.get("enabled", False):
                image_data = render_grid_overlay(
                    image_data,
                    _grid_config.get("columns", 8),
                    _grid_config.get("rows", 6)
                )
            
            # Add point labels
            all_points = {}
            for pid, pinfo in _pending_points.items():
                all_points[pid] = {**pinfo, "confirmed": False}
            for pid, pinfo in _confirmed_points.items():
                all_points[pid] = {**pinfo, "confirmed": True}
            
            if all_points:
                image_data = add_point_labels_overlay(image_data, all_points, view)
            
            return base64.b64encode(image_data).decode('utf-8')
            
        finally:
            if os.path.exists(path):
                os.remove(path)
                
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Capture with grid failed: {e}\n")
        return None


def estimate_marker_size() -> float:
    """
    Estimate an appropriate marker sphere size based on the model's bounding box.
    
    Returns:
        Recommended marker radius in mm
    """
    try:
        doc = FreeCAD.ActiveDocument
        if not doc:
            return 2.0
        
        # Find bounding box of all objects
        min_coords = [float('inf')] * 3
        max_coords = [float('-inf')] * 3
        
        for obj in doc.Objects:
            if hasattr(obj, "Shape") and hasattr(obj.Shape, "BoundBox"):
                bb = obj.Shape.BoundBox
                min_coords = [min(min_coords[i], [bb.XMin, bb.YMin, bb.ZMin][i]) for i in range(3)]
                max_coords = [max(max_coords[i], [bb.XMax, bb.YMax, bb.ZMax][i]) for i in range(3)]
            elif obj.TypeId == "Mesh::Feature" and hasattr(obj, "Mesh"):
                bb = obj.Mesh.BoundBox
                min_coords = [min(min_coords[i], [bb.XMin, bb.YMin, bb.ZMin][i]) for i in range(3)]
                max_coords = [max(max_coords[i], [bb.XMax, bb.YMax, bb.ZMax][i]) for i in range(3)]
        
        if float('inf') in min_coords:
            return 2.0
        
        # Calculate diagonal
        diagonal = sum((max_coords[i] - min_coords[i]) ** 2 for i in range(3)) ** 0.5
        
        # Marker should be about 1-2% of diagonal, but at least 0.5mm and at most 5mm
        marker_size = max(0.5, min(5.0, diagonal * 0.015))
        return marker_size
        
    except Exception:
        return 2.0


def get_scene_bounding_box():
    """Get the bounding box encompassing all objects in the active document."""
    try:
        doc = FreeCAD.ActiveDocument
        if not doc:
            return None
        
        min_coords = [float('inf')] * 3
        max_coords = [float('-inf')] * 3
        found_objects = False
        
        for obj in doc.Objects:
            bb = None
            if hasattr(obj, "Shape") and hasattr(obj.Shape, "BoundBox"):
                bb = obj.Shape.BoundBox
            elif obj.TypeId == "Mesh::Feature" and hasattr(obj, "Mesh"):
                bb = obj.Mesh.BoundBox
            
            if bb:
                found_objects = True
                min_coords = [min(min_coords[i], [bb.XMin, bb.YMin, bb.ZMin][i]) for i in range(3)]
                max_coords = [max(max_coords[i], [bb.XMax, bb.YMax, bb.ZMax][i]) for i in range(3)]
        
        if not found_objects:
            return None
        
        return {
            "min": min_coords,
            "max": max_coords,
            "center": [(min_coords[i] + max_coords[i]) / 2 for i in range(3)],
            "size": [max_coords[i] - min_coords[i] for i in range(3)]
        }
        
    except Exception:
        return None

# Tool definitions
TOOLS = {
    "setup_dual_docs": {
        "description": "Initialize dual-document mode: creates TargetDoc (with reference STL) and WorkDoc (for your creations). Screenshots will show both side-by-side.",
        "parameters": {
            "target_stl_path": "string (path to reference STL file)",
            "target_doc_name": "string (optional, default 'TargetDoc')",
            "work_doc_name": "string (optional, default 'WorkDoc')"
        }
    },
    "new_document": {
        "description": "Create a new FreeCAD document",
        "parameters": {"name": "string (optional, default 'Unnamed')"}
    },
    "list_documents": {
        "description": "List all open FreeCAD documents",
        "parameters": {}
    },
    "list_objects": {
        "description": "List all objects in a document",
        "parameters": {
            "doc": "string (optional: 'target', 'work', default 'work' in dual mode)"
        }
    },
    "create_box": {
        "description": "Create a box primitive",
        "parameters": {"length": "number (mm)", "width": "number (mm)", "height": "number (mm)", "name": "string (optional)"}
    },
    "create_cylinder": {
        "description": "Create a cylinder primitive",
        "parameters": {"radius": "number (mm)", "height": "number (mm)", "name": "string (optional)"}
    },
    "create_sphere": {
        "description": "Create a sphere primitive",
        "parameters": {"radius": "number (mm)", "name": "string (optional)"}
    },
    "create_cone": {
        "description": "Create a cone primitive",
        "parameters": {"radius1": "number (mm)", "radius2": "number (mm)", "height": "number (mm)", "name": "string (optional)"}
    },
    "boolean_union": {
        "description": "Create a union of two objects",
        "parameters": {"object1": "string", "object2": "string", "name": "string (optional)"}
    },
    "boolean_cut": {
        "description": "Cut one object from another",
        "parameters": {"base": "string", "tool": "string", "name": "string (optional)"}
    },
    "move_object": {
        "description": "Move an object by offset",
        "parameters": {"name": "string", "x": "number (optional)", "y": "number (optional)", "z": "number (optional)"}
    },
    "delete_object": {
        "description": "Delete an object",
        "parameters": {"name": "string"}
    },
    "export_stl": {
        "description": "Export to STL file",
        "parameters": {"path": "string", "objects": "array of strings (optional)"}
    },
    "export_step": {
        "description": "Export to STEP file",
        "parameters": {"path": "string", "objects": "array of strings (optional)"}
    },
    "get_object_info": {
        "description": "Get object information (volume, bounds, etc.)",
        "parameters": {
            "name": "string",
            "doc": "string (optional: 'target', 'work', default 'work' in dual mode)"
        }
    },
    "save_document": {
        "description": "Save the document",
        "parameters": {"path": "string (optional)"}
    },
    "recompute": {
        "description": "Recompute the document",
        "parameters": {}
    },
    "compare_to_stl": {
        "description": "Compare current document shapes to a reference STL file. Returns Hausdorff distance, volume/area comparison.",
        "parameters": {
            "reference_path": "string (path to reference STL file)",
            "tolerance": "number (mm, optional, default 1.0)",
            "tessellation": "number (mm, optional, tessellation accuracy, default 0.1)"
        }
    },
    "get_mesh_points": {
        "description": "Export current shapes as point cloud for external comparison",
        "parameters": {
            "tessellation": "number (mm, optional, default 0.1)",
            "sample_rate": "number (optional, sample every Nth point, default 1)"
        }
    },
    # === View and Screenshot Tools ===
    "take_screenshot": {
        "description": "Take a screenshot. In dual mode, defaults to split view showing both target and work.",
        "parameters": {
            "mode": "string (optional: 'split', 'target', 'work', default 'split' in dual mode)",
            "width": "number (optional, default 800)",
            "height": "number (optional, default 600)",
            "background": "string (optional: 'White', 'Black', 'Transparent', default 'White')"
        }
    },
    "set_view": {
        "description": "Set camera to a preset view angle for a specific document",
        "parameters": {
            "preset": "string (front/back/top/bottom/left/right/isometric)",
            "doc": "string (optional: 'target', 'work', or 'both', default 'work' in dual mode)"
        }
    },
    "fit_all": {
        "description": "Fit camera to show all objects in the viewport",
        "parameters": {
            "doc": "string (optional: 'target', 'work', or 'both', default 'work' in dual mode)"
        }
    },
    "import_stl": {
        "description": "Import an STL file as a visible mesh object (for reference/target)",
        "parameters": {
            "path": "string (path to STL file)",
            "name": "string (optional, object name)"
        }
    },
    "set_visibility": {
        "description": "Show or hide objects in the viewport",
        "parameters": {
            "name": "string (object name, or '*' for all objects)",
            "visible": "boolean"
        }
    },
    "rotate_view": {
        "description": "Rotate the camera view by specified angles for a specific document",
        "parameters": {
            "yaw": "number (degrees, rotation around Z axis, optional)",
            "pitch": "number (degrees, rotation around X axis, optional)",
            "roll": "number (degrees, rotation around Y axis, optional)",
            "doc": "string (optional: 'target', 'work', or 'both', default 'work' in dual mode)"
        }
    },
    # === Display Mode Tools ===
    "set_display_mode": {
        "description": "Change how an object renders (solid, transparent, or wireframe)",
        "parameters": {
            "object": "string (object name)",
            "mode": "string ('solid', 'transparent', or 'wireframe')",
            "transparency": "number (optional, 0-100 for transparent mode, default 70)"
        }
    },
    "set_clipping_plane": {
        "description": "Enable a cross-section clipping plane to reveal internal surfaces",
        "parameters": {
            "axis": "string ('X', 'Y', or 'Z')",
            "percent": "number (0-100, position along axis as percentage of bounding box)",
            "enabled": "boolean (true to enable, false to disable)"
        }
    },
    # === Camera Navigation Tools ===
    "zoom": {
        "description": "Zoom camera in or out by a percentage",
        "parameters": {
            "percent": "number (>100 zooms in, <100 zooms out, e.g. 150 = 1.5x zoom)",
            "doc": "string (optional: 'target', 'work', or 'both', default 'work' in dual mode)"
        }
    },
    "pan": {
        "description": "Pan camera by percentage of viewport",
        "parameters": {
            "x": "number (-100 to 100, percentage to pan horizontally)",
            "y": "number (-100 to 100, percentage to pan vertically)",
            "doc": "string (optional: 'target', 'work', or 'both', default 'work' in dual mode)"
        }
    },
    # === Measurement Mode Tools ===
    "start_measurement": {
        "description": "Begin measurement mode: shows grid overlay (8x6) for point selection",
        "parameters": {}
    },
    "end_measurement": {
        "description": "End measurement mode: hides grid overlay, clears pending (unconfirmed) points",
        "parameters": {}
    },
    "zoom_grid_region": {
        "description": "Zoom into a grid region for precise point selection. The region becomes a new 8x6 grid.",
        "parameters": {
            "start_cell": "string (e.g. 'A5', 'C3' - top-left cell of the region)",
            "size": "number (size of region: 2 = 2x2 cells, 3 = 3x3 cells)"
        }
    },
    "reset_grid_zoom": {
        "description": "Reset grid zoom to show the full view",
        "parameters": {}
    },
    "select_point": {
        "description": "Select a point on a mesh surface using grid coordinates. Places a visible marker.",
        "parameters": {
            "grid_cell": "string (e.g. 'C2', 'D5' - the grid cell to select)",
            "offset_x": "number (optional, 0-1, position within cell horizontally, default 0.5)",
            "offset_y": "number (optional, 0-1, position within cell vertically, default 0.5)"
        }
    },
    "confirm_point": {
        "description": "Confirm a pending point selection, locking it in for measurement",
        "parameters": {
            "point_id": "string (e.g. 'point_1')"
        }
    },
    "clear_point": {
        "description": "Remove a point marker (pending or confirmed)",
        "parameters": {
            "point_id": "string (point ID or 'all' to clear all points)"
        }
    },
    "list_points": {
        "description": "List all current point markers with their coordinates and status",
        "parameters": {}
    },
    "measure_distance": {
        "description": "Measure distance between two confirmed points. Draws a visual line between them.",
        "parameters": {
            "point_a": "string (first point ID, e.g. 'point_1')",
            "point_b": "string (second point ID, e.g. 'point_2')"
        }
    },
    "clear_measurements": {
        "description": "Remove all measurement lines and markers",
        "parameters": {}
    },
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool on the main thread."""
    
    def _execute():
        global _target_doc_name, _work_doc_name, _dual_mode_enabled
        global _measurement_mode, _grid_config
        global _pending_points, _confirmed_points, _point_counter
        global _measurement_objects
        
        # For most tools, use work doc in dual mode, else active document
        if is_dual_mode():
            doc = get_work_doc()
        else:
            doc = FreeCAD.ActiveDocument
        
        if name == "setup_dual_docs":
            import Mesh
            import os as os_module
            
            stl_path = arguments.get("target_stl_path")
            if not stl_path:
                return {"success": False, "error": "target_stl_path is required"}
            
            if not os_module.path.exists(stl_path):
                return {"success": False, "error": f"File not found: {stl_path}"}
            
            target_name = arguments.get("target_doc_name", "TargetDoc")
            work_name = arguments.get("work_doc_name", "WorkDoc")
            
            try:
                # Close existing docs if they exist
                for existing_name in [target_name, work_name]:
                    try:
                        existing = FreeCAD.getDocument(existing_name)
                        if existing:
                            FreeCAD.closeDocument(existing_name)
                    except:
                        pass
                
                # Create TargetDoc and import STL
                target_doc = FreeCAD.newDocument(target_name)
                _target_doc_name = target_doc.Name
                
                # Import STL into target doc
                Mesh.insert(stl_path, target_doc.Name)
                
                # Find the imported mesh object
                mesh_objects = [o for o in target_doc.Objects if o.TypeId == "Mesh::Feature"]
                target_mesh_name = None
                target_mesh_info = {}
                if mesh_objects:
                    imported = mesh_objects[-1]
                    imported.Label = "TargetMesh"
                    target_mesh_name = imported.Name
                    target_mesh_info = {
                        "name": imported.Name,
                        "label": imported.Label,
                        "points": imported.Mesh.CountPoints,
                        "facets": imported.Mesh.CountFacets
                    }
                
                target_doc.recompute()
                
                # Create WorkDoc (empty, for agent to build in)
                work_doc = FreeCAD.newDocument(work_name)
                _work_doc_name = work_doc.Name
                
                # Set work doc as active (all creation tools will use this)
                FreeCAD.setActiveDocument(work_doc.Name)
                
                # Enable dual mode
                _dual_mode_enabled = True
                
                # Set up views
                try:
                    import FreeCADGui
                    from PySide2 import QtWidgets
                    
                    # Set isometric view for both
                    for doc_name in [_target_doc_name, _work_doc_name]:
                        activate_document(doc_name)
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            gui_doc.ActiveView.viewIsometric()
                            gui_doc.ActiveView.fitAll()
                    
                    # Re-activate work doc
                    activate_document(_work_doc_name)
                    QtWidgets.QApplication.processEvents()
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"View setup warning: {e}\n")
                
                return {
                    "success": True,
                    "target_doc": _target_doc_name,
                    "work_doc": _work_doc_name,
                    "target_mesh": target_mesh_info,
                    "dual_mode": True,
                    "message": f"Dual mode enabled. Target STL loaded into '{_target_doc_name}'. Create objects in '{_work_doc_name}'."
                }
                
            except Exception as e:
                reset_dual_mode()
                return {"success": False, "error": f"Failed to setup dual docs: {e}"}
        
        elif name == "new_document":
            doc_name = arguments.get("name", "Unnamed")
            doc = FreeCAD.newDocument(doc_name)
            return {"success": True, "document": doc.Name}
        
        elif name == "list_documents":
            docs = [{"name": d, "objects": len(FreeCAD.getDocument(d).Objects)} 
                    for d in FreeCAD.listDocuments()]
            return {"success": True, "documents": docs}
        
        elif name == "list_objects":
            # Allow querying specific document in dual mode
            doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
            query_doc = doc
            if is_dual_mode():
                if doc_param == "target":
                    query_doc = get_target_doc()
                elif doc_param == "work":
                    query_doc = get_work_doc()
            
            if query_doc is None:
                return {"success": False, "error": "No active document"}
            objects = []
            for obj in query_doc.Objects:
                info = {"name": obj.Name, "type": obj.TypeId}
                if hasattr(obj, "Shape") and hasattr(obj.Shape, "Volume"):
                    info["volume"] = round(obj.Shape.Volume, 2)
                # For mesh objects, include mesh info
                if obj.TypeId == "Mesh::Feature" and hasattr(obj, "Mesh"):
                    info["points"] = obj.Mesh.CountPoints
                    info["facets"] = obj.Mesh.CountFacets
                objects.append(info)
            return {"success": True, "objects": objects, "document": query_doc.Name}
        
        elif name == "create_box":
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            obj = doc.addObject("Part::Box", arguments.get("name", "Box"))
            obj.Length = arguments["length"]
            obj.Width = arguments["width"]
            obj.Height = arguments["height"]
            doc.recompute()
            return {"success": True, "name": obj.Name, "volume": round(obj.Shape.Volume, 2)}
        
        elif name == "create_cylinder":
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            obj = doc.addObject("Part::Cylinder", arguments.get("name", "Cylinder"))
            obj.Radius = arguments["radius"]
            obj.Height = arguments["height"]
            doc.recompute()
            return {"success": True, "name": obj.Name, "volume": round(obj.Shape.Volume, 2)}
        
        elif name == "create_sphere":
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            obj = doc.addObject("Part::Sphere", arguments.get("name", "Sphere"))
            obj.Radius = arguments["radius"]
            doc.recompute()
            return {"success": True, "name": obj.Name, "volume": round(obj.Shape.Volume, 2)}
        
        elif name == "create_cone":
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            obj = doc.addObject("Part::Cone", arguments.get("name", "Cone"))
            obj.Radius1 = arguments["radius1"]
            obj.Radius2 = arguments["radius2"]
            obj.Height = arguments["height"]
            doc.recompute()
            return {"success": True, "name": obj.Name, "volume": round(obj.Shape.Volume, 2)}
        
        elif name == "boolean_union":
            if doc is None:
                return {"success": False, "error": "No active document"}
            obj1 = doc.getObject(arguments["object1"])
            obj2 = doc.getObject(arguments["object2"])
            if not obj1 or not obj2:
                return {"success": False, "error": "Objects not found"}
            fusion = doc.addObject("Part::MultiFuse", arguments.get("name", "Union"))
            fusion.Shapes = [obj1, obj2]
            doc.recompute()
            return {"success": True, "name": fusion.Name, "volume": round(fusion.Shape.Volume, 2)}
        
        elif name == "boolean_cut":
            if doc is None:
                return {"success": False, "error": "No active document"}
            base = doc.getObject(arguments["base"])
            tool = doc.getObject(arguments["tool"])
            if not base or not tool:
                return {"success": False, "error": "Objects not found"}
            cut = doc.addObject("Part::Cut", arguments.get("name", "Cut"))
            cut.Base = base
            cut.Tool = tool
            doc.recompute()
            return {"success": True, "name": cut.Name, "volume": round(cut.Shape.Volume, 2)}
        
        elif name == "move_object":
            if doc is None:
                return {"success": False, "error": "No active document"}
            obj = doc.getObject(arguments["name"])
            if not obj:
                return {"success": False, "error": f"Object not found"}
            pos = obj.Placement.Base
            obj.Placement.Base = FreeCAD.Vector(
                pos.x + arguments.get("x", 0),
                pos.y + arguments.get("y", 0),
                pos.z + arguments.get("z", 0)
            )
            doc.recompute()
            p = obj.Placement.Base
            return {"success": True, "position": [p.x, p.y, p.z]}
        
        elif name == "delete_object":
            if doc is None:
                return {"success": False, "error": "No active document"}
            if not doc.getObject(arguments["name"]):
                return {"success": False, "error": "Object not found"}
            doc.removeObject(arguments["name"])
            doc.recompute()
            return {"success": True}
        
        elif name == "export_stl":
            import Mesh
            import MeshPart
            if doc is None:
                return {"success": False, "error": "No active document"}
            objs = [doc.getObject(n) for n in arguments.get("objects", [])] if arguments.get("objects") else \
                   [o for o in doc.Objects if hasattr(o, "Shape")]
            objs = [o for o in objs if o and hasattr(o, "Shape")]
            if not objs:
                return {"success": False, "error": "No objects"}
            
            # Use MeshPart to properly convert shapes to mesh
            combined_mesh = Mesh.Mesh()
            for o in objs:
                try:
                    shape_mesh = MeshPart.meshFromShape(o.Shape, LinearDeflection=0.1)
                    combined_mesh.addMesh(shape_mesh)
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"Failed to mesh {o.Name}: {e}\n")
            
            if combined_mesh.CountPoints == 0:
                return {"success": False, "error": "Failed to create mesh from shapes"}
            
            combined_mesh.write(arguments["path"])
            return {"success": True, "path": arguments["path"], "points": combined_mesh.CountPoints}
        
        elif name == "export_step":
            import Part
            if doc is None:
                return {"success": False, "error": "No active document"}
            objs = [doc.getObject(n) for n in arguments.get("objects", [])] if arguments.get("objects") else \
                   [o for o in doc.Objects if hasattr(o, "Shape")]
            objs = [o for o in objs if o]
            if not objs:
                return {"success": False, "error": "No objects"}
            Part.export(objs, arguments["path"])
            return {"success": True, "path": arguments["path"]}
        
        elif name == "get_object_info":
            # Allow querying specific document in dual mode
            doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
            query_doc = doc
            if is_dual_mode():
                if doc_param == "target":
                    query_doc = get_target_doc()
                elif doc_param == "work":
                    query_doc = get_work_doc()
            
            if query_doc is None:
                return {"success": False, "error": "No active document"}
            obj = query_doc.getObject(arguments["name"])
            if not obj:
                return {"success": False, "error": f"Object '{arguments['name']}' not found in {query_doc.Name}"}
            info = {"name": obj.Name, "type": obj.TypeId, "document": query_doc.Name}
            if hasattr(obj, "Shape"):
                s = obj.Shape
                info["volume"] = round(s.Volume, 2)
                info["area"] = round(s.Area, 2)
                b = s.BoundBox
                info["bounds"] = {"min": [b.XMin, b.YMin, b.ZMin], "max": [b.XMax, b.YMax, b.ZMax]}
            # For mesh objects, include mesh-specific info
            if obj.TypeId == "Mesh::Feature" and hasattr(obj, "Mesh"):
                mesh = obj.Mesh
                info["points"] = mesh.CountPoints
                info["facets"] = mesh.CountFacets
                info["volume"] = round(mesh.Volume, 2)
                info["area"] = round(mesh.Area, 2)
                b = mesh.BoundBox
                info["bounds"] = {"min": [b.XMin, b.YMin, b.ZMin], "max": [b.XMax, b.YMax, b.ZMax]}
            return {"success": True, "info": info}
        
        elif name == "save_document":
            if doc is None:
                return {"success": False, "error": "No active document"}
            path = arguments.get("path")
            if path:
                doc.saveAs(path)
            elif doc.FileName:
                doc.save()
            else:
                return {"success": False, "error": "Path required for new document"}
            return {"success": True, "path": doc.FileName}
        
        elif name == "recompute":
            if doc is None:
                return {"success": False, "error": "No active document"}
            doc.recompute()
            return {"success": True}
        
        elif name == "compare_to_stl":
            import Mesh
            import os
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            ref_path = arguments.get("reference_path")
            if not ref_path or not os.path.exists(ref_path):
                return {"success": False, "error": f"Reference file not found: {ref_path}"}
            
            tolerance = arguments.get("tolerance", 1.0)
            tess_accuracy = arguments.get("tessellation", 0.1)
            
            # Load reference STL
            try:
                ref_mesh = Mesh.Mesh(ref_path)
            except Exception as e:
                return {"success": False, "error": f"Failed to load reference STL: {e}"}
            
            ref_points = [[p.x, p.y, p.z] for p in ref_mesh.Points]
            if not ref_points:
                return {"success": False, "error": "Reference STL has no points"}
            
            # Get current shapes and tessellate
            current_shapes = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
            if not current_shapes:
                return {"success": False, "error": "No shapes in document"}
            
            current_points = []
            current_volume = 0.0
            current_area = 0.0
            
            for obj in current_shapes:
                try:
                    vertices, faces = obj.Shape.tessellate(tess_accuracy)
                    for v in vertices:
                        current_points.append([v.x, v.y, v.z])
                    current_volume += obj.Shape.Volume
                    current_area += obj.Shape.Area
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"Failed to tessellate {obj.Name}: {e}\n")
            
            if not current_points:
                return {"success": False, "error": "Failed to tessellate current shapes"}
            
            # Compute Hausdorff distance (sample for speed)
            import math
            
            def distance(p1, p2):
                return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))
            
            def min_distance_to_set(point, point_set, sample_rate=10):
                """Find minimum distance from point to any point in set."""
                min_dist = float('inf')
                for i, p in enumerate(point_set):
                    if i % sample_rate == 0:  # Sample for speed
                        d = distance(point, p)
                        if d < min_dist:
                            min_dist = d
                return min_dist
            
            # Sample points for faster computation
            sample_rate = max(1, len(ref_points) // 500)
            sampled_ref = ref_points[::sample_rate]
            sampled_current = current_points[::sample_rate]
            
            # Directed Hausdorff: ref -> current
            max_ref_to_current = 0.0
            for p in sampled_ref:
                d = min_distance_to_set(p, current_points, sample_rate=1)
                if d > max_ref_to_current:
                    max_ref_to_current = d
            
            # Directed Hausdorff: current -> ref
            max_current_to_ref = 0.0
            for p in sampled_current:
                d = min_distance_to_set(p, ref_points, sample_rate=1)
                if d > max_current_to_ref:
                    max_current_to_ref = d
            
            hausdorff = max(max_ref_to_current, max_current_to_ref)
            
            # Get reference mesh metrics
            ref_volume = ref_mesh.Volume
            ref_area = ref_mesh.Area
            
            # Compute errors
            volume_error = abs(ref_volume - current_volume) / ref_volume if ref_volume > 0 else 0
            area_error = abs(ref_area - current_area) / ref_area if ref_area > 0 else 0
            
            is_match = hausdorff <= tolerance and volume_error <= 0.05
            
            return {
                "success": True,
                "hausdorff_distance": round(hausdorff, 4),
                "is_match": is_match,
                "tolerance": tolerance,
                "reference_volume": round(ref_volume, 2),
                "current_volume": round(current_volume, 2),
                "volume_error": round(volume_error, 4),
                "reference_area": round(ref_area, 2),
                "current_area": round(current_area, 2),
                "area_error": round(area_error, 4),
                "reference_points": len(ref_points),
                "current_points": len(current_points),
            }
        
        elif name == "get_mesh_points":
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            tess_accuracy = arguments.get("tessellation", 0.1)
            sample_rate = arguments.get("sample_rate", 1)
            
            current_shapes = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
            if not current_shapes:
                return {"success": False, "error": "No shapes in document"}
            
            points = []
            total_volume = 0.0
            total_area = 0.0
            bounds_min = [float('inf')] * 3
            bounds_max = [float('-inf')] * 3
            
            for obj in current_shapes:
                try:
                    vertices, faces = obj.Shape.tessellate(tess_accuracy)
                    for i, v in enumerate(vertices):
                        if i % sample_rate == 0:
                            points.append([round(v.x, 4), round(v.y, 4), round(v.z, 4)])
                            for j in range(3):
                                coord = [v.x, v.y, v.z][j]
                                bounds_min[j] = min(bounds_min[j], coord)
                                bounds_max[j] = max(bounds_max[j], coord)
                    total_volume += obj.Shape.Volume
                    total_area += obj.Shape.Area
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"Failed to tessellate {obj.Name}: {e}\n")
            
            return {
                "success": True,
                "points": points,
                "point_count": len(points),
                "volume": round(total_volume, 2),
                "area": round(total_area, 2),
                "bounds_min": [round(b, 2) for b in bounds_min],
                "bounds_max": [round(b, 2) for b in bounds_max],
            }
        
        elif name == "take_screenshot":
            width = arguments.get("width", _screenshot_width)
            height = arguments.get("height", _screenshot_height)
            background = arguments.get("background", "White")
            mode = arguments.get("mode", "split" if is_dual_mode() else "single")
            
            if is_dual_mode():
                if mode == "split":
                    screenshot = capture_split_view(width // 2, height)
                elif mode == "target":
                    screenshot = capture_document_viewport(_target_doc_name, width, height)
                elif mode == "work":
                    screenshot = capture_document_viewport(_work_doc_name, width, height)
                else:
                    screenshot = capture_split_view(width // 2, height)
            else:
                screenshot = capture_viewport_base64(width, height, background)
            
            if screenshot:
                return {"success": True, "screenshot": screenshot, "width": width, "height": height, "mode": mode}
            else:
                return {"success": False, "error": "Failed to capture screenshot (GUI may not be available)"}
        
        elif name == "set_view":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                
                preset = arguments.get("preset", "isometric").lower()
                doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
                
                def apply_view_preset(view, preset_name):
                    """Apply a view preset to a view."""
                    if preset_name == "front":
                        view.viewFront()
                    elif preset_name == "back":
                        view.viewRear()
                    elif preset_name == "top":
                        view.viewTop()
                    elif preset_name == "bottom":
                        view.viewBottom()
                    elif preset_name == "left":
                        view.viewLeft()
                    elif preset_name == "right":
                        view.viewRight()
                    elif preset_name == "isometric":
                        view.viewIsometric()
                    else:
                        return False
                    view.fitAll()
                    return True
                
                # Determine which documents to apply the view to
                docs_to_update = []
                if is_dual_mode():
                    if doc_param == "target":
                        docs_to_update = [_target_doc_name]
                    elif doc_param == "work":
                        docs_to_update = [_work_doc_name]
                    elif doc_param == "both":
                        docs_to_update = [_target_doc_name, _work_doc_name]
                    else:
                        docs_to_update = [_work_doc_name]
                else:
                    if FreeCADGui.ActiveDocument is None:
                        return {"success": False, "error": "No active document with view"}
                    docs_to_update = [FreeCAD.ActiveDocument.Name]
                
                updated_docs = []
                for doc_name in docs_to_update:
                    if activate_document(doc_name):
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            if apply_view_preset(gui_doc.ActiveView, preset):
                                updated_docs.append(doc_name)
                
                QtWidgets.QApplication.processEvents()
                
                if not updated_docs:
                    return {"success": False, "error": f"Unknown view preset: {preset}. Use: front/back/top/bottom/left/right/isometric"}
                
                return {"success": True, "view": preset, "documents": updated_docs}
            except Exception as e:
                return {"success": False, "error": f"Failed to set view: {e}"}
        
        elif name == "fit_all":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                
                doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
                
                # Determine which documents to apply fit_all to
                docs_to_update = []
                if is_dual_mode():
                    if doc_param == "target":
                        docs_to_update = [_target_doc_name]
                    elif doc_param == "work":
                        docs_to_update = [_work_doc_name]
                    elif doc_param == "both":
                        docs_to_update = [_target_doc_name, _work_doc_name]
                    else:
                        docs_to_update = [_work_doc_name]
                else:
                    if FreeCADGui.ActiveDocument is None:
                        return {"success": False, "error": "No active document with view"}
                    docs_to_update = [FreeCAD.ActiveDocument.Name]
                
                updated_docs = []
                for doc_name in docs_to_update:
                    if activate_document(doc_name):
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            gui_doc.ActiveView.fitAll()
                            updated_docs.append(doc_name)
                
                QtWidgets.QApplication.processEvents()
                
                return {"success": True, "documents": updated_docs}
            except Exception as e:
                return {"success": False, "error": f"Failed to fit view: {e}"}
        
        elif name == "import_stl":
            import Mesh
            import os as os_module  # Local import to avoid scoping issues
            
            stl_path = arguments.get("path")
            if not stl_path:
                return {"success": False, "error": "Path is required"}
            
            if not os_module.path.exists(stl_path):
                return {"success": False, "error": f"File not found: {stl_path}"}
            
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            try:
                # Import the STL mesh
                mesh_obj = Mesh.insert(stl_path, doc.Name)
                
                # Find the imported object (it's the last mesh object added)
                mesh_objects = [o for o in doc.Objects if o.TypeId == "Mesh::Feature"]
                if mesh_objects:
                    imported = mesh_objects[-1]
                    obj_name = arguments.get("name")
                    if obj_name:
                        imported.Label = obj_name
                    
                    # Fit view to show the imported object
                    try:
                        import FreeCADGui
                        if FreeCADGui.ActiveDocument:
                            FreeCADGui.ActiveDocument.ActiveView.fitAll()
                    except:
                        pass
                    
                    return {
                        "success": True,
                        "name": imported.Name,
                        "label": imported.Label,
                        "points": imported.Mesh.CountPoints,
                        "facets": imported.Mesh.CountFacets
                    }
                else:
                    return {"success": False, "error": "Failed to import mesh"}
            except Exception as e:
                return {"success": False, "error": f"Failed to import STL: {e}"}
        
        elif name == "set_visibility":
            try:
                import FreeCADGui
                
                if doc is None:
                    return {"success": False, "error": "No active document"}
                
                obj_name = arguments.get("name")
                visible = arguments.get("visible", True)
                
                if obj_name == "*":
                    # Set visibility for all objects
                    count = 0
                    for obj in doc.Objects:
                        if hasattr(obj, "ViewObject") and obj.ViewObject:
                            obj.ViewObject.Visibility = visible
                            count += 1
                    return {"success": True, "objects_affected": count, "visible": visible}
                else:
                    obj = doc.getObject(obj_name)
                    if not obj:
                        return {"success": False, "error": f"Object not found: {obj_name}"}
                    
                    if hasattr(obj, "ViewObject") and obj.ViewObject:
                        obj.ViewObject.Visibility = visible
                        return {"success": True, "name": obj_name, "visible": visible}
                    else:
                        return {"success": False, "error": f"Object has no ViewObject: {obj_name}"}
            except Exception as e:
                return {"success": False, "error": f"Failed to set visibility: {e}"}
        
        elif name == "rotate_view":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                
                yaw = arguments.get("yaw", 0)
                pitch = arguments.get("pitch", 0)
                roll = arguments.get("roll", 0)
                doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
                
                def apply_rotation(view, yaw_val, pitch_val, roll_val):
                    """Apply rotation to a view."""
                    current_rot = view.getCameraOrientation()
                    
                    if yaw_val != 0:
                        rot_z = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), yaw_val)
                        current_rot = rot_z.multiply(current_rot)
                    if pitch_val != 0:
                        rot_x = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), pitch_val)
                        current_rot = rot_x.multiply(current_rot)
                    if roll_val != 0:
                        rot_y = FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), roll_val)
                        current_rot = rot_y.multiply(current_rot)
                    
                    view.setCameraOrientation(current_rot)
                
                # Determine which documents to apply rotation to
                docs_to_update = []
                if is_dual_mode():
                    if doc_param == "target":
                        docs_to_update = [_target_doc_name]
                    elif doc_param == "work":
                        docs_to_update = [_work_doc_name]
                    elif doc_param == "both":
                        docs_to_update = [_target_doc_name, _work_doc_name]
                    else:
                        docs_to_update = [_work_doc_name]
                else:
                    if FreeCADGui.ActiveDocument is None:
                        return {"success": False, "error": "No active document with view"}
                    docs_to_update = [FreeCAD.ActiveDocument.Name]
                
                updated_docs = []
                for doc_name in docs_to_update:
                    if activate_document(doc_name):
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            apply_rotation(gui_doc.ActiveView, yaw, pitch, roll)
                            updated_docs.append(doc_name)
                
                QtWidgets.QApplication.processEvents()
                
                return {"success": True, "yaw": yaw, "pitch": pitch, "roll": roll, "documents": updated_docs}
            except Exception as e:
                return {"success": False, "error": f"Failed to rotate view: {e}"}
        
        # === Display Mode Tools ===
        elif name == "set_display_mode":
            try:
                import FreeCADGui
                
                if doc is None:
                    return {"success": False, "error": "No active document"}
                
                obj_name = arguments.get("object")
                mode = arguments.get("mode", "solid").lower()
                transparency = arguments.get("transparency", 70)
                
                obj = doc.getObject(obj_name)
                if not obj:
                    return {"success": False, "error": f"Object not found: {obj_name}"}
                
                if not hasattr(obj, "ViewObject") or obj.ViewObject is None:
                    return {"success": False, "error": f"Object has no ViewObject: {obj_name}"}
                
                vo = obj.ViewObject
                
                if mode == "transparent":
                    vo.Transparency = int(transparency)
                    vo.DisplayMode = "Shaded"
                elif mode == "wireframe":
                    vo.Transparency = 0
                    vo.DisplayMode = "Wireframe"
                elif mode == "solid":
                    vo.Transparency = 0
                    vo.DisplayMode = "Shaded"
                else:
                    return {"success": False, "error": f"Unknown mode: {mode}. Use: solid, transparent, wireframe"}
                
                return {"success": True, "object": obj_name, "mode": mode, "transparency": vo.Transparency}
            except Exception as e:
                return {"success": False, "error": f"Failed to set display mode: {e}"}
        
        elif name == "set_clipping_plane":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                
                axis = arguments.get("axis", "X").upper()
                try:
                    percent = float(arguments.get("percent", 50.0))
                except (TypeError, ValueError):
                    return {"success": False, "error": "percent must be a number between 0 and 100"}
                enabled = arguments.get("enabled", True)
                
                if axis not in ["X", "Y", "Z"]:
                    return {"success": False, "error": f"Invalid axis: {axis}. Use X, Y, or Z"}
                if percent < 0 or percent > 100:
                    return {"success": False, "error": "Percent must be between 0 and 100"}
                
                if FreeCADGui.ActiveDocument is None:
                    return {"success": False, "error": "No active document with view"}
                
                view = FreeCADGui.ActiveDocument.ActiveView
                if view is None:
                    return {"success": False, "error": "No active view"}
                
                # Prefer the ActiveView API; fall back to underlying viewer
                viewer = None
                try:
                    viewer = view.getViewer()
                except Exception:
                    viewer = None
                
                toggle_handler = None
                if hasattr(view, "toggleClippingPlane"):
                    def _toggle_clip(toggle_val: int, placement: FreeCAD.Placement):
                        try:
                            view.toggleClippingPlane(toggle_val, False, True, placement)
                        except TypeError:
                            view.toggleClippingPlane(toggle_val)
                    toggle_handler = _toggle_clip
                elif viewer is not None and hasattr(viewer, "toggleClippingPlane"):
                    def _toggle_clip(toggle_val: int, placement: FreeCAD.Placement):
                        try:
                            viewer.toggleClippingPlane(toggle_val, False, True, placement)
                        except TypeError:
                            viewer.toggleClippingPlane(toggle_val)
                    toggle_handler = _toggle_clip
                
                if toggle_handler is None:
                    return {"success": False, "error": "Viewer does not support clipping planes"}
                
                # Always remove any existing clip plane so we can reapply with new settings
                try:
                    toggle_handler(0, FreeCAD.Placement())
                except Exception as e:
                    return {"success": False, "error": f"Failed to reset clipping plane: {e}"}
                # Also remove any fallback Coin3D clip plane we may have added
                try:
                    from pivy import coin
                    if viewer is not None and hasattr(viewer, "getSoRenderManager"):
                        sg = viewer.getSoRenderManager().getSceneGraph()
                        clip_name = "MCP_ClipPlane"
                        for i in range(sg.getNumChildren()):
                            child = sg.getChild(i)
                            if hasattr(child, "getName") and child.getName() == clip_name:
                                sg.removeChild(i)
                                break
                except ImportError:
                    pass
                except Exception:
                    pass
                
                if not enabled:
                    QtWidgets.QApplication.processEvents()
                    return {"success": True, "clipping": False}
                
                # Get bounding box to calculate position
                bbox = get_scene_bounding_box()
                if not bbox:
                    return {"success": False, "error": "No objects in scene to clip"}
                
                axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]
                min_val = bbox["min"][axis_idx]
                max_val = bbox["max"][axis_idx]
                position = min_val + (max_val - min_val) * (percent / 100.0)
                
                normal = FreeCAD.Vector(0, 0, 0)
                point = FreeCAD.Vector(0, 0, 0)
                if axis == "X":
                    normal = FreeCAD.Vector(1, 0, 0)
                    point = FreeCAD.Vector(position, 0, 0)
                elif axis == "Y":
                    normal = FreeCAD.Vector(0, 1, 0)
                    point = FreeCAD.Vector(0, position, 0)
                else:  # Z
                    normal = FreeCAD.Vector(0, 0, 1)
                    point = FreeCAD.Vector(0, 0, position)
                
                # Align FreeCAD's clip plane with the requested axis and location
                rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, -1), normal)
                placement = FreeCAD.Placement(point, rotation)
                
                # Apply via viewer API, then fall back to Coin3D insertion if needed
                clip_applied = False
                try:
                    toggle_handler(1, placement)
                    # Verify if the viewer reports a clipping plane
                    for candidate in (view, viewer):
                        if candidate and hasattr(candidate, "hasClippingPlane"):
                            try:
                                if candidate.hasClippingPlane():
                                    clip_applied = True
                                    break
                            except Exception:
                                pass
                except Exception as e:
                    return {"success": False, "error": f"Failed to apply clipping plane: {e}"}
                
                if not clip_applied:
                    try:
                        from pivy import coin
                        # Remove any existing fallback clip
                        if viewer is not None and hasattr(viewer, "getSoRenderManager"):
                            sg = viewer.getSoRenderManager().getSceneGraph()
                            clip_name = "MCP_ClipPlane"
                            for i in range(sg.getNumChildren()):
                                child = sg.getChild(i)
                                if hasattr(child, "getName") and child.getName() == clip_name:
                                    sg.removeChild(i)
                                    break
                            
                            clip = coin.SoClipPlane()
                            clip.setName(clip_name)
                            plane = coin.SbPlane(
                                coin.SbVec3f(normal.x, normal.y, normal.z),
                                coin.SbVec3f(point.x, point.y, point.z)
                            )
                            clip.plane.setValue(plane)
                            clip.on.setValue(True)
                            sg.insertChild(clip, 0)
                            clip_applied = True
                    except ImportError:
                        pass
                    except Exception as e:
                        FreeCAD.Console.PrintWarning(f"Fallback clip plane failed: {e}\n")
                
                QtWidgets.QApplication.processEvents()
                
                return {
                    "success": True,
                    "clipping": True,
                    "axis": axis,
                    "percent": percent,
                    "position_mm": round(position, 2)
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to set clipping plane: {e}"}
        
        # === Camera Navigation Tools ===
        elif name == "zoom":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                import math

                if not getattr(FreeCAD, "GuiUp", False):
                    return {"success": False, "error": "Zoom requires FreeCAD GUI. Start FreeCAD (not FreeCADCmd/headless) and try again."}
                
                percent = arguments.get("percent", 100)
                doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
                
                if percent <= 0:
                    return {"success": False, "error": "Zoom percent must be positive"}
                
                def apply_zoom(view, zoom_percent):
                    """Apply zoom using the navigation style (avoids direct Coin camera access)."""
                    if zoom_percent == 100:
                        return True
                    
                    factor = zoom_percent / 100.0
                    # Empirical step factor similar to mouse wheel zoom
                    step_factor = 1.1
                    steps = max(1, int(abs(math.log(factor) / math.log(step_factor)) + 0.5))
                    
                    try:
                        for _ in range(steps):
                            if factor > 1.0:
                                view.zoomIn()
                            else:
                                view.zoomOut()
                        return True
                    except Exception as e:
                        FreeCAD.Console.PrintWarning(f"Zoom failed: {e}\n")
                        return False
                
                # Determine which documents to apply zoom to
                docs_to_update = []
                if is_dual_mode():
                    if doc_param == "target":
                        docs_to_update = [_target_doc_name]
                    elif doc_param == "work":
                        docs_to_update = [_work_doc_name]
                    elif doc_param == "both":
                        docs_to_update = [_target_doc_name, _work_doc_name]
                    else:
                        docs_to_update = [_work_doc_name]
                else:
                    if FreeCADGui.ActiveDocument is None:
                        return {"success": False, "error": "No active document with view"}
                    docs_to_update = [FreeCAD.ActiveDocument.Name]
                
                updated_docs = []
                for doc_name in docs_to_update:
                    if activate_document(doc_name):
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            if apply_zoom(gui_doc.ActiveView, percent):
                                updated_docs.append(doc_name)
                
                QtWidgets.QApplication.processEvents()
                
                return {"success": True, "zoom_percent": percent, "documents": updated_docs}
            except Exception as e:
                return {"success": False, "error": f"Failed to zoom: {e}"}
        
        elif name == "pan":
            try:
                import FreeCADGui
                from PySide2 import QtWidgets

                if not getattr(FreeCAD, "GuiUp", False):
                    return {"success": False, "error": "Pan requires FreeCAD GUI. Start FreeCAD (not FreeCADCmd/headless) and try again."}
                
                x_percent = arguments.get("x", 0)
                y_percent = arguments.get("y", 0)
                doc_param = arguments.get("doc", "work" if is_dual_mode() else None)
                
                def apply_pan(view, pan_x, pan_y):
                    """Apply pan using camera placement (avoids direct Coin camera access)."""
                    try:
                        current_pl = view.viewPosition()  # returns FreeCAD.Placement
                        if not current_pl:
                            return False
                        
                        # Scene scale to keep pan movement reasonable
                        bbox = get_scene_bounding_box()
                        scene_span = max(bbox["size"]) if bbox else 100.0
                        scale = scene_span * 0.01  # 1% of span per 1% pan input
                        
                        right = current_pl.Rotation.multVec(FreeCAD.Vector(1, 0, 0))
                        up = current_pl.Rotation.multVec(FreeCAD.Vector(0, 1, 0))
                        
                        offset = right * (pan_x * scale) + up * (pan_y * scale)
                        new_pos = current_pl.Base + offset
                        
                        new_pl = FreeCAD.Placement(new_pos, current_pl.Rotation)
                        view.viewPosition(new_pl)
                        return True
                    except Exception as e:
                        FreeCAD.Console.PrintWarning(f"Pan failed: {e}\n")
                        return False
                
                # Determine which documents to apply pan to
                docs_to_update = []
                if is_dual_mode():
                    if doc_param == "target":
                        docs_to_update = [_target_doc_name]
                    elif doc_param == "work":
                        docs_to_update = [_work_doc_name]
                    elif doc_param == "both":
                        docs_to_update = [_target_doc_name, _work_doc_name]
                    else:
                        docs_to_update = [_work_doc_name]
                else:
                    if FreeCADGui.ActiveDocument is None:
                        return {"success": False, "error": "No active document with view"}
                    docs_to_update = [FreeCAD.ActiveDocument.Name]
                
                updated_docs = []
                for doc_name in docs_to_update:
                    if activate_document(doc_name):
                        gui_doc = FreeCADGui.getDocument(doc_name)
                        if gui_doc and gui_doc.ActiveView:
                            if apply_pan(gui_doc.ActiveView, x_percent, y_percent):
                                updated_docs.append(doc_name)
                
                QtWidgets.QApplication.processEvents()
                
                return {"success": True, "pan_x": x_percent, "pan_y": y_percent, "documents": updated_docs}
            except Exception as e:
                return {"success": False, "error": f"Failed to pan: {e}"}
        
        # === Measurement Mode Tools ===
        elif name == "start_measurement":
            _measurement_mode = True
            _grid_config["enabled"] = True
            _grid_config["region"] = {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
            
            # Capture screenshot with grid
            screenshot = capture_with_grid_and_labels()
            
            result = {
                "success": True,
                "measurement_mode": True,
                "grid": {
                    "columns": _grid_config["columns"],
                    "rows": _grid_config["rows"]
                },
                "message": "Measurement mode active. Use grid coordinates (A1-H6) to select points."
            }
            if screenshot:
                result["screenshot"] = screenshot
            
            return result
        
        elif name == "end_measurement":
            _measurement_mode = False
            _grid_config["enabled"] = False
            
            # Clear pending points (keep confirmed ones)
            cleared_pending = list(_pending_points.keys())
            for point_id in cleared_pending:
                info = _pending_points.pop(point_id, None)
                if info and info.get("marker"):
                    try:
                        doc.removeObject(info["marker"].Name)
                    except:
                        pass
            
            return {
                "success": True,
                "measurement_mode": False,
                "cleared_pending": cleared_pending,
                "confirmed_points": list(_confirmed_points.keys())
            }
        
        elif name == "zoom_grid_region":
            if not _measurement_mode:
                return {"success": False, "error": "Not in measurement mode. Call start_measurement first."}
            
            try:
                start_cell = arguments.get("start_cell", "A1")
                size = arguments.get("size", 2)
                
                col, row = parse_grid_cell(start_cell)
                
                # Validate
                cols = _grid_config["columns"]
                rows = _grid_config["rows"]
                
                if col < 0 or col >= cols or row < 0 or row >= rows:
                    return {"success": False, "error": f"Invalid cell: {start_cell}"}
                
                if size < 1 or size > min(cols, rows):
                    return {"success": False, "error": f"Invalid size: {size}. Must be 1-{min(cols, rows)}"}
                
                # Calculate new region bounds (as fraction of current region)
                current = _grid_config["region"]
                cell_width = (current["x_max"] - current["x_min"]) / cols
                cell_height = (current["y_max"] - current["y_min"]) / rows
                
                new_x_min = current["x_min"] + col * cell_width
                new_x_max = min(current["x_max"], new_x_min + size * cell_width)
                new_y_min = current["y_min"] + row * cell_height
                new_y_max = min(current["y_max"], new_y_min + size * cell_height)
                
                _grid_config["region"] = {
                    "x_min": new_x_min,
                    "x_max": new_x_max,
                    "y_min": new_y_min,
                    "y_max": new_y_max
                }
                
                # Also zoom the camera to this region
                # This is approximate - zoom in by the inverse of the region size
                zoom_factor = 1.0 / (size / cols)
                
                try:
                    import FreeCADGui
                    from PySide2 import QtWidgets
                    
                    if FreeCADGui.ActiveDocument and FreeCADGui.ActiveDocument.ActiveView:
                        view = FreeCADGui.ActiveDocument.ActiveView
                        cam = view.getCameraNode()
                        if cam:
                            current_height = cam.height.getValue()
                            cam.height.setValue(current_height / zoom_factor)
                        QtWidgets.QApplication.processEvents()
                except:
                    pass
                
                # Capture with new grid
                screenshot = capture_with_grid_and_labels()
                
                result = {
                    "success": True,
                    "zoomed_to": f"{start_cell} (size {size})",
                    "region": _grid_config["region"],
                    "message": f"Zoomed to region starting at {start_cell}. Grid now covers this zoomed area."
                }
                if screenshot:
                    result["screenshot"] = screenshot
                
                return result
                
            except ValueError as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": f"Failed to zoom grid region: {e}"}
        
        elif name == "reset_grid_zoom":
            _grid_config["region"] = {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
            
            # Fit camera to show all
            try:
                import FreeCADGui
                from PySide2 import QtWidgets
                
                if FreeCADGui.ActiveDocument and FreeCADGui.ActiveDocument.ActiveView:
                    FreeCADGui.ActiveDocument.ActiveView.fitAll()
                    QtWidgets.QApplication.processEvents()
            except:
                pass
            
            # Capture with reset grid
            screenshot = capture_with_grid_and_labels()
            
            result = {
                "success": True,
                "message": "Grid zoom reset to full view."
            }
            if screenshot:
                result["screenshot"] = screenshot
            
            return result
        
        elif name == "select_point":
            try:
                import FreeCADGui
                import Part
                from PySide2 import QtWidgets
                
                grid_cell = arguments.get("grid_cell", "A1")
                offset_x = arguments.get("offset_x", 0.5)
                offset_y = arguments.get("offset_y", 0.5)
                
                # Parse grid cell
                col, row = parse_grid_cell(grid_cell)
                
                cols = _grid_config["columns"]
                rows = _grid_config["rows"]
                
                if col < 0 or col >= cols or row < 0 or row >= rows:
                    return {"success": False, "error": f"Invalid grid cell: {grid_cell}. Use A1-{chr(ord('A')+cols-1)}{rows}"}
                
                if FreeCADGui.ActiveDocument is None:
                    return {"success": False, "error": "No active document with view"}
                
                view = FreeCADGui.ActiveDocument.ActiveView
                if view is None:
                    return {"success": False, "error": "No active view"}
                
                # Get viewport size
                try:
                    view_size = view.getSize()
                    view_width, view_height = view_size[0], view_size[1]
                except:
                    view_width, view_height = 800, 600
                
                # Calculate pixel position (respecting grid region/zoom)
                region = _grid_config["region"]
                
                # Normalized position within current grid region
                norm_x = region["x_min"] + (col + offset_x) / cols * (region["x_max"] - region["x_min"])
                norm_y = region["y_min"] + (row + offset_y) / rows * (region["y_max"] - region["y_min"])
                
                # Convert to pixel coordinates
                pixel_x = int(norm_x * view_width)
                pixel_y = int(norm_y * view_height)
                
                # Ray cast from camera through this pixel
                # Try different methods depending on FreeCAD version
                point_3d = None
                
                try:
                    # Method 1: getPointOnScreen (older versions)
                    point_3d = view.getPointOnScreen(pixel_x, pixel_y)
                except:
                    pass
                
                if point_3d is None:
                    try:
                        # Method 2: getObjectInfo
                        info = view.getObjectInfo((pixel_x, pixel_y))
                        if info and "x" in info:
                            point_3d = FreeCAD.Vector(info["x"], info["y"], info["z"])
                    except:
                        pass
                
                if point_3d is None:
                    return {
                        "success": False,
                        "error": f"No surface at grid cell {grid_cell}. Try a different cell or adjust view."
                    }
                
                # Create marker sphere
                _point_counter += 1
                point_id = f"point_{_point_counter}"
                
                marker_radius = estimate_marker_size()
                color_idx = (_point_counter - 1) % len(_marker_colors)
                color = _marker_colors[color_idx]
                
                if doc is None:
                    doc = FreeCAD.ActiveDocument
                
                marker = doc.addObject("Part::Sphere", f"Marker_{point_id}")
                marker.Radius = marker_radius
                marker.Placement.Base = point_3d
                doc.recompute()
                
                # Set marker appearance
                if hasattr(marker, "ViewObject") and marker.ViewObject:
                    marker.ViewObject.ShapeColor = color
                    marker.ViewObject.Transparency = 0
                
                QtWidgets.QApplication.processEvents()
                
                # Store in pending points
                _pending_points[point_id] = {
                    "coords": point_3d,
                    "marker": marker,
                    "grid_cell": grid_cell
                }
                
                # Capture screenshot with grid and labels
                screenshot = capture_with_grid_and_labels()
                
                result = {
                    "success": True,
                    "point_id": point_id,
                    "grid_cell": grid_cell,
                    "coordinates": {
                        "x": round(point_3d.x, 3),
                        "y": round(point_3d.y, 3),
                        "z": round(point_3d.z, 3)
                    },
                    "status": "pending_confirmation",
                    "message": f"Point placed at {point_id}. Call confirm_point('{point_id}') to lock it in, or clear_point('{point_id}') to remove."
                }
                if screenshot:
                    result["screenshot"] = screenshot
                
                return result
                
            except ValueError as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": f"Failed to select point: {e}"}
        
        elif name == "confirm_point":
            point_id = arguments.get("point_id")
            if not point_id:
                return {"success": False, "error": "point_id is required"}
            
            if point_id not in _pending_points:
                if point_id in _confirmed_points:
                    return {"success": False, "error": f"Point {point_id} is already confirmed"}
                return {"success": False, "error": f"Point {point_id} not found in pending points"}
            
            # Move from pending to confirmed
            point_info = _pending_points.pop(point_id)
            _confirmed_points[point_id] = point_info
            
            coords = point_info["coords"]
            
            return {
                "success": True,
                "point_id": point_id,
                "status": "confirmed",
                "coordinates": {
                    "x": round(coords.x, 3),
                    "y": round(coords.y, 3),
                    "z": round(coords.z, 3)
                },
                "message": f"Point {point_id} confirmed. You can now use it in measure_distance."
            }
        
        elif name == "clear_point":
            point_id = arguments.get("point_id")
            if not point_id:
                return {"success": False, "error": "point_id is required"}
            
            cleared = []
            
            if point_id == "all":
                # Clear all points
                for pid in list(_pending_points.keys()):
                    info = _pending_points.pop(pid)
                    if info.get("marker"):
                        try:
                            doc.removeObject(info["marker"].Name)
                        except:
                            pass
                    cleared.append(pid)
                
                for pid in list(_confirmed_points.keys()):
                    info = _confirmed_points.pop(pid)
                    if info.get("marker"):
                        try:
                            doc.removeObject(info["marker"].Name)
                        except:
                            pass
                    cleared.append(pid)
            else:
                # Clear specific point
                if point_id in _pending_points:
                    info = _pending_points.pop(point_id)
                    if info.get("marker"):
                        try:
                            doc.removeObject(info["marker"].Name)
                        except:
                            pass
                    cleared.append(point_id)
                elif point_id in _confirmed_points:
                    info = _confirmed_points.pop(point_id)
                    if info.get("marker"):
                        try:
                            doc.removeObject(info["marker"].Name)
                        except:
                            pass
                    cleared.append(point_id)
                else:
                    return {"success": False, "error": f"Point {point_id} not found"}
            
            if doc:
                doc.recompute()
            
            return {"success": True, "cleared": cleared}
        
        elif name == "list_points":
            points = []
            
            for pid, info in _pending_points.items():
                coords = info.get("coords")
                points.append({
                    "point_id": pid,
                    "status": "pending",
                    "grid_cell": info.get("grid_cell"),
                    "coordinates": {
                        "x": round(coords.x, 3),
                        "y": round(coords.y, 3),
                        "z": round(coords.z, 3)
                    } if coords else None
                })
            
            for pid, info in _confirmed_points.items():
                coords = info.get("coords")
                points.append({
                    "point_id": pid,
                    "status": "confirmed",
                    "grid_cell": info.get("grid_cell"),
                    "coordinates": {
                        "x": round(coords.x, 3),
                        "y": round(coords.y, 3),
                        "z": round(coords.z, 3)
                    } if coords else None
                })
            
            return {
                "success": True,
                "points": points,
                "pending_count": len(_pending_points),
                "confirmed_count": len(_confirmed_points)
            }
        
        elif name == "measure_distance":
            point_a_id = arguments.get("point_a")
            point_b_id = arguments.get("point_b")
            
            if not point_a_id or not point_b_id:
                return {"success": False, "error": "Both point_a and point_b are required"}
            
            if point_a_id not in _confirmed_points:
                return {"success": False, "error": f"Point {point_a_id} not found or not confirmed"}
            if point_b_id not in _confirmed_points:
                return {"success": False, "error": f"Point {point_b_id} not found or not confirmed"}
            
            try:
                import Part
                
                p1 = _confirmed_points[point_a_id]["coords"]
                p2 = _confirmed_points[point_b_id]["coords"]
                
                # Calculate distance
                distance = p1.distanceToPoint(p2)
                
                # Create visual line between points
                if doc is None:
                    doc = FreeCAD.ActiveDocument
                
                line_name = f"Measurement_{point_a_id}_{point_b_id}"
                line_shape = Part.makeLine(p1, p2)
                line_obj = doc.addObject("Part::Feature", line_name)
                line_obj.Shape = line_shape
                doc.recompute()
                
                # Style the line
                if hasattr(line_obj, "ViewObject") and line_obj.ViewObject:
                    line_obj.ViewObject.LineColor = (1.0, 0.0, 0.0)  # Red
                    line_obj.ViewObject.LineWidth = 3.0
                
                _measurement_objects.append(line_obj)
                
                # Capture screenshot
                screenshot = capture_with_grid_and_labels()
                
                result = {
                    "success": True,
                    "distance_mm": round(distance, 4),
                    "point_a": {
                        "id": point_a_id,
                        "coordinates": {"x": round(p1.x, 3), "y": round(p1.y, 3), "z": round(p1.z, 3)}
                    },
                    "point_b": {
                        "id": point_b_id,
                        "coordinates": {"x": round(p2.x, 3), "y": round(p2.y, 3), "z": round(p2.z, 3)}
                    },
                    "measurement_line": line_name
                }
                if screenshot:
                    result["screenshot"] = screenshot
                
                return result
                
            except Exception as e:
                return {"success": False, "error": f"Failed to measure distance: {e}"}
        
        elif name == "clear_measurements":
            cleared = []
            
            # Clear measurement lines
            for obj in _measurement_objects:
                try:
                    if doc and doc.getObject(obj.Name):
                        doc.removeObject(obj.Name)
                        cleared.append(obj.Name)
                except:
                    pass
            _measurement_objects = []
            
            # Also clear all points
            for pid in list(_pending_points.keys()):
                info = _pending_points.pop(pid)
                if info.get("marker"):
                    try:
                        doc.removeObject(info["marker"].Name)
                        cleared.append(info["marker"].Name)
                    except:
                        pass
            
            for pid in list(_confirmed_points.keys()):
                info = _confirmed_points.pop(pid)
                if info.get("marker"):
                    try:
                        doc.removeObject(info["marker"].Name)
                        cleared.append(info["marker"].Name)
                    except:
                        pass
            
            if doc:
                doc.recompute()
            
            return {"success": True, "cleared": cleared}
        
        elif name == "list_tools":
            return {"success": True, "tools": TOOLS}
        
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}
    
    # Execute the tool
    result = _bridge.execute_sync(_execute)
    
    # Auto-append screenshot to successful responses (if GUI available)
    if _auto_screenshot_enabled and result.get("success", False):
        # Skip screenshot for list_tools and get_mesh_points (large data responses)
        skip_screenshot_tools = {"list_tools", "get_mesh_points", "take_screenshot"}
        if name not in skip_screenshot_tools:
            # Run capture on the main thread to avoid GUI thread crashes
            def _capture_screenshot():
                if is_dual_mode():
                    return capture_split_view()
                return capture_viewport_base64()
            
            try:
                screenshot = _bridge.execute_sync(_capture_screenshot)
            except Exception as e:
                FreeCAD.Console.PrintWarning(f"Auto screenshot failed: {e}\n")
                screenshot = None
            if screenshot:
                result["screenshot"] = screenshot
    
    return result


class SimpleMCPServer:
    """Simple TCP server for MCP-like communication."""
    
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.socket = None
        self.running = False
    
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('127.0.0.1', self.port))
        self.socket.listen(5)
        self.socket.settimeout(1.0)
        self.running = True
        
        FreeCAD.Console.PrintMessage(f"MCP Server listening on port {self.port}\n")
        
        while self.running:
            try:
                client, addr = self.socket.accept()
                self._handle_client(client)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    FreeCAD.Console.PrintError(f"Server error: {e}\n")
    
    def _handle_client(self, client):
        try:
            client.settimeout(30.0)
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            
            if data:
                request = json.loads(data.decode('utf-8').strip())
                tool_name = request.get("tool", request.get("method", ""))
                arguments = request.get("arguments", request.get("params", {}))
                
                if tool_name == "list_tools":
                    response = {"success": True, "tools": TOOLS}
                else:
                    response = execute_tool(tool_name, arguments)
                
                client.sendall((json.dumps(response) + "\n").encode('utf-8'))
        except Exception as e:
            try:
                client.sendall((json.dumps({"success": False, "error": str(e)}) + "\n").encode('utf-8'))
            except:
                pass
        finally:
            client.close()
    
    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()


def start(port: int = DEFAULT_PORT, use_stdio: bool = False) -> Tuple['SimpleMCPServer', threading.Thread]:
    """Start the MCP server."""
    global _server, _bridge, _server_thread
    
    if _server is not None:
        FreeCAD.Console.PrintWarning("MCP Server already running\n")
        return _server, _server_thread
    
    _bridge = get_bridge()
    _server = SimpleMCPServer(port)
    
    _server_thread = threading.Thread(target=_server.start, daemon=True)
    _server_thread.start()
    
    FreeCAD.Console.PrintMessage(f"MCP Server started on port {port}\n")
    FreeCAD.Console.PrintMessage("Connect with: echo '{\"tool\":\"list_tools\"}' | nc localhost 9876\n")
    
    return _server, _server_thread


def stop(server=None, thread=None):
    """Stop the MCP server."""
    global _server, _server_thread
    
    if _server:
        _server.stop()
    
    _server = None
    _server_thread = None
    reset_bridge()
    
    FreeCAD.Console.PrintMessage("MCP Server stopped\n")


def get_server():
    return _server
