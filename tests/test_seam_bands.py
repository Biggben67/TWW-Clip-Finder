"""Derived per-seam reachability + search bands (session 49, generalization Phase-5 prerequisite).

The kaze-hardcoded numeric ranges that used to gate the solvers are now DERIVED per-seam, so a novel
seam solves via the same path with no typed-in constants ([[no-overtuned-constants]]):

  * `SeamGeo.reach` / `reach_at(speedf)` -- the lunge DISPLACEMENT (the FAR edge of the reachable
    band), computed from the cut model, not pasted.
  * `SeamGeo.search_band()` -- a general RELATIVE bracket around the reach (same seam-independent
    fractions for every seam), only FOCUSING the search.
  * `solver.wall_faithful()` -- the REACHABILITY guard (dead-end #3): the near edge is decided by a
    walled PHYSICS re-sim (Dereck's session-49 call), not a typed `old_z` band. It replaces the old
    `ZLO/ZHI`. `walkstab` already used the same walled re-sim (`_wall_faithful`).

This locks: the derivations are camera/seam-DEPENDENT (a reintroduced hardcode would fail these),
the shipped kaze roll + walk hits fall inside the derived windows, and the roll physics guard accepts
the shipped hit's reachable `old` but rejects a fabricated unreachable one.
"""
import json
import math
import os
import struct

import pytest

try:
    from harness.rollstab import solver as SV
    from harness.rollstab import walkstab as W
    from harness.rollstab import geometry as G
    from harness.rollstab.seamgeo import SeamGeo
    _rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _GEO = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json')))
    _HAVE = True
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness unavailable")


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


# The shipped seed-0 kaze roll-stab hit (matches test_solver_seam_param / test_sheathed_roll_clip).
ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'
A_PROJ, DRAW_AT, DTM_SEED = -500.0, 3, 0
MOVES = ((9, (73, 254), 2), (10, (99, 183)), (4, (96, 192)), (6, (98, 188)))
START = ((77, 249), (98, 191))
SHIPPED_OLD = (9072.208984375, 308.028076171875)


def test_reach_is_derived_not_pasted():
    """`reach` == |LUNGE| == the cut model's displacement at the roll cap (49.2202u). It moves with
    `roll_speedf` (a slower roll reaches less) -- so it is COMPUTED, not a frozen constant."""
    assert abs(G.SEAM.reach - math.hypot(*G.SEAM.LUNGE)) < 1e-9
    assert abs(G.SEAM.reach - 49.2202) < 1e-3
    slow = SeamGeo(_GEO, G.SEAM.csangle, roll_speedf=20.0)
    assert slow.reach < G.SEAM.reach          # a slower roll reaches less -> derived, not hardcoded


def test_search_band_is_relative_to_reach():
    """`search_band` is a general relative bracket around the derived reach (not a per-seam typed
    distance): the same fractions scale with reach, so a shorter-reach seam gets a proportionally
    nearer band."""
    lo, hi = G.SEAM.search_band()
    assert lo == pytest.approx(G.SEAM.reach * 0.80, rel=1e-9)
    assert hi == pytest.approx(G.SEAM.reach * 1.02, rel=1e-9)
    slo, shi = SeamGeo(_GEO, G.SEAM.csangle, roll_speedf=20.0).search_band()
    assert shi < hi                            # shorter reach -> nearer band (scales, not pasted)


def test_shipped_roll_old_is_inside_the_derived_band():
    """The shipped kaze roll hit's `old` sits inside the derived d2S search band (so the generalized
    search would consider it) -- guards against a band that no longer brackets the real hit."""
    lo, hi = G.SEAM.search_band()
    d2S = G.SEAM.d2S(SHIPPED_OLD)
    assert lo <= d2S <= hi


def test_walk_bounds_bracket_the_shipped_walk_hit():
    """The walk solver's DERIVED bounds bracket the shipped walk-stab clip (golden
    walkstab_deliver.json): its cut frame N and its `old` distance-to-S both fall in-window."""
    gold = json.load(open(os.path.join(_rb, 'tests', 'golden', 'walkstab_deliver.json')))
    old = gold['sim_old']
    N = gold['hit']['N']
    b = W.bounds()
    d2S = math.hypot(W.sg().S[0] - old[0], W.sg().S[1] - old[1])
    assert b['WIN_LO'] <= d2S <= b['WIN_HI']
    assert b['NLO'] <= N <= b['NHI']
    # the window upper edge is the derived reach (general), not a pasted 40.35
    assert b['WIN_HI'] == pytest.approx(W.sg().reach_at(17.0) * 1.02, rel=1e-9)


def test_wall_faithful_accepts_shipped_roll_hit():
    """The roll physics reachability guard ACCEPTS the shipped hit: replaying its exact stream through
    a walled re-sim reaches `old` bit-for-bit with no wall stopping the approach (it clipped live
    0-ULP, session 44, so the walled roll must reach it)."""
    r = SV.run(ANCHOR, MOVES, A_proj=A_PROJ, start=START, draw_at=DRAW_AT, dtm_seed=DTM_SEED, seam=G.SEAM)
    assert r is not None and r.get('fired') and r['genuine'] and r['clear']
    assert (_bits(r['old'][0]), _bits(r['old'][1])) == (_bits(SHIPPED_OLD[0]), _bits(SHIPPED_OLD[1]))
    assert SV.wall_faithful(ANCHOR, r['stream'], r['old'], G.SEAM, dtm_seed=DTM_SEED) is True


def test_wall_faithful_rejects_wrong_old():
    """The guard is a real bit-exact reachability check, not a rubber stamp: replaying the shipped
    stream but claiming a different `old` (an unreachable position) is REJECTED."""
    r = SV.run(ANCHOR, MOVES, A_proj=A_PROJ, start=START, draw_at=DRAW_AT, dtm_seed=DTM_SEED, seam=G.SEAM)
    wrong_old = (r['old'][0] + 1.0, r['old'][1] - 1.0)   # a spot the walled roll does not reach
    assert SV.wall_faithful(ANCHOR, r['stream'], wrong_old, G.SEAM, dtm_seed=DTM_SEED) is False
