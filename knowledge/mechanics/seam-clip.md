# Seam clips - why walking/rolling through a wall corner works

**Answers:** Why do "seam clips" work - how does Link pass through a wall where two collision
triangles meet? What's the float-precision root cause? Why the three requirements (≥~36 u of
displacement in one frame, corner angle >90° but not 180°, perfectly vertical walls)? How do I
model / predict one offline?
**Status:** validated - a stdlib FP-faithful port of the collision resolution
([`tww_sim/core/collision.py`](../../tww_sim/core/collision.py)) reproduces the game's per-triangle
crossing points to f32 and every hit/miss, 24/24 live position-hack cases on the GanonL
grand-staircase seam (GZLJ01, 2026-07-06), and predicts 14024/14049 (99.82%) of a brute-force clip
set offline. Model + validator: [`harness/collision/`](../../harness/collision/README.md).
**Source:** decomp `cM3d_Cross_LinTri` / `cM3d_Cross_LinPla` / `cM3d_CrossX/Y/Z_Tri`
(`SSystem/SComponent/c_m3d.cpp`), `RwgLineCheck` (`c_bg_w.cpp`), `dBgS_Acch::CrrPos` + `LineCheck`
(`d/d_bg_s_acch.cpp`), `RwgWallCorrect` (`d/d_bg_w.cpp`), player cylinders
`daPy_lk_c::setBgCheckParam` (`d_a_player_main.cpp:10715`). Live capture via a breakpoint on
`cM3d_Cross_LinTri`. Constants: [reference/constants.md](../reference/constants.md#collision-player-wall-cylinders).

---

## The two horizontal barriers each frame

Every frame the player runs `dBgS_Acch::CrrPos`, which stops/redirects XZ movement with **two
independent checks** (see [collision.md](collision.md) for the mesh/reader):

1. **LineCheck (swept).** Tests Link's centre-line from `old_pos` to `new_pos` against each wall
   triangle via `cM3d_Cross_LinTri` = a plane crossing (`cM3d_Cross_LinPla`) + a projected
   point-in-triangle test (`cM3d_CrossX/Y/Z_Tri`). Only **front→back** crossings count
   (`frontFlag=1, backFlag=0`). It runs only when the horizontal displacement exceeds the wall
   radius (`distXZ² > 35²`). On a hit it snaps `new_pos` back to the crossing point.
2. **WallCorrect (static).** At `new_pos`, pushes Link's wall **cylinder** (radius **35**, three
   heights 30.1/89.9/125.0) out of any wall it still overlaps (`RwgWallCorrect`).

A clip happens only when **both** miss.

## Root cause: independent per-triangle planes at the seam

A stage wall quad is stored as **two triangles**, and adjacent quads meet at a shared vertical
**seam** edge - so up to four triangles meet at the seam. Crucially, each triangle stores its **own
independently-normalised plane** (`cM3d_CalcPla`: `normalize(cross(v1−v0, v2−v0))`, `d=−dot(n,v0)`).
Because the normalize is per-triangle, the two triangles of one quad have normals that differ in the
last mantissa bits - e.g. at the GanonL seam the upper/lower triangles of wall A carry
`0.24360720813` vs `0.24360716343`, and the two triangles of wall B differ too.

`LineCheck` intersects the swept centre-line with **each triangle's own plane independently**, then
tests whether that crossing point lies inside that triangle. Near the seam vertex the four planes
are crossed at **four slightly different points**, and each lands **just outside** its own
triangle's shared edge - so the projected point-in-triangle test (even with its ±20 area-unit
tolerance) rejects all four. **All four triangles report "no crossing" → LineCheck finds no wall.**

Meanwhile, if the one-frame displacement is larger than the cylinder radius, `new_pos` is far enough
past the seam that WallCorrect's static radius-35 cylinder no longer overlaps either wall segment →
no push-back. With both barriers missing, Link keeps `new_pos` - he's through the wall.

