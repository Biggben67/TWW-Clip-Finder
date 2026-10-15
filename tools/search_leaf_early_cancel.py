"""Replay a recorded leaf route and test an earlier leaf cancellation.

This tool deliberately validates candidates in Dolphin.  It preserves the native
multi-controller DTM, patches only P1, and temporarily installs the candidate as
the slot-5 companion movie so a deep savestate resumes at the correct cursor.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import time

from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import dolphin_pids, open_dolphin
from harness.rollstab.recorded_route import (
    RecordedRoute,
    movie_vi_from_savestate,
    patch_route_movie,
    read_dtm_vi_rows,
)


PLAYER_PTR = 0x803AD860
ACCH_PTR = 0x803BD910
GAME_INFO = 0x803B8108
FAN_GLIDE = 0x93
FALL = 0x27
LAND = 0x25
HANG_PROCS = {0x2A, 0x2B}


def connect(timeout: float = 30.0) -> DolphinControl:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for pid in reversed(dolphin_pids()):
            control = DolphinControl(pid)
            try:
                control.command("status")
                return control
            except RuntimeError:
                pass
        time.sleep(0.1)
    raise RuntimeError("no responsive Dolphin control pipe")


def route_through_movie_end(movie: Path, start: Path, end: Path | None) -> RecordedRoute:
    start_vi = movie_vi_from_savestate(start)
    vi_rows = read_dtm_vi_rows(movie, controller=1)
    end_vi = movie_vi_from_savestate(end) if end is not None else len(vi_rows)
    usable_end = min(end_vi, len(vi_rows))
    return RecordedRoute(
        movie=movie,
        start_state=start,
        start_vi=start_vi,
        end_vi=usable_end,
        controller=1,
        rows=tuple(vi_rows[start_vi:usable_end:2]),
    )


def snapshot(reader, frame: int) -> dict:
    deadline = time.monotonic() + 3.0
    player = reader.u32(PLAYER_PTR)
    while not 0x80000000 <= player < 0x81800000 and time.monotonic() < deadline:
        time.sleep(0.01)
        player = reader.u32(PLAYER_PTR)
    if not 0x80000000 <= player < 0x81800000:
        raise RuntimeError("player pointer did not become ready after movie startup")
    acch = reader.u32(ACCH_PTR)
    return {
        "frame": frame,
        "x": reader.f32(player + 0x120),
        "y": reader.f32(player + 0x124),
        "z": reader.f32(player + 0x128),
        "proc": reader.u32(player + 0x3100),
        "facing": reader.u16(player + 0x136),
        "travel": reader.u16(player + 0x12E),
        "speed_f": reader.f32(player + 0x17C),
        "magic": reader.u8(GAME_INFO + 0x14),
        "ground_poly": reader.u16(acch + 0x554),
        "ground_bg": reader.u16(acch + 0x556),
    }


def finish_movie(control: DolphinControl) -> DolphinControl:
    try:
        status = control.command("status")
        if not status.get("playing"):
            return control
        control.command("resume")
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if not control.command("status").get("playing"):
                control.pause()
                return control
            time.sleep(0.02)
        control.pause()
        raise RuntimeError("active movie did not finish")
    except RuntimeError:
        return connect()


def start_candidate(control: DolphinControl, movie: Path, game: Path,
                    start_state: Path, start_vi: int) -> DolphinControl:
    control = finish_movie(control)
    control.command("playmovie", {
        "path": str(movie).replace("\\", "/"),
        "game": str(game).replace("\\", "/"),
    })
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        try:
            status = control.command("status")
        except RuntimeError:
            control = connect()
            continue
        frame = int(status.get("frame", -1))
        if status.get("playing") and 0 <= frame <= 2:
            try:
                control.pause()
                control.load_state(str(start_state))
            except RuntimeError:
                control = connect()
                time.sleep(0.25)
                continue
            time.sleep(0.5)
            control.pause()
            loaded = control.command("status")
            if loaded.get("playing") and int(loaded.get("frame", -1)) == start_vi:
                return control
            # Some TAS Edition boots briefly return to the frame-zero slate
            # while the async state load is committing. Retry the same anchor.
            time.sleep(0.25)
            continue
        time.sleep(0.05)
    raise RuntimeError("candidate movie did not reach its startup cursor")


def run_candidate(control: DolphinControl, route: RecordedRoute, rows: list[dict],
                  name: str, output_dir: Path, game: Path,
                  _companion: Path | None = None,
                  trace_frames: int | None = None) -> tuple[dict, DolphinControl]:
    movie = output_dir / f"{name}.dtm"
    patch_route_movie(route, rows, movie)
    candidate_state = Path(str(movie) + ".sav")
    shutil.copy2(route.start_state, candidate_state)
    shutil.copy2(movie, Path(str(movie) + ".sav.dtm"))
    control = start_candidate(control, movie, game, candidate_state, route.start_vi)
    time.sleep(0.5)
    try:
        control.pause()
        control.command("status")
    except RuntimeError:
        control = connect()
        control.pause()
    reader = None
    deadline = time.monotonic() + 5.0
    while reader is None and time.monotonic() < deadline:
        try:
            probe = open_dolphin(control.pid)
            snapshot(probe, -1)
            reader = probe
        except (OSError, RuntimeError):
            try:
                probe.close()
            except Exception:
                pass
            control = connect()
            control.pause()
            time.sleep(0.1)
    if reader is None:
        raise RuntimeError("Dolphin process did not stabilize after candidate load")
    trace = []
    try:
        for frame in range(trace_frames or len(rows) + 6):
            trace.append(snapshot(reader, frame))
            control.advance(1)
    finally:
        reader.close()
        control.pause()
    leaf_frame = next((r["frame"] for r in trace if r["proc"] == FAN_GLIDE), None)
    cancel = next((r for r in trace if leaf_frame is not None and
                   r["frame"] > leaf_frame and r["proc"] != FAN_GLIDE), None)
    land = next((r for r in trace if cancel and r["frame"] >= cancel["frame"] and
                 r["proc"] == LAND), None)
    result = {
        "name": name,
        "movie": str(movie),
        "leaf_frame": leaf_frame,
        "cancel": cancel,
        "land": land,
        "hang": next((r for r in trace if r["proc"] in HANG_PROCS), None),
        "final": trace[-1],
        "trace": trace,
    }
    (output_dir / f"{name}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="ascii"
    )
    return result, control


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--start-state", type=Path)
    parser.add_argument("--source-movie", type=Path)
    parser.add_argument("--end-state", type=Path)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("_generated/leaf_early_cancel"))
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = args.start_state or args.state_dir / "GZLJ01.s05"
    end = args.end_state
    source_movie = args.source_movie or args.state_dir / "GZLJ01.s10.dtm"
    route = route_through_movie_end(source_movie, start, end)
    baseline_cancel_row = next(
        (index for index, row in enumerate(route.rows)
         if index >= 40 and row["buttons"] & 0x0100),
        None,
    )
    if baseline_cancel_row is None or baseline_cancel_row < 2:
        raise RuntimeError("recorded route has no first-leaf A cancel input")
    target_cancel_row = baseline_cancel_row - 1

    base = copy.deepcopy(list(route.rows))

    def early_cancel(rows: list[dict]) -> list[dict]:
        rows = copy.deepcopy(rows)
        rows[target_cancel_row]["buttons"] |= 0x0100
        rows[baseline_cancel_row]["buttons"] &= ~0x0100
        return rows

    candidates: list[tuple[str, list[dict]]] = [
        (f"cancel_row_{target_cancel_row}", early_cancel(base))
    ]
    # First move the long, stable part of the leaf trajectory.  These changes
    # preserve the deployment/cancel timing and alter only the approach point.
    for start_row in (
        max(0, baseline_cancel_row - 55),
        max(0, baseline_cancel_row - 39),
        max(0, baseline_cancel_row - 19),
        max(0, baseline_cancel_row - 10),
    ):
        for dx, dy in (
            (-3, 0), (-2, 0), (-1, 0), (1, 0), (2, 0), (3, 0),
            (0, -2), (0, -1), (0, 1), (0, 2),
            (-2, -1), (-1, -1), (1, 1), (2, 1),
        ):
            rows = early_cancel(base)
            for index in range(start_row, baseline_cancel_row):
                rows[index]["stickX"] = max(0, min(255, rows[index]["stickX"] + dx))
                rows[index]["stickY"] = max(0, min(255, rows[index]["stickY"] + dy))
            candidates.append((f"leaf_{start_row}_dx{dx:+d}_dy{dy:+d}", rows))

    # Launch the slash one frame earlier but leave the leaf button on its
    # recorded row.  This can add runway distance without increasing glide age.
    slash_rows = [
        index for index, row in enumerate(base[:baseline_cancel_row])
        if row["buttons"] & 0x0040
    ]
    slash_row = max(slash_rows) if slash_rows else None
    if slash_row is not None and slash_row > 0:
        rows = early_cancel(base)
        rows[slash_row - 1]["buttons"] |= rows[slash_row]["buttons"] & 0x0040
        rows[slash_row - 1]["triggerL"] = max(
            rows[slash_row - 1]["triggerL"], rows[slash_row]["triggerL"]
        )
        rows[slash_row]["buttons"] &= ~0x0040
        rows[slash_row]["triggerL"] = 0
        candidates.append(("slash_one_early", rows))

    # Small changes on the pre-slash braking rows alter the launch point and
    # angle while retaining the recorded action sequence.
    for dx, dy in ((-2, 0), (-1, 0), (1, 0), (2, 0),
                   (0, -2), (0, -1), (0, 1), (0, 2),
                   (-1, 1), (1, -1)):
        rows = early_cancel(base)
        launch_start = max(0, (slash_row or 1) - 3)
        for index in range(launch_start, slash_row or launch_start):
            rows[index]["stickX"] = max(0, min(255, rows[index]["stickX"] + dx))
            rows[index]["stickY"] = max(0, min(255, rows[index]["stickY"] + dy))
        candidates.append((f"launch_dx{dx:+d}_dy{dy:+d}", rows))

    candidates.sort(key=lambda item: (
        0 if item[0] == f"cancel_row_{target_cancel_row}" else
        1 if item[0].startswith("slash_") else
        2 if item[0].startswith("launch_") else 3
    ))
    control = connect()
    restore = args.output_dir / "before_search.sav"
    control.pause()
    control.save_state(str(restore))
    try:
        summaries = []
        for number, (name, rows) in enumerate(candidates, 1):
            result, control = run_candidate(
                control, route, rows, name, args.output_dir,
                args.game, trace_frames=baseline_cancel_row + 10,
            )
            concise = {key: result[key] for key in
                       ("leaf_frame", "cancel", "land", "hang", "final")}
            summaries.append({"name": name, **concise})
            final = result["final"]
            print(
                f"{number}/{len(candidates)} {name}: "
                f"cancel={None if result['cancel'] is None else result['cancel']['frame']} "
                f"land={None if result['land'] is None else result['land']['frame']} "
                f"hang={result['hang'] is not None} magic={final['magic']} "
                f"pos=({final['x']:.6f},{final['y']:.6f},{final['z']:.6f})",
                flush=True,
            )
            (args.output_dir / "results.json").write_text(
                json.dumps(summaries, indent=2) + "\n", encoding="ascii"
            )
            if result["land"] and final["magic"] >= 13:
                (args.output_dir / "verified.json").write_text(
                    json.dumps({"name": name, **concise}, indent=2) + "\n",
                    encoding="ascii",
                )
                print(f"VERIFIED {result['movie']}", flush=True)
                return 0
        return 1
    finally:
        try:
            control.pause()
            control.load_state(str(restore))
            time.sleep(0.5)
            control.pause()
        except RuntimeError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
