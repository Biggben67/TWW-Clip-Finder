"""Seam-clip INPUT PLANNER: given a start pose + a wall-corner seam, emit the controller input
sequence for a roll-stab that clips it.

This is the missing bridge between the three validated-but-disjoint pieces:

  * the collision geometry model (:mod:`harness.collision.seam_clip_check` / :mod:`seam_model` /
    :mod:`tetra_clip`) - answers "does a displacement clip THIS seam" and gives the settled ``old``,
    the f32-reachable ``new``, the clip facing, and whether a Tetra push is needed;
  * the roll-stab physics (:meth:`tww_sim.land.land.LandState.enter_cut`) - the decomp-faithful,
    live-0-ULP first-frame lunge (roll speedF 26 + ANM_CUT joint-0 root translate = ~49.22u); and
  * the land input inverse (:func:`tww_sim.land.plan_land.stick_for_bearing`) - the world-facing ->
    stick-byte inverse that also encodes the live fine-aim (a tilted stick to raise the roll facing).

None of these emitted a *controller input sequence from a start position + seam*. This module does.

Grounding (all decomp / live, nothing new invented here):
  * The roll faces ``shape_angle.y`` set to the stick target at ``procFrontRoll_init``
    (d_a_player_main.cpp:6837 ``current.angle.y = shape_angle.y``); the entry lunge fires along that
    facing (roll-stab.md). So aiming the ROLL aims the 49.22 lunge -> we solve for the roll facing.
  * The clip facing = the settled ``old`` -> f32 ``new`` bearing from the collision model.
  * The input skeleton mirrors the live-validated ``tests/dolphin/spotcheck_rollstab.py`` sequence
    (draw B, run up, A roll, ``kroll``=15 held frames = the "first possible" cut frame that carries
    the full 26, then the thrust), with the neutral-up stick replaced by the aimed stick.
  * The push half (when the bare 49.22 falls short) reuses the live-anchored Tetra pipeline
    (:mod:`tetra_clip`, ``dCcS`` rank-table 0.50 share; actor-push.md) to size the overlap and place
    Tetra's body cylinder.

What is model-validated vs open-loop: the CUT displacement and the clip/needs-push verdict are run
through the bit-exact collision + cut models (0-ULP vs live). The RUN-UP is emitted open-loop (the
land sim does not yet integrate WallCorrect, so it can't re-settle Link at ``old`` offline) - it is
aimed at the clip facing and relies, exactly as the live roll-stab does, on the wall pinning the roll
at ``old`` (the wall holds speedF=26 for 10+ frames; actor-push.md "The wall holds the roll speed").

Self-test (the live-anchored Hyrule (-1727,-990) corner - a real needs-push clip):
    python -m harness.collision.plan_seam_clip --selftest
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys

from tww_sim.core.collision import Tri, Plane
from tww_sim.core.cc_push import WEIGHT_TETRA_V5, WEIGHT_LINK, push_shares
from tww_sim.land.plan_land import stick_for_bearing, world_angle_s16
from harness.collision.gap_search import settle
from harness.collision.seam_clip_check import clip_check, ROLL_STAB_MAX
from harness.collision.tetra_clip import clip_with_push, LINK_CO_R, TETRA_CO_R

# Button bits (state.py step()): A=roll, B=sword/thrust, L(digital)=target for CUT_A.
A_BTN, B_BTN, L_BTN = 0x100, 0x200, 0x40
KROLL = 15                 # held frames between the A roll and the thrust (the full-26 "first" frame)


# ---------------------------------------------------------------- cut displacement (model / fallback)

def _modeled_thrust(facing, cut):
    """The roll-stab first-frame lunge (dx, dz), MODELED by the land sim (``LandState.enter_cut`` out of
    a 26u roll aimed at ``facing``) - bit-exact vs live. Falls back to ``unit(facing)*ROLL_STAB_MAX``
    when the dev cut-keyframe data (_generated/anim/link_anim_cuts.json) is absent."""
    try:
        from tww_sim.land.land import LandState, FRONT_ROLL, CUT_F, CUT_A
        ct = CUT_A if cut == "CUT_A" else CUT_F
        s = LandState(pos_x=0.0, pos_z=0.0, facing=facing, travel=facing, state=FRONT_ROLL,
                      nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
        return s.enter_cut(ct), True
    except Exception:
        r = facing / 65536.0 * 2 * math.pi
        return (ROLL_STAB_MAX * math.sin(r), ROLL_STAB_MAX * math.cos(r)), False


def _roll_center(old, facing):
    """Link's FRONT_ROLL body Co-cylinder centre at the corner (live-validated bit-exact); feet proxy
    (``old``) if the anim data is absent. Used to place Tetra on the true animated centre."""
    try:
        from tww_sim.core.anim import body_cyl
        if body_cyl.available():
            return body_cyl.roll_co_center(old[0], old[1], facing, 12.0)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- input emission

def _emit_seq(aim_stick, cut, runup_frames, tail_frames=8):
    """The aimed roll-stab controller sequence (list of ``(sx, sy, buttons, triggerL)`` per frame),
    mirroring the live-validated spotcheck skeleton with the neutral-up stick replaced by ``aim_stick``:

        [aim]*4  [aim+B(draw)]  [aim]*runup  [aim+A(roll)]  [aim]*KROLL  [THRUST]  [aim]*tail

    THRUST: CUT_F = aim + B; CUT_A = neutral stick + L(target) + B (the vertical slash, in-line 49.22).
    """
    ax, ay = aim_stick
    aim = (ax, ay, 0, 0)
    out = [aim] * 4
    out.append((ax, ay, B_BTN, 0))            # first B unsheathes the sword (no slash)
    out += [aim] * runup_frames               # run up: build speedF toward the 17 walk cap
    out.append((ax, ay, A_BTN, 0))            # A: forward roll (facing snaps to the aimed stick target)
    out += [aim] * KROLL                       # the 15 held frames -> the first cut frame carries full 26
    if cut == "CUT_A":
        out.append((128, 128, L_BTN | B_BTN, 255))     # L target + B, neutral stick
    else:
        out.append((ax, ay, B_BTN, 0))                 # up + B forward thrust
    out += [aim] * tail_frames
    return out


def _seq_string(seq):
    """Compact run-length per-frame string; renders +A / +B / +L button annotations and L-trigger."""
    def tok(st):
        sx, sy, btn, tl = st
        t = f"{sx},{sy}"
        if btn & A_BTN:
            t += "+A"
        if btn & B_BTN:
            t += "+B"
        if (btn & L_BTN) or tl >= 200:
            t += "+L"
        return t
    out = []
    for st in seq:
        k = tok(st)
        if out and out[-1][0] == k:
            out[-1][1] += 1
        else:
            out.append([k, 1])
    return " ".join(t if n == 1 else f"{t} x{n}" for t, n in out)


# ---------------------------------------------------------------- approach geometry

def _approach(start_pos, facing_clip, old):
    """The run-up geometry. The roll travels along ``facing_clip`` (its aimed facing), so to pass
    through ``old`` Link must start on the ray ``old - t*dir(facing_clip)``. Report the distance to
    ``old`` along that ray and Link's lateral offset from it (large offset -> reposition/pre-turn)."""
    r = facing_clip / 65536.0 * 2 * math.pi
    dirx, dirz = math.sin(r), math.cos(r)           # unit forward (matches pos_x+=sin, pos_z+=cos)
    vx, vz = old[0] - start_pos[0], old[1] - start_pos[1]
    along = vx * dirx + vz * dirz                    # signed distance start->old projected on the ray
    latx, latz = vx - along * dirx, vz - along * dirz
    lateral = math.hypot(latx, latz)
    return dict(runway=along, lateral_offset=lateral,
                bearing_to_old=world_angle_s16(vx, vz),
                on_ray=lateral < 1.0 and along > 0.0)


