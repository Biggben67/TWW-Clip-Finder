"""Regression guard for the SHIPPED seam-clip scanner (:mod:`harness.collision.seam_locator`) — the
fast analytic locator wired into ``scan_all_dzb`` / ``dzb_iso.main``. Offline (no Dolphin), on the
same captured region goldens as :mod:`test_seam_clip_check`.

Two invariants are gated here:
  * The locator is a **superset** of :func:`seam_clip_check.scan_region` — it applies the SAME
    structural gates (standable floor, OOB-skirt via ``_floor_at``, step/ledge riser) so it never
    admits a different class of phantom, and its anisotropic f32 verify finds every clip the shipped
    checker does (plus real ones it missed). A MISS (a checker clip the locator drops) is the bug.
  * The native (Cython) ``first_f32_clip`` ring is bit-identical to the pure ring (same FIRST hit and
    n_calls). Skipped when the ``_collc`` .pyd is absent (the pure fallback IS the reference).
"""
import os

import pytest

from harness.collision.seam_scan import load_region_tris
from harness.collision import seam_scan as SS
from harness.collision import seam_clip_check as SCC
from harness.collision import seam_locator as SL

# Deselected by default: the region-wide f32 verify is a heavy search (>90s pure-Python), not a
# 0-ULP assert. Run with `pytest -m slow`; see the slow-offline-tests memory (build native _collc).
pytestmark = pytest.mark.slow

_G = os.path.join(os.path.dirname(__file__), "golden")


def _region(name):
    region, _stage = load_region_tris(os.path.join(_G, name))
    return region


def _keys(clips):
    return {(round(c["S"][0], 1), round(c["S"][2], 1)) for c in clips}


def test_locator_finds_ganonl_staircase_clips():
    """GanonL grand-staircase seams: found, roll-stab reachable, seam Y = the STANDABLE floor
    (~5852) not the wall base (~5762) — the clip is height-invariant."""
    box = (1000.0, 1200.0, 5700.0, 6000.0, -36600.0, -36400.0)
    clips = SL.scan_region(_region("ganonl_seamY_region.json"), box, verbose=False)
    assert clips, "expected the GanonL staircase clips"
    for c in clips:
        assert abs(c["S"][1] - c["old"][1]) < 0.05, c        # seam Y == standable floor
        assert c["S"][1] > 5840.0, c                          # the floor (~5852), NOT the base (~5762)


def test_locator_finds_hyrule_near_coincident_clip():
    """The live-confirmed Hyrule (-1232.49, 1765.95) clip the pre-fix dump missed (near-coincident
    seam vertices). Found and roll-stab reachable."""
    box = (-1500.0, -1000.0, -50.0, 100.0, 1500.0, 2000.0)
    clips = SL.scan_region(_region("hyrule_nearcoincident_region.json"), box, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] + 1232.49) < 0.5 and abs(c["S"][2] - 1765.95) < 0.5]
    assert hits, sorted(_keys(clips))
    assert hits[0]["reachable_rollstab"], hits[0]


def test_locator_rejects_oob_skirt():
    """Hyrule stage underside: the wall tops out below the lowest cylinder sample, so the game never
    touches it. The ``_floor_at`` collidable-at-stance gate must drop it (no phantom clip)."""
    box = (400.0, 700.0, -2100.0, 300.0, 1600.0, 1900.0)
    clips = SL.scan_region(_region("hyrule_oob_skirt_region.json"), box, verbose=False)
    assert clips == [], [tuple(round(x, 1) for x in c["S"]) for c in clips]


def test_locator_rejects_step_riser():
    """Hyrule (734.87, 322.73): a short wall whose crown is a walkable floor ~75 u up — Link ascends
    via a ground snap, not a clip. The step/ledge-riser gate must drop it (the f32 verify alone would
    re-admit this phantom)."""
    box = (600.0, 900.0, -230.0, 50.0, 200.0, 500.0)
    clips = SL.scan_region(_region("hyrule_step_riser_region.json"), box, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] - 734.87) < 3 and abs(c["S"][2] - 322.73) < 3]
    assert not hits, [tuple(round(x, 1) for x in c["S"]) for c in clips]


