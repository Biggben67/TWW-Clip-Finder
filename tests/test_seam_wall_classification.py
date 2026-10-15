"""Regression guard for the background-collision WALL/GROUND/ROOF classification (the normal-Y split
that routes a triangle to WallCorrect vs GroundCross), and the Omori Room0 false-positive it fixed.

Root cause (2026-07-15, Omori locator-vs-live diagnosis): the seam-clip scanner classified a "wall"
as ``|ny| < 0.03`` (near-vertical only). The game (``cBgW_CheckB*``, SSystem/SComponent/c_bg_w.h)
classifies by the triangle NORMAL's Y: ``ny >= 0.5`` ground, ``ny < -0.8`` roof, ELSE wall -- so a
sloped wall up to ny 0.5 IS a wall. At the Omori Room0 seam S=(1075.9, 350, -1190.57) a sloped wall
(poly 392, ny=0.384) shares the seam vertex; the game's WallCorrect braces the r=35 cylinder on it and
BLOCKS (live drift 35.70), but the strict ``|ny|<0.03`` filter dropped it, so the offline model saw a
phantom clip. The fix classifies with the decomp predicates everywhere. This test is Dolphin-free.
"""
import os

from tww_sim.core.collision import (bg_is_ground, bg_is_roof, bg_is_wall, bg_blocks_crrpos,
                                     crr_pos_walls, BG_GROUND_NY, BG_ROOF_NY)
from tww_sim.core.fp import f32 as _f
from harness.collision.seam_scan import load_region_tris, enumerate_seams, GROUND_NY_MIN
from harness.collision.seam_locator import locate

_G = os.path.join(os.path.dirname(__file__), "golden")

# The exact live-diagnosed coords (full f32 precision -- a razor verdict flips on sub-0.001u).
OMORI_OLD = (1036.069091796875, 358.0038757324219, -1157.871826171875)
OMORI_NEW = (1076.442626953125, 358.0038757324219, -1191.0167236328125)
OMORI_BOX = (900.0, 1340.0, 300.0, 600.0, -1440.0, -980.0)


def test_classification_matches_decomp_thresholds():
    """cBgW_CheckBGround (ny>=0.5), cBgW_CheckBRoof (ny<-0.8), cBgW_CheckBWall (in between)."""
    assert BG_GROUND_NY == 0.5 and BG_ROOF_NY == -4.0 / 5.0
    # ground
    assert bg_is_ground(0.5) and bg_is_ground(0.98) and not bg_is_ground(0.49)
    # roof (strict <)
    assert bg_is_roof(-0.81) and not bg_is_roof(-0.8)
    # wall = neither: near-vertical AND the sloped ones the old |ny|<0.03 dropped
    assert bg_is_wall(0.0) and bg_is_wall(0.342) and bg_is_wall(0.384)   # polys 386 / 392
    assert bg_is_wall(-0.8) and not bg_is_wall(0.5) and not bg_is_wall(-0.9)
    # CrrPos blocker set = wall + roof = NOT ground (WallCorrect walks both lists)
    assert bg_blocks_crrpos(0.384) and bg_blocks_crrpos(-0.9) and not bg_blocks_crrpos(0.5)


def _region():
    return load_region_tris(os.path.join(_G, "omori_seam_region.json"))[0]


def test_omori_seam_strict_filter_false_positives_but_correct_blocks():
    """The bug + the fix in one place: the old near-vertical-only wall set THREADS the Omori clip;
    the decomp blocker set (wall+roof) BLOCKS it -- reproducing the live drift ~35.7."""
    region = _region()
    po = (_f(OMORI_OLD[0]), _f(OMORI_OLD[1]), _f(OMORI_OLD[2]))
    pn = (_f(OMORI_NEW[0]), _f(OMORI_OLD[1]), _f(OMORI_NEW[2]))

    strict = [t["T"] for t in region if abs(t["n"][1]) < 0.03]          # the OLD (buggy) wall filter
    res_s, _ = crr_pos_walls(po, pn, strict)
    drift_s = ((res_s[0] - OMORI_NEW[0]) ** 2 + (res_s[2] - OMORI_NEW[2]) ** 2) ** 0.5
    assert drift_s < 1.0                                                # would-be phantom clip

    correct = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]   # the decomp-faithful set
    res_c, info = crr_pos_walls(po, pn, correct)
    drift_c = ((res_c[0] - OMORI_NEW[0]) ** 2 + (res_c[2] - OMORI_NEW[2]) ** 2) ** 0.5
    assert info["wall_hit"] and 35.0 < drift_c < 36.5                   # matches live BLOCK (35.70)


def test_omori_seam_not_located():
    """The shipped locator now REJECTS the Omori seam (matches the live teleport BLOCK)."""
    region = _region()
    ground = [t for t in region if t["n"][1] >= GROUND_NY_MIN]
    seam = min(enumerate_seams(region, OMORI_BOX),
               key=lambda s: (s["S"][0] - 1075.9) ** 2 + (s["S"][2] + 1190.6) ** 2)
    assert seam["polys"] == [383, 388] and round(seam["interior"], 1) == 160.1
    assert locate(region, ground, seam, {}) is None
