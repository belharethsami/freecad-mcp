# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Document Management Tools

Tools for creating, opening, saving, and managing FreeCAD documents.
"""

from typing import Optional, List, Dict, Any
import FreeCAD

from ..bridge import MainThreadBridge


def register_document_tools(server, bridge: MainThreadBridge):
    """Register document management tools with the MCP server."""
    
    @server.tool()
    async def new_document(name: str = "Unnamed") -> Dict[str, Any]:
        """
        Create a new FreeCAD document.
        
        Args:
            name: Name for the new document (default: "Unnamed")
        
        Returns:
            Dictionary with document info including name and label
        """
        def _create():
            doc = FreeCAD.newDocument(name)
            return {
                "success": True,
                "name": doc.Name,
                "label": doc.Label,
                "message": f"Created new document '{doc.Name}'"
            }
        
        return await bridge.execute(_create)
    
    @server.tool()
    async def open_document(path: str) -> Dict[str, Any]:
        """
        Open an existing FreeCAD document from a file.
        
        Args:
            path: Full path to the FreeCAD document (.FCStd file)
        
        Returns:
            Dictionary with document info or error message
        """
        def _open():
            try:
                doc = FreeCAD.openDocument(path)
                return {
                    "success": True,
                    "name": doc.Name,
                    "label": doc.Label,
                    "path": path,
                    "object_count": len(doc.Objects),
                    "message": f"Opened document '{doc.Name}' with {len(doc.Objects)} objects"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to open document: {e}"
                }
        
        return await bridge.execute(_open)
    
    @server.tool()
    async def save_document(path: Optional[str] = None) -> Dict[str, Any]:
        """
        Save the active FreeCAD document.
        
        Args:
            path: Optional path to save to. If not provided, saves to current location.
                  For new documents, a path must be provided.
        
        Returns:
            Dictionary with save result
        """
        def _save():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                return {
                    "success": False,
                    "error": "No active document",
                    "message": "No active document to save"
                }
            
            try:
                if path:
                    doc.saveAs(path)
                    save_path = path
                else:
                    if doc.FileName:
                        doc.save()
                        save_path = doc.FileName
                    else:
                        return {
                            "success": False,
                            "error": "No path specified",
                            "message": "Document has never been saved. Please provide a path."
                        }
                
                return {
                    "success": True,
                    "name": doc.Name,
                    "path": save_path,
                    "message": f"Saved document '{doc.Name}' to {save_path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to save document: {e}"
                }
        
        return await bridge.execute(_save)
    
    @server.tool()
    async def close_document(name: Optional[str] = None, save: bool = False) -> Dict[str, Any]:
        """
        Close a FreeCAD document.
        
        Args:
            name: Name of document to close. If not provided, closes the active document.
            save: Whether to save before closing (default: False)
        
        Returns:
            Dictionary with close result
        """
        def _close():
            if name:
                doc = FreeCAD.getDocument(name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": f"No document found with name '{name}'" if name else "No active document"
                }
            
            doc_name = doc.Name
            
            try:
                if save and doc.FileName:
                    doc.save()
                
                FreeCAD.closeDocument(doc_name)
                
                return {
                    "success": True,
                    "name": doc_name,
                    "message": f"Closed document '{doc_name}'"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to close document: {e}"
                }
        
        return await bridge.execute(_close)
    
    @server.tool()
    async def list_documents() -> Dict[str, Any]:
        """
        List all open FreeCAD documents.
        
        Returns:
            Dictionary with list of open documents and their basic info
        """
        def _list():
            docs = []
            active_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            
            for name in FreeCAD.listDocuments():
                doc = FreeCAD.getDocument(name)
                docs.append({
                    "name": doc.Name,
                    "label": doc.Label,
                    "path": doc.FileName or "(unsaved)",
                    "object_count": len(doc.Objects),
                    "is_active": doc.Name == active_name
                })
            
            return {
                "success": True,
                "count": len(docs),
                "documents": docs,
                "active_document": active_name
            }
        
        return await bridge.execute(_list)
    
    @server.tool()
    async def set_active_document(name: str) -> Dict[str, Any]:
        """
        Set the active document by name.
        
        Args:
            name: Name of the document to make active
        
        Returns:
            Dictionary with result
        """
        def _set_active():
            doc = FreeCAD.getDocument(name)
            if doc is None:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": f"No document found with name '{name}'"
                }
            
            FreeCAD.setActiveDocument(name)
            
            return {
                "success": True,
                "name": doc.Name,
                "message": f"Set '{doc.Name}' as active document"
            }
        
        return await bridge.execute(_set_active)
    
    @server.tool()
    async def list_objects(document_name: Optional[str] = None) -> Dict[str, Any]:
        """
        List all objects in a document.
        
        Args:
            document_name: Name of document. If not provided, uses the active document.
        
        Returns:
            Dictionary with list of objects and their basic info
        """
        def _list_objects():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": f"No document found" if not document_name else f"Document '{document_name}' not found"
                }
            
            objects = []
            for obj in doc.Objects:
                obj_info = {
                    "name": obj.Name,
                    "label": obj.Label,
                    "type": obj.TypeId,
                }
                
                # Add shape info if available
                if hasattr(obj, "Shape"):
                    shape = obj.Shape
                    obj_info["has_shape"] = True
                    obj_info["shape_type"] = shape.ShapeType if hasattr(shape, "ShapeType") else "Unknown"
                    if hasattr(shape, "Volume"):
                        obj_info["volume"] = shape.Volume
                else:
                    obj_info["has_shape"] = False
                
                objects.append(obj_info)
            
            return {
                "success": True,
                "document": doc.Name,
                "count": len(objects),
                "objects": objects
            }
        
        return await bridge.execute(_list_objects)
    
    @server.tool()
    async def delete_object(name: str, document_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Delete an object from a document.
        
        Args:
            name: Name of the object to delete
            document_name: Name of document. If not provided, uses the active document.
        
        Returns:
            Dictionary with deletion result
        """
        def _delete():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": "No active document"
                }
            
            obj = doc.getObject(name)
            if obj is None:
                return {
                    "success": False,
                    "error": "Object not found",
                    "message": f"No object named '{name}' in document '{doc.Name}'"
                }
            
            try:
                doc.removeObject(name)
                doc.recompute()
                
                return {
                    "success": True,
                    "deleted": name,
                    "document": doc.Name,
                    "message": f"Deleted object '{name}' from document '{doc.Name}'"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to delete object: {e}"
                }
        
        return await bridge.execute(_delete)
    
    @server.tool()
    async def recompute(document_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Recompute (update) a document to reflect all changes.
        
        Args:
            document_name: Name of document. If not provided, uses the active document.
        
        Returns:
            Dictionary with recompute result
        """
        def _recompute():
            if document_name:
                doc = FreeCAD.getDocument(document_name)
            else:
                doc = FreeCAD.ActiveDocument
            
            if doc is None:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": "No active document"
                }
            
            try:
                doc.recompute()
                return {
                    "success": True,
                    "document": doc.Name,
                    "message": f"Recomputed document '{doc.Name}'"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to recompute: {e}"
                }
        
        return await bridge.execute(_recompute)


