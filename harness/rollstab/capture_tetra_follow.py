"""Capture Tetra's FOLLOW trajectory live -> a sim gate fixture (ROADMAP Phase C).

Drives a clean, controllable follow: hold Link on the safe corner spot, teleport Tetra far
enough that the follow engages (3D dist > 230), then log her per-frame chase back toward Link
(turn -> accelerate -> distance-capped cruise -> decelerate -> stop at ~130). This exercises
every branch of the ``optn_1``/``optn_2`` follow state machine against a STATIONARY target (the
cleanest bit-exact check), and Y stays on the flat water/ground plane so the follow XZ dynamics
are isolated.

    python -m harness.rollstab.capture_tetra_follow                 # defaults -> default fixture
    python -m harness.rollstab.capture_tetra_follow tx=-1450 tz=-700 frames=120 out=<path>

The offline gate (:mod:`tests.test_tetra_follow`) seeds :class:`tww_sim.core.npc_zl1.Zl1FollowState`
from the post-teleport frame and steps it with each frame's LOGGED Link position, asserting Tetra's
pos/angle/speedF/state match per frame.

Live-only (needs Dolphin at the Tetra corner: flooded Hyrule, savestate slot 3; see
../tools/DOLPHIN_CONTROL.md). Reads/writes RAM via `dolphin_mem` (../tools/) ONLY -- self-contained
(mirrors capture_walls.py / capture_ground.py). This is a VALIDATION capture; the sim itself takes
no live input (pure-sim objective intact).
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

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'hyrule_tetra_follow.json')

# Live actor bases on slot 3 (flooded Hyrule; stable across loadstate 3, verified 2026-07-10).
LINK_BASE = 0x80AC6C6C
TETRA_BASE = 0x80ACD20C
# fopAc_ac_c field offsets (f_op_actor.h): current.pos +0x1F8, current.angle.y +0x206,
# shape_angle.y +0x20E, speedF +0x254; daNpc_Zl1_c field_0x84B (stt) / field_0x84F (type).
OFF_POS = 0x1F8
OFF_ANGY = 0x206
OFF_SHAPEY = 0x20E
OFF_SPEEDF = 0x254
OFF_STT = 0x84B
OFF_TYPE = 0x84F
GROUND_Y = 0.1632676        # flat water/ground plane at the corner (Phase G)


def _dist3d(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _dm():
    import dolphin_mem as dm
    h, mem1 = dm.attach()
    return dm, h, mem1


def _reader(dm, h, mem1):
    class R:
        def f32(self, a):
            return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]

        def s16(self, a):
            return struct.unpack('>h', dm.read_bytes(h, mem1, a, 2))[0]

        def s8(self, a):
            return struct.unpack('>b', dm.read_bytes(h, mem1, a, 1))[0]

        def wf32(self, a, v):
            dm.write_bytes(h, mem1, a, struct.pack('>f', v))
    return R()


def _actor(r, base):
    return {
        'pos': [r.f32(base + OFF_POS), r.f32(base + OFF_POS + 4), r.f32(base + OFF_POS + 8)],
        'angle_y': r.s16(base + OFF_ANGY),
        'shape_y': r.s16(base + OFF_SHAPEY),
        'speedF': r.f32(base + OFF_SPEEDF),
    }


def capture(out=DEFAULT_OUT, tx=-1450.0, tz=-700.0, frames=120, link_base=LINK_BASE,
            tetra_base=TETRA_BASE):
    dm, h, mem1 = _dm()
    r = _reader(dm, h, mem1)

    ttype = r.s8(tetra_base + OFF_TYPE)
    if ttype != 5:
        raise RuntimeError("Tetra at 0x%08x is type %d, not the type-5 following variant; "
                           "load slot 3 (flooded-Hyrule Tetra corner) first" % (tetra_base, ttype))

    pre = {'link': _actor(r, link_base), 'tetra': _actor(r, tetra_base),
           'tetra_stt': r.s8(tetra_base + OFF_STT)}

    # Teleport Tetra to the far spot on the flat plane and zero her speed (idle re-entry).
    r.wf32(tetra_base + OFF_POS, tx)
    r.wf32(tetra_base + OFF_POS + 8, tz)
    r.wf32(tetra_base + OFF_POS + 4, GROUND_Y)
    r.wf32(tetra_base + OFF_SPEEDF, 0.0)

    rows = []

    def log(fidx):
        rows.append({'f': fidx,
                     'link': _actor(r, link_base),
                     'tetra': _actor(r, tetra_base),
                     'tetra_stt': r.s8(tetra_base + OFF_STT)})

    log(0)  # the seed: post-teleport, pre-advance
    for i in range(1, frames + 1):
        dm.control_pipe_quiet("advancewith",
                              {"stickX": 128, "stickY": 128, "substickY": 128, "frames": 1})
        log(i)

    seed = rows[0]
    dist0 = _dist3d(seed["link"]["pos"], seed["tetra"]["pos"])
    fix = {'stage': 'Hyrule', 'slot': 3, 'ground_y': GROUND_Y,
           'link_base': '0x%08x' % link_base, 'tetra_base': '0x%08x' % tetra_base,
           'tetra_type': ttype, 'teleport_to': [tx, GROUND_Y, tz],
           'seed_dist3d': dist0, 'pre_teleport': pre, 'frames': rows}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(fix, f, indent=1)

    # Terse summary: seed, peak speed, final distance / state.
    peak = max(row['tetra']['speedF'] for row in rows)
    fin = rows[-1]
    dfin = _dist3d(fin["link"]["pos"], fin["tetra"]["pos"])
    print('captured %d frames  seed d3d=%.2f  peak speedF=%.3f  final dXZ=%.2f stt=%d'
          % (len(rows), dist0, peak, dfin, fin['tetra_stt']), flush=True)
    print('wrote -> %s' % out, flush=True)
    return 0


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    sys.exit(capture(out=kw.get('out', DEFAULT_OUT),
                     tx=float(kw.get('tx', -1450.0)), tz=float(kw.get('tz', -700.0)),
                     frames=int(kw.get('frames', 120)),
                     link_base=int(kw['link_base'], 16) if 'link_base' in kw else LINK_BASE,
                     tetra_base=int(kw['tetra_base'], 16) if 'tetra_base' in kw else TETRA_BASE))