# ---------------------------------------------------------------- the planner

def discover_clip(tris, S, wallA, wallB, link_y):
    """Auto-discover a clip target for a seam when you don't already have one, via
    :func:`seam_clip_check.clip_check` on the geometry model (``tris`` as the barrier, no ground mesh,
    ``link_y`` supplied). Returns ``(old, new, link_y)`` or ``None``. The returned ``(old, new)`` is a
    near-minimal standable f32 clip; for the authoritative minimum use a live capture / ``min_f32_clip``
    and pass it to :func:`plan_seam_clip` directly."""
    geo = clip_check(tris, [], S, wallA, wallB, require_standable=False,
                     override_link_y=link_y, roll_stab=ROLL_STAB_MAX)
    if not geo["clips"]:
        return None
    return geo["old"], geo["new"], geo["link_y"]


def plan_seam_clip(tris, old, new, start_pos, link_y, csangle=None,
                   cut="CUT_F", tetra_weight=WEIGHT_TETRA_V5, runup_frames=18):
    """Plan a roll-stab seam clip from an AUTHORITATIVE clip target.

    ``tris`` = ALL wall :class:`Tri` near the seam (the CrrPos barrier set). ``old`` = the settled
    front-of-corner position (x,z) Link rolls into (a WallCorrect fixed point); ``new`` = the
    f32-representable clip endpoint just past the seam (x,z). Get these from a live capture / the seam
    anchor / :func:`min_f32_clip` (authoritative), or from :func:`discover_clip` (approximate).
    ``link_y`` = the floor height. ``start_pos`` = Link's start (x,z). ``csangle`` = the live camera
    yaw (s16); when None it is assumed equal to the clip facing (=> a straight-up aim stick) and the
    caller is told to supply the real yaw for a live-accurate stick. ``cut`` = "CUT_F" (fwd+B) or
    "CUT_A" (L+B). ``tetra_weight`` sizes the push split if one is needed.

    The roll facing (= the direction the 49.22 lunge fires) is ``world_angle_s16(new - old)``. Returns
    a dict: verdict flags (``clips`` / ``reachable_rollstab`` / ``needs_push``), the ``facing_clip``,
    modeled ``thrust`` + ``disp``, ``approach`` geometry, the ``push`` plan (None if the bare roll-stab
    clips), the emitted ``seq`` + ``seq_string`` + ``csangle`` + ``aim_stick``, and a human ``verdict``.
    """
    facing_clip = world_angle_s16(new[0] - old[0], new[1] - old[1])
    clip_disp = math.hypot(new[0] - old[0], new[1] - old[1])
    thrust, modeled = _modeled_thrust(facing_clip, cut)
    disp = math.hypot(*thrust)

    # Clip verdict against the bit-exact collision model: does old + thrust clip on its own?
    old3 = settle(tris, old, link_y)                     # (x,y,z) settled front-of-corner old_pos
    old_xz = (old3[0], old3[2])
    base = clip_with_push(old_xz, link_y, thrust, (old_xz[0] - 1e6, old_xz[1]), tris,
                          link_center=_roll_center(old_xz, facing_clip))
    push_plan = None
    if base["clipped"]:
        verdict = "Bare roll-stab CLIPS (lunge %.3fu; clip needs %.3fu). No push needed." % (
            disp, clip_disp)
    else:
        push_plan = _plan_push(tris, old3, link_y, thrust, new, facing_clip, tetra_weight)
        if push_plan is None:
            verdict = ("Roll-stab BLOCKED (lunge %.3fu; clip endpoint is %.3fu out) and no modeled "
                       "Tetra push closes it -- corner needs more than the roll-stab + a push can "
                       "supply here." % (disp, clip_disp))
        else:
            verdict = ("Roll-stab alone is BLOCKED (lunge %.3fu; clip endpoint %.3fu out); a Tetra "
                       "push of overlap %.3fu (Link gets %.3fu at the %.2f share) CLIPS it." % (
                           disp, clip_disp, push_plan["overlap"], push_plan["push_mag"],
                           push_plan["share"]))

    if csangle is None:
        csangle = facing_clip                              # camera-forward == clip facing -> stick is up
    aim_stick = stick_for_bearing(facing_clip, csangle=csangle, msd=1.0)
    seq = _emit_seq(aim_stick, cut, runup_frames)
    approach = _approach(start_pos, facing_clip, old)

    return dict(
        clips=True, reachable_rollstab=base["clipped"], needs_push=not base["clipped"],
        old=old, new=new, link_y=link_y, clip_disp=clip_disp, facing_clip=facing_clip,
        thrust=thrust, disp=disp, thrust_modeled=modeled, cut=cut, csangle=csangle,
        aim_stick=aim_stick, approach=approach, push=push_plan, seq=seq,
        seq_string=_seq_string(seq), verdict=verdict)


