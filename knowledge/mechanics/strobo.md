# Stroboscopic bands

**Answers:** What is the stroboscopic effect? At what speeds do the bands occur? Are they exact?
How does air shift them? Why does ESS stay efficient in a band?
**Status:** validated empirically (mechanism understood; exact decomp derivation open).
**Source:** emerges from the ESS anim-increment formula; live 2026-06-26 (high-speed slate).

---

## What it is

The [animation frame](../reference/glossary.md) advances by a fixed increment each ESS frame. At
certain speeds that increment lands at **≈ 23·k** (a near-integer multiple of the `End_swim = 23`
wrap), so the anim barely advances frame-to-frame — it **aliases** ("strobes"). Because the anim
sits at nearly the same phase each frame, the [head-bob drag](../reference/glossary.md#af_drag)
`|cos(π·anim/23)|` stays roughly constant, so ESS **true speed closely tracks potential speed**.
These speed bands are therefore valuable targets to ride.

## Where the bands are (air-dependent)

The ESS anim increment is `|v|/36 + 0.6 + (1 − (air+1)/900)`. Solving `increment ≈ 23·k`:

| Band | Approx \|v\| | At |
|------|------------|-----|
| k = 1 | **≈ −794** | air ≈ 597 (measured −783) |
| k = 2 | **≈ −1630** | air ≈ 900 |

> The legacy community figures **−850 / −1650** are these same bands; the difference is the air
> term, which those figures didn't account for.

**The bands move as air depletes.** The air term `(1 − (air+1)/900)` shrinks as air drains, so the
increment drops — to stay at `23·k` you need a **larger |v|**. So during a long swim the band
**drifts to higher speed under you**; you slide out the bottom of the band as air runs down.

## Drift inside a band

In a band the increment is just under (or over) `23·k`, so the anim **slowly drifts** in the
direction set by `sign(increment − 23k)`:

- increment < 23k → anim **decreases**; increment > 23k → anim **increases**.
- Live (band-1, −783, increment 22.76): anim crawled **~−0.25/frame** (vs +8.8/frame at low speed)
  and drifted from |cos| = 0.72 toward mid-cycle (|cos| → 0.18 over 18 frames) — i.e. true speed
  **degrading** as the phase walked toward the trough (anim 11.5).

This slow, directional drift is the whole reason [reboost](../strategy/reboost.md) works: a small
charge bumps the speed, flips the drift direction, and walks the anim phase back up toward the
efficiency peak (anim 0/23).

## Strategy in a band (summary)

Ride a **sustained full ESS** — the anim self-stabilizes at a good phase, so sustained ESS maxes
out the minimal-drag benefit. Do **not** pump (pumping is the opposite, low-speed regime). Use
[reboost](../strategy/reboost.md) **only** to re-aim the anim if it drifts toward the trough — and
only **phase-triggered**, never on a fixed cadence (a blind cadence loses; see reboost page).

## Open / approximate

The exact derivation from the decomp is not pinned (likely a Nonmatching term in
`J3DFrameCtrl::update`); whether the bands are sharp or fuzzy, and second-order air effects, are
not fully characterized. The band is **not explicitly modeled** in the planner — it emerges from
the increment formula, and the beam-search optimizer rediscovers band strategies on its own.

## Constants used here

End_swim 23, increment formula, band speeds ≈ −794 / −1630. See
[reference/constants](../reference/constants.md#stroboscopic-bands).

## See also

- [Reboost](../strategy/reboost.md) — the phase-triggered tactic for staying in a band.
- [Head-bob drag](../reference/glossary.md#af_drag) — why phase governs efficiency.
- History / provenance: [reboost-strobo-history](../history/reboost-strobo-history.md).
