# Decay curve (potential-speed loss vs stick)

**Answers:** How much potential speed do you lose per frame for a given stick value? Is it three
discrete states or a continuous curve? Where does it saturate? Why is neutral different?
**Status:** validated exact (decomp + live).
**Source:** decomp `PADClamp`, `JUTGamePad::CStick::update` (JUTGamePad.cpp:303-310),
`setSpeedAndAngleSwim`; live 2026-06-26.

---

## Decay is CONTINUOUS in stick distance

Potential-speed decay for any *registered* (non-dead-zone) input is one continuous function of
distance from neutral, **NOT three discrete states**. Charge (+3) and ESS (−1/6) are just two
sampled points on the same curve — charge = full deflection, ESS = the minimum.

```
decay = clamp((|raw − 128| − 15) / 54, 0, 1) · 3
```

The pipeline: `PADClamp` removes the radial **dead zone 15** → `JUTGamePad` divides by **54** →
`mStickDistance` → `setSpeedAndAngleSwim` multiplies by 3. Constants:
**dead zone = 15, divisor = 54, ×3** ([constants](../reference/constants.md#speed-deltas)).

## Live validation

| stickY | off | measured \|decay\| | linear (off−15)/54·3 |
|--------|-----|--------------------|----------------------|
| 110 | 18 | 0.16667 | 0.16667 ✓ (ESS) |
| 90  | 38 | 1.27777 | 1.27778 ✓ |
| 75  | 53 | 2.11111 | 2.11111 ✓ |
| 70  | 58 | 2.38889 | 2.38889 ✓ |
| 65  | 63 | 2.66667 | 2.66667 ✓ |
| 63  | 65 | 2.72223 | 2.77778 (−1 unit) |
| 60  | 68 | 2.88889 | 2.94444 (−1 unit) |
| 58  | 70 | 3.00000 | 3.00000 ✓ (saturated) |
| 128 | 0  | 2.00000 | neutral path = 2 |

The linear law is **exact across the whole ESS + arrow-swim regime** (off ≤ 63). A ~1-stick-unit
shortfall appears only in the narrow off 65–68 band (PADClamp top-end radial compression), then
**saturates to exactly 3.0 by off ≥ 70** (stickY ≤ 58). The community "128,61+" saturation note was
off by ~1 unit; saturation begins at 128,59.

## Neutral is a SEPARATE path

**Neutral's −2 is not a point on this curve.** `(128,128)` is inside the dead zone → no swim input →
a flat, drag-free **−2** code path. That's why neutral loses *less* than full deflection (−2 < −3)
yet *more* than ESS — different rules. See [neutral](neutral.md).

## Why this matters

[Arrow swimming](arrow.md) lives on this continuum: partial deflection toward the destination =
intermediate decay + simultaneous movement. Modeling the stick→decay curve directly (not 3 discrete
states) is what lets the optimizer represent arrow swimming.

The sim applies this law correctly for partial deflections too — including a partial-magnitude hold
interleaved in a charge burst (live-validated bit-exact via DTM, 2026-06-30, after
[resolved BUG #3](../history/resolved-bugs.md#bug3--partial-hold-gain-dropped-at-a-holdcharge-boundary)).
A planner search over partial `ess:<rawY>`/`chg:<rawY>` actions is therefore valid physics — but
empirically on-axis partials still save **0 frames** (deeper-than-ESS only bleeds speed; the
build-vs-progress tradeoff is gated by stick *direction*, not magnitude). The untested lever
remains **off-axis** ([arrow swimming](arrow.md)), which needs the 2-D heading model.

## See also

- [ESS](ess.md) · [Arrow](arrow.md) · [Neutral](neutral.md) · raw data [reference/data.md](../reference/data.md#decay-curve-sweep-potential-speed-decay-vs-stick-low-speed-slate).
