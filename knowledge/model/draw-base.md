# The draw base - WHERE and WHEN the model is posed

**Answers:** Which position does Link's model calc run from - the one at the start of the frame or after
`posMove` has moved him? Does the MOVE turn lean (`shape_angle.z`) go into the base? Why does a proc
`*_init` frame pose differently? Why does any of this matter when the base is cancelled out again?
**Status:** validated live 0-ULP: every model-local x/z of a console capture's `mFootData` toes and
heels matches at the sampled frames, and the anim-driven frames of a delivered plan went from 12-1159
ULP off to exact.
**Source:** decomp `d_a_player_main.cpp` `setWorldMatrix` (`:9559-9575`, called `:11551`) +
`commonProcInit` (`:5841`); sim
[`tww_sim/core/anim/foot_speedf.py`](../../tww_sim/core/anim/foot_speedf.py)
(`defer_draw`/`finish_draw`), [`tww_sim/land/state.py`](../../tww_sim/land/state.py) (the frame-end
block), [`tww_sim/core/anim/fk.py`](../../tww_sim/core/anim/fk.py) (`world_base`).

---

There is ONE `mpCLModel->calc()` per frame, and everything pose-shaped reads it: the foot toe stream
[posMoveFromFootPos](anim-engine.md#toe--speedf) consumes, the `setCollision` root/neck midpoint that
becomes the [Co-cylinder centre](../mechanics/link-co-centre.md), Link's `mHeadTopPos`. So they all
share one base matrix, and the base has three parts.

## Position: AFTER posMove, not before

`setWorldMatrix` builds `worldBase = transS(current.pos) . ZXYrotM(shape_angle)` late in `execute`,
after `posMove` has already integrated the frame's motion. The pose the game hands to the NEXT frame's
`posMoveFromFootPos` is therefore taken at the END-of-frame position - which is also why the toe stream
runs one frame behind (`t1` = last frame's draw, `t2` = the one before).

In the sim this is `FootSpeedF.defer_draw`: the compose reads only `t1`/`t2`, so `speedF` is exact
before the draw; the pose is stashed and `finish_draw()` lands it once `LandState.step` has moved Link.
A pre-integration draw is a different (wrong) base.

## Lean: `shape_angle.z`, except on a proc-init frame

`ZXYrotM` concats the Z rotation, so the MOVE turn lean (`m351C >> 1`, see
[ground-turns](../mechanics/ground-turns.md) and [roll-lean-decay](../mechanics/roll-lean-decay.md))
tilts the base. The exception is a frame on which a proc `*_init` ran: `commonProcInit` zeroes
`shape_angle.z` BEFORE `setWorldMatrix`, and `setMoveSlantAngle` only restores it afterwards, so that
frame draws **upright**.

"A proc init ran" = the post-step proc differs from the frame-START proc - and capture that before the
A-roll trigger, which would otherwise mask a roll entry. Same rule, same frame, for the Co centre: they
are the same calc.

## Why ULPs of base matter

The base is removed again by `m37B4` (`PSMTXInverse(worldBase)`), so in exact arithmetic none of this
would move the model-local pose at all. It is not exact arithmetic: the FK accumulates at WORLD
magnitude, so each joint matrix is quantized to the f32 spacing there - 1.22e-4 u at `|x| ~ 1600` - and
the cancellation cannot undo that. See [anim-engine](anim-engine.md#foot-fk-runs-in-world-space).

That granularity is the whole error budget of `f31_2`, the plant-toe delta: a walk step's delta is a few
units, so ONE world ULP in a toe component is a ~1e-4 u error in `speedF`. It is invisible while
`m3598 == 0` (momentum owns the speed and the stream is only warmed), and it *is* the position the
moment the walk anim owns the speed. Getting the base wrong costs 32-128 ULP per toe component and 1 to
~1000 ULP of Link position on the first anim-driven frames.

## See also

- [anim-engine](anim-engine.md) - the pose pipeline the base feeds
- [equipped-anim-set](equipped-anim-set.md) - WHICH anims get posed
- [wait-stop-pose](wait-stop-pose.md) - what gets posed while Link is standing still
- [../mechanics/link-co-centre.md](../mechanics/link-co-centre.md) - the Co centre built from the same
  calc, and the second place the lean lands
