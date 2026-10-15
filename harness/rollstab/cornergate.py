"""Phase-W CORNER gate: walk into the kaze r11 110-degree seam vertex, per-frame 0-ULP vs live.

The single-face gates (`wallgate.py`) prove WallCorrect against ONE plane. A corner needs TWO
non-coplanar walls to correct in the SAME frame, and WallCorrect does them SEQUENTIALLY (each
correction moves the cylinder the next one sees), so the visitation ORDER decides the resolved
position. The order is the game's DZB block-grid walk, reconstructed statically from the DZB tables by
`capture_walls.py` and written to `fixtures/kaze_r11_walls_ordered.json`; at the kaze seam it puts
wallA (poly 705) before wallB (poly 713) -- same block, ascending poly index.

The gate walks straight into the corner along the interior bisector (bearing 33318, which cruises
in at facing 33295 -- the seam-clip roll facing) until the cylinder wedges between both walls, then
holds. From first contact the pinned frames are two-wall corrections; feeding the game-ordered mesh
matches live bit-for-bit, and the SWAPPED order does NOT (the `check_order` diagnostic asserts the
order is load-bearing on this trajectory -- 36/60 frames differ offline).

    python -m harness.rollstab.cornergate mint          # once (mints the corner anchor)
    python -m harness.rollstab.cornergate plan          # offline preview (contact + pinned rows)
    python -m harness.rollstab.cornergate order          # offline: prove the order is load-bearing
    python -m harness.rollstab.cornergate run            # live DTM + rich log, then verify
    python -m harness.rollstab.cornergate verify         # offline 0-ULP diff vs the live log
    python -m harness.rollstab.cornergate golden         # promote the verified log to tests/golden/
"""
import os, sys, json, struct
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.land.walls import load_ordered_mesh, _mk_tri
from harness.rollstab import rest as C

BASE = 'kaze_r11_rollstab_idle13@twwgz'
ANCHOR = 'kaze_r11_wallcorner@twwgz'
# idle13 (9107.64,1006.05) + delta = (9090.34,638.65): 380u out from the seam vertex S along the
# interior bisector (0.0536,0.9986); a straight walk wedges the cylinder between wallA and wallB.
MINT_DX, MINT_DZ = -17.3, -367.4
BEAR_CORNER = 33318           # into the corner: bisector outward-normal angle 550, +0x8000
N_CORNER = 48                 # contact ~row 24 + ~24 pinned two-wall rows
MESH_PATH = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')
GATE_PATH = os.path.join(_rb, '_generated', 'cornergate.json')
GOLD_PATH = os.path.join(_rb, 'tests', 'golden', 'rollstab_corner.json')
WALL_A_POLY, WALL_B_POLY = 705, 713

_MESH = json.load(open(MESH_PATH))
_WALLS = [_mk_tri(p) for p in _MESH['polys']]


def bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _stick(anchor):
    seed = C.G.load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    return C.dtm_stick(stick_for_bearing(BEAR_CORNER, cs, 1.0))


def stream_for(anchor=None):
    sx, sy = _stick(anchor or ANCHOR)
    return [(sx, sy, 0)] * N_CORNER


def _sim(anchor, stream, walls=None):
    s = C.rest_state(anchor, walls=walls if walls is not None else _WALLS)
    rows = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        rows.append(dict(proc=s.state & 0xFF, pos_x=s.pos_x, pos_z=s.pos_z,
                         facing=s.facing & 0xFFFF, wall=s.wall_hit))
    return rows


def _first_pin(rows):
    return next((i for i, r in enumerate(rows) if r['wall']), None)


def plan():
    st = stream_for()
    rows = _sim(ANCHOR, st)
    pin = _first_pin(rows)
    print('corner rows=%d contact@%s procs: %s' % (
          len(st), pin, ' '.join('%x' % r['proc'] for r in rows)))
    for i, r in enumerate(rows):
        if pin is not None and i >= pin - 1:
            print('  k=%-2d proc=0x%02x pos=(%.7f, %.7f) wall=%s' % (
                  i, r['proc'], r['pos_x'], r['pos_z'], r['wall']))
    return 0


