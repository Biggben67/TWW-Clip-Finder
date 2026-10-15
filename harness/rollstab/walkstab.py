"""WALK-stab seam-clip driver + solver scaffold (kaze r11, anchor kaze_r11_walkstab@twwgz).

GENERALIZED (session 48): the seam geometry + exact acceptance is the shared `seamgeo.SeamGeo`
(built from `fixtures/kaze_r11_walkstab_geo.json` + the anchor csangle), not private duplicates. The
acceptance functions below (`in_front`/`genuine_clip`/`perp_ray`/`fast_cut`) delegate to it. The
thrust facing F and the crawl-window center are DERIVED, not pasted: F = derive_F(bear_to_S) (a nearly
flat seam grazes toward S, not into the corner bisector; == the shipped 5625), and `solve_focused`'s
`cruise_beta` defaults to bear_to_S (was the pasted 5556).

The walk stab is the roll stab WITHOUT the roll: walk up to a sub-cap speed, then thrust (fwd stick
+ B) so a CUT_F fires out of a MOVE. lunge = speedF + 23.220 (the CUT_F joint-0 root translate; KB
mechanics/walk-stab.md), so a capped walk (speedF 17) reaches disp 40.22. The kaze r11 slot-3 seam
S=(9030.955,1385.858) (poly 803 x 802, interior 168.97 deg) clips from disp >= 35.02 (min speedF
~11.8), so no roll is needed.

WHAT IS PROVEN (live-gated):
  * ACCEPTANCE STRUCTURE (harness.collision.gap_search.characterize on this seam): a perp RAZOR --
    the offset window is ~2e-4u -- with a WIDE aim window (+-40 deg) and a wide displacement window
    (disp 35.5-40 all clip). So the razor is the perpendicular offset `rho` (the cut ray's distance
    to S); aim and disp are forgiving.
  * FROM-REST is BIT-EXACT 0-ULP (position + facing) under the C-DOWN camera pin (`substickY=0`; the
    auto-cam would otherwise swing csangle and drift facing -- session 28). The session-29/30 "walk-
    entry foot toe-stream residual" was NOT a foot-FK gap -- it was `rest.rest_state` picking the wrong
    ANIM SET (sword-drawn WALKS/DASHS for a Wind-Waker anchor; fixed session 31, seeds `sword_drawn`
    from the anchor equip). So any genuine OFFLINE clip is a TRUE one-shot -- no residual to eat the
    razor. Live regression: tests/test_walkstab_rest.py.
  * THE CLIP IS DELIVERED LIVE, 0-ULP (session 32): tests/golden/walkstab_deliver.json.

DRIVER: walk N frames from the rest seed (C-down held), then the CUT-DISPATCH frame
(`enter_cut_from_move`, session 75): procMove's setSpeedAndAngleNormal chase runs first, then the
CUT_F entry foot term fires along the CHASED travel (not facing -- live 0-ULP, the seam352 razor
fix). The item put-away delay is 4 frames of continued walking (the equip anime is upper-body; KB
walk-stab.md), so the sim is walk-N-then-dispatch and the B-press is delivered at frame N-5 (4-frame
put-away + 1-frame DTM buffering -> CUT_F at frame N). The B-timing sets where `old` lands; time it
to fire at the target `old` before any wall decel (the search's wall-faithful gate enforces speedF
still 17 at the cut).

SOLVER (`solve_focused()`, session 32): the objective-compliant one-shot -- the freeze-solver pattern
(cheap monotone predictor + bracket + exact bit-confirm), pure sim, no calibration. The acceptance perp
razor (~2e-4u) is a GAP in the reachable-old byte lattice at K<=2 crawls (min|perp| floors ~1.3e-3u,
~13x the razor -- which is why the old `solve()`, CRAWLS K<=2 + a collapsing arc/fine nudge, finds 0).
The fix: a K=3 START CRAWL densifies the perp lattice ~20x per frame (K=1 ~0.03u -> K=2 ~1.3e-3u ->
K=3 ~2e-5u), reaching the razor. Phase A brackets |perp_ray| coarsely (no CrrPos); Phase B drills a
byte-NUDGED 3rd crawl frame (octagon INTERIOR = the fine perp fill; the full-mag arc/cruise octagon-
CLAMP and collapse -- that collapse is why the old knobs failed); Phase C re-sims WITH walls and
accepts only wall_hit==False cuts (rejecting the dead-end #28 wall-overshoot artifacts). It finds
wall-faithful genuine hits in < 2 min. (`solve()` is kept as `solve_legacy` for the record.)

DELIVERY IS LIVE + 0-ULP (session 32) -- retires dead-end #28's "the walk-entry foot residual eats the
razor" premise (that was the sword/equip anim-set bug, fixed session 31; the from-rest walk is now
0-ULP, so any genuine offline clip is a true one-shot). `deliver()` shipped the top `solve_focused` hit
as a clean DTM (C-down every frame, B at frame N-5, NEVER advancewith): the CUT_F fired at N=13 with
`old`/`new` BIT-FOR-BIT the sim's from-rest prediction, the clip is genuine, and Link went OOB (proc
0x24, pos_y below the floor) THROUGH the seam. Live golden: tests/golden/walkstab_deliver.json;
regression tests/test_walkstab_clip.py.
"""
import os, sys, json, math, time
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from tww_sim.land.land import CUT_F
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.core.fp import f32 as _f
from harness.rollstab import rest as C
from harness.rollstab.seamgeo import SeamGeo

CDOWN = 0                       # substickY=0 = C-down = the free-cam pin (delivery MUST hold it)

# seam/anchor config (session 72: RETARGETABLE via configure() -- sets ANCHOR/GEO_PATH/_GEO/SEAM/
# LINK_Y/HITS_PATH/GOLDEN_PATH/DTM_SEED; do NOT assign elsewhere; acceptance = shared seamgeo.SeamGeo).
_KAZE_ANCHOR = 'kaze_r11_walkstab@twwgz'
_KAZE_GEO = os.path.join(_rb, 'fixtures', 'kaze_r11_walkstab_geo.json')

NAME = ANCHOR = GEO_PATH = _GEO = SEAM = LINK_Y = HITS_PATH = GOLDEN_PATH = None
DTM_SEED = 1
_SG = None
TARGET_FACING = None
TARGET_OLD = None
ANGLE_LO, ANGLE_HI = 0, 65535
FEASIBILITY = None
_TARGET_RHO = None


