# The roll's cut window - the earliest and latest a roll can stab

**Answers:** How early can the B thrust fire out of a forward roll? How LATE can it? Does holding the
stick during the roll open the cut window sooner? What sets the aim of the cut once it is open?
**Status:** decomp-derived from the HIO data and confirmed against a console-delivered
[roll stab](roll-stab.md). Enforce it where an input stream is BUILT, not only where it is replayed -
see the rule below.
**Source:** decomp `d_a_player_main.cpp` (`procFrontRoll` 6852, `procFrontRoll_init` 6817,
`setSingleMoveAnime` 12795), `d_a_player_HIO_data.inc` (`daPy_HIO_roll_c0::m`); sim
[`tww_sim/land/procs/roll.py`](../../tww_sim/land/procs/roll.py) (`_roll_exit`) and
[`tww_sim/land/hio.py`](../../tww_sim/land/hio.py) (`ROLL_RATE`/`ROLL_EARLY`/`ROLL_END`). Values:
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

## The gate is the animation frame, and only that

`procFrontRoll` routes to a cut through `checkNextMode(1)`, and reaches it on one condition:

```c
if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mRoll.m.field_0x10) {   // 17.0
    checkNextMode(1);
```

The roll's frame control is set by `procFrontRoll_init` through
`setSingleMoveAnime(anm, f32 rate, f32 start, s16 end, f32 morf)`:

| | field | value |
|---|---|---|
| rate | `mRoll.field_0x8` | **1.1** per frame |
| start | `mRoll.field_0xC` (passed as `param_1`) | **0.0** |
| gate | `mRoll.field_0x10` | **17.0** |

So `getFrame()` after k frames is `1.1k`, and `1.1 x 16 = 17.6` is the first value past 17.0. **The
earliest cut dispatch is roll step 15.**

Two things worth stating because both were guessed wrong before being checked:

- **the start frame is 0.0.** A model that initialises `roll_frame = 0` is right, but only by luck of
  the value - `setSingleMoveAnime` takes rate BEFORE start, and the same argument slot is read as a
  rate for the roll and as a start for the cut. Re-derive the layout rather than pattern-matching it.
- **the stick is not in the gate.** `mStickDistance` appears in the *other* branch of `procFrontRoll` -
  the `getRate() < 0.01` path, where a neutral stick subtracts `field_0x20` from `mNormalSpeed`. Holding
  the stick up (or any direction) through the roll **cannot** make the cut window open sooner.

## And there is a ceiling, one step past the anim

The same `getRate() < 0.01` branch is the window's far edge. `1.1 x 18 = 19.8` is the first value at or
past `ROLL_END` 19.0, so **roll step 17 is the last step the roll still exists on** - and it still cuts,
because `_roll_exit` takes the buffered-B branch before `checkNextMode`. One step later there is no roll
to press B into: it has already exited to MOVE (or ATN_MOVE), and the press does nothing.

**The whole window is roll steps 15..17.** Derive it from `ROLL_RATE` / `ROLL_EARLY` / `ROLL_END` rather
than restating the tuple, so a change to the HIO block cannot leave a hardcoded range behind.

## What the window does and does not decide

It decides whether a press produces a cut. It says nothing about where that cut lands: the thrust is a
fixed root-translate lunge ([roll-stab.md](roll-stab.md)), so each step within the window fires it from
a different position along the roll, and only some of those reach a given target. Whether a
*dispatchable* thrust also *arrives* is a separate question with a separate answer - measure it, never
read it off the window.

What the stick DOES control once the window is open is the cut's **aim**: `_roll_exit` takes
`aim = target if msd > 0.05 and not l_held`, so a held direction re-aims the lunge and L held routes to
CUT_A instead of CUT_F.

## The rule

**A formula in closed form is not an enforced constraint.** Computing `cut_step = thrust + 2` and never
asking whether that step is dispatchable is how a schedule builder prices a press the game refuses -
while the simulated reference refuses it silently, because a refusal that raises somewhere else is not
a refusal here. And a fidelity gate that samples only the range where the formula is already known good
tests nothing about where it is used: sweep the range the caller can actually emit.

## See also

- [roll-stab.md](roll-stab.md) - what the cut does: the single-frame lunge, CUT_F vs CUT_A, the aim range.
- [roll.md](roll.md) - the roll itself, its speed law and its ordinary exits.
- [roll-attack-threshold.md](roll-attack-threshold.md) - the gate on the A that starts the roll.
- [roll-lean-decay.md](roll-lean-decay.md) - what the body is doing by the time the window opens.
