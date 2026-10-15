"""Check native direction reversals and idle-turn regressions, without Dolphin."""
import argparse
import json
import math
from pathlib import Path

from harness.rollstab.native_route import NativeWorker, decode_row, extract_assets
from harness.validate.native_slash_smoke import flat_room


def reversal_routes():
    up = decode_row(dict(stickX=128, stickY=252, buttons=0))
    down = decode_row(dict(stickX=128, stickY=2, buttons=0))
    return [[up] * 3 + [down] * 12, [up] * 10 + [down] * 25]


def check(worker, request):
    results = []
    for count in (1, 10):
        reply = worker.request(dict(request, workers=count, diagnostics=True))["results"]
        errors = [item["error"] for item in reply if "error" in item]
        if errors:
            raise AssertionError(errors)
        for item in reply:
            for frame in item["frames"]:
                for animation in frame["under"]:
                    assert all(math.isfinite(animation[key]) for key in ("frame", "rate", "ratio", "pose_frame"))
        results.append(reply)
    assert results[0] == results[1], "CPU lane count changed the movement/animation result"
    return results[0]


def run(executable, assets, trace=None, batch=None):
    worker = NativeWorker(executable, assets, flat_room())
    try:
        result = check(worker, dict(benchmark=True, routes=reversal_routes(), camera=0))
        assert 24 in [f["state"] for f in result[0]["frames"]], "low-speed reversal did not use MOVE_TURN"
        states = [f["state"] for f in result[1]["frames"]]
        assert 25 in states and 24 in states, "brakeslide did not enter and recover into MOVE_TURN"
    finally:
        worker.close()
    summary = {"direction_reversals": 2, "deterministic": True, "finite_animation_clocks": True}
    if trace is not None and batch is not None:
        worker = NativeWorker(executable, assets, trace["native"]["room"])
        try:
            result = check(worker, batch)
            summary["captured_room_routes"] = len(result)
        finally:
            worker.close()
    print(json.dumps(summary))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True)
    parser.add_argument("--iso", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--batch", type=Path)
    args = parser.parse_args()
    if bool(args.trace) != bool(args.batch):
        parser.error("--trace and --batch must be supplied together")
    assets = extract_assets(args.iso, args.output / "assets")
    summary = run(args.worker, assets,
                  json.loads(args.trace.read_text()) if args.trace else None,
                  json.loads(args.batch.read_text()) if args.batch else None)
    (args.output / "movement_paths.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