This is not a coarse geometric wedge: the crossing points sit within ~0.01 u of the seam edge, and
the clip vs block outcome flips on the last few float bits. Faithful reproduction therefore needs
(a) the console's fused multiply-add (see [FP note](#fp-note)) and (b) the triangle's plane
**exactly** as the game computes it.

> **✅ Status: `calc_pla` is bit-exact (4506/4506 Hyrule planes).** Both paths are now verified.
> The sim *logic* (LineCheck + WallCorrect + `cM3d` math), fed the game's stored planes, reproduces
> real clips bit-for-bit (incl. a live Hyrule clip at the (−1727,−990) seam). And the plane *compute*
> path [`calc_pla`](../../tww_sim/core/collision.py) now matches every RAM plane, every field, so the
> **synthetic-angle results below are trustworthy** (no longer provisional). Reading the plane from
> RAM (`cBgW.pm_tri`, stride 0x18) is still the simplest path for a real seam, but `calc_pla`
> reproduces it exactly - see the FP note under "The model."

## Why the three requirements

- **≥ ~36 u of displacement in one frame** (35 is the hard floor). The displacement must exceed the
  radius-35 wall **cylinder** so that WallCorrect's *static* test at `new_pos` no longer overlaps the
  wall. Below that, even if LineCheck's swept test misses, WallCorrect shoves Link back out.
- **A corner is needed, but there is NO clean angle cutoff - including near 90°.** The two walls'
  planes must differ so the per-triangle crossings land on different sides of the seam; the *amount*
  of difference is set by the per-triangle plane **fan**, a sub-ULP property of the exact vertices,
  not a clean function of the dihedral. The synthetic-angle sweep
  ([`harness/collision/angle_experiment.py`](../../harness/collision/README.md)) - now on
  **bit-exact `calc_pla` planes** - finds clips across interior angles
  **80°–137°** (and reflex/concave corners wider); near-90° clips are also confirmed live on real
  RAM geometry, so the *qualitative* result (no clean angle cutoff) holds. Clippability at a given
  angle is decided by the exact float fan, so it is effectively per-geometry: exactly-90.0° can miss
  while 88°/92° clip. The folk "> 90° and not 180°" rule is only approximate - treat the real
  gate as "the two triangles' bit-exact planes fan enough to miss both crossings," which you check by
  running the model on the actual geometry. (Sharper convex corners tend to need more displacement to
  clear the cylinder, so speed rises as you sharpen.)

