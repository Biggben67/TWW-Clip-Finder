# What superswimming is

**Answers:** What is a superswim? What are potential speed and true speed? What's the basic loop?
**Status:** validated (community + decomp).
**Source:** zeldaspeedruns.com/tww superswim docs; decomp `d_a_player_swim.inc`.

---

Setup via Storage + camera lock with the Wind Waker leaves Link in a swimming state where holding
the control stick builds speed. **Superswim proper is alternating the stick fully back-and-forth
every frame.** Each alternation adds **3 units of potential speed** (the decomp's `mNormalSpeed`).
Speed is negative-signed by convention (the model stores velocity; charging does `+= 3`).

## The two speeds that matter

- **Potential speed** (`velocity` / `mNormalSpeed`) — the underlying speed value. Charging grows
  it; [ESS](ess.md) / [neutral](neutral.md) decay it.
- **True speed / true displacement** — how far Link *actually* moves this frame = potential speed
  scaled by two drag factors ([head-bob / animation](animation.md) + air meter). See
  [animation](animation.md#true-displacement).

## The phases of a swim (the loop)

A full route is roughly: **charge** (build speed) → optionally [arrow](arrow.md) toward the target
→ [ESS](ess.md) cruise (preserve speed, ride a [strobo band](strobo.md), [reboost](../strategy/reboost.md)
to stay efficient) → terminal [neutral](neutral.md) dash to the destination. The detailed ordering
and tradeoffs are in [strategy/phase-ordering](../strategy/phase-ordering.md).

## See also

- [Charging & speed gain](charging.md) · [ESS](ess.md) · [Decay curve](decay-curve.md) ·
  [Neutral](neutral.md)
- [Glossary](../reference/glossary.md) for any unfamiliar term.
