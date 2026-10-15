"""From-rest dust solver: search the input knobs for a genuine+clear roll-stab clip.

Run shape (from the anchor's REST state, harness.rollstab.rest.rest_state -- bit-exact from
row 0, no live calibration):
    [start-crawl sticks (rows 0..k-1)] + [cruise on the F aim stick, with MOVES placed lead
    frames before the A press] + [A] + [15 aim] + [B edge] + [aim tail]

Knobs (all sticks are dtm_stick-calibrated -- sim ONLY the bytes dtm_make will deliver):
  * start  -- the 1D-approach START CRAWL: up to START_KMAX partial-magnitude sticks (msd
              0.52..0.889 + full, aimed at F) in the FIRST rows, while speed is LOW -- each
              partial shifts the whole downstream trajectory along-track by a fine quantum
              (the dense fill that made the freeze planner's 0-ULP targeting work);
  * moves  -- (lead, stick) 1-frame partial-magnitude "fines" and (lead, stick, dur) bearing
              ARCS (gross lateral shift of the roll line);
  * A_proj -- the press threshold (z phase, 17u grid).

Acceptance is EXACT per candidate, never a fitted residual: genuine_clip on the run's real
old->new + approach_clear (no roll segment fires the wall) + speedF==17 at the A press (a sub-cap
walk gives a sub-26 roll and a shrunken lunge -- never clips) + facing==F.

    python -m harness.rollstab.solver anchor=<anchor>        # catalog + ranked search
    python -m harness.rollstab.solver anchor=<anchor> drill  # + iterative-deepening drill

Hits -> _generated/rollstab_hits.json (ship with harness.rollstab.deliver).
"""
import bisect, os, sys, json, math, time
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.land.land import FRONT_ROLL, CUT_F, CUT_A
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.core.fp import f32 as _F
from harness.rollstab.geometry import SEAM as _KAZE_SEAM, load_seed
from harness.rollstab import rest as C

HITS_PATH = os.path.join(_rb, '_generated', 'rollstab_hits.json')
START_KMAX = 3                 # start-crawl window (K<=3: low-speed micro-moves, 1D approach)
FAST_POSE = True               # lazy cruise-pose defer in run()/wall_faithful (bit-exact; see
#                                FootSpeedF._drain_skipped). Off only for the test_solver_fastpose A/B.
_BASE = {}
_BASE_WALLED = {}


def base(anchor, dtm_seed=1):
    """A cloned from-rest sim seeded for the make_dtm `dtm_seed` the stream will be DELIVERED with.
    The roll-stab clip ships with seed=0 (the make_dtm delivery fix, session 43) so it solves on the
    seed-0 model (noops=2); legacy callers keep seed=1 (byte-identical)."""
    key = (anchor, dtm_seed)
    if key not in _BASE:
        _BASE[key] = C.rest_state(anchor, dtm_seed=dtm_seed)
    return _BASE[key].clone()


def walled_base(anchor, seam, dtm_seed=1):
    """A cloned from-rest sim with the seam's wall tris in the stepper (Phase W CrrPos), so the roll
    approach BRAKES exactly as live does. Used by `wall_faithful` to decide reachability by real
    physics rather than a typed-in `old_z` band (Dereck's session-49 call)."""
    key = (anchor, dtm_seed, id(seam))
    if key not in _BASE_WALLED:
        _BASE_WALLED[key] = C.rest_state(anchor, walls=seam.TRIS, dtm_seed=dtm_seed)
    return _BASE_WALLED[key].clone()


def wall_faithful(anchor, stream, old_ref, seam, dtm_seed=1):
    """PHYSICS reachability guard (dead-end #3): replay the candidate's exact recorded `stream`
    through a WALLED rest_state; the candidate `old` is genuinely REACHABLE iff the roll reaches it
    with NO wall stopping the approach first. Returns True/False.

    This replaces the kaze-hardcoded `ZLO/ZHI` old_z band: that band was a proxy for exactly this
    check (rejecting an `old` the wall-LESS roll overshot into -- the session-4 artifact). Deciding
    it by the actual walled sim is per-seam-general and needs no typed boundary. A candidate is
    rejected if any frame before the CUT flags `wall_hit`, or if the walled `old` differs from the
    wall-less `old` (the wall subtly diverted the approach)."""
    s = walled_base(anchor, seam, dtm_seed=dtm_seed)
    if FAST_POSE and s._foot is not None:
        s._foot.skip_cruise_pose = True    # lazy cruise-pose defer (bit-exact; drains on any consumer)
    rows = []
    hit_before_cut = False
    cut_i = None
    for (sx, sy, btn) in stream:
        s.step(sx, sy, buttons=btn)
        st = s.state & 0xFF
        if cut_i is None and st in (CUT_F, CUT_A):
            cut_i = len(rows)                     # index of the CUT row (old is the row before)
        if cut_i is None and getattr(s, 'wall_hit', False):
            hit_before_cut = True
        rows.append((st, s.pos_x, s.pos_z))
    if cut_i is None or cut_i == 0 or hit_before_cut:
        return False
    from tww_sim.core.fp import f32 as _f
    wold = (rows[cut_i - 1][1], rows[cut_i - 1][2])
    return _f(wold[0]) == _f(old_ref[0]) and _f(wold[1]) == _f(old_ref[1])


