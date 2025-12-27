#!/bin/bash
# Test script for all FreeCAD MCP tools
# Usage: ./test_all_tools.sh
# Assumes FreeCAD is running with MCP server on port 9876

set -e

HOST="localhost"
PORT="9876"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper function to call MCP tool
call_tool() {
    local tool_name="$1"
    local args="$2"
    echo -e "${BLUE}[Testing]${NC} $tool_name"
    if [ -z "$args" ]; then
        result=$(echo "{\"tool\":\"$tool_name\",\"arguments\":{}}" | nc -w 5 $HOST $PORT 2>/dev/null)
    else
        result=$(echo "{\"tool\":\"$tool_name\",\"arguments\":$args}" | nc -w 5 $HOST $PORT 2>/dev/null)
    fi
    
    # Check if successful
    if echo "$result" | grep -q '"success": true\|"success":true'; then
        echo -e "${GREEN}[✓ PASS]${NC} $tool_name"
    else
        echo -e "${RED}[✗ FAIL]${NC} $tool_name"
        echo "  Response: $(echo "$result" | head -c 200)"
    fi
    echo ""
    sleep 0.3
}

echo "========================================"
echo "  FreeCAD MCP Tools Test Suite"
echo "========================================"
echo ""

# === DOCUMENT TOOLS ===
echo -e "${YELLOW}=== Document Tools ===${NC}"
call_tool "list_tools" ""
call_tool "new_document" '{"name":"TestDoc"}'
call_tool "list_documents" ""

# === PRIMITIVE CREATION ===
echo -e "${YELLOW}=== Primitive Creation ===${NC}"
call_tool "create_box" '{"length":50,"width":30,"height":20,"name":"TestBox"}'
call_tool "create_cylinder" '{"radius":10,"height":40,"name":"TestCylinder"}'
call_tool "create_sphere" '{"radius":15,"name":"TestSphere"}'
call_tool "create_cone" '{"radius1":20,"radius2":5,"height":30,"name":"TestCone"}'

# === OBJECT OPERATIONS ===
echo -e "${YELLOW}=== Object Operations ===${NC}"
call_tool "list_objects" ""
call_tool "get_object_info" '{"name":"TestBox"}'
call_tool "move_object" '{"name":"TestCylinder","x":60,"y":0,"z":0}'
call_tool "recompute" ""

# === BOOLEAN OPERATIONS ===
echo -e "${YELLOW}=== Boolean Operations ===${NC}"
call_tool "create_box" '{"length":30,"width":30,"height":30,"name":"BoolBase"}'
call_tool "create_cylinder" '{"radius":8,"height":40,"name":"BoolTool"}'
call_tool "move_object" '{"name":"BoolTool","x":15,"y":15,"z":-5}'
call_tool "boolean_cut" '{"base":"BoolBase","tool":"BoolTool","name":"CutResult"}'

call_tool "create_box" '{"length":20,"width":20,"height":20,"name":"UnionA"}'
call_tool "create_sphere" '{"radius":12,"name":"UnionB"}'
call_tool "move_object" '{"name":"UnionB","x":10,"y":10,"z":10}'
call_tool "boolean_union" '{"object1":"UnionA","object2":"UnionB","name":"UnionResult"}'

# === VIEW & SCREENSHOT TOOLS ===
echo -e "${YELLOW}=== View & Screenshot Tools ===${NC}"
call_tool "set_view" '{"preset":"isometric"}'
call_tool "fit_all" ""
call_tool "rotate_view" '{"yaw":30,"pitch":15}'
call_tool "zoom" '{"percent":120}'
call_tool "pan" '{"x":10,"y":-5}'
call_tool "take_screenshot" '{"width":400,"height":300}'

# === DISPLAY MODE TOOLS ===
echo -e "${YELLOW}=== Display Mode Tools ===${NC}"
call_tool "set_display_mode" '{"object":"TestBox","mode":"transparent","transparency":50}'
call_tool "set_display_mode" '{"object":"TestBox","mode":"wireframe"}'
call_tool "set_display_mode" '{"object":"TestBox","mode":"solid"}'
call_tool "set_visibility" '{"name":"TestSphere","visible":false}'
call_tool "set_visibility" '{"name":"TestSphere","visible":true}'

# === CLIPPING PLANE ===
echo -e "${YELLOW}=== Clipping Plane ===${NC}"
call_tool "set_clipping_plane" '{"axis":"X","percent":50,"enabled":true}'
call_tool "set_clipping_plane" '{"axis":"X","percent":50,"enabled":false}'

# === MEASUREMENT MODE ===
echo -e "${YELLOW}=== Measurement Mode ===${NC}"
call_tool "start_measurement" ""
call_tool "select_point" '{"grid_cell":"D3"}'
call_tool "list_points" ""
call_tool "confirm_point" '{"point_id":"point_1"}'
call_tool "select_point" '{"grid_cell":"F4"}'
call_tool "confirm_point" '{"point_id":"point_2"}'
call_tool "measure_distance" '{"point_a":"point_1","point_b":"point_2"}'
call_tool "zoom_grid_region" '{"start_cell":"C3","size":2}'
call_tool "reset_grid_zoom" ""
call_tool "clear_point" '{"point_id":"all"}'
call_tool "end_measurement" ""
call_tool "clear_measurements" ""

# === EXPORT TOOLS ===
echo -e "${YELLOW}=== Export Tools ===${NC}"
call_tool "export_stl" '{"path":"/tmp/mcp_test_export.stl","objects":["TestBox"]}'
call_tool "export_step" '{"path":"/tmp/mcp_test_export.step","objects":["TestBox"]}'

# === MESH COMPARISON ===
echo -e "${YELLOW}=== Mesh Comparison ===${NC}"
call_tool "get_mesh_points" '{"tessellation":0.5,"sample_rate":10}'
call_tool "compare_to_stl" '{"reference_path":"/tmp/mcp_test_export.stl","tolerance":1.0}'

# === STL IMPORT ===
echo -e "${YELLOW}=== STL Import ===${NC}"
call_tool "import_stl" '{"path":"/tmp/mcp_test_export.stl","name":"ImportedMesh"}'

# === CLEANUP ===
echo -e "${YELLOW}=== Cleanup ===${NC}"
call_tool "delete_object" '{"name":"TestBox"}'
call_tool "delete_object" '{"name":"TestCylinder"}'
call_tool "delete_object" '{"name":"TestSphere"}'
call_tool "delete_object" '{"name":"TestCone"}'

# === SAVE ===
echo -e "${YELLOW}=== Save ===${NC}"
call_tool "save_document" '{"path":"/tmp/mcp_test_document.FCStd"}'

echo "========================================"
echo -e "${GREEN}  Test suite complete!${NC}"
echo "========================================"

