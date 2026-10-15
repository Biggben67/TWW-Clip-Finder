"""Replay a fixed diagnostic route once and compare native animation/movement."""
import argparse
import json
from pathlib import Path
import shutil
import time
from contextlib import contextmanager

from harness.collision.live_moving_drop import _snapshot
from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import open_dolphin
from harness.rollstab.native_route import NativeWorker, _route, normalized_stick, validate_replay, f32_equal
from harness.rollstab.native_route_capture import capture_seed
from harness.rollstab.native_route_playback import attached_route, advance_game_frame
from harness.rollstab.recorded_route import RecordedRoute, install_route_movie, read_dtm_vi_rows


@contextmanager
def runtime_movie_rows(control, route, rows, output, *, replace_from=0):
    """Read-only savestate loads retain the old buffer; edit and restore it explicitly."""
    script = output.resolve() / "dolphin_movie_patch.py"
    shutil.copy2(Path(__file__).with_name(script.name), script)
    payload = dict(controller=route.controller, rows=[])
    buttons = ("Start", "A", "B", "X", "Y", "Z", "Up", "Down", "Left", "Right", "L", "R")
    masks = (0x1000, 0x100, 0x200, 0x400, 0x800, 0x10, 1, 4, 8, 2, 0x40, 0x20)
    for index, row in enumerate(rows):
        if index < replace_from:
            continue
        state = dict(StickX=row["stickX"], StickY=row["stickY"],
                     CStickX=row["substickX"], CStickY=row["substickY"],
                     TriggerLeft=row["triggerL"], TriggerRight=row["triggerR"])
        state.update((name, bool(row["buttons"] & mask)) for name, mask in zip(buttons, masks))
        span = (route.poll_spans[index] if getattr(route, "poll_spans", ())
                else (route.start_vi * 2 + index * 4, route.start_vi * 2 + index * 4 + 4))
        for poll in range(*span):
            payload["rows"].append(dict(row=poll, state=state))

    def invoke(action):
        request = dict(payload, action=action)
        script.with_suffix(".json").write_text(json.dumps(request))
        result = script.with_suffix(".result.json")
        # Clear the acknowledgement before launching the next one-shot script.
        result.write_text("null")
        control.command("enablescript", dict(path=str(script)))
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    data = json.loads(result.read_text())
                except json.JSONDecodeError:
                    time.sleep(0.02)
                    continue
                if data is not None:
                    if not data["ok"]:
                        raise RuntimeError(data["error"])
                    return
                time.sleep(0.02)
            raise RuntimeError("Dolphin did not acknowledge the diagnostic input edit")
        finally:
            control.command("disablescript", dict(path=str(script)))

    try:
        invoke("apply")
        yield
    finally:
        if script.with_suffix(".backup.json").is_file():
            invoke("restore")


def validate_consumed_pads(actual, intended):
    if len(actual) != len(intended):
        raise RuntimeError("Dolphin did not consume the complete diagnostic input sequence")
    floats = ("mx", "my", "distance", "cx", "cy", "cvalue", "tl", "tr")
    integers = ("angle", "cangle", "hold", "item_button", "target")
    for index, (live, requested) in enumerate(zip(actual, intended)):
        if (any(not f32_equal(live[key], requested[key]) for key in floats)
                or any((int(live[key]) & 65535) != (int(requested[key]) & 65535) for key in integers)):
            raise RuntimeError(f"Dolphin ignored or changed diagnostic input {index}; no validation is valid")


def raw_sticks(pads):
    """Invert exact normalized CPAD values, not rounded display coordinates."""
    tables = []
    for sub in (False, True):
        table = {}
        for x in range(256):
            for y in range(256):
                px, py, value, angle = normalized_stick(x, y, sub)
                table.setdefault((px, py, value, angle & 65535), (x, y))
        tables.append(table)
    result = []
    for pad in pads:
        main = (pad["mx"], pad["my"], pad["distance"], (pad["angle"] - 32768) & 65535)
        sub = (pad["cx"], pad["cy"], pad["cvalue"], pad["cangle"] & 65535)
        result.append((*tables[0][main], *tables[1][sub]))
    return result


