# Documentation eval — question bank

Test questions covering the KB — game mechanics, sim/planner model, strategy, reference — plus a
**control / harness-workflow** category (driving Dolphin). Each entry: the question, a graded
**reference answer** (the key fact a correct answer must contain), the **page** that should own it,
and a **source**. `hazard: true` marks questions where an *earlier* conclusion was later overturned
(or is an intuitive-but-wrong trap) — the highest-value checks, because a stale doc / a wrong
instinct would confidently give the WRONG answer.

The eval runs each question in two modes:
- **Tier A (retrieval):** agent gets the question only and must *find* the answer within a tool-call
  budget. Failure = a discoverability gap (fix the index/structure).
- **Tier B (comprehension):** agent gets only the page named below and must answer from it. Failure
  = the page is wrong/incomplete (fix the content).

## Categories & scope

- **Physics / sim / strategy** (most entries): answers live under `knowledge/`. Restrictions for
  these eval agents: read only under `knowledge/`; never open `.py`; never touch Dolphin; hard
  tool-call budget; if not found, report `found:false` and stop (no goose chase).
- **Never let an eval agent read `knowledge/_eval/`** (this bank IS the answer key). A retrieval
  agent that greps and opens `_eval/questions.md` will parrot the reference answer and score a false
  pass — observed in practice. Instruct every Tier-A agent to ignore any `_eval/` hits.
- **`category: control`** (Dolphin / harness workflow): the answer lives OUTSIDE `knowledge/` — in
  `../tools/DOLPHIN_CONTROL.md`, `harness/`, or `tests/dolphin/`. Tier-A retrieval scope is widened
  to repo **docs** (`.md`) anywhere under `speedrunning/`. The specific weakness being probed: does
  the agent land on `DOLPHIN_CONTROL.md` (the single source of truth), or does it start reading `.py`
  implementation to reverse-engineer commands? **Opening a `.py` file to answer a control question is
  itself a discoverability FAIL** — record `opened_code: true`. Still never *run* Dolphin during the
  eval.

Every entry stays graded against the reference answer; still report `found:false` when the answer
can't be located within budget.

---

