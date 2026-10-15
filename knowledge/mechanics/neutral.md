# Neutral swimming (state 54) & the ESS↔neutral exit

**Answers:** What does neutral do per frame? Is it really flat −2? How fast does its animation
advance? What speed do you carry out of ESS into neutral, and how does exit phase affect it?
**Status:** validated (decomp + live, 2026-06-27 clean slate).
**Source:** decomp `procSwimWait`/`procSwimWait_init` (d_a_player_swim.inc:406-424); live.

---

## Neutral (state 54) per frame

- **Decay = −2.000/frame exactly** at normal speed; **displacement = |v| exactly** (drag-free,
  step/|v| = 1.0000). Speed-independent (−280 and −1630 give identical deltas).
- **Animation wraps at 26** (`End_wait`, ANM_SWIMWAIT) at rate `0.5 + 2.5·(1 − (air+1)/900)` per
  frame — speed-independent, rises as air depletes (HIO `field_0x40 = 0.5`, `field_0x70 = 2.5`).
- Distinct from [ESS](ess.md) state 55 (ANM_SWIMING, anim wraps at 23, ~7/frame).

> **Low-speed correction:** the decay is `cLib_addCalc`-based, not literally a flat −2. At |v| > 100
> it is the flat −2; in 25 < |v| < 100 it is proportional (~0.02·|v|); **below |v| = 25 it snaps
> toward 0 at 0.5/frame** (no overshoot). Only the high-speed −2 case matters for 200k+ plans.

## ESS → neutral exit (release_ess_speed)

On the state 55→54 transition (1-frame lag), the speed carried into neutral is the **head-bob-dragged
(true) speed at the release frame**, then the −2 decay resumes:

```
exit_speed = af_drag(potential, release_anim)
```

So the speed you keep depends on **when you exit**:

| effective anim | \|cos\| | speed kept |
|----------------|---------|------------|
| ~0 / 23 (ends) | ~1 | ~100% |
| ~11.5 (middle) | ~0 | ~60% |

**Practical rule: release ESS when the animation is near 0/23; releasing mid-cycle (~11.5) costs up
to ~40%.** This is the normal [head-bob drag](animation.md), now baked into the carried-over neutral
speed — there is no separate "exit tax" beyond `release_ess_speed`.

> Historical note: an earlier model read the wrong frame for this (the "2-increment phase error").
> The current sim advances the exit-frame physics before applying `af_drag`; it is bit-exact. See
> [history/resolved-bugs](../history/resolved-bugs.md).

## The endgame tradeoff

Neutral moves full |v| (drag-free) but decays −2/fr, so a terminal neutral dash is fastest only if
you exit at a **good phase**. The min-frames planner prices this automatically: at a good exit phase
it dashes immediately; at a bad one it HOLDS ESS a few frames to advance anim to a better phase, then
dashes. (Live: anim-20 start → dash = 13 fr; anim-11.5 start → hold-then-dash = 18 fr vs 20 fr if you
exited immediately.) See [strategy/phase-ordering](../strategy/phase-ordering.md) and
[strategy/neutral-dip](../strategy/neutral-dip.md).

## See also

- [Pumps](pumps.md) — the neutral→ESS direction (entry tax + x598 scramble).
- [Decay curve](decay-curve.md) — why neutral's −2 is a separate code path.
- [Constants](../reference/constants.md#animation).
