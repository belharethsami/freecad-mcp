#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Bridge

This script implements a proper MCP (Model Context Protocol) server that
communicates with Cursor/Claude via stdio, and forwards tool calls to
the FreeCAD TCP server running on port 9876.

Usage:
    1. Start FreeCAD and run: start_server()
    2. Configure Cursor to use this bridge (see below)

Cursor MCP Configuration (~/.cursor/mcp.json):
{
  "mcpServers": {
    "freecad": {
      "command": "python3",
      "args": ["/path/to/freecad_mcp/mcp_bridge.py"]
    }
  }
}
"""

import asyncio
import json
import socket
import sys
from typing import Any

# MCP Protocol version
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "freecad-mcp"
SERVER_VERSION = "0.1.0"

# FreeCAD TCP server settings
FREECAD_HOST = "127.0.0.1"
FREECAD_PORT = 9876


def send_to_freecad(tool: str, arguments: dict = None) -> dict:
    """Send a request to the FreeCAD TCP server."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((FREECAD_HOST, FREECAD_PORT))
        
        request = {"tool": tool, "arguments": arguments or {}}
        sock.sendall((json.dumps(request) + "\n").encode('utf-8'))
        
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break
        
        sock.close()
        return json.loads(response.decode('utf-8').strip())
    except ConnectionRefusedError:
        return {"success": False, "error": "FreeCAD server not running. Start it with: from freecad_mcp import start_server; start_server()"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tools() -> list:
    """Get tool definitions in MCP format."""
    return [
        {
            "name": "new_document",
            "description": "Create a new FreeCAD document",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Document name", "default": "Unnamed"}
                }
            }
        },
        {
            "name": "list_documents",
            "description": "List all open FreeCAD documents",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "list_objects",
            "description": "List all objects in the active document",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "create_box",
            "description": "Create a 3D box/cuboid primitive. All dimensions in millimeters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "length": {"type": "number", "description": "Length (X dimension) in mm"},
                    "width": {"type": "number", "description": "Width (Y dimension) in mm"},
                    "height": {"type": "number", "description": "Height (Z dimension) in mm"},
                    "name": {"type": "string", "description": "Object name", "default": "Box"}
                },
                "required": ["length", "width", "height"]
            }
        },
        {
            "name": "create_cylinder",
            "description": "Create a cylinder primitive. Dimensions in millimeters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "Radius in mm"},
                    "height": {"type": "number", "description": "Height in mm"},
                    "name": {"type": "string", "description": "Object name", "default": "Cylinder"}
                },
                "required": ["radius", "height"]
            }
        },
        {
            "name": "create_sphere",
            "description": "Create a sphere primitive.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "Radius in mm"},
                    "name": {"type": "string", "description": "Object name", "default": "Sphere"}
                },
                "required": ["radius"]
            }
        },
        {
            "name": "create_cone",
            "description": "Create a cone primitive. Use radius2=0 for a pointed cone.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "radius1": {"type": "number", "description": "Bottom radius in mm"},
                    "radius2": {"type": "number", "description": "Top radius in mm (0 for pointed)"},
                    "height": {"type": "number", "description": "Height in mm"},
                    "name": {"type": "string", "description": "Object name", "default": "Cone"}
                },
                "required": ["radius1", "radius2", "height"]
            }
        },
        {
            "name": "boolean_union",
            "description": "Combine two objects into one (union/fusion)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object1": {"type": "string", "description": "First object name"},
                    "object2": {"type": "string", "description": "Second object name"},
                    "name": {"type": "string", "description": "Result name", "default": "Union"}
                },
                "required": ["object1", "object2"]
            }
        },
        {
            "name": "boolean_cut",
            "description": "Cut/subtract one object from another",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "Base object (to cut from)"},
                    "tool": {"type": "string", "description": "Tool object (to cut with)"},
                    "name": {"type": "string", "description": "Result name", "default": "Cut"}
                },
                "required": ["base", "tool"]
            }
        },
        {
            "name": "move_object",
            "description": "Move/translate an object by an offset",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Object name"},
                    "x": {"type": "number", "description": "X offset in mm", "default": 0},
                    "y": {"type": "number", "description": "Y offset in mm", "default": 0},
                    "z": {"type": "number", "description": "Z offset in mm", "default": 0}
                },
                "required": ["name"]
            }
        },
        {
            "name": "delete_object",
            "description": "Delete an object from the document",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Object name to delete"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "get_object_info",
            "description": "Get detailed information about an object (volume, surface area, bounding box)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Object name"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "export_stl",
            "description": "Export objects to STL file (for 3D printing)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Output file path (.stl)"},
                    "objects": {"type": "array", "items": {"type": "string"}, "description": "Object names (optional, exports all if empty)"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "export_step",
            "description": "Export objects to STEP file (CAD interchange format)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Output file path (.step)"},
                    "objects": {"type": "array", "items": {"type": "string"}, "description": "Object names (optional, exports all if empty)"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "save_document",
            "description": "Save the FreeCAD document",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (.FCStd) - required for new documents"}
                }
            }
        },
        {
            "name": "recompute",
            "description": "Recompute/refresh the document to update all objects",
            "inputSchema": {"type": "object", "properties": {}}
        }
    ]


def handle_request(request: dict) -> dict:
    """Handle an MCP request and return a response."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION
                }
            }
        }
    
    elif method == "notifications/initialized":
        # This is a notification, no response needed
        return None
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": get_tools()
            }
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        # Forward to FreeCAD
        result = send_to_freecad(tool_name, arguments)
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        }
    
    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {}
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


async def main():
    """Main entry point - read from stdin, write to stdout."""
    # Use line-buffered I/O
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    
    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())
    
    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            
            request = json.loads(line.decode('utf-8').strip())
            response = handle_request(request)
            
            if response:  # Don't send response for notifications
                writer.write((json.dumps(response) + "\n").encode('utf-8'))
                await writer.drain()
                
        except json.JSONDecodeError as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {e}"
                }
            }
            writer.write((json.dumps(error_response) + "\n").encode('utf-8'))
            await writer.drain()
        except Exception as e:
            # Log to stderr (won't interfere with MCP protocol on stdout)
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

