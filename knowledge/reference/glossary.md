# Glossary

**Answers:** What does <term> mean? Swim (csangle, ESS, head-bob, af_drag, x598, strobo, reboost,
pump, slate, …), land (brakeslide, EBS, FRONT_ROLL, roll stab, speedF, facing vs travel, C-up freeze,
seam clip, Co push, …), and engine (foot FK, oldframe-morf, FMA-fused, `m3598`, …) terms.
**Status:** reference.
**Source:** terms defined from the mechanics pages; follow the links for detail.

One-line definitions. Each links to the page that explains it fully.

| Term | Definition |
|------|-----------|
| **Superswim** | A swimming state (set up via Storage + camera lock with the Wind Waker) where alternating the control stick fully back-and-forth each frame builds speed. |
| **Potential speed** (`mNormalSpeed`, `velocity`) | The underlying speed value. Charging adds to it; ESS/neutral decay it. Negative-signed by convention. |
| **True speed / true displacement** | How far Link actually moves this frame = potential speed scaled by [head-bob](#af_drag) and air drag. |
| **Charge** | Full alternating deflection: **+3** potential speed/frame (on-axis). See [constants](constants.md#speed-deltas). |
| **ESS** (extended superslide) | A legacy Zelda-series term (not descriptive — see [ess.md](../mechanics/ess.md)); in TWW it's holding the **minimum** non-neutral stick deflection (e.g. `(128,110)`). Decays potential speed only **−1/6** but pays head-bob + air drag on true speed. See [glossary: head-bob](#af_drag). |
| **Neutral** | Stick at `(128,128)`, inside the dead zone. Decays **−2/frame** but is **drag-free** (true speed = potential speed). A separate code path, not a point on the ESS decay curve. |
| **`mStickDistance`** | Normalized stick deflection `clamp((|raw−128|−15)/54, 0, 1)`; the magnitude that scales the per-frame speed gain. |
| **Animation frame / anim** | Position in the swim stroke cycle (`0..23` ESS, `0..26` neutral). Drives the head-bob. |
| <a id="af_drag"></a>**Head-bob drag** (`af_drag`) | Link's head bobs with the anim cycle, modulating true speed. Numerator `0.6v + 0.4v·|cM_scos(π·anim/23)|`, then **divided by `1 + 0.35·getSwimTimerRate(air)`** for full true speed (don't drop the denominator). `cM_scos` is the [console cosine](#cm_scos) ≈ `cos`. Near anim 0/23 → ~100% kept; near 11.5 → ~60%. Full formula + constants: [constants](constants.md#head-bob-animation-frame-drag--true-speed). |
| <a id="cm_scos"></a>**`cM_scos`** | The **console** cosine: a 4096-entry s16 lookup with the low 4 bits truncated, *not* `math.cos`. Tiny error, amplified by [x598](#x598) and high-speed exits → must be matched for bit-exactness. |
| **Instant turnaround / charge snap** | When charging, Link's facing flips 180° in one frame if the stick points within **45°** of straight-back. See [turnaround](../mechanics/turnaround.md). |
| **Arrow swimming** | Charging while tilted toward the target so Link drifts toward it ("tip of an arrow") at a reduced charge rate. See [arrow](../mechanics/arrow.md). |
| **Tilt α** | Arrow move-direction offset from the pure-back axis. `charge_rate = −3·cos(2α)`; cross-drift `= disp·sin α`. Usable α ∈ [0°, ~20°]. |
| **Stroboscopic band** | A speed (≈ −794, ≈ −1630) where the anim increment ≈ 23·k, so the anim barely advances (aliases) and head-bob efficiency stays roughly stable. See [strobo](../mechanics/strobo.md). |
| **Reboost** | A short up/down charge in a strobo band to bump speed and re-aim the slow anim drift back toward the head-bob peak. Phase-triggered, not on a timer. See [strategy/reboost](../strategy/reboost.md). |
| **Pump (ESS pump)** | A short ESS burst out of neutral on a favorable anim frame to preserve speed cheaply. Pays a 1-frame entry tax (first frame is still neutral). Low-speed tech. |
| <a id="x598"></a>**x598 scramble** | The neutral→ESS transition multiplies the anim by `End_wait·End_swim = 26·23 = 598`, scrambling the ESS-start phase. Deterministic but hypersensitive — see [model](../model/) (planner) and [history](../history/). |
| **`release_ess_speed`** | The speed carried into neutral on ESS→neutral exit = `af_drag` at the release anim. Exit near anim 0/23 keeps ~100%; near 11.5 keeps ~60%. |
| **csangle** | The camera yaw. The stick is camera-relative: `world_angle = stick_angle + csangle + 0x8000`. A fine lateral-steering lever. |
| **Slate** | A savestate dump of game RAM used as a known starting point for live tests (e.g. "slot 10", a flat-water cold-start). Not shipped (copyrighted RAM). |
| **Anchor** | A test-owned savestate `<test>@<isokey>.sav` under `tests/dolphin/anchors/`. |
| **DTM** | A Dolphin movie file; the faithful input-delivery path for live validation (vs the `advanceseq` pipe — see bug#2). |
| **Bug#2** | The dense-pump live divergence — resolved as a pipe input-delivery artifact, not physics. DTM playback is faithful. |
| **Cold start** | A swim begun from `v = 0` (vs seeded at cruise speed). |
| **Quadrant grid** | The Great Sea = a **7×7 grid of 49 quadrants**, one island each. Routes are planned quadrant-to-quadrant. See [ocean-environment](../mechanics/ocean-environment.md). |
| **Air refill** | Resetting air to [900](constants.md#air) by skimming a loaded island's land/water boundary while still swimming (**touching land 1 frame loses ALL speed**). See [air-refill](../mechanics/air-refill.md). |
| **Sploosh zone** | A sparse flat-ocean quadrant where the **ocean surface collision loads too slowly** — entering too fast drops Link to the sea floor ("sploosh"). Must be approached under a max-speed cap or routed around. See [ocean-environment](../mechanics/ocean-environment.md#sploosh-zones-ocean-collision-load-failure). |
| **Collision streaming** | Only **one island's collision is loaded at a time** (load timing unpredictable) — why mid-swim refills are rare. See [ocean-environment](../mechanics/ocean-environment.md). |

## Land terms

| Term | Definition |
|------|-----------|
| **facing vs travel** | Land's two headings: **facing** = `shape_angle.y` (body direction), **travel** = `current.angle.y` (velocity direction). Swim keeps them fused; land tech lives in their divergence. See [walk-run](../mechanics/walk-run.md). |
| **`potential_speed`** (`mNormalSpeed`) | The signed 1-D land speed (negative = moving opposite to facing). The physics variable, before the foot-plant blend. |
| **`speedF`** (true speed) | What position actually integrates = `mNormalSpeed·(1−m3598) + f31_2·m3598` — the potential speed blended with the planted-foot delta. Equals `mNormalSpeed` at cruise (`m3598=0`). See [walk-run](../mechanics/walk-run.md). |
| **`msd`** (`mStickDistance`) | Normalized stick deflection `clamp((\|raw−128\|−15)/54, 0, 1)`; scales the per-frame speed gain. On land the movement gate needs `msd > 0.5`. |
| **Brakeslide** | Hold L (target) + full-down + ESS from a run: facing locks, travel flips 180°, Link slides backward-as-negative-speed. See [brakeslide-ebs](../mechanics/brakeslide-ebs.md). |
| **EBS** (extended brakeslide) | Release L out of a brakeslide: momentum bleeds ~13× slower. If facing steers toward `csangle` the decay collapses to ~−0.001/frame — speed held almost forever. |
| **Wiggle EBS** | Just the **alternating-ESS component** of an EBS — alternate the held ESS so facing oscillates around forward while travel stays backward, holding the speed at the camera-relative minimum. Not a separate technique. |
| **FRONT_ROLL** | The forward roll (A while moving): `mNormalSpeed = clamp(speedF·1.5+0.5, 5, 26)`, the 26-cap workhorse ground-cover tech. See [roll](../mechanics/roll.md). |
| **Roll stab** | A sword cut (CUT_F/CUT_A) fired out of a roll → a single-frame **49.22u** lunge (roll 26 + the anim root-translate 23.22). The seam-clip reach. See [roll-stab](../mechanics/roll-stab.md). |
| **Sidehop / backflip** | Targeted ballistic hops (L+A+direction): sidehop ≈ ±323u perpendicular, backflip ≈ −270u. The consistent standstill movers. See [ballistic-hops](../mechanics/ballistic-hops.md). |
| **WAIT_TURN / MOVE_TURN / SLIP** | The three big-reversal ground-turn procs: standstill pivot / slow turn-around / fast skid. See [ground-turns](../mechanics/ground-turns.md). |
| **ATN_MOVE** | The targeting (L-held) move proc (state 7): brakeslide, strafes, L-target forward. Runs `setSpeedAndAngleAtn`. |
| **C-up freeze / subjectivity** | The C-up speed cancel: enters `daPyProc_SUBJECTIVITY_e` (first-person), `mNormalSpeed=0`, position LOCKS — the float-perfect stop. See [precise-stop](../mechanics/precise-stop.md). |
| **Seam clip** | Walking/rolling through a wall corner via a float-precision gap in the collision push-out. See [seam-clip](../mechanics/seam-clip.md). |
| **Co push** | Actor-vs-actor cylinder push (the "Tetra nudge"): overlap → a rank-weighted position correction. Supplies the extra displacement a seam clip needs. See [actor-push](../mechanics/actor-push.md). |
| **DZB** | The stage collision triangle mesh (in-RAM `cBgD_t`): vertices + triangles + groups. See [collision](../mechanics/collision.md). |

## Engine terms

| Term | Definition |
|------|-----------|
| **Foot FK** | Reduced foot-chain forward kinematics: BCK Hermite keyframe eval → euler→quat → `QuatLerp` → matrix concat → the world-space toe position whose per-frame delta becomes `speedF`. See [anim-engine](../model/anim-engine.md). |
| **Hermite** | The cubic keyframe interpolation the J3D BCK anim tracks use (value + in/out tangents per key). |
| **`PSMTXQuat` / QuatLerp** | GC matrix-from-quaternion and quaternion-lerp ops, ported bit-exact (some FMA-fused). Part of the foot FK chain. |
| **oldframe-morf** | The blend, on a proc/anim entry, from the *previous* frame's pose toward the new anim (`mScale·(1−rate) + oldScale·rate`) over a few frames — warms the toe stream so the walk-off is bit-exact. |
| **FMA-fused** | A multiply-add the hardware computes with a single rounding (`fma`); the sim reproduces it via an f64 intermediate (`tww_sim.core.fp`) where the game fuses, else bit-exactness breaks. See [fp-faithfulness](../model/fp-faithfulness.md). |
| **`m3598`** | The WALK↔DASH blend factor: `speedF = mNormalSpeed·(1−m3598) + f31_2·m3598`. 0 at cruise, 1 below ½·max. |
| **INPUT_DELAY** | The 2-frame latency between a stick/button and the game acting on it (both press and release). |