```yaml
- id: turn-threshold
  question: "What is the angle threshold for an instant turnaround (charge snap), and when does Link turn gradually instead?"
  answer: "Snap fires when the stick points >135° (0x6000) from current facing — i.e. within 45° of straight-back. Beyond that budget he turns gradually at ~7°/frame."
  page: mechanics/turnaround.md
  source: thread-3

- id: turn-units
  question: "In the turnaround decomp, what angles do 0x6000 and 0x2000 correspond to?"
  answer: "0x6000 = 135° (DIR_BACKWARD snap threshold); 0x2000 = 45° (left/right). Units: 0x10000 = 360°."
  page: reference/constants.md
  source: thread-3

- id: turn-reorient
  question: "Can you reorient the charge axis ~90° with a single instant snap? If not, how?"
  answer: "No — a single snap only fires for targets >135° off facing, so a ~90° reorient needs walking facing through 2–3 intermediate diagonal snaps (each charges)."
  page: mechanics/turnaround.md
  source: thread-3

- id: arrow-rate-18
  question: "Charging an arrow at 18° tilt off the back axis — what charge rate, and roughly what fraction of full?"
  answer: "charge_rate = -3·cos(2·18°) ≈ -2.43 (~81% of -3). Live measured -2.44."
  page: mechanics/arrow.md
  source: thread-4

- id: arrow-drift
  question: "What is the per-frame cross-track drift while arrow swimming at tilt α?"
  answer: "cross_drift = displacement · sin(α) per frame (accumulates toward the target)."
  page: mechanics/arrow.md
  source: thread-4

- id: arrow-tipover
  question: "What is the tilt limit before arrow swimming breaks, and what happens past it?"
  answer: "Usable to α ≈ 20° (Xbias ≈ 190). Past it the backward snap dies → forward release → speed LOSS (tip-over). Same as the 45° turnaround budget."
  page: mechanics/arrow.md
  source: thread-3,4

- id: arrow-spinup
  question: "What is the arrow spin-up cost?"
  answer: "~2 frames — the first non-snap forward frames each lose ~+3/fr before the 0↔180 swing locks in."
  page: mechanics/arrow.md
  source: thread-14

- id: arrow-stickdist
  question: "When you tilt the arrow stick, does mStickDistance change?"
  answer: "No. Tilt changes the cosine (snap angle), not the magnitude; mStickDistance stays capped at 1 / closed-form /54."
  page: mechanics/arrow.md
  source: fresh-negative

- id: arrow-pays
  question: "Does arrow swimming actually save time over a straight cruise at 200k?"
  answer: "Likely NO — offline it loses ~2–4 frames (early drift doesn't cover prefix overhead), and it is NOT yet validated from a cold start (entry-tax + x598 unmodeled). Open question."
  page: history/reboost-strobo-history.md
  source: thread-14
  hazard: true

- id: strobo-speeds
  question: "At what potential speeds do the stroboscopic bands occur?"
  answer: "≈ -794 (k=1) and ≈ -1630 (k=2), air-dependent (where the ESS anim increment ≈ 23·k)."
  page: mechanics/strobo.md
  source: thread-16

- id: strobo-legacy
  question: "Is the strobo band exactly at -1650 (the commonly cited number)?"
  answer: "No — that legacy figure ignores the air dependence. The band is ≈ -1630 at air 900 and drifts with air; -850/-1650 are the same bands, off by the air term."
  page: mechanics/strobo.md
  source: fresh-negative
  hazard: true

- id: strobo-air-drift
  question: "As air depletes during a long swim, does the strobo band move to higher or lower speed?"
  answer: "Higher speed — the air term shrinks, so reaching increment = 23·k needs a larger |v|. The band drifts up under you."
  page: mechanics/strobo.md
  source: thread-16

- id: reboost-saves
  question: "Does reboosting in a strobo band save time?"
  answer: "Yes, but ONLY when phase-triggered (fire as anim drifts off the peak) — up to +15%. A fixed cadence loses."
  page: strategy/reboost.md
  source: thread-6
  hazard: true

- id: reboost-fixed
  question: "Should you reboost on a fixed cadence (e.g. every 20 frames)?"
  answer: "No. Blind fixed cadence loses (-2% band-2, -8% band-1) — it fires at random anim phases and pays the turnaround tax without aiming the drift."
  page: strategy/reboost.md
  source: thread-6
  hazard: true

- id: reboost-size
  question: "How big should a maintenance reboost be, and when do you fire it?"
  answer: "A 2-frame up-down (minimal), fired when anim drifts off the top of the peak (anim ~20-23/0-2), to re-park it at the peak. ~4 frames only to recover an anim that slid deep."
  page: strategy/reboost.md
  source: thread-6

- id: reboost-transfer
  question: "Does an optimal reboost frame schedule transfer to a nearby seed (e.g. speed ±5)?"
  answer: "No — the frame numbers shift with the seed (band drifts with speed/air). Stable across seeds: ~3 minimal 2-frame boosts near the peak per 200 fr. Re-solve per exact state."
  page: strategy/reboost.md
  source: thread-13

- id: reboost-cost
  question: "Why does each reboost cost a few frames of forward progress?"
  answer: "The full-deflection charge triggers an instant 180° turnaround snap (one ~dead frame + a reversed frame), the per-boost turnaround tax."
  page: strategy/reboost.md
  source: fresh-crosslink

- id: const-deadzone
  question: "What is the stick radial dead-zone constant?"
  answer: "15 raw units (removed before any input registers)."
  page: reference/constants.md
  source: fresh

- id: const-divisor
  question: "What is the main-stick divisor?"
  answer: "54 (mPosX = stickX/54 after dead-zone removal)."
  page: reference/constants.md
  source: fresh

- id: const-wraps
  question: "What are the animation wrap points for ESS (swimming) and neutral (swim-wait)?"
  answer: "End_swim (ANM_SWIMING) = 23; End_wait (ANM_SWIMWAIT) = 26."
  page: reference/constants.md
  source: fresh

- id: const-x598
  question: "What is x598 and where does it come from?"
  answer: "598 = End_wait · End_swim = 26·23; the neutral→ESS anim-scramble multiplier. 598 ≡ 0 (mod 23), so only the fractional entry phase matters — which is why it's hypersensitive."
  page: reference/glossary.md
  source: thread-5

- id: afdrag-formula
  question: "What is the head-bob (animation-frame) drag formula on true speed?"
  answer: "af_drag = 0.6·v + 0.4·v·|cM_scos(π·anim/23)| (then divided by 1 + 0.35·getSwimTimerRate). Near anim 0/23 keeps ~100%, near 11.5 keeps ~60%."
  page: reference/constants.md
  source: thread-17
```

