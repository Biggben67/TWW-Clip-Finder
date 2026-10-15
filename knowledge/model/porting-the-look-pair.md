# Porting the look pair: what a ratio can and cannot tell you

**Answers:** My profile says two models are 89% of a step - is that the whole story, and how much of it
do I actually get back? How do I port a stateful animation model into C without silently changing what
it computes? What does a 0-ULP gate have to compare when the model has a long memory?
**Status:** the NPC look model ([tetra-look](../mechanics/tetra-look.md)) and Link's head twist
([link-head-look](../mechanics/link-head-look.md)) are both PORTED into the native core
(`Zl1LookCore` / `NeckLookCore` in [`_zl1c.pxi`](../../tww_sim/core/anim/_zl1c.pxi), armed by
`LandCore.seed_look`), and were 0-ULP against the Python models on every field of their hidden state;
the coupled step went **9279 -> 62682 steps/s (6.8x)**. The frame that called them was a coupled
two-actor driver that no longer ships, so on the public `LandCore.step` the pair is resident but never
advanced. **No offline gate ships in this repo** either - the models' anim banks are disc-extracted and
gitignored, so nothing here can even load them on a clean clone.
**Source:** [`tww_sim/core/anim/_zl1c.pxi`](../../tww_sim/core/anim/_zl1c.pxi) (the port),
[`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) (`seed_look`, `head_top_exec`, `head_mtx_exec`, and
the snapshot accessors the 0-ULP gate diffs), against [`tww_sim/core/npc_zl1_look.py`](../../tww_sim/core/npc_zl1_look.py) and
[`tww_sim/land/neck_look.py`](../../tww_sim/land/neck_look.py).

---

## The ratio was right about the target and wrong about the size

The port was named from a ratio: a stripped native run at 98179 steps/s against 10797 with the Python
models in the loop, so the two are ~89% of the step and "worth ~9x". Measuring the split first said the
same thing more precisely, and the extra precision mattered:

| piece | us/frame | share |
|---|---|---|
| the C core step | 10.0 | 9.1% |
| Link's head twist (select + update) | 14.9 | 13.4% |
| the NPC look step | 85.9 | **77.5%** |

and inside her frame the head POSE is 71% of it (the local-pose build alone 52%), the look-at chase 20%.
So the money is her **J3D pose chain**, which makes this mostly a DATA port - her keyframe bank has to
become C-resident the way Link's `AnimData` already is - and not a control-flow one.

**The delivered win is 6.8x, not 9x, and the gap is the point.** A ratio of "X is 89% of the step"
silently assumes the ported X costs nothing. It does not: the look pair is 5.6 us/frame in C against a
10.4 us core, so it is still 35% of the step afterwards. The honest form of the estimate is
`1 / (rest + ported)`, and the ceiling it names (the stripped run) is a number you approach and never
reach. Quote the delivered figure.

## What made it cheap, and what would have made it wrong

**The C engine already had the two pose values.** `LandCore.head_top_exec`/`head_mtx_exec` were built for
the Python models to call; running them in-frame needs the same two matrices. But called separately they
cost **two full 7-joint FK walks**, and the head-top IS the head matrix plus one head-offset multiply
(`d_a_player_main.cpp:11592`) - so the port takes the matrix once and derives the top from it.
Worth 6.5 -> 5.6 us/frame, and free of risk because it is the same value by construction.

**The sqrt is not the sqrt.** Both look models reach their `absXZ` through
[`core.collision.fsqrt`](../../tww_sim/core/collision.py), which is `f32(sqrt(f32(x)))` - a
CORRECTLY-ROUNDED square root. The native engine also carries the MSL `frsqrte` + 3-Newton shape the
game links for `std::sqrtf` (pinned in the shipped JP binary,
[../mechanics/actor-push.md](../mechanics/actor-push.md)). They agree to ~2^-32 relative, which is
exactly the size of bug that survives a plausibility check and dies in a 0-ULP gate. **Port the sqrt the
model you are reproducing uses**, not the one that is more faithful to the console, or the port stops
being a port.

**Her non-morf pose is euler, not quat.** The local matrix is built with
`J3DGetTranslateRotateMtx` off the anim TRS while STORING the euler-to-quat for the next morf. Those are
not the same matrix in the low bits, so a port that "simplified" to one path would be wrong on every
non-morf frame - which is most of them.

## Gating a model with a long memory

The eye is one output of a state machine that remembers. Two things follow for the gate:

**Compare the hidden state, not the output.** Her morf's per-joint OLD-POSE STORE is rewritten every
frame and only reaches the eye through the NEXT blend, so a wrong store is invisible for one frame and
then diverges. Diff the whole snapshot - the joint chase angles and their clamped targets, every timer,
the frame ctrl, the old-pose store, Link's `m3564` - not just the eye.

**The recorded window does not exercise her.** Over the validated 45 frames her look-target flag is set
on every frame: she looks at Link and the look-around anim never fires, because its timer was seeded
past the end of the window. So the anim switch, the morf blend it starts, the wrap flag and the RNG
horizon are all outside the fixture, and a gate that only replayed the movie would be comparing four
fields against constants. Run a long window too, and ASSERT the coverage you need.

Constants are handed to C from the Python models at arm time rather than re-declared in the `.pxi`: one
canonical value per constant, and a change to a model cannot leave a stale copy compiled into C behind it.

## Once the state moves to C, READ it there - do not mirror it

In native-look mode the eye, the NPC's attention target and `m3564` live in the C core, so the
run-object's accessors for them should be **properties that read the core on access**. The alternative -
mirroring the values back into Python attributes every frame - costs the hot loop something on every step
to produce a copy that is wrong in the one way that matters: stale, on a run that still looks like a run.
Keep the seed object as the SEED rather than syncing it, so there is exactly one live copy and reading
the state means asking for it.

The one wrinkle is the seed itself: the core is built FROM those same attributes, so the properties must
fall back to the Python values while the core does not yet exist. That guard is a genuine two-phase
lifetime, not a defensive check.

## See also

- [../mechanics/tetra-look.md](../mechanics/tetra-look.md) ·
  [../mechanics/link-head-look.md](../mechanics/link-head-look.md) - the two models being ported.
- [the-branch-a-fast-engine-skips.md](the-branch-a-fast-engine-skips.md) - the same job for a collision
  pass, and the refuse-don't-skip rule.
- [anim-engine.md](anim-engine.md) - Link's own pose pipeline, whose `AnimData` contract this follows.
