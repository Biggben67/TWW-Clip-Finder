# Player wall response (the per-frame CrrPos wall pass)

**Answers:** What does the game do, each frame, when Link's body meets a wall? Where in the frame
does the correction run, what state does it leave for the procs, and how does the sim reproduce it
0-ULP? Why does A against a wall not roll? When does a roll bonk vs grind?
**Status:** LIVE-GATED 0-ULP (2026-07-10): four single-face clean-DTM gates on a minted kaze r11
anchor (head-on hold, oblique slide, roll bonk/crash, slow-roll grind) plus a CORNER gate (walk
into the 110-degree seam vertex, two walls correct per frame) all per-frame bit-exact.
Regression: `tests/test_rollstab_walls.py` + `tests/test_rollstab_corner.py` (live goldens) +
`tests/test_land_walls.py` (mechanics).
**Source:** decomp `d_a_player_main.cpp` (execute 11407-11411, setBgCheckParam 10680,
setNormalSpeedF 2311, procFrontRoll 6838/6869, procFrontRollCrash 6891, setFrontWallType 4552),
`d_bg_s_acch.cpp` (CrrPos 209, LineCheck 175), `d_bg_w.cpp` (RwgWallCorrect 43, WallCorrectRp 261,
WallCorrectGrpRp 296), `c_bg_w.cpp` (ClassifyPlane 145); session-11/12 handoffs.
Constants: [reference/constants.md#land-movement](../reference/constants.md#land-movement).

## Where the wall pass sits in the frame

Player execute order: procs run, then `posMove()` integrates `current.pos += speed`, then
**`mAcch.CrrPos`** (the collision pass), then water/ground bookkeeping, and `setWorldMatrix`
draws at the END of the frame. So the wall response sees the POST-integration position, and the
drawn pose is at the POST-correction position. Inside `CrrPos` the wall part is: conditional
**LineCheck** (swept centre line), then **WallCorrect** (static cylinder push-out), then a
re-LineCheck if a wall corrected, then roof, then **GroundCheck** (snaps y up, zeroes `speed.y`).

Two details that took live diffing to get right:

- **The player line-checks EVERY frame.** The `LINE_CHECK` flag is on for all non-HANG procs, so
  the "only when displacement > radius" shortcut is wrong for Link.
- **WallCorrect sees the mid-frame gravity dip.** `posMoveFromFootPos` adds gravity (-2.5) to the
  snap-zeroed `speed.y` and integrates it BEFORE CrrPos; the ground snap comes after. The slice
  height per cylinder is `sp7C = GetWallAddY + (pos.y + wallH) - speed.y` with the dipped
  `pos.y`: deterministic, but not algebraically `ground + wallH` in f32. `GetWallAddY` (the
  previous ground plane's slope lift) is exactly 0 on a flat floor.

Link's wall body = three cylinders at heights {30.1, 89.9, 125.0}, radius 35 (normal ground
state; crawl/swim/hang differ, see `setBgCheckParam`). On a LineCheck wall hit the game snaps to
the crossing, **adds one full unit of the plane normal**, latches `SetWallHDirect(pos.y)` (which
replaces that cylinder's `sp7C`), then subtracts the cylinder height. The `sqrtf` throughout is
the console's MSL frsqrte + 3 double Newton iterations, not a correctly-rounded sqrt.

## The wall-hit state the procs read (one frame late)

CrrPos leaves `mAcch.ChkWallHit()` (aggregate), per-cylinder `mAcchCir[i].ChkWallHit()`, and
`SetWallAngleY(cM_atan2s(n.x, n.z))`. Procs run before the frame's CrrPos, so they see the
PREVIOUS frame's flags. Consumers:

- **Wall-hold** (`setNormalSpeedF` 2311): heading into a hit wall (`|travel+0x8000 -
  wallAngleY| < 0x4000`) scales the target speed by `1 - cos(diff)*0.6`. A head-on walk holds at
  0.4x target while the cylinder pins the position at the 35u tangent.
- **Roll bonk** (`procFrontRoll` 6869): crash fires iff speedF >= 10, the roll did NOT start
  against the wall (the `m3570` init latch, same head-on test), cir0 hit, head-on within 5000,
  and the ROLLF anim frame is in [6, 15]. `procFrontRollCrash`: `nspeed = speedF*0.4` with travel
  reversed, `speed.y = 7` (airborne bounce), ROLLFMIS frozen at frame 6 until the landing, then
  played at 0.7/frame to 24. **A roll that misses any window grinds instead**: it coasts pinned
  against the face for its full length (a sub-10-speed roll, or an off-angle > 5000 hit like the
  seam-corner rolls).
- **Sidle preempts the roll**: A while wall-hit with facing within 0x2000 of head-on (and a
  25+radius facing ray hitting a steep `|n_y| <= 0.05` wall) sets `mFrontWallType = 2`, doStatus
  SIDLE, `procWHideReady`. The ATTACK/roll dispatch never runs. You cannot roll from against a
  wall; back off or face > 45 deg away first.

## Corner ordering: two walls in one frame (the DZB traversal)

WallCorrect pushes the cylinder out of each overlapping wall SEQUENTIALLY -- every correction
moves the position the next one sees -- so when two non-coplanar walls engage in one frame (a
corner) the poly VISITATION ORDER changes the resolved position. The order is fixed by the DZB
block-grid walk (`d_bg_w.cpp`): `WallCorrectGrpRp` (groups: this group's octree first via
`m_tree_idx`, then child groups `m_first_child` -> `m_next_sibling`) -> `WallCorrectRp` (octree
depth-first, children `mChild[0..7]` in index order; at a leaf the block's WALL rwg list then its
roof list) -> `RwgWallCorrect` (the block's wall linked list). Roofs are near-horizontal so they
no-op in WallCorrect; only walls reorder anything.

The whole order is reconstructable STATICALLY from the DZB header tables, because `ClassifyPlane`
(`c_bg_w.cpp:145`) builds each block's wall rwg list in ASCENDING poly index -- so the runtime
`pm_rwg`/`pm_blk` linked lists need not be read; a block's wall polys, sorted, ARE its list.
`harness/rollstab/capture_walls.py` walks `m_b_tbl`/`m_tree_tbl`/`m_g_tbl` and writes the room's
wall polys in exact game order (with the stored, bit-exact planes) to
`fixtures/kaze_r11_walls_ordered.json`. Far polys are visited too and simply
no-op (the correction's `seg > wallRR` early-out), so the full ordered list is safe to feed the sim
-- ORDER, not membership, is what a corner needs. At the kaze seam this puts wallA (poly 705)
before wallB (poly 713): same block (137), ascending index. The corner gate confirmed it live:
walking into the vertex wedges the cylinder between both walls, and the game-ordered mesh matches
bit-for-bit where the SWAPPED order diverges (24/48 frames), i.e. the ordering is load-bearing.

## The sim (Phase W)

`LandState(walls=[Tri...])` opts in (`land/walls.py`); wall-free behavior stays byte-identical.
The pass runs `core.collision.acch_crr_pos` (the exact acch layer: every-frame LineCheck with the
full response, WallHDirect, console `sqrtf_c`, exact `cM3d_IsZero` 2^-18) right after position
integration, then stores the wall-hit state on the LandState for the next frame's procs. The
crash proc is fully modeled (positions are pure momentum, exact without ROLLFMIS keyframes). The
sidle is NOT: the sim just forbids the roll and latches the sticky `sidle_blocked` flag, and a
bonk shows up as `FRONT_ROLL_CRASH` in `state`/`visited`. **Planners must reject either.**

For a corner, feed the traversal-ordered mesh (`load_ordered_mesh`); for a single face the
hand-picked `load_geo_tris` subset suffices (order-free). The `wall_angle`/`cir_hit` the pass
stores are per-cylinder (one poly's angle per cylinder), so a corner leaves the LAST-corrected
wall's angle -- fine for the current consumers (wall-hold, bonk) which only test a head-on cone.

Scope/caveats (the open edges, in priority order):

- **Full-room mesh + block-grid cull**: `wall_traversal_order` emits the whole room in order
  (765 walls at kaze r11) and the sim iterates all of them (~33 ms/frame pure-Python). Correct
  but unoptimized; a spatial pre-cull (the game's octree AABB test) would speed the solver if a
  corner ever enters the 2-minute budget. Far polys are already no-ops, so a cull is pure speed.
- **Not wall-passed yet**: the ballistic hops and the C-up freeze's early-return frames.
- **Post-crash walking** consumes an unwarmed ROLLFMIS toe stream (the anim dump lacks
  `rollfmis`). Same flagged class as the late-roll drawn poses.
- **Mid-run stop then re-walk** (found by the grind gate's first design): a full stop to WAIT
  and re-entry into MOVE is NOT bit-exact yet. The one-frame WAIT matched; the re-walk entry
  speedF diverged. Unrelated to walls: a from-rest anchor entry is exact, a mid-run re-entry is
  not. Avoid full stops in plans until modeled.

## See also

- [collision.md](collision.md) - the collision system + geometry readers this builds on.
- [seam-clip.md](seam-clip.md) - the CrrPos FP port + why razor seams thread it.
- [roll.md](roll.md) · [land-movement.md](land-movement.md) - the procs the wall state feeds.
- `harness/rollstab/wallgate.py` - the four single-face live gates (mint / plan / run / verify).
- `harness/rollstab/cornergate.py` + `capture_walls.py` - the corner gate + the traversal-order
  mesh capture (reconstructs the DZB block-grid walk statically; reads RAM via `../tools/`).
