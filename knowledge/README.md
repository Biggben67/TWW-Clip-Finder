# tww_sim knowledge base

The retrieval-first knowledge base for TWW player physics - **superswimming** (swim) and **land**
movement - plus strategy, the shared engine, and the sim/planner model. **Start here** - find your
question below, follow the link, read one small page.

## How this is organized

Knowledge is split by **layer** - different kinds of fact with different lifespans:

| Layer | What | Lifespan |
|-------|------|----------|
| [`mechanics/`](mechanics/) | Game truth - formulas, constants, decomp-grounded behavior | timeless |
| [`strategy/`](strategy/) | TAS heuristics + search methodology - reboost, dips, phase ordering, seam-clip delivery, search prunes | evolves |
| [`model/`](model/) | How the sim/planner implements it - engine (FP, anim), swim, land | tracks code |
| [`reference/`](reference/) | [Constants](reference/constants.md), [addresses](reference/addresses.md), [glossary](reference/glossary.md), [commands](reference/commands.md), [data](reference/data.md) | lookup |
| [`history/`](history/) | Provenance, dead ends, superseded conclusions, open questions | frozen |

**`history/` is not current truth** - its pages carry a `status: historical` banner. When you grep
for an answer, prefer the mechanics/strategy/model/reference pages; only read history for "how did we
get here" or provenance. Every page opens with an **`Answers:` / `Status:` / `Source:`** header so
you can triage in one glance.

## Question index

### Basics
- **What is superswimming / potential vs true speed?** → [mechanics/overview.md](mechanics/overview.md)
- **What does <term> mean?** (csangle, ESS, head-bob, x598, …) → [reference/glossary.md](reference/glossary.md)
- **What is the value of <constant>?** → [reference/constants.md](reference/constants.md) (NPC / actor Co-push + `Zl1` look-at values live in [reference/constants-npc.md](reference/constants-npc.md))
- **How do I run the sim / planner / a live test?** → [reference/commands.md](reference/commands.md)

### Charging, ESS, neutral, decay
- **How fast does charging build speed / what's the gain formula?** → [mechanics/charging.md](mechanics/charging.md)
- **What is ESS / what stick values / why is diagonal more efficient?** → [mechanics/ess.md](mechanics/ess.md)
- **How much speed do I lose for a given stick value?** (continuous decay law) → [mechanics/decay-curve.md](mechanics/decay-curve.md)
- **What does neutral do / is it really −2 / what's the exit-release speed?** → [mechanics/neutral.md](mechanics/neutral.md)
- **How does the animation cycle / head-bob drag / true displacement work?** → [mechanics/animation.md](mechanics/animation.md)

