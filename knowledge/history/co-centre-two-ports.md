# The Co-centre "two ports" seam

> **status: historical** - this records a diagnosis that was right about the correlation and wrong
> about the LAYER, which is a reusable mistake. Current truth: the root cause is
> [model/anim-frame-is-f32.md](../model/anim-frame-is-f32.md), and the settled centre is
> [mechanics/link-co-centre.md](../mechanics/link-co-centre.md).

## What was claimed

A cross-engine pre-flight rejected a handful of already-confirmed push candidates: the composite
per-frame stepper refused a ~49.86 u lunge that the fast scoring engine scored genuine, and one of the
refusals was the frame-minimal survivor of the pass. It was recorded as *agreement is a property of
the CANDIDATE* and promoted from a diagnostic into a filter.

## Where it was traced

To one code seam. Two ports compute the same quantity: `foot_fk.FootFK.body_co_center` (rebuilt from
the pose driver's stored old pose, what the composite stepper carries) against
`body_cyl.roll_co_chain_consts` (the `rollf` anim sampled directly, what the fast engine bakes). They
agreed only to **1-2 ULP**.

The census was clean: every rejection sat on a frame where the two ports differ, none of the drops
from other gates did, and almost none of the kept candidates did. The causal test was clean too:
swap the composite onto the fast engine's centre and every rejection agrees, two of them flipping to
the identical lunge.

Neither engine was changed, and the question was recorded OPEN, because every console capture in hand
fell on a candidate where the two paths agree -- measured, zero frames changed on the one that had
been delivered -- so no capture discriminated. `roll_co_center` was console-gated 0-ULP at the leans in
question; `body_co_center` was live-pinned only to a `<=6.1e-5 u` **tolerance**, about 1 ULP at those
magnitudes. Suggestive, not evidence. That restraint was right: picking the tighter-sounding gate
would have been a coin flip dressed as a decision.

## What overturned it

A console delivery on a *rejected* candidate. It clipped -- the lunge landed bit-identical to the fast
engine's number, on the cut frame and on two pre-cut control samples, both actors.

Then the ULP-level diff moved the answer one layer down: **neither port was wrong.** They were
sampling `rollf` at two different f32 frames, because the frame ctrl stored the Python `double` its
caller passed where `J3DFrameCtrl::mRate` is f32 (`tww_sim/core/anim/anim_state.py`; the roll's rate is
`ROLL_RATE` in `tww_sim/land/hio.py`), and at roll frame 2.2 -> 3.3 the true f32 sum is an exact tie.
Rounded at the `FrameCtrl` boundary, the two ports agree bit for bit, the composite reproduces the
capture 0-ULP, and every one of the rejected candidates delivers.

## What to carry forward

- **"A property of the candidate" was a code seam not yet named** -- and **a code seam can itself be a
  symptom.** Two implementations that disagree may both be faithful and be fed different inputs. Ask
  what each one is *given* before asking which one is right.
- **The measured cost was accurate and the reason it was small was not.** "A few candidates, zero
  frames" read as evidence the seam was peripheral. It was one f32 tie in the shared anim engine,
  reachable by anything that advances a frame ctrl.
- **The experiment design is the transferable part.** With every capture in hand blind to the
  question, the move was not a better argument -- it was finding the case where the two answers are
  tens of units apart instead of 1 ULP, so a single run could not come back ambiguous.

## See also

- [co-centre-body-chn-twist.md](co-centre-body-chn-twist.md) - the earlier mistake on the same
  quantity: a lean term ruled out by a capture that could not see it.
- [aim-alphabet-whole-grid.md](aim-alphabet-whole-grid.md) - a third of the same family: a claim
  measured on the engine that shared its omission.