def configure(anchor=_KAZE_ANCHOR, geo_path=_KAZE_GEO, name='walkstab', dtm_seed=None,
              target_facing=None, angle_lo=0, angle_hi=65535, feasibility=None,
              target_old=None):
    """Retarget the walk-stab tier to a NOVEL (anchor, seam-geo) -- session 72, the generalization
    that unblocks novel walk-stab corners. Resets the seam/anchor globals (ANCHOR/GEO_PATH/_GEO/
    SEAM/LINK_Y) and clears every anchor-or-seam-derived cache (the SeamGeo, the rest seeds, the
    bearing, the bounds, and the stick caches -- which key on the anchor csangle). `name` namespaces
    the hits/golden output paths so a novel seam never clobbers the kaze walkstab golden; the default
    name 'walkstab' reproduces the exact legacy paths. Called once at import with the kaze defaults,
    so the default behaviour + all existing goldens/tests are byte-identical."""
    global ANCHOR, GEO_PATH, _GEO, SEAM, LINK_Y, HITS_PATH, GOLDEN_PATH, NAME, DTM_SEED
    global TARGET_FACING, TARGET_OLD, ANGLE_LO, ANGLE_HI, FEASIBILITY, _TARGET_RHO
    global _SG, _BASE, _BEAR_S, _BASE_WALLED, _BOUNDS
    ANCHOR = anchor
    # DTM_SEED = the leading-poll seed this anchor is REST-bit-exact at (noops==2): legacy kaze seed=1,
    # a fresh novel mint seed=0. solve+deliver both use it (a mismatch delivers the walk 1 frame off).
    DTM_SEED = (1 if name == 'walkstab' else 0) if dtm_seed is None else int(dtm_seed)
    GEO_PATH = geo_path if os.path.isabs(geo_path) else os.path.join(_rb, geo_path)
    _GEO = json.load(open(GEO_PATH))
    SEAM = (_GEO['S'][0], _GEO['S'][2])     # the seam vertex (x, z), full f32 precision
    LINK_Y = _GEO['link_y']                 # the walkable floor Y at the seam
    NAME = name
    TARGET_FACING = None if target_facing is None else int(target_facing) & 0xFFFF
    TARGET_OLD = None if target_old is None else (float(target_old[0]), float(target_old[1]))
    ANGLE_LO, ANGLE_HI = int(angle_lo) & 0xFFFF, int(angle_hi) & 0xFFFF
    FEASIBILITY = feasibility
    _TARGET_RHO = None
    _tag = '' if name == 'walkstab' else '_' + name
    HITS_PATH = os.path.join(_rb, '_generated', 'walkstab_hits%s.json' % _tag)
    GOLDEN_PATH = os.path.join(_rb, 'tests', 'golden', 'walkstab%s_deliver.json' % _tag)
    _SG = _BASE = _BEAR_S = _BASE_WALLED = _BOUNDS = None
    _SFB_CACHE.clear()
    _SFBD_CACHE.clear()


def sg():
    """The walk-stab seam's SeamGeo (the general roll/wall acceptance object), built once from the geo
    fixture + the anchor csangle, its thrust facing F derived from bear_to_S (a nearly-flat seam grazes
    toward S, not into the corner -- see seamgeo). Cached; every acceptance call below delegates here."""
    global _SG
    if _SG is None:
        _SG = SeamGeo(_GEO, seed().csangle, aim_deg=search_bearing() / 65536.0 * 360.0)
    return _SG


def in_front(x, z):
    g = sg()
    return g.in_front(g.p32(x, z))


def genuine_clip(old, new):
    """EXACT acceptance (delegates to the seam's SeamGeo): the cut segment old->new clips the seam --
    CrrPos NOT blocked, `old` in front of BOTH seam faces, `new` behind at least one. Returns
    (ok, why); the boolean is byte-identical to the pre-SeamGeo private copy (same TRIS, planes, LINK_Y)."""
    g = sg()
    if not g.in_front(g.p32(old[0], old[1])):
        return False, 'old_behind'
    if g.seg_blocked(old, new):
        return False, 'blocked'
    pn = g.p32(new[0], new[1])
    behind = g.wA.pla.func(pn) < 0 or g.wB.pla.func(pn) < 0
    return (behind, 'clip' if behind else 'short')


def perp_dist_to_S(old, facing):
    """Perpendicular distance from S to the ray from `old` at angle `facing` -- a rough label (uses
    continuous trig for the direction, offset by the >>4 console table). See perp_ray for the exact
    razor quantity (`rho`)."""
    a = facing / 65536.0 * 2 * math.pi
    dx, dz = math.sin(a), math.cos(a)
    px, pz = -dz, dx
    return (SEAM[0] - old[0]) * px + (SEAM[1] - old[1]) * pz


_BASE = None


def seed():
    """The from-rest seed for the walkstab anchor -- rest.rest_state (bit-exact facing under C-down).
    Cached; clone per run."""
    global _BASE
    if _BASE is None:
        _BASE = C.rest_state(ANCHOR, dtm_seed=DTM_SEED)
    return _BASE.clone()


def walk_then_cut(sticks, N, aim=None):
    """DRIVER: walk `sticks` for N frames from rest (C-down held), then the buffered-B cut DISPATCH
    frame (`enter_cut_from_move`: procMove's setSpeedAndAngleNormal chase runs first, then the CUT_F
    entry lunge fires its foot term along the chased travel -- live 0-ULP, session 75). Frames past
    len(sticks) reuse the last; the dispatch frame consumes sticks[N]. The 4-frame equip delay is
    delivery-only (the DTM presses B at frame N-5). Returns an acceptance dict or None."""
    s = seed()
    for k in range(N):
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=CDOWN)
    old = (s.pos_x, s.pos_z)
    dstk = sticks[N] if N < len(sticks) else sticks[-1]
    try:
        s.enter_cut_from_move(dstk[0], dstk[1], csx=128, csy=CDOWN, cut_type=CUT_F, aim=aim)
    except Exception:
        return None
    fac, spF = s.facing, s.speedF
    new = (s.pos_x, s.pos_z)
    disp = math.hypot(new[0] - old[0], new[1] - old[1])
    ok, why = genuine_clip(old, new)
    return dict(old=old, new=new, facing=fac, spF=spF, disp=disp, ok=ok, why=why,
                rho=perp_dist_to_S(old, fac))


def snapshot_walk(sticks, nmax=18):
    """Walk the rest seed (C-down), returning a clone at the START of each frame (so all cut frames N
    come from one walk)."""
    s = seed()
    snaps = []
    for k in range(nmax):
        snaps.append(s.clone())
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=CDOWN)
    return snaps


def fast_cut(old_x, old_z, facing, nspeed, travel=None):
    """The CUT_F entry lunge -- BIT-IDENTICAL to the dispatch-frame enter_cut but ~20x cheaper (no
    clone, no J3D keyframe eval). Delegates to SeamGeo.cut_new with the runtime walk `facing`,
    per-frame `nspeed`, and the DISPATCH-frame `travel` (the walk travel AFTER that frame's
    setSpeedAndAngleNormal chase -- the foot term fires along it, session 75; the walk's own next
    step() runs the identical chase, so callers read it off the walking state one frame later).
    `travel=None` assumes travel==facing (exact only for a converged walk). Returns (new_x, new_z)."""
    return sg().cut_new((old_x, old_z), facing=facing, speedf=nspeed, travel=travel)


