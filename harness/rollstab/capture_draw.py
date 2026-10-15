"""capture_draw.py - live-capture a mid-walk sword pull-out to pin f_draw + the DASH->DASHS leg swap.

The scanner's ROLL dispatch needs a SHEATHED anchor to draw the sword mid-walk (the roll->cut trigger
requires sword_drawn, land/procs/roll.py:79). The sim freezes the foot anim set (_walk/_dash ->
base WALK/DASH vs sword WALKS/DASHS) once at UnderAnimState construction, so it cannot represent the
draw. Decomp (d_a_player_main.cpp): getAnmData (12951) keys the leg table off mEquipItem, setMoveAnime
(12734) RE-FETCHES it every frame, and procMove's steady setBlendMoveAnime(-1.0f) (6229) passes
i_morf<0 -> NO oldframe-morf. So the leg-set swap is an INSTANTANEOUS, phase-preserved pose jump the
frame after mEquipItem flips to daPyItem_SWORD_e (0x103) at the upper equip-anime completion (3976).

This capture VALIDATES that read live. Straight on-axis UP walk (advancewith is faithful for on-axis;
dead-end #1 is about OFF-axis sticks) to DASH cruise, draw (UP+B) mid-cruise, keep walking. Logs per
frame: mEquipItem, pos, facing, speedF/nspeed/m3598/m359C, the model-local toe stream, and the upper
equip frame ctrl (frame/rate) so f_draw can be read against the decomp's 7.0-frame on-back take.

    python -m harness.rollstab.capture_draw                       # observe (drive + print live log)
    python -m harness.rollstab.capture_draw out=<path>            # also write the fixture
    python -m harness.rollstab.capture_draw anchor=<key> cruise=10 draw=13 tail=14

Live-only (Dolphin). dolphin_mem only.
"""
import json
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

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'walk_draw.json')
LINK_PTR = 0x803AD860
SWORD = 0x103          # daPyItem_SWORD_e

# pointer offsets into P = deref(0x803AD860) (RAM = header class offset - 0xD8; verified via m3598).
OFF = dict(
    pos_x=0x120, pos_y=0x124, pos_z=0x128, shape_y=0x136, angle_y=0x12E,
    speedF=0x17C, nspeed=0x34E4, m3598=0x34C0, m359C=0x34C4, m35B4=0x34DC, msd=0x34D8,
    rtoe=0x3CF8, rheel=0x3CEC, ltoe=0x3E10, lheel=0x3E04, plant=0x33E4, gang=0x3408,
    equip=0x3488,               # mEquipItem (header 0x3560 - 0xD8), u16
    up2_frame=0x2FB4,           # mFrameCtrlUpper[UPPER_MOVE2_e].mFrame (header 0x3054+2*0x14+0x10 - 0xD8)
    up2_rate=0x2FB0,            # mFrameCtrlUpper[UPPER_MOVE2_e].mRate
    curproc=0x3100,
)


def _dm():
    import dolphin_mem as dm
    h, mem1 = dm.attach()
    return dm, h, mem1