### Turnaround & arrow
- **How do turnaround frames work? What's the angle threshold?** → 45° off straight-back (`0x6000` = 135°) → [mechanics/turnaround.md](mechanics/turnaround.md)
- **How do you reorient the charge axis?** → [turnaround.md#reorienting-the-charge-axis-turnaround-chains](mechanics/turnaround.md#reorienting-the-charge-axis-turnaround-chains)
- **What is arrow swimming / charge-rate loss / tip-over / spin-up?** → [mechanics/arrow.md](mechanics/arrow.md)
- **Does arrow swimming actually save time?** → **no** (exhaustive offline sweep, 0 wins; best case loses +4 fr) → [arrow.md#does-arrow-swimming-save-time--no-offline-exhaustive](mechanics/arrow.md#does-arrow-swimming-save-time--no-offline-exhaustive)

### Strobo & reboost
- **What is the stroboscopic effect / at what speeds?** → ≈ −794 / ≈ −1630 (air-dependent) → [mechanics/strobo.md](mechanics/strobo.md)
- **Does reboost save time? How big / when? Why does fixed cadence lose?** → [strategy/reboost.md](strategy/reboost.md)

### Pumps & dips
- **What is an ESS pump / the 1-frame entry tax / the x598 scramble?** → [mechanics/pumps.md](mechanics/pumps.md)
- **What is a neutral dip and when does it help?** → [strategy/neutral-dip.md](strategy/neutral-dip.md)
- **What order do the swim phases go in?** → [strategy/phase-ordering.md](strategy/phase-ordering.md)

### Camera
- **How does camera yaw affect movement / the steering law / fine steering?** (swim) → [mechanics/camera.md](mechanics/camera.md)
- **What drives `csangle` on LAND (manualCamera, the C-stick, L-target blips)?** → the C-stick owns the yaw target; Link's motion moves only the centre → [mechanics/land-camera.md](mechanics/land-camera.md)

### Culling / rendering
- **How does TWW decide what's drawn vs culled / the view frustum / FOV-near-far / per-actor cull box / why is the culling far ≠ render far / how do I view it live?** → [mechanics/culling.md](mechanics/culling.md)

### Collision geometry & wall seams
- **How is stage/room collision stored in RAM (the DZB triangle mesh) / how do I reach it from a global / the vertex+triangle layout / ground vs wall vs roof / how do I view the live collision mesh in 3D?** → [mechanics/collision.md](mechanics/collision.md)
- **What happens each frame when Link walks/rolls INTO a wall (the CrrPos wall pass) / wall-hold / roll bonk vs grind / why A against a wall sidles instead of rolling / how does the sim run walls?** → [mechanics/wall-response.md](mechanics/wall-response.md)
- **Why do seam clips work (walking/rolling through a wall corner) / the float-precision root cause / why ≥~36 u + corner >90° + vertical walls / how do I predict one?** → [mechanics/seam-clip.md](mechanics/seam-clip.md)
- **Is THIS corner clippable, and with what exact coords / the deterministic clip model / the standability gates / how is a whole stage (or the whole game) scanned?** → [mechanics/seam-clip-scanner.md](mechanics/seam-clip-scanner.md)
- **How do we plan and validate a roll-stab SEAM CLIP (dust acceptance, live calibration, the knobs)?** → [strategy/seam-clip-solver.md](strategy/seam-clip-solver.md)
- **How does the clip pipeline run in a room other than kaze r11 / which room is worth capturing next / which room-level hazards the seam screen cannot see?** → [strategy/seam-clip-rooms.md](strategy/seam-clip-rooms.md)

### Actor-vs-actor collision (the Co push)
- **How does an actor push Link (the Tetra "nudge") / cyl-cyl overlap + weight split / can it supply the extra displacement for a seam clip?** → [mechanics/actor-push.md](mechanics/actor-push.md)
- **How FAR can a push move an actor in one frame / is `|speedF|/2` a hard bound / what sets the sustained rate / why does a shallow contact push less?** → the overlap halved per frame; 13.0 u/f is a steady state, not a bound → [mechanics/push-magnitude.md](mechanics/push-magnitude.md)
- **Where is the cylinder that pushes other actors (it is not Link's feet) / which lean tilts it and which frame's value does each term read / why does a roll off a curved approach push differently?** → [mechanics/link-co-centre.md](mechanics/link-co-centre.md)
- **Why does the same corner clip on one thrust and refuse two frames earlier when the animation is identical / which frame of a roll can a cut collect a push on at all?** → [mechanics/cut-frame-co-swing.md](mechanics/cut-frame-co-swing.md)
- **Sweeping the pushed actor's PLACEMENT changes nothing about my cut-frame contact / my sweep is FLAT in her position - why, and what axis is left?** → [mechanics/plow-ejection-equilibrium.md](mechanics/plow-ejection-equilibrium.md)
- **How much OVERLAP does my cut frame need, and where must the pushed actor stand / why is a small aligned push worth more than a big crooked one / how do I rank a raw sweep row before the geometry is solved?** → [model/required-cut-contact.md](model/required-cut-contact.md)
- **My sweep found a placement that clips - can the actor actually STAND there? Why does a position seeded INSIDE a wall push perfectly happily instead of being ejected / which of my search's axes owes a deliverability filter?** → [model/placement-standability.md](model/placement-standability.md)

### NPCs, attention & lock-on
- **When/how does Tetra follow Link (follow radius, speed), and when can Link lock onto / talk to her (the region a planner must avoid)?** → [mechanics/tetra-follow.md](mechanics/tetra-follow.md)
- **Where do an NPC's eyePos (the ATN_ACTOR re-aim target) and attention position (the camera's lock target) come from - the look-at head chase, the anims, the hidden seed state?** → [mechanics/tetra-look.md](mechanics/tetra-look.md)
- **How does Link's own head turn toward a lock-on target (the `m3564` setNeckAngle twist) / what moves `mHeadTopPos` / why does it feed back into facing through the NPC's look-at?** → [mechanics/link-head-look.md](mechanics/link-head-look.md)
- **How long does a lock-on keep driving the ATN_ACTOR procs after L is released / which check ends LOCK vs RELEASE / why does the roll still exit into the untarget brakeslide once the target is out of frame?** → [mechanics/attention-lock-lifetime.md](mechanics/attention-lock-lifetime.md)
- **Why did an A-press start a CONVERSATION (proc 170 DEMO_TALK) instead of the roll / which state decides talk-vs-roll / what exact bearing does the ±90° talk cone compare?** → [mechanics/talk-eat.md](mechanics/talk-eat.md)

### Ocean world, refills & routing
- **How is the sea laid out / why is only one island loaded / what's a sploosh zone / why route around quadrants?** → [mechanics/ocean-environment.md](mechanics/ocean-environment.md)
- **How do air refills work / why is touching land fatal / flat vs wavy / corner refills / the manual-refill workflow?** → [mechanics/air-refill.md](mechanics/air-refill.md)
- **How does the sim handle unmodeled world features (refills, sploosh) / the re-plan loop?** → [model/planner.md#unmodeled-world-features--the-re-plan-loop](model/planner.md#unmodeled-world-features--the-re-plan-loop)

### Land movement (walk, roll, turns, freeze)
- **Where do I find each land tech / the shared model (two angles, proc states, bit-exact status)?** → [mechanics/land-movement.md](mechanics/land-movement.md) (the land index)
- **How does walking accelerate / what are the two movement angles (facing vs travel) / the speedF foot-plant blend?** → [mechanics/walk-run.md](mechanics/walk-run.md)
- **Is there a walk-before-run speed plateau (~5.0)?** → no - full stick goes straight to the 17 cap (the "plateau" was a phantom front roll) → [walk-run.md#walk--run-acceleration-baseline](mechanics/walk-run.md#walk--run-acceleration-baseline)
- **What is a brakeslide / extended brakeslide (EBS) / why does ESS left-or-right hold speed almost forever / what is the wiggle EBS?** → is *facing* (not travel) relative to `csangle` → [mechanics/brakeslide-ebs.md](mechanics/brakeslide-ebs.md)
- **How does the 1-frame facing snap out of an EBS work / can the camera be steered to make it fire?** → the facing chase crossing TRAVEL, and NO: travel chases `csangle`, so the window is unreachable → [mechanics/ebs-turnaround.md](mechanics/ebs-turnaround.md)
- **How does the forward roll work / the 26 cap / chained + intermediate roll speeds / the frame-perfect roll-EBS?** → [mechanics/roll.md](mechanics/roll.md)
- **My A-press rolled in the sim and did NOT roll on console - what deflection does a roll need / what does the game do with a shallower press?** → `mStickDistance > 0.75`, else it sheathes → [mechanics/roll-attack-threshold.md](mechanics/roll-attack-threshold.md)
- **How EARLY can the B thrust fire out of a roll, and how late / does holding the stick during the roll open the cut window sooner / what aims the cut?** → [mechanics/roll-cut-thrust-floor.md](mechanics/roll-cut-thrust-floor.md)
- **Is the entry lean a lever on what happens LATE in a roll / how many frames does `m351C` survive / which engine computes the decay?** → [mechanics/roll-lean-decay.md](mechanics/roll-lean-decay.md)
- **What is the roll stab / the 49.22 single-frame lunge (CUT_F/CUT_A) that reaches a seam clip?** → [mechanics/roll-stab.md](mechanics/roll-stab.md)
- **What is the WALK stab (the no-roll seam clip) / how far does its lunge reach / why is the thrust delayed while an item is held?** → [mechanics/walk-stab.md](mechanics/walk-stab.md)
- **How do the big-reversal ground turns work (WAIT_TURN pivot / MOVE_TURN turn-around / SLIP skid)?** → [mechanics/ground-turns.md](mechanics/ground-turns.md)
- **What are the targeted ballistic hops (sidehop / backflip) / the A=roll vs L+A=hop mapping / the ESS aim-turn?** → [mechanics/ballistic-hops.md](mechanics/ballistic-hops.md)
- **How do I stop Link at an exact position (the C-up SUBJECTIVITY freeze) / B-cancel / why isn't the re-walk cold?** → [mechanics/precise-stop.md](mechanics/precise-stop.md)
- **From a standstill, fastest way into a roll chain / why hold L on frame 1 / why the frame-6 roll caps at ~25.9?** → [strategy/roll-launch.md](strategy/roll-launch.md)
- **Which partial stick magnitudes are live-valid in a land plan / why NEVER emit Y 192–254?** → [mechanics/precise-stop.md](mechanics/precise-stop.md). NB: this live-valid *stick-input* band is a different thing from the sim's [`Y171` partial-magnitude *regime*](model/land-sim.md#partial-magnitude-regime-y171-msd052) - don't conflate "partial stick" with "partial regime".

### Searching for an input plan (methodology)
- **My search's hits keep getting REJECTED by the confirm/replay step even though the state looks right - what prune am I missing? Which frame's proc does a queued button dispatch from?** → [strategy/search-prune-the-dispatch.md](strategy/search-prune-the-dispatch.md)

### Model - engine (core)
- **Why f32/ctypes / op-order / `_F32_PI` / `cM_rad2s` truncation / the baked cos+sin tables / which matrix-quat ops are FMA-fused?** → [model/fp-faithfulness.md](model/fp-faithfulness.md)
- **How does the J3D anim runtime work / the 42-joint skeleton / Hermite keyframes / world-space foot FK / `PSMTXQuat` / how does the toe become `speedF`?** → [model/anim-engine.md](model/anim-engine.md)
- **Why must an anim frame ctrl's `rate` be f32 / how can two rates that "are 1.1" advance to different frames / why does one ULP of anim frame matter?** → [model/anim-frame-is-f32.md](model/anim-frame-is-f32.md)
- **Why must the euler→quat half-angle be sign-extended / why isn't a negated quaternion bit-equivalent?** → [model/euler-quat-signed-half.md](model/euler-quat-signed-half.md)
- **Which position/lean is the model POSED from (before or after `posMove`) / why does a proc-init frame draw upright / why do ULPs of base matter?** → [model/draw-base.md](model/draw-base.md)
- **Does a drawn sword change the walk anims (WALKS/DASHS) / which anims does `getAnmData` swap / why can that move `speedF`?** → [model/equipped-anim-set.md](model/equipped-anim-set.md)
- **Does the anim keep running while Link is STOPPED / why is a re-walk's first step tiny / when does a stop reset the walk phase / what does low health change?** → [model/wait-stop-pose.md](model/wait-stop-pose.md)
- **How do I port a STATEFUL anim model into C without silently changing what it computes / what must a 0-ULP gate compare when the model has a long memory / why did my port land far below the ratio that named it?** → [model/porting-the-look-pair.md](model/porting-the-look-pair.md)
- **My fast engine is MISSING a branch the slow one has and it does not complain - what is that costing me, and how do I stop the gap lying to me? Where does a C step get its collision / keyframe data from?** → [model/the-branch-a-fast-engine-skips.md](model/the-branch-a-fast-engine-skips.md)

### Model - swim
- **Why f32 / the console cosine table / CHARGE_DISP_FACTOR / cold-start mRate?** → [model/swim-sim.md](model/swim-sim.md)
- **How does the planner search / why are mid-swim pumps off by default / the crossover decomposition / the speed-retention prune?** → [model/planner.md](model/planner.md)
- **What are the predict/ modules / the off-axis residual?** → [model/predictors.md](model/predictors.md)

### Model - land
- **How does the land sim accumulate position (f32) / the `Y171` partial regime / the 7 red ULP tests?** → [model/land-sim.md](model/land-sim.md)
- **How does floors mode follow a sloped floor (Phase G) / the zero atan cell / m35B8 / m35C4 (setStepsOffset) / field_0x030 / what does a floors anchor seed carry?** → [model/ground-model.md](model/ground-model.md)
- **How does the land planner reach a target (x,z) / the live-valid stick set / the C-up freeze to z=2000 / seam-clip vs RTA bars?** → [model/land-planner.md](model/land-planner.md)
- **How does the land SETUP FINDER work (human-consistent discrete moves → ranked input seqs) / why re-simulate instead of summing displacements / which moves are "blocks" / why isn't walking one?** → [model/land-setup-finder.md](model/land-setup-finder.md)
- **What are the targeted ballistic hops (sidehop / backflip) / the A=roll vs L+A=sidehop/backflip input mapping?** → [mechanics/ballistic-hops.md](mechanics/ballistic-hops.md)

### Provenance & open work
- **Was <bug> a physics issue or an artifact?** (bug#2, 554, off-axis, omega grid, cosine table) → [history/resolved-bugs.md](history/resolved-bugs.md)
- **What's still unresolved?** → [history/open-questions.md](history/open-questions.md)
- **How was the camera steering law derived (the live probe, the decomp watchpoint, the omega grid)?** → [history/camera-model-history.md](history/camera-model-history.md)
- **How was the swim + camera position predictor made bit-accurate (GAP 1 / GAP 2, the off-axis residual)?** → [history/camera-predict-history.md](history/camera-predict-history.md)
- **What was superseded about strobo / reboost / arrow, and which dead ends were ruled out?** → [history/reboost-strobo-history.md](history/reboost-strobo-history.md)
- **Which land-planner precision claims were overturned, and what physics constraint hid them?** → [history/land-planner-precision.md](history/land-planner-precision.md)
- **Which roll-stab seam-clip approaches were TRIED and ruled out?** → [history/seam-clip-dead-ends.md](history/seam-clip-dead-ends.md)
- **Which analytic seam-window shortcuts did the scanner try and reject?** → [history/seam-scanner-analytic-attempts.md](history/seam-scanner-analytic-attempts.md)
- **Why was the mass-proportional actor-push split wrong, and how was it corrected?** → [history/tetra-push-massprop-superseded.md](history/tetra-push-massprop-superseded.md)
- **My model is live-gated 0 ULP and still wrong - how? Why record the REGIME a capture covers next to the claim it proves?** → [history/co-centre-body-chn-twist.md](history/co-centre-body-chn-twist.md)
- **Two implementations of one quantity disagree and every capture I have is blind to the difference - how do I design the run that decides? Why can a code seam be a symptom rather than the bug?** → [history/co-centre-two-ports.md](history/co-centre-two-ports.md)
- **I widened a search's input alphabet on a measurement and the console refused a third of it - why can a gate on the model prove nothing about a DISPATCH?** → [history/aim-alphabet-whole-grid.md](history/aim-alphabet-whole-grid.md)

## Page template (for contributors)

```
# Title
**Answers:** <the questions this page answers, in plain language>
**Status:** validated | approximate | open  (+ how)
**Source:** decomp <file:line> · live <date> · History: <link>
---
<definition → formula → constants (LINK to reference/constants.md, don't restate) → validation>
## See also
```

Keep pages **small and single-topic** (one Read should answer the question). Put dated narrative and
superseded findings in `history/`, not in the truth pages. One canonical value per constant - link
to [constants.md](reference/constants.md) instead of restating numbers.

If a topic has an **unresolved verdict**, give it a short `## Open question - <current status>`
section *in the truth page* (state the current best answer + "unproven"), and link to `history/` for
the provenance. The definitive *current* answer must be reachable from the truth layer - not only
from a `status: historical` page. (Validated by the doc-eval: weak agents were told to prefer
non-history pages, so an answer that lives only in history is effectively hidden.)

The KB is regression-tested by a bounded weak-agent eval - the question bank + run protocol under
[`_eval/`](_eval/) (Tier-A retrieval / Tier-B comprehension, run by fanning out weak sub-agents;
agents must never read `_eval/` itself, the answer key).