> **Practical viability = analytic gap width vs the local f32 position ULP.** A geometric gap is
> necessary but not sufficient. Link's position is f32, so a clip is *reachable* only if the gap
> window (in world units) is wide enough that an f32-representable position lands inside it - i.e.
> the window must be comparable to or larger than the **local f32 ULP**, which grows with distance
> from the origin (≈ `coord · 2⁻²³`: ~1.2e-4 u at coord 1250, ~5e-3 u at coord 37000). Example: a
> Hyrule 90° corner near (−157, −1250) has a continuous gap ~2e-5 u but a local ULP ~8e-5 u - the
> gap is sub-ULP, so **0 of 129 605 enumerated f32 positions clip** (unclippable in practice), while
> the GanonL staircase gap (~4e-3) is comparable to its ULP (~5e-3) and clips. Going *further* from
> the origin does **not** help - the position grid coarsens faster than the gap grows. So the real
> viability target is a large **plane fan**, not distance. **Min displacement** is set by the *old*
> position: `old_pos` must be a settled WallCorrect fixed point (never inside the cylinder), so it
> sits ~`wall_r/sin(halfangle)` in front (`halfangle` = half the **interior** corner angle) - ~37.6 u
> for the GanonL 137° corner, ~49.3 u for a ~90.6° corner - which dominates the one-frame displacement
> (geometry-dependent, ~35–50 u, NOT a flat 35).
>
> **The min-displacement floor is a HARD analytic screen.** `floor = wall_r / sin(interior/2)` is a
> lower bound no clip can beat (settled `old` clears both radius-35 cylinders; `new` is on the far
> side of S). So it screens a whole region analytically, no search: to clip at `< D` you need
> `interior > 2·asin(wall_r/D)` (e.g. `< 49.22 u` ⇒ interior `> 90.63°`; `< 40 u` ⇒ `> 122°`). The
> *actual* min is floor + a smaller geometry-dependent "how far past S must `new` sit to clear
> WallCorrect" term (≈0.6 u at the −1727 corner: floor 49.26 → true 49.90). Worked example
> (`harness/collision/seam_scan.py`, Hyrule box X±1800 Y±160 Z −1100..0): 8 vertical corners, most
> obtuse is (−1727,−990) at 90.57° (floor 49.26, true 49.90); the seven 90.0° corners don't even
> reach the f32 lattice (no clip). Sub-49.22 is analytically impossible in that region.
>
> **Reaching the floor needs a STACKED land move - a single roll is too slow.** The 35 u floor is a
> hard lower bound for *any* corner, and Link's fastest **single** ground move is a **FRONT_ROLL at
> 26.0 u** (`clamp(speedF·1.5+0.5, 5, 26)`, cap `0.5 + mMaxNormalSpeed·1.5`, `mMaxNormalSpeed = 17`;
> walk ~14, dash ~17) - 26 < 35, so a roll (or walk/dash) *alone* clips no corner. The clip uses a
> **roll + sword thrust** (the [roll stab](roll-stab.md)):
> fire a CUT_F/CUT_A cut out of the roll and the cut's first frame stacks the animation root-translate
> lunge (`m3700`, +23.22 u) onto the carried roll speed (26) for a **49.22 u** single frame. The land sim
> now models this **bit-exact end to end** (`LandState` `CUT_F`/`CUT_A`, live 0 ULP) - the roll AND the
> thrust half. See [actor-push.md](actor-push.md) for the stacked-displacement + Tetra-push pipeline.
>
> **⚠️ The search must run on f32 positions - a double-precision search FALSE-POSITIVES.** Link's
> position is f32 (`cXyz` = three f32; `pm_pos`/`pm_old_pos` are `cXyz*`, `d_bg_s_acch.h`), and
> `core.fp` is only console-faithful when fed f32 (its docstring: "callers feed f32"). A search that
> feeds *double*-precision `old`/`new` to the model finds "clips" at sub-ULP positions the game can
> never hold - they vanish the instant the position is rounded to f32. Measured at the live
> (−1727,−990) seam: a rel=−14° travel direction shows **9 double-precision "clips" over a 0.04 u
> offset span but 0 survive f32 rounding**, while the genuine clip zone survives (2571 double vs 2573
> f32 of 20001 samples). So `gap_search` now snaps every candidate to f32 (`_p32`) before the model,
> and the reliable primitive is **`gap_search.min_f32_clip`** - a direct f32-lattice enumeration
> (settled f32 `old` in front + f32 `new` swept behind the wall). The continuous
> `find_clip`/`characterize` machinery only *approximates* and its `min_displacement` **over-estimates**
> (reported 63 u where the true f32 minimum is 49.9 u); treat `min_f32_clip` as authoritative for
> "clippable?" and min-displacement, and the continuous window as an upper bound only.