## Charging, ESS, decay, neutral, animation, pumps, camera, ocean, air, land, dips

```yaml
- id: charge-nets-zero
  question: "Does continuous back-and-forth charging make net forward progress on its own? Roughly how far do 272 continuous charges from a cold start net?"
  answer: "Almost none — each charge flips facing 180° so consecutive frames move in opposite world directions and nearly cancel. 272 continuous charges from a cold start net only ~390 units."
  page: mechanics/charging.md
  source: "charging.md 'Charging nets ~zero progress on its own'"

- id: charge-phased-progress
  question: "How can you net real forward progress *during* the speed build (short of arrow swimming), and how much better is it than plain charging?"
  answer: "Head-bob-phased charging: break the charge into bursts separated by single ESS frames so toward-target charges land on the head-bob peak and away frames on the trough. On the 200k cold-start plan this nets ~4948 progress vs ~390 for plain charging."
  page: mechanics/charging.md
  source: "charging.md head-bob-phased charging"

- id: ess-raw110-optimal
  question: "Why is raw stick value 110 (offset 18) the optimal ESS deflection rather than 111 or 112?"
  answer: "110 is the minimal deflection that still clears the swim-move gate mStickDistance > 0.05: (18-15)/54 = 0.0556 > 0.05. 111/112 only look 'better' in the offline sim — they are artifacts; probe against the decomp gate."
  page: mechanics/ess.md
  source: "ess.md 'raw=110 is provably optimal'"

- id: ess-diagonal-efficiency
  question: "Is diagonal ESS more or less efficient than cardinal ESS, and by how much? What are the two decay constants?"
  answer: "Diagonal is ~5% MORE efficient: decay -0.1571 vs cardinal -1/6 (~ -0.1667). The octagonal dead-zone geometry removes slightly more (effective magnitude 0.0524 vs 0.0556)."
  page: mechanics/ess.md
  source: "ess.md 'Diagonal ESS (decay -0.1571, ~5% more efficient)'; constants.md"

- id: decay-saturation-point
  question: "At what stick value does potential-speed decay saturate to a flat -3, and was the community '128,61+' figure right?"
  answer: "Saturates to exactly -3.0 by off >= 70 (stickY <= 58). The community '128,61+' note was off by ~1 unit — saturation actually begins at 128,59."
  page: mechanics/decay-curve.md
  source: "decay-curve.md saturation"
  hazard: true

- id: decay-onaxis-partials
  question: "Do on-axis partial-magnitude holds (deeper than ESS but not full charge) save frames over plain ESS?"
  answer: "No — empirically 0 frames saved; deeper-than-ESS only bleeds speed. The build-vs-progress tradeoff is gated by stick DIRECTION, not magnitude. The untested lever is off-axis (arrow swimming)."
  page: mechanics/decay-curve.md
  source: "decay-curve.md on-axis partials"

- id: neutral-lowspeed
  question: "Is neutral swimming a flat -2/frame at all speeds? What happens below |v| = 25?"
  answer: "No — it's cLib_addCalc-based. Flat -2 only at |v| > 100; proportional (~0.02*|v|) in 25 < |v| < 100; below |v| = 25 it snaps toward 0 at 0.5/frame. Only the high-speed -2 case matters for 200k+ plans."
  page: mechanics/neutral.md
  source: "neutral.md low-speed correction"

- id: neutral-exit-phase
  question: "When exiting ESS into neutral, how much speed do you keep, and at what animation phase should you release?"
  answer: "Speed kept = af_drag(potential, release_anim). Release near anim 0/23 keeps ~100%; releasing mid-cycle (~11.5) costs up to ~40%. Rule: exit ESS when animation is near 0/23."
  page: mechanics/neutral.md
  source: "neutral.md ESS->neutral exit table"

- id: anim-ess-increment
  question: "What is the per-frame ESS animation-frame increment formula?"
  answer: "increment = |velocity|/36 + 3/5 + (1 - (air+1)/900). Speed term /(2*maxSpeed=36), 3/5 base, and the air term (getSwimTimerRate). Higher speed and lower air both speed the cycle."
  page: mechanics/animation.md
  source: "animation.md 'Animation frame'"

- id: anim-legacy-airdrag
  question: "Is the legacy separate 'air_drag = 18000*v/(24300 - 7*air)' term correct?"
  answer: "No — it is ~0.04% low. The exact form is a single denominator /(1 + 0.35*getSwimTimerRate) on the head-bob numerator, not a separate air-drag factor."
  page: mechanics/animation.md
  source: "animation.md legacy air term note"
  hazard: true

- id: pump-minimum-length
  question: "What is the minimum useful ESS-pump length out of neutral, and why does a 1-frame pump do nothing?"
  answer: "Minimum effective pump = 2 frames. The first ESS-input frame stays in state 54 (pure neutral, -2, no benefit) — it only queues the 54->55 transition; the -1/6 ESS decay starts on frame 2."
  page: mechanics/pumps.md
  source: "pumps.md '1-frame entry tax'"

- id: camera-world-angle
  question: "How does camera yaw (csangle) enter the world travel-angle formula while swimming?"
  answer: "world_travel_angle = stick_angle + csangle + 0x8000 (halfword, 0x10000 = 360deg). The stick is camera-relative, so rotating the camera rotates Link's entire travel axis."
  page: mechanics/camera.md
  source: "camera.md 'Why the camera matters'"

- id: camera-speed-independent
  question: "Does Link's speed affect the C-stick camera-rotation rate (omega)?"
  answer: "No — omega_cmd is speed-independent (verified). It is a 2-D lookup over (csx,csy); full deflection saturates at +-3.0 deg/frame, smoothed with factor k = 0.5."
  page: mechanics/camera.md
  source: "camera.md omega_cmd lookup"

- id: ocean-sploosh
  question: "What is a sploosh zone and what constraint does it put on a route?"
  answer: "A sparse flat-ocean quadrant where the ocean-surface collision hasn't loaded; entering too fast makes Link fall through to the sea floor (lost swim). Must be approached below a max-speed threshold or routed around — a quadrant-level routing constraint, not per-frame physics."
  page: mechanics/ocean-environment.md
  source: "ocean-environment.md 'Sploosh zones'"

- id: ocean-one-island-loaded
  question: "How many islands have their collision loaded at once, and what does that imply for mid-swim air refills?"
  answer: "Only ONE island's collision is loaded at a time (load timing hard to predict). So a target island usually won't finish loading before you arrive at superswim speed — which is why mid-swim refills are rare and refills cluster at the start."
  page: mechanics/ocean-environment.md
  source: "ocean-environment.md single-island load"

- id: air-touch-land
  question: "What happens if Link touches land for even one frame during a refill skim?"
  answer: "He loses ALL speed. The refill is a precise skim: close enough to the land/water boundary of a loaded island to trick a refill, never close enough to touch."
  page: mechanics/air-refill.md
  source: "air-refill.md touch-land penalty"

- id: air-refill-launch-pattern
  question: "Where do the vast majority of superswim air refills happen, and at roughly what distance?"
  answer: "~90% of swims refill at the very START (distance ~ 0), skimming the already-loaded launch island right after charging. Mid-swim refills exist but are rare (target island won't load in time)."
  page: mechanics/air-refill.md
  source: "air-refill.md 'the launch-island pattern'"

- id: land-walk-constants
  question: "What are the on-ground walk cap, acceleration, release deceleration, and input latency?"
  answer: "Run cap mMaxNormalSpeed = 17; accel = +3.5/frame; release decel = -2.5/frame (then a cLib min-step snap tail); input latency = 2 frames on BOTH press and release."
  page: mechanics/walk-run.md
  source: "land-movement.md Values table"

- id: land-no-walk-plateau
  question: "Is there a walk-before-run speed plateau (~5.0) before Link reaches the run cap on flat ground?"
  answer: "No — full stick accelerates straight to the 17 cap with no plateau. The apparent ~16-frame 5.0 plateau in an early capture was a phantom FRONT ROLL (state 30) from a stray button, not a mechanic."
  page: mechanics/walk-run.md
  source: "land-movement.md walk acceleration"
  hazard: true

- id: land-ebs-facing-not-travel
  question: "During an extended brakeslide, is speed preservation governed by travel direction or facing?"
  answer: "Facing, not travel. ESS steering FACING toward csangle collapses decay to ~ -0.001/frame (held almost forever); facing toward csangle+180deg engages the -2.5/frame brake. In the decoupling test both had ~identical travel but opposite outcomes."
  page: mechanics/brakeslide-ebs.md
  source: "land-movement.md 'Camera-relative speed preservation'"

- id: land-roll-speed
  question: "What speed does a forward roll set, and what does a full-run roll reach?"
  answer: "mNormalSpeed = clamp(pre-roll speedF*1.5 + 0.5, 5.0, 26.0), set once at entry. A full-run roll (speedF 17) hits the 26 cap — well above the walk cap of 17 — which is why rolling is the workhorse ground-cover tech."
  page: mechanics/roll.md
  source: "land-movement.md 'Roll (FRONT_ROLL)'"

- id: land-partial-stick-band
  question: "Which partial stick magnitudes are safe for an offline land search, and which must never be emitted?"
  answer: "Restrict to Y <= 191 (msd <= 0.889) plus true full (128,255); NEVER emit Y in [192,254] — the sim over-reads msd vs live PADClamp there (e.g. (128,196) sim v=16.38 vs live 15.76), so plans diverge live."
  page: mechanics/precise-stop.md
  source: "land-movement.md 'Live-valid stick magnitudes'"
  hazard: true

- id: neutral-dip-what
  question: "What is a neutral dip and why does it save speed?"
  answer: "A 1-frame neutral tap inserted mid-ESS-cruise (inverse of a pump). Taken at the head-bob peak (|cos|=1) it sets v = af_drag lossless AND skips the flat -2 neutral decay that frame — netting ~ +0.833 saved vs two flat-neutral frames."
  page: strategy/neutral-dip.md
  source: "neutral-dip.md 'What it is'"
```

