"""Decomp-derived carried bomb/pot release primitives.

This module covers the part the old CSV drop scanner skipped:

    Link hand pose -> B release -> prop background correction -> active Co center

An ordinary sword-equipped B press while the action status is DROP does not
enter GRABTHROW. ``checkNextActionGrab`` calls ``freeGrabItem`` directly, so the
prop retains zero horizontal speed.  Throw constants are exposed separately
because A/THROW and B/THROW use a different path.

This module still needs the exact release-transition Link pose before it can
generate all 60 measured vectors from animation data alone.  It deliberately
does not call a free-space measured endpoint a wall proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import sys

from . import fp
from . import mathlib as M
from .anim import fk, j3d_eval, quat as Q
from .cc_push import WEIGHT_LINK, co_push_link, push_shares
from .collision import acch_crr_pos
from .prop_specs import PROP_SPECS, PropSpec


CL_JNT_LEFT_HAND = 0x08
CL_JNT_RIGHT_HAND = 0x0C
CL_JNT_LINK_ROOT = 0x00
CL_JNT_NECK = 0x0E
CL_JNT_LEFT_TOE = 0x23
CL_JNT_RIGHT_TOE = 0x28

# daPy_HIO_grab_c0::m, d_a_player_HIO_data.inc:
# procGrabThrow frees the actor when frameCtrl.checkPass(field_0x8C).
GRAB_THROW_SPEED_F = 19.0
GRAB_THROW_SPEED_Y = 34.0
GRAB_THROW_RELEASE_FRAME = 2.0
GRAB_THROW_START_FRAME = 1.0
GRAB_THROW_RATE = 0.8
# daPy_HIO_cut_c0::m.field_0x0. setAnimeEquipSword passes this explicit
# endpoint to setActAnimeUpper, so REST starts at 14 - 0.001, not BCK frameMax.
EQUIP_REST_END_FRAME = 14.0

# B/DROP releases directly from GRAB_WAIT.  These compatibility names describe
# relative executes, not GRABTHROW animation frames: the prop was last posed on
# execute 0, B releases it on execute 1, and Link consumes the Co push on 2.
NORMAL_B_DROP_HELD_FRAME = 0.0
NORMAL_B_DROP_RELEASE_CHECK_FRAME = 1.0
NORMAL_B_DROP_RELEASE_NEXT_FRAME = 2.0

BOMB_GRAVITY = -2.9
BOMB_RADIUS = 30.0
BOMB_CO_Y_OFFSET = 30.0


@dataclass(frozen=True)
class DropObject:
    name: str
    prop_spec: PropSpec
    gravity: float
    throw_speed_f: float
    throw_speed_y: float
    co_y_offset: float
    source: str


# daTsubo::mode_drop_init overwrites Link's throw speed with data().m18 and
# data().m14.  For zero player speed: small pot type0 = F36/Y27, large type1 =
# F43/Y22.  Bombs keep Link's throw constants.
DROP_OBJECTS = {
    "bomb": DropObject(
        "bomb", PROP_SPECS["bomb"], BOMB_GRAVITY, GRAB_THROW_SPEED_F,
        GRAB_THROW_SPEED_Y, BOMB_CO_Y_OFFSET,
        "d_a_player_grab.inc freeGrabItem + d_a_bomb3.inc procCarry/procWait",
    ),
    "pot_small": DropObject(
        "pot_small", PROP_SPECS["pot_small"], -6.0, 36.0, 27.0, 0.0,
        "d_a_tsubo.cpp M_data type0 + mode_carry/mode_wait",
    ),
    "pot_large": DropObject(
        "pot_large", PROP_SPECS["pot_large"], -6.5, 43.0, 22.0, 0.0,
        "d_a_tsubo.cpp M_data type1 + mode_carry/mode_wait",
    ),
}


@dataclass(frozen=True)
class CarryPose:
    """Link state needed by ``setGrabItemPos`` for ordinary bomb/pot carries."""

    pos: tuple[float, float, float]
    facing: int
    frame: float = GRAB_THROW_RELEASE_FRAME
    anim: str = "grabwait"
    field_0x2b0: float = 0.0
    m35cc: float = 0.0
    hand_mid: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class DropTimeline:
    """Relative execute timing for an ordinary B/DROP release."""

    held_frame: float = NORMAL_B_DROP_HELD_FRAME
    release_check_frame: float = NORMAL_B_DROP_RELEASE_CHECK_FRAME
    next_frame: float = NORMAL_B_DROP_RELEASE_NEXT_FRAME
    source: str = "GRAB_WAIT checkNextActionGrab -> freeGrabItem (no GRABTHROW)"


NORMAL_B_DROP_TIMELINE = DropTimeline()


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rb = here
    while rb != os.path.dirname(rb) and not os.path.exists(os.path.join(rb, "pyproject.toml")):
        rb = os.path.dirname(rb)
    return rb


def load_grab_anims(path: str | None = None):
    if path is None:
        path = os.path.join(_repo_root(), "_generated", "anim", "link_anim_grab.json")
    return j3d_eval.load_anim(path)


_SKELETON_CACHE = None
_SKELETON_INDEX_CACHE = {}
_LOCAL_JOINT_CACHE = {}


def load_skeleton(path: str | None = None):
    global _SKELETON_CACHE
    if path is None:
        path = os.path.join(_repo_root(), "_generated", "anim", "link_skeleton.json")
    if _SKELETON_CACHE is None:
        with open(path) as f:
            _SKELETON_CACHE = json.load(f)
    return _SKELETON_CACHE


def _skeleton_joints(skeleton):
    key = id(skeleton)
    joints = _SKELETON_INDEX_CACHE.get(key)
    if joints is None:
        joints = {j["index"]: j for j in skeleton["joints"]}
        _SKELETON_INDEX_CACHE[key] = joints
    return joints


def _cached_local_joint(anm, joint_idx, frame):
    key = (id(anm), int(joint_idx), float(frame))
    hit = _LOCAL_JOINT_CACHE.get(key)
    if hit is not None:
        return hit
    tr = j3d_eval.calc_transform(anm, joint_idx, frame)
    local = Q.psmtx_quat(Q.euler_to_quat(*tr["rotation"]))
    local[0][3] = fp.f32(tr["translate"][0])
    local[1][3] = fp.f32(tr["translate"][1])
    local[2][3] = fp.f32(tr["translate"][2])
    scale = tuple(fp.f32(value) for value in tr["scale"])
    if any(abs(value - 1.0) >= 1e-5 for value in scale):
        for row in range(3):
            for col in range(3):
                local[row][col] = fp.fmuls(local[row][col], scale[col])
    frozen = (tuple(tuple(row) for row in local), scale)
    _LOCAL_JOINT_CACHE[key] = frozen
    return frozen


def _joint_world_matrix(anm, skeleton, frame, pos, facing, joint_idx, *,
                        neutralize_grab_root=False):
    joints = _skeleton_joints(skeleton)
    parent = {idx: j["parent"] for idx, j in joints.items()}
    chain = []
    j = joint_idx
    while j != -1:
        chain.append(j)
        j = parent[j]
    chain.reverse()
    base, _ = fk.world_base(pos[0], pos[1], pos[2], facing)
    cur = [row[:] for row in base]
    parent_scale = (fp.f32(1.0), fp.f32(1.0), fp.f32(1.0))
    grab_root_inverse = None
    grab_root_world = None
    for j in chain:
        # jointBeforeCB's checkGrabAnime branch saves the root matrix, then at
        # joint 1 post-concats the inverse of joint 0's animated quaternion.
        # This leaves the root translation intact but removes its rotation from
        # the upper-body chain. The waist branch restores the saved root matrix
        # at joint 29. Bomb/pot hand positions are calculated in this state;
        # after freeGrabItem(), checkGrabAnime is false for Link's release Co.
        if neutralize_grab_root and j == 1 and grab_root_inverse is not None:
            cur = fk.mtx_concat(cur, grab_root_inverse)
        elif neutralize_grab_root and j == 0x1D and grab_root_world is not None:
            cur = [row[:] for row in grab_root_world]
        frozen, scale = _cached_local_joint(anm, j, frame)
        local = [list(row) for row in frozen]
        if joints[j].get("scale_compensate") == 1:
            inv_parent = tuple(fp.fdivs(1.0, value) for value in parent_scale)
            for row in range(3):
                for col in range(3):
                    local[row][col] = fp.fmuls(local[row][col], inv_parent[row])
        cur = fk.mtx_concat(cur, local)
        if neutralize_grab_root and j == CL_JNT_LINK_ROOT:
            grab_root_world = [row[:] for row in cur]
            root_rotation = [row[:] for row in local]
            root_rotation[0][3] = fp.f32(0.0)
            root_rotation[1][3] = fp.f32(0.0)
            root_rotation[2][3] = fp.f32(0.0)
            grab_root_inverse = fk.psmtx_inverse(root_rotation)
        parent_scale = scale
    return cur


def hand_positions(pose: CarryPose, anims=None, skeleton=None):
    """Return ``(left, right)`` from Link's grab animation at ``pose.frame``.

    These are the same joints ``daPy_lk_c::setWorldMatrix`` stores into
    ``mLeftHandPos`` and ``mRightHandPos`` before ``setGrabItemPos`` runs.
    """
    if pose.hand_mid is not None:
        return pose.hand_mid, pose.hand_mid
    if anims is None or skeleton is None:
        skeleton = load_skeleton() if skeleton is None else skeleton
        anims = load_grab_anims() if anims is None else anims
    anm = anims[pose.anim]
    left_m = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_LEFT_HAND,
        neutralize_grab_root=True,
    )
    right_m = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_RIGHT_HAND,
        neutralize_grab_root=True,
    )
    return (
        (left_m[0][3], left_m[1][3], left_m[2][3]),
        (right_m[0][3], right_m[1][3], right_m[2][3]),
    )


def link_body_co(pose: CarryPose, anims=None, skeleton=None, carrying=False):
    """Link's body Co cylinder for the grab/drop animation pose.

    Port of the non-roll branch of ``daPy_lk_c::setCollision``:

    * X/Z center = midpoint of root joint and neck joint world translations.
    * Y base = lower of left/right toe joint world Y.
    * height = ``40.1 + (neck_y - base_y)``.
    * radius = 50 while ``checkGrabWear()``, otherwise 30.

    On the frame after ``freeGrabItem`` this should usually be ``carrying=False``;
    the option exists for frame-order validation.
    """
    if anims is None or skeleton is None:
        skeleton = load_skeleton() if skeleton is None else skeleton
        anims = load_grab_anims() if anims is None else anims
    anm = anims[pose.anim]
    root = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_LINK_ROOT,
        neutralize_grab_root=carrying,
    )
    neck = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_NECK,
        neutralize_grab_root=carrying,
    )
    ltoe = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_LEFT_TOE,
        neutralize_grab_root=carrying,
    )
    rtoe = _joint_world_matrix(
        anm, skeleton, pose.frame, pose.pos, pose.facing, CL_JNT_RIGHT_TOE,
        neutralize_grab_root=carrying,
    )
    base_y = rtoe[1][3] if ltoe[1][3] > rtoe[1][3] else ltoe[1][3]
    center = (
        fp.fmuls(0.5, fp.fadds(root[0][3], neck[0][3])),
        base_y,
        fp.fmuls(0.5, fp.fadds(root[2][3], neck[2][3])),
    )
    height = fp.fadds(40.1, fp.fsubs(neck[1][3], base_y))
    return {
        "center": center,
        "radius": 50.0 if carrying else 30.0,
        "height": height,
    }


def carried_actor_pos(pose: CarryPose, anims=None, skeleton=None):
    """Ordinary bomb/pot path of ``daPy_lk_c::setGrabItemPos``.

    Barrels/magtails/grab-up interpolation are intentionally excluded.  For a
    held bomb/small pot/large pot during ``GRAB_WAIT`` this is the hand midpoint
    plus ``field_0x2b0`` and ``m35CC`` Y offsets.
    """
    left, right = hand_positions(pose, anims=anims, skeleton=skeleton)
    return (
        fp.fmuls(0.5, fp.fadds(left[0], right[0])),
        fp.fadds(fp.fadds(fp.fmuls(0.5, fp.fadds(left[1], right[1])), pose.field_0x2b0), pose.m35cc),
        fp.fmuls(0.5, fp.fadds(left[2], right[2])),
    )


def _first_velocity(speed_f, speed_y, gravity, facing):
    sx = fp.fmuls(speed_f, M.cM_ssin_s16(facing))
    sy = fp.fadds(speed_y, gravity)
    sz = fp.fmuls(speed_f, M.cM_scos_s16(facing))
    return sx, sy, sz


def first_free_actor_pos(pose: CarryPose, obj: DropObject, release="b_drop"):
    """Actor ``current.pos`` after its first execute following release.

    ``b_drop`` is the normal sword-equipped B/DROP path. ``freeGrabItem`` does
    not assign throw speed. A bomb enters ``procWait`` with speedF=0; a pot sees
    speedF=0 and enters ``mode_wait`` instead of ``mode_drop``. Consequently
    both preserve the held X/Z position. ``throw`` models the separate
    GRABTHROW path and uses the object's throw constants.
    """
    p = carried_actor_pos(pose)
    if release == "b_drop":
        vx, vy, vz = _first_velocity(0.0, 0.0, obj.gravity, pose.facing)
    elif release == "throw":
        vx, vy, vz = _first_velocity(obj.throw_speed_f, obj.throw_speed_y, obj.gravity, pose.facing)
    else:
        raise ValueError("release must be 'b_drop' or 'throw'")
    return (fp.fadds(p[0], vx), fp.fadds(p[1], vy), fp.fadds(p[2], vz))


def first_active_co_center(pose: CarryPose, object_type: str, release="b_drop"):
    """First active Co center for ``object_type`` on the release/update frame."""
    obj = DROP_OBJECTS[object_type]
    p = first_free_actor_pos(pose, obj, release=release)
    return (p[0], fp.fadds(p[1], obj.co_y_offset), p[2])


def first_active_co_center_from_timeline(pos, facing, object_type: str,
                                         timeline: DropTimeline = NORMAL_B_DROP_TIMELINE,
                                         anim: str = "grabwait", hand_mid=None,
                                         anims=None, skeleton=None):
    """First active Co center using the ordinary B-drop timeline.

    ``held_frame`` is the last frame where ``setGrabItemPos`` writes the carried
    actor. Timeline values are relative executes, not GRABWAIT animation
    positions.
    """
    pose = CarryPose(tuple(pos), facing, timeline.held_frame, anim=anim, hand_mid=hand_mid)
    if hand_mid is None and (anims is not None or skeleton is not None):
        carried = carried_actor_pos(pose, anims=anims, skeleton=skeleton)
        pose = CarryPose(tuple(pos), facing, timeline.held_frame, anim=anim, hand_mid=carried)
    return first_active_co_center(pose, object_type)


def release_push_for_link(pose: CarryPose, object_type: str, link_center_xz=None,
                          link_y=None, link_r=None, link_h=None, anims=None, skeleton=None):
    """Link's pending Co push from the modeled first active object center.

    ``link_center_xz`` must be Link's body-Co center for the collision frame.
    If omitted, this uses Link feet XZ as a conservative convenience, but seam
    proofs should feed the animation-derived body Co center.
    """
    obj = DROP_OBJECTS[object_type]
    co = first_active_co_center(pose, object_type)
    if link_center_xz is None or link_y is None or link_r is None or link_h is None:
        body = link_body_co(pose, anims=anims, skeleton=skeleton)
        ctr = (body["center"][0], body["center"][2]) if link_center_xz is None else link_center_xz
        ly = body["center"][1] if link_y is None else link_y
        lr = body["radius"] if link_r is None else link_r
        lh = body["height"] if link_h is None else link_h
    else:
        ctr = link_center_xz
        ly = link_y
        lr = link_r
        lh = link_h
    link_c = (fp.f32(ctr[0]), fp.f32(ly), fp.f32(ctr[1]))
    return co_push_link(link_c, lr, lh, co, obj.prop_spec.radius, obj.prop_spec.height,
                        link_w=WEIGHT_LINK, other_w=obj.prop_spec.weight)


def displacement_from_hands(hand_mid, facing, object_type, release="b_drop"):
    """World displacement from hand midpoint to the first active Co center.

    Useful for replacing the measured CSV table with decomp constants once a hand
    pose table exists.  ``hand_mid`` is the exact result of ``setGrabItemPos`` for
    the frame being tested.
    """
    obj = DROP_OBJECTS[object_type]
    if release == "b_drop":
        vx, vy, vz = _first_velocity(0.0, 0.0, obj.gravity, facing)
    elif release == "throw":
        vx, vy, vz = _first_velocity(obj.throw_speed_f, obj.throw_speed_y, obj.gravity, facing)
    else:
        raise ValueError("release must be 'b_drop' or 'throw'")
    return (vx, fp.fadds(vy, obj.co_y_offset), vz)


@dataclass(frozen=True)
class BDropCollisionResult:
    """One release-to-Link-consumption step, including both BG passes."""

    object_type: str
    prop_old: tuple[float, float, float]
    prop_after_bg: tuple[float, float, float]
    prop_bg_info: dict
    prop_co_center: tuple[float, float, float]
    link_push: tuple[float, float, float]
    link_raw: tuple[float, float, float]
    link_after_bg: tuple[float, float, float]
    link_bg_info: dict


@dataclass(frozen=True)
class CalibratedBDropPose:
    """World-space B-drop centers reconstructed from one measured free-space row."""

    table_frame: int
    held_prop_pos: tuple[float, float, float]
    link_co_center: tuple[float, float, float]
    link_co_radius: float
    link_co_height: float
    local_center_separation: tuple[float, float]
    world_center_separation: tuple[float, float]


@dataclass(frozen=True)
class DecompBDropPose:
    """First-principles centers for a B release at one displayed anim position."""

    animation_position: int
    held_frame: float
    collision_under_frame: float
    equip_frame: float
    held_prop_pos: tuple[float, float, float]
    link_co_center: tuple[float, float, float]
    link_co_radius: float
    link_co_height: float


def _mixed_release_joint_matrix(anims, skeleton, under_frame, equip_frame,
                                pos, facing, joint_idx):
    """World joint matrix for the GRABWAIT + REST B-release draw.

    GRAB_WAIT's mode flags suppress jointCB0's equip-ratio toggles. Joint 0 and
    joint 1 are still on PART_UNDER (GRABWAIT); the body branch beginning at
    joint 2 is PART_UPPER and therefore takes REST at ratio 1.
    """
    joints = _skeleton_joints(skeleton)
    chain = []
    j = joint_idx
    while j != -1:
        chain.append(j)
        j = joints[j]["parent"]
    chain.reverse()
    base, _ = fk.world_base(pos[0], pos[1], pos[2], facing)
    cur = [row[:] for row in base]
    parent_scale = (fp.f32(1.0), fp.f32(1.0), fp.f32(1.0))
    for j in chain:
        if j <= 1 or j >= 0x1D:
            anm = anims["grabwait"]
            frame = under_frame
        else:
            anm = anims["rest"]
            frame = equip_frame
        frozen, scale = _cached_local_joint(anm, j, frame)
        local = [list(row) for row in frozen]
        if joints[j].get("scale_compensate") == 1:
            inv_parent = tuple(fp.fdivs(1.0, value) for value in parent_scale)
            for row in range(3):
                for col in range(3):
                    local[row][col] = fp.fmuls(local[row][col], inv_parent[row])
        cur = fk.mtx_concat(cur, local)
        parent_scale = scale
    return cur


_JOINT_TRANSLATION_PLAN_CACHE = {}


def _joint_translation_plan(anims, skeleton, under_frame, equip_frame,
                            facing, joint_idx, mixed):
    """Cache the world-FK translation increments for one joint chain.

    Joint rotations do not depend on Link's world position. PSMTXConcat adds
    the base translation once per joint, however, so collapsing the final
    offset to ``pos + local`` loses world-magnitude rounding. Replaying these
    increments preserves that ordering while avoiding repeated matrix work.
    """
    facing_bucket = int(facing) & 0xFFF0
    key = (
        id(anims), id(skeleton), float(under_frame), float(equip_frame),
        facing_bucket, int(joint_idx), bool(mixed),
    )
    cached = _JOINT_TRANSLATION_PLAN_CACHE.get(key)
    if cached is not None:
        return cached
    joints = _skeleton_joints(skeleton)
    chain = []
    j = joint_idx
    while j != -1:
        chain.append(j)
        j = joints[j]["parent"]
    chain.reverse()
    base, _ = fk.world_base(0.0, 0.0, 0.0, facing_bucket)
    cur = [row[:] for row in base]
    parent_scale = (fp.f32(1.0), fp.f32(1.0), fp.f32(1.0))
    increments = []
    for j in chain:
        if mixed and not (j <= 1 or j >= 0x1D):
            anm = anims["rest"]
            frame = equip_frame
        else:
            anm = anims["grabwait"]
            frame = under_frame
        frozen, scale = _cached_local_joint(anm, j, frame)
        local = [list(row) for row in frozen]
        if joints[j].get("scale_compensate") == 1:
            inv_parent = tuple(fp.fdivs(1.0, value) for value in parent_scale)
            for row in range(3):
                for col in range(3):
                    local[row][col] = fp.fmuls(local[row][col], inv_parent[row])
        increments.append(tuple(
            fp.fmadds(
                cur[row][2], local[2][3],
                fp.fmadds(cur[row][1], local[1][3], fp.fmuls(cur[row][0], local[0][3])),
            )
            for row in range(3)
        ))
        cur = fk.mtx_concat(cur, local)
        parent_scale = scale
    result = tuple(increments)
    _JOINT_TRANSLATION_PLAN_CACHE[key] = result
    return result


def _apply_joint_translation_plan(pos, plan):
    translation = [fp.f32(pos[0]), fp.f32(pos[1]), fp.f32(pos[2])]
    for increment in plan:
        for row in range(3):
            translation[row] = fp.fadds(increment[row], translation[row])
    return tuple(translation)


def _planned_joint_translation(anims, skeleton, under_frame, equip_frame,
                               pos, facing, joint_idx, mixed):
    plan = _joint_translation_plan(
        anims, skeleton, under_frame, equip_frame, facing, joint_idx, mixed
    )
    return _apply_joint_translation_plan(pos, plan)


def _layered_local_joint(lower_anims, lower, upper_anims, upper_anim,
                         upper_frame, joint_idx, equip_transition=False):
    """Return one local joint matrix from Link's under/upper layer split.

    Joints 0, 1 and the waist/lower branch (>=0x1D) use PART_UNDER;
    the body branch uses PART_UPPER.  ``lower`` is the rendered two-animation
    blend dictionary emitted by ``UnderAnimState``/``FootSpeedF``.
    """
    # checkEquipAnime's joint callback disables UPPER_MOVE2 at joint 1 and
    # restores it at joint 4. J3D invokes that node callback after calculating
    # the node itself, so the REST layer begins at joint 4's children.
    lower_joint = joint_idx <= (4 if equip_transition else 1) or joint_idx >= 0x1D
    if lower_joint:
        move0 = lower["move0"]
        move1 = lower.get("move1") or move0
        frame0 = lower["f0"]
        frame1 = lower.get("f1", frame0)
        ratio = fp.f32(lower.get("ratio", 0.0))
        if move0 == move1 and float(frame0) == float(frame1):
            frozen, scale = _cached_local_joint(
                lower_anims[move0], joint_idx, frame0
            )
            return [list(row) for row in frozen], scale
        info0 = j3d_eval.calc_transform(lower_anims[move0], joint_idx, frame0)
        info1 = j3d_eval.calc_transform(lower_anims[move1], joint_idx, frame1)
        local = fk.local_mtx_quat_blend(info0, info1, ratio)
        scale = tuple(
            fp.fmadds(
                info1["scale"][axis], ratio,
                fp.fmuls(info0["scale"][axis], fp.fsubs(1.0, ratio)),
            )
            for axis in range(3)
        )
        for row in range(3):
            for col in range(3):
                local[row][col] = fp.fmuls(local[row][col], scale[col])
        return local, scale
    frozen, scale = _cached_local_joint(
        upper_anims[upper_anim], joint_idx, upper_frame
    )
    return [list(row) for row in frozen], scale


def _layered_joint_translation(lower_anims, lower, upper_anims, upper_anim,
                               upper_frame, skeleton, pos, facing, joint_idx,
                               lean=0, *, body_lean=0,
                               neutralize_grab_root=False,
                               equip_transition=False, root_matrix=None):
    joints = _skeleton_joints(skeleton)
    chain = []
    j = joint_idx
    while j != -1:
        chain.append(j)
        j = joints[j]["parent"]
    chain.reverse()
    base, _ = fk.world_base(pos[0], pos[1], pos[2], facing, lean=lean)
    cur = [row[:] for row in base]
    parent_scale = (fp.f32(1.0), fp.f32(1.0), fp.f32(1.0))
    grab_root_inverse = None
    if root_matrix is not None:
        cur = [[fp.f32(value) for value in row] for row in root_matrix]
        local, parent_scale = _layered_local_joint(
            lower_anims, lower, upper_anims, upper_anim, upper_frame, CL_JNT_LINK_ROOT,
            equip_transition=equip_transition,
        )
        if neutralize_grab_root:
            root_rotation = [row[:] for row in local]
            for row in root_rotation:
                row[3] = fp.f32(0.0)
            grab_root_inverse = fk.psmtx_inverse(root_rotation)
        chain = chain[1:]
    for j in chain:
        if neutralize_grab_root and j == 1 and grab_root_inverse is not None:
            cur = fk.mtx_concat(cur, grab_root_inverse)
        local, scale = _layered_local_joint(
            lower_anims, lower, upper_anims, upper_anim, upper_frame, j,
            equip_transition=equip_transition,
        )
        if j == 2 and body_lean:
            signed_lean = int(body_lean) & 0xFFFF
            if signed_lean >= 0x8000:
                signed_lean -= 0x10000
            twist = Q.psmtx_quat(Q.euler_to_quat(-signed_lean, 0, 0))
            twist[0][3] = twist[1][3] = twist[2][3] = fp.f32(0.0)
            local = fk.mtx_concat(local, twist)
        if joints[j].get("scale_compensate") == 1:
            inv_parent = tuple(fp.fdivs(1.0, value) for value in parent_scale)
            for row in range(3):
                for col in range(3):
                    local[row][col] = fp.fmuls(local[row][col], inv_parent[row])
        cur = fk.mtx_concat(cur, local)
        if neutralize_grab_root and j == CL_JNT_LINK_ROOT:
            root_rotation = [row[:] for row in local]
            root_rotation[0][3] = fp.f32(0.0)
            root_rotation[1][3] = fp.f32(0.0)
            root_rotation[2][3] = fp.f32(0.0)
            grab_root_inverse = fk.psmtx_inverse(root_rotation)
        parent_scale = scale
    return cur[0][3], cur[1][3], cur[2][3]


def decomp_moving_b_drop_pose(held_link_pos, collision_link_pos, facing,
                              held_lower, collision_lower, grab_frame,
                              object_type="pot_small", *, lower_anims=None,
                              upper_anims=None, skeleton=None, held_lean=0,
                              collision_lean=0, collision_facing=None,
                              held_body_lean=0, collision_body_lean=0,
                              held_root_matrix=None, collision_root_matrix=None):
    """Build a moving B-drop pose from Link's actual layered animation state.

    Unlike :func:`decomp_b_drop_pose`, PART_UNDER is the live DASH/WALK blend.
    The last carried prop draw uses GRABWAIT in PART_UPPER; after B releases the
    prop, ``setAnimeEquipSword`` installs REST in that branch while the lower
    locomotion phase continues.  World positions are kept separate because
    Link can move between the held draw and the collision draw.
    """
    if object_type not in ("bomb", "pot_small"):
        raise ValueError("moving B-drop pose supports bomb and pot_small")
    if lower_anims is None:
        lower_anims = j3d_eval.load_anim(
            os.path.join(_repo_root(), "_generated", "anim", "link_anim_walk_dash.json")
        )
    if upper_anims is None:
        upper_anims = load_grab_anims()
    if skeleton is None:
        skeleton = load_skeleton()
    if collision_facing is None:
        collision_facing = facing

    hands = [
        _layered_joint_translation(
            lower_anims, held_lower, upper_anims, "grabwait", grab_frame,
            skeleton, held_link_pos, facing, joint, held_lean,
            body_lean=held_body_lean, neutralize_grab_root=True,
            root_matrix=held_root_matrix,
        )
        for joint in (CL_JNT_LEFT_HAND, CL_JNT_RIGHT_HAND)
    ]
    held_prop = tuple(fp.fmuls(0.5, fp.fadds(hands[0][i], hands[1][i])) for i in range(3))
    equip_frame = fp.fsubs(EQUIP_REST_END_FRAME, 0.001)
    root = _layered_joint_translation(
        lower_anims, collision_lower, upper_anims, "rest", equip_frame,
        skeleton, collision_link_pos, collision_facing, CL_JNT_LINK_ROOT, collision_lean,
        body_lean=collision_body_lean, equip_transition=True,
        root_matrix=collision_root_matrix,
    )
    neck = _layered_joint_translation(
        lower_anims, collision_lower, upper_anims, "rest", equip_frame,
        skeleton, collision_link_pos, collision_facing, CL_JNT_NECK, collision_lean,
        body_lean=collision_body_lean, equip_transition=True,
        root_matrix=collision_root_matrix,
    )
    ltoe = _layered_joint_translation(
        lower_anims, collision_lower, upper_anims, "rest", equip_frame,
        skeleton, collision_link_pos, collision_facing, CL_JNT_LEFT_TOE, collision_lean,
        body_lean=collision_body_lean, equip_transition=True,
        root_matrix=collision_root_matrix,
    )
    rtoe = _layered_joint_translation(
        lower_anims, collision_lower, upper_anims, "rest", equip_frame,
        skeleton, collision_link_pos, collision_facing, CL_JNT_RIGHT_TOE, collision_lean,
        body_lean=collision_body_lean, equip_transition=True,
        root_matrix=collision_root_matrix,
    )
    base_y = rtoe[1] if ltoe[1] > rtoe[1] else ltoe[1]
    center = (
        fp.fmuls(0.5, fp.fadds(root[0], neck[0])),
        base_y,
        fp.fmuls(0.5, fp.fadds(root[2], neck[2])),
    )
    height = fp.fadds(40.1, fp.fsubs(neck[1], base_y))
    return DecompBDropPose(
        animation_position=int(grab_frame),
        held_frame=float(grab_frame),
        collision_under_frame=float(collision_lower["f0"]),
        equip_frame=equip_frame,
        held_prop_pos=held_prop,
        link_co_center=center,
        link_co_radius=30.0,
        link_co_height=height,
    )


def decomp_b_drop_pose(link_pos, facing, animation_position, object_type="bomb",
                       *, anims=None, skeleton=None):
    """Build the exact held-prop and Link-Co centers for a normal B drop.

    The TAS overlay's displayed animation position trails the draw pose by one
    update. Pressing B advances GRABWAIT once more before handling the release:

    * held prop: GRABWAIT ``animation_position + 1`` (last setGrabItemPos draw)
    * Link Co: GRABWAIT root/center at ``animation_position + 2`` mixed with
      newly installed REST at ``end - 0.001`` for the upper-body branch

    This ordering is decomp-derived and live-validated at animation positions
    11 and 51 at nonzero world coordinates/facings.
    """
    if object_type not in ("bomb", "pot_small"):
        raise ValueError("first-principles B-drop pose supports bomb and pot_small")
    if anims is None:
        anims = load_grab_anims()
    if skeleton is None:
        skeleton = load_skeleton()
    frame_max = int(anims["grabwait"]["frame_max"])
    held_frame = float((int(animation_position) + 1) % frame_max)
    under_frame = float((int(animation_position) + 2) % frame_max)
    equip_frame = fp.fsubs(EQUIP_REST_END_FRAME, 0.001)

    left_hand = _planned_joint_translation(
        anims, skeleton, held_frame, equip_frame, link_pos, facing,
        CL_JNT_LEFT_HAND, False,
    )
    right_hand = _planned_joint_translation(
        anims, skeleton, held_frame, equip_frame, link_pos, facing,
        CL_JNT_RIGHT_HAND, False,
    )
    held_prop = (
        fp.fmuls(0.5, fp.fadds(left_hand[0], right_hand[0])),
        fp.fmuls(0.5, fp.fadds(left_hand[1], right_hand[1])),
        fp.fmuls(0.5, fp.fadds(left_hand[2], right_hand[2])),
    )
    root = _planned_joint_translation(
        anims, skeleton, under_frame, equip_frame, link_pos, facing,
        CL_JNT_LINK_ROOT, True,
    )
    neck = _planned_joint_translation(
        anims, skeleton, under_frame, equip_frame, link_pos, facing,
        CL_JNT_NECK, True,
    )
    # The waist joint switches back to PART_UNDER, so both toe matrices are
    # pure GRABWAIT at the collision frame.
    ltoe = _planned_joint_translation(
        anims, skeleton, under_frame, equip_frame, link_pos, facing,
        CL_JNT_LEFT_TOE, False,
    )
    rtoe = _planned_joint_translation(
        anims, skeleton, under_frame, equip_frame, link_pos, facing,
        CL_JNT_RIGHT_TOE, False,
    )
    base_y = rtoe[1] if ltoe[1] > rtoe[1] else ltoe[1]
    center = (
        fp.fmuls(0.5, fp.fadds(root[0], neck[0])),
        base_y,
        fp.fmuls(0.5, fp.fadds(root[2], neck[2])),
    )
    height = fp.fadds(40.1, fp.fsubs(neck[1], base_y))
    return DecompBDropPose(
        animation_position=int(animation_position),
        held_frame=held_frame,
        collision_under_frame=under_frame,
        equip_frame=equip_frame,
        held_prop_pos=held_prop,
        link_co_center=center,
        link_co_radius=30.0,
        link_co_height=height,
    )


def _rotate_xz(dx, dz, facing):
    s = M.cM_ssin_s16(facing)
    c = M.cM_scos_s16(facing)
    return (
        fp.fadds(fp.fmuls(dx, c), fp.fmuls(dz, s)),
        fp.fadds(fp.fmuls(fp.f32(-dx), s), fp.fmuls(dz, c)),
    )


def calibrated_b_drop_pose(link_pos, facing, table_frame, local_push_dx,
                           local_push_dz, object_type="bomb", *, anims=None,
                           skeleton=None):
    """Reconstruct world prop/Link centers from a measured free-space push.

    Unlike rotating the final push endpoint, this inverts the Co correction to
    recover the radius-30 center separation.  The exact release-frame Link Co
    center is the local anchor; the measured separation places the prop center
    relative to it.  Link and prop are then transformed independently into
    world space before :func:`b_drop_collision_step` recomputes Co after the
    prop's BG correction.

    This is the practical calibrated model while the layered B-release pose is
    unfinished. It is not a first-principles animation result: the measured row
    supplies Link's X/Z center relative to the held prop. ``table_frame`` is the
    zero-based CSV row.  The user-visible animation position is one-based, and
    ``animeUpdate`` runs before the B input is handled, so Link's release Co
    uses the following GRABWAIT frame.  The prop retains the preceding held
    pose's Y, but its X/Z comes from the measured center separation.

    Anchoring in local space is important.  The previous implementation first
    transformed the held prop and then subtracted a rotated separation in
    world space.  That couples two independent actor/model transforms and can
    move either center by one world-coordinate ULP, which produced false seam
    candidates away from the original calibration wall.
    """
    if object_type not in ("bomb", "pot_small"):
        raise ValueError("calibrated bomb table only supports bomb and pot_small")
    if anims is None:
        anims = load_grab_anims()
    if skeleton is None:
        skeleton = load_skeleton()

    local_sep = center_separation_from_measured_push(
        local_push_dx, local_push_dz, object_type=object_type
    )
    world_sep = _rotate_xz(local_sep[0], local_sep[1], facing)

    frame_max = int(anims["grabwait"]["frame_max"])
    release_frame = float((int(table_frame) + 1) % frame_max)
    local_held_pose = CarryPose((0.0, 0.0, 0.0), 0, float(table_frame), anim="grabwait")
    local_held_prop = carried_actor_pos(local_held_pose, anims=anims, skeleton=skeleton)
    local_release_pose = CarryPose((0.0, 0.0, 0.0), 0, release_frame, anim="grabwait")
    local_body = link_body_co(
        local_release_pose, anims=anims, skeleton=skeleton, carrying=False
    )
    # The released actor's absolute X/Z comes from the last setGrabItemPos()
    # hand midpoint. Use the measured center separation to infer Link's Co
    # center from that prop anchor, not the other way around.
    local_prop = local_held_prop
    world_base, _ = fk.world_base(link_pos[0], link_pos[1], link_pos[2], facing)
    held_prop = fk.mtx_mult_vec(world_base, local_prop)

    local_link_center = (
        fp.fsubs(local_prop[0], local_sep[0]),
        local_body["center"][1],
        fp.fsubs(local_prop[2], local_sep[1]),
    )
    link_center = fk.mtx_mult_vec(world_base, local_link_center)
    return CalibratedBDropPose(
        table_frame=int(table_frame),
        held_prop_pos=held_prop,
        link_co_center=link_center,
        link_co_radius=local_body["radius"],
        link_co_height=local_body["height"],
        local_center_separation=local_sep,
        world_center_separation=world_sep,
    )


def b_drop_collision_step(link_pos, link_co_center, link_co_height, held_prop_pos,
                          object_type, walls, *, link_co_radius=30.0,
                          link_wall_h=(30.1, 89.9, 125.0), link_wall_r=35.0,
                          link_motion=(0.0, 0.0, 0.0)):
    """Run the source-ordered horizontal part of an ordinary B drop.

    ``held_prop_pos`` is the actor position last written by ``setGrabItemPos``.
    The released prop first executes its own movement and ``mAcch.CrrPos``.  Its
    active Co body is then tested against Link during scene Draw.  Link consumes
    the resulting pending correction on its next execute before its own
    ``mAcch.CrrPos``. ``link_motion`` is actor displacement applied earlier in
    that ``posMove``; it is added separately before the Co move so f32 addition
    order is retained.

    Bomb and small-pot B drops both enter this function with zero horizontal
    speed.  A bomb uses an R30 sphere centered at actor Y+30; for the horizontal
    SetPosCorrect calculation it has the same base/radius/height envelope as the
    small pot's R30/H60 cylinder.  The vertical overlap gate is preserved.
    """
    obj = DROP_OBJECTS[object_type]
    spec = obj.prop_spec
    prop_old = tuple(fp.f32(v) for v in held_prop_pos)
    prop_pre_bg = (
        prop_old[0],
        fp.fadds(prop_old[1], obj.gravity),
        prop_old[2],
    )
    # Bomb mCir is H30/R30 with LineCheck on. Tsubo's mAcchCir is also H30
    # with the object's radius; mode_wait has LineCheck off. With zero XZ
    # movement the distinction only affects diagnostics, not the static push.
    prop_after_bg, prop_bg_info = acch_crr_pos(
        prop_old,
        prop_pre_bg,
        walls,
        speed_y=obj.gravity,
        wall_h=(30.0,),
        wall_r=spec.radius,
        line_check_flag=(object_type == "bomb"),
    )
    prop_co_center = (
        prop_after_bg[0],
        fp.fadds(prop_after_bg[1], obj.co_y_offset),
        prop_after_bg[2],
    )
    link_center = tuple(fp.f32(v) for v in link_co_center)
    # Use the sphere's bottom as the equivalent vertical-cylinder base. The
    # CylSph source uses the same horizontal radius sum and overlap depth.
    prop_base = (
        prop_co_center[0],
        fp.fsubs(prop_co_center[1], spec.radius) if spec.shape.startswith("sphere")
        else prop_co_center[1],
        prop_co_center[2],
    )
    link_push = co_push_link(
        link_center,
        link_co_radius,
        link_co_height,
        prop_base,
        spec.radius,
        spec.height,
        link_w=WEIGHT_LINK,
        other_w=spec.weight,
    )
    link_old = tuple(fp.f32(v) for v in link_pos)
    link_moved = tuple(fp.fadds(link_old[i], fp.f32(link_motion[i])) for i in range(3))
    link_raw = tuple(fp.fadds(link_moved[i], link_push[i]) for i in range(3))
    link_after_bg, link_bg_info = acch_crr_pos(
        link_old,
        link_raw,
        walls,
        wall_h=link_wall_h,
        wall_r=link_wall_r,
    )
    return BDropCollisionResult(
        object_type=object_type,
        prop_old=prop_old,
        prop_after_bg=prop_after_bg,
        prop_bg_info=prop_bg_info,
        prop_co_center=prop_co_center,
        link_push=link_push,
        link_raw=link_raw,
        link_after_bg=link_after_bg,
        link_bg_info=link_bg_info,
    )


def center_separation_from_measured_push(local_dx, local_dz, object_type="bomb",
                                         link_radius=30.0):
    """Invert one free-space push into the Co center-to-center XZ vector.

    This is a calibration helper, not a wall proof. It recovers where the prop
    Co center was relative to Link's center at actor origin. A wall proof must
    transform the two centers separately to world f32 coordinates and rerun
    :func:`b_drop_collision_step`; rotating the final vector loses translation
    rounding and any prop background correction.
    """
    spec = DROP_OBJECTS[object_type].prop_spec
    shares = push_shares(WEIGHT_LINK, spec.weight)
    if shares is None or shares[0] <= 0.0:
        raise ValueError("object pair has no movable Link share")
    mag = math.hypot(local_dx, local_dz)
    if mag <= 0.0:
        raise ValueError("measured push must be nonzero")
    separation = link_radius + spec.radius - mag / shares[0]
    if separation < 0.0:
        raise ValueError("measured push exceeds the maximum Co correction")
    # Link is pushed away from the prop, so prop-link points opposite the push.
    return (
        fp.f32(-local_dx / mag * separation),
        fp.f32(-local_dz / mag * separation),
    )


def available():
    try:
        load_grab_anims()
        load_skeleton()
        return True
    except (FileNotFoundError, OSError, KeyError):
        return False


def dump_displacements(object_types=("bomb", "pot_small", "pot_large"), anim="grabwait",
                       facing=0, frames=None):
    """Yield held-pose first-active Co centers, not final Link push rows."""
    if frames is None:
        anims = load_grab_anims()
        end = int(anims[anim]["frame_max"])
        frames = range(end + 1)
    else:
        anims = load_grab_anims()
    sk = load_skeleton()
    for frame in frames:
        pose = CarryPose((0.0, 0.0, 0.0), facing, float(frame), anim=anim)
        carried = carried_actor_pos(pose, anims=anims, skeleton=sk)
        for name in object_types:
            co = first_active_co_center(
                CarryPose((0.0, 0.0, 0.0), facing, float(frame), anim=anim,
                          hand_mid=carried),
                name,
            )
            yield {
                "object": name,
                "anim": anim,
                "frame": frame,
                "facing": facing & 0xFFFF,
                "hand_mid": carried,
                "co_disp": co,
            }


def _parse_cli(argv):
    opts = {"objects": ["bomb", "pot_small", "pot_large"], "anim": "grabwait",
            "facing": 0, "frames": None}
    for a in argv:
        if a.startswith("object="):
            opts["objects"] = [p for p in a[7:].split(",") if p]
        elif a.startswith("anim="):
            opts["anim"] = a[5:]
        elif a.startswith("facing="):
            opts["facing"] = int(a[7:], 0)
        elif a.startswith("frame="):
            opts["frames"] = [float(x) for x in a[6:].split(",") if x]
        elif a in ("-h", "--help", "help"):
            opts["help"] = True
    return opts


def main(argv=None):
    opts = _parse_cli(sys.argv[1:] if argv is None else argv)
    if opts.get("help"):
        print("usage: python -m tww_sim.core.drop_release "
              "[object=bomb,pot_small,pot_large] [anim=grabwait] [facing=0x0000] [frame=1.0,1.8]")
        return 0
    unknown = [p for p in opts["objects"] if p not in DROP_OBJECTS]
    if unknown:
        print("unknown object(s): %s" % ", ".join(unknown), file=sys.stderr)
        return 2
    try:
        rows = list(dump_displacements(opts["objects"], opts["anim"], opts["facing"], opts["frames"]))
        print("object,anim,frame,facing,hand_x,hand_y,hand_z,co_dx,co_dy,co_dz")
        for r in rows:
            h = r["hand_mid"]
            c = r["co_disp"]
            print("%s,%s,%.6g,%d,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g" % (
                r["object"], r["anim"], r["frame"], r["facing"],
                h[0], h[1], h[2], c[0], c[1], c[2],
            ))
    except FileNotFoundError as exc:
        print("missing generated animation data: %s" % exc, file=sys.stderr)
        print("run: python -m harness.anim.parse_bmd", file=sys.stderr)
        print("run: python -m harness.anim.parse_bck which=link_anim_grab", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
