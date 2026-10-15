"""From-rest COUPLED dust solver (Phase T): the Tetra-corner counterpart of `solver.py`.

!!! SUPERSEDED STAGING ASSUMPTION -- DO NOT BUILD ON THIS AS-IS (session 19 correction).
    This module was written assuming a STATIONARY behind-Link Tetra delivers the push, with a STATIC
    `co_move_pair` acceptance. The coupled DYNAMICS REFUTE that staging: the needed push is only ~11deg
    off the roll line, so the delivering Tetra sits ~15u from the line -- exactly where Link's rolling
    Co centre travels -- so the roll-in PLOWS her (large chaotic pushes, flung ~40u) before the cut
    frame, and CUT_F fires with zero/wrong push. See README ## Status, dead-ends #17, and
    `_notes/seam-clip-live-validation-handoff-2026-07-11-session19.md`. The CORRECT staging is the OPEN
    question (brace Tetra behind, or a timed placement), and acceptance must be the DYNAMIC coupled cut
    (run the plow through `cc_stepper.CcCoupledStepper`), NOT the static predictor below.

Still valid here: the Tetra corner (-1727,-990) is a NEEDS-PUSH clip (the 49.2202u lunge lands ~0.75u
short, so acceptance tests the COUPLED endpoint `new = f32(old + push + LUNGE)`, `geometry_tetra`); the
push must point TOWARD the seam so Tetra is BEHIND Link (a corner-BRACED Tetra pushes the wrong way);
and the placement is a 2D f32 knob, not a 1D distance -- the push bearing (~235deg) is ~11deg off F, so
COLINEAR-BEHIND (along -F) never clips ([[tetra-push-model]] "the STEER decides it"). `solver.py`'s knob
families gained an optional `F=` param (backward-compatible) so a Tetra search can reuse them at GT.F.

The STATIC acceptance below (`accept` = `co_move_pair` push -> `geometry_tetra.coupled_new` ->
`genuine_clip`) reproduces the live golden endpoint bit-exact and is what `tests/test_tetra_solver.py`
gates -- but it does NOT model the dynamic shove, so a "hit" here is not a dynamically-reachable clip.

    python -m harness.rollstab.solver_tetra                 # offline self-check vs the golden
"""
import os, sys, math, json, time

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from harness.rollstab import geometry_tetra as GT
from harness.rollstab import rest as C
from harness.rollstab import solver as S0
from harness.rollstab.cc_stepper import (CcCoupledStepper, LINK_CO_R, LINK_CO_H,
                                         TETRA_CO_R, TETRA_CO_H)
from tww_sim.core.cc_push import co_move_pair, WEIGHT_LINK, WEIGHT_TETRA_V5
from tww_sim.core.anim import body_cyl
from tww_sim.core.fp import f32
from tww_sim.land.land import LandState, FRONT_ROLL, CUT_F, CUT_A
from tww_sim.land.walls import load_ordered_mesh
from tww_sim.land.plan_land import stick_for_bearing, world_angle_s16
from tww_sim.core.npc_zl1 import Zl1FollowState, STT_IDLE

SUM_R = LINK_CO_R + TETRA_CO_R                 # 80 (Link Co R=30 + Tetra Co R=50)
LINK_Y = GT.LINK_Y
GROUND_Y = 0.1632676                           # flat Tetra floor (Phase G; fixtures/hyrule_tetra_ground)
HITS_PATH = os.path.join(_rb, '_generated', 'rollstab_tetra_hits.json')
WALLS_PATH = os.path.join(_rb, 'fixtures', 'hyrule_tetra_walls_ordered.json')
DEFAULT_SHARE = 0.50                           # Link's rank-table Co share (rank 5 vs 5)


# ------------------------------------------------------------------ the coupled acceptance CORE

def link_co_center(old_x, old_z, roll_frame, shape_z=0):
    """Link's animated FRONT_ROLL body Co-cylinder centre (x, z) at `roll_frame` -- the exact
    `body_cyl.roll_co_center` the coupled stepper poses each frame (leads the feet toward the corner;
    `shape_z` = the draw-time turn lean, 0 for a straight approach)."""
    cx, cz = body_cyl.roll_co_center(f32(old_x), f32(old_z), GT.F, float(roll_frame), shape_z=shape_z)
    return (cx, cz)