def run(anchor, moves, A_proj=-506.0, tail=8, start=(), draw_at=None, dtm_seed=1, seam=None,
        cross_hint=None):
    """One exact run from REST. `start` = sticks for stream rows 0..len-1 (the acceleration
    micro-crawl; the entry acts them with the 2-frame delay). `moves` = [(lead, stick[, dur]),
    ...] placed lead frames before the A press (fixpoint placement: the press frame is
    threshold-derived, so placement iterates to a fixed point). `draw_at` (session 35, sheathed
    roll path): the approach row index to feed a single B rising edge (the mid-walk sword
    pull-out). With `rest_state`'s model_draw ON (auto for a sheathed anchor), the sword draw
    completes DRAW_DELAY acted-frames later and sets `sword_drawn` before the A press, so the
    roll routes to a CUT. draw_at MUST land before the A press with margin (the draw + rebuild to
    cap in the sword set). Returns an info dict (old/new/rho/z/genuine/clear/spF_at_A/cross/stream)
    or None.

    `cross_hint` (session 56, throughput): a caller-supplied guess of the A-press cross frame,
    used only to SEED the placement fixpoint (placed built from the hint instead of an empty first
    pass). The acceptance invariant is unchanged -- a run is only returned once want == placed on
    the SIMULATED trajectory -- so a right hint saves one full approach sim and a wrong one just
    falls back to the normal iteration. Neighbouring candidates (a nudge grid on one bracket)
    share their cross, so sweeps thread the previous run's `cross` back in."""
    seam = _KAZE_SEAM if seam is None else seam
    # Aim the approach at THIS seam's F (generalization Phase 5): C.sticks_of hardcodes geometry.F,
    # which walks a NOVEL seam's approach the wrong way. Byte-identical for the kaze seam (seam.F==G.F).
    _cs = load_seed(anchor)['csangle'] & 0xFFFF
    aim = C.dtm_stick(stick_for_bearing(seam.F, _cs, 1.0))
    start = tuple(start)
    # Prepend (1-dtm_seed) neutral ABSORBER frames so the seed-0 layout's extra leading no-op does not
    # silently eat start[0] (dead-end #35; a full frame preserves seed-0's poll phase). seed=1 => 0.
    n_absorb = max(0, 1 - int(dtm_seed))
    placed = None
    if cross_hint is not None and moves:
        want0, ok = {}, True
        for mv in moves:
            ld, stk = mv[0], mv[1]
            dur = mv[2] if len(mv) > 2 else 1
            for d in range(dur):
                idx = cross_hint - ld + d
                if idx < len(start) or idx >= cross_hint or idx in want0:
                    ok = False
                    break
                want0[idx] = stk
            if not ok:
                break
        if ok:
            placed = want0
    for _ in range(4):
        s = base(anchor, dtm_seed=dtm_seed)
        if FAST_POSE and s._foot is not None:
            s._foot.skip_cruise_pose = True  # lazy cruise-pose defer (bit-exact; drains on any consumer)
        suffix = []
        for _ in range(n_absorb):
            s.step(128, 128)
            suffix.append((128, 128, 0))
        ci = 0
        cross = None
        for _ in range(90):
            if ci >= len(start) and seam.along((s.pos_x, s.pos_z)) >= A_proj:
                cross = ci
                break
            stk = start[ci] if ci < len(start) else aim
            if placed is not None and ci in placed:
                stk = placed[ci]
            btn = seam.B_BTN if (draw_at is not None and ci == draw_at) else 0
            s.step(stk[0], stk[1], buttons=btn)
            suffix.append((stk[0], stk[1], btn))
            ci += 1
        if cross is None:
            return None
        want = {}
        for mv in moves:
            ld, stk = mv[0], mv[1]
            dur = mv[2] if len(mv) > 2 else 1
            for d in range(dur):
                idx = cross - ld + d
                if idx < len(start) or idx >= cross or idx in want:
                    return None
                want[idx] = stk
        if want != (placed or {}):
            placed = want
            continue
        spF_at_A = s.speedF
        rows = []

        def do(sx, sy, btn=0):
            s.step(sx, sy, buttons=btn)
            suffix.append((sx, sy, btn))
            rows.append((s.state & 0xFF, s.pos_x, s.pos_z, s.facing & 0xFFFF))

        do(aim[0], aim[1], seam.A_BTN)
        for _ in range(seam.KROLL):
            do(aim[0], aim[1])
        do(aim[0], aim[1], seam.B_BTN)
        for _ in range(tail):
            do(aim[0], aim[1])
        cut_i = next((i for i, rr in enumerate(rows) if rr[0] in (CUT_F, CUT_A)), None)
        if cut_i is None or cut_i == 0:
            return dict(fired=False, spF_at_A=spF_at_A, cross=cross)
        old = (rows[cut_i - 1][1], rows[cut_i - 1][2])
        new = (rows[cut_i][1], rows[cut_i][2])
        roll_pts = [(rr[1], rr[2]) for rr in rows if rr[0] == FRONT_ROLL]
        gen = seam.genuine_clip(old, new)
        clear = gen and not any(seam.seg_blocked(roll_pts[i], roll_pts[i + 1])
                                for i in range(len(roll_pts) - 1))
        return dict(fired=True, old=old, new=new, rho=seam.perp(old), z=old[1],
                    genuine=gen, clear=clear, spF_at_A=spF_at_A, cross=cross,
                    facing=rows[cut_i][3], cut_proc=rows[cut_i][0],
                    disp=math.hypot(new[0] - old[0], new[1] - old[1]),
                    n_roll=len(roll_pts), stream=suffix)
    return None


def start_family(anchor, kmax=START_KMAX, F=None, seam=None):
    """The 1D-approach start-crawl lattice: distinct dtm-calibrated sticks at bearing F, full +
    every distinct live-valid partial (msd 0.889..0.52, the movement gate band -- the (0.889,1)
    band is live-divergent, see plan_land._freeze_start_lattice). Combos are k-tuples with the
    NON-FULL stick count kept low (each run is exact; the full x full.. prefix is the baseline).
    Ordered shallow-first so cheap candidates come first. `F` overrides the aim facing (default the
    kaze `geometry.F`) so the Tetra-corner solver can reuse this at its own clip facing."""
    F = (_KAZE_SEAM if seam is None else seam).F if F is None else F
    seed = load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    full = C.dtm_stick(stick_for_bearing(F, cs, 1.0))
    alph, seen = [], {full}
    for j in range(889, 519, -1):
        stk = C.dtm_stick(stick_for_bearing(F, cs, j / 1000.0))
        if stk not in seen:
            seen.add(stk)
            alph.append(stk)
    combos = []
    for stk in alph:                                     # k=1: one partial first frame
        combos.append((stk,))
    for stk in alph:                                     # k=2: partial + full, full + partial
        combos.append((stk, full))
        combos.append((full, stk))
    for stk in alph:                                     # k=3: one partial in three slots
        combos.append((stk, full, full))
        combos.append((full, stk, full))
        combos.append((full, full, stk))
    for a in alph[::4]:                                  # k=2 double-partial (coarse subsample)
        for b in alph[::4]:
            combos.append((a, b))
    return combos


