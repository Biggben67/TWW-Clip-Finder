"""Phase-W live wall gates: walk/roll INTO the kaze r11 wallB face, per-frame 0-ULP vs live.

Four gates, all from-rest clean-DTM runs on a minted anchor sitting 400u off the MIDDLE of
wallB's face (so only that one plane engages -- corner two-wall ordering is out of scope until
a corner gate exists):

  headon   walk dead into the face (travel = its inward normal): WallCorrect pins the centre at
           the 35u tangent, setNormalSpeedF's wall term decays nspeed to 0.4x.
  oblique  walk ~34deg off the normal: normal push + surviving tangential motion = the slide.
  crash    A mid-approach so the FRONT_ROLL meets the face inside the bonk window (frame 6-15,
           speedF >= 10, head-on within 5000): procFrontRollCrash -- reversed bounce, vy=7 arc,
           landing, ROLLFMIS playout.
  grind    a SLOW roll ground against the face: stop short of the wall, re-push 3 rows, A at
           speedF < 6.3 -> roll nspeed < 10, so the crash is disarmed by its speed floor
           (mRoll.field_0x3C) and the roll grinds the face full-length (the session-5 live
           behavior class). NOTE an A press while pinned head-on does NOT roll -- the game
           offers SIDLE (WHIDE_READY, proc 0x13); the sim forbids the roll there
           (walls.sidle_blocks_roll) without modeling the sidle itself.

Protocol (rest.py's): mint once, then per gate one clean-DTM run with rich per-frame logging ->
_generated/wallgate_<gate>.json, then the offline from-rest replay WITH the walls mesh diffs
pos/proc/facing 0-ULP per row. Goldens: tests/golden/rollstab_wall_<gate>.json (promote with
`golden`), regression: tests/test_rollstab_walls.py.

    python -m harness.rollstab.wallgate mint          # once (live, mints the anchor)
    python -m harness.rollstab.wallgate plan          # offline: streams + contact rows + A rows
    python -m harness.rollstab.wallgate run  <gate>   # live DTM + rich log
    python -m harness.rollstab.wallgate verify <gate> # offline 0-ULP diff vs the live log
    python -m harness.rollstab.wallgate golden        # promote verified logs to tests/golden/
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
from tww_sim.land.constants import FRONT_ROLL, FRONT_ROLL_CRASH
from tww_sim.land.walls import load_geo_tris
from harness.rollstab import rest as C
from harness.rollstab.geometry import ANCHOR_DIR

BASE = 'kaze_r11_rollstab_idle13@twwgz'
ANCHOR = 'kaze_r11_wallgate_faceB@twwgz'
# idle13 (9107.64, 1006.05) + this delta = (9156.5, 698.4): 400u from wallB's face middle
# (8911, 383) along its inward normal; interior segment (no wall between, clean first sweep).
MINT_DX, MINT_DZ = 48.9, -307.7

BEAR_IN = 39654               # into wallB: its normal angle cM_atan2s(nB) = 6886, +0x8000
BEAR_OBL = 36500              # ~17 deg off the normal: contacts mid-face, slides TOWARD the corner
N_OBL_SLIDE = 6               # slide rows post-pin (~5u/row toward the corner; more and the
#                               cylinder starts touching the wallA plane = the unordered corner)
A_BTN = 0x100
N_HEADON = 46                 # contact ~row 26 (entry turn + 400u cruise) + ~15 pinned rows
N_TAIL_CRASH = 44             # neutral post-A rows: bounce arc + landing + ROLLFMIS playout to WAIT
GATE_PATH = os.path.join(_rb, '_generated', 'wallgate_%s.json')
GOLD_PATH = os.path.join(_rb, 'tests', 'golden', 'rollstab_wall_%s.json')

_WALLS = load_geo_tris(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json'))


def bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _sticks(anchor):
    seed = C.G.load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    return (C.dtm_stick(stick_for_bearing(BEAR_IN, cs, 1.0)),
            C.dtm_stick(stick_for_bearing(BEAR_OBL, cs, 1.0)))


def _sim(anchor, stream):
    s = C.rest_state(anchor, walls=_WALLS)
    rows = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        rows.append(dict(proc=s.state & 0xFF, pos_x=s.pos_x, pos_z=s.pos_z,
                         facing=s.facing & 0xFFFF, wall=s.wall_hit,
                         nspeed=s.nspeed, speedF=s.speedF))
    return rows


def _first_pin(rows):
    return next((i for i, r in enumerate(rows) if r['wall']), None)


def stream_for(gate, anchor=None):
    """Build the gate's (sx, sy, buttons) stream. The A rows for crash/grind are derived by
    OFFLINE simulation against the walls mesh (exact, not eyeballed): crash = the earliest A row
    whose roll enters FRONT_ROLL_CRASH; grind = A three rows after the wall pin."""
    anchor = anchor or ANCHOR
    straight, oblq = _sticks(anchor)
    if gate == 'headon':
        return [(straight[0], straight[1], 0)] * N_HEADON
    if gate == 'oblique':
        base = [(oblq[0], oblq[1], 0)] * N_HEADON
        pin = _first_pin(_sim(anchor, base))
        assert pin is not None, 'oblique stream never reaches the wall'
        return base[:pin + 1 + N_OBL_SLIDE]          # short slide: keep clear of the corner
    base = [(straight[0], straight[1], 0)] * N_HEADON
    pin = _first_pin(_sim(anchor, base))
    assert pin is not None, 'straight stream never reaches the wall'
    if gate == 'grind':
        # Coast without stopping (a WAIT opens the unmodeled stop->re-walk blend), re-push,
        # A at speedF < 6.33 so the crash speed floor never arms: scan for that combo.
        for cut in range(pin - 8, pin - 3):
            for coast in (3, 4, 5, 6):
                for push in (1, 2, 3):
                    held = base[:cut] + [(128, 128, 0)] * coast
                    held += [(straight[0], straight[1], A_BTN if i == push - 1 else 0)
                             for i in range(push)]
                    st = held + [(straight[0], straight[1], 0)] * 30
                    rows = _sim(anchor, st)
                    if (any(r['proc'] == FRONT_ROLL and r['wall'] for r in rows)
                            and not any(r['proc'] == FRONT_ROLL_CRASH for r in rows)
                            and not any(r['proc'] == 4 for r in rows[cut:])):
                        return st
        raise AssertionError('no cut/coast/push combo produced a wall-grinding slow roll')
    if gate == 'crash':
        for k in range(pin - 12, pin - 2):           # roll must MEET the wall in frames 6-15
            # stick held through the A press (+2-frame delivery) then NEUTRAL: the crash plays
            # out to WAIT (position-frozen), avoiding a re-walk on the unwarmed ROLLFMIS stream.
            held = [(straight[0], straight[1], A_BTN if i == k else 0) for i in range(k + 3)]
            st = held + [(128, 128, 0)] * N_TAIL_CRASH
            rows = _sim(anchor, st)
            if any(r['proc'] == FRONT_ROLL_CRASH for r in rows):
                return st
        raise AssertionError('no A row produced a crash (window scan empty)')
    raise KeyError(gate)


def plan():
    """Offline preview of all four gates: per-row proc/pos/wall so the streams + windows are
    verified BEFORE any live run."""
    for gate in ('headon', 'oblique', 'crash', 'grind'):
        st = stream_for(gate)
        rows = _sim(ANCHOR, st)
        pin = _first_pin(rows)
        procs = ' '.join('%x' % r['proc'] for r in rows)
        print('%-7s rows=%d pin@%s procs: %s' % (gate, len(st), pin, procs))
        for i, r in enumerate(rows):
            if pin is not None and (abs(i - pin) <= 2 or r['proc'] in (FRONT_ROLL, FRONT_ROLL_CRASH)):
                print('   k=%-2d proc=0x%02x pos=(%.7f, %.7f) nspeed=%.4f wall=%s' % (
                      i, r['proc'], r['pos_x'], r['pos_z'], r['nspeed'], r['wall']))
    return 0


def mint():
    from harness.rollstab.mint import mint as do_mint
    do_mint(BASE, ANCHOR, MINT_DX, MINT_DZ)
    return 0


def run(gate, norelaunch=False):
    """One live clean-DTM run of the gate stream with rest.py's rich per-frame logging."""
    from harness.dtm.run_dtm import run_dtm, land_ready
    import harness.dtm.run_dtm as R
    import dolphin_mem as D
    _orig = R._read_frame

    def rich(h, m):
        d = _orig(h, m)
        Pp = struct.unpack('>I', D.read_bytes(h, m, 0x803AD860, 4))[0]
        for kk, off in (('d_frame', 0x2F64), ('w_frame', 0x2F78), ('d_rate', 0x2F60),
                        ('m3598', 0x34C0), ('m359C', 0x34C4), ('m35B4', 0x34DC)):
            d[kk] = struct.unpack('>f', D.read_bytes(h, m, Pp + off, 4))[0]
        return d
    R._read_frame = rich
    stream = stream_for(gate)
    sticks = [dict(stickX=sx, stickY=sy, substickX=128, substickY=128, buttons=b)
              for (sx, sy, b) in stream]
    sticks += [dict(stickX=128, stickY=128, substickX=128, substickY=128, buttons=0)] * 20
    end = run_dtm(sticks, anchor=ANCHOR, ready=land_ready, relaunch_dolphin=not norelaunch,
                  log_frames=len(stream) + 2, verbose=True)
    frames = end['log']
    out = dict(anchor=ANCHOR, gate=gate, stream=[list(r) for r in stream],
               frames=[dict(pos_x=f['pos_x'], pos_z=f['pos_z'], facing=f['facing'] & 0xFFFF,
                            proc=f['proc'], d_frame=f.get('d_frame'), w_frame=f.get('w_frame'),
                            m3598=f.get('m3598'), m359C=f.get('m359C')) for f in frames])
    os.makedirs(os.path.dirname(GATE_PATH % gate), exist_ok=True)
    json.dump(out, open(GATE_PATH % gate, 'w'))
    print('wrote %s (%d frames)' % (GATE_PATH % gate, len(frames)), flush=True)
    return verify(gate, out)


