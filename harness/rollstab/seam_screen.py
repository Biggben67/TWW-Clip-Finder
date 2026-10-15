"""Room-wide roll-corner DENSITY SCREEN -- rank every enumerated corner seam by genuine-dust
density BEFORE minting anything (the session-55/57 lesson made a tool: dust density prices the
search, and near-band yield -- which tracks the perp BAND WIDTH -- prices it better; the 97m's
84-sample/0.018u-band dust defeated ~15 draws while the 152's 1409/0.41u delivered in one).

Per corner seam in the ordered wall mesh: build the geo (make_seam_geo), screen
`SeamGeo.roll_reachable`, then run the s55-calibrated density scan (0.02 along x 0.0002 perp over
the reach band, perp window = the coarse genuine-column band +- 0.02) and measure the approach
CORRIDOR length (how far back along the aim the walk line stays >= 40u from every wall). Delivered
benchmarks for calibration: 152 = 1408 samples / 70% rows / 0.021u band; mirror = 360/17%/0.021;
the undelivered 97m = 84/14%/0.018.

Session-58 proof: this screen picked the 157-corner (polys 456x459: 1480 samples / 50% rows /
0.33u band / corridor 1400u) and `solve_focused` found 2 wall-faithful clips in one default draw.

PICKING RULES (all three matter):
  * density/band: want the 152's class (>~1000 samples, band >~0.02u; a WIDE band is the
    strongest signal -- near-band candidates come cheap);
  * link_y == the walkable floor (-6534.33 in kaze r11): an upper-level seam's floor/approach is
    unproven (the two densest raw candidates here sit at -4680);
  * corridor >= ~1000u: `mint_online`'s settle-until-frozen walk travels ~300-450u and must END
    at the ~580u rest (teleport-to-rest resets the cam leash -- dead-end #42), so the park needs
    d2s + settle of clear line.

    python -m harness.rollstab.seam_screen [out=<json>] [mesh=<walls_ordered.json>]
        # full screen (~10 min cold on the kaze mesh; scales with poly count)
"""
import os, sys, json, math, time

_rb = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from harness.collision.seam_scan import enumerate_seams
from harness.rollstab.make_seam_geo import build
from harness.rollstab.seamgeo import SeamGeo
from tww_sim.core.mathlib import deg_to_s16
from tww_sim.core.fp import f32 as _F

MESH = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')
OUT_DEFAULT = os.path.join(_rb, '_generated', 'seam_screen.json')


def _mesh_abs(mesh_path):
    p = mesh_path.replace('\\', '/')
    return p if os.path.isabs(mesh_path) else os.path.join(_rb, *p.split('/'))

# delivered / already-worked KAZE-R11 seams (S in XZ), excluded from a novel-target screen --
# applied only when the mesh's stage is kaze (a coincidental XZ match must not hide a candidate).
KNOWN = [
    ('proven', 9069.9043, 259.1986), ('mirror', 9069.9043, -265.9138),
    ('152', 10555.1904, 190.6696), ('157', 9689.1406, -150.3137),
    ('97+493', 13539.2393, 493.3560), ('97m', 13539.2393, -493.3560),
    ('152m', 10555.1904, -190.6696), ('824', 9689.1406, 123.4604),
    ('467-floorblocked', 10762.5254, -273.2637), ('163-corridorblocked', 9709.58, -13.43),
]
REACH = 49.2202          # the full-cap roll-stab displacement (reference/constants.md)
MAX_INTERIOR = 165.0     # corner filter: past this the seam is walk-stab (grazing) territory
CORRIDOR_CLEAR = 40.0    # walk-line wall clearance (Link's WallCorrect hold ~35u + margin)


def _edge_dist_xz(vv, x, z):
    best = 1e18
    for i in range(3):
        ax, az = vv[i][0], vv[i][2]
        bx, bz = vv[(i + 1) % 3][0], vv[(i + 1) % 3][2]
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
        best = min(best, math.hypot(x - (ax + t * dx), z - (az + t * dz)))
    return best


def genuine_perps(seam, astep=0.05, pstep=0.001, pspan=0.5):
    """Coarse genuine-column scan (solver._genuine_perps semantics, standalone for the screen)."""
    lo, hi = seam.search_band()
    Sx, Sz = seam.S
    out = set()
    a = -hi
    while a <= -lo:
        p = -pspan
        while p <= pspan:
            if seam.pred_genuine((_F(Sx + a * seam.DIRX + p * seam.PX),
                                  _F(Sz + a * seam.DIRZ + p * seam.PZ))):
                out.add(round(p, 3))
            p += pstep
        a += astep
    return sorted(out)