def _plan_push(tris, old3, link_y, thrust, new, facing_clip, tetra_weight):
    """Size + place the Tetra push that steers ``old + thrust`` onto the f32 clip point ``new``.
    Reuses the live-anchored pipeline (tetra_clip): push = NEW - OLD - thrust, overlap = |push|/share
    (share = Link's rank-table fraction), Tetra behind Link's animated roll-cyl centre along -push.
    Returns None if the placement does not reproduce the clip."""
    shares = push_shares(WEIGHT_LINK, tetra_weight)
    if shares is None:
        return None
    share = shares[0]                                      # Link's fraction of the overlap depth
    old_xz = (old3[0], old3[2])
    pneed = (new[0] - old_xz[0] - thrust[0], new[1] - old_xz[1] - thrust[1])
    pm = math.hypot(*pneed)
    if pm < 1e-6:
        return None
    overlap = pm / share
    lc = _roll_center(old_xz, facing_clip)
    ctr = lc if lc is not None else old_xz
    cd = (LINK_CO_R + TETRA_CO_R) - overlap               # Tetra centre distance for this overlap
    u = (pneed[0] / pm, pneed[1] / pm)
    tetra = (ctr[0] - cd * u[0], ctr[1] - cd * u[1])
    r = clip_with_push(old_xz, link_y, thrust, tetra, tris, tetra_w=tetra_weight, link_center=lc)
    if not r["clipped"]:
        return None
    return dict(push_vec=pneed, push_mag=math.hypot(*r["push"]), overlap=overlap, share=share,
                tetra_center=tetra, tetra_weight=tetra_weight, link_center=lc,
                clip_new=r["new"])


