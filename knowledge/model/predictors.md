# Position & camera predictors

**Answers:** What are the predict/ modules and how do they relate? How is arbitrary-direction gain
priced? Why a live stick-angle grid instead of atan2? What was the off-axis charge residual?
**Status:** validated bit-exact (`tests/test_complicated.py`, `tests/test_stick_table_integrity.py`).
**Source:** `tww_sim/swim/predict/*` (swim + stick-angle), `tww_sim/core/camera/*` (camera yaw); live RE 2026-06-27/28, stick-grid gold re-dump 2026-07-01. Full log: [history/camera-predict-history](../history/camera-predict-history.md).

---

The base [swim sim](swim-sim.md) is bit-exact for v/anim/air/state under one assumption: **C-stick held down
(camera frozen)**. The `predict/` modules remove that assumption to predict the **camera (csangle)**
and **Link's position (x/z)** bit-exactly under arbitrary main-stick + C-stick. They import the sim
read-only.

| Module | Role |
|--------|------|
| `swim_arbitrary.py` (`ArbitrarySwimState`) | speed gain for arbitrary stick direction |
| `stick_angle.py` (+ `stick_angle_table.csv`) | exact main-stick → angle |
| `camera_exact.py` / `camera_arbitrary.py` (+ `omega_table*.csv`) | camera yaw recurrence |
| `swim_exact.py` | exact displacement direction + magnitude given the camera angle |
| `swim_predict_complicated.py` | the unified predictor |

> The 4 `swim_predict*` variants form an evolution chain kept as separate modules; consolidating them
> is a known follow-up (each merge re-validated bit-exact).

## Arbitrary-direction gain

The decomp prices EVERY deflected swim frame identically: gain = `mStickDistance · 3 · cM_scos(d_turn)`
with a 1-frame lag — there is **no chg/ess distinction in the game**. So `ArbitrarySwimState` routes
every deflected frame through the charge path (correct 1-frame lag); neutral → `neu`. The earlier
snap-cone chg/ess split mis-priced the snap↔non-snap boundary. Ordering (live-pinned): the facing/gain
`m34E8` uses **cam[f]** (the current frame's csangle), not cam[f−1].

## Why a live stick-angle grid (not a closed form)

The decomp is `mAngle = 10430.379f · atan2f(mPosX, −mPosY)` with `mStickDistance = mMainStickValue =
min(hypot(clamped_stick)/54, 1)`, the stick vector from `PADClamp`/`ClampStick` (deadzone 15, octagon
max 72 / xy 40). A pure decomp port reproduces the angle math exactly at non-boundary cells, but
**diverges from live Dolphin at 17.6 % of cells** — Dolphin's byte→analog mapping differs from the SDK
`PADClamp` at the deadzone boundary and octagon. The sim is validated against **Dolphin, not console**,
so the live capture is authoritative and a closed-form generator cannot replace it. The exact
`mMainStickAngle` for all 65536 (sx,sy) cells is captured live into `stick_angle_table.csv`. For an
**on-axis** stick (sx==128: ESS / pure charge) the closed form is exact anyway.

The table's `stick_dist` and `value` columns **both equal** the closed-form `/54` gain magnitude the
sim already uses (locked by `tests/test_partial_magnitude.py::test_grid_stick_dist_matches_closed_form`
and `tests/test_stick_table_integrity.py`). Integrity — `angle` bit-consistent with `atan2f(x,−y)` for
all 65536 cells, exact-diagonals on the 45° grid — is locked offline.

## Stick-angle table corruption (resolved)

The shipped `stick_angle_table.csv` carried two live-dump artifacts, both now fixed by a settle-and-
verify gold re-dump (`harness/capture/stick_grid_redump.py`):

- **Input-path** (older, [resolved-bugs](../history/resolved-bugs.md)): x/y/`value` had been dumped via
  Dolphin's **calibrated `set_gc_buttons`** path instead of the **raw-byte `advancewith`** path the
  game/tests/DTM use (±155 s16 on off-axis cells → a 0.0105 too-high off-axis charge v, after a wrong
  "controlled-vs-smoothed yaw" hypothesis). Regenerating via `advancewith` fixed the magnitude path.
- **Read latency** (found+fixed 2026-07-01): the 1-frame set/read dump pipeline read `mMainStickAngle`
  / `mStickDistance` *before* the game had updated them. ~2609 `angle` cells and the **entire**
  `stick_dist` column were latency-lagged (`stick_dist` shifted ~2 rows). Worst at exact-diagonal cells
  (`|deadzone(sx)|==|deadzone(sy)|`): e.g. (160,160) read 24260 vs the correct 24576, (160,112) 15162
  vs 15771. Since the sim reads the `angle` column to drive facing, this was a **real facing desync** —
  confirmed 3.35° at (160,112) via a clean-DTM negative-v (true superswim) test; the corrected cell
  matched live to 0.00°. `test_complicated` never caught it: its inputs stay in sx 98–157, sy∈{0,255}
  (near-vertical), never sampling the sx≥160 / diagonal corrupt region.

The gold re-dump holds each stick for a multi-frame settle, then verifies stability across two
consecutive settled frames (0 unstable / 65536), with per-frame air/speed/pos re-lock so Link stays an
in-place superswimmer; 4-instance parallel orchestration via `run_parallel_dump.py`. See
[history/resolved-bugs](../history/resolved-bugs.md).

## See also

- [Camera](../mechanics/camera.md) · [Arrow](../mechanics/arrow.md) (`ArrowState` 2-D stepper) ·
  [Swim sim](swim-sim.md) · [history/camera-predict-history](../history/camera-predict-history.md).
