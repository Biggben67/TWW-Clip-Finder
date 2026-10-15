"""Export manual-playback candidates for a one-frame-earlier Deku Leaf cancel."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil

from harness.rollstab.recorded_route import (
    RecordedRoute,
    movie_vi_from_savestate,
    patch_route_movie,
    read_dtm_vi_rows,
)


A = 0x0100
B = 0x0040


def load_route(movie: Path, start: Path) -> RecordedRoute:
    start_vi = movie_vi_from_savestate(start)
    vi_rows = read_dtm_vi_rows(movie, controller=1)
    return RecordedRoute(
        movie=movie,
        start_state=start,
        start_vi=start_vi,
        end_vi=len(vi_rows),
        controller=1,
        rows=tuple(vi_rows[start_vi::2]),
    )


def clamp(value: int) -> int:
    return max(0, min(255, value))


def offset(rows: list[dict], indices, **changes: int) -> None:
    for index in indices:
        for field, delta in changes.items():
            rows[index][field] = clamp(rows[index][field] + delta)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-state", type=Path, required=True)
    parser.add_argument("--source-movie", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    route = load_route(args.source_movie, args.start_state)
    base = copy.deepcopy(list(route.rows))
    cancel_row = next(
        index for index, row in enumerate(base)
        if index >= 40 and row["buttons"] & A
    )
    early_row = cancel_row - 1
    slash_row = max(
        index for index, row in enumerate(base[:cancel_row])
        if row["buttons"] & B
    )

    def early() -> list[dict]:
        rows = copy.deepcopy(base)
        rows[early_row]["buttons"] |= A
        rows[cancel_row]["buttons"] &= ~A
        return rows

    specs: list[tuple[str, list[dict], str]] = []
    specs.append(("01_direct", early(), "A one frame earlier; unchanged trajectory"))

    rows = early()
    rows[slash_row - 1]["buttons"] |= B
    rows[slash_row - 1]["triggerL"] = rows[slash_row]["triggerL"]
    rows[slash_row]["buttons"] &= ~B
    rows[slash_row]["triggerL"] = 0
    specs.append((
        "02_slash_one_early", rows,
        "slash one row earlier; leaf deployment remains on its recorded row",
    ))

    # Pre-slash position/angle dust. These rows are late enough to affect the
    # launch but do not rewrite the established brakeslide sequence.
    for number, (dx, dy) in enumerate((
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, -1), (-1, 1), (2, -1), (-2, 1),
    ), 3):
        rows = early()
        offset(rows, range(slash_row - 3, slash_row), stickX=dx, stickY=dy)
        specs.append((
            f"{number:02d}_launch_dx{dx:+d}_dy{dy:+d}", rows,
            f"pre-slash rows {slash_row - 3}-{slash_row - 1}: main ({dx:+d},{dy:+d})",
        ))

    # Slash-camera dust changes the launch bearing without disturbing the leaf
    # steering sequence. Keep these separate so playback feedback is diagnostic.
    next_number = len(specs) + 1
    for cam_dx in (-2, -1, 1, 2):
        rows = early()
        offset(rows, range(slash_row - 3, slash_row), substickX=cam_dx)
        specs.append((
            f"{next_number:02d}_slash_cam_dx{cam_dx:+d}", rows,
            f"pre-slash rows {slash_row - 3}-{slash_row - 1}: C X {cam_dx:+d}",
        ))
        next_number += 1

    manifest = {
        "source_movie": str(args.source_movie.resolve()),
        "start_state": str(args.start_state.resolve()),
        "start_vi": route.start_vi,
        "route_frames": len(route.rows),
        "slash_row": slash_row,
        "original_cancel_row": cancel_row,
        "early_cancel_row": early_row,
        "goal": "leave leaf one gameplay frame earlier, land on the platform, retain magic 13",
        "candidates": [],
    }
    for name, rows, description in specs:
        movie = args.output_dir / f"{name}.dtm"
        patch_route_movie(route, rows, movie)
        shutil.copy2(args.start_state, Path(str(movie) + ".sav"))
        shutil.copy2(movie, Path(str(movie) + ".sav.dtm"))
        manifest["candidates"].append({
            "order": len(manifest["candidates"]) + 1,
            "name": name,
            "description": description,
            "movie": str(movie.resolve()),
            "state": str(Path(str(movie) + ".sav").resolve()),
        })
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