def cut_at(snap, dstick, aim=None):
    """Cut from a walk snapshot via the dispatch frame (`dstick` = the frame's controller stick)."""
    c = snap.clone()
    old = (c.pos_x, c.pos_z)
    try:
        c.enter_cut_from_move(dstick[0], dstick[1], csx=128, csy=CDOWN, cut_type=CUT_F, aim=aim)
    except Exception:
        return None
    fac, spF = c.facing, c.speedF
    new = (c.pos_x, c.pos_z)
    ok, why = genuine_clip(old, new)
    return dict(old=old, new=new, facing=fac, spF=spF,
                disp=math.hypot(new[0] - old[0], new[1] - old[1]),
                ok=ok, why=why, rho=perp_dist_to_S(old, fac))


def perp_ray(old, new):
    """Signed perpendicular distance from S to the ACTUAL cut ray old->new (delegates to the seam's
    SeamGeo.perp_to_ray). ~0 for a clip. The correct razor quantity (unlike `perp_dist_to_S`, a rough
    label). A clip needs |perp_ray| inside the seam's ~2e-4u f32 sliver at the walk facing."""
    return sg().perp_to_ray(old, new)


def target_rho():
    """Signed cut-ray offset of the exact physical witness selected by the live finder."""
    global _TARGET_RHO
    if TARGET_OLD is None:
        return 0.0
    if _TARGET_RHO is None:
        new = sg().cut_new(
            TARGET_OLD, facing=TARGET_FACING, speedf=17.0, travel=TARGET_FACING
        )
        _TARGET_RHO = perp_ray(TARGET_OLD, new)
    return _TARGET_RHO


def perp_margin(old, new):
    """Delivery-robustness metric: the contiguous perp half-window at `old` (fresh in-line lunge), in
    +-2e-5u steps -- how far `old` can shift PERPENDICULAR and still clip. Ranks hits: a bigger margin
    is a wider f32 sliver (more forgiving). The from-rest sim is 0-ULP (session 31 sword fix), so the
    live `old` lands exactly on the sim's, and any positive-margin hit delivers (session 32 shipped a
    margin-5 hit); the margin just picks the safest column."""
    a = math.atan2(new[0] - old[0], new[1] - old[1])
    pdx, pdz = -math.cos(a), math.sin(a)
    lunge = (_f(new[0] - old[0]), _f(new[1] - old[1]))

    def clips(k):
        o2 = (_f(old[0] + _f(k * 2e-5 * pdx)), _f(old[1] + _f(k * 2e-5 * pdz)))
        n2 = (_f(o2[0] + lunge[0]), _f(o2[1] + lunge[1]))
        return genuine_clip(o2, n2)[0]

    if not clips(0):
        return -1
    p = 0
    while p < 40 and clips(p + 1):
        p += 1
    n = 0
    while n < 40 and clips(-(n + 1)):
        n += 1
    return min(p, n)


# --- the dust solver (ported from harness.rollstab.solver; walk-N-then-cut form) -----------------
_BEAR_S = None
CRAWLS = ((0.72, 0.72), (0.6, 0.72), (0.72, 0.6), (0.66, 0.66), (0.6,))
LEADS_DURS = ((5, 3), (4, 3), (5, 2), (4, 2))
OFFS = (800, 900, 1000, 700, 600, 1100, 400, 0)
# HITS_PATH / GOLDEN_PATH are set by configure() (session 72) -- namespaced per seam `name`.

_BOUNDS = None


def bounds():
    """The search-region bounds, DERIVED per-seam (session 49) -- NO kaze-hardcoded d2S / N windows.
    Which candidates are truly REACHABLE is decided by the walled physics re-sim (`_wall_faithful`,
    Dereck's session-49 call); these bounds only FOCUS the search, and every accept is the exact
    genuine test -- so a generous, seam-general window is correct. Returns a dict:
      * WIN_LO/WIN_HI: the distance-to-S bracket = the seam's derived reach band at the walk cap
        (`sg().search_band(speedf=17)`) -- a general relative bracket around the lunge reach, not a
        typed distance ([[no-overtuned-constants]]).
      * NLO/NHI/NMAX: the walk-frame range where the baseline cruise walk's d2S enters the reach
        band, widened for the crawl streams' start-delay (a crawl covers less ground early, so it
        reaches the band a few frames LATER). Derived from the baseline trajectory + WIN_HI.
      * PERP_GATE: the coarse |perp_ray| pre-filter for the exact test -- a small general multiple of
        the reach (~the f32 razor, ~2e-4u). Real acceptance is the exact genuine_clip; this prunes."""
    global _BOUNDS
    if _BOUNDS is None:
        g = sg()
        lo, hi = g.search_band(speedf=17.0)
        cs = seed().csangle
        cruise = _sfbd(search_bearing(), cs, 1.0)
        n_cross = None
        for (N, ox, oz, fac, nsp, trv) in _walk_fast([cruise] * 24, 22):
            if math.hypot(g.S[0] - ox, g.S[1] - oz) <= hi:
                n_cross = N
                break
        n_cross = n_cross or 12
        nlo = max(2, n_cross - 2)              # edge frame + start-delay slack (seam-general)
        nhi = n_cross + 4                      # a K=3 crawl reaches the band up to ~4 frames later
        _BOUNDS = dict(WIN_LO=lo, WIN_HI=hi, NLO=nlo, NHI=nhi, NMAX=nhi, PERP_GATE=hi * 1.5e-4)
    return _BOUNDS


def bear_to_S():
    """Bearing from the anchor's start to S (s16) -- centers the beta sweep (no hardcode)."""
    global _BEAR_S
    if _BEAR_S is None:
        s = seed()
        _BEAR_S = int((math.atan2(SEAM[0] - s.pos_x, SEAM[1] - s.pos_z) % (2 * math.pi))
                      / (2 * math.pi) * 65536)
    return _BEAR_S


def search_bearing():
    """Walking direction selected by the physical dust scan, or Link->S for legacy callers."""
    return bear_to_S() if TARGET_FACING is None else TARGET_FACING


def facing_allowed(angle):
    angle = int(angle) & 0xFFFF
    return (ANGLE_LO <= angle <= ANGLE_HI if ANGLE_LO <= ANGLE_HI
            else angle >= ANGLE_LO or angle <= ANGLE_HI)


