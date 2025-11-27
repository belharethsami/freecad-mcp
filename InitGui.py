# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCAD MCP Server - GUI initialization
"""

import FreeCAD
import FreeCADGui

FreeCAD.Console.PrintLog("Loading FreeCAD MCP Server addon...\n")


class StartMCPServerCommand:
    def GetResources(self):
        return {"MenuText": "Start MCP Server", "ToolTip": "Start the MCP server for LLM integration"}
    
    def IsActive(self):
        try:
            from . import is_running
            return not is_running()
        except:
            return True
    
    def Activated(self):
        from . import start_server
        start_server()


class StopMCPServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop MCP Server", "ToolTip": "Stop the MCP server"}
    
    def IsActive(self):
        try:
            from . import is_running
            return is_running()
        except:
            return False
    
    def Activated(self):
        from . import stop_server
        stop_server()


class MCPServerStatusCommand:
    def GetResources(self):
        return {"MenuText": "MCP Server Status", "ToolTip": "Show the current MCP server status"}
    
    def IsActive(self):
        return True
    
    def Activated(self):
        try:
            from PySide2 import QtWidgets
        except ImportError:
            from PySide6 import QtWidgets
        
        from . import is_running
        
        if is_running():
            status = "MCP Server is running.\n\nLLMs can now connect and control FreeCAD."
        else:
            status = "MCP Server is not running.\n\nUse 'Start MCP Server' to enable LLM integration."
        
        QtWidgets.QMessageBox.information(FreeCADGui.getMainWindow(), "MCP Server Status", status)


FreeCADGui.addCommand("MCP_StartServer", StartMCPServerCommand())
FreeCADGui.addCommand("MCP_StopServer", StopMCPServerCommand())
FreeCADGui.addCommand("MCP_Status", MCPServerStatusCommand())


def initialize():
    try:
        try:
            from PySide2 import QtWidgets
        except ImportError:
            from PySide6 import QtWidgets
        
        mw = FreeCADGui.getMainWindow()
        if mw:
            menu_bar = mw.menuBar()
            tools_menu = None
            for action in menu_bar.actions():
                if "Tools" in action.text():
                    tools_menu = action.menu()
                    break
            
            if tools_menu:
                mcp_menu = QtWidgets.QMenu("MCP Server", tools_menu)
                
                start_action = QtWidgets.QAction("Start MCP Server", mcp_menu)
                start_action.triggered.connect(lambda: FreeCADGui.runCommand("MCP_StartServer"))
                mcp_menu.addAction(start_action)
                
                stop_action = QtWidgets.QAction("Stop MCP Server", mcp_menu)
                stop_action.triggered.connect(lambda: FreeCADGui.runCommand("MCP_StopServer"))
                mcp_menu.addAction(stop_action)
                
                mcp_menu.addSeparator()
                
                status_action = QtWidgets.QAction("Status", mcp_menu)
                status_action.triggered.connect(lambda: FreeCADGui.runCommand("MCP_Status"))
                mcp_menu.addAction(status_action)
                
                tools_menu.addMenu(mcp_menu)
                FreeCAD.Console.PrintLog("MCP Server menu added to Tools\n")
    except Exception as e:
        FreeCAD.Console.PrintError(f"Error initializing MCP Server menu: {e}\n")


try:
    from PySide2 import QtCore
except ImportError:
    from PySide6 import QtCore

QtCore.QTimer.singleShot(2000, initialize)

FreeCAD.Console.PrintMessage("FreeCAD MCP Server addon loaded. Use Tools > MCP Server to start.\n")
