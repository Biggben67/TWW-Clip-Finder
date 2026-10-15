"""Capture the GROUND under the Tetra roll-stab approach -> a sim fixture (ROADMAP Phase G).

Phase G asks one question before any ground modeling: is the floor Link's roll crosses at the Tetra
corner FLAT? If flat, `getGroundAngle`'s slope term is 0 (the sim already hardcodes r3=0 in the
speedF `cM_scos` scale, and the r3<0 x0.85 branch never fires) and the m35B8 per-foot ground-lift is
provably 0 -- so Phase G collapses and the existing flat-floor model (exact at kaze, also flat)
applies unchanged. This reads the running room's DZB and samples the WALKABLE ground plane along the
roll footprint old->seam, writing the sampled polys + normals to a fixture the test asserts flat.

    python -m harness.rollstab.capture_ground                 # Tetra corner defaults -> default fixture
    python -m harness.rollstab.capture_ground out=<path> old=X,Z new=X,Z

Live-only (needs Dolphin at the Tetra corner: flooded Hyrule, savestate slot 3; see
../tools/DOLPHIN_CONTROL.md). Reads RAM via `dolphin_mem` (../tools/) ONLY -- self-contained, no
dependency on any sibling repo (mirrors `capture_walls.py`). The DZB read is identical to
capture_walls'; only the surface class filter differs (ground ny>=0.5, not wall).
"""
import json
import math
import os
import struct
import sys

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'hyrule_tetra_ground.json')

# JP/GZLJ01 addresses + offsets (same DZB read as capture_walls.py; see collision.md).
DBGS = 0x803B93A8          # cBgS registry, stride 0x14 (+0 cBgW*, +4 flags bit0=used)
LINK_ACCH = 0x803BD910     # -> dBgS_LinkAcch; +0x554 gnd polyIdx u16, +0x556 gnd bgIdx u16
STAGE_NAME = 0x803BD23C
LINK_X = 0x803D78FC        # link_x/y/z (f32)

# The Tetra clip's settled `old` and the seam endpoint NEW (actor-push.md; NEW live-confirmed
# bit-for-bit, old = NEW - push - thrust). The roll footprint runs old -> the seam vertex.
TETRA_OLD = (-1692.31, -955.02)
TETRA_NEW = (-1727.3423, -990.6356)
WALK_Y_BAND = 50.0         # keep only the walkable ~Y0 plane; skip the ~560u overhead sloped terrain


def _reader():
    import dolphin_mem as dm
    h, mem1 = dm.attach()

    class R:
        def block(self, a, n):
            return dm.read_bytes(h, mem1, a, n)

        def u16(self, a):
            return struct.unpack('>H', self.block(a, 2))[0]

        def s32(self, a):
            return struct.unpack('>i', self.block(a, 4))[0]

        def u32(self, a):
            return struct.unpack('>I', self.block(a, 4))[0]

        def f32(self, a):
            return struct.unpack('>f', self.block(a, 4))[0]
    return R()


def _stage(r):
    return r.block(STAGE_NAME, 11).split(b'\x00')[0].decode('ascii', 'replace')


def _classify(ny):
    if ny >= 0.5:
        return 'ground'
    if ny < -0.8:
        return 'roof'
    return 'wall'


def _in_tri(px, pz, v0, v1, v2):
    """2D (XZ) point-in-triangle via barycentric sign test."""
    d1 = (px - v1[0]) * (v0[2] - v1[2]) - (v0[0] - v1[0]) * (pz - v1[2])
    d2 = (px - v2[0]) * (v1[2] - v2[2]) - (v1[0] - v2[0]) * (pz - v2[2])
    d3 = (px - v0[0]) * (v2[2] - v0[2]) - (v2[0] - v0[0]) * (pz - v0[2])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _room_bg(r):
    acch = r.u32(LINK_ACCH)
    if 0x80000000 <= acch < 0x81800000:
        poly = r.u16(acch + 0x554)
        bg = r.u16(acch + 0x556)
        if poly != 0xFFFF and bg != 0x100:
            return bg
    raise RuntimeError("Link has no floor poly; stand Link on the room floor before capturing")


