"""Prepare a live, carried-object start and record a matching moving-drop DTM."""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import time

from harness.collision.find_drop_push_candidate import prepare_search
from harness.collision.live_moving_drop import GRAB_WAIT, _snapshot, _stop_active_recording
from harness.collision.room_collision import load_live_room_collision
from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import (
    _SUBJECTIVITY_ENTRY_ROWS,
    _teleport_and_step,
    _write_subjectivity_pose_paused,
    open_dolphin,
    read_state,
)


def _same_f32(actual, expected):
    return struct.pack(">f", actual) == struct.pack(">f", expected)


def _save_state_ready(control, path, timeout=10.0):
    """Wait for Dolphin's asynchronous save, including compressed savestates."""
    path = Path(path)
    path.unlink(missing_ok=True)
    control.pause()
    control.save_state(str(path))
    deadline = time.monotonic() + timeout
    previous = None
    stable_since = None
    while time.monotonic() < deadline:
        try:
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            signature = None
        now = time.monotonic()
        if signature is not None and signature[0] > 1024:
            if signature == previous:
                if stable_since is not None and now - stable_since >= 0.5:
                    return
            else:
                stable_since = now
        else:
            stable_since = None
        previous = signature
        time.sleep(0.1)
    raise RuntimeError("Dolphin did not finish writing savestate %s" % path)


def _check_prepared(snapshot, result, grab_actor):
    expected = result["start_pos"]
    actual = (snapshot.x, snapshot.y, snapshot.z)
    if snapshot.state != 1 or snapshot.grab_actor != grab_actor:
        raise RuntimeError("first-person preparation lost the carried object")
    if not _same_f32(snapshot.upper_frame, 0.0) or not _same_f32(snapshot.upper_rate, 0.0):
        raise RuntimeError("first-person carried upper animation is not at its fixed frame 0")
    if not all(_same_f32(a, e) for a, e in zip(actual, expected)):
        raise RuntimeError(
            "prepared first-person coordinates drifted to %r (wanted %r)"
            % (actual, tuple(expected))
        )
    if snapshot.facing != int(result["start_facing"]):
        raise RuntimeError(
            "prepared facing drifted to %d (wanted %d)"
            % (snapshot.facing, result["start_facing"])
        )


def _playback_rows(result):
    rows = [dict(row) for row in result["rows"]]
    b_index = int(result["b_index"])
    if not rows or not 0 <= b_index < len(rows):
        raise ValueError("moving-drop result has no valid B input row")
    if not int(rows[b_index].get("buttons", 0)) & 0x0200:
        raise ValueError("moving-drop result does not press B at its reported row")
    follow = dict(rows[-1])
    follow["buttons"] = int(follow.get("buttons", 0)) & ~0x0200
    rows.extend(dict(follow) for _ in range(4))
    return rows


def _prepare_start(control, reader, result, grab_actor, log):
    if _snapshot(reader, 0).state == 1:
        for _ in range(15):
            if _snapshot(reader, 0).state != 1:
                break
            control.advance_with(substickY=0, frames=1)
    for _ in range(90):
        snap = _snapshot(reader, 0)
        if snap.grab_actor != grab_actor:
            raise RuntimeError("Link released the held object before preparation")
        if snap.state == GRAB_WAIT:
            break
        control.advance_with(substickY=128, frames=1)
    else:
        raise RuntimeError("Link did not settle into GRAB_WAIT while carrying the object")

    x, y, z = result["start_pos"]
    facing = int(result["start_facing"])
    _teleport_and_step(reader, control, x, y, z, facing)
    if _snapshot(reader, 0).grab_actor != grab_actor:
        raise RuntimeError("Link lost the held object while teleporting")

    control.command("clearinput")
    for sx, sy, csx, csy, buttons, trigger_l in _SUBJECTIVITY_ENTRY_ROWS:
        control.advance_with(
            stickX=sx, stickY=sy, substickX=csx, substickY=csy,
            buttons=buttons, triggerL=trigger_l, frames=1,
        )
    snap = _snapshot(reader, 0)
    if snap.state != 1 or snap.grab_actor != grab_actor:
        raise RuntimeError(
            "Link did not enter first person while holding the object "
            "(state=%d, held=%s)" % (snap.state, bool(snap.grab_actor))
        )

    # Entering first person can update the camera and heading, so reapply the
    # requested pose before checking that subsequent game frames preserve it.
    _write_subjectivity_pose_paused(reader, x, y, z, facing)
    for _ in range(4):
        control.advance_with(substickY=128, frames=1)
    snap = _snapshot(reader, 0)
    if snap.state != 1 or snap.grab_actor != grab_actor:
        raise RuntimeError("Link left first person or lost the object after teleporting")
    if not all(_same_f32(a, e) for a, e in zip((snap.x, snap.y, snap.z), (x, y, z))):
        raise RuntimeError("teleport was corrected by nearby collision; this start cannot be exported")
    if snap.facing != facing:
        raise RuntimeError(
            "first-person camera changed facing to %d (wanted %d)" % (snap.facing, facing)
        )

    _check_prepared(snap, result, grab_actor)
    log(
        "Prepared first-person pose; live upper grabwait frame=%.3f rate=%.3f "
        "(solver assumed phase %d)"
        % (snap.upper_frame, snap.upper_rate, result["start_animation_phase"])
    )
    return snap