## Model — engine, swim, land, planner, predictors (+ resolved/open provenance)

```yaml
- id: fp-f32-pi
  question: "Why must a pi used inside a console cos/sin argument be single-precision (_F32_PI), not math.pi?"
  answer: "The compiler emits f32_expr*M_PI as an lfs + fmuls (single), so the arg is f32(f32(pi)*x) with f32(pi) ~1 ULP above double pi. That 1 ULP flips a truncated cos-table cell at knife-edge angles (was the pump-300k desync); order is f32(anim/23)*pi, not (pi*anim)/23."
  page: model/fp-faithfulness.md
  source: "fp-faithfulness.md '_F32_PI'"

- id: fp-console-cos-table
  question: "Does using x86 math.cos instead of the console cosine table matter for bit-exactness?"
  answer: "Yes — a PowerPC-libm-built cosine table differs from an x86 recompute at 2964/4096 entries (max 4.17e-7). x598-amplified, that 1 ULP was a 0.07 speed jump at pump exits, so the live-dumped 4096-entry table (index >> 4, no interp) must be used."
  page: model/fp-faithfulness.md
  source: "fp-faithfulness.md 'Console cosine and sine tables'"

- id: anim-no-foot-ik
  question: "Is there a foot-IK ground-snap on the planted foot on flat ground?"
  answer: "No. On flat ground every leg-angle Zrot is 0, so jointCB1 reduces to a pure matrix rebuild that is bit-exact to the FK (0 ULP). The earlier 'ground-snap on the planted foot' guess was wrong."
  page: model/anim-engine.md
  source: "anim-engine.md 'jointCB1 foot rebuild (not IK)'"
  hazard: true

- id: swim-coldstart-mrate
  question: "When seeding a cold-start swim, can the seed anim-rate (mRate) be recomputed from the savestate snapshot?"
  answer: "No — mRate_seed carries pre-seed air history and must be LOGGED live; it cannot be recomputed from a snapshot. Also seed the FULL-PRECISION anim: a 4-digit-rounded seed drifts through the x598 scramble into a completely different swim (1408 vs 3004)."
  page: model/swim-sim.md
  source: "swim-sim.md 'Cold-start seeding (the mRate rule)'"

- id: planner-frontier-nonmonotone
  question: "Is a larger search frontier always at least as good in the swim planner? What's the recommended default?"
  answer: "No — the A* rank (_hcost) is NOT admissible, so frontier->frames is non-monotone: a larger frontier can give a WORSE plan (400k = 812 at mf~2000 but 814 at mf=8000). Default the quality frontier to ~2000 and sweep {1000,2000,4000}."
  page: model/planner.md
  source: "planner.md 'mf=2000 is the sweet spot (non-monotone!)'"
  hazard: true

- id: planner-balloon
  question: "What are the key physics numbers of a balloon swim (landing + resurface + air)?"
  answer: "On landing speed x0.75 (mNormalSpeed *= 0.75f), then a 27-frame resurface at -3/frame, plus a forced air refill to 900. Decomp-confirmed."
  page: model/planner.md
  source: "planner.md 'Balloon swim'"

- id: predictor-stick-grid
  question: "Why does the sim use a live-captured stick-angle grid instead of the decomp's atan2 closed form?"
  answer: "A pure decomp port (mAngle = 10430.379*atan2f(x,-y)) is exact at non-boundary cells but diverges from live Dolphin at 17.6% of cells (Dolphin's byte->analog mapping differs from SDK PADClamp at the deadzone boundary/octagon). The sim validates against Dolphin, so the live capture is authoritative."
  page: model/predictors.md
  source: "predictors.md 'Why a live stick-angle grid'"

- id: landsim-f32-accumulation
  question: "Should land position be accumulated in f64 for maximum precision?"
  answer: "No — the game stores pos.x/z as f32 and re-rounds every frame, so the sim must accumulate in f32 too. An f64 running sum is MORE precise than hardware and drifts ~2.5 ULP over a ~115-frame walk — the wrong direction for float-exact work."
  page: model/land-sim.md
  source: "land-sim.md 'Land position accumulates in f32'"
  hazard: true

- id: bug2-pipe-artifact
  question: "Dense back-to-back pump plans reached only ~127k live vs the sim's ~300k. Was this a physics/modeling error?"
  answer: "No — it was the advanceseq pipe's FrameAdvance listener jittering SI polls on dense transitions (bug#2). A cleanly authored DTM plays bit-exact (cruise_pump300k net 300,816). Dense pump plans are valid."
  page: history/resolved-bugs.md
  source: "resolved-bugs.md 'bug#2'"
  hazard: true

- id: arrow-resolved-exhaustive
  question: "Is the arrow-swimming time question still open/unproven, or has it been resolved?"
  answer: "RESOLVED (2026-07-02): no, it does not save time. An exhaustive offline insertion sweep (134 cells) found ZERO wins; best case loses +4 frames, worsening the later/longer you arrow."
  page: history/open-questions.md
  source: "open-questions.md arrow resolution"
  hazard: true

- id: multipump-precision-resolved
  question: "Is there a modeling precision floor that prevents pump-heavy plans from being validated?"
  answer: "No longer — the '~1e-4 per-entry anim oscillation' was a double-vs-single-pi bug in the release cos, resolved 2026-07-02 with _F32_PI. Pumped plans now DTM-verify bit-exact at 50k/100k/200k/300k/400k. Remaining blocker to flipping allow_pump default is frontier saturation, not precision."
  page: history/open-questions.md
  source: "open-questions.md 'Multi-pump precision floor'"
  hazard: true

- id: afdrag-divisor-omitted
  question: "Is the main swim sim's displacement (af_drag / true_disp) bit-exact?"
  answer: "No — sim.af_drag computes 0.6*v + 0.4*v*|cM_scos| but DROPS the console's /(1 + 0.35*getSwimTimerRate) divisor, so net/distance is a validated approximation only. v/anim/air/state ARE bit-exact (af_drag never feeds them). The exact form exists in predict/swim_exact.disp_magnitude."
  page: history/open-questions.md
  source: "open-questions.md 'Main-sim displacement omits the head-bob divisor'"
  hazard: true
```

