# Seam-clip scanner - "is this corner clippable, and with what exact coords?"

**Answers:** How does the region/stage/full-game scanner decide a wall seam is clippable and hand back
a performable `(old, new)`? What is the DETERMINISTIC clip model (why a clip = cone  AND  standable  AND 
unblocked)? What are the standability gates (OOB skirt, step riser)? Why does the reported seam Y sit at
the floor, not the wall base? Why is the DZB read in world coords (no MULT)? How is the whole game
batch-scanned into the collision-viewer CSVs?
**Status:** model validated; scanner complete AND fast (the shipped full-game batch scanner is
`seam_locator`, an analytic superset of `clip_check` at ~8x). The mechanism/root-cause is
[seam-clip.md](seam-clip.md); this page is the tooling around it. Live-confirmed on GanonL (6/6, and
the full room) and Hyrule seams (near-coincident pair, -1727 needs-push), all clean-placement CLIP
drift 0. Guards: [`tests/test_seam_clip_check.py`](../../tests/test_seam_clip_check.py) (single-seam
`clip_check`, 10 cases) and [`tests/test_seam_locator.py`](../../tests/test_seam_locator.py) (the
shipped locator: superset + structural gates + native-ring identity) and
[`tests/test_seam_wall_classification.py`](../../tests/test_seam_wall_classification.py) (the
decomp-faithful wall/ground/roof split + the Omori false-positive it fixed).
**Source:** [`harness/collision/seam_locator.py`](../../harness/collision/README.md) (`scan_region` /
`locate`, the shipped scanner), `seam_clip_check.py` (`clip_check`, the single-seam checker + the
shared standability gates), `gap_search.py` (`first_f32_clip`; native ring in `core/_collc.pyx`),
`seam_scan.py` (`enumerate_seams`, `_gather`, `floor_ys_at`, `read_region_tris`), `dzb_iso.py` (offline
disc reader), `window_dataset.py` (the window-labeling oracle), `scan_all_dzb.py` (batch straight to
CSV), `validate_clips.py` (live confirm). Cylinder / ground constants: `d_bg_s_acch.cpp`,
`d_a_player_main.cpp`.

---

## What it answers

`seam_locator.scan_region(region, box)` (the shipped scanner) and the older single-seam
`clip_check(barrier_tris, ground_tris, S, wallA, wallB, ...)` both decide whether a seam clips and
return one physically-valid **standable** `(old, new)` that performs it: **existence + performable
coords, NOT the minimum displacement** (that is `gap_search.min_f32_clip`, an O(box^2) lattice sweep).
Both are pure geometry, no Dolphin (region live from `read_region_tris` or offline from
`dzb_iso.load_room_region` / `seam_scan.load_region_tris`). `seam_locator` is a strict superset of
`clip_check`'s output: same structural gates, a more thorough anisotropic f32 search. On Hyrule room 0
it returns 35 clips = all 34 of `clip_check`'s (0 misses) + 1 real one `clip_check`'s shallow search
dropped, in 25 s vs 198 s.

## The reliable detector is the f32 lattice

Link's position is f32 (`cXyz`), so the ONLY reachable clips are f32-representable. `first_f32_clip`
(ring-search the f32 lattice out from a guess `new_center`, early-exit on the first clip) is the truth.
**Detection cannot be ULP-coarsened**: the offset window is a razor ~1e-5..1e-3 u regardless of
coordinate magnitude (a coarser step false-negated the live Hyrule seam). Speed must come from
searching the right *place*, not a coarse step - which is what the deterministic model below gives.

## The DETERMINISTIC clip model (this is what makes it computable, not searched)

The game is deterministic, so a clip is *calculable* from the triangle geometry. Reverse-engineered and
validated against the bit-exact model (`window_dataset.py` oracle + the scratch experiments recorded in
[history/seam-scanner-analytic-attempts.md](../history/seam-scanner-analytic-attempts.md)):

