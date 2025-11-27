#!/usr/bin/env python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Standalone Runner

This script runs the MCP server in standalone mode, designed to be called
from Cursor's MCP configuration. It initializes FreeCAD headless and starts
the server with stdio transport.

Usage in .cursor/mcp.json:
{
  "mcpServers": {
    "freecad": {
      "command": "/path/to/FreeCAD/python",
      "args": ["/path/to/freecad-mcp/run_standalone.py"]
    }
  }
}
"""

import sys
import os

def setup_freecad():
    """Setup FreeCAD environment for headless operation."""
    # Try to find FreeCAD lib path
    possible_paths = [
        # macOS
        "/Applications/FreeCAD.app/Contents/Resources/lib",
        "/Applications/FreeCAD.app/Contents/lib",
        os.path.expanduser("~/Applications/FreeCAD.app/Contents/Resources/lib"),
        # Linux
        "/usr/lib/freecad/lib",
        "/usr/lib/freecad-python3/lib",
        "/usr/local/lib/freecad/lib",
        # From environment
        os.environ.get("FREECAD_LIB_PATH", ""),
        os.environ.get("PATH_TO_FREECAD_LIBDIR", ""),
    ]
    
    # Add any found paths to sys.path
    for path in possible_paths:
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    
    # Try to import FreeCAD
    try:
        import FreeCAD
        return True
    except ImportError as e:
        print(f"Error: Could not import FreeCAD: {e}", file=sys.stderr)
        print("Please set FREECAD_LIB_PATH environment variable to your FreeCAD lib directory", file=sys.stderr)
        return False


def main():
    """Main entry point for standalone MCP server."""
    if not setup_freecad():
        sys.exit(1)
    
    # Now import our modules (after FreeCAD is available)
    import FreeCAD
    
    # Add addon path to import path
    addon_path = os.path.dirname(os.path.abspath(__file__))
    if addon_path not in sys.path:
        sys.path.insert(0, os.path.dirname(addon_path))
    
    FreeCAD.Console.PrintMessage("Starting FreeCAD MCP Server (standalone mode)...\n")
    
    # Import and run the server
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import asyncio
        
        # Create server
        server = Server("freecad-mcp")
        
        # Import and register tools
        # Note: We need to handle this differently in standalone mode
        # since we don't have the Qt event loop for the bridge
        
        from freecad_mcp.tools.document import register_document_tools
        from freecad_mcp.tools.primitives import register_primitive_tools
        from freecad_mcp.tools.operations import register_operation_tools
        from freecad_mcp.tools.partdesign import register_partdesign_tools
        from freecad_mcp.tools.export import register_export_tools
        from freecad_mcp.tools.query import register_query_tools
        
        # In standalone mode, we use a simpler bridge that executes directly
        class StandaloneBridge:
            async def execute(self, func):
                return func()
        
        bridge = StandaloneBridge()
        
        register_document_tools(server, bridge)
        register_primitive_tools(server, bridge)
        register_operation_tools(server, bridge)
        register_partdesign_tools(server, bridge)
        register_export_tools(server, bridge)
        register_query_tools(server, bridge)
        
        # Run server
        async def run():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options()
                )
        
        asyncio.run(run())
        
    except ImportError as e:
        print(f"Error: Missing dependency: {e}", file=sys.stderr)
        print("Please install the mcp package: pip install mcp", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


