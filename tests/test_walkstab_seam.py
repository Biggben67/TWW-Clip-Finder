"""Walk-stab generalization (Phase 4): the walk-stab driver's acceptance is the general `SeamGeo`,
and its thrust facing F is DERIVED (from bear_to_S, the flat-seam grazing aim), not pasted.

Locks, offline (pure sim, no Dolphin):
  * F derives from bear_to_S via the derive_F stick-settle -- == the shipped threading facing 5625,
    and it MOVES with the camera yaw (guards a reintroduced hardcode). The corner bisector would give
    a different facing (this seam is nearly flat, so it grazes toward S, not into the corner).
  * the seam's SeamGeo reproduces the shipped clip's genuine verdict, with the ordered CrrPos barrier
    (`tris`) + full-precision S/link_y sourced from the fixture (no rounded literals).
  * fast_cut delegates to SeamGeo.cut_new and stays bit-identical to the real LandState.enter_cut for
    a runtime walk facing + per-frame speedF (the walk-stab lunge speed, not the fixed roll cap).
"""
import json
import os
import struct

import pytest

try:
    from harness.rollstab import walkstab as W
    from harness.rollstab.seamgeo import SeamGeo, derive_F
    from tww_sim.core.fp import f32 as _f
    from tww_sim.land.land import LandState
    from tww_sim.land.constants import CUT_F
    _HAVE = W.seed is not None
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / anim data unavailable")

GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'tests', 'golden', 'walkstab_deliver.json')


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_walkstab_F_derived_from_bear_to_S():
    """F == the shipped threading facing 5625, derived via derive_F fed bear_to_S (the flat-seam aim).
    The corner bisector -- the fixture's `bisector_deg`, ~19.4deg -- would give a DIFFERENT facing, so
    the walk-stab genuinely uses the grazing aim, not the corner convention."""
    g = W.sg()
    assert g.F == 5625
    # F is the bear_to_S decode, NOT the bisector decode (they differ for this near-flat seam).
    bis_F = derive_F(W._GEO['bisector_deg'], g.csangle)
    assert bis_F != g.F, "bear_to_S aim and bisector aim must differ for a near-flat seam"
    assert g.aim_deg == pytest.approx(W.bear_to_S() / 65536.0 * 360.0)


def test_walkstab_F_is_camera_dependent():
    """F is genuinely derived (a function of csangle), not hardcoded: a different camera yaw at the
    same aim yields a different thrust facing. (Guards against a reintroduced pasted F.)"""
    g = W.sg()
    other = SeamGeo(W._GEO, (g.csangle + 4096) & 0xFFFF, aim_deg=g.aim_deg)
    assert other.F != g.F


def test_walkstab_seam_geometry_from_fixture():
    """The seam's CrrPos barrier + S + link_y come from the fixture (full precision), not rounded
    module literals: the ordered `tris` chain is [801,803,802,804,798,800]; S/link_y are the precise
    shared floor vertex (the old code used z=1385.858, link_y=-6534.329 -- now exact)."""
    g = W.sg()
    assert [t['poly'] for t in W._GEO['tris']] == [801, 803, 802, 804, 798, 800]
    assert len(g.TRIS) == 6
    assert g.S == (9030.955078125, 1385.858154296875)
    assert g.LINK_Y == -6534.32861328125
    assert W.SEAM == g.S and W.LINK_Y == g.LINK_Y


def test_walkstab_seam_reproduces_shipped_verdict():
    """The shipped clip's live old->new classifies genuine through the seam's SeamGeo (same booleans
    the pre-SeamGeo private genuine_clip gave: in front of both faces, unblocked, new behind a face)."""
    gold = json.load(open(GOLDEN))
    old, new = tuple(gold['live_old']), tuple(gold['live_new'])
    ok, why = W.genuine_clip(old, new)
    assert ok and why == 'clip'
    assert W.sg().genuine_clip(old, new)


def test_walkstab_fast_cut_matches_enter_cut_bit_exact():
    """fast_cut (SeamGeo.cut_new with the runtime walk facing + per-frame nspeed) == the real
    LandState.enter_cut, 0-ULP, at the shipped hit's walk end-state (a sub-cap walk speedF, not the
    roll cap the roll seam uses)."""
    gold = json.load(open(GOLDEN))
    hit = gold['hit']
    sticks = [tuple(sk) for sk in hit['sticks']]
    s = W.seed()
    s._foot.skip_cruise_pose = True
    for k in range(hit['N']):
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=W.CDOWN)
    fx, fz = W.fast_cut(s.pos_x, s.pos_z, s.facing, s.nspeed)
    # the real engine cut from the same walk state
    st = LandState(native=False)
    st.pos_x, st.pos_z = s.pos_x, s.pos_z
    st.facing, st.travel = s.facing, s.facing
    st.nspeed, st.speedF = s.nspeed, s.speedF
    st.enter_cut(CUT_F)
    assert _bits(fx) == _bits(st.pos_x) and _bits(fz) == _bits(st.pos_z)
