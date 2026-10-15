# The land setup finder — start + target → ranked human-consistent input sequences

**Answers:** What is the land setup finder? How is it different from the `reach_freeze`/A* planner and
from the Twilight-Princess subset-sum tool? Why must it compose blocks by re-simulation (not additive
constants)? What is a "block", which blocks exist, and why is plain walking NOT one? What does
"float-perfect" mean here?
**Status:** v1 built + offline-green (`tests/test_setup_finder.py`); ballistic block displacements are
**pending live 0-ULP calibration** (the optimizer machinery is independent of the exact numbers).
Open ground only (no collision). 2026-07-05.
**Source:** `tww_sim/land/blocks.py` (catalog + `apply_block`) · `tww_sim/land/setup_finder.py`
(A* optimizer + CLI). Forward model: [land sim](land-sim.md) · [land movement](../mechanics/land-movement.md).

---

## Goal

Given a start `LandState`, a world target `(tx, tz)`, and a set of **human-consistent** ground moves,
return **ranked input sequences** (by total frame COST, then by residual `|diff|`) that place Link at /
near the target. It is the TWW analogue of the TP subset-sum setup tool, but built on the bit-exact sim.

It is a *different tool* from the [land planner](land-planner.md): `reach_freeze`/A* steer Link with
per-frame precision (frame-perfect input); the setup finder composes **discrete moves a human performs
without frame-perfect timing** and lets the *combination* land precisely. The C-up freeze is explicitly
**excluded** — it is a frame-perfect input while walking.

## Why re-simulation, not additive displacement constants (the float-perfect crux)

The TP tool sums fixed per-move displacement constants. That is **not** float-exact in TWW:
1. Position accumulates per frame as `pos = f32(pos + f32(d·cos))`, so the *same* move from a different
   f32 start position nets a slightly different displacement — the rounding scales with position
   magnitude (the [`walk_y171` world-magnitude foot-FK lesson](land-sim.md)).
2. f32 addition is not associative — a sum of net-displacements ≠ the true accumulated position.

So the finder composes blocks by **re-simulating each through `LandState.step` from the actual f32
state** and reading the resulting position from the sim (0 ULP vs console). `blocks.apply_block(state,
block)` = `clone()` → feed the block's macro → coast to standstill → child state + exact frame count.
"**Float-perfect**" therefore means: each candidate's *predicted landing position is bit-exact* (a
returned plan, re-run, reproduces its endpoint byte-for-byte — `test_resim_consistency_bit_exact`). The
target itself is reachable only on the block lattice, so a residual (reported exactly) is expected; the
tool returns the closest + cheapest reachable spots.

**Nuance — the residual is sub-ULP for *clamped/reset* atoms, so additive is a fine *planner* model.**
A **neutral flat roll** is genuinely entry-*independent*: its launch speed is `clamp(speedF·1.5 + 0.5,
5.0, 26.0)` ([roll](../mechanics/roll.md)), so a
near-zero (neutral) entry saturates to the **5.0 floor** and a full-run entry to the **26 cap** — either
way a *constant*, and `setSingleMoveAnime(ANM_ROLLF)` resets the anim frame ctrl (no phase carry) while
flat ground drops the slope term. The magnitude is thus fixed; the *only* variation is the sub-ULP
position/facing rounding of point 1 (< 1u per roll, usually 0). Same for the ballistic hops (fixed
launch constant) and the crawl cycle. So for those atoms you **can** plan by summing constants (accurate
to sub-unit) and re-simulate the chosen chain **once** only to certify a 0-ULP landing. Re-simulation
is *strictly* required only for (a) bit-exact seam/tile targets where accumulated sub-ULP drift can
cross a ±1u boundary, and (b) genuinely entry-*dependent* blocks — a **moving** roll whose `speedF`
lands inside the open `(floor, cap)` band, or a jump carrying horizontal speed.

## What is a "block" — and why WALK is not one

A block starts and ends at a standstill and needs **no frame-perfect input**, so its effect is
repeatable. Because a directional roll/hop reorients or launches deterministically, blocks compose.

**Plain walking is NOT a block:** there is no way to *stop* a walk without a frame-perfect input (a
precise release frame, or the C-up freeze). So the consistent movers are the ballistic hops + rolls +
crawl — never a raw walk.

### Input mapping (decomp truth — a common gotcha)
`checkNextActionFromButton` (`d_a_player_main.cpp:4309-4323`):
- **A while moving, NOT targeting** → FRONT_ROLL (roll). A *directional* roll snaps `shape_angle.y =
  m34E8` on entry, so a backward roll is the free "turnaround roll" (no pivot cost).
- **L held + A + directional stick** → doStatus JUMP → **SIDE_STEP (sidehop, stick L/R)** or
  **BACK_JUMP (backflip, stick back)**. There is **no L+A roll** and **no targeted forward move**.

### v1 catalog (`blocks.default_catalog`)
| block | input | effect (facing +z) | consistency |
|-------|-------|--------------------|-------------|
| `backflip` | L+A+back | ~**−270u** (opposite facing), facing unchanged | exact (ballistic) |
| `sidehop_l` | L+A+left | ~**+323u** perpendicular (2-D) | exact (ballistic) |
| `sidehop_r` | L+A+right | ~**−323u** perpendicular (2-D) | exact (ballistic) |

Ballistic mechanics + constants: [land movement](../mechanics/ballistic-hops.md).

### Follow-on blocks (not yet in the catalog)
- **Facing turn** — the **ESS + C-down in-place rotation** (hold a low/ESS-magnitude stick at a world
  angle with the camera frozen): Link rotates in place with `nspeed = 0` (no translation). At the ESS
  magnitude it is only ~0.055°/frame — a fine sidehop-aim nudge, not a fast 90° snap; **how it stops
  cleanly at a wanted facing needs live confirmation** before it becomes a block. This is the primitive
  that lets a sidehop (perpendicular) serve a chosen axis. See [land movement](../mechanics/land-movement.md).
- **Roll** (needs a consistent entry speed — e.g. off a run) and **crawl** (`CRAWL_*` 0x0F–0x12, its own
  `d_a_player_crawl.inc` subsystem) — each a bit-exact sim port + live gate, then a catalog entry.

## The optimizer (`setup_finder.find_setups`)

A* over `LandState` nodes: priority = frames-so-far + optimistic frames-to-target
(`dist / _BEST_PER_FRAME`); each edge applies a block via `apply_block`; goal = within `tol` of the
target. **Dominance** dedups by quantized `(pos_x, pos_z, facing)` (pruning only — the exact `LandState`
stays in the node, so endpoints are bit-exact). Optional `bounds` corridor keeps every intermediate rest
off a wall (the sim has no collision). Returns every within-tol node, ranked, capped to `max_results`.
`expand_path` re-expands a plan to the full per-frame controller inputs for live/DTM verification.

CLI: `python -m tww_sim.land.setup_finder tz=<z> [sz= sx= sy= facing= tx= tol= maxf= depth= n=]`.

## Roadmap
Live-calibrate the ballistic displacements (0 ULP, `tests/dolphin`); model the ESS+C-down facing turn;
add roll + crawl blocks; 2-D relaxation (the state + search are already 2-D-native). Collision/basin
scoring track the [land planner](land-planner.md) flavor-A/B work.

## See also
- [Land movement](../mechanics/land-movement.md) (ballistic hops + input mapping) ·
  [Land sim](land-sim.md) (position f32 accumulation, the air/ballistic path) ·
  [Land planner](land-planner.md) (the per-frame `reach_freeze`/A* tool this complements).