## Control / harness workflow (driving Dolphin)

Scope: answers live OUTSIDE `knowledge/` — in `../tools/DOLPHIN_CONTROL.md`, `harness/`,
`tests/dolphin/`. Tier-A retrieval is widened to repo `.md` docs anywhere under `speedrunning/`.
The weakness probed: does the agent find `DOLPHIN_CONTROL.md`, or start reading `.py`?
**Opening `.py` to answer = discoverability FAIL (`opened_code: true`).** Never *run* Dolphin.

```yaml
- id: ctl-how-control-dolphin
  question: "I need to control a running Dolphin (read game memory, advance frames, send inputs). Where do I start, and what should I NOT do first?"
  answer: "Read ../tools/DOLPHIN_CONTROL.md FIRST — the single source of truth for dolphin_mem.py, opening with an 'I want to... -> command' jump table. All control is `python dolphin_mem.py <command>`. Do NOT start by reading the Python implementation (dolphin_mem.py / ControlPipe.cpp) to reverse-engineer commands."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md header + jump table; tww_sim/CLAUDE.md HARD RULE"
  category: control
  hazard: true

- id: ctl-test-input-sequence
  question: "I want to test a simple sequence of controller inputs on the running game. How?"
  answer: "For a dense per-frame input list submit one advanceseq pipe call (the only race-free way to replay dense charge dips). For a single open-loop hold use `seq \"sx,sy,frames\"` or advancewith. For a trustworthy dense check, author a clean DTM and play it via harness/dtm/run_dtm.py."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Batch sequence — advanceseq; #Frame advance"
  category: control

