"""Offline gate for the ROLL-STAB CLIP FRAME's three-way ordering (ROADMAP Phase C).

Replays a locked live capture (`fixtures/hyrule_cc_rollstab.json`, from
`harness/rollstab/capture_cc_push.py` with `draw_at=`/`thrust_at=` on slot 3) through the coupled
Link+Tetra stepper WITHOUT Dolphin and diffs every frame bit-for-bit. The scenario is the seam-clip
lunge itself: the sword is drawn during the walk-up, Link rolls into the corner-braced Tetra (Co push
active, ~22u), and on the clip frame he fires a FORWARD `CUT_F` out of the roll -- so that single frame
stacks, in the decomp's `posMove` order (`d_a_player_main.cpp:2556-2610`):

    posMoveFromFootPos (the roll speedF move)
      -> consume mStts.m_cc_move   (the CC push accumulated from the prior frame's dCcS overlap)
      -> the m34C2 cut root-translate lunge  (~49u, the roll-stab)
      -> dBgS_Acch::CrrPos          (the wall pass)

This is THE clip frame the Tetra seam clip rides. What this locks in as bit-exact (0 ULP): every frame
from Tetra's placement through the `CUT_F` entry frame -- the roll-into-braced-Tetra approach AND the
push x cut-lunge x wall-pass interaction on the clip frame -- for BOTH actors.

Scope: through the `CUT_F` ENTRY frame (the single-frame lunge that decides the clip). The CUT *tail*
(the frames after entry) is a separate, non-clip gap and is intentionally NOT asserted: the sim keeps
posing Link's Co centre with the frozen roll anim (`body_cyl.roll_co_center`) rather than the CUT pose,
and live enters a post-cut recovery proc (`0x5a`) the sim does not model -- both irrelevant to the clip,
which is fully decided by the entry-frame lunge (like the already-descoped roll->MOVE exit gap; see
`test_cc_gate`). Model the CUT-pose Co centre + the recovery proc to extend the window.
"""
import json
import math
import os

import pytest

_HERE = os.path.dirname(__file__)
_FIX = os.path.join(_HERE, "..", "fixtures", "hyrule_cc_rollstab.json")
_WALLS = os.path.join(_HERE, "..", "fixtures", "hyrule_tetra_walls_ordered.json")

CUT_F_PROC = 0x42               # daPyProc_CUT_F_e -- the forward thrust (a neutral B is a side slash)
FRONT_ROLL_PROC = 30
CO_OVERLAP_DIST = 80.0          # LINK_CO_R (30) + TETRA_CO_R (50): closer than this => the Co push fires


def _load():
    from tww_sim.land.walls import load_ordered_mesh
    from harness.rollstab.cc_stepper import couple_replay
    fix = json.load(open(_FIX))
    walls = load_ordered_mesh(_WALLS)
    res = couple_replay(fix["frames"], fix["tetra_placed_at"], fix["tetra_placed_xz"],
                        walls, fix["ground_y"], sword_drawn=fix.get("sword_drawn", True))
    return fix, res


def test_fixture_present():
    assert os.path.exists(_FIX), (
        "run: python -m harness.rollstab.capture_cc_push out=fixtures/hyrule_cc_rollstab.json "
        "draw_at=2 thrust_at=15 place_after_roll=0 walk=6 roll_frames=24 tcx=-1710 tcz=-965 (slot 3)")


@pytest.mark.slow
def test_clip_frame_ordering_bitexact():
    """Every frame from Tetra's placement through the CUT_F ENTRY (the clip frame) is 0 ULP for BOTH
    actors -- the roll-into-braced-Tetra approach AND the push x cut-lunge x CrrPos ordering on the
    clip frame. The clip frame must be a FORWARD CUT_F (not a side slash) reached out of a real roll,
    with the actors overlapping so the CC push is genuinely exercised on it."""
    _fix, res = _load()
    clip = next((r for r in res if r["proc"] == CUT_F_PROC), None)
    assert clip is not None, "no CUT_F frame -> the roll-stab did not dispatch (draw/thrust timing off)"

    roll_before = [r for r in res if r["proc"] == FRONT_ROLL_PROC and r["f"] < clip["f"]]
    assert len(roll_before) >= 10, "CUT_F did not come out of a real roll (too few FRONT_ROLL frames)"

    for r in res:
        if r["f"] > clip["f"]:
            break
        assert r["dlx"] == 0 and r["dlz"] == 0, (
            "Link not bit-exact at f%d (proc %d): dlx=%d dlz=%d" % (r["f"], r["proc"], r["dlx"], r["dlz"]))
        assert r["dtx"] == 0 and r["dtz"] == 0, (
            "Tetra not bit-exact at f%d (proc %d): dtx=%d dtz=%d" % (r["f"], r["proc"], r["dtx"], r["dtz"]))

    # meaningfulness: the actors overlap on the clip frame, so the CC push is live there (not a bare
    # cut+wall). Uses the LIVE positions (the sim already matched them bit-exact above).
    ov = math.hypot(clip["live_link"][0] - clip["live_tetra"][0],
                    clip["live_link"][1] - clip["live_tetra"][1])
    assert ov < CO_OVERLAP_DIST, (
        "actors not overlapping at the clip frame (dist=%.2f >= %.1f) -> the CC push is not exercised"
        % (ov, CO_OVERLAP_DIST))
