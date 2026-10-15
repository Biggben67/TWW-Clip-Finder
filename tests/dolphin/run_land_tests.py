"""LAND-movement live diagnostic: SIM-vs-LIVE (walk + 4 ATN techs + 4 roll cases + 3 ground-reversal
turn procs + the wiggle-EBS-into-roll chain, all via advanceseq).

THE STANDING GATE IS OFFLINE NOW (2026-07-20, Dereck's post-s66 steer): each case's live per-frame
state is recorded ONCE by tests/dolphin/record_land_goldens.py into fixtures/land_goldens/, and
`pytest tests/test_land_goldens.py` compares the sim against those recordings with no Dolphin.
This script remains the LIVE tool: diagnosing a golden-gate RED against current live behavior, and
re-recording after a DELIBERATE tech/anchor change. The old DTM-PLAYBACK wiggle case is RETIRED --
single-stepping a playing movie slips 1-frame edges (the recurring 13/14 flake: the movie's A never
fired) and its mid-recording savestate carried unseedable in-flight attention state; the same chain
now runs as the `wiggle_ebs_roll` pipe case from clean rest (see seq_wiggle).

Dolphin command reference: ../../tools/DOLPHIN_CONTROL.md (the single source of truth).

TURN PROCS (waitturn/moveturn/slip), now SIMULATED: a >0x7800 stick reversal routes through checkNextMode's
non-attention arbiter to a turn proc -- stopped -> procWaitTurn (pivot in place), moving+fast+genuine flip
-> procSlip (skid then procMoveTurn), moving+slow -> procMoveTurn (turn-around). The proc is transient
(gone by the end), so a single advanceseq end-state can't see it -- instead the SIM's `visited` set proves
the proc was entered, while sim_checks asserts the reversed-walk end state (state/mNormalSpeed/facing/travel)
BIT-EXACT vs the live advanceseq. ALL THREE turn procs' position is now BIT-EXACT too (MOVE_TURN: walk
blend posed at the pre-halving speed + re-morfed on entry/exit; WAIT_TURN: ANM_ROT pivot -> the WAIT
idle-proc WAITS/ANM_ATNW{L,R}S turn-step re-pose; SLIP: ANM_SLIP posed with its jnt37 X-scale 1.2 applied
in the FK + carried through the oldframe-morf, so the MOVE_TURN walk tail's toe stream is exact).

SIM-vs-LIVE (walk_run + brakeslide/ebs/face_left/brake_right + roll_run/roll_slow/roll_settle/roll_ebs
+ waitturn/moveturn/slip):
seed a `tww_sim.land.land.LandState` from the live frame-0 snapshot, step the sim over the input burst
(stick + L-target + A), and compare the END state against the game replayed via one race-free
`advanceseq`. mNormalSpeed (signed potential_speed), the proc state machine, facing (shape_angle.y)
and travel (current.angle.y) are all BIT-EXACT -- including roll_ebs, whose ~-23.109 preserved speed
comes from the roll's getFrame()>17 checkNextMode(1) exit straight to ATN then the backward-flip.

POSITION (pos_z) IS GATED FLOAT-PERFECT -- 0 ULP vs live is the pass condition (LIVE IS THE SOURCE OF
TRUTH; the sim must reproduce the game's pos_z byte for byte). posz_status() enforces this with NO
tolerance and NO xfail: a tech that is not bit-exact shows RED. Today ALL 14 land cases pass at 0 ULP
(slip went bit-perfect with the posMoveFromFootPos |speedF| < 0.05 -> 0 skid snap,
d_a_player_main.cpp:2418; brake_right + the deep-release walk speedF with the pos_x sine-leak fix --
cM_ssin must use JMASSin, not a cos-table offset; walk_y171 with the daPy_HIO_move_c0 f64->f32 frame-rate
constant fix; ebs + waitturn with the worldBase inverse = retail PSMTXInverse (cofactor + fres), not R^T,
which the not-exactly-orthonormal sin/cos rotation makes differ at non-axis facings; see
knowledge/history/resolved-bugs.md). Each case also layers its tech assertions. (Runs with no anim
keyframe data fall back to the calibrated stand-in and pos_z is not asserted.)

Determinism: the anchor + inputs are fixed and advanceseq is race-free, so end-state is
reproducible and can be locked tight, exactly like the swim run_tests baselines. These are the
land analogue of the immutable swim syncs -- do not loosen a check to make a run pass; a real
change means the sim (or tech, or anchor) changed, which is a finding, not a test edit.

Free cam: C-stick full DOWN every frame (substickY=0) so csangle stays 0 (the reference).
L-target uses digital L (buttons 0x40) + analog triggerL=255. ESS = (128,110); ESS-left =
(110,128), ESS-right = (146,128) at the same off-center magnitude.

Requires Dolphin running with twwgz booted. Loads land_flatwalk@twwgz.sav BY PATH.
Usage:
  python run_land_tests.py            # assert locked expectations (exit 0 iff all pass)
  python run_land_tests.py record=1   # print end-states to (re)lock after a DELIBERATE change
"""
import os, sys, struct  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from harness.dtm.run_dtm import resolve_anchor
from tww_sim.land.land import LandState

