"""SeamGeo: the roll/wall-clip geometry abstraction derives F + the cut lunge from the seam,
instead of pasting them. Gates the session-45 generalization kickoff (Phases 1-2, standard-roll
path only -- the Tetra push clip stays a standalone solver and is NOT covered here).

  * F is COMPUTED from the interior bisector + camera yaw (bit-exact == the old by-inspection 33295).
  * the cut endpoint is COMPUTED per candidate from the CUT_F root translate at F (bit-identical to
    the real LandState.enter_cut) -- there is no frozen per-`old` LUNGE literal to reproduce.
  * geometry.py (the kaze shim) is instance-backed by SeamGeo, so its whole `G` surface is unchanged.
"""
import os, sys
_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _rb not in sys.path:
    sys.path.insert(0, _rb)

import json


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from tww_sim.core.fp import f32 as _f
from tww_sim.land.land import LandState
from tww_sim.land.constants import CUT_F
from harness.rollstab.seamgeo import SeamGeo, derive_F
from harness.rollstab import geometry as G
import pytest



_GEO = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json')))
# csangle comes from STATE (the anchor's RAM snapshot), not a pasted literal -- the same field a
# live tww-python Dolphin feed supplies. It happens to be 29883 (the kaze camera is frozen).
_KAZE_CSANGLE = G.load_seed('kaze_r11_rollstab_sheathed@twwgz')['csangle'] & 0xFFFF


def test_F_derived_bit_exact():
    """F == the closest-reachable bisector decode, NOT a pasted literal (kaze: csangle 29883)."""
    assert derive_F(_GEO['bisector_deg'], _KAZE_CSANGLE) == 33295
    assert SeamGeo(_GEO, _KAZE_CSANGLE).F == 33295


def test_F_is_camera_dependent():
    """F is genuinely derived (a function of csangle), not hardcoded: a different camera yaw yields
    a different roll facing. (Guards against someone reintroducing a pasted `F = 33295`.)"""
    other = derive_F(_GEO['bisector_deg'], (_KAZE_CSANGLE + 4096) & 0xFFFF)
    assert other != 33295


def test_cut_new_matches_enter_cut_bit_exact():
    """The derived cut endpoint == the real sim CUT_F entry (LandState.enter_cut), 0-ULP, at several
    olds spanning the seam band -- so the lunge is computed from the CUT anim, not a stored delta."""
    seam = SeamGeo(_GEO, _KAZE_CSANGLE)
    for old in [(9072.208984375, 308.028076171875), (9071.5, 302.6), (0.0, 0.0), (9072.7, 305.1)]:
        st = LandState(native=False)
        st.pos_x, st.pos_z = _f(old[0]), _f(old[1])
        st.facing = seam.F
        st.travel = seam.F
        st.nspeed = seam.roll_speedf
        st.speedF = seam.roll_speedf
        st.enter_cut(CUT_F)
        real = (st.pos_x, st.pos_z)
        assert seam.cut_new((_f(old[0]), _f(old[1]))) == real, old


def test_shim_is_instance_backed():
    """geometry.py exports come straight from a fresh SeamGeo built on the same fixture+csangle:
    the `G` surface is exactly the abstraction, nothing pasted alongside it."""
    seam = SeamGeo(_GEO, _KAZE_CSANGLE)
    assert G.F == seam.F == 33295
    assert G.LUNGE == seam.LUNGE
    assert G.S == seam.S and G.LINK_Y == seam.LINK_Y and len(G.TRIS) == len(seam.TRIS)
    # acceptance verdicts identical across the whole dust band the drill ranker probes
    zz = 302.6
    while zz <= 308.2:
        xx = 9071.5
        while xx <= 9072.7:
            o = (_f(xx), _f(zz))
            assert G.pred_genuine(o) == seam.pred_genuine(o)
            xx += 0.05
        zz += 0.2


def test_lunge_magnitude_is_roll_reach():
    """The derived lunge magnitude is the roll-stab reach (~49.2202u) thrust_scan keys off."""
    seam = SeamGeo(_GEO, _KAZE_CSANGLE)
    mag = (seam.LUNGE[0] ** 2 + seam.LUNGE[1] ** 2) ** 0.5
    assert abs(mag - 49.2202) < 1e-3


def test_roll_reachable_screen():
    """`SeamGeo.roll_reachable` is the ACCURATE reachability screen: it defers to the shipped analytic
    locator's geometry-first core (seam_locator.locate_geo) on the seam's own walls + flat floor, so a
    seam whose only genuine dust hugs a wall (inside Link's 35u WallCorrect hold) has NO standable-old
    clip and is rejected -- while a seam whose dust sits in the open corner mouth is accepted.

    Live-anchored ground truth (session 53): the 97-deg corner is roll-UNREACHABLE (its roll is held
    35u off wallA, bit-exact vs live -- test_seam97_clip.py); the proven + mirror corners were both
    roll-DELIVERED. This screen replaces the disp-floor proxy (which the 97-corner passed) and the
    deleted nearest-wall heuristic (which false-negated the proven seam)."""
    def seam_of(fixture, anchor):
        cs = G.load_seed(anchor)['csangle'] & 0xFFFF
        return SeamGeo(json.load(open(os.path.join(_rb, 'fixtures', fixture))), cs)

    proven = seam_of('kaze_r11_geo.json', 'kaze_r11_rollstab_idle13@twwgz')
    mirror = seam_of('kaze_r11_seam_mirror_geo.json', 'kaze_r11_rollstab_mirror@twwgz')
    corner97 = seam_of('kaze_r11_seam97_geo.json', 'kaze_r11_rollstab_seam97@twwgz')

    assert corner97.roll_reachable() is None, "97-deg corner must be rejected (dust hugs wallA)"
    for name, seam in (('proven', proven), ('mirror', mirror)):
        r = seam.roll_reachable()
        assert r is not None, "%s corner must be roll-reachable (a standable old clips)" % name
        # a standable old that clears BOTH walls, and the clip lands past the seam (behind a wall)
        assert seam.wA.pla.func(r['old']) > 0 and seam.wB.pla.func(r['old']) > 0, (name, r['old'])
