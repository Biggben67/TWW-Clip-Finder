"""Capture a live Link-roll + Tetra Co-push at the corner -> the CC-push stepper gate (ROADMAP Phase C).

Stages the clip's push geometry directly (teleport, per Dereck) instead of timing Tetra into Link's
approach: (1) teleport Tetra FAR so she can't talk/lock during setup; (2) teleport Link to his flat
corner floor spot with room to roll; (3) drive Link into a FRONT_ROLL; (4) at roll entry, teleport
Tetra ONTO Link so their Co cylinders overlap -> the push fires (Link is moving, so his Co cylinder
is registered) and is consumed on the next roll frame. Logs Link + Tetra per frame.

The offline gate seeds `harness.rollstab.cc_stepper.CcCoupledStepper` at the live roll-entry frame
(FRONT_ROLL, speedF pinned -- like spotcheck_rollstab isolates the cut) and replays the roll inputs,
asserting Link's and Tetra's per-frame position bit-exact. Pure-sim: the sim takes no live input;
this is a VALIDATION capture.

    python -m harness.rollstab.capture_cc_push                 # observe (drive + print live log)
    python -m harness.rollstab.capture_cc_push out=<path>      # also write the fixture

Live-only (Dolphin at the Tetra corner: flooded Hyrule, savestate slot 3). dolphin_mem only.
"""
import json
import math
import os
import struct
import sys

# >>> repo bootstrap
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'hyrule_cc_push.json')
SLOT = 3
LINK_BASE = 0x80AC6C6C
TETRA_BASE = 0x80ACD20C
# Link via the player pointer chain P = deref(0x803AD860) (spotcheck_rollstab offsets).
LINK_PTR = 0x803AD860
L = dict(pos_x=0x120, pos_y=0x124, pos_z=0x128, shape_y=0x136, angle_y=0x12E, speedF=0x17C,
         nspeed=0x34E4, curproc=0x3100, csangle=None,
         shape_z=0x138,          # shape_angle.z (class 0x210 - 0xD8): the drawn body lean
         m351C=0x3444)           # MOVE turn-lean state (class 0x351C - 0xD8); shape_z = m351C>>1
# Tetra via actor base (capture_tetra_follow offsets).
T = dict(pos=0x1F8, angle_y=0x206, shape_y=0x20E, speedF=0x254, stt=0x84B, type=0x84F)
# teleport globals (dolphin_mem cmd_teleport).
POS_OFFS = (0x10c, 0x120)
DBG_XYZ = (0x803D78FC, 0x803D7900, 0x803D7904)
FACING_ADDR = 0x803EA3D2
GROUND_Y = 0.1632676
FAR = (-1670.0, -3000.0)         # Tetra parking spot (far in -z; > 230u so no talk, off the corner)


def _dm():
    import dolphin_mem as dm
    h, mem1 = dm.attach()
    return dm, h, mem1