def fine_family(anchor, mstep=0.004, leads=(4, 5, 6, 7, 10), F=None, seam=None):
    """1-frame partial-magnitude perp fines across the full msd range down to 0.50. The (0.889, 1.0)
    band is INCLUDED (session 43): the s41 "band walk-speed" exclusion was overturned -- RAM-reading
    `g_mDoCPd_cpadInfo[0]` proved the physics + decode are faithful and a 1-frame band stick delivers
    its raw value when ISOLATED (dead-end #34). The s41 live miss was a make_dtm DELIVERY DROP (the
    default seed=1 poll cadence dropped a clustered band fine), fixed by delivering with seed=0; so
    band fines are usable again and restore the near-full-mag perp density the band-free search lacked
    (session 40's ~0.0013u wall). Solve on the seed-0 model (`run(..., dtm_seed=0)`) so the sim matches
    the seed-0 delivery, and ship via seed=0."""
    F = (_KAZE_SEAM if seam is None else seam).F if F is None else F
    out, seen = [], set()
    seed = load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    aim = C.dtm_stick(stick_for_bearing(F, cs, 1.0))
    for j in range(-4, 5):
        m = 0.999
        while m >= 0.50:
            stk = C.dtm_stick(stick_for_bearing((F + 16 * j) & 0xFFFF, cs, m))
            if stk not in seen:
                seen.add(stk)
                out.append(stk)
            m -= mstep
    return [(ld, stk) for stk in out if stk != aim for ld in leads]


def arc_family(anchor, bstep=50, durs=(1, 2, 3), leads=(10, 9, 8, 7), min_settle=5, F=None, seam=None):
    F = (_KAZE_SEAM if seam is None else seam).F if F is None else F
    out, seen = [], set()
    seed = load_seed(anchor)
    cs = seed['csangle'] & 0xFFFF
    aim = C.dtm_stick(stick_for_bearing(F, cs, 1.0))
    for d in list(range(-1000, -149, bstep)) + list(range(150, 1001, bstep)):
        stk = C.dtm_stick(stick_for_bearing((F + d) & 0xFFFF, cs, 1.0))
        for dur in durs:
            for ld in leads:
                if ld - dur < min_settle:
                    continue
                key = (stk, dur, ld)
                if key in seen or stk == aim:
                    continue
                seen.add(key)
                out.append((ld, stk, dur))
    return out


def _record(hits, r, moves, A_proj, start, anchor, dtm_seed=1, draw_at=None):
    hits.append(dict(anchor=anchor, moves=[[m[0], list(m[1])] + list(m[2:]) for m in moves],
                     A_proj=A_proj, start=[list(x) for x in start], dtm_seed=dtm_seed, draw_at=draw_at,
                     old=list(r['old']), new=list(r['new']),
                     rho=r['rho'], facing=r['facing'], disp=r['disp'], cut_proc=r['cut_proc'],
                     n_roll=r['n_roll'], stream=[list(x) for x in r['stream']]))
    os.makedirs(os.path.dirname(HITS_PATH), exist_ok=True)
    json.dump(hits, open(HITS_PATH, 'w'))


def _derive_a_projs(anchor, seam, dtm_seed, r0, start=()):
    """Derive A-press thresholds whose baseline roll lands around the seam reach band.

    A named anchor normally starts behind the legacy -506 threshold, so its baseline gives a useful
    landing from which to shift the scan. A live anchor can start *past* -506; that presses A on row
    zero at speed 0 and has no ``old``. In that case, first sweep thresholds forward from the actual
    start projection to locate the capped-roll landing nearest the reach band, then refine around it.
    """
    lo, hi = seam.search_band()
    target_along = -(lo + hi) / 2.0
    start = tuple(tuple(stick) for stick in start)

    def capped_landing(A):
        r = run(anchor, [], A_proj=A, start=start, dtm_seed=dtm_seed, seam=seam)
        if not (r and r.get('fired') and r.get('old') and r.get('spF_at_A') == 17.0):
            return None
        old_along = seam.along(r['old'])
        return old_along, r

    if r0 and r0.get('old') and r0.get('spF_at_A') == 17.0:
        a_center = -506.0 + (target_along - seam.along(r0['old']))
    else:
        s0 = base(anchor, dtm_seed=dtm_seed)
        for stick in start:
            s0.step(*stick)
        start_along = seam.along((s0.pos_x, s0.pos_z))
        best = None
        # A must be ahead of the start or it fires immediately. The upper cap covers the complete
        # useful approach while avoiding a long scan after Link has already rolled through the seam.
        A = start_along + 0.5
        stop = min(128.0, start_along + 1200.0)
        while A <= stop:
            landed = capped_landing(A)
            if landed is not None:
                score = abs(landed[0] - target_along)
                if best is None or score < best[0]:
                    best = (score, A)
            A += 4.0
        if best is None:
            return ()
        a_center = best[1]

    cands, seen = [], set()
    for i in range(-60, 61):
        A = a_center + i * 0.5
        landed = capped_landing(A)
        if landed is None:
            continue
        old_along, _r = landed
        if -hi - 18.0 <= old_along <= -lo + 18.0:
            key = round(old_along, 0)
            if key not in seen:
                seen.add(key)
                cands.append((abs(old_along - target_along), A))
    cands.sort()
    return tuple(a for _, a in cands)