def _record_movie(control, reader, result, grab_actor, workdir, output, log):
    frame0 = workdir / "frame0.sav"
    probe = workdir / "frame0_probe.dtm"
    movie = workdir / "recorded.dtm"
    control.command("recordstart", {"path": probe.as_posix()})
    time.sleep(0.4)
    if not control.command("status").get("recording"):
        raise RuntimeError("Dolphin did not start the frame-zero recording")
    _save_state_ready(control, frame0)
    control.command("recordstop", {"path": probe.as_posix()})
    time.sleep(0.4)

    control.command("recordstart", {"path": movie.as_posix()})
    time.sleep(0.4)
    if not control.command("status").get("recording"):
        raise RuntimeError("Dolphin did not start recording the clip inputs")
    _check_prepared(_snapshot(reader, 0), result, grab_actor)
    rows = _playback_rows(result)
    seam = tuple(result["seam"])
    region, _live, _bg = load_live_room_collision(reader.pid)
    context = prepare_search(
        region,
        (seam[0] - 180, seam[0] + 180, seam[1] - 260, seam[1] + 260,
         seam[2] - 180, seam[2] + 180),
        seam,
    )
    trace = []
    detached = False
    detach_index = None
    b_old = None
    for index, row in enumerate(rows):
        previous = _snapshot(reader, index)
        control.advance_with(frames=1, **row)
        snap = _snapshot(reader, index + 1)
        if index == int(result["b_index"]):
            b_old = (snap.x, snap.y, snap.z)
        if previous.grab_actor and not snap.grab_actor:
            detached = True
            detach_index = index
        pos = (snap.x, snap.y, snap.z)
        trace.append({
            "row": index, "pos": pos, "facing": snap.facing,
            "held": bool(snap.grab_actor),
            "speed": snap.speed_f,
            "prop_pos": snap.prop_pos,
            "link_co_center": snap.link_co_center,
            "cc_move": snap.cc_move,
            "lower_frames": snap.lower_frames,
            "upper_frames": snap.upper_frames,
            "depth": min(-context.wall_a.pla.func(pos), -context.wall_b.pla.func(pos)),
        })
    control.command("recordstop", {"path": movie.as_posix()})
    time.sleep(0.5)
    if not movie.is_file() or not frame0.is_file():
        raise RuntimeError("Dolphin did not write the movie and its starting state")
    if movie.read_bytes()[:10] != b"DTM\x1a" + reader.read_bytes(0x80000000, 6):
        raise RuntimeError("recorded movie header does not match the active game")

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(movie, output)
    shutil.copy2(frame0, str(output) + ".sav")
    shutil.copy2(movie, str(output) + ".sav.dtm")
    log("Recorded %d game input rows to %s" % (len(rows), output))
    live_verified = _clip_verified(trace, detach_index)
    predicted_old = result["old"]
    old_error = None if b_old is None else math.dist(b_old, predicted_old)
    diagnostics = {
        "live_verified": live_verified,
        "max_depth": max(item["depth"] for item in trace),
        "final_depth": trace[-1]["depth"],
        "detached": detached,
        "detach_row": detach_index,
        "b_old": b_old,
        "predicted_old_error": old_error,
        "trace": trace,
        "predicted_old": result["old"],
        "predicted_resolved": result["resolved"],
    }
    Path(str(output) + ".json").write_text(json.dumps(diagnostics, indent=2), encoding="ascii")
    return str(output), str(output) + ".sav", len(rows), diagnostics


