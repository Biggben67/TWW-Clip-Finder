"""Regression guard for the GROUND-DETECTION false positive: a reported ``old`` must sit on a floor
the GAME accepts, tested with its exact ground point-in-triangle -- not a loose barycentric eps.

Root cause (2026-07-16, Asoko Room0, user-flagged "initial positions that just fall OOB"): the scanner
reported clip ``old`` positions that fall out of bounds. ``seam_scan.floor_ys_at`` decided standability
with a barycentric ``eps=1e-3``; on a ~200u-wide floor triangle that is ~0.1u of slop past the edge. A
settled ``old`` parks a hair PAST a floor edge (WallCorrect braces it against the seam wall, which can
overhang the floor lip by a fraction of a unit), so the loose test counted an off-floor point as
standable. The game's ``cBgW::RwgGroundCheck`` uses ``cM3d_CrossY_Tri_Front`` (strict (z,x) AABB + all
three signed areas >= -20, the front winding), which rejects those points -- Link finds no ground and
falls. NOTE the material hypothesis (a void/lava ground-code) was DISPROVEN: every Asoko faller floor is
ground-code 0 / attribute NORMAL; the defect is geometric edge slop, not surface material.

The fix (``collision.cross_y_tri_front`` + ``ground_cross_y``, wired into ``floor_ys_at``) makes the
standability gate bit-faithful to the game, so the search itself excludes an ``old`` with no accepted
floor. Validated LIVE on Asoko Room0 (clean-place each init, read current.pos.y): the 12 fallers all
fall (empty floor list) and the 8 standers all hold -- 20/20 -- and the shipped ``seam_locator``
scan drops from 20 reported clips to the 8 standable ones. This test is Dolphin-free (captured
sub-region golden covering both classes at y~=-100)."""
import os

import pytest

from harness.collision.seam_scan import load_region_tris, floor_ys_at, GROUND_NY_MIN
from harness.collision.seam_locator import scan_region

_G = os.path.join(os.path.dirname(__file__), "golden")
BOX = (-450.0, 400.0, -160.0, 120.0, 1700.0, 2750.0)

# (x, z) of representative reported inits, from the pre-fix Asoko Room0 CSV, with the LIVE verdict
# (clean-placement current.pos.y read). Each faller finds no ground; each stander holds.
FALLER_XZ = [(373.5209, 2171.8362), (67.3454, 2699.5706), (117.6740, 1788.3165),
             (-398.8347, 2276.2898), (-398.8344, 1892.7620)]      # idx 4, 7, 9, 13/14, 17
STANDER_XZ = [(270.2037, 1808.2576), (-208.5110, 1788.4203), (144.8166, 1900.3423),
              (-262.6905, 2418.7065), (-262.6906, 2590.4055)]     # idx 6, 8, 16, 18, 19


def _region():
    return load_region_tris(os.path.join(_G, "asoko_ground_region.json"))[0]


def test_floor_ys_at_rejects_off_edge_fallers():
    """The faithful ground test finds NO floor under an ``old`` parked off a floor edge (the game
    falls there); it DOES find one under a stander. This is the fix at the predicate level."""
    ground = [t for t in _region() if t["n"][1] >= GROUND_NY_MIN]
    for x, z in FALLER_XZ:
        assert floor_ys_at(ground, x, z) == [], (x, z)
    for x, z in STANDER_XZ:
        assert floor_ys_at(ground, x, z), (x, z)


@pytest.mark.slow
def test_scanner_excludes_unstandable_inits():
    """End-to-end: the shipped locator's search itself excludes the faller seams (their only settleable
    ``old`` is off the floor) and keeps the standable ones. Before the fix all were reported."""
    region = _region()
    clips = scan_region(region, BOX, verbose=False)
    got = [(round(c["old"][0], 1), round(c["old"][2], 1)) for c in clips]
    for x, z in FALLER_XZ:
        assert not any(abs(gx - x) < 2.0 and abs(gz - z) < 2.0 for gx, gz in got), (x, z, got)
    for x, z in STANDER_XZ:
        assert any(abs(gx - x) < 2.0 and abs(gz - z) < 2.0 for gx, gz in got), (x, z, got)
