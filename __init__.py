# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server Addon

Allows LLMs to control FreeCAD via a simple TCP server.

Usage:
    from freecad_mcp import start_server, stop_server
    start_server()  # Starts on port 9876
    
    # Test from terminal:
    echo '{"tool":"list_tools"}' | nc localhost 9876
"""

__version__ = "0.1.0"

_server_instance = None
_server_thread = None

DEFAULT_PORT = 9876


def start_server(port: int = DEFAULT_PORT):
    """
    Start the MCP server on the specified port.
    
    Args:
        port: TCP port to listen on (default: 9876)
    
    Returns:
        True if server started successfully
    """
    global _server_instance, _server_thread
    
    if _server_instance is not None:
        import FreeCAD
        FreeCAD.Console.PrintWarning("MCP Server is already running\n")
        return False
    
    from . import mcp_server
    _server_instance, _server_thread = mcp_server.start(port=port)
    
    return True


def stop_server():
    """Stop the MCP server."""
    global _server_instance, _server_thread
    
    if _server_instance is None:
        import FreeCAD
        FreeCAD.Console.PrintWarning("MCP Server is not running\n")
        return False
    
    from . import mcp_server
    mcp_server.stop()
    _server_instance = None
    _server_thread = None
    
    return True


def is_running() -> bool:
    """Check if the MCP server is currently running."""
    return _server_instance is not None