# ---------------------------------------------------------------- self-test (live-anchored Hyrule seam)

def _fh(s):
    return struct.unpack(">f", struct.pack(">I", int(s, 16)))[0]


def _load_hyrule_anchor():
    """The live (-1727,-990) Hyrule corner from the golden RAM capture (a real needs-push clip). Returns
    the barrier tris and the AUTHORITATIVE clip target (settled ``old`` + f32 ``new``) + floor Y."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "tests", "golden", "hyrule_seam_1727_ram.json")
    g = json.load(open(p))
    tris = [Tri([_fh(x) for x in t["v"][0]], [_fh(x) for x in t["v"][1]], [_fh(x) for x in t["v"][2]],
                plane=Plane(*[_fh(x) for x in t["n"]], _fh(t["D"]))) for t in g["tris"]]
    link_y = _fh(g["seam_v_hex"][1])
    old = (_fh(g["old_hex"][0]), _fh(g["old_hex"][1]))
    new = (_fh(g["new_hex"][0]), _fh(g["new_hex"][1]))
    return tris, link_y, old, new


def _selftest():
    tris, link_y, old, new = _load_hyrule_anchor()
    facing_clip = world_angle_s16(new[0] - old[0], new[1] - old[1])
    # start ~200u back along the (reverse) clip facing so the run-up drives the roll into the corner.
    r = facing_clip / 65536.0 * 2 * math.pi
    start = (old[0] - 200.0 * math.sin(r), old[1] - 200.0 * math.cos(r))
    print("Hyrule (-1727,-990) self-test: start=(%.1f,%.1f) old=(%.1f,%.1f) new=(%.1f,%.1f)" % (
        start + old + new), flush=True)
    plan = plan_seam_clip(tris, old, new, start, link_y, cut="CUT_F")
    print("  clips=%s reachable_rollstab=%s needs_push=%s" % (
        plan["clips"], plan["reachable_rollstab"], plan["needs_push"]), flush=True)
    print("  facing_clip=%d (%.2f deg)  lunge=%.4f  clip_disp=%.4f  thrust_modeled=%s" % (
        plan["facing_clip"], plan["facing_clip"] / 65536 * 360, plan["disp"], plan["clip_disp"],
        plan["thrust_modeled"]), flush=True)
    print("  " + plan["verdict"], flush=True)
    if plan["push"]:
        pp = plan["push"]
        print("  push: overlap=%.3fu Link_push=%.3fu  Tetra centre=(%.2f,%.2f) weight=0x%X" % (
            pp["overlap"], pp["push_mag"], pp["tetra_center"][0], pp["tetra_center"][1],
            pp["tetra_weight"]), flush=True)
    print("  approach: runway=%.1fu lateral_offset=%.2fu on_ray=%s aim_stick=%s csangle=%d" % (
        plan["approach"]["runway"], plan["approach"]["lateral_offset"], plan["approach"]["on_ray"],
        plan["aim_stick"], plan["csangle"]), flush=True)
    print("  SEQ: " + plan["seq_string"], flush=True)
    assert plan["clips"], "SELF-TEST FAILED: no clip found at the live-anchored Hyrule corner"
    assert plan["needs_push"] and plan["push"] is not None, \
        "SELF-TEST FAILED: Hyrule -1727 is a known needs-push clip; push plan should close it"
    assert plan["seq"], "SELF-TEST FAILED: no input sequence emitted"
    print("  SELF-TEST PASSED", flush=True)


def main(argv):
    if "--selftest" in argv or not argv:
        _selftest()
        return 0
    print("usage: python -m harness.collision.plan_seam_clip --selftest")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
