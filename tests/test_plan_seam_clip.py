"""Offline regression for the seam-clip INPUT PLANNER (harness/collision/plan_seam_clip.py).

Guards the bridge from (start pose + seam) to an emitted controller input sequence:
  1. On the live-anchored Hyrule (-1727,-990) corner it derives the correct roll facing (40874 BAM),
     reports the bare roll-stab as short, and closes the clip with a ~1.5u Tetra overlap placed at the
     live-confirmed centre (matches test_tetra_clip / actor-push.md).
  2. The emitted sequence is the aimed roll-stab skeleton (draw B, run up, A roll, kroll=15, thrust),
     consumable by LandState.step, with the aim stick straight-up when the camera faces the clip.
  3. stick_for_bearing round-trips: the emitted aim stick reproduces the target facing for a tilted
     camera (the live fine-aim).

Robust to the gitignored cut-keyframe data being absent: enter_cut falls back to the golden 49.22u
magnitude, so the disp/clip assertions carry tolerances.
"""
import json
import math
import os
import struct


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from tww_sim.core.collision import Tri, Plane
from tww_sim.land.plan_land import world_angle_s16, stick_for_bearing
from harness.collision.plan_seam_clip import plan_seam_clip, KROLL, A_BTN, B_BTN

CLIP_FACING = 40874          # anchor old->new bearing (~224.5 deg); see actor-push.md


def _fh(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def _anchor():
    p = os.path.join(os.path.dirname(__file__), "golden", "hyrule_seam_1727_ram.json")
    g = json.load(open(p))
    tris = [Tri([_fh(x) for x in t["v"][0]], [_fh(x) for x in t["v"][1]], [_fh(x) for x in t["v"][2]],
                plane=Plane(*[_fh(x) for x in t["n"]], _fh(t["D"]))) for t in g["tris"]]
    link_y = _fh(g["seam_v_hex"][1])
    old = (_fh(g["old_hex"][0]), _fh(g["old_hex"][1]))
    new = (_fh(g["new_hex"][0]), _fh(g["new_hex"][1]))
    return tris, link_y, old, new


def test_hyrule_1727_plan_needs_push_and_clips():
    tris, link_y, old, new = _anchor()
    r = CLIP_FACING / 65536.0 * 2 * math.pi
    start = (old[0] - 200.0 * math.sin(r), old[1] - 200.0 * math.cos(r))   # 200u back on the clip ray
    plan = plan_seam_clip(tris, old, new, start, link_y, cut="CUT_F")

    assert plan["clips"]
    # roll facing is the old->new bearing (the 49.22 lunge fires along it)
    assert plan["facing_clip"] == world_angle_s16(new[0] - old[0], new[1] - old[1]) == CLIP_FACING
    # the bare roll-stab (~49.22u) is short of the ~49.96u f32 clip endpoint -> needs a push
    assert abs(plan["disp"] - 49.2202) < 5e-2
    assert plan["needs_push"] and not plan["reachable_rollstab"]
    # the Tetra push closes it at the live-confirmed ~1.5u overlap / ~0.75u share / centre ~(-1623.7,-903.8)
    pp = plan["push"]
    assert pp is not None
    assert 1.2 < pp["overlap"] < 1.8 and abs(pp["push_mag"] - 0.5 * pp["overlap"]) < 1e-3
    assert abs(pp["tetra_center"][0] - (-1623.7)) < 1.5 and abs(pp["tetra_center"][1] - (-903.8)) < 1.5


def test_emitted_sequence_shape():
    tris, link_y, old, new = _anchor()
    plan = plan_seam_clip(tris, old, new, (old[0], old[1] - 200.0), link_y, cut="CUT_F")
    seq = plan["seq"]
    # each frame is (sx, sy, buttons, triggerL)
    assert all(len(f) == 4 for f in seq)
    a_idx = [i for i, f in enumerate(seq) if f[2] & A_BTN]
    b_idx = [i for i, f in enumerate(seq) if f[2] & B_BTN]
    assert len(a_idx) == 1, "exactly one A (roll) press"
    assert len(b_idx) == 2, "two B presses: the sword draw and the thrust"
    # kroll held frames between the roll and the thrust
    assert b_idx[1] - a_idx[0] - 1 == KROLL


def test_aim_stick_roundtrips_for_tilted_camera():
    # A camera yawed 3000 BAM off the clip facing -> a tilted aim stick that still targets the facing.
    tris, link_y, old, new = _anchor()
    cam = (CLIP_FACING + 3000) & 0xFFFF
    plan = plan_seam_clip(tris, old, new, (old[0], old[1] - 200.0), link_y, csangle=cam)
    sx, sy = plan["aim_stick"]
    assert (sx, sy) != (128, 255), "off-axis camera should tilt the stick (the live fine-aim)"
    assert plan["aim_stick"] == stick_for_bearing(CLIP_FACING, csangle=cam)


def test_camera_forward_gives_straight_up_stick():
    tris, link_y, old, new = _anchor()
    plan = plan_seam_clip(tris, old, new, (old[0], old[1] - 200.0), link_y)   # csangle defaults to facing
    assert plan["csangle"] == plan["facing_clip"]
    assert plan["aim_stick"] == (128, 255)