def emergent_push(center_xz, tetra_xz, tetra_w=WEIGHT_TETRA_V5):
    """Link's consumed `m_cc_move` XZ for a Co overlap with a Tetra whose cylinder centre is
    `tetra_xz` -- the SAME `co_move_pair` call `cc_stepper._cc_check` makes. (0, 0) if no overlap."""
    lc = (f32(center_xz[0]), f32(LINK_Y), f32(center_xz[1]))
    tc = (f32(tetra_xz[0]), f32(LINK_Y), f32(tetra_xz[1]))
    lmv, _ = co_move_pair(lc, LINK_CO_R, LINK_CO_H, tc, TETRA_CO_R, TETRA_CO_H,
                          w1=WEIGHT_LINK, w2=tetra_w)
    return (lmv[0], lmv[2])


def accept(old, tetra_xz, roll_frame, shape_z=0, tetra_w=WEIGHT_TETRA_V5):
    """Exact coupled acceptance for a candidate (settled `old`, Tetra placement, cut `roll_frame`).
    Returns the Co centre, the emergent push, the coupled endpoint `new` (bit-identical to the real
    cut) and `genuine` (`geometry_tetra.genuine_clip` on it). This is the cheap-exact predictor."""
    center = link_co_center(old[0], old[1], roll_frame, shape_z)
    push = emergent_push(center, tetra_xz, tetra_w)
    new = GT.coupled_new(old, push)
    return dict(center=center, push=push, new=new, genuine=GT.genuine_clip(old, new),
                overlap=math.hypot(f32(center[0]) - f32(tetra_xz[0]),
                                   f32(center[1]) - f32(tetra_xz[1])))


# ------------------------------------------------------------------ the Tetra placement knob (2D f32)

def place_behind(center_xz, push_bearing_s16, overlap):
    """Tetra's f32 XZ so the emergent push points along `push_bearing_s16` at ~`overlap`*share: Tetra
    sits OPPOSITE the push from Link's Co centre, at centre-distance `SUM_R - overlap`."""
    r = (push_bearing_s16 & 0xFFFF) / 65536.0 * 2 * math.pi
    ux, uz = math.sin(r), math.cos(r)
    cd = SUM_R - overlap
    return (f32(center_xz[0] - cd * ux), f32(center_xz[1] - cd * uz))


def nominal_placement(old, roll_frame, shape_z=0, share=DEFAULT_SHARE):
    """A first-guess behind-Link Tetra for a settled `old`, from the AUTHORITATIVE target: the push
    NEEDED is `target_new - old - LUNGE`; place Tetra opposite it at the overlap that supplies its
    magnitude at `share`. Coarse -- the approach knobs thread the razor around it. Returns
    `(tetra_xz, push_bearing_s16, need_mag)`."""
    center = link_co_center(old[0], old[1], roll_frame, shape_z)
    need = (f32(GT.TARGET['new'][0]) - f32(old[0]) - GT.LUNGE[0],
            f32(GT.TARGET['new'][1]) - f32(old[1]) - GT.LUNGE[1])
    nm = math.hypot(*need)
    brg = world_angle_s16(need[0], need[1])
    return place_behind(center, brg, nm / share), brg, nm


def placement_search(old, roll_frame, span=2.0, step=0.02, shape_z=0, tetra_w=WEIGHT_TETRA_V5):
    """2D f32 sweep of Tetra XZ around the nominal placement; return the genuine-clip placements
    (each an EXACT candidate). For a FIXED `old` this is a razor point; the solver's real fill is the
    approach knobs moving `old` (this sweep exists to prove the placement axis + seed the nominal)."""
    nom, _, _ = nominal_placement(old, roll_frame, shape_z)
    hits, k = [], int(span / step)
    for ix in range(-k, k + 1):
        for iz in range(-k, k + 1):
            tetra = (f32(nom[0] + ix * step), f32(nom[1] + iz * step))
            a = accept(old, tetra, roll_frame, shape_z, tetra_w)
            if a['push'] != (0.0, 0.0) and a['genuine']:
                hits.append((tetra, a))
    return hits


# ------------------------------------------------------------------ from-rest coupled run (LIVE-PENDING)

def _load_seed(anchor):
    # geometry_tetra has no seed loader (it is corner geometry, not an anchor); reuse geometry's.
    from harness.rollstab import geometry as _G
    return _G.load_seed(anchor)


def _aim(anchor):
    """The dtm-calibrated full-magnitude stick aimed at the Tetra clip facing GT.F from the anchor's
    camera yaw (the from-rest cruise/roll aim)."""
    seed = _load_seed(anchor)
    return C.dtm_stick(stick_for_bearing(GT.F, seed['csangle'] & 0xFFFF, 1.0))


