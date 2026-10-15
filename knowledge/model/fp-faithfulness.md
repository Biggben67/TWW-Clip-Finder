# Floating-point faithfulness — reproducing Gekko (GameCube) FP bit-exactly

**Answers:** Why does the sim run everything in f32/ctypes? Why does op *order* matter? What is
`_F32_PI` / why is `M_PI` single-precision in cos args? Why does `cM_rad2s` truncate? Why bake the
console cosine/sine tables? Which matrix/quaternion ops are FMA-**fused** and which are **non-fused**?
What is the `PSMTXQuat` `fres`+Newton reciprocal and the `_FRES` table?
**Status:** validated bit-exact against live console (RAM disasm of TWW JP + per-op live oracles).
**Source:** `tww_sim/core/fp.py` (+ `_fpc.pyx` Cython), `tww_sim/core/mathlib.py`,
`tww_sim/core/anim/{quat,fk,foot_speedf}.py`; decomp + live calibration. History:
[history/resolved-bugs](../history/resolved-bugs.md).

---

This is the **engine-wide** floating-point contract every component (swim, land, and the coming
[collision](#forward-note-collision) work) sits on. The GameCube CPU (Gekko/PowerPC 750) is
single-precision with a fused multiply-add; to be bit-exact the sim must reproduce both the width
and the fusion of every op the game executes. The rules below are each pinned to a decomp site and a
live oracle.

## Everything runs in f32 (and op *order* matters)

The sim uses `f32(...)` (`ctypes.c_float`, or the Cython `_fpc` fast path — bit-identical) for every
arithmetic step. f64 is *more* precise than the hardware and drifts the wrong way: ~0.013 anim /
0.004 v over ~480 swim frames (enough to land the wrong [exit phase](../mechanics/neutral.md)), and
~2.5 ULP over a ~115-frame land walk.

`fmuls`/`fadds`/`fsubs`/`fdivs` (PowerPC opcode 59) are single: compute in f64, round once to f32 —
modeled as `f32(a*b)` etc. `fmul`/`fadd` (opcode 63) are true f64. **Op order is part of the
contract:** `af_drag` and `release_ess_speed` use *different* f32 orderings (two different decomp
expressions); sharing one ordering left a ~2 ULP error that the
[x598 scramble](../mechanics/pumps.md#the-x598-scramble) amplified into a 0.07 speed jump at pump
exits.

**A constant that mirrors a game f32 field/param must be `f32`-quantized at the site** — `fp.fmuls`/
`fadds`/`fsubs`/`fdivs` do NOT quantize their *operands*, only the result, so a Python f64 literal like
`1.1`/`0.8`/`0.3`/`2.4` fed to one of them multiplies at f64 and rounds the product 1 ULP off. This
exact leak has masqueraded as a "sub-ULP FK/Hermite frontier" **three times** — the entry-morf f64
counter, the `f31_2` f64 `0.3`/`0.7` smoothing, and the [`Y171` f64 HIO frame-rate constants](../history/resolved-bugs.md#y171-partial-magnitude-speedf--f64-hio-frame-rate-constants-not-a-jnt0-hermite-frontier)
(`daPy_HIO_move_c0` 1.1/0.8). Before decomposing an FK chain for a residual, sweep the regime's
constants for un-quantized f64 literals; a residual that a bit-exact neighbouring regime never triggers
points at a constant only that regime uses.

## `M_PI` in a cos/sin arg is SINGLE precision (`_F32_PI`)

The compiler emits `f32_expr * M_PI` as `lfs f, M_PI; fmuls` — a **float** constant load + a
single-precision multiply, not a double multiply. So the argument is `f32(f32(pi) * x)` with
`f32(pi) = 3.1415927410125732` (~1 ULP above double π). Use `mathlib._F32_PI`, never `math.pi`, in
any argument fed to a console `cM_fcos`/`cM_scos`. Verified sites: the neutral-release cos
(`procSwimWait_init`) and the head-bob cos (`posMoveFromFootPos`). This 1-ULP-of-π difference flips a
truncated cos-table cell at knife-edge angles — it **was** the pump-300k desync (dip 43 cell 2003 vs
live 2004, x598-amplified). Order within the arg matters too: the console computes `getFrame/getEnd`
first (`fdivs`) *then* `*pi` (`fmuls`), i.e. `f32(f32(anim/23) * f32(pi))`, not `(pi*anim)/23`.

Pure geometry (world x/z bearings; facing via the s16 `cM_scos_s16`, which takes no π) and
display/heuristic metrics do **not** need `_F32_PI` — only args that reach a console `cM_fcos`.

## `cM_rad2s` truncates (round-toward-zero)

`cM_rad2s = (s16)(fmod(rad, 2π_f64) * 10430.3779296875)` with **truncation** (`fctiwz`, opcode
`0xfc00001e`), not round-to-nearest. The `fmod` and scale multiply are f64; the s16 result then
indexes `JMASCos = cosTable[(u16)v >> 4]` (low 4 bits dropped → 4096-entry table).

## Console cosine and sine tables

`cM_scos` indexes the **real console cosine table** dumped live from `jmaCosTable @ 0x80498168`, not
`math.cos`: a PowerPC-libm-built table differs from an x86 recompute at **2964/4096 entries** (max
4.17e−7). x598-amplified, that 1 ULP was a 0.07 speed jump at pump exits. It is 4096 entries indexed
by the s16 angle with the low 4 bits truncated (`index >> 4`, no interpolation).

`JMAEulerToQuat` uses `JMASSin`/`JMASCos` off a **separate** console `jmaSinTable`
(`jmaCosTable = jmaSinTable + 1024`, `jmaSinShift = 4`, size 4096) — **not** a −1024 view of the
cosine table; the old wrap-around reconstruction was 1 ULP off at 816/4096 entries.

**`cM_ssin` is `JMASSin`, not a cos offset.** `cM_ssin(a) = JMASSin(a)` / `cM_scos(a) = JMASCos(a)`
(`c_math.h:38`) — so any sine on an s16 angle must index the **sin** table (`mathlib.cM_ssin_s16`),
never `cM_scos((a−0x4000)&0xFFFF)`. They are not interchangeable: `cos[0xC000] = 1.75e-7` but
`sin[0] = 0`. Reconstructing sine from cos leaked a spurious `speed.x ≈ speedF·1.75e-7 ≈ 3e-6/frame`
on the on-axis land walk (`travel==0` → should be exactly 0), drifting `pos_x` to ~9e-5; because the
foot FK quantizes at world magnitude, that nonzero px flipped the plant-toe X 1 ULP (deep-release
`speedF` f37/f39 + `brake_right`). See
[history/resolved-bugs](../history/resolved-bugs.md#deep-release-speedf-f37f39--brake_right--a-spurious-pos_x-sine-leak-not-a-foot-fk-x-residual). Both baked tables
(`core/tables/cos_table.bin`, `sin_table.bin`; `mathlib._COS_TABLE`/`_SIN_TABLE`) were re-verified
against the live console (`jmaSinTable` ptr @ `0x803EAE28`): **0 mismatches** across all 4096 sin AND
cos entries. The tables are not a source of any remaining residual.

Related: `J3DFrameCtrl::update` is replicated as a **repeated f32 subtraction loop** (not a single
modulo) so post-x598 the anim loops down with the console's exact rounding.

## FMA fusion vs. non-fusion (the load-bearing distinction)

A single-precision fused multiply-add computes `a·b ± c·d` with **one** rounding; a non-fused
sequence rounds each product first. Whether a given expression fuses depends on how the game's code
was compiled — and it varies op by op. Getting this wrong is a 1-ULP error that pos/anim accumulation
can amplify. `core/fp.py` provides the faithful primitives (`fmadds`/`fmsubs`/`fnmsubs`/`fnmadds` +
the plain `fmuls`/`fadds`/`fsubs`/`fdivs`); a single FMA via one f64 intermediate is provably the
correctly-rounded single FMA (2·24+2 = 50 ≤ 53 mantissa bits).

**Fused** (verified op-for-op against the paired-single asm):
- **`PSMTXConcat`** — `ab[i][j] = fmadds(a_i2, b_2j, fmadds(a_i1, b_1j, fmuls(a_i0, b_0j)))`, `+a_i3`
  on the translate column via `fmadds(1, a_i3, accum) == fadds`.
- **`PSMTXMultVec`** — `dst = (m0·sx + m2·sz) + (m1·sy + m3)`, two `fmadds` partials joined by
  `ps_sum0`/`fadds`.
- **`PSMTXInverse`** (`fk.psmtx_inverse`) — a general **cofactor/determinant** inverse (each cofactor
  `fmsubs(a, b, fmuls(c, d))`; det = first-column cofactor expansion), with the reciprocal computed via
  **`fres` estimate + one Newton refine** (`recip = 2·est − det·est²`), **not** an `fdivs`. This is NOT a
  transpose: for a rotation built from the sin/cos tables `R` is not exactly orthonormal
  (`c²+s² ≠ 1.0` in f32 at a non-axis BAM), so `PSMTXInverse ≠ Rᵀ` off the axes — the fix that made the
  `waitturn` pivot and `ebs` foot toe bit-exact (see [history/resolved-bugs](../history/resolved-bugs.md#ebs--waitturn--worldbase-inverse-was-rt-not-psmtxinverse-foot-toe-at-non-axis-facings)).
- **`cXyz::absXZ`** — `f31_2 = sqrtf(abs2XZ)` with `abs2XZ = fmadds(dz, dz, fmuls(dx, dx))` (one
  fused round), and `sqrtf` = `frsqrte` seed + 3 Newton refines in double then `f32(x·guess)`.
  Ported as `foot_speedf._absxz` — use this, **not** `math.hypot`.

**Non-fused** (each product separately f32-rounded, then combined):
- **`JMAEulerToQuat`** (`JMath.cpp:41`) — each quaternion component is `(a·b) ± (c·d)` with BOTH
  products separately rounded. Fusing `x`/`y` here put the planted-foot jnt34 quat 1 ULP off.
- **Blend translate/scale** — `mDoExt_MtxCalcAnmBlendTblOld::calc` (`m_Do_ext.cpp:1183`) blends
  `info1.mTranslate·f30 + info2.mTranslate·ratio` (`f30 = 1−ratio`) **without** FMA contraction; a
  fused `fmadds` put blend-frame joint translates 1 ULP off (e.g. jnt31.z). The oldframe-morf blend
  was already non-fused.

## PSMTXQuat reciprocal and the FRES table

`mDoMtx_quat` is retail **`PSMTXQuat`** (paired single), NOT `C_MTXQuat`: the off-diagonals are
**fused then scaled** — `m[0][1] = (x·y − z·w)·s` via `ps_msub`. The scale `s = 2/denom`
(`denom = w²+x²+y²+z²`) is computed with the console's **`fres` reciprocal estimate + a Newton
refine**, exactly as the asm (`quat._recip2_of`, `scale_mode='newton'`, the default). The `_fres`
emulation must match Dolphin's `fres_expected` table byte-for-byte: `_FRES_BASE` (32-entry base/dec
table; `interp = base − (dec·frac + 1) >> 1`) had **8 wrong high-index entries** (idx 22/24/26–31),
so the seed was ~1 ULP low **for `denom < 1`**.

This only bit the **WALK↔DASH blend** poses: `JMAQuatLerp` does not renormalize, so a lerped quat's
`denom` drops just below 1 → the high table indices; single-anim poses have `denom ≈ 1` → index 0
(always correct), which is why non-blend frames looked fine with the broken table. `'newton'` is the
right mode: at a single-axis joint's half-ULP division midpoint (`denom = 1 − 2⁻²⁴`) the console lands
`fdivs − 1 ULP` (round-to-even); raw `fdivs` is +1 ULP and the plain `_fres` table is −7. With the
corrected table + Newton, the leg chain jnt0..jnt33 is bit-exact vs the live `anmMtx`. See
[anim-engine](anim-engine.md) for how these feed the foot FK.

## Cython fast path

Two optional, **bit-identical** native accelerators; both fall back to pure Python when the compiled
`.pyd` is absent (the `.pyx` source is tracked, the `.pyd`/`.c` are gitignored). Build both with
`_build_native.py` (`python _build_native.py` = both; `… _anmc` = just the anim one).

- **`core/_fpc.pyx`** (`cpdef inline <float>`) — the f32 ops (`fp.py` imports it, else ctypes). ~2.4×
  on the swim planner.
- **`core/anim/_anmc.pyx`** — the **land-walk per-frame pipeline**. The foot-FK / quaternion / Hermite
  chain is ~95% of `LandState.step` (anim data present), and every tiny `fp` op there was a Python call.
  `_anmc` progressively absorbed the whole hot path into C, each step verified 0-ULP vs the golden suite
  + the `perf_land` fingerprint (identical with and without the module):
  - leaf ports (`mtx_concat`/`mtx_mult_vec`, `euler_to_quat`/`quat_lerp`/`psmtx_quat`, `hermite_*`) — 3.4×;
  - a fused per-joint `blend_joint` + `chain_concat` — 5.8×;
  - **`PoseEngine`** (a `cdef class`): the keyframe data, skeleton chains, oldframe-morf counter, per-joint
    old pose, worldBase/`m37B4`, and the toe stream all live in C, so `seed()`/`set_pos()`/`step_feet()`
    collapse to a single native call per frame that does `calc_transform` + the 12-joint blend/morf/
    PSMTXQuat pose + both foot chain FKs + the toe/heel `PSMTXMultVec` + `PSMTXInverse` with zero
    per-frame Python object churn; plus `foot_compose` (the posMoveFromFootPos speedF tail) and the
    `cam_bezier` manualCamera math (`rationalBezierRatio` + substick clamp + s16 azimuth recompute).
  - **Fused walk step:** the whole `anim_state.UnderAnimState` machine (`FrameCtrl.update`,
    `setBlendMoveAnime`/`setMoveAnime` regimes, the ATN side/back blends, `set_single`/`set_wait_idle`) +
    the `FootSpeedF` orchestration (started/stopped/pending-morf/idle-drift/single-entry) + the toe stream
    now live on `PoseEngine` too (`w_step`/`w_step_atn`/`w_step_single`/`w_enter_*`, working in fixed anim
    *codes* mapped to data-indices). One `foot.step(...)` = **one** C call. The anim machine's vestigial
    `i_morf` return (never read downstream) is dropped; the FK oldframe-morf is driven solely by the
    `FootSpeedF` morf value. `foot_speedf.py` delegates to the engine when present, else the intact
    pure-Python `st`/`ff` path (same fingerprint proves the drop-in is bit-identical, not a reimplementation).
  - **`LandCore`** (a `cdef class`): the whole `land.LandState` per-frame physics now runs in C — the
    proc dispatch, the stick decode (`setStickData` + the `mathlib` dead-zone/angle/`deg_to_s16` helpers),
    the `setSpeedAndAngleNormal`/`Atn`/`AtnBack` two-angle chase (`cLib_addCalc`/`cLib_addCalcAngleS`),
    `checkNextMode`, the WAIT_TURN/MOVE_TURN/SLIP/FRONT_ROLL procs, the `manualCamera` s16 chase, and the
    `speedF`→position integration. It owns the physics state and drives the same `PoseEngine` for `speedF`
    (one `w_step*` call/frame); `LandState.step` delegates to it and syncs the output fields back for
    tests/planners. The `mathlib` leaf helpers only paid off once their caller (`land.py`) was in the same
    C translation unit — ported standalone they broke even against the Python↔C call cost.
  - Net: **~88× on `LandState.step`** (668 → 7.6 µs/frame, `tests/benchmark/perf_land.py`). This is the
    native compute floor: `pose_toe` ≈ 6.4 µs + ~1 µs of Python shell (`_sync_from_core`). Going further
    means optimizing the foot-FK/quaternion pose itself, not the physics/stick/camera glue.

  The old blocker ("32-bit-C overflow in `quat._fres` `1<<52`") is fixed by doing the `fres` bit surgery
  in `unsigned long long`. `psmtx_quat`'s non-default scale modes and the identity-FK path stay in Python;
  the C `PoseEngine` is used only on the world-space FK path (whose `quatfn` is PSMTXQuat).

Orthogonal but large: `anim/fk.load()` + `j3d_eval.load_anim()` now **cache** the parsed anim/skeleton
JSON (read-only; the shared `_ct_cache` calc_transform memoize is pure). This cut `LandState.clone()`
from ~7.8 ms to ~0.08 ms (**~97×**) — it had been re-parsing ~300 KB per clone, dominating the A* land
planner and every anim-using test.

## Forward note (collision)

The upcoming seam-clip / collision work is a boolean knife-edge decided by `fmadds`/`frsqrte`
rounding — the same FP contract, one step more sensitive (a single flipped ULP flips the clip). The
fused primitives and `frsqrte` seed above are the on-ramp; `core/fp.py` is the home for the collision
math when it lands.

## See also

- [Anim engine](anim-engine.md) (how the fused/non-fused rules assemble the foot FK) ·
  [Swim sim](swim-sim.md) · [Land sim](land-sim.md) · [Pumps / x598](../mechanics/pumps.md) ·
  [history/resolved-bugs](../history/resolved-bugs.md).
