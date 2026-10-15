# Reboost (phase-triggered charging in a strobo band)

**Answers:** Does reboost save time? How big should a boost be? When do you fire it? Why does a
fixed cadence lose? What's the optimal schedule and does it transfer?
**Status:** validated (live + beam search). **Reboost saves time ONLY when phase-triggered, not on
a fixed cadence** — see the reversal note below.
**Source:** live 2026-06-26 (`essloop`); beam search `tww_sim/swim/optimize.py`.

---

## The idea

In a [stroboscopic band](../mechanics/strobo.md) the anim phase drifts slowly. If it drifts toward
the trough (anim 11.5), ESS efficiency `(0.6 + 0.4·|cos(π·anim/23)|)` decays frame after frame. A
short **up/down charge ("reboost")** bumps potential speed, which raises the anim increment above
`23·k`, which **flips the drift direction** — anim climbs back toward the |cos| = 1 peak and true
speed rises monotonically afterward. **The win is re-aiming the drift, not the +speed itself.**

> ⚠️ **Reversal (do not copy the old advice):** an earlier conclusion was "reboost is net-negative,
> never reboost." That was an artifact of testing **blind fixed cadences only**. A fixed cadence
> fires at arbitrary anim phases — sometimes kicking the drift the *wrong* way — and pays the
> turnaround tax for nothing (measured **−2% band-2 / −8% band-1**). Reboost done right
> (phase-triggered) is a real, measured time-save (**up to +15%**). See [history](../history/reboost-strobo-history.md).

## Boost size is coupled to anim phase

Boost just enough to **land anim at the peak (0/23)**; how big depends on how far anim is from the
peak when you fire:

| anim when fired | right boost | what happens | measured (band 2) |
|-----------------|-------------|--------------|-------------------|
| near peak (~20–23 / 0–2) | **2 frames (one up-down)** — *maintenance* | re-parks anim at the peak | **+8.5%** |
| deep mid-cycle (~13–16) | **~4 frames** — *recovery* | drives anim back up to the peak | +11% |
| near peak | 4+ | overshoots past the peak | −18% |
| deep mid-cycle | 2 | only nudges increment → freezes at a mediocre phase | ≈ baseline |

**The genuinely optimal line:** keep anim pinned at the peak with **minimal up-down maintenance**
(2-frame boosts), and never let it drift far enough to need a big recovery kick. The 4-frame
recovery is the rescue move for when you've already let anim slide deep.

## Practical rules

1. **Phase-triggered, sparse, sized to the phase.** Steady state = a 2-frame up-down fired when
   anim drifts off the top of the peak. Use ~4 frames only to recover an anim that already slid deep.
2. **Never boost on a timer, and never boost every eligible frame.** Over-boosting (`cooldown=0`,
   16 boosts) ran speed away and crashed net/fr **−30%**. The right count is a handful per swim.
3. **The gain is front-loaded.** One boost launches an anim climb that eventually overshoots; it
   helps more per-frame over a short window (+11% / 150 fr) than amortized over a long one
   (+5% / 220 fr). Re-time the next boost for when anim is descending toward the trough again.
4. **Each boost costs ~a few frames of forward progress** (the path−net gap): a full-deflection
   charge snaps Link 180° via the [instant turnaround](../mechanics/turnaround.md) (one ~dead
   frame + a reversed frame). Timing the kick onto lower-|cos| phases minimizes this.

## Optimal schedule — searched, not guessed

`tww_sim/swim/optimize.py` beam-searches the full per-frame {ESS, charge} space. Band-2, 200-frame
window (−1630, air 900): converged (beam 2000 = 4000 = 8000) to **3 minimal up-downs (length-2)**
at frames 2 / 44 / 110 → **+15% net/fr**; **live-verified +15.7%** (sim predicted +15.1%). The
search independently rediscovered that the **minimal 2-frame up-down is the optimal boost**.

**The frame numbers do NOT transfer.** They shift with the seed:
- Small tweaks (anim ±0.3, speed ±few) → small smooth shifts; gain steady ~15%.
- Larger changes → big shifts (anim 2/16/21 → boosts 24·64·107 / 2·26·115 / 2·63·107; air 900→600
  → 6 → 2 boosts, gain +15% → +5%).
- **Stable across all seeds:** minimal 2-frame boosts near the peak, ~3 per 200 fr, with one bigger
  recovery kick when starting far from the peak. Gain always positive (+3.7% above-band … +15.6%
  band-centre).
- **Implication:** re-solve per exact (speed, anim, air). A fixed frame list won't carry over.

## See also

- [Strobo bands](../mechanics/strobo.md) — the mechanism reboost exploits.
- [Turnaround](../mechanics/turnaround.md) — the snap that costs the per-boost tax.
- Tooling: `essloop` (closed-loop live), `tww_sim/swim/optimize.py` (beam search). Command refs live
  in the reference layer (migrating).