def build_approach_stream(anchor, moves=(), A_proj=-506.0, start=(), kroll=13, tail=6):
    """Build the full per-frame input stream for a from-rest roll-stab aimed at the Tetra corner,
    mirroring `solver.run`'s placement (single-actor rest sim; the A press fires when the roll line
    reaches `A_proj` along GT; `moves`/`start` are the approach knobs) but at GT.F. Returns
    `(stream, spF_at_A, roll_pts, old_single, new_single)` where the *_single are the WALL-FREE
    single-actor roll's cut (a prefilter; the coupled run recomputes the real coupled cut)."""
    aim = _aim(anchor)
    start = tuple(start)
    placed = None
    for _ in range(4):
        s = C.rest_state(anchor)
        stream, ci, cross = [], 0, None
        for _ in range(90):
            if ci >= len(start) and GT.along((s.pos_x, s.pos_z)) >= A_proj:
                cross = ci
                break
            stk = start[ci] if ci < len(start) else aim
            if placed is not None and ci in placed:
                stk = placed[ci]
            s.step(stk[0], stk[1])
            stream.append((stk[0], stk[1], 0))
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
            stream.append((sx, sy, btn))
            rows.append((s.state & 0xFF, s.pos_x, s.pos_z))

        do(aim[0], aim[1], GT.A_BTN)
        for j in range(kroll):
            do(aim[0], aim[1])
        do(aim[0], aim[1], GT.B_BTN)
        for _ in range(tail):
            do(aim[0], aim[1])
        cut_i = next((i for i, rr in enumerate(rows) if rr[0] in (CUT_F, CUT_A)), None)
        roll_pts = [(rr[1], rr[2]) for rr in rows if rr[0] == FRONT_ROLL]
        old_s = (rows[cut_i - 1][1], rows[cut_i - 1][2]) if cut_i else None
        new_s = (rows[cut_i][1], rows[cut_i][2]) if cut_i else None
        return stream, spF_at_A, roll_pts, old_s, new_s
    return None


def _seed_tetra(tetra_xz):
    return Zl1FollowState(x=f32(tetra_xz[0]), y=f32(GROUND_Y), z=f32(tetra_xz[1]),
                          angle_y=0, speedF=0.0, stt=STT_IDLE)


def replay_coupled(anchor, stream, tetra_xz, walls, ground_y=GROUND_Y, tetra_w=WEIGHT_TETRA_V5):
    """Replay a pre-built approach `stream` through the REAL coupled stepper (from-rest Link + a
    stationary idle Tetra at `tetra_xz`), reading the ACTUAL cut frame. Returns an info dict
    (old/new/push/genuine/clear/facing/spF-context) or None if no CUT dispatched. LIVE-PENDING:
    needs a minted flooded-Hyrule anchor for `C.rest_state`."""
    link = C.rest_state(anchor, walls=walls)
    link._roll_m3570 = False
    drv = CcCoupledStepper(link, _seed_tetra(tetra_xz), walls_tetra=walls, ground_y=ground_y,
                           tetra_w=tetra_w)
    rows = []
    for (sx, sy, btn) in stream:
        pre = (drv.link.pos_x, drv.link.pos_z)
        d = drv.step(sx, sy, buttons=btn)
        rows.append(dict(proc=drv.link.state & 0xFF, pre=pre,
                         post=(drv.link.pos_x, drv.link.pos_z), push=d['link_push'],
                         facing=drv.link.facing & 0xFFFF))
    cut_i = next((i for i, r in enumerate(rows) if r['proc'] in (CUT_F, CUT_A)), None)
    if cut_i is None or cut_i == 0:
        return None
    old, new = rows[cut_i]['pre'], rows[cut_i]['post']
    roll_pts = [r['pre'] for r in rows if r['proc'] == FRONT_ROLL]
    gen = GT.genuine_clip(old, new)
    clear = gen and not any(GT.seg_blocked(roll_pts[i], roll_pts[i + 1])
                            for i in range(len(roll_pts) - 1))
    return dict(old=old, new=new, push=(rows[cut_i]['push'][0], rows[cut_i]['push'][2]),
                genuine=gen, clear=clear, facing=rows[cut_i]['facing'],
                cut_proc=rows[cut_i]['proc'], n_roll=len(roll_pts))


def run_coupled(anchor, tetra_xz, moves=(), A_proj=-506.0, start=(), kroll=13, tail=6,
                walls=None, ground_y=GROUND_Y, tetra_w=WEIGHT_TETRA_V5):
    """One exact from-rest COUPLED run: build the approach stream, replay it through the coupled
    stepper with Tetra at `tetra_xz`, and read the real cut. LIVE-PENDING (needs a minted anchor)."""
    if walls is None:
        walls = load_ordered_mesh(WALLS_PATH)
    built = build_approach_stream(anchor, moves, A_proj, start, kroll, tail)
    if built is None:
        return None
    stream, spF_at_A, _roll_pts, _os, _ns = built
    info = replay_coupled(anchor, stream, tetra_xz, walls, ground_y, tetra_w)
    if info is not None:
        info['spF_at_A'] = spF_at_A
        info['stream'] = stream
        info['tetra'] = tetra_xz
    return info


