# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Primitive Creation Tools

Tools for creating basic 3D shapes: boxes, cylinders, spheres, cones, torus, etc.
"""

from typing import Optional, Dict, Any, List
import FreeCAD

from ..bridge import MainThreadBridge


def register_primitive_tools(server, bridge: MainThreadBridge):
    """Register primitive creation tools with the MCP server."""
    
    @server.tool()
    async def create_box(
        length: float,
        width: float,
        height: float,
        name: str = "Box",
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a box (rectangular prism) primitive.
        
        Args:
            length: Length of the box (X dimension) in mm
            width: Width of the box (Y dimension) in mm
            height: Height of the box (Z dimension) in mm
            name: Name for the object (default: "Box")
            position: Optional [x, y, z] position for the box origin
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Box", name)
            obj.Length = length
            obj.Width = width
            obj.Height = height
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Box",
                "dimensions": {
                    "length": float(obj.Length),
                    "width": float(obj.Width),
                    "height": float(obj.Height)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created box '{obj.Name}' ({length} x {width} x {height} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_cylinder(
        radius: float,
        height: float,
        name: str = "Cylinder",
        angle: float = 360.0,
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a cylinder primitive.
        
        Args:
            radius: Radius of the cylinder in mm
            height: Height of the cylinder in mm
            name: Name for the object (default: "Cylinder")
            angle: Arc angle in degrees (360 = full cylinder, less = partial)
            position: Optional [x, y, z] position for the cylinder origin
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Cylinder", name)
            obj.Radius = radius
            obj.Height = height
            obj.Angle = angle
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Cylinder",
                "dimensions": {
                    "radius": float(obj.Radius),
                    "height": float(obj.Height),
                    "angle": float(obj.Angle)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created cylinder '{obj.Name}' (r={radius}, h={height} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_sphere(
        radius: float,
        name: str = "Sphere",
        angle1: float = -90.0,
        angle2: float = 90.0,
        angle3: float = 360.0,
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a sphere primitive.
        
        Args:
            radius: Radius of the sphere in mm
            name: Name for the object (default: "Sphere")
            angle1: First angle (latitude start, -90 to 90)
            angle2: Second angle (latitude end, -90 to 90)
            angle3: Third angle (longitude sweep, 0 to 360)
            position: Optional [x, y, z] position for the sphere center
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Sphere", name)
            obj.Radius = radius
            obj.Angle1 = angle1
            obj.Angle2 = angle2
            obj.Angle3 = angle3
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Sphere",
                "dimensions": {
                    "radius": float(obj.Radius)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created sphere '{obj.Name}' (r={radius} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_cone(
        radius1: float,
        radius2: float,
        height: float,
        name: str = "Cone",
        angle: float = 360.0,
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a cone primitive.
        
        Args:
            radius1: Bottom radius of the cone in mm
            radius2: Top radius of the cone in mm (0 for pointed cone)
            height: Height of the cone in mm
            name: Name for the object (default: "Cone")
            angle: Arc angle in degrees (360 = full cone)
            position: Optional [x, y, z] position for the cone origin
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Cone", name)
            obj.Radius1 = radius1
            obj.Radius2 = radius2
            obj.Height = height
            obj.Angle = angle
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Cone",
                "dimensions": {
                    "radius1": float(obj.Radius1),
                    "radius2": float(obj.Radius2),
                    "height": float(obj.Height)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created cone '{obj.Name}' (r1={radius1}, r2={radius2}, h={height} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_torus(
        radius1: float,
        radius2: float,
        name: str = "Torus",
        angle1: float = -180.0,
        angle2: float = 180.0,
        angle3: float = 360.0,
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a torus (donut shape) primitive.
        
        Args:
            radius1: Distance from center to the tube center in mm
            radius2: Radius of the tube in mm
            name: Name for the object (default: "Torus")
            angle1: First angle parameter
            angle2: Second angle parameter
            angle3: Revolution angle (360 = complete torus)
            position: Optional [x, y, z] position for the torus center
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Torus", name)
            obj.Radius1 = radius1
            obj.Radius2 = radius2
            obj.Angle1 = angle1
            obj.Angle2 = angle2
            obj.Angle3 = angle3
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Torus",
                "dimensions": {
                    "radius1": float(obj.Radius1),
                    "radius2": float(obj.Radius2)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created torus '{obj.Name}' (R={radius1}, r={radius2} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_wedge(
        xmin: float, xmax: float,
        ymin: float, ymax: float,
        zmin: float, zmax: float,
        x2min: float, x2max: float,
        z2min: float, z2max: float,
        name: str = "Wedge"
    ) -> Dict[str, Any]:
        """
        Create a wedge primitive.
        
        Args:
            xmin, xmax: X bounds at the base
            ymin, ymax: Y bounds (height)
            zmin, zmax: Z bounds at the base
            x2min, x2max: X bounds at the top
            z2min, z2max: Z bounds at the top
            name: Name for the object (default: "Wedge")
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Wedge", name)
            obj.Xmin = xmin
            obj.Xmax = xmax
            obj.Ymin = ymin
            obj.Ymax = ymax
            obj.Zmin = zmin
            obj.Zmax = zmax
            obj.X2min = x2min
            obj.X2max = x2max
            obj.Z2min = z2min
            obj.Z2max = z2max
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Wedge",
                "volume": obj.Shape.Volume,
                "message": f"Created wedge '{obj.Name}'"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_prism(
        polygon_sides: int,
        circumradius: float,
        height: float,
        name: str = "Prism",
        position: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a regular prism primitive.
        
        Args:
            polygon_sides: Number of sides (3 = triangular prism, 6 = hexagonal, etc.)
            circumradius: Circumscribed circle radius in mm
            height: Height of the prism in mm
            name: Name for the object (default: "Prism")
            position: Optional [x, y, z] position
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Prism", name)
            obj.Polygon = polygon_sides
            obj.Circumradius = circumradius
            obj.Height = height
            
            if position:
                obj.Placement.Base = FreeCAD.Vector(position[0], position[1], position[2])
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Prism",
                "dimensions": {
                    "sides": int(obj.Polygon),
                    "circumradius": float(obj.Circumradius),
                    "height": float(obj.Height)
                },
                "volume": obj.Shape.Volume,
                "message": f"Created {polygon_sides}-sided prism '{obj.Name}'"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_helix(
        pitch: float,
        height: float,
        radius: float,
        name: str = "Helix",
        angle: float = 0.0,
        left_handed: bool = False
    ) -> Dict[str, Any]:
        """
        Create a helix (spiral) curve.
        
        Args:
            pitch: Distance between turns in mm
            height: Total height of the helix in mm
            radius: Radius of the helix in mm
            name: Name for the object (default: "Helix")
            angle: Cone angle (0 = cylindrical helix)
            left_handed: If True, create left-handed helix
        
        Returns:
            Dictionary with object info
        """
        def _create():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            obj = doc.addObject("Part::Helix", name)
            obj.Pitch = pitch
            obj.Height = height
            obj.Radius = radius
            obj.Angle = angle
            obj.LocalCoord = 1 if left_handed else 0
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Helix",
                "dimensions": {
                    "pitch": float(obj.Pitch),
                    "height": float(obj.Height),
                    "radius": float(obj.Radius)
                },
                "message": f"Created helix '{obj.Name}'"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_line(
        start: List[float],
        end: List[float],
        name: str = "Line"
    ) -> Dict[str, Any]:
        """
        Create a line between two points.
        
        Args:
            start: Start point [x, y, z] in mm
            end: End point [x, y, z] in mm
            name: Name for the object (default: "Line")
        
        Returns:
            Dictionary with object info
        """
        def _create():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            line = Part.makeLine(
                FreeCAD.Vector(start[0], start[1], start[2]),
                FreeCAD.Vector(end[0], end[1], end[2])
            )
            
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = line
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Feature (Line)",
                "start": start,
                "end": end,
                "length": line.Length,
                "message": f"Created line '{obj.Name}' (length={line.Length:.2f} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_circle(
        radius: float,
        name: str = "Circle",
        position: Optional[List[float]] = None,
        normal: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Create a circle (2D curve).
        
        Args:
            radius: Radius of the circle in mm
            name: Name for the object (default: "Circle")
            position: Optional center point [x, y, z]
            normal: Optional normal vector [x, y, z] for the circle plane
        
        Returns:
            Dictionary with object info
        """
        def _create():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            center = FreeCAD.Vector(0, 0, 0)
            if position:
                center = FreeCAD.Vector(position[0], position[1], position[2])
            
            norm = FreeCAD.Vector(0, 0, 1)
            if normal:
                norm = FreeCAD.Vector(normal[0], normal[1], normal[2])
            
            circle = Part.makeCircle(radius, center, norm)
            
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = circle
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Feature (Circle)",
                "radius": radius,
                "circumference": circle.Length,
                "message": f"Created circle '{obj.Name}' (r={radius} mm)"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def create_polygon(
        points: List[List[float]],
        name: str = "Polygon",
        closed: bool = True
    ) -> Dict[str, Any]:
        """
        Create a polygon from a list of points.
        
        Args:
            points: List of points [[x1,y1,z1], [x2,y2,z2], ...]
            name: Name for the object (default: "Polygon")
            closed: If True, close the polygon (connect last point to first)
        
        Returns:
            Dictionary with object info
        """
        def _create():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Unnamed")
            
            vectors = [FreeCAD.Vector(p[0], p[1], p[2]) for p in points]
            if closed and vectors[0] != vectors[-1]:
                vectors.append(vectors[0])
            
            wire = Part.makePolygon(vectors)
            
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = wire
            
            doc.recompute()
            
            return {
                "success": True,
                "name": obj.Name,
                "label": obj.Label,
                "type": "Part::Feature (Polygon)",
                "point_count": len(points),
                "closed": closed,
                "length": wire.Length,
                "message": f"Created polygon '{obj.Name}' with {len(points)} points"
            }
        
        return await bridge.execute(_create)