def run(pid, trace, packet, candidate, executable, assets, output):
    route = _route(trace)
    source_pads = packet["routes"][candidate]
    seed_index = next(i for i, seed in enumerate(trace["native"]["seeds"])
                      if seed == packet["seed"])
    delay = 2
    rows = [dict(row) for row in route.rows]
    for index, sticks in enumerate(raw_sticks(source_pads), seed_index - delay):
        for key, value in zip(("stickX", "stickY", "substickX", "substickY"), sticks):
            rows[index][key] = value
        pad = source_pads[index - (seed_index - delay)]
        rows[index]["buttons"] = sum(dtm for mask, dtm in (
            (0x8000, 1), (0x4000, 2), (0x2000, 4), (0x1000, 8),
            (0x800, 0x10), (0x400, 0x20), (0x200, 0x40), (0x100, 0x100),
            (0x80, 0x200), (0x40, 0x400), (0x20, 0x800), (0x10, 0x1000),
        ) if pad["hold"] & mask)
        rows[index]["triggerL"] = round(30 + 150 * pad["tl"]) if pad["tl"] else 0
        rows[index]["triggerR"] = round(30 + 150 * pad["tr"]) if pad["tr"] else 0
    # A recording may end with an incomplete final poll. This diagnostic does
    # not synthesize tail events: only patch the complete portion of the movie.
    complete_vis = len(read_dtm_vi_rows(route.movie, route.controller))
    rows = rows[:max(0, (complete_vis - route.start_vi) // 2)]
    route = RecordedRoute(route.movie, route.start_state, route.start_vi,
                          route.start_vi + 2 * len(rows), route.controller, tuple(rows))
    movie = install_route_movie(route, rows, output / "diagnostic_only.dtm", short=False)
    diagnostic = RecordedRoute(movie, route.start_state, route.start_vi,
                               route.end_vi, route.controller, tuple(rows))
    seeds, expected = [], []
    control = DolphinControl(pid)
    with attached_route(control, diagnostic, output, print), runtime_movie_rows(control, route, rows, output):
        reader = open_dolphin(pid)
        try:
            for index in range(len(rows) + 1):
                snapshot = _snapshot(reader, 0)
                seed = capture_seed(reader, snapshot)
                seeds.append(seed)
                if index:
                    camera = seed["camera_state"]["fields"]
                    expected.append(dict(x=snapshot.x, y=snapshot.y, z=snapshot.z,
                                         state=snapshot.state, facing=snapshot.facing,
                                         speed_f=snapshot.speed_f, camera=snapshot.camera,
                                         camera_eye=camera["mEye"], camera_center=camera["mCenter"],
                                         under=seed["under"]))
                if index < len(rows):
                    advance_game_frame(control, reader)
        finally:
            reader.close()
    worker = NativeWorker(executable, assets, trace["native"]["room"])
    try:
        pads = [seed["pad"] for seed in seeds[seed_index:-1]]
        validate_consumed_pads(pads, source_pads[:len(pads)])
        replay = worker.replay(seeds[seed_index], [pads], seeds[seed_index]["camera"], diagnostics=True)[0]
        report = dict(replay=replay, expected=expected[seed_index:], candidate=candidate)
        (output / "live_movement_check.json").write_text(json.dumps(report, indent=2))
        if replay.get("error"):
            raise RuntimeError(replay["error"])
        validate_replay(replay["frames"], expected[seed_index:])
        print("PASS: live movement, camera and under-animation clocks match bit-for-bit.")
    finally:
        worker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--candidate", default=2, type=int)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--assets", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run(args.pid, json.loads(args.trace.read_text()), json.loads(args.batch.read_text()),
        args.candidate, args.worker, args.assets, args.output)


if __name__ == "__main__":
    main()
