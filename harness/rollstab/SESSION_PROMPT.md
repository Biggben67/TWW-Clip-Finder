# Seam-clip session prompt (the standing instructions)

Tracked, durable, improvable. This file holds the STABLE instructions only. It asserts
NOTHING time-sensitive: current state (what is solved, what is open) lives in the
`## Status` section of `harness/rollstab/README.md` and the newest handoff, which are
authoritative. If this file and the README status ever disagree about state, the README
is right and this file is stale.

To start a session, paste this ONE line, the SAME every time:

    Read harness/rollstab/SESSION_PROMPT.md and follow it.

That is all that is needed. The default action is to continue the newest handoff's
"Next step". To steer somewhere else on a given session, add a goal after that line
(optional), e.g. "... This session's goal: <one line>."

---

OBJECTIVE (stable): given a fixed initial anchor state and a target seam, ONE-SHOT
compute the controller input sequence that clips Link through it, found ENTIRELY in
the sim, and DTM-verify it.

HARD CONSTRAINTS:
- Full search runs in < 2 minutes. No exceptions.
- Float-perfect: the shipped seq clips 0-ULP in the sim and reproduces live via a
  clean DTM (NEVER advancewith).
- PURE SIM, NO CALIBRATION. The search takes ONLY the static anchor (its seed.json)
  as input and produces the input sequence with no live-Dolphin round-trip in the
  loop. This was the ORIGINAL requirement.

STANDING PRINCIPLE ON CALIBRATION (this is why past sessions drifted):
  A live-calibration / teleport / position-feedback / per-move bias workaround VIOLATES
  the objective. Do NOT add one. If one still exists in the pipeline (e.g. a live
  calibration step), REMOVING it is the priority, not building on it. The root cause it
  papers over is the from-rest idle -> walk entry not being cold-start-faithful in the
  sim; the objective-compliant fix is to MODEL that entry from the anchor seed, not to
  seed it from a live run. Check the README ## Status for where this currently stands.

READ, IN THIS ORDER, before proposing anything or touching code:
  1. harness/rollstab/README.md: the pipeline, run protocol, verification, and the ## Status
     section (current state -- what is shipped, what is open and why). It is ~160 lines now; the
     session-by-session log it used to carry is harness/rollstab/README-archive.md, which is
     provenance, not state.
  2. harness/rollstab/ROADMAP.md: the multi-phase NORTH STAR (toward the Tetra seam
     clip) -- which phase is open and what its live-gated "done" is.
  3. The newest _notes/seam-clip-live-validation-handoff-*.md: this session's starting
     point and next step.
  4. knowledge/strategy/seam-clip-solver.md: why the acceptance region is f32 DUST and
     every candidate must be tested exactly, not against a fitted ribbon.
  5. knowledge/history/seam-clip-dead-ends.md: the full RULED-OUT ledger (sessions 4-9).
Then restate, before editing anything: (a) current state in one paragraph, (b) the
specific goal for THIS session, (c) your plan. If the session message names no goal,
the goal IS the newest handoff's "Next step"; if there is no handoff yet, ask.

DO NOT REOPEN SOLVED WORK. The README ## Status says what is already bit-exact / shipped
/ found-routinely. Do not rewrite the sim model, the solver acceptance test, or the
collision/cut models without a state-level reason. If you believe the frontier is
somewhere other than what the Status + handoff say, state why BEFORE starting.

METHOD REFERENCE (for HOW to be fast + exact, a pattern to absorb, not code to reuse):
tww_sim/land/plan_land/_freeze/roll.py, the SOLVED 1D freeze search. Its pattern is a
cheap monotone predictor (pos_cap) + subtree prune + exact bit-confirm, no table, no
calibration. Any search work must follow that pattern; brute-force sweeping is the
known-slow path that blows the 2-minute budget.

