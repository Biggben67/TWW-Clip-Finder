"""Is a seam roll-clippable, and AT WHICH AIM? -- a full-aim-circle f32 feasibility probe.

WHY THIS EXISTS (session 51): session 50 ruled the 97-deg corner S=(13539.24,493.36) "NOT
roll-clippable at any displacement" using tools that swept aim only `dir +-15deg` around the
INTO-CORNER bisector. That was WRONG: the seam IS clippable, its genuine gap sitting at a ~90-deg
GRAZING aim (~41deg off the bisector) that no sweep reached (dead-end ledger, "A sharp corner's
clippable aim can be FAR off the bisector"). The lesson: a feasibility check MUST sweep the FULL
aim circle at TRUE f32 perp resolution -- a coarse perp step reads 0 even for the PROVEN/mirror
seams (the genuine acceptance is single ~0.001u f32 columns), and a bisector-only aim misses
off-bisector gaps.

This probe scans `SeamGeo.pred_genuine` (the EXACT sim cut acceptance, bit-identical to
LandState.enter_cut) over (along, perp) at each facing across the whole circle, so it answers
both "is this seam clippable at all?" and "at what aim does its razor sit?" -- the aim to pass as
`SeamGeo(aim_deg=)` and to mint an anchor toward. It is the correct front-end to a novel-seam pick
(run it BEFORE minting; a nonzero genuine count at some aim == a real, if precise, target).

    python -m harness.rollstab.seam_feasibility geo=fixtures/kaze_r11_seam_mirror_geo.json
    python -m harness.rollstab.seam_feasibility geo=<fixture> anchor=<any kaze anchor> [fstep=2048]
"""
import os, sys, json, math, time
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.core.fp import f32 as _f
from harness.rollstab.seamgeo import SeamGeo
from harness.rollstab.geometry import load_seed


def scan_aim(seam, F, perp_w=2.0, pstep=0.001, astep=0.3, along_frac=(0.5, 1.05), speedf=None,
             min_clearance=None, travel=None):
    """Genuine f32 dust for a roll-stab firing its CUT at facing `F`. Places `old` at
    `S - along*dir(F) + perp*perp(F)` over the reach band and tests the EXACT `pred_genuine`
    (== the sim cut). f32 resolution in perp is LOAD-BEARING (coarse steps miss the ~0.001u
    columns). Returns (count, [(along, perp, old_x, old_z), ...]).

    `min_clearance` (session 72): if set, keep only dust whose `old` is > this far from the incident
    walls (`SeamGeo.wall_clearance`) -- the WALK-reachable subset, since a walk-stab approach whose
    cylinder is inside Link's ~35u WallCorrect radius brakes on the wall (the wall-faithful reject).
    This makes the shared detector answer 'where is the WALK-reachable dust?', not just the
    geometrically-genuine dust ([[oneshot-no-manual-tweaking]] -- one detector, enhanced, not a copy)."""
    Sx, Sz = seam.S
    reach = seam.reach_at(speedf)
    r = (F & 0xFFFF) / 65536.0 * 2 * math.pi
    dx, dz = math.sin(r), math.cos(r)
    px, pz = -dz, dx
    hits = []
    a = reach * along_frac[0]
    while a <= reach * along_frac[1]:
        p = -perp_w
        while p <= perp_w:
            ox, oz = _f(Sx - a * dx + p * px), _f(Sz - a * dz + p * pz)
            if seam.pred_genuine(
                    (ox, oz), facing=(F & 0xFFFF), speedf=speedf, travel=travel):
                if min_clearance is None or seam.wall_clearance(ox, oz) > min_clearance:
                    hits.append((a, p, float(ox), float(oz)))
            p += pstep
        a += astep
    return len(hits), hits


def _angle_in_range(angle, lo, hi):
    angle, lo, hi = angle & 0xFFFF, lo & 0xFFFF, hi & 0xFFFF
    return lo <= angle <= hi if lo <= hi else angle >= lo or angle <= hi


