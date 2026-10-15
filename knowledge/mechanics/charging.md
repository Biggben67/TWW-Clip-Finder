# Charging & speed gain

**Answers:** How fast does charging build speed? What's the formula? How does charging at an angle
(arrow) change the gain?
**Status:** validated (decomp + live).
**Source:** decomp `setSpeedAndAngleSwim` (d_a_player_swim.inc:41,66).

---

## The gain formula

```
delta = mStickDistance · 3.0 · cM_scos(shape_angle.y − oldAngleY)
```

- **Full back-and-forth, on-axis** → `cos(Δ) = 1` → **+3 potential speed/frame** (max charge rate).
- **Holding at an angle** ([arrow swimming](arrow.md)) → `cos(Δ) < 1`, so you gain *less* speed but
  Link drifts toward the destination. He forms the "tip of an arrow" pointing at the target.

`mStickDistance` is the normalized deflection `clamp((|raw−128|−15)/54, 0, 1)`, capped at 1 (see
[decay curve](decay-curve.md) and [constants](../reference/constants.md#stick-geometry)). Tilting
the charge axis changes the **cosine**, not the magnitude.

`cM_scos` is the [console cosine table](../reference/glossary.md#cm_scos), not `math.cos` — this
matters for bit-exactness, see [model/sim](../model/fp-faithfulness.md#console-cosine-and-sine-tables).

## Charging nets ~zero progress on its own

A turnaround charge flips facing 180° every frame (see [turnaround](turnaround.md)) and moves Link
**backward along facing**, so consecutive frames move in opposite world directions. Continuous
up/down charging nearly cancels: **272 continuous charges from a cold start net only ~390 units**.

To net progress *during* the build you either [arrow-swim](arrow.md) (tilt toward target) or use
**head-bob-phased charging** — break the charge into bursts separated by single ESS frames so the
toward-target charge frames land on the head-bob **peak** (big displacement) and the away frames on
the **trough** (small), and the un-flipped ESS frames add pure forward steps. On the 200k cold-start
plan this nets **~4948 progress** by the same frame/speed vs ~390 for plain charging. This effect
lives entirely in position (a wave-affected byproduct, not bit-validated per frame); it was
optimizer-discovered. See [strategy/phase-ordering](../strategy/phase-ordering.md).

## See also

- [Arrow swimming](arrow.md) — the angled-charge model.
- [Turnaround](turnaround.md) — why facing flips each charge frame.
- [Animation / head-bob](animation.md) — the displacement modulation phased charging exploits.
