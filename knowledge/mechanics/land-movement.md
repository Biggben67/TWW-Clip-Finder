# Land movement - overview & index

**Answers:** Where do I find each land-movement tech? What's the shared model (the two angles, the
proc state machine, the bit-exact status)?
**Status:** validated live - the flat-ground walk, the ATN_MOVE tier (brakeslide/EBS), the forward
roll + roll-stab, the ground-turn procs (WAIT_TURN/MOVE_TURN/SLIP), the ballistic hops, and the C-up
freeze are all simulated in `tww_sim.land`; facing/travel/speed and position are **bit-exact** vs live
(**14 sim-vs-live cases**, each also locked OFFLINE by a per-frame recorded golden -
`tests/test_land_goldens.py`, recorded once by `tests/dolphin/record_land_goldens.py`). Anchor
`land_flatwalk@twwgz.sav`.
**Source:** decomp `d_a_player_main.cpp` proc enum + the per-proc functions; live captures
(`harness/capture/land_capture.py`). Constants:
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

Land is the next target after superswim. Unlike swim, it separates **two headings** - travel
(`current.angle.y`, velocity) and facing (`shape_angle.y`, body) - and a signed `potential_speed`;
every ground tech lives in how those three diverge. The proc state machine dispatches by `link_state`
(4 WAIT · 5 FREE_WAIT · 6 MOVE · 7 ATN_MOVE · 23 WAIT_TURN · 24 MOVE_TURN · 25 SLIP · 30 FRONT_ROLL ·
CUT_F/CUT_A · SUBJECTIVITY). Each tech has its own single-topic page:

| Tech | Page | What |
|------|------|------|
| Walk / run baseline | [walk-run.md](walk-run.md) | the two angles, +3.5 accel to the 17 cap, the `speedF` foot-plant composition |
| Brakeslide / EBS | [brakeslide-ebs.md](brakeslide-ebs.md) | L-held brake, the extended (camera-relative) preservation, facing/travel decouple, the wiggle EBS + L+Up cancel |
| Forward roll | [roll.md](roll.md) | FRONT_ROLL (26-cap), the frame-perfect roll-EBS, chained/intermediate rolls, the anim reset that makes the freeze analytic |
| Roll stab | [roll-stab.md](roll-stab.md) | the CUT_F/CUT_A 49.22 single-frame lunge (the seam-clip reach) |
| Walk stab | [walk-stab.md](walk-stab.md) | the no-roll thrust (40.22 lunge from a capped walk), the item put-away delay, which corners clip without a roll |
| Ballistic hops | [ballistic-hops.md](ballistic-hops.md) | sidehop / backflip (the A=roll vs L+A=hop mapping) + the ESS+C-down aim-turn |
| Ground turns | [ground-turns.md](ground-turns.md) | WAIT_TURN pivot / MOVE_TURN turn-around / SLIP skid on a hard reversal |
| Precise stop | [precise-stop.md](precise-stop.md) | the C-up SUBJECTIVITY freeze, live-valid sticks, L-target, B-cancel, the input-driven `step()` gesture |

## Shared status

**All land position is bit-exact with the anim data present** (`tww_sim.core.anim`, the ported J3D
engine); the calibrated fallback is used only when the keyframe DATA (dev-supplied, gitignored under
`_generated/anim/`) is absent, and the offline goldens SKIP then. Position/precision detail:
[model/land-sim.md](../model/land-sim.md); the foot FK → `speedF` engine: [model/anim-engine.md](../model/anim-engine.md);
the FP contract: [model/fp-faithfulness.md](../model/fp-faithfulness.md). The target→inputs planner:
[model/land-planner.md](../model/land-planner.md); the human-consistent setup finder:
[model/land-setup-finder.md](../model/land-setup-finder.md).

## See also

- [ESS](ess.md) - the `(128,110)`-class stick position land reuses · [Camera](camera.md) - `csangle`,
  a live per-frame movement input.
- [seam-clip](seam-clip.md) / [actor-push](actor-push.md) - where the roll-stab lunge + a Tetra push
  produce a wall-corner clip.
- `_notes/tww-sim-architecture-design.md` §5/§5b - how land folds into the generalized proc-machine sim.
