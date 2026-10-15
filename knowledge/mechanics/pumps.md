# ESS pumps & the neutral→ESS x598 scramble

**Answers:** What is an ESS pump? Why does a 1-frame pump do nothing? Why is the post-pump
animation phase scrambled (hypersensitive)? What's the minimum useful pump?
**Status:** validated (decomp + live).
**Source:** decomp `setSwimMoveAnime` (d_a_player_swim.inc:264); live 2026-06-26.

---

## What a pump is

While [neutral](neutral.md), briefly tapping [ESS](ess.md) for a few frames to preserve potential
speed cheaply (−1/6 instead of −2) on frames whose true displacement stays near neutral's. It is a
**low-speed** tech — at [strobo bands](strobo.md) ESS is already efficient, so don't pump there.

## The 1-frame entry tax

The **first** ESS-input frame out of neutral stays in **state 54** and behaves as **pure neutral**
(decay −2, drag-free, anim +neutral-rate). The stick only QUEUES the 54→55 transition; the −1/6 ESS
decay starts on the **2nd** frame.

| pump frame | state | decay | behaves as |
|------------|-------|-------|------------|
| 1 | 54 | −2 | neutral (no benefit) |
| 2+ | 55 | −1/6 | real ESS |

So a pump of length L = 1 frame@−2 + (L−1)@−1/6. Speed saved vs L neutral frames: L=1 → 0
(**useless**), L=2 → 1.83, L=3 → 3.67. **Minimum effective pump = 2 frames**; each pays a fixed
1-frame entry tax.

## The x598 scramble

The post-pump ESS-start animation phase is **scrambled** by the animation controller. `setSwimMoveAnime`
loads ANM_SWIMING and does `setFrame(oldFrame · oldEnd · newEnd)` with `oldEnd = 26` (ANM_SWIMWAIT)
and `newEnd = 23` (ANM_SWIMING):

```
anim_ESS_start = (swimwait_frame · 598 + ESS_increment) mod 23        [598 = 26·23]
ESS_increment  = |v|/36 + 3/5 + (1 − (air+1)/900)
```

where `swimwait_frame` is the neutral-anim controller frame on the transition frame.

**Key insight:** 598 ≡ 0 (mod 23), so the INTEGER part of `swimwait_frame` is irrelevant — only its
**fractional** (sub-frame) phase sets the ESS-start phase, scaled ×598. **1/26 frame of entry jitter
= a full 23-cycle swing.** Measured ESS-start across consecutive entries jumps chaotically (7.08,
2.68, 22.94, 21.87, …) — it is **deterministic but effectively scrambled**. A predictor must
replicate the frame-controller math exactly; a smooth approximation fails. (Raw data:
[reference/data.md](../reference/data.md#neutraless-anim-scramble-ess3--first-real-state-55-ess-frame).)

## Why pumps are off by default in the planner

The landed phase is hypersensitive, but the sim models it **exactly** — cold-start and short pump
chains are bit-exact vs clean DTM. Pumps (= mid-cruise [neutral dips](../strategy/neutral-dip.md)) DO
help at band-1 cruise (with `allow_pump=True` the planner recovers the optimal 200k plan, 555 fr / 26
dips). They are still **off by default** (`allow_pump=False`; neutral planned as a single terminal
dash) because the pump DP saturates the frontier, long chains hit a precision floor (beyond ~1.5
cycles), and a long pumped plan is not yet end-to-end clean-DTM validated. The historic "band-1 plan
bled to zero, 71% short" was a pipe-delivery artifact ([bug#2](../history/resolved-bugs.md)), not a
modeling failure. Full detail: [model/planner](../model/planner.md#why-mid-swim-pumps-are-off-by-default).

## See also

- [Neutral](neutral.md) (the exit direction) · [Animation](animation.md#neutral-animates-differently)
  (23 vs 26) · [glossary: x598](../reference/glossary.md#x598).