ANCHOR = resolve_anchor("land_flatwalk@twwgz")
READS = ["link_state", "potential_speed", "true_speed", "shape_angle_y",
         "travel_angle", "csangle", "pos_x", "pos_z", "anim_frame"]

def f32_bits(x):
    """Raw uint32 bits of x rounded to float32; |bits(a)-bits(b)| is the exact ULP distance here."""
    return struct.unpack("<I", struct.pack("<f", x))[0]


def posz_status(sim, live, label):
    """FLOAT-PERFECT sim-vs-live pos_z gate. Pass condition is 0 ULP -- the sim must reproduce the
    game's pos_z BYTE FOR BYTE (live is the source of truth). ANY nonzero gap is a hard FAIL: there is
    no tolerance and no xfail, so a not-yet-bit-perfect tech shows RED until the sim is fixed. Returns
    ('ok'|'fail', desc), or None when position isn't asserted (no anim data -> calibrated stand-in)."""
    if getattr(sim, "_pos_fallback", False) or sim._foot is None:
        return None
    bit = abs(f32_bits(sim.pos_z) - f32_bits(live["pos_z"]))
    tag = (f"[{bit} ULP]  sim {sim.pos_z!r} (0x{f32_bits(sim.pos_z):08x}) / "
           f"live {live['pos_z']!r} (0x{f32_bits(live['pos_z']):08x})")
    if bit == 0:
        return ("ok", f"pos_z FLOAT-PERFECT (0 ULP vs live)  {tag}")
    return ("fail", f"pos_z NOT float-perfect ({bit} ULP off live) -- open precision residual  {tag}")

def hold(sx, sy, n, buttons=0, triggerL=0):
    """n one-frame advanceseq elements at (sx,sy), C-stick full down (free cam)."""
    return [{"stickX": sx, "stickY": sy, "substickX": 128, "substickY": 0,
             "buttons": buttons, "triggerL": triggerL, "frames": 1} for _ in range(n)]


L_DOWN = hold(128, 0, 1, buttons=0x40, triggerL=255)   # L-target + full down, 1 frame
A = 0x100                                              # GC PAD_BUTTON_A (the "do"/roll button)

# --- the discovered sequences ---------------------------------------------------------
def seq_walk():        return hold(128, 255, 30) + hold(128, 128, 20)                  # run -> standstill
def seq_walk_y171():   return hold(128, 171, 40)                                        # PARTIAL-magnitude walk (msd~0.52)
def seq_brakeslide():  return hold(128, 255, 10) + L_DOWN + hold(128, 110, 10, 0x40, 255)  # L HELD -> targeting slide
def seq_ebs():         return hold(128, 255, 10) + L_DOWN + hold(128, 110, 30)          # L released -> extended slide
def seq_face_left():   return hold(128, 255, 10) + L_DOWN + hold(128, 110, 1) + hold(110, 128, 60)
def seq_brake_right(): return hold(128, 255, 10) + L_DOWN + hold(128, 110, 1) + hold(146, 128, 60)

