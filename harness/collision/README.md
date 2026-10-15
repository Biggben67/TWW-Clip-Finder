# harness/collision - seam-clip model & live validator

Offline, bit-exact model of the **GanonL grand-staircase seam clip** + a live sim-vs-game validator.
The mechanics/root-cause write-up is [`knowledge/mechanics/seam-clip.md`](../../knowledge/mechanics/seam-clip.md);
this folder is the runnable model.

## What's here

| File | Role |
|------|------|
| [`seam_model.py`](seam_model.py) | The seam geometry (4 wall tris + STORED per-triangle planes) + `predict_clip(initial, end)` / `settle_initial`. Wraps [`tww_sim.core.collision`](../../tww_sim/core/collision.py). |
| [`validate_live.py`](validate_live.py) | Drives a running Dolphin (position-hacking) and compares live clip/block vs `predict_clip` fed the game's actual old_pos. |
| [`validate_clips.py`](validate_clips.py) | Live-confirms a `scan_region` result: for each clippable seam, CLEAN-places Link at `old` (writes both player class-pos triples `[0x803AD860]+0x10c`/`+0x120` so the placement sweep is zero-length, else the swept CrrPos snaps him ~100u away) and steps the one clip frame to `new`; clip iff Link stays. 6/6 on GanonL. `box=... [slot=N]`. |
| [`gap_search.py`](gap_search.py) | Seam-gap finder. **`min_f32_clip`** = the reliable f32-lattice search (settled f32 `old` + f32 `new` box; no false positives, authoritative min-displacement) - use this. `find_clip` / `characterize` / `min_displacement_for_line` = the continuous approximation (pin the line through S, sweep direction, micro-scan offset); now f32-snapped (`_p32`) so it no longer false-POSITIVES on sub-ULP double-precision "gaps", but its `min_displacement` over-estimates. All candidate positions MUST be f32 (Link's pos is `cXyz`=f32); see the f32-honesty notes in the module + `knowledge/mechanics/seam-clip.md`. |
| [`dzb_iso.py`](dzb_iso.py) | **Read a room's DZB collision straight from the extracted disc, no Dolphin.** RARC (Yaz0-aware) extract of `Room<N>.arc` -> `room.dzb` -> verts+tris -> world-transform by the stage `MULT` room placement -> per-triangle planes via bit-exact `calc_pla` (the DZB stores none; the game computes them the same way at load). Feeds the same `region_tris` as the live reader, so `scan_region` runs on any room offline. `load_room_region(stage, room)`; CLI `python -m harness.collision.dzb_iso stage=M_Dai room=18`. Validated: GanonL via ISO reproduces the 40 live-confirmed clips exactly. Extract dir from `dolphin.local.json` (`tww_extract_dir`). |
| [`seam_scan.py`](seam_scan.py) | **Stage-wide region scanner** (live). Enumerates a box's differing-normal vertical seam corners, screens each by the analytic floor `wall_r/sin(interior/2)`, and reports its reliable f32 min-displacement via `min_f32_clip`. `python -m harness.collision.seam_scan box=xmin,xmax,ymin,ymax,zmin,zmax target=<D>` (needs `DOLPHIN_PID`). `enumerate_seams`/`scan_seam`/`disp_floor` are the pure pieces. |
| [`drop_release_clip.py`](drop_release_clip.py) | **Source-ordered bomb/pot B-drop collision simulator.** Runs released-prop BG correction, Co overlap/rank split, deferred Link move, and Link BG correction. See [`knowledge/mechanics/prop-push.md`](../../knowledge/mechanics/prop-push.md). |
| [`drop_push_clip.py`](drop_push_clip.py) | **Bomb/small-pot setup generator.** Without `csv=`, it routes to the first-principles scanner: GRABWAIT hand pose, mixed GRABWAIT/REST Link Co pose, prop BG, Co recomputation, full Link `Acch`, standability, follow-up stability, and console trig-bucket boundaries. The historical CSV path remains diagnostic-only. |
| [`find_drop_push_candidate.py`](find_drop_push_candidate.py) | **Fast first-principles search for one seam/animation position.** Solves backward along a decomp-generated reference push, then recomputes every candidate at its exact world binary32 coordinates. No displacement CSV is loaded. |
| [`drop_push_gui.py`](drop_push_gui.py) | **Desktop bomb/small-pot setup finder.** Live mode reads Link's position, facing, animation frame, stage, room, and active room collision directly from Dolphin. Offline ISO/JSON/DAE collision remains available by clearing **Use current room collision**. Coordinate triplet paste and all search settings persist across launches. The optional OOB mode requires the endpoint to land behind both walls, within the requested XZ radius of the vertical seam, on the same floor, and remain stable. Launch with `pythonw -m harness.collision.drop_push_gui`. |
| [`angle_experiment.py`](angle_experiment.py) | Sweeps synthetic corner angles (pivot wall B about the seam) through `gap_search` and reports clippability. Near-90° clips; no clean angle cutoff (per-geometry float fan). |
| [`tetra_clip.py`](tetra_clip.py) | **Tetra-nudge → clip pipeline.** Composes [`tww_sim.core.cc_push`](../../tww_sim/core/cc_push.py) (the decomp cyl-cyl Co-push: overlap depth + weight split) with `crr_pos_walls`. `clip_with_push(old, link_y, thrust, tetra_xz, tris)` = one clip frame (`new = old + push + thrust`); `solve_min_overlap(...)` places Tetra behind Link and returns the smallest overlap that clips. On the live (−1727,−990) anchor a 49.22 u roll needs ≈1.23 u overlap (push ≈0.615 u; game uses `dCcS::SetPosCorrect` rank-table split → Link/Tetra both rank 5 → 50/50, live-confirmed; `sumR=30+50`). See `knowledge/mechanics/actor-push.md`. |
| [`seam_clip_check.py`](seam_clip_check.py) | **Single-seam checker** "is THIS seam clippable, with what EXACT coords?" `clip_check(barrier_tris, ground_tris, S, wallA, wallB, require_standable=True, override_link_y=None)`: cone sweep + f32-lattice search (`first_f32_clip`), returning a physically-valid **standable** `(old, new)` (floor from the DZB ground mesh, not Link's Y; `old` a WallCorrect fixed point in front of both walls) plus `disp` / `reachable_rollstab` / `needs_push`. Existence + performable coords, NOT the minimum. Owns the shared **standability gates** `_floor_at` (collidable-at-stance / OOB-skirt), `_representative_link_y`, `_is_step_riser` (used by `seam_locator` too). `--selftest` = GanonL. |
| [`seam_locator.py`](seam_locator.py) | **The shipped region / full-game scanner** (fast analytic rebuild of `seam_clip_check`, a strict superset at ~8x). `scan_region(region, box)` / `locate(region, ground, seam)`: per hot-spot-ordered cone direction settle a DEEP standable `old`, then verify ANISOTROPICALLY (coarse along-track world scan × a thin perpendicular f32 box, full trilist) via the native `first_f32_clip` ring. Same structural gates as `clip_check` (so its clip set is a superset, never a different phantom class). Pure geometry, no Dolphin. `python -m harness.collision.seam_locator stage=Hyrule room=0 [probe]`. Guard: `tests/test_seam_locator.py`. |
| [`scan_all_dzb.py`](scan_all_dzb.py) | **Full-game batch scan → CSV.** Scans every game DZB with `seam_locator` and writes one CSV per clippable DZB straight into the collision viewer's `tww-python-scripts/ww/data/seam_clips/<stage>/<Arc>__<dzb>.csv` (seam / init / dest xyz + interior angle, FULL f32 precision). Streams (viewer live-updates) + resumable (skips existing CSVs). Room DZBs world-transformed by the stage `MULT`. `python -m harness.collision.scan_all_dzb [stage=… ] [out=… ]`. |
| [`plan_seam_clip.py`](plan_seam_clip.py) | **Seam-clip INPUT PLANNER** (the bridge). Given the barrier tris + an authoritative clip target (settled `old` + f32 `new`) + a start pose, `plan_seam_clip(tris, old, new, start_pos, link_y, csangle=None, cut="CUT_F")` emits the controller **input sequence** for the aimed roll-stab (draw B · run up · A roll · `kroll`=15 · thrust), decides bare-roll-stab vs needs-push against the bit-exact models, and - when short - sizes the Tetra overlap + placement via `tetra_clip`. `discover_clip(...)` wraps `clip_check` when you don't already have `(old, new)`. `--selftest` reproduces the live (−1727,−990) clip end-to-end (facing 40874, overlap 1.50 u, Tetra centre ≈(−1623.7,−903.8)). Composes [`enter_cut`](../../tww_sim/land/land.py) + [`stick_for_bearing`](../../tww_sim/land/plan_land/__init__.py) + `tetra_clip`. |
| `ganonl_seam_capture.json` | Ground truth: every triangle the game's `LineCheck` tested for the row-1 clip line, with stored plane (n, D) + the game's crossing point + return. Captured via a breakpoint on `cM3d_Cross_LinTri`. Also the oracle for the bit-exact `calc_pla` (frsqrte) test. |

The reusable, geometry-agnostic port of the collision resolution (`LineCheck` + `WallCorrect` +
the `cM3d` math) lives in [`tww_sim/core/collision.py`](../../tww_sim/core/collision.py).

## Run it

### Bomb/pot finder in another room

1. Launch `launch_drop_push_gui.cmd`.
2. Enter the room in Dolphin, pause anywhere in gameplay, and press **Refresh**.
3. Paste the seam as `X, Y, Z` into any seam-coordinate field.
4. Run **Scan seam**. The finder captures the current static room's WallCorrect and GroundCross collision from RAM.

Live collision searches include every registered static and moveable BG, including
actor seams and actor floors, using their current world-space vertices and stored
planes. Keep Dolphin paused at the desired actor pose while capturing collision;
the search uses that snapshot and does not predict an actor moving during the setup.

For offline use, clear **Use current room collision**, enter Stage and Room, and select an ISO,
JSON cache, or DAE. ISO rooms are cached under `_generated/collision`; a manually selected JSON
must contain matching stage/room metadata. The ISO is never copied into the simulation folder.

```bash
# offline: predict clip vs the brute-force solution set (14k rows)
python -c "from harness.collision.seam_model import predict_clip; print(predict_clip((-817.6296387,-37307.21875),(-855.1299438,-37343.96094)))"

# live vs the game (needs Dolphin on the GanonL seam savestate in slot 1; target it by PID)
DOLPHIN_PID=<pid> python -m harness.collision.validate_live 20
```

## Root cause (one paragraph)

A stage wall quad is two triangles; adjacent quads meet at a shared vertical **seam** edge, so four
triangles meet there. Each triangle stores its **own independently-normalised plane**
(`cM3d_CalcPla`), so the two triangles of one quad differ in the last mantissa bits. `LineCheck`
intersects Link's swept centre-line with **each triangle's own plane** and then runs a projected
point-in-triangle test; near the seam the four crossings land at four slightly different points,
each **just outside** its own triangle → all miss → no wall is reported. If the one-frame
displacement also exceeds the radius-35 wall cylinder (so the static `WallCorrect` at the new
position no longer overlaps the wall), Link ends up past the wall - a clip. This explains the
observed requirements: **>~36 u displacement** (clear the cylinder), **corner angle >90° and not
180°** (the walls must be non-coplanar so their planes differ but still form a seam), and
**perfectly vertical walls** (ny≈0, so `cM3d_Cross_LinTri` skips the Y projection and the seam edge
is a clean shared vertical line).

## Validation

* **Bit-exact**: fed the stored planes, the port reproduces the game's per-triangle crossing points
  to f32 and every hit/miss (`ganonl_seam_capture.json`).
* **Live**: 24/24 cases agree when the port is fed the game's actual old_pos (20-row boundary sweep
  + 4 offline-miss rows), GZLJ01 2026-07-06.
* **Offline over the 14k brute-force clip set**: 14024/14049 (99.82%) predicted as clips with an
  approximated (4-frame WallCorrect) old_pos; the residual is old_pos approximation + dump entries
  that don't reproduce under a clean settle, not model error.

The one fused op that a naive port gets wrong: the plane function's dot product
(`PSVECDotProduct`) fuses `nx*px + ny*py` (`ps_madd`, one rounding). `cM3d_VectorProduct2d` and the
crossing interpolation are NOT fused. See `tww_sim/core/collision.py`.
