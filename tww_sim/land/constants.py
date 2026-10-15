#!/usr/bin/env python3
"""land/constants.py - leaf constants + helpers for the land procs.

Proc-state enums, direction buckets, the C-up-freeze gates, and the small angle/zero helpers
the procs share. No LandState dependency, so the proc mixins (procs/*) and state.py both import
from here with no import cycle. See land.py (shim) for the public re-export surface.
"""
from __future__ import annotations
from ..core import mathlib as S
from ..core.mathlib import s16_signed

# link_state / daPyProc values (d_a_player_main.h). Walk trio + the targeting-move proc.
SUBJECTIVITY = 1  # daPyProc_SUBJECTIVITY_e (first-person view; the C-up-cancel FREEZE: mNormalSpeed=0)
WAIT = 4          # daPyProc_WAIT_e         (idle standstill)
FREE_WAIT = 5     # daPyProc_FREE_WAIT_e    (anchor's resting proc)
MOVE = 6          # daPyProc_MOVE_e         (ground locomotion)
ATN_MOVE = 7      # daPyProc_ATN_MOVE_e     (targeting move: brakeslide / L-held slide, no locked actor)
ATN_ACTOR_WAIT = 8  # daPyProc_ATN_ACTOR_WAIT_e (actor-lock idle: setSpeedAndAngleAtnActor at rest)
ATN_ACTOR_MOVE = 9  # daPyProc_ATN_ACTOR_MOVE_e (actor-lock move: the untarget brakeslide, faces the actor)
WAIT_TURN = 23    # daPyProc_WAIT_TURN_e    (pivot-in-place reversal from a standstill)
MOVE_TURN = 24    # daPyProc_MOVE_TURN_e    (turn-around reversal, low speed / post-slip)
SLIP = 25         # daPyProc_SLIP_e         (high-speed reversal skid, hands to MOVE_TURN)
FRONT_ROLL = 30   # daPyProc_FRONT_ROLL_e   (A-button forward roll)
FRONT_ROLL_CRASH = 31  # daPyProc_FRONT_ROLL_CRASH_e (roll bonk: reversed momentum + airborne bounce)
CUT_A = 0x41      # daPyProc_CUT_A_e        (L+B neutral: vertical/overhead slash)
CUT_F = 0x42      # daPyProc_CUT_F_e        (fwd+B: forward thrust; the roll-stab's 49.22 lunge)
# Targeted ballistic hops (L-held + A + directional stick -> doStatus JUMP). Pure momentum + gravity,
# no foot-plant (m3598==0), so position is scalar-exact without the anim engine. See land-movement.md.
SIDE_STEP = 0x0A       # daPyProc_SIDE_STEP_e       (sidehop: stick L/R while targeting)
SIDE_STEP_LAND = 0x0B  # daPyProc_SIDE_STEP_LAND_e  (sidehop recovery -> WAIT)
BACK_JUMP = 0x22       # daPyProc_BACK_JUMP_e       (backflip: stick back while targeting)
BACK_JUMP_LAND = 0x23  # daPyProc_BACK_JUMP_LAND_e  (backflip recovery -> WAIT)

#: Procs an A-press dispatches the ATTACK ROLL from (checkNextActionFromButton 4309 -> 4188): grounded
#: AND locomoting AND past `ATTACK_MSD_MIN`. See knowledge/strategy/search-prune-the-dispatch.md.
ROLL_FROM = (MOVE, ATN_MOVE)

_STATE_TAG = {MOVE: "MOVE", ATN_MOVE: "ATN", ATN_ACTOR_MOVE: "ATNACT", ATN_ACTOR_WAIT: "ATNACTW",
              FRONT_ROLL: "ROLL", FRONT_ROLL_CRASH: "CRASH",
              WAIT_TURN: "WAITTURN",
              MOVE_TURN: "MOVETURN", SLIP: "SLIP", WAIT: "WAIT", FREE_WAIT: "WAIT",
              SUBJECTIVITY: "SUBJ",
              SIDE_STEP: "SIDEHOP", SIDE_STEP_LAND: "SIDEHOPLAND",
              BACK_JUMP: "BACKFLIP", BACK_JUMP_LAND: "BACKFLIPLAND",
              CUT_F: "CUT_F", CUT_A: "CUT_A"}