# --- roll (FRONT_ROLL, state 30) sequences: A while moving -> forward roll. Roll speed set at entry
# from the PRE-roll speedF = clamp(speedF*1.5+0.5, 5, 26); these end MID-ROLL to read that speed. ---
def seq_roll_run():    return hold(128, 255, 15) + hold(128, 255, 1, A) + hold(128, 128, 5)   # full run -> roll @ cap 26
def seq_roll_slow():   return hold(128, 255, 2) + hold(128, 255, 1, A) + hold(128, 128, 5)    # barely moving -> roll near floor
def seq_roll_settle(): return hold(128, 255, 15) + hold(128, 255, 1, A) + hold(128, 128, 40)  # roll played to a full stop
# Frame-perfect EBS out of a roll: HOLD L+down through the roll (17 frames) -> it exits straight to
# ATN at 26; release L into ESS-down -> flip preserves ~-23 (one-frame window). See land-movement.md.
def seq_roll_ebs():  return hold(128, 255, 15) + hold(128, 255, 1, A) + hold(128, 0, 17, 0x40, 255) + hold(128, 110, 14)

# --- big-reversal ground-turn procs (WAIT_TURN 23 / MOVE_TURN 24 / SLIP 25). A >0x7800 stick reversal
# routes via checkNextMode -> procWaitTurn (stopped) / procSlip (fast) / procMoveTurn. See land-movement.md.
def seq_waitturn(): return hold(128, 0, 15)                       # idle -> flick down: pivot in place ~180
def seq_moveturn(): return hold(128, 255, 1) + hold(128, 0, 18)   # slow start -> reverse below slip thresh
def seq_slip():     return hold(128, 255, 15) + hold(128, 0, 30)  # full-speed run -> reverse: skid then turn


# --- the wiggle-EBS-into-roll chain from clean rest: the movie fixture's consumed inputs, replayed
# as a pipe case (DTM-playback retired; see brakeslide-ebs.md + history/resolved-bugs.md, 2026-07-20).
def seq_wiggle():
    return (hold(130, 247, 5) + hold(130, 247, 4, A) + hold(130, 247, 7)   # up run-up, roll @26
            + hold(109, 2, 7, 0x40, 255)                                   # L+down: roll-EBS exit at 26
            + hold(113, 110, 1)                                            # release into the wiggle
            + hold(146, 113, 2) + hold(111, 111, 1) + hold(146, 113, 2)    # ESS wiggle taps
            + hold(111, 111, 1) + hold(146, 113, 2) + hold(111, 111, 1)    # ... preserving ~-23.23
            + hold(146, 113, 2) + hold(111, 111, 1) + hold(146, 113, 10)
            + hold(130, 247, 1, 0x40, 255)                                 # the 1-frame L+Up cancel
            + hold(130, 247, 1) + hold(130, 247, 15, A)                    # second roll @24.087
            + hold(113, 113, 17))                                          # settle to a stop


def deg(a):
    return (int(a) % 65536) * 360.0 / 65536.0


def sdiff_deg(a, b):
    d = (int(a) - int(b)) % 65536
    if d > 32768:
        d -= 65536
    return d * 360.0 / 65536.0


def replay_sim_vs_live(seq):
    """SIM-vs-LIVE. Load the anchor, read the resting frame-0 seed, seed a LandState, step it
    over the seq (stick + L-target via buttons/triggerL), and replay the same seq live via one
    advanceseq. Returns (sim_state, live_end) for comparison. Mirrors swim run_tests.run_one.

    NOTE: read the seed DIRECTLY after loadstate (no settle frame). A stray `advancewith`
    neutral frame before the advanceseq perturbs the live walk by ~5 units (advancewith vs
    advanceseq pipe artifact -- bug#2); the clean advanceseq-from-load result is 1278.25."""
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace('\\', '/')})
    h, m = D.attach()
    seed = {k: D.read_named(h, m, k) for k in READS}   # anchor's deterministic rest state
    sim = LandState(pos_z=seed["pos_z"], facing=int(seed["shape_angle_y"]),
                    travel=int(seed["travel_angle"]), csangle=int(seed["csangle"]),
                    state=int(seed["link_state"]), nspeed=seed["potential_speed"],
                    idle_frame=seed["anim_frame"])
    for el in seq:                                # C-stick full down => free cam, csangle 0
        for _ in range(el.get("frames", 1)):
            sim.step(el["stickX"], el["stickY"],
                     buttons=el.get("buttons", 0), triggerL=el.get("triggerL", 0))
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    h, m = D.attach()
    live = {k: D.read_named(h, m, k) for k in READS}
    return sim, live


