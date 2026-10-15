# Seam-scanner analytic-window attempts (2026-07-08) - what failed and why

> **status: historical** - research log / dead ends, NOT current truth. The current scanner + the
> validated deterministic model live in [mechanics/seam-clip-scanner.md](../mechanics/seam-clip-scanner.md).
> This page records the analytic approaches that were TRIED and REJECTED so the next session does not
> repeat them.

Context: the previous dump missed real clips and listed some that "don't work." Root-causing the misses
(this session) produced the deterministic model on the scanner page. Getting from that model to a
guaranteed-fast COMPLETE scanner is still open. These attempts were on the road there.

## 1. "Clips live only at the bisector or the grazing edges +-interior/2" - REJECTED (incomplete)

First hypothesis: a sharp corner clips near rel 0, an obtuse one clips at the cone edges (grazing a wall
face), so search only bands around `0` and `+-interior/2`. It caught all 80 kaze octagon 135deg facets
(they ARE symmetric, so their windows sit at the edges) and looked like the fix. It is WRONG for
ASYMMETRIC corners: Hyrule (1127,1621) (interior 144, edge +-72) clips at rel -34..-68, a broad band
MID-cone, nowhere near 0 or +-72. Windows can sit anywhere in the cone, so hot-spots-only misses them.

## 2. `sign(kA) == sign(kB)` 2D-tangent direction condition - REJECTED (predicted nothing)

Tried to predict the clip-possible directions analytically: with travel dir `d`, perp `p`, wall face
tangents `uA/uB`, the offset that makes the swept line miss wall A is `rho*kA < 0` where
`kA = (p.uA) - (nA.p)(d.uA)/(nA.d)`; a common `rho` (miss both) needs `sign(kA) == sign(kB)`. It
predicted ZERO clip directions everywhere real clips exist. WHY it is wrong: TWW's inclusion test
(`cM3d_InclusionCheckPosIn3PosBox2d` + `_tri_in_2d`) runs in the triangle's DOMINANT projection (X or Z,
which for a vertical wall involves the Y axis) with a `+-20` area tolerance, and for a diagonal wall BOTH
the X and Z projections must be inside for a hit. The pure-XZ tangent model ignores all of that. A
correct closed form must be derived from `_tri_in_2d`, not the 2D tangent.

## 3. Full-cone brute sweep with deep distances - CORRECT, was slow, now SUPERSEDED

Sweeping the analytic cone (`|rel| <= interior/2`) at deep old-distances (offset +0..+18) with hot-spot
ordering DOES find the oblique clips (fixes the distance-coverage root cause). It was the shipped
`clip_check` state and was SLOW: unclippable seams (the majority) drained the whole per-seam budget on
empty `first_f32_clip` rings (~5-18 s each). SUPERSEDED 2026-07-08 by `seam_locator` (anisotropic
search + native ring + LineCheck short-circuit), which made the full-game dump practical - see the
scanner page. `clip_check` itself is retained as the single-seam checker.

## 4. "Search the bare 2-wall corner first, then verify barriers at that `new*`" - REJECTED

Idea: the isolated 2-wall corner clips at EVERY cone direction (verified), and its `first_f32_clip`
never rings out empty (it always finds a clip fast), so search the bare corner for `new*`, then verify
the full barrier set + wall-correct in a TINY box around `new*`. Measured on 5 Hyrule seams: NOT
reliably faster (105 s vs 36 s on one unclippable seam - the bare search itself rings far when that
specific old's bare clip is distant), and INCOMPLETE (missed rel -43 on (1127,1621), found 7 spurious
extras on (919,-7986)) because verifying around a SINGLE `new*` misses the other clipping `new` and the
tiny box mis-includes barrier-blocked ones. The right shape is a per-direction CHEAP prune
(barrier-line-block + valid-old + floor, all O(barriers), no f32 ring), reducing f32 work to a tiny
verify only on surviving directions. That prune is the open work.

## 5. "cone AND floor AND valid-old AND not-blocked EQUALS the real f32-clip set" - OVERTURNED (superset, not equal)

The 2026-07-06/07 model on the scanner page claimed (a) an isolated 2-wall corner clips at EVERY
direction in its cone, and (b) a real room's narrow windows are ENTIRELY barrier + floor pruning of
that full cone. The 2026-07-08c first-experiment refuted the *equality*: the cheap set
`{cone ∧ floor ∧ valid-old ∧ not-blocked}` is a **sound SUPERSET** of the real f32-clip set
(`real_only = 0` on all Hyrule test seams, i.e. it never drops a real clip) but is **NOT tight**
(`cheap_only` = 98-232 vs `both` = 29-30). For ISOLATED / barrier-free corners the cheap prune passes
the WHOLE cone (FN0 (1127,1621) and FN1 (919,-7986) have zero barriers and a flat floor) yet the f32
clips land only in a narrow sub-band. So claim (a) holds in CONTINUOUS space but the **f32-reachable**
clip set is a coordinate-magnitude-dependent SUBSET of the cone (local ULP vs the ~1e-3 fan gap: FN2
(3305,-17350), coord ~17350, ULP ~2e-3 > gap ~1e-3, has NO f32 clip anywhere), and claim (b) is FALSE
for isolated corners (there the window is pure f32-lattice availability + the deep-old validity
constraint, not barrier pruning). **Consequence: the f32 verify is LOAD-BEARING, not an optional
speed-up.** The clip is a LINE property: thin (~1e-3) in the perpendicular offset ρ from the seam
vertex, broad ALONG travel, so the verify must search ANISOTROPICALLY (this is what `seam_locator`
does; the old square-ULP ring conflated the two axes and missed high-coord clips displaced along the
wall).

