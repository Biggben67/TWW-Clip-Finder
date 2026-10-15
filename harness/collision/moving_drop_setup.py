"""Automatically find first-person walking starts for moving bomb/pot BPCs."""
from __future__ import annotations

import math
from pathlib import Path
from typing import NamedTuple

from harness.collision.find_drop_push_candidate import (
    _floor_at,
    _valid_initial,
    find_candidates,
    prepare_search,
)
from harness.collision.offline_moving_drop import (
    Node,
    _clock,
    _controller_tuple,
    _candidate_local_dust,
    _pose_of,
    _step,
    _try_drop,
    _moving_candidate_rank,
)
from harness.rollstab.rest import dtm_stick
from tww_sim.core import drop_release as dr
from tww_sim.core import fp
from tww_sim.land.constants import SUBJECTIVITY
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.land.plan_land import world_angle_s16
from tww_sim.land.state import LandState


class NearPath(NamedTuple):
    score: tuple
    start_pos: tuple
    start_facing: int
    bearing: int
    magnitude: float
    row: dict
    phase: int
    frame: int
    switch_frame: int | None
    switch_row: dict | None
    candidate: dict


def _walk_row(bearing, camera, magnitude):
    sx, sy = dtm_stick(stick_for_bearing(bearing, camera, magnitude))
    return {
        "stickX": sx, "stickY": sy, "substickX": 128, "substickY": 128,
        "buttons": 0, "triggerL": 0,
    }


def _start_node(pos, facing, context, anim_phase, settle_frames, object_type):
    floors = [item["T"] for item in context.floors]
    from tww_sim.land.floors import ground_cross

    floor_y, floor_index = ground_cross(floors, pos[0], fp.fadds(pos[1], 60.0), pos[2])
    if floor_index is None or abs(floor_y - pos[1]) > 2.0:
        raise ValueError("first-person start position must be on modeled ground collision")
    gnd_seed = {
        "ground_hit": True,
        "gnd_pla": floors[floor_index].pla,
    }
    state = LandState(
        pos_x=pos[0], pos_y=pos[1], pos_z=pos[2], facing=facing, travel=facing,
        csangle=facing, state=SUBJECTIVITY, nspeed=0.0, speedF=0.0,
        use_anim=True, native=False, walls=context.walls, floors=floors,
        gnd_seed=gnd_seed, input_delay=2,
    )
    state._subj_frames = max(9, int(settle_frames))
    state._drop_object_type = object_type
    state._foot.defer_draw = True
    state._foot.enter_subjectivity(state.msd)
    lower = state._foot.st.clone()
    # procGrabWait_init installs the carried upper GRABWAIT with rate 0.0.
    # Entering subjectivity does not turn it into a freely selectable clock.
    upper = _clock(0.0, 0.0, dr.load_grab_anims()["grabwait"]["frame_max"])
    node = Node(state, lower, upper, None, None, [], {})
    node.previous = _pose_of(node)
    return node


def _exit_first_person(node, settle_frames):
    """Model an already-settled subjectivity pose and its C-down exit with input latency."""
    count = max(11, int(settle_frames) + 2)
    row = {
        "stickX": 128, "stickY": 128, "substickX": 128, "substickY": 0,
        "buttons": 0, "triggerL": 0,
    }
    for _ in range(count):
        node = _step(node, row)
    if node.state.state == SUBJECTIVITY:
        raise RuntimeError("C-down exit did not leave first person in the simulated setup")
    # Keep two buffered rows that the angle sweep replaces with the selected walk input.
    node.rows[-2:] = [dict(row), dict(row)]
    node.state._inbuf = [_controller_tuple(row), _controller_tuple(row)]
    return node


