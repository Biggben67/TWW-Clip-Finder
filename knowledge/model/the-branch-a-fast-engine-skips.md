# The branch a fast engine skips: port it, or make it refuse

**Answers:** My fast engine is missing a branch the slow one has - what does that actually cost me, and
how do I keep the gap from lying to me while I queue the port? Where do I get the collision / keyframe
data a C step needs? What does a 0-ULP gate for a ported branch have to compare?
**Status:** the two branches described here are resident in the native core's coupled-actor surface -
both actors' `dBgS_Acch::CrrPos` wall pass ([`_acchc.pxi`](../../tww_sim/core/anim/_acchc.pxi)) and the
roll's buffered-B CUT arm ([`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) `CutAnimData`,
`LandCore._cut_init`/`_proc_cut`, `seed_cut`, `seed_walls`, `wall_check`) - each written against the
Python procs as its oracle. The public `LandCore.step` does not dispatch either, so a native-only walk
still has no cut. Two mid-roll cases RAISE by design (below).
**Source:** [`tww_sim/core/anim/_acchc.pxi`](../../tww_sim/core/anim/_acchc.pxi) (the wall pass),
[`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) (`_link_wall_pass`, `_tetra_wall_pass`, `wall_check`),
and the Python oracles [`tww_sim/core/collision.py`](../../tww_sim/core/collision.py) /
[`tww_sim/land/procs/roll.py`](../../tww_sim/land/procs/roll.py).

---

## A missing branch does not announce itself

Both gaps had the same shape, and it is the shape worth recognising: **the fast engine did not fail on
the input the branch exists for - it computed something plausible and went on.**

- A collision mesh assigned to a native run was a **silent no-op**: the C step tracked the second actor
  as a bare XZ point, so a "walled" native run was bit-identical to an unwalled one and she went tens of
  units THROUGH a wall the console braces her against
  ([../mechanics/tetra-follow.md](../mechanics/tetra-follow.md)).
- A mid-roll **B press was ignored**: no buffered-B arm in the C roll proc, so the roll ran to its
  ordinary exit and the ~23 u thrust lunge simply did not happen
  ([../mechanics/roll-stab.md](../mechanics/roll-stab.md)).

Neither shows up as an error, a warning, or a diverging field - the run just answers a different
question than the one asked. Both were found by someone reading the C source beside the Python one. The
defence that works is not vigilance, it is **structure**: a branch the engine cannot carry must refuse
the frame.

## Refuse, don't skip

A `noexcept nogil` frame cannot raise - which is exactly why it is tempting to let it skip. The pattern:
the C step sets a sticky flag, and the GIL-holding caller converts it (`LandCore.wall_check`, called
**before any field is synced**, so a refused frame never leaks a half-computed state).

Two cases are refused rather than modelled, both consequences of wiring Link's mesh:

| case | why it is refused |
|---|---|
| the roll **bonk** (a head-on wall hit inside the crash window) | dispatches `procFrontRollCrash`, an unported proc. A bonked roll crashed, so the plan is dead either way. |
| an A press the wall turns into a **SIDLE** | `setDoStatus` SIDLE preempts ATTACK; the sidle proc is modelled on NEITHER path (`LandState.sidle_blocked` rejects the same stream). |

The same principle covers the wiring itself. A mesh handed to the core must go through a setter that
**re-seeds** it; a field assigned onto the Python object after construction cannot be intercepted, so
the step compares the run's meshes against the ones its core was seeded with and refuses a mismatch.
That turns "a probe that looked walled and was not" from a silent wrong answer into an exception.

## Where the data comes from

A C branch needs the same data the Python one reads, and the answer both times was to hand it over
rather than restate it:

- **The mesh** becomes a `WallMesh`: verts, planes, and the per-tri `sqrtf(nx^2 + nz^2)` flattened to C
  arrays, built ONCE per trilist and shared by reference (the `AnimData` contract), so a clone copies
  nothing and parallel workers read it. No AABB prefilter: at a few dozen tris the whole pass is far
  under the pose FK, so every tri is tested and exactness is structural rather than dependent on a
  margin being large enough.
- **The lunge** becomes a `CutAnimData`: joint 0's three translate tracks, evaluated by the keyframe
  interpolator already in the module. Nothing else in the cut BCK moves position, and a cut poses no
  foot chain, so that is the whole root-motion port.
- **The cylinders and the HIO fields** are read out of the Python modules at seed time (`seed_walls`,
  `land_init_consts`), never re-declared in the `.pxi`. One canonical value per constant, and a change
  to a model cannot leave a stale copy compiled into C behind it.

## What the gate has to compare

A wall pass is a transcription, so **Python is the oracle** and the sweep is the fixture: a
deterministic lattice over a real mesh at both actors' cylinders, sized so a few hundred candidates
genuinely correct against geometry. *A sweep that never touches a wall proves nothing.* Writing one
caught exactly one gap - the Python `acch_crr_pos` rounds both endpoints to f32 on entry (the console has
no f64 to skip) and the C port did not, which is a 1-ULP brace, which is a razor clip turned into a
block.

For the frame-level gates, three things a naive engine-vs-engine diff would miss:

1. **The unwalled arm is half the gate.** The port added branches to the hot frame; none of them may
   move a run with no mesh. It is the reference every other native gate is built on.
2. **A silently-uncut roll passes an engine-vs-engine diff by being equally wrong on both sides.** So
   reconstruct the cut frame from first principles as well -
   `((pre + speedF*dir(travel)) + the CC recoil) + rotate(m3700, shape_angle.y)` with `m3700_prev = 0` -
   and assert it 0-ULP on BOTH engines. That is a statement about the model, not about C.
3. **Every field the branch writes goes on the allowlist**, including the ones no earlier native gate
   had reason to read (`wall_hit`, `line_hit`, `wall_cir_hit`, `wall_angle`). A field nobody listed is a
   field a bug hides in.

## Why port a collision pass rather than prune around it

The asymmetry is the argument. In Python the wall pass costs well over half of a coupled step; in C it
costs a few percent. So a search that leans on a wall-free *constraint* instead of running the pass is
usually not making a fidelity choice - it is making an affordability one, and the affordability changes
once the pass is in C. Re-ask the question after the port.

## See also

- [porting-the-look-pair.md](porting-the-look-pair.md) - the same job for a stateful animation model,
  and what a gate for a long-memory model has to compare.
- [../mechanics/wall-response.md](../mechanics/wall-response.md) - the pass being transcribed.
- [fp-faithfulness.md](fp-faithfulness.md) - which ops fuse, and where an f32 round belongs.
