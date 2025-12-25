# FreeCAD MCP Server

A plugin that allows LLMs (like Claude) to control FreeCAD in real-time through a simple TCP server. Watch as AI creates 3D models while you see changes rendered live in FreeCAD!

## Features

- **No compilation required** - Pure Python addon
- **Real-time visualization** - See changes instantly in FreeCAD's 3D viewport
- **Simple JSON protocol** - Easy to integrate with any LLM
- **16 tools included** - Create shapes, boolean operations, export, and more

## Quick Install (macOS)

```bash
# 1. Find your FreeCAD Mod directory and create it if needed
mkdir -p ~/Library/Application\ Support/FreeCAD/Mod

# 2. Download/clone the addon
cd ~/Library/Application\ Support/FreeCAD/Mod
git clone https://github.com/YOUR_REPO/freecad_mcp.git
# Or manually copy the freecad_mcp folder here

# 3. Restart FreeCAD
```

## Quick Install (Linux)

```bash
# 1. Find your FreeCAD Mod directory and create it if needed
mkdir -p ~/.local/share/FreeCAD/Mod

# 2. Download/clone the addon
cd ~/.local/share/FreeCAD/Mod
git clone https://github.com/YOUR_REPO/freecad_mcp.git
# Or manually copy the freecad_mcp folder here

# 3. Restart FreeCAD
```

## Quick Install (Windows)

```powershell
# 1. Open PowerShell and create the Mod directory if needed
mkdir "$env:APPDATA\FreeCAD\Mod" -Force

# 2. Download/clone the addon
cd "$env:APPDATA\FreeCAD\Mod"
git clone https://github.com/YOUR_REPO/freecad_mcp.git
# Or manually copy the freecad_mcp folder here

# 3. Restart FreeCAD
```

## Finding Your FreeCAD Mod Directory

If you're unsure where your FreeCAD Mod directory is, open FreeCAD and run this in the Python console (View > Panels > Python Console):

```python
import FreeCAD
print(FreeCAD.getUserAppDataDir() + "Mod")
```

This will print the exact path where you should install the addon.

## Verifying Installation

After restarting FreeCAD, you should see this message in the console:
```
FreeCAD MCP Server addon loaded. Use Tools > MCP Server to start.
```

You can also check by running in FreeCAD's Python console:
```python
from freecad_mcp import start_server
```

If this runs without error, the addon is installed correctly.

## Starting the Server

### Option 1: From FreeCAD's Python Console

```python
from freecad_mcp import start_server
start_server()
```

You should see:
```
MCP Server started on port 9876
MCP Server listening on port 9876
```

### Option 2: From the Menu

Go to `Tools > MCP Server > Start MCP Server`

## Testing the Server

Open a **new terminal window** (not inside FreeCAD) and run:

```bash
# List available tools
echo '{"tool":"list_tools"}' | nc localhost 9876

# Create a box (50mm x 30mm x 20mm)
echo '{"tool":"create_box","arguments":{"length":50,"width":30,"height":20}}' | nc localhost 9876

# Create a cylinder
echo '{"tool":"create_cylinder","arguments":{"radius":10,"height":40}}' | nc localhost 9876

# List all objects
echo '{"tool":"list_objects"}' | nc localhost 9876
```

You should see the shapes appear in FreeCAD's 3D viewport!

## Available Tools

| Tool | Description | Required Arguments |
|------|-------------|-------------------|
| `list_tools` | List all available tools | none |
| `new_document` | Create a new document | `name` (optional) |
| `list_documents` | List all open documents | none |
| `list_objects` | List objects in active document | none |
| `create_box` | Create a box | `length`, `width`, `height`, `name` (optional) |
| `create_cylinder` | Create a cylinder | `radius`, `height`, `name` (optional) |
| `create_sphere` | Create a sphere | `radius`, `name` (optional) |
| `create_cone` | Create a cone | `radius1`, `radius2`, `height`, `name` (optional) |
| `boolean_union` | Unite two objects | `object1`, `object2`, `name` (optional) |
| `boolean_cut` | Cut one object from another | `base`, `tool`, `name` (optional) |
| `move_object` | Move an object | `name`, `x`, `y`, `z` (all optional except name) |
| `delete_object` | Delete an object | `name` |
| `get_object_info` | Get object details | `name` |
| `export_stl` | Export to STL | `path`, `objects` (optional array) |
| `export_step` | Export to STEP | `path`, `objects` (optional array) |
| `save_document` | Save the document | `path` (optional) |
| `recompute` | Recompute document | none |
| `compare_to_stl` | Compare shapes to reference STL | `reference_path`, `tolerance` (optional) |
| `get_mesh_points` | Export mesh as point cloud | `tessellation` (optional), `sample_rate` (optional) |

