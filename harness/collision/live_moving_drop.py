"""Capture an exact moving-pot seed, then solve the clip in the binary32 model.

Dolphin is used for one deterministic prelude only: buffered full-stick input
through the captured sidehop and its early landing exit. The resulting cruise
state preserves controller latency and both animation layers. Candidate steering
and B timing are searched offline; the old replay search remains opt-in solely
as a diagnostic comparison.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
import struct
import time

from harness.collision.find_drop_push_candidate import prepare_search
from harness.collision.room_collision import load_live_room_collision
from harness.dolphin_control import DolphinControl
from harness.dtm.writer import build_dtm_from_sticks, install_savestate_companions
from harness.rollstab.live_slash import open_dolphin, read_state
from harness.rollstab.rest import dtm_stick
from tww_sim.land.plan_land import stick_for_bearing, world_angle_s16


BUTTON_B = 0x0200
SIDE_STEP = 0x0A
SIDE_STEP_LAND = 0x0B
MOVE = 0x06
GRAB_WAIT = 0x73
GRAB_ID_OFFSET = -0xD8 + 0x318C
GRAB_ACTOR_OFFSET = -0xD8 + 0x3190
ACTOR_PTR = 0x803BD910
FOOT_OFFSETS = (0x3CF8, 0x3E10, 0x3CEC, 0x3E04)
FOOT024_OFFSETS = (0x3D04, 0x3E1C)
FOOT001_OFFSETS = (0x3CE1, 0x3DF9)


@dataclass(frozen=True)
class DropSnapshot:
    frame: int
    x: float
    y: float
    z: float
    facing: int
    travel: int
    camera: int
    state: int
    speed_f: float
    normal_speed: float
    animation_frame: float
    stick_distance: float
    equip_item: int
    sword_drawn: bool
    grab_id: int
    grab_actor: int
    prop_pos: tuple[float, float, float] | None
    hand_mid: tuple[float, float, float]
    link_co_center: tuple[float, float, float]
    link_co_radius: float
    link_co_height: float
    link_old_pos: tuple[float, float, float]
    cc_move: tuple[float, float, float]
    lower_ratio: float
    lower_frames: tuple[float, float]
    lower_rates: tuple[float, float]
    lower_blend_ratio: float
    shape_z: int
    body_angles: tuple[int, int, int]
    root_tilt: tuple[int, int]
    joint_positions: tuple[tuple[float, float, float], ...]
    joint_matrices: tuple[tuple[float, ...], ...]
    foot_delta: float
    previous_stick_distance: float
    stick_local_angle: int
    target_angle: int
    upper_frame: float
    upper_rate: float
    upper_frames: tuple[float, float, float]
    upper_rates: tuple[float, float, float]
    upper_anim_ptrs: tuple[int, int, int]
    upper_ratios: tuple[float, float, float]


@dataclass
class ReleaseTrial:
    aim_offset: float
    b_row: int
    release_frame: int
    release_old: tuple[float, float, float]
    deepest: tuple[float, float, float]
    final: tuple[float, float, float]
    depth: float
    final_depth: float
    speed_at_release: float
    facing_at_release: int
    rows: list[dict]


def _snapshot(reader, frame: int) -> DropSnapshot:
    state = read_state(reader)
    player = state.player
    grab_id = reader.u32(player + GRAB_ID_OFFSET)
    grab_actor = reader.u32(player + GRAB_ACTOR_OFFSET)
    actor = reader.u32(ACTOR_PTR)
    left = tuple(reader.f32(actor + 0x2D4 + 4 * i) for i in range(3))
    right = tuple(reader.f32(actor + 0x2E0 + 4 * i) for i in range(3))
    hand_mid = tuple((left[i] + right[i]) * 0.5 for i in range(3))
    # daPy_lk_c::mCyl is at class+0x4024. Its embedded cM3dGCyl geometry starts
    # at class+0x413C in the JP player layout (center, radius, height). Reading
    # the collision primitive avoids reconstructing a mid-morph layered pose.
    link_co_center = tuple(reader.f32(actor + 0x413C + 4 * i) for i in range(3))
    link_co_radius = reader.f32(actor + 0x4148)
    link_co_height = reader.f32(actor + 0x414C)
    link_old_pos = tuple(reader.f32(actor + 0x1E4 + 4 * i) for i in range(3))
    cc_move = tuple(reader.f32(actor + 0x3FE8 + 4 * i) for i in range(3))
    prop_pos = None
    if 0x80000000 <= grab_actor < 0x81800000:
        prop_pos = tuple(reader.f32(grab_actor + 0x1F8 + 4 * i) for i in range(3))
    model = reader.u32(player + 0x254)
    joint_base = reader.u32(model + 0x8C) if 0x80000000 <= model < 0x81800000 else 0
    joint_positions = ()
    joint_matrices = ()
    if 0x80000000 <= joint_base < 0x81800000:
        joint_matrices = tuple(
            tuple(reader.f32(joint_base + joint * 0x30 + component * 4)
                  for component in range(12))
            for joint in range(42)
        )
        joint_positions = tuple(
            (matrix[3], matrix[7], matrix[11]) for matrix in joint_matrices
        )
    return DropSnapshot(
        frame=frame,
        x=state.x,
        y=state.y,
        z=state.z,
        facing=state.facing,
        travel=state.travel,
        camera=state.csangle,
        state=state.state,
        speed_f=state.speedF,
        normal_speed=state.nspeed,
        animation_frame=state.animation_frame,
        stick_distance=state.stick_distance,
        equip_item=state.equip_item,
        sword_drawn=state.sword_drawn,
        grab_id=grab_id,
        grab_actor=grab_actor,
        prop_pos=prop_pos,
        hand_mid=hand_mid,
        link_co_center=link_co_center,
        link_co_radius=link_co_radius,
        link_co_height=link_co_height,
        link_old_pos=link_old_pos,
        cc_move=cc_move,
        lower_ratio=reader.f32(player + 0x34C0),
        lower_frames=(reader.f32(player + 0x2F64), reader.f32(player + 0x2F78)),
        lower_rates=(reader.f32(player + 0x2F60), reader.f32(player + 0x2F74)),
        lower_blend_ratio=reader.f32(player + 0x2EE4),
        shape_z=reader.s16(actor + 0x210),
        body_angles=tuple(reader.s16(actor + 0x2B4 + component * 2)
                          for component in range(3)),
        root_tilt=(reader.s16(actor + 0x34F2), reader.s16(actor + 0x34F4)),
        joint_positions=joint_positions,
        joint_matrices=joint_matrices,
        foot_delta=reader.f32(player + 0x34C4),
        previous_stick_distance=reader.f32(player + 0x34DC),
        stick_local_angle=reader.u16(player + 0x3404),
        target_angle=reader.u16(player + 0x3410),
        upper_frame=reader.f32(actor + 0x308C),
        upper_rate=reader.f32(actor + 0x3088),
        upper_frames=tuple(reader.f32(actor + 0x3064 + slot * 0x14) for slot in range(3)),
        upper_rates=tuple(reader.f32(actor + 0x3060 + slot * 0x14) for slot in range(3)),
        upper_anim_ptrs=tuple(reader.u32(actor + 0x2FC8 + slot * 8) for slot in range(3)),
        upper_ratios=tuple(reader.f32(actor + 0x2FC4 + slot * 8) for slot in range(3)),
    )


def _depth(context, pos) -> float:
    """Positive distance means the point is behind both incident seam walls."""
    return min(-context.wall_a.pla.func(pos), -context.wall_b.pla.func(pos))


def _front(context, pos) -> bool:
    return context.wall_a.pla.func(pos) > 0.0 and context.wall_b.pla.func(pos) > 0.0


def _row_for_target(snapshot: DropSnapshot, target_x: float, target_z: float,
                    buttons: int = 0) -> dict:
    bearing = world_angle_s16(target_x - snapshot.x, target_z - snapshot.z)
    return _row_for_bearing(snapshot.camera, bearing, buttons)


def _row_for_bearing(camera: int, bearing: int, buttons: int = 0) -> dict:
    sx, sy = dtm_stick(stick_for_bearing(bearing, camera, 1.0))
    return {
        "stickX": sx,
        "stickY": sy,
        "substickX": 128,
        "substickY": 128,
        "buttons": buttons,
        "triggerL": 0,
        "triggerR": 0,
    }


def _signed_angle_delta(target: int, current: int) -> int:
    return ((int(target) - int(current) + 0x8000) & 0xFFFF) - 0x8000


def _takeover_bearing(snapshot: DropSnapshot, seam) -> tuple[int, int]:
    """Nearest seam-directed bearing that cannot trigger the zero-speed reversal pivot."""
    land_travel = (snapshot.travel + 0x8000) & 0xFFFF
    desired = world_angle_s16(seam[0] - snapshot.x, seam[2] - snapshot.z)
    delta = _signed_angle_delta(desired, land_travel)
    # Game gate is strictly >0x7800. Leave 0x100 s16 clearance for stick inverse quantization.
    delta = max(-0x7700, min(0x7700, delta))
    return (land_travel + delta) & 0xFFFF, land_travel


def _advance(control: DolphinControl, row: dict) -> dict:
    return control.advance_with(frames=1, **row)


def _replay(control: DolphinControl, rows: list[dict]) -> None:
    for row in rows:
        _advance(control, row)


def _load_state_settled(control: DolphinControl, path: Path | str) -> None:
    """Load a standalone state and wait for Dolphin's async load to commit."""
    control.pause()
    control.load_state(str(path))
    time.sleep(0.35)
    control.pause()