def capture(out=None, link_xz=(-1620.0, -850.0), facing=None, walk=6, roll_frames=20,
            tetra_on=None, tetra_at=None, place_after_roll=1, draw_at=None, thrust_at=None,
            slot=SLOT):
    """``draw_at`` (walk-frame index) ORs a B into that walk frame to UNSHEATHE the sword early -- a
    drawn sword is required for the roll->CUT (roll-stab) dispatch, and drawing early (while speed is
    still low) lets the drawn-sword walk rebuild to the speedF-17 cap for a full-26 roll. ``thrust_at``
    (hold-frame index after the roll) ORs a B into that hold frame to fire the sword thrust OUT of the
    roll -- with a neutral stick this is an in-line CUT_F (aim == facing) that stacks the m34C2 lunge
    onto the CC push + the CrrPos wall pass, THE CLIP FRAME. Time it so the ACTED edge lands at roll
    anim-frame > 17 (INPUT_DELAY=2 -> press ~2 frames early; kroll~15 per spotcheck_rollstab)."""
    dm, h, mem1 = _dm()

    def rf(a): return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]
    def ri(a): return struct.unpack('>i', dm.read_bytes(h, mem1, a, 4))[0]
    def ru16(a): return struct.unpack('>H', dm.read_bytes(h, mem1, a, 2))[0]
    def wf(a, v): dm.write_bytes(h, mem1, a, struct.pack('>f', v))

    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, LINK_PTR, 4))[0]
    base = P - 0xD8
    if struct.unpack('>b', dm.read_bytes(h, mem1, TETRA_BASE + T['type'], 1))[0] != 5:
        raise RuntimeError("not the type-5 Tetra; load slot 3 first")

    def rs16(a): return struct.unpack('>h', dm.read_bytes(h, mem1, a, 2))[0]

    def link():
        return dict(proc=ri(P + L['curproc']), pos=[rf(P + L['pos_x']), rf(P + L['pos_y']),
                    rf(P + L['pos_z'])], shape_y=ru16(P + L['shape_y']),
                    angle_y=ru16(P + L['angle_y']), speedF=rf(P + L['speedF']),
                    nspeed=rf(P + L['nspeed']),
                    shape_z=rs16(P + L['shape_z']), m351C=rs16(P + L['m351C']))

    def tetra():
        return dict(pos=[rf(TETRA_BASE + T['pos']), rf(TETRA_BASE + T['pos'] + 4),
                    rf(TETRA_BASE + T['pos'] + 8)], shape_y=ru16(TETRA_BASE + T['shape_y']),
                    angle_y=ru16(TETRA_BASE + T['angle_y']), speedF=rf(TETRA_BASE + T['speedF']),
                    stt=struct.unpack('>b', dm.read_bytes(h, mem1, TETRA_BASE + T['stt'], 1))[0])

    def tp_tetra(x, z, y=GROUND_Y):
        wf(TETRA_BASE + T['pos'], x); wf(TETRA_BASE + T['pos'] + 4, y)
        wf(TETRA_BASE + T['pos'] + 8, z); wf(TETRA_BASE + T['speedF'], 0.0)

    # 1) park Tetra far so she can't talk/lock during setup.
    tp_tetra(*FAR)
    # 2) clean-place Link on his flat floor spot (both pos triples + globals + optional facing).
    for off in POS_OFFS:
        wf(base + off, link_xz[0]); wf(base + off + 4, GROUND_Y); wf(base + off + 8, link_xz[1])
    for a, v in zip(DBG_XYZ, (link_xz[0], GROUND_Y, link_xz[1])):
        wf(a, v)
    if facing is not None:
        dm.write_bytes(h, mem1, FACING_ADDR, struct.pack('>H', int(facing) & 0xFFFF))
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 128, "frames": 1})

    UP = dict(stickX=128, stickY=255, substickX=128, substickY=128, buttons=0, triggerL=0, frames=1)
    A = {**UP, 'buttons': 0x100}
    HOLD = dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0, triggerL=0, frames=1)
    DRAW = {**UP, 'buttons': 0x200}                 # UP + B: unsheathe (first B draws; spotcheck_rollstab)
    THRUST = {**UP, 'buttons': 0x200}               # UP + B: FORWARD thrust CUT_F (a neutral B is a side
    #                                                 slash CUT_R/L -- dead-end #12; the forward stick aims it)
    FRONT_ROLL_PROC = 30
    # Rollstab (thrust_at) mode holds UP so the pushed stick fires the roll early-turn at anim-frame>17
    # and the B makes a forward CUT_F (roll PATH is stick-independent until then); plain mode: neutral.
    hold_base = UP if thrust_at is not None else HOLD
    walk_seq = [("draw", DRAW) if draw_at is not None and k == draw_at else ("walk", UP)
                for k in range(walk)]
    hold_seq = [("thrust", THRUST) if thrust_at is not None and k == thrust_at else ("hold", hold_base)
                for k in range(roll_frames)]
    seq = walk_seq + [("roll", A)] + hold_seq
    rows = [dict(f=0, tag="seed", link=link(), tetra=tetra())]
    tetra_placed_at = None            # ROW index that first reflects the placement (advanced after it)
    tetra_placed_xz = None
    roll_entry = None
    for i, (tag, inp) in enumerate(seq, 1):
        lk_now = link()                                       # state after frame i-1 (pre-advance)
        if roll_entry is None and lk_now['proc'] == FRONT_ROLL_PROC:
            roll_entry = i - 1
        # write Tetra BEFORE advancing frame i (row i is the first frame reflecting it): `tetra_at` =
        # ABSOLUTE corner spot (wedges -> WallCorrect braces, Link converges); `tetra_on` = feet offset.
        if ((tetra_on is not None or tetra_at is not None) and tetra_placed_at is None
                and roll_entry is not None and (i - 1) - roll_entry >= place_after_roll):
            if tetra_at is not None:
                tx, tz = tetra_at
            else:
                tx = lk_now['pos'][0] + tetra_on[0]; tz = lk_now['pos'][2] + tetra_on[1]
            tp_tetra(tx, tz)
            tetra_placed_at = i
            tetra_placed_xz = (tx, tz)
        dm.control_pipe_quiet("advancewith", inp)
        # store the raw controller input so the offline replay drives the SAME sequence (incl. the
        # B thrust that fires the roll->CUT) -- see cc_stepper._row_step_args.
        rec = {k: inp[k] for k in ('stickX', 'stickY', 'substickX', 'substickY', 'buttons', 'triggerL')}
        rows.append(dict(f=i, tag=tag, link=link(), tetra=tetra(), inp=rec))

    # print the live log
    print("Link seed pos=%.3f,%.3f facing=%d  base=%08X" % (
        rows[0]['link']['pos'][0], rows[0]['link']['pos'][2], rows[0]['link']['shape_y'], base))
    print(" f  tag   proc   Link(x,z)              spF   face   Tetra(x,z)            tY     tSpF  ov")
    for r in rows:
        lk, tt = r['link'], r['tetra']
        ov = math.hypot(lk['pos'][0] - tt['pos'][0], lk['pos'][2] - tt['pos'][2])
        mark = " <-Tetra" if r['f'] == tetra_placed_at else ""
        print("%2d  %-5s %4d  (%9.3f,%9.3f) %6.2f %5d  (%9.3f,%9.3f) %6.3f %5.2f %6.1f%s" % (
            r['f'], r['tag'], lk['proc'], lk['pos'][0], lk['pos'][2], lk['speedF'], lk['shape_y'],
            tt['pos'][0], tt['pos'][2], tt['pos'][1], tt['speedF'], ov, mark))

    if out:
        fix = dict(stage='Hyrule', slot=slot, ground_y=GROUND_Y, link_base='0x%08x' % base,
                   tetra_base='0x%08x' % TETRA_BASE, tetra_placed_at=tetra_placed_at,
                   tetra_placed_xz=tetra_placed_xz, sword_drawn=bool(draw_at is not None),
                   seq=[t for t, _ in [("seed", None)] + seq], frames=rows)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(fix, f, indent=1)
        print("wrote -> %s" % out)
    return dict(rows=rows, tetra_placed_at=tetra_placed_at, tetra_placed_xz=tetra_placed_xz)