### STL Comparison Tool

The `compare_to_stl` tool compares current document shapes against a reference STL file using Hausdorff distance. **No additional packages required** - this works with just `freecad_mcp` and FreeCAD.

#### Complete Test Example

1. **Start FreeCAD** and run in the Python console:
   ```python
   from freecad_mcp import start_server
   start_server()
   ```

2. **In a separate terminal**, run these commands:

```bash
# Create document and box
echo '{"tool":"new_document","arguments":{"name":"Test"}}' | nc localhost 9876
echo '{"tool":"create_box","arguments":{"length":50,"width":30,"height":20,"name":"RefBox"}}' | nc localhost 9876

# Export to STL
echo '{"tool":"export_stl","arguments":{"path":"/tmp/reference_box.stl"}}' | nc localhost 9876

# Verify file exists
ls -la /tmp/reference_box.stl

# Compare current shapes to the reference (should match perfectly)
echo '{"tool":"compare_to_stl","arguments":{"reference_path":"/tmp/reference_box.stl","tolerance":1.0}}' | nc localhost 9876
```

Expected response:
```json
{
  "success": true,
  "hausdorff_distance": 0.0,
  "is_match": true,
  "reference_volume": 30000.0,
  "current_volume": 30000.0,
  "volume_error": 0.0,
  "area_error": 0.0
}
```

#### Testing Shape Mismatch

```bash
# Delete and create wrong size box
echo '{"tool":"delete_object","arguments":{"name":"RefBox"}}' | nc localhost 9876
echo '{"tool":"create_box","arguments":{"length":40,"width":25,"height":15,"name":"WrongBox"}}' | nc localhost 9876

# Compare - should show mismatch
echo '{"tool":"compare_to_stl","arguments":{"reference_path":"/tmp/reference_box.stl","tolerance":1.0}}' | nc localhost 9876
```

This will return `"is_match": false` with non-zero `hausdorff_distance` and `volume_error`.

#### Reloading After Code Changes

If you modify `mcp_server.py`, reload without restarting FreeCAD:

```python
# In FreeCAD Python console
from freecad_mcp import stop_server
stop_server()

import importlib
from freecad_mcp import mcp_server
importlib.reload(mcp_server)

from freecad_mcp import start_server
start_server()
```

#### Response Fields

| Field | Description |
|-------|-------------|
| `hausdorff_distance` | Maximum geometric deviation in mm |
| `volume_error` | Relative volume difference (0-1) |
| `area_error` | Relative surface area difference (0-1) |
| `is_match` | `true` if within tolerance |
| `reference_volume` | Volume of reference STL (mm³) |
| `current_volume` | Volume of current shapes (mm³) |

## Request Format

Send JSON requests to `localhost:9876`:

```json
{
  "tool": "tool_name",
  "arguments": {
    "arg1": "value1",
    "arg2": "value2"
  }
}
```

## Example: Creating a Box with a Hole

```bash
# Create a box
echo '{"tool":"create_box","arguments":{"length":50,"width":50,"height":20,"name":"Base"}}' | nc localhost 9876

# Create a cylinder for the hole
echo '{"tool":"create_cylinder","arguments":{"radius":10,"height":30,"name":"Hole"}}' | nc localhost 9876

# Move the cylinder to center of box
echo '{"tool":"move_object","arguments":{"name":"Hole","x":25,"y":25,"z":-5}}' | nc localhost 9876

# Cut the hole from the box
echo '{"tool":"boolean_cut","arguments":{"base":"Base","tool":"Hole","name":"BoxWithHole"}}' | nc localhost 9876

# Export to STL
echo '{"tool":"export_stl","arguments":{"path":"/tmp/box_with_hole.stl","objects":["BoxWithHole"]}}' | nc localhost 9876
```

## Integration with Cursor (MCP)

This addon includes a proper MCP bridge (`mcp_bridge.py`) that implements the Model Context Protocol, allowing Cursor to directly communicate with FreeCAD.

### Setup

1. **Start FreeCAD** and run the TCP server:
   ```python
   from freecad_mcp import start_server
   start_server()
   ```

2. **Configure Cursor** - Create or edit `~/.cursor/mcp.json`:
   ```json
   {
     "mcpServers": {
       "freecad": {
         "command": "python3",
         "args": ["/Users/YOUR_USERNAME/Library/Application Support/FreeCAD/Mod/freecad_mcp/mcp_bridge.py"]
       }
     }
   }
   ```
   
   **For Linux:**
   ```json
   {
     "mcpServers": {
       "freecad": {
         "command": "python3",
         "args": ["/home/YOUR_USERNAME/.local/share/FreeCAD/Mod/freecad_mcp/mcp_bridge.py"]
       }
     }
   }
   ```