> **Flat / 180° (coplanar) seams: clippable PER-SEAM, not categorically unclippable.** A flat wall is
> two coplanar segments with a ~1-ULP plane difference (RAM: `nx` `0x3f800000` vs `0x3f800001`).
> USUALLY the two coplanar quads **tile** the wall with no angular divergence, so a crossing past the
> seam for one triangle lands inside the neighbour's footprint and its ~1-ULP-different plane still
> catches it - no gap. That holds at the Hyrule flat wall x=−157.578 (poly 2360/2355): the analytic
> scan (an order of magnitude finer than the fan) finds NO clip - permanent guard
> `tests/test_seam_clip.py::test_flat_seam_unclippable` (golden `tests/golden/flat_seam_ram.json`).
> **BUT it is a tendency, not a law:** where the swept line crosses the plane at the wall's own
> vertical *tessellation edge* (the two coplanar tris meet and f32 rounding opens a threadable gap), a
> flat wall DOES clip - **live-confirmed at A_mori (4077.6,−1708.8)**, disp ~52.9, `floor_tri` 172,
> `new` 11.8 u behind landing OOB (external tool + our bit-exact model agree). So `enumerate_seams`
> emits single-normal (coplanar) seams too (`coplanar=True`), and the exact f32 verify + full-room
> re-verify decides per-seam - never assume a flat wall is unclippable. History (the overturned blanket
> claim + the two locator false-positive fixes): [history/seam-scanner-analytic-attempts.md](../history/seam-scanner-analytic-attempts.md).
>
> **The clip-offset window IS analytic** (the standing "derive the gap analytically" TODO). For a
> fixed line direction, parametrise the swept line by its perpendicular offset ρ from the seam
> vertex S. Each triangle's plane-crossing point is *linear* in ρ (affine plane func, affine line),
> and the point-in-triangle miss test (`incl_box2d`/`vprod2d` on the seam edge) is a *linear
> inequality* in that crossing → linear in ρ. So each triangle's "miss" is a half-line in ρ and the
> clip window is their intersection = a closed-form interval `[ρ_lo, ρ_hi]` (±1 ULP fused-rounding
> fuzz + the ±20 area tolerance shift the bounds by known amounts). The numeric offset *scan* in
> `gap_search` aliases over sub-ULP windows and can **false-negative** - the closed-form interval,
> intersected with the f32 position lattice, is the alias-free replacement (see the handoff).
- **Perfectly vertical walls (ny ≈ 0).** This is the sharpest requirement, and its cause is
  **LineCheck's three fixed cylinder heights** (30.1 / 89.9 / 125.0), *not* the Y-projection gate.
  A vertical seam's gap is a height-invariant vertical slab, so all three heights miss the same XZ
  point together. Tilt the walls and the seam's gap sits at a *different* XZ at each height - even a
  0.5° lean spreads the three crossing points ~0.4–1.3 u apart (the cylinders are ~95 u apart in Y),
  versus a gap only ~0.01 u wide - so no single straight line can thread all three at once and at
  least one cylinder catches the wall. Verified with the model
  ([`harness/collision/`](../../harness/collision/README.md), `tilt_experiment`): a vertical seam
  yields many clip solutions; **any** tilt ≥0.01° (ny ≥ 0.0002, well below the 0.008 Y-projection
  threshold) drops it to **zero**. With a *single* cylinder height a tilted seam does still clip -
  confirming the per-triangle-plane gap itself is not tilt-dependent; it's the "all three heights
  must miss simultaneously" condition that forces verticality.

## Modelling / predicting a clip

[`tww_sim.core.collision`](../../tww_sim/core/collision.py) is a geometry-agnostic FP-faithful port
of `CrrPos` (LineCheck + WallCorrect + the `cM3d` math). Its `cM3d_CalcPla` is **bit-exact**
(4506/4506 Hyrule planes; see the status note above), so it works on synthetic geometry as well as
on RAM-read planes. [`harness/collision/seam_model.py`](../../harness/collision/README.md)
wraps it with the GanonL seam and exposes `predict_clip(initial, end)` → clip/block;
[`gap_search.py`](../../harness/collision/README.md) is the gap finder: **`min_f32_clip`** is the
reliable f32-lattice search (settled f32 `old` + f32 `new` box - no false positives, authoritative
min-displacement), and `find_clip` / `characterize` / `min_displacement_for_line` are the continuous
approximation (pin the swept line through S, sweep travel direction, micro-scan the offset - now
f32-snapped, but the min-displacement over-estimates; see the f32-viability note above).
[`angle_experiment.py`](../../harness/collision/README.md) sweeps synthetic corner angles through it.
[`seam_scan.py`](../../harness/collision/README.md) is the stage-wide scanner - enumerate a region's
vertical seams (differing-normal corners AND coplanar flat-wall edges) live from Dolphin, screen by the analytic floor, and report each
one's reliable f32 min-displacement (`enumerate_seams` / `scan_seam` / `disp_floor`).
The live (−1727,−990) Hyrule clip is a permanent regression anchor
(`tests/test_seam_clip.py::test_hyrule_1727_f32_clip_anchor`, golden `hyrule_seam_1727_ram.json`):
model min-disp 49.9 u vs live 49.99 u.
`harness/collision/validate_live.py` checks it against a running game by position-hacking Link's
debug pos (`0x803D78FC`).

