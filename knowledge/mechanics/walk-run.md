# Land walk / run: the two angles + speedF composition

**Answers:** How does on-ground walking accelerate? What are the two movement angles (facing vs
travel)? Is there a walk-before-run speed plateau? How does position (`speedF`) relate to
`mNormalSpeed` - what's the foot-plant blend?
**Status:** validated live (2026-07-04) - `mNormalSpeed`, facing (`shape_angle.y`), travel
(`current.angle.y`), and the walk `speedF`/position are all **bit-exact** vs live (`tww_sim.land`,
via the ported J3D anim engine). Anchor `land_flatwalk@twwgz.sav`.
**Source:** live captures (`harness/capture/land_capture.py`); decomp `d_a_player_main.cpp`
`setSpeedAndAngleNormal` / `setNormalSpeedF` / `posMoveFromFootPos` / `mDoExt_MtxCalcAnmBlendTblOld`.

---

## Two movement angles (the core of land, unlike swim)

Land separates **two** headings that swim kept fused:
- **travel** = `current.angle.y` (velocity direction), read as `travel_angle`.
- **facing** = `shape_angle.y` (visual body direction), read as `shape_angle_y`.

`potential_speed` is **signed** relative to facing (negative = moving opposite to facing). World
motion = |speed| along (facing + 180° if speed<0). All ground tech lives in how these three
(facing, travel, speed-sign) diverge. The stick's world target is `target_angle = m34DC(stick) +
csangle` - camera-relative, so `csangle` is a first-class input, not a constant (swim could pin it).
Fields logged via `dolphin_mem` named reads `travel_angle` / `shape_angle_y` / `target_angle` /
`csangle` / `potential_speed` (see [addresses](../reference/addresses.md#land-player-fields)).

## Walk / run acceleration (baseline)

From idle (state 5/4), full stick accelerates straight to the run cap **`mMaxNormalSpeed` = 17**
units/frame via `setNormalSpeedF` - **no walk-before-run plateau** (an apparent ~16-frame 5.0 plateau
in an early capture was a phantom **front roll**, state 30, from a stray button - not a mechanic).
- **2-frame input latency** on both press AND release (the game acts on the stick delivered 2 frames
  earlier - one constant reproduces both edges; `tww_sim.land.INPUT_DELAY`).
- **Accel = +3.5/frame** exactly (`dVar9 = cM_scos(0)·field_0x14·msd²`), injected straight into
  `mNormalSpeed` by `setNormalSpeedF`, clamped to the cap.
- **Decel on release = `cLib_addCalc(mNormalSpeed, 0, 0.6, 2.5, 1.8)`**:
  `17→14.5→12→9.5→7→4.5→2→0.2→0` - a constant `−2.5/frame` while far from 0, then the cLib min-step
  snap tail. Clean stop (state 4).
- proc = `daPyProc_MOVE_e` (state **6**). On flat, wall-free ground, collision (`mAcch` wall/slope) is
  inert, so `mNormalSpeed` is pure 1-D physics - **transcribed bit-exact** in `tww_sim.land`.

Constants: [reference/constants.md#land-movement](../reference/constants.md#land-movement).

## Position ≠ `mNormalSpeed` - the speedF composition

The pos integrates **`speedF`** (true_speed), a **blend** of the potential speed and the foot-plant
delta. Known **bit-exact** (verified 0-ULP across an accel+cruise+decel arc, `land_walk_anim.csv`):

```
speedF = f32( mNormalSpeed·(1 − m3598)  +  f31_2·m3598 )
```
- **`m3598`** = the WALK↔DASH **blend factor** (`blend_move`, pointer-off `0x34C0`). On the flat
  on-axis walk it is a **closed form in the (already bit-exact) `mNormalSpeed`**, no animation state
  needed: `m3598 = clamp( f32(2·(1 − mNormalSpeed/17)), 0, 1 )` - bit-exact (op order matters: divide
  by 17 first, subtract from 1, ×2; the reversed order misses by 1 ULP). ⇒ `m3598 = 0` at cruise
  (`mNormalSpeed = 17`), ramps to 1 as speed falls below ½·max. Validated for the **on-axis partial
  magnitude** walk too (the `Y171` regime rides `m3598 == 1.0`, 0 ULP live - see
  [model/land-sim.md#partial-magnitude-regime-y171-msd052](../model/land-sim.md#partial-magnitude-regime-y171-msd052));
  **off-axis** (diagonal sticks) is decoded correctly too: the raw stick runs through the PADClamp
  octagonal clamp (ported from decomp `Padclamp.c ClampStick` in `core.mathlib.main_stick_decode`
  + native `_anmc`), so the near-full off-axis want-angle matches clean-DTM live. The advancewith-
  captured `stick_angle_table.csv` is NOT used: its off-axis cells carry a ~160 s16 injection
  artifact (see [history/resolved-bugs.md](../history/resolved-bugs.md)).
- **`f31_2`** = the **planted foot's XZ displacement** this frame (`foot_delta_prev` / `m359C`,
  pointer-off `0x34C4`) - the genuinely animation-driven term (`posMoveFromFootPos` reads the WALK/DASH
  foot-joint matrices; plant = the foot with lower Y). A per-frame *delta* of a joint world position,
  reproduced by the **ported J3D animation runtime** (`tww_sim.core.anim`), not a table.

**The foot-plant subsystem is BUILT and bit-exact** (`tww_sim.core.anim`, FMA-faithful via an f64
intermediate, `tww_sim.core.fp`). The chain, all offline: `UnderAnimState` (the
`setBlendMoveAnime`/`setMoveAnime`/`J3DFrameCtrl` state machine → which anims fill MOVE0/MOVE1, their
frame-ctrl frames, the blend ratio, and `m3598`, driven by the bit-exact `mNormalSpeed`) → `FootFK`
(reduced foot-chain forward kinematics: BCK Hermite keyframe eval → euler→quat → `QuatLerp` blend →
`PSMTXQuat`/`Concat`/`MultVec`, plus the walk-entry **oldframe-morf**) → `posMoveFromFootPos` (plant
select, the 1-frame-delayed toe delta `f31_2`, the recursive smoothing gate, and the `speedF`
composition). `tww_sim.core.anim.foot_speedf.FootSpeedF` is the whole thing; `LandState` drives it each
frame → **`speedF` matches live to ~1e-5 across accel/cruise/decel including the standing→walk entry
and the stop; final `pos_z` bit-exact (d=0.0000)**.
- The steady-walk pose is the **DASH** anim (cruise = both slots DASH, ratio 1); the arc is
  FREEB(idle)→WAITS→WALK→DASH→WALK→WAITS. The standing→walk **entry** frame's `f31_2` is the FREEB idle
  drift `absXZ(FK(FREEB@f+2) − FK(FREEB@f+1))`, so the engine advances the standing idle through the
  input-latency frames to get it exact.
- **Cruise needs none of it** - since `m3598 = 0` at `mNormalSpeed = 17`, `speedF = mNormalSpeed`
  exactly; `f31_2` only bends position during the ~11 transient frames (accel + release decel).
- **Copyright:** the anim keyframe DATA (Link.arc/LkAnm.arc) is gitignored under `_generated/anim/`
  and dev-supplied from the user's own ISO - **not shipped**. When absent, `LandState` falls back to a
  calibrated `cLib` chase (endpoint ±3) so the package still runs; the offline golden tests SKIP.

## See also

- [Land movement overview](land-movement.md) - index of all land techs.
- [Brakeslide / EBS](brakeslide-ebs.md) · [Roll](roll.md) · [Ground turns](ground-turns.md) ·
  [Precise stop](precise-stop.md).
- [model/land-sim](../model/land-sim.md) (position precision) · [model/anim-engine](../model/anim-engine.md)
  (foot FK → `speedF`) · [model/fp-faithfulness](../model/fp-faithfulness.md).
- [ESS](ess.md) - the `(128,110)`-class stick position land reuses.