def test_locator_finds_amori_coplanar_flatwall_clip():
    """A_mori (4077.6, -1708.8): a CONFIRMED clip (external tool + live floor_tri=172) through a
    single-normal FLAT wall -- the swept line threads the f32 gap at the wall's own vertical
    tessellation edge (two COPLANAR tris meeting), not a differing-normal corner. The pre-fix
    enumerate_seams dropped every single-normal cluster ('flat / free edge, not a corner') so the
    locator never even tested this spot. It must now be found (interior 180, roll-stab reachable)."""
    box = (3850.0, 4350.0, 3600.0, 3760.0, -1900.0, -1500.0)
    clips = SL.scan_region(_region("amori_coplanar_region.json"), box, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] - 4077.6) < 3 and abs(c["S"][2] + 1708.8) < 3]
    assert hits, sorted(_keys(clips))
    assert hits[0]["interior"] >= 179.5, hits[0]          # a flat (coplanar) seam, not a corner
    assert hits[0]["reachable_rollstab"], hits[0]


def test_locator_rejects_ganonk_top_flatwall_phantom():
    """GanonK top-of-room (+-250, 7770, -2902.6): the external scanner reported these as clips but
    they DON'T work -- WallCorrect stops Link short (user-flagged). The seams ARE enumerated and the
    init IS standable (floor ~7770, 780 u ABOVE the seam-vertex Y 6997), so the gate must be the CLIP
    verify, not a missing floor. Two bugs conspired to false-positive them: (a) the barrier was
    gathered at the seam-vertex Y, missing the walls at Link's real (much higher) floor; (b) even the
    gathered set can miss a blocker. The fix gathers at Link's floor Y AND re-verifies the exact
    old->new against the FULL room. No clip must survive."""
    box = (-320.0, 320.0, 6900.0, 7950.0, -3000.0, -2800.0)
    region = _region("ganonk_top_flatwall_region.json")
    # the two top seams must still be ENUMERATED and STANDABLE (else the test would pass for the
    # wrong reason -- a dropped-for-no-floor seam, not a rejected phantom clip).
    seams = [s for s in SS.enumerate_seams(region, box)
             if abs(s["S"][0]) < 300 and abs(s["S"][2] + 2902.6) < 40]
    assert len(seams) == 2, [tuple(round(x, 1) for x in s["S"]) for s in seams]
    clips = SL.scan_region(region, box, verbose=False)
    assert clips == [], [tuple(round(x, 1) for x in c["S"]) for c in clips]


def test_locator_superset_of_shipped_checker():
    """On a real region the locator must find EVERY clip the shipped :func:`seam_clip_check.scan_region`
    finds (0 misses) — same structural gates, stricter f32 search. Extras (locator-only) are allowed
    (they are the real clips the checker's shallow search dropped)."""
    box = (-1500.0, -1000.0, -50.0, 100.0, 1500.0, 2000.0)
    region = _region("hyrule_nearcoincident_region.json")
    scc = _keys(SCC.scan_region(region, box, require_standable=True, verbose=False))
    loc = _keys(SL.scan_region(region, box, verbose=False))
    assert scc <= loc, "locator dropped checker clips: %s" % sorted(scc - loc)


def test_native_ring_matches_pure():
    """Native ``first_f32_clip`` (Cython ring) is bit-identical to the pure ring: identical FIRST hit
    and n_calls. Skipped when the _collc .pyd is absent (pure fallback is the reference)."""
    import importlib.util
    if importlib.util.find_spec("tww_sim.core._collc") is None:
        import pytest
        pytest.skip("native _collc not built")
    from tww_sim.core._collc import first_f32_clip as native
    from harness.collision import gap_search as gs
    from harness.collision.seam_model import SEAM_TRIS, LINK_Y
    S = (-847.632, -37336.613)
    old = gs.settle(SEAM_TRIS, (S[0] - 45.0, S[1] - 45.0), LINK_Y)
    for nc in [(S[0] + 0.1, S[1] + 0.1), (S[0] + 0.5, S[1] + 0.5), (S[0] + 1.2, S[1] + 1.2)]:
        hp, np_ = gs._first_f32_clip_py(SEAM_TRIS, old, nc, LINK_Y, box_ulps=60, max_calls=8000)
        hn, nn = native(old, nc, LINK_Y, SEAM_TRIS, box_ulps=60, max_calls=8000)
        assert np_ == nn, (nc, np_, nn)
        assert (hp is None) == (hn is None), (nc, hp, hn)
        if hp is not None:
            assert hp["new"] == hn["new"] and hp["disp"] == hn["disp"], (nc, hp, hn)