def _launch_anchors(context, seam, max_frames, limit):
    """Sample grounded starts on the valid side of the seam, nearest first."""
    sx, sy, sz = seam
    max_radius = min(220.0, max(56.0, max_frames * 12.0))
    radii = list(range(40, int(max_radius) + 1, 12))
    anchors = []
    # A 512-BAM polar grid is the broad phase. Exact float and controller
    # quantization are tested later by the forward movement/drop simulation.
    for radius in radii:
        for direction in range(0, 0x10000, 512):
            radians = direction * (2.0 * math.pi / 65536.0)
            x = fp.f32(sx - math.sin(radians) * radius)
            z = fp.f32(sz - math.cos(radians) * radius)
            y = _floor_at(context.ground, x, z, context.yspan)
            if y is None:
                continue
            pos = (x, fp.f32(y), z)
            if not (
                context.wall_a.pla.func(pos) > 0.0
                and context.wall_b.pla.func(pos) > 0.0
            ):
                continue
            if not _valid_initial(
                context.barriers, context.ground, pos,
                context.wall_a, context.wall_b, context.yspan, True,
            ):
                continue
            facing = world_angle_s16(sx - x, sz - z) & 0xFFFF
            anchors.append((radius, direction, pos, facing))
    anchors.sort(key=lambda item: (item[0], item[1]))
    if len(anchors) <= limit:
        return anchors
    # Preserve coverage across both radius and angle instead of spending the
    # cap on the first ring.
    stride = len(anchors) / float(limit)
    return [anchors[min(len(anchors) - 1, int(i * stride))] for i in range(limit)]


def _coarse_phases(phases):
    """Use representative phases for the broad pass; refine selected paths at every phase."""
    phases = tuple(dict.fromkeys(int(phase) for phase in phases))
    if len(phases) <= 6:
        return phases
    selected = [phase for phase in (5, 11, 51) if phase in phases]
    for index in range(3):
        if len(selected) >= 3:
            break
        selected.append(phases[round(index * (len(phases) - 1) / 2)])
    return tuple(dict.fromkeys(selected))


def _facing_allowed(facing, ranges):
    return any(lo <= facing <= hi for lo, hi, _step in ranges)


def _static_witnesses(context, phases, facing_ranges, object_type):
    """Find exact still-drop crossings to locate promising moving release corridors."""
    priorities = [phase for phase in (5, 11, 51) if phase in phases]
    if not priorities:
        priorities = list(_coarse_phases(phases)[:3])
    coarse_ranges = tuple(
        (lo, hi, max(step, 256) if hi - lo >= 256 else max(1, step))
        for lo, hi, step in facing_ranges
    )
    witnesses = []
    for phase in priorities:
        witnesses.extend(find_candidates(
            context, phase, object_type=object_type,
            facing_ranges=coarse_ranges,
            phases=(0.45, 0.98, 0.02), limit=12,
        ))
    return witnesses


def _witness_anchors(context, witnesses, limit):
    """Place walking starts behind exact still-drop positions on valid ground."""
    anchors = []
    seen = set()
    for distance in (16, 28, 44, 8, 64):
        for lateral in (0, -5, 5):
            for witness in witnesses:
                angle = witness.facing * (2.0 * math.pi / 65536.0)
                forward_x, forward_z = math.sin(angle), math.cos(angle)
                x = fp.f32(witness.old[0] - distance * forward_x + lateral * forward_z)
                z = fp.f32(witness.old[2] - distance * forward_z - lateral * forward_x)
                y = _floor_at(context.ground, x, z, context.yspan)
                if y is None:
                    continue
                pos = (x, fp.f32(y), z)
                if not _valid_initial(
                    context.barriers, context.ground, pos,
                    context.wall_a, context.wall_b, context.yspan, True,
                ):
                    continue
                key = (x, z, witness.facing)
                if key in seen:
                    continue
                seen.add(key)
                anchors.append((distance, witness.facing, pos, witness.facing))
                if len(anchors) >= limit:
                    return anchors
    return anchors


def _near_score(candidate, context):
    raw = candidate["raw"]
    distance = math.hypot(
        raw[0] - context.seam_target[0], raw[2] - context.seam_target[2],
    )
    ray = _moving_candidate_rank(candidate, context)[4]
    return (1 if candidate["prop_wall"] else 0, ray + 0.15 * distance, distance)


