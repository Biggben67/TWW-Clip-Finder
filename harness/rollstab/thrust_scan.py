"""Centralized THRUST-CLIP scanner: given an initial state (anchor seed) + a target seam, DECIDE
whether to WALK-stab, ROLL-stab, or report it can't, then dispatch the matching solver.

This is the front-end that unifies the two existing single-seam solvers -- it does NOT rewrite them:
  * WALK -> `harness.rollstab.walkstab.solve_focused` (the K=3-crawl dust search; session 32).
  * ROLL -> `harness.rollstab.solver.search`.
The Tetra push-aside clip (needs an actor push) is OUT OF SCOPE and reported, never dispatched.

THE DECISION (Dereck's steer, 2026-07-13):
  * Displacement FLOOR from the seam interior angle: `floor = 35 / sin(interior/2)`
    (`harness.collision.seam_scan.disp_floor`). `old` is a settled WallCorrect fixed point, so it
    clears both r=35 wall cylinders -- on the bisector that puts it `floor` from S, and since `new`
    is on the far side of S the one-frame displacement can NEVER beat `floor`.
  * REACH per technique (KB mechanics/walk-stab.md): a capped WALK (speedF 17) thrusts
    `17 + 23.220 (CUT_F root) = 40.220`; a ROLL (speedF 26) reaches `49.220`. So:
        floor <= 40.220  -> WALK geometrically capable
        40.220 < floor <= 49.220 -> ROLL required
        floor > 49.220 -> needs an actor push (OUT OF SCOPE; reported as INFEASIBLE/push).
  * FEWEST FRAMES wins (Dereck): a walk is always fewer frames than a roll (roll = walk-to-cap ~5f +
    the roll ~9-16f), so prefer WALK when it FITS THE SPACE, else ROLL when it fits, else infeasible.
  * FEASIBILITY-GATE on RUN-UP SPACE (load-bearing): simulate the straight approach from the anchor
    toward S (sword-aware `rest.rest_state`, C-down camera pin, per-frame re-aim at S) and read
    speedF-vs-distance. A technique fits iff its required speedF (WALK: `floor - 23.220`; ROLL: the
    17.0 cap) is BUILT while `old` is still at `d2S >= floor` (room before the seam). If neither fits
    the space, report INFEASIBLE/space with the reason -- never a crash.

Grounded: reach constants + disp-floor tier table in `knowledge/mechanics/walk-stab.md`; the approach
model is the same bit-exact-from-rest `rest.rest_state` the solvers seed from (no calibration).
"""
import os, sys, math, json

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.land.plan_land import stick_for_bearing
from harness.rollstab import rest as C
from harness.collision.seam_scan import disp_floor, interior_angle_deg

# --- reach tiers (KB mechanics/walk-stab.md; do not restate the numbers elsewhere) ---
CUT_ROOT = 23.220               # the CUT_F joint-0 root translate added to speedF on the entry frame
WALK_CAP_SPEEDF = 17.0          # walk speedF cap
ROLL_SPEEDF = 26.0              # roll nspeed (from a capped walk) -- informational
WALK_REACH = WALK_CAP_SPEEDF + CUT_ROOT      # 40.220 -- a capped walk-stab's one-frame displacement
ROLL_REACH = 49.2202            # a roll-stab's one-frame displacement (geometry.LUNGE magnitude)
_EPS = 1e-4
CDOWN = 0                       # substickY=0 = C-down = the free-cam pin (matches the walk-stab driver)

# tiers keyed off the disp floor (geometry only -- no anchor needed)
TIER_WALK, TIER_ROLL, TIER_PUSH = 'WALK', 'ROLL', 'PUSH'


def seam_floor(seam):
    """Displacement floor for a seam dict. Uses a stored `floor`/`interior` if present, else derives
    the interior from the two seam-wall normals (`nA`/`nB`)."""
    if seam.get('floor') is not None:
        return float(seam['floor'])
    interior = seam.get('interior')
    if interior is None:
        interior = interior_angle_deg(seam['nA'], seam['nB'])
    return disp_floor(interior)


def seam_interior(seam):
    if seam.get('interior') is not None:
        return float(seam['interior'])
    return interior_angle_deg(seam['nA'], seam['nB'])


def geometric_tier(seam):
    """The technique a seam's displacement floor ALLOWS, ignoring run-up space (geometry only):
    WALK (floor <= 40.220), ROLL (<= 49.220), or PUSH (needs an actor push, out of scope)."""
    floor = seam_floor(seam)
    if floor <= WALK_REACH + _EPS:
        return TIER_WALK
    if floor <= ROLL_REACH + _EPS:
        return TIER_ROLL
    return TIER_PUSH


def _sxz(seam):
    """(x, z) of the seam vertex -- S may be stored as (x, y, z) or (x, z)."""
    s = seam['S']
    return (float(s[0]), float(s[-1]))