def _save_state_settled(control: DolphinControl, path: Path | str) -> None:
    """Save a state and let Dolphin finish its asynchronous compression/write."""
    control.pause()
    control.save_state(str(path))
    time.sleep(0.75)
    control.pause()


def _stop_active_recording(control: DolphinControl, output_dir: Path, log=print) -> Path | None:
    """Savestate anchors cannot be loaded reliably while a movie is attached."""
    status = control.command("status")
    if status.get("playing"):
        raise RuntimeError("stop Dolphin movie playback before capturing a moving-drop anchor")
    if not status.get("recording"):
        return None
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    backup = output_dir / time.strftime("pre_capture_recording_%Y%m%d_%H%M%S.dtm")
    control.command("recordstop", {"path": str(backup).replace("\\", "/")})
    time.sleep(0.35)
    if control.command("status").get("recording"):
        raise RuntimeError("Dolphin did not stop the active movie recording")
    log(f"Saved and stopped the active movie recording at {backup}")
    return backup


def export_native_candidate(pid: int, candidate_path: Path, output_movie: Path | None = None,
                            *, start_state: Path | None = None, camera_hold_y: int = 99,
                            log=print):
    """Record solved rows into a playback-faithful frame-0 DTM.

    Synthetic DTMs cannot safely inherit a deep TAS savestate's movie counters or
    controller-poll phase.  This path uses Dolphin's recorder to mint both pieces:
    a frame-0 state from the exact candidate start and the native input stream.
    """
    candidate_path = Path(candidate_path)
    candidate = json.loads(candidate_path.read_text(encoding="ascii"))
    payload = candidate.get("best", candidate)
    rows = [dict(row) for row in payload["rows"]]
    for row in rows:
        row["substickY"] = max(0, min(255, int(camera_hold_y)))

    source_state = start_state
    if source_state is None:
        for owner in (payload, candidate):
            value = owner.get("base_state") or owner.get("movie_state")
            if value:
                source_state = Path(value)
                break
    if source_state is None or not Path(source_state).is_file():
        raise RuntimeError("candidate does not identify a usable starting savestate")

    output_movie = Path(output_movie or candidate_path.with_name("moving_pot_clip_native.dtm"))
    output_movie.parent.mkdir(parents=True, exist_ok=True)
    frame0_state = output_movie.with_name(output_movie.name + ".frame0.sav")
    restore_state = output_movie.with_name(output_movie.name + ".restore.sav")
    frame0_probe = output_movie.with_name(output_movie.name + ".frame0_probe.dtm")

    control = DolphinControl(pid)
    control.pause()
    _stop_active_recording(control, output_movie.parent, log)
    _load_state_settled(control, source_state)
    _stop_active_recording(control, output_movie.parent, log)
    reader = open_dolphin(pid)
    try:
        start = _snapshot(reader, 0)
        if not start.grab_actor:
            raise RuntimeError("native export start is not carrying a droppable object")
        game_id = reader.read_bytes(0x80000000, 6).decode("ascii")

        # Recordstart resets the movie cursor. Save after that reset, then stop
        # before advancing; advancing immediately after an asynchronous state
        # compression can restart this TAS Edition build.
        control.command("recordstart", {"path": str(frame0_probe).replace("\\", "/")})
        time.sleep(0.4)
        if not control.command("status").get("recording"):
            raise RuntimeError("Dolphin did not start the frame-0 probe recording")
        _save_state_settled(control, frame0_state)
        control.command("recordstop", {"path": str(frame0_probe).replace("\\", "/")})
        time.sleep(0.5)
        _save_state_settled(control, restore_state)

        control.command("recordstart", {"path": str(output_movie).replace("\\", "/")})
        time.sleep(0.4)
        if not control.command("status").get("recording"):
            raise RuntimeError("Dolphin did not start the candidate recording")
        for row in rows:
            _advance(control, row)
        end = _snapshot(reader, len(rows))
        control.command("recordstop", {"path": str(output_movie).replace("\\", "/")})
        time.sleep(0.6)

        shutil.copy2(frame0_state, str(output_movie) + ".sav")
        shutil.copy2(output_movie, str(output_movie) + ".sav.dtm")

        seam = tuple(candidate.get("seam", payload.get("seam", ())))
        retained_depth = None
        if len(seam) == 3:
            region, _live, _bg = load_live_room_collision(pid, status=lambda _text: None)
            x, y, z = seam
            context = prepare_search(
                region,
                (x - 180.0, x + 180.0, y - 260.0, y + 260.0,
                 z - 180.0, z + 180.0),
                seam,
            )
            retained_depth = _depth(context, (end.x, end.y, end.z))
        if end.grab_actor:
            raise RuntimeError("native candidate never released the held object")
        if retained_depth is not None and retained_depth <= 0.0:
            raise RuntimeError(
                f"native candidate ended outside the seam (depth={retained_depth:+.9f})"
            )

        result = {
            "candidate": str(candidate_path),
            "movie": str(output_movie),
            "movie_state": str(output_movie) + ".sav",
            "game_id": game_id,
            "camera_hold_y": int(camera_hold_y),
            "rows": rows,
            "start": asdict(start),
            "end": asdict(end),
            "retained_depth": retained_depth,
            "verification": "native_recording_endpoint",
        }
        output_movie.with_suffix(".json").write_text(
            json.dumps(result, indent=2), encoding="ascii"
        )
        log(
            "Native DTM recorded from frame 0: end=(%.9f, %.9f), depth=%s"
            % (end.x, end.z, "n/a" if retained_depth is None else f"{retained_depth:.9f}")
        )
        return result
    finally:
        try:
            if control.command("status").get("recording"):
                control.command(
                    "recordstop",
                    {"path": str(output_movie.with_name(output_movie.name + ".failed.dtm")).replace("\\", "/")},
                )
            if restore_state.is_file():
                _load_state_settled(control, restore_state)
        finally:
            reader.close()