def verify(gate, log=None):
    """Offline gate: replay the stream from rest WITH the walls mesh; every live row must match
    pos (bit), proc, and facing exactly. 0 == WALL GATE BIT-EXACT."""
    if log is None:
        log = json.load(open(GATE_PATH % gate))
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
        mark = 'ok  ' if ok else 'DIFF'
        print('  k=%-2d %s proc %02x|%02x pos(%.7f,%.7f)|(%.7f,%.7f) face %d|%d' % (
              k, mark, s.state & 0xFF, lf['proc'], s.pos_x, s.pos_z, lf['pos_x'], lf['pos_z'],
              s.facing & 0xFFFF, lf['facing'] & 0xFFFF), flush=True)
    print('\n%s: %s' % (gate, 'WALL GATE BIT-EXACT' if nbad == 0 else 'DIVERGED (%d rows)' % nbad))
    return 0 if nbad == 0 else 1


def golden():
    """Promote verified live logs to committed goldens (only rows the regression test replays)."""
    import shutil
    n = 0
    for gate in ('headon', 'oblique', 'crash', 'grind'):
        src = GATE_PATH % gate
        if os.path.exists(src) and verify(gate) == 0:
            shutil.copyfile(src, GOLD_PATH % gate)
            print('promoted %s' % (GOLD_PATH % gate))
            n += 1
    return 0 if n else 1


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != 'norelaunch']
    cmd = args[0] if args else 'plan'
    if cmd == 'mint':
        sys.exit(mint())
    if cmd == 'plan':
        sys.exit(plan())
    if cmd == 'run':
        sys.exit(run(args[1], norelaunch='norelaunch' in sys.argv))
    if cmd == 'verify':
        sys.exit(verify(args[1]))
    if cmd == 'golden':
        sys.exit(golden())
    print(__doc__)
    sys.exit(2)