- **A clip exists ONLY inside the geometric cone `|rel| <= interior/2`** (`rel` = bisector-relative travel
  direction). A clip needs `new` behind BOTH wall planes; the angle between the normals is
  `180-interior`, so the back-wedge sector `{nA.d<0  and  nB.d<0}` is exactly `interior` wide, i.e.
  `+/-interior/2` about the bisector. Verified: 87/88 measured windows lie inside (one leaks 2deg under the
  +/-20 area tolerance). This bound is FIRM and analytic.
- **The cheap prune `{cone AND floor AND valid-old AND not-blocked}` is a SOUND SUPERSET, NOT the real
  set.** It NEVER drops a real clip (`real_only = 0` on every test seam) but is not tight: for isolated
  / barrier-free corners it passes the WHOLE cone, yet the f32 clips land only in a narrow sub-band.
  **So the f32 verify is LOAD-BEARING, not an optional speed-up.** (This overturned the 07-06/07 model
  that a bare corner "clips at every cone direction" and that real windows are "100% barrier+floor
  pruning" - true in CONTINUOUS space, but the f32-REACHABLE set is a coord-magnitude-dependent subset;
  migrated to [history/seam-scanner-analytic-attempts.md](../history/seam-scanner-analytic-attempts.md) #5.)
- **The clip is a LINE property, so search it ANISOTROPICALLY.** For a fixed travel direction the
  LineCheck-miss window is thin (~1e-3 u, the plane fan) in the PERPENDICULAR offset from the seam
  vertex but broad ALONG travel. The old square-ULP ring conflated the two axes and missed high-coord
  clips displaced along the wall. `seam_locator` verifies a coarse along-track world scan x a thin f32
  box perpendicular, with the FULL trilist (barriers handled by the verify, never a cheap - and unsound -
  direction-level block test).
- **A DISTANCE-coverage bug caused the earliest missed seams.** An oblique approach settles its `old`
  FARTHER from the seam than the bisector clearance (`floor`), so a clip's old sits at `floor + ~6..20 u`;
  probing only `floor + 0..2` missed every oblique clip (e.g. Hyrule (1127,1621), window rel -34..-68 at
  those deeper distances). `seam_locator` settles deep-first.

## The shipped scanner: `seam_locator` (fast, complete, gated)

Per hot-spot-ordered cone direction (bisector + edges first), settle one valid standable DEEP `old`
(`DIST_OFFSETS`, deep-first), then VERIFY anisotropically (`S_LO..S_HI` along-track world steps x a
`BOX_ULP`-thin perpendicular f32 box via `first_f32_clip`); first f32 clip wins. Cheap rejection comes
from the standability gates (most unclippable seams have no standable floor). A per-seam `SEAM_BUDGET`
bounds the sub-ULP cheap-pass-wide worst case (an isolated corner with no cheap SOUND unclippability
proof; see history #6). Speed: the `first_f32_clip` ring is native (Cython, `core/_collc.pyx`) and
SHORT-CIRCUITS the clip test (only the boolean is needed, so a first-LineCheck hit returns "not a clip"
without running WallCorrect - the dominant case for the budget-draining unclippable corners). Together
~4x over the pure ring: the hardest unclippable Hyrule corner dropped 4.75 s -> 1.1 s, the full room 106 s
-> 25 s. The native ring is 0-ULP identical to the pure ring (gated).

## Standability: a reported `old` must be somewhere Link can stand AND collide

Decided from the static DZB (Dolphin-free; `require_standable=False` / `override_link_y=` opt out):

- **Floor from the DZB ground mesh** (`floor_ys_at`, ny>=0.5) under the approach XZ, never Link's live
  Y, never the wall base; and `old` must be a settled WallCorrect fixed point in front of both walls.
  The point-in-triangle is the game's EXACT ground test (`collision.cross_y_tri_front` =
  `cM3d_CrossY_Tri_Front`: strict (z,x) AABB + all three signed areas >= -20, the front winding; height
  via `getCrossY_NonIsZero`), NOT a barycentric eps. A settled `old` parks a hair PAST a floor edge (the
  seam wall it braces against can overhang the floor lip), and a loose eps (1e-3 barycentric ~= 0.1u on a
  200u floor tri) counted that off-floor point as standable -- so Asoko Room0 reported inits that FALL
  OOB (user-flagged; live-validated the game's `RwgGroundCheck` rejects them 20/20, scan 20->8 clips).
  NOT a surface-material bug: every Asoko faller floor is ground-code 0 / attribute NORMAL (the
  ground-code/void hypothesis was disproven); the defect was geometric edge slop. Gate:
  [`tests/test_seam_standable_ground.py`](../../tests/test_seam_standable_ground.py).
- **The wall must be COLLIDABLE at that floor** (`_floor_at`): a floor is valid only if a LineCheck
  cylinder sample (feet + `WALL_H` = 30.1 / 89.9 / 125.0) lands inside the wall's vertical span. This is
  exactly the game's wall-registration rule (`RwgWallCorrect`, `d_bg_w.cpp:85-89`). It rejects **OOB
  skirt lips**: a wall that tops out below feet+30.1 is never touched (Hyrule underside: floor Y~=-100,
  wall span (-1945,-99.6); the plane-only model reported a phantom clip there).
- **Not a step / ledge riser** (the 60 u ground-snap, `m_ground_check_offset`, `d_bg_s_acch.cpp:60`):
  each frame CrrPos raises Link onto the highest floor within feet+`GROUND_SNAP`. If a staircase of
  floors at the seam XZ climbs from his floor to the wall's CROWN in <=`GROUND_SNAP` hops, he ascends
  the riser ("pops up above"), not a clip. A true barrier's crown is open, or a single jump too tall to
  snap (GanonL's 73 u steps stay clippable). Live: Hyrule (735,-150,323) climbs -150 to -100 to -75.

## Reported seam Y = the standable floor (not the wall base)

The wall is vertical, so the clip is height-invariant; the base vertex can sit well below reachable
ground (GanonL walls based at y~=5762 but the walkable floor is y~=5852, ~90 u up). `scan_region` reports
the seam at the standable floor Y (`= link_y`), so the CSV/viewer place the dot where the clip is
actually performed.

## Enumeration handles authored-geometry variance

Two live-confirmed Hyrule clips were missing from the first dump; `enumerate_seams` now handles both:

- **Near-coincident vertices.** Corner walls need NOT store a bit-identical seam vertex (observed a
  0.09 u XZ offset). An exact `round(x,2)` bucket split them into two single-normal buckets and dropped
  the corner. Now vertical edges are **clustered within `SEAM_XZ_TOL`** (grid union-find, y-span
  overlap) so the two walls pair.
- **Stacked lower/upper tris.** A tall wall is split into stacked triangles; a single representative tri
  can be the UPPER half (y 199-499). `scan_region` computes the standable `yspan` over ALL incident tris
  of the corner (from `seam['polys']`) so the floor check doesn't reject the real floor.
- **Coplanar (single-normal) flat-wall seams.** `enumerate_seams` also emits single-normal vertical
  edges (`coplanar=True`, interior 180) - a flat wall's own tessellation seam can clip where f32
  rounding opens a threadable gap (live A_mori (4077.6,-1708.8)). NOT categorical: the f32 verify
  decides per-seam. See [seam-clip.md](seam-clip.md) + [history](../history/seam-scanner-analytic-attempts.md).

## Wall/ground/roof classification = the NORMAL, not a stored attribute

The scanner selects "wall" triangles by the game's own rule (`cBgW_CheckB*`, `c_bg_w.h`; see
[collision.md](collision.md#ground--wall--roof-classification)) - a pure test on the face-normal **Y**,
canonically `tww_sim.core.collision.bg_is_{ground,roof,wall}`:
- `ny >= 0.5` → ground, `ny < -0.8` → roof, ELSE (`-0.8 <= ny < 0.5`) → **wall** (`bg_is_wall`).
- The **CrrPos blocker set** fed to `crr_pos_walls` is wall **+** roof = NOT ground (`bg_blocks_crrpos`):
  the game's `WallCorrectRp`/`RwgWallCrrPos` walk a block's wall AND roof poly lists (`d_bg_w.cpp`).
- This is NOT a per-triangle attribute. The DZB's per-tri property/group ids (`GetGroundCode`) carry
  surface MATERIAL (sand, grass, void `code 4`, ...), never the wall-vs-ground geometry.

There is no "verticality" threshold: a **sloped wall up to `ny` 0.5** is a wall the game braces against.

## The shared seam edge must be at Link's stance height (floating-seam false positive)

A corner clip needs BOTH walls present at Link's cylinder; the seam is the two walls' **shared vertical
edge**, and `enumerate_seams` records its y-span (`seam["edge_yspan"]`). If the standable floor sits far
ABOVE or BELOW that edge, only one wall (or none) faces Link there, so the two-plane fan can't produce a
clip, whatever the f32 verify finds. The gate `seam_clip_check._cyl_overlaps_edge(link_y, edge_yspan)`
(wired into `seam_locator.locate` and `seam_clip_check.scan_region`) drops the clip unless a cylinder
sample (feet + `WALL_H`) lands inside the edge span. Two user-flagged cases, symmetric:
- **Edge ABOVE the floor** (Omori Room0 (2249.6, 358, 1772.6), interior 145.2): polys 31/864 share a
  vertical edge at y905..1227, but the standable floor is y358: poly 31 does not exist at floor level,
  so there is no corner there ("no seam here"). The old gate accepted the floor because it tested the
  UNION of both walls' vertices (poly 864 dips to y350), masking that the *other* wall floats overhead.
- **Edge BELOW the floor** (GanonK top (±250, 7770, -2902.6)): the shared edge tops out at y7504 but the
  settled floor is y7770; poly 1319 rises to y9917 ALONE above the edge (no corner). Previously this was
  culled only by the full-room re-verify; the edge-overlap gate rejects it directly (and does not fall
  back to the pillar-base floor, so it surfaces no new untested candidate). Gate:
  [`tests/test_seam_edge_overlap.py`](../../tests/test_seam_edge_overlap.py) + the GanonK-top case in
  `test_seam_locator.py`.

## Three gather / verify false-positive fixes (2026-07-15)

`locate` reported "clips that don't work" (user-flagged). Three causes, all fixed:
- **Wall classification too strict** (Omori Room0 S=(1075.9,350,-1190.57), interior 160.1). The scanner
  had classified walls as `|ny| < 0.03` (near-vertical ONLY), so it dropped the sloped walls
  (`bg_is_wall` up to `ny` 0.5) that also brace. Here a sloped wall (poly 392, `ny`=0.384) shares the
  seam vertex; the game's WallCorrect braces the r=35 cylinder on it and BLOCKS (live drift 35.70), but
  the strict filter saw a phantom clip. Now the whole pipeline classifies via `bg_is_wall` /
  `bg_blocks_crrpos`. (Live/offline geometry was bit-identical, and only ADDING blockers - so this
  can only kill false positives, never a live-confirmed clip; A_mori/GanonL/GanonK goldens unchanged.)
  Diagnosis handoff + gate [`tests/test_seam_wall_classification.py`](../../tests/test_seam_wall_classification.py).
- The CrrPos barrier was gathered at the **seam-vertex Y**, but the wall cylinder is at **Link's floor
  Y** - hundreds of u higher on a tall corner (GanonK top: base 6997, floor 7778), so the walls at
  Link's height were excluded and the verify missed the WallCorrect blocker. Now gathered at the
  representative standable floor Y.
- Even at the right Y the edge-distance gather can miss a blocker. `locate` now **re-verifies the exact
  `old`->`new` against the WHOLE room's walls** and drops any clip whose full-room sweep is stopped
  short. Far walls can't touch the short cut segment, so this never false-negatives a genuine clip.

## DZB is stored in WORLD coordinates; MULT is NOT applied

`dzb_iso` reads raw DZB verts and does **not** apply the stage `MULT` room placement. Verified across
the whole game: **all 50 non-identity-MULT rooms are `sea` rooms, and each one's raw DZB centroid
already equals its MULT (tx,tz) exactly** (sea Room44 raw ~= (-200000,+300000) == MULT); 0 rooms are
local. Applying MULT double-offset the sea (world coords ~2x out, the source of the -603213 garbage);
dungeons were unaffected only because their MULT is identity. Planes are the bit-exact `calc_pla` (the
DZB stores none). NOTE: offline-verified (centroid == MULT is conclusive); a live sea-room RAM check
(`[cBgW+0x90]` world verts vs the DZB) is the belt-and-suspenders confirmation, not yet run.

## Batch to CSV to viewer

`scan_all_dzb` scans every game DZB with `seam_locator` and writes one CSV per clippable DZB into
`_generated/seam_clips/<stage>/<Arc>__<dzb>.csv` (override with `out=`; one row per clippable seam:
seam / init / dest xyz + interior angle). It streams (each DZB's CSV appears the moment it finishes, so
the viewer live-updates) and is resumable (skips DZBs whose CSV exists). No intermediate `.md`. Room
DZBs are world-transformed by the stage `MULT`; coords are written at FULL f32 precision (a rounded
seam coord flips the razor CLIP verdict to BLOCK).

**Undecided seams are flagged, not silently dropped.** A seam whose cone sweep exhausts the per-seam
`SEAM_BUDGET` (200k f32 CrrPos evals) WITHOUT finding a clip and WITHOUT finishing is UNDECIDED, not
proven unclippable. `scan_region(..., return_unknown=True)` returns those separately, and `scan_all_dzb`
writes them to a sibling `<Arc>__<dzb>__unknown.csv` (`seam_x,seam_y,seam_z,interior,floor`; no
init/dest). The clip CSV schema is untouched. These are mostly COPLANAR flat-wall seams (interior 180,
~180-deg cone, sub-ULP gap): cheap-pass-wide and expensive to rule out, so the budget caps first (Hyrule
r0: 58 clips + 76 unknown). A budget-capped seam MIGHT clip in an unexplored direction; treating it as
no-clip was a silent cap (KB principle: no silent coverage bounds).

## Live validation: clean placement (HARD gotcha)

`validate_clips.py` confirms a scan's clip live: place Link at `old` by writing BOTH player class-pos
triples (`[0x803AD860]+0x10c` and `+0x120`) AND the debug `link_x/y/z` so the placement sweep is
zero-length, then step one clip frame to `new`. Debug-pos-only leaves `pm_old_pos` behind, so the next
CrrPos sweeps a long line, crosses a wall, and snaps Link ~100 u away (spurious BLOCK). Feed full f32 (a
3-decimal-rounded coord flips the razor verdict). Full detail: `../tools/DOLPHIN_CONTROL.md`.

## See also
- [mechanics/seam-clip.md](seam-clip.md): why seam clips work (the float-precision root cause) + the
  bit-exact `cM3d_CalcPla` FP note.
- [mechanics/roll-stab.md](roll-stab.md): the 49.22 single-frame lunge that reaches a clip.
- [reference/constants.md](../reference/constants.md#collision-player-wall-cylinders): wall radius,
  cylinder heights, tolerances.
- [harness/collision/](../../harness/collision/README.md): the runnable scanner + live validator.
