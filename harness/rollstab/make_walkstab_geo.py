"""Derive the kaze r11 WALK-STAB seam geometry fixture (rollstab convention) from the ordered mesh.

Offline + reproducible (no Dolphin): reads `fixtures/kaze_r11_walls_ordered.json` (the block-grid
ordered wall mesh capture_walls.py reconstructs from live DZB RAM) and writes
`fixtures/kaze_r11_walkstab_geo.json` in the SAME schema as `kaze_r11_geo.json`, so the walk-stab
driver loads it via `seamgeo.SeamGeo` exactly like the roll seam loads its corner.

The walk-stab seam is the NEARLY-FLAT seam at S=(9030.955, 1385.858) (poly 803 x 802, interior
168.97 deg). Its CrrPos barrier is the LOCAL wall chain the r=35 cylinder can touch on the walk in,
in the ordered-mesh order [801, 803, 802, 804, 798, 800] -- the list the shipped walk-stab solver
used; emitted verbatim as `tris` (the canonical ordered barrier SeamGeo consumes). `wallA`/`wallB`
are the two incident seam faces (803 / 802); `S` is their shared floor vertex (full f32 precision,
NOT the old rounded literal); `link_y` is that vertex's floor Y. `bisector_deg` is recorded for the
schema (the corner into-aim), but the walk-stab thrust facing derives from bear_to_S, not it (a flat
seam grazes toward S) -- so the driver builds its SeamGeo with `aim_deg=bear_to_S`.

    python -m harness.rollstab.make_walkstab_geo    # regenerate fixtures/kaze_r11_walkstab_geo.json
"""
import os, sys, json, math
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

MESH = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')
OUT = os.path.join(_rb, 'fixtures', 'kaze_r11_walkstab_geo.json')

WALLA_POLY, WALLB_POLY = 803, 802          # the two incident seam faces
BARRIER_ORDER = [801, 803, 802, 804, 798, 800]   # ordered-mesh CrrPos chain (r=35 sweep footprint)


def _tri(p):
    return dict(poly=p['poly'], v=p['v'], n=p['n'], d=p['d'])


def build():
    mesh = json.load(open(MESH))
    by = {p['poly']: p for p in mesh['polys']}
    wallA, wallB = by[WALLA_POLY], by[WALLB_POLY]
    # seam vertex S = the floor vertex shared by both incident walls (full f32 precision).
    va = [tuple(v) for v in wallA['v']]
    vb = [tuple(v) for v in wallB['v']]
    shared = [v for v in va if v in vb]
    S = min(shared, key=lambda v: v[1])        # the lower (floor) shared vertex
    link_y = S[1]
    # interior corner angle + into-corner bisector from the incident wall NORMALS (XZ), make_tetra_geo
    # convention. bisector is the corner default aim; the flat-seam driver overrides it with bear_to_S.
    nA = (wallA['n'][0], wallA['n'][2])
    nB = (wallB['n'][0], wallB['n'][2])
    dot = max(-1.0, min(1.0, (nA[0] * nB[0] + nA[1] * nB[1])
                        / (math.hypot(*nA) * math.hypot(*nB))))
    interior = 180.0 - math.degrees(math.acos(dot))
    bx, bz = -(nA[0] + nB[0]), -(nA[1] + nB[1])
    bis_deg = math.degrees(math.atan2(bx, bz)) % 360.0
    tris = [_tri(by[pid]) for pid in BARRIER_ORDER]
    out = dict(
        stage='kaze', room=11,
        source='fixtures/kaze_r11_walls_ordered.json (block-grid ordered DZB mesh, savestate slot 3)',
        S=list(S), interior=round(interior, 3), bisector_deg=bis_deg, link_y=link_y,
        wallA=_tri(wallA), wallB=_tri(wallB),
        barrier=tris,          # schema field (== tris here; SeamGeo consumes `tris`)
        tris=tris)             # the canonical ordered CrrPos barrier (r=35 cylinder footprint)
    json.dump(out, open(OUT, 'w'), indent=1)
    print('wrote', OUT)
    print('  S=%s link_y=%.9f interior=%.3f bisector=%.2fdeg'
          % (S, link_y, interior, bis_deg))
    print('  wallA poly %d n=%s' % (wallA['poly'], wallA['n']))
    print('  wallB poly %d n=%s' % (wallB['poly'], wallB['n']))
    print('  tris order %s' % BARRIER_ORDER)
    return out


if __name__ == '__main__':
    build()
