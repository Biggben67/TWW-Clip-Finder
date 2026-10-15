# "Every aim in the window fires the roll"

> **status: historical** - this records a claim that was measured, written down, gated, and used to
> widen a search by 13x, and it was wrong because the engine it was measured on shared the omission.
> Current truth is [mechanics/roll-attack-threshold.md](../mechanics/roll-attack-threshold.md). Kept
> for the lesson, which is about measuring a dispatch on the model that dispatches it.

## What was claimed

A roll-entry search's aim alphabet started as the saturated octagon-boundary byte pairs -- the sticks
at full deflection -- because a roll was assumed to need a deep stick. That magnitude floor was then
called unphysical and removed:

> That floor is not a physical one: `_set_stick_data` latches the target from ANY non-dead-centre
> stick and `_roll_init` snaps facing to it unconditionally, while the roll's speed comes from the walk
> cap and not from the stick. **Measured, every aim in the window fires the roll and lands on the
> facing it commands**, so the alphabet is the whole decoded-angle grid.

That was a 13x widening of the aim axis, it was gated, and every pass afterwards drew from it.

## What it actually is

The reasoning about the ROLL is correct and still stands: a roll needs no magnitude, its speed comes
from the pre-roll `speedF`, and `_roll_init` snaps facing to the latched target at any deflection.
What it skips is **getting** the roll. `setDoStatusBasic` (`d_a_player_main.cpp:2220`) only sets
`dActStts_ATTACK_e` -- the one status `checkNextActionFromButton` turns into `procFrontRoll_init` --
above `mBasic.field_0x1C` (`ATTACK_MSD_MIN`, `tww_sim/land/hio.py`). At or below it the press is
`PUT_AWAY` and Link sheathes.

## Why the gate could not see it

"Measured, every aim fires the roll" was measured in the sim, whose roll dispatch tested only the
**locomotion** floor (`moving = msd > 0.05`, `tww_sim/land/state.py`), so it could only ever agree.
The confirm step -- whose entire job is "does Link actually roll from here" -- replays a real A-press
**on that same engine**, so it confirmed sub-threshold aims too. A gate is only evidence about the
thing it does not share with the claim.

The widening was worse than additive. The alphabet deduped the byte grid by decoded ANGLE and kept the
first pair in grid order, which is usually a shallow interior one -- so it did not merely add deep
aims, it **replaced** representatives with shallow ones. One angle's kept representative sat at stick
magnitude 0.540 while a human's own press for the same angle is at 1.0.

Any convenience inverse has that shape. `plan_land.stick_for_bearing` returns ONE byte pair per
(bearing, magnitude), so an alphabet built by inverting bearings is a set of *representatives*, and a
representative can be perfectly legal for locomotion and illegal for the dispatch you meant to press.

## What it cost

One console delivery, which is what falsified it: the frame-minimal hit of a 55-candidate pass, aimed
at magnitude 0.5705. The movie went out exactly as authored and Link never entered `FRONT_ROLL` at all
-- at the sampled frame he is walking to a stop with the target actor bit-identical to her pre-roll
position, because he never reached her. Of that pass's confirmed, DTM-deliverable hits, **36 of 55**
used the shallow representative and could never have rolled as pinned.

**Re-measured against the right atom, the axis lost nothing.** The physical atom is the sine-table
**CELL**, not the angle: `JMASSin`/`JMASCos` index `[(u16)angle >> 4]`, so two decoded angles inside
the same 16-BAM cell walk in bit-identical directions. Angles 40834 and 40841 both live in cell 2552,
so the dispatch gate moves that cell's representative to a deep member rather than deleting the cell.
Re-run correctly, the same scorings come back at the same entries and residuals, with no unrollable
aim among them and the frame floor unchanged. The "36 dead" number above describes the *pinned* rows
re-confirmed against the stale representative; it was never a property of the candidates.

The honest reading is the one in between the two claims: the alphabet is every reachable angle CELL,
each represented by a member deep enough to dispatch.

## The lesson

**Measure a dispatch against the decomp, not against the model that performs it.** Every part of this
claim was checked -- swept, gated, cross-checked against a recorded human's own inputs -- and the one
unchecked assumption was the branch that decides whether the press is a roll at all. The
containment check ([[search-space-contains-human]]) passed throughout, because a human's stick is a
grid member by construction; containment tells you the space is wide enough, never that every member
of it is legal.
