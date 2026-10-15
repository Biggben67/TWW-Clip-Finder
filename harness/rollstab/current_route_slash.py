#!/usr/bin/env python3
"""Search small edits to a captured route's final walk-to-slash transition.

This tool is intentionally offline.  It reconstructs Link from a rich live seed,
keeps the captured movie prefix intact, and emits complete native DTMs for manual
playback.  It never opens or advances Dolphin.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from harness.collision.offline_moving_drop import _make_seed, _step
from harness.rollstab.recorded_route import (
    DTM_HEADER_SIZE,
    CONTROLLER_ROW_SIZE,
    RecordedRoute,
    decode_controller_row,
    movie_vi_from_savestate,
)
from harness.rollstab.seamgeo import SeamGeo
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.land.constants import SUBJECTIVITY
from tww_sim.land.walls import _mk_tri as make_wall


def _route(source: Path, state: Path) -> RecordedRoute:
    # Zelda TAS Edition's Wind Waker movie uses four P1 polls per 30-Hz game
    # frame, and this savestate field is the game-frame cursor.  Treating it as
    # a 60-Hz VI cursor reads exactly halfway through a long movie.
    start_frame = movie_vi_from_savestate(state)
    data = source.read_bytes()
    body = data[DTM_HEADER_SIZE:]
    raw = [body[i:i + CONTROLLER_ROW_SIZE]
           for i in range(0, len(body) - CONTROLLER_ROW_SIZE + 1,
                          CONTROLLER_ROW_SIZE)]
    rows = []
    # Each VI stores two lanes and two polls: the tuner/GBA lane first and P1
    # GameCube input second.  Wind Waker executes gameplay every other VI.
    total_vi = len(raw) // 4
    for vi in range(start_frame, total_vi, 2):
        rows.append(decode_controller_row(raw[vi * 4 + 3]))
    return RecordedRoute(source, state, start_frame, total_vi, 0, tuple(rows))


def _mesh(records, maker):
    return [maker(record) for record in records]


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _row(base, sx=None, sy=None, *, forward=False, camera=None):
    row = dict(base)
    if forward:
        sx, sy = stick_for_bearing(camera[0], camera[1], 1.0)
    if sx is not None:
        row["stickX"] = int(sx)
    if sy is not None:
        row["stickY"] = int(sy)
    return row


class CapturedCameraTrace:
    """Camera-angle source for an offline replay captured from the same route.

    First-person exit changes camera mode. ``CameraManual`` intentionally models
    settled manual camera only, so substituting it here would corrupt the first
    movement headings while still looking close. A captured trace keeps the
    player/action simulation exact until the subject-camera port is complete.
    """

    def __init__(self, angles, index=0):
        self.angles = tuple(int(angle) & 0xFFFF for angle in angles)
        if not self.angles:
            raise ValueError("camera trace is empty")
        self.index = int(index)
        self.csangle = self.angles[self.index]

    def step(self, _csx=128, _csy=128):
        self.index = min(self.index + 1, len(self.angles) - 1)
        self.csangle = self.angles[self.index]
        return self.csangle

    def clone(self):
        return CapturedCameraTrace(self.angles, self.index)


def _preceding_rows(source: Path, start_vi: int, count: int = 3):
    """Decode gameplay rows immediately preceding a native tuner/P1 movie cursor."""
    data = source.read_bytes()[DTM_HEADER_SIZE:]
    raw = [data[i:i + CONTROLLER_ROW_SIZE]
           for i in range(0, len(data) - CONTROLLER_ROW_SIZE + 1,
                          CONTROLLER_ROW_SIZE)]
    first = start_vi - count * 2
    if first < 0:
        raise ValueError("movie does not contain enough pre-savestate input history")
    return [decode_controller_row(raw[vi * 4 + 3])
            for vi in range(first, start_vi, 2)]


def replay(seed, walls, rows, *, prior_rows=(), camera_angles=()):
    # The generic live-slash seed stores the current calculated pose directly;
    # moving-drop anchors also carry it under ``previous``.  SUBJECTIVITY is
    # stationary here, so the current pose is the correct previous draw source.
    if not seed.get("previous"):
        seed = dict(seed)
        seed["previous"] = seed
    raw_state = int(seed["snapshot"].get("state", -1))
    # Dolphin exposes the first-person action as raw proc 154; LandState's
    # compact modeled enum calls the same action SUBJECTIVITY (1).
    force_state = SUBJECTIVITY if raw_state == 154 else None
    seed = dict(seed)
    if len(seed.get("rows", ())) < 3 and prior_rows:
        # LandState has two frames of controller latency. The third row supplies
        # the prior A/B edge state, which is essential when B exits first person.
        seed["rows"] = [dict(row) for row in prior_rows[-3:]]
    node = _make_seed(seed, walls, force_state=force_state, model_draw=True)
    if raw_state == 154 and len(seed.get("rows", ())) < 3:
        raise ValueError(
            "a first-person seed requires three preceding gameplay rows; "
            "neutral padding changes its exit and acceleration"
        )
    if camera_angles:
        node.state._cam = CapturedCameraTrace(camera_angles)
    states = [node]
    for row in rows:
        node = _step(node, row)
        states.append(node)
    return states


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path("_generated/slash_clip_current"))
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    source_dir = root / "source"
    seed = json.loads((root / "start_seed.json").read_text(encoding="ascii"))
    geometry = json.loads((root / "geometry.json").read_text(encoding="ascii"))
    route = _route(source_dir / "source.dtm", source_dir / "slot5.sav")
    walls = _mesh(geometry["wall_mesh"]["polys"], make_wall)
    trace = json.loads((source_dir / "live_trace.json").read_text(encoding="ascii"))
    states = replay(
        seed, walls, route.rows,
        prior_rows=_preceding_rows(route.movie, route.start_vi),
        camera_angles=[frame["camera"] for frame in trace],
    )
    # This diagnostic owns the first-person exit and locomotion prefix. Stop at
    # CUT_L dispatch; sword-action reconstruction is a separate model and must
    # not make the proven prefix appear inaccurate.
    prefix_length = next(
        (index for index, frame in enumerate(trace) if frame["state"] == 68),
        min(len(states), len(trace)),
    )
    report = []
    for index in range(min(len(states), len(trace), prefix_length)):
        state = states[index].state
        live = trace[index]
        report.append({
            "i": index,
            "sim": [state.pos_x, state.pos_z],
            "live": [live["x"], live["z"]],
            "error": _distance((state.pos_x, state.pos_z), (live["x"], live["z"])),
            "sim_state": state.state,
            "live_state": live["state"],
            "sim_facing": state.facing,
            "live_facing": live["facing"],
            "sim_travel": state.travel,
            "live_travel": live["travel"],
            "sim_speed": state.speedF,
            "live_speed": live["speedF"],
        })
    (root / "offline_replay_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="ascii"
    )
    for item in report:
        print(
            f"{item['i']:2d} err={item['error']:.6f} "
            f"proc={item['sim_state']}/{item['live_state']} "
            f"F={item['sim_facing']}/{item['live_facing']} "
            f"T={item['sim_travel']}/{item['live_travel']} "
            f"speed={item['sim_speed']:.6f}/{item['live_speed']:.6f}"
        )
    mismatches = [
        item for item in report
        if item["error"] != 0.0
        or item["sim_facing"] != item["live_facing"]
        or item["sim_travel"] != item["live_travel"]
    ]
    if mismatches:
        raise SystemExit(
            f"first-person locomotion prefix diverged on {len(mismatches)} frame(s)"
        )
    print(f"validated {len(report)} exact first-person/locomotion frames through pre-slash")
    if args.diagnose:
        return

    # Search/export is added only after the baseline reconstruction is proven
    # against the captured trace.  Refusing here prevents plausible-looking but
    # phase-wrong movies from being emitted.
    raise SystemExit("baseline diagnostic complete; inspect replay errors before search")


if __name__ == "__main__":
    main()
