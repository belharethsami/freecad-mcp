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
        
        # Force GUI update before capturing
        QtWidgets.QApplication.processEvents()
        view.fitAll()
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
        
        # Force GUI update before capturing
        view.fitAll()
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
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool on the main thread."""
    
    def _execute():
        global _target_doc_name, _work_doc_name, _dual_mode_enabled
        
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
