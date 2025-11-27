# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - PartDesign Workflow Tools

Tools for parametric modeling using FreeCAD's PartDesign workbench:
- Creating bodies and sketches
- Adding sketch geometry (lines, circles, rectangles, arcs)
- Adding sketch constraints
- Creating features (pad, pocket, revolve, fillet, chamfer)
"""

from typing import Optional, Dict, Any, List, Tuple
import FreeCAD

from ..bridge import MainThreadBridge


def register_partdesign_tools(server, bridge: MainThreadBridge):
    """Register PartDesign workflow tools with the MCP server."""
    
    # ==================== Body Management ====================
    
    @server.tool()
    async def create_body(name: str = "Body") -> Dict[str, Any]:
        """
        Create a new PartDesign Body.
        
        A Body is the container for parametric PartDesign features.
        
        Args:
            name: Name for the body (default: "Body")
        
        Returns:
            Dictionary with body info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            body = doc.addObject("PartDesign::Body", name)
            doc.recompute()
            
            return {
                "success": True,
                "name": body.Name,
                "label": body.Label,
                "type": "PartDesign::Body",
                "message": f"Created PartDesign body '{body.Name}'"
            }
        
        return await bridge.execute(_create)
    
    # ==================== Sketch Management ====================
    
    @server.tool()
    async def create_sketch(
        body: str,
        plane: str = "XY",
        name: str = "Sketch",
        offset: float = 0.0
    ) -> Dict[str, Any]:
        """
        Create a new sketch attached to a body.
        
        Args:
            body: Name of the PartDesign body to attach to
            plane: Base plane - "XY", "XZ", or "YZ" (default: "XY")
            name: Name for the sketch (default: "Sketch")
            offset: Offset from the plane in mm
        
        Returns:
            Dictionary with sketch info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            body_obj = doc.getObject(body)
            if body_obj is None:
                return {"success": False, "error": f"Body '{body}' not found"}
            
            # Create sketch
            sketch = doc.addObject("Sketcher::SketchObject", name)
            
            # Map plane name to support
            plane_map = {
                "XY": (FreeCAD.Vector(0, 0, 1), FreeCAD.Vector(1, 0, 0)),
                "XZ": (FreeCAD.Vector(0, 1, 0), FreeCAD.Vector(1, 0, 0)),
                "YZ": (FreeCAD.Vector(1, 0, 0), FreeCAD.Vector(0, 1, 0)),
            }
            
            if plane.upper() not in plane_map:
                return {"success": False, "error": f"Invalid plane '{plane}'. Use XY, XZ, or YZ"}
            
            normal, x_dir = plane_map[plane.upper()]
            
            # Set sketch placement
            sketch.Placement = FreeCAD.Placement(
                FreeCAD.Vector(0, 0, offset) if plane.upper() == "XY" else
                FreeCAD.Vector(0, offset, 0) if plane.upper() == "XZ" else
                FreeCAD.Vector(offset, 0, 0),
                FreeCAD.Rotation(normal, 0)
            )
            
            # Add sketch to body
            body_obj.addObject(sketch)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": sketch.Name,
                "label": sketch.Label,
                "body": body,
                "plane": plane,
                "type": "Sketcher::SketchObject",
                "message": f"Created sketch '{sketch.Name}' on {plane} plane"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def add_sketch_line(
        sketch: str,
        x1: float, y1: float,
        x2: float, y2: float,
        construction: bool = False
    ) -> Dict[str, Any]:
        """
        Add a line to a sketch.
        
        Args:
            sketch: Name of the sketch
            x1, y1: Start point coordinates in mm
            x2, y2: End point coordinates in mm
            construction: If True, create as construction geometry
        
        Returns:
            Dictionary with geometry index info
        """
        def _add():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Create line geometry
            line = Part.LineSegment(
                FreeCAD.Vector(x1, y1, 0),
                FreeCAD.Vector(x2, y2, 0)
            )
            
            # Add to sketch
            geo_index = sketch_obj.addGeometry(line, construction)
            
            doc.recompute()
            
            return {
                "success": True,
                "sketch": sketch,
                "geometry_index": geo_index,
                "type": "Line",
                "start": [x1, y1],
                "end": [x2, y2],
                "construction": construction,
                "message": f"Added line to sketch '{sketch}' (index {geo_index})"
            }
        
        return await bridge.execute(_add)
    
    @server.tool()
    async def add_sketch_circle(
        sketch: str,
        cx: float, cy: float,
        radius: float,
        construction: bool = False
    ) -> Dict[str, Any]:
        """
        Add a circle to a sketch.
        
        Args:
            sketch: Name of the sketch
            cx, cy: Center point coordinates in mm
            radius: Circle radius in mm
            construction: If True, create as construction geometry
        
        Returns:
            Dictionary with geometry index info
        """
        def _add():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Create circle geometry
            circle = Part.Circle(
                FreeCAD.Vector(cx, cy, 0),
                FreeCAD.Vector(0, 0, 1),
                radius
            )
            
            # Add to sketch
            geo_index = sketch_obj.addGeometry(circle, construction)
            
            doc.recompute()
            
            return {
                "success": True,
                "sketch": sketch,
                "geometry_index": geo_index,
                "type": "Circle",
                "center": [cx, cy],
                "radius": radius,
                "construction": construction,
                "message": f"Added circle to sketch '{sketch}' (index {geo_index})"
            }
        
        return await bridge.execute(_add)
    
    @server.tool()
    async def add_sketch_rectangle(
        sketch: str,
        x1: float, y1: float,
        x2: float, y2: float,
        construction: bool = False
    ) -> Dict[str, Any]:
        """
        Add a rectangle to a sketch (as 4 lines).
        
        Args:
            sketch: Name of the sketch
            x1, y1: First corner coordinates in mm
            x2, y2: Opposite corner coordinates in mm
            construction: If True, create as construction geometry
        
        Returns:
            Dictionary with geometry indices info
        """
        def _add():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Create 4 lines for rectangle
            lines = [
                Part.LineSegment(FreeCAD.Vector(x1, y1, 0), FreeCAD.Vector(x2, y1, 0)),  # Bottom
                Part.LineSegment(FreeCAD.Vector(x2, y1, 0), FreeCAD.Vector(x2, y2, 0)),  # Right
                Part.LineSegment(FreeCAD.Vector(x2, y2, 0), FreeCAD.Vector(x1, y2, 0)),  # Top
                Part.LineSegment(FreeCAD.Vector(x1, y2, 0), FreeCAD.Vector(x1, y1, 0)),  # Left
            ]
            
            # Add lines to sketch
            indices = []
            for line in lines:
                idx = sketch_obj.addGeometry(line, construction)
                indices.append(idx)
            
            # Add coincident constraints to close the rectangle
            sketch_obj.addConstraint(FreeCAD.Sketcher.Constraint("Coincident", indices[0], 2, indices[1], 1))
            sketch_obj.addConstraint(FreeCAD.Sketcher.Constraint("Coincident", indices[1], 2, indices[2], 1))
            sketch_obj.addConstraint(FreeCAD.Sketcher.Constraint("Coincident", indices[2], 2, indices[3], 1))
            sketch_obj.addConstraint(FreeCAD.Sketcher.Constraint("Coincident", indices[3], 2, indices[0], 1))
            
            doc.recompute()
            
            return {
                "success": True,
                "sketch": sketch,
                "geometry_indices": indices,
                "type": "Rectangle",
                "corner1": [x1, y1],
                "corner2": [x2, y2],
                "width": abs(x2 - x1),
                "height": abs(y2 - y1),
                "construction": construction,
                "message": f"Added rectangle to sketch '{sketch}'"
            }
        
        return await bridge.execute(_add)
    
    @server.tool()
    async def add_sketch_arc(
        sketch: str,
        cx: float, cy: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        construction: bool = False
    ) -> Dict[str, Any]:
        """
        Add an arc to a sketch.
        
        Args:
            sketch: Name of the sketch
            cx, cy: Center point coordinates in mm
            radius: Arc radius in mm
            start_angle: Start angle in degrees
            end_angle: End angle in degrees
            construction: If True, create as construction geometry
        
        Returns:
            Dictionary with geometry index info
        """
        def _add():
            import Part
            import math
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Convert angles to radians
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            
            # Create arc geometry
            arc = Part.ArcOfCircle(
                Part.Circle(
                    FreeCAD.Vector(cx, cy, 0),
                    FreeCAD.Vector(0, 0, 1),
                    radius
                ),
                start_rad,
                end_rad
            )
            
            # Add to sketch
            geo_index = sketch_obj.addGeometry(arc, construction)
            
            doc.recompute()
            
            return {
                "success": True,
                "sketch": sketch,
                "geometry_index": geo_index,
                "type": "Arc",
                "center": [cx, cy],
                "radius": radius,
                "start_angle": start_angle,
                "end_angle": end_angle,
                "construction": construction,
                "message": f"Added arc to sketch '{sketch}' (index {geo_index})"
            }
        
        return await bridge.execute(_add)
    
    @server.tool()
    async def close_sketch(sketch: str) -> Dict[str, Any]:
        """
        Close a sketch (finish editing).
        
        Args:
            sketch: Name of the sketch to close
        
        Returns:
            Dictionary with result info
        """
        def _close():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            doc.recompute()
            
            # Check if sketch is valid (closed profiles for features)
            wire_count = len(sketch_obj.Shape.Wires) if hasattr(sketch_obj, "Shape") else 0
            
            return {
                "success": True,
                "sketch": sketch,
                "geometry_count": sketch_obj.GeometryCount,
                "constraint_count": sketch_obj.ConstraintCount,
                "wire_count": wire_count,
                "message": f"Sketch '{sketch}' ready with {sketch_obj.GeometryCount} geometry elements"
            }
        
        return await bridge.execute(_close)
    
    # ==================== PartDesign Features ====================
    
    @server.tool()
    async def pad_sketch(
        sketch: str,
        length: float,
        name: str = "Pad",
        symmetric: bool = False,
        reversed: bool = False
    ) -> Dict[str, Any]:
        """
        Create a Pad (extrusion) feature from a sketch.
        
        Args:
            sketch: Name of the sketch to extrude
            length: Extrusion length in mm
            name: Name for the pad feature (default: "Pad")
            symmetric: If True, extrude symmetrically in both directions
            reversed: If True, extrude in the opposite direction
        
        Returns:
            Dictionary with feature info
        """
        def _pad():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Find the body containing this sketch
            body = None
            for obj in doc.Objects:
                if obj.TypeId == "PartDesign::Body":
                    if sketch_obj in obj.Group:
                        body = obj
                        break
            
            if body is None:
                return {"success": False, "error": f"Sketch '{sketch}' is not in a PartDesign body"}
            
            # Create pad feature
            pad = doc.addObject("PartDesign::Pad", name)
            pad.Profile = sketch_obj
            pad.Length = length
            pad.Symmetric = symmetric
            pad.Reversed = reversed
            
            # Add to body
            body.addObject(pad)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": pad.Name,
                "label": pad.Label,
                "type": "PartDesign::Pad",
                "sketch": sketch,
                "length": length,
                "volume": body.Shape.Volume if hasattr(body, "Shape") else None,
                "message": f"Created pad '{pad.Name}' with length {length} mm"
            }
        
        return await bridge.execute(_pad)
    
    @server.tool()
    async def pocket_sketch(
        sketch: str,
        depth: float,
        name: str = "Pocket",
        through_all: bool = False,
        reversed: bool = False
    ) -> Dict[str, Any]:
        """
        Create a Pocket (cut) feature from a sketch.
        
        Args:
            sketch: Name of the sketch defining the pocket profile
            depth: Pocket depth in mm (ignored if through_all is True)
            name: Name for the pocket feature (default: "Pocket")
            through_all: If True, cut through the entire part
            reversed: If True, cut in the opposite direction
        
        Returns:
            Dictionary with feature info
        """
        def _pocket():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Find the body containing this sketch
            body = None
            for obj in doc.Objects:
                if obj.TypeId == "PartDesign::Body":
                    if sketch_obj in obj.Group:
                        body = obj
                        break
            
            if body is None:
                return {"success": False, "error": f"Sketch '{sketch}' is not in a PartDesign body"}
            
            # Create pocket feature
            pocket = doc.addObject("PartDesign::Pocket", name)
            pocket.Profile = sketch_obj
            pocket.Reversed = reversed
            
            if through_all:
                pocket.Type = 1  # Through all
            else:
                pocket.Type = 0  # Dimension
                pocket.Length = depth
            
            # Add to body
            body.addObject(pocket)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": pocket.Name,
                "label": pocket.Label,
                "type": "PartDesign::Pocket",
                "sketch": sketch,
                "depth": depth if not through_all else "through all",
                "volume": body.Shape.Volume if hasattr(body, "Shape") else None,
                "message": f"Created pocket '{pocket.Name}'"
            }
        
        return await bridge.execute(_pocket)
    
    @server.tool()
    async def revolve_sketch(
        sketch: str,
        angle: float = 360.0,
        axis: str = "Vertical",
        name: str = "Revolution",
        reversed: bool = False
    ) -> Dict[str, Any]:
        """
        Create a Revolution feature from a sketch.
        
        Args:
            sketch: Name of the sketch to revolve
            angle: Revolution angle in degrees (default: 360 = full revolution)
            axis: Revolution axis - "Vertical", "Horizontal", or a sketch line name
            name: Name for the feature (default: "Revolution")
            reversed: If True, revolve in the opposite direction
        
        Returns:
            Dictionary with feature info
        """
        def _revolve():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Find the body containing this sketch
            body = None
            for obj in doc.Objects:
                if obj.TypeId == "PartDesign::Body":
                    if sketch_obj in obj.Group:
                        body = obj
                        break
            
            if body is None:
                return {"success": False, "error": f"Sketch '{sketch}' is not in a PartDesign body"}
            
            # Create revolution feature
            rev = doc.addObject("PartDesign::Revolution", name)
            rev.Profile = sketch_obj
            rev.Angle = angle
            rev.Reversed = reversed
            
            # Set axis
            if axis.lower() == "vertical":
                rev.Axis = (0, 1, 0)
                rev.Base = (0, 0, 0)
            elif axis.lower() == "horizontal":
                rev.Axis = (1, 0, 0)
                rev.Base = (0, 0, 0)
            
            # Add to body
            body.addObject(rev)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": rev.Name,
                "label": rev.Label,
                "type": "PartDesign::Revolution",
                "sketch": sketch,
                "angle": angle,
                "volume": body.Shape.Volume if hasattr(body, "Shape") else None,
                "message": f"Created revolution '{rev.Name}' with {angle}° rotation"
            }
        
        return await bridge.execute(_revolve)
    
    @server.tool()
    async def fillet_edges(
        body: str,
        radius: float,
        edges: Optional[List[str]] = None,
        name: str = "Fillet"
    ) -> Dict[str, Any]:
        """
        Add fillets (rounded edges) to a body.
        
        Args:
            body: Name of the PartDesign body
            radius: Fillet radius in mm
            edges: Optional list of edge names (e.g., ["Edge1", "Edge2"]). 
                   If not provided, you'll need to select edges manually.
            name: Name for the fillet feature (default: "Fillet")
        
        Returns:
            Dictionary with feature info
        """
        def _fillet():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            body_obj = doc.getObject(body)
            if body_obj is None:
                return {"success": False, "error": f"Body '{body}' not found"}
            
            # Create fillet feature
            fillet = doc.addObject("PartDesign::Fillet", name)
            fillet.Radius = radius
            
            # If edges specified, set them
            if edges and hasattr(body_obj, "Shape"):
                # Find the tip feature (last solid feature in body)
                tip = body_obj.Tip
                if tip and hasattr(tip, "Shape"):
                    refs = []
                    for edge_name in edges:
                        refs.append((tip, edge_name))
                    fillet.Base = refs
            
            # Add to body
            body_obj.addObject(fillet)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": fillet.Name,
                "label": fillet.Label,
                "type": "PartDesign::Fillet",
                "body": body,
                "radius": radius,
                "message": f"Created fillet '{fillet.Name}' with radius {radius} mm"
            }
        
        return await bridge.execute(_fillet)
    
    @server.tool()
    async def chamfer_edges(
        body: str,
        size: float,
        edges: Optional[List[str]] = None,
        name: str = "Chamfer"
    ) -> Dict[str, Any]:
        """
        Add chamfers (beveled edges) to a body.
        
        Args:
            body: Name of the PartDesign body
            size: Chamfer size in mm
            edges: Optional list of edge names (e.g., ["Edge1", "Edge2"]).
                   If not provided, you'll need to select edges manually.
            name: Name for the chamfer feature (default: "Chamfer")
        
        Returns:
            Dictionary with feature info
        """
        def _chamfer():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            body_obj = doc.getObject(body)
            if body_obj is None:
                return {"success": False, "error": f"Body '{body}' not found"}
            
            # Create chamfer feature
            chamfer = doc.addObject("PartDesign::Chamfer", name)
            chamfer.Size = size
            
            # If edges specified, set them
            if edges and hasattr(body_obj, "Shape"):
                tip = body_obj.Tip
                if tip and hasattr(tip, "Shape"):
                    refs = []
                    for edge_name in edges:
                        refs.append((tip, edge_name))
                    chamfer.Base = refs
            
            # Add to body
            body_obj.addObject(chamfer)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": chamfer.Name,
                "label": chamfer.Label,
                "type": "PartDesign::Chamfer",
                "body": body,
                "size": size,
                "message": f"Created chamfer '{chamfer.Name}' with size {size} mm"
            }
        
        return await bridge.execute(_chamfer)
    
    @server.tool()
    async def add_hole(
        body: str,
        sketch: str,
        diameter: float,
        depth: float,
        name: str = "Hole",
        through_all: bool = False,
        threaded: bool = False,
        thread_size: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a hole feature.
        
        Args:
            body: Name of the PartDesign body
            sketch: Name of a sketch with a point defining hole center
            diameter: Hole diameter in mm
            depth: Hole depth in mm (ignored if through_all is True)
            name: Name for the hole feature (default: "Hole")
            through_all: If True, create a through hole
            threaded: If True, create a threaded hole
            thread_size: Thread specification (e.g., "M6", "M8x1")
        
        Returns:
            Dictionary with feature info
        """
        def _hole():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            body_obj = doc.getObject(body)
            if body_obj is None:
                return {"success": False, "error": f"Body '{body}' not found"}
            
            sketch_obj = doc.getObject(sketch)
            if sketch_obj is None:
                return {"success": False, "error": f"Sketch '{sketch}' not found"}
            
            # Create hole feature
            hole = doc.addObject("PartDesign::Hole", name)
            hole.Profile = sketch_obj
            hole.Diameter = diameter
            
            if through_all:
                hole.DepthType = 1  # Through all
            else:
                hole.DepthType = 0  # Dimension
                hole.Depth = depth
            
            hole.Threaded = threaded
            if threaded and thread_size:
                hole.ThreadSize = thread_size
            
            # Add to body
            body_obj.addObject(hole)
            
            doc.recompute()
            
            return {
                "success": True,
                "name": hole.Name,
                "label": hole.Label,
                "type": "PartDesign::Hole",
                "diameter": diameter,
                "depth": depth if not through_all else "through all",
                "threaded": threaded,
                "message": f"Created hole '{hole.Name}' (Ø{diameter} mm)"
            }
        
        return await bridge.execute(_hole)