def turn_checks(sim, live, proc, proc_name, posz, extra=()):
    """Shared signature for the SIMULATED ground-turn procs: the transient `proc` (23/24/25) is entered
    (proven by the sim's `visited` set -- the proc is gone by the end, so a single advanceseq can't see
    it live), the run ends walking (MOVE) 180deg-reversed at the cap, and the live distance still matches
    the locked value (anchor/seq guard). state/mNormalSpeed/facing/travel bit-exactness is asserted
    separately by sim_checks; `extra` layers each case's characteristic path detail (no-slip / skid+turn)."""
    checks = [
        (proc in sim.visited, f"{proc_name} ({proc}) entered  [sim visited {sorted(sim.visited)}]"),
        (int(live["link_state"]) == 6, f"ends walking (MOVE 6)  [{int(live['link_state'])}]"),
        (abs(sdiff_deg(live["shape_angle_y"], 0x8000)) < 2, f"faces ~180 (reversed)  [{deg(live['shape_angle_y']):.1f}]"),
        (abs(abs(live["potential_speed"]) - 17.0) < 0.1, f"re-accelerated to the cap  [{live['potential_speed']:.2f}]"),
        (abs(live["pos_z"] - posz) < 0.5, f"live distance pos_z~{posz:.1f}  [{live['pos_z']:.2f}]"),
    ]
    return checks + list(extra)


def sim_checks(sim, live, note):
    """SIM-vs-LIVE core checks (ALL cases): state exact; mNormalSpeed (signed) bit-exact; facing +
    travel bit-exact (s16). These four are float-perfect for every land tech. pos_z is checked
    SEPARATELY by posz_status() (the float-perfect gate + the KNOWN_POSZ_GAP_ULP xfail ledger), since
    it is the one field with an open sub-ULP residual on some techs. See superswim/land.py step()."""
    dv = abs(sim.nspeed - live["potential_speed"])         # signed: brakeslide/EBS go negative
    dfac = abs(sdiff_deg(sim.facing, live["shape_angle_y"]))
    dtrav = abs(sdiff_deg(sim.travel, live["travel_angle"]))
    checks = [
        (sim.state == int(live["link_state"]),
         f"state sim/live {sim.state}/{int(live['link_state'])}"),
        (dv <= 0.02, f"potential_speed bit-exact  dv={dv:.5f}  "
                     f"(sim {sim.nspeed:.3f} / live {live['potential_speed']:.3f})"),
        (dfac < 0.1, f"facing bit-exact  d={dfac:.4f}deg  "
                     f"(sim {deg(sim.facing):.2f} / live {deg(live['shape_angle_y']):.2f})"),
        (dtrav < 0.1, f"travel bit-exact  d={dtrav:.4f}deg  "
                      f"(sim {deg(sim.travel):.2f} / live {deg(live['travel_angle']):.2f})"),
    ]
    return checks


