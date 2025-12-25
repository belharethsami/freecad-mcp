# Process Explanation & Next Steps

## Reward Metrics Breakdown by Repository

### What's Calculated Where?

| Metric | `freecad_mcp` (Inside FreeCAD) | `freecad_openenv` (Outside FreeCAD) |
|--------|-------------------------------|-------------------------------------|
| **Hausdorff Distance** | ✅ `compare_to_stl` tool | ✅ `mesh_rewards.py` via trimesh |
| **Volume** | ✅ `Shape.Volume` (exact BREP) | ✅ `trimesh.volume` (from mesh) |
| **Surface Area** | ✅ `Shape.Area` (exact BREP) | ✅ `trimesh.area` (from mesh) |
| **Bounding Box IoU** | ✅ `get_shape_info` returns bbox | ✅ Can compute from mesh bounds |
| **Object Count** | ✅ `doc.Objects` count | ✅ Via MCP `get_shape_info` |
| **Point Cloud** | ✅ `get_mesh_points` tool | ✅ `trimesh.vertices` |

### Key Difference: BREP vs Mesh

```
freecad_mcp (BREP - Exact):
  - Shape.Volume = mathematically exact (π*r³ for sphere)
  - Shape.Area = mathematically exact
  - Must tessellate to compare with STL

freecad_openenv (Mesh - Approximation):
  - volume = sum of signed tetrahedra volumes
  - area = sum of triangle areas
  - Already discrete, direct comparison
```

---

## 1. Why MCP vs. freecad_openenv?

There are two approaches for shape comparison:

### Option A: In MCP (Inside FreeCAD)

```
freecad_openenv ──HTTP──→ MCP Server ──→ FreeCAD Python API
                                              ↓
                                         Compare shapes
```

**Pros:** 
- Direct access to FreeCAD's BREP geometry (exact mathematical representation)
- No file I/O overhead
- Lower latency for single comparisons

**Cons:** 
- Requires FreeCAD to be running
- Blocks FreeCAD's main thread
- Single-threaded

### Option B: In freecad_openenv (Outside FreeCAD) ✅ Better for batch!

```
freecad_openenv:
  1. Ask MCP to export current shape as STL/STEP
  2. Load both files with trimesh/Open3D (pure Python)
  3. Compare locally - no FreeCAD needed for comparison!
```

**This is better because:**
- Comparison logic is testable without FreeCAD
- Can run reward computation in parallel
- More libraries available (trimesh, Open3D, PyVista)

```python
# In freecad_openenv/mesh_rewards.py - NO MCP needed!
import trimesh

def compare_to_reference(reference_path: str, current_path: str) -> float:
    """Compare two mesh files directly in Python."""
    ref = trimesh.load(reference_path)
    current = trimesh.load(current_path)
    
    # Hausdorff distance
    distance = trimesh.proximity.max_distance(ref, current)
    
    return distance
```

### The Workflow

1. Agent creates shape via MCP tools
2. Environment calls `export_stl` via MCP to get current state
3. Environment compares STL files locally (no MCP needed)

---

## 2. Speed Comparison: Inside vs Outside FreeCAD

| Approach | Pros | Cons |
|----------|------|------|
| Inside FreeCAD | No file I/O, direct memory access | Blocks FreeCAD's main thread, single-threaded |
| Outside (trimesh) | Parallel processing, doesn't block FreeCAD | Requires export → file I/O overhead |

### Timing Breakdown

```
Inside FreeCAD:
  [Create shape] → [Compare in memory] → [Return reward]
  ~5ms              ~10-50ms              ~1ms

Outside FreeCAD:
  [Create shape] → [Export STL] → [Load in trimesh] → [Compare] → [Return]
  ~5ms              ~20-100ms     ~10-50ms            ~10-50ms    ~1ms
```

**Inside is faster if:**
- You're doing single comparisons
- FreeCAD is already loaded

**Outside is faster if:**
- You want to parallelize (run 100 comparisons at once)
- You're doing batch evaluation

---

## 3. How FreeCAD Processes an STL Reference

FreeCAD can import STL and convert it to a Mesh object, then compare:

```python
# Inside FreeCAD (in mcp_server.py compare_to_stl tool)
import FreeCAD
import Mesh
import numpy as np

def compare_to_stl(reference_stl_path: str, tolerance: float = 1.0):
    """Compare current document shapes to a reference STL."""
    
    doc = FreeCAD.ActiveDocument
    if not doc:
        return {"success": False, "error": "No document"}
    
    # 1. Load reference STL into FreeCAD as a Mesh
    ref_mesh = Mesh.Mesh(reference_stl_path)
    ref_points = np.array([[p.x, p.y, p.z] for p in ref_mesh.Points])
    
    # 2. Get current shapes and tessellate them
    current_points = []
    for obj in doc.Objects:
        if hasattr(obj, "Shape") and obj.Shape.Volume > 0:
            # Tessellate BREP to mesh (0.1mm tolerance)
            vertices, faces = obj.Shape.tessellate(0.1)
            for v in vertices:
                current_points.append([v.x, v.y, v.z])
    
    if not current_points:
        return {"success": False, "error": "No shapes in document"}
    
    current_points = np.array(current_points)
    
    # 3. Compute Hausdorff distance
    def min_distances(points_a, points_b):
        """For each point in A, find distance to closest point in B."""
        min_dists = []
        for p in points_a:
            dists = np.sqrt(np.sum((points_b - p) ** 2, axis=1))
            min_dists.append(np.min(dists))
        return np.array(min_dists)
    
    d_ref_to_current = min_distances(ref_points, current_points)
    d_current_to_ref = min_distances(current_points, ref_points)
    
    hausdorff = max(np.max(d_ref_to_current), np.max(d_current_to_ref))
    
    # 4. Get volumes and areas
    ref_volume = ref_mesh.Volume
    ref_area = ref_mesh.Area
    current_volume = sum(o.Shape.Volume for o in doc.Objects if hasattr(o, "Shape"))
    current_area = sum(o.Shape.Area for o in doc.Objects if hasattr(o, "Shape"))
    
    return {
        "success": True,
        "hausdorff_distance": float(hausdorff),
        "is_match": hausdorff <= tolerance,
        "reference_volume": ref_volume,
        "current_volume": current_volume,
        "volume_error": abs(ref_volume - current_volume) / ref_volume if ref_volume > 0 else 0,
        "reference_area": ref_area,
        "current_area": current_area,
        "area_error": abs(ref_area - current_area) / ref_area if ref_area > 0 else 0,
    }
```

### The Key Insight: BREP vs Mesh

FreeCAD stores shapes as BREP (exact math), but STL is a mesh (triangles):

```
BREP (Current Shape):          STL (Reference):
  - Exact sphere equation        - 1000 triangles approximating sphere
  - Infinite precision           - Fixed resolution
  - Can tessellate to any res    - Resolution is baked in

To compare, we must:
  1. Tessellate BREP → mesh
  2. Compare mesh to mesh
```

FreeCAD's `Shape.tessellate(tolerance)`:
```python
# tolerance = max deviation from true surface in mm
vertices, faces = shape.tessellate(0.1)  # 0.1mm accuracy

# Lower tolerance = more triangles = more accurate but slower
# 0.01mm → Very accurate, slow
# 0.1mm  → Good balance ✓
# 1.0mm  → Fast but rough
```

---

## 4. Extracting Constraints from Assembly Files

Yes! Assembly file formats contain constraint/relationship data:

### STEP Assembly (AP214/AP242)

STEP files contain:
- Individual parts as separate entities
- `PRODUCT_DEFINITION_RELATIONSHIP` - links parts together
- `REPRESENTATION_RELATIONSHIP` - positioning
- `GEOMETRIC_CONSTRAINT` - mates, alignments

### FreeCAD Assembly (.FCStd)

```python
# FreeCAD stores constraints in the Assembly workbench
import FreeCAD

doc = FreeCAD.openDocument("assembly.FCStd")
for obj in doc.Objects:
    if obj.TypeId == "Assembly::Constraint":
        print(f"Constraint: {obj.ConstraintType}")
        print(f"  Part A: {obj.Object1}")
        print(f"  Part B: {obj.Object2}")
        print(f"  Type: {obj.Type}")  # "Coincident", "Parallel", etc.
```

### Parsing STEP for Constraints

```python
# Using pythonOCC or cadquery
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.XSControl import XSControl_WorkSession

def extract_step_assembly(step_path: str):
    reader = STEPControl_Reader()
    reader.ReadFile(step_path)
    
    session = reader.WS()
    model = session.Model()
    
    parts = []
    constraints = []
    
    for entity in model.Entities():
        if entity.IsKind("PRODUCT_DEFINITION"):
            parts.append(parse_part(entity))
        elif entity.IsKind("SHAPE_ASPECT_RELATIONSHIP"):
            constraints.append(parse_constraint(entity))
    
    return parts, constraints
```

---

## 5. Open Source 3D Assembly Datasets

| Source | Format | Assemblies? | Size |
|--------|--------|-------------|------|
| ABC Dataset | STEP, STL | ❌ Parts only | 1M CAD models |
| **Fusion 360 Gallery** | STEP, JSON | ✅ Yes! | 20K assemblies |
| MCAD | STEP | ✅ Assemblies | 1K+ |
| TraceParts | STEP, STL | ✅ Industrial parts | Millions (free account) |
| GrabCAD | STEP, STL, FCStd | ✅ Community | 4M+ models |
| McMaster-Carr | STEP | ✅ Real parts | Hardware catalog |

### Best for RL Training: Fusion 360 Gallery

It includes:
- STEP files with full assembly structure
- JSON metadata with constraints
- Construction sequence (how it was built!)

```json
// Fusion 360 Gallery metadata example
{
  "assembly": {
    "components": [
      {"name": "base", "file": "base.step"},
      {"name": "shaft", "file": "shaft.step"}
    ],
    "joints": [
      {
        "type": "revolute",
        "component1": "base",
        "component2": "shaft",
        "origin": [0, 0, 50]
      }
    ]
  },
  "timeline": [
    {"action": "sketch", "plane": "XY"},
    {"action": "extrude", "distance": 20}
  ]
}
```