## Region scanner (existence + exact coords)

The out-of-the-box "is there a clippable seam in this box, and with what exact standable coordinates?"
scanner (`seam_clip_check.clip_check` / `scan_region`), the full-game batch, and the CSV export for the
collision viewer live on their own page: **[seam-clip-scanner.md](seam-clip-scanner.md)** (two-phase
angular search for oblique clips, the standability gates for OOB skirts + step risers, seam-Y-at-floor,
DZB-is-world-coords, and the clean-placement live-validation gotcha).

<a id="fp-note"></a>**FP note.** `cM3d_CalcPla` is bit-exact (4506/4506 RAM planes) once you get four
console-exact details right - all four verified live via a breakpoint at `PSVECMag`/`cM3d_CalcPla`
(inject a known `sq`, single-step, read the FPRs):
1. **Plane dot product** - `PSVECDotProduct` (paired-single) computes `dot = fadds(fmadds(nx,px,
   fmuls(ny,py)), fmuls(nz,pz))`; `nx*px + ny*py` is **fused** (rounds once). `cM3d_VectorProduct2d`
   (point-in-triangle) and the crossing interpolation (`cM3d_InDivPos1/2`) are **not** fused.
2. **Cross product** - `PSVECCrossProduct` (asm @ `0x8030BC14`) has an exact paired-single lane
   layout: the `nx` lane is `fmsubs(a.y, b.z, fmuls(b.y, a.z))` - it **fuses `a.y*b.z`** and
   **pre-rounds `b.y*a.z`** with a separate `ps_mul`. Getting which product is fused vs pre-rounded
   wrong (e.g. the naive `-(a*b - c)`) flips ~36% of normals by 1 ULP.
3. **Plane normalise** - `cM3d_CalcPla` normalises via `VECMag` (`0x8030BBB0`), which uses Gekko
   **`frsqrte`** (recip-sqrt estimate + ONE Newton step), *not* a correctly-rounded `sqrt`. `calc_pla`
   ports Dolphin's exact `frsqrte` table, and the Newton step is the **fused** `fnmsubs(esq, sq, 3.0)`
   (= `3.0 - esq*sq`, one rounding) - not a separate `fmuls` then subtract.
4. **Gekko 25-bit multiply** - single-precision `fmuls`/`ps_mul` round the **`frC` (multiplier)
   operand to 25 mantissa bits** before the op (Dolphin `Force25Bit`). This is a no-op for genuine
   f32 operands (their low mantissa bits are 0), so it only bites in one place: `fmuls e, e` in
   `VECMag`, where `e` is the ~27-bit `frsqrte` estimate (a f64, not an f32). Without it, `e*e`
   double-rounds 1 ULP off - the last ~3.6% of planes. See `collision.py::_force25`.
The port uses [`core.fp`](../../tww_sim/core/fp.py)'s `fmadds`/`fmuls`/`fadds`/`fmsubs`/`fnmsubs`.

**old_pos matters.** The discriminator is the swept line, so the *exact* `old_pos` (Link's previous
position) decides clip vs block at the razor edge. **Settle** a raw brute-force initial (a few
`WallCorrect` iterations) first: the game nudges an initial overlapping the wall cylinder off the wall
front, so its carried `pm_old_pos` differs from the placed position by ~0.08 u - enough to flip cases.

## See also
- [mechanics/collision.md](collision.md) - the DZB triangle mesh, the `dBgS` manager, the live reader/viewer.
- [reference/constants.md](../reference/constants.md#collision-player-wall-cylinders) - wall radius, cylinder heights, tolerances.
- [harness/collision/](../../harness/collision/README.md) - the runnable model + live validator + ground-truth capture.