def check_runway(verbose=True):
    """MINT GUARD (session 72): does the freshly-minted anchor have enough runway to reach the walk
    cap (speedF 17) BEFORE Link enters the cut/reach band? A walk-stab clips only from the FULL
    ~40.22u reach -- speedF == 17 at the cut is the tier's hard gate -- so if the rest sits too close
    to S the walk never caps and NO genuine clip exists (the 'too close to the seam, never enough
    speed' failure). This runs the straight from-rest walk (aim = bear_to_S) offline and checks the
    speedF at the frame Link first enters the reach band (d2S <= WIN_HI). DERIVED, no magic distance:
    the requirement IS 'capped before the band' ([[no-overtuned-constants]]). Also reports the rest's
    signed |perp| off the aim line (the arc knob reaches only ~9u, so a large perp is its own warning).
    Returns (ok, msg, info). mint_walkstab calls it so a doomed anchor is flagged BEFORE a live
    REST-gate run is wasted on it."""
    B = bounds()
    WIN_HI = B['WIN_HI']
    g = sg()
    s = seed()
    s._foot.skip_cruise_pose = True
    rest_perp = g.perp((s.pos_x, s.pos_z))
    rest_d2S = math.hypot(SEAM[0] - s.pos_x, SEAM[1] - s.pos_z)
    cruise = _sfbd(search_bearing(), s.csangle, 1.0)
    entry = None
    for N in range(1, 24):
        s.step(cruise[0], cruise[1], csx=128, csy=CDOWN)
        if math.hypot(SEAM[0] - s.pos_x, SEAM[1] - s.pos_z) <= WIN_HI:
            entry = (N, math.hypot(SEAM[0] - s.pos_x, SEAM[1] - s.pos_z), s.speedF)
            break
    if entry is None:
        ok = False
        msg = ('runway UNKNOWN: the straight from-rest walk never reached the reach band '
               '(d2S<=%.1f) within 23 frames from rest d2S=%.1f -- mint CLOSER to S' % (WIN_HI, rest_d2S))
    else:
        N, d2s_e, spF = entry
        ok = spF >= 16.99          # capped == the full ~40.22u reach available at the cut
        if ok:
            msg = ('rest OK: speedF=%.2f CAPPED at reach-band entry (d2S=%.1f<=%.1f, N=%d); '
                   'rest d2S=%.1f perp=%+.1f' % (spF, d2s_e, WIN_HI, N, rest_d2S, rest_perp))
        else:
            msg = ('MINT GUARD FAILED -- REST TOO CLOSE TO S: speedF only %.2f at reach-band entry '
                   '(d2S=%.1f<=%.1f, N=%d) -- the walk never caps to 17 before the cut zone, so NO '
                   'clip is reachable. Mint FARTHER from S (current rest d2S=%.1f, perp=%+.1f).'
                   % (spF, d2s_e, WIN_HI, N, rest_d2S, rest_perp))
    if verbose:
        print('[runway] %s' % msg, flush=True)
    return ok, msg, dict(rest_d2S=rest_d2S, rest_perp=rest_perp, entry=entry, WIN_HI=WIN_HI)


def _dtm(stk):
    return C.dtm_stick(stk)


# stick_for_bearing runs a per-call bisection (~650 main_stick_decode calls); it is a PURE function of
# (bearing, cs, mag) requested millions of times, so memoizing it is the dominant search speedup.
_SFB_CACHE = {}
_SFBD_CACHE = {}


def _sfb(bearing, cs, mag):
    k = (bearing & 0xFFFF, cs, mag)
    v = _SFB_CACHE.get(k)
    if v is None:
        v = stick_for_bearing(bearing & 0xFFFF, cs, mag)
        _SFB_CACHE[k] = v
    return v


def _sfbd(bearing, cs, mag):
    """Delivered (calibrated) stick for a bearing -- _dtm(_sfb(...)), memoized."""
    k = (bearing & 0xFFFF, cs, mag)
    v = _SFBD_CACHE.get(k)
    if v is None:
        v = _dtm(_sfb(bearing, cs, mag))
        _SFBD_CACHE[k] = v
    return v


def build_stream(beta, crawl_msds, off, lead, dur, fframe=None, fdx=0, fdz=0):
    """Walk stream (DELIVERY-FAITHFUL): [start-crawl msds] + full-mag cruise at `beta`, a bearing ARC
    (off-aim `off` for `dur` frames at `lead`, the gross perp knob), and an optional per-byte FINE
    nudge (fdx,fdz) at `fframe` -- THE fine f32-lottery (bearing->stick octagon-clamping makes `off`
    coarse). The nudge is applied to the AUTHORED (raw) stick byte, clamped to [0,255] (a DTM cannot
    deliver out-of-range), THEN the whole stream is run through dtm_make's delivery calibration
    (`_dtm`: 255->254, 0->1) -- so the sim sims exactly the bytes the clean DTM delivers (README model
    term #6). Nudging a post-calibration byte instead can overflow the [0,255] range and desync
    sim-vs-delivered on the 0/255 edges."""
    cs = seed().csangle
    raw = [_sfb(beta, cs, m) for m in crawl_msds] + [_sfb(beta, cs, 1.0)] * 30
    araw = _sfb((beta + off) & 0xFFFF, cs, 1.0)
    for d in range(dur):
        raw[lead + d] = araw
    if fframe is not None and (fdx or fdz):
        b = raw[fframe]
        raw[fframe] = (min(255, max(0, b[0] + fdx)), min(255, max(0, b[1] + fdz)))
    return [_dtm(r) for r in raw]


def _cut_all(sticks, base, base_k):
    """Continue the C-down walk from `base` (already `base_k` frames in) to NMAX, cutting in-window.
    FAST PATH: skip the cruise foot pose (bit-exact for walk-then-cut) and cut via the cached-lunge
    `fast_cut` (no clone, no J3D eval) -- both are 0-ULP vs the full engine (see fast_cut / the
    skip_cruise_pose flag). Reads (old, facing, nspeed) straight off the walking state per frame."""
    B = bounds()
    NMAX = B['NMAX']
    s = base.clone()
    s._foot.skip_cruise_pose = True
    rows = []             # (k, pos after frame k)
    dispatch = {}         # k -> (facing, nspeed, travel) after frame k+1's chase (session 75)
    prev = None
    for k in range(base_k, NMAX + 2):
        rows.append((k, s.pos_x, s.pos_z))
        if prev is not None:
            dispatch[prev] = (s.facing, s.nspeed, s.travel)
        prev = k
        if k <= NMAX:
            stk = sticks[k] if k < len(sticks) else sticks[-1]
            s.step(stk[0], stk[1], csx=128, csy=CDOWN)
    out = []
    for (k, ox, oz) in rows:
        if k < B['NLO'] or k not in dispatch:
            continue
        dd = math.hypot(SEAM[0] - ox, SEAM[1] - oz)
        if not (B['WIN_LO'] <= dd <= B['WIN_HI']):
            continue
        fac, nsp, trv = dispatch[k]
        old = (ox, oz)
        nx, nz = fast_cut(ox, oz, fac, nsp, trv)
        new = (nx, nz)
        ok, why = genuine_clip(old, new)
        out.append((k, dd, dict(old=old, new=new, facing=fac,
                                disp=math.hypot(nx - ox, nz - oz), ok=ok, why=why)))
    return out


