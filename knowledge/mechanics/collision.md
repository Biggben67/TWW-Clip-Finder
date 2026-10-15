# Stage collision geometry (the surfaces the game tests)

**Answers:** How is TWW's stage/room collision stored in RAM (the DZB triangle mesh)? How do I reach
the currently-loaded collision from a global? What's the vertex/triangle layout? How does the game
classify a triangle as ground vs wall vs roof? How do I see the live collision mesh in 3D?
**Status:** validated - the in-RAM `cBgD_t` layout matches Winditor's on-disk DZB format
byte-for-byte; live reader (`harness/collision/collision_geo.py`) walks the `dBgS` manager and
its floor-triangle report matches `dBgS_LinkAcch`'s current ground poly (stage `H_test`, GZLJ01,
2026-07-06). The land sim now consumes WALLS from this groundwork (see
[Sim integration status](#sim-integration-status) + [wall-response.md](wall-response.md)).
**Source:** decomp `SSystem/SComponent/c_bg_w.h` (`cBgD_t`/`cBgW`), `c_bg_s.h` (`cBgS` registry),
`d/d_bg_s.h` (`dBgS`), `d/actor/d_a_bg.cpp` (room load), `d_com_inf_game.h:4254` (`dComIfG_Bgsp`);
Winditor `Editor/Collision/CollisionMesh/*` (DZB format). Addresses:
[reference/addresses](../reference/addresses.md#collision-geometry-dzb--jpgzlj01-live-verified-2026-07-06).

---

## The model

Each **room** ships a `room.dzb` collision file (inside its RARC archive, at `dzb/room.dzb`). At
load the file is relocated in place (`cBgS::ConvDzb` turns its file-relative offsets into absolute
pointers) and wrapped in a runtime `cBgW`, which is registered into the global collision manager
`dBgS`. Movable objects (doors, platforms, pushable blocks) each register their own small `cBgW`.
Every collision query the player runs - ground height, wall correction, roof, line checks - walks
these registered meshes.

**The mesh is a plain indexed triangle soup.** The DZB header `cBgD_t` points at two flat arrays:

- **Vertices** - `cBgD_Vtx_t` = `Vec` = 3×f32 `(x,y,z)`, 12 bytes each, count `m_v_num`.
- **Triangles** - `cBgD_Tri_t`, 10 bytes each, count `m_t_num`:
  `u16 vtx0, vtx1, vtx2` (indices into the vertex array), `u16 id` (→ property/attribute table
  `m_ti_tbl`), `u16 grp` (→ group table `m_g_tbl`). The three vertices in DZB winding order define
  the face and its normal.

(Groups form a scene-graph tree with per-group transforms/room-ids/flags; an octree
`m_tree_tbl`/`m_b_tbl` accelerates queries. Neither is needed to reconstruct the drawable mesh.)

### Ground / wall / roof classification

The game classifies a triangle purely by its face-normal **Y** (`cBgW_CheckB*`, `c_bg_w.h`):

- `ny >= 0.5` → **ground** (walkable floor; the land sim's floor snap uses this bucket)
- `ny < -0.8` → **roof** (ceiling)
- otherwise → **wall**

Attribute/material codes (dirt, wood, stone, grass, lava, void, sand, ice, water …) are decoded from
the property record `m_ti_tbl[id]` via `dBgS::GetAttributeCode` / `GetGroundCode` etc.

## Reaching it live

The manager is a fixed global; **iterate its 256-slot registry** to enumerate all collision:

```
dBgS @ 0x803B93A8 (JP)   = g_dComIfG_gameInfo (0x803B8108) + play (0x12A0)
  cBgS::m_chk_element[256], stride 0x14:  +0x00 cBgW*  +0x04 flags (bit0 = slot in use)
cBgW (0xA8):  +0x6C mFlags (GLOBAL_e=0x20 static room, MOVE_BG_e=0x01 movable)
              +0x90 pm_vtx_tbl  ← WORLD-space verts (use this, NOT m_v_tbl)
              +0x94 pm_bgd → cBgD_t
cBgD_t:  +0x00 v_num  +0x04 v_tbl   +0x08 t_num  +0x0C t_tbl   +0x20 g_num  +0x24 g_tbl
```

The **slot index == the `mBgIndex`** carried in a `cBgS_PolyInfo` hit result, so Link's current
floor triangle (`dBgS_LinkAcch` @ `0x803BD910` → +0x554 polyIndex, +0x556 bgIndex; `0xFFFF`/`0x100`
= none) indexes directly back into `meshes[bgIndex].tris[polyIndex]`.

> **Read WORLD verts from `cBgW+0x90`, not the DZB `m_v_tbl` (`cBgD_t+0x04`).** For a static room
> (`GLOBAL_e`) they coincide, but a movable BG's base matrix is baked into `pm_vtx_tbl` - reading
> `m_v_tbl` for those draws the object at its untransformed local origin.

## Viewing it live (in-Dolphin 3D viewer)

`tww-python-scripts/collision_viewer.py` (sibling to `cull_viewer.py`) renders the live mesh: enable
it from Dolphin's Scripts panel while TWW runs. Orbit/pan/zoom around Link, triangles colored by
class (green ground / red wall / blue roof); **movable-BG objects** (doors/platforms/blocks) are
drawn in **purple** and always shown (exempt from the radius filter + distance cap, since they are
few and are the dynamic collision of interest). The floor triangle Link stands on is highlighted
yellow.
Link himself is a shaded **cyan 3D cone** whose apex faces his heading - it reads over the yellow
floor and shows facing at a glance. The visual-facing world vector is `(sin θ, 0, cos θ)` where
`θ = raw · 2π/65536` (u16 heading @ `0x803EA3D2`) - measured live against travel direction (raw
16384 east → +X, 49152 west → −X, 0 north → +Z).
The reader is `ww/collision_geo.py` (self-contained, same `rd.read_bytes` reader contract as
`ww/cull.py`); the canvas has no depth buffer, so filled triangles are painter-sorted and a
draw-radius slider bounds the drawn count on large rooms. Triangles are **near-plane clipped**
(Sutherland-Hodgman → a 3–4 pt polygon) before projection - without it, a *large* triangle that
straddles the camera plane (e.g. the ~95k-unit-tall Hyrule barrier / `Ycage00` cylinder walls) would
be dropped whole and vanish when you stand next to it.

> **GOTCHA - the canvas builds ONE ImGui draw list with 16-bit indices (65535-vertex ceiling).**
> Drawing a whole room's filled+wireframe triangles overruns it and **crashes the core** (a hard
> native crash, not a catchable Python error). The viewer enforces a per-frame **hard cap** (draw
> only the nearest ~1100 tris with wireframe on) so it can never overflow regardless of zoom. Any
> new canvas that emits thousands of primitives per frame needs the same guard. (The cap ranks by
> world distance **to Link**, not to the orbiting camera - otherwise geometry right by the player
> gets dropped in favor of whatever is nearest the eye.)

**Perf.** The script runs on the emu thread, so per-frame Python cost directly throttles emulation.
Two things keep it cheap: (1) the reader caches each mesh's raw tables **and** derived per-triangle
**centroid + surface class** (computed once for the static room, only re-derived for the few movable
meshes) - the viewer never recomputes `tri_normal`/`classify` per frame; (2) the nearest-Link cap is
applied via a partial sort **before** projection, so only ~`cap` triangles are ever projected, not
the whole room. Together these cut the per-frame draw-prep ~3× (≈19 ms → ≈6 ms on a 4.8k-tri stage).

## Sim integration status

**WALLS ARE IN THE STEPPER** (Phase W, live-gated 0-ULP 2026-07-10): `LandState(walls=...)` runs
the player-faithful `CrrPos` wall pass every frame, with the wall-hit state feeding the procs
(wall-hold, roll bonk, the sidle roll-guard). The full model + its open edges (corner poly
ordering, full-room mesh, ground slopes) live in [wall-response.md](wall-response.md); the exact
acch layer is `core.collision.acch_crr_pos`. `GroundCross`/`RoofChk` (slopes, ceilings) and the
game's octree traversal order are still unmodeled: flat floors only (Phase G scopes the rest).

## See also
- [mechanics/seam-clip.md](seam-clip.md) - why seam clips work (the float-precision root cause) + the FP-faithful `CrrPos` port and live validator.
- [reference/addresses.md](../reference/addresses.md#collision-geometry-dzb--jpgzlj01-live-verified-2026-07-06) - the address/offset table.
- [mechanics/culling.md](culling.md) - the sibling live in-Dolphin viewer (`cull_viewer.py`) and its reader pattern.
- [mechanics/land-movement.md](land-movement.md) - how the sim currently handles ground (flat-floor snap) and the reachability caveat.
