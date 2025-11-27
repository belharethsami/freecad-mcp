# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Main server implementation

Uses a simple JSON-RPC server over TCP for communication with LLM clients.
"""

import asyncio
import threading
import json
import socket
from typing import Optional, Tuple, List

import FreeCAD

from .bridge import get_bridge, reset_bridge, MainThreadBridge


# Global instances
_server: Optional['SimpleMCPServer'] = None
_bridge: Optional[MainThreadBridge] = None
_server_thread: Optional[threading.Thread] = None

DEFAULT_PORT = 9876

# Tool definitions
TOOLS = {
    "new_document": {
        "description": "Create a new FreeCAD document",
        "parameters": {"name": "string (optional, default 'Unnamed')"}
    },
    "list_documents": {
        "description": "List all open FreeCAD documents",
        "parameters": {}
    },
    "list_objects": {
        "description": "List all objects in the active document",
        "parameters": {}
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
        "parameters": {"name": "string"}
    },
    "save_document": {
        "description": "Save the document",
        "parameters": {"path": "string (optional)"}
    },
    "recompute": {
        "description": "Recompute the document",
        "parameters": {}
    },
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool on the main thread."""
    
    def _execute():
        doc = FreeCAD.ActiveDocument
        
        if name == "new_document":
            doc_name = arguments.get("name", "Unnamed")
            doc = FreeCAD.newDocument(doc_name)
            return {"success": True, "document": doc.Name}
        
        elif name == "list_documents":
            docs = [{"name": d, "objects": len(FreeCAD.getDocument(d).Objects)} 
                    for d in FreeCAD.listDocuments()]
            return {"success": True, "documents": docs}
        
        elif name == "list_objects":
            if doc is None:
                return {"success": False, "error": "No active document"}
            objects = []
            for obj in doc.Objects:
                info = {"name": obj.Name, "type": obj.TypeId}
                if hasattr(obj, "Shape") and hasattr(obj.Shape, "Volume"):
                    info["volume"] = round(obj.Shape.Volume, 2)
                objects.append(info)
            return {"success": True, "objects": objects}
        
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
            if doc is None:
                return {"success": False, "error": "No active document"}
            objs = [doc.getObject(n) for n in arguments.get("objects", [])] if arguments.get("objects") else \
                   [o for o in doc.Objects if hasattr(o, "Shape")]
            objs = [o for o in objs if o]
            if not objs:
                return {"success": False, "error": "No objects"}
            mesh = Mesh.Mesh()
            for o in objs:
                mesh.addMesh(Mesh.Mesh(o.Shape.tessellate(0.1)[0]))
            mesh.write(arguments["path"])
            return {"success": True, "path": arguments["path"]}
        
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
            if doc is None:
                return {"success": False, "error": "No active document"}
            obj = doc.getObject(arguments["name"])
            if not obj:
                return {"success": False, "error": "Object not found"}
            info = {"name": obj.Name, "type": obj.TypeId}
            if hasattr(obj, "Shape"):
                s = obj.Shape
                info["volume"] = round(s.Volume, 2)
                info["area"] = round(s.Area, 2)
                b = s.BoundBox
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
        
        elif name == "list_tools":
            return {"success": True, "tools": TOOLS}
        
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}
    
    return _bridge.execute_sync(_execute)


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