---

## 6. File Format Comparison

| Format | Parts | Assemblies | Constraints | Readable | Best For |
|--------|-------|------------|-------------|----------|----------|
| STL | ✅ | ❌ (merged only) | ❌ | Binary/ASCII | 3D printing, simple comparison |
| OBJ | ✅ | ❌ | ❌ | Text | Visualization |
| **STEP** | ✅ | ✅ | ✅ | Text (verbose) | CAD interchange, assemblies |
| IGES | ✅ | ⚠️ Limited | ❌ | Text | Legacy CAD |
| FCStd | ✅ | ✅ | ✅ | ZIP (XML inside) | FreeCAD native |
| 3MF | ✅ | ✅ | ❌ | ZIP (XML) | Modern 3D printing |
| JT | ✅ | ✅ | ✅ | Binary | Industry (Siemens) |
| glTF | ✅ | ✅ | ❌ | JSON+Binary | Web/visualization |

### Recommendation for RL Environment

```
Reference files: STEP (contains geometry + constraints + hierarchy)
                     ↓
              Parse with pythonOCC or cadquery
                     ↓
         Extract: parts, positions, constraints
                     ↓
         Task definition with full assembly info
```

---

## 7. Current Architecture

```
freecad_mcp/                  ← MCP Server (runs inside FreeCAD)
├── mcp_server.py             ← Tools: create_box, export_stl, compare_to_stl
├── tools/
│   ├── primitives.py         ← Shape creation
│   ├── operations.py         ← Boolean ops, transforms
│   └── export.py             ← STL/STEP export

freecad_openenv/              ← RL Environment (runs outside FreeCAD)
├── environment.py            ← Gymnasium-style env, calls MCP
├── rewards.py                ← Reward computation logic
├── mesh_rewards.py           ← Trimesh-based comparison
├── types.py                  ← Task, Observation, Action types
└── examples/
    └── test_stl_comparison.py
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    freecad_openenv (Python)                      │
│                                                                   │
│  Agent ──action──→ Environment ──JSON──→ MCP Client              │
│                         ↓                    ↓                    │
│                   Reward Calc           TCP Socket                │
│                   (trimesh)                  ↓                    │
└──────────────────────────────────────────────│───────────────────┘
                                               ↓
┌──────────────────────────────────────────────│───────────────────┐
│                    freecad_mcp (FreeCAD)     ↓                    │
│                                                                   │
│  TCP Server ←── mcp_server.py ──→ FreeCAD Python API             │
│       ↑                               ↓                          │
│   JSON Response                 Create/Modify Shapes             │
│                                       ↓                          │
│                              export_stl / compare_to_stl         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Recommendation Summary

| Scenario | Use |
|----------|-----|
| Development/Testing | Outside FreeCAD (trimesh) - easier to debug |
| Production Training | Inside FreeCAD - fewer moving parts |
| Batch Evaluation | Outside FreeCAD - can parallelize |
| Real-time Reward | Inside FreeCAD - lowest latency |

### Current Setup

1. **`compare_to_stl` tool in MCP** - for real-time reward during training
2. **`mesh_rewards.py` with trimesh** - for batch evaluation and testing

---

## 9. Next Steps

### Immediate (Implemented)
- [x] `compare_to_stl` tool in `freecad_mcp/mcp_server.py`
- [x] `mesh_rewards.py` in `freecad_openenv`
- [x] `export_stl` bug fix

### Short-term (TODO)
- [ ] `assembly_parser.py` - Parse STEP/FCStd for constraints
- [ ] Dataset loader for Fusion 360 Gallery
- [ ] `AssemblyTask` type in `types.py`
- [ ] Multi-part comparison (per-component matching)

### Long-term
- [ ] KD-tree optimization for Hausdorff (scipy.spatial.cKDTree)
- [ ] GPU-accelerated mesh comparison (PyTorch3D)
- [ ] Constraint satisfaction reward component
- [ ] Construction sequence learning (imitation learning from Fusion 360 timelines)

---

## 10. Testing the Current Setup

### Basic MCP Test (No freecad_openenv needed)

```bash
# 1. Start FreeCAD and run in Python console:
from freecad_mcp import start_server
start_server()

# 2. In terminal:
echo '{"tool":"new_document","arguments":{"name":"Test"}}' | nc localhost 9876
echo '{"tool":"create_box","arguments":{"length":50,"width":30,"height":20,"name":"RefBox"}}' | nc localhost 9876
echo '{"tool":"export_stl","arguments":{"path":"/tmp/reference_box.stl"}}' | nc localhost 9876
echo '{"tool":"compare_to_stl","arguments":{"reference_path":"/tmp/reference_box.stl","tolerance":1.0}}' | nc localhost 9876
```

### Full Environment Test (Requires freecad_openenv)

```python
# In separate Python environment with trimesh installed
from freecad_openenv.mesh_rewards import compare_stl_files, MeshRewardConfig

config = MeshRewardConfig(hausdorff_tolerance=2.0)
reward, success = compare_stl_files("/tmp/reference.stl", "/tmp/current.stl", config)
print(f"Reward: {reward}, Success: {success}")
```