3. **Restart Cursor** to load the MCP configuration

### How It Works

```
┌─────────────┐     stdio      ┌─────────────┐     TCP:9876    ┌─────────────┐
│   Cursor    │ ◄────────────► │ mcp_bridge  │ ◄─────────────► │  FreeCAD    │
│  (Claude)   │   MCP Protocol │   .py       │   JSON requests │  TCP Server │
└─────────────┘                └─────────────┘                 └─────────────┘
```

- **Cursor** speaks MCP protocol over stdio
- **mcp_bridge.py** translates MCP to our simple JSON format
- **FreeCAD TCP server** executes the tools and returns results

### Testing the MCP Bridge

```bash
# Test that the bridge can connect to FreeCAD
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 mcp_bridge.py
```

## Stopping the Server

```python
from freecad_mcp import stop_server
stop_server()
```

Or use the menu: `Tools > MCP Server > Stop MCP Server`

## Troubleshooting

### "Connection refused" when using nc

Make sure the server is running in FreeCAD:
```python
from freecad_mcp import start_server
start_server()
```

### "Module not found" error

Make sure the addon is in the correct directory. Run this in FreeCAD:
```python
import FreeCAD
print(FreeCAD.getUserAppDataDir() + "Mod")
```

### Server won't start

If you get an "Address already in use" error, the server might already be running, or another process is using port 9876. Try:
```python
from freecad_mcp import stop_server, start_server
stop_server()
start_server()
```

Or use a different port:
```python
start_server(port=9877)
```

## File Structure

```
freecad_mcp/
├── __init__.py      # Main entry point, imports from mcp_server.py
├── Init.py          # FreeCAD headless init
├── InitGui.py       # GUI menu integration
├── mcp_server.py    # TCP server and ALL TOOLS (main file)
├── bridge.py        # Thread-safe execution bridge
├── mcp_bridge.py    # MCP protocol translation for Cursor
├── tools/           # (Tool modules - simplified)
└── README.md        # This file
```

## Development Workflow

### Understanding the Architecture

FreeCAD loads addons from a **specific directory**, not your working directory:

| OS | Addon Directory |
|----|-----------------|
| macOS | `~/Library/Application Support/FreeCAD/Mod/` |
| Linux | `~/.local/share/FreeCAD/Mod/` |
| Windows | `%APPDATA%\FreeCAD\Mod\` |

The `freecad_mcp/` folder runs **inside FreeCAD** as an addon. If you also have `freecad_openenv/` (the RL environment), that runs **outside FreeCAD** and connects via TCP:

```
Your project:
├── freecad_mcp/        ← Runs INSIDE FreeCAD (addon)
│   └── mcp_server.py   ← Tools that FreeCAD executes
│
└── freecad_openenv/    ← Runs OUTSIDE FreeCAD (separate Python)
    ├── environment.py  ← RL environment (connects via TCP)
    └── mesh_rewards.py ← External mesh comparison
```

### Option 1: Symlink (Recommended)

Create a symlink so FreeCAD always uses your development copy:

```bash
# macOS
rm -rf ~/Library/Application\ Support/FreeCAD/Mod/freecad_mcp
ln -s /path/to/your/project/freecad_mcp ~/Library/Application\ Support/FreeCAD/Mod/freecad_mcp

# Linux
rm -rf ~/.local/share/FreeCAD/Mod/freecad_mcp
ln -s /path/to/your/project/freecad_mcp ~/.local/share/FreeCAD/Mod/freecad_mcp
```

With symlinks, changes are automatic - just restart FreeCAD or reload the module.

### Option 2: Copy Changed Files

If you modify `mcp_server.py` (where all tools are defined), copy just that file:

```bash
# macOS
cp /path/to/your/project/freecad_mcp/mcp_server.py \
   ~/Library/Application\ Support/FreeCAD/Mod/freecad_mcp/

# Linux
cp /path/to/your/project/freecad_mcp/mcp_server.py \
   ~/.local/share/FreeCAD/Mod/freecad_mcp/
```

You only need to copy files you've changed. The other files (`__init__.py`, `bridge.py`, etc.) don't need updating if unchanged.

### Reloading Without Restart

After copying updated files, reload in FreeCAD's Python console:

```python
from freecad_mcp import stop_server
stop_server()

import importlib
from freecad_mcp import mcp_server
importlib.reload(mcp_server)

from freecad_mcp import start_server
start_server()
```

## License

LGPL-2.1-or-later (same as FreeCAD)