- id: ctl-jp-symbol-map
  question: "Where is the TWW JP symbol/address map, and how do I look up an address by name?"
  answer: "The JP watch/symbol reference is tww_jp_ref.json in ../tools/ (built by build_tww_ref.py). Search it with `python dolphin_mem.py name <substring>`. If a value isn't there or in NAMED_ADDRS, fall back to the tww-python-scripts library and the 'TWW - JP -cleaner.dmw' watch file — then add it to NAMED_ADDRS."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Watch entry lookup, #Finding addresses"
  category: control

- id: ctl-breakpoints
  question: "How do I set a code breakpoint, run into it, and read registers over the pipe? What must I remember afterward?"
  answer: "`python dolphin_mem.py bp <addr> [cond=<expr>]` sets a code breakpoint (mbp for memory watchpoints); resume, poll status until 'paused', then regs [fpr] / reg <name>; stepin|stepover|stepout to single-step. CRUCIAL: clear when done (bp clear / mbp clear) — a breakpoint left armed halts EVERY run, so a later advanceseq/test stalls at the hit."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Debugging"
  category: control
  hazard: true

- id: ctl-write-dtm-from-plan
  question: "I have a plan's input sequence. How do I turn it into a .dtm movie?"
  answer: "Use harness/dtm/ — make_dtm.py expands a swim seq to sticks and calls tools/dtm_make; run_dtm.py authors a clean DTM from a seq (seq=NAME under fixtures/, or sticks=<csv>) and plays it. Over the pipe directly: record start -> boot <game> (records from frame 0) -> record stop path=run.dtm."
  page: tests/dolphin/README.md
  source: "harness/README.md dtm row; tests/dolphin/README.md #run_dtm.py; DOLPHIN_CONTROL.md #Movie recording"
  category: control

