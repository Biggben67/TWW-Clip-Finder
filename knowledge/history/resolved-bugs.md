# History — resolved bugs & their provenance

> **status: historical** — how these were found and fixed. The current truth is in the linked
> mechanics/model pages. Kept because the *reasons* (and the wrong turns) matter for future debugging.

---

## bug#2 — dense-pump live divergence = pipe artifact, NOT physics

Dense back-to-back pump plans reached only ~127k live vs the sim's ~300k. Root cause: the external
`advanceseq` pipe's FrameAdvance listener **jitters SI polls** on dense neutral↔ESS transitions
(off-thread input misses the emu-thread poll). A cleanly **authored** DTM (8 ControllerState rows per
30 fps game-frame, 254/1 calibration) played via the movie system is **bit-exact** (cruise_pump300k:
net 300,816). A DTM *recorded* from the pipe inherits the jitter — only an independently authored DTM
is unbiased. **Dense plans are valid.** → [reference/commands](../reference/commands.md#live-validation--dtm-the-faithful-delivery-path), [model/planner](../model/planner.md).

> The `run_tests.py` **pump-transition** DTM baseline (formerly labelled "bug2 neu-pump") is a
> LOCKED clean-DTM sync, bit-exact. A one-session "sim over-bleeds pump exits" scare was a
> **seed mismatch** (the sim seeded with the slot-10 slate's mRate 0.5472 while validated against
> the anchor's cold start, real mRate 0.5); seeded correctly the sim is bit-exact. The mRate rule
> and the [554 cold-start seeding](../model/swim-sim.md#cold-start-seeding-the-mrate-rule) stand. Lesson
> in [tests/dolphin/README](../../tests/dolphin/README.md#locked-tests-are-immutable-hard-rule).

## bug3 — partial-hold gain dropped at a hold→charge boundary

A **partial** on-axis hold (e.g. `(128,77)`) interleaved in a charge burst was mispredicted: live
`25×chg + 4×(128,77) + 10×chg` gave **v=−92.0** but the sim gave **−93.83** (dv ≈ 1.83); the
`(128,110)` ESS control was bit-exact. Per-frame DTM ground truth localized it to the first `chg`
*after* the holds: live applied the 4th hold's `setSpeedAndAngleSwim` gain (lagged one frame, +2),
but the sim took its `is_chg` branch and applied `ess_decay` (+1/6) instead — **dropping the last
hold's gain** (error 2 − 1/6 = 1.833). Root cause: `step()` applied the ESS gain *same-frame* but
the charge gain *lagged*, carrying only one preempted transient (`_post_burst_transient`); at a
hold→charge boundary the steady holds had self-applied, so nothing was pending and the charge
overwrote the slot. **Fix:** defer the swim gain ONE frame UNIFORMLY for ESS and charge (the
discipline `ArrowState` already used). Validated bit-exact via clean DTM (110 **and** 77);
`run_tests.py bug3 partial hold` is now a baseline. Repro: `harness/dtm/partial_hold_dtm.py`. →
[model/sim](../model/swim-sim.md#charge-frame-model-four-1-frame-lags), [mechanics/decay-curve](../mechanics/decay-curve.md).

## walk entry-transient — two f64-vs-f32 constant bugs (NOT a Hermite/foot-IK frontier)

The straight-walk `speedF`/`pos_z` was float-perfect at cruise but the **entry transient** stayed
RED for several sessions: jnt0.z ~5 ULP off at MOVE frame 3, `speedF` −1 ULP at frames 5/6. The
04x hypothesis was "a `calc_transform`/Hermite sub-ULP in the root jnt0.z track" + "a planted-foot
jnt34/39 sub-ULP (likely a foot-IK ground snap)." **Both were wrong.** Live decomposition
(reload-anchor + `advanceseq` prefix-replay, reading `oldTransInfo`/`m359C` via the
[anim-engine oracles](../model/anim-engine.md#live-oracles-for-re-validation)) proved:

1. **oldframe-morf counter was f64.** At MOVE frame 3 the anim frames are *exactly* 0.0/0.0 and the
   ratio is bit-exact, so the per-anim jnt0.z and the ratio-blend are trivially exact — the divergence
   was entirely in the morf blend, and a single-input sweep pinned it to `oldFrameRate` being 1 ULP
   low. `MorfState.init_morf` stored `self.counter = float(i_morf)` — Python's **f64** `2.4`
   (=2.39999999…), but `mOldFrameMorfCounter` and the `i_morf` param are **f32** in the game
   (`m_Do_ext.cpp:1227`), so the constant is `f32(2.4)`=2.40000009… *before* the `-=1.0`. The f64
   value rounds `counter` (then `f10`, then the rate) 1 ULP low. **Fix:** `i_morf = fp.f32(i_morf)`
   on entry → jnt0.z entry-morf bit-exact.
2. **`f31_2` smoothing used f64 `0.3`/`0.7`.** With jnt0.z fixed the toe stream is fully bit-exact
   (both feet, x+z, aligned by the 1-frame lag `sim toe(N)==live spB0(N+1)`), so the remaining
   `speedF` −1 ULP at frames 5/6 was pure `posMoveFromFootPos` arithmetic. It traced to the recursive
   smoothing `f31_2 = f31_2*0.3f + 0.7f*m359C` (`d_a_player_main.cpp:2400`): `0.3f`/`0.7f` are **f32
   literals**, but the sim multiplied by Python's f64 `0.3`/`0.7` (=0.2999999…/0.6999999…), rounding
   each product 1 ULP off. The expression is **non-fused** (fused forms miss). **Fix:** f32 constants
   `_F0_3`/`_F0_7` → `m359C` bit-exact frames 3–7, live `walk_run` bit-exact.

**Lesson:** an entry-transient "sub-ULP FK frontier" was really two garden-variety **f64 constant
leaks** — a Python literal fed to an `fp` op is f64; the game's constant is whatever its field/param
type says (usually f32). Quantize constants to f32 at the site that mirrors an f32 store/param.
`fp.fmuls`/`fadds` do **not** quantize their operands, so the caller must. Also: the raw-`FootSpeedF`
driver in `test_speedf_matches_live_bit_exact` is a **harness artifact** in the release region
(frames 33–36 read hundreds of ULP off while LandState is bit-exact) — same class as the Y171 raw
driver; trust LandState-driven values.
→ [model/anim-engine](../model/anim-engine.md), [model/land-sim](../model/land-sim.md).

## deep-release speedF f37/f39 + brake_right — a spurious `pos_x` sine leak (NOT a foot-FK-X residual)

The straight-walk release tail was `speedF`-bit-exact except frames 37/39 (±1 ULP), and `brake_right`
was 2 ULP in `pos_z`. The 04x hypothesis (recorded on the anim-engine truth page, now migrated here)
was a **"1-ULP-low toe X in the local foot-FK chain (quat→matrix / blend / concat), the same
FK-chain frontier as Y171/ATN"** — reached by a live `spB0` decomposition that saw the drawn right-foot
toe **X** 1 ULP low at frames 34/35/38. **That attribution was wrong.** A full live per-joint `anmMtx`
decomposition (capture the right chain 0→1→29→30→36→37→38→39 over the release; compare `m37B4·anmMtx(39)·l_toe`
to the stored toe) proved:

1. **The foot FK is bit-exact.** Every joint's `anmMtx` **rotation** row matches live to 0 ULP, and the
   toe-multiply (`PSMTXMultVec`) reproduces the stored toe from the live matrices at 0 ULP. The only
   divergence was the world-space **X-translate**, and it **cancelled internally** (sim `m37B4` and
   sim `anmMtx` differ from live by the *same* world-X term → the self-consistent toe was clean except
   ≤1 ULP on 3 frames).
2. **The real cause: the sim leaked a spurious `pos_x`.** Live `pos_x ≡ 0` (m37B4[0][3] = −0.0) on the
   on-axis walk; the sim drifted `pos_x → ~9e-5`. The foot FK quantizes at **world magnitude**, so even
   a ~9e-5 lateral offset shifts the X grid and flips the plant-toe X 1 ULP on some frames → `speedF`
   f37/f39. It also fed the `brake_right`/`ebs` position tails.
3. **Why px leaked: `cM_ssin` reconstructed from the cos table.** `LandState` integrated
   `speed.x = speedF·_cM_ssin_s16(travel)` with `_cM_ssin_s16(a) = cM_scos_s16((a−0x4000)&0xFFFF)`.
   But the game's `cM_ssin(a) = JMASSin(a)` (`c_math.h:38`) — the **console SIN table** directly. Sin is
   NOT a −0x4000 view of cos: `cos[0xC000] = 1.75e-7 ≠ sin[0] = 0` (and 816/4096 entries differ 1 ULP,
   the same table asymmetry the [sin-table fix](../model/fp-faithfulness.md#console-cosine-and-sine-tables)
   found for `JMAEulerToQuat`). So `_cM_ssin_s16(0)` returned `1.75e-7` instead of `0`, leaking
   `speed.x ≈ 17·1.75e-7 ≈ 3e-6/frame`. **Fix:** route `_cM_ssin_s16` through `mathlib.cM_ssin_s16`
   (the baked sin table). Offline land 180→182 pass; live gate 10→11 (`brake_right` + the deep-release
   `speedf` now bit-exact); no regression.

**Lesson (again):** a claimed "sub-ULP foot-FK-X frontier" was a **wrong-table** input leak one layer
up. When a toe residual "cancels internally" in the world-space FK, the fault is the *world position
fed to the FK*, not the chain. And any sine on an s16 angle must use the **sin** table — never a
cos-table offset. Still open after this fix (genuine world-magnitude frontier, all position-neutral to
gameplay): `Y171` speedF/pos_z (px now clean → the toe.z Z-quantization + the partial-mag smoothing
regime), and `ebs`/`waitturn` (turn transients, ≤1 ULP).
→ [model/anim-engine](../model/anim-engine.md), [model/land-sim](../model/land-sim.md).

## `Y171` partial-magnitude speedF — f64 HIO frame-rate constants (NOT a jnt0 Hermite frontier)

The partial-magnitude (`Y171`, `msd`≈0.52) walk was `speedF`-RED at f17 (≤3 ULP) and `pos_z`-RED at f27
(1 ULP). The prior hypothesis (recorded on the land-sim truth page, now overturned) was a **"jnt0
root-translate sub-ULP that grows through the WAITS↔WALK blend"** — a per-joint `anmMtx` decomposition
had shown the foot rotation 0 ULP everywhere but the model-space jnt0 X-translate drifting, so the
residual was attributed to a `calc_transform`/Hermite sub-ULP in the root translate track. **That
attribution was wrong** — it was the third "sub-ULP FK/Hermite frontier" in a row that turned out to be
a plain **f64-constant leak** (after the [entry-morf](#walk-entry-transient--two-f64-vs-f32-constant-bugs-not-a-hermitefoot-ik-frontier)
and [pos_x sine-leak](#deep-release-speedf-f37f39--brake_right--a-spurious-pos_x-sine-leak-not-a-foot-fk-x-residual) cases).

Root cause: the `daPy_HIO_move_c0` frame-rate constants (`field_0x38` = 1.1, `field_0x40` = 0.8, and the
side/back `atnMove`/`atnMoveB` fields) are **f32 members** in the game, but the sim held them as Python
**f64 literals** and fed them straight into `fp.fmuls`/`fadds`/`fdivs` — which do NOT quantize their
operands. `setMoveAnime`'s new-MOVE0 rate `f27r = f28 + f27*(f25*f3/f26 - f28)` (with `f28`=1.1,
`f25`=0.8) then rounded 1 ULP off, drifting the frame-ctrl phase → the WAITS↔WALK blend toe → `speedF`.
The full-deflection walk never sees these (it cruises in regime 3, `field_0x48`=2.3 with `f3==f26`, so the
rate collapses to an exactly-reproduced value), which is why only the partial regime was red. **Fix:**
`fp.f32(...)` every `daPy_HIO_move_c0`/`atnMove`/`atnMoveB` constant at definition (a no-op for the
exactly-representable 0.5/1.0/17.0/1.25; corrects 1.1/0.8/2.3/0.9/1.8/0.95/…). `walk_y171` went 0 ULP
offline (both `speedf`/`pos_z` tests) **and** live (per-frame bit-exact).

**Lesson (a third time):** before decomposing an FK chain for a "sub-ULP Hermite/translate frontier",
sweep the regime's constants for f64 literals fed to `fp` ops. A regime-specific residual that the
bit-exact neighbouring regime never triggers points at a **constant only that regime uses**, not the
shared FK. → [model/land-sim](../model/land-sim.md), [model/anim-engine](../model/anim-engine.md),
[model/fp-faithfulness](../model/fp-faithfulness.md).

## `ebs` + `waitturn` — worldBase inverse was R^T, not PSMTXInverse (foot toe at non-axis facings)

The last two red land cases were `waitturn` (walk re-entry `speedF` **−192 ULP** at the first post-pivot
MOVE frame) and `ebs` (backward-walk `speedF` 1–3 ULP), both leaving a 1-ULP `pos_z`. The prior
land-sim truth page (now overturned) filed them as an accept-as-is **"foot-FK toe-stream frontier / world-
magnitude quantization"** — a genuine sub-ULP FK residual to live with. **Wrong again** — same class as
the [Y171](#y171-partial-magnitude-speedf--f64-hio-frame-rate-constants-not-a-jnt0-hermite-frontier) /
[entry-morf](#walk-entry-transient--two-f64-vs-f32-constant-bugs-not-a-hermitefoot-ik-frontier) /
[pos_x sine-leak](#deep-release-speedf-f37f39--brake_right--a-spurious-pos_x-sine-leak-not-a-foot-fk-x-residual)
cases: a **wrong input one layer up**, not the FK.

Localized with `harness/anim/perframe_compare.py` + a live `mFootData` toe capture (adapt `foot_probe.py`;
align by the 1-frame lag `sim pose(N) == live mFootData(N+1)`): the sim's model-local foot toe was
**bit-exact at axis-aligned facings** (0, `0x8000`) but off by **≤127 ULP at the WaitTurn pivot's
intermediate facings** (`0xE0C0`, `0xC180`, …). `waitturn`'s f9 `f31_2 = |ATNWRS(f8) − ROT(f7)|` reads the
f7 ROT toe posed at facing `0x8300` → the −192 ULP `speedF`.

Root cause: the foot FK runs in **world space** from `worldBase` and de-bases the toe with
`m37B4 = mDoMtx_stack_c::inverse()` = **PSMTXInverse** (`dolphin/mtx/mtx.c:404`, retail paired-single) — a
general **cofactor/determinant** inverse whose reciprocal is `fres` (12-bit estimate) + **one Newton
refine** (`recip = 2·est − det·est²`), *not* an `fdivs`. The sim used an analytic **transpose** (`R^T`).
`worldBase`'s `R` is built from the `JMASin/JMACos` tables, so it is **not exactly orthonormal**
(`c²+s² ≠ 1.0` in f32 at a non-axis BAM) → `PSMTXInverse ≠ R^T` there. Only when `R`'s entries are `0/±1`
(axis facings) do the two coincide — exactly the frames that were already bit-exact. **Fix:** port
PSMTXInverse into `fk.psmtx_inverse` (cofactors fused `ps_msub`, det via first-column cofactor expansion,
`fres`+1-Newton reciprocal reusing `quat._fres`, translation `−R⁻¹·T` fused) and use it for `m37B4`.
`waitturn` and `ebs` both went **0 ULP live** (14/14 land techs green; 186/0 offline). One fix closed
both because `ebs`'s brakeslide decouples facing to ~90° (also non-axis).

**Lesson (a fifth time):** a "sub-ULP FK toe frontier" that appears *only at non-axis facings* and is
bit-exact at axis-aligned ones is a **matrix-op fidelity gap** (inverse/rotate algorithm), not the FK
chain. Match the retail **PSMTX*** paired-single algorithm (cofactor+`fres`, not transpose/`fdivs`) for
any matrix built from the not-exactly-orthonormal sin/cos tables. → [model/land-sim](../model/land-sim.md),
[model/anim-engine](../model/anim-engine.md), [model/fp-faithfulness](../model/fp-faithfulness.md).

## 554 / "anim drifts ~3 fr by f400" — truncated-seed artifact

A phantom ~3-frame anim drift by f400 was a **truncated cold-start seed** (anim 8.9417 vs true
8.941699028…); the cold-start [×598 scramble](../mechanics/pumps.md#the-x598-scramble) amplified the
sub-ULP error ~600×. With the full-precision seed the sim is bit-exact per-frame. Fix: never seed a
truncated anim. → [model/sim](../model/swim-sim.md#cold-start-seeding-the-mrate-rule).

## Off-axis charge v residual — corrupt stick-angle table (input path)

A 0.0105 too-high v on off-axis charge was traced (after a wrong "camera-field mismatch" hypothesis)
to `stick_angle_table.csv` being dumped via the **calibrated `set_gc_buttons`** path while the
game/tests/DTM use the **raw-byte `advancewith`** path — differing up to ±155 s16 on ~12k off-axis
cells. Regenerating via `advancewith` → v bit-exact. This fixed the x/y/`value` (magnitude) alignment;
a separate **read-latency** corruption in the `angle` and `stick_dist` columns survived it and was
found+fixed later (next entry). → [model/predictors](../model/predictors.md#stick-angle-table-corruption-resolved).

## Stick-angle table — read-latency corruption in angle + stick_dist (gold re-dump)

The `advancewith`-regenerated table still carried a 1-frame **read-latency** artifact: the set/read
dump pipeline (`tww-python-scripts/stick_angle_grid_dump.py`) read `mMainStickAngle` / `mStickDistance`
one frame before the game had updated them. ~2609 `angle` cells and the **entire** `stick_dist` column
were lagged (`stick_dist` shifted ~2 rows), worst at exact-diagonal cells: (160,160) read 24260 vs the
correct 24576, (160,112) 15162 vs 15771. The sim reads the `angle` column to drive facing, so this was
a **real** sim-vs-live facing desync (3.35° at (160,112), confirmed via a clean-DTM negative-v true-
superswim test; corrected cell → 0.00°). `test_complicated` missed it — its inputs (sx 98–157,
sy∈{0,255}) never reach the sx≥160 / diagonal region.

Fixed by a settle-and-verify gold re-dump (`harness/capture/stick_grid_redump.py` +
`run_parallel_dump.py`): hold each stick through a multi-frame settle, verify stability across two
consecutive settled frames (0 unstable / 65536), per-frame air/speed/pos re-lock. New table: `angle`
bit-consistent with `atan2f(x,−y)` for all 65536 cells, exact-diagonals on the 45° grid, and
`stick_dist == value == mMainStickValue == /54` (so `test_partial_magnitude.py` now LOCKS the grid ==
closed-form magnitude, inverted from the old "is-not-the-gain"). Integrity locked offline by
`tests/test_stick_table_integrity.py`. A pure decomp port (`mAngle = 10430.379·atan2f(x,−y)`,
`mStickDistance = min(hypot/54,1)`) reproduces the angle at non-boundary cells but diverges from live
Dolphin at 17.6 % of cells (deadzone-boundary/octagon byte-mapping), so the live capture — not a
closed form — is authoritative. → [model/predictors](../model/predictors.md#stick-angle-table-corruption-resolved).

## Omega camera grid — input-path corruption + coarse subsample

The camera-rate grid had the same input-path bug (`set_gc_buttons` recorded −546 where `advancewith`
gives −547; 1816/4096 cells off by +1), and the shipped grid had been a **coarse 4096-cell
subsample** (csx 0..15 only), so `camera_arbitrary` raised KeyError off-grid for csy ≠ 128.
Regenerated first as the raw-byte grid (`omega_full_redump.py`), then **completed to the full
csx 0..255 × csy 0..255 = 65536 grid** (2026-07-01) — no more off-grid gaps; charge cases go cam=0hw.
Dump method history and the fast in-place redump are in
[camera-model-history](camera-model-history.md#omega-grid-completed). → [mechanics/camera](../mechanics/camera.md).

## Console cosine table — 1-ULP exits

x86 `cos()` differs from the console `jmaCosTable` at 2964/4096 entries; ×598-amplified, a 1 ULP
became a 0.07 v jump at pump exits. Fixed by baking the live table from `0x80498168`. →
[model/sim](../model/fp-faithfulness.md#console-cosine-and-sine-tables).

## release_ess_speed — 2-increment phase error

The exit speed was computed off the wrong (last-ESS) anim frame; the game applies `af_drag` at the
release frame (exit-frame physics + 1-frame lag), up to ~40% off when the offset lands a mid-cos
frame. Fixed by advancing the exit-frame physics before `af_drag`. →
[mechanics/neutral](../mechanics/neutral.md#ess--neutral-exit-release_ess_speed).

## `wiggle_ebs_roll` DTM-playback flake - movie single-step slips edges (delivery, not physics)

The land suite's one recurring FAIL (13/14, "the roll never fires", s66) was the DELIVERY layer:
single-stepping a PLAYING movie (per-frame `advance` on the `.dtm.sav` fixture) can slip the movie's
1-frame A edge, while a BULK `advance frames=N` from a clean load delivers the same movie faithfully
(probed 2026-07-20: end == the locked state-4 stop). The fixture also resumed MID-recording, so its
savestate carried in-flight attention state no clean-rest sim can seed. Resolution: the chain's exact
consumed inputs were read back per logic frame from `g_mDoCPd_cpadInfo[0]` (buttons/trigL/decoded
sticks, inverted to bytes through the sim's own `clamp_stick`), and the case now runs as a clean-rest
PIPE case, bit-exact per frame - the DTM-playback path is retired. Corollary re-measured on the way:
the pipe mis-injects near-full OFF-AXIS sticks by +-1 raw byte ((112,215) arrived as x 111: game
clamp (-1,71) vs decomp/sim (0,71)), so pipe seqs should use dead-zone-axis byte pairs like the
movie's own (130,247). -> the offline gate `tests/test_land_goldens.py`;
[mechanics/brakeslide-ebs](../mechanics/brakeslide-ebs.md#wiggle-ebs--lup-cancel--chained-roll).
