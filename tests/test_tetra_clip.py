"""Offline regression for the Tetra Co-push model + clip pipeline.

Guards:
  1. cyl-cyl overlap depth (cM3d_Cross_CylCyl) + the dCcS::SetPosCorrect rank-table weight split —
     the pure math, incl. the live-confirmed 0.50 share (Link rank 5 vs Tetra rank 5) and push
     direction, and the immovable (0xFF, rank 10) case that gives Link the full depth.
  2. The pipeline on the live (-1727,-990) anchor: a roll/thrust at 49.22u does NOT clip alone, but a
     Tetra placed behind Link with a small overlap DOES — min overlap ~1.23u (push ~0.615u at the
     0.50 share).

Decomp-grounded (see tww_sim/core/cc_push.py); weights & cylinders live-confirmed on GZLJ01 (2026-07-06).
"""
import json
import math
import os
import struct

from tww_sim.core.cc_push import (co_push_link, cyl_cyl_cross_len, get_rank, push_shares,
                                   WEIGHT_LINK, WEIGHT_TETRA_V5, WEIGHT_TETRA_DEFAULT)
from tww_sim.core.collision import Tri, Plane
from harness.collision.gap_search import settle
from harness.collision.tetra_clip import clip_with_push, LINK_CO_R, TETRA_CO_R


