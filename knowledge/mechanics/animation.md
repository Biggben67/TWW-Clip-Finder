# Animation frame, head-bob drag & true displacement

**Answers:** How fast does the animation cycle? What is the head-bob drag? How is true
displacement computed from potential speed? What's the air-meter effect?
**Status:** validated bit-exact (decomp + live to ~0.00002 anim / 0.0003 v).
**Source:** decomp `d_a_player_main.cpp:2424-2428`, `getSwimTimerRate` (d_a_player_swim.inc:283).

---

## Animation frame

The swim animation cycles **0..23** (`nfmod(·, 23.0)`, 24 positions). Per ESS frame it advances:

```
increment = |velocity|/36 + 3/5 + (1 − (air+1)/900)
```
- `|velocity|/36` — speed term (`/(2·maxSpeed)`, maxSpeed = 18).
- `3/5` — base.
- `(1 − (air+1)/900)` — air term. **Decomp:** `getSwimTimerRate() = 1 − itemTimeCount·0.0011111111
  = 1 − air/900`. Higher speed and lower air both speed up the cycle.

## Head-bob drag (the animation-frame drag)

Link's head bobs with the animation, modulating true speed. The exact decomp expression
(`d_a_player_main.cpp:2424-2428`):

```
af_drag(v, anim) = ( 0.6·v + 0.4·v·|cM_scos(π·anim/23)| ) / ( 1 + 0.35·getSwimTimerRate(air) )
```
- `field_0x60 = 0.4` (head-bob cos weight; base weight `1 − 0.4 = 0.6`).
- `field_0x7C = 0.35` (swim-timer drag denominator coeff; backed out exact from live).
- `cM_scos` is the [console cosine table](../reference/glossary.md#cm_scos), **not** `math.cos`.

Efficiency runs **~100% at anim 0/23** (|cos| = 1) down to **~60% at anim 11.5** (|cos| = 0). This
modulation is what [stroboscopic bands](strobo.md) and [reboost](../strategy/reboost.md) exploit.

> The legacy tool approximated the air term as a separate `air_drag = 18000·v / (24300 − 7·air)`.
> That is ~0.04% low; the exact form is the single `/(1 + 0.35·getSwimTimerRate)` denominator above.

## True displacement

```
true_displacement = af_drag(velocity, animation_frame)      # the expression above (incl. air term)
```

Validated live (cardinal ESS, measured/predicted ratio ≈ 1.000):

| f | vel | anim | air | measured | predicted | ratio |
|---|-----|------|-----|----------|-----------|-------|
| 1 | −233.84 | 3.54 | 790 | 214.12 | 213.98 | 1.0007 |
| 2 | −233.67 | 10.75 | 789 | 143.65 | 143.52 | 1.0009 |
| 3 | −233.51 | 17.97 | 788 | 203.43 | 203.43 | 1.0000 |
| 4 | −233.34 | 2.18 | 787 | 219.71 | 219.59 | 1.0005 |

Displacement oscillates 214→144→203→220… as anim cycles — the head-bob term. (Raw data:
[reference/data.md](../reference/data.md).)

## Neutral animates differently

In [neutral](neutral.md) the anim wraps at **26** (not 23) at rate `0.5 + 2.5·(1 − (air+1)/900)`,
speed-independent. The 23↔26 difference is the source of the [x598 scramble](pumps.md#the-x598-scramble).

## See also

- [Constants](../reference/constants.md#animation) · [Strobo](strobo.md) ·
  [model/fp-faithfulness](../model/fp-faithfulness.md) (f32 + console cosine precision).
