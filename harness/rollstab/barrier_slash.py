"""Calibrate and optimize a recorded Hyrule-barrier slash route.

The Wind Waker knockback cancel is retained as a deterministic recorded prefix.
Only the final target-walk, sword draw, and slash controls are candidates for
offline optimization.  One control-pipe replay captures the otherwise hidden
mid-animation state required to seed the binary32 movement model.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import time

from harness.collision.live_moving_drop import (
    _load_state_settled,
    _pose_seed,
    _save_state_settled,
    _sim_seed,
    _snapshot,
    _stop_active_recording,
)
from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import (
    _mesh_tris,
    open_dolphin,
    read_live_target_collision,
    resolve_geo,
)
from harness.rollstab.recorded_route import (
    RecordedRoute,
    install_route_movie,
    extract_route,
    nearest_route_start,
)
from harness.collision.offline_moving_drop import _make_seed
from harness.rollstab.seamgeo import SeamGeo
from tww_sim.land.constants import (
    ATN_MOVE, ATN_ACTOR_MOVE, ATN_ACTOR_WAIT, FRONT_ROLL, MOVE,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "_generated" / "barrier_slash"
CUT_F = 0x42


def _button_names(buttons: int) -> str:
    names = []
    for mask, name in (
        (0x1000, "Start"), (0x0100, "A"), (0x0200, "B"),
        (0x0400, "X"), (0x0800, "Y"), (0x0010, "Z"),
        (0x0040, "L"), (0x0020, "R"),
    ):
        if buttons & mask:
            names.append(name)
    return "+".join(names) if names else "-"


def describe_row(index: int, row: dict) -> str:
    return (
        f"{index:02d}: main=({row['stickX']},{row['stickY']}) "
        f"C=({row.get('substickX', 128)},{row.get('substickY', 128)}) "
        f"buttons={_button_names(row.get('buttons', 0))} "
        f"L={row.get('triggerL', 0)} R={row.get('triggerR', 0)}"
    )


def _seed_kind(before_state: int, after_state: int) -> str:
    if after_state == MOVE and before_state in (
        ATN_MOVE, ATN_ACTOR_MOVE, ATN_ACTOR_WAIT, FRONT_ROLL,
    ):
        return "move_reentry_anchor"
    return "exact_moving_anchor"


def discover_recorded_route(state_dir: str | Path, game_id: str = "GZLJ01",
                            controller: int = 1) -> RecordedRoute:
    """Find the newest DTM that has a valid earlier savestate bracket."""
    state_dir = Path(state_dir)
    movies = sorted(
        state_dir.glob(f"{game_id}.s??.dtm"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not movies:
        raise RuntimeError(f"no {game_id}.sNN.dtm recording was found in {state_dir}")
    candidates = list(state_dir.glob(f"{game_id}.s??"))
    failures = []
    for movie in movies:
        end_state = movie.with_suffix("")
        if not end_state.is_file():
            failures.append(f"{movie.name}: missing {end_state.name}")
            continue
        try:
            start = nearest_route_start(movie, end_state,
                                        [path for path in candidates if path != end_state])
            return extract_route(movie, start, end_state, controller=controller)
        except (RuntimeError, ValueError) as exc:
            failures.append(f"{movie.name}: {exc}")
    detail = "; ".join(failures[-3:])
    raise RuntimeError(f"no recorded route with a valid savestate bracket was found ({detail})")


def search_recorded_route_candidate(trace: dict, *, output: Path | None = None,
                                    samples: int = 5000, random_seed: int = 4004,
                                    log=print, short_movie: bool = False) -> dict:
    """Find a binary32-faithful final approach for a captured barrier route.

    The seed after route row 6 has rows 5 and 6 in its two-poll input buffer.
    Varying those pending polls changes the final walking frames while
    retaining the recorded Wind Waker cancel and sword-draw timing.  The
    recorded B edge is already present on row 5.  With the game's two-poll
    latency it enters CUT_F on row 9: rows 7 and 8 are the last ordinary MOVE
    updates, and the delayed row-7 stick controls the row-9 cut dispatch.
    Consequently the clip transition is exactly ``after row 8 -> CUT_F row
    9``. No measured coordinate offset or additional B input is applied.
    """
    rows = [dict(row) for row in trace["route"]["rows"]]
    seeds = trace.get("seeds", [])
    if len(rows) < 11 or len(seeds) < 9:
        raise RuntimeError("barrier route is too short for the final walking search")
    walls = _mesh_tris(trace["wall_mesh"])
    seed = dict(seeds[6])
    if len(trace.get("trace", [])) > 6:
        seed["seed_kind"] = _seed_kind(
            int(trace["trace"][5]["after"]["state"]),
            int(trace["trace"][6]["after"]["state"]),
        )
    base = _make_seed(seed, walls, force_state=None, model_draw=False)
    seam = SeamGeo(trace["geo"], seed["snapshot"]["camera"])
    rng = random.Random(int(random_seed))
    bases = ((195, 230), (66, 228))
    best = None
    for sample in range(max(1, int(samples))):
        choices = []
        for base_x, base_y in bases:
            choices.append((
                max(1, min(255, base_x + rng.randint(-128, 128))),
                max(1, min(255, base_y + rng.randint(-70, 1))),
            ))
        cut_stick = (rng.randint(1, 255), rng.randint(128, 255))
        state = base.state.clone()
        pending = list(state._inbuf[0])
        pending[0], pending[1] = choices[0]
        state._inbuf[0] = tuple(pending)
        pending = list(state._inbuf[1])
        pending[0], pending[1] = choices[1]
        state._inbuf[1] = tuple(pending)
        for index in (7, 8):
            row = rows[index]
            sx, sy = cut_stick if index == 7 else (row["stickX"], row["stickY"])
            state.step(sx, sy, row.get("buttons", 0),
                       row.get("triggerL", 0), row.get("substickX", 128),
                       row.get("substickY", 128))
        old = (state.pos_x, state.pos_z)
        dispatch = rows[9]
        state.enter_cut_from_move(
            dispatch["stickX"], dispatch["stickY"],
            csx=dispatch.get("substickX", 128),
            csy=dispatch.get("substickY", 128),
        )
        new = (state.pos_x, state.pos_z)
        ray_error = abs(seam.perp_to_ray(old, new))
        score = (0 if seam.genuine_clip(old, new) else 1, ray_error)
        candidate = {
            "sample": sample,
            "pending_sticks": [list(choices[0]), list(choices[1])],
            "cut_stick": list(cut_stick),
            "old": list(old), "new": list(new),
            "facing": state.facing, "travel": state.travel,
            "speedF": state.speedF, "ray_error": ray_error,
            "genuine_clip": bool(seam.genuine_clip(old, new)),
            "score": list(score),
        }
        if best is None or tuple(score) < tuple(best["score"]):
            best = candidate
        if not candidate["genuine_clip"]:
            continue
        patched = [dict(row) for row in rows]
        patched[5]["stickX"], patched[5]["stickY"] = choices[0]
        patched[6]["stickX"], patched[6]["stickY"] = choices[1]
        patched[7]["stickX"], patched[7]["stickY"] = cut_stick
        candidate["cut_button_row"] = 5
        candidate["rows"] = patched
        if output is not None:
            route = RecordedRoute(
                movie=Path(trace["route"]["movie"]),
                start_state=Path(trace["route"]["start_state"]),
                start_vi=int(trace["route"]["start_vi"]),
                end_vi=int(trace["route"]["end_vi"]),
                controller=int(trace["route"]["controller"]),
                rows=tuple(rows),
            )
            candidate["movie"] = str(install_route_movie(
                route, patched, output, short=short_movie
            ))
        log(
            "Offline barrier candidate: row5=(%d,%d), row6=(%d,%d), row7=(%d,%d), "
            "old=(%.9f, %.9f), new=(%.9f, %.9f), facing=%d" %
            (choices[0][0], choices[0][1], choices[1][0], choices[1][1],
             cut_stick[0], cut_stick[1],
             old[0], old[1], new[0], new[1], state.facing)
        )
        return candidate
    raise RuntimeError(
        "no exact barrier clip in %d samples; best ray error %.9f" %
        (samples, best["ray_error"] if best else float("inf"))
    )


def _frame_record(index, response, before, after, row, seam: SeamGeo) -> dict:
    old = (before.x, before.z)
    new = (after.x, after.z)
    return {
        "row": index,
        "emu_frame": response.get("frame"),
        "input": dict(row),
        "before": asdict(before),
        "after": asdict(after),
        "old": list(old),
        "new": list(new),
        "genuine_transition": bool(seam.genuine_clip(old, new)),
        "old_planes": [seam.wA.pla.func(seam.p32(*old)), seam.wB.pla.func(seam.p32(*old))],
        "new_planes": [seam.wA.pla.func(seam.p32(*new)), seam.wB.pla.func(seam.p32(*new))],
    }


def capture_manual_route(pid: int, target, route: RecordedRoute,
                         output_dir: str | Path = OUTPUT_DIR, log=print, native=False) -> dict:
    """Replay a recorded route once and capture exact per-frame simulation seeds."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    control = DolphinControl(pid)
    control.pause()

    reader = open_dolphin(pid)
    try:
        current = _snapshot(reader, 0)
        wall_mesh, floor_mesh, seam_bg, floor_bg = read_live_target_collision(
            reader, target, current.y
        )
        geo, seam_entry = resolve_geo(wall_mesh, tuple(float(value) for value in target))
        geo["link_y"] = current.y
        seam = SeamGeo(geo, current.camera)
        native_room = None
        if native:
            from harness.rollstab.native_route_capture import capture_room
            if seam_bg != floor_bg:
                raise RuntimeError("native import needs a multi-BG adapter for this seam; capture was not replayed")
            native_room = capture_room(reader, seam_bg)
    finally:
        reader.close()

    log(
        "Resolved barrier seam on movable BG %d (floor BG %d): "
        "S=(%.9f, %.9f, %.9f)" %
        (seam_bg, floor_bg, geo["S"][0], geo["S"][1], geo["S"][2])
    )
    log(
        f"Recovered {len(route.rows)} exact gameplay rows from VI "
        f"{route.start_vi}..{route.end_vi}."
    )
    for index, row in enumerate(route.rows):
        log(describe_row(index, row))

    control_status = control.command("status")
    playback = bool(control_status.get("playing"))
    if playback and int(control_status.get("frame", -1)) != route.start_vi:
        raise RuntimeError(
            f"Dolphin movie is paused at VI {control_status.get('frame')}, not the "
            f"recorded-route start VI {route.start_vi}"
        )
    restore_state = None
    if not playback:
        _stop_active_recording(control, output_dir, log=log)
        restore_state = output_dir / "restore_current.sav"
        _save_state_settled(control, restore_state)
    trace = []
    seeds = []
    native_seeds = []
    reader = None
    try:
        if not playback:
            _load_state_settled(control, route.start_state)
            status = control.command("status")
            playback = bool(status.get("playing"))
            if playback and int(status.get("frame", -1)) != route.start_vi:
                raise RuntimeError("loaded route state restored at the wrong movie VI")
        reader = open_dolphin(pid)
        previous_seed = None
        before = _snapshot(reader, 0)
        if native:
            from harness.rollstab.native_route_capture import capture_seed
            native_seeds.append(capture_seed(reader, before))
        for index, row in enumerate(route.rows):
            # Prefer native movie playback: it preserves the saved controller-poll
            # phase. Injection is only a fallback for standalone route states.
            response = control.advance(1) if playback else control.advance_with(frames=1, **row)
            after = _snapshot(reader, index + 1)
            if native:
                native_seeds.append(capture_seed(reader, after))
            seed = _sim_seed(reader, after, list(route.rows[:index + 1]))
            seed["seed_kind"] = _seed_kind(before.state, after.state)
            seed["previous"] = previous_seed
            seed["source_row"] = index
            seeds.append(seed)
            frame = _frame_record(index, response, before, after, row, seam)
            trace.append(frame)
            log(
                "row %02d: state=%d pos=(%.9f, %.9f) speed=%.9f facing=%d%s" %
                (index, after.state, after.x, after.z, after.speed_f, after.facing,
                 " CUT_F" if after.state == CUT_F else
                 " CLIP" if frame["genuine_transition"] else "")
            )
            previous_seed = _pose_seed(seed)
            before = after
        result = {
            "target": list(target),
            "resolved_seam": seam_entry,
            "seam_bg": seam_bg,
            "floor_bg": floor_bg,
            "geo": geo,
            "wall_mesh": wall_mesh,
            "floor_mesh": floor_mesh,
            "route": {
                "movie": str(route.movie),
                "start_state": str(route.start_state),
                "start_vi": route.start_vi,
                "end_vi": route.end_vi,
                "controller": route.controller,
                "rows": list(route.rows),
            },
            "trace": trace,
            "seeds": seeds,
        }
        if native:
            result["native"] = {"protocol": 1, "room": native_room, "seeds": native_seeds}
        path = output_dir / "manual_route_trace.json"
        path.write_text(json.dumps(result, indent=2), encoding="ascii")
        log(f"Exact route trace saved to {path}")
        return result
    finally:
        if reader is not None:
            reader.close()
        _load_state_settled(control, restore_state or route.start_state)
        time.sleep(0.1)


def _parse_target(value: str):
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("target must be x,y,z")
    return tuple(parts)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--target", type=_parse_target, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--game-id", default="GZLJ01")
    parser.add_argument("--controller", type=int, default=1,
                        help="zero-based DTM controller index (default: 1)")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--optimize", action="store_true",
                        help="search the final buffered walking polls and export a short DTM")
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=4004)
    parser.add_argument("--short-movie", action="store_true",
                        help="export a frame-zero route movie instead of patching the full source DTM")
    args = parser.parse_args(argv)
    route = discover_recorded_route(args.state_dir, args.game_id, args.controller)
    trace = capture_manual_route(args.pid, args.target, route, args.output)
    if args.optimize:
        movie = args.output / "barrier_candidate.dtm"
        candidate = search_recorded_route_candidate(
            trace, output=movie, samples=args.samples,
            random_seed=args.random_seed, short_movie=args.short_movie,
        )
        (args.output / "barrier_candidate.json").write_text(
            json.dumps(candidate, indent=2), encoding="ascii"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