def _capture_release_probe(control, reader, base_state, rows, prop_actor):
    """Replay one modeled B timing and record exact collision primitives.

    This is a calibration trace for the chosen deterministic route, not a
    candidate search. At a state after N rows, raw row N-3 is the B edge that
    acts on that execute under the two-row controller pipeline.
    """
    if len(rows) < 4:
        return None
    replay_rows = [dict(row) for row in rows]
    b_index = len(replay_rows) - 3
    replay_rows[b_index]["buttons"] = replay_rows[b_index].get("buttons", 0) | BUTTON_B
    follow = dict(replay_rows[-1])
    follow["buttons"] = 0
    replay_rows.extend([dict(follow) for _ in range(3)])

    _load_state_settled(control, base_state)
    frames = []
    keep_from = max(0, b_index - 2)
    for index, row in enumerate(replay_rows):
        response = _advance(control, row)
        if index < keep_from:
            continue
        snap = _snapshot(reader, index + 1)
        prop = None
        prop_old = None
        if 0x80000000 <= prop_actor < 0x81800000:
            prop = tuple(reader.f32(prop_actor + 0x1F8 + 4 * i) for i in range(3))
            prop_old = tuple(reader.f32(prop_actor + 0x1E0 + 4 * i) for i in range(3))
        frames.append({
            "row": index + 1,
            "emu_frame": response.get("frame"),
            "raw_b": index == b_index,
            "snapshot": asdict(snap),
            "released_prop_pos": prop,
            "released_prop_old_pos": prop_old,
        })
    return {"b_index": b_index, "frames": frames}


