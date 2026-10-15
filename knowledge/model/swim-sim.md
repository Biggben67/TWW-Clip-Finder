# The offline swim sim: precision & calibration

**Answers:** How does the sim reproduce swim physics with no Dolphin? What are the four charge-frame
lags? What is `CHARGE_DISP_FACTOR`? How is a cold start seeded (the mRate rule)? How accurate is it?
**Status:** validated bit-exact (v/anim/air/state) over full cold-start swims.
**Source:** `tww_sim/swim/sim.py`, `tww_sim/swim/coldstart.py`; decomp + live calibration. Engine FP
rules: [fp-faithfulness](fp-faithfulness.md).

---

`tww_sim/swim/sim.py` reproduces the superswim physics with **no Dolphin dependency**. It is bit-exact
for potential speed / anim / air / state; x/z displacement is a wave-affected byproduct (well-modeled
in aggregate, not bit-checked per frame). Bit-exactness rests on the engine-wide
[floating-point contract](fp-faithfulness.md): all math in f32 with faithful op order, the baked
[console cosine table](fp-faithfulness.md#console-cosine-and-sine-tables), and
`_F32_PI` in cos args. The swim-specific calibration on top of that is below.

## Charge-frame model (four 1-frame lags)

Charging is governed by four separate live-calibrated lags (each measured against unrounded RAM):

1. **Anim-rate lag** - the anim controller advances using the PREVIOUS frame's speed; advance anim
   *before* applying the speed change.
2. **Swim-gain lag (uniform)** - the `setSpeedAndAngleSwim` gain (charge +3 *and* the ESS
   facing-gain alike) lands on the NEXT frame, replacing that frame's decay. ESS and charge use the
   SAME 1-frame deferral (as `ArrowState` does). The earlier asymmetric same-frame-ESS /
   lagged-charge split dropped a partial hold's last gain at a hold→charge boundary. See
   [resolved BUG #3](../history/resolved-bugs.md#bug3--partial-hold-gain-dropped-at-a-holdcharge-boundary).
3. **First-charge decay** - the first `chg` of a burst still applies the normal ESS decay; +3 engages
   from the 2nd frame.
4. **Facing flip** - each `chg` toggles a 180° facing flip applied the next frame; even-length bursts
   return to the original heading.

`CHARGE_DISP_FACTOR = 0.9466`: charge frames move ~5.3% LESS than ESS at the same (v, anim, air).
Measured live band-2 (ESS 1463.60 vs charge 1385.44 at v=−1632, anim=17.66, air=895). **Band-2 only.
Revalidate far from −1630.**

## Cold-start seeding (the mRate rule)

A cold start is hypersensitive to the seed: a seed anim rounded to 4 digits (vs the true 0.06392288…)
drifts ~2e−5 → ~0.012 anim after the cold-start x598 scramble → a *completely different* swim (one
test reached 1408 vs 3004). **Always seed the full-precision live anim.** The cold-start scramble
oldframe is:

```
oldframe       = f32( f32(anim_seed + mRate_seed) + neutral_anim_rate(air_seed − 1) )
scramble_anim  = f32( f32(oldframe · 26.0) · 23.0 )
```

`mRate_seed` (the MOVE0 anim-rate at seed) **must be LOGGED live**: it carries pre-seed air history
and cannot be recomputed from a snapshot. (`coldstart.py`; cold-start uses logged mRate, warm pumps
recompute `neutral_anim_rate(air−1)`, different entry histories, different rules.)

## Accuracy

Against a full-precision RAM capture: per-frame anim to **0.00002**, v to **0.0003**. On a 150-frame
ESS run vs Dolphin: cumulative path error **−0.02%**, mean per-frame step **0.15%** (excluding 2
Dolphin auto-camera glitch frames). The earlier "1–3% gap" was the four lags + the cosine table. All
resolved.

## See also

- [FP faithfulness](fp-faithfulness.md) · [Planner](planner.md) · [Predictors](predictors.md) ·
  [Animation / head-bob](../mechanics/animation.md) · [Pumps / x598](../mechanics/pumps.md) ·
  [history/resolved-bugs](../history/resolved-bugs.md).