- id: ctl-advanceseq-vs-dtm
  question: "When should I drive inputs with advanceseq vs. author and play a clean DTM?"
  answer: "advanceseq (the pipe) is fast and needs no reboot, but jitters SI polls on dense charge dips and can SLIP inputs (bug#2) — a failure on a dense charge/pump/arrow plan may be a delivery artifact, not a real sim error. A clean DTM via run_dtm.py is the TRUSTWORTHY path (bit-identical); use it to gate dense plans or whenever the pipe disagrees."
  page: tests/dolphin/README.md
  source: "tests/dolphin/README.md #Which path: pipe vs clean DTM"
  category: control
  hazard: true

- id: ctl-set-test-speed
  question: "To test at a specific potential speed (e.g. a strobo band), should I charge there with `superswim N`?"
  answer: "No — prefer writing the speed directly: `writename potential_speed -794` (or -1630). Charging with superswim is slow AND depletes air, which shifts the strobo band. writename works for any NAMED_ADDRS entry, placing an exact (speed, air, anim) point instantly."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Setting potential speed directly"
  category: control
  hazard: true

- id: ctl-teleport-sploosh
  question: "Can I teleport Link to a clean test slate by writing link_x/link_y/link_z?"
  answer: "Not by changing Y — a Y write makes Link 'sploosh': he dives (state 39), Y plunges, and potential_speed RESETS to 0; a state saved mid-sploosh is useless. A pure X/Z teleport at the SAME Y does not sploosh. Recipe: teleport, frame-advance neutral until state==54, then rewrite only X/Z."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Teleport / clean-slate procedure"
  category: control
  hazard: true