def _beta_spiral(center, half, step):
    yield center
    d = step
    while d <= half:
        yield center + d
        yield center - d
        d += step


def solve(budget=110.0, want=20, verbose=True):
    """LEGACY K<=2 dust search (kept as `solve_legacy` for the record). Enumerates C-down walk streams
    (beta spiral | crawl | arc | per-byte fine nudge at an arc frame | N) and tests the EXACT
    genuine_clip. SUPERSEDED by `solve_focused`: its CRAWLS are K<=2 and its fine knobs (arc `off`,
    the arc-frame byte nudge) are FULL-MAG and octagon-CLAMP, so the reachable perp lattice floors
    ~1.3e-3u (~13x the razor) and it finds 0 in the corrected sim. `solve_focused` uses a K=3 crawl
    with an octagon-INTERIOR byte-nudged 3rd frame (the fine perp fill) + a wall-faithful gate."""
    t0 = time.time()
    c = bear_to_S()
    if verbose:
        print('bearing Link->S=%d; spiral beta around %d' % (c, c - 24), flush=True)
    clips, seen = [], set()
    for beta in _beta_spiral(c - 24, 40, 2):
        if time.time() - t0 > budget or len(clips) >= want:
            break
        cs = seed().csangle
        cruise = _sfbd(beta, cs, 1.0)
        for crawl in CRAWLS:
            crawl_sticks = [_sfbd(beta, cs, m) for m in crawl]
            for (lead, dur) in LEADS_DURS:
                base = seed()
                pre = crawl_sticks + [cruise] * 30
                for k in range(lead):
                    base.step(pre[k][0], pre[k][1], csx=128, csy=CDOWN)
                for off in OFFS:
                    for fframe in range(lead, lead + dur):
                        for fdx in range(-4, 5):
                            for fdz in range(-4, 5):
                                sticks = build_stream(beta, crawl, off, lead, dur, fframe, fdx, fdz)
                                for (N, dd, r) in _cut_all(sticks, base, lead):
                                    if r['ok']:
                                        key = (round(r['old'][0], 5), round(r['old'][1], 5))
                                        if key not in seen:
                                            seen.add(key)
                                            clips.append(dict(
                                                beta=beta, crawl=list(crawl), off=off, lead=lead,
                                                dur=dur, fframe=fframe, fdx=fdx, fdz=fdz, N=N,
                                                d2S=dd, old=list(r['old']), new=list(r['new']),
                                                facing=r['facing'], disp=r['disp'],
                                                perp=perp_ray(r['old'], r['new'])))
                    if time.time() - t0 > budget or len(clips) >= want:
                        break
                if time.time() - t0 > budget or len(clips) >= want:
                    break
            if time.time() - t0 > budget or len(clips) >= want:
                break
    for h in clips:
        h['margin'] = perp_margin(h['old'], h['new'])
    clips.sort(key=lambda h: -h['margin'])
    os.makedirs(os.path.dirname(HITS_PATH), exist_ok=True)
    json.dump(clips, open(HITS_PATH, 'w'), indent=1)
    if verbose:
        print('%d unique clips in %.1fs -> %s. top by perp margin:'
              % (len(clips), time.time() - t0, HITS_PATH), flush=True)
        for h in clips[:8]:
            print('  margin=%d beta=%d crawl=%s arc(off=%+d,l%d,d%d) fine(f%d,%+d,%+d) N=%d d2S=%.2f '
                  'facing=%d disp=%.3f old=(%.6f,%.6f)'
                  % (h['margin'], h['beta'], h['crawl'], h['off'], h['lead'], h['dur'], h['fframe'],
                     h['fdx'], h['fdz'], h['N'], h['d2S'], h['facing'], h['disp'],
                     h['old'][0], h['old'][1]))
    return clips


# --- the FOCUSED K=3 search (session 32): the objective-compliant one-shot ---
# Why K=3 + an octagon-interior byte nudge beats solve()'s K<=2: see solve_focused's docstring + KB walk-stab.
_BASE_WALLED = None
# PERP_GATE_F / NLO_F / NHI_F are now DERIVED per-seam via bounds() (session 49) -- see bounds().


def seed_walled():
    """Rest seed WITH the local seam walls in the stepper (Phase W CrrPos), so the walk BRAKES exactly
    as live does. Used to reject wall artifacts: a cut whose walk touched a wall (`wall_hit`) has an
    `old` the wall-less sim overshot (dead-end #28); only a wall_hit==False walk is faithful (its old
    is bit-identical to the wall-less walk, so the fast wall-less search is exact for accepted hits)."""
    global _BASE_WALLED
    if _BASE_WALLED is None:
        _BASE_WALLED = C.rest_state(ANCHOR, walls=sg().TRIS, dtm_seed=DTM_SEED)
    return _BASE_WALLED.clone()


def _walk_fast(sticks, nmax):
    """Wall-less C-down walk from rest with the cruise pose skipped (bit-exact for walk-then-cut).
    Yields (N, old_x, old_z, facing, nspeed, travel) for each frame N=1..nmax, where old_* is the
    position after frame N and (facing, nspeed, travel) are the CUT-DISPATCH-frame values: the state
    after frame N+1's setSpeedAndAngleNormal chase. The walk's own next step() runs the identical
    procMove prefix, so they are read off the walking state one frame later at zero extra cost
    (session 75: the entry foot term fires along the chased travel, not the frame-N travel)."""
    s = seed(); s._foot.skip_cruise_pose = True
    prev = None
    for k in range(nmax + 1):
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=CDOWN)
        if prev is not None:
            yield (prev[0], prev[1], prev[2], s.facing, s.nspeed, s.travel)
        prev = (k + 1, s.pos_x, s.pos_z)


def _wall_faithful(sticks, N):
    """Re-sim the walk WITH walls; return the walled (old, new, facing, speedF) iff no wall was hit
    through frame N (so `old` is the true pre-brake position). None if a wall braked the walk (the
    wall-less `old` is an overshoot -> a delivery would MISS: dead-end #28). The cut runs the EXACT
    dispatch-frame path (`enter_cut_from_move`, consuming sticks[N]) -- this is the authoritative
    accept the fast one-frame-lag filter approximates."""
    s = seed_walled()
    for k in range(N):
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=CDOWN)
        if getattr(s, 'wall_hit', False):
            return None
    old = (s.pos_x, s.pos_z)
    dstk = sticks[N] if N < len(sticks) else sticks[-1]
    try:
        s.enter_cut_from_move(dstk[0], dstk[1], csx=128, csy=CDOWN)
    except Exception:
        return None
    return old, (s.pos_x, s.pos_z), s.facing, s.speedF


def _stream_k3(cs, c1, c2, c3d, cruise):
    return [c1, c2, c3d] + [cruise] * 30


