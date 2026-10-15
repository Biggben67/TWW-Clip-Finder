"""Offline binary32 input search for a full-speed moving small-pot seam clip."""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import heapq
import itertools
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import shutil
from types import SimpleNamespace

from harness.collision.find_drop_push_candidate import (
    _candidate_crosses,
    prepare_search,
)
from harness.collision.gap_search import first_f32_acch_clip
from harness.collision.room_collision import load_live_room_collision, load_room_collision
from harness.dtm.writer import build_dtm_from_sticks, install_savestate_companions
from harness.dtm.stick import dtm_stick
from tww_sim.core import drop_release as dr
from tww_sim.core import fp
from tww_sim.core.anim import fk
from tww_sim.core.anim.anim_state import ANIM_META, EMode_LOOP, FrameCtrl, UnderAnimState
from tww_sim.land.constants import MOVE
from tww_sim.land.state import LandState
from tww_sim.land.plan_land import stick_for_bearing, world_angle_s16


BUTTON_B = 0x0200

_MOTION_GRID_STATE = None
_MOTION_GRID_FOLLOW = None
_MOTION_GRID_OLD = None
_MOTION_GRID_POSE = None
_MOTION_GRID_CONTEXT = None


def _init_motion_grid_worker(state, follow, old, pose, context):
    global _MOTION_GRID_STATE, _MOTION_GRID_FOLLOW, _MOTION_GRID_OLD
    global _MOTION_GRID_POSE, _MOTION_GRID_CONTEXT
    _MOTION_GRID_STATE = state
    _MOTION_GRID_FOLLOW = follow
    _MOTION_GRID_OLD = old
    _MOTION_GRID_POSE = pose
    _MOTION_GRID_CONTEXT = context


def _motion_grid_worker(stick):
    stick_x, stick_y = stick
    next_state = _MOTION_GRID_STATE.clone()
    pending = list(next_state._inbuf[0])
    pending[0], pending[1] = stick_x, stick_y
    next_state._inbuf[0] = tuple(pending)
    follow = _MOTION_GRID_FOLLOW
    next_state.step(
        follow["stickX"], follow["stickY"], follow.get("buttons", 0),
        follow.get("triggerL", 0), follow.get("substickX", 128),
        follow.get("substickY", 128),
    )
    old = _MOTION_GRID_OLD
    motion = (
        next_state.pos_x - old[0], next_state.pos_y - old[1],
        next_state.pos_z - old[2],
    )
    pose = _MOTION_GRID_POSE
    result = dr.b_drop_collision_step(
        old, pose.link_co_center, pose.link_co_height, pose.held_prop_pos,
        "pot_small", _MOTION_GRID_CONTEXT.walls,
        link_co_radius=pose.link_co_radius, link_motion=motion,
    )
    crosses, _stable = _candidate_crosses(_MOTION_GRID_CONTEXT, old, result)
    if result.prop_bg_info["wall_hit"]:
        return None
    return stick_x, stick_y, result.link_raw, result.link_after_bg, crosses


@dataclass
class PoseFrame:
    pos: tuple[float, float, float]
    facing: int
    lean: int
    body_lean: int
    lower: UnderAnimState
    upper: FrameCtrl
    lower_blend: dict | None = None


@dataclass
class Node:
    state: LandState
    lower: UnderAnimState
    upper: FrameCtrl
    previous: PoseFrame
    held_prop: tuple[float, float, float] | None
    rows: list[dict]
    prefix_patch: dict[int, dict]


@dataclass
class Hit:
    depth: int
    b_index: int
    old: tuple
    raw: tuple
    resolved: tuple
    retained_depth: float
    facing: int
    speed: float
    rows: list[dict]


def _controller_tuple(row):
    return (
        row["stickX"], row["stickY"], row.get("buttons", 0),
        row.get("triggerL", 0), row.get("substickX", 128),
        row.get("substickY", 128),
    )


def _signed_s16(value):
    value = int(value) & 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _clock(frame, rate, end):
    ctrl = FrameCtrl()
    ctrl.set(EMode_LOOP, 0.0, end, rate, frame)
    return ctrl


def _lower_clock(seed):
    move0 = seed.get("move0", "dash")
    move1 = seed.get("move1", move0)
    lower = UnderAnimState(move0_anim=move0, move0_frame=seed["f0"],
                           move1_anim=move1, m34C3=1)
    lower.fc0.set(EMode_LOOP, 0.0, ANIM_META[move0][0], seed["rate0"], seed["f0"])
    lower.fc1.set(EMode_LOOP, 0.0, ANIM_META[move1][0], seed["rate1"], seed["f1"])
    lower.ratio = seed["ratio"]
    lower.m3598 = seed["m3598"]
    return lower


def _matrix_rows(flat):
    return [list(flat[index:index + 4]) for index in range(0, 12, 4)]


