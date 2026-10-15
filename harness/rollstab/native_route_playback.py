"""Capture the original movie, not an injected approximation of its route."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import struct
import tempfile

from harness.collision.live_moving_drop import (
    _load_state_settled, _save_state_settled, _snapshot, _sim_seed, _pose_seed,
    _stop_active_recording,
)
from harness.dolphin_control import DolphinControl
from harness.rollstab.recorded_route import movie_vi_from_savestate

GAME_FRAME = 0x803E9D34


@contextmanager
def attached_route(control, route, output_dir, log):
    """Load a private state/movie pair and restore the user's paused state on exit."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    control.pause()
    status = control.command("status")
    if status.get("recording"):
        _stop_active_recording(control, output_dir, log)
    with tempfile.TemporaryDirectory(prefix="route_capture_", dir=output_dir) as folder:
        folder = Path(folder)
        restore = folder / "restore.sav"
        _save_state_settled(control, restore)
        start = folder / "start.sav"
        shutil.copy2(route.start_state, start)
        # The base slot's companion often ends at the base cursor. Use the final
        # slot's full movie instead, without editing either user's slot.
        shutil.copy2(route.movie, Path(str(start) + ".dtm"))
        try:
            _load_state_settled(control, start)
            status = control.command("status")
            if not status.get("playing"):
                raise RuntimeError("Dolphin did not attach the route movie in read-only playback; "
                                   "enable Movie > Read-Only Mode and retry")
            if int(status.get("frame", -1)) != route.start_vi:
                raise RuntimeError("route capture loaded the wrong movie cursor, not an invalid route")
            log(f"Attached original DTM at VI {route.start_vi}; no input injection or restart.")
            yield folder
        finally:
            _load_state_settled(control, restore)
            control.pause()


def advance_game_frame(control, reader):
    """Skip lag VIs, but stop immediately after one real TWW update."""
    initial = reader.u32(GAME_FRAME)
    for _ in range(8):
        status = control.command("status")
        if not status.get("playing"):
            raise RuntimeError("the original route movie ended before its final game update")
        control.advance(1)
        frame = reader.u32(GAME_FRAME)
        if frame == (initial + 1) & 0xFFFFFFFF:
            return control.command("status")
        if frame != initial:
            raise RuntimeError("the control pipe skipped a TWW gameplay update during capture")
    raise RuntimeError("the original route did not advance its TWW game-frame counter")


def validate_endpoint(actual, expected):
    for name in ("x", "y", "z", "speed_f"):
        if struct.pack(">f", getattr(actual, name)) != struct.pack(">f", getattr(expected, name)):
            raise RuntimeError(f"movie capture differs from the final slot ({name}); "
                               "the saved route was not reproduced, so no search was started")
    if (actual.state, actual.facing) != (expected.state, expected.facing):
        raise RuntimeError("movie capture differs from the final slot (action/facing); "
                           "the saved route was not reproduced, so no search was started")


