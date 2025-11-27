# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Query and Inspection Tools

Tools for querying object properties, measurements, and document information.
"""

from typing import Optional, Dict, Any, List
import FreeCAD

from ..bridge import MainThreadBridge


def register_query_tools(server, bridge: MainThreadBridge):
    """Register query and inspection tools with the MCP server."""
    
    @server.tool()
    async def get_object_properties(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all properties of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional, uses active document if not specified)
        
        Returns:
            Dictionary with object properties
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            # Collect properties
            properties = {}
            for prop_name in obj.PropertiesList:
                try:
                    value = getattr(obj, prop_name)
                    # Convert to JSON-serializable format
                    if isinstance(value, FreeCAD.Vector):
                        properties[prop_name] = [value.x, value.y, value.z]
                    elif isinstance(value, FreeCAD.Placement):
                        properties[prop_name] = {
                            "position": [value.Base.x, value.Base.y, value.Base.z],
                            "rotation": list(value.Rotation.Q)
                        }
                    elif isinstance(value, (int, float, str, bool)):
                        properties[prop_name] = value
                    elif hasattr(value, "Value"):  # Quantity
                        properties[prop_name] = float(value.Value)
                    elif value is None:
                        properties[prop_name] = None
                    else:
                        properties[prop_name] = str(value)
                except Exception:
                    properties[prop_name] = "<unable to read>"
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": obj.TypeId,
                "properties": properties
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_bounding_box(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the bounding box of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with bounding box coordinates
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            bbox = obj.Shape.BoundBox
            
            return {
                "success": True,
                "name": obj.Name,
                "bounding_box": {
                    "min": [bbox.XMin, bbox.YMin, bbox.ZMin],
                    "max": [bbox.XMax, bbox.YMax, bbox.ZMax],
                    "center": [bbox.Center.x, bbox.Center.y, bbox.Center.z],
                    "size": [bbox.XLength, bbox.YLength, bbox.ZLength],
                    "diagonal": bbox.DiagonalLength
                }
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_volume(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the volume of a solid object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with volume information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            shape = obj.Shape
            
            if not shape.Solids:
                return {"success": False, "error": f"Object '{name}' is not a solid"}
            
            return {
                "success": True,
                "name": obj.Name,
                "volume_mm3": shape.Volume,
                "volume_cm3": shape.Volume / 1000.0,
                "volume_m3": shape.Volume / 1e9
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_surface_area(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the surface area of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with surface area information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            shape = obj.Shape
            
            return {
                "success": True,
                "name": obj.Name,
                "area_mm2": shape.Area,
                "area_cm2": shape.Area / 100.0,
                "area_m2": shape.Area / 1e6
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_center_of_mass(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the center of mass of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with center of mass coordinates
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            shape = obj.Shape
            com = shape.CenterOfMass
            
            return {
                "success": True,
                "name": obj.Name,
                "center_of_mass": [com.x, com.y, com.z]
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_shape_info(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about an object's shape topology.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with shape topology information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            shape = obj.Shape
            
            return {
                "success": True,
                "name": obj.Name,
                "shape_type": shape.ShapeType,
                "topology": {
                    "solids": len(shape.Solids),
                    "shells": len(shape.Shells),
                    "faces": len(shape.Faces),
                    "wires": len(shape.Wires),
                    "edges": len(shape.Edges),
                    "vertices": len(shape.Vertexes)
                },
                "is_valid": shape.isValid(),
                "is_closed": shape.isClosed() if hasattr(shape, "isClosed") else None,
                "orientation": shape.Orientation
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_edges(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get information about all edges of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with edge information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            edges_info = []
            for i, edge in enumerate(obj.Shape.Edges):
                edge_info = {
                    "index": i,
                    "name": f"Edge{i+1}",
                    "length": edge.Length,
                    "type": edge.Curve.__class__.__name__
                }
                
                # Add curve-specific info
                curve = edge.Curve
                if hasattr(curve, "Radius"):
                    edge_info["radius"] = curve.Radius
                if hasattr(curve, "Center"):
                    edge_info["center"] = [curve.Center.x, curve.Center.y, curve.Center.z]
                
                edges_info.append(edge_info)
            
            return {
                "success": True,
                "name": obj.Name,
                "edge_count": len(edges_info),
                "edges": edges_info
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_faces(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get information about all faces of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with face information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{name}' has no shape"}
            
            faces_info = []
            for i, face in enumerate(obj.Shape.Faces):
                face_info = {
                    "index": i,
                    "name": f"Face{i+1}",
                    "area": face.Area,
                    "type": face.Surface.__class__.__name__
                }
                
                # Add surface-specific info
                surface = face.Surface
                if hasattr(surface, "Radius"):
                    face_info["radius"] = surface.Radius
                if hasattr(surface, "Center"):
                    face_info["center"] = [surface.Center.x, surface.Center.y, surface.Center.z]
                
                # Normal at center
                try:
                    uv = face.Surface.parameter(face.CenterOfMass)
                    normal = face.normalAt(uv[0], uv[1])
                    face_info["normal"] = [normal.x, normal.y, normal.z]
                except Exception:
                    pass
                
                faces_info.append(face_info)
            
            return {
                "success": True,
                "name": obj.Name,
                "face_count": len(faces_info),
                "faces": faces_info
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def measure_distance(
        point1: List[float],
        point2: List[float]
    ) -> Dict[str, Any]:
        """
        Measure the distance between two points.
        
        Args:
            point1: First point [x, y, z] in mm
            point2: Second point [x, y, z] in mm
        
        Returns:
            Dictionary with distance measurement
        """
        def _measure():
            p1 = FreeCAD.Vector(point1[0], point1[1], point1[2])
            p2 = FreeCAD.Vector(point2[0], point2[1], point2[2])
            
            diff = p2 - p1
            distance = diff.Length
            
            return {
                "success": True,
                "point1": point1,
                "point2": point2,
                "distance_mm": distance,
                "distance_cm": distance / 10.0,
                "distance_m": distance / 1000.0,
                "delta": [diff.x, diff.y, diff.z]
            }
        
        return await bridge.execute(_measure)
    
    @server.tool()
    async def get_placement(
        name: str,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the placement (position and orientation) of an object.
        
        Args:
            name: Name of the object
            document_name: Document name (optional)
        
        Returns:
            Dictionary with placement information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(name)
            if obj is None:
                return {"success": False, "error": f"Object '{name}' not found"}
            
            if not hasattr(obj, "Placement"):
                return {"success": False, "error": f"Object '{name}' has no placement"}
            
            placement = obj.Placement
            position = placement.Base
            rotation = placement.Rotation
            
            # Get Euler angles
            euler = rotation.toEulerAngles("ZYX")
            
            return {
                "success": True,
                "name": obj.Name,
                "placement": {
                    "position": [position.x, position.y, position.z],
                    "rotation_quaternion": list(rotation.Q),
                    "rotation_euler_zyx": list(euler),
                    "rotation_axis_angle": {
                        "axis": list(rotation.Axis),
                        "angle": rotation.Angle
                    }
                }
            }
        
        return await bridge.execute(_get)
    
    @server.tool()
    async def get_document_info(
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a document.
        
        Args:
            document_name: Document name (optional, uses active document)
        
        Returns:
            Dictionary with document information
        """
        def _get():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Count object types
            type_counts = {}
            for obj in doc.Objects:
                type_id = obj.TypeId
                type_counts[type_id] = type_counts.get(type_id, 0) + 1
            
            return {
                "success": True,
                "name": doc.Name,
                "label": doc.Label,
                "path": doc.FileName or "(unsaved)",
                "modified": doc.Modified,
                "object_count": len(doc.Objects),
                "object_types": type_counts,
                "objects": [
                    {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
                    for obj in doc.Objects
                ]
            }
        
        return await bridge.execute(_get)


