# The route planner & optimizer

**Answers:** How does the planner search? What's the objective? Why are mid-swim pumps disabled?
Why the crossover (build + cruise) decomposition? What's the balloon-swim option?
**Status:** validated (live-confirmed plans, frame-exact via DTM).
**Source:** `tww_sim/swim/plan.py`, `tww_sim/swim/optimize.py`; the legacy C# `SwimEnvironment`/PSO.

---

## Objective: minimum frames to a destination

The TAS objective is **minimum frames to reach a fixed target distance D**, not max distance over a
fixed window. This shapes the endgame: near D you should NOT boost (no frames to recoup the
[turnaround](../mechanics/turnaround.md) tax), and the optimum wants to finish in
[neutral](../mechanics/neutral.md) (drag-free) for the last stretch — exiting at a good
[head-bob phase](../mechanics/animation.md).

## Search

- **Beam search** over the per-frame {ESS, charge} decision space (`optimize.py`), keeping
  anim-phase diversity so a state that just paid a boost (lower x, better anim) isn't pruned by raw
  x. Anim bucket = 0.03.
- **`air` is in the dominance key** (`optimize.sig()`). Without [refill](#air-refill--the-far-swim-regime-sim-model),
  every action decrements air by 1, so a whole DP layer shares one air value — air is a per-layer
  constant and including it in the key is a no-op (bucketing byte-identical; all baselines unchanged,
  110 pytest pass). **With** refill, air is pinned at [900](../reference/constants.md#air) inside the
  refill zone, so two states in the same layer that *left* the refill zone at different frames carry
  different air and different futures. Omitting air would then unsoundly **merge** them, so it must be
  in the key.
- **Air-budget (drowning) enforcement** (`plan_min_frames(..., allow_drown=False)`, default): any
  successor with `air < 0` is dropped. The sim's `step()` is a pure physics stepper with no `air ≤ 0`
  check — air just goes negative and it keeps computing — so without this the planner emits far-dest
  "solutions" that actually drown (a non-refill 500k "reached" with `end_air = −7`, impossible). With
  enforcement such dests correctly return not-reached (`frames=None`), the signal that the swim needs
  a [refill](#air-refill--the-far-swim-regime-sim-model). Non-refill ≤ 400k are unaffected (they
  arrive with air to spare, e.g. 400k `end_air ≈ 84`).
- **Speed-retention prune** (`plan_min_frames`, default `speed_gate=0.98`): drop any successor that
  keeps < 98% of the parent's `|v|`, relaxing to 90% (`speed_gate_end`) inside the last ~40 estimated
  frames so the terminal neutral dash still enters. Only speed LOSSES are pruned — charge/reboost
  build `|v|`, so the only frames it touches are off-peak neutral-dip/exit `af_drag` frames. Loss-free
  for the min-frames objective (retained speed compounds over remaining frames, so a big one-frame
  dump only pays near the end); validated byte-identical on the golden suite and cruise 200k/400k/500k
  + a full build+reboost, at 3–7× fewer nodes on cruise. Set `speed_gate=0` to disable.
- The legacy C# tool used Particle Swarm (`Omega=0.7627, Phi_G=1, Phi_P=3`) over `[chargeTime,
  essTime]` with neutral time computed analytically; PSO is overkill for this low-dimensional,
  monotonic-ish space — beam/closed-form is more reliable.
- **Closed-form helpers**: `time_to_travel_distance = (√(2·c·d + v²) − v)/c`; `ess_normal_minima`
  solves the optimal ESS↔neutral switch distance analytically; `avg_ess_rate = (4+3π)/(5π)` (mean
  speed fraction retained as displacement while ESSing).

## Frontier size vs quality — mf=2000 is the sweet spot (non-monotone!)

`max_frontier` is the runtime↔quality lever, and search work scales ~**linearly** with it (mf=2000 vs
8000 = exactly 4× fewer nodes, ~4.1–4.7× faster wall). But because the A* rank (`_hcost`) is **not
admissible** (a pruning priority, not a lower bound), frontier→frames is **non-monotone**: a *larger*
frontier can yield a *worse* plan. When a layer exceeds `max_frontier` the ranked cut can evict the
eventual-optimal state, and which states survive is not a clean superset as the cap grows.

Empirically (benchmark `grid` tier, cold pump): **mf=2000 achieves the best-known frames in every dest
swept (10/10)** — 100/200/250/300/350/400/450k + refill 400/500/600k — strictly beating mf=1000 in 7/10
by 1–5 fr and tying otherwise. The standout is **400k = 812 across a stable mf=1800–2500 plateau, vs 814
at mf=1000/4000/8000** — i.e. mf=2000 is 4.7× faster *and* 2 frames better than the mf=8000 run. (The
non-monotonicity is dest-dependent: 200k is monotone, 300k is flat 705 everywhere, 400k has the valley.)

Consequences: (1) **default the quality frontier to ~2000**, not 8000 — dominant on both speed and
quality; (2) with a non-admissible prune, no single frontier is trustworthy as "the optimum" — a cheap
**frontier sweep** (min over {1000, 2000, 4000}) beats cranking one large frontier. A high-enough
(effectively uncapped) frontier *would* converge back up to the plateau optimum, but at 400k the width
exceeds 8000, so 8000 is still in the lossy-cut regime. NOTE 400k=812 is an unverified improvement
candidate over the DTM-verified 814 — needs its own DTM before replacing the base truth.

### Saturation is INTRINSIC diversity — the frontier cannot be shrunk or reshaped losslessly

The frontier pins `max_frontier` on ~98% of layers (400k: 803/813 capped, from layer ~10 onward),
and this is **not** removable precision. A layer's composition, measured deep in cruise: only
**~30–48 distinct velocity buckets** (96% of states inside a ~12–17-unit `|v|` span near max speed)
and ~8–11 flag-combos, but **~380–430 anim-phase buckets** — phase is the diversity axis. Three
levers to exploit that were tested and all **fail**:

- **Uniform anim/v-bucket coarsening** (older attempt) — leaves the frontier pinned; lossy.
- **Distance-adaptive phase coarsening** (coarsen phase far from dest, keep it fine near dest —
  motivated by head-bob phase-averaging: `|cos(π·anim/23)|` integrates to [`avg_ess_rate`](#search),
  so same-`v` states differing only in phase accumulate a *bounded* position gap). It does **not**
  shrink the frontier (even phase-bucket 1.0 = ~23 possible phases leaves `anim×v×flags` > 2000
  occupied cells, so the cap stays full) and it **loses frames** (400k 812 → 814/815). The
  phase-averaging argument is defeated because **mid-cruise dips are phase-locked to the head-bob
  peak** — so mid-cruise phase IS frame-relevant, not just endgame phase.
- **Diversity-preserving cut** (phase- or v-stratified selection when the cap fires, instead of pure
  top-rank) — only chaotic ±1–2-frame jitter (v-stratified `mf=1000` → 813 beats baseline 814, but
  `mf=1500` → 815 is *worse* than baseline 813). No cut reaches the 812 optimum below the frontier
  width the plain cut already needs (1800).

Mechanistic root: `_hcost`'s `best_disp` uses `cos=1` (peak phase) for **every** state regardless of
its actual phase, so the rank is nearly **phase-blind** — among same-`v` states it is ~constant, making
the cap's choice *among phases* effectively arbitrary. That single fact explains both the
non-monotonicity *and* why a wide frontier is required (it retains phases blindly). But the diversity
it retains is genuinely frame-relevant (mf=1000→2000 gains real frames), so it can't be cut away.

**Bottom line:** frontier saturation is intrinsic and cannot be reduced *algorithmically* without
losing frames — the "shrink/reshape the frontier" line is closed. Work is linear in frontier, so the
only remaining cost levers are **cheaper per-expansion** ([Cython](fp-faithfulness.md#cython-fast-path), the durable ~2–3×, needs a
build step) or **parallelizing the per-layer expansion** (embarrassingly parallel within a layer, but
Python pickling of ~2000 states × ~700 layers is a real risk) — neither reduces the frontier itself.

## Why mid-swim pumps are off by default

Mid-swim pumps (`neu→ess` re-entries — the same move as a mid-cruise [neutral dip](../strategy/neutral-dip.md))
are disabled by default (`allow_pump=False`); neutral is planned as a single one-way **terminal dash**.
They **do** help at band-1 cruise: with `allow_pump=True` the planner recovers the optimal 200k plan
(**555 fr, 26 dips**, −6 vs the 561-frame pump-free plan). They're off by default — not for lack of
payoff, and not from any sim-modeling failure — for these reasons:

- **Frontier saturation.** The [×598 scramble](../mechanics/pumps.md#the-x598-scramble) lands a distinct
  anim phase per entry, so the pump DP pins `max_frontier` (200k `allow_pump` run: frontier at 8000,
  544/555 layers capped). It still finds the optimum, but the search is heavy.
- **End-to-end validation pending.** A long pumped plan has not yet been re-validated via clean DTM.
  (The [speed-retention prune](#search) keeps all 26 dips at gate 0.98 and prunes off-peak pump
  landings, which should keep pumps sane — a promising path to re-enabling them.)
- **Long-chain precision floor.** The sim models the ×598 scramble
  exactly — cold-start and short pump chains are bit-exact vs clean DTM (an 11-pump build matched live
  `v/anim/air/state`, `dan`=0.000) — but beyond ~1.5 pump cycles a ~1e-4 per-entry anim oscillation
  accumulates (~0.07 v/pump). See [open-questions](../history/open-questions.md).
- **End-to-end validation pending.** A long pumped plan has not yet been re-validated via clean DTM.

The historic "band-1 200k plan bled to zero, 71% short" was **not** a sim error: it was the
`advanceseq` pipe-delivery artifact ([bug#2](../history/resolved-bugs.md)) plus planning from a
truncated cold-start seed. Clean-DTM playback tracks the sim frame-exact.

**Cold-start seeding:** seed builds with the savestate's LOGGED move0 mRate (`cold_mrate=`, which
seeds `ColdStartSwimState`) and a FULL-PRECISION anim — a truncated seed diverges ×598 through pumps.

## Why the crossover (build + cruise) decomposition

The flat pump DP saturates: the x598 pump scramble lands a DISTINCT anim phase per pump entry, so the
frontier hits `max_frontier` on every layer and dominance cannot merge genuinely-distinct futures
(empirically confirmed — frontier pinned at 8000 even after coarsening anim AND v buckets). A flat DP
wastes its whole long-cruise horizon carrying a saturated pumped frontier for nothing (cold
dest=100000: 511s, 388/396 layers capped). **Pumps only pay in the low-speed BUILD** (measured:
cruise dest=60000 pump vs no-pump both 41 fr; greedily inserting pumps into the pump-free optimum
never improves it). So the planner decomposes into a **pumped build + a pump-free cruise suffix**
(crossover), continuing each build-frontier node pump-free toward the far destination. Build distance
scales with seed speed (a fast seed is already cruising → pumps never help → pure cruise DP).

## Balloon swim

Project at current velocity for N frames, then **0.75× speed on landing** + 27-frame resurface
(−3/frame), forced air refill to 900. Decomp confirms the 0.75 landing multiplier
(`mNormalSpeed *= 0.75f`, d_a_player_swim.inc:137) and the 900 air reset (line 126).

## Air refill — the far-swim regime (SIM MODEL)

> **Status: sim-model-derived, NOT live-DTM-verified.** The refill *rule* below is a user-specified
> 1-D approximation, and every number in this section is an illustrative sim result — treat it as a
> planner model, not validated game truth. For the *game* mechanic (boundary-skim trick, touch-land =
> total speed loss, flat vs wavy, corner refills) see [mechanics/air-refill](../mechanics/air-refill.md).

**Model** (`plan_min_frames(..., refill_air=True, refill_until=X)`): air is pinned to
[900](../reference/constants.md#air) while forward progress `-x ≤ X`, then depletes −1/frame as
normal. It models building a swim "pinned back at the start" on an air-refill spot, then committing
to a single cruise. From full air a cold cruise lasts the ~900-frame [air budget](../reference/constants.md#air).

Sim-model findings (illustrative, not live-verified):

- **Benefit scales with distance:** ~1.5% frames saved at 100k, ~3.8% at 200k (higher sustained air
  → less [head-bob/air drag](../mechanics/animation.md) → faster true speed).
- **Simplifies plans:** fewer [neutral dips](../strategy/neutral-dip.md) — e.g. 200k drops 35 → 27
  dips (103 → 60 neutral frames) because high air already keeps drag low.
- **Enabling at the far end (not a percentage):** non-refill drowns around ~450–500k (500k non-refill
  ends at air = −7); a refill plan reaches 500k with ~411 air to spare, and 600k is reachable — build
  to high speed "for free" at the pinned-back spot, then cruise within the ~900-frame budget.
- The **real TAS swim regime is ~200k–600k**, i.e. squarely where refill matters.

**Out of scope / open:** mid-cruise or *multiple* refills are a real thing the 1-D sim cannot place
(it has no x/z coordinates), but they are **rare** — the target island's collision won't
[load in time](../mechanics/ocean-environment.md#only-one-islands-collision-is-loaded-at-a-time) at
superswim speed, so refills cluster at the launch island (distance ≈ 0), which `refill_until` already
approximates. See [open-questions](../history/open-questions.md).

## Unmodeled world features & the re-plan loop

The sim is **1-D swim physics only** — bit-exact along a straight leg in flat open water, but it models
**no world**: no waves, no island/ocean collision, no [refill placement](../mechanics/air-refill.md), no
[sploosh zones](../mechanics/ocean-environment.md#sploosh-zones-ocean-collision-load-failure). Those
unmodeled features — not physics drift — are what eventually make a real run diverge from the plan.

**Why this is fine (the re-plan loop).** In flat open water a plan holds indefinitely (no re-plan
needed). You re-plan **event-driven**, when you approach a feature the sim doesn't know: run the sim as
a template, execute, and when reality diverges (a manual refill, a route change) **re-seed from the live
state and re-solve the remainder** — the planner already takes arbitrary initial `(v, anim, air)`. And
the ~1–2 frames a better plan saves are **real, not noise**: at cruise `|v|` (~1300/frame) the
sub-frame position error from unmodeled features rarely crosses a whole discrete frame boundary, so a
bit-exact leg delivers its computed frame count. (This is *not* an argument for chasing provable
sim-optimality via minute-long uncapped runs — see [frontier § saturation](#saturation-is-intrinsic-diversity--the-frontier-cannot-be-shrunk-or-reshaped-losslessly).)

**Design stance for world features (proposed, not built):**
- **Refills = calibrated boundary events, never collision physics.** Model a refill as `air:=900` plus a
  measured frame cost at a *fixed route point the human/route decides* — not a search dimension. This
  keeps the [frontier](#frontier-size-vs-quality--mf2000-is-the-sweet-spot-non-monotone) exactly 1-D
  (zero cost), generalizes `refill_until` from one start-region to a set of route boundaries, and lets a
  known multi-refill island-chain template in one run. The precise touch-nothing skim stays **manual**.
- **Sploosh zones = a coarse quadrant-route constraint,** not per-frame state: a max-speed cap on entry
  and possible detour, decided at a small 7×7-grid route layer that feeds per-leg cruise DPs. Folding
  collision into the cruise DP would multiply an already-saturated frontier for no benefit.

## See also

- [Swim sim](swim-sim.md) · [Pumps / x598](../mechanics/pumps.md) ·
  [strategy/reboost](../strategy/reboost.md) · [strategy/phase-ordering](../strategy/phase-ordering.md)
  · [history/resolved-bugs](../history/resolved-bugs.md) (bug#2 / DTM delivery).
