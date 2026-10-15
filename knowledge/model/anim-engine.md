# The J3D animation engine - skeleton, keyframes, foot FK

**Answers:** How is Link's skeleton laid out (Maya, 42 joints)? What's the BMD/BCK → pose pipeline?
How does Hermite keyframe interpolation work? How is the foot chain posed (euler→quat→blend)? What is
the two-anim blend / `getRatio` / oldframe-morf? Why is the foot FK run in **world space**? What is
`jointCB1`? How does the foot toe become `speedF`? Where are the live oracles?
**Status:** validated - leg chain jnt0..jnt33 bit-exact vs live `anmMtx`; straight full-deflection
walk `pos_z` float-perfect AND `speedF` bit-exact through the entry transient (live `walk_run`
bit-exact). The two entry-transient residuals were root-caused + fixed 2026-07-04 (both f64-vs-f32
constant leaks, NOT the suspected Hermite/foot-IK frontier): the oldframe-morf counter was f64 (→
jnt0.z entry-morf now bit-exact) and the `f31_2` smoothing used f64 `0.3`/`0.7` (→ speedF frames 5/6
now bit-exact) - see [history/resolved-bugs](../history/resolved-bugs.md#walk-entry-transient--two-f64-vs-f32-constant-bugs-not-a-hermitefoot-ik-frontier).
The full-speed **slip** skid + reversed-walk arc is now `pos_z` bit-exact too - it was NOT a FK
residual but a missing `speedF < 0.05 -> 0` snap (`posMoveFromFootPos`, d_a_player_main.cpp:2418);
see [land-sim](land-sim.md#speedf-snaps-to-0-below-005-the-slip-skid-tail). The **deep-release
`speedF` f37/f39** and **brake_right** are now bit-exact too - also NOT a foot-FK residual: the sim
leaked a spurious on-axis `pos_x` (a cos-table sine reconstruction instead of `JMASSin`), and the
foot FK quantizes at world magnitude so that tiny px flipped the plant-toe X 1 ULP (see
[history/resolved-bugs](../history/resolved-bugs.md#deep-release-speedf-f37f39--brake_right--a-spurious-pos_x-sine-leak-not-a-foot-fk-x-residual)).
The **partial-magnitude (`Y171`)** walk is now bit-exact too - a THIRD "sub-ULP Hermite frontier" that
was really an f64-constant leak: the `daPy_HIO_move_c0` frame-rate fields (1.1/0.8/…) were f64 literals
fed to `fp.fmuls` (see [history/resolved-bugs](../history/resolved-bugs.md#y171-partial-magnitude-speedf--f64-hio-frame-rate-constants-not-a-jnt0-hermite-frontier)).
`ebs` and `waitturn` are now bit-exact too - a FIFTH "sub-ULP toe frontier" that was really a matrix-op
gap: `m37B4` (the worldBase inverse) must be the retail **PSMTXInverse** (cofactor + `fres` reciprocal),
not a transpose, or the foot toe drifts ≤127 ULP at non-axis facings (see
[history/resolved-bugs](../history/resolved-bugs.md#ebs--waitturn--worldbase-inverse-was-rt-not-psmtxinverse-foot-toe-at-non-axis-facings)).
Every land tech is now 0 ULP vs live.
**Source:** `tww_sim/core/anim/{j3d_eval,fk,foot_fk,quat,foot_speedf,anim_state}.py`; decomp
(`J3DAnimation.cpp`, `J3DJoint.cpp`, `m_Do_ext.cpp`, `d_a_player_main`) + live foot-toe oracle.
This engine is **core** (generic, FP-faithful); only [land](land-sim.md) consumes it today, but it is
not land-specific. FP rules it relies on: [fp-faithfulness](fp-faithfulness.md).

---

Land `speedF` (and thus position) is driven by the **planted-foot toe displacement** - a value the
game reads out of the fully-posed skeleton, not a closed-form curve. Reproducing it float-perfect
required porting the J3D animation runtime the way Nintendo's code runs it, op for op. (A dumped
integer-frame table + lerp is *not* bit-exact: the WALK/DASH toe track is Hermite-interpolated, with
real curvature inside one integer frame interval.)

## Skeleton (Maya, 42 joints)

Parsed from `Link.arc` → `cl.bdl`: **INF1** hierarchy + **JNT1** bind (`harness/anim/parse_bmd.py` →
`_generated/anim/link_skeleton.json`; anim data is copyrighted - regenerate locally, never commit).
- **42 joints**; matrix-calc type = **Maya** (`INF1 flags & 0xF == 2`). JNT1 stride is the standard
  **0x40** (the decomp `J3DJointInitData` 0x30 comment is misannotated).
- **Foot FK chain:** root(0) → center(1) → waist_chn(29) → waist(30) → {L,R}clotch(31/36) →
  legA(32/37) → legB(33/38) → foot(34/39); toe joints 35/40. No animated scale in the foot chain
  (scaleCompensate on 30/33/38 is inert - parent scale stays 1). BMD joint order == the `getAnmMtx`
  index; joint enum values aren't in the decomp headers, so identify WAIST/LFOOT/RFOOT by name from
  JNT1.

## Keyframe evaluation (BCK / ANK1, Hermite)

Body anims are `.bck` (ANK1 chunk) in `LkAnm.arc` (`harness/anim/parse_bck.py`). walk/dash: 42
joints, **frameMax = 32**, decShift = 1. Per joint, three TRS tracks each with keyframes
(stride 3 `time,val,tan` or 4 `time,val,tanIn,tanOut`).
- `j3d_eval.calc_transform` evaluates one joint's TRS at frame *f*: **scale/translate** via
  `JMAHermiteInterpolation` (f32, `JMath.cpp:82`); **rotation** via `hermite_s16` - an exact
  instruction port of the `J3DAnimation.cpp:342` inline asm (s16 loaded via `psq_l` `GQR5=S16`,
  scale0 = pure `(float)s16`), the authoritative form (not the C comment), then `(s32)v << mDecShift`.
- Keyframe lookup = bisect + endpoint clamp (`J3DGetKeyFrameInterpolation`). Results are cached per
  anm dict keyed **on the dict contents, not `id()`** (id reuse after GC corrupted `roll_settle`).

## Posing the foot chain (euler → quat → blend → matrix)

**Key discovery:** the CL lower body (`PART_UNDER`, the foot chain) is posed by
`mDoExt_MtxCalcAnmBlendTblOld::calc` (`m_Do_ext.cpp:1164`), **not** direct `J3DMtxCalcMaya`. So each
foot-chain joint matrix is built as:

1. euler s16 (half-angle s16/2) → quaternion - `JMAEulerToQuat` (**non-fused**, see
   [fp-faithfulness](fp-faithfulness.md#fma-fusion-vs-non-fusion-the-load-bearing-distinction)),
   `quat.euler_to_quat`. The half-angle is taken on the **signed** s16 - halving a raw u16 picks the
   negated (bit-different) table entry, see
   [euler-quat-signed-half](euler-quat-signed-half.md).
2. optional **two-anim blend** - `JMAQuatLerp` (`quat.quat_lerp`: dot in f32, lerp in f64→f32,
   **no renormalize**), plus the non-fused translate/scale blend.
3. quaternion → matrix - `mDoMtx_quat = PSMTXQuat` (fused-then-scaled off-diagonals; `fres`+Newton
   reciprocal - [fp-faithfulness](fp-faithfulness.md#psmtxquat-reciprocal-and-the-fres-table)),
   `quat.psmtx_quat`; then `setJ3DData` writes the translate column (scale = 1, no-op).

The euler `J3DGetTranslateRotateMtx` path is WRONG here - it differs ~1.5e-3/joint (half-angle table
lookups), compounding ~0.16 over the chain.

### Two-anim blend & morf

Steady cruise is **pure DASH anim in both slots** (`getRatio(1) = 1.0`) - an earlier "walk.bck → slot
1" model was wrong and gave ~20-unit Z error. The arc is FREEB → WAITS → WALK → **DASH** → WALK →
WAITS; only the accel/decel transients (≈11 frames) actually blend two changing anims (that's why
they need the anim state machine - slot management + ratio ramp + frame-ctrl rates - while cruise
needs none: `speedF = 17` there). A transient walk-start also applies an **oldframe-morf**
(`mDoExt_MtxCalcOldFrame`, non-fused). The morf **counter** (`mOldFrameMorfCounter`) and the `i_morf`
trigger value (2.4) are **f32** - quantize the constant to f32 *before* the `-=1.0`, or the rate
lands 1 ULP low and the entry-morf jnt0.z is +5 ULP (see [history](../history/resolved-bugs.md#walk-entry-transient--two-f64-vs-f32-constant-bugs-not-a-hermitefoot-ik-frontier)).

### Sword-drawn dash is DASHS, not DASH

`setBlendMoveAnime` names the DASH slot `ANM_DASH`, but the resource it resolves to depends on the
equipped item: `getAnmData` (`d_a_player_main.cpp`) indexes `mSwordAnmIndexTable` when the sword is
equipped, mapping `ANM_DASH → dRes_INDEX_LKANM_BCK_DASHS_e` (the sword-drawn dash). `dashs.bck` has
**different leg-joint rotations** than the sheathed `dash.bck` (jnt 34/36/37/38/39), so the posed
foot toe (and hence `posMoveFromFootPos`'s `f31_2`) differs. The same table also maps
`ANM_WALK → WALKS` (`d_a_player_main_data.inc:698`; waits unchanged): `walks.bck`'s legs are
near-identical to `walk`'s but not byte-equal, so the sim poses the sword variants for BOTH slots
whenever the sword is out: `UnderAnimState(sword=True)` selects `dashs` (regimes 2 and 3) and
`walks` (regimes 1 and 2), threaded from `LandState.sword_drawn` through `FootSpeedF`.

This was invisible for months because a pure DASH cruise has `m3598 = 0`, so the toe term drops out
of `speedF` (= `nspeed`) and the wrong dash pose never moved position - the from-rest on-axis suite
only ever validated the WALK toe (regimes 1/2, `m3598 > 0`). It surfaces only on a partial-magnitude
(`m3598 > 0`) frame off a sword-drawn dash cruise, where the wrong toe threw `speedF` off ~0.08u.
Regression: `tests/dolphin/spotcheck_swordwalk.py` (game's loaded `dashs` data == the json, the
`dashs` foot toe == live stored `rtoe` 0-ULP, and the sword-state selection).

The native `_anmc` engine can't select `dashs` (its 15-anim array is hardcoded to `C_DASH`), so
`FootSpeedF` forces the pure-Python foot path whenever `sword=True` - correctness over the native
speedup, until the engine learns DASHS.

#### Mid-walk draw: the anim-set switch is instantaneous (no morf)

The set is not fixed for a run - a **mid-walk sword pull-out** flips it base→sword partway through a
walk (the roll-stab ROLL path from a sheathed anchor draws, rebuilds to cap, then A-presses). The
swap is an **instantaneous, phase-preserved pose jump** with NO oldframe-morf: `getAnmData` reselects
the sword table the instant `mEquipItem` flips to `daPyItem_SWORD_e` at the equip-anime completion
(`d_a_player_main.cpp:3976`), `setMoveAnime` re-fetches it every frame (12734), and `procMove`'s
steady `setBlendMoveAnime(-1.0f)` (6229) passes `i_morf < 0` - so no morf fires; `setMoveAnime`
preserves the phase `f31 = frame/frameMax` (12732) and WALK/WALKS + DASH/DASHS share `frameMax`, so
the frame value is literally unchanged, only the leg keyframes swap. Model: `FootSpeedF.draw_sword()`
flips `_walk`/`_dash`; `LandState(model_draw=True)` auto-triggers it `DRAW_DELAY` acted-frames after a
B rising edge while walking sheathed. **`f_draw` = 5 frames after the raw B feed** (= 3 after the
`INPUT_DELAY`-acted swordTrigger edge), live-pinned on `land_flatwalk` for the on-back take. Because
the from-rest walk is 0-ULP with the switch but drifts both ways without it (never-draw stays DASH and
misses the post-draw partial-mag frames; always-drawn poses DASHS on the pre-draw accel frame), the
switch TIMING is load-bearing for where the roll `old` lands. Regression:
`tests/test_draw_switch.py` (live fixture `fixtures/walk_draw.json`, capture
`harness/rollstab/capture_draw.py`).

## Foot FK runs in WORLD space

`posMoveFromFootPos` computes the stored toe `spB0 = m37B4 · anmMtx(FOOT) · l_toe_pos`, where
`anmMtx(FOOT)` is the **world-space** joint matrix (translations ≈ Link's world pos, `z ≈ 764`).
Although `m37B4 = PSMTXInverse(worldBase)` cancels `worldBase` *algebraically*, it does **not** in
f32: the FK accumulates each joint matrix at world magnitude, so each is quantized to ≈6e-5 (f32
spacing at 763); `m37B4` removes the base afterward but the rounding is already baked in. FK from
identity (local scale ≈ tens → ≈1e-6 quantization) misses this - the source of the old 1–2 ULP.

**Fix (shipped):** build `worldBase` offline - `fk.world_base = transS(pos.x, 0, pos.z) · Yrot(shape_angle.y)`
(base.y is 0 live; only the Y column, irrelevant to the XZ that `f31_2` uses) - and its inverse `m37B4`
via `fk.psmtx_inverse` (the retail **PSMTXInverse**: cofactor/determinant with an `fres`+1-Newton
reciprocal, **not** a transpose - they diverge at non-axis facings because `worldBase`'s `R` from the
sin/cos tables isn't exactly orthonormal; this is what made `waitturn`/`ebs` bit-exact). Run the chain
from `cur = worldBase`, then apply `m37B4` (`FootFK` world mode).
`LandState.step` feeds `pos.x/pos.z/facing` each frame via `FootSpeedF.set_pos` - the FK quantizes
the toe at world magnitude, so the driver **must** get the live position each frame, and **which**
position (and lean) is itself a law: the game draws AFTER `posMove`, upright on a proc-init frame -
see [draw-base](draw-base.md).

## `jointCB1` foot rebuild (not IK)

`daPy_lk_c::jointCB1` (a J3D node callback) rewrites the leg/foot `anmMtx` after the anim calc:
`anmMtx(LFOOT) = concat(anmMtx(LLEGB), Trans(oldTrans)·Quat(oldQuat)·ZrotM(field_0x002))`, using the
**old-frame** stored pose (`m_Do_ext.cpp:1219`) and per-foot leg-angle Zrots from
`footBgCheck`/`setLegAngle`. **On flat ground every leg-angle Zrot is 0** (verified live), so
`jointCB1` reduces to a pure rebuild that is bit-exact to the FK given the (now-exact) quats - 
verified `concat(live_anm33, Trans·Quat[oldQuat34]) == live anm34`, 0 ULP. So there is **no foot-IK
snap on flat ground** (the earlier "ground-snap on the planted foot" guess was wrong).

## Toe → `speedF`

The planted foot is the lower-Y of the two; `f31_2 = absXZ(toe_delta_smoothed)` where the smoothing is
`f·0.3f + 0.7f·m359C_prev` - **non-fused**, and `0.3f`/`0.7f` are **f32 literals** (multiplying by
Python's f64 `0.3`/`0.7` rounds each product 1 ULP off → speedF −1 ULP through the entry). (`absXZ` =
the faithful `sqrtf(fmadds(...))`, see
[fp-faithfulness](fp-faithfulness.md#fma-fusion-vs-non-fusion-the-load-bearing-distinction)). `f31_2`
is the plant-foot XZ delta and the only anim-derived input to land `speedF`; how it composes into
`speedF` and position is [land-sim](land-sim.md).

### The FK is only as exact as the world position fed to it

The foot FK runs from `worldBase(pos)`, so a wrong `pos` quantizes the toe wrong even when every
matrix op is bit-exact. The deep-release `speedF` f37/f39 (and `brake_right`) looked like a
"1-ULP-low toe **X** in the local chain," but a full per-joint `anmMtx` decomposition showed the FK
rotation is 0 ULP everywhere and the toe residual **cancels internally** - the fault was a spurious
on-axis `pos_x` (the sim reconstructed `cM_ssin` from the cos table instead of `JMASSin`), and the
world-magnitude quantization flipped the toe X 1 ULP. Fixed; see
[history/resolved-bugs](../history/resolved-bugs.md#deep-release-speedf-f37f39--brake_right--a-spurious-pos_x-sine-leak-not-a-foot-fk-x-residual).
Diagnostic rule: when a world-space-FK toe residual cancels between `m37B4` and `anmMtx`, suspect the
**position fed to the FK**, not the chain. `test_speedf_matches_live_bit_exact` is LandState-driven
(the raw `FootSpeedF` driver reads hundreds of ULP off in the release region - a harness artifact).

## Live oracles (for re-validation)

- `mBaseTransformMtx` = `mpCLModel@obj+0x32C → +0x24`; `m37B4` = `obj+0x37B4`.
- per-joint `anmMtx(j)` = `obj+0x32C → mpNodeMtx@+0x8C → [j]` (48-byte `Mtx`; `LFOOT = 0x22`,
  `RFOOT = 0x27`). Align by `anim_frame` (`sim(N) == live(N)`).
- stored `spB0` toe: `mFootData[i].field_0x018` (foot0/R `+0x3CF8`, foot1/L `+0x3E10` from base
  `0x803AD860`) - **lags one frame** (`sim toe(N) == live field_0x018(N+1)`).
- `oldQuat` array: `m_old_fdata@obj+0x31B4 → +0x20` (`Quaternion[jnt]`); `mOldFrameTransInfo`:
  `→+0x1C` (`J3DTransformInfo[jnt]`, translate at `+0x14`).
- frame controllers: `mFrameCtrlUnder[2]@class 0x302C` (dash `mFrame` ptr `0x2F64`, walk `0x2F78`);
  ratio(1) `0x2EE4`; loaded res idx `0x2F04`/`0x2F14`.

## See also

- [FP faithfulness](fp-faithfulness.md) · [Land sim](land-sim.md) ·
  [Land movement](../mechanics/land-movement.md) · [Animation / head-bob (swim)](../mechanics/animation.md).
- [Draw base](draw-base.md) (where/when the pose is taken) · [Equipped anim set](equipped-anim-set.md)
  (which anims get posed) · [WAIT stop pose](wait-stop-pose.md) (what gets posed while stopped, and
  why the re-walk's first step depends on it).