def _angle_grid(lo, hi, max_step):
    """Sample a circular range without dropping established full-circle grid facings."""
    lo, hi = lo & 0xFFFF, hi & 0xFFFF
    width = (hi - lo) & 0xFFFF
    if width == 0:
        return [lo]
    # Keep roughly full-circle scan density even for a narrow requested range. Also retain every
    # max_step-aligned facing: f32 dust can alias at one facing and disappear at its neighbours.
    step = min(max(1, int(max_step)), max(1, width // 32))
    values = {((lo + offset) & 0xFFFF) for offset in range(0, width + 1, step)}
    values.add(hi)
    values.update(
        facing for facing in range(0, 65536, max(1, int(max_step)))
        if _angle_in_range(facing, lo, hi)
    )
    return sorted(values, key=lambda facing: (facing - lo) & 0xFFFF)


def post_clip_depth(seam, facing, hit, speedf=17.0, travel=None):
    """Signed forward distance of the CUT endpoint beyond the seam vertex.

    Positive values are past the seam in the slash direction.  This is the useful stability margin
    for an OOB landing; old-position wall clearance alone favors shallow clips near maximum reach.
    """
    old = (float(hit[2]), float(hit[3]))
    new = seam.cut_new(old, facing=facing, speedf=speedf, travel=travel)
    radians = (int(facing) & 0xFFFF) / 65536.0 * 2.0 * math.pi
    return ((new[0] - seam.S[0]) * math.sin(radians)
            + (new[1] - seam.S[1]) * math.cos(radians))


def cut_tail_outcome(seam, facing, hit, speedf=17.0, walls=None, travel=None):
    """Model CUT_F entry and its first following frame, including WallCorrect."""
    from tww_sim.land.constants import MOVE
    from tww_sim.land.land import LandState

    old = (float(hit[2]), float(hit[3])) if len(hit) >= 4 else tuple(hit)
    state = LandState(
        pos_x=old[0], pos_z=old[1], pos_y=seam.LINK_Y,
        facing=int(facing) & 0xFFFF,
        travel=int(facing if travel is None else travel) & 0xFFFF,
        state=MOVE, nspeed=speedf, speedF=speedf, use_anim=True,
        native=False, foot_native=False, sword_drawn=True,
        walls=walls if walls is not None else seam.TRIS,
    )
    state.enter_cut()
    entry = (state.pos_x, state.pos_z)
    state.step(128, 254, csx=128, csy=128)
    following = (state.pos_x, state.pos_z)
    return {
        "entry": entry,
        "next": following,
        "next_oob": not seam.in_front(seam.p32(*following)),
        "wall_hit": bool(state.wall_hit),
        "line_hit": bool(state.line_hit),
        "state": int(state.state),
        "speedF": float(state.speedF),
        "animation_frame": float(state.cut_frame),
    }


def best_walk_aim(seam, speedf=17.0, min_clearance=35.0, fstep=1024, budget=60.0,
                  perp_w=1.5, pstep=0.001, astep=0.3, verbose=False,
                  angle_lo=0, angle_hi=65535, prefer_depth=False,
                  prefer_stable=False, return_ranked=False):
    """Pick the CUT facing whose genuine dust is richest -- the self-adaptive target-finder a
    walk-stab solver aims at (session 72; replaces walkstab's redundant perp-to-S auto-graze, which
    found rays threading S where NO genuine old exists). Ranks facings by TOTAL genuine dust (stable
    at f32 resolution -- the clearance-filtered subset aliases badly for ranking because the dust
    hugs the wall at clr~35), and reports the WALK-reachable (clearance > `min_clearance`) subset of
    the winner separately -- clearance is a STEERING constraint (the wall-faithful gate), not a
    ranking one. With `prefer_depth`, rank by the deepest wall-clear post-seam endpoint before dust
    density; this is used by the GUI to avoid clips that barely cross and pop back in bounds.
    Returns (best_F, total_count, safe_count, [safe olds...]) or (None,0,0,[]). DRY front-end: pure
    `scan_aim` reuse."""
    import time
    t0 = time.time()
    best = (None, 0, [], [])
    best_rank = None
    ranked = []
    for F in _angle_grid(angle_lo, angle_hi, fstep):
        n, hits = scan_aim(seam, F, speedf=speedf, perp_w=perp_w, pstep=pstep, astep=astep)
        safe = [h for h in hits if seam.wall_clearance(h[2], h[3]) > min_clearance]
        # Dense geometric dust inside Link's wall cylinder is not a usable walking runway.
        deepest = max(
            (post_clip_depth(seam, F, hit, speedf=speedf) for hit in safe),
            default=float("-inf"),
        )
        stable_hits = (
            [hit for hit in safe
             if cut_tail_outcome(seam, F, hit, speedf=speedf)["next_oob"]]
            if prefer_stable else []
        )
        persistent = bool(stable_hits)
        ranked_depth = max(
            (post_clip_depth(seam, F, hit, speedf=speedf) for hit in stable_hits),
            default=deepest,
        )
        rank = ((bool(safe), persistent, ranked_depth, n, len(safe))
                if prefer_depth and prefer_stable
                else (bool(safe), deepest, n, len(safe)) if prefer_depth
                else (bool(safe), n, len(safe)))
        if safe:
            ranked.append((rank, (F, n, len(safe), safe)))
        if best_rank is None or rank > best_rank:
            best = (F, n, hits, safe)
            best_rank = rank
        if verbose and n:
            print('  aim F=%5d (%.1fdeg): genuine=%d wall-clear=%d'
                  % (F, F / 65536 * 360, n, len(safe)), flush=True)
        # A cutoff must not turn an unsafe geometric witness into a false physical answer.
        if time.time() - t0 > budget and best[3]:
            if verbose:
                print('  ...budget cutoff at F=%d' % F, flush=True)
            break
    if best[0] is None:
        return [] if return_ranked else (None, 0, 0, [])
    if return_ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _rank, candidate in ranked]
    return (best[0], best[1], len(best[3]), best[3])




def feasible_aims(seam, fstep=2048, budget=140.0, verbose=True, **scan_kw):
    """Sweep the FULL aim circle; return the facings whose roll-stab has genuine dust, most first.
    A coarse facing step FLAGS candidate aims (the razor spans a few hundred s16 in aim); refine a
    flagged aim with `scan_aim` at a finer facing/perp grid to characterize + locate its `old`."""
    t0 = time.time()
    found = []
    for F in range(0, 65536, fstep):
        n, _ = scan_aim(seam, F, **scan_kw)
        if n:
            found.append((F, n))
            if verbose:
                print('  aim F=%5d (%.1fdeg): genuine=%d' % (F, F / 65536 * 360, n), flush=True)
        if time.time() - t0 > budget:
            if verbose:
                print('  ...budget cutoff at F=%d' % F, flush=True)
            break
    found.sort(key=lambda x: -x[1])
    if verbose:
        if found:
            print('CLIPPABLE at %d aim(s); best F=%d (%.1fdeg, genuine=%d). Derived bisector F=%d.'
                  % (len(found), found[0][0], found[0][0] / 65536 * 360, found[0][1], seam.F),
                  flush=True)
        else:
            print('NO genuine dust at any swept aim (fstep=%d) -- likely truly infeasible; '
                  'try a finer fstep before concluding.' % fstep, flush=True)
    return found


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    anchor = o.get('anchor', 'kaze_r11_rollstab_mirror@twwgz')
    cs = load_seed(anchor)['csangle'] & 0xFFFF
    seam = SeamGeo(json.load(open(o['geo'])), cs)
    print('seam interior=%.2f bisector-derived F=%d reach=%.3f'
          % (seam.geo.get('interior', -1), seam.F, seam.reach), flush=True)
    aims = feasible_aims(seam, fstep=int(o.get('fstep', 2048)))
    if aims:
        Fb = aims[0][0]
        n, hits = scan_aim(seam, Fb, pstep=0.0005, astep=0.1)
        print('refine F=%d: %d f32 points' % (Fb, n))
        for a, p, ox, oz in hits[:8]:
            print('   along=%.2f perp=%+.4f old=(%.5f,%.5f) d2S=%.2f'
                  % (a, p, ox, oz, math.hypot(ox - seam.S[0], oz - seam.S[1])))
        # AUTHORITATIVE reachability (SeamGeo defers to the locator core on the seam's own walls; no
        # nearest-wall heuristic / disp-floor proxy): None == clippable but not reachable by a free roll.
        clip = seam.roll_reachable()
        if clip is None:
            print('REACHABILITY: NOT roll-reachable -- no WallCorrect-standable old clips this seam '
                  '(the genuine dust hugs a wall, inside the ~35u roll hold; e.g. the 97-deg corner). '
                  'Pick a seam whose dust sits in the OPEN mouth, or use a push-steer technique.')
        else:
            print('REACHABILITY: roll-reachable -- a standable old clips (disp<=%.2f, deep-first upper '
                  'bound; confirm pred_genuine at a search_band old for the precise roll-stab reach).'
                  % clip['disp'])