def search(anchor, nhits=4, walls=None, ground_y=GROUND_Y, kroll=13, do_drill=False):
    """From-rest coupled search: for a coarse behind-Link Tetra placement (nominal at the baseline
    `old`), sweep the approach knobs (start-crawl / arcs / fines at GT.F) to thread `old` onto the
    razor, testing the EXACT coupled cut per run. LIVE-PENDING: needs a minted flooded-Hyrule anchor.
    Mirrors `solver.search`; hits -> `_generated/rollstab_tetra_hits.json`."""
    if walls is None:
        walls = load_ordered_mesh(WALLS_PATH)
    t0 = time.time()
    base = run_coupled(anchor, GT.S, walls=walls, ground_y=ground_y, kroll=kroll)  # placeholder Tetra
    if base is None:
        print('baseline run produced no cut (approach/kroll off, or anchor not minted)', flush=True)
        return []
    # seed the coarse Tetra placement from the baseline old
    nom, brg, nm = nominal_placement(base['old'], roll_frame=16.5)
    print('baseline old=(%.7f,%.7f) rho=%+0.6f nominal Tetra=(%.4f,%.4f) push~%.4f' % (
          base['old'][0], base['old'][1], GT.perp(base['old']), nom[0], nom[1], nm), flush=True)
    hits, n = [], 0

    def check(moves, A_proj, start=()):
        nonlocal n
        n += 1
        r = run_coupled(anchor, nom, moves=moves, A_proj=A_proj, start=start, kroll=kroll,
                        walls=walls, ground_y=ground_y)
        if r is None or r['facing'] != GT.F or r.get('spF_at_A') != 17.0:
            return None
        if r['genuine'] and r['clear']:
            print('CLIP start=%s moves=%s A=%.0f old=(%.7f,%.7f) (%.0fs)' % (
                  list(start), moves, A_proj, r['old'][0], r['old'][1], time.time() - t0), flush=True)
            hits.append(r)
            os.makedirs(os.path.dirname(HITS_PATH), exist_ok=True)
            json.dump([dict(anchor=anchor, tetra=list(h['tetra']), old=list(h['old']),
                            new=list(h['new']), push=list(h['push']),
                            stream=[list(x) for x in h['stream']]) for h in hits],
                      open(HITS_PATH, 'w'))
        return r

    A_projs = (-506.0, -512.0, -500.0)
    fam = S0.arc_family(anchor, F=GT.F) + S0.fine_family(anchor, F=GT.F)
    for mv in fam:
        for A in A_projs:
            check([mv], A)
            if len(hits) >= nhits:
                return hits
    for st in S0.start_family(anchor, F=GT.F):
        check([], A_projs[0], start=st)
        if len(hits) >= nhits:
            return hits
    print('done: %d runs, hits=%d (%.0fs)' % (n, len(hits), time.time() - t0), flush=True)
    return hits


# ------------------------------------------------------------------ offline self-check (vs the golden)

def _selfcheck():
    """Offline, no anchor: prove the coupled acceptance core + 2D placement axis against the live
    golden -- a behind-Link Tetra whose EMERGENT push (via the real Co machinery) clips the golden
    seam and reproduces `new` bit-exact, while a colinear-behind Tetra does not."""
    import struct

    def bits(x):
        return struct.unpack('<I', struct.pack('<f', float(x)))[0]

    old = (f32(GT.TARGET['old'][0]), f32(GT.TARGET['old'][1]))
    gnew = (f32(GT.TARGET['new'][0]), f32(GT.TARGET['new'][1]))
    print('golden old=%s new=%s' % (old, gnew))
    for fr in (8.0, 12.0, 16.5):
        hits = placement_search(old, fr)
        exact = [t for (t, a) in hits
                 if bits(a['new'][0]) == bits(gnew[0]) and bits(a['new'][1]) == bits(gnew[1])]
        print('roll_frame=%.1f: %d genuine placements, %d reproduce golden new BIT-EXACT %s'
              % (fr, len(hits), len(exact), (exact[0] if exact else '')))
    # colinear-behind guard
    center = link_co_center(old[0], old[1], 12.0)
    tetra_col = place_behind(center, GT.F, 1.5)          # push along +F (colinear), not the steer
    a = accept(old, tetra_col, 12.0)
    print('colinear-behind (along F): genuine=%s (expect False -- the STEER matters)' % a['genuine'])


if __name__ == '__main__':
    _selfcheck()
