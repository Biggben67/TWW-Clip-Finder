# Precise stopping: the C-up speed cancel (SUBJECTIVITY freeze)

**Answers:** How do you stop Link at an exact world position (float-perfect)? What is the C-up speed
cancel / the `daPyProc_SUBJECTIVITY_e` freeze? Why must you arrive slow? What are the live-valid stick
magnitudes and the L-target low-speed access? How does B cancel the recovery, and why isn't the re-walk
a cold walk? How is the whole gesture input-driven in `step()`?
**Status:** validated live **0 ULP** (2026-07-05, both pure-Python and fused-native paths). This page
is the *mechanism*; the *planner* that searches for the fewest-frame freeze to a target lives in
[model/land-planner.md](../model/land-planner.md).
**Source:** decomp `d_a_player_main.cpp` `procSubjectivity_init` / `checkSubjectEnd` (5694) /
`setBlendMoveAnime`; `d_camera.cpp` (C-up/C-down routing); live captures.

---

For placing Link at an exact world position (float-perfect stop) — validated live 2026-07-04.

## Live-valid stick magnitudes (a sim `msd` caveat)

`_set_stick_data` uses `msd = min(hypot(deadzone)/54, 1)`. For **Y ≤ 191** (msd ≤ 0.889) this is
bit-exact live; for **Y ∈ [192, 254]** the sim OVER-reads msd vs the live PADClamp (which saturates
differently near the cap) — a walk at `(128,196)` gives sim v=16.38 but live 15.76, ~1u+ divergence
over a run. `(128,255)` (true full) is exact. **So any offline search over partial magnitudes must
restrict to `Y ≤ 191 ∪ {255}`; NEVER emit 192–254** or the plan diverges live. (Same input-layer≠`/54`
family as the [stick-angle table redump](../history/resolved-bugs.md).) From a **standstill** the walk
needs `msd > 0.5` to move at all (the `setSpeedAndAngleNormal` `dVar9` gate `0.5 − 0.5·|v|/max`), so the
smallest up-input that moves is **`(128,171)`** (msd 0.519 → cruises ~4.6/fr); `(128,170)` and below stay
planted. (This live-valid *input* band is distinct from the sim's `Y171` *speed regime* — see
[model/land-sim.md](../model/land-sim.md#partial-magnitude-regime-y171-msd052).)

## L-target forward = X-neutral low-speed access

Holding L (Z-target; `buttons 0x40` + `triggerL 255`) + up-stick + centered X from a standstill →
`ATN_MOVE` (state 7), direction FORWARD, facing locked, travel stays 0 → **X stays 0**, bit-exact live.
It unlocks speeds normal walk can't reach from rest (`Y=168`→3.64, `Y=170`→4.25, below the 171 gate)
and runs different accel/decel (`ATN_ACC 7.5`/`ATN_DEC 4.0`). **Hold C-DOWN (`substickY=0`) on every
targeting frame** — otherwise the camera auto-swings during targeting (moves `csangle` → moves X);
C-down keeps it frozen (the sim's `CameraManual` is frozen for `csy∈{0,128}`).

## C-up speed cancel = the instant freeze (the float-exact enabler)

While walking (free cam): one frame **half-press L** (analog `triggerL≈100`, ends manual cam), then
**left stick NEUTRAL + C-stick FULL UP** (`substickY=255`). Effect: 2 input-latency frames (still
cruising) + 1 normal-decel frame, then speed **snaps to 0 and position LOCKS** (`link_state → 1`). X
stays 0. **The existing sim reproduces the freeze position with zero new code**: `frozen_pos = walk-sim
pos 3 frames after the neutral+C-up input` (the 2-frame `INPUT_DELAY` + one `cLib` decel already produce
it) — verified bit-exact (live froze at z=795.126 from a Y171 cruise; sim's 3rd-neutral-frame pos =
795.1258). Because the freeze happens MID-MOTION there is no resting dead-band, so a slow approach +
cancel places the frozen float essentially anywhere.

**Arrive SLOW to arrive fine (the freeze-coast constraint).** The frozen position = walk pos + the
3-frame coast, and that coast **scales with the approach speed** (2 latency frames still cruise the
pending sticks). So a fast arrival gives coarse ~10–17u freeze steps; only a SLOW approach gives a fine
straddle. But you can't crawl arbitrarily slowly: msd < 0.5 collapses to a dead stop (the `dVar9` gate),
so the **minimum sustained crawl is msd 0.5 → nspeed≈4.25 → ~1u/frame** (once already moving; it can't
be started from rest). The finest *sustainable* step is ~1u; sub-ULP resolution comes from a drill that
fills that 1u step, not from a slower crawl. (The freeze itself is 0-ULP-modeled from ANY approach speed
— full-speed cruise included: live froze at z=1121.9905 from a 23-frame full cruise. The halfL frame
RE-ISSUES the last approach stick, it does not add a frame.)

## The freeze IS `daPyProc_SUBJECTIVITY_e` (first-person view)

`link_state → 1` is proc 1, and `procSubjectivity_init` (`d_a_player_main.cpp:5948`) does two things:
`mNormalSpeed = 0.0` (the position lock) and `setBlendMoveAnime(field_0xC)`. On-axis that hits the
`ModeFlg_00000001` idle arm (line 3114) → `setMoveAnime(f27=0, f28=1.1, f25=0.8, ANM_WAITS, ANM_WALK,
r29=2, morf)`: **MOVE0 = WAITS (rate 1.1), MOVE1 = WALK (rate 0.587), `m34C3 = 2`, ratio 0,
`m3598 = 0`**, walk phase PRESERVED (`f31 = fc0.frame/frameMax`). `procSubjectivity` itself only
`setBodyAngleToCamera`s each frame, so the WAITS frame-ctrl advances at 1.1/frame.

## B cancels the freeze recovery (~2 frames vs ~8) — the chained coarse+fine primitive (TAS)

After the freeze locks, Link plays a **~8-frame recovery** before actionable. **Pressing B
(`PAD_BUTTON_B` 0x200) interrupts it** via `checkSubjectEnd` (`mItemTrigger & (BTN_A|BTN_B)`) →
`changeWaitProc` → WAIT (state 1 → 4), registered ~2 frames later (just `INPUT_DELAY`). Measured
2026-07-05c; **C-down did NOT speed recovery (still ~8), only B did.** This enables **coarse-freeze →
B-cancel → short fine-walk-from-rest → fine-freeze**: freeze from FULL speed (fast stop on a coarse
~17u lattice), B-cancel to rest (SKIPS the ~7-frame decel a crawl needs), then a few fine frames to the
exact float. The planner strategy that uses this is [model/land-planner.md](../model/land-planner.md).

**Why the re-walk ≠ a cold walk (SOLVED + modeled).** The post-B-cancel re-walk has the same `nspeed`
ramp but ~2× smaller low-speed `dz` — because the **foot-anim phase is CARRIED**, not reset. A cold
walk resumes from FREE_WAIT (single anim, `m34C3 = 0`), so `procMove_init`'s `setMoveAnime` forces
`f31 = 0` → the walk restarts at anim frame 0. The re-walk resumes from the subjectivity/WAIT blend
(`m34C3 = 2`), so `f31 = fc0.frame/frameMax` is preserved → the walk re-warms at the carried WAITS
phase. Live proof: first MOVE frame `fc0 = 0.000` (cold) vs `43.499` (re-walk), every other field identical.

## `step()` models the whole gesture from the RAW stream (input-driven)

The C-up cancel, the B button, L, C-DOWN, and the resume are all handled INSIDE `LandState.step()`
(pure-Python AND fused-native) — a plan is just an input sequence and playback is 1:1 (feed the identical
controller stream to sim + Dolphin, no `enter_freeze`/`hold_freeze`/`resume_walk` translation). The full
state machine, each piece **live-proven 0 ULP** (`spotcheck_subj_inputdriven.py`, both paths):
- **Entry (C-up → freeze):** the C-up gesture (near-neutral main stick + C-stick pushed UP; the sim
  reads the same normalized `cstick_normalize` posY the camera does, `d_camera.cpp:1096`) routes through
  the CAMERA, so it lands **3 frames** after the C-up poll — the 2-frame `INPUT_DELAY` **plus one camera
  frame**. The last MOVE frame still decelerates one step; `procSubjectivity_init` freezes on the next.
- **Exits (`checkSubjectEnd`, 5694), three of them:**
  - **A/B** = `mItemTrigger` **rising EDGE** — a B *held* from before `procSubjectivity`'s body runs
    (lock+1) MISSES the edge and does NOT exit (live-confirmed). Player-direct, **no floor**.
  - **L held** = `mItemButton & BTN_L` (BTN_L = `0x20` internal; hardware L = `0x40`). Player-direct, no
    floor. **⚠ Not reproducible via `advanceseq` OR the current DTM tooling** (neither injects the digital
    L that `checkSubjectEnd` reads — DTM omits pad bits 6-11); modeled from decomp + hand-confirmed on a
    real controller, live-0-ULP-validation pending better L injection (see `../../tools/DOLPHIN_CONTROL.md`).
  - **C-DOWN** = C-stick pushed DOWN (`mStickCPosY < −0.74`) → the camera's subject state machine sets
    `dCamAttnStts_00002000_e` (`d_camera.cpp:4230`, needs 2 frames of C-down). It is **FLOORED**: exit ≈
    `max(lock+9, C-down_poll+4)`. B beats it (no floor).
- **The freeze PERSISTS while C-up is re-requested.** If you keep holding C-up after an exit fires, the
  camera re-requests subjectivity and you **re-enter cup-cam** (stuck first-person). A re-walk needs C-up
  **released** first. The exit-to-`WAIT` is its own hold frame (`changeWaitProc` → `WAIT`, THEN
  `checkNextMode` → MOVE), so a re-walk resumes the frame AFTER the freeze has ended, not the exit frame.
- **Re-walk (forward stick → MOVE):** once ended + C-up released, a forward stick re-enters
  `procMove_init` (`m34C3 = 2`, phase carried). Position stays frozen throughout the freeze;
  subjectivity-hold and post-exit WAIT-hold advance the WAITS anim IDENTICALLY (`fc0 +1.1`/frame), so
  both use `step_subjectivity`. *Caveat:* holding a forward stick **simultaneously through** a C-DOWN
  exit leaves a ~0.15u residual (a `procMove_init`-vs-body 1-frame subtlety); the tech separates exit
  from walk.

The manual `enter_freeze`/`hold_freeze`/`resume_walk` API (and the anim primitives
`FootSpeedF.enter_subjectivity/step_subjectivity`, native twin `PoseEngine.w_enter_subjectivity/
w_step_subjectivity`) is retained for the planner's fast re-simulation. Live gates:
`tests/dolphin/spotcheck_subj_inputdriven.py` (input-driven, varied timings + fiat guards) and
`spotcheck_freeze.py` (frozen position via the planner API); offline
`test_subjectivity_freeze_rewalk_bit_exact`.

## Reachability caveat (the sim has no collision)

The sim has NO collision geometry, so a plan can target past a wall. The `land_flatwalk` anchor's +z
corridor hits a **wall at `pos_z ≈ 2932.4294` (`0x453746df`)**: targets beyond it freeze AT the wall,
not the requested z — a physical limit, not a sim error. On-axis freeze targets must lie in
`(764.08, 2932.43)` on this anchor.

## See also

- [Land movement overview](land-movement.md) · [walk-run](walk-run.md) · [roll](roll.md) (a roll
  approach makes the freeze analytic).
- **[model/land-planner.md](../model/land-planner.md)** — the fewest-frame freeze SEARCH (`reach_freeze`,
  roll/min-frames/robust modes, exact-target windowed-deepening). This page is the mechanism; that is
  the strategy.
- [model/land-sim](../model/land-sim.md) — land position accumulates in f32 (why the freeze is 0-ULP).
