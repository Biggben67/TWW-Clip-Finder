# The plow ejects the pushed actor to a fixed distance, whatever you seed

**Answers:** Why does sweeping the pushed actor's PLACEMENT change nothing about the contact my cut frame
gets? Why is my search flat in her position? Where does a plowed actor end up after a roll sweeps past
her, and can I choose it? Which axis is left once the placement is dead?
**Status:** measured on a flooded-Hyrule Tetra corner and reproduced by the coupled stepper.
**Source:** [`tww_sim/core/cc_push.py`](../../tww_sim/core/cc_push.py) (`co_move_pair`) and the native
sweep core [`tww_sim/core/_shovec.pyx`](../../tww_sim/core/_shovec.pyx) (`ShoveCtx._run`, and the
`extra=True` contact pair). Constants:
[reference/constants-npc.md](../reference/constants-npc.md#collision-actor-co-push).

---

## The mechanism

`dCcS::SetPosCorrect` splits one Co overlap **50/50** between a same-rank pair
([actor-push.md](actor-push.md)), so every frame the two cylinders overlap by `cross_len` the pushed
actor is displaced `0.5 * cross_len` **directly away from the pusher's Co centre**. Nothing pulls her
back. Over the frames a roll spends near her that is a contraction with a fixed point:

- seed her deep inside the pusher and the first frame ejects her by half of a large overlap;
- each following frame the overlap is roughly halved, so the displacement decays geometrically;
- by the time the roll's late frames arrive she is sitting **just outside the radius sum**, and where
  exactly is set by the ejection history, not by where she started.

So her distance from the Co centre on any late frame is an **attractor**. Seeding her a unit closer buys
a slightly deeper early plow, which ejects her a unit further; the two cancel.

## What that measures

Over a +-40 u grid of static seeds along and across the approach ray at the earliest cut step (25 seeds,
24 of which come into contact at all):

| | |
|---|---|
| cut-frame distance `\|c - t\|` | **87..93 u** for 22 of the 24 (one outlier at 68) |
| how far she was displaced getting there | **10..60 u** |
| what the corner needs | **<= 79.4 u** ([../model/required-cut-contact.md](../model/required-cut-contact.md)) |

The single seed that does arrive inside the radius gets there with 12 u of overlap and a push aimed so
far off the useful direction that it is the **worst** row on the grid. That is the trade in one line:
the push that aims at the corner is the push that has just plowed her out of reach of it.

## Why it makes a search go blind

With no overlap on the cut-consumed frame the push is zero, and the result stops depending on her
placement **at all**. A climb on the depth therefore has no gradient exactly where it needs one to walk
her into contact - the objective is flat over the axis being swept, which reads as "this axis does not
matter" rather than "this axis is saturated". Report the **contact pair** for that frame (the
animation-posed Co centre and where she is standing, `ShoveCtx.sweep_par(..., extra=True)`) so the gap a
search must close is visible instead of hidden behind a zero.

## The axis that survives it

Momentum. A displacement cannot be undone by a placement, but it can be fought by a velocity, so the
seed gains `(speedF, facing, stt)`. What is deliverable is narrow and worth stating:

- `stt` must be the MOVE state; the idle state has already zeroed her `speedF`, so a moving idle seed is
  not a state the game produces - and the idle branch never touches `speedF` again, so a simulator
  handed one integrates it forever.
- `speedF` is capped at her follow cap.
- Near the pusher she has **no drive**: the follow target speed is `0.04*sqrt(d^2 - 130^2)`, zero inside
  130 u ([tetra-follow.md](tetra-follow.md)). A seed near the corner is *residual* momentum decaying
  1.0/frame, spent after `speedF` frames. It does not close the contact at the cut: it buys a
  **different ejection history**, i.e. a different place to be standing when the animation-posed Co
  centre swings past.

Measured, the momentum axis moves the equilibrium by about 3 u against a 10.8 u deficit: real, and not
enough on its own.

## See also

- [actor-push.md](actor-push.md) - the 50/50 split this contracts on.
- [push-magnitude.md](push-magnitude.md) - the per-frame depth law, and the sustained fixed point that is
  the same mechanism seen from the pusher's side.
- [cut-frame-co-swing.md](cut-frame-co-swing.md) - why the frames before the cut are not free.
- [../model/placement-standability.md](../model/placement-standability.md) - a seeded placement is not
  automatically a position she can stand in.
