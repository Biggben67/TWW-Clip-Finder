"""Offline regression for the CC-push COUPLED stepper (Phase C: the push wired into the per-frame
stepper). Guards the three wiring facts, all decomp-grounded (d_a_player_main.cpp / d_cc_s.cpp /
d_s_play.cpp; see harness/rollstab/cc_stepper.py + mechanics/actor-push.md):

  1. ``cc_push.co_move_pair`` reproduces ``dCcS::SetPosCorrect`` for BOTH actors -- its Link (obj1)
     move is bit-identical to the shipped ``co_push_link``, its Tetra (obj2) move is the decomp's
     ``vec2`` (equal-and-opposite for the same-rank 50/50 pair; the immovable partner recoils 0).
  2. ``LandState`` consumes ``_cc_move`` at the decomp point in ``posMove`` -- AFTER the speedF/foot
     move, BEFORE the CrrPos wall pass -- so on a plain FRONT_ROLL frame the push f32-adds onto the
     post-integration position exactly (and None / (0,0,0) is byte-identical to the no-push path).
  3. The coupled stepper produces equal-and-opposite pushes on an overlap (fed to both on the next
     frame) and zero when the cylinders miss.
"""
import struct

import pytest


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from tww_sim.core.cc_push import (co_move_pair, co_push_link, push_shares,
                                   WEIGHT_LINK, WEIGHT_TETRA_V5, WEIGHT_TETRA_DEFAULT)
from tww_sim.core.fp import f32
from tww_sim.land.land import LandState, FRONT_ROLL, CUT_F


def _bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


# ---- (1) co_move_pair == SetPosCorrect for both actors ---------------------

def test_co_move_pair_link_matches_co_push_link():
    """obj1 (Link) move from co_move_pair is bit-identical to the shipped co_push_link (same decomp
    vec1 = -objsDist*obj2Weight); tested off-axis so all components exercise."""
    link = (10.0, 0.16, -5.0)
    tetra = (-69.6, 0.16, -8.2)
    for w in (WEIGHT_TETRA_V5, WEIGHT_TETRA_DEFAULT):
        lm, _tm = co_move_pair(link, 30, 81.25, tetra, 50, 140, w1=WEIGHT_LINK, w2=w)
        lp = co_push_link(link, 30, 81.25, tetra, 50, 140, link_w=WEIGHT_LINK, other_w=w)
        assert tuple(_bits(a) for a in lm) == tuple(_bits(b) for b in lp)


def test_co_move_pair_tetra_recoil():
    link = (10.0, 0.16, -5.0)
    tetra = (-69.6, 0.16, -8.2)
    # same-rank (Link 5 vs Tetra-v5 5) -> 50/50 -> equal and opposite, sum bit-exactly zero.
    lm, tm = co_move_pair(link, 30, 81.25, tetra, 50, 140, w1=WEIGHT_LINK, w2=WEIGHT_TETRA_V5)
    assert push_shares(WEIGHT_LINK, WEIGHT_TETRA_V5)[0] == pytest.approx(0.5)
    for a, b in zip(lm, tm):
        assert _bits(f32(a + b)) == _bits(0.0)
    # immovable Tetra (0xFF, rank 10): rank_tbl[5][10]=100 -> Link full depth, Tetra recoils 0.
    lm2, tm2 = co_move_pair(link, 30, 81.25, tetra, 50, 140, w1=WEIGHT_LINK, w2=WEIGHT_TETRA_DEFAULT)
    assert all(_bits(c) in (_bits(0.0), _bits(-0.0)) for c in tm2)
    # Link's immovable-partner move is 2x the 50/50 move (share 1.0 vs 0.5).
    assert abs(lm2[0] - 2.0 * lm[0]) < 1e-6 and abs(lm2[2] - 2.0 * lm[2]) < 1e-6


def test_co_move_pair_misses_and_deadzone():
    link = (0.0, 0.0, 0.0)
    z = (0.0, 0.0, 0.0)
    # XZ miss (centers 81 apart > sumR 80)
    lm, tm = co_move_pair(link, 30, 81.25, (-81.0, 0.0, 0.0), 50, 140)
    assert lm == z and tm == z
    # deadzone: overlap 5e-6 < cM3d_IsZero (1e-5)
    lm, tm = co_move_pair(link, 30, 81.25, (-79.999995, 0.0, 0.0), 50, 140)
    assert lm == z and tm == z


# ---- (2) LandState consumes _cc_move at the posMove point ------------------

