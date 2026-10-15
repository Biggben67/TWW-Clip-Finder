"""Regression for the centralized THRUST-CLIP scanner (harness.rollstab.thrust_scan).

OFFLINE only (no Dolphin): the DECISION layer is pure sim -- it reads the anchor seed via
`rest.rest_state` and the seam geometry from the tracked fixtures. Covers the four cases from the
session-32 handoff plus the tier boundaries and the roll-required-but-no-space branch:

  * kaze WALK seam (polys 803x802, floor 35.16)          -> WALK
  * kaze ROLL seam (fixtures/kaze_r11_geo.json, floor 42.6) from a far anchor -> ROLL
  * a synthetic steep seam (interior 90 deg, floor 49.5 > roll reach) -> INFEASIBLE(push)
  * the WALK seam placed right in front of the anchor (no run-up) -> INFEASIBLE(space)
  * a ROLL-tier seam placed in front of the anchor (no run-up) -> INFEASIBLE(space)
"""
import math
import pytest


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from harness.rollstab import thrust_scan as T
from harness.rollstab import rest as C
import os



WALK_ANCHOR = 'kaze_r11_walkstab@twwgz'
ROLL_ANCHOR = 'kaze_r11_rollstab_idle13@twwgz'


def _seam_ahead(anchor, dist, interior):
    """A synthetic seam whose vertex S sits `dist` u ahead of the anchor along its facing (so the
    approach starts already close -- exercises the run-up-space gate)."""
    s = C.rest_state(anchor)
    a = s.facing / 65536.0 * 2 * math.pi
    return dict(S=(s.pos_x + dist * math.sin(a), -6534.329, s.pos_z + dist * math.cos(a)),
                interior=interior)


# --------------------------------------------------------------------- reach constants / tiers
def test_reach_constants():
    # a capped walk thrusts 17 + 23.22 = 40.22; a roll reaches 49.22 (KB mechanics/walk-stab.md).
    assert T.WALK_REACH == pytest.approx(40.220, abs=1e-3)
    assert T.ROLL_REACH == pytest.approx(49.2202, abs=1e-3)
    assert T.WALK_CAP_SPEEDF + T.CUT_ROOT == pytest.approx(T.WALK_REACH)


def test_tier_boundaries():
    # floor = 35 / sin(interior/2): more obtuse -> lower floor -> cheaper technique.
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=168.968)) == T.TIER_WALK   # floor 35.16
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=110.444)) == T.TIER_ROLL   # floor 42.61
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=90.0)) == T.TIER_PUSH      # floor 49.50
    # WALK<->ROLL boundary: floor == 40.22 at interior = 2*asin(35/40.22).
    ib = 2 * math.degrees(math.asin(35.0 / T.WALK_REACH))
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=ib + 0.2)) == T.TIER_WALK
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=ib - 0.2)) == T.TIER_ROLL
    # ROLL<->PUSH boundary: floor == 49.22 at interior = 2*asin(35/49.22).
    ip = 2 * math.degrees(math.asin(35.0 / T.ROLL_REACH))
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=ip + 0.2)) == T.TIER_ROLL
    assert T.geometric_tier(dict(S=(0, 0, 0), interior=ip - 0.2)) == T.TIER_PUSH


# --------------------------------------------------------------------- the four handoff cases
def test_walk_seam_decides_walk():
    v = T.decide(WALK_ANCHOR, T.kaze_walk_seam())
    assert v['feasible'] and v['technique'] == T.TIER_WALK
    assert v['tier'] == T.TIER_WALK
    assert v['floor'] == pytest.approx(35.163, abs=1e-2)
    assert v['build_d2S'] >= v['floor']          # req speedF built with room before the seam


def test_roll_seam_decides_roll():
    v = T.decide(ROLL_ANCHOR, T.kaze_roll_seam())
    assert v['feasible'] and v['technique'] == T.TIER_ROLL
    assert v['tier'] == T.TIER_ROLL
    assert v['floor'] == pytest.approx(42.612, abs=1e-2)
    assert v['req_speedF'] == pytest.approx(T.WALK_CAP_SPEEDF)   # roll needs the speedF-17 cap


def test_steep_seam_infeasible_push():
    v = T.decide(WALK_ANCHOR, dict(S=(9030.955, -6534.329, 1385.858), interior=90.0))
    assert not v['feasible'] and v['reason'] == 'push'
    assert v['tier'] == T.TIER_PUSH
    assert v['technique'] is None


def test_close_start_infeasible_space():
    # WALK-tier seam (floor 35.16) but only ~28u ahead of the anchor -> no room to build speedF.
    v = T.decide(WALK_ANCHOR, _seam_ahead(WALK_ANCHOR, 28.0, 168.968))
    assert not v['feasible'] and v['reason'] == 'space'
    assert v['tier'] == T.TIER_WALK              # geometrically a walk, just no run-up


def test_roll_tier_no_space():
    # ROLL-tier seam (interior 110 -> floor 42.6) placed right in front of the anchor: a roll is
    # REQUIRED (floor > walk reach) but there is no room to build the speedF-17 cap -> space.
    v = T.decide(WALK_ANCHOR, _seam_ahead(WALK_ANCHOR, 30.0, 110.444))
    assert v['tier'] == T.TIER_ROLL
    assert not v['feasible'] and v['reason'] == 'space'


# --------------------------------------------------------------------- fewest-frames preference
def test_prefers_walk_when_both_fit():
    # The far walk anchor can both walk (floor 35.16 <= 40.22) and would clip via a roll, but WALK is
    # fewer frames -> the scanner must pick WALK.
    v = T.decide(WALK_ANCHOR, T.kaze_walk_seam())
    assert v['technique'] == T.TIER_WALK


def test_scan_dispatch_recognizes_known_seams():
    # scan() with solve/deliver off returns the decision without touching a solver or Dolphin.
    vw = T.scan(WALK_ANCHOR, T.kaze_walk_seam(), verbose=False)
    vr = T.scan(ROLL_ANCHOR, T.kaze_roll_seam(), verbose=False)
    assert vw['technique'] == T.TIER_WALK and 'hits' not in vw
    assert vr['technique'] == T.TIER_ROLL and 'hits' not in vr
