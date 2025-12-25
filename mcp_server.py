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
