# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Boolean Operations and Transforms

Tools for boolean operations (union, cut, intersection) and geometric transforms
(move, rotate, scale, mirror).
"""

from typing import Optional, Dict, Any, List
import FreeCAD

from ..bridge import MainThreadBridge


def register_operation_tools(server, bridge: MainThreadBridge):
    """Register boolean and transform tools with the MCP server."""
    
    # ==================== Boolean Operations ====================
    
    @server.tool()
    async def boolean_union(
        objects: List[str],
        name: str = "Union",
        refine: bool = True
    ) -> Dict[str, Any]:
        """
        Create a union (fusion) of multiple objects.
        
        Args:
            objects: List of object names to unite
            name: Name for the result object (default: "Union")
            refine: If True, refine the result shape to remove unnecessary edges
        
        Returns:
            Dictionary with result info
        """
        def _union():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            if len(objects) < 2:
                return {"success": False, "error": "Need at least 2 objects for union"}
            
            # Get the objects
            objs = []
            for obj_name in objects:
                obj = doc.getObject(obj_name)
                if obj is None:
                    return {"success": False, "error": f"Object '{obj_name}' not found"}
                objs.append(obj)
            
            # Create fusion
            fusion = doc.addObject("Part::MultiFuse", name)
            fusion.Shapes = objs
            fusion.Refine = refine
            
            doc.recompute()
            
            return {
                "success": True,
                "name": fusion.Name,
                "label": fusion.Label,
                "type": "Part::MultiFuse",
                "input_objects": objects,
                "volume": fusion.Shape.Volume,
                "message": f"Created union '{fusion.Name}' from {len(objects)} objects"
            }
        
        return await bridge.execute(_union)
    
    @server.tool()
    async def boolean_cut(
        base: str,
        tool: str,
        name: str = "Cut",
        refine: bool = True
    ) -> Dict[str, Any]:
        """
        Cut one object from another (boolean subtraction).
        
        Args:
            base: Name of the base object (to cut from)
            tool: Name of the tool object (to cut with)
            name: Name for the result object (default: "Cut")
            refine: If True, refine the result shape
        
        Returns:
            Dictionary with result info
        """
        def _cut():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            base_obj = doc.getObject(base)
            tool_obj = doc.getObject(tool)
            
            if base_obj is None:
                return {"success": False, "error": f"Base object '{base}' not found"}
            if tool_obj is None:
                return {"success": False, "error": f"Tool object '{tool}' not found"}
            
            # Create cut
            cut = doc.addObject("Part::Cut", name)
            cut.Base = base_obj
            cut.Tool = tool_obj
            cut.Refine = refine
            
            doc.recompute()
            
            return {
                "success": True,
                "name": cut.Name,
                "label": cut.Label,
                "type": "Part::Cut",
                "base": base,
                "tool": tool,
                "volume": cut.Shape.Volume,
                "message": f"Created cut '{cut.Name}' ({base} - {tool})"
            }
        
        return await bridge.execute(_cut)
    
    @server.tool()
    async def boolean_intersection(
        objects: List[str],
        name: str = "Intersection",
        refine: bool = True
    ) -> Dict[str, Any]:
        """
        Create an intersection (common volume) of multiple objects.
        
        Args:
            objects: List of object names to intersect
            name: Name for the result object (default: "Intersection")
            refine: If True, refine the result shape
        
        Returns:
            Dictionary with result info
        """
        def _intersection():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            if len(objects) < 2:
                return {"success": False, "error": "Need at least 2 objects for intersection"}
            
            # Get the objects
            objs = []
            for obj_name in objects:
                obj = doc.getObject(obj_name)
                if obj is None:
                    return {"success": False, "error": f"Object '{obj_name}' not found"}
                objs.append(obj)
            
            # Create common
            common = doc.addObject("Part::MultiCommon", name)
            common.Shapes = objs
            common.Refine = refine
            
            doc.recompute()
            
            return {
                "success": True,
                "name": common.Name,
                "label": common.Label,
                "type": "Part::MultiCommon",
                "input_objects": objects,
                "volume": common.Shape.Volume,
                "message": f"Created intersection '{common.Name}' from {len(objects)} objects"
            }
        
        return await bridge.execute(_intersection)
    
    # ==================== Transform Operations ====================
    
    @server.tool()
    async def move_object(
        name: str,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        relative: bool = True
    ) -> Dict[str, Any]:
        """
        Move an object to a new position.
        
        Args:
            name: Name of the object to move
            x: X coordinate or offset in mm
            y: Y coordinate or offset in mm
            z: Z coordinate or offset in mm
            relative: If True, move relative to current position. If False, move to absolute position.
        
        Returns:
            Dictionary with result info
        """
        def _move():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if relative:
                # Move relative to current position
                current = obj.Placement.Base
                obj.Placement.Base = FreeCAD.Vector(
                    current.x + x,
                    current.y + y,
                    current.z + z
                )
            else:
                # Move to absolute position
                obj.Placement.Base = FreeCAD.Vector(x, y, z)
            
            doc.recompute()
            
            new_pos = obj.Placement.Base
            return {
                "success": True,
                "name": obj.Name,
                "position": [new_pos.x, new_pos.y, new_pos.z],
                "message": f"Moved '{obj.Name}' to ({new_pos.x}, {new_pos.y}, {new_pos.z})"
            }
        
        return await bridge.execute(_move)
    
    @server.tool()
    async def rotate_object(
        name: str,
        angle: float,
        axis: List[float] = [0, 0, 1],
        center: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Rotate an object around an axis.
        
        Args:
            name: Name of the object to rotate
            angle: Rotation angle in degrees
            axis: Rotation axis as [x, y, z] vector (default: Z axis)
            center: Optional center point for rotation (default: object origin)
        
        Returns:
            Dictionary with result info
        """
        def _rotate():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            axis_vec = FreeCAD.Vector(axis[0], axis[1], axis[2])
            
            if center:
                center_vec = FreeCAD.Vector(center[0], center[1], center[2])
            else:
                center_vec = obj.Placement.Base
            
            # Create rotation
            rotation = FreeCAD.Rotation(axis_vec, angle)
            
            # Apply rotation around center
            current_placement = obj.Placement
            new_rotation = rotation.multiply(current_placement.Rotation)
            obj.Placement.Rotation = new_rotation
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "angle": angle,
                "axis": axis,
                "message": f"Rotated '{obj.Name}' by {angle}° around axis {axis}"
            }
        
        return await bridge.execute(_rotate)
    
    @server.tool()
    async def scale_object(
        name: str,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        scale_z: float = 1.0,
        uniform: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Scale an object.
        
        Note: Scaling creates a new scaled copy of the shape. The original
        parametric properties are not preserved.
        
        Args:
            name: Name of the object to scale
            scale_x: Scale factor for X axis
            scale_y: Scale factor for Y axis
            scale_z: Scale factor for Z axis
            uniform: If provided, use this value for all axes (overrides x/y/z)
        
        Returns:
            Dictionary with result info
        """
        def _scale():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape to scale"}
            
            sx = uniform if uniform is not None else scale_x
            sy = uniform if uniform is not None else scale_y
            sz = uniform if uniform is not None else scale_z
            
            # Create transformation matrix for scaling
            mat = FreeCAD.Matrix()
            mat.scale(sx, sy, sz)
            
            # Transform the shape
            new_shape = obj.Shape.transformGeometry(mat)
            
            # Update the object's shape
            obj.Shape = new_shape
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "scale": [sx, sy, sz],
                "volume": obj.Shape.Volume,
                "message": f"Scaled '{obj.Name}' by ({sx}, {sy}, {sz})"
            }
        
        return await bridge.execute(_scale)
    
    @server.tool()
    async def mirror_object(
        name: str,
        plane: str = "XY",
        base_point: Optional[List[float]] = None,
        copy: bool = True,
        new_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mirror an object across a plane.
        
        Args:
            name: Name of the object to mirror
            plane: Plane to mirror across: "XY", "XZ", or "YZ"
            base_point: Optional base point for the mirror plane (default: origin)
            copy: If True, create a mirrored copy. If False, mirror in place.
            new_name: Name for the mirrored copy (only used if copy=True)
        
        Returns:
            Dictionary with result info
        """
        def _mirror():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape to mirror"}
            
            # Determine mirror normal
            plane_normals = {
                "XY": FreeCAD.Vector(0, 0, 1),
                "XZ": FreeCAD.Vector(0, 1, 0),
                "YZ": FreeCAD.Vector(1, 0, 0),
            }
            
            if plane.upper() not in plane_normals:
                return {"success": False, "error": f"Invalid plane '{plane}'. Use XY, XZ, or YZ"}
            
            normal = plane_normals[plane.upper()]
            base = FreeCAD.Vector(0, 0, 0)
            if base_point:
                base = FreeCAD.Vector(base_point[0], base_point[1], base_point[2])
            
            # Mirror the shape
            mirrored_shape = obj.Shape.mirror(base, normal)
            
            if copy:
                # Create new object with mirrored shape
                result_name = new_name or f"{name}_mirrored"
                new_obj = doc.addObject("Part::Feature", result_name)
                new_obj.Shape = mirrored_shape
                doc.recompute()
                
                return {
                    "success": True,
                    "name": new_obj.Name,
                    "original": name,
                    "plane": plane,
                    "message": f"Created mirrored copy '{new_obj.Name}' of '{name}' across {plane} plane"
                }
            else:
                # Mirror in place
                obj.Shape = mirrored_shape
                doc.recompute()
                
                return {
                    "success": True,
                    "name": obj.Name,
                    "plane": plane,
                    "message": f"Mirrored '{obj.Name}' across {plane} plane"
                }
        
        return await bridge.execute(_mirror)
    
    @server.tool()
    async def copy_object(
        name: str,
        new_name: Optional[str] = None,
        offset: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a copy of an object.
        
        Args:
            name: Name of the object to copy
            new_name: Name for the copy (default: auto-generated)
            offset: Optional [x, y, z] offset for the copy position
        
        Returns:
            Dictionary with result info
        """
        def _copy():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape to copy"}
            
            # Create copy
            copy_name = new_name or f"{name}_copy"
            new_obj = doc.addObject("Part::Feature", copy_name)
            new_obj.Shape = obj.Shape.copy()
            
            # Apply offset if provided
            if offset:
                new_obj.Placement.Base = FreeCAD.Vector(
                    obj.Placement.Base.x + offset[0],
                    obj.Placement.Base.y + offset[1],
                    obj.Placement.Base.z + offset[2]
                )
            else:
                new_obj.Placement = obj.Placement
            
            doc.recompute()
            
            return {
                "success": True,
                "name": new_obj.Name,
                "original": name,
                "offset": offset,
                "message": f"Created copy '{new_obj.Name}' of '{name}'"
            }
        
        return await bridge.execute(_copy)
    
    @server.tool()
    async def array_linear(
        name: str,
        count: int,
        offset: List[float],
        new_name: str = "LinearArray"
    ) -> Dict[str, Any]:
        """
        Create a linear array of an object.
        
        Args:
            name: Name of the object to array
            count: Number of copies (including original)
            offset: [x, y, z] offset between each copy
            new_name: Name for the array compound
        
        Returns:
            Dictionary with result info
        """
        def _array():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            if count < 1:
                return {"success": False, "error": "Count must be at least 1"}
            
            # Create array of shapes
            shapes = []
            for i in range(count):
                shape_copy = obj.Shape.copy()
                shape_copy.translate(FreeCAD.Vector(
                    offset[0] * i,
                    offset[1] * i,
                    offset[2] * i
                ))
                shapes.append(shape_copy)
            
            # Create compound
            compound = Part.makeCompound(shapes)
            
            array_obj = doc.addObject("Part::Feature", new_name)
            array_obj.Shape = compound
            
            doc.recompute()
            
            return {
                "success": True,
                "name": array_obj.Name,
                "source": name,
                "count": count,
                "offset": offset,
                "message": f"Created linear array '{array_obj.Name}' with {count} copies"
            }
        
        return await bridge.execute(_array)
    
    @server.tool()
    async def array_polar(
        name: str,
        count: int,
        axis: List[float] = [0, 0, 1],
        center: List[float] = [0, 0, 0],
        angle: float = 360.0,
        new_name: str = "PolarArray"
    ) -> Dict[str, Any]:
        """
        Create a polar (circular) array of an object.
        
        Args:
            name: Name of the object to array
            count: Number of copies (including original)
            axis: Rotation axis [x, y, z]
            center: Center point [x, y, z] for the rotation
            angle: Total angle to span in degrees (360 = full circle)
            new_name: Name for the array compound
        
        Returns:
            Dictionary with result info
        """
        def _array():
            import Part
            import math
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            if count < 1:
                return {"success": False, "error": "Count must be at least 1"}
            
            axis_vec = FreeCAD.Vector(axis[0], axis[1], axis[2])
            center_vec = FreeCAD.Vector(center[0], center[1], center[2])
            angle_step = angle / count
            
            # Create array of shapes
            shapes = []
            for i in range(count):
                shape_copy = obj.Shape.copy()
                shape_copy.rotate(center_vec, axis_vec, angle_step * i)
                shapes.append(shape_copy)
            
            # Create compound
            compound = Part.makeCompound(shapes)
            
            array_obj = doc.addObject("Part::Feature", new_name)
            array_obj.Shape = compound
            
            doc.recompute()
            
            return {
                "success": True,
                "name": array_obj.Name,
                "source": name,
                "count": count,
                "angle": angle,
                "message": f"Created polar array '{array_obj.Name}' with {count} copies over {angle}°"
            }
        
        return await bridge.execute(_array)