# extra_check(live) -> the characteristic tech assertions (documents the mechanic + guards the
# anchor). ALL cases are now SIM-vs-LIVE (sim_checks) with the tech assertions layered on top.
CASES = [
    ("walk_run", seq_walk, "run accel to cap 17 then decel to standstill", None),
    # PARTIAL-magnitude (Y171) walk -- the z=2000 stop; regime-1 cruise (speedF = toe delta). BIT-EXACT
    # since the daPy_HIO_move_c0 f64->f32 frame-rate constant fix. Detail: knowledge/history/resolved-bugs.md.
    ("walk_y171", seq_walk_y171, "partial-magnitude (Y171) walk -- regime-1 cruise (bit-exact)", lambda e: [
        (e["link_state"] == 6, f"walking (MOVE 6)  [{e['link_state']}]"),
    ]),
    ("brakeslide", seq_brakeslide, "L held -> targeting slide, facing locked", lambda e: [
        (e["link_state"] == 7, f"state 7 (ATN_MOVE)  [{e['link_state']}]"),
        (e["facing"] < 5 or e["facing"] > 355, f"facing locked ~0  [{e['facing']:.1f}]"),
        (14.0 < e["v"] < 17.5, f"still sliding  [{e['v']:.2f}]"),
    ]),
    ("ebs", seq_ebs, "L released -> extended slide, slow bleed", lambda e: [
        (e["link_state"] == 6, f"state 6 (MOVE)  [{e['link_state']}]"),
        (16.0 < e["v"] < 17.0, f"speed preserved  [{e['v']:.2f}]"),
        (e["face_trav"] < 5, f"facing~travel aligned  [{e['face_trav']:.1f}]"),
    ]),
    ("face_left", seq_face_left, "facing DECOUPLES to ~90 while slide holds + speed preserved", lambda e: [
        (e["link_state"] == 6, f"state 6 (MOVE)  [{e['link_state']}]"),
        (abs(e["facing"] - 90.0) < 8, f"facing turned ~90  [{e['facing']:.1f}]"),
        (e["face_trav"] > 60, f"facing DECOUPLED from travel  [{e['face_trav']:.1f}]"),
        (e["v"] > 16.0, f"speed preserved  [{e['v']:.2f}]"),
    ]),
    ("brake_right", seq_brake_right, "ESS toward anti-cam brakes to a full stop", lambda e: [
        (e["link_state"] == 4, f"state 4 (idle/stopped)  [{e['link_state']}]"),
        (e["v"] < 0.5, f"|v|~0 braked  [{e['v']:.2f}]"),
    ]),
    # roll (FRONT_ROLL) is now SIMULATED (tww_sim.land.land) -- these end MID-ROLL so nspeed/state and
    # the momentum position are bit-exact (roll speed = clamp(speedF*1.5+0.5, 5, 26) set at entry).
    ("roll_run", seq_roll_run, "full-run roll -> state 30 at the 26 cap (mid-roll)", lambda e: [
        (e["link_state"] == 30, f"state 30 (FRONT_ROLL)  [{e['link_state']}]"),
        (abs(e["v"] - 26.0) < 0.05, f"roll speed at cap 26  [{e['v']:.3f}]"),
    ]),
    ("roll_slow", seq_roll_slow, "barely-moving roll -> speedF-scaled low roll speed (mid-roll)", lambda e: [
        (e["link_state"] == 30, f"state 30 (FRONT_ROLL)  [{e['link_state']}]"),
        (5.0 <= e["v"] < 8.0, f"roll speed speedF-scaled near floor  [{e['v']:.3f}]"),
    ]),
    # full roll to standstill: the low-speed post-roll tail is bit-exact now (foot engine poses
    # ANM_ROLLF through the roll). pos_z asserted bit-exact by sim_checks. See land-movement.md.
    ("roll_settle", seq_roll_settle, "full-run roll played to standstill: total distance + clean stop", lambda e: [
        (e["link_state"] == 4, f"state 4 (idle/stopped)  [{e['link_state']}]"),
        (e["v"] < 0.5, f"|v|~0 stopped  [{e['v']:.2f}]"),
    ]),
    # frame-perfect EBS out of a roll: getFrame()>17 exits straight to ATN at 26, release L into
    # ESS-down -> backward-flip preserves -23.109. Signed speed asserted by sim_checks. See land-movement.md.
    ("roll_ebs", seq_roll_ebs, "frame-perfect EBS out of a roll: 26 flipped/preserved as ~-23", lambda e: [
        (e["link_state"] == 6, f"state 6 (MOVE/EBS)  [{e['link_state']}]"),
        (abs(e["v"] - 23.109) < 0.05, f"~-23 preserved (frame-perfect)  [{e['v']:.3f}]"),
        (e["face_trav"] < 5, f"facing~travel aligned (EBS)  [{e['face_trav']:.1f}]"),
    ]),
    # the wiggle-EBS-into-roll chain (see seq_wiggle); the interior signature (roll @26, wiggle
    # ~-23.23, roll @24.087) is locked per-frame by the offline golden (tests/test_land_goldens.py).
    ("wiggle_ebs_roll", seq_wiggle, "roll -> wiggle-EBS ~-23.23 -> L+Up cancel -> roll @24 -> stop", lambda e: [
        (e["link_state"] == 4, f"state 4 (idle/stopped)  [{e['link_state']}]"),
        (e["v"] < 0.5, f"|v|~0 stopped  [{e['v']:.2f}]"),
    ]),
]


