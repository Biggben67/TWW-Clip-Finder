# Neutral dip (the cruise "pump")

**Answers:** What is a neutral dip and why does it save speed? When is it effective? How is it
different from an ESS pump?
**Status:** validated (planner uses it; live-confirmed plans, 50k & 200k clean-DTM sync).
**Source:** decomp exit-release math; live 2026-06-27 + 2026-07-02; A* planner.

---

## What it is

A **1-frame neutral tap inserted mid-ESS-cruise** — the *inverse* of an [ESS pump](../mechanics/pumps.md).
It exploits the [ESS→neutral exit](../mechanics/neutral.md#ess--neutral-exit-release_ess_speed): the
single state-54 frame is the EXIT frame of the prior ESS, so v is set to `af_drag(v, anim)` —
**lossless at the head-bob peak (|cos| = 1)** — and the flat −2 neutral decay is **skipped** that
frame (you re-enter ESS before sustained neutral begins).

So a dip taken at the anim peak DODGES the −2 loss: that frame costs ~0 potential speed, then you
resume ESS at −1/6. Net ≈ **+0.833 saved** vs two flat-neutral frames. Cost: the −3 facing-flip
transient on re-entry, amortized across many dips.

## When it's effective

Dips pay when the animation **lingers on the head-bob peak**, so you can catch it near-losslessly
frame after frame. Whether it lingers is set entirely by the per-frame anim drift = `incr mod 23`
(`incr = |v|/36 + 3/5 + air term`, so drift depends on `|v|`). In a
[stroboscopic band](../mechanics/strobo.md) `incr ≈ a multiple of 23`, so the drift → ~0 and the phase
camps on the peak (band-1, |v|≈790: ~0.1 anim/frame). Away from a band the drift is larger (at the 50k
cruise |v|≈447 it's ~9.6/frame), so the phase rarely lands on the peak and dips are fewer and less
free. The payoff therefore **grows with distance** as the optimal cruise speed climbs toward a band.
**Dip at the anim peak.**

Every cruise dip lands its *release* frame on the peak (`af_drag` retention ≈ 100%, near-lossless
exit). But dipping at *every* peak over-dips and LOSES — the optimizer is selective, and the planner's
[speed-retention prune](../model/planner.md#search) encodes this: it drops off-peak exits (> 2% `|v|`
cut) and keeps the near-peak ones.

## Measured

Both live-synced (clean DTM, bit-exact) with `allow_pump=True` + the speed gate:
- **200k** (band-1 cruise, |v|≈790): 26 dips → **555 fr** vs 561 no-pump (**−6**).
- **50k** (off-band, |v|≈447): 9 dips → **280 fr** vs 282 no-pump (**−2**).

## Don't confuse with mid-swim ESS pumps

A neutral dip is itself a `neu→ess` re-entry, so the planner treats it as a **pump** — mid-swim pumps
are off by default (`allow_pump=False`), which is why the default planner emits a pump-free plan (561
fr at 200k) and only `allow_pump=True` recovers the dip-laden optimum (555 fr, 26 dips). Off by default
for frontier saturation + pending live validation, NOT lack of payoff — see
[model/planner](../model/planner.md#why-mid-swim-pumps-are-off-by-default).

## See also

- [Neutral](../mechanics/neutral.md) · [Pumps](../mechanics/pumps.md) · [Phase ordering](phase-ordering.md).
