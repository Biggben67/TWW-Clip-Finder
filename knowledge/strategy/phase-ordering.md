# Optimal swim phase ordering

**Answers:** What order do the phases go in? Which are real wins vs traps? When do you switch from
ESS to neutral?
**Status:** validated (the ordering); some phases unproven (flagged inline).
**Source:** synthesis of the mechanics pages; live-confirmed plans.

---

A full route, in order:

1. **Charge** at +3/frame (fastest growth). See [charging](../mechanics/charging.md).
2. **Air refill** if possible — air −1/frame (max 900). Lower air → head deeper → slower ESS true
   speed (stacks on the [head-bob](../mechanics/animation.md) penalty).
3. **Arrow charge** *(not recommended — loses frames)* — start [arrow-swimming](../mechanics/arrow.md)
   toward the destination while still charging at the reduced (cos-penalized) rate; trades charge
   rate for early progress. An exhaustive offline insertion sweep (2026-07-02) found it **never
   saves frames** — best case loses +4, worse the later/longer you arrow (see
   [arrow verdict](../mechanics/arrow.md#does-arrow-swimming-save-time--no-offline-exhaustive)).
4. **ESS toward destination** — preserve potential speed (−1/6). Ride a
   [stroboscopic band](../mechanics/strobo.md) and [reboost](reboost.md) (phase-triggered) to stay
   at the head-bob peak.
5. **Neutral dash** — once ESS drag outweighs the −2 neutral loss, exit to
   [neutral](../mechanics/neutral.md) (true speed = potential speed) for the terminal stretch.
   **Exit at a good head-bob phase** (anim near 0/23) or hold ESS a few frames to reach one.
6. **ESS pump / neutral dip** — see [neutral-dip](neutral-dip.md). These `neu→ess` re-entries save
   frames at band-1 cruise (the 555-fr 200k optimum has 26), but the planner keeps them **off by
   default** (`allow_pump=False`) — see [model/planner](../model/planner.md#why-mid-swim-pumps-are-off-by-default).

## The ESS↔neutral switch is the key decision

ESS preserves potential speed but pays head-bob + air drag on true speed; neutral is drag-free but
decays −2/fr. The optimizer finds the switch distance (closed-form `ess_normal_minima`, or the
min-frames search). The switch is coupled to the **exit phase** — see
[neutral: the endgame tradeoff](../mechanics/neutral.md#the-endgame-tradeoff).

## Two-phase planning structure

In practice the planner fixes the BUILD (charge) phase and searches the cruise + terminal dash with
[reboost](reboost.md); the cruise→dash boundary is a fixed point coupled to the route. Mid-swim
pumps are off by default — see [model/planner](../model/planner.md#why-mid-swim-pumps-are-off-by-default).

## See also

- [Reboost](reboost.md) · [Neutral dip](neutral-dip.md) · all [mechanics/](../mechanics/) pages.
