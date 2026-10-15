"""Capture once, then diagnose native camera/player replay without running a search."""
import argparse
import json
from pathlib import Path

from harness.rollstab.recorded_route import extract_route
from harness.rollstab.native_route_playback import capture_native_route
from harness.rollstab.native_route import NativeWorker, extract_assets, validate_replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int)
    parser.add_argument("--states", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--iso", required=True)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if args.capture:
        route = extract_route(args.states / "GZLJ01.s10.dtm", args.states / "GZLJ01.s05",
                              args.states / "GZLJ01.s10", controller=1)
        trace = capture_native_route(args.pid, (-499.174835, 948.859436, -2359.114014),
                                     route, args.output)
    else:
        trace = json.loads((args.output / "manual_route_trace.json").read_text())
    worker = NativeWorker(args.worker, extract_assets(args.iso, args.output / "assets"),
                          trace["native"]["room"])
    try:
        seeds = trace["native"]["seeds"]
        results = []
        failures = []
        for anchor in range(16, min(22, len(seeds) - 1)):
            pads = [s["pad"] for s in seeds[anchor:-1]]
            replay = worker.replay(seeds[anchor], [pads], seeds[anchor]["camera"])[0]
            results.append({"anchor": anchor, "replay": replay})
            if "error" in replay:
                print(anchor, replay["error"])
                failures.append((anchor, replay["error"]))
                continue
            try:
                validate_replay(replay["frames"], [f["after"] for f in
                                trace["trace"][anchor:anchor + len(pads)]])
            except RuntimeError as exc:
                failures.append((anchor, str(exc)))
            for offset, actual in enumerate(replay["frames"]):
                expected = trace["trace"][anchor + offset]["after"]
                print(anchor, offset, "pos", actual["pos"], "expected",
                      [expected[k] for k in ("x", "y", "z")], "camera",
                      actual["camera"], expected["camera"], "state", actual["state"], expected["state"])
        (args.output / "native_camera_replay.json").write_text(json.dumps(results, indent=2))
        if failures:
            raise RuntimeError("native replay regression: " + repr(failures))
        print(f"PASS: {len(results)} replay windows match the captured route bit-for-bit.")
    finally:
        worker.close()


if __name__ == "__main__":
    main()