def approach_profile(anchor, Sxz, nmax=45, seed_state=None):
    """Simulate the STRAIGHT approach from the anchor toward S and return speedF-vs-distance.

    Walks the from-rest sim (`rest.rest_state`, the same seed the solvers use -- sword-aware, no
    calibration) holding the C-down camera pin and re-aiming the full-mag stick at S every frame
    (pursuit, so it heads to S regardless of the frozen camera). Returns a list of
    ``(k, d2S, speedF, facing)`` from frame 0 (rest) until Link passes S or ``nmax`` frames.
    `seed_state` lets a caller pass a pre-built/cloned rest state (e.g. a synthetic close-start)."""
    s = seed_state.clone() if seed_state is not None else C.rest_state(anchor)
    out = []
    prev_d = None
    for k in range(nmax):
        d2S = math.hypot(Sxz[0] - s.pos_x, Sxz[1] - s.pos_z)
        out.append((k, d2S, s.speedF, s.facing & 0xFFFF))
        # stop once we are essentially on top of S (d2S turned back up = walked past it)
        if prev_d is not None and d2S > prev_d + 1.0:
            break
        prev_d = d2S
        br = int((math.atan2(Sxz[0] - s.pos_x, Sxz[1] - s.pos_z) % (2 * math.pi))
                 / (2 * math.pi) * 65536)
        stk = stick_for_bearing(br, s.csangle, 1.0)
        s.step(stk[0], stk[1], csx=128, csy=CDOWN)
    return out


def _build_d2S(profile, req_speedF):
    """d2S at the FIRST frame speedF reaches `req_speedF` (the run-up point), or None if never."""
    for (k, d2S, sp, _f) in profile:
        if sp >= req_speedF - _EPS:
            return d2S
    return None


def decide(anchor, seam, seed_state=None, verbose=False):
    """Decide WALK / ROLL / INFEASIBLE for one (anchor, seam) pair, gated on run-up space.

    Returns a verdict dict:
      technique : 'WALK' | 'ROLL' | None
      feasible  : bool
      reason    : 'walk' | 'roll' | 'push' (floor too steep) | 'space' (no run-up)
      interior, floor, tier, req_speedF, build_d2S (d2S when req speedF is built), min_d2S, S
    """
    interior = seam_interior(seam)
    floor = seam_floor(seam)
    tier = geometric_tier(seam)
    Sxz = _sxz(seam)
    v = dict(technique=None, feasible=False, interior=round(interior, 3),
             floor=round(floor, 3), tier=tier, S=Sxz, req_speedF=None,
             build_d2S=None, min_d2S=None)

    if tier == TIER_PUSH:
        v['reason'] = 'push'
        if verbose:
            print('  INFEASIBLE(push): floor %.3f > roll reach %.3f -- needs an actor push (out of '
                  'scope)' % (floor, ROLL_REACH))
        return v

    profile = approach_profile(anchor, Sxz, seed_state=seed_state)
    v['min_d2S'] = round(min(p[1] for p in profile), 3)

    # fewest frames first: WALK before ROLL. Only techniques the floor geometrically allows.
    order = ([TIER_WALK] if floor <= WALK_REACH + _EPS else []) + [TIER_ROLL]
    for tech in order:
        req = (floor - CUT_ROOT) if tech == TIER_WALK else WALK_CAP_SPEEDF
        reach = WALK_REACH if tech == TIER_WALK else ROLL_REACH
        build = _build_d2S(profile, req)
        # FITS iff the required speedF is built while `old` is still at d2S >= floor. Once built, Link
        # approaches monotonically (wall sits at ~floor), so he sweeps [floor, reach] -- no upper gate.
        fits = build is not None and build >= floor - _EPS
        if verbose:
            print('  %s: req speedF %.2f built at d2S=%s (floor %.3f, reach %.3f) -> %s'
                  % (tech, req, ('%.2f' % build) if build is not None else 'never', floor, reach,
                     'FITS' if fits else 'no space'))
        if fits:
            v.update(technique=tech, feasible=True, reason=tech.lower(),
                     req_speedF=round(req, 3), build_d2S=round(build, 3))
            return v

    v['reason'] = 'space'
    if verbose:
        print('  INFEASIBLE(space): floor %.3f is reachable (tier %s) but the anchor lacks the run-up '
              'to build the required speedF before the seam' % (floor, tier))
    return v


# --- known-seam dispatch (the solvers are each tuned to ONE kaze seam; do not rewrite them) ------
_KAZE_WALK_S = (9030.955078125, 1385.858)      # walkstab.SEAM (polys 803 x 802)
_KAZE_ROLL_S = (9069.904296875, 259.1986083984375)  # kaze_r11_geo.json roll seam
_MATCH_TOL = 2.0


def _matches(Sxz, known):
    return math.hypot(Sxz[0] - known[0], Sxz[1] - known[1]) < _MATCH_TOL