def _clip_verified(trace, detach_index):
    if detach_index is None or not trace:
        return False
    after_drop = trace[detach_index:]
    return any(item["depth"] > 0.0 for item in after_drop) and after_drop[-1]["depth"] > 0.0


def export_moving_drop_with_state(pid, result, output, game_id,
                                  allow_recording_stop=False, log=lambda _text: None):
    """Leave Dolphin at the prepared start; restore the original state on failure."""
    control = DolphinControl(pid)
    status = control.command("status")
    if status.get("playing"):
        raise RuntimeError("Stop Dolphin movie playback before exporting a matching state")
    if status.get("recording") and not allow_recording_stop:
        raise RuntimeError(
            "Stop the active Dolphin movie before export. Its recording/playback was not changed."
        )
    output = Path(output).resolve()
    generated = Path(__file__).resolve().parents[2] / "_generated" / "moving_drop_export"
    generated.mkdir(parents=True, exist_ok=True)
    recording_backup = None
    if status.get("recording"):
        recording_backup = _stop_active_recording(control, generated, log=log)
    control.pause()
    reader = None
    try:
        reader = open_dolphin(pid, writable=True)
        live = read_state(reader)
        actual_id = reader.read_bytes(0x80000000, 6)
        if actual_id != game_id:
            raise RuntimeError(
                "DTM game ID %s does not match Dolphin's %s"
                % (game_id.decode("ascii"), actual_id.decode("ascii", "replace"))
            )
        if live.stage != result.get("stage") or live.room != result.get("room"):
            raise RuntimeError(
                "Dolphin is in %s room %d, but this result uses %s room %s"
                % (live.stage, live.room, result.get("stage"), result.get("room"))
            )
        snap = _snapshot(reader, 0)
        if not snap.grab_actor:
            raise RuntimeError("Link must already be carrying the selected bomb or small pot")
        grab_actor = snap.grab_actor
        held_type = reader.u16(grab_actor + 8)
        expected_type = {"bomb": 0x128, "pot_small": 0x1CB}.get(result.get("object_type"))
        if expected_type is None or held_type != expected_type:
            raise RuntimeError(
                "selected %s does not match Link's held actor 0x%03X"
                % (result.get("object_type"), held_type)
            )
        with tempfile.TemporaryDirectory(prefix="export-", dir=generated) as temp:
            workdir = Path(temp)
            original = workdir / "original.sav"
            prepared = workdir / "prepared.sav"
            _save_state_ready(control, original)
            try:
                _prepare_start(control, reader, result, grab_actor, log)
                _save_state_ready(control, prepared)
                control.load_state(str(prepared))
                time.sleep(0.35)
                control.pause()
                _check_prepared(_snapshot(reader, 0), result, grab_actor)
                log("Saved the matching first-person starting state")
                movie, state, row_count, diagnostics = _record_movie(
                    control, reader, result, grab_actor, workdir, output, log
                )
                control.pause()
                control.load_state(str(prepared))
                time.sleep(0.35)
                control.pause()
                _check_prepared(_snapshot(reader, 0), result, grab_actor)
                return {
                    "movie": movie, "movie_state": state,
                    "rows": row_count,
                    "live_verified": diagnostics["live_verified"],
                    "max_depth": diagnostics["max_depth"],
                    "final_depth": diagnostics["final_depth"],
                    "recording_backup": str(recording_backup) if recording_backup else None,
                }
            except Exception:
                try:
                    if control.command("status").get("recording"):
                        control.command(
                            "recordstop", {"path": (workdir / "failed_recording.dtm").as_posix()}
                        )
                    control.pause()
                    control.load_state(str(original))
                    time.sleep(0.35)
                    control.pause()
                except Exception as restore_error:
                    raise RuntimeError(
                        "Export failed and Dolphin could not restore the original state: %s"
                        % restore_error
                    ) from restore_error
                raise
    except Exception as exc:
        if recording_backup:
            raise RuntimeError(
                "%s\nOriginal recording was backed up to %s"
                % (exc, recording_backup)
            ) from exc
        raise
    finally:
        if reader is not None:
            reader.close()