def search(anchor, nhits=4, do_drill=False, K=60, levels=2, draw_at=None, dtm_seed=1, seam=None):
    """Arc/fine singles, then the start-crawl sweep (dense along-track fill), then (optionally)
    an iterative-deepening drill combining the nearest configs. Every accept is the exact run.

    `draw_at` (session 35, sheathed roll path): forwarded to every `run` -- the approach row on
    which to feed the mid-walk sword draw's single B rising edge. For a sheathed anchor
    (`rest_state` model_draw ON) the draw completes before the A press so the roll routes to a
    CUT; None (a drawn anchor) is byte-identical to the pre-session-35 behaviour.

    `seam` (session 46, generalization Phase 3): the per-seam `SeamGeo` supplying `F` + exact
    acceptance; default None = the kaze r11 seam (`geometry.SEAM`), so the standard invocation is
    byte-identical. Threaded into every `run`/family call and the `!= seam.F` accept gate + drill
    dust cache, so a NEW enumerated seam solves via the same path (no module-global geometry)."""
    seam = _KAZE_SEAM if seam is None else seam
    t0 = time.time()
    r0 = run(anchor, [], draw_at=draw_at, dtm_seed=dtm_seed, seam=seam)
    print('baseline old=(%.7f,%.7f) z=%.4f rho=%+0.6f' % (
          r0['old'][0], r0['old'][1], r0['z'], r0['rho']), flush=True)
    hits, samples, n = [], [], 0

    def check(moves, A_proj, start=()):
        nonlocal n
        n += 1
        r = run(anchor, moves, A_proj, start=start, draw_at=draw_at, dtm_seed=dtm_seed, seam=seam)
        if (r is None or not r.get('fired') or r['facing'] != seam.F or r['spF_at_A'] != 17.0):
            return None
        samples.append((r['old'][0], r['old'][1], [list(m) for m in moves], A_proj,
                        [list(x) for x in start]))
        # Reachability is decided by the WALLED physics re-sim, not a typed-in old_z band (session 49):
        # accept only genuine + clear cuts whose approach actually reaches `old` past the wall.
        if r['genuine'] and r['clear'] and wall_faithful(anchor, r['stream'], r['old'], seam, dtm_seed):
            print('CLIP start=%s moves=%s A=%.0f old=(%.7f,%.7f) rho=%+0.6f (%.0fs)' % (
                  list(start), moves, A_proj, r['old'][0], r['old'][1], r['rho'],
                  time.time() - t0), flush=True)
            _record(hits, r, moves, A_proj, start, anchor, dtm_seed=dtm_seed, draw_at=draw_at)
        return r

    A_projs = _derive_a_projs(anchor, seam, dtm_seed, r0)
    print('A_projs (derived, bracket reach band): %s' % [round(a, 1) for a in A_projs], flush=True)
    fam = arc_family(anchor, seam=seam) + fine_family(anchor, seam=seam)
    for mv in fam:
        for A in A_projs:
            check([mv], A)
            if len(hits) >= nhits:
                return hits
    print('singles done: %d runs, hits=%d (%.0fs)' % (n, len(hits), time.time() - t0), flush=True)
    starts = start_family(anchor, seam=seam)
    for st in starts:
        check([], A_projs[0], start=st)
        if len(hits) >= nhits:
            return hits
    print('start-crawl done: %d runs, hits=%d (%.0fs)' % (n, len(hits), time.time() - t0),
          flush=True)
    if not do_drill:
        return hits
    # drill: extend the configs nearest to genuine dust with one more move / a start crawl
    def score(x, z):
        # x-column match dominates: the razor is thin in x and the along-track knobs are dense
        best = 1e9
        for gx, gz in _dust_cache():
            d = math.hypot((gx - x) * 200.0, gz - z)
            best = min(best, d)
        return best

    _dc = []

    def _dust_cache():
        # The drill's genuine TARGET set: sweep pred_genuine over the region the search REACHES --
        # centered on the sim baseline `old`, extents from the seam reach band, capped (session 49; no kaze box).
        if not _dc:
            from tww_sim.core.fp import f32 as _f
            lo, hi = seam.search_band()
            span = min(hi - lo, 8.0)                     # along extent, capped
            cx, cz = r0['old']
            olds = [(s[0], s[1]) for s in samples] or [(cx, cz)]
            hx = min(max(abs(o[0] - cx) for o in olds) + 0.6, 2.0)   # perp-ish (x), thin
            hz = min(max(abs(o[1] - cz) for o in olds) + 0.6, span)  # along-ish (z)
            x_lo, x_hi, z_lo, z_hi = cx - hx, cx + hx, cz - hz, cz + hz
            zz = z_lo
            while zz <= z_hi:
                xx = x_lo
                while xx <= x_hi:
                    if seam.pred_genuine((_f(xx), _f(zz))):
                        _dc.append((float(_f(xx)), float(_f(zz))))
                    xx += 0.001
                zz += 0.02
            print('dust cache: %d pts (box x[%.2f,%.2f] z[%.2f,%.2f])' % (
                  len(_dc), x_lo, x_hi, z_lo, z_hi), flush=True)
        return _dc

    pool = {json.dumps(s[2]) + str(s[3]) + json.dumps(s[4]): s for s in samples}
    for lvl in range(levels):
        cands = sorted(pool.values(), key=lambda s: score(s[0], s[1]))[:K]
        print('drill level %d (best %.5f)' % (lvl, score(cands[0][0], cands[0][1])), flush=True)
        for x, z, moves, A, start in cands:
            used = set()
            for m in moves:
                dur = m[2] if len(m) > 2 else 1
                used |= set(range(m[0] - dur + 1, m[0] + 1))
            movesT = [tuple([m[0], tuple(m[1])] + list(m[2:])) for m in moves]
            startT = tuple(tuple(x2) for x2 in start)
            for mv in fam:                       # one more arc/fine on this config
                dur = mv[2] if len(mv) > 2 else 1
                if set(range(mv[0] - dur + 1, mv[0] + 1)) & used:
                    continue
                check(movesT + [mv], A, start=startT)
                if len(hits) >= nhits:
                    return hits
            if not startT:                       # or a start crawl under this config
                for st in start_family(anchor, seam=seam)[:120]:
                    check(movesT, A, start=st)
                    if len(hits) >= nhits:
                        return hits
        pool = {json.dumps(s[2]) + str(s[3]) + json.dumps(s[4]): s for s in samples}
    print('done: %d runs, hits=%d (%.0fs)' % (n, len(hits), time.time() - t0), flush=True)
    return hits


NUDGE_SPMAX = 14.0             # nudge only start-crawl frames acted below this speedF (the octagon INTERIOR;
                               # above it sticks CLAMP + the fine lattice collapses -- see solve_focused doc).

