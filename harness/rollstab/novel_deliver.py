"""ONE-SHOT novel-seam delivery -- ROADMAP Phase A step 2 (session 61).

Folds the per-delivery touch-list (sessions 58-60) into one command: given a screened corner's
two wall poly ids, run every stage of the recipe IN ORDER, aborting on the first RED gate:

  1. geo       build the geo fixture (make_seam_geo), named by the seam name, aim_deg injectable
  2. recheck   offline reachability + HONEST density (band_dense, session-59 step 0)
  3. floor     LIVE park-floor probe along the aim line (ledger #43: corridor != floor)
  4. cam       LIVE cam-target screen (ledger #44) -> a FROZEN target + the MEASURED settle travel
  5. mint      mint_online at the screened target/settle; verify the baseline roll fires ON-LINE
  6. rest      the LIVE REST gate (one clean DTM) -- BIT-EXACT or abort; writes the rest golden
  7. dust      dust2d prebuild (outside the draw budget)
  8. solve     solve_focused: the default draw, then the DOCUMENTED knob families on a 0-hit
               (session 59: a thin-dense-band seam may need c3m variants -- vary families, never
               invent per-seam constants)
  9. ship      deliver.ship -> live 0-ULP clean-DTM clip; writes the ship golden
 10. test      write the per-seam test scaffold (never overwrites an existing locked test)

Per-stage outputs persist in `_generated/novel_<name>.json`, so a re-run resumes at `start=`
with the earlier stages' measured values (cam target, settle, draws tried) intact. Every knob is
measured per seam or a documented family -- nothing tuned ([[no-overtuned-constants]]).

Run from the repo root (fixture/golden paths are stored repo-relative):

    python -m harness.rollstab.novel_deliver wallA=<pid> wallB=<pid> [name=seam<pid>]
        [aim_deg=<deg>] [d2s=580] [budget=110] [start=<stage>] [stop=<stage>]
        [mesh=<walls_ordered.json>] [prefix=kaze_r11] [base=<mint base anchor>]
        [max_iter=3]   # mint_online re-park budget; raise when the secant is still
                       # converging at the cap (it aborts cleanly either way)

Second-room knobs (ROADMAP Phase A step 4): `mesh=` names the room's block-grid ordered wall
mesh (capture_walls.py), `prefix=` names the room in anchor/fixture/test paths (default
kaze_r11), `base=` names the mint-base anchor savestate IN that room (the teleport source for
floor/cam/mint -- any settled idle anchor in the stage works; mint_current re-captures the full
seed). All three default to the kaze r11 values, byte-identical for every existing seam.
"""
import os, sys, json, math, time

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

from tww_sim.core.mathlib import deg_to_s16

STAGES = ('geo', 'recheck', 'floor', 'cam', 'mint', 'rest', 'dust', 'solve', 'ship', 'test')
PERP_TOL = 2.0            # mint_online's on-line acceptance (arc-reach fraction, session 54)
SETTLE_EST0 = 420.0       # cam-screen park settle allowance before the travel is MEASURED
FLOOR_MARGIN = 100.0      # probe the park and one step past it (ledger #43's 1050-vs-1100 edge)
# Documented c3m crawl families, tried IN ORDER on a 0-hit draw (strategy page, session 59:
# each is a fresh independent lattice, never a tuned constant; 0.78 delivered the 152m).
DRAW_FAMILIES = ({}, {'c3m': 0.78}, {'c3m': 0.72}, {'c3m': 0.56})


def _state_path(name):
    return os.path.join(_rb, '_generated', 'novel_%s.json' % name)


def _load_state(name):
    p = _state_path(name)
    return json.load(open(p)) if os.path.exists(p) else {}


def _save_state(name, st):
    os.makedirs(os.path.dirname(_state_path(name)), exist_ok=True)
    json.dump(st, open(_state_path(name), 'w'), indent=1)


def _banner(stage, msg=''):
    print('\n=== novel_deliver [%s] %s' % (stage, msg), flush=True)


def _fail(stage, msg):
    print('=== novel_deliver [%s] FAIL: %s' % (stage, msg), flush=True)
    return 1


