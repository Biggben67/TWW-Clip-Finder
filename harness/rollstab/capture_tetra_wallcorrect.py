"""Capture Tetra's BG WallCorrect at the corner -> a sim gate fixture (ROADMAP Phase C).

The follow keeps a 130 u distance, so Tetra never touches a wall in a normal chase. A wedged Tetra is
WALL-BRACED: her `mObjAcch.CrrPos` WallCorrect against the corner walls cancels her CC recoil so she
holds in place instead of recoiling. This capture validates that WallCorrect MECHANIC in isolation
(whether corner-bracing helps the clip is a separate, refuted question -- it pushes the wrong way; see
the rollstab README ## Status). The capture:
teleport Tetra to OVERLAP the corner's +x wall (x = -1727) and log the frame-1 ejection, so the
offline gate can confirm `core.collision.acch_crr_pos` with her R=50 / half-H=30 cylinder
reproduces the corrected position bit-for-bit.

    python -m harness.rollstab.capture_tetra_wallcorrect                 # defaults -> default fixture

Two-step teleport so `pm_old_pos` syncs to a CLEAR waypoint first (avoids a long CrrPos sweep-snap):
place Tetra clear of the wall, advance one frame (old_pos <- clear), then write the overlapping
`new` and advance one frame -- that frame's CrrPos sweeps clear->overlap and WallCorrect ejects her.
Link is left at his slot-3 idle spot; Tetra's speedF is 0 on the eject frame (she only starts to
follow afterward), so `new` == the written overlap position with no movement added.

Live-only (Dolphin at the Tetra corner: flooded Hyrule, savestate slot 3). `dolphin_mem` only.
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

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'hyrule_tetra_wallcorrect.json')
TETRA_BASE = 0x80ACD20C
OFF_POS = 0x1F8
OFF_SPEEDF = 0x254
OFF_TYPE = 0x84F
GROUND_Y = 0.1632676
# Corner +x wall is at x = -1727 (normal +x), spanning z = -990..753. Stage the overlap mid-span,
# clear of the corner vertex: a CLEAR waypoint 57 u off the wall, then 23 u INSIDE her R=50.
CLEAR = (-1670.0, -500.0)
OVERLAP = (-1700.0, -500.0)


def capture(out=DEFAULT_OUT, tetra_base=TETRA_BASE):
    import dolphin_mem as dm
    h, mem1 = dm.attach()

    def f32(a):
        return struct.unpack('>f', dm.read_bytes(h, mem1, a, 4))[0]

    def wf(a, v):
        dm.write_bytes(h, mem1, a, struct.pack('>f', v))

    def pos():
        return [f32(tetra_base + OFF_POS), f32(tetra_base + OFF_POS + 4), f32(tetra_base + OFF_POS + 8)]

    if struct.unpack('>b', dm.read_bytes(h, mem1, tetra_base + OFF_TYPE, 1))[0] != 5:
        raise RuntimeError("not the type-5 Tetra; load slot 3 first")

    # Step 1: clear waypoint, sync old_pos.
    wf(tetra_base + OFF_POS, CLEAR[0]); wf(tetra_base + OFF_POS + 4, GROUND_Y)
    wf(tetra_base + OFF_POS + 8, CLEAR[1]); wf(tetra_base + OFF_SPEEDF, 0.0)
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 128, "frames": 1})
    old = pos()
    # Step 2: write the overlapping new, advance one frame -> WallCorrect ejects.
    wf(tetra_base + OFF_POS, OVERLAP[0]); wf(tetra_base + OFF_POS + 8, OVERLAP[1])
    new = pos()
    speedf_before = f32(tetra_base + OFF_SPEEDF)
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 128, "frames": 1})
    ejected = pos()

    fix = {'stage': 'Hyrule', 'slot': 3, 'wall': 'corner +x face at x=-1727 (normal +x)',
           'wall_r': 50.0, 'wall_half_h': 30.0, 'ground_y': GROUND_Y,
           'old': old, 'new': new, 'speedf_before_eject': speedf_before, 'ejected': ejected}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fp:
        json.dump(fix, fp, indent=1)
    print('old=%.4f,%.4f new=%.4f,%.4f -> ejected=%.6f,%.6f (speedF_before=%.3f)'
          % (old[0], old[2], new[0], new[2], ejected[0], ejected[2], speedf_before), flush=True)
    print('wrote -> %s' % out, flush=True)
    return 0


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    sys.exit(capture(out=kw.get('out', DEFAULT_OUT)))