def replay_and_compare(rows, tetra_placed_at, tetra_placed_xz, ground_y=GROUND_Y, sword_drawn=False):
    """Replay the capture through the coupled sim OFFLINE and print a per-frame ULP diff table so a
    divergence is localized (pre-push = Phase-W wall-held roll; at/after the push = the CC wiring /
    the roll-frame Co-center morf). Thin wrapper over `cc_stepper.couple_replay` (the shared engine
    the offline gate `tests/test_cc_gate` uses too)."""
    from tww_sim.land.walls import load_ordered_mesh
    from harness.rollstab.cc_stepper import couple_replay

    walls = load_ordered_mesh(os.path.join(_rb, 'fixtures', 'hyrule_tetra_walls_ordered.json'))
    res = couple_replay(rows, tetra_placed_at, tetra_placed_xz, walls, ground_y, sword_drawn=sword_drawn)
    print("\nCOUPLED REPLAY:  dLinkX/dLinkZ/dTetX/dTetZ = sim-live ULP")
    print(" live  proc   dLinkX dLinkZ   dTetX dTetZ  note")
    okall = True
    for r in res:
        bad = any(abs(r[k]) > 0 for k in ('dlx', 'dlz', 'dtx', 'dtz'))
        okall &= not bad
        note = "<-Tetra placed" if r['placed'] else ""
        print("  f%-3d  %4d  %+6d %+6d  %+6d %+6d  %s%s" % (
            r['f'], r['proc'], r['dlx'], r['dlz'], r['dtx'], r['dtz'], note,
            "  <-- DIVERGE" if bad else ""))
    print("RESULT: %s" % ("ALL BIT-EXACT (0 ULP)" if okall else "divergence (see table)"))
    return okall


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    res = capture(out=kw.get('out'),
                  link_xz=(float(kw['lx']), float(kw['lz'])) if 'lx' in kw else (-1620.0, -850.0),
                  facing=int(kw['facing'], 0) if 'facing' in kw else None,
                  walk=int(kw.get('walk', 6)), roll_frames=int(kw.get('roll_frames', 20)),
                  tetra_on=(float(kw['tox']), float(kw['toz'])) if 'tox' in kw else None,
                  tetra_at=(float(kw['tcx']), float(kw['tcz'])) if 'tcx' in kw else None,
                  place_after_roll=int(kw.get('place_after_roll', 1)),
                  draw_at=int(kw['draw_at']) if 'draw_at' in kw else None,
                  thrust_at=int(kw['thrust_at']) if 'thrust_at' in kw else None,
                  slot=int(kw.get('slot', SLOT)))
    if kw.get('gate') == '1':
        replay_and_compare(res['rows'], res['tetra_placed_at'], res['tetra_placed_xz'],
                           sword_drawn=('draw_at' in kw or kw.get('sword_drawn') == '1'))
