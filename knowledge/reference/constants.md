# Constants - canonical values

**Answers:** What is the value of <some superswim constant>? Deadzone? Stick divisor? The
turnaround angle threshold? Animation wrap points? The strobo band speeds?
**Status:** validated (decomp + live) unless a row says otherwise.
**Source:** per-row. This is the single source of truth - other pages link here instead of
restating. If a number elsewhere disagrees with this table, this table wins and the other page
is wrong.

> Scope note: this table covers the **stick / speed / animation / turnaround / strobo** constants,
> the **collision** (wall cylinder + actor Co push) and **land sword-cut** constants, the **land
> movement / turn-proc** constants, and a camera-steering summary. Balloon and planner constants are
> added as those topics migrate.

---

## Stick geometry

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Neutral | `(128, 128)` | center; inside the dead zone → no swim input | decomp `PADClamp` |
| Radial dead zone | **15** | raw units removed around neutral before any input registers | `PADClamp` (GC SDK) |
| Main-stick divisor | **54** | `mPosX = stickX / 54` after dead-zone removal | `JUTGamePad::CStick::update` (JUTGamePad.cpp:303-310) |
| Cardinal ESS offset | **18** | min registered deflection, e.g. `(128, 110)` | live |
| Diagonal ESS offset | **17** per axis | e.g. `(111, 111)`; magnitude ~24 but smaller per-axis | live |

**Stick distance:** `mStickDistance = clamp((|raw − 128| − 15) / 54, 0, 1)` (cardinal).

**Swim-input gate:** a frame counts as a swim input iff **`mStickDistance > 0.05`**
(`d_a_player_main`), i.e. `hypot(dz_x, dz_y) > 2.7` after dead-zone removal - a *radial* test,
not the dz-15 *square*. They differ only on a thin ring (~260 cells) just outside the square where
one axis is 1–2 past the dead zone but the radial magnitude is still ≤ 0.05; the game blocks the
tiny gain there. The sim uses this exact gate (`sim.stick_angle_deg` returns `None`), bit-identical
to the gold stick table's `value ≤ 0.05` (locked by `tests/test_stick_table_integrity.py`). Real
routes never hit the ring (they use full deflection, ess `(128,110)`, or true neutral).

## Speed deltas

Per frame, to potential speed:

| Regime | Δ potential speed | Notes | Source |
|--------|-------------------|-------|--------|
| Charge (on-axis) | **+3** | full alternating deflection; `×cos(angleΔ)` if tilted | `setSpeedAndAngleSwim` (d_a_player_swim.inc:41,66) |
| ESS cardinal | **−1/6** (≈ −0.1667) | min non-neutral hold, e.g. `(128, 110)` | live (exact) |
| ESS diagonal | **−0.1571** | octagonal geometry removes slightly more → more efficient | live |
| Neutral | **−2** | dead zone, separate code path (drag-free) | live (exact) |
| Saturation | flat **−3** | reached at off ≥ 70 (stickY ≤ 58) | live |
| Max normal speed | **18** | `maxNormalSpeed`, HIO mSwim | decomp |

**Decay law (any registered input):** `decay = clamp((|raw − 128| − 15) / 54, 0, 1) · 3`.
Piecewise-linear, exact to ~off 63; a ~1-unit shortfall appears in off 65–68 (PADClamp top-end
compression); saturates to exactly 3.0 by off ≥ 70.

## Speed gain while charging / arrow swimming

```
delta = mStickDistance · 3.0 · cM_scos(facing_after − facing_before)
```
- On-axis (Δ=0) → +3. Tilt α off the pure-back axis → `charge_rate = −3·dist·cos(2α)`.
- `mStickDistance` caps at 1 (live-confirmed); tilt changes the **cos**, not the magnitude.

## Animation

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| `End_swim` (ANM_SWIMING) | **23** | ESS anim wraps here (`nfmod(·, 23)`); = the `cos(π·x/23)` head-bob period | live (22.9965) |
| `End_wait` (ANM_SWIMWAIT) | **26** | neutral anim wraps here | live (25.997) |
| **x598** | **598** = 26·23 | the neutral→ESS anim-scramble multiplier (`End_wait · End_swim`) | derived + live |

