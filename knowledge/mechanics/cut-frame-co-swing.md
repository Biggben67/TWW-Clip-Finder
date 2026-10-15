# The cut frame's Co-centre swing

**Answers:** Why does the same corner clip on one thrust and refuse on the one two frames earlier, when
the animation is identical? Which frame of a roll can a cut actually collect a push on? Why is sweeping
the pushed actor's placement, velocity, lean and aim worth so little at the earliest thrust?
**Status:** derived from the roll animation and confirmed against a delivered
[roll-stab clip](roll-stab.md), whose free ~1.2 u of overlap this predicts the sign and the frame of.
**Source:** the animated Co centre - [`tww_sim/core/anim/body_cyl.py`](../../tww_sim/core/anim/body_cyl.py)
(`roll_co_center`, `roll_co_chain_consts`) and
[`foot_fk.body_co_center`](../../tww_sim/core/anim/foot_fk.py); the push it feeds is
[actor-push.md](actor-push.md).

---

## The one number

A cut consumes the Co overlap on the frame **before** it fires, and a pushed actor shoves Link
**directly away from herself** - so the only direction she can pay in is up the line from her to him.
When Link is braced against a wall his feet contribute nothing that frame, and the Co centre's entire
step is the animation's. Project it on the roll direction:

    swing  =  (off[cut_step - 1] - off[cut_step - 2]) . m_hat

`off[k]` is the animation-posed Co centre's offset from his feet - the root/neck joint midpoint
([link-co-centre.md](link-co-centre.md)) - at roll step `k`. **Positive means the cylinder is moving
forward, away from the one direction that pays; negative means it is swinging back onto her.**

Across the three dispatchable thrust steps ([roll-cut-thrust-floor.md](roll-cut-thrust-floor.md)):

| cut fires on roll step | consumed frame | swing | frame before |
|---|---|---|---|
| 15 | 14 | **+8.9252** | +8.07 |
| 16 | 15 | **+1.8547** | +8.93 |
| 17 | 16 | **-1.2850** | +1.85 |

That ordering **is** the push ordering measured independently from the depth law (+0.1304 / +0.4773 /
+0.5175 u of useful push). The clip a corner actually gives is not a lucky placement: it is the frame on
which the cylinder comes back.

## What the roll is doing

The Co centre sweeps forward to +31.3 u during the launch, back through the tuck to -13.5 u at roll step
11, then straightens hard:

    step   9    10    11     12     13    14    15    16    17
    along -0.7 -8.1 -13.5  -13.2   -5.1  +3.8  +5.7  +4.4  +4.0

The straightening is the fast part, +8.07 then +8.93 u/frame, and the earliest cut lands on both of
them. The latest lands two frames later, after the recovery has settled and reversed. Same animation -
and this names exactly which property of "a different frame of it" does the work.

## Why it is a property of the animation and not a knob

`off[k]` is a pure function of `(facing, roll_frame, lean)`:

- `roll_frame` is a fixed f32 accumulation of the roll rate, so it is pinned by `k`
  ([../model/anim-frame-is-f32.md](../model/anim-frame-is-f32.md));
- the [lean is spent](roll-lean-decay.md) long before step 15, so it cannot move a pose there;
- the facing rotates the offset **and** the direction it is projected on together, so over a whole
  ~45-cell aim window the swing varies by less than **1e-4**.

There is no knob on it. Moving where the pushed actor stands, how fast she is closing, which aim cell
fires and where Link enters changes none of: which frame of the roll the cut lands on, or which way the
cylinder is travelling when it does.

## Why the frames before it are not free either

The overlap the cut sees is not independent of the frames before it: a plow resolves the whole
penetration each frame ([plow-ejection-equilibrium.md](plow-ejection-equilibrium.md)), so a spot that is
touching on the cut frame was touching more deeply the frame before and has been ejected for it. With
the cylinder receding at ~8.9 u/frame, reaching a given overlap on the cut frame demands roughly twice
that on the frame before, and twice again before that - a chain that runs past an 80 u radius sum inside
three or four frames. A closing velocity offsets part of it (capped, and decaying with no drive at close
range - [tetra-follow.md](tetra-follow.md)) but does not turn the sign of the swing.

## Reading it on a new corner

The swing is analytic and instant, so **check it before pricing a thrust step**. A step whose consumed
frame has a positive swing is collecting its push from a receding cylinder, and every downstream search
is fighting that; one with a negative swing gets contact for free. It is a gate and not a rate: a
negative swing admits a clip, it does not supply the geometry or the plan.

## See also

- [link-co-centre.md](link-co-centre.md) - what `off[k]` is and how it is computed.
- [push-magnitude.md](push-magnitude.md) - the swing is also why one frame can beat the sustained ceiling.
- [roll-cut-thrust-floor.md](roll-cut-thrust-floor.md) - which roll steps a cut can fire on at all.
- [roll-stab.md](roll-stab.md) - the lunge the cut frame delivers.