- id: ctl-air-sync-not-trustworthy
  question: "Over the pipe, can I confirm an input landed each frame by checking air_live == air_sim?"
  answer: "No. A dropped input is invisible to an air-sync check — when an override doesn't land, the poll reuses the previous frame's stick but air still decrements 1, so air stays aligned even on a corrupt frame. Validate delivery with a race-free advanceseq (or a clean DTM), not by trusting air alignment."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Why the override is applied on the emu thread (air-sync note)"
  category: control
  hazard: true

- id: ctl-loadstate-safe
  question: "Which command loads a savestate, and why not the other one?"
  answer: "Always `loadstate <slot>` — it pauses the game first, then loads. Never `savestate load` directly: if the emulator is running during the load the game processes frames on stale inputs (underwater, Link drowns / acts on stale sticks)."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Savestates + 'Always pause before loading'"
  category: control

- id: ctl-boot-while-running
  question: "How do I switch games or play a movie while a game is already running via the pipe?"
  answer: "You can't cleanly — with a game running, Dolphin's 'Confirm on Stop' dialog blocks the swap and a pipe-driven stop+reboot can wedge the instance. No reliable pipe workaround: kill the Dolphin process and relaunch, then boot/play into the fresh instance."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md #Game control ('only work cleanly from a stopped state')"
  category: control
  hazard: true

- id: ctl-anchors-not-slots
  question: "For repeatable live sim-vs-Dolphin validation, should I use Dolphin save slots as the starting state?"
  answer: "No — use test-owned savestate ANCHORS (tests/dolphin/anchors/<test>@<isokey>.sav, minted by harness/dtm/capture_anchor.py), not save slots. Slots get overwritten and their facing/csangle drift, breaking repeatability."
  page: tests/dolphin/README.md
  source: "tests/dolphin/README.md #Anchors; DOLPHIN_CONTROL.md #Test slates / anchors"
  category: control
  hazard: true

- id: ctl-check-dolphin-loaded
  question: "Before reading game memory / advancing frames, how do I confirm Dolphin is running with a game loaded — and what works without a game?"
  answer: "Run `python dolphin_mem.py status` (prints state + current frame). Memory reads/writes, frame advance, savestates, and input all NEED a game running; only status, boot, listgames, and script controls work at the game-list screen with no game. Boot-and-block with `boot <path> wait`. Check state first rather than assuming a game is up."
  page: ../tools/DOLPHIN_CONTROL.md
  source: "DOLPHIN_CONTROL.md header + #Emulator state (status) + jump table"
  category: control

- id: ctl-where-is-exe
  question: "Where is the Dolphin .exe, and how does the test harness find/launch it (rather than me starting Dolphin by hand)?"
  answer: "Machine paths — ISO dir, Dolphin exe, slate — come from a gitignored dolphin.local.json at the repo root (copy dolphin.local.example.json); env vars TWW_ISOS_DIR / DOLPHIN_EXE / TWWGZ_SLATE override it. run_tests.py needs no manual setup: harness/dolphin_env.py ensure_running reuses a running instance or launches the pipe-enabled Release build and boots the iso. Pass warmup=0 to manage Dolphin yourself."
  page: tests/dolphin/README.md
  source: "tests/dolphin/README.md #Requirements"
  category: control

- id: ctl-cdown-camera-freeze
  question: "When I hold L to target-walk (or measure steady-state decay at speed), what must I do with the C-stick every frame, and what breaks if I don't?"
  answer: "Hold C-stick DOWN (substickY=0) on every hold/targeting frame. Otherwise the auto-camera swings/flips, moving csangle — and because stick->direction is camera-relative, that moves Link's X off-axis and drifts the run off-model (or flips a fast swim's camera). csy in {0,128} freezes the sim's CameraManual, so C-down keeps you in-model. Only skip it if steering the camera IS the intent. Note: C-DOWN = camera-freeze/free-cam; C-UP (substickY=255) is the separate speed-cancel/instant-freeze — don't confuse them."
  page: mechanics/precise-stop.md
  source: "land-movement.md 'L-target forward' (Hold C-DOWN...); DOLPHIN_CONTROL.md #Measuring steady-state stick decay"
  category: control
  hazard: true
```

## Fresh questions to add as more topics migrate (not pilot-scoped)

Kept here so they aren't lost: cosine-table ULP count (2964/4096), neutral decay below |v|=25
(cLib_addCalc snap), DTM rows-per-frame (8), mRate non-recomputability, off-axis residual cause
(stick table dump path). These belong to model/reference pages built during the full migration.