def density_scan(seam, gp, astep=0.02, pstep=0.0002, pmargin=0.02):
    """The s55 fine-scan metric: genuine sample count, along-row coverage, perp band width."""
    lo, hi = seam.search_band()
    Sx, Sz = seam.S
    n = rows = rows_hit = 0
    plo, phi = gp[0] - pmargin, gp[-1] + pmargin
    a = -hi
    while a <= -lo:
        rows += 1
        hit = 0
        p = plo
        while p <= phi:
            if seam.pred_genuine((_F(Sx + a * seam.DIRX + p * seam.PX),
                                  _F(Sz + a * seam.DIRZ + p * seam.PZ))):
                hit += 1
            p += pstep
        if hit:
            rows_hit += 1
            n += hit
        a += astep
    # band = full span (outlier-inflatable, see strategy page); band_dense = largest contiguous
    # column cluster's span (gap <= 3x the 0.001 column pitch), the honest width predictor

    best_lo = best_hi = gp[0]
    lo = hi = gp[0]
    for p in gp[1:]:
        if p - hi <= 0.003:
            hi = p
        else:
            lo = hi = p
        if hi - lo > best_hi - best_lo:
            best_lo, best_hi = lo, hi
    return dict(n=n, rows=rows, rows_hit=rows_hit, frac=round(rows_hit / max(1, rows), 3),
                band=round(gp[-1] - gp[0], 4), band_dense=round(best_hi - best_lo, 4),
                ncols=len(gp))


def corridor_len(walls, geo, clear=CORRIDOR_CLEAR, max_d=1400):
    """How far back along the aim line the approach stays >= `clear` from every floor-band wall."""
    ly = geo['link_y']
    ar = math.radians(geo.get('aim_deg', geo['bisector_deg']) % 360.0)
    dx, dz = math.sin(ar), math.cos(ar)
    Sx, Sz = geo['S'][0], geo['S'][2]
    length = 0
    for d in range(60, max_d + 1, 20):
        x, z = Sx - d * dx, Sz - d * dz
        for p in walls:
            ys = [v[1] for v in p['v']]
            if max(ys) < ly - 5 or min(ys) > ly + 180:
                continue
            if _edge_dist_xz(p['v'], x, z) < clear:
                return length
        length = d
    return length


def recheck(geo):
    """Re-measure ONE pick's reachability + honest density from its freshly built geo (the
    session-59 'step 0' -- always re-check `band_dense` before minting; the screen's stored row
    may predate a metric fix or carry an outlier-inflated `band`). Returns the same density/
    corridor fields as a screen row."""
    seam = SeamGeo(geo, deg_to_s16(geo.get('aim_deg', geo['bisector_deg'])))
    row = dict(reachable=seam.roll_reachable() is not None)
    if not row['reachable']:
        return row
    gp = genuine_perps(seam)
    if gp:
        row.update(density_scan(seam, gp))
    else:
        row['n'] = 0
    mesh = json.load(open(_mesh_abs(geo.get('mesh') or MESH)))
    row['corridor'] = corridor_len(mesh['polys'], geo)
    return row


def screen(out_path=OUT_DEFAULT, verbose=True, mesh_path=MESH):
    mesh_path = _mesh_abs(mesh_path)
    mesh = json.load(open(mesh_path))
    by = {p['poly']: p for p in mesh['polys']}
    region = [dict(poly=p['poly'], v=p['v'], n=p['n']) for p in mesh['polys']]
    xs = [v[0] for t in region for v in t['v']]
    ys = [v[1] for t in region for v in t['v']]
    zs = [v[2] for t in region for v in t['v']]
    seams = enumerate_seams(region, (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    if verbose:
        print('%d seams enumerated' % len(seams))
    out = []
    known = KNOWN if mesh.get('stage', 'kaze') == 'kaze' else []
    import tempfile
    for s in seams:
        Sx, Sz = s['S'][0], s['S'][2]
        if next((k for k, x, z in known if math.hypot(Sx - x, Sz - z) < 5.0), None):
            continue
        if s['coplanar'] or s['interior'] > MAX_INTERIOR or s['floor'] > REACH:
            continue
        groups = {}
        for pid in s['polys']:
            n = by[pid]['n']
            groups.setdefault((round(n[0], 4), round(n[2], 4)), []).append(pid)
        gk = sorted(groups, key=lambda k: -len(groups[k]))
        if len(gk) < 2:
            continue
        wa, wb = groups[gk[0]][0], groups[gk[1]][0]
        name = 'seam_%04d_%04d' % (wa, wb)
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
                gpath = tf.name
            geo = build(wallA_poly=wa, wallB_poly=wb, out=gpath, mesh_path=mesh_path)
            os.unlink(gpath)
            seam = SeamGeo(geo, deg_to_s16(geo.get('aim_deg', geo['bisector_deg'])))
            row = dict(name=name, polys=[wa, wb], S=[round(seam.S[0], 4), round(seam.S[1], 4)],
                       interior=geo.get('interior'), link_y=geo['link_y'], floor=s['floor'],
                       reachable=seam.roll_reachable() is not None)
            if row['reachable']:
                gp = genuine_perps(seam)
                if gp:
                    row.update(density_scan(seam, gp))
                else:
                    row['n'] = 0
                row['corridor'] = corridor_len(mesh['polys'], geo)
        except Exception as e:
            row = dict(name=name, polys=[wa, wb], error=str(e))
        out.append(row)
        if verbose:
            print(json.dumps(row))
    out.sort(key=lambda r: -(r.get('n') or 0))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, 'w'), indent=1)
    if verbose:
        print('wrote %s (%d rows)' % (out_path, len(out)))
    return out


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    screen(out_path=o.get('out', OUT_DEFAULT), mesh_path=o.get('mesh', MESH))