def scan(anchor, seam, solve=False, deliver=False, verbose=True):
    """DECIDE then (optionally) DISPATCH. Prints the verdict; on `solve`/`deliver` and a recognized
    seam, calls the matching tuned solver. For an unrecognized seam it reports the DECISION only
    (the per-seam solver generalization -- settled facing + crawl count -- is a follow-up; the
    solvers are hardcoded to their kaze seam today)."""
    v = decide(anchor, seam, verbose=verbose)
    Sxz = v['S']
    if verbose:
        head = ('%s' % v['technique']) if v['feasible'] else ('INFEASIBLE(%s)' % v['reason'])
        print('VERDICT %s  seam S=(%.3f,%.3f) interior=%.2f floor=%.3f (tier %s)'
              % (head, Sxz[0], Sxz[1], v['interior'], v['floor'], v['tier']))
    if not (solve or deliver) or not v['feasible']:
        return v

    if v['technique'] == TIER_WALK and _matches(Sxz, _KAZE_WALK_S):
        from harness.rollstab import walkstab as W
        hits = W.solve_focused(verbose=verbose)
        v['hits'] = len(hits)
        if deliver and hits:
            v['deliver_rc'] = W.deliver(verbose=verbose)
    elif v['technique'] == TIER_ROLL and _matches(Sxz, _KAZE_ROLL_S):
        from harness.rollstab import solver as R
        hits = R.search(anchor, do_drill=deliver)
        v['hits'] = len(hits)
    elif verbose:
        print('  (no tuned solver for this seam yet -- decision only; solver generalization is a '
              'follow-up. The kaze WALK/ROLL solvers are seam-hardcoded.)')
    return v


# --- convenience seam builders for the known kaze seams (regression + demo) ----------------------
def kaze_walk_seam():
    """The kaze r11 slot-3 WALK seam (polys 803 x 802) as a scanner seam dict."""
    M = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')))
    by = {p['poly']: p for p in M['polys']}
    nA, nB = by[803]['n'], by[802]['n']
    return dict(S=(_KAZE_WALK_S[0], -6534.329, _KAZE_WALK_S[1]),
                interior=interior_angle_deg(nA, nB), polys=[802, 803], nA=nA, nB=nB)


def kaze_roll_seam():
    """The kaze r11 ROLL seam from `fixtures/kaze_r11_geo.json`."""
    g = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json')))
    return dict(S=g['S'], interior=g.get('interior'), floor=g.get('floor'),
                nA=g['wallA']['n'], nB=g['wallB']['n'])


def scan_region_file(path, anchor=None, verbose=True):
    """Offline room scan: enumerate every seam in a dumped region and print its geometric tier +
    floor (the auto-enumeration the handoff asked for). If `anchor` is given, add the run-up
    feasibility decision per seam. `path` = a `seam_scan.dump_region_tris` JSON."""
    from harness.collision.seam_scan import load_region_tris, enumerate_seams
    region, stage = load_region_tris(path)
    xs = [v[0] for t in region for v in t['v']]
    ys = [v[1] for t in region for v in t['v']]
    zs = [v[2] for t in region for v in t['v']]
    box = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    seams = enumerate_seams(region, box)
    if verbose:
        print('stage=%s: %d seams (tier = disp-floor bucket):' % (stage, len(seams)))
    rows = []
    for s in seams:
        tier = geometric_tier(s)
        row = dict(S=_sxz(s), interior=s['interior'], floor=s['floor'], tier=tier)
        if anchor is not None:
            v = decide(anchor, s)
            row['verdict'] = v['technique'] if v['feasible'] else 'INFEASIBLE(%s)' % v['reason']
        rows.append(row)
        if verbose:
            extra = ('  %s' % row.get('verdict', '')) if anchor else ''
            print('  S=(%.2f,%.2f) interior=%.2f floor=%.3f  %-4s%s'
                  % (row['S'][0], row['S'][1], s['interior'], s['floor'], tier, extra))
    return rows


def main(argv):
    which = argv[0] if argv else 'walk'
    anchor = next((a.split('=')[1] for a in argv if a.startswith('anchor=')), None)
    do_solve = 'solve' in argv
    do_deliver = 'deliver' in argv
    if which == 'walk':
        scan(anchor or 'kaze_r11_walkstab@twwgz', kaze_walk_seam(),
             solve=do_solve, deliver=do_deliver)
    elif which == 'roll':
        scan(anchor or 'kaze_r11_rollstab_idle13@twwgz', kaze_roll_seam(),
             solve=do_solve, deliver=do_deliver)
    elif which == 'region':
        path = next((a.split('=')[1] for a in argv if a.startswith('file=')), None)
        scan_region_file(path, anchor=anchor)
    else:
        print('usage: python -m harness.rollstab.thrust_scan [walk|roll|region] '
              '[anchor=<a>] [file=<region.json>] [solve] [deliver]')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