def solve_moving_drop_setup(seam, region, *, object_type="bomb",
                            max_frames=24, animation_positions=(1, 5, 11, 51),
                            facing_ranges=((0, 65535, 16),),
                            magnitudes=(0.7, 0.85, 1.0), max_start_positions=500,
                            require_oob_landing=False,
                            oob_tolerance=0.005, max_results=10, settle_frames=9,
                            cancelled=None, progress=None):
    """Search generated first-person anchors and forward walking/drop trajectories.

    Launch position and facing are solver variables, not user-provided inputs. Candidate starts
    are placed on modeled ground in front of both seam planes, then walked toward the seam with
    nearby controller bearings and analog magnitudes. Every accepted drop uses the layered,
    wall-faithful moving B-drop model.
    """
    if object_type not in ("bomb", "pot_small"):
        raise ValueError("moving drop setup supports bomb and small pot")
    if not 1 <= int(max_frames) <= 120:
        raise ValueError("movement frames must be between 1 and 120")
    if not 0.0 < float(oob_tolerance) <= 1.0:
        raise ValueError("OOB seam distance must be greater than 0 and at most 1 unit")
    if int(max_start_positions) < 1:
        raise ValueError("launch search effort must be at least 1")
    phases = tuple(dict.fromkeys(int(phase) for phase in animation_positions))
    if not phases or any(not 1 <= phase <= 60 for phase in phases):
        raise ValueError("animation positions must be between 1 and 60")
    facing_ranges = tuple(facing_ranges)
    if not facing_ranges:
        raise ValueError("at least one facing range is required")

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
    witnesses = _static_witnesses(context, phases, facing_ranges, object_type)
    witness_limit = min(128, max(1, int(max_start_positions) // 2))
    witness_anchors = _witness_anchors(context, witnesses, witness_limit)
    grid_limit = int(max_start_positions) - len(witness_anchors)
    anchors = list(witness_anchors)
    if grid_limit:
        anchors.extend(_launch_anchors(context, seam, int(max_frames), grid_limit))
    anchors = list(dict.fromkeys(anchors))
    if not anchors:
        raise ValueError(
            "no grounded launch anchors were found on the approach side of this seam; "
            "check the selected room collision and seam coordinates"
        )
    hits = []
    tested = 0
    near = []
    coarse_phases = (0,)
    def scan_trajectory(prefix, trajectory, eligible_frames, selected_phases,
                        start_pos, start_facing, bearing, magnitude, row,
                        record_near=False, only_frame=None,
                        switch_frame=None, switch_row=None):
        nonlocal tested
        best = None
        for phase in (0,):
            for frame in eligible_frames:
                if only_frame is not None and frame != only_frame:
                    continue
                saved_node = trajectory[frame]
                candidate = Node(
                    saved_node.state, saved_node.lower, saved_node.upper,
                    saved_node.previous,
                    saved_node.held_prop, saved_node.rows, saved_node.prefix_patch,
                )
                diagnostics = {} if record_near else None
                hit = _try_drop(
                    candidate, context, prefix, lower_anims, upper_anims,
                    skeleton, diagnostics=diagnostics, minimum_depth=3,
                    next_move=trajectory.get(frame + 1),
                )
                tested += 1
                if hit is not None and _facing_allowed(hit.facing, facing_ranges):
                    seam_distance = math.hypot(
                        hit.resolved[0] - context.seam_target[0],
                        hit.resolved[2] - context.seam_target[2],
                    )
                    floor = _floor_at(
                        context.ground, hit.resolved[0], hit.resolved[2], context.yspan
                    )
                    wall_depths = (
                        -context.wall_a.pla.func(hit.resolved),
                        -context.wall_b.pla.func(hit.resolved),
                    )
                    oob = (
                        wall_depths[0] > 0.0 and wall_depths[1] > 0.0
                        and seam_distance <= oob_tolerance and floor is not None
                        and abs(floor - hit.old[1]) <= 1e-3
                    )
                    if not require_oob_landing or oob:
                        start_phase = 0
                        if not replay_hit(hit, start_pos, start_facing, start_phase, frame):
                            continue
                        hits.append({
                            "depth": frame, "b_index": hit.b_index,
                            "facing": hit.facing, "speed": hit.speed,
                            "old": hit.old, "raw": hit.raw, "resolved": hit.resolved,
                            "retained_depth": hit.retained_depth,
                            "seam_distance": seam_distance, "oob_landing": oob,
                            "wall_depths": wall_depths, "floor": floor,
                            "rows": hit.rows, "walk_bearing": bearing,
                            "walk_magnitude": magnitude, "animation_phase": phase,
                            "start_animation_phase": start_phase,
                            "object_type": object_type, "seam": list(seam),
                            "start_pos": list(start_pos), "start_facing": start_facing,
                        })
                if diagnostics is not None:
                    candidate_near = diagnostics.get("best_candidate")
                    if (candidate_near is not None
                            and _facing_allowed(candidate_near["facing"], facing_ranges)):
                        score = _near_score(candidate_near, context)
                        if best is None or score < best.score:
                            best = NearPath(
                                score, start_pos, start_facing, bearing,
                                magnitude, row, phase, frame,
                                switch_frame, switch_row, candidate_near,
                            )
        return best

    def trace_route(base, row, switch_frame=None, switch_row=None, frame_limit=None):
        prefix = [dict(item) for item in base.rows]
        state = base.state.clone()
        state._drop_object_type = object_type
        node = Node(
            state, base.lower.clone(), base.upper.clone(), base.previous,
            base.held_prop, [], {},
        )
        trajectory = {}
        eligible = []
        for frame in range(1, (frame_limit or int(max_frames)) + 1):
            input_row = switch_row if switch_frame is not None and frame >= switch_frame else row
            node = _step(node, input_row)
            trajectory[frame] = node
            if node.state.state == SUBJECTIVITY:
                break
            old = (node.state.pos_x, node.state.pos_y, node.state.pos_z)
            if (frame >= 3 and abs(node.state.speedF) >= 0.25
                    and context.wall_a.pla.func(old) > 0.0
                    and context.wall_b.pla.func(old) > 0.0
                    and math.hypot(
                        old[0] - context.seam_target[0],
                        old[2] - context.seam_target[2],
                    ) <= 80.0):
                eligible.append(frame)
        return prefix, trajectory, eligible

    def replay_hit(hit, start_pos, start_facing, start_phase, frame):
        """Require the returned rows to reproduce the searched upper-body phase."""
        try:
            node = _exit_first_person(
                _start_node(start_pos, start_facing, context, start_phase,
                            settle_frames, object_type), settle_frames,
            )
        except (ValueError, RuntimeError):
            return False
        prefix = [dict(row) for row in node.rows]
        if hit.rows[:len(prefix)] != prefix:
            return False
        for source in hit.rows[len(prefix):len(prefix) + frame]:
            row = dict(source)
            row["buttons"] = row.get("buttons", 0) & ~0x0200
            node = _step(node, row)
        replayed = _try_drop(
            node, context, prefix, lower_anims, upper_anims, skeleton,
            minimum_depth=3,
        )
        return (replayed is not None
                and replayed.old == hit.old
                and replayed.raw == hit.raw
                and replayed.resolved == hit.resolved
                and replayed.facing == hit.facing)

    def probe_start(item, px, pz):
        start_facing, bearing, magnitude = item.start_facing, item.bearing, item.magnitude
        row, phase, frame = item.row, item.phase, item.frame
        px, pz = fp.f32(px), fp.f32(pz)
        py = _floor_at(context.ground, px, pz, context.yspan)
        if py is None:
            return None
        pos = (px, fp.f32(py), pz)
        if not _valid_initial(
            context.barriers, context.ground, pos,
            context.wall_a, context.wall_b, context.yspan, True,
        ):
            return None
        try:
            base = _exit_first_person(
                _start_node(pos, start_facing, context, 1.0,
                            settle_frames, object_type), settle_frames,
            )
        except (ValueError, RuntimeError):
            return None
        prefix, trajectory, eligible = trace_route(
            base, row, switch_frame=item.switch_frame,
            switch_row=item.switch_row, frame_limit=frame + 1,
        )
        if frame not in eligible:
            return None
        return scan_trajectory(
            prefix, trajectory, eligible, (phase,),
            pos, start_facing, bearing, magnitude, row,
            record_near=True, only_frame=frame,
            switch_frame=item.switch_frame, switch_row=item.switch_row,
        )

    def refine_nearby(candidates, max_paths=24):
        if not candidates:
            return
        directed = []
        for item in candidates:
            direct = world_angle_s16(
                context.seam_target[0] - item.start_pos[0],
                context.seam_target[2] - item.start_pos[2],
            ) & 0xFFFF
            offset = ((item.bearing - direct + 32768) & 0xFFFF) - 32768
            if abs(offset) <= 512 and item.magnitude >= 0.99:
                directed.append(item)
        ordered = sorted(directed, key=lambda item: item.score)
        ordered.extend(sorted(candidates, key=lambda item: item.score))
        selected = []
        seen = set()
        for item in ordered:
            key = (item.start_pos, item.bearing, item.magnitude, item.phase,
                   item.frame, item.switch_frame,
                   None if item.switch_row is None else (
                       item.switch_row["stickX"], item.switch_row["stickY"],
                       item.switch_row["substickX"],
                   ))
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= max_paths:
                break
        for item in selected:
            if cancelled is not None and cancelled():
                return
            candidate = item.candidate
            old, raw = candidate["old"], candidate["raw"]
            vx, vz = raw[0] - old[0], raw[2] - old[2]
            length = math.hypot(vx, vz)
            if length < 1.0:
                continue
            depths = (
                (min(0.4 * oob_tolerance / length, 0.01), 0.02, 0.05)
                if require_oob_landing else (0.05, 0.10, 0.02)
            )
            for depth in depths:
                target_x = context.seam_target[0] + depth * vx
                target_z = context.seam_target[2] + depth * vz
                px = item.start_pos[0] + target_x - raw[0]
                pz = item.start_pos[2] + target_z - raw[2]
                aligned = probe_start(item, px, pz)
                if hits:
                    return
                if aligned is None:
                    continue
                moved = aligned.candidate
                dust = _candidate_local_dust(
                    moved, context, box_ulps=12, max_calls=625,
                )
                if dust is None:
                    continue
                center_x = fp.f32(aligned.start_pos[0] + dust[0] - moved["raw"][0])
                center_z = fp.f32(aligned.start_pos[2] + dust[1] - moved["raw"][2])
                x_step = math.ldexp(1.0, math.frexp(abs(center_x))[1] - 24)
                z_step = math.ldexp(1.0, math.frexp(abs(center_z))[1] - 24)
                for ring in range(5):
                    for ix in range(-ring, ring + 1):
                        for iz in range(-ring, ring + 1):
                            if max(abs(ix), abs(iz)) != ring:
                                continue
                            if cancelled is not None and cancelled():
                                return
                            probe_start(
                                aligned, center_x + ix * x_step,
                                center_z + iz * z_step,
                            )
                            if hits:
                                return

    def scan_late_steering(candidates, max_paths=8):
        """Try a short stick or camera correction where the coarse route nearly crossed."""
        selected = []
        seen = set()
        for item in sorted(candidates, key=lambda candidate: candidate.score):
            key = (item.start_pos, item.row["stickX"], item.row["stickY"],
                   item.phase, item.frame)
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= max_paths:
                break
        steering_near = []
        edits = {
            "stickX": (-4, -2, -1, 1, 2, 4),
            "stickY": (-4, -2, -1, 1, 2, 4),
            "substickX": (-32, -16, -8, 8, 16, 32),
        }
        for item in selected:
            if cancelled is not None and cancelled():
                return
            try:
                base = _exit_first_person(
                    _start_node(item.start_pos, item.start_facing, context, 1.0,
                                settle_frames, object_type), settle_frames,
                )
            except (ValueError, RuntimeError):
                continue
            for axis, deltas in edits.items():
                for delta in deltas:
                    switch_row = dict(item.row)
                    switch_row[axis] = max(0, min(255, switch_row[axis] + delta))
                    if switch_row[axis] == item.row[axis]:
                        continue
                    for duration in (3, 5):
                        switch_frame = max(1, item.frame - duration + 1)
                        prefix, trajectory, eligible = trace_route(
                            base, item.row, switch_frame=switch_frame,
                            switch_row=switch_row, frame_limit=item.frame + 1,
                        )
                        closer = scan_trajectory(
                            prefix, trajectory, eligible, (item.phase,),
                            item.start_pos, item.start_facing, item.bearing,
                            item.magnitude, item.row, record_near=True,
                            only_frame=item.frame, switch_frame=switch_frame,
                            switch_row=switch_row,
                        )
                        if closer is not None:
                            steering_near.append(closer)
                        if hits:
                            return
        near.extend(steering_near)
        refine_nearby(steering_near, max_paths=16)

    def finish_anchor_batch(anchor_index, grid_index, batch_start):
        if (grid_index < 0
                and ((anchor_index + 1) % 8 == 0
                     or anchor_index + 1 == len(witness_anchors))):
            batch = near[batch_start:]
            refine_nearby(batch)
            if not hits:
                scan_late_steering(batch)
        elif (grid_index >= 0
              and ((grid_index + 1) % 32 == 0
                   or anchor_index + 1 == len(anchors))):
            refine_nearby(near[batch_start:], max_paths=8)
        return bool(hits)
    # Refine the geometrically direct approach with a small fan of directions;
    # magnitudes use the engine's analog movement model, not a displacement table.
    route_offsets = (-3072, -2048, -1024, 0, 1024, 2048, 3072)
    routes = [(offset, magnitude) for offset in route_offsets for magnitude in magnitudes]
    total = len(anchors) * len(routes)
    completed = 0
    batch_start = 0
    for anchor_index, (_radius, _polar, start_pos, start_facing) in enumerate(anchors):
        if cancelled is not None and cancelled():
            return hits[:max_results]
        grid_index = anchor_index - len(witness_anchors)
        if ((grid_index < 0 and anchor_index % 8 == 0)
                or (grid_index >= 0 and grid_index % 32 == 0)):
            batch_start = len(near)
        try:
            base = _start_node(
                start_pos, start_facing, context, 1.0, settle_frames, object_type
            )
            base = _exit_first_person(base, settle_frames)
        except (ValueError, RuntimeError):
            completed += len(routes)
            if finish_anchor_batch(anchor_index, grid_index, batch_start):
                break
            continue
        direct = world_angle_s16(
            context.seam_target[0] - start_pos[0],
            context.seam_target[2] - start_pos[2],
        ) & 0xFFFF
        unique_routes = {}
        for offset, magnitude in routes:
            bearing = (direct + offset) & 0xFFFF
            row = _walk_row(bearing, base.state.csangle, float(magnitude))
            unique_routes.setdefault((row["stickX"], row["stickY"]), (bearing, magnitude, row))
        for bearing, magnitude, row in unique_routes.values():
            if cancelled is not None and cancelled():
                return hits[:max_results]
            prefix, trajectory, eligible = trace_route(base, row)
            candidate_near = scan_trajectory(
                prefix, trajectory, eligible, coarse_phases,
                start_pos, start_facing, bearing, magnitude, row,
                record_near=True,
            )
            if candidate_near is not None:
                near.append(candidate_near)
            completed += 1
            if progress is not None and completed % 8 == 0:
                progress(completed, total, tested, len(hits))
        if finish_anchor_batch(anchor_index, grid_index, batch_start):
            break
    if not hits and near:
        near.sort(key=lambda item: item.score)
        selected = []
        seen = set()
        for item in near:
            key = (item.start_pos, item.start_facing,
                   item.row["stickX"], item.row["stickY"],
                   item.switch_frame,
                   None if item.switch_row is None else (
                       item.switch_row["stickX"], item.switch_row["stickY"],
                       item.switch_row["substickX"],
                   ))
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= 24:
                break
        remaining_phases = ()
        for rank, item in enumerate(selected, 1):
            if cancelled is not None and cancelled():
                return hits[:max_results]
            start_pos, start_facing = item.start_pos, item.start_facing
            bearing, magnitude, row = item.bearing, item.magnitude, item.row
            try:
                base = _exit_first_person(
                    _start_node(start_pos, start_facing, context, 1.0,
                                settle_frames, object_type), settle_frames,
                )
            except (ValueError, RuntimeError):
                continue
            prefix, trajectory, eligible = trace_route(
                base, row, switch_frame=item.switch_frame,
                switch_row=item.switch_row,
            )
            if remaining_phases:
                finer = scan_trajectory(
                    prefix, trajectory, eligible, remaining_phases,
                    start_pos, start_facing, bearing, magnitude, row,
                    record_near=True,
                    switch_frame=item.switch_frame, switch_row=item.switch_row,
                )
                if finer is not None:
                    near.append(finer)
            if hits:
                break
            if progress is not None:
                progress(total + rank, total + len(selected), tested, len(hits))
        if not hits:
            refine_nearby(near, max_paths=24)
        if not hits:
            scan_late_steering(near)
    hits.sort(key=lambda item: (
        item["b_index"],
        -item["retained_depth"],
        item["seam_distance"] if require_oob_landing else 0.0,
        -item["speed"],
    ))
    return hits[:max_results]