def _seam_for(geo, anchor=None):
    """SeamGeo at the minted anchor's csangle when it exists, else the aim-derived pre-mint yaw
    (density/dust geometry is csangle-independent only through F -- both screens used this)."""
    from harness.rollstab.seamgeo import SeamGeo
    from harness.rollstab.geometry import load_seed
    if anchor is not None:
        return SeamGeo(geo, load_seed(anchor)['csangle'] & 0xFFFF)
    return SeamGeo(geo, deg_to_s16(geo.get('aim_deg', geo['bisector_deg'])))


KAZE_BASE = 'kaze_r11_rollstab_idle13@twwgz'


def deliver_novel(wallA, wallB, name=None, aim_deg=None, d2s=580.0, budget=110.0,
                  start='geo', stop='test', mesh=None, prefix='kaze_r11', base=KAZE_BASE,
                  max_iter=3):
    name = name or ('seam%d' % wallA)
    anchor = '%s_rollstab_%s@twwgz' % (prefix, name)
    geo_rel = 'fixtures/%s_%s_geo.json' % (prefix, name)
    geo_abs = os.path.join(_rb, *geo_rel.split('/'))
    rest_golden = os.path.join(_rb, 'fixtures', '%s_rest_golden.json' % name)
    ship_golden = os.path.join(_rb, 'fixtures', '%s_roll_ship_golden.json' % name)
    test_path = os.path.join(_rb, 'tests', 'test_%s_clip.py' % name)
    st = _load_state(name)
    st.update(name=name, anchor=anchor, geo=geo_rel, wallA=wallA, wallB=wallB,
              prefix=prefix, base=base, **({'mesh': mesh} if mesh else {}))
    run = {s: (STAGES.index(start) <= i <= STAGES.index(stop)) for i, s in enumerate(STAGES)}

    # --- 1. geo ---------------------------------------------------------------------------
    if run['geo']:
        _banner('geo', '%s walls %d x %d -> %s' % (name, wallA, wallB, geo_rel))
        from harness.rollstab.make_seam_geo import build, MESH as _KAZE_MESH
        geo = build(wallA_poly=wallA, wallB_poly=wallB, out=geo_abs,
                    mesh_path=(mesh or _KAZE_MESH))
        if aim_deg is not None:
            geo['aim_deg'] = float(aim_deg)
            json.dump(geo, open(geo_abs, 'w'), indent=1)
            print('  aim_deg=%s declared in the fixture' % aim_deg)
    if not os.path.exists(geo_abs):
        return _fail('geo', 'no geo fixture at %s (run from stage geo)' % geo_rel)
    geo = json.load(open(geo_abs))
    _save_state(name, st)

    # --- 2. recheck (offline honest density) ----------------------------------------------
    if run['recheck']:
        _banner('recheck', 'reachability + band_dense (session-59 step 0)')
        from harness.rollstab.seam_screen import recheck
        row = recheck(geo)
        st['recheck'] = row
        _save_state(name, st)
        print('  %s' % json.dumps(row), flush=True)
        if not row['reachable']:
            return _fail('recheck', 'not roll-reachable (needs a non-roll technique)')
        if not row.get('n'):
            return _fail('recheck', 'no genuine dust in the reach band')

    # --- 3. floor (LIVE park-floor probe) --------------------------------------------------
    if run['floor']:
        park = d2s + SETTLE_EST0
        _banner('floor', 'park-floor probe at d2S %.0f / %.0f (ledger #43)'
                % (park, park + FLOOR_MARGIN))
        from harness.rollstab.mint import floor_probe
        fl = floor_probe(geo_abs, [park, park + FLOOR_MARGIN], base=base)
        st['floor'] = {str(k): v for k, v in fl.items()}
        _save_state(name, st)
        if not fl[park]:
            return _fail('floor', 'no floor at the park (d2S %.0f) -- unmintable by this '
                         'pipeline (467 precedent); needs the walk-stab tier or '
                         'camera-in-the-loop' % park)

    # --- 4. cam (session-69 INVARIANT camera screen -> a CLEAN frozen csangle + settle) ----
    if run['cam']:
        _banner('cam', 'invariant csangle screen (ledger #56) + smallest-settle floored pick (#45)')
        from harness.rollstab.mint import cam_clean_screen, floor_probe
        # CLEAN (#56) is orthogonal to the settle, so a CLEAN off-floor park is unmintable: keep #45
        # -- default if CLEAN+floored, else the smallest-settle CLEAN+floored #44 alternate (#57).
        F = deg_to_s16(float(geo.get('aim_deg', geo['bisector_deg'])) % 360.0)
        cands = [F] + [(F + off) & 0xFFFF for off in (-8000, 8000, -16384, 16384)]
        floored_edge = max([float(k) for k, fv in st.get('floor', {}).items() if fv],
                           default=d2s + SETTLE_EST0)   # the floor stage's deepest FLOOR probe

        def _park_floored(park):
            """park is floored if within the probed floor edge, else one live floor probe."""
            if park <= floored_edge + 1e-9:
                return True
            fl = floor_probe(geo_abs, [park], base=base)
            st.setdefault('floor', {})[str(park)] = fl[park]
            _save_state(name, st)
            return fl[park]

        probes, chosen, clean_offfloor = [], None, []
        for i, target in enumerate(cands):
            v = cam_clean_screen(geo_abs, target_csangle=target, d2s=d2s,
                                 settle_est=SETTLE_EST0, base=base)
            probes.append((target, v))
            if not v['clean']:
                continue
            settle = max(0.0, (d2s + SETTLE_EST0) - v['rest_d2S'])   # park - rest = MEASURED settle
            park = d2s + settle
            if not _park_floored(park):
                clean_offfloor.append((target, park))
                continue
            cand = (target, v, settle, park)
            if i == 0:
                chosen = cand          # default fast-path: CLEAN + floored, accept (s70 intent)
                break
            if chosen is None or settle < chosen[2]:
                chosen = cand          # smallest-settle among CLEAN+floored alternates (#45)
        if chosen is None:
            if clean_offfloor:         # CLEAN but every park is off the floor (467/#43 class)
                t, pk = min(clean_offfloor, key=lambda x: x[1])
                return _fail('cam', 'every CLEAN target parks off-floor (nearest %d @ d2S %.0f, '
                             'floor edge ~%.0f) -- floor-blocked corridor (467 class); needs the '
                             'walk-stab tier or a shorter-settle technique' % (t, pk, floored_edge))
            t0, v0 = probes[0]
            fd = v0.get('first_drift')
            loc = ('f%d pos=(%.1f,%.1f)' % (fd['f'], fd['lx'], fd['lz'])) if fd else '(no frame)'
            return _fail('cam', 'every probed csangle is DIRTY (bumpCheck camera-wall push). '
                         'default target=%d first drift %s -- the corridor pushes the arm off a '
                         'wall; widen the aim or rule the corner out' % (t0, loc))
        target, v, settle, park = chosen
        st['cam'] = dict(target=target, rest_cs=v['rest_cs'], rest_d2S=v['rest_d2S'],
                         settle=settle, park=park, clean=True, max_dcs=v['max_dcs'],
                         nprobed=len(probes))
        _save_state(name, st)
        print('  CLEAN+FLOORED target=%d (rest_cs=%d rest_d2S=%.1f) settle=%.1f park=%.1f [%d probed]'
              % (target, v['rest_cs'], v['rest_d2S'], settle, park, len(probes)), flush=True)

    # --- 5. mint (mint_online at the screened target/settle; verify ON-LINE) ---------------
    if run['mint']:
        if 'cam' not in st:
            return _fail('mint', 'no cam-screen state (run from stage cam)')
        _banner('mint', '%s target_csangle=%d settle_est=%.1f'
                % (anchor, st['cam']['target'], st['cam']['settle']))
        from harness.rollstab.mint import mint_online
        mint_online(anchor, geo_abs, d2s=d2s, settle_est=st['cam']['settle'],
                    target_csangle=st['cam']['target'], base=base, max_iter=max_iter)
        import harness.rollstab.solver as SV
        for _c in (SV._BASE, SV._BASE_WALLED):
            for _k in [k for k in _c if k[0] == anchor]:
                del _c[_k]
        seam = _seam_for(geo, anchor)
        r0 = SV.run(anchor, [], dtm_seed=0, seam=seam)
        old = r0.get('old') if (r0 and r0.get('fired')) else None
        if old is None:
            return _fail('mint', 'baseline roll never fired (rest outside the ~580u envelope)')
        perp = seam.perp(old)
        st['mint'] = dict(baseline_old=list(old), perp=perp)
        _save_state(name, st)
        if abs(perp) > PERP_TOL:
            return _fail('mint', 'anchor off-line (baseline |old perp| %.3f > %.1f)'
                         % (abs(perp), PERP_TOL))
        print('  ON-LINE: baseline |old perp| %.3f' % abs(perp), flush=True)

    # --- 6. rest (the LIVE REST gate; abort on DIFF; writes the rest golden) ---------------
    if run['rest']:
        _banner('rest', 'live REST verification (one clean DTM, seed=0)')
        from harness.rollstab import rest as R
        seam = _seam_for(geo, anchor)
        rc = R.main(anchor, seam=seam, dtm_seed=0, golden=rest_golden, geo=geo_rel)
        st['rest'] = dict(bitexact=(rc == 0), golden=os.path.relpath(rest_golden, _rb))
        _save_state(name, st)
        if rc != 0:
            return _fail('rest', 'REST DIVERGED -- check the calib csangle column: a wobble '
                         'band means re-run the cam screen with more targets (ledger #44); '
                         'monotone creep means the settle (ledger #42)')

    # --- 7. dust (dust2d prebuild, outside the draw budget) --------------------------------
    if run['dust']:
        _banner('dust', 'dust2d prebuild (disk-cached)')
        from harness.rollstab.solver import _dust2d
        t0 = time.time()
        P, _A = _dust2d(_seam_for(geo, anchor))
        print('  %d exact dust points (%.0fs)' % (len(P), time.time() - t0), flush=True)

    # --- 8. solve (default draw, then documented families on a 0-hit) ----------------------
    if run['solve']:
        from harness.rollstab.solver import solve_focused
        seam = _seam_for(geo, anchor)
        hits, draws = [], st.get('draws', [])
        for fam in DRAW_FAMILIES:
            _banner('solve', 'solve_focused %s' % (fam or 'default'))
            hits = solve_focused(anchor, seam, dtm_seed=0, budget=budget, **fam)
            draws.append(dict(family=fam, hits=len(hits)))
            st['draws'] = draws
            _save_state(name, st)
            if hits:
                break
        if not hits:
            return _fail('solve', '0 wall-faithful hits over %d documented families -- an '
                         'honest lottery at this dust thinness (97m precedent); rerun stage '
                         'solve for more draws or pick a denser corner' % len(DRAW_FAMILIES))
        print('  %d wall-faithful hits (top margin %d)' % (len(hits), hits[0].get('margin', -1)),
              flush=True)

    # --- 9. ship (live 0-ULP clean-DTM delivery; writes the ship golden) -------------------
    if run['ship']:
        _banner('ship', 'deliver.ship hit=0 (clean DTM, seed=0)')
        from harness.rollstab.deliver import ship
        rc = ship(0, geo=geo_rel, golden=ship_golden)
        st['ship'] = dict(ok=(rc == 0), golden=os.path.relpath(ship_golden, _rb))
        _save_state(name, st)
        if rc != 0:
            return _fail('ship', 'live delivery failed -- do NOT tweak inputs by guesswork; '
                         'diff per-frame (SESSION_PROMPT rule)')

    # --- 10. test (per-seam scaffold; never overwrite a locked test) -----------------------
    if run['test']:
        _banner('test', os.path.relpath(test_path, _rb))
        if os.path.exists(test_path):
            print('  exists -- locked tests are immutable, leaving it untouched', flush=True)
        else:
            open(test_path, 'w').write(_test_scaffold(name, anchor, geo))
            print('  wrote scaffold (run pytest to gate)', flush=True)

    if stop == 'test':
        _banner('DONE', '%s delivered; review _generated/novel_%s.json, run pytest, update '
                'the README ## Status' % (name, name))
    else:
        _banner('DONE', 'stages %s..%s green (partial run)' % (start, stop))
    return 0