def _matrix_quat_scale(matrix, reference):
    """Recover a local TRS from a calculated J3D joint matrix.

    The captured matrix has already passed through PSMTXQuat, so this inverse
    only seeds a two-frame old-pose blend; subsequent poses return to the
    regular bit-faithful animation evaluator.
    """
    scale = []
    for column in range(3):
        length = math.sqrt(sum(float(matrix[row][column]) ** 2 for row in range(3)))
        scale.append(fp.f32(length if length else 1.0))
    r = [[float(matrix[row][column]) / float(scale[column]) for column in range(3)]
         for row in range(3)]
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        quat = (0.25 * s, (r[2][1] - r[1][2]) / s,
                (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s)
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2.0
        quat = ((r[2][1] - r[1][2]) / s, 0.25 * s,
                (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s)
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2.0
        quat = ((r[0][2] - r[2][0]) / s, (r[0][1] + r[1][0]) / s,
                0.25 * s, (r[1][2] + r[2][1]) / s)
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2.0
        quat = ((r[1][0] - r[0][1]) / s, (r[0][2] + r[2][0]) / s,
                (r[1][2] + r[2][1]) / s, 0.25 * s)
    norm = math.sqrt(sum(component * component for component in quat))
    quat = tuple(fp.f32(component / norm) for component in quat)
    if sum(quat[index] * reference[index] for index in range(4)) < 0.0:
        quat = tuple(fp.f32(-component) for component in quat)
    return quat, tuple(scale)


def _seed_captured_old_pose(foot, seed):
    captured = seed.get("joint_matrices")
    if not captured:
        return False
    matrices = [_matrix_rows(matrix) for matrix in captured]
    snap = seed["snapshot"]
    base, _inverse = fk.world_base(
        snap["x"], snap["y"], snap["z"], snap["facing"], int(seed.get("shape_z", 0))
    )
    joints = set(foot.ff._chains[34]) | set(foot.ff._chains[39])
    if foot.ff.body_co:
        joints.update((2, 3, 4, 14, 15))
    for joint in sorted(joints):
        parent = foot.ff.parent[joint]
        parent_world = base if parent == -1 else matrices[parent]
        local = fk.mtx_concat(fk.psmtx_inverse(parent_world), matrices[joint])
        quat, scale = _matrix_quat_scale(local, foot.ff.old_quat[joint])
        foot.ff.old_quat[joint] = quat
        foot.ff.old_trans[joint] = tuple(fp.f32(local[row][3]) for row in range(3))
        foot.ff.old_scale[joint] = scale
    return True


def _captured_current_feet(seed):
    """Return draw-N feet from Link's live joint matrices.

    The public mFootData fields visible at frame N still contain draw N-1.
    posMoveFromFootPos on frame N+1 consumes draw N and N-1, so a mid-proc
    seed must obtain the newer side directly from mpCLModel.
    """
    captured = seed.get("joint_matrices")
    if not captured:
        return None
    matrices = [_matrix_rows(matrix) for matrix in captured]
    snap = seed["snapshot"]
    _base, inverse = fk.world_base(
        snap["x"], snap["y"], snap["z"], snap["facing"], int(seed.get("shape_z", 0))
    )
    right = fk.mtx_concat(inverse, matrices[39])
    left = fk.mtx_concat(inverse, matrices[34])
    rt = fk.mtx_mult_vec(right, fk.L_TOE)
    lt = fk.mtx_mult_vec(left, fk.L_TOE)
    rh = fk.mtx_mult_vec(right, fk.L_HEEL)
    lh = fk.mtx_mult_vec(left, fk.L_HEEL)
    return (*rt, *lt, *rh, *lh)


def _make_seed(seed, walls, floors=None, *, force_state=MOVE, model_draw=False):
    """Reconstruct an exact moving LandState from a captured joint/foot seed.

    Moving-pot searches historically force ``MOVE``. Slash-route calibration can
    pass ``force_state=None`` to retain a captured ``ATN_MOVE`` and can enable the
    modeled item-to-sword draw without changing the existing drop-search path.
    """
    snap = seed["snapshot"]
    lower = _lower_clock(seed["lower"])
    gnd_seed = None
    if floors:
        from tww_sim.land.floors import ground_cross
        floor_y, floor_index = ground_cross(
            floors, snap["x"], fp.fadds(snap["y"], 60.0), snap["z"]
        )
        ground = seed.get("ground", {})
        gnd_seed = {
            "m35b8": ground.get("m35b8", 0.0),
            "m35c4": ground.get("m35c4", 0.0),
            "foot024": ground.get("foot024"),
            "foot001": tuple(ground.get("foot001", (5, 5))),
            "waist": ground.get("waist"),
            "ground_hit": floor_index is not None,
            "gnd_pla": floors[floor_index].pla if floor_index is not None else None,
        }
    seed_state = snap.get("state", MOVE) if force_state is None else force_state
    state = LandState(
        pos_x=snap["x"], pos_y=snap["y"], pos_z=snap["z"],
        facing=snap["facing"], travel=snap["travel"],
        csangle=snap["camera"], state=seed_state,
        nspeed=snap["normal_speed"], speedF=snap["speed_f"],
        use_anim=True, native=False, walls=walls, floors=floors,
        gnd_seed=gnd_seed, input_delay=2,
        low_life=seed.get("life", 99) <= 6,
        sword_drawn=bool(snap.get("sword_drawn", False)),
        model_draw=bool(model_draw),
    )
    state._inbuf = [_controller_tuple(row) for row in seed["rows"][-2:]]
    if len(seed["rows"]) >= 3:
        previous = seed["rows"][-3]
        state._abtn_prev = int(previous.get("buttons", 0))
        state._l_prev = bool(state._abtn_prev & 0x40) or int(previous.get("triggerL", 0)) >= 200
    state.msd = fp.f32(snap.get("stick_distance", state.msd))
    state._drop_object_type = seed.get("object_type", "pot_small")
    history = seed.get("movement_history", {})
    state.m34dc = int(history.get("m34dc", state.m34dc)) & 0xFFFF
    state.m34de = int(history.get("m34de", state.m34de)) & 0xFFFF
    state.m34E6 = int(history.get("m34e6", state.m34E6)) & 0xFFFF
    state.target = int(history.get("target", state.target)) & 0xFFFF
    state.m34ea = int(history.get("m34ea", state.m34ea)) & 0xFFFF
    state.m351C = int(history.get("m351c", int(seed.get("shape_z", 0)) * 2)) & 0xFFFF
    state.direction = int(history.get("direction", state.direction))
    state._draw_lean = int(seed.get("shape_z", 0))
    foot = state._foot
    foot.st = lower.clone()
    current_feet = _captured_current_feet(seed)
    if current_feet is not None and seed.get("feet"):
        foot.t1 = tuple(current_feet)
        foot.t2 = tuple(seed["feet"])
    foot.prev_f312 = seed["lower"]["m359C"]
    foot.m35B4 = seed["lower"]["m35B4"]
    foot.started = True
    foot.stopped = False
    foot.defer_draw = True
    foot.ff.seed(lower.move0, lower.fc0.frame)
    _seed_captured_old_pose(foot, seed)
    if seed.get("seed_kind") == "move_reentry_anchor":
        # The captured frame is the ATN_MOVE/ATN_ACTOR_MOVE -> MOVE transition.
        # procMove_init triggered the 2.4-frame old-pose morph and that frame's
        # draw already consumed its first rate. Recreate the remaining 0.2857
        # draw so the next frame's toe pose and following speedF stay exact.
        foot.ff.morf.init_morf(state.MOVE_REENTRY_MORF)
        foot.ff.morf.dec()
    elif seed.get("seed_kind") == "exact_moving_anchor":
        # This seed is already inside a settled MOVE trajectory. The captured
        # calculated matrices are the current old-pose source; no proc-entry
        # morph is active and restarting one changes both toes and held-item FK.
        foot.ff.morf.init_morf(-1.0)
    else:
        # The saved first-moving frame is the procMove morph trigger. Its end-of-
        # frame joint pass has already advanced the 2.4-frame morph to this state.
        foot.ff.morf.init_morf(state.MOVE_REENTRY_MORF)
        foot.ff.morf.dec()
    upper = _clock(seed["upper_grab"]["frame"], seed["upper_grab"]["rate"], 60.0)
    previous = _pose_from_seed(seed["previous"])
    held_prop = tuple(snap["prop_pos"]) if snap.get("prop_pos") is not None else None
    return Node(state, lower, upper, previous, held_prop, [], {})


def _pose_from_seed(seed):
    snap = seed["snapshot"]
    return PoseFrame(
        (snap["x"], snap["y"], snap["z"]), snap["facing"], int(seed.get("shape_z", 0)),
        int(snap.get("body_angles", (0, 0, 0))[2]),
        _lower_clock(seed["lower"]),
        _clock(seed["upper_grab"]["frame"], seed["upper_grab"]["rate"], 60.0),
        {
            "move0": seed["lower"].get("move0", "walk"),
            "move1": seed["lower"].get("move1", "dash"),
            "f0": seed["lower"]["f0"], "f1": seed["lower"]["f1"],
            "ratio": seed["lower"]["ratio"],
        },
    )


def _pose_of(node):
    return PoseFrame(
        (node.state.pos_x, node.state.pos_y, node.state.pos_z),
        node.state.facing, node.state._draw_lean,
        _signed_s16(node.state.m351C) >> 1,
        node.lower.clone(), node.upper.clone(), _lower_pose(node),
    )


def _step(node, row):
    state = node.state.clone()
    state.step(
        row["stickX"], row["stickY"], row.get("buttons", 0),
        row.get("triggerL", 0), row.get("substickX", 128),
        row.get("substickY", 128),
    )
    lower = state._foot.st.clone()
    upper = node.upper.clone()
    upper.update()
    return Node(
        state, lower, upper, _pose_of(node), None, node.rows + [dict(row)],
        dict(node.prefix_patch),
    )


def _lower_pose(node):
    if isinstance(node, PoseFrame) and node.lower_blend is not None:
        return node.lower_blend
    lower = node.lower
    return {
        "move0": lower.move0,
        "move1": lower.move1 or lower.move0,
        "f0": lower.fc0.frame,
        "f1": lower.fc1.frame if lower.move1 is not None else lower.fc0.frame,
        "ratio": lower.ratio,
    }


def _movement_rows(state, seam, spread=4096, step=128):
    direct = world_angle_s16(seam[0] - state.pos_x, seam[2] - state.pos_z)
    rows = []
    seen = set()
    for delta in range(-spread, spread + 1, step):
        bearing = (direct + delta) & 0xFFFF
        sx, sy = dtm_stick(stick_for_bearing(bearing, state.csangle, 1.0))
        if (sx, sy) in seen:
            continue
        seen.add((sx, sy))
        rows.append({
            "stickX": sx, "stickY": sy,
            "substickX": 128, "substickY": 128,
            "buttons": 0, "triggerL": 0, "triggerR": 0,
        })
    return rows


def _depth_diverse(candidates, per_depth=8):
    """Retain the best routes at every B timing, not only the nearest timing."""
    retained = []
    counts = {}
    for candidate in candidates:
        depth = int(candidate.get("depth", -1))
        if counts.get(depth, 0) >= per_depth:
            continue
        retained.append(candidate)
        counts[depth] = counts.get(depth, 0) + 1
    return retained


def _moving_candidate_rank(candidate, context):
    """Rank a push by its swept seam geometry, preserving forward crossings."""
    old_x, old_z = candidate["old"][0], candidate["old"][2]
    raw_x, raw_z = candidate["raw"][0], candidate["raw"][2]
    vx, vz = raw_x - old_x, raw_z - old_z
    wx = context.seam_target[0] - old_x
    wz = context.seam_target[2] - old_z
    length_sq = vx * vx + vz * vz
    if length_sq <= 0.0:
        line_offset = math.inf
        shortfall = math.inf
    else:
        length = math.sqrt(length_sq)
        line_offset = abs(vx * wz - vz * wx) / length
        along = (wx * vx + wz * vz) / length_sq
        shortfall = (along - 1.0) * length
    dust_distance = candidate.get("dust_distance")
    return (
        1 if candidate.get("prop_wall") else 0,
        0 if shortfall <= 0.0 else 1,
        0 if dust_distance is not None else 1,
        dust_distance if dust_distance is not None else math.inf,
        line_offset + max(0.0, shortfall),
        line_offset,
        max(0.0, shortfall),
    )


def _candidate_local_dust(candidate, context, box_ulps=12, max_calls=625):
    """Attach the nearest authoritative f32 endpoint for this release state.

    The accepted dust depends on ``old`` as well as the raw endpoint. A target
    inherited from another route is therefore not a valid optimization goal.
    """
    cache_key = (int(box_ulps), int(max_calls))
    if candidate.get("dust_probe") == cache_key:
        target = candidate.get("dust_target")
        return tuple(target) if target is not None else None
    candidate["dust_probe"] = cache_key
    candidate.pop("dust_target", None)
    candidate.pop("dust_distance", None)
    old = candidate["old"]
    raw = candidate["raw"]
    vx, vz = raw[0] - old[0], raw[2] - old[2]
    length = math.hypot(vx, vz)
    if length <= 0.0:
        return None
    wx = context.seam_target[0] - old[0]
    wz = context.seam_target[2] - old[2]
    line_offset = abs(vx * wz - vz * wx) / length
    along = (wx * vx + wz * vz) / (length * length)
    if (
        line_offset > 0.05
        or along > 1.02
        or context.wall_a.pla.func(raw) >= 0.0
        or context.wall_b.pla.func(raw) >= 0.0
    ):
        return None
    dust, calls = first_f32_acch_clip(
        context.walls, tuple(old), (raw[0], raw[2]), old[1],
        box_ulps=box_ulps, max_calls=max_calls,
    )
    candidate["dust_calls"] = calls
    if dust is None:
        return None
    target = tuple(dust["new"])
    candidate["dust_target"] = target
    candidate["dust_distance"] = math.hypot(
        raw[0] - target[0], raw[2] - target[1]
    )
    return target


def _annotate_dust_frontier(candidates, context, per_depth=12):
    """Probe candidate-local dust for the best geometry at every B timing."""
    geometric = sorted(candidates, key=lambda item: (
        int(item.get("depth", 1 << 30)), _moving_candidate_rank(item, context)
    ))
    counts = {}
    for candidate in geometric:
        depth = int(candidate.get("depth", -1))
        if counts.get(depth, 0) >= per_depth:
            continue
        counts[depth] = counts.get(depth, 0) + 1
        _candidate_local_dust(
            candidate, context, box_ulps=32, max_calls=4225,
        )
    candidates.sort(key=lambda item: (
        0 if item.get("dust_distance") is not None else 1,
        int(item.get("depth", 1 << 30)),
        _moving_candidate_rank(item, context),
    ))
    return candidates


def _refine_promising_routes(start, candidates, context, prefix, lower_anims,
                              upper_anims, skeleton, release_probe, log,
                              minimum_depth=0, per_depth=2):
    """Try exact local inversion before opening the combinatorial fallback.

    Constant- and two-bearing routes already cover the useful fast approach
    families. Once one of those routes has candidate-local exact dust, a
    broad movement beam only repeats work at much greater cost.
    """
    if not candidates:
        return []
    _annotate_dust_frontier(candidates, context, per_depth=4)
    selected = []
    counts = {}
    for candidate in candidates:
        depth = int(candidate.get("depth", -1))
        if depth < minimum_depth or candidate.get("dust_target") is None:
            continue
        if counts.get(depth, 0) >= per_depth:
            continue
        selected.append(candidate)
        counts[depth] = counts.get(depth, 0) + 1
    if not selected:
        log("fast-route screen found no candidate-local exact dust")
        return []
    log(
        "refining %d fast route(s) with candidate-local exact f32 dust before "
        "the fallback beam" % len(selected)
    )
    for candidate in selected:
        hits = _refine_near_route(
            start, candidate, context, prefix, lower_anims, upper_anims,
            skeleton, release_probe, log, minimum_depth,
        )
        if hits:
            return hits
    return []


def _fallback_movement_rows(state, seam):
    """Use analog resolution only where it can affect a release candidate."""
    distance = math.hypot(state.pos_x - seam[0], state.pos_z - seam[2])
    if distance > 100.0:
        return _movement_rows(state, seam, spread=4096, step=1024)
    if distance > 78.0:
        return _movement_rows(state, seam, spread=6144, step=768)
    return _movement_rows(state, seam, spread=8192, step=512)


def _fallback_beam_width(distance, requested):
    if distance > 100.0:
        return min(requested, 400)
    if distance > 78.0:
        return min(requested, 1000)
    return min(requested, 1500)


def _try_drop(node, context, prefix_rows, lower_anims, upper_anims, skeleton,
              diagnostics=None, release_probe=None, minimum_depth=0,
              next_move=None):
    if diagnostics is not None:
        diagnostics["tested"] = diagnostics.get("tested", 0) + 1
    if len(prefix_rows) + len(node.rows) < 2:
        if diagnostics is not None:
            diagnostics["too_short"] = diagnostics.get("too_short", 0) + 1
        return None
    if len(node.rows) < minimum_depth:
        if diagnostics is not None:
            diagnostics["immutable_prefix"] = diagnostics.get("immutable_prefix", 0) + 1
        return None
    old = (node.state.pos_x, node.state.pos_y, node.state.pos_z)
    seam_distance = math.hypot(
        old[0] - context.seam_target[0], old[2] - context.seam_target[2]
    )
    # A small-pot push is at most 54u and one full-speed movement frame adds
    # 17u. Outside this finite corner neighborhood, the incident triangle
    # planes are only infinite mathematical extensions, not the selected seam.
    if seam_distance > 80.0:
        if diagnostics is not None:
            diagnostics["too_far"] = diagnostics.get("too_far", 0) + 1
        return None
    if not (
        context.wall_a.pla.func(old) > 0.0
        and context.wall_b.pla.func(old) > 0.0
    ):
        if diagnostics is not None:
            diagnostics["not_front"] = diagnostics.get("not_front", 0) + 1
        return None
    # B acts after the two-row controller delay. Keep the last full stick held
    # through both movement updates used by the release/push timeline.
    follow = node.rows[-1] if node.rows else prefix_rows[-1]
    held = node.previous
    # The B edge changes the carried upper pose one execute before freeGrabItem
    # clears grab_actor. The detach execute draws Link's REST upper body and
    # generates m_cc_move; Link consumes that correction on the NEXT execute.
    # Therefore `node` is the release/collision pose and `next_move` supplies
    # only the movement applied before the pending Co correction is consumed.
    if next_move is None:
        next_move = _step(node, follow)
    object_type = getattr(node.state, "_drop_object_type", "pot_small")
    pose = dr.decomp_moving_b_drop_pose(
        held.pos,
        (node.state.pos_x, node.state.pos_y, node.state.pos_z),
        held.facing,
        _lower_pose(held), _lower_pose(node), held.upper.frame,
        object_type, lower_anims=lower_anims, upper_anims=upper_anims,
        skeleton=skeleton, held_lean=held.lean,
        collision_lean=node.state._draw_lean,
        collision_facing=node.state.facing,
        held_body_lean=held.body_lean,
        collision_body_lean=_signed_s16(node.state.m351C) >> 1,
    )
    motion = (
        next_move.state.pos_x - node.state.pos_x,
        next_move.state.pos_y - node.state.pos_y,
        next_move.state.pos_z - node.state.pos_z,
    )
    held_prop = pose.held_prop_pos
    link_co_center = pose.link_co_center
    link_co_radius = pose.link_co_radius
    link_co_height = pose.link_co_height
    result = dr.b_drop_collision_step(
        old, link_co_center, link_co_height, held_prop,
        object_type, context.walls, link_co_radius=link_co_radius,
        link_motion=motion,
    )
    crosses, _stable = _candidate_crosses(context, old, result)
    raw_depth = min(-context.wall_a.pla.func(result.link_raw),
                    -context.wall_b.pla.func(result.link_raw))
    resolved_depth = min(-context.wall_a.pla.func(result.link_after_bg),
                         -context.wall_b.pla.func(result.link_after_bg))
    if diagnostics is not None:
        if raw_depth > diagnostics.get("best_raw_depth", -math.inf):
            diagnostics["best_raw_pos"] = result.link_raw
            diagnostics["best_raw_planes"] = (
                context.wall_a.pla.func(result.link_raw),
                context.wall_b.pla.func(result.link_raw),
            )
            candidate_rows = [dict(row) for row in prefix_rows + node.rows + [follow]]
            for index, replacement in node.prefix_patch.items():
                candidate_rows[index] = dict(replacement)
            candidate_b = len(prefix_rows) + len(node.rows) - 3
            candidate_rows[candidate_b]["buttons"] = (
                candidate_rows[candidate_b].get("buttons", 0) | BUTTON_B
            )
            diagnostics["best_candidate"] = {
                "depth": len(node.rows),
                "b_index": candidate_b,
                "old": old,
                "facing": node.state.facing,
                "speed": node.state.speedF,
                "held_prop": held_prop,
                "link_co": link_co_center,
                "raw": result.link_raw,
                "resolved": result.link_after_bg,
                "prop_wall": bool(result.prop_bg_info["wall_hit"]),
                "link_wall": bool(result.link_bg_info["wall_hit"]),
                "crosses": bool(crosses),
                "rows": candidate_rows,
            }
        diagnostics["best_raw_depth"] = max(
            diagnostics.get("best_raw_depth", -math.inf), raw_depth
        )
        diagnostics["best_resolved_depth"] = max(
            diagnostics.get("best_resolved_depth", -math.inf), resolved_depth
        )
        if result.prop_bg_info["wall_hit"]:
            diagnostics["prop_wall"] = diagnostics.get("prop_wall", 0) + 1
        if result.link_bg_info["wall_hit"]:
            diagnostics["link_wall"] = diagnostics.get("link_wall", 0) + 1
        if raw_depth <= 0.0:
            diagnostics["raw_not_across"] = diagnostics.get("raw_not_across", 0) + 1
        if raw_depth > 0.0 and resolved_depth <= 0.0:
            diagnostics["resolved_out"] = diagnostics.get("resolved_out", 0) + 1
    if not crosses or result.prop_bg_info["wall_hit"]:
        return None
    resolved = result.link_after_bg
    retained = min(
        -context.wall_a.pla.func(resolved),
        -context.wall_b.pla.func(resolved),
    )
    rows = [dict(row) for row in prefix_rows + node.rows + [follow]]
    for index, replacement in node.prefix_patch.items():
        rows[index] = dict(replacement)
    # At the state after N raw rows, row N-2 and N-1 remain buffered; row N-3 acted this frame.
    b_index = len(prefix_rows) + len(node.rows) - 3
    rows[b_index]["buttons"] = rows[b_index].get("buttons", 0) | BUTTON_B
    return Hit(
        depth=len(node.rows), b_index=b_index, old=old,
        raw=result.link_raw, resolved=result.link_after_bg,
        retained_depth=retained, facing=node.state.facing,
        speed=node.state.speedF, rows=rows,
    )


def _exact_release_probe(seed):
    """Extract a deterministic release trace for model diagnostics only."""
    probe = seed.get("release_probe")
    if not probe:
        return None
    frames = probe.get("frames", [])
    for index, frame in enumerate(frames):
        snap = frame["snapshot"]
        if snap.get("grab_actor", 0) == 0 and index:
            previous = frames[index - 1]
            held_prop = previous.get("released_prop_pos")
            center = snap.get("link_co_center")
            if held_prop is None or center is None:
                return None
            return {
                "release_row": frame["row"],
                "held_prop_pos": tuple(held_prop),
                # The sampled cylinder has already received mCcMove. Recover
                # the pre-push center only for comparison with the FK model.
                "link_co_center": tuple(
                    fp.fsubs(center[axis], snap.get("cc_move", (0.0, 0.0, 0.0))[axis])
                    for axis in range(3)
                ),
                "link_co_radius": snap["link_co_radius"],
                "link_co_height": snap["link_co_height"],
                "captured_cc_move": tuple(snap.get("cc_move", (0.0, 0.0, 0.0))),
            }
    return None


def _constant_bearing_search(start, context, prefix, lower_anims, upper_anims,
                             skeleton, max_depth, release_probe, log,
                             minimum_depth=0):
    """Search the low-dimensional fastest route family before any beam.

    A held full-stick bearing fixes the entire turn/acceleration trajectory.
    Sweeping the 512 useful BAM cells is cheap and covers the natural
    no-slowdown approach requested by the moving-drop finder.
    """
    pending_index = len(prefix) - 2
    pending_next_index = len(prefix) - 1
    hits = []
    near = []
    seen = set()
    for bearing in range(0, 0x10000, 128):
        sx, sy = dtm_stick(stick_for_bearing(bearing, start.state.csangle, 1.0))
        if (sx, sy) in seen:
            continue
        seen.add((sx, sy))
        row = {
            "stickX": sx, "stickY": sy, "substickX": 128, "substickY": 128,
            "buttons": 0, "triggerL": 0, "triggerR": 0,
        }
        state = start.state.clone()
        state._inbuf[0] = _controller_tuple(row)
        state._inbuf[1] = _controller_tuple(row)
        node = Node(
            state, start.lower.clone(), start.upper.clone(), start.previous,
            start.held_prop, [], {
                pending_index: dict(row), pending_next_index: dict(row),
            },
        )
        for depth in range(max_depth + 1):
            diagnostics = {}
            hit = _try_drop(
                node, context, prefix, lower_anims, upper_anims, skeleton,
                diagnostics=diagnostics, release_probe=release_probe,
                minimum_depth=minimum_depth,
            )
            if hit is not None:
                hits.append(hit)
            candidate = diagnostics.get("best_candidate")
            if candidate is not None:
                candidate["bearing"] = bearing
                candidate["wall_planes"] = diagnostics["best_raw_planes"]
                candidate["raw_depth"] = diagnostics["best_raw_depth"]
                near.append(candidate)
            if depth != max_depth:
                node = _step(node, row)
                if node.state.state != MOVE or node.state.wall_hit:
                    break
    near.sort(key=lambda item: _moving_candidate_rank(item, context) + (
        item["depth"],
    ))
    log(
        "directed offline sweep: %d full-stick bearings, %d exact hit(s); best %d route(s) "
        "retained for turn refinement (raw-to-seam %.6f)"
        % (len(seen), len(hits), min(len(near), 16),
           math.hypot(near[0]["raw"][0] - context.seam_target[0],
                      near[0]["raw"][2] - context.seam_target[2]) if near else math.inf)
    )
    return hits, _depth_diverse(near)


def _two_bearing_search(start, context, prefix, lower_anims, upper_anims,
                        skeleton, max_depth, release_probe, log,
                        minimum_depth=0):
    """Screen one-turn full-speed routes without a combinatorial input beam."""
    pending_index = len(prefix) - 2
    pending_next_index = len(prefix) - 1
    near = []
    tested = 0
    for first_bearing in range(0, 0x10000, 2048):
        first_x, first_y = dtm_stick(
            stick_for_bearing(first_bearing, start.state.csangle, 1.0)
        )
        first = {
            "stickX": first_x, "stickY": first_y,
            "substickX": 128, "substickY": 128,
            "buttons": 0, "triggerL": 0, "triggerR": 0,
        }
        state = start.state.clone()
        state._inbuf[0] = _controller_tuple(first)
        state._inbuf[1] = _controller_tuple(first)
        first_node = Node(
            state, start.lower.clone(), start.upper.clone(), start.previous,
            start.held_prop, [], {
                pending_index: dict(first), pending_next_index: dict(first),
            },
        )
        for switch_depth in range(max_depth + 1):
            if first_node.state.state != MOVE or first_node.state.wall_hit:
                break
            direct = world_angle_s16(
                context.seam_target[0] - first_node.state.pos_x,
                context.seam_target[2] - first_node.state.pos_z,
            )
            seen = set()
            for offset in range(-8192, 8193, 1024):
                second_bearing = (direct + offset) & 0xFFFF
                sx, sy = dtm_stick(
                    stick_for_bearing(second_bearing, first_node.state.csangle, 1.0)
                )
                if (sx, sy) in seen:
                    continue
                seen.add((sx, sy))
                second = {
                    "stickX": sx, "stickY": sy,
                    "substickX": 128, "substickY": 128,
                    "buttons": 0, "triggerL": 0, "triggerR": 0,
                }
                node = first_node
                for _depth in range(switch_depth, max_depth):
                    node = _step(node, second)
                    if node.state.state != MOVE or node.state.wall_hit:
                        break
                    diagnostics = {}
                    _try_drop(
                        node, context, prefix, lower_anims, upper_anims, skeleton,
                        diagnostics=diagnostics, release_probe=release_probe,
                        minimum_depth=minimum_depth,
                    )
                    tested += 1
                    candidate = diagnostics.get("best_candidate")
                    if candidate is not None:
                        candidate["wall_planes"] = diagnostics["best_raw_planes"]
                        candidate["raw_depth"] = diagnostics["best_raw_depth"]
                        near.append(candidate)
            if switch_depth != max_depth:
                first_node = _step(first_node, first)
    near.sort(key=lambda item: _moving_candidate_rank(item, context) + (
        item["depth"],
    ))
    best_distance = (
        math.hypot(near[0]["raw"][0] - context.seam_target[0],
                   near[0]["raw"][2] - context.seam_target[2])
        if near else math.inf
    )
    log(
        "two-bearing screen: %d release states; best %d curved routes retained "
        "(raw-to-seam %.6f)"
        % (tested, min(16, len(near)), best_distance)
    )
    return _depth_diverse(near)


def _pending_pair_search(start, context, prefix, lower_anims, upper_anims,
                         skeleton, release_probe, log, minimum_depth=0,
                         shortlist_size=4000):
    """Search the two raw controller rows still buffered at a captured state.

    These rows are independent, but ordinary forward beams do not see the
    second row until depth two and can collapse both into one approach family.
    Movement-only screening is cheap; held-item FK and collision run only for
    the seam-local shortlist.
    """
    pending_index = len(prefix) - 2
    pending_next_index = len(prefix) - 1
    rows = _movement_rows(
        start.state, context.seam_target, spread=0x8000, step=256,
    )
    screened = []
    screened_count = 0
    serial = 0
    for first in rows:
        state = start.state.clone()
        state._inbuf[0] = _controller_tuple(first)
        state._inbuf[1] = _controller_tuple(first)
        initial = Node(
            state, start.lower.clone(), start.upper.clone(), start.previous,
            start.held_prop, [], {
                pending_index: dict(first), pending_next_index: dict(first),
            },
        )
        after_first = _step(initial, first)
        if after_first.state.state != MOVE or after_first.state.wall_hit:
            continue
        for second in rows:
            child_state = after_first.state.clone()
            child_state._inbuf[0] = _controller_tuple(second)
            child = Node(
                child_state, after_first.lower.clone(), after_first.upper.clone(),
                after_first.previous, after_first.held_prop,
                list(after_first.rows), {
                    pending_index: dict(first), pending_next_index: dict(second),
                },
            )
            child = _step(child, second)
            if child.state.state != MOVE or child.state.wall_hit:
                continue
            old = (child.state.pos_x, child.state.pos_y, child.state.pos_z)
            if not (
                context.wall_a.pla.func(old) > 0.0
                and context.wall_b.pla.func(old) > 0.0
            ):
                continue
            distance = math.hypot(
                old[0] - context.seam_target[0],
                old[2] - context.seam_target[2],
            )
            # Small-pot Co correction is roughly 40-54 units. Prefer states in
            # that annulus, but retain a broad enough band for moving Link.
            if 28.0 <= distance <= 78.0:
                screened_count += 1
                serial += 1
                entry = (-abs(distance - 50.0), serial, child)
                if len(screened) < shortlist_size:
                    heapq.heappush(screened, entry)
                elif entry[0] > screened[0][0]:
                    heapq.heapreplace(screened, entry)

    shortlist = [(-score, node) for score, _serial, node in screened]
    shortlist.sort(key=lambda item: item[0])
    hits = []
    near = []
    for _score, node in shortlist:
        diagnostics = {}
        hit = _try_drop(
            node, context, prefix, lower_anims, upper_anims, skeleton,
            diagnostics=diagnostics, release_probe=release_probe,
            minimum_depth=minimum_depth,
        )
        if hit is not None:
            hits.append(hit)
        candidate = diagnostics.get("best_candidate")
        if candidate is not None:
            candidate["wall_planes"] = diagnostics["best_raw_planes"]
            candidate["raw_depth"] = diagnostics["best_raw_depth"]
            near.append(candidate)
    near.sort(key=lambda item: _moving_candidate_rank(item, context))
    log(
        "two-pending-row screen: %d movement pairs, %d exact release evaluations, "
        "%d hit(s), best raw-to-seam %.6f"
        % (screened_count, len(shortlist), len(hits),
           math.hypot(near[0]["raw"][0] - context.seam_target[0],
                      near[0]["raw"][2] - context.seam_target[2]) if near else math.inf)
    )
    return hits, near[:32]


def _refine_near_route(start, seed_candidate, context, prefix, lower_anims,
                       upper_anims, skeleton, release_probe, log,
                       minimum_depth=0, checkpoint_path=None):
    """Locally refine controller bytes around a seam-adjacent route.

    The coarse search only needs to enter the correct corner neighborhood.
    Float-perfect seam alignment is then a small discrete optimization over
    the pending row and the route's delivered rows, rather than another global
    trajectory beam.
    """
    source_rows = seed_candidate["rows"]
    depth = int(seed_candidate["depth"])
    if "b_index" in seed_candidate:
        reopened_depth = int(seed_candidate["b_index"]) - len(prefix) + 3
        delivered_prefix = max(0, len(prefix) - 2)
        if (
            reopened_depth >= 1
            and len(source_rows) >= len(prefix) + reopened_depth
            and source_rows[:delivered_prefix] == prefix[:delivered_prefix]
        ):
            if reopened_depth != depth:
                log(
                    "reopening depth-%d route as depth %d from the earlier "
                    "compatible anchor" % (depth, reopened_depth)
                )
            depth = reopened_depth
    controls = [
        dict(source_rows[len(prefix) - 2]),
        dict(source_rows[len(prefix) - 1]),
    ]
    controls.extend(dict(row) for row in source_rows[len(prefix):len(prefix) + depth])
    cache = {}
    raw_seed = seed_candidate.get("raw")
    raw_seed_distance = (
        math.hypot(raw_seed[0] - context.seam_target[0],
                   raw_seed[2] - context.seam_target[2])
        if raw_seed is not None else math.inf
    )
    dust_center = (
        (raw_seed[0], raw_seed[2])
        if raw_seed_distance < 0.05
        else (context.seam_target[0], context.seam_target[2])
    )
    # Saved near-candidate diagnostics may predate the final row edits. Use
    # their raw endpoint only as a bootstrap; replay the rows below before
    # selecting the authoritative f32 target for this route.
    dust_x, dust_z = dust_center
    refine_axes = ("stickX", "stickY", "substickX", "substickY")
    log(
        "replaying depth-%d route before selecting exact f32 dust near "
        "(%.9f, %.9f)"
        % (depth, dust_x, dust_z)
    )

    def seam_geometry(candidate):
        old_x, old_z = candidate["old"][0], candidate["old"][2]
        raw_x, raw_z = candidate["raw"][0], candidate["raw"][2]
        vx, vz = raw_x - old_x, raw_z - old_z
        wx = context.seam_target[0] - old_x
        wz = context.seam_target[2] - old_z
        length_sq = vx * vx + vz * vz
        if length_sq <= 0.0:
            return math.inf, math.inf, math.inf, math.inf
        length = math.sqrt(length_sq)
        signed_line = (vx * wz - vz * wx) / length
        along = (wx * vx + wz * vz) / length_sq
        signed_shortfall = (along - 1.0) * length
        projection_penalty = max(0.0, -along, along - 1.0) * length
        return signed_line, signed_shortfall, abs(signed_line), projection_penalty

    def select_geometry_beam(results, width=32):
        """Retain complementary route families across the discrete controller map."""
        usable = [item for item in results if item[2] is not None]
        if not usable:
            return []

        def metrics(item):
            signed_line, shortfall, line_offset, projection = seam_geometry(item[2])
            return signed_line, shortfall, line_offset, projection

        orderings = (
            sorted(usable, key=lambda item: item[0]),
            sorted(
                usable,
                key=lambda item: metrics(item)[2] + max(0.0, metrics(item)[1]),
            ),
            sorted(usable, key=lambda item: metrics(item)[2]),
            sorted(usable, key=lambda item: metrics(item)[1]),
        )
        selected = []
        seen = set()
        cursors = [0] * len(orderings)
        while len(selected) < width:
            added = False
            for ordering_index, ordering in enumerate(orderings):
                while cursors[ordering_index] < len(ordering):
                    item = ordering[cursors[ordering_index]]
                    cursors[ordering_index] += 1
                    route_key = tuple(
                        (row["stickX"], row["stickY"],
                         row.get("substickX", 128))
                        for row in item[3]
                    )
                    if route_key not in seen:
                        seen.add(route_key)
                        selected.append(item)
                        added = True
                        break
                if len(selected) == width:
                    break
            if not added:
                break
        return selected

    def evaluate(items):
        key = tuple(
            (row["stickX"], row["stickY"], row.get("substickX", 128),
             row.get("substickY", 128))
            for row in items
        )
        if key in cache:
            return cache[key]
        state = start.state.clone()
        state._inbuf[0] = _controller_tuple(items[0])
        state._inbuf[1] = _controller_tuple(items[1])
        node = Node(
            state, start.lower.clone(), start.upper.clone(), start.previous,
            start.held_prop, [], {
                len(prefix) - 2: dict(items[0]),
                len(prefix) - 1: dict(items[1]),
            },
        )
        for row in items[2:]:
            node = _step(node, row)
        diagnostics = {}
        hit = _try_drop(
            node, context, prefix, lower_anims, upper_anims, skeleton,
            diagnostics=diagnostics, release_probe=release_probe,
            minimum_depth=minimum_depth,
        )
        candidate = diagnostics.get("best_candidate")
        if candidate is not None:
            candidate["wall_planes"] = diagnostics["best_raw_planes"]
            candidate["raw_depth"] = diagnostics["best_raw_depth"]
        if hit is not None:
            score = (-1, -hit.retained_depth, hit.b_index)
        elif candidate is None:
            score = (2, math.inf, math.inf)
        else:
            plane_a, plane_b = candidate["wall_planes"]
            violation = math.hypot(max(0.0, plane_a), max(0.0, plane_b))
            local_dust = _candidate_local_dust(candidate, context)
            dust_distance = (
                candidate["dust_distance"]
                if local_dust is not None else math.inf
            )
            _signed_line, signed_shortfall, line_offset, projection_penalty = (
                seam_geometry(candidate)
            )
            score = (
                1 if candidate["prop_wall"] else 0,
                0 if signed_shortfall <= 0.0 else 1,
                0 if local_dust is not None else 1,
                dust_distance,
                projection_penalty,
                line_offset,
                violation,
                0 if candidate.get("crosses") else 1,
                candidate["depth"],
            )
        result = (score, hit, candidate, [dict(row) for row in items])
        cache[key] = result
        return result

    def checkpoint(result, stage):
        if checkpoint_path is None or result[2] is None:
            return
        payload = dict(result[2])
        # The candidate already owns the complete prefix + refined route.
        # Keep the optimizer controls separately; replacing ``rows`` here made
        # resumable checkpoints contain only the short mutable suffix.
        payload["refine_controls"] = [dict(row) for row in result[3]]
        payload["refine_stage"] = stage
        path = Path(checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="ascii")

    def exact_hamming_search(result, first_order, last_order):
        """Exhaust tiny byte edits when the authoritative endpoint is nearby."""
        if result[2] is None:
            return result, []

        def candidate_signature(candidate):
            if candidate is None:
                return None
            return (
                tuple(candidate["old"]), tuple(candidate["raw"]),
                int(candidate["facing"]), float(candidate["speed"]),
                tuple(candidate["held_prop"]), tuple(candidate["link_co"]),
            )

        route = result[3]
        delivered_rows = min(depth + 1, len(route))
        variables = [
            (index, axis)
            for index in range(delivered_rows)
            for axis in refine_axes
        ]
        for order in range(first_order, last_order + 1):
            best = result
            tested = 0
            base_signature = candidate_signature(result[2])
            active_variables = set()
            for selected in itertools.combinations(variables, order):
                for signs in itertools.product((-1, 1), repeat=order):
                    neighbor = [dict(item) for item in route]
                    valid = True
                    for (index, axis), delta in zip(selected, signs):
                        value = neighbor[index][axis] + delta
                        if not 1 <= value <= 254:
                            valid = False
                            break
                        neighbor[index][axis] = value
                    if not valid:
                        continue
                    trial = evaluate(neighbor)
                    tested += 1
                    if (
                        order == 1
                        and candidate_signature(trial[2]) != base_signature
                    ):
                        active_variables.add(selected[0])
                    if trial[1] is not None:
                        log(
                            "exact byte-combination search found a hit at order %d "
                            "after %d streams" % (order, len(cache))
                        )
                        return trial, [trial[1]]
                    if trial[0] < best[0]:
                        best = trial
            if best[0] < result[0]:
                result = best
                route = result[3]
            distance = math.hypot(
                result[2]["raw"][0] - dust_x,
                result[2]["raw"][2] - dust_z,
            )
            log(
                "byte-combination order %d: raw-to-dust=%.9f, tested=%d"
                % (order, distance, tested)
            )
            if order == 1 and last_order > 1:
                variables = [
                    variable for variable in variables
                    if variable in active_variables
                ]
                log(
                    "exact-near sensitivity retained %d/%d controller bytes"
                    % (len(variables), delivered_rows * len(refine_axes))
                )
        return result, []

    def retarget_nearest(result):
        """Follow the exact f32 gap as trajectory edits move Link's old position."""
        nonlocal dust_x, dust_z
        candidate = result[2]
        if candidate is None:
            return result
        target = candidate.get("dust_target")
        if target is None:
            target = _candidate_local_dust(
                candidate, context, box_ulps=300, max_calls=50000,
            )
        if target is None:
            return result
        new_x, new_z = target
        if (new_x, new_z) == (dust_x, dust_z):
            return result
        dust_x, dust_z = new_x, new_z
        route = result[3]
        cache.clear()
        result = evaluate(route)
        log("retargeted moving f32 dust=(%.9f, %.9f)" % (dust_x, dust_z))
        return result

    current = evaluate(controls)
    if current[1] is not None:
        return [current[1]]
    current = retarget_nearest(current)

    # Invert the short approach separately from the drop.  An aligned saved
    # route gives both the required displacement and release facing; translate
    # its old position forward by the measured shortfall, then solve only the
    # seven-frame movement trajectory to that release state.
    if current[2] is not None and depth >= 2:
        seed_line, seed_shortfall, seed_offset, _seed_projection = seam_geometry(
            current[2]
        )
        if seed_offset < 0.05 and seed_shortfall > 0.0:
            seed_old = current[2]["old"]
            seed_raw = current[2]["raw"]
            push_x = seed_raw[0] - seed_old[0]
            push_z = seed_raw[2] - seed_old[2]
            push_length = math.hypot(push_x, push_z)
            target_release = (
                seed_old[0] + (seed_shortfall + 0.05) * push_x / push_length,
                seed_old[1],
                seed_old[2] + (seed_shortfall + 0.05) * push_z / push_length,
            )
            target_facing = int(current[2]["facing"])
            pending_index = len(prefix) - 2
            pending_next_index = len(prefix) - 1
            pending_rows = _movement_rows(
                start.state, target_release, spread=2048, step=128,
            )
            approach_frontier = []
            for pending in pending_rows:
                state = start.state.clone()
                state._inbuf[0] = _controller_tuple(pending)
                state._inbuf[1] = _controller_tuple(pending)
                approach_frontier.append(Node(
                    state, start.lower.clone(), start.upper.clone(),
                    start.previous, start.held_prop, [], {
                        pending_index: dict(pending),
                        pending_next_index: dict(pending),
                    },
                ))

            def approach_rank(node, step_depth):
                distance = math.hypot(
                    node.state.pos_x - target_release[0],
                    node.state.pos_z - target_release[2],
                )
                facing_error = abs(
                    ((node.state.facing - target_facing + 32768) & 0xFFFF)
                    - 32768
                )
                facing_weight = 12.0 * (step_depth / depth) ** 3
                return distance + facing_weight * facing_error / 65536.0

            for step_depth in range(1, depth + 1):
                expanded = []
                for node in approach_frontier:
                    if node.state.wall_hit:
                        continue
                    for row in _movement_rows(
                        node.state, target_release, spread=1536, step=128,
                    ):
                        child = _step(node, row)
                        if child.state.state == MOVE and child.state.speedF > 0.0:
                            expanded.append(child)
                expanded.sort(key=lambda node: approach_rank(node, step_depth))
                unique = {}
                for node in expanded:
                    key = (
                        round(node.state.pos_x, 5), round(node.state.pos_z, 5),
                        node.state.facing, node.state.travel,
                        tuple(
                            _controller_tuple(row)[:2] for row in node.rows[-2:]
                        ),
                    )
                    unique.setdefault(key, node)
                    if len(unique) >= 64:
                        break
                approach_frontier = list(unique.values())
                if approach_frontier:
                    best_node = approach_frontier[0]
                    log(
                        "target approach depth %d: pos=(%.6f, %.6f), "
                        "facing=%d, distance=%.6f, states=%d"
                        % (
                            step_depth, best_node.state.pos_x,
                            best_node.state.pos_z, best_node.state.facing,
                            math.hypot(
                                best_node.state.pos_x - target_release[0],
                                best_node.state.pos_z - target_release[2],
                            ), len(approach_frontier),
                        )
                    )
                if not approach_frontier:
                    break

            approach_results = []
            for node in approach_frontier:
                route = [
                    dict(node.prefix_patch[pending_index]),
                    dict(node.prefix_patch[pending_next_index]),
                ] + [dict(row) for row in node.rows]
                approach_results.append(evaluate(route))
            exact = [item[1] for item in approach_results if item[1] is not None]
            if exact:
                log(
                    "targeted release approach found %d exact hit(s) after %d streams"
                    % (len(exact), len(cache))
                )
                return exact
            usable = [item for item in approach_results if item[2] is not None]
            if usable:
                def approach_geometry_score(item):
                    _line, shortfall, offset, _projection = seam_geometry(item[2])
                    return offset + max(0.0, shortfall)

                best_approach = min(usable, key=approach_geometry_score)
                if approach_geometry_score(best_approach) < approach_geometry_score(current):
                    current = retarget_nearest(best_approach)
                line, shortfall, _offset, _projection = seam_geometry(best_approach[2])
                log(
                    "targeted release approach: old=(%.9f, %.9f), facing=%d, "
                    "line=%+.9f, shortfall=%+.9f, candidates=%d"
                    % (
                        best_approach[2]["old"][0],
                        best_approach[2]["old"][2],
                        best_approach[2]["facing"], line, shortfall,
                        len(approach_results),
                    )
                )
            else:
                log(
                    "targeted release approach produced no valid release "
                    "candidate from %d final state(s)" % len(approach_results)
                )

    for step in (32, 16, 8, 4, 2, 1):
        for _pass in range(4):
            trials = [current]
            route = current[3]
            for index, row in enumerate(route):
                for axis in refine_axes:
                    for delta in (-step, step):
                        value = max(1, min(254, row[axis] + delta))
                        if value == row[axis]:
                            continue
                        neighbor = [dict(item) for item in route]
                        neighbor[index][axis] = value
                        trials.append(evaluate(neighbor))
            trials.sort(key=lambda item: item[0])
            exact = [item[1] for item in trials if item[1] is not None]
            if exact:
                log(
                    "adaptive route refinement found %d exact hit(s) after %d streams"
                    % (len(exact), len(cache))
                )
                return exact
            if trials[0][0] >= current[0]:
                break
            current = retarget_nearest(trials[0])
        if current[2] is not None:
            distance = math.hypot(current[2]["raw"][0] - dust_x,
                                  current[2]["raw"][2] - dust_z)
            signed_line, shortfall, _offset, _projection = seam_geometry(current[2])
            log(
                "adaptive refinement step %d: raw-to-dust=%.9f, "
                "line=%+.9f, shortfall=%+.9f, streams=%d"
                % (step, distance, signed_line, shortfall, len(cache))
            )
            checkpoint(current, "adaptive-step-%d" % step)

    if current[2] is not None:
        distance = math.hypot(
            current[2]["raw"][0] - dust_x,
            current[2]["raw"][2] - dust_z,
        )
        if distance < 0.001:
            current, exact = exact_hamming_search(current, 1, 3)
            if exact:
                return exact

    # If the push is already aimed at the seam but ends short, preserve the
    # release/drop rows and translate the approach with only the early walking
    # inputs.  This directly inverts the cheap movement simulation instead of
    # re-searching facing and camera families that are already correct.
    if current[2] is not None:
        delivered_rows = min(depth + 1, len(current[3]))
        translation_rows = max(0, delivered_rows - 3)

        def translation_score(result):
            candidate = result[2]
            if candidate is None or candidate.get("prop_wall"):
                return math.inf
            _signed_line, shortfall, line_offset, _projection = seam_geometry(
                candidate
            )
            return line_offset + max(0.0, shortfall)

        _signed_line, shortfall, line_offset, _projection = seam_geometry(current[2])
        if translation_rows and line_offset < 0.05 and shortfall > 0.0:
            for iteration in range(12):
                candidate = current[2]
                signed_line, shortfall, line_offset, _projection = seam_geometry(
                    candidate
                )
                if shortfall <= 0.0 or line_offset >= 0.5:
                    break
                old_x, old_z = candidate["old"][0], candidate["old"][2]
                vx = candidate["raw"][0] - old_x
                vz = candidate["raw"][2] - old_z
                length = math.hypot(vx, vz)
                if length <= 0.0:
                    break
                target_old_x = old_x + (shortfall + 0.05) * vx / length
                target_old_z = old_z + (shortfall + 0.05) * vz / length
                route = current[3]
                derivatives = []
                variables = []
                for index, row in enumerate(route[:translation_rows]):
                    for axis in ("stickX", "stickY"):
                        samples = []
                        for delta in (-4, 4):
                            neighbor = [dict(item) for item in route]
                            neighbor[index][axis] = max(
                                1, min(254, row[axis] + delta)
                            )
                            samples.append((neighbor[index][axis], evaluate(neighbor)))
                        span = samples[1][0] - samples[0][0]
                        if (
                            span == 0 or samples[0][1][2] is None
                            or samples[1][1][2] is None
                        ):
                            derivatives.append((0.0, 0.0))
                        else:
                            lo_old = samples[0][1][2]["old"]
                            hi_old = samples[1][1][2]["old"]
                            derivatives.append((
                                (hi_old[0] - lo_old[0]) / span,
                                (hi_old[2] - lo_old[2]) / span,
                            ))
                        variables.append((index, axis))
                xx = sum(dx * dx for dx, _dz in derivatives)
                xz = sum(dx * dz for dx, dz in derivatives)
                zz = sum(dz * dz for _dx, dz in derivatives)
                determinant = xx * zz - xz * xz
                if abs(determinant) < 1e-12:
                    break
                residual_x = target_old_x - old_x
                residual_z = target_old_z - old_z
                inv_x = (zz * residual_x - xz * residual_z) / determinant
                inv_z = (xx * residual_z - xz * residual_x) / determinant
                correction = [
                    dx * inv_x + dz * inv_z for dx, dz in derivatives
                ]
                proposals = [current]
                for scale in (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.25):
                    neighbor = [dict(item) for item in route]
                    for (index, axis), delta in zip(variables, correction):
                        neighbor[index][axis] = max(
                            1,
                            min(
                                254,
                                neighbor[index][axis] + round(delta * scale),
                            ),
                        )
                    proposals.append(evaluate(neighbor))
                exact = [item[1] for item in proposals if item[1] is not None]
                if exact:
                    log(
                        "release-translation inverse found %d exact hit(s) "
                        "after %d streams"
                        % (len(exact), len(cache))
                    )
                    return exact
                best = min(proposals, key=translation_score)
                if translation_score(best) >= translation_score(current):
                    break
                current = retarget_nearest(best)
                signed_line, shortfall, _offset, _projection = seam_geometry(
                    current[2]
                )
                log(
                    "release translation %d: line=%+.9f, shortfall=%+.9f, "
                    "old=(%.9f, %.9f), streams=%d"
                    % (
                        iteration + 1, signed_line, shortfall,
                        current[2]["old"][0], current[2]["old"][2], len(cache),
                    )
                )

    # Camera input is quantized across a deadzone, so its local derivative is
    # discontinuous.  Enumerate the nearby C-stick states for rows that can
    # affect movement before release, then compensate their heading changes
    # with a narrow main-stick beam.  This is a small discrete inverse search,
    # not a live Dolphin brute force.
    delivered_rows = min(depth + 1, len(current[3]))
    camera_rows = max(0, delivered_rows - 2)
    if camera_rows:
        route = current[3]
        c_options = []
        for row in route[:camera_rows]:
            center = row.get("substickX", 128)
            c_options.append(tuple(sorted({
                max(1, center - 32), center, min(254, center + 32), 128,
            })))
        camera_trials = [current]
        for values in itertools.product(*c_options):
            neighbor = [dict(item) for item in route]
            for index, value in enumerate(values):
                neighbor[index]["substickX"] = value
            camera_trials.append(evaluate(neighbor))
        camera_trials.sort(key=lambda item: item[0])
        exact = [item[1] for item in camera_trials if item[1] is not None]
        if exact:
            log(
                "C-stick lattice found %d exact hit(s) after %d streams"
                % (len(exact), len(cache))
            )
            return exact

        beam = select_geometry_beam(camera_trials, 32)
        wide_c_values = tuple(sorted(set(range(1, 255, 8)) | {128, 254}))
        for c_pass in range(2):
            wide_trials = list(beam)
            for seed_result in beam:
                seed_route = seed_result[3]
                for index in range(camera_rows):
                    current_c = seed_route[index].get("substickX", 128)
                    for value in wide_c_values:
                        if value == current_c:
                            continue
                        neighbor = [dict(item) for item in seed_route]
                        neighbor[index]["substickX"] = value
                        wide_trials.append(evaluate(neighbor))
            wide_trials.sort(key=lambda item: item[0])
            exact = [item[1] for item in wide_trials if item[1] is not None]
            if exact:
                log(
                    "wide C-stick beam found %d exact hit(s) on pass %d "
                    "after %d streams"
                    % (len(exact), c_pass + 1, len(cache))
                )
                return exact
            beam = select_geometry_beam(wide_trials, 32)
            if beam and beam[0][2] is not None:
                signed_line, shortfall, _offset, _projection = seam_geometry(
                    beam[0][2]
                )
                log(
                    "wide C-stick pass %d: line=%+.9f, shortfall=%+.9f, "
                    "streams=%d"
                    % (c_pass + 1, signed_line, shortfall, len(cache))
                )
                checkpoint(beam[0], "wide-c-pass-%d" % (c_pass + 1))

        for step in (8, 4, 2, 1):
            for _pass in range(2):
                main_trials = list(beam)
                for seed_result in beam:
                    seed_route = seed_result[3]
                    for index, row in enumerate(seed_route[:delivered_rows]):
                        for axis in ("stickX", "stickY"):
                            for delta in (-step, step):
                                value = max(1, min(254, row[axis] + delta))
                                if value == row[axis]:
                                    continue
                                neighbor = [dict(item) for item in seed_route]
                                neighbor[index][axis] = value
                                main_trials.append(evaluate(neighbor))
                main_trials.sort(key=lambda item: item[0])
                exact = [item[1] for item in main_trials if item[1] is not None]
                if exact:
                    log(
                        "C/main compensation beam found %d exact hit(s) "
                        "at step %d after %d streams"
                        % (len(exact), step, len(cache))
                    )
                    return exact
                beam = select_geometry_beam(main_trials, 32)
            if beam and beam[0][2] is not None:
                signed_line, shortfall, _offset, _projection = seam_geometry(
                    beam[0][2]
                )
                log(
                    "C/main compensation step %d: line=%+.9f, "
                    "shortfall=%+.9f, streams=%d"
                    % (step, signed_line, shortfall, len(cache))
                )
                checkpoint(beam[0], "c-main-step-%d" % step)
        if beam and beam[0][0] < current[0]:
            current = retarget_nearest(beam[0])

    if depth == 1:
        # Only pending raw row N-2 has reached movement on a depth-1 release.
        # Search its two calibrated controller bytes jointly; coordinate
        # descent can miss a diagonal cell across stick-angle quantization.
        for grid_step, radius in ((4, 64), (1, 8)):
            route = current[3]
            center_x = route[0]["stickX"]
            center_y = route[0]["stickY"]
            trials = []
            for stick_x in range(
                max(1, center_x - radius), min(254, center_x + radius) + 1,
                grid_step,
            ):
                for stick_y in range(
                    max(1, center_y - radius), min(254, center_y + radius) + 1,
                    grid_step,
                ):
                    neighbor = [dict(item) for item in route]
                    neighbor[0]["stickX"] = stick_x
                    neighbor[0]["stickY"] = stick_y
                    trials.append(evaluate(neighbor))
            trials.sort(key=lambda item: item[0])
            exact = [item[1] for item in trials if item[1] is not None]
            if exact:
                log(
                    "pending-B lattice found %d exact hit(s) after %d streams"
                    % (len(exact), len(cache))
                )
                return exact
            if trials and trials[0][0] < current[0]:
                current = retarget_nearest(trials[0])
            if current[2] is not None:
                distance = math.hypot(current[2]["raw"][0] - dust_x,
                                      current[2]["raw"][2] - dust_z)
                log(
                    "pending-B lattice step %d: raw-to-dust=%.9f, streams=%d"
                    % (grid_step, distance, len(cache))
                )

    # Solve the two endpoint residuals with simultaneous controller changes.
    # Single-byte coordinate descent can stop where every individual change
    # is worse even though a paired change advances both X and Z.
    for jac_step in (4, 2, 1):
        for _iteration in range(10):
            if current[2] is None:
                break
            route = current[3]
            base_raw = current[2]["raw"]
            derivatives = []
            for index, row in enumerate(route):
                for axis in refine_axes:
                    samples = []
                    axis_step = 32 if axis == "substickX" else jac_step
                    for delta in (-axis_step, axis_step):
                        value = max(1, min(254, row[axis] + delta))
                        neighbor = [dict(item) for item in route]
                        neighbor[index][axis] = value
                        samples.append((value, evaluate(neighbor)))
                    span = samples[1][0] - samples[0][0]
                    if span == 0 or samples[0][1][2] is None or samples[1][1][2] is None:
                        derivatives.append((0.0, 0.0))
                    else:
                        lo_raw = samples[0][1][2]["raw"]
                        hi_raw = samples[1][1][2]["raw"]
                        derivatives.append(((hi_raw[0] - lo_raw[0]) / span,
                                            (hi_raw[2] - lo_raw[2]) / span))
            xx = sum(dx * dx for dx, _dz in derivatives)
            xz = sum(dx * dz for dx, dz in derivatives)
            zz = sum(dz * dz for _dx, dz in derivatives)
            determinant = xx * zz - xz * xz
            if abs(determinant) < 1e-12:
                break
            target_x = dust_x - base_raw[0]
            target_z = dust_z - base_raw[2]
            inv_x = (zz * target_x - xz * target_z) / determinant
            inv_z = (xx * target_z - xz * target_x) / determinant
            delta_vector = [dx * inv_x + dz * inv_z for dx, dz in derivatives]
            proposals = [current]
            for scale in (0.25, 0.5, 0.75, 1.0, 1.25):
                neighbor = [dict(item) for item in route]
                variable = 0
                for row in neighbor:
                    for axis in refine_axes:
                        delta = max(-64, min(64, round(delta_vector[variable] * scale)))
                        row[axis] = max(1, min(254, row[axis] + delta))
                        variable += 1
                proposals.append(evaluate(neighbor))
            proposals.sort(key=lambda item: item[0])
            exact = [item[1] for item in proposals if item[1] is not None]
            if exact:
                return exact
            if proposals[0][0] >= current[0]:
                break
            current = retarget_nearest(proposals[0])
            distance = math.hypot(current[2]["raw"][0] - dust_x,
                                  current[2]["raw"][2] - dust_z)
            log(
                "joint endpoint solve step %d: raw-to-dust=%.9f, streams=%d"
                % (jac_step, distance, len(cache))
            )

    if depth == 2 and current[2] is not None:
        distance = math.hypot(current[2]["raw"][0] - dust_x,
                              current[2]["raw"][2] - dust_z)
        if distance < 2.0:
            radii = (2, 4) if depth == 2 else (2,)
            for radius in radii:
                route = current[3]
                trials = []
                offsets = range(-radius, radius + 1)
                delivered_rows = min(depth + 1, len(route))
                variable_count = delivered_rows * 2
                for deltas in itertools.product(offsets, repeat=variable_count):
                    neighbor = [dict(item) for item in route]
                    variable = 0
                    for row in neighbor[:delivered_rows]:
                        for axis in ("stickX", "stickY"):
                            row[axis] = max(
                                1, min(254, row[axis] + deltas[variable])
                            )
                            variable += 1
                    trials.append(evaluate(neighbor))
                trials.sort(key=lambda item: item[0])
                exact = [item[1] for item in trials if item[1] is not None]
                if exact:
                    log(
                        "%d-row byte lattice found %d exact hit(s) after %d streams"
                        % (delivered_rows, len(exact), len(cache))
                    )
                    return exact
                if trials and trials[0][0] < current[0]:
                    current = retarget_nearest(trials[0])
                distance = math.hypot(current[2]["raw"][0] - dust_x,
                                      current[2]["raw"][2] - dust_z)
                log(
                    "%d-row byte lattice radius %d: raw-to-dust=%.9f, streams=%d"
                    % (delivered_rows, radius, distance, len(cache))
                )

    if depth >= 2 and current[2] is not None:
        distance = math.hypot(current[2]["raw"][0] - dust_x,
                              current[2]["raw"][2] - dust_z)
        _signed_line, _shortfall, line_offset, projection_penalty = (
            seam_geometry(current[2])
        )
        if (
            (0.01 <= distance < 5.0 or line_offset < 1.0)
            and not (line_offset < 0.01 and projection_penalty > 1.0)
        ):
            delivered_rows = min(depth + 1, len(current[3]))
            rng_seed = 0x545757
            for row in current[3][:delivered_rows]:
                rng_seed = (
                    rng_seed * 1315423911
                    + row["stickX"] * 257 + row["stickY"]
                    + row.get("substickX", 128) * 65537
                ) & 0xFFFFFFFF
            rng = random.Random(rng_seed)
            for spread in (64, 32, 16, 8, 4, 2, 1):
                route = current[3]
                base_line, base_shortfall, _line_offset, _projection_penalty = (
                    seam_geometry(current[2])
                )
                derivatives = []
                derivative_step = 8
                for index, row in enumerate(route[:delivered_rows]):
                    for axis in refine_axes:
                        samples = []
                        axis_step = 32 if axis == "substickX" else derivative_step
                        for delta in (-axis_step, axis_step):
                            neighbor = [dict(item) for item in route]
                            neighbor[index][axis] = max(
                                1, min(254, row[axis] + delta)
                            )
                            samples.append((neighbor[index][axis], evaluate(neighbor)))
                        span = samples[1][0] - samples[0][0]
                        if span == 0 or samples[0][1][2] is None or samples[1][1][2] is None:
                            derivatives.append((0.0, 0.0))
                        else:
                            lo_line, lo_shortfall, _lo_offset, _lo_projection = (
                                seam_geometry(samples[0][1][2])
                            )
                            hi_line, hi_shortfall, _hi_offset, _hi_projection = (
                                seam_geometry(samples[1][1][2])
                            )
                            derivatives.append((
                                (hi_line - lo_line) / span,
                                (hi_shortfall - lo_shortfall) / span,
                            ))
                ll = sum(dline * dline for dline, _dshort in derivatives)
                ls = sum(dline * dshort for dline, dshort in derivatives)
                ss = sum(dshort * dshort for _dline, dshort in derivatives)
                determinant = ll * ss - ls * ls
                if abs(determinant) < 1e-12:
                    break
                trials = [current]

                # The linearized inverse can be much larger than the legal byte
                # range when the endpoint is several units short.  Include
                # damped, deterministic steps before adding null-space noise;
                # applying the full correction directly merely saturates the
                # controller bytes and skips the useful local neighborhood.
                residual_line = -base_line
                residual_shortfall = -0.05 - base_shortfall
                inv_line = (
                    ss * residual_line - ls * residual_shortfall
                ) / determinant
                inv_shortfall = (
                    ll * residual_shortfall - ls * residual_line
                ) / determinant
                direct_correction = [
                    dline * inv_line + dshort * inv_shortfall
                    for dline, dshort in derivatives
                ]
                direct_trials = []
                for scale in (0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0):
                    neighbor = [dict(item) for item in route]
                    variable = 0
                    for row in neighbor[:delivered_rows]:
                        for axis in refine_axes:
                            row[axis] = max(
                                1,
                                min(
                                    254,
                                    row[axis]
                                    + round(direct_correction[variable] * scale),
                                ),
                            )
                            variable += 1
                    direct_result = evaluate(neighbor)
                    trials.append(direct_result)
                    direct_trials.append((scale, direct_result))
                if spread == 64:
                    log(
                        "geometry inverse correction range %.3f..%.3f bytes"
                        % (min(direct_correction), max(direct_correction))
                    )
                    for scale, direct_result in direct_trials:
                        candidate = direct_result[2]
                        if candidate is None:
                            log("  damp %.3f: no release candidate" % scale)
                            continue
                        signed_line, shortfall, _offset, _projection = (
                            seam_geometry(candidate)
                        )
                        log(
                            "  damp %.3f: prop-wall=%s line=%+.6f "
                            "shortfall=%+.6f raw=(%.6f, %.6f)"
                            % (
                                scale, candidate["prop_wall"], signed_line,
                                shortfall, candidate["raw"][0],
                                candidate["raw"][2],
                            )
                        )

                for _sample in range(2500):
                    deltas = [rng.randint(-spread, spread) for _ in derivatives]
                    predicted_line = sum(
                        delta * derivative[0]
                        for delta, derivative in zip(deltas, derivatives)
                    )
                    predicted_shortfall = sum(
                        delta * derivative[1]
                        for delta, derivative in zip(deltas, derivatives)
                    )
                    residual_line = -base_line - predicted_line
                    residual_shortfall = -0.05 - base_shortfall - predicted_shortfall
                    inv_line = (
                        ss * residual_line - ls * residual_shortfall
                    ) / determinant
                    inv_shortfall = (
                        ll * residual_shortfall - ls * residual_line
                    ) / determinant
                    corrected = [
                        delta + dline * inv_line + dshort * inv_shortfall
                        for delta, (dline, dshort) in zip(deltas, derivatives)
                    ]
                    neighbor = [dict(item) for item in route]
                    variable = 0
                    for row in neighbor[:delivered_rows]:
                        for axis in refine_axes:
                            row[axis] = max(
                                1, min(254, row[axis] + round(corrected[variable]))
                            )
                            variable += 1
                    trials.append(evaluate(neighbor))
                trials.sort(key=lambda item: item[0])
                exact = [item[1] for item in trials if item[1] is not None]
                if exact:
                    log(
                        "%d-row null-space search found %d exact hit(s) after %d streams"
                        % (delivered_rows, len(exact), len(cache))
                    )
                    return exact
                if trials[0][0] < current[0]:
                    current = retarget_nearest(trials[0])
                current = retarget_nearest(current)
                distance = math.hypot(current[2]["raw"][0] - dust_x,
                                      current[2]["raw"][2] - dust_z)
                _signed_line, _shortfall, line_offset, projection_penalty = (
                    seam_geometry(current[2])
                )
                log(
                    "%d-row null-space spread %d: raw-to-dust=%.9f, "
                    "line-miss=%.9f, forward-shortfall=%.9f, streams=%d"
                    % (
                        delivered_rows, spread, distance, line_offset,
                        projection_penalty, len(cache),
                    )
                )
                checkpoint(current, "null-space-spread-%d" % spread)
                if spread == 16 and distance > 0.2 and line_offset > 0.2:
                    break

    # The row at index `depth` is consumed by next_move after the release pose.
    # It changes the raw endpoint while preserving the old position, so search
    # its two controller bytes jointly before mixing in upstream trajectory edits.
    if depth >= 1 and current[2] is not None:
        distance = math.hypot(current[2]["raw"][0] - dust_x,
                              current[2]["raw"][2] - dust_z)
        _signed_line, _shortfall, line_offset, projection_penalty = (
            seam_geometry(current[2])
        )
        if (
            (distance < 0.05 or (line_offset < 0.01 and projection_penalty < 10.0))
            and depth < len(current[3])
        ):
            route = current[3]
            motion_index = depth
            base_state = start.state.clone()
            base_state._inbuf[0] = _controller_tuple(route[0])
            base_state._inbuf[1] = _controller_tuple(route[1])
            base_node = Node(
                base_state, start.lower.clone(), start.upper.clone(), start.previous,
                start.held_prop, [], {
                    len(prefix) - 2: dict(route[0]),
                    len(prefix) - 1: dict(route[1]),
                },
            )
            for row in route[2:]:
                base_node = _step(base_node, row)
            old = (
                base_node.state.pos_x, base_node.state.pos_y, base_node.state.pos_z
            )
            held = base_node.previous
            fixed_pose = dr.decomp_moving_b_drop_pose(
                held.pos, old, held.facing,
                _lower_pose(held), _lower_pose(base_node), held.upper.frame,
                "pot_small", lower_anims=lower_anims, upper_anims=upper_anims,
                skeleton=skeleton, held_lean=held.lean,
                collision_lean=base_node.state._draw_lean,
                collision_facing=base_node.state.facing,
                held_body_lean=held.body_lean,
                collision_body_lean=_signed_s16(base_node.state.m351C) >> 1,
            )
            follow = base_node.rows[-1]
            tested = 0
            best_motion = None
            worker_context = SimpleNamespace(
                walls=context.walls, wall_a=context.wall_a, wall_b=context.wall_b,
            )
            workers = max(1, min(10, os.cpu_count() or 1))
            rows_to_test = itertools.product(range(1, 255), repeat=2)
            log(f"complete buffered-motion grid: 64516 rows on {workers} workers")
            pool_context = mp.get_context("spawn")
            with pool_context.Pool(
                workers, initializer=_init_motion_grid_worker,
                initargs=(base_node.state, follow, old, fixed_pose, worker_context),
            ) as pool:
                for trial in pool.imap_unordered(
                    _motion_grid_worker, rows_to_test, chunksize=64,
                ):
                    tested += 1
                    if trial is None:
                        continue
                    stick_x, stick_y, raw, resolved, crosses = trial
                    motion_candidate = {
                        "old": old, "raw": raw,
                    }
                    _signed_line, _shortfall, motion_line, motion_projection = (
                        seam_geometry(motion_candidate)
                    )
                    plane_a = context.wall_a.pla.func(raw)
                    plane_b = context.wall_b.pla.func(raw)
                    motion_violation = math.hypot(
                        max(0.0, plane_a), max(0.0, plane_b)
                    )
                    motion_score = (
                        motion_line + motion_projection
                        + 0.001 * motion_violation
                    )
                    if best_motion is None or motion_score < best_motion[0]:
                        best_motion = (
                            motion_score, stick_x, stick_y, raw, resolved,
                            motion_line, motion_projection,
                        )
                    if not crosses:
                        continue
                    motion_row = dict(route[motion_index])
                    motion_row["stickX"] = stick_x
                    motion_row["stickY"] = stick_y
                    node_rows = [dict(row) for row in base_node.rows]
                    node_rows[motion_index - 2] = motion_row
                    rows = [dict(row) for row in prefix + node_rows + [follow]]
                    for index, replacement in base_node.prefix_patch.items():
                        rows[index] = dict(replacement)
                    b_index = len(prefix) + len(node_rows) - 3
                    rows[b_index]["buttons"] = rows[b_index].get("buttons", 0) | BUTTON_B
                    retained = min(
                        -context.wall_a.pla.func(resolved),
                        -context.wall_b.pla.func(resolved),
                    )
                    log(
                        "buffered-motion grid found an exact hit after %d streams"
                        % tested
                    )
                    return [Hit(
                        depth=len(node_rows), b_index=b_index, old=old,
                        raw=raw, resolved=resolved,
                        retained_depth=retained, facing=base_node.state.facing,
                        speed=base_node.state.speedF, rows=rows,
                    )]
            if best_motion is not None:
                (_motion_score, stick_x, stick_y, _raw, _resolved,
                 motion_line, motion_projection) = best_motion
                neighbor = [dict(item) for item in route]
                neighbor[motion_index]["stickX"] = stick_x
                neighbor[motion_index]["stickY"] = stick_y
                motion_result = evaluate(neighbor)
                if motion_result[0] < current[0]:
                    current = motion_result
                current = retarget_nearest(current)
                distance = math.hypot(current[2]["raw"][0] - dust_x,
                                      current[2]["raw"][2] - dust_z)
                log(
                    "buffered-motion grid: best stick=(%d,%d), "
                    "line-miss=%.9f, forward-shortfall=%.9f, "
                    "raw-to-dust=%.9f, tested=%d"
                    % (
                        stick_x, stick_y, motion_line, motion_projection,
                        distance, tested,
                    )
                )

    # If broader compensation returned to the exact neighborhood, finish the
    # fourth-order shell without repeating the cheaper shells run above.
    if depth >= 2 and current[2] is not None:
        distance = math.hypot(current[2]["raw"][0] - dust_x,
                              current[2]["raw"][2] - dust_z)
        if distance < 0.01:
            current, exact = exact_hamming_search(current, 4, 4)
            if exact:
                return exact

    # A one-byte change in two separate rows can cross a discrete turning
    # boundary even when every single-coordinate neighbor is worse.
    frontier = [current]
    for _round in range(3):
        expanded = list(frontier)
        for _score, _hit, _candidate, route in frontier:
            for index, row in enumerate(route):
                for axis in refine_axes:
                    for delta in (-1, 1):
                        value = max(1, min(254, row[axis] + delta))
                        if value == row[axis]:
                            continue
                        neighbor = [dict(item) for item in route]
                        neighbor[index][axis] = value
                        expanded.append(evaluate(neighbor))
        expanded.sort(key=lambda item: item[0])
        exact = [item[1] for item in expanded if item[1] is not None]
        if exact:
            return exact
        frontier = expanded[:24]
    if current[2] is not None:
        checkpoint(current, "final-near")
        seed_candidate.clear()
        seed_candidate.update(current[2])
    return []


def solve(pid, seed_path, output_dir, max_depth=8, beam_size=5000, log=print,
          stage=None, room=None, iso=None, base_state=None, refine_near=None,
          min_refine_depth=0, refine_candidate_index=0):
    seed = json.loads(Path(seed_path).read_text(encoding="ascii"))
    if base_state is not None:
        seed["base_state"] = str(base_state)
    seam = tuple(seed["seam"])
    if pid is not None:
        region, live, _bg = load_live_room_collision(pid, status=log)
    else:
        stage = stage or seed.get("stage")
        room = seed.get("room") if room is None else room
        if not stage or room is None:
            raise ValueError("offline collision requires stage and room")
        region, _box, _loaded_stage = load_room_collision(
            {"stage": stage, "room": int(room), "iso": iso}, status=log,
        )
        live = SimpleNamespace(stage=stage, room=int(room))
    x, y, z = seam
    context = prepare_search(
        region,
        (x - 180.0, x + 180.0, y - 260.0, y + 260.0, z - 180.0, z + 180.0),
        seam,
    )
    lower_anims = dr.j3d_eval.load_anim(
        str(Path(__file__).resolve().parents[2] / "_generated" / "anim" / "link_anim_walk_dash.json")
    )
    upper_anims = dr.load_grab_anims()
    skeleton = dr.load_skeleton()
    start = _make_seed(
        seed, context.walls, floors=[item["T"] for item in context.floors]
    )
    release_probe = _exact_release_probe(seed)
    if release_probe is not None:
        log(
            "exact B-transition calibration: release row %d held=(%.9f, %.9f, %.9f) "
            "LinkCo=(%.9f, %.9f, %.9f)"
            % (release_probe["release_row"], *release_probe["held_prop_pos"],
               *release_probe["link_co_center"])
        )
    prefix = seed["rows"]
    minimum_depth = 1 if seed.get("seed_kind") == "exact_moving_anchor" else 0
    if refine_near is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = json.loads(Path(refine_near).read_text(encoding="ascii"))
        if isinstance(saved, list):
            eligible = [
                item for item in saved
                if int(item.get("depth", -1)) >= min_refine_depth
            ]
            if not eligible:
                raise RuntimeError("saved candidate list has no eligible refinement depth")
            if not 0 <= refine_candidate_index < len(eligible):
                raise RuntimeError(
                    f"saved candidate index {refine_candidate_index} is outside "
                    f"the {len(eligible)} eligible candidates"
                )
            candidate = eligible[refine_candidate_index]
        else:
            candidate = saved
        hits = _refine_near_route(
            start, candidate, context, prefix, lower_anims, upper_anims,
            skeleton, release_probe, log, minimum_depth,
            checkpoint_path=output_dir / "moving_pot_refine_checkpoint.json",
        )
        if not hits:
            candidate["seam"] = list(seam)
            movie = output_dir / "moving_pot_near.dtm"
            build_dtm_from_sticks(
                candidate["rows"], str(movie), seed=0, game_id=seed["game_id"]
            )
            candidate["movie"] = str(movie)
            candidate["movie_state"] = install_savestate_companions(
                str(movie), seed["base_state"]
            )
            (output_dir / "moving_pot_near.json").write_text(
                json.dumps(candidate, indent=2), encoding="ascii"
            )
            raise RuntimeError("saved-candidate refinement found no exact clip")
        hits.sort(key=lambda hit: (hit.b_index, -hit.speed, -hit.retained_depth))
        best = hits[0]
        movie = output_dir / "moving_pot_clip_offline.dtm"
        build_dtm_from_sticks(best.rows, str(movie), seed=0, game_id=seed["game_id"])
        movie_state = Path(install_savestate_companions(str(movie), seed["base_state"]))
        result = {
            "stage": live.stage, "room": live.room, "seam": list(seam),
            "object_type": seed.get("object_type", "pot_small"),
            "best": best.__dict__, "movie": str(movie),
            "movie_state": str(movie_state), "hits_at_fastest_depth": len(hits),
        }
        (output_dir / "moving_pot_clip_offline.json").write_text(
            json.dumps(result, indent=2), encoding="ascii"
        )
        log(
            "offline exact hit: B row %d, old=(%.9f, %.9f), "
            "resolved=(%.9f, %.9f), depth=%.9f"
            % (best.b_index, best.old[0], best.old[2], best.resolved[0],
               best.resolved[2], best.retained_depth)
        )
        return result
    hits, directed_near = _constant_bearing_search(
        start, context, prefix, lower_anims, upper_anims, skeleton,
        max_depth, release_probe, log, minimum_depth,
    )
    directed_distance = (
        math.hypot(directed_near[0]["raw"][0] - context.seam_target[0],
                   directed_near[0]["raw"][2] - context.seam_target[2])
        if directed_near else math.inf
    )
    has_depth_one_near = any(
        int(candidate.get("depth", -1)) == 1 and not candidate.get("prop_wall")
        for candidate in directed_near
    )
    start_distance = math.hypot(
        start.state.pos_x - context.seam_target[0],
        start.state.pos_z - context.seam_target[2],
    )
    pair_hits, pair_near = _pending_pair_search(
        start, context, prefix, lower_anims, upper_anims, skeleton,
        release_probe, log, minimum_depth,
    ) if not hits and not has_depth_one_near and start_distance <= 100.0 else ([], [])
    hits.extend(pair_hits)
    curved_near = _two_bearing_search(
        start, context, prefix, lower_anims, upper_anims, skeleton,
        max_depth, release_probe, log, minimum_depth,
    ) if not hits and directed_distance > 8.0 else []
    near_candidates = list(pair_near) + list(directed_near) + list(curved_near)
    if not hits:
        hits.extend(_refine_promising_routes(
            start, near_candidates, context, prefix, lower_anims, upper_anims,
            skeleton, release_probe, log, minimum_depth,
        ))
    if hits:
        frontier = []
    else:
        frontier = []
    # Raw prefix row N-1 (zero index N-2) is still pending at the captured state. Sweep it offline:
    # both buffered rows can change future movement without changing the captured pose. The broad
    # fallback keeps them on one bearing; the low-dimensional refiner separates them afterward.
    pending_index = len(prefix) - 2
    pending_next_index = len(prefix) - 1
    if not hits:
        for pending in _movement_rows(start.state, context.seam_target, spread=0x3000, step=64):
            state = start.state.clone()
            state._inbuf[0] = _controller_tuple(pending)
            state._inbuf[1] = _controller_tuple(pending)
            frontier.append(Node(
                state, start.lower.clone(), start.upper.clone(), start.previous,
                start.held_prop, [], {
                    pending_index: dict(pending), pending_next_index: dict(pending),
                },
            ))
        log(f"offline pending-input sweep: {len(frontier)} exact delivered stick cell(s)")
    for depth in range(max_depth + 1 if not hits else 0):
        diagnostics = {}
        for node in frontier:
            hit = _try_drop(
                node, context, prefix, lower_anims, upper_anims, skeleton,
                diagnostics=diagnostics, release_probe=release_probe,
                minimum_depth=minimum_depth,
            )
            if hit is not None:
                hits.append(hit)
        log(
            "offline depth %d release diagnostics: tested=%d not_front=%d prop_wall=%d "
            "too_far=%d link_wall=%d raw_not_across=%d resolved_out=%d "
            "best_raw=%.6f best_resolved=%.6f"
            % (depth, diagnostics.get("tested", 0), diagnostics.get("not_front", 0),
               diagnostics.get("prop_wall", 0), diagnostics.get("too_far", 0),
               diagnostics.get("link_wall", 0),
               diagnostics.get("raw_not_across", 0), diagnostics.get("resolved_out", 0),
               diagnostics.get("best_raw_depth", float("nan")),
               diagnostics.get("best_resolved_depth", float("nan")))
        )
        if diagnostics.get("best_raw_pos") is not None:
            pos = diagnostics["best_raw_pos"]
            planes = diagnostics["best_raw_planes"]
            log(
                "  best raw pos=(%.9f, %.9f, %.9f) wall_planes=(%+.9f, %+.9f)"
                % (*pos, *planes)
            )
            candidate = diagnostics.get("best_candidate")
            if candidate is not None:
                planes = diagnostics["best_raw_planes"]
                candidate["wall_planes"] = planes
                candidate["raw_depth"] = diagnostics["best_raw_depth"]
                near_candidates.append(candidate)
        if hits:
            break
        expanded = []
        for node in frontier:
            if node.state.wall_hit:
                continue
            distance = math.hypot(
                node.state.pos_x - context.seam_target[0],
                node.state.pos_z - context.seam_target[2],
            )
            # Far from the corner, adjacent controller cells produce the same
            # coarse approach family. Preserve the full 128-BAM resolution
            # once the release can become seam-local.
            for row in _fallback_movement_rows(node.state, context.seam_target):
                child = _step(node, row)
                if child.state.state == MOVE and child.state.speedF > 0.0:
                    expanded.append(child)
        def rank(node):
            dist = math.hypot(
                node.state.pos_x - context.seam_target[0],
                node.state.pos_z - context.seam_target[2],
            )
            return (abs(dist - 52.0), dist)
        expanded.sort(key=rank)
        unique = {}
        frontier_distance = min(
            (
                math.hypot(node.state.pos_x - context.seam_target[0],
                           node.state.pos_z - context.seam_target[2])
                for node in expanded
            ),
            default=math.inf,
        )
        depth_beam_size = _fallback_beam_width(frontier_distance, beam_size)
        for node in expanded:
            key = (
                round(node.state.pos_x, 5), round(node.state.pos_z, 5),
                node.state.facing, node.state.travel,
                tuple(_controller_tuple(row)[:2] for row in node.rows[-2:]),
            )
            unique.setdefault(key, node)
            if len(unique) >= depth_beam_size:
                break
        frontier = list(unique.values())
        log(
            "offline depth %d: retained %d binary32 states (nearest %.3f, cap %d)"
            % (depth + 1, len(frontier), frontier_distance, depth_beam_size)
        )
        if not frontier:
            break
    if not hits:
        if near_candidates:
            _annotate_dust_frontier(near_candidates, context)
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "moving_pot_near_candidates.json").write_text(
                json.dumps(near_candidates, indent=2), encoding="ascii"
            )
            refine_candidates = []
            refine_counts = {}
            for candidate in near_candidates:
                candidate_depth = int(candidate.get("depth", -1))
                if candidate_depth < min_refine_depth:
                    continue
                limit = 1 if candidate_depth == 1 else 4
                if refine_counts.get(candidate_depth, 0) >= limit:
                    continue
                refine_candidates.append(candidate)
                refine_counts[candidate_depth] = refine_counts.get(candidate_depth, 0) + 1
            for near in refine_candidates:
                refined = _refine_near_route(
                    start, near, context, prefix, lower_anims, upper_anims, skeleton,
                    release_probe, log, minimum_depth,
                )
                if refined:
                    hits.extend(refined)
                    break
            (output_dir / "moving_pot_refined_candidates.json").write_text(
                json.dumps(near_candidates, indent=2), encoding="ascii"
            )
        if near_candidates and not hits:
            _annotate_dust_frontier(near_candidates, context)
            near = near_candidates[0]
            near["seam"] = list(seam)
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            near_movie = output_dir / "moving_pot_near.dtm"
            build_dtm_from_sticks(
                near["rows"], str(near_movie), seed=0, game_id=seed["game_id"]
            )
            near["movie"] = str(near_movie)
            near["movie_state"] = install_savestate_companions(
                str(near_movie), seed["base_state"]
            )
            (output_dir / "moving_pot_near.json").write_text(
                json.dumps(near, indent=2), encoding="ascii"
            )
            log(
                "best rejected stream exported: depth=%d planes=(%+.6f,%+.6f) "
                "prop_wall=%s link_wall=%s"
                % (near["depth"], *near["wall_planes"], near["prop_wall"],
                   near["link_wall"])
            )
        if not hits:
            raise RuntimeError("offline moving-drop search found no exact clip")
    hits.sort(key=lambda hit: (hit.b_index, -hit.speed, -hit.retained_depth))
    best = hits[0]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    movie = output_dir / "moving_pot_clip_offline.dtm"
    build_dtm_from_sticks(best.rows, str(movie), seed=0, game_id=seed["game_id"])
    movie_state = Path(install_savestate_companions(str(movie), seed["base_state"]))
    result = {
        "stage": live.stage, "room": live.room, "seam": list(seam),
        "object_type": seed.get("object_type", "pot_small"),
        "best": best.__dict__, "movie": str(movie),
        "movie_state": str(movie_state), "hits_at_fastest_depth": len(hits),
    }
    (output_dir / "moving_pot_clip_offline.json").write_text(
        json.dumps(result, indent=2), encoding="ascii"
    )
    log(
        "offline exact hit: B row %d, old=(%.9f, %.9f), resolved=(%.9f, %.9f), depth=%.9f"
        % (best.b_index, best.old[0], best.old[2], best.resolved[0],
           best.resolved[2], best.retained_depth)
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int)
    parser.add_argument(
        "--seed", type=Path,
        default=Path(__file__).resolve().parents[2] / "_generated" / "moving_drop" / "moving_pot_cruise.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[2] / "_generated" / "moving_drop",
    )
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--beam", type=int, default=5000)
    parser.add_argument("--stage")
    parser.add_argument("--room", type=int)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--base-state", type=Path)
    parser.add_argument("--refine-near", type=Path)
    parser.add_argument("--min-refine-depth", type=int, default=0)
    parser.add_argument("--refine-candidate-index", type=int, default=0)
    args = parser.parse_args(argv)
    if args.pid is None and (not args.stage or args.room is None):
        parser.error("provide --pid, or provide both --stage and --room")
    solve(
        args.pid, args.seed, args.output, args.max_depth, args.beam,
        stage=args.stage, room=args.room, iso=str(args.iso) if args.iso else None,
        base_state=args.base_state,
        refine_near=args.refine_near,
        min_refine_depth=args.min_refine_depth,
        refine_candidate_index=args.refine_candidate_index,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