def _stream_k(coarse, mid, last, cruise):
    """A K = len(coarse)+len(mid)+1 start-crawl stream (session 72 generalization of `_stream_k3`):
    the two COARSE-swept crawl frames, then k-3 FIXED middle crawl frames (empty for k=3), then the
    byte-NUDGED last crawl frame, then the cruise hold. Byte-identical to `_stream_k3` at k=3
    (coarse=[c1,c2], mid=[], last=c3d)."""
    return list(coarse) + list(mid) + [last] + [cruise] * 30


def _band_perp(sticks, N_only=None):
    """Walk `sticks` wall-less and return (min|perp_ray|, best_N, snap) over the reach-band frames
    (d2S in [WIN_LO,WIN_HI], N in [NLO,NHI]); `snap`=(ox,oz,fac,nsp) at best_N. The cheap perp
    predictor the auto-refine minimizes. (None,None,None) if no frame lands in the band."""
    B = bounds()
    best = (1e18, None, None)
    for (N, ox, oz, fac, nsp, trv) in _walk_fast(sticks, B['NHI']):
        if not (B['NLO'] <= N <= B['NHI']):
            continue
        if N_only is not None and N != N_only:
            continue
        if not (B['WIN_LO'] <= math.hypot(SEAM[0] - ox, SEAM[1] - oz) <= B['WIN_HI']):
            continue
        rho = perp_ray((ox, oz), fast_cut(ox, oz, fac, nsp, trv))
        pr = abs(rho - target_rho()) if TARGET_OLD is not None else abs(rho)
        if pr < best[0]:
            best = (pr, N, (ox, oz, fac, nsp, trv))
    return best


def _graze_aim(verbose=False):
    """AUTO-find the grazing cruise aim (session 72) -- the piece that killed the per-seam manual
    `cruise_off` hand-tuning ([[oneshot-no-manual-tweaking]]). The cut ray's |perp to S| is a smooth,
    unimodal function of the cruise-walk azimuth near a corner (a near-flat seam grazes toward S; a
    sharp corner aims into it), so a coarse sweep + hill-descent finds the perp-minimizing aim with NO
    hand-picked offset or sign. Objective = the straight-cruise walk's min band |perp_ray| (no crawl,
    cheap). Returns the best cruise_beta (s16)."""
    cs = seed().csangle
    c0 = search_bearing()

    def obj(cb):
        # the CENTERED k=3 crawl stream's band |perp| (a1=a2=cb, Phase A's center point) -- NOT bare
        # cruise: the partial-mag crawl frames shift the trajectory, moving the perp-min aim.
        cbm = int(cb) & 0xFFFF
        return _band_perp(_stream_k([_sfbd(cbm, cs, 0.66), _sfbd(cbm, cs, 0.72)], [],
                                    _dtm(_sfb(cbm, cs, 0.66)), _sfbd(cbm, cs, 1.0)))[0]

    best_cb = min(range(c0 - 1600, c0 + 1601, 80), key=obj)     # coarse sweep (both signs)
    best_p = obj(best_cb)
    for st in (40, 16, 6, 2, 1):                                # hill-descent refine
        moved = True
        while moved:
            moved = False
            for cb in (best_cb - st, best_cb + st):
                p = obj(cb)
                if p < best_p:
                    best_p, best_cb, moved = p, cb, True
    if verbose:
        print('  auto-graze: cruise_beta=%d (%+d off bear_to_S) straight |perp|=%.6f'
              % (best_cb, best_cb - c0, best_p), flush=True)
    return best_cb & 0xFFFF