def _test_scaffold(name, anchor, geo):
    hdr = ('"""The NOVEL %s corner S=(%.4f, %.4f) (interior %.2f, walls %d x %d) -- delivered\n'
           'end-to-end by the ONE-SHOT `harness.rollstab.novel_deliver` pipeline.\n\n'
           'Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard\n'
           'rule). Scaffold generated by novel_deliver; per-stage record in\n'
           '`_generated/novel_%s.json`.\n"""\n') % (
        name, geo['S'][0], geo['S'][2], geo.get('interior', -1.0),
        geo['wallA']['poly'], geo['wallB']['poly'], name)
    body = '''import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', '{name}_rest_golden.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / {name} golden unavailable")

ANCHOR = '{anchor}'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_{name}_rest_bitexact():
    """The pan-minted anchor is REST BIT-EXACT (0 ULP) from rest through the walk approach,
    delivered C-down every frame + seed=0. Index-aligned vs the live golden."""
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    stream = ([tuple(golden['straight'])] * golden['NPREF']
              + [tuple(golden['aim'])] * golden['NCRUISE'])
    s = C.rest_state(ANCHOR, dtm_seed=0)
    frames = golden['frames']
    matched, bad = 0, []
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy)
        if k >= len(frames):
            break
        lf = frames[k]
        st = s._foot.st
        matched += 1
        if not (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])
                and _bits(st.fc0.frame) == _bits(lf['d_frame'])
                and _bits(st.fc1.frame) == _bits(lf['w_frame'])
                and _bits(s._foot.prev_f312) == _bits(lf['m359C'])):
            bad.append(k)
    assert matched >= 24, "too few rows matched (%d)" % matched
    assert not bad, "{name} from-rest diverged at rows %s" % bad


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', '{name}_roll_ship_golden.json')


@pytest.mark.skipif(not os.path.exists(_SHIP), reason="{name} ship golden unavailable")
def test_{name}_clip_delivered():
    """The {name}-corner roll-stab clip, found by the generalized `solver.solve_focused` and
    delivered LIVE 0-ULP via a clean DTM at seed=0 (novel_deliver one-shot).

    The from-rest sim (rest_state on the shipped hit's exact stream) reproduces the live CUT_F
    entry old/new BIT-FOR-BIT (0 ULP). Live-captured golden, never edited to make the sim pass."""
    from harness.rollstab.deliver import replay
    from tww_sim.land.land import CUT_F, CUT_A
    g = json.load(open(_SHIP))
    assert g['anchor'] == ANCHOR and g.get('dtm_seed') == 0
    assert g['threads'] and g['behindA'] and g['behindB'], "golden did not confirm a live clip"

    stream = [tuple(fr) for fr in g['stream']]
    rows = replay(ANCHOR, stream, dtm_seed=0)
    ci = next((i for i, rr in enumerate(rows) if rr[0] in (CUT_F, CUT_A)), None)
    assert ci and ci > 0, "sim CUT never fired"
    sim_old, sim_new = (rows[ci - 1][1], rows[ci - 1][2]), (rows[ci][1], rows[ci][2])
    for nm, s, l in (('old', sim_old, g['live_old']), ('new', sim_new, g['live_new'])):
        assert _bits(s[0]) == _bits(l[0]) and _bits(s[1]) == _bits(l[1]), \\
            "%s not 0-ULP: sim=%s live=%s" % (nm, s, l)

    lc = g['live_cut_frame']
    assert g['live'][lc]['proc'] == (CUT_F & 0xFF), "live cut proc not CUT_F"
'''.format(name=name, anchor=anchor)
    return hdr + body


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    if 'wallA' not in o or 'wallB' not in o:
        print(__doc__)
        sys.exit(2)
    sys.exit(deliver_novel(int(o['wallA']), int(o['wallB']), name=o.get('name'),
                           aim_deg=(float(o['aim_deg']) if 'aim_deg' in o else None),
                           d2s=float(o.get('d2s', 580.0)), budget=float(o.get('budget', 110.0)),
                           start=o.get('start', 'geo'), stop=o.get('stop', 'test'),
                           mesh=o.get('mesh'), prefix=o.get('prefix', 'kaze_r11'),
                           base=o.get('base', KAZE_BASE),
                           max_iter=int(o.get('max_iter', 3))))