def _fh(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def _load_anchor():
    g = json.load(open(os.path.join(os.path.dirname(__file__), "golden", "hyrule_seam_1727_ram.json")))
    tris = [Tri([_fh(x) for x in t["v"][0]], [_fh(x) for x in t["v"][1]], [_fh(x) for x in t["v"][2]],
                plane=Plane(*[_fh(x) for x in t["n"]], _fh(t["D"]))) for t in g["tris"]]
    link_y = _fh(g["seam_v_hex"][1])
    old = (_fh(g["old_hex"][0]), _fh(g["old_hex"][1]))
    new = (_fh(g["new_hex"][0]), _fh(g["new_hex"][1]))
    return tris, link_y, old, new


# Anchor old->new direction (224.5 deg): the corner clip facing (see knowledge/mechanics/actor-push.md
# "Live corner reproduction"). Live-achievable at stickX~96; razor-thin window (~30 BAM matters).
CLIP_FACING = 40874


# ---- the pure math ---------------------------------------------------------

def test_get_rank():
    # GetRank thresholds (d_cc_s.cpp:153). Link 120 and Tetra 140 both land on rank 5.
    assert get_rank(120) == 5 and get_rank(140) == 5
    assert get_rank(0xFF) == 10 and get_rank(0xFE) == 9 and get_rank(0x01) == 1 and get_rank(0) == 0
    assert get_rank(0x6D) == 5 and get_rank(0x91) == 6      # boundary


def test_push_shares_rank_table():
    # Link(rank5) vs Tetra-v5(rank5) -> rank_tbl[5][5]=50 -> exact 50/50 (live-confirmed).
    s = push_shares(WEIGHT_LINK, WEIGHT_TETRA_V5)
    assert s is not None and abs(s[0] - 0.5) < 1e-7 and abs(s[1] - 0.5) < 1e-7
    # Immovable Tetra (0xFF, rank10): rank_tbl[5][10]=100 -> Link takes the full depth.
    s2 = push_shares(WEIGHT_LINK, WEIGHT_TETRA_DEFAULT)
    assert abs(s2[0] - 1.0) < 1e-7
    # both immovable -> no correction
    assert push_shares(0xFF, 0xFF) is None


def test_overlap_depth_and_gates():
    # centers 79.6 apart, Link R=30 + Tetra R=50 -> overlap 0.4
    hit, cl = cyl_cyl_cross_len((0.0, 0.0, 0.0), 30, 81.25, (-79.6, 0.0, 0.0), 50, 140)
    assert hit and abs(cl - 0.4) < 1e-4
    # XZ miss (dist > sum of radii = 80)
    hit, cl = cyl_cyl_cross_len((0.0, 0.0, 0.0), 30, 81.25, (-81.0, 0.0, 0.0), 50, 140)
    assert not hit and cl == 0.0
    # Y ranges don't overlap (Link far above Tetra's top)
    hit, cl = cyl_cyl_cross_len((0.0, 300.0, 0.0), 30, 81.25, (-79.6, 0.0, 0.0), 50, 140)
    assert not hit


def test_push_split_share_and_direction():
    # Tetra-v5 vs Link: Link takes 0.50 of the depth, away from Tetra (+x here).
    link = (0.0, 0.0, 0.0)
    tetra = (-79.6, 0.0, 0.0)           # Tetra at -x -> push toward +x
    px, py, pz = co_push_link(link, 30, 81.25, tetra, 50, 140, other_w=WEIGHT_TETRA_V5)
    assert py == 0.0 and abs(pz) < 1e-6
    assert px > 0.0                                   # away from Tetra
    assert abs(px - 0.4 * 0.5) < 1e-4                 # 0.50 * depth
    # Immovable Type0 Tetra (0xFF) instead gives Link the FULL depth
    px0, _, _ = co_push_link(link, 30, 81.25, tetra, 50, 140, other_w=WEIGHT_TETRA_DEFAULT)
    assert abs(px0 - 0.4) < 1e-4


def test_push_deadzone():
    # overlap 5e-6 < cM3d_IsZero (1e-5) -> no push
    p = co_push_link((0.0, 0.0, 0.0), 30, 81.25, (-79.999995, 0.0, 0.0), 50, 140, other_w=WEIGHT_TETRA_V5)
    assert p == (0.0, 0.0, 0.0)


# ---- the pipeline on the live anchor --------------------------------------

def _bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _modeled_thrust(facing=CLIP_FACING):
    """The roll-stab's first-frame lunge (dx, dz), MODELED by the land sim (LandState.enter_cut out of a
    26u roll) aimed at ``facing`` -- the real stacked roll+sword-thrust vector (bit-exact vs live,
    tests/test_land.py::test_rollstab_cut_bit_exact), replacing the old ``unit(old->new) * 49.22``
    synthetic reconstruction. When the cut keyframe data is absent, fall back to the golden magnitude
    (49.2202) aimed along ``facing``."""
    try:
        from tww_sim.land.land import LandState, CUT_F, FRONT_ROLL
        s = LandState(pos_x=0.0, pos_z=0.0, facing=facing, travel=facing, state=FRONT_ROLL,
                      nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
        return s.enter_cut(CUT_F)
    except Exception:
        r = facing / 65536.0 * 2 * math.pi
        return (49.2202 * math.sin(r), 49.2202 * math.cos(r))


def _roll_center(old, facing):
    """Link's FRONT_ROLL body Co cyl centre at the corner (live-validated bit-exact); feet proxy if the
    anim data is absent."""
    try:
        from tww_sim.core.anim import body_cyl
        if body_cyl.available():
            return body_cyl.roll_co_center(old[0], old[1], facing, 12.0)
    except Exception:
        pass
    return None


def test_tetra_push_closes_the_1727_clip():
    """Roll + sword-thrust alone is blocked at the (-1727,-990) corner; a Tetra nudge clips it. The move
    is now MODEL-DERIVED end to end: the thrust (dx, dz) is LandState.enter_cut out of a 26u roll aimed at
    the anchor's clip facing (bit-exact vs live, test_rollstab_cut_bit_exact), and the push geometry uses
    Link's live-validated FRONT_ROLL body-cyl centre (roll_co_center) -- no ``unit(old->new)`` synthetic
    reconstruction. The Tetra sits behind Link at the overlap the anchor implies (the push the live clip
    needed = NEW - OLD - thrust), and the pipeline then reproduces the live clip endpoint bit-for-bit."""
    tris, link_y, old, new = _load_anchor()
    lc = _roll_center(old, CLIP_FACING)
    thrust = _modeled_thrust()
    assert abs(math.hypot(*thrust) - 49.2202) < 1e-3, f"modeled roll-stab lunge {thrust} != 49.2202"

    # roll + thrust ALONE (Tetra infinitely far behind) does NOT clip -- live-confirmed at the corner
    # (a bare roll-stab bonks off the wall, proc 0x5A; 2026-07-06 capture).
    base = clip_with_push(old, link_y, thrust, (old[0] - 1e6, old[1]), tris, link_center=lc)
    assert not base["clipped"], "roll+thrust ~49.22u should NOT clip without Tetra"

    # Push the clip needed = NEW - OLD - thrust; at the 0.50 rank split, overlap = 2*|push|. Place Tetra
    # behind Link's cyl centre along -push at centre distance sumR - overlap.
    pneed = (new[0] - old[0] - thrust[0], new[1] - old[1] - thrust[1])
    pm = math.hypot(*pneed)
    overlap = 2.0 * pm
    assert 0.5 < overlap < 3.0, f"implied Tetra overlap {overlap} off the ~1.5u expectation"
    ctr = lc if lc is not None else old
    cd = (LINK_CO_R + TETRA_CO_R) - overlap
    u = (pneed[0] / pm, pneed[1] / pm)
    tetra = (ctr[0] - cd * u[0], ctr[1] - cd * u[1])

    r = clip_with_push(old, link_y, thrust, tetra, tris, link_center=lc)
    assert r["clipped"], "the modeled thrust + implied Tetra push should clip"
    # reproduces the live clip endpoint (NEW) to well under a ULP-scale unit
    assert abs(r["new"][0] - new[0]) < 5e-3 and abs(r["new"][1] - new[1]) < 5e-3, \
        f"pipeline new {r['new']} != live NEW {new}"
    # the push Link actually gets is 0.50 * overlap
    assert abs(math.hypot(*r["push"]) - 0.5 * overlap) < 1e-3, "push should be 0.50 * overlap"


def test_real_roll_alone_is_short():
    """The land sim's modeled FRONT_ROLL caps at 26u/frame -- below the 35u seam-clip floor, so a roll
    ALONE (without the stacked sword thrust) does not clip the (-1727,-990) corner. The thrust half of
    the ~49u stacked move is now modeled too (CUT_F/CUT_A; test_rollstab_cut_bit_exact) -- see
    test_tetra_push_closes_the_1727_clip for the full modeled roll+thrust; this guards the roll alone."""
    tris, link_y, old, new = _load_anchor()
    settled = settle(tris, old, link_y)
    dx, dz = new[0] - settled[0], new[1] - settled[2]
    dm = math.hypot(dx, dz); dhx, dhz = dx / dm, dz / dm
    ROLL_CAP = 26.0                                    # clamp(speedF*1.5+0.5, 5, 0.5+17*1.5)
    thrust = (dhx * ROLL_CAP, dhz * ROLL_CAP)
    base = clip_with_push((settled[0], settled[2]), link_y, thrust, (settled[0] - 1e6, settled[2]), tris)
    assert not base["clipped"], "a 26u roll alone must NOT clip (needs the stacked thrust)"
    assert abs(base["disp"] - 26.0) < 0.02, "modeled roll displacement should be the 26u cap"
