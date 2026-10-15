# A candidate is a promise: prune on the input you intend to press

**Answers:** My search returns candidates that the confirm/replay step then rejects - the state looks
right, so what prune am I missing? How do I know a state my plan ends on can actually perform the
action the plan assumes? Which frame's proc does a queued button dispatch from? Is a validity prune
worth adding if it saves no simulation time?
**Status:** mechanism decomp-grounded and live-confirmed. The prune IS the sim's own A-dispatch
condition list (`state.py`, a port of `checkNextActionFromButton`), and every non-obvious condition in
it has been checked live from both sides: the wall/sidle preempt (gated kept-and-dropped in
[`tests/test_land_walls.py`](../../tests/test_land_walls.py)) and the stick-magnitude gate (a console
delivery whose A-press sheathed instead of rolling). Validated offline on an actor-push roll-entry fan,
where the prune agreed with a real A-press in both directions.
**Source:** `tww_sim/land/state.py` (the `checkNextActionFromButton` dispatch, `sidle_blocked` /
`attack_blocked`), `tww_sim/land/constants.py` (`ROLL_FROM`, `INPUT_DELAY`), `tww_sim/land/hio.py`
(`ATTACK_MSD_MIN`); decomp `checkNextActionFromButton` (`d_a_player_main.cpp:4309` -> `:4188`),
`setDoStatusBasic` (`:2220`). Values: [reference/constants.md](../reference/constants.md#land-movement).

---

## The shape of the bug

A search over "reach a state, then do X" is really enumerating a set of *promises*: each candidate
says **X will happen from here**. The keep-test almost always checks the part of the state the
scoring cares about - where the actor is, how fast, is he still inside some bound - because that is
the part the objective is written in. The part it forgets is whether the game will let X happen at
all.

That gap does not show up as a wrong answer. It shows up one step later, as a confirm/replay stage
that keeps rejecting hits which look perfect:

> a roll-entry fan for an actor push pruned on position (the follow bar) and speed (the walk cap),
> then predicted a roll entry from each surviving endpoint. Of the 23 genuine draws its widest pass
> returned, **3 did not roll at all** - the A-press landed while Link was mid-turn and simply kept
> turning.

Three draws is not much. The reason it is worth a page is that the search had no way to know: every
number it reported about those three was correct, and only an out-of-band replay could tell them
apart from the twenty that worked.

## Read the dispatch and turn each of its conditions into a prune

The fix is not a heuristic. The action you are promising has a dispatch in the decomp with an
explicit condition list, and **every condition in it is a prune you owe the search.** For the A-press
roll the conditions are: the button edge; no L held (with L it is a ballistic hop instead); a
*grounded, already-locomoting* proc, which resolves to `MOVE` or `ATN_MOVE` and nothing else; a stick
deflection past the ATTACK threshold and not merely past the locomotion floor
([mechanics/roll-attack-threshold.md](../mechanics/roll-attack-threshold.md)); and no wall pinning
Link head-on, which preempts the roll with SIDLE.

The fan enforced the first two by construction and the rest not at all. Encode each condition once,
where the dispatch lives (`land.ROLL_FROM` for the proc set, `hio.ATTACK_MSD_MIN` for the
magnitude), and have both the dispatch and the search read it - a search that restates the condition
is a search that will drift away from the physics it is predicting.

The failure the fan hit is the most likely one for any locomotion search: a turn proc. `MOVE_TURN` is
reachable from an ordinary walk (any stick reversal past the arbiter's threshold routes into it), it
looks exactly like a walk in position and speed, and it swallows the button.

A refused press is worth a **signal**, not a silent no-op. The sim latches `sidle_blocked` /
`attack_blocked` stickily on the state, so a planner can reject the whole input stream instead of
reading a state that quietly kept walking.

## Which frame's proc? The controller delay answers it for you

The subtlety that makes this prune cheap: you do not need to look ahead a frame.

The input is delivered on one frame and *acted* on a later one (`INPUT_DELAY` 2 for raw controller
latency, 1 for a DTM-driven replay -
[reference/constants.md](../reference/constants.md#land-movement)). The proc
field stored at the end of the delivery frame is precisely the proc the acting frame dispatches,
because the transition arbiter (`checkNextMode`) runs at the end of each frame and writes *next*
frame's proc. So the endpoint's own stored proc **is** the dispatch proc of the frame your queued
input acts on, and the prune reads a field the candidate already carries.

Worth checking rather than assuming on a new engine: if you get this off by one you will prune the
wrong frame and the gate below will fail in one direction only.

## Gate it against the real action, in BOTH directions

A prune like this is one line and reads a field the search already has, so the temptation is to gate
it against itself. That gate is vacuous - it only proves the field was copied. What has to be shown
is that the field *means* what it is being asked to mean:

- everything the prune KEEPS actually performs the action when replayed for real;
- nothing it DROPS would have.

The second half is the one that matters, because a validity prune that is slightly too strict is a
search that has quietly shrunk its own space
([[search-space-contains-human]] - the range must intrinsically contain the good input). On the push
fan both directions were checked against a real A-press replay, and the wired replay's own proc at
that frame was compared with the native core's - a cross-engine read, not the same number twice. The
sidle sibling is gated the same way: pinned head-on the roll must not fire and the flag must latch;
pinned obliquely the same press must roll.

## It buys correctness, not time - add it anyway

Be honest about what this class of prune is worth. It fires at *collection* time, after the frames
have already been stepped, so it saves no simulation: on that fan it drops about **7%** of endpoints
and the pass takes just as long.

What it buys is that the population you report is the population you can use. Every candidate a
search hands on is a claim someone downstream will spend a real run confirming, and 3 in 23 of those
being unactionable is a 13% tax on the most expensive step in the pipeline. A prune that removes an
entire *category* of false candidate is worth adding at zero speedup - and unlike a tuned threshold,
it can never remove a true one, because it is the game's own condition.

## See also

- [mechanics/roll.md](../mechanics/roll.md) - the roll itself (entry, speed, EBS exit).
- [mechanics/roll-attack-threshold.md](../mechanics/roll-attack-threshold.md) - the stick-magnitude
  condition, and what the model does with a refused press.
- [mechanics/land-movement.md](../mechanics/land-movement.md) - the proc set and the input mapping.
- [history/aim-alphabet-whole-grid.md](../history/aim-alphabet-whole-grid.md) - the same mistake in
  the aim axis: a search alphabet measured against the model that performs the dispatch.
