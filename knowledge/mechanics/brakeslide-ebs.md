# Brakeslide & extended brakeslide (EBS)

**Answers:** What is a brakeslide / extended brakeslide (EBS)? Why does holding ESS left/right
preserve speed "almost forever"? Is preservation governed by facing or travel? What is the wiggle
EBS and the L+Up cancel into a chained roll?
**Status:** validated live (2026-07-04) - the whole ATN_MOVE tier (brakeslide / EBS-release /
facing-decouple / brake) is **bit-exact** incl. position (`tww_sim.land`). The wiggle-EBS→chained-roll
combo is SIMULATED bit-exact per frame too (2026-07-20): the `wiggle_ebs_roll` pipe case from clean
rest, locked live + by the offline recorded golden (`tests/test_land_goldens.py`).
**Source:** decomp `d_a_player_main.cpp` `setSpeedAndAngleAtn` / `setSpeedAndAngleAtnBack` /
`setBlendAtnMoveAnime` (the `mDirection` machine) / `checkNextMode` (MOVE↔ATN_MOVE); live captures.

---

Brakeslide/EBS run the **`daPyProc_ATN_MOVE_e` (state 7)** targeting-move tier and its foot anims.
The walk/run baseline they brake out of is [walk-run.md](walk-run.md); constants live in
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

## Brakeslide (L held)

From a run, **press L (target) + full-down for 1 frame, keep L held, then hold ESS-down** `(128,110)`:
- proc → **`ATN_MOVE` (state 7)** (`procAtnMove` → `setSpeedAndAngleAtn`).
- **facing LOCKS**: on the L-engage frame `m34E6 = shape_angle.y` is captured (2067) and every ATN
  frame writes `shape_angle.y = m34E6` back - the run heading is frozen.
- travel flips to 180°: `getDirectionFromCurrentAngle()==DIR_BACKWARD` reflects `current.angle.y` by
  `0x8000` and negates `mNormalSpeed` (2863) - the backward slide is a **negative speed on a flipped
  heading**, world motion still forward.
- steady state runs **`setSpeedAndAngleAtnBack`** (`mDirection==DIR_BACKWARD`, cap → **15**). The
  ~−0.14/frame bleed is *not* a decay term: it's the accel-inject branch of `setNormalSpeedF` adding
  `f1 = 2.5·mStickDistance·cos(Δtravel) ≈ +0.139` to the negative speed each frame, walking it toward
  0 (`msd = 0.0556` at the ESS magnitude).
- **Simulated bit-exact incl. position**: the steady backslide poses `ANM_ATNDB` single with
  **`m3598 = 0`**, so `speedF == mNormalSpeed` - pure momentum (see *ATN position* below).

## Extended brakeslide (EBS) - release L

Same start, but **release L after the 1 full-down frame**, then hold ESS:
- proc drops out of targeting to **`MOVE` (state 6)** (`checkNextMode` `r24` false → `procMove_init`);
  facing unlocks and tracks travel via the normal facing-chase.
- momentum bleeds **~13× slower (~−0.011/frame)** than the brakeslide - the "extended" part. Ordinary
  `setSpeedAndAngleNormal` on a nearly-reversed heading (cap back to **17**): the `cM_scos(target−
  travel)` speed scale is ~1 while travel slowly chases the backward target, so `mNormalSpeed` barely moves.
- **Simulated bit-exact** (reuses the walk proc; the negative-speed entry carries from the 1 ATN frame).

## Camera-relative speed preservation (the EBS payoff)

Once in the EBS, the **held ESS direction relative to `csangle`** decides everything:
- **ESS steering facing TOWARD `csangle`** → decay collapses to **~−0.001/frame** - speed held *almost
  forever* (minutes).
- **ESS steering facing toward `csangle + 180°`** (straight away from camera) → the **normal −2.5/frame
  brake** engages → full stop in ~7 frames (state 4).

Which of left/right preserves vs brakes depends on the camera angle (with `csangle`=0: **left preserves,
right brakes**). The brakeslide brakes precisely *because* its facing points anti-camera.

**Facing, not travel, is the predictor.** In the decoupling test both directions hold near-identical
travel (~172°), yet the one whose *facing* rotates toward camera preserves and the one whose facing
stays anti-camera brakes - same travel, opposite outcome. **Mechanism:** once L is released the frame
runs `setSpeedAndAngleNormal`, whose target-speed scale is `cM_scos(m34E8 − current.angle.y)` - the
cosine of *stick-target vs travel*. Steering the ESS toward camera keeps that angle small (cos≈1,
speed held); steering anti-camera pushes it past `0x7800`, taking the reversal branch (`dVar9 = 0`) so
speed decays at the normal −2.5/frame brake to a full stop (state 4).

## Facing/travel decoupling (how to turn facing independently)

Timing matters: **ESS-down for exactly ONE frame, then ESS-left/right the very next frame (held)**
makes **facing rotate to the ESS direction (~90°) and lock there while travel stays at the slide
heading (~171°)** - a sustained ~80° facing≠travel split, speed preserved. (Holding ESS-down 3+ frames
first instead keeps facing glued to travel.)

