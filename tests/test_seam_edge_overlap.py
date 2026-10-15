"""Regression guard for the FLOATING-SEAM false positive: the shared corner edge must be within
Link's cylinder at his stance, else the two-wall fan can't produce a clip (one wall is absent at his
height).

Root cause (2026-07-15, Omori Room0 locator-vs-live diagnosis, user-flagged): the scanner reported a
clip at S=(2249.6, 358.0, 1772.6) but there is no seam there. The two walls forming the corner (polys
31, 864) share a vertical edge running y905..1227, but the standable floor is y358 -- ~420u BELOW the
corner. Poly 31 (one wall of the pair) does not exist at floor level; only poly 864 is there, so at
Link's stance there is a single wall, not a clippable corner. The downstream standability gate accepted
the floor because it tested the UNION of both walls' vertices (poly 864 dips to y350), masking that the
OTHER wall floats above.

The fix (``seam_clip_check._cyl_overlaps_edge``) gates the settled stance on the SHARED seam-edge span
(from ``enumerate_seams``' edge cluster, exposed as ``seam['edge_yspan']``): a clip is dropped unless a
cylinder sample (feet + ``WALL_H``) lies inside that edge span. This culls BOTH the Omori case (edge
ABOVE the cylinder) and the symmetric GanonK-top case (edge BELOW the settled floor -- gated in
test_seam_locator). This test is Dolphin-free (small captured region golden)."""
import os

from harness.collision.seam_scan import load_region_tris, enumerate_seams, GROUND_NY_MIN
from harness.collision.seam_clip_check import _cyl_overlaps_edge
from harness.collision.gap_search import WALL_H
from harness.collision.seam_locator import locate
from harness.collision import seam_clip_check as SCC

_G = os.path.join(os.path.dirname(__file__), "golden")
BOX = (1800.0, 2500.0, 300.0, 1300.0, 1400.0, 2600.0)


def test_cyl_overlaps_edge_predicate():
    """The shared-edge overlap predicate: pass iff a cylinder sample lands in the edge span."""
    assert _cyl_overlaps_edge(358.0, None)                     # synthetic geometry (no edge) -> pass
    # Omori: floor 358, edge y905..1227 -> cylinder (388/448/483) all BELOW -> reject
    assert not _cyl_overlaps_edge(358.0, (905.24, 1227.44))
    # GanonK top: floor 7770, edge y6997..7504 -> cylinder (7800/7860/7895) all ABOVE -> reject
    assert not _cyl_overlaps_edge(7770.0, (6997.4, 7504.1))
    # a normal floor-level corner: floor 358, edge y350..1227 -> cylinder inside -> pass
    assert _cyl_overlaps_edge(358.0, (350.0, 1227.44))
    # boundary: a sample within the +-2u collidability tolerance still passes
    assert _cyl_overlaps_edge(358.0, (483.0 + 2.0, 900.0))     # 358+125 == 483 touches lo-2


def _region():
    return load_region_tris(os.path.join(_G, "omori_floating_seam_region.json"))[0]


def test_omori_floating_seam_enumerated_and_standable():
    """The test passes for the RIGHT reason: the seam IS enumerated, its floor IS standable, and its
    shared edge genuinely floats ~420u above that floor -- so a rejection is the phantom gate firing,
    not a missing seam / missing floor."""
    region = _region()
    ground = [t for t in region if t["n"][1] >= GROUND_NY_MIN]
    seam = min(enumerate_seams(region, BOX),
               key=lambda s: (s["S"][0] - 2249.6) ** 2 + (s["S"][2] - 1772.6) ** 2)
    assert seam["polys"] == [31, 864] and round(seam["interior"], 1) == 145.2
    elo, ehi = seam["edge_yspan"]
    assert round(elo) == 905 and round(ehi) == 1227           # shared edge is up high
    from harness.collision.seam_scan import floor_ys_at
    floors = floor_ys_at(ground, seam["S"][0], seam["S"][2])
    assert any(abs(f - 358.0) < 1.0 for f in floors)          # a real standable floor at y358
    assert 358.0 + WALL_H[-1] < elo                           # the whole cylinder is below the edge


def test_omori_floating_seam_rejected_by_locator():
    """The shipped locator now REJECTS the Omori floating seam (was a reported clip, is a live BLOCK)."""
    region = _region()
    ground = [t for t in region if t["n"][1] >= GROUND_NY_MIN]
    seam = min(enumerate_seams(region, BOX),
               key=lambda s: (s["S"][0] - 2249.6) ** 2 + (s["S"][2] - 1772.6) ** 2)
    assert locate(region, ground, seam, {}) is None


def test_omori_floating_seam_rejected_by_checker():
    """The shipped :func:`seam_clip_check.scan_region` (the locator's superset partner) also drops it,
    so the two stay in lock-step (guards the superset invariant in test_seam_locator)."""
    region = _region()
    clips = SCC.scan_region(region, BOX, verbose=False)
    hits = [c for c in clips if abs(c["S"][0] - 2249.6) < 3 and abs(c["S"][2] - 1772.6) < 3]
    assert hits == [], [tuple(round(x, 1) for x in c["S"]) for c in hits]