def solve_focused(budget=110.0, want=30, verbose=True, ks=(3, 4)):
    """SELF-ADAPTIVE one-shot walk-stab dust search (pure sim, no calibration, NO per-seam tuning --
    [[oneshot-no-manual-tweaking]]). The freeze-solver pattern (cheap perp predictor + bracket + exact
    bit-confirm + wall-faithful gate), with every knob the tool USED to need by hand now searched:

      0. AUTO-GRAZE (`_graze_aim`): 1D-minimize the cruise-walk's cut-ray |perp to S| over the walk
         azimuth -> the grazing aim, no hand-picked `cruise_off`/sign.
      A. Coarse brackets: at the grazed aim, sweep the 2 crawl-frame aims (a1,a2)x mags, rank each by
         its centered-c4 band |perp_ray| (the cheap predictor). ALL brackets are kept, sorted.
      B/C. BREADTH exact-genuine drill (session 73): per bracket, IN cheap-perp order until `want` hits
         or the budget, drill the last crawl frame's byte (c4) over its 2D range AT THE BRACKET'S OWN
         AIMS and test the EXACT genuine_clip, then the walled re-sim (accept only wall_hit==False --
         old is the true pre-brake position, speedF still capped -> the >35u WallCorrect clearance).
         NO hill-descent: minimizing the cheap perp predictor lands on the perp-MIN f32 cell, which is
         NOT genuine, and steers off the genuine dust one lattice cell over (the dead-end #41 greedy
         trap; #61) -- breadth over brackets + the exact test threads the razor where greedy floors it.
         The c4 2D lattice's perp swing is several u, so its incommensurate byte steps fill the reach
         to the ~1e-4 razor at a good bracket ([[no-overtuned-constants]]).
      * AUTO crawl-length retry: try each k in `ks` until hits (K=3 base; K=4 adds along phase for a
        rest whose walk is long -- the k-3 middle frames held at the 0.66-mag grazed crawl).

    Rank by perp_margin (delivery robustness). Writes ranked hits (explicit delivered `sticks` + N for
    deliver()) to HITS_PATH. Caller passes NOTHING per-seam: feed a corner, get the clip inputs."""
    t0 = time.time()
    B = bounds()
    NLO_F, NHI_F = B['NLO'], B['NHI']
    cs = seed().csangle
    # The live finder supplies the physical dust facing used to build this runway. Legacy callers
    # perform the same shared feasibility scan here before searching.
    from harness.rollstab.seam_feasibility import best_walk_aim
    if FEASIBILITY is None:
        bF, ntot, nsafe, _safe = best_walk_aim(
            sg(), speedf=17.0, min_clearance=35.0, fstep=2048, budget=25.0,
            verbose=False, angle_lo=ANGLE_LO, angle_hi=ANGLE_HI,
        )
    else:
        bF, ntot, nsafe, _safe = FEASIBILITY
    if ntot == 0 or nsafe == 0:
        if verbose:
            reason = ('NO genuine walk-cap dust in the selected angle range' if ntot == 0 else
                      'genuine dust exists, but none is outside Link\'s wall-collision radius')
            print('solve_focused: %s -- no physical walking-slash runway.' % reason, flush=True)
        os.makedirs(os.path.dirname(HITS_PATH), exist_ok=True)
        json.dump([], open(HITS_PATH, 'w'))
        return []
    if verbose:
        print('feasible: richest dust aim F=%d (%.1fdeg) genuine=%d walk-reachable=%d (%.1fs)'
              % (bF, bF / 65536 * 360, ntot, nsafe, time.time() - t0), flush=True)
    if TARGET_FACING is None:
        cb = _graze_aim(verbose)
    else:
        # The live finder already refined this to a DTM-stable facing with exact safe dust.
        cb = search_bearing()
        if verbose:
            print('  controller-stable cruise_beta=%d (physical dust target)' % cb, flush=True)
    cruise = _sfbd(cb, cs, 1.0)
    c3base = _sfb(cb, cs, 0.66)
    c3base_d = _dtm(c3base)
    clips, seen = [], set()
    for k in ks:
        if clips or time.time() - t0 > budget:
            break
        mid = [c3base_d] * max(0, k - 3)
        # --- Phase A: enumerate crawl-aim brackets, ranked by centered-c4 band |perp_ray| ---
        brackets = []
        for a1 in range(cb - 1600, cb + 1601, 160):
            for m1 in (0.6, 0.66, 0.72):
                c1 = _sfbd(a1, cs, m1)
                for a2 in range(cb - 1600, cb + 1601, 160):
                    for m2 in (0.6, 0.72):
                        c2 = _sfbd(a2, cs, m2)
                        pr, N, _ = _band_perp(_stream_k([c1, c2], mid, c3base_d, cruise))
                        if N is not None:
                            brackets.append((pr, a1, m1, a2, m2))
        brackets.sort(key=lambda b: b[0])
        if verbose:
            print('Phase A (k=%d, cb=%d): %d brackets, best witness-rho error=%.6f (%.1fs)'
                  % (k, cb, len(brackets), brackets[0][0] if brackets else -1,
                     time.time() - t0), flush=True)
        # --- Phase B/C: BREADTH exact-genuine c4 drill at EACH bracket's OWN aims (no hill-descent
        #     -- see the docstring: greedy perp-min lands on the non-genuine perp-min cell). ---
        for (pc, a1, m1, a2, m2) in brackets:
            if time.time() - t0 > budget or len(clips) >= want:
                break
            c1 = _sfbd(a1, cs, m1)
            c2 = _sfbd(a2, cs, m2)
            # ALONG: drill the last crawl frame's byte over its 2D range; the incommensurate perp
            # steps fill the reach to the razor, and the EXACT genuine_clip is the accept.
            for dz in range(-14, 15):
                for dx in range(-7, 8):
                    if time.time() - t0 > budget or len(clips) >= want:
                        break
                    c4 = _dtm((min(254, max(1, c3base[0] + dx)), min(254, max(1, c3base[1] + dz))))
                    sticks = _stream_k([c1, c2], mid, c4, cruise)
                    pr, N, snap = _band_perp(sticks)
                    if N is None or pr >= B['PERP_GATE'] or snap is None:
                        continue
                    ox, oz, fac, nsp, trv = snap
                    nx, nz = fast_cut(ox, oz, fac, nsp, trv)
                    if not genuine_clip((ox, oz), (nx, nz))[0]:
                        continue
                    wf = _wall_faithful(sticks, N)              # Phase C: reject wall artifacts
                    if wf is None:
                        continue
                    (wox, woz), (wnx, wnz), wfac, wsp = wf
                    if not facing_allowed(wfac):
                        continue
                    if not genuine_clip((wox, woz), (wnx, wnz))[0]:
                        continue
                    key = (round(wox, 5), round(woz, 5))
                    if key in seen:
                        continue
                    seen.add(key)
                    clips.append(dict(sticks=[list(sk) for sk in sticks[:18]], N=N,
                                      a1=a1, m1=m1, a2=a2, m2=m2, c3dx=dx, c3dz=dz, k=k,
                                      cruise_beta=cb, old=[wox, woz], new=[wnx, wnz],
                                      facing=wfac, speedF=wsp,
                                      margin=perp_margin((wox, woz), (wnx, wnz)),
                                      d2S=math.hypot(SEAM[0] - wox, SEAM[1] - woz),
                                      perp=perp_ray((wox, woz), (wnx, wnz))))
    clips.sort(key=lambda h: -h['margin'])
    os.makedirs(os.path.dirname(HITS_PATH), exist_ok=True)
    json.dump(clips, open(HITS_PATH, 'w'), indent=1)
    if verbose:
        print('%d wall-faithful clips in %.1fs -> %s. top by perp margin:'
              % (len(clips), time.time() - t0, HITS_PATH), flush=True)
        for h in clips[:8]:
            print('  margin=%d k=%d N=%d a1=%d a2=%d c4=(%+d,%+d) d2S=%.2f perp=%+.6f old=(%.6f,%.6f)'
                  % (h['margin'], h['k'], h['N'], h['a1'], h['a2'], h['c3dx'], h['c3dz'],
                     h['d2S'], h['perp'], h['old'][0], h['old'][1]))
    return clips


def reachability(beta=5730, mag=1.0, nmax=15):
    """Print the C-down walk's per-frame (facing, speedF, old_d2S, rho) at aim `beta` -- the map the
    solver threads. facing settles at the stick-decode-quantized aim; `rho` at the along-correct
    frame is the razor to thread with the arc."""
    cr = stick_for_bearing(beta, seed().csangle, mag)
    snaps = snapshot_walk([cr] * (nmax + 1), nmax=nmax + 1)
    print('aim beta=%d mag=%.2f  (facing settles at the quantized decode)' % (beta, mag))
    for N in range(2, nmax):
        r = cut_at(snaps[N], cr)
        if r is None:
            continue
        d2S = math.hypot(SEAM[0] - r['old'][0], SEAM[1] - r['old'][1])
        print('  N=%-2d facing=%d spF=%6.3f old_d2S=%6.2f rho=%+.4f disp=%.3f %s'
              % (N, r['facing'], r['spF'], d2S, r['rho'], r['disp'], r['why']))


