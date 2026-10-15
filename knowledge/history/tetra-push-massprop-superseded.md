# Tetra Co-push: the superseded mass-proportional model (2026-07-06)

> **status: historical** — this records a model that was WRONG and how it was corrected. Current
> truth is [mechanics/actor-push.md](../mechanics/actor-push.md). Kept for the lesson.

## What was claimed (handoff-06g/06h, first `cc_push.py`)

The actor-vs-actor Co push was ported from **`cCcS::SetPosCorrect`** (`c_cc_s.cpp:254`), whose weight
split is **mass-proportional**: actor *i* moves `depth × wⱼ/(wᵢ+wⱼ)`. With Link weight 120 and Tetra
weight 140, that gave Link **140/260 ≈ 0.538 ×** the overlap depth. The Link body Co cylinder was
taken as **R=50, H=81.25, centered at the feet (`current.pos`)**. The seam-clip worked example
concluded a **≈0.68 u** Tetra overlap (push ≈0.37 u) closes the (−1727,−990) clip.

## Why it was wrong (live-corrected 2026-07-06)

Three separate errors, all found by live breakpointing on GZLJ01:

1. **Wrong function.** `SetPosCorrect` is **virtual**, and the live collision system is the subclass
   `dCcS`. A breakpoint on the base `cCcS::SetPosCorrect` (JP 0x8024101C) **never fires**; the game
   dispatches to `dCcS::SetPosCorrect` (JP 0x800AB1E4). The override uses a **rank table**
   (`dCcS::GetRank` → `rank_tbl[r1][r2]/100`), NOT mass-proportional. Link (120) and Tetra (140) both
   collapse to **rank 5**, and `rank_tbl[5][5] = 50` → an exact **50/50** split. Live-confirmed:
   `|Link.cc| / |Tetra.cc| = 1.0000` every frame (the mass-proportional model predicts 1.167).
2. **Wrong Link radius.** `daPy_lk_c::setCollision` sets the body Co cylinder to **R=30** while
   walking/rolling (`SetR(50)` only under `checkGrabWear()`, i.e. carrying an item). Live R read = 30.
   So `sumR = 30+50 = 80`, not 100.
3. **Wrong Link center.** The cylinder center is the **horizontal midpoint of the root & neck joints**
   (animation-driven, swaying ~16–22 u from `current.pos`), not the feet. Also H ≈ 107 walking, not
   81.25.

Corrected result: the nudge still works, but needs **≈1.23 u** overlap (push ≈0.615 u at the 0.50
share) — about 2× the overlap the 0.538 model implied.

## Lessons

- **Breakpoint the *virtual* target, not the base class.** For any `cCcS`/`dCcS`-style engine, the
  game uses the `d`-prefixed override. Confirm the base symbol's breakpoint actually *fires* before
  trusting a port of it; if it doesn't, find the override in `framework.map` (`SetPosCorrect__4dCcS…`).
- **Player collision cylinders are state/animation-dependent.** Link's body Co cyl radius, height, and
  center all change with proc/anim (walk vs roll vs grab). Read them live in the *actual* state, don't
  assume a single constant.
- **Idle Link doesn't push.** The body Co cylinder is only set/checked while Link is actively moving;
  a debug-pos hack that drops idle Link into an overlap exercises nothing. Drive Link *into* the
  partner with real movement input (see `dolphin_mem moveto`).