def capture(out=DEFAULT_OUT, old=TETRA_OLD, new=TETRA_NEW, bg=None):
    r = _reader()
    if bg is None:
        bg = _room_bg(r)
    bgw = r.u32(DBGS + bg * 0x14 + 0x00)
    pm_bgd = r.u32(bgw + 0x94)
    v_num = r.s32(pm_bgd + 0x00)
    t_num = r.s32(pm_bgd + 0x08)
    t_tbl = r.u32(pm_bgd + 0x0C)
    pm_vtx = r.u32(bgw + 0x90)                        # WORLD verts (12B x,y,z)
    pm_tri = r.u32(bgw + 0x88)                        # runtime planes stride 0x18: nx,ny,nz,d
    vb = r.block(pm_vtx, v_num * 12)
    verts = [struct.unpack_from('>3f', vb, i * 12) for i in range(v_num)]
    tb = r.block(t_tbl, t_num * 10)
    tris = [struct.unpack_from('>3H', tb, i * 10) for i in range(t_num)]
    pb = r.block(pm_tri, t_num * 0x18)
    planes = [struct.unpack_from('>4f', pb, i * 0x18) for i in range(t_num)]

    def walkable_ground_at(px, pz):
        """Walkable ground tris (class ground, |plane-Y| < band) containing (px,pz)."""
        out_hits = []
        for j, (a, b, c) in enumerate(tris):
            n = planes[j]
            if _classify(n[1]) != 'ground':
                continue
            y = -(n[0] * px + n[2] * pz + n[3]) / n[1]
            if abs(y) > WALK_Y_BAND:
                continue
            if _in_tri(px, pz, verts[a], verts[b], verts[c]):
                out_hits.append((j, n, y))
        return out_hits

    # Sample the walkable floor along the roll footprint old -> seam. t=1.0 (NEW) is the clip point
    # BEHIND the wall (no floor there by design), so sample up to just short of the seam.
    samples = []
    for k in range(19):                               # t = 0.00 .. 0.90
        t = k * 0.05
        px = old[0] + (new[0] - old[0]) * t
        pz = old[1] + (new[1] - old[1]) * t
        hits = walkable_ground_at(px, pz)
        rec = {'t': round(t, 2), 'x': px, 'z': pz,
               'polys': [{'poly': j, 'n': [n[0], n[1], n[2]], 'd': n[3], 'y': y}
                         for j, n, y in hits]}
        samples.append(rec)

    def slope_deg(n):
        return math.degrees(math.acos(max(-1.0, min(1.0, n[1]))))

    all_walk = [(j, n, y) for s in samples for j, n, y in
                [(p['poly'], p['n'], p['y']) for p in s['polys']]]
    flat = all(abs(n[0]) < 1e-6 and abs(n[1] - 1.0) < 1e-6 and abs(n[2]) < 1e-6
               for _j, n, _y in all_walk) and len(all_walk) > 0
    ys = sorted({round(y, 5) for _j, _n, y in all_walk})
    fix = {'stage': _stage(r), 'bg': bg, 'old': list(old), 'new': list(new),
           'walk_y_band': WALK_Y_BAND, 'flat': flat, 'floor_ys': ys, 'samples': samples}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(fix, f, indent=1)
    covered = sum(1 for s in samples if s['polys'])
    max_slope = max((slope_deg(n) for _j, n, _y in all_walk), default=float('nan'))
    print('stage=%s bg=%d  approach samples covered %d/%d  floor_ys=%s  max_slope=%.6f deg  FLAT=%s'
          % (fix['stage'], bg, covered, len(samples), ys, max_slope, flat), flush=True)
    print('wrote -> %s' % out, flush=True)
    return 0


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    old = tuple(float(x) for x in kw['old'].split(',')) if 'old' in kw else TETRA_OLD
    new = tuple(float(x) for x in kw['new'].split(',')) if 'new' in kw else TETRA_NEW
    sys.exit(capture(out=kw.get('out', DEFAULT_OUT), old=old, new=new,
                     bg=int(kw['bg']) if 'bg' in kw else None))
