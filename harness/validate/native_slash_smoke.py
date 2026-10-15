"""Exercise real native walk/roll/slash paths and compare CPU batch determinism."""
import argparse
import json
from pathlib import Path
import time

from harness.rollstab.native_route import NativeWorker, decode_row, extract_assets


def flat_room():
    return {
        "vertices": [[-524288, 0, 524288], [524288, 0, 524288],
                     [-524288, 0, -524288], [524288, 0, -524288]],
        "triangles": [[0, 1, 2, 0, 0], [3, 2, 1, 0, 0]], "blocks": [0],
        "trees": [[1, 65535, 0, 0, 0, 0, 0, 0, 0, 0]],
        "groups": [{"scale": [1, 1, 1], "translation": [0, 0, 0],
                    "rotation": [0, 0, 0], "links": [65535, 65535, 65535, 0, 0, 0],
                    "info": 0}],
        "attributes": [[0, 0, 0, 0]],
    }


def routes():
    def row(buttons=0):
        return decode_row({"stickX": 128, "stickY": 252, "buttons": buttons})
    walk = [row() for _ in range(20)] + [row(0x200)] + [row() for _ in range(4)]
    roll = [row() for _ in range(12)] + [row(0x100)] + [row() for _ in range(15)]
    roll += [row(0x200)] + [row() for _ in range(4)]
    return [walk, roll]


def run(executable, iso, output, count=128, workers=8):
    output = Path(output)
    assets = extract_assets(iso, output / "assets")
    worker = NativeWorker(executable, assets, flat_room())
    try:
        batch = [routes()[i % 2] for i in range(count)]
        samples = []
        reference = None
        for threads in (1, workers):
            started = time.perf_counter()
            result = worker.request({"benchmark": True, "routes": batch, "camera": 0,
                                     "workers": threads})["results"]
            elapsed = time.perf_counter() - started
            errors = [item["error"] for item in result if "error" in item]
            if errors:
                raise AssertionError("native smoke failed: " + errors[0])
            assert len(result) == count
            assert any(frame["state"] == 30 for frame in result[1]["frames"]), "roll did not occur"
            assert all(any(frame["state"] in range(0x41, 0x46) for frame in item["frames"])
                       for item in result), "slash did not occur"
            if reference is not None:
                assert reference == result, "thread count changed native output"
            reference = result
            samples.append({"workers": threads, "routes": count, "seconds": elapsed,
                            "frames_per_second": sum(len(item["frames"]) for item in result) / elapsed})
        report = {"synthetic_only": True, "deterministic": True, "samples": samples,
                  "examples": reference[:2]}
        path = output / "smoke.json"
        path.write_text(json.dumps(report, indent=2), encoding="ascii")
        print(json.dumps({"report": str(path), "samples": samples}, indent=2))
        return report
    finally:
        worker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True)
    parser.add_argument("--iso", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=128)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.count < 2 or not 1 <= args.workers <= 16:
        parser.error("count must be >= 2 and workers must be 1..16")
    run(args.worker, args.iso, args.output, args.count, args.workers)


if __name__ == "__main__":
    main()