def probe_exported_candidate(pid: int, candidate_path: Path, output_path: Path | None = None,
                             log=print):
    """Replay one exported offline stream and capture its exact release outcome."""
    candidate = json.loads(Path(candidate_path).read_text(encoding="ascii"))
    payload = candidate.get("best", candidate)
    rows = [dict(row) for row in payload["rows"]]
    b_index = int(payload["b_index"])
    base_state = Path(payload.get("movie_state", candidate["movie_state"]))
    if "seam" in candidate:
        seam = tuple(candidate["seam"])
    else:
        seed = json.loads(
            Path(candidate_path).with_name("moving_pot_early.json").read_text(encoding="ascii")
        )
        seam = tuple(seed["seam"])
    control = DolphinControl(pid)
    control.pause()
    _stop_active_recording(control, Path(candidate_path).parent, log)
    _load_state_settled(control, base_state)
    reader = open_dolphin(pid)
    start = _snapshot(reader, 0)
    prop_actor = start.grab_actor
    follow = dict(rows[-1])
    follow["buttons"] = 0
    replay_rows = rows + [dict(follow) for _ in range(5)]
    frames = []
    try:
        for index, row in enumerate(replay_rows):
            response = _advance(control, row)
            if index < max(0, min(b_index - 2, 9)):
                continue
            snap = _snapshot(reader, index + 1)
            prop = None
            if 0x80000000 <= prop_actor < 0x81800000:
                prop = tuple(reader.f32(prop_actor + 0x1F8 + 4 * i) for i in range(3))
            frames.append({
                "row": index + 1,
                "emu_frame": response.get("frame"),
                "raw_b": index == b_index,
                "snapshot": asdict(snap),
                "released_prop_pos": prop,
            })
        region, _live, _bg = load_live_room_collision(pid, status=lambda _text: None)
        x, y, z = seam
        context = prepare_search(
            region, (x - 180.0, x + 180.0, y - 260.0, y + 260.0,
                     z - 180.0, z + 180.0), seam,
        )
        for frame in frames:
            snap = frame["snapshot"]
            pos = (snap["x"], snap["y"], snap["z"])
            frame["wall_planes"] = (
                context.wall_a.pla.func(pos), context.wall_b.pla.func(pos)
            )
        result = dict(candidate=candidate, frames=frames)
        if output_path is None:
            output_path = Path(candidate_path).with_name("moving_pot_near_live.json")
        Path(output_path).write_text(json.dumps(result, indent=2), encoding="ascii")
        deepest = min(
            (min(frame["wall_planes"]) for frame in frames), default=float("nan")
        )
        log(f"Exact candidate replay captured; deepest incident-plane value={deepest:+.9f}")
        return result
    finally:
        _load_state_settled(control, base_state)
        reader.close()


def _sim_seed(reader, snapshot, rows):
    player = read_state(reader).player
    actor = reader.u32(ACTOR_PTR)
    model = reader.u32(player + 0x254)
    joint_base = reader.u32(model + 0x8C) if 0x80000000 <= model < 0x81800000 else 0
    if not 0x80000000 <= joint_base < 0x81800000:
        raise RuntimeError("Link model joint-matrix pointer is not valid")
    joint_matrices = [
        [reader.f32(joint_base + joint * 0x30 + component * 4) for component in range(12)]
        for joint in range(42)
    ]
    ratio = reader.f32(player + 0x2EE4)
    speed_ratio = abs(snapshot.normal_speed) / 17.0
    if speed_ratio < 0.5:
        move0, move1 = "waits", "walk"
    elif speed_ratio < 1.0:
        move0, move1 = "walk", "dash"
    else:
        move0 = move1 = "dash"
    return {
        "snapshot": asdict(snapshot),
        "rows": rows,
        "lower": {
            "move0": move0,
            "move1": move1,
            "f0": reader.f32(player + 0x2F64),
            "rate0": reader.f32(player + 0x2F60),
            "f1": reader.f32(player + 0x2F78),
            "rate1": reader.f32(player + 0x2F74),
            "ratio": ratio,
            "m3598": reader.f32(player + 0x34C0),
            "m359C": reader.f32(player + 0x34C4),
            "m35B4": reader.f32(player + 0x34DC),
        },
        "upper_grab": {
            "frame": reader.f32(actor + 0x308C),
            "rate": reader.f32(actor + 0x3088),
        },
        "shape_z": reader.s16(actor + 0x210),
        "movement_history": {
            "m34dc": reader.u16(player + 0x3404),
            "m34de": reader.u16(player + 0x3406),
            "m34e6": reader.u16(player + 0x340E),
            "target": reader.u16(player + 0x3410),
            "m34ea": reader.u16(player + 0x3412),
            "m351c": reader.u16(player + 0x3444),
            "direction": reader.u8(player + 0x34B8),
        },
        "feet": [
            reader.f32(player + offset + component * 4)
            for offset in FOOT_OFFSETS for component in range(3)
        ],
        "ground": {
            "m35b8": reader.f32(player + 0x34E0),
            "m35c4": reader.f32(player + 0x34EC),
            "foot024": [
                list(struct.unpack(">3f", reader.read_bytes(player + offset, 12)))
                for offset in FOOT024_OFFSETS
            ],
            "foot001": [reader.u8(player + offset) for offset in FOOT001_OFFSETS],
            "waist": [
                joint_matrices[30][3], joint_matrices[30][7],
                joint_matrices[30][11],
            ],
        },
        # mpCLModel's calculated world matrices preserve the old-frame morph
        # source that is otherwise absent from the public movement state.  A
        # first-moving seed needs this pose for the next two foot draws.
        "joint_matrices": joint_matrices,
        "life": reader.u8(0x803B810B),
        "game_id": reader.read_bytes(0x80000000, 6).decode("ascii"),
    }


