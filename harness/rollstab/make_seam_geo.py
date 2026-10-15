"""Derive a ROLL/wall seam geometry fixture (rollstab convention) from the block-grid ordered mesh.

Offline + reproducible (no Dolphin): reads `fixtures/kaze_r11_walls_ordered.json` (the block-grid
ordered wall mesh `capture_walls.py` reconstructs from live DZB RAM) and writes a geo fixture in the
SAME schema as `kaze_r11_geo.json`, so `seamgeo.SeamGeo` loads it exactly like the kaze roll corner.

Generalizes `make_walkstab_geo.py` (which was hardcoded to the one walk seam): given the two incident
seam-wall poly ids, it AUTO-GATHERS the CrrPos barrier -- every floor-level wall the r=35 cylinder can
touch within `GATHER_R` of the seam vertex S, whose y-span overlaps the standing cylinder band -- in
the ordered-mesh (game block-grid correction) order. That is the same rule `seam_scan._gather` uses,
so the barrier is derived, not hand-picked (the walk-stab fixture's hand-listed BARRIER_ORDER).

The Phase-5 novel target (session 50) is the MIRROR-ROLL corner at S=(9069.90, -265.91) (polys 355 x
357), interior 109.4 -- a genuinely distinct seam from the proven roll seam (at +259, mirrored across z),
reached by a fresh live-minted anchor. Being a sharp corner it aims INTO the corner along the interior
bisector (the SeamGeo DEFAULT), NOT bear_to_S (dead-end s48: bear_to_S is only for near-FLAT seams).

RULED OUT (session 50, dead-end ledger): the distinct 97-deg corner S=(13539.24, 493.36) (polys 871 x
899) is NOT roll-clippable -- a dedicated search found no CrrPos-missing gap at any displacement (wall 899
extends +z, away from the into-corner roll dir, so the roll exits both finite wall segments). `disp_floor
< reach` is NECESSARY, not SUFFICIENT.

    python -m harness.rollstab.make_seam_geo               # regenerate the default (mirror) fixture
    python -m harness.rollstab.make_seam_geo wallA=871 wallB=899 out=<path>   # the ruled-out 97-deg corner
    python -m harness.rollstab.make_seam_geo mesh=fixtures/<room>_walls_ordered.json wallA=.. wallB=..
"""
import os, sys, json, math

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from harness.collision.seam_scan import _tri_xz_edge_dist, GATHER_R, WALL_H

MESH = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')
OUT_DEFAULT = os.path.join(_rb, 'fixtures', 'kaze_r11_seam_mirror_geo.json')

# the two incident seam faces of the Phase-5 novel target (mirror-roll corner; enumerate_seams):
WALLA_POLY, WALLB_POLY = 355, 357


def _tri(p):
    return dict(poly=p['poly'], v=p['v'], n=p['n'], d=p['d'])


def build(wallA_poly=WALLA_POLY, wallB_poly=WALLB_POLY, out=OUT_DEFAULT, mesh_path=MESH):
    if not os.path.isabs(mesh_path):
        mesh_path = os.path.join(_rb, *mesh_path.replace('\\', '/').split('/'))
    mesh_rel = os.path.relpath(mesh_path, _rb).replace('\\', '/')
    mesh = json.load(open(mesh_path))
    by = {p['poly']: p for p in mesh['polys']}
    wallA, wallB = by[wallA_poly], by[wallB_poly]

    # seam vertex S = the floor (lower-Y) vertex the two incident walls share.
    va = [tuple(v) for v in wallA['v']]
    vb = [tuple(v) for v in wallB['v']]
    shared = [v for v in va if v in vb]
    if not shared:
        # walls store slightly-offset seam verts (SEAM_XZ_TOL); take the closest floor vert pair.
        best = min(((a, b) for a in va for b in vb),
                   key=lambda ab: math.hypot(ab[0][0] - ab[1][0], ab[0][2] - ab[1][2]))
        shared = [min(best, key=lambda v: v[1])]
    S = min(shared, key=lambda v: v[1])
    link_y = S[1]

    # interior corner angle + into-corner bisector from the incident wall NORMALS (XZ) -- the sharp
    # corner aims along this bisector (make_tetra_geo / make_walkstab_geo convention).
    nA = (wallA['n'][0], wallA['n'][2])
    nB = (wallB['n'][0], wallB['n'][2])
    dot = max(-1.0, min(1.0, (nA[0] * nB[0] + nA[1] * nB[1])
                        / (math.hypot(*nA) * math.hypot(*nB))))
    interior = 180.0 - math.degrees(math.acos(dot))
    bx, bz = -(nA[0] + nB[0]), -(nA[1] + nB[1])
    bis_deg = math.degrees(math.atan2(bx, bz)) % 360.0

    # CrrPos barrier (DERIVED, the seam_scan._gather rule, not hand-picked): floor-level walls within
    # GATHER_R of S whose y-span overlaps the standing cylinder band, in block-grid (game order).
    lo, hi = link_y - 5.0, link_y + WALL_H[-1] + 5.0
    tris = []
    for p in mesh['polys']:
        vv = [tuple(v) for v in p['v']]
        ys = [v[1] for v in vv]
        if max(ys) < lo or min(ys) > hi:
            continue
        if _tri_xz_edge_dist(vv, S[0], S[2]) < GATHER_R:
            tris.append(_tri(p))

    out_geo = dict(
        stage=mesh.get('stage', 'kaze'), room=mesh.get('room'), mesh=mesh_rel,
        source='%s (block-grid ordered DZB mesh); '
               'walls %d x %d; barrier auto-gathered (GATHER_R=%.0f, band-overlap, ordered)'
               % (mesh_rel, wallA_poly, wallB_poly, GATHER_R),
        S=list(S), interior=round(interior, 3), bisector_deg=bis_deg, link_y=link_y,
        wallA=_tri(wallA), wallB=_tri(wallB),
        barrier=tris, tris=tris)
    json.dump(out_geo, open(out, 'w'), indent=1)
    print('wrote', out)
    print('  S=%s link_y=%.9f interior=%.3f bisector=%.3fdeg'
          % (tuple(round(c, 4) for c in S), link_y, interior, bis_deg))
    print('  wallA poly %d n=%s' % (wallA['poly'], [round(c, 5) for c in wallA['n']]))
    print('  wallB poly %d n=%s' % (wallB['poly'], [round(c, 5) for c in wallB['n']]))
    print('  barrier polys (ordered) %s' % [t['poly'] for t in tris])
    return out_geo


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    build(wallA_poly=int(kw.get('wallA', WALLA_POLY)),
          wallB_poly=int(kw.get('wallB', WALLB_POLY)),
          out=kw.get('out', OUT_DEFAULT),
          mesh_path=kw.get('mesh', MESH))