# solve_focused Phase-B workers: each owns a from-rest sim cache and evaluates EXACT candidates
# (the same run + wall_faithful path as the serial loop) -- parallelism never changes results.
_PB = None


def _pb_init(anchor, seam_args, dtm_seed):
    global _PB
    from harness.rollstab.seamgeo import SeamGeo
    seam = SeamGeo(*seam_args)                   # (geo, csangle, roll_speedf, aim_deg): exact rebuild
    _PB = (anchor, seam, int(dtm_seed))


def _pb_eval(job):
    """Evaluate one Phase-A'/B/B2 candidate exactly. Returns None (did not fire / off-gate), a full
    hit dict (genuine + clear + wall-faithful, with margin -- the fields the parent records), or a
    compact `('near', old_x, old_z, cross)` for a fired on-gate non-hit (the parent ranks these by
    TRUE 2D distance to the genuine dust cloud; `cross` seeds the bracket's Phase-B fixpoint)."""
    moves, A, start, hint = job
    anchor, seam, dtm_seed = _PB
    r = run(anchor, [tuple(m) for m in moves], A_proj=A, start=start,
            dtm_seed=dtm_seed, seam=seam, cross_hint=hint)
    if not (r and r.get('fired')):
        return None
    if not (r['facing'] == seam.F and r['spF_at_A'] == 17.0):
        return None
    if (r['genuine'] and r['clear']
            and wall_faithful(anchor, r['stream'], r['old'], seam, dtm_seed)):
        r['margin'] = _perp_margin(seam, r['old'], r['new'])
        return r
    return ('near', r['old'][0], r['old'][1], r.get('cross'))


def _genuine_perps(seam, samples=None):
    """The perp offsets of the genuine dust columns inside the seam's reach band -- a PURE-GEOMETRY
    (no sim) target set for the Phase-A bracket ranker. Scans `pred_genuine` over the band in the seam's
    (along, perp) frame and returns the sorted distinct perp values where a column exists. The corner
    razor is NOT at perp 0 (that is only true for a flat grazing seam); this derives its actual offset
    band from the geometry, so the ranker needs no per-seam target perp ([[no-overtuned-constants]])."""
    lo, hi = seam.search_band()
    Sx, Sz = seam.S
    out = set()
    a = -hi
    while a <= -lo:
        p = -0.5
        while p <= 0.5:
            x = Sx + a * seam.DIRX + p * seam.PX
            z = Sz + a * seam.DIRZ + p * seam.PZ
            if seam.pred_genuine((_F(x), _F(z))):
                out.add(round(p, 3))
            p += 0.001
        a += 0.05
    return sorted(out)


DUST_PW = 200.0                # perp weight in the 2D dust distance -- the same x-column-dominates
                               # weighting the legacy drill's score used (the razor is thin in perp,
                               # the along-track knobs are dense).


def _dust2d(seam, astep=0.005, pstep=2e-5, pmargin=0.010):
    """The EXACT 2D genuine-dust point cloud in the seam's (along, perp) frame -- the true target
    set the session-56 rounded-column ranker approximated (dead-end #40: `_genuine_perps` rounds
    perp to 1e-3, so a candidate could rank razor-close to a phantom column while sitting units
    from any real dust in along). Scans `pred_genuine` at `astep` along x `pstep` perp over the
    reach band, with the perp window restricted to the genuine column band +- `pmargin` (derived
    from `_genuine_perps`, pure geometry -- no per-seam constants). ~30s for a 10u band; DISK-CACHED
    under `_generated/` keyed by the seam's geometry + frame, so a draw pays it once per seam.
    Returns (P, A): the cloud's perp values sorted ascending + the matching along values."""
    import hashlib
    key = hashlib.sha1(json.dumps([seam.geo, seam.F, seam.roll_speedf, astep, pstep, pmargin],
                                  sort_keys=True).encode()).hexdigest()[:16]
    path = os.path.join(_rb, '_generated', 'dust2d_%s.json' % key)
    if os.path.exists(path):
        d = json.load(open(path))
        return d['P'], d['A']
    gp = _genuine_perps(seam)
    P, A = [], []
    if gp:
        lo, hi = seam.search_band()
        Sx, Sz = seam.S
        pts = []
        a = -hi
        while a <= -lo:
            p = gp[0] - pmargin
            while p <= gp[-1] + pmargin:
                x = Sx + a * seam.DIRX + p * seam.PX
                z = Sz + a * seam.DIRZ + p * seam.PZ
                if seam.pred_genuine((_F(x), _F(z))):
                    pts.append((a, p))
                p += pstep
            a += astep
        pts.sort(key=lambda ap: ap[1])
        P = [p for _, p in pts]
        A = [a for a, _ in pts]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({'P': P, 'A': A}, open(path, 'w'))
    return P, A


def _dust_dist(P, A, along, perp, pw=DUST_PW):
    """Weighted TRUE distance from (along, perp) to the nearest exact dust point:
    min hypot(pw*(perp - P[i]), along - A[i]). `P` sorted ascending; walks outward from the perp
    insertion point and stops each side once the perp term alone exceeds the best -- exact, and
    O(neighbourhood) per query. Empty cloud -> inf (callers fall back to the perp-column score)."""
    best = float('inf')
    i = bisect.bisect_left(P, perp)
    lo_i, hi_i = i - 1, i
    lo_done, hi_done = lo_i < 0, hi_i >= len(P)
    while not (lo_done and hi_done):
        if not lo_done:
            if abs((P[lo_i] - perp) * pw) > best:
                lo_done = True
            else:
                best = min(best, math.hypot((P[lo_i] - perp) * pw, A[lo_i] - along))
                lo_i -= 1
                lo_done = lo_i < 0
        if not hi_done:
            if abs((P[hi_i] - perp) * pw) > best:
                hi_done = True
            else:
                best = min(best, math.hypot((P[hi_i] - perp) * pw, A[hi_i] - along))
                hi_i += 1
                hi_done = hi_i >= len(P)
    return best


