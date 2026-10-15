# Swim + Camera position predictor — bit-accuracy research log (2026-06-28)

> **status: historical** — research log / provenance, NOT current truth. Current camera law:
> [mechanics/camera.md](../mechanics/camera.md); predictor architecture: [model/predictors.md](../model/predictors.md).
> This page is the full bit-accuracy derivation (GAP 1/GAP 2, ordering, the resolved off-axis residual).

GOAL (user): from slate 10, given a sequence of (main-stick + C-stick) inputs, predict
**bit-exactly** where the CAMERA (csangle) is AND where Link (link_x/z) is, every frame —
INCLUDING while moving. The existing `superswim_sim.py` is bit-exact for v/anim/air/state
under ONE assumption: C-stick held down (camera frozen). We are removing that assumption.

CONSTRAINTS (user):
- Bit accuracy is the bar. "Close" (% error) is only an interim step.
- Do NOT modify `superswim_sim.py` or the planner. New files only (subclass/import read-only).
- SI-polling is DISPROVEN as a factor (see bug#2 fix / [[superswim-bug2-input-delivery]]).
  The 1-frame lags observed are deterministic game update-ORDER, not poll timing.
- Sub-agents OK for context relief (esp. read-only decomp analysis).

## >>> RESOLVED (2026-06-28) — COMPLICATED INPUT (ARBITRARY MAIN + C-STICK) IS BIT-EXACT <<<
The predictor now handles ARBITRARY per-frame main-stick directions AND arbitrary C-stick
(random csy), not just clean charge + csy=128. `tests/test_complicated.py` PASSES bit-exact
(cam 0 hw, v 0.0, anim 0.0, POS 0.0039 = the f32 floor) on:
  - cap_randcharge (random-dir charge to ~-140 + FULLY-random camera csx,csy 0..255)
  - cap_camchaos   (clean charge + random csx, csy=128)
  - gen_charge     (NEW random seed 101: random-dir charge + fully-random camera) — generalization
No regression: validate_coldstart (3/3), swim_predict_exact --cruise (6/6), swim_predict_full
on cap_full/cap_full3/cap_full_steady all still **cam 0 hw, v 0.0, anim 0.0, POS 0.0039**.

NEW FILES (all import superswim_sim/planner READ-ONLY; none modify them):
  - `stick_angle.py` + `stick_angle_capture.py` + `stick_angle_table.csv` (GAP 2 angle source)
  - `swim_arbitrary.py` (ArbitrarySwimState — GAP 2 gain)
  - `camera_arbitrary.py` + `omega_capture.py` + `omega_table.csv` (GAP 1 camera)
  - `swim_predict_complicated.py` (unified predictor), `gen_random_seq.py` (generalization seqs)

### GAP 2 — arbitrary-direction speed gain (ArbitrarySwimState, swim_arbitrary.py)
The base SwimState prices the per-frame gain via the discrete ess/neu/chg token (stick_to_action
only knows sx==128); for sx!=128 it mis-routes and v diverges (216 off on cap_randcharge). FIX:
- The decomp prices EVERY deflected swim frame identically (setSpeedAndAngleSwim): gain =
  mStickDistance*3*cM_scos(d_turn), applied with a 1-frame lag. There is NO chg/ess distinction
  in the game. So `action_for` routes EVERY deflected frame as 'chg' (the path with the correct
  1-frame charge-lag + cold-start entry scheduling); neutral -> 'neu'. Verified v=0.0 on the
  charge build (cap_randcharge, gen_charge) AND the clean ESS cruise/steer (cap_full*) — in
  cruise the per-frame gain is small so the 1-frame lag washes out (no regression). The earlier
  snap-cone chg/ess split mis-priced the snap<->non-snap boundary (spurious post-burst transient).
- `_swim_facing` is overridden to use the REAL per-frame stick + the EXACT stick angle.
- EXACT STICK ANGLE: the closed-form atan2+dead-zone-15 (superswim_sim.stick_angle_deg) is only
  good to ~0.86deg (worst 156 s16) because the game applies the GC RADIAL GATE normalization, not
  a per-axis dead-zone. The exact mMainStickAngle is a pure fn of (sx,sy), captured LIVE off a
  guaranteed facing-snap (facing[f+1] = mMainStickAngle(stick[f]) + 0x8000 + csangle[f], read at a
  >135deg snap; near-cardinal sticks that never snap are read via a gradual-chase convergence).
  Cached in stick_angle_table.csv; matches INPUT_DUMP_MAIN.csv with 0 error where present. For an
  ON-AXIS stick (sx==128: ESS / pure charge) the closed form IS exact (verified) -> no capture.
- ORDERING (live-pinned, key finding): the facing/gain m34E8 uses cam[f] (the CURRENT frame's
  csangle), NOT cam[f-1] (cap_randcharge: cam[f-1] is wrong by up to 408 s16). The camera updates
  with a 1-frame INPUT lag (csx[f-1] -> cam[f]), so cam[f] is known before the stick is read. The
  MOVE-direction gradual chase (cur_y -> dx/dz) still consumes cam[f-1] (validated cruise path).

### GAP 1 — camera under ARBITRARY C-stick (CameraArbitrary, camera_arbitrary.py)
camera_exact modeled omega_cmd as a fn of csx ONLY with a csy<=64 'freeze' (return 0); bit-exact
only at csy=128. For random csy it broke (1613 hw). LIVE RE findings:
- The integer recurrence is UNCHANGED and still bit-exact: target += omega_cmd(csx,csy) [1-frame
  lag]; yaw += int((s16)(target-yaw)/2); csangle = (yaw+0x8000)&0xFFFF. (cam_yaw/cam_target read
  live; the chase int(diff/2) verified every frame incl. sign flips.)
- The "auto-FOLLOW" the brief hypothesized was DISPROVEN: with neutral OR frozen C-stick the
  camera does NOT move while Link charges/turns (d_cam_target == 0 over a held-charge sweep). ALL
  camera motion is the C-stick via omega_cmd; there is no facing-follow term.
- omega_cmd is a fn of the WHOLE C-stick VECTOR (csy modulates the horizontal rate): e.g. csx=255
  gives omega 546 for csy in [32,220] but 199 at csy=255 and 173 at csy=0 — the csy<=64 'freeze=0'
  was never real. Captured the exact 2-D omega_cmd(csx,csy) LIVE (hold each C-stick ~11 frames
  from a fresh loadstate so the k=0.5 omega ramp settles; read the steady d(cam_target)). Cached
  in omega_table.csv; verified == the live per-frame omega in cap_randcharge/cap_camchaos (0
  cells differ). Fixes both the 1613-hw arbitrary-csy break AND the old 1-hw csy=128 residual
  (the one wrong cell was omega_cmd(109,128): old table 0, live -1). csy=128 not in the table
  falls back to the original csx-only table -> the 13 clean captures need no re-capture.

### KNOWN BOUNDARY (reported, not curve-fit away)
The charge-build / cruise / steer regimes are bit-exact. Two NEW pure-random generalization
captures probe regimes BEYOND the charge build:
  - gen_fullsx (random sx full-range + 255/0 charge sy): cam 0 hw, anim ~0.02; v worst 0.0325 /
    POS ~9. Residual is a tiny per-frame gain-cos drift on off-axis non-charge frames (~0.002/fr).
  - gen_chaos (pure random sx,sy,csx,csy -> Link swims FORWARD, partial deflections): cam 0 hw,
    but v worst ~80 / POS ~460. This is the v>=0 FORWARD-swim gain (setNormalSpeedF chase) +
    partial-deflection mStickDistance regime — the SAME open gap as run_tests' `bug1 v>=0 tail`
    XFAIL. NOT a charge-build regime; out of scope for this task. The camera is bit-exact (0 hw)
    in BOTH, so GAP 1 fully generalizes; only the forward-swim PHYSICS gain remains.

## >>> RESOLVED (2026-06-28 late) — FULL RUN (COLD-START BUILD → CRUISE → STEER) IS BIT-EXACT <<<
The cold start is now bit-exact. The validated logged-mRate scramble rule + a corrected
direction chase-order make the WHOLE run (build → cruise → steer) predict camera AND position
bit-exactly from inputs alone. **NO slate restoration needed** — the slate was never the problem.

THE COLD-START SCRAMBLE RULE (live-pinned, slot 10, 3 cold-starts, err +0.00000 each):
```
oldframe      = f32( f32(anim_seed + mRate_seed) + neutral_anim_rate(air_seed - 1) )
scramble_anim = f32( f32(oldframe * 26.0) * 23.0 )
```
- Exactly ONE state-54 entry-tax frame on the charge input, then the 54→55 scramble frame.
- advance1 (entry-tax) = the LOGGED `move0_mrate` (= fc_rate @ 0x803AD860 +0x2F60); carries
  pre-seed AIR HISTORY (0.547222 at air-written 900 ⇔ air≈882), NOT recomputable → must be LOGGED.
- advance2 (scramble) = `neutral_anim_rate(air_seed-1)` (air decremented by the entry-tax frame);
  COMPUTABLE, no logging. (Seed air 900→899 → 0.5; verified 700→699 → 1.056 too.)
- Old sim `f32(anim+1.0)` → oldframe 9.9417, scramble 5945.14 vs live 5973.37 (err −28, ×598-amp).

THE DIRECTION CHASE-ORDER FIX (what made the steer/build position bit-exact):
- The MOVE direction uses `facing` (shape_angle.y) DIRECTLY — confirmed live: `move_dxdz(f1_live,
  facing_live[f])` reproduces live dx/dz to f32 noise (worst 0.0075). There is NO separate
  lagging current.angle.y field to capture (scanned the whole player struct; the apparent "lag"
  was the cos-table >>4 quantization in my atan2 back-out, not a real field).
- GRADUAL chase (cruise/steady/reversal steer) applies THIS frame BEFORE the move (no lag).
  A DIR_BACKWARD SNAP (the per-frame 180° charge flip) DEFERS to next frame (the 1-frame facing-
  snap lag the base SwimState models with _pending_facing). Getting this ORDER right is the whole
  game: moving with the pre-chase heading lagged the steer dz by ~0.05/frame (→0.7 POS); the
  180°-snap-immediately flipped the build oscillation 180° out of phase (→33 POS).

VALIDATION (all NEW files, superswim_sim/planner/run_tests untouched):
- `validate_coldstart.py` — 3 run_tests baselines via logged-mRate cold start: cold-3k / 4-pump /
  8-pump all **dv=+0.00000, dan=0.00000** (run_tests itself FAILS them on this slate, as noted).
- `swim_predict_full.py` — full BUILD→cruise→steer, 3 independent captures (steady steer csx=155,
  fast reversal 160↔96, double-steer 170/108): **cam=0hw, v=0.00000, anim=0.00000, POS=0.0039**
  (the 0.0039 is the f32 noise floor, reached in the build and not growing).
- New files: `swim_coldstart.py` (ColdStartSwimState subclass), `validate_coldstart.py`,
  `swim_predict_full.py`, `capture_full.py`. dolphin_mem NAMED_ADDRS += `move0_mrate`.

## >>> OUTCOME (2026-06-28 pm) — FULL POSITION PREDICTION IS BIT-EXACT FOR CRUISE/STEER <<<
The unified predictor (camera + direction + magnitude + physics) is **BIT-EXACT** — verified
`POS=0.0000, cam=0hw, v=0.00000, anim=0.00000` across 6 diverse captures (steady steer, holds,
ramps, reversal, taps): `python swim_predict_exact.py --cruise`. The camera runs from rest (f0,
bit-exact); the swim is seeded from the first state-55 (cruise) frame. This is the steering regime
the project cares about (camera nudge → lateral drift).

REMAINING GAP = the cold-start/pump anim SCRAMBLE (the speed-BUILD phase), and it is currently
**BLOCKED BY A CLOBBERED SLATE**, not by modeling:
- **Slot 10 was OVERWRITTEN at 19:33 this session** (the camera agent saved over it; only one
  s10 file, no backup: `Binary/x64/Release/User/StateSaves/GZLJ01.s10`). The calibrated COLD slate
  (cold-start seed anim = 0.06392288208007812, where the sim's scramble model is bit-exact and the
  3 run_tests baselines PASSED) is LOST. The current slot 10 is a WARM mid-swim state (raw anim
  8.397, **air 883 not 900**, cold-start seed 8.94) — so run_tests now FAILS all 3 baselines on
  BOTH anim AND velocity (dv=+9 cold-3k, −33 4-pump; x598 amplifies the seed mismatch). The sim was
  NOT changed; the live slate was.
- Exact restoration is infeasible (the x598-exact SWIMWAIT phase can't be hit by frame-advancing).
  => Needs the USER: restore the original slot-10 savestate from a backup, or recreate the cold
  slate via the Storage+Camera-Lock setup. THEN the build should be bit-exact again (it was before).
- PRACTICAL WORKAROUND (no slate needed, already bit-exact): run the speed-build LIVE, read the
  post-build cruise state, and seed the predictor there — the steered cruise predicts bit-exact
  (that's exactly `validate_from_cruise`). For pure-offline build-from-cold you need the slate.

Files added/finalized: `camera_exact.py` (bit-exact camera, 0hw/347fr), `swim_exact.py` (exact
direction+magnitude, field_0x7C=0.35), `swim_predict_exact.py` (unified; `--cruise` = bit-exact
validator). `superswim_sim.py`/planner untouched.

## >>> COLD-START UNBLOCKED — "log init config" CONFIRMED (2026-06-28 pm) <<<
The slate is NOT broken — the cold-start failure is that the sim ASSUMES `oldframe = display+1.0`
and recomputes the neutral rate from air, instead of LOGGING the live controller state. PROVEN
on a live cold-start trace from the current (clobbered) slot 10:
- seed display = 8.94170, logged MOVE0 `mRate` = 0.547222 (read @ anim-chain base +0x2F60).
- true oldframe = display + the two logged neutral advances = 8.94170 + 0.54722 + 0.5 = 9.98892.
  scramble = f32(f32(oldframe*26)*23): logged→**5973.37 = live, err +0.00 (BIT-EXACT)**;
  sim's +1.0 (oldframe 9.9417)→5945.14, **err −28.23** (×598-amplified → the run_tests dv/anim fail).
- CRUCIAL: `neutral_anim_rate(900)=0.4972` ≠ the logged mRate 0.5472 — the logged rate reflects
  pre-seed AIR HISTORY (mRate 0.5472 ⇔ air≈882, not the written 900); it CANNOT be recomputed, only
  LOGGED. This is why the +1.0/air-recompute model is slate-phase-dependent and broke when slot 10's
  phase changed. Logging mRate makes the cold-start scramble phase-INDEPENDENT.
=> PATH TO FULL BIT-EXACT (no original slate needed): log the init config (the MOVE0 `mRate`, or
   simplest: log the post-scramble state-55 anim and seed there — the 2 scramble frames are run live,
   everything downstream predicts bit-exact offline). Implement as a SwimState SUBCLASS (new file)
   that takes the logged mRate for the cold-start oldframe instead of +1.0. `run_tests` would go green
   the same way (log mRate into its seed). NOT blocked; no slate restoration required.
- Named addr to add: `move0_mrate` = anim-chain base (0x803AD860 deref) +0x2F60, f32.

## New files (all import superswim_sim read-only; none modify it)
- `camera_capture.py` — drive per-frame (main+C-stick) inputs live from a slot, log full
  ground truth to CSV (csangle,facing,link_state,potential_speed,anim_frame,air,x,z,dx,dz).
  Attaches once, advancewith frames=1. (For DENSE charge use DTM instead — pipe jitter.)
- `camera_predict.py` — CameraState: per-frame csangle predictor from C-stick (EMPIRICAL).
- `swim_predict.py` — position predictor: heading from camera + magnitude from sim physics;
  validate_position (live cam vs predicted), validate_full (inputs-only end-to-end).
- captures: capA.csv (straight cruise), capB.csv (steady steer sx=160), capC.csv (tap-lock).

## Three sub-models needed for bit-exact position (status)
### 1. CAMERA yaw (csangle) — **BIT-EXACT (0 hw)** as of 2026-06-28 pm. SOLVED. See `camera_exact.py`.
The earlier "velocity + k=0.5 smooth + float accumulator" picture was an ARTIFACT of fitting the
per-frame s16 deltas; the real mechanism is a **two-s16-field position chase**, recovered by live
RE (NOT decomp — `dCamMath::rationalBezierRatio` is Nonmatching, confirmed dead-end).

LIVE MECHANISM (read out of the dCamera_c instance; base = 0x80acffa4 after slot 10, = the writer
r28 at PC 0x80160a0c; resolved generically as the csangle pointer-chain instance, p2+0x244):
  - `cam_yaw`    s16 @ instance **+0x0E**  (0x80acffb2): the integrated camera yaw. Writer PC 0x80165980.
  - `cam_target` s16 @ instance **+0x3AE** (0x80ad0352): the angle accumulator cam_yaw chases.
  - **csangle == (cam_yaw + 0x8000) & 0xFFFF**  (verified live every frame; the +0x6C / +0x2B0 read).
  - Both added as named addrs `cam_yaw` / `cam_target` in dolphin_mem.py (csangle chain + 0x252 / +0x5F2).

EXACT PER-FRAME RECURRENCE (pure integer; verified bit-exact through ramps, reversals, sign flips):
```
# 1-frame input lag: the C-stick on frame f is consumed on f+1 (update ORDER, NOT SI polling).
target = (target + omega_cmd(csx_prev, csy_prev)) & 0xFFFF       # accumulate the rate command
diff   = s16(target - yaw)
yaw    = (yaw + int(diff / 2)) & 0xFFFF                          # C integer divide, trunc toward 0
csangle = (yaw + 0x8000) & 0xFFFF
```
- `omega_cmd(csx)` is the **integer** per-frame target increment (== the live cam_target delta,
  read directly — no fitting). It IS the C-stick→camera-rate curve (the Nonmatching bezier output):
  deadzone csx 109..148 -> 0; saturation csx>=175 -> +546, csx<=81 -> -547 (=±3.0°/frame, |d|>=47);
  steep S-curve in between, NOT perfectly symmetric (csx=160(+d32)->+18 but csx=96(-d32)->-19).
  Full tables in `camera_exact.py` (_OMEGA_POS / _OMEGA_NEG), measured live on GZLJ01.
- The chase `yaw += int(diff/2)` is cLib_addCalcAngleS-style scale-2 convergence (no min/max clamp
  in this regime). The C `/2` truncation reproduces BOTH the build ramp (rising yaw truncs down)
  AND the release/decay tail (which the old "round(omega)" / float-accumulator model got wrong by
  up to 3 hw — that was the entire "2 hw" residual).
- REST: with neutral C-stick, target == yaw-1 (a fixed -1 offset; int(-1/2)==0 holds yaw still).
  `CameraExact` seeds target = yaw_init - 1.
- VALIDATION: **0 hw error on 13 captures / ~320 frames** — straight cruise, steady steer at
  csx=155/160/165/170/175, deadzone edges (149/151/108), tap-and-release, multi-tap, full
  deflection both ways, mixed ramps, and a hard reversal through a sign flip. No irreducible floor.

### 2. MOVEMENT DIRECTION — decomp leads solid; not yet ported/validated.
From sub-agent (d_a_player_main.cpp / d_a_player_swim.inc), to verify against source:
- `m34E8 = (mainStickAngle + 0x8000) + dCam_getControledAngleY(camera)`  (setStickData ~10575)
- `cLib_addCalcAngleS(&shape_angle.y, m34E8, field_0x8, maxStep, minStep)`  (swim.inc ~38)
- `cLib_addCalcAngleS(&current.angle.y, shape_angle.y, 2, 0x2000, 0x1000)` (swim.inc ~47)
- move dir = `current.angle.y`:  speed.x = f1*cM_ssin(cay); speed.z = f1*cM_scos(cay) (~2430)
- => movement tracks CAMERA because m34E8 contains camAngle; for ESS facing & current.angle
  both coincide with cam-tracking (why I measured "heading == cam, facing-independent").
- 1-frame lag: posMove applies the PREVIOUS frame's speed vector.
- EMPIRICAL check: heading[atan2(dx,dz)] = cam[f-1] to ~0.04° (the residual is the chase lag /
  current.angle.y not fully caught up). Need the exact cLib_addCalcAngleS + field_0x8 to close.
- NOTE: existing SwimState already tracks shape_angle.y (facing) but uses a separate 180-flip
  heading for movement and a FIXED cam. The real move dir is current.angle.y (a distinct field
  that chases shape_angle.y). `facing` named addr (0x803EA3D2) = shape_angle.y; current.angle.y
  is a DIFFERENT field (need its address to capture/validate).

### 3. DISPLACEMENT MAGNITUDE — existing true_disp ~0.04% LOW. NOT bit-exact.
- Existing: true_disp = air_drag(af_drag(v,anim),air); air_drag=18000v/(24300-7air).
- Live capA: |dx| = |af_drag| at the anim PEAK exactly (698.000), i.e. air_drag should NOT
  reduce it there; true_disp is ~0.2-0.28 too low every frame (consistent sign).
- Decomp (d_a_player_main.cpp ~2424-2431, posMoveFromFootPos): f1 = (speedF*(1-0x60) +
  0x60*speedF*|cM_scos(rad2s(pi*getFrame/getEnd))|) / (1 + field_0x7C*getSwimTimerRate()),
  field_0x60=0.4, field_0x7C=1.0, getEnd=23 (UNDER_MOVE0). getFrame is the LOOPED [0,23) frame.
  => the air term in the existing sim's air_drag is likely the WRONG structure; replace with
  the exact decomp denominator. THIS IS THE MOST TRACTABLE EXACT PIECE (pure fn of v,anim,air;
  validate directly vs capA |dx|, camera fixed, no direction confound). DOING THIS NEXT.

## Validation harness
- `python camera_capture.py <seq> out=capX.csv speed=-700 air=900` (seeds a test point).
- `python camera_predict.py capX.csv`         (camera-only error in hw)
- `python swim_predict.py capX.csv [livecam]`  (position; livecam isolates direction+mag)
- `python swim_predict.py capX.csv full`       (inputs-only end-to-end)
- SEEDING (mirror run_tests.py:95-105): loadstate; neutral pre-advance substickY=0; write
  air/speed; read v0/anim0/air0/st0; SwimState(...).state=st0; _entry_tax=False. (My early
  full-predictor v_err=-5 was a spurious entry_tax=True; anim blowup was wrong cold-start path.)

## EXACT DECOMP (confirmed from source, 2026-06-28) — direction + magnitude SOLVED on paper
All from the JP-logic decomp (US line numbers): `d_a_player_main.cpp::posMoveFromFootPos`
(~2424-2431), `d_a_player_swim.inc::setSpeedAndAngleSwim` (~24-50), `c_lib.cpp` (160-189),
HIO `daPy_HIO_swim_c1` (HIO.h ~728-762).

### MAGNITUDE (was the existing sim's unvalidated true_disp; now exact, field_0x7C=0.35)
```
getSwimTimerRate(air) = f32(1 - f32((air+1) * 0.0011111111f))      # itemTimeCount = air+1
af_num(v, frame)      = f32( f32(v * f32(1-0.40)) + f32(0.40 * f32(v * |c|)) )   # field_0x60=0.4
   where |c| = f32(abs(cM_scos(cM_rad2s(M_PI * getFrame/23.0))))   # getFrame=LOOPED MOVE0 [0,23)
f1 (per-frame disp magnitude) = f32( af_num / f32(1 + f32(0.35 * getSwimTimerRate(air))) )
```
- field_0x7C = **0.35** (backed out from capA straight cruise; later frames -> 0.35000).
- REPLACES the existing `air_drag = 18000v/(24300-7air)` (an approximation, ~0.04% / 0.28-unit low).
- Validated vs capA |dx| (camera fixed -> |dx|==|f1|): worst 0.008 at the entry frame, ~0.001-0.002
  elsewhere. The residual is ANIM-SOURCE TIMING (logged anim_frame vs the exact getFrame() at
  displacement time) -> resolves when driven in lockstep by SwimState's anim. Formula is exact.
- NOTE getFrame is the LOOPED [0,23) frame; feeding the RAW post-scramble anim (e.g. 337) into
  cM_rad2s loses f32 precision in the large multiply before the mod -> use the looped frame.

### DIRECTION (move bearing) — exact chain
- `m34E8 = mMainStickAngle(sx,sy) + 0x8000 + camAngle`   (setStickData; camAngle = cam[f-1], see
  ordering below). All s16.
- setSpeedAndAngleSwim (stick>0.05, no attention lock):
  - if `|m34E8 - shape_angle.y| > 0x6000` (DIR_BACKWARD): SNAP `shape_angle.y = current.angle.y = m34E8`.
  - else: `cLib_addCalcAngleS(&shape_angle.y, m34E8, scale=0x11, maxStep=0x1388, minStep=0x4B0)`.
  - then ALWAYS: `cLib_addCalcAngleS(&current.angle.y, shape_angle.y, scale=2, maxStep=0x2000, minStep=0x1000)`.
- speed.x = f1*cM_ssin(current.angle.y); speed.z = f1*cM_scos(current.angle.y).  Move dir = current.angle.y.
- Because superswim v<0, f1<0 -> displacement is REVERSED: world bearing atan2(dx,dz) = current.angle.y + 180.
  For ESS(128,110) mMainStickAngle gives heading == cam[f-1] (the two 0x8000 + the 180 reversal cancel).
- cLib_addCalcAngleS (EXACT, all s16 wrap, integer divide):
  ```
  diff = (s16)(target - *p)
  if *p != target:
    step = (s16)(diff / scale)                 # trunc toward 0
    if step > minStep or step < -minStep:
      step = clamp(step, -maxStep, maxStep); *p += step
    else:                                       # |proportional step| <= minStep
      if diff >= 0: *p += minStep; if target-*p <= 0: *p = target
      else:         *p -= minStep; if target-*p >= 0: *p = target
  ```
  CONSEQUENCE for cruise: per-frame diff ~18 (one frame of cam rotation) << minStep -> both chases
  SNAP to target each frame. So current.angle.y == m34E8 each frame (no chase lag in cruise). Charges
  (diff ~180deg) hit the hard DIR_BACKWARD snap. The chase only "lags" for medium diffs (rare).
- FRAME ORDERING (the real 1-frame lag, NOT SI polling): within a frame the player runs
  setStickData (reads camera) -> procSwimMove -> posMoveFromFootPos -> posMove, and dCamera_c::Run
  updates the camera LATER. So setStickData[f] sees cam[f-1]. Hence heading[f] = f(cam[f-1]).

### STILL ONLY EMPIRICAL: the camera yaw (csangle) itself (see sub-model 1 above). The above gives
### BIT-EXACT POSITION *GIVEN* the camera angle; the camera prediction is the last non-exact piece.

## NEXT STEPS (ordered)
1. [DONE on paper] Exact displacement magnitude: f1 = af_num/(1+0.35*getSwimTimerRate). field_0x7C
   =0.35. Validated to measurement/anim-timing noise vs capA. -> implement in a new module.
2. [DONE on paper] Exact movement direction: m34E8 + cLib_addCalcAngleS chains (snap in cruise) ->
   current.angle.y; heading = current.angle.y+180 (v<0). Matches measurement. -> implement + port
   cLib_addCalcAngleS + mMainStickAngle(sx,sy). Capture current.angle.y live to double-check the
   rare non-snapping (medium-diff) cases & charge transitions.
3. [REMAINING — the only non-exact piece] CAMERA yaw (csangle) bit-exact. Empirical law is 2hw.
   DECOMP IS A DEAD-END (2nd agent confirmed): d_camera.cpp::followCamera shows the smoothing
   `m3E0 += (target - m3E0)*0.5` at line 3197 (CONFIRMS k=0.5) and the yaw integ at ~3200-3265
   (m3BC target accumulator, m3A0 yaw-deg, cAngle::d2s -> s16), BUT the C-stick(substickX)->rate
   mapping goes through `dCamMath::rationalBezierRatio` which is **Nonmatching / not decompiled**,
   so the exact omega_cmd curve is NOT in source. => Finish via LIVE RE, not decomp:
   - dCamera_c internal float offsets (agent, verify live): mStickCPosXLast @ +0x16C (f32 C-stick X,
     -1..1), m3A0 @ ~+0x3A0 (yaw deg f32), m3BC @ ~+0x3BC (target yaw f32), m3E0 @ ~+0x3E0 (0.5
     smoothing f32), mAngleY @ +0x6C. NOTE these are offsets from the dCamera_c INSTANCE; the live
     u16 yaw we read is [[0x803AD380]+0x34]+0x2B0 (object at 0x80acfd60 after slate10) — RECONCILE
     which object that is vs the instance the +0x3A0 offsets belong to (they don't obviously match;
     find the dCamera_c instance base, e.g. via the writer PC 0x80160a0c's base register).
   - PLAN: read m3A0 (float yaw) + the omega/target floats live each frame while driving a known
     C-stick; confirm s16_csangle == round/d2s(float yaw); fit the float recurrence EXACTLY. The
     omega_cmd curve: measure steady-state rate to FLOAT precision by holding sx for ~200 frames and
     dividing total rotation (long-average kills the ±0.5 rounding that makes my 10-pt table 2hw off).
     The structure (k=0.5 confirmed, deadzone, sat 3.0deg, float-accumulate->s16) is right; only the
     float omega_cmd magnitudes need exactness.
4. Build the unified bit-exact predictor (new file, NOT modifying superswim_sim/planner): drive
   SwimState (physics+anim, seeded per run_tests) + the exact camera + exact direction + exact
   magnitude. Validate inputs-only bit-exact on cruise+steer; then cold-start build (use DTM as
   ground truth for dense charge per [[superswim-bug2-input-delivery]]) + steer.

## SUMMARY OF STATUS (updated 2026-06-28 pm — camera SOLVED)
- Camera yaw (csangle): **BIT-EXACT, 0 hw** on 13 captures/~320 frames. `camera_exact.CameraExact`.
  Two-s16-field position chase (target accumulates integer omega_cmd; yaw += int((target-yaw)/2);
  csangle = yaw+0x8000). NOT the old float-velocity model. Recovered by live RE; bezier still
  Nonmatching but irrelevant (omega_cmd read directly off the live cam_target delta).
- Movement direction: EXACT (swim_exact.step_direction; heading via cur_y chase, cam[f-1]).
  Live-confirmed bit-exact per-frame (dx/dz match to f32 noise ~0.007) from the 2nd cruise frame on.
- Displacement magnitude: EXACT (swim_exact.disp_magnitude; field_0x7C=0.35). Matches live dx/dz to
  f32 noise in cruise. Residual ONLY on (a) the state54->55 ENTRY frame's magnitude and (b) the
  charge-build phase — both are the anim/displacement sub-model's entry handling, not the camera.
- Physics v/anim/air/state: bit-exact in superswim_sim.SwimState for the regimes its baselines cover.
  ⚠️ 2026-06-28 pm: run_tests baselines currently FAIL on **anim only** (v is still dv=+0.000 through
  the charges) — the live cold-start anim scramble oldframe shifted (live ~9.99 vs sim's display+1.0
  =9.94 => +28 at the x598 scramble, ~5 thereafter). This is the anim sub-model's cold-start
  calibration vs the current live game (post-reboot controller-frame phase), NOT a camera/position
  regression and NOT caused by this session (superswim_sim.py/run_tests.py untouched).

## UNIFIED PREDICTOR (new file `swim_predict_exact.py`)
Drives SwimState (physics) + CameraExact (camera) + swim_exact (direction+magnitude). Per-frame
ordering: snapshot cam (cam[f-1]) -> SwimState.step -> direction chase + disp magnitude -> cam.step.
- CAMERA: 0 hw on every capture (the deliverable).
- POSITION: bit-exact per-frame (dxz ~0.007 = f32 noise) in cruise/steer once physics is correct;
  the only position residuals are the 1-frame entry magnitude and the charge-build phase (anim
  sub-model), and they vanish when SwimState's anim matches live (i.e. when the baselines pass).
- New capture tool `capture_unified.py` (run_tests-style seeding, robust to mid-run Dolphin close).

Files (all import superswim_sim/planner read-only; none modify them):
  camera_exact.py, swim_predict_exact.py, capture_unified.py;
  tww-python-scripts/{bp_cam_base,bp_yaw_writer,bp_yaw_fpr}.py (RE breakpoints; all disabled/cleared).
  dolphin_mem.py NAMED_ADDRS += cam_yaw (+0x0E), cam_target (+0x3AE).
```
