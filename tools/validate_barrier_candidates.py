"""Replay corrected barrier candidates from their preserved full-movie state."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time

from harness.collision.live_moving_drop import _snapshot
from harness.dolphin_control import DolphinControl
from harness.rollstab.live_slash import open_dolphin
from harness.rollstab.recorded_route import RecordedRoute, patch_route_movie
from harness.rollstab.seamgeo import SeamGeo


def _load_movie_start(control, state_path, start_vi, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = control.command("status")
        frame = int(status.get("frame", -1))
        # playmovie is asynchronous. While it boots, the pipe can still report
        # the previous deep movie as playing; wait until the new stream's
        # frame-zero cursor is visible before loading the deep anchor.
        if status.get("playing") and 0 <= frame < 1000:
            control.pause()
            control.load_state(str(state_path))
            settle_deadline = time.monotonic() + 5.0
            while time.monotonic() < settle_deadline:
                loaded = control.command("status")
                if (loaded.get("playing") and
                        int(loaded.get("frame", -1)) == start_vi):
                    return loaded
                time.sleep(0.02)
            raise RuntimeError(
                f"candidate state did not restore movie cursor VI {start_vi}"
            )
        time.sleep(0.05)
    raise RuntimeError("candidate movie did not start")


def _finish_active_movie(control, timeout=5.0):
    status = control.command("status")
    if not status.get("playing"):
        return
    control.command("resume")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not control.command("status").get("playing"):
            control.pause()
            return
        time.sleep(0.02)
    control.pause()
    raise RuntimeError("previous movie did not reach its end")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--hits", type=Path, required=True)
    parser.add_argument("--source-movie", type=Path, required=True)
    parser.add_argument("--start-state", type=Path, required=True)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    trace = json.loads(args.trace.read_text())
    hits = json.loads(args.hits.read_text())
    rows = tuple(dict(row) for row in trace["route"]["rows"])
    route = RecordedRoute(
        movie=args.source_movie,
        start_state=args.start_state,
        start_vi=int(trace["route"]["start_vi"]),
        end_vi=int(trace["route"]["end_vi"]),
        controller=int(trace["route"]["controller"]),
        rows=rows,
    )
    seam = SeamGeo(trace["geo"], trace["seeds"][6]["snapshot"]["camera"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    control = DolphinControl(args.pid)
    results = []
    anchor_companion = Path(str(args.start_state) + ".dtm")
    original_companion = anchor_companion.read_bytes()

    # Test deepest candidates first, then distinct lower-speed crossings.
    hits.sort(key=lambda hit: min(hit["planes"]))
    seen_inputs = set()
    try:
        for number, hit in enumerate(hits, 1):
            key = (tuple(hit["row5"]), tuple(hit["row6"]), tuple(hit["row7"]))
            if key in seen_inputs:
                continue
            seen_inputs.add(key)
            patched = [dict(row) for row in rows]
            for index, name in ((5, "row5"), (6, "row6"), (7, "row7")):
                patched[index]["stickX"], patched[index]["stickY"] = hit[name]
            movie = args.output_dir / f"barrier_exact_{number:02d}.dtm"
            patch_route_movie(route, patched, movie)
            shutil.copy2(args.start_state, Path(str(movie) + ".sav"))
            shutil.copy2(movie, Path(str(movie) + ".sav.dtm"))
            shutil.copy2(movie, anchor_companion)

            _finish_active_movie(control)
            control.command("playmovie", {
                "path": str(movie).replace("\\", "/"),
                "game": str(args.game).replace("\\", "/"),
            })
            _load_movie_start(control, args.start_state, route.start_vi)
            reader = open_dolphin(args.pid)
            frames = []
            try:
                before = _snapshot(reader, -1)
                for index, row in enumerate(patched):
                    response = control.advance(1)
                    after = _snapshot(reader, index)
                    frames.append({
                        "row": index,
                        "emu_frame": response.get("frame"),
                        "input": row,
                        "before": asdict(before),
                        "after": asdict(after),
                    })
                    before = after
            finally:
                reader.close()

            old_state = frames[8]["after"]
            new_state = frames[9]["after"]
            old = (old_state["x"], old_state["z"])
            new = (new_state["x"], new_state["z"])
            genuine = seam.genuine_clip(old, new)
            result = {
            "movie": str(movie), "inputs": {name: hit[name] for name in ("row5", "row6", "row7")},
            "predicted": hit, "old": list(old), "new": list(new),
            "old_facing": old_state["facing"], "new_facing": new_state["facing"],
            "new_state": new_state["state"], "genuine_clip": genuine,
            "old_planes": [seam.wA.pla.func(seam.p32(*old)), seam.wB.pla.func(seam.p32(*old))],
            "new_planes": [seam.wA.pla.func(seam.p32(*new)), seam.wB.pla.func(seam.p32(*new))],
            "frames": frames,
        }
            results.append(result)
            print(
            f"candidate {number}: old=({old[0]:.9f},{old[1]:.9f}) "
            f"new=({new[0]:.9f},{new[1]:.9f}) state={new_state['state']} "
            f"planes={result['new_planes']} genuine={genuine}", flush=True,
        )
            (args.output_dir / "live_results.json").write_text(json.dumps(results, indent=2) + "\n")
            if genuine:
                (args.output_dir / "verified_candidate.json").write_text(json.dumps(result, indent=2) + "\n")
                print(f"VERIFIED {movie}", flush=True)
                return 0
        print("No candidate produced a native genuine transition", flush=True)
        return 1
    finally:
        anchor_companion.write_bytes(original_companion)


if __name__ == "__main__":
    raise SystemExit(main())