# mDirection enum (d_a_player_main.h daPy_lk_c::direction_e). getDirectionFromAngle buckets the
# stick-vs-heading angle into these; ATN physics branches on it (fwd->Normal, back->AtnBack, side).
DIR_FORWARD = 0
DIR_BACKWARD = 1
DIR_LEFT = 2
DIR_RIGHT = 3
DIR_NONE = 4

# Frames of controller-input latency: physics at frame f acts on the stick from frame f-2.
INPUT_DELAY = 2

# C-up-cancel (subjectivity freeze) gates + the three checkSubjectEnd exits. Full model + decomp
# cites: knowledge/mechanics/land-movement.md (subjectivity freeze). C-up entry: camera path, +1 frame.
CUP_POSY = 0.5          # C-stick posY (up) the camera reads as a subjective-view request (d_camera.cpp:1096)
CUP_MAIN_MAX = 0.5      # main-stick magnitude below which the C-up request is accepted (mStickMainValueLast)
CDOWN_POSY = -0.74      # C-stick posY (down) hard threshold that arms the 0x2000 subject-exit (d_camera.cpp:4230)
SUBJ_CAM_FLOOR = 9      # body frames after lock before the CAMERA (C-DOWN) exit can fire (SUBJ_VIEW_IN)
CDOWN_RUN = 3           # acted C-down frames the m3C4 0->1->2 + report needs (== poll+4 with INPUT_DELAY)

# speedF->pos FALLBACK: calibrated cLib chase toward mNormalSpeed, used only when the anim engine
# (tww_sim.core.anim.foot_speedf) lacks keyframe data (endpoint +-3). With data, speedF is bit-exact.
SPEEDF_CHASE = (0.5, 2.0, 1.4)   # (scale, maxStep, minStep) fit vs land_walk_gt.csv

# Standing-idle FREEB frame-controller value at the land_flatwalk anchor (mFrameCtrlUnder[0]). It
# sets the entry idle-drift phase for the anim engine; seed it from live for other anchors.
DEFAULT_IDLE_FRAME = 70.0


def cLib_addCalcAngleS(value, target, scale, max_step, min_step):
    """Faithful cLib_addCalcAngleS (c_lib.cpp:160), s16 integer math. Chase an s16 `value`
    toward `target` by diff/scale, clamped to +-max_step, else snap by +-min_step without
    overshoot. Returns the new value (the decomp mutates in place + returns the residual).
    All arithmetic is s16-wrapping like the game (diff = target - value as s16)."""
    value &= 0xFFFF
    target &= 0xFFFF
    if value == target:
        return value
    diff = s16_signed(target - value)
    step = int(diff / scale)                 # C integer division (truncate toward zero)
    if step > min_step or step < -min_step:
        if step > max_step:
            step = max_step
        if step < -max_step:
            step = -max_step
        return (value + step) & 0xFFFF
    if diff >= 0:
        nv = (value + min_step) & 0xFFFF
        return target if s16_signed(target - nv) <= 0 else nv
    else:
        nv = (value - min_step) & 0xFFFF
        return target if s16_signed(target - nv) >= 0 else nv


def _is_zero(x):
    # cM3d_IsZero: |x| < 0.00001 (c_m3d.cpp). Only the exact-0 dVar9 (release) matters here.
    return abs(x) < 1.0e-5


def _dist_angle_s(a, b):
    # cLib_distanceAngleS: |signed s16 difference| (magnitude of the shortest turn).
    return abs(s16_signed(int(a) - int(b)))


def _cM_ssin_s16(angle):
    # cM_ssin(a) == JMASSin(a): the console SIN table directly, NOT a cos offset (cos[0xC000] != sin[0]).
    # See knowledge/model/fp-faithfulness.md (sin table) + history/resolved-bugs.md (pos_x sine leak).
    return S.cM_ssin_s16(angle)