IF YOU MUST CHANGE THE SIM, research in priority order:
  A. Decomp (src/d/, Link's actor + camera are complete): ground truth.
  B. Dolphin breakpoints / ASM / RAM: only if decomp is insufficient.
  C. Guess-and-check / derivation from samples: only if A and B fail, and CONSULT
     DERECK FIRST.
After any 0-ULP sim fix, add a live-data-backed regression test:
  1. memory-capture a live input sequence (xyz, anim frame, facing, proc, ...);
  2. write a sim unit test seeded from that captured source of truth;
  3. enforce 0-ULP on ALL frames.
If unsolved at session end, create the test anyway and let it flag RED.

RESPECT THE DEAD-END LEDGER (knowledge/history/seam-clip-dead-ends.md + README "Dead
ends" + the newest handoff). Do not re-run a ruled-out approach without NEW evidence;
if tempted, first state what changed. When you rule a NEW approach out, APPEND it to
knowledge/history/seam-clip-dead-ends.md. That is what keeps the ledger alive.

STALL RULE: if you get stuck, or are about to spend real effort outside the handoff's
plan, surface it before continuing.

REPO CONTEXT (2026-08-20): main was split. A one-off Courtyard Tetra-push route planner had been the
only thing worked on for ~170 sessions; it is parked on branch dmiller/courtyard-tetra-push (forked
at c516cc3) and nothing on main depends on it. Generalizing THIS solver is the active work again.
The era's general half was forward-ported: the native player engine, the land camera, the NPC
look-at head and the attention/lock-on machine are all on main now, and the native driver has had
that planner's search block cut out of it (tww_sim/core/anim/_anmc.pyx, no "courtyard" left in it).

Savestate slot 5 = kaze flat room for roll clips. Savestate slot 3 = the WALK-STAB kaze r11 seam
(session-28 pivot; durable anchor `tests/dolphin/anchors/kaze_r11_walkstab@twwgz.sav`, was the
flooded-Hyrule Tetra corner (-1727,-990) for Phase C, slot reused). **Savestate slot 6 = the SHIPPED Tetra push-aside clip** (Phase T,
live bit-exact): its whole mint/author/deliver/diff pipeline is `harness/rollstab/pushaside.py` --
read that module's docstring BEFORE any Tetra-clip delivery work; it encodes the four delivery truths
(walkable Tetra floor / NEUTRAL roll stick / B one step later in the DTM / seed the sim at the DTM's
REAL roll entry) that cost session 22 and are NOT re-derivable from the sim alone.
**Savestate slot 7 = the FOLLOW-ENABLED turnaround-roll clip** (session 23-24, "kill the glitched
Tetra"): a NORMAL following (type-5) Tetra idle in the corner, Link behind her facing away, sword OUT.
The turnaround-clip solver + full live pipeline is `harness/rollstab/turnaround.py` (read its docstring):
`entry` (measure the live roll entry) -> `solve` (fine-scan genuine Tetra placements there) -> `deliver`
/`diff`. **The clip is LIVE + BIT-EXACT as of session 24** (gate `tests/test_turnaround_clip.py`); Link
is moved +110u NE, Tetra placed genuine, `b_step=16`. The remaining pure-sim polish (model the from-rest
slot-7 walk so the roll entry is computed, not measured) is optional -- see the newest handoff + README
## Status.

**When a live delivery disagrees with the sim, do NOT tweak inputs by guesswork.** Run
`python -m harness.rollstab.pushaside diff` (per-frame, BOTH actors) -- the divergence frame names the
bug. Four live runs were burned guessing before this rule was learned.

When you hit a Dolphin / lookup gotcha with no existing doc, document it (whichever
fits: ../tools/DOLPHIN_CONTROL.md, KB, or memory) before moving on.

END OF SESSION:
  1. If seam-clip behavior changed, update the README ## Status section (a pre-commit
     gate enforces this on any commit touching harness/rollstab/*.py).
  2. Write a handoff using harness/rollstab/HANDOFF_TEMPLATE.md.
  3. Commit. Push to GH only if Dereck asks.

---

FUTURE-WORK NOTES (not this session's scope; here so architecture leaves room. Do NOT
build these until asked):
- Mid-walk sword unsheathe/draw as a transient. **DONE (session 34): the foot anim set is switchable
  at the draw-completion frame** (`FootSpeedF.draw_sword`; `LandState(model_draw=True)` auto-triggers
  it `DRAW_DELAY` frames after a B rising edge). Live-gated 0-ULP (`tests/test_draw_switch.py`); the
  swap is instantaneous no-morf per the decomp. What remains is WIRING it into the scanner's ROLL
  dispatch (needs the roll-path solver) -- see the README ## Status "NEXT" list.
- Body-lean physics: daPy_lk_c::jointBeforeCB per-joint leans + jointCB1 foot-plant IK (leg-angle
  Z-bends, CLOTCH translate) + waist ground-tilt. NOTE: these are ALL ZERO on flat ground and the
  MOMI joints (0x10/0x11) are FACE joints, NOT in the foot chain -- so this is NOT the walk-stab
  "foot residual" (a sword/equip anim-set bug, dead-end #28) and it was NOT the late-FRONT_ROLL
  pose drift either, which is now closed (the quaternion sign extension plus a FrameCtrl frame kept
  in double). Body lean has been the prime suspect for two gaps and was neither. The MOMI lean
  (m3516/m3518/m351A, d_a_player_main.cpp:9487) is WIND-driven, not accel. Only matters on sloped
  ground / a non-zero-lean approach; verify live before modelling.