def deliver(hit=None, b_frame=None, log_n=40, norelaunch=False, verbose=True, save_golden=True,
            dtm_seed=None):
    """LIVE clean-DTM delivery of a solver hit (C-down every frame; NEVER advancewith). Authors the
    hit's walk stream + a B edge at `b_frame` (the 4-frame item put-away delay + 1-frame DTM buffering
    fires CUT_F at frame N), logs per frame, and diffs vs the from-rest sim. Reports the walk residual,
    where CUT_F fires, whether `old_live` clips genuine (bit-exact from rest), and whether Link goes
    OOB (`pos_y` drops below the floor -- the definitive clip signal; a post-cut proc that is neither
    an idle nor the recoil also flags it). Per-frame diff -> never guess the B frame; read the divergence.

    `dtm_seed` (session 72): the make_dtm leading-poll layout the DTM is delivered with, threaded to
    BOTH the authored movie AND the from-rest sim (rest_state) so they align. It MUST match the seed
    the anchor's REST gate verified BIT-EXACT: a freshly-minted (mint_walkstab/mint_current) anchor is
    bit-exact at seed=0 (noops = rest_noops + 1), so DEFAULT 0. The old default (1) delivered a novel
    anchor's walk 1 frame off -> `old` ~1u past the razor -> the CUT_F lunge CrrPos-blocks (found by a
    per-frame delivery diff, not a guess -- the [[run-dtm 1-frame jitter]] seed fix).

    Returns 0 (clip confirmed live) / 2 (cut fired but no clip) / 1 (no CUT fired). Reads the top hit
    from HITS_PATH if `hit` is None; saves the live golden on a confirmed clip."""
    from harness.dtm.run_dtm import run_dtm, land_ready
    B_BTN = 0x200
    if dtm_seed is None:
        dtm_seed = DTM_SEED           # the anchor's REST-bit-exact seed (configure): kaze 1, novel 0
    if hit is None:
        hit = json.load(open(HITS_PATH))[0]
    # New (solve_focused) hits carry the explicit delivered `sticks`; legacy hits carry build_stream params.
    if 'sticks' in hit:
        sticks = [tuple(sk) for sk in hit['sticks']]
    else:
        sticks = build_stream(hit['beta'], tuple(hit['crawl']), hit['off'], hit['lead'], hit['dur'],
                              hit['fframe'], hit['fdx'], hit['fdz'])
    N = hit['N']
    if b_frame is None:
        # Sword-aware B-frame (KB walk-stab.md): sword OUT has no equip delay -> B at N-1; sheathed /
        # an item held runs the 4-frame put-away (lower body keeps walking) -> B at N-5. CUT_F at N.
        seed = C.G.load_seed(ANCHOR)
        sword_out = bool(seed.get('sword_drawn', seed.get('equip_item', 0x103) == 0x103))
        b_frame = (N - 1) if sword_out else (N - 5)
    s = C.rest_state(ANCHOR, dtm_seed=dtm_seed)
    rows = []
    for k in range(N):
        s.step(sticks[k][0], sticks[k][1], csx=128, csy=CDOWN)
        rows.append((s.pos_x, s.pos_z, s.facing & 0xFFFF))
    sold = (s.pos_x, s.pos_z)
    dstk = sticks[N] if N < len(sticks) else sticks[-1]
    s.enter_cut_from_move(dstk[0], dstk[1], csx=128, csy=CDOWN)   # the dispatch-frame cut (s75)
    snew = (s.pos_x, s.pos_z)
    if verbose:
        print('SIM hit: old=(%.7f,%.7f) new=(%.7f,%.7f) genuine=%s' %
              (sold[0], sold[1], snew[0], snew[1], genuine_clip(sold, snew)))
    dtm = [dict(stickX=sticks[k][0] if k < len(sticks) else sticks[-1][0],
                stickY=sticks[k][1] if k < len(sticks) else sticks[-1][1],
                substickX=128, substickY=CDOWN, buttons=(B_BTN if k == b_frame else 0))
           for k in range(18)]
    dtm += [dict(stickX=128, stickY=128, substickX=128, substickY=CDOWN, buttons=0)] * 90
    end = run_dtm(dtm, anchor=ANCHOR, ready=land_ready, relaunch_dolphin=not norelaunch,
                  log_frames=log_n, verbose=verbose, seed=dtm_seed)
    live = end['log']
    cut_i = next((i for i, f in enumerate(live) if f['proc'] == 0x42), None)
    if cut_i is None:
        print('NO CUT_F (0x42) -- adjust b_frame'); return 1
    lold = (live[cut_i - 1]['pos_x'], live[cut_i - 1]['pos_z'])
    lnew = (live[cut_i]['pos_x'], live[cut_i]['pos_z'])
    gen, why = genuine_clip(lold, lnew)
    tail = live[cut_i:]
    # OOB clip signal: Link's world Y drops below the floor (LINK_Y) as he falls through the seam.
    oob = any(f.get('pos_y', LINK_Y) < LINK_Y - 2.0 for f in tail)
    if verbose:
        print('LIVE CUT_F@f%d: old=(%.7f,%.7f) new=(%.7f,%.7f) genuine=%s(%s) OOB=%s'
              % (cut_i, lold[0], lold[1], lnew[0], lnew[1], gen, why, oob))
        for i, f in enumerate(tail[:16]):
            print('   +%-2d proc=0x%02x state=%d pos=(%.2f,%.2f) y=%.2f' %
                  (i, f['proc'] & 0xFF, f['state'], f['pos_x'], f['pos_z'], f.get('pos_y', 0.0)))
        print('  %s' % ('*** WALK-STAB CLIP CONFIRMED LIVE (OOB) ***' if (gen and oob) else
                        ('cut fired, genuine=%s oob=%s -- inspect the tail' % (gen, oob))))
    ok = gen and oob
    if ok and save_golden:
        import copy
        gold = dict(anchor=ANCHOR, hit=copy.deepcopy(hit), b_frame=b_frame,
                    sim_old=list(sold), sim_new=list(snew),
                    live_cut_frame=cut_i, live_old=list(lold), live_new=list(lnew),
                    genuine=bool(gen), oob=bool(oob),
                    live_tail=[dict(proc=f['proc'] & 0xFF, state=f['state'], pos_x=f['pos_x'],
                                    pos_z=f['pos_z'], pos_y=f.get('pos_y', 0.0)) for f in tail[:20]])
        os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
        json.dump(gold, open(GOLDEN_PATH, 'w'), indent=1)
        # Mark the delivered hit in HITS_PATH so the regression gate flips xfail->PASS.
        try:
            allh = json.load(open(HITS_PATH))
            for h in allh:
                if round(h.get('old', [0, 0])[0], 4) == round(hit['old'][0], 4):
                    h['delivered'] = True
                    h['live_old'] = list(lold)
                    h['live_new'] = list(lnew)
            json.dump(allh, open(HITS_PATH, 'w'), indent=1)
        except Exception:
            pass
        if verbose:
            print('  live golden -> %s' % GOLDEN_PATH)
    return 0 if ok else 2


configure()   # default target: the kaze r11 walk-stab seam (byte-identical to the pre-s72 hardcode)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'reach'
    _kw = dict(a.split('=', 1) for a in sys.argv[2:] if '=' in a)
    # Retarget to a NOVEL seam from the CLI: anchor=<isokey> geo=<fixture> name=<slug>.
    if 'anchor' in _kw or 'geo' in _kw:
        configure(_kw.get('anchor', _KAZE_ANCHOR), _kw.get('geo', _KAZE_GEO),
                  name=_kw.get('name', 'walkstab'))
    if cmd == 'reach':
        reachability()
    elif cmd == 'solve':
        solve_focused(budget=float(_kw.get('budget', 110.0)))
    elif cmd == 'solve_legacy':
        solve()
    elif cmd == 'deliver':
        bf = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('b=')), None)
        sys.exit(deliver(b_frame=bf, norelaunch=('norelaunch' in sys.argv),
                         dtm_seed=(int(_kw['seed']) if 'seed' in _kw else None)))