def capture(out=None, anchor="land_flatwalk@twwgz", cruise=10, draw=13, tail=14, sy=255,
            decel=0, sy2=180):
    from harness.dtm.run_dtm import resolve_anchor
    dm, h, mem1 = _dm()

    def P():
        return struct.unpack('>I', dm.read_bytes(h, mem1, LINK_PTR, 4))[0]

    sav = resolve_anchor(anchor)
    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    p = P()

    # anchor rest seed (named reads) -> the offline from-rest LandState seed (cf. run_land_tests).
    SEED_KEYS = ["link_state", "potential_speed", "true_speed", "shape_angle_y",
                 "travel_angle", "csangle", "pos_x", "pos_z", "anim_frame"]
    seed = {k: dm.read_named(h, mem1, k) for k in SEED_KEYS}

    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, p + o, 4))[0]
    def ru(o, sz): return struct.unpack('>' + {1: 'B', 2: 'H', 4: 'I'}[sz], dm.read_bytes(h, mem1, p + o, sz))[0]
    def rs(o, sz): return struct.unpack('>' + {1: 'b', 2: 'h', 4: 'i'}[sz], dm.read_bytes(h, mem1, p + o, sz))[0]
    def vec(o): return [rf(o), rf(o + 4), rf(o + 8)]

    def snap(phase):
        return dict(phase=phase, equip=ru(OFF['equip'], 2), curproc=ru(OFF['curproc'], 4),
                    pos=[rf(OFF['pos_x']), rf(OFF['pos_y']), rf(OFF['pos_z'])],
                    shape_y=ru(OFF['shape_y'], 2), angle_y=ru(OFF['angle_y'], 2),
                    speedF=rf(OFF['speedF']), nspeed=rf(OFF['nspeed']), m3598=rf(OFF['m3598']),
                    m359C=rf(OFF['m359C']), m35B4=rf(OFF['m35B4']), msd=rf(OFF['msd']),
                    rtoe=vec(OFF['rtoe']), ltoe=vec(OFF['ltoe']),
                    rheel=vec(OFF['rheel']), lheel=vec(OFF['lheel']),
                    plant=ru(OFF['plant'], 1), gang=rs(OFF['gang'], 2),
                    up2_frame=rf(OFF['up2_frame']), up2_rate=rf(OFF['up2_rate']))

    UP = dict(stickX=128, stickY=int(sy), substickX=128, substickY=128, buttons=0, triggerL=0)
    DRAW = {**UP, 'buttons': 0x200}       # UP + B: unsheathe (first B draws)
    # A `decel` tail at a partial stick (sy2) bleeds speed back through the WALK<->DASH blend (m3598>0)
    # so the sword DASHS legs show on VISIBLE frames (cruise's m3598==0 hides the toe).
    DOWNSHIFT = dict(stickX=128, stickY=int(sy2), substickX=128, substickY=128, buttons=0, triggerL=0)

    rows = [snap("rest")]
    rest_equip = rows[0]['equip']
    print("rest mEquipItem = 0x%X  (SWORD=0x103; sheathed if != 0x103)" % rest_equip)

    seq = ([("walk", UP)] * cruise + [("DRAW", DRAW)] + [("walk", UP)] * tail
           + [("decel", DOWNSHIFT)] * decel)
    inputs = []
    for k, (tag, inp) in enumerate(seq):
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        p = P()
        rows.append(snap(tag))
        inputs.append({kk: inp[kk] for kk in ('stickX', 'stickY', 'substickX', 'substickY',
                                               'buttons', 'triggerL')})

    # locate the flip
    f_flip = next((i for i, r in enumerate(rows) if r['equip'] == SWORD and rows[i - 1]['equip'] != SWORD),
                  None) if rest_equip != SWORD else None
    hdr = " i  phase  equip  proc |  speedF  nspeed  m3598   m359C  | up2(fr/rate) |    pos_x       pos_z    | rtoe_x  rtoe_z"
    print(hdr)
    for i, r in enumerate(rows):
        mark = " <== mEquipItem flip (f_draw)" if i == f_flip else ""
        print("%2d %6s  0x%03X %5d | %7.3f %7.3f %6.4f %7.4f | %5.2f/%4.2f | %11.5f %11.5f | %6.3f %6.3f%s"
              % (i, r['phase'], r['equip'], r['curproc'], r['speedF'], r['nspeed'], r['m3598'], r['m359C'],
                 r['up2_frame'], r['up2_rate'], r['pos'][0], r['pos'][2], r['rtoe'][0], r['rtoe'][2], mark))
    if f_flip is not None:
        b_row = 1 + cruise   # the DRAW frame's snapshot index (rows[0]=rest, so seq[k] -> rows[k+1])
        print("\nf_draw signal: mEquipItem flips at row %d; B (DRAW) delivered at row %d -> %d frames after the B."
              % (f_flip, b_row, f_flip - b_row))
    else:
        print("\nNo mEquipItem flip observed (Link may already hold the sword, or the draw did not complete).")

    result = dict(anchor=anchor, cruise=cruise, draw=draw, tail=tail, sy=int(sy),
                  decel=int(decel), sy2=int(sy2), rest_equip=rest_equip, f_flip=f_flip,
                  b_row=1 + cruise, seed=seed, inputs=inputs, rows=rows)
    if out:
        with open(out, 'w') as f:
            json.dump(result, f, indent=1)
        print("wrote", out)
    return result


if __name__ == '__main__':
    kw = {}
    for a in sys.argv[1:]:
        if '=' in a:
            k, v = a.split('=', 1)
            kw[k] = v
    out = kw.pop('out', None)
    if out == '':
        out = DEFAULT_OUT
    for ik in ('cruise', 'draw', 'tail', 'sy', 'decel', 'sy2'):
        if ik in kw:
            kw[ik] = int(kw[ik])
    capture(out=out, **kw)
