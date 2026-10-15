"""Phase-T gate: the STATIC acceptance geometry of `harness/rollstab/solver_tetra.py`, vs the golden.

SCOPE (session-19 correction): this gates the STATIC `co_move_pair` acceptance ONLY. It does NOT prove
the staging works. The stationary behind-Link staging `solver_tetra` assumes is REFUTED by the coupled
dynamics (Tetra gets plowed before the cut -- README ## Status, dead-ends #17, the session-19 handoff);
a real reachable clip must be checked with the DYNAMIC coupled cut, not this static predictor.

What IS locked in here, against the live golden (`fixtures/hyrule_tetra_geo.json`, from the RAM capture
`tests/golden/hyrule_seam_1727_ram.json`, slot 3) -- all still-true geometry:

  * for a behind-Link Tetra placement, the EMERGENT push (the SAME `co_move_pair` output
    `cc_stepper._cc_check` computes: the Co overlap of Link's animated FRONT_ROLL centre with Tetra's
    cylinder) reproduces the live golden `new` BIT-EXACT (0-ULP) when placed at the golden's overlap;
  * the Tetra placement is a 2D f32 knob, not a 1D distance: a COLINEAR-BEHIND Tetra (push along the
    roll facing F) does NOT clip -- the steer bearing (~235deg, ~11deg off F) decides it
    ([[tetra-push-model]] correction); a wrong-side (in-front) Tetra never clips (direction guard).

Pure-geometry + offline (no Dolphin, fast). The full per-frame CUT_F ordering (push consume -> m34C2
lunge -> CrrPos) is separately live-gated by `test_cc_rollstab.py`.
"""
import pytest

import struct


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from harness.rollstab import solver_tetra as ST
from harness.rollstab import geometry_tetra as GT
from tww_sim.core.fp import f32
import os




def _bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def _golden():
    return ((f32(GT.TARGET["old"][0]), f32(GT.TARGET["old"][1])),
            (f32(GT.TARGET["new"][0]), f32(GT.TARGET["new"][1])))


def test_placement_search_reproduces_golden_bit_exact():
    """For the golden settled `old`, the 2D behind-Link Tetra placement search finds exactly the
    placement whose emergent push (via the real Co machinery) clips the seam AND reproduces the live
    golden `new` 0-ULP -- at every candidate cut roll_frame."""
    old, gnew = _golden()
    for fr in (8.0, 12.0, 16.5):
        hits = ST.placement_search(old, fr, span=0.4)       # golden cell sits at the nominal centre
        assert hits, "no genuine behind-Link Tetra placement found at roll_frame %.1f" % fr
        exact = [t for (t, a) in hits
                 if _bits(a["new"][0]) == _bits(gnew[0]) and _bits(a["new"][1]) == _bits(gnew[1])]
        assert len(exact) == 1, (
            "expected exactly one golden-bit-exact placement at roll_frame %.1f, got %d" % (fr, len(exact)))


def test_emergent_push_is_toward_corner_075u():
    """The emergent push from the golden-reproducing placement is the ~0.75u toward-the-seam push the
    corner needs (bearing ~235deg, ~11deg off the roll facing F=224.53deg -- hence the 2D steer)."""
    import math
    old, gnew = _golden()
    hits = ST.placement_search(old, 12.0, span=0.4)
    exact = [(t, a) for (t, a) in hits
             if _bits(a["new"][0]) == _bits(gnew[0]) and _bits(a["new"][1]) == _bits(gnew[1])]
    assert exact, "no golden-bit-exact placement"
    push = exact[0][1]["push"]
    mag = math.hypot(*push)
    brg = math.degrees(math.atan2(push[0], push[1])) % 360.0
    assert 0.74 < mag < 0.76, "push magnitude %.4f not ~0.75u" % mag
    assert 230.0 < brg < 240.0, "push bearing %.1f not toward the corner (~235deg)" % brg
    assert abs(brg - GT.F / 65536.0 * 360.0) > 5.0, "push must STEER off F, not be colinear"


def test_colinear_behind_does_not_clip():
    """A Tetra placed COLINEAR-BEHIND (push along the roll facing F) does NOT clip -- the memory's
    correction: the STEER, not just the overlap depth, decides it."""
    old, _ = _golden()
    center = ST.link_co_center(old[0], old[1], 12.0)
    tetra_col = ST.place_behind(center, GT.F, 1.5)          # overlap 1.5u but pushed along +F
    assert ST.accept(old, tetra_col, 12.0)["genuine"] is False


def test_wrong_side_tetra_never_clips():
    """A Tetra placed IN FRONT (toward the corner) pushes Link backward -- it must never clip, over a
    2D f32 grid. Guards the staging direction (behind-Link only)."""
    import math
    old, _ = _golden()
    r = GT.F / 65536.0 * 2 * math.pi
    dx, dz = math.sin(r), math.cos(r)
    clipped = 0
    for fr in (8.0, 12.0, 16.5):
        center = ST.link_co_center(old[0], old[1], fr)
        for cd10 in range(740, 801, 5):                     # centre-dist 74..80u, in front along +F
            cd = cd10 / 10.0
            tetra = (f32(center[0] + cd * dx), f32(center[1] + cd * dz))
            if ST.accept(old, tetra, fr)["genuine"]:
                clipped += 1
    assert clipped == 0, "%d in-front (wrong-side) placements clipped (expected 0)" % clipped


def test_bare_no_tetra_is_short():
    """With no Tetra (push 0) the bare lunge is short of the seam -- the corner is needs-push (ties to
    test_tetra_geo). `accept` with a far-away Tetra (no overlap) == the bare roll."""
    old, _ = _golden()
    a = ST.accept(old, (old[0] - 1e6, old[1]), 12.0)        # Tetra a mile away -> no overlap
    assert a["push"] == (0.0, 0.0)
    assert a["genuine"] is False


@pytest.mark.slow
def test_family_reuse_at_tetra_facing():
    """`solver`'s knob families take the Tetra clip facing via the new `F=` param (backward-compatible
    default = kaze). The solver_tetra search relies on this to aim the from-rest approach at GT.F."""
    from harness.rollstab import solver as S0
    anchor = "kaze_r11_rollstab_idle13@twwgz"               # any anchor: the family needs only csangle
    default = S0.start_family(anchor)                        # kaze facing (geometry.F)
    tetra = S0.start_family(anchor, F=GT.F)                  # Tetra facing
    assert default and tetra
    assert default != tetra                                  # different aim -> different sticks
