# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Export Tools

Tools for exporting FreeCAD objects to various file formats:
- STEP (Standard for the Exchange of Product Data)
- STL (Stereolithography)
- IGES (Initial Graphics Exchange Specification)
- OBJ (Wavefront)
- BREP (OpenCASCADE native format)
- FreeCAD native format (.FCStd)
"""

from typing import Optional, Dict, Any, List
import os
import FreeCAD

from ..bridge import MainThreadBridge


def register_export_tools(server, bridge: MainThreadBridge):
    """Register export tools with the MCP server."""
    
    @server.tool()
    async def export_step(
        path: str,
        objects: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Export objects to STEP format.
        
        STEP is the industry standard format for exchanging CAD data.
        It preserves geometry accurately and supports assemblies.
        
        Args:
            path: Full path for the output file (should end in .step or .stp)
            objects: List of object names to export. If None, exports all visible objects.
        
        Returns:
            Dictionary with export result
        """
        def _export():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Get objects to export
            if objects:
                export_objs = []
                for name in objects:
                    obj = doc.getObject(name)
                    if obj is None:
                        return {"success": False, "error": f"Object '{name}' not found"}
                    export_objs.append(obj)
            else:
                # Export all objects with shapes
                export_objs = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
            
            if not export_objs:
                return {"success": False, "error": "No objects to export"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                # Export using Part module
                Part.export(export_objs, path)
                
                return {
                    "success": True,
                    "format": "STEP",
                    "path": path,
                    "object_count": len(export_objs),
                    "objects": [obj.Name for obj in export_objs],
                    "file_size": os.path.getsize(path),
                    "message": f"Exported {len(export_objs)} objects to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"STEP export failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def export_stl(
        path: str,
        objects: Optional[List[str]] = None,
        mesh_tolerance: float = 0.1
    ) -> Dict[str, Any]:
        """
        Export objects to STL format.
        
        STL is widely used for 3D printing. Note that STL converts
        geometry to triangular meshes, losing exact shape information.
        
        Args:
            path: Full path for the output file (should end in .stl)
            objects: List of object names to export. If None, exports all visible objects.
            mesh_tolerance: Mesh tolerance for tessellation (smaller = finer mesh)
        
        Returns:
            Dictionary with export result
        """
        def _export():
            import Mesh
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Get objects to export
            if objects:
                export_objs = []
                for name in objects:
                    obj = doc.getObject(name)
                    if obj is None:
                        return {"success": False, "error": f"Object '{name}' not found"}
                    export_objs.append(obj)
            else:
                export_objs = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
            
            if not export_objs:
                return {"success": False, "error": "No objects to export"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                # Create meshes from shapes
                meshes = []
                for obj in export_objs:
                    if hasattr(obj, "Shape"):
                        mesh = Mesh.Mesh(obj.Shape.tessellate(mesh_tolerance)[0])
                        meshes.append(mesh)
                
                # Merge all meshes
                if meshes:
                    combined = meshes[0]
                    for m in meshes[1:]:
                        combined.addMesh(m)
                    
                    combined.write(path)
                
                return {
                    "success": True,
                    "format": "STL",
                    "path": path,
                    "object_count": len(export_objs),
                    "objects": [obj.Name for obj in export_objs],
                    "mesh_tolerance": mesh_tolerance,
                    "file_size": os.path.getsize(path),
                    "message": f"Exported {len(export_objs)} objects to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"STL export failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def export_iges(
        path: str,
        objects: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Export objects to IGES format.
        
        IGES is an older CAD exchange format, still used in some industries.
        
        Args:
            path: Full path for the output file (should end in .iges or .igs)
            objects: List of object names to export. If None, exports all visible objects.
        
        Returns:
            Dictionary with export result
        """
        def _export():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Get objects to export
            if objects:
                export_objs = []
                for name in objects:
                    obj = doc.getObject(name)
                    if obj is None:
                        return {"success": False, "error": f"Object '{name}' not found"}
                    export_objs.append(obj)
            else:
                export_objs = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
            
            if not export_objs:
                return {"success": False, "error": "No objects to export"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                Part.export(export_objs, path)
                
                return {
                    "success": True,
                    "format": "IGES",
                    "path": path,
                    "object_count": len(export_objs),
                    "objects": [obj.Name for obj in export_objs],
                    "file_size": os.path.getsize(path),
                    "message": f"Exported {len(export_objs)} objects to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"IGES export failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def export_obj(
        path: str,
        objects: Optional[List[str]] = None,
        mesh_tolerance: float = 0.1
    ) -> Dict[str, Any]:
        """
        Export objects to OBJ (Wavefront) format.
        
        OBJ is commonly used for 3D graphics and game assets.
        
        Args:
            path: Full path for the output file (should end in .obj)
            objects: List of object names to export. If None, exports all visible objects.
            mesh_tolerance: Mesh tolerance for tessellation
        
        Returns:
            Dictionary with export result
        """
        def _export():
            import Mesh
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Get objects to export
            if objects:
                export_objs = []
                for name in objects:
                    obj = doc.getObject(name)
                    if obj is None:
                        return {"success": False, "error": f"Object '{name}' not found"}
                    export_objs.append(obj)
            else:
                export_objs = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
            
            if not export_objs:
                return {"success": False, "error": "No objects to export"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                # Create meshes and export
                meshes = []
                for obj in export_objs:
                    if hasattr(obj, "Shape"):
                        mesh = Mesh.Mesh(obj.Shape.tessellate(mesh_tolerance)[0])
                        meshes.append(mesh)
                
                if meshes:
                    combined = meshes[0]
                    for m in meshes[1:]:
                        combined.addMesh(m)
                    combined.write(path)
                
                return {
                    "success": True,
                    "format": "OBJ",
                    "path": path,
                    "object_count": len(export_objs),
                    "objects": [obj.Name for obj in export_objs],
                    "file_size": os.path.getsize(path),
                    "message": f"Exported {len(export_objs)} objects to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"OBJ export failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def export_brep(
        path: str,
        object_name: str
    ) -> Dict[str, Any]:
        """
        Export a single object to BREP format.
        
        BREP is OpenCASCADE's native format, preserving exact geometry.
        
        Args:
            path: Full path for the output file (should end in .brep)
            object_name: Name of the object to export
        
        Returns:
            Dictionary with export result
        """
        def _export():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            obj = doc.getObject(object_name)
            if obj is None:
                return {"success": False, "error": f"Object '{object_name}' not found"}
            
            if not hasattr(obj, "Shape"):
                return {"success": False, "error": f"Object '{object_name}' has no shape"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                obj.Shape.exportBrep(path)
                
                return {
                    "success": True,
                    "format": "BREP",
                    "path": path,
                    "object": object_name,
                    "file_size": os.path.getsize(path),
                    "message": f"Exported '{object_name}' to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"BREP export failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def export_freecad(
        path: str
    ) -> Dict[str, Any]:
        """
        Export/save the document in FreeCAD's native format.
        
        This preserves all parametric information and feature history.
        
        Args:
            path: Full path for the output file (should end in .FCStd)
        
        Returns:
            Dictionary with export result
        """
        def _export():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {"success": False, "error": "No active document"}
            
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            try:
                doc.saveAs(path)
                
                return {
                    "success": True,
                    "format": "FreeCAD",
                    "path": path,
                    "document": doc.Name,
                    "object_count": len(doc.Objects),
                    "file_size": os.path.getsize(path),
                    "message": f"Saved document to {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Save failed: {e}"
                }
        
        return await bridge.execute(_export)
    
    @server.tool()
    async def import_step(path: str) -> Dict[str, Any]:
        """
        Import a STEP file into the active document.
        
        Args:
            path: Full path to the STEP file (.step or .stp)
        
        Returns:
            Dictionary with import result
        """
        def _import():
            import Part
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Imported")
            
            if not os.path.exists(path):
                return {"success": False, "error": f"File not found: {path}"}
            
            try:
                before_count = len(doc.Objects)
                Part.insert(path, doc.Name)
                after_count = len(doc.Objects)
                
                imported_count = after_count - before_count
                
                doc.recompute()
                
                return {
                    "success": True,
                    "format": "STEP",
                    "path": path,
                    "document": doc.Name,
                    "imported_objects": imported_count,
                    "message": f"Imported {imported_count} objects from {path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"STEP import failed: {e}"
                }
        
        return await bridge.execute(_import)
    
    @server.tool()
    async def import_stl(path: str, name: str = "ImportedMesh") -> Dict[str, Any]:
        """
        Import an STL file into the active document.
        
        Args:
            path: Full path to the STL file
            name: Name for the imported mesh object
        
        Returns:
            Dictionary with import result
        """
        def _import():
            import Mesh
            
            doc = FreeCAD.ActiveDocument
            if doc is None:
                doc = FreeCAD.newDocument("Imported")
            
            if not os.path.exists(path):
                return {"success": False, "error": f"File not found: {path}"}
            
            try:
                mesh = Mesh.Mesh(path)
                mesh_obj = doc.addObject("Mesh::Feature", name)
                mesh_obj.Mesh = mesh
                
                doc.recompute()
                
                return {
                    "success": True,
                    "format": "STL",
                    "path": path,
                    "document": doc.Name,
                    "object_name": mesh_obj.Name,
                    "facet_count": mesh.CountFacets,
                    "point_count": mesh.CountPoints,
                    "message": f"Imported mesh '{mesh_obj.Name}' with {mesh.CountFacets} facets"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"STL import failed: {e}"
                }
        
        return await bridge.execute(_import)