## ATN position (the strafe/backslide foot anims) - BIT-EXACT

The ATN_MOVE tier's **position** is bit-exact too (`setBlendAtnMoveAnime`, `d_a_player_main.cpp:3280`,
in `tww_sim/core/anim/anim_state.py`; foot posed each ATN frame by `foot_speedf.step_atn`). Each ATN
frame the `mDirection` machine picks the foot anim from **`f31 = |mNormalSpeed·cos(m34E2)| /
mMaxNormalSpeed`** (on flat ground `m34E2 = 0`, so `f31 = |nspeed|/max`):
- **side** (`DIR_LEFT/RIGHT`): blends `ANM_ATN{L,R}S` → `ANM_ATNW{L,R}S` → `ANM_ATND{L,R}S` with `f31`.
  At slide speeds `f31 ≥ 0.9` ⇒ the single `ANM_ATND{L,R}S` pose, **`m3598 = 0`**.
- **backward** (`DIR_BACKWARD`, `setBlendAtnBackMoveAnime`): `ANM_WAITS` → `ANM_ATNWB` → `ANM_ATNDB`.
  The brakeslide runs the single `ANM_ATNDB` at `f31 ≥ 1.0`, **`m3598 = 0`**.
- **forward** (`DIR_FORWARD`): reuses the plain walk `setBlendMoveAnime` (cap back to 17).

Because `m3598 = 0` at slide speed, `speedF == mNormalSpeed` - the ATN slide is **pure momentum**. What
matters for position is that the ATN pose still **warms the toe stream**: on an **EBS release** (L
dropped → `MOVE` next frame, `procMove_init` re-morf `mBasic.field_0xC` = 2.4), the first walk frame's
foot-plant delta `f31_2` spans the last ATN pose → the walk pose, so the strafe anim must be posed
exactly for the walk-off to be bit-exact (same warm-the-stream mechanism as the roll and WAIT_TURN
tails). Locked by `run_land_tests` `brakeslide`/`ebs`/`face_left`/`brake_right` (pos_z bit-exact) +
offline `test_atn_*` position asserts. mDirection is validated live (player+0x34B8).

## Wiggle EBS + L+Up cancel → chained roll

The **wiggle EBS is just the alternating-[ESS](ess.md) component of an EBS** - not a separate
technique. During an EBS you *alternate* the held ESS between two positions (a "wiggle") so **facing
oscillates around forward** while travel stays pinned backward; this both holds the speed at the
camera-relative minimum AND keeps the body pointed roughly forward (so the next move gives forward
speed). Combined with an L+Up cancel it carries a roll's speed through a reversal into a *second* roll - 
the highest speed-preservation land tech found so far. Full chain: **roll (26) → frame-perfect
roll-EBS (−23) → wiggle EBS → L+Up cancel → second roll (24.088) → stop**. First observed in a
recorded DTM; the chain's exact consumed inputs were read back per logic frame from
`g_mDoCPd_cpadInfo[0]` and now run as the `run_land_tests` `wiggle_ebs_roll` **pipe case from clean
rest** (2026-07-20).

- **Wiggle (the alternating ESS):** alternate the ESS between two positions (observed `target_angle`
  cycling ~`270° → 270° → 135°`, msd ≈ 0.06) so **facing oscillates right around forward** (≈ 328–360°/
  0–2°) while travel stays backward (~185°). Holds the −23 speed at only **≈ −0.002/frame** - the
  camera-relative preservation (`cM_scos(target − travel) ≈ 1`), but wiggled so the *body* points
  forward instead of drifting. **The C-stick is also nudged to shift the camera** (`csangle`) into the
  angle that yields the desired EBS - `target = m34DC(stick) + csangle`, so camera is a live input.
- **L+Up cancel:** tapping L + forward (Up) snaps `target` to forward, the ATN backward-flip converts
  the backward slide, and it lands in MOVE at **+16** forward (speedF ~15.7).
- **Second roll:** rolling off that preserved speedF → `15.725·1.5 + 0.5 =` **24.088** - a second
  near-cap roll out of what began as a braking slide.

SIMULATED bit-exact per frame (2026-07-20): from clean rest with the camera held (C-stick down) the
whole chain needs no camera model, and the sim matches the live recording 0-ULP on every frame
(state / mNormalSpeed / facing / travel / pos_x / pos_z), roll speeds 26 and 24.087, wiggle plateau
−23.227. Locked live (`run_land_tests` `wiggle_ebs_roll`) and offline
(`tests/test_land_goldens.py`, golden `fixtures/land_goldens/wiggle_ebs_roll_golden.json` incl. the
chain-signature guard). The roll-EBS entry (−23) is documented in
[roll.md](roll.md#frame-perfect-ebs-out-of-a-roll-23).

## See also

- [Land movement overview](land-movement.md) · [walk-run](walk-run.md) · [roll](roll.md) ·
  [ground-turns](ground-turns.md).
- [ESS](ess.md) - the `(128,110)`-class stick position (land reuses the swim ESS coordinate).
- [Camera](camera.md) - `csangle`, here a live per-frame movement input.
