"""Capture a live FRONT_ROLL on slot 3 and log the body-lean terms + mCyl centre per frame.

Debug aid for the body Co-cylinder centre (`tww_sim.core.anim.body_cyl.roll_co_center`). The clean
single-`rollf` pose is bit-exact only after roll frame ~11; the early-frame residual was pinned (this
session) NOT to the oldframe-morf (that is `mRoll.field_0x14 = 2.0`, so it touches frame 0 only) but to
`daPy_lk_c::jointBeforeCB` (d_a_player_main.cpp:296): the callback rotates the root joint by
`(m34F2,0,m34F4)` and the `body_chn` joint by `(-mBodyAngle.z, mBodyAngle.y, mBodyAngle.x)`, and both
sit on the neck FK chain (root->center->body_chn->stomach->chest->neck) the centre reads. This capture
logs those terms live so the model can be validated OFFLINE against the game.

Per frame it records: proc, pos.xz, shape_angle.y, speedF, the roll anim frame, mCyl.center.xz (+R/H,
auto-located by the R=30/H=81.25 FRONT_ROLL pattern), mBodyAngle.x/y/z, m34F2/m34F4, shape_angle.z.

    python -m harness.rollstab.capture_roll_lean                # observe (drive + print)
    python -m harness.rollstab.capture_roll_lean out=<path>     # also write the json

Live-only (Dolphin at the Tetra corner: flooded Hyrule, savestate slot 3). dolphin_mem only. Pure-sim
is unaffected: the sim takes no live input; this is a validation capture (SESSION_PROMPT protocol).
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

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'hyrule_roll_lean.json')
SLOT = 3
LINK_PTR = 0x803AD860
GROUND_Y = 0.1632676

# TWO offset conventions (see spotcheck_rollstab.py:33): pointer-chain fields are P-relative (= class
# offset - 0xD8), read at P+off; header members are TRUE class offsets, read at base+C (base = P-0xD8).
POFF = dict(pos_x=0x120, pos_y=0x124, pos_z=0x128, shape_y=0x136, angle_y=0x12E,
            speedF=0x17C, curproc=0x3100, anim_frame=0x2F64, anim_rate=0x2F60)  # P-relative
COFF = dict(shape_z=0x210,                                   # shape_angle.z (csXyz @ 0x20C)
            body_x=0x2B4, body_y=0x2B6, body_z=0x2B8,        # csXyz mBodyAngle @ 0x2B4
            m34F2=0x34F2, m34F4=0x34F4)                      # TRUE class offsets
MCYL_CLASS = 0x4024        # dCcD_Cyl @0x4024; cM3dGCyl geom auto-located by the R/H pattern

FRONT_ROLL_PROC = 30


def _dm():
    import dolphin_mem as dm
    h, mem1 = dm.attach()
    return dm, h, mem1


def capture(out=None, link_xz=(-1500.0, -700.0), facing=None, walk=7, roll_frames=22):
    dm, h, mem1 = _dm()

    def rf(a): return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]
    def ri(a): return struct.unpack('>i', dm.read_bytes(h, mem1, a, 4))[0]
    def ru16(a): return struct.unpack('>H', dm.read_bytes(h, mem1, a, 2))[0]
    def rs16(a): return struct.unpack('>h', dm.read_bytes(h, mem1, a, 2))[0]
    def wf(a, v): dm.write_bytes(h, mem1, a, struct.pack('>f', v))

    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": SLOT})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, LINK_PTR, 4))[0]
    base = P - 0xD8

    # locate the FRONT_ROLL Co cyl: scan a window at +0x4024 for R=30, H=81.25 (center just before).
    def find_cyl():
        blob = dm.read_bytes(h, mem1, base + MCYL_CLASS, 0x160)
        for o in range(0, len(blob) - 0x14, 4):
            r = struct.unpack('>f', blob[o + 0xC:o + 0x10])[0]
            hh = struct.unpack('>f', blob[o + 0x10:o + 0x14])[0]
            if abs(r - 30.0) < 1e-3 and abs(hh - 81.25) < 1e-2:
                return base + MCYL_CLASS + o
        return None

    def rd():
        d = dict(proc=ri(P + POFF['curproc']),
                 pos=[rf(P + POFF['pos_x']), rf(P + POFF['pos_y']), rf(P + POFF['pos_z'])],
                 shape_y=ru16(P + POFF['shape_y']),
                 speedF=rf(P + POFF['speedF']),
                 anim_frame=rf(P + POFF['anim_frame']),
                 body=[rs16(base + COFF['body_x']), rs16(base + COFF['body_y']), rs16(base + COFF['body_z'])],
                 shape_z=rs16(base + COFF['shape_z']),
                 m34F2=rs16(base + COFF['m34F2']), m34F4=rs16(base + COFF['m34F4']))
        cyl = find_cyl()
        if cyl is not None:
            d['cyl'] = [rf(cyl), rf(cyl + 4), rf(cyl + 8), rf(cyl + 0xC), rf(cyl + 0x10)]
            d['cyl_off'] = '0x%x' % (cyl - base)
        else:
            d['cyl'] = None
        return d

    # place Link (both pos triples + debug globals) and optional facing, like capture_cc_push.
    for off in (0x10c, 0x120):
        wf(base + off, link_xz[0]); wf(base + off + 4, GROUND_Y); wf(base + off + 8, link_xz[1])
    for a, v in zip((0x803D78FC, 0x803D7900, 0x803D7904), (link_xz[0], GROUND_Y, link_xz[1])):
        wf(a, v)
    if facing is not None:
        dm.write_bytes(h, mem1, 0x803EA3D2, struct.pack('>H', int(facing) & 0xFFFF))
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 128, "frames": 1})

    UP = dict(stickX=128, stickY=255, substickX=128, substickY=128, buttons=0, triggerL=0, frames=1)
    A = {**UP, 'buttons': 0x100}
    HOLD = dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0, triggerL=0, frames=1)
    seq = [UP] * walk + [A] + [HOLD] * roll_frames

    rows = [dict(f=0, **rd())]
    for i, inp in enumerate(seq, 1):
        dm.control_pipe_quiet("advancewith", inp)
        rows.append(dict(f=i, **rd()))

    print("Link base=%08X  seed pos=(%.3f,%.3f) facing=%d  cyl_off=%s" % (
        base, rows[0]['pos'][0], rows[0]['pos'][2], rows[0]['shape_y'],
        next((r['cyl_off'] for r in rows if r.get('cyl')), '?')))
    print(" f  proc  animF   pos(x,z)               spF    cyl(x,z)              R     H     "
          "body(x,y,z)          shz   m34F2 m34F4")
    for r in rows:
        c = r['cyl']
        cs = ("(%9.3f,%9.3f) %5.1f %5.2f" % (c[0], c[2], c[3], c[4])) if c else "  (no cyl)          "
        print("%2d  %4d %6.2f (%9.3f,%9.3f) %6.2f %s (%6d,%6d,%6d) %5d %5d %5d" % (
            r['f'], r['proc'], r['anim_frame'], r['pos'][0], r['pos'][2], r['speedF'], cs,
            r['body'][0], r['body'][1], r['body'][2], r['shape_z'], r['m34F2'], r['m34F4']))

    if out:
        fix = dict(stage='Hyrule', slot=SLOT, ground_y=GROUND_Y, link_base='0x%08x' % base, frames=rows)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(fix, f, indent=1)
        print("wrote -> %s" % out)
    return rows


if __name__ == '__main__':
    kw = {}
    for a in sys.argv[1:]:
        if '=' in a:
            k, v = a.split('=', 1)
            if k in ('walk', 'roll_frames'):
                kw[k] = int(v)
            elif k == 'facing':
                kw[k] = int(v)
            elif k == 'out':
                kw[k] = v if v not in ('1', 'true') else DEFAULT_OUT
            elif k in ('lx', 'lz'):
                kw.setdefault('_xz', {})[k] = float(v)
    if '_xz' in kw:
        xz = kw.pop('_xz')
        kw['link_xz'] = (xz.get('lx', -1500.0), xz.get('lz', -700.0))
    capture(**kw)