## 6. `offset_window` as an f32-reachability GATE, and a direction-level barrier-block prune - BOTH REJECTED

Two cheap-prune ideas from the 07-08b plan, killed 07-08c:
- **`offset_window` (continuous ρ-window) as a soundness proof of "no f32 clip here"** FAILS: its
  synthetic short old (`t_back=3`) does not represent the settled-old clip, so it returns empty windows
  for directions that genuinely clip. A continuous/double ρ-window is not a tight proxy for the
  f32-reachable set (the false-positive caveat cuts both ways). There is **no cheap SOUND
  unclippability proof for isolated corners**, hence `seam_locator`'s per-seam f32 budget cap.
- **A direction-level barrier-block prune** (skip a direction if a barrier blocks the representative
  line `old → S+0.45·dir`) is **UNSOUND**: a barrier can block the representative line while the true
  clipping `new` threads PAST it (it false-negated m477, which the baseline finds). Barriers must be
  handled by the full-trilist f32 verify, not a separate cheap test.

## Reusable assets left for the next session

- `harness/collision/window_dataset.py`: the ground-truth window-labeling oracle (feature vector +
  measured clip window per seam, streaming JSONL). Run it to regenerate/extend the dataset.
- `_generated/window_hyrule0.jsonl`, `_generated/window_kaze12.jsonl`: partial measured datasets
  (gitignored; regenerate via the oracle).
- The deterministic model (cone + bare-corner-clips-everywhere + prune) on the scanner page is the
  foundation; the missing piece is the cheap, exact prune computation.

## OVERTURNED 2026-07-15: "flat / 180deg (coplanar) seams are unclippable" was over-broad

The old blanket claim (was `mechanics/seam-clip.md`): a flat wall's two coplanar segments **tile**
it, so any crossing past the seam for one triangle lands inside the neighbour (whose ~1-ULP-different
plane still catches it) -> no gap -> flat seams unclippable, and `enumerate_seams` SKIPPED every
single-normal vertical-edge cluster ("flat / free edge, not a corner").

Overturned by a CONFIRMED flat-wall clip at **A_mori (4077.6, -1708.8)** (external prediction tool +
our bit-exact `crr_pos_walls`, live `floor_tri` 172): old=(4059.622,-1673.617) -> new=(4083.649,
-1720.699), disp ~52.9, `line_hit`/`wall_hit` both False, `new` 11.8u behind the wall landing OOB.
The swept line crosses the wall plane EXACTLY at the wall's own vertical **tessellation edge**
(4077.58,-1708.8), where the two coplanar triangles meet, and f32 rounding opens a threadable gap
there. So the tiling argument is a TENDENCY, not a law. Fix: `enumerate_seams` now emits single-normal
(coplanar) seams (`coplanar=True`, interior 180); the exact f32 verify decides per-seam. The specific
Hyrule wall x=-157.578 (poly 2360/2355) IS still unclippable (sub-ULP gap everywhere) -- its guard
`tests/test_seam_clip.py::test_flat_seam_unclippable` still passes -- so the refined truth is
"per-seam, not categorical." Gate: `tests/test_seam_locator.py::test_locator_finds_amori_coplanar_flatwall_clip`.

## Two false-positive causes in the shipped locator, fixed 2026-07-15 (user-flagged)

Both surfaced as "seam clips the scanner listed that don't actually work" (GanonK top-of-room):
- **Barrier gathered at the SEAM-VERTEX Y, not Link's floor Y.** The wall cylinder is at Link's feet,
  but `locate` gathered the CrrPos barrier at `seam["S"][1]`. On a TALL corner the standable floor is
  hundreds of u above the seam base (GanonK top: base 6997, floor ~7778), so the walls at Link's real
  height were excluded and the f32 verify never saw the WallCorrect blocker -> false clip. Fix: gather
  at the representative standable floor Y (the same `_representative_link_y` the step-riser gate uses).
- **The gathered barrier (edge-dist `GATHER_R`) can still MISS a blocker** even at the right Y (busy
  A_mori side corners: 5 phantoms). Fix: `locate` now RE-VERIFIES the winning exact `old`->`new`
  against the WHOLE room's walls; a clip whose full-room sweep is stopped short (line/wall hit, or
  doesn't reach `new`) is dropped. Far walls can't touch the short cut segment, so this never
  false-negatives a real clip. Gate: `tests/test_seam_locator.py::test_locator_rejects_ganonk_top_flatwall_phantom`.