def _roll_state():
    # A moving FRONT_ROLL frame (walls off): push is the only term after the speedF integration, so
    # final pos == f32(post_speedf + push). Built in-FRONT_ROLL (bypass _roll_init) -> set the latch.
    s = LandState(pos_x=100.0, pos_z=200.0, facing=8000, travel=8000, state=FRONT_ROLL,
                  nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
    s._roll_m3570 = True
    return s


def test_cc_move_zero_is_byte_identical():
    a = _roll_state(); a.step(0, 0)
    b = _roll_state(); b.set_cc_move((0.0, 0.0, 0.0)); b.step(0, 0)
    c = _roll_state(); c.set_cc_move(None); c.step(0, 0)
    assert _bits(a.pos_x) == _bits(b.pos_x) == _bits(c.pos_x)
    assert _bits(a.pos_z) == _bits(b.pos_z) == _bits(c.pos_z)


def test_cc_move_f32_adds_after_speedf_on_roll_frame():
    """On a plain FRONT_ROLL frame the push is the LAST position term (no cut, no wall), so the
    pushed position is bit-exactly f32(no-push position + push) componentwise."""
    push = (0.375, 0.0, -0.212)
    base = _roll_state(); base.step(0, 0)
    pushed = _roll_state(); pushed.set_cc_move(push); pushed.step(0, 0)
    assert _bits(pushed.pos_x) == _bits(f32(base.pos_x + push[0]))
    assert _bits(pushed.pos_z) == _bits(f32(base.pos_z + push[2]))


def test_cc_move_shifts_cut_frame():
    """On the roll-stab cut frame the push still lands (before the m34C2 root-translate lunge + the
    CrrPos wall pass), moving the endpoint vs the no-push cut."""
    base = _roll_state(); base.enter_cut(CUT_F); base.step(0, 0)
    pushed = _roll_state(); pushed.enter_cut(CUT_F); pushed.set_cc_move((1.0, 0.0, 1.0)); pushed.step(0, 0)
    assert (_bits(pushed.pos_x) != _bits(base.pos_x)) or (_bits(pushed.pos_z) != _bits(base.pos_z))


def test_cc_move_rejected_on_native_path():
    s = LandState(pos_x=0.0, pos_z=0.0, state=FRONT_ROLL, nspeed=26.0, speedF=26.0,
                  use_anim=False, native=True)      # native on (no walls) -> no CC pass
    if s._core is None:
        pytest.skip("native LandCore unavailable in this build")
    s.set_cc_move((1.0, 0.0, 0.0))
    with pytest.raises(RuntimeError):
        s.step(0, 0)


# ---- (3) the coupled stepper ----------------------------------------------

def test_coupled_stepper_equal_opposite_and_miss():
    from tww_sim.core.npc_zl1 import Zl1FollowState
    from harness.rollstab.cc_stepper import CcCoupledStepper, LINK_CO_R, TETRA_CO_R

    # Tetra seeded AT Link's start (feet-centered Co via use_anim off): the roll carries Link ~26u
    # this frame, leaving ~26u < sumR 80 so the post-step CC check overlaps ~54u; she idles (<130u).
    link = _roll_state()
    sumr = LINK_CO_R + TETRA_CO_R                 # 80
    tetra = Zl1FollowState(x=link.pos_x, y=link.pos_y, z=link.pos_z, angle_y=0, speedF=0.0)
    drv = CcCoupledStepper(link, tetra, ground_y=link.pos_y,
                           link_co_center_fn=lambda l: (l.pos_x, l.pos_y, l.pos_z))
    r = drv.step(0, 0)
    # first frame: pushes consumed are the seeds (None/zero); the CHECK produced next-frame pushes.
    nl, nt = r["next_link_push"], r["next_tetra_push"]
    assert nl != (0.0, 0.0, 0.0)                  # overlapping -> nonzero
    for a, b in zip(nl, nt):                       # 50/50 equal-and-opposite
        assert _bits(f32(a + b)) == _bits(0.0)

    # A clearly-separated Tetra -> no overlap -> zero push.
    link2 = _roll_state()
    far = Zl1FollowState(x=link2.pos_x - 500.0, y=link2.pos_y, z=link2.pos_z, angle_y=0)
    drv2 = CcCoupledStepper(link2, far, ground_y=link2.pos_y,
                            link_co_center_fn=lambda l: (l.pos_x, l.pos_y, l.pos_z))
    r2 = drv2.step(0, 0)
    assert r2["next_link_push"] == (0.0, 0.0, 0.0) and r2["next_tetra_push"] == (0.0, 0.0, 0.0)
