# Targeted ballistic hops (sidehop / backflip) + the ESS aim-turn

**Answers:** What are the targeted ballistic hops (sidehop / backflip)? What's the A=roll vs
L+A=sidehop/backflip input mapping? How far do they travel? How do you aim them (the ESS+C-down
in-place facing turn)?
**Status:** offline sim only for the hops (`tww_sim.land`, Python path) — **pending live 0-ULP
calibration** (airtime/anim-gate off-by-one + `pos_y` seed). The ESS+C-down aim-turn is decomp-derived
but its clean-stop is **not yet confirmed live**.
**Source:** decomp `d_a_player_main.cpp` `checkNextActionFromButton` / `procSideStep_init` /
`procBackJump_init` / `posMoveFromFootPos`. Constants:
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

The consistent standstill movers — the backbone of the [setup finder](../model/land-setup-finder.md).

## Input mapping (decomp truth, a common gotcha)

`checkNextActionFromButton` (`d_a_player_main.cpp:4309-4323`) routes the A ("do") button by do-status:
- **A while moving, NOT targeting** → `dActStts_ATTACK_e` → [FRONT_ROLL](roll.md).
- **L held (targeting) + A + directional stick** → `dActStts_JUMP_e` →
  `getDirectionFromShapeAngle()`: stick **LEFT/RIGHT → SIDE_STEP (sidehop)**, stick **BACKWARD →
  BACK_JUMP (backflip)**, FORWARD → nothing.

So **there is no "L+A roll" and no targeted forward move** — L+A is the *hop* family, plain A
(untargeted) is the roll. Both work from a standstill. Unlike the roll (entry-speed dependent) or a
walk (can't be stopped without a frame-perfect input), a hop's displacement is fixed — one button
combo, ballistic, no release timing.

## Ballistic model

`tww_sim.land.LandState`, Python path; pure momentum + gravity, `m3598 = 0`, no foot-plant. Per
`posMoveFromFootPos` (`2464-2479`) + the `execute` order (`posMove → CrrPos`): each air frame
`speed.y = f32(speed.y + gravity)` (clamp `MAX_FALL = −175`), then `current.pos += speed` (x/y/z
together), then collision snaps `pos.y` to the flat floor and sets `GROUND_HIT` — **read one frame
later**, so the land is detected the frame after `pos.y` crosses. Horizontal is `speedF = mNormalSpeed`
along `current.angle.y`, constant through flight.

- **Sidehop** (`procSideStep_init` 6313): `current.angle.y = shape_angle.y ± 0x4000` (perpendicular);
  `mNormalSpeed = cM_scos(6200)·30`, `speed.y = cM_ssin(6200)·30`, `gravity = −2.4`. Lands on the FIRST
  ground-hit frame. Sim net ≈ **±323u** perpendicular, ~22 frames to standstill.
- **Backflip** (`procBackJump_init` 7003): `current.angle.y = shape_angle.y + 0x8000` (backward);
  `mNormalSpeed = 22.5`, `speed.y = 19.0`, `gravity = −3.0`. Lands only once ground-hit **AND** the
  `ANM_ROLLB` frame ctrl (start 2 → end 11 @ 0.8) has finished (`getRate()<0.01`), so momentum can
  slide along the ground for the frames between contact and anim-end. Sim net ≈ **−270u** (opposite
  facing), facing unchanged, ~22 frames.

**Status: offline sim only — pending live 0-ULP calibration** (the airtime/anim-gate off-by-one and the
magnitude-dependent vertical f32 rounding must be gated vs Dolphin; seed `pos_y` from the live anchor).
The XZ path rides the same 0-ULP `LandState.step` accumulation as the walk. Procs `SIDE_STEP 0x0A` /
`SIDE_STEP_LAND 0x0B` / `BACK_JUMP 0x22` / `BACK_JUMP_LAND 0x23`. Ballistics live on the **Python** path
only for now (the native C twin doesn't implement them → build the state `native=False`).

## Facing turn for aiming hops — ESS + C-down in-place rotation

Holding a low/**ESS**-magnitude stick (e.g. `(110,128)` left / `(146,128)` right) at a world angle with
the camera frozen (C-down, `substickY=0`) rotates Link **in place** — `nspeed` stays 0 (the movement
gate `msd > 0.5` isn't met) while `setSpeedAndAngleNormal` still chases facing/travel toward the stick
target, so **facing turns with zero translation**. At the ESS magnitude the rate is only
~**0.055°/frame** (`travel` steps `≈ F0·msd² ≈ 10` s16/frame, facing pinned to travel) — a **fine
sidehop-aim nudge**, not a fast 90° snap. It matters because a sidehop moves perpendicular to facing,
so this rotation points a hop along a chosen axis.

### Open question — the clean stop is unconfirmed live

How the ESS+C-down turn is made to **stop cleanly at a wanted facing** (self-stop at the stick's target
angle vs a timed release) is **not yet confirmed live** — so it is a *pending* facing primitive, not
yet a [setup-finder](../model/land-setup-finder.md) block. Best current guess: it self-stops when
facing reaches the stick target (the chase converges), but this hasn't been gated vs Dolphin.

## See also

- [Land movement overview](land-movement.md) · [roll](roll.md) (the other A-button branch) ·
  [walk-run](walk-run.md).
- [model/land-setup-finder](../model/land-setup-finder.md) — hops as human-consistent blocks.
- [ESS](ess.md) — the low-magnitude stick the aim-turn uses.