def _pose_seed(seed):
    """Keep the exact prior-frame fields consumed by the release pose model."""
    return {
        "snapshot": seed["snapshot"],
        "lower": seed["lower"],
        "upper_grab": seed["upper_grab"],
        "shape_z": seed["shape_z"],
        "movement_history": seed["movement_history"],
        "feet": seed["feet"],
        "joint_matrices": seed["joint_matrices"],
    }


def capture_candidate_anchor(pid: int, candidate_path: Path, anchor_row: int,
                             output_path: Path, log=print):
    """Replay one fixed candidate prefix and capture an exact offline resume seed.

    The candidate's B edge is cleared before replay. ``anchor_row`` is the
    post-execute raw-row count, so an anchor at 19 is captured after rows 0..18.
    This is one deterministic calibration replay, not a live candidate search.
    """
    candidate_path = Path(candidate_path)
    candidate = json.loads(candidate_path.read_text(encoding="ascii"))
    rows = [dict(row) for row in candidate["rows"]]
    if not 2 <= anchor_row <= len(rows):
        raise ValueError(
            f"anchor row must be between 2 and {len(rows)}, got {anchor_row}"
        )
    for row in rows:
        row["buttons"] = int(row.get("buttons", 0)) & ~BUTTON_B

    base_state = Path(candidate["movie_state"])
    seam = tuple(candidate["seam"])
    output_path = Path(output_path)
    anchor_state = output_path.with_suffix(".sav")
    control = DolphinControl(pid)
    control.pause()
    _stop_active_recording(control, output_path.parent, log)
    _load_state_settled(control, base_state)
    reader = open_dolphin(pid)
    try:
        start = _snapshot(reader, 0)
        if not start.grab_actor:
            raise RuntimeError("candidate base state is not carrying a droppable object")

        previous_seed = None
        anchor_seed = None
        trace = []
        for index, row in enumerate(rows[:anchor_row]):
            response = _advance(control, row)
            snapshot = _snapshot(reader, index + 1)
            trace.append({
                "row": index + 1,
                "emu_frame": response.get("frame"),
                "state": snapshot.state,
                "speed_f": snapshot.speed_f,
                "normal_speed": snapshot.normal_speed,
                "x": snapshot.x,
                "y": snapshot.y,
                "z": snapshot.z,
                "facing": snapshot.facing,
                "travel": snapshot.travel,
            })
            frame_seed = _sim_seed(reader, snapshot, rows[:index + 1])
            if index + 1 == anchor_row - 1:
                previous_seed = _pose_seed(frame_seed)
            elif index + 1 == anchor_row:
                anchor_seed = frame_seed

        if anchor_seed is None or previous_seed is None:
            raise RuntimeError("failed to capture both anchor pose frames")
        snapshot = anchor_seed["snapshot"]
        if not snapshot["grab_actor"]:
            raise RuntimeError("the held object detached before the requested anchor row")
        if snapshot["state"] != MOVE:
            raise RuntimeError(
                f"anchor row {anchor_row} is not MOVE (state={snapshot['state']})"
            )

        _save_state_settled(control, anchor_state)
        anchor_seed.update({
            "seed_kind": "exact_moving_anchor",
            "previous": previous_seed,
            "rows": [dict(row) for row in rows[:anchor_row]],
            "seam": list(seam),
            "base_state": str(base_state),
            "anchor_state": str(anchor_state),
            "anchor_row": anchor_row,
            "trace": trace,
            "source_candidate": str(candidate_path),
        })
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(anchor_seed, indent=2), encoding="ascii")
        log(
            "Captured exact row-%d moving anchor: pos=(%.9f, %.9f, %.9f), "
            "speedF=%.9f, normal=%.9f, facing=%d"
            % (anchor_row, snapshot["x"], snapshot["y"], snapshot["z"],
               snapshot["speed_f"], snapshot["normal_speed"], snapshot["facing"])
        )
        return anchor_seed
    finally:
        _load_state_settled(control, base_state)
        reader.close()