**ESS anim increment / frame:** `|v|/36 + 3/5 + (1 − (air+1)/900)`.
**Neutral anim rate / frame:** `0.5 + 2.5·(1 − (air+1)/900)` (HIO `field_0x40 = 0.5`,
`field_0x70 = 2.5`). Speed-independent; rises as air depletes.

## Head-bob (animation-frame) drag → true speed

```
af_drag(v, anim) = 0.6·v + 0.4·v·|cM_scos(π·anim/23)|          # numerator
true_disp        = af_drag(v, anim) / (1 + 0.35·getSwimTimerRate(air))   # full true speed
```

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| `field_0x60` | **0.4** | head-bob cos weight (so base weight = 0.6) | decomp `d_a_player_main.cpp:2424-2428` |
| `field_0x7C` | **0.35** | swim-timer drag denominator coeff | decomp; backed out exact from live |
| `getSwimTimerRate` | `1 − air/900` | air term; decomp `1 − itemTimeCount·0.0011111111` | d_a_player_swim.inc:283 |

**`cM_scos` is the console cosine table, not `math.cos`** - a 4096-entry s16 table, low 4 bits
truncated (`index >> 4`, no interp). The ~5e-4 error vs true cos is amplified by the high-speed
exit and the x598 scramble; using `math.cos` breaks bit-exactness. See [glossary](glossary.md#cm_scos).

## Air

| Constant | Value | Source |
|----------|-------|--------|
| Max air | **900** | reset on swim entry (`changeSwimProc`, d_a_player_swim.inc:126) | 
| Air drain | **−1 / frame** | live |
| Cold-swim air budget | **≈ 900 frames** | 900 air ÷ 1/frame - a cold cruise from full air lasts this long before drowning; the planner enforces it (`allow_drown=False`) | derived |

## Turnaround / arrow angular budget

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| `0x6000` | **135°** | `DIR_BACKWARD` threshold: stick > 135° off facing → instant 180° snap | decomp `getDirectionFromAngle` (d_a_player_main.cpp:2278) |
| `0x2000` | **45°** | LEFT / RIGHT threshold | same |
| Arrow budget | **45°** off straight-back | the snap cone is 90° wide around 180°, i.e. stick < 45° off directly-behind | derived from `0x6000` |
| Gradual turn rate | **~7° / frame** | `cLib_addCalcAngleS` chase, used once the stick exceeds the 45° budget | live |
| Arrow tip-over | Xbias ≈ 190–200 (α ≳ 20°) | snap dies → forward release, speed LOSS | live |
| Arrow spin-up | **2 frames** | non-snap forward frames (−each loses ~+3/fr) before the 0↔180 swing locks in | live (sim.py) |

Angle units: `0x10000 = 360°`. World travel axis: `world_angle = stick_angle + csangle + 0x8000`.

## Stroboscopic bands

Band speeds solve `ESS increment = 23·k`, so they are **air-dependent**:

| Band | Approx |v| | Condition |
|------|-----------|-----------|
| k=1 | **≈ −794** (air 597) | increment ≈ 23 |
| k=2 | **≈ −1630** (air 900) | increment ≈ 46 |

The legacy "−850 / −1650" community figures are the same bands, off by the air dependence.

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| `charge_disp_factor` | **0.9466** | charge frames move ~5.3% LESS than ESS at the same (v,anim,air) | live (band 2 only - revalidate far from −1630) |
| `avg_ess_rate` | `(4+3π)/(5π)` | mean fraction of speed retained as displacement while ESSing | tool closed-form |

## Collision (player wall cylinders)

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Wall radius | **35.0** | player wall-collision cylinder radius (standing/walking) - the "must-clear" distance for a seam clip | decomp `daPy_lk_c::setBgCheckParam` (d_a_player_main.cpp:10715) |
| Wall cylinder heights | **30.1 / 89.9 / 125.0** | the 3 `dBgS_AcchCir` heights above Link at which LineCheck/WallCorrect probe | decomp same fn |
| Point-in-triangle tolerance | **±20.0** (area units) | `cM3d_CrossX/Y/Z_Tri` signed-area edge slack, both windings | decomp `c_m3d.cpp` |
| `cM3d_IsZero` (kZero) | **1e-5** | float "is zero" threshold in the collision math | decomp `c_m3d.h` |

How these produce the seam clip: [mechanics/seam-clip.md](../mechanics/seam-clip.md).

## Collision (actor Co push)

Cylinders, weights, the rank split, `Zl1` look-at clamps: [constants-npc.md](constants-npc.md) ([actor-push.md](../mechanics/actor-push.md)).

<a id="land-sword-cut-roll-stab"></a>
## Land sword-cut (roll stab)

The [roll stab](../mechanics/roll-stab.md):
a sword cut fired out of a FRONT_ROLL. HIO `daPy_HIO_cutF_c1`/`cutA_c1`
(`d_a_player_HIO_data.inc:31/27`); procs `d_a_player_sword.inc:660/430`. Live-validated bit-exact (0 ULP,
GZLJ01 savestate 7, 2026-07-06). Only the joint-0 (root) translate of `cutf.bck`/`cuta.bck` is used.

| Constant | CUT_F | CUT_A | Meaning (field) |
|----------|-------|-------|-----------------|
| anim frame ctrl rate | **1.2** | 1.2 | `mFrameCtrlUnder[MOVE0]` rate (field_0x4) |
| anim start frame | **4.0** | 4.0 | `setSingleMoveAnime` start (field_0x8); `+1.2/frame`, `EMode_NONE` end 19 |
| checkPass launch frame | **6.0** | 6.0 | `field_0x28` → set `mNormalSpeed` |
| `mNormalSpeed` launch | `\|speedF\|·0.2 + 8.0` | `\|speedF\|·0.2 + 10.0` | field_0x10 mult / field_0x14 add |
| decel maxStep / minStep / scale | **0.95** / 0.5 / 0.7 | **2.6** / 0.5 / 0.7 | `cLib_addCalc` (field_0x18/0x1C/0x20) |
| early-exit frame → WAIT | **17.0** | 16.0 | `getFrame() > field_0xC` → `checkNextMode(1)` |
| first-frame lunge (from a 26 roll) | **49.220** | 49.220 | `speedF 26 + m3700.z(4.0)=23.220` (posMove m34C2==1) |
| diagonal-aim turn (scale/max/min) | 30 / 0x3CDF / **0x1F40** | same | `cLib_addCalcAngleS(shape, m34D4, mTurn.f4/f0/f2)`; min ≫ diff → snap |
| in-line thrust aim range (`CUT_DIR_FWD`) | **0x2000** | 0x2000 | `\|aim − roll_facing\| < this` stays CUT_F (`getDirectionFromAngle`); else CUT_L/R |

The lunge = `speedF` (foot term, along `current.angle.y`) + the root-translate delta
`m3700(t)−m3700(t−1)` rotated by `shape_angle.y`; `m3700` resets to 0 in `procCut*_init`, so frame 1
stacks the full root translate onto the carried roll speed. A **diagonal thrust** (roll straight, aim
the stick + B) latches `m34D4` and snaps `shape=travel` to it on the first cut frame, rotating the tail
while the 49.22 stays along the roll facing - a diagonal 49.22 needs an aimed *roll*. See
[roll-stab.md](../mechanics/roll-stab.md), [seam-clip.md](../mechanics/seam-clip.md).

<a id="land-movement"></a>
## Land movement (walk / roll / ATN / hops)

Walk/run, brakeslide/EBS, roll, ballistic hops. Decomp `d_a_player_main.cpp` HIO
(`mMove`/`mRoll`/`mAtnMove`/`mAtnMoveB`/`mSideStep`/`mBackJump`); live-validated bit-exact. Techs:
[walk-run](../mechanics/walk-run.md) · [brakeslide-ebs](../mechanics/brakeslide-ebs.md) · [roll](../mechanics/roll.md) · [ballistic-hops](../mechanics/ballistic-hops.md).

| Constant | Value | Meaning (field) |
|----------|-------|-----------------|
| run cap `mMaxNormalSpeed` | **17.0** | `mMove.field_0x18` |
| walk accel step | **+3.5/fr** | `field_0x14 = 3.5` × `cM_scos(0)` × `msd²` |
| walk decel `cLib_addCalc(v,0,scale,max,min)` | scale **0.6** / max **2.5** / min **1.8** | `field_0x24/0x1C/0x20` |
| input latency | **2 frames** (press and release) | `tww_sim.land.INPUT_DELAY` |
| ESS down / left / right | `(128,110)` / `(110,128)` / `(146,128)` | see [ess.md](../mechanics/ess.md) |
| decay: brakeslide / EBS / EBS-toward-cam / brake | −0.14 / −0.011 / ~−0.001 / −2.5 per frame | live |
| ATN cap (attention / DIR_BACKWARD) | **12** (`mAtnMove.field_0xC`) / **15** (`mAtnMoveB.field_0xC`) | |
| ATN speed scale (side / back) `field_0x8` | 5.0 / 2.5 | |
| ATN `setNormalSpeedF` (scale/max/min) side / back | 0.5 / 7.5 / 4.0 · 0.5 / 8.0 / 2.0 | |
| ATN travel-chase `cLib_addCalcAngleS(scale,max,min)` | 6 / 3000 / 2000 | |
| direction cos thresholds (fwd / back) `mAtnMoveB.0x2C/0x30` | ≥0.99 → FORWARD · ≤−0.99 → BACKWARD (else side) | |
| roll speed `clamp(speedF·field_0x18 + field_0x1C, field_0x20, cap)` | **×1.5 + 0.5, floor 5.0, cap 26.0** (= 0.5 + 17·1.5) | `mRoll` |
| roll duration / exit frame `mRoll.field_0x10` | **17** (anim rate 1.1, ≈18 frames) | |
| A-press → roll (ATTACK) stick floor | `mStickDistance > `**0.75** (×**0.5** while heavy); at or below → `PUT_AWAY`, sheathe, no roll | `mBasic.field_0x1C` / `mMove.field_0x80` (`setDoStatusBasic` 2220/2218 → 4318); [roll-attack-threshold.md](../mechanics/roll-attack-threshold.md) |
| roll anim ctrl (rate / start / cut gate / end) | **1.1** / **0.0** / **17.0** / **19.0** → cut dispatchable on roll steps **15..17** | `mRoll.field_0x8/0xC/0x10`, `field_0x0`; [roll-cut-thrust-floor.md](../mechanics/roll-cut-thrust-floor.md) |
| body lean decay `LandState.SLANT_DECAY` (`m351C`, `_set_move_slant_angle`) | **0.3499999940395355** per frame (undriven: −191 → 0 in 13 frames) | tilts the draw base and the Co centre; [roll-lean-decay.md](../mechanics/roll-lean-decay.md) |
| roll-EBS (frame-perfect) | full-run roll → hold L+down through roll → release L into ESS-down → **≈ −23.1** | live |
| WAIT idle blend `setMoveAnime(0, f28, f25, WAITS, WALK, 2)` | f28 **1.1** / f25 **0.8** | `mMove.field_0x38`/`0x40` |
| low-life stop `ANM_WAITATOB` (rate / start / ctrl end / morf) | **0.6** / **0.0** / **12** / **6.0** | `mMove.field_0x68`/`0x6C`/`0x10`/`0x70`; end overrides the clip's own frameMax 13 |
| settled low-life idle `setMoveAnime(0, 0.4, 0.8, WAITB, WALK, 2)` | WAITB rate **0.4** (frameMax 19) | `mMove.field_0x3C`; follows WAITATOB |
| `checkRestHPAnime` life threshold | `getLife() <= ` **6** (quarter-hearts) | `mMove.field_0xE`; see [wait-stop-pose.md](../model/wait-stop-pose.md) |
| sidehop `procSideStep_init` | `nspeed = cM_scos(6200)·30`, `speed.y = cM_ssin(6200)·30`, gravity **−2.4** | `mSideStep` `d_a_player_HIO_data.inc:223` |
| backflip `procBackJump_init` | `nspeed = 22.5`, `speed.y = 19.0`, gravity **−3.0** | `mBackJump` `:102` |
| default gravity (grounded speed.y at CrrPos) | **−2.5**/fr | `mAutoJump.field_0xC`, reset by `commonProcInit` (5826) |
| wall cylinders (ground state) | heights **30.1 / 89.9 / 125.0**, radius **35** | `setBgCheckParam` 10680 ([wall-response.md](../mechanics/wall-response.md)) |
| wall-hit speed slow (head-on ×0.4) | target `×(1 − cos(diff)·`**0.6**`)`, `\|diff\| < 0x4000` | `mBasic.field_0x14` (setNormalSpeedF 2311) |
| roll bonk window | head-on ≤ **5000**, anim frame **[6, 15]**, speedF ≥ **10** | `mRoll.0x4/0x34/0x38/0x3C` (procFrontRoll 6869) |
| roll crash (bonk fired) | `nspeed = speedF·`**0.4** reversed, `speed.y = `**7.0**; ROLLFMIS start 6 → end 24, rate **0.7** at landing, early-exit frame > **20** | `mRoll.0x40/0x44/0x28/0x2/0x24/0x30` |
| sidle (A-at-wall) window | wall-hit + facing ray `25+r` hits `\|n_y\|≤0.05` wall + facing ≤ **0x2000** off head-on → SIDLE, no roll | `setFrontWallType` 4552 |

| proc | `link_state` |
|------|-----|
| WAIT · FREE_WAIT · MOVE · ATN_MOVE | 4 · 5 · 6 · 7 |
| WAIT_TURN · MOVE_TURN · SLIP | 0x17/23 · 0x18/24 · 0x19/25 |
| FRONT_ROLL(+CRASH) · SIDE_STEP(+LAND) · BACK_JUMP(+LAND) | 30/**31** · 0x0A/0x0B · 0x22/0x23 |

<a id="land-turn-procs"></a>
## Land turn procs (SLIP / MOVE_TURN / WAIT_TURN)

The big-reversal ground-turn constants. Decomp `mSlip`/`mTurn`/`mMove`; see
[ground-turns.md](../mechanics/ground-turns.md).

| Constant | Value | Meaning |
|----------|-------|---------|
| slip speed threshold `mSlip.field_0x4` | `speedF/mMaxNormalSpeed > 0.6` → SLIP (else MOVE_TURN) | on a moving reversal (+ genuine stick flip) |
| slip entry `mSlip.0x8` | `nspeed = speedF·1.1` (uncapped) | |
| slip decel `mSlip.0x18/0x10/0x14` | cLib scale 0.6 / max 1.25 / min 0.1875 (~−1.25/fr) | |
| WaitTurn facing pivot `mTurn.0x4/0x0/0x2` | `cLib_addCalcAngleS(scale 30, max 0x3CDF, min 0x1F40)` → ~0x1F40 (≈8000)/frame | |
| MoveTurn facing sweep `cLib_addCalcAngleS(scale,max,min)` | 1-path 2 / (F0·4+0x4A56) / (F0·2) · slip-exit 3 / (F0·2) / F0 | F0 = `mMove.field_0x0` = 3000 |

<a id="link-head-look"></a>
## Link head-look

`setNeckAngle`'s `m3564` twist (`d_a_player_main.cpp:8938-9169`); mechanic [link-head-look.md](../mechanics/link-head-look.md).

| Constant | Value | Meaning (source) |
|----------|-------|------------------|
| head-centre / eye local offsets | (11.25, 0, 0) / (11.25, 18.75, 0) | `l_head_center_offset` / `l_eye_offset` (`d_a_player_main_data.inc:20`) |
| look-pos cone | **±0x6000** of `m34DE` | `checkAttentionPosAngle` / :9014 |
| chase `cLib_addCalcAngleS(scale,max,min)` | **3 / 0x1000 / 0x100** | :9157 |
| pitch clamp | **[−10000, 8000]** | :9093 |
| yaw clamp | **±14336** | HIO `mShip.m.field_0x0` (`d_a_player_HIO_data.inc:297`) |
| yaw-freeze proximity | `absXZ(target − head centre) < `**30** | :9090 |
| head-top offset | (40, 0, 0) | `head_offset` :11589 (`mHeadTopPos` :11592) |

## Camera (steering) - summary (full table migrates with the camera topic)

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Camera-rate smoothing `k` | **0.5** | `omega_t = omega_{t-1} + (cmd − omega_{t-1})·0.5` | live ([camera](../mechanics/camera.md)) |
| Camera-rate saturation | **±3.0° / frame** (±546/−547 hw) | full C-stick X deflection | live |
| substickX dead zone | up to ~149 (Δ ≤ 21) | no camera rotation below this | live |
