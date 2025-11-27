# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - Headless initialization

This file is loaded by FreeCAD when running in console/headless mode (FreeCADCmd).
It registers the addon but doesn't start the GUI components.
"""

import FreeCAD

FreeCAD.Console.PrintLog("Loading FreeCAD MCP Server addon (headless mode)...\n")

# The MCP server can still be started in headless mode via:
# >>> from freecad_mcp import start_server
# >>> start_server()