def capture_native_route(pid, target, route, output_dir, log=print, cancelled=lambda: False,
                         capture_extra=None):
    from harness.rollstab.barrier_slash import _frame_record, _seed_kind
    from harness.rollstab.live_slash import open_dolphin, read_live_target_collision, resolve_geo
    from harness.rollstab.native_route_capture import capture_world, capture_seed, collision_signature
    from harness.rollstab.seamgeo import SeamGeo

    output_dir = Path(output_dir)
    control = DolphinControl(pid)
    with attached_route(control, route, output_dir, log) as folder:
        reader = open_dolphin(pid)
        try:
            endpoint = route.movie.with_suffix("")
            if not endpoint.is_file():
                raise RuntimeError("native capture requires the recorded route's final savestate")
            check = folder / "endpoint.sav"
            shutil.copy2(endpoint, check)
            shutil.copy2(route.movie, Path(str(check) + ".dtm"))
            _load_state_settled(control, check)
            expected = _snapshot(reader, 0)
            end_game_frame = reader.u32(GAME_FRAME)
            _load_state_settled(control, folder / "start.sav")
            before = _snapshot(reader, 0)
            extra = [capture_extra(reader, before)] if capture_extra else []
            count = (end_game_frame - reader.u32(GAME_FRAME)) & 0xFFFFFFFF
            if not 1 <= count <= 1000:
                raise RuntimeError("the saved states do not bracket a short forward gameplay route")
            walls, floors, seam_bg, floor_bg = read_live_target_collision(reader, target, before.y)
            geo, seam_entry = resolve_geo(walls, tuple(map(float, target)))
            geo["link_y"] = before.y
            seam = SeamGeo(geo, before.camera)
            room = capture_world(reader)
            signature = collision_signature(reader)
            log(f"Imported {len(room['backgrounds'])} live BG mesh(es), including actor collision.")
            trace, seeds, native_seeds = [], [], [capture_seed(reader, before)]
            previous_seed = None
            captured_rows = []
            for index in range(count):
                if cancelled():
                    raise RuntimeError("search cancelled")
                row = route.rows[min(index, len(route.rows) - 1)]
                captured_rows.append(row)
                response = advance_game_frame(control, reader)
                if collision_signature(reader) != signature:
                    raise RuntimeError("background collision changed during the route; animated BG motion "
                                       "is not yet supported by the native replay adapter")
                after = _snapshot(reader, index + 1)
                if capture_extra:
                    extra.append(capture_extra(reader, after))
                native_seeds.append(capture_seed(reader, after))
                seed = _sim_seed(reader, after, captured_rows)
                seed.update(seed_kind=_seed_kind(before.state, after.state),
                            previous=previous_seed, source_row=index)
                seeds.append(seed)
                frame = _frame_record(index, response, before, after, row, seam)
                camera = native_seeds[-1]["camera_state"]["fields"]
                frame["after"].update(camera_eye=camera["mEye"], camera_center=camera["mCenter"])
                trace.append(frame)
                previous_seed = _pose_seed(seed)
                before = after
                log(f"route row {index}: VI {response['frame']}, action={after.state}, "
                    f"pos=({after.x:.9f}, {after.z:.9f})")
            validate_endpoint(before, expected)
            log("Original movie replay matches the final slot bit-for-bit (pose/speed/action).")
            captured_start = output_dir / "route_start.sav"
            captured_movie = output_dir / "route_movie.dtm"
            shutil.copy2(folder / "start.sav", captured_start)
            shutil.copy2(route.movie, captured_movie)
            result = {
                "target": list(target), "resolved_seam": seam_entry,
                "seam_bg": seam_bg, "floor_bg": floor_bg, "geo": geo,
                "wall_mesh": walls, "floor_mesh": floors,
                "route": {"movie": str(captured_movie), "start_state": str(captured_start),
                          "start_vi": route.start_vi, "end_vi": movie_vi_from_savestate(endpoint),
                          "controller": route.controller, "rows": captured_rows},
                "trace": trace, "seeds": seeds,
                "native": {"protocol": 1, "room": room, "seeds": native_seeds},
                "capture": {"method": "original_movie", "endpoint_checked": True},
            }
            if capture_extra:
                result["extra"] = extra
            unaligned = output_dir / "manual_route_unaligned.json"
            unaligned.write_text(json.dumps(result, indent=2), encoding="ascii")
            from harness.rollstab.native_route import decode_row
            from harness.rollstab.native_route_timing import align_movie_polls
            from harness.rollstab.smart_route_search import _route
            timed = align_movie_polls(_route(result), trace, native_seeds, decode_row)
            result["route"].update(rows=list(timed.rows), poll_spans=list(timed.poll_spans))
            unaligned.unlink(missing_ok=True)
            log("Matched every live controller sample to its original DTM poll timestamp.")
            path = output_dir / "manual_route_trace.json"
            path.write_text(json.dumps(result, indent=2), encoding="ascii")
            log(f"Original movie route trace saved to {path}")
            return result
        finally:
            reader.close()