def solve_focused(anchor, seam, dtm_seed=0, budget=110.0, want=8, off_span=1800,
                  off_step=120, nudge=10, kbr=40, m2s=None, c3m=0.66,
                  verbose=True, procs=None, prefix=(), use_dust=True, dust_hint=None,
                  near_out=None):
    """Focused roll-stab dust search (the walkstab.solve_focused pattern in the roll `run` form): an ARC
    gross-perp bracket + a LOW-SPEED byte-nudge densifier + the wall_faithful gate. Pure sim, no
    calibration. This is the objective-compliant one-shot for a NOVEL seam whose reachable roll line sits
    units off the razor -- which the cold `search`/drill cannot thread.

    WHY the cold drill fails and this doesn't (session 51): the genuine acceptance is a single f32 column
    (~0.001u wide, sparse) and, for a novel seam, the reachable roll `old` sits GROSSLY off it in perp (the
    mirror seam's approach line is ~2.7u off the F-through-S line; the proven kaze seam was already near its
    razor, so `search`'s fine knobs sufficed there). Closing that gap needs the ARC (a full-mag off-aim
    stint -- the gross perp knob; it octagon-SATURATES, so a wide off range collapses onto the same shift).
    Then the exact column is threaded by a byte-NUDGE of a start-crawl frame acted at LOW speed (the nudged
    frame's speedF < NUDGE_SPMAX): near the walk cap sticks octagon-CLAMP and the reachable lattice
    collapses; below it the partial-mag stick stays in the octagon INTERIOR. NOTE the nudge is NOT a smooth
    fine knob in the roll form (unlike walk-stab's short walk-then-cut): a low-speed perturbation propagates
    through the whole cruise+roll, so the reachable `old` lattice is CHAOTIC -- a genuine hit is an isolated
    lattice point, found by sweeping the nudge grid and testing each EXACTLY.

    Phase A' (session 57: the bracket ranking includes the CRAWL): sweep arc(off, lead, dur) x the
      derived A_projs x the m2 crawl family, where each center is the run Phase B will actually nudge
      -- start=(full, f2(m2), c3 center) -- and rank the fired spF@A==17 centers by TRUE 2D distance
      to the exact genuine dust cloud (`_dust2d`/`_dust_dist`). Keep `kbr` brackets, consumed
      ROUND-ROBIN across arc families (each off's best m2 first): a center point is noise at the
      cloud's ~1-2u chaotic scale, so a DENSE seam needs family breadth while a THIN seam needs the
      nearest-band families first -- the round-robin serves both. TWO session-56/57
      measurement findings drive this shape (dead-ends #40/#41): (1) the old Phase A ranked the
      CRAWL-LESS arc trajectory, but the K=3 crawl Phase B always adds displaces the center ~1.2u of
      perp on the 97m -- the "razor-close" brackets were razor-close for a family Phase B never
      evaluated, which is where the cloud's median ~1.9u perp spread actually came from; (2) the
      rounded-column perp score ranked candidates 3-12u of along away from any real dust at the top
      (dcol 1e-5 with d_true 3.0). `m2s` is the crawl partial-magnitude family (README knobs; None =
      the full derived msd family, distinct delivered sticks): each m2 is a fresh independent center
      family, and the ranking now sees every family's real landing.
    Phase B (nudge): for each kept (bracket, m2), byte-NUDGE the 3rd crawl frame over a +-`nudge`
      grid; test the EXACT genuine_clip + clear at spF@A==17, facing==seam.F.
    Phase C (walled confirm): `wall_faithful` re-sim -- accept only cuts whose approach reaches `old` past
      the wall (dead-end #3). Rank by the perp sliver margin (delivery robustness). Records to HITS_PATH
      (same schema as `search`, carrying the explicit `start`/`moves`/`A_proj`/`dtm_seed`) for `deliver`.
    Phase B2 (fine drill, session 56; ranking fixed session 57): extends the near-misses nearest to
      REAL dust (TRUE 2D distance, not the rounded-column score) with one documented 1-frame
      partial-magnitude FINE (`fine_family`), tested exactly, until the budget. NOTE the session-57
      measurement: a fine is NOT a local refiner in the roll form (children land median ~3.5u of along
      from the parent -- the same chaotic propagation as the nudge), so B2 is extra independent draws
      around good families, not a last-mile closer.

    Every knob is derived or a documented physical regime (NUDGE_SPMAX, the octagon-interior magnitude
    0.66, the general symmetric arc span, the geometry-derived genuine-perp target) -- no per-seam tuned
    constants ([[no-overtuned-constants]]).

    `procs` (session 56 throughput): Phase-B worker processes (None = cpu_count-2 capped at 10; 1 =
    the serial loop). Workers evaluate the SAME exact candidates through the SAME `run` +
    `wall_faithful` gates -- parallelism multiplies how much of the grid a wall-clock budget covers,
    never what a candidate evaluates to. With the lazy cruise-pose defer + the fixpoint cross hint
    (also session 56) a 2-min draw covers ~25x the session-55 candidate count."""
    t0 = time.time()
    prefix = tuple(tuple(stick) for stick in prefix)
    _cs = load_seed(anchor)['csangle'] & 0xFFFF
    full = C.dtm_stick(stick_for_bearing(seam.F, _cs, 1.0))
    c3raw = stick_for_bearing(seam.F, _cs, c3m)       # octagon-interior mid-magnitude nudge base
    #                                                   (c3m: the documented msd family 0.52..0.889 --
    #                                                   a different base = a fresh independent lattice)
    c30 = C.dtm_stick(c3raw)
    r0 = run(anchor, [], start=prefix, dtm_seed=dtm_seed, seam=seam)
    A_projs = _derive_a_projs(anchor, seam, dtm_seed, r0, start=prefix)
    if dust_hint is not None:
        dP, dA = dust_hint
    else:
        dP, dA = _dust2d(seam) if use_dust else ([], [])
    # _dust2d already ran the expensive exact-column discovery on a cache miss. Reconstruct the
    # display-only column list from its cloud instead of rescanning the geometry every invocation.
    gperps = (sorted({round(p, 3) for p in dP}) if dP else
              (_genuine_perps(seam) if use_dust else []))
    prep_seconds = time.time() - t0
    # Geometry preprocessing is disk-cached but can exceed the requested trajectory budget on its
    # first run. The user budget starts here; otherwise Phase A receives zero jobs on a fresh seam.
    t0 = time.time()

    def score(old):                                   # TRUE 2D distance to the exact dust cloud
        if not dP:                                    # range mode: rank the actual slash ray
            return abs(seam.perp_to_ray(old, seam.cut_new(old)))
        return _dust_dist(dP, dA, seam.along(old), seam.perp(old))

    # m2 crawl family: full + every DISTINCT delivered partial over the documented msd knob band
    # (see the docstring; dedup by delivered stick, so the family size is octagon-derived).
    m2fam, _seen2 = [], set()
    for m in ([1.0] + [j / 1000.0 for j in range(960, 519, -40)] if m2s is None else m2s):
        stk = full if m >= 1.0 else C.dtm_stick(stick_for_bearing(seam.F, _cs, m))
        if stk not in _seen2:
            _seen2.add(stk)
            m2fam.append((m, stk))

    if verbose:
        print(('focused: %d exact dust pts (%d perp cols); m2 family %d; A_projs=%s ' +
               '(preprocessing %.0fs; trajectory budget %.0fs)') % (
              len(dP), len(gperps), len(m2fam), [round(a, 1) for a in A_projs[:8]],
              prep_seconds, budget), flush=True)
        if dust_hint is not None:
            print('exact facing witness retained as the rank target; every accepted hit remains exact',
                  flush=True)
        elif not use_dust:
            print('angle-range pass: dust preprocessing disabled; every accepted hit remains exact',
                  flush=True)

    hits, seen = [], set()
    pool = None
    if procs is None:
        import multiprocessing
        procs = max(1, min(10, multiprocessing.cpu_count() - 2))
    if procs > 1:
        from concurrent.futures import ProcessPoolExecutor
        pool = ProcessPoolExecutor(max_workers=procs, initializer=_pb_init,
                                   initargs=(anchor, (seam.geo, seam.csangle, seam.roll_speedf,
                                                      seam.aim_deg), dtm_seed))
        if verbose:
            print('workers: %d' % procs, flush=True)
    else:
        global _PB
        _PB = (anchor, seam, int(dtm_seed))          # serial path: _pb_eval reads the same global

    def _accept(r, tag, moves, A, start):
        key = (round(r['old'][0], 5), round(r['old'][1], 5))
        if key in seen:
            return
        seen.add(key)
        _record(hits, r, moves, A, start, anchor, dtm_seed=dtm_seed)
        hits[-1]['margin'] = r['margin']
        json.dump(hits, open(HITS_PATH, 'w'))
        if verbose:
            print('  CLIP margin=%d %s A=%.1f old=(%.7f,%.7f) perp_ray=%+.6f d2S=%.3f (%.0fs)' % (
                  r['margin'], tag, A, r['old'][0], r['old'][1],
                  seam.perp_to_ray(r['old'], r['new']), seam.d2S(r['old']),
                  time.time() - t0), flush=True)

    def _c3(dx, dz):
        return C.dtm_stick((min(254, max(1, c3raw[0] + dx)), min(254, max(1, c3raw[1] + dz))))

    near = []                     # fired non-hits: (d_true, moves, A, start, tag, cross)

    def _sweep(jobs, tags):
        """Evaluate exact candidate jobs (pooled or serial), routing full hits through _accept and
        collecting fired near-misses into `near` (ranked by TRUE dust distance for Phase B2)."""
        if pool is not None:
            results = pool.map(_pb_eval, jobs, chunksize=max(1, len(jobs) // (procs * 4)))
        else:
            results = map(_pb_eval, jobs)
        for job, tag, r in zip(jobs, tags, results):
            if r is None:
                continue
            if isinstance(r, tuple):                    # ('near', old_x, old_z, cross)
                near.append((score((r[1], r[2])), job[0], job[1], job[2], tag, r[3]))
                continue
            _accept(r, tag, list(job[0]), job[1], job[2])

    try:
        # --- Phase A': crawl-included centers (arc x A_proj x m2), ranked by TRUE dust distance ---
        n_ctr = 0
        ctrs = []                 # fired centers: (d_true, off, moves, A, start, tag, cross)
        off_values = [o for o in range(-off_span, off_span + 1, off_step) if o != 0]

        # A complete dense offset family is expensive in the serial GUI path. Probe every offset
        # once, then spend at most 45% of the trajectory budget densely evaluating the best ones.
        # This prevents a useful positive arc from being starved by negative offsets encountered first.
        scouted = []
        scout_start = prefix + (full, full, c30)
        for off in off_values:
            arc = C.dtm_stick(stick_for_bearing((seam.F + off) & 0xFFFF, _cs, 1.0))
            r = run(
                anchor, [(7, arc, 5)], A_projs[0], start=scout_start,
                dtm_seed=dtm_seed, seam=seam,
            )
            if r and r.get('fired') and r.get('old') and r.get('spF_at_A') == 17.0:
                scouted.append((score(r['old']), off))
        scouted.sort()
        ordered_offsets = [off for _, off in scouted]
        ordered_offsets += [off for off in off_values if off not in set(ordered_offsets)]
        phase_a_deadline = t0 + budget * 0.45

        for off in ordered_offsets:
            if time.time() > phase_a_deadline or len(hits) >= want:
                break
            arc = C.dtm_stick(stick_for_bearing((seam.F + off) & 0xFFFF, _cs, 1.0))
            jobs, tags = [], []
            for dur in (2, 3, 4, 5):
                for lead in (4, 5, 6, 7):
                    for A in A_projs[:6]:
                        for (m2, f2) in m2fam:
                            jobs.append((((lead, arc, dur),), A, prefix + (full, f2, c30), None))
                            tags.append('off=%+d dur=%d lead=%d m2=%.2f center' % (off, dur, lead, m2))
            n_ctr += len(jobs)
            mark = len(near)
            _sweep(jobs, tags)
            ctrs += [(x[0], off) + x[1:] for x in near[mark:]]
        ctrs.sort(key=lambda x: x[0])
        # ROUND-ROBIN across arc families, best-d_true first within each (greedy over-concentrates;
        # rationale in the docstring Phase-A' paragraph + dead-end #41).
        fams, fam_order = {}, []
        for x in ctrs:
            if x[1] not in fams:
                fams[x[1]] = []
                fam_order.append(x[1])
            fams[x[1]].append(x)
        brackets = []
        while len(brackets) < min(kbr, len(ctrs)) and any(fams.values()):
            for off in fam_order:
                if fams[off]:
                    brackets.append(fams[off].pop(0))
        if verbose:
            print("Phase A': %d crawl-included centers -> %d fired (%d arc families), "
                  "best d_true=%.5f (%.0fs)" % (n_ctr, len(ctrs), len(fam_order),
                  ctrs[0][0] if ctrs else -1, time.time() - t0), flush=True)

        # --- Phase B + C: the c3 byte-nudge grid per kept (bracket, m2) center ---
        for (d0, off, moves0, A, start0, tag0, cross) in brackets:
            if time.time() - t0 > budget or len(hits) >= want:
                break
            f2 = start0[len(prefix) + 1]
            jobs, tags = [], []
            for dx in range(-nudge, nudge + 1):
                for dz in range(-nudge, nudge + 1):
                    if dx == 0 and dz == 0:
                        continue                       # the center itself ran in Phase A'
                    jobs.append((tuple(moves0), A, prefix + (full, f2, _c3(dx, dz)), cross))
                    tags.append('%s nudge=(%+d,%+d)' % (tag0.replace(' center', ''), dx, dz))
            _sweep(jobs, tags)
        if verbose:
            nb = sum(1 for x in near if x[0] < 0.02)
            print('Phase B: %d fired candidates, near-band(d_true<0.02)=%d, best d_true=%.5f (%.0fs)'
                  % (len(near), nb, min((x[0] for x in near), default=-1), time.time() - t0),
                  flush=True)

        # --- Phase B2: fine drill on the near-misses nearest to REAL dust (fines are chaotic --
        # extra independent draws around good families, not a last-mile closer; see docstring). ---
        if len(hits) < want and time.time() - t0 < budget:
            fam = fine_family(anchor, seam=seam)
            keepers = sorted(near, key=lambda x: x[0])   # snapshot: _sweep keeps appending to near
            n_drill = 0
            for dtrue0, moves0, A, start0, tag0, _cross in keepers:
                if time.time() - t0 > budget or len(hits) >= want:
                    break
                used = set()
                for m in moves0:
                    dur0 = m[2] if len(m) > 2 else 1
                    used |= set(range(m[0] - dur0 + 1, m[0] + 1))
                jobs, tags = [], []
                for mv in fam:
                    if mv[0] in used:
                        continue
                    jobs.append((tuple(moves0) + (mv,), A, start0, None))
                    tags.append('%s +fine(ld=%d stk=%s)' % (tag0, mv[0], list(mv[1])))
                _sweep(jobs, tags)
                n_drill += 1
            if verbose:
                print('Phase B2: drilled %d near-misses (best d_true=%.6f) of %d (%.0fs)' % (
                      n_drill, keepers[0][0] if keepers else -1, len(keepers), time.time() - t0),
                      flush=True)
    finally:
        if pool is not None:
            pool.shutdown()
    if near_out is not None:
        for dtrue, moves0, a_proj, start0, tag0, cross0 in sorted(near, key=lambda x: x[0])[:32]:
            replay = run(
                anchor, list(moves0), A_proj=a_proj, start=start0,
                dtm_seed=dtm_seed, seam=seam, cross_hint=cross0,
            )
            if not (replay and replay.get("fired") and replay.get("old")):
                continue
            replay["d_true"] = dtrue
            replay["moves"] = [list(move) for move in moves0]
            replay["A_proj"] = a_proj
            replay["start"] = [list(stick) for stick in start0]
            replay["tag"] = tag0
            near_out.append(replay)
    hits.sort(key=lambda h: -h.get('margin', 0))
    json.dump(hits, open(HITS_PATH, 'w'))
    if verbose:
        print('focused done: %d wall-faithful clips in %.0fs -> %s' % (
              len(hits), time.time() - t0, HITS_PATH), flush=True)
    return hits


def _perp_margin(seam, old, new, step=2e-5, cap=60):
    """The contiguous perp half-window at `old` (fresh in-line lunge), in +-`step` u -- how far `old` can
    shift PERPENDICULAR and still clip. Ranks hits by f32-sliver width (delivery robustness); the from-rest
    sim is 0-ULP so the live `old` lands exactly on the sim's and any positive-margin hit delivers (the
    same metric walkstab.perp_margin uses)."""
    from tww_sim.core.fp import f32 as _f
    a = math.atan2(new[0] - old[0], new[1] - old[1])
    pdx, pdz = -math.cos(a), math.sin(a)
    lunge = (_f(new[0] - old[0]), _f(new[1] - old[1]))

    def clips(k):
        o2 = (_f(old[0] + _f(k * step * pdx)), _f(old[1] + _f(k * step * pdz)))
        n2 = (_f(o2[0] + lunge[0]), _f(o2[1] + lunge[1]))
        return seam.genuine_clip(o2, n2)

    if not clips(0):
        return -1
    p = 0
    while p < cap and clips(p + 1):
        p += 1
    q = 0
    while q < cap and clips(-(q + 1)):
        q += 1
    return min(p, q)


if __name__ == '__main__':
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    anchor = o.get('anchor', 'kaze_r11_rollstab_idle2@twwgz')
    if 'focused' in sys.argv:
        from harness.rollstab.seamgeo import SeamGeo
        geo = json.load(open(o['geo'])) if 'geo' in o else None
        seam = SeamGeo(geo, load_seed(anchor)['csangle']) if geo else _KAZE_SEAM
        solve_focused(anchor, seam, dtm_seed=int(o.get('seed', 0)),
                      procs=(int(o['procs']) if 'procs' in o else None),
                      budget=float(o.get('budget', 110.0)), c3m=float(o.get('c3m', 0.66)),
                      nudge=int(o.get('nudge', 10)), kbr=int(o.get('kbr', 40)))
    else:
        search(anchor, do_drill=('drill' in sys.argv))
