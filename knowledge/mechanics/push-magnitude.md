# How FAR a Co push moves an actor - the per-frame depth law and the sustained ceiling

**Answers:** How far can an actor-vs-actor push move an actor in one frame? Is `|speedF|/2` a hard bound
or an average? What sets the sustained push rate? Why does a shallow contact push less?
**Status:** validated - the per-frame law is verified frame by frame over a whole 72-frame push
sequence, and the sustained/per-frame distinction is measured off a recorded console window.
**Source:** decomp `dCcS::SetPosCorrect` (`d_cc_s.cpp:138`); the mechanism page is
[actor-push.md](actor-push.md); code [`tww_sim/core/cc_push.py`](../../tww_sim/core/cc_push.py)
(`co_move_pair`). Constants:
[reference/constants-npc.md](../reference/constants-npc.md#collision-actor-co-push).

---

This is the MAGNITUDE half of the [Co push](actor-push.md): that page says which way an actor is shoved
and by what mechanism, this one says how far.

## What a single frame IS bounded by, exactly

The ejection is the overlap depth halved, so with the pushed actor at rest the frame's push equals

    (R_link + R_actor - centre_distance) / 2

measured to Link's **animated** Co centre, not his feet ([link-co-centre.md](link-co-centre.md)).
Verified frame by frame over a whole 72-frame sequence at the 30/50 cylinder pair: `centre_feet` 45.9
gives 17.036 u, 59.6 gives 10.188 u, every frame, rolls included.

## The sustained rate is a STEADY STATE, not a bound

Because the two actors eject in opposite directions along the centre line, a sustained push settles at
each moving **half** of the pusher's own step: with Link at the roll cap 26 the pushed actor advances at
most `26 / 2 = 13.0` u/frame **on average**.

That fixed point follows from the law above rather than being a separate fact - each frame the pusher
advances by his step and both actors eject, leaving `centre_next ~ R_sum - advance`, which at 26 settles
at 54 and hence 13.0 u/frame. So the SUSTAINED rate is set by the MEAN centre distance.

**A single frame is not bounded by it.** The depth is measured to the animated centre, which moves by
Link's foot term *plus* the pose swing that leads or trails his feet by 6-28 u
([cut-frame-co-swing.md](cut-frame-co-swing.md)) - so a frame on which the swing carries the centre
forward pushes far harder than half the foot term. Measured on a console window: the biggest single
frame advances the pushed actor **18.84 u** (a FRONT_ROLL frame, ~1.45x the "ceiling"), and a 23-frame
stretch sustains **13.36 u/frame**. The swing cancels over a long enough window - the pose returns -
which is why the 44-frame mean is **12.758**, 98.2% of 13.0 and under it.

So: use 13.0 u/frame for a sustained rate or a distance estimate, never as a per-frame law, and never as
a hard floor on how few frames a displacement can take (a ~25-frame window can beat it by ~0.3-0.6
u/frame). A window that exceeds it is not a physics bug.

The same asymmetry runs the other way: contact going shallow costs the rate. On one measured arrival the
roll frames sustain 99.6% of the ceiling at mean `centre_feet` 54.1, while the junction frames between
them manage 93.5% at 55.4.

## Why the depth at the END of a push is not free

A contact that finishes shallow was shallow - and so pushing weakly - on its way there. So the depth a
push ends at and the distance it delivered are **anti-correlated**, and any objective that wants both a
shallow finish and a long displacement is asking for two things that move in opposite directions.
Measured over ~1500 real arrivals, the best achievable displacement degrades monotonically past a final
`centre_feet` of 50 u, at **0.32-0.53 u of displacement per u of depth**. Price both against the SAME
arrival; a depth taken from one population and a distance from another describes no reachable state.

## See also

- [actor-push.md](actor-push.md) - the mechanism: cyl-cyl overlap, the rank-table 50/50 split, which way
  each actor goes, and the FP shape of the distance.
- [link-co-centre.md](link-co-centre.md) - the animated centre the depth is measured to.
- [cut-frame-co-swing.md](cut-frame-co-swing.md) - how far that centre travels per roll frame, which is
  what lets a single frame beat the ceiling.
- [plow-ejection-equilibrium.md](plow-ejection-equilibrium.md) - what repeated pushes converge on.
- [roll.md](roll.md) - where the `speedF` 26 roll cap that sets the 13.0 fixed point comes from.