def capture_cruise_anchor(pid: int, seam, output_dir: Path, log=print,
                          staging_offset=0x1800, post_cap_frames=1,
                          final_bearing=None, final_switch_row=16,
                          exact_anchor_row=14, stop_after_early=False):
    """Capture the first moving seed and a later full-speed diagnostic seed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base_state = output_dir / "moving_pot_base.sav"
    early_state = output_dir / "moving_pot_early.sav"
    exact_state = output_dir / "moving_pot_exact_anchor.sav"
    cruise_state = output_dir / "moving_pot_cruise.sav"
    control = DolphinControl(pid)
    control.pause()
    _stop_active_recording(control, output_dir, log)
    _save_state_settled(control, base_state)
    reader = open_dolphin(pid)
    rows = []
    try:
        snap = _snapshot(reader, 0)
        if snap.state not in (SIDE_STEP, SIDE_STEP_LAND, GRAB_WAIT) or not snap.grab_actor:
            raise RuntimeError(
                f"capture requires the sidehop, its landing, or post-action GRAB_WAIT; state={snap.state}, "
                f"grab_actor=0x{snap.grab_actor:08X}"
            )
        sx, _sy, sz = seam
        control_started = 0
        start_emu_frame = control.command("status").get("frame")
        first_accel_row = None
        early_seed = None
        trace = []
        previous_pose_seed = None
        cap_frames = 0
        takeover_bearing, land_travel = _takeover_bearing(snap, seam)
        seam_bearing = world_angle_s16(seam[0] - snap.x, seam[2] - snap.z)
        turn_sign = 1 if _signed_angle_delta(takeover_bearing, snap.facing) >= 0 else -1
        staging_bearing = (seam_bearing + turn_sign * int(staging_offset)) & 0xFFFF
        log(
            "Buffered takeover bearing %d around post-sidehop travel %d; staging bearing %d "
            "keeps the accelerating carry clear of the wall." %
            (takeover_bearing, land_travel, staging_bearing)
        )
        for _ in range(60):
            # Buffer the fastest approach immediately. SIDE_STEP ignores ground movement input,
            # while SIDE_STEP_LAND consumes the delivered stick as soon as frame>HIO 1.5.
            if first_accel_row is None:
                bearing = takeover_bearing
            elif final_bearing is not None and len(rows) + 1 >= int(final_switch_row):
                bearing = int(final_bearing) & 0xFFFF
            else:
                bearing = staging_bearing
            row = _row_for_bearing(snap.camera, bearing)
            rows.append(row)
            response = _advance(control, row)
            snap = _snapshot(reader, len(rows))
            trace.append({
                "row": len(rows), "emu_frame": response.get("frame"),
                "state": snap.state, "speed_f": snap.speed_f,
                "normal_speed": snap.normal_speed, "x": snap.x, "y": snap.y, "z": snap.z,
                "facing": snap.facing, "travel": snap.travel, "camera": snap.camera,
            })
            if (first_accel_row is None and snap.state not in (SIDE_STEP, SIDE_STEP_LAND)
                    and snap.normal_speed > 0.0):
                first_accel_row = len(rows)
                log(
                    "First controllable acceleration on row %d / emu frame %s: "
                    "state=%d speed=%.9f pos=(%.9f, %.9f)."
                    % (first_accel_row, response.get("frame"), snap.state,
                       snap.speed_f, snap.x, snap.z)
                )
            player = read_state(reader).player
            m3598 = reader.f32(player + 0x34C0)
            frame_seed = _sim_seed(reader, snap, rows)
            if early_seed is None and first_accel_row == len(rows):
                _save_state_settled(control, early_state)
                early_seed = dict(frame_seed)
                early_seed["rows"] = [dict(item) for item in rows]
                early_seed["previous"] = previous_pose_seed
                early_seed["seam"] = list(seam)
                early_seed["control_start_row"] = control_started
                early_seed["start_emu_frame"] = start_emu_frame
                early_seed["first_accel_row"] = first_accel_row
                early_seed["trace"] = list(trace)
                early_seed["base_state"] = str(base_state)
                early_seed["early_state"] = str(early_state)
                early_path = output_dir / "moving_pot_early.json"
                early_path.write_text(json.dumps(early_seed, indent=2), encoding="ascii")
                log(
                    "Saved first-moving solver seed on row %d; optimization starts with the "
                    "still-pending row %d input."
                    % (first_accel_row, first_accel_row - 1)
                )
                if stop_after_early:
                    return early_seed
            if len(rows) == int(exact_anchor_row):
                if previous_pose_seed is None:
                    raise RuntimeError("exact moving anchor has no prior-frame pose")
                _save_state_settled(control, exact_state)
                exact_seed = dict(frame_seed)
                exact_seed.update({
                    "seed_kind": "exact_moving_anchor",
                    "previous": previous_pose_seed,
                    "rows": [dict(item) for item in rows],
                    "seam": list(seam),
                    "control_start_row": control_started,
                    "start_emu_frame": start_emu_frame,
                    "first_accel_row": first_accel_row,
                    "trace": list(trace),
                    "base_state": str(base_state),
                    "anchor_state": str(exact_state),
                    "anchor_row": len(rows),
                })
                exact_path = output_dir / "moving_pot_exact_anchor.json"
                exact_path.write_text(json.dumps(exact_seed, indent=2), encoding="ascii")
                log(
                    "Saved post-morph exact solver anchor on row %d: "
                    "speedF=%.9f normal=%.9f pos=(%.9f, %.9f)."
                    % (len(rows), snap.speed_f, snap.normal_speed, snap.x, snap.z)
                )
            if (
                snap.state == MOVE
                and snap.normal_speed == 17.0
                and snap.speed_f == 17.0
                and m3598 == 0.0
            ):
                if cap_frames < int(post_cap_frames):
                    cap_frames += 1
                    previous_pose_seed = _pose_seed(frame_seed)
                    continue
                _save_state_settled(control, cruise_state)
                seed = frame_seed
                seed["previous"] = previous_pose_seed
                seed["seam"] = list(seam)
                seed["control_start_row"] = control_started
                seed["start_emu_frame"] = start_emu_frame
                seed["first_accel_row"] = first_accel_row
                seed["trace"] = trace
                seed["base_state"] = str(base_state)
                seed["cruise_state"] = str(cruise_state)
                seed["release_probe"] = _capture_release_probe(
                    control, reader, base_state, rows, snap.grab_actor
                )
                path = output_dir / "moving_pot_cruise.json"
                path.write_text(json.dumps(seed, indent=2), encoding="ascii")
                log(
                    "Captured earliest exact cruise seed on row %d: pos=(%.9f, %.9f, %.9f), "
                    "facing=%d, lower=%.6f, upper=%.6f"
                    % (len(rows), snap.x, snap.y, snap.z, snap.facing,
                       seed["lower"]["f0"], seed["upper_grab"]["frame"])
                )
                return early_seed or seed
            previous_pose_seed = _pose_seed(frame_seed)
        raise RuntimeError("the post-sidehop approach did not reach exact speed 17")
    finally:
        _load_state_settled(control, base_state)
        reader.close()


def solve_from_current_state(pid: int, seam, output_dir: Path, *, max_depth=20,
                             beam_size=5000, object_type="pot_small", log=print):
    """Capture the earliest controllable state and search all movement offline."""
    output_dir = Path(output_dir)
    seed = capture_cruise_anchor(
        pid, seam, output_dir, log=log, stop_after_early=True,
    )
    seed["object_type"] = object_type
    (output_dir / "moving_pot_early.json").write_text(
        json.dumps(seed, indent=2), encoding="ascii"
    )
    from harness.collision.offline_moving_drop import solve
    return solve(
        pid, output_dir / "moving_pot_early.json", output_dir,
        max_depth=max_depth, beam_size=beam_size, log=log,
    )


def _trace_approach(control, reader, base_state, context, seam, offset,
                    max_frames, reach):
    _load_state_settled(control, base_state)
    sx, _sy, sz = seam
    rows = []
    snap = _snapshot(reader, 0)
    # The captured sidehop is a fixed opening.  Do not steer or buffer a walk
    # during either the airborne proc or its landing recovery; take control on
    # the first frame after the action has completely returned to a land proc.
    while snap.state in (SIDE_STEP, SIDE_STEP_LAND):
        if len(rows) >= max_frames:
            return rows, [], (sx, sz)
        row = {
            "stickX": 128, "stickY": 128,
            "substickX": 128, "substickY": 128,
            "buttons": 0, "triggerL": 0, "triggerR": 0,
        }
        rows.append(row)
        _advance(control, row)
        snap = _snapshot(reader, len(rows))

    boundary = snap
    dx, dz = sx - boundary.x, sz - boundary.z
    length = math.hypot(dx, dz) or 1.0
    # Offset the aim point along the approach tangent.  The point is slightly
    # past the seam so a full stick remains held through collision and release.
    tangent_x, tangent_z = dz / length, -dx / length
    target_x = sx + tangent_x * offset + dx / length * 20.0
    target_z = sz + tangent_z * offset + dz / length * 20.0
    gates = []
    for frame in range(len(rows), max_frames):
        if snap.grab_actor == 0 or not (0x80000000 <= snap.grab_actor < 0x81800000):
            break
        row = _row_for_target(snap, target_x, target_z)
        rows.append(row)
        _advance(control, row)
        snap = _snapshot(reader, frame + 1)
        dist = math.hypot(snap.x - sx, snap.z - sz)
        if snap.state == MOVE and _front(context, (snap.x, snap.y, snap.z)) and dist <= reach:
            gates.append((len(rows), snap, dist))
        if dist < 20.0 or (frame > 20 and snap.speed_f < 0.1):
            break
    return rows, gates, (target_x, target_z)


def _test_release(control, reader, base_state, context, prefix, target,
                  aim_offset, post_frames=6):
    _load_state_settled(control, base_state)
    _replay(control, prefix)
    before = _snapshot(reader, len(prefix))
    if before.state != MOVE or not _front(context, (before.x, before.y, before.z)):
        return None

    rows = list(prefix)
    detach = None
    deepest = None
    deepest_depth = -math.inf
    prev = before
    # One B edge followed by uninterrupted full movement.  The controller
    # delay decides the actual release frame; grab_actor clearing identifies it.
    for i in range(post_frames + 3):
        row = _row_for_target(prev, target[0], target[1], BUTTON_B if i == 0 else 0)
        rows.append(row)
        _advance(control, row)
        snap = _snapshot(reader, len(rows))
        if detach is None and prev.grab_actor and not snap.grab_actor:
            detach = (snap.frame, prev)
        if detach is not None:
            depth = _depth(context, (snap.x, snap.y, snap.z))
            if depth > deepest_depth:
                deepest_depth = depth
                deepest = (snap.x, snap.y, snap.z)
        prev = snap

    if detach is None or deepest is None:
        return None
    release_frame, release_old_snap = detach
    final = (prev.x, prev.y, prev.z)
    final_depth = _depth(context, final)
    # A viable moving clip must still be behind collision after several more
    # full-stick frames.  This rejects one-frame seam penetration/pop-outs.
    if deepest_depth <= 0.0 or final_depth <= 0.0:
        return None
    return ReleaseTrial(
        aim_offset=aim_offset,
        b_row=len(prefix),
        release_frame=release_frame,
        release_old=(release_old_snap.x, release_old_snap.y, release_old_snap.z),
        deepest=deepest,
        final=final,
        depth=deepest_depth,
        final_depth=final_depth,
        speed_at_release=release_old_snap.speed_f,
        facing_at_release=release_old_snap.facing,
        rows=rows,
    )


def find_moving_drop(pid: int, seam, output_dir: Path, *, max_frames=48,
                     reach=105.0, offsets=None, log=print):
    offsets = offsets or tuple(float(v) for v in range(-40, 41, 4))
    output_dir.mkdir(parents=True, exist_ok=True)
    base_state = output_dir / "moving_pot_base.sav"
    control = DolphinControl(pid)
    control.pause()
    _stop_active_recording(control, output_dir, log)
    _save_state_settled(control, base_state)

    region, live, _bg = load_live_room_collision(pid, status=log)
    x, y, z = seam
    box = (x - 180.0, x + 180.0, y - 260.0, y + 260.0, z - 180.0, z + 180.0)
    context = prepare_search(region, box, seam)
    reader = open_dolphin(pid)
    try:
        start = _snapshot(reader, 0)
        if start.state != SIDE_STEP:
            raise RuntimeError(f"expected the captured sidehop state 10, got {start.state}")
        if not start.grab_actor:
            raise RuntimeError("Link is not carrying an actor in the captured state")
        log(
            "Captured moving pot start: pos=(%.9f, %.9f, %.9f), travel=%d, "
            "speed=%.9f, camera=%d" %
            (start.x, start.y, start.z, start.travel, start.speed_f, start.camera)
        )

        trials = []
        screened = 0
        for offset in offsets:
            approach_rows, gates, target = _trace_approach(
                control, reader, base_state, context, context.seam_target,
                offset, max_frames, reach,
            )
            if not gates:
                continue
            # Test every plausible raw B row, earliest first.  Duplicate gate
            # lengths are removed because controller delay can make adjacent
            # screen snapshots refer to the same eventual release phase.
            for prefix_len in sorted({item[0] for item in gates}):
                screened += 1
                trial = _test_release(
                    control, reader, base_state, context,
                    approach_rows[:prefix_len], target, offset,
                )
                if trial is not None:
                    trials.append(trial)
                    log(
                        "hit offset=%+.1f B-row=%d release=%d speed=%.6f "
                        "depth=%.6f retained=%.6f" %
                        (offset, trial.b_row, trial.release_frame,
                         trial.speed_at_release, trial.depth, trial.final_depth)
                    )

        if not trials:
            raise RuntimeError(
                f"no live-verified moving pot clip in {screened} release trials"
            )
        # Fastest actual detach wins; retained depth breaks ties, then raw B row.
        trials.sort(key=lambda t: (t.release_frame, -t.final_depth, t.b_row))
        best = trials[0]
        movie = output_dir / "moving_pot_clip.dtm"
        game_id = reader.read_bytes(0x80000000, 6)
        build_dtm_from_sticks(best.rows, str(movie), seed=0, game_id=game_id)
        movie_state = Path(install_savestate_companions(str(movie), str(base_state)))
        result = {
            "pid": pid,
            "stage": live.stage,
            "room": live.room,
            "seam": list(seam),
            "resolved_seam": list(context.seam_target),
            "start": asdict(start),
            "best": asdict(best),
            "tested_release_trials": screened,
            "movie": str(movie),
            "movie_state": str(movie_state),
        }
        result_path = output_dir / "moving_pot_clip.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="ascii")
        log(f"Best moving clip exported to {movie}")
        return result
    finally:
        _load_state_settled(control, base_state)
        reader.close()


def _parse_seam(text: str):
    values = [float(v.strip()) for v in text.split(",")]
    if len(values) != 3:
        raise argparse.ArgumentTypeError("seam must be x,y,z")
    return tuple(values)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--seam", type=_parse_seam)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "_generated" / "moving_drop",
    )
    parser.add_argument("--max-frames", type=int, default=48)
    parser.add_argument("--capture-cruise", action="store_true")
    parser.add_argument("--legacy-live-search", action="store_true")
    parser.add_argument("--max-depth", type=int, default=16)
    parser.add_argument("--beam", type=int, default=5000)
    parser.add_argument("--staging-offset", type=lambda value: int(value, 0), default=0x1800)
    parser.add_argument("--post-cap-frames", type=int, default=1)
    parser.add_argument("--final-bearing", type=lambda value: int(value, 0))
    parser.add_argument("--final-switch-row", type=int, default=16)
    parser.add_argument("--exact-anchor-row", type=int, default=14)
    parser.add_argument("--anchor-candidate", type=Path)
    parser.add_argument("--anchor-row", type=int, default=19)
    parser.add_argument("--anchor-output", type=Path)
    parser.add_argument("--native-export-candidate", type=Path)
    parser.add_argument("--native-output", type=Path)
    parser.add_argument("--start-state", type=Path)
    parser.add_argument("--camera-hold-y", type=int, default=99)
    parser.add_argument("--skip-native-export", action="store_true")
    args = parser.parse_args(argv)
    if args.native_export_candidate:
        export_native_candidate(
            args.pid, args.native_export_candidate, args.native_output,
            start_state=args.start_state, camera_hold_y=args.camera_hold_y,
        )
        return 0
    if args.anchor_candidate:
        output = args.anchor_output or args.output / "moving_pot_exact_anchor.json"
        capture_candidate_anchor(
            args.pid, args.anchor_candidate, args.anchor_row, output,
        )
        return 0
    if args.seam is None:
        parser.error("--seam is required unless --anchor-candidate is used")
    if args.legacy_live_search:
        result = find_moving_drop(
            args.pid, args.seam, args.output, max_frames=args.max_frames
        )
        best = result["best"]
        print(
            "SUCCESS B-row=%d release-frame=%d facing=%d speed=%.9f "
            "old=(%.9f, %.9f, %.9f) final=(%.9f, %.9f, %.9f) retained-depth=%.9f" %
            (best["b_row"], best["release_frame"], best["facing_at_release"],
             best["speed_at_release"], *best["release_old"], *best["final"],
             best["final_depth"])
        )
        return 0
    capture_cruise_anchor(
        args.pid, args.seam, args.output, staging_offset=args.staging_offset,
        post_cap_frames=args.post_cap_frames,
        final_bearing=args.final_bearing, final_switch_row=args.final_switch_row,
        exact_anchor_row=args.exact_anchor_row,
    )
    if args.capture_cruise:
        return 0
    from harness.collision.offline_moving_drop import solve
    result = solve(
        args.pid, args.output / "moving_pot_exact_anchor.json", args.output,
        max_depth=args.max_depth, beam_size=args.beam,
    )
    if not args.skip_native_export:
        native = export_native_candidate(
            args.pid, args.output / "moving_pot_clip_offline.json",
            args.output / "moving_pot_clip_native.dtm",
            start_state=args.output / "moving_pot_base.sav",
            camera_hold_y=args.camera_hold_y,
        )
        result["native_movie"] = native["movie"]
        result["native_movie_state"] = native["movie_state"]
    best = result["best"]
    print(
        "SUCCESS B-row=%d facing=%d speed=%.9f old=(%.9f, %.9f, %.9f) "
        "resolved=(%.9f, %.9f, %.9f) retained-depth=%.9f" %
        (best["b_index"], best["facing"], best["speed"], *best["old"],
         *best["resolved"], best["retained_depth"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