def check_order():
    """Prove the corner order is load-bearing: the game-ordered mesh and one with wallA/wallB
    swapped must diverge on the pinned frames (else the gate would not test the ordering)."""
    iA = next(i for i, p in enumerate(_MESH['polys']) if p['poly'] == WALL_A_POLY)
    iB = next(i for i, p in enumerate(_MESH['polys']) if p['poly'] == WALL_B_POLY)
    sw = _MESH['polys'][:]
    sw[iA], sw[iB] = sw[iB], sw[iA]
    walls_sw = [_mk_tri(p) for p in sw]
    st = stream_for()
    a = _sim(ANCHOR, st)
    b = _sim(ANCHOR, st, walls=walls_sw)
    ndiff = sum(1 for ra, rb in zip(a, b)
                if bits(ra['pos_x']) != bits(rb['pos_x']) or bits(ra['pos_z']) != bits(rb['pos_z']))
    print('wallA(poly705)@idx%d before wallB(poly713)@idx%d; frames where order matters: %d/%d'
          % (iA, iB, ndiff, len(st)))
    print('ORDER IS LOAD-BEARING' if ndiff else 'ORDER DOES NOT MATTER (pick a deeper wedge)')
    return 0 if ndiff else 1


def mint():
    from harness.rollstab.mint import mint as do_mint
    do_mint(BASE, ANCHOR, MINT_DX, MINT_DZ)
    return 0


def run(norelaunch=False):
    """One live clean-DTM run of the corner walk-in with rich per-frame logging."""
    from harness.dtm.run_dtm import run_dtm, land_ready
    import harness.dtm.run_dtm as R
    import dolphin_mem as D
    _orig = R._read_frame

    def rich(h, m):
        d = _orig(h, m)
        Pp = struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]
        for kk, off in (('d_frame', 0x2F64), ('m359C', 0x34C4)):
            d[kk] = struct.unpack('>f', D.read_bytes(h, m, Pp + off, 4))[0]
        return d
    R._read_frame = rich
    stream = stream_for()
    sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=b)
              for (sx, sy, b) in stream]
    sticks += [dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0)] * 12
    end = run_dtm(sticks, anchor=ANCHOR, ready=land_ready, relaunch_dolphin=not norelaunch,
                  log_frames=len(stream) + 2, verbose=True)
    frames = end['log']
    out = dict(anchor=ANCHOR, mesh=os.path.basename(MESH_PATH), stream=[list(r) for r in stream],
               frames=[dict(pos_x=f['pos_x'], pos_z=f['pos_z'], facing=f['facing'] & 0xFFFF,
                            proc=f['proc'], d_frame=f.get('d_frame'), m359C=f.get('m359C'))
                       for f in frames])
    os.makedirs(os.path.dirname(GATE_PATH), exist_ok=True)
    json.dump(out, open(GATE_PATH, 'w'))
    print('wrote %s (%d frames)' % (GATE_PATH, len(frames)), flush=True)
    return verify(out)


def verify(log=None):
    """Offline gate: replay the walk-in from rest WITH the ordered mesh; every live row must match
    pos (bit), proc, and facing exactly. 0 == CORNER GATE BIT-EXACT."""
    if log is None:
        log = json.load(open(GATE_PATH))
    stream = [tuple(r) for r in log['stream']]
    s = C.rest_state(log['anchor'], walls=_WALLS)
    nbad = 0
    for k, (sx, sy, b) in enumerate(stream):
        s.step(sx, sy, buttons=b)
        if k >= len(log['frames']):
            break
        lf = log['frames'][k]
        ok = (bits(s.pos_x) == bits(lf['pos_x']) and bits(s.pos_z) == bits(lf['pos_z'])
              and (s.state & 0xFF) == lf['proc'] and (s.facing & 0xFFFF) == (lf['facing'] & 0xFFFF))
        nbad += 0 if ok else 1
        print('  k=%-2d %s proc %02x|%02x pos(%.7f,%.7f)|(%.7f,%.7f) face %d|%d' % (
              k, 'ok  ' if ok else 'DIFF', s.state & 0xFF, lf['proc'], s.pos_x, s.pos_z,
              lf['pos_x'], lf['pos_z'], s.facing & 0xFFFF, lf['facing'] & 0xFFFF), flush=True)
    print('\ncorner: %s' % ('CORNER GATE BIT-EXACT' if nbad == 0 else 'DIVERGED (%d rows)' % nbad))
    return 0 if nbad == 0 else 1


def golden():
    import shutil
    if os.path.exists(GATE_PATH) and verify() == 0:
        shutil.copyfile(GATE_PATH, GOLD_PATH)
        print('promoted %s' % GOLD_PATH)
        return 0
    return 1


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    nr = 'norelaunch' in sys.argv
    sys.exit({'mint': mint, 'plan': plan, 'order': check_order,
              'run': lambda: run(norelaunch=nr), 'verify': verify, 'golden': golden}
             .get(cmd, lambda: (print(__doc__), 2)[1])())