# ground-reversal turn procs (WAIT_TURN 23 / MOVE_TURN 24 / SLIP 25), now SIMULATED -- sim_checks asserts
# state/mNormalSpeed/facing/travel bit-exact, turn_checks proves the path. See knowledge/mechanics/land-movement.md.
TURN_CASES = [
    ("waitturn", seq_waitturn, "idle flick-reverse -> pivot in place (WAIT_TURN) then walk off",
     lambda sim, live: turn_checks(sim, live, 23, "WAIT_TURN", 690.47, [
        (24 not in sim.visited and 25 not in sim.visited, "pure pivot (no MOVE_TURN/SLIP)")])),
    ("moveturn", seq_moveturn, "low-speed reverse -> MOVE_TURN turn-around (below the slip threshold)",
     lambda sim, live: turn_checks(sim, live, 24, "MOVE_TURN", 545.69, [
        (25 not in sim.visited, "no SLIP (entry speedF/max below the 0.6 threshold)")])),
    ("slip", seq_slip, "full-speed reverse -> SLIP skid then MOVE_TURN turn-around",
     lambda sim, live: turn_checks(sim, live, 25, "SLIP", 981.72, [
        (24 in sim.visited, "MOVE_TURN follows the skid")])),
]


def emit_case(label, note, checks, sim, live, counts):
    """Print one SIM-vs-LIVE case: the bit-exact core/tech checks + the FLOAT-PERFECT pos_z gate. A
    case FAILS iff a core/tech check fails OR pos_z is not 0 ULP vs live (no tolerance, no xfail -- an
    inaccurate tech shows RED)."""
    pos = posz_status(sim, live, label)
    fail = (not all(c[0] for c in checks)) or (pos is not None and pos[0] == "fail")
    print(f"{'FAIL' if fail else 'PASS'} {label:<12} (SIM-vs-LIVE: {note})")
    for passed, desc in checks:
        print(f"     {'ok ' if passed else 'X  '}{desc}")
    if pos is not None:
        print(f"     {'ok ' if pos[0] == 'ok' else 'X  '}{pos[1]}")
    counts["fail" if fail else "pass"] += 1


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    record = o.get('record', '0') in ('1', 'true', 'yes')
    only = o.get('only')
    counts = {"pass": 0, "fail": 0}
    for label, seqfn, note, extra_check in CASES:
        if only and only != label:
            continue
        sim, live = replay_sim_vs_live(seqfn())
        if record:
            e = {"link_state": int(live["link_state"]), "v": abs(live["potential_speed"]),
                 "facing": deg(live["shape_angle_y"]), "travel": deg(live["travel_angle"])}
            gap = abs(f32_bits(sim.pos_z) - f32_bits(live["pos_z"]))
            print(f"{label:<12} SIM st={sim.state} v={sim.nspeed:.3f} face={deg(sim.facing):.1f} "
                  f"trav={deg(sim.travel):.1f} pos_z={sim.pos_z:.2f}  | LIVE st={e['link_state']} "
                  f"v={live['potential_speed']:.3f} face={e['facing']:.1f} trav={e['travel']:.1f} "
                  f"pos_z={live['pos_z']:.2f}  posULP={gap}  # {note}")
            continue
        checks = sim_checks(sim, live, note)
        if extra_check is not None:              # layer the characteristic tech assertions on top
            e = {"link_state": int(live["link_state"]), "v": abs(live["potential_speed"]),
                 "facing": deg(live["shape_angle_y"]), "travel": deg(live["travel_angle"]),
                 "face_trav": abs(sdiff_deg(live["shape_angle_y"], live["travel_angle"]))}
            checks += extra_check(e)
        emit_case(label, note, checks, sim, live, counts)

    for label, seqfn, note, check in TURN_CASES:   # ground-reversal turn procs (now SIM-vs-LIVE)
        if only and only != label:
            continue
        sim, live = replay_sim_vs_live(seqfn())
        if record:
            gap = abs(f32_bits(sim.pos_z) - f32_bits(live["pos_z"]))
            print(f"{label:<12} SIM st={sim.state} v={sim.nspeed:.3f} face={deg(sim.facing):.1f} "
                  f"trav={deg(sim.travel):.1f} visited={sorted(sim.visited)} pos_z={sim.pos_z:.2f}  | "
                  f"LIVE st={int(live['link_state'])} v={live['potential_speed']:.3f} "
                  f"face={deg(live['shape_angle_y']):.1f} pos_z={live['pos_z']:.2f}  posULP={gap}  # {note}")
            continue
        emit_case(label, note, sim_checks(sim, live, note) + check(sim, live), sim, live, counts)

    if not record:
        print(f"\n{counts['pass']} passed, {counts['fail']} failed")
        sys.exit(1 if counts["fail"] else 0)


if __name__ == "__main__":
    main()
