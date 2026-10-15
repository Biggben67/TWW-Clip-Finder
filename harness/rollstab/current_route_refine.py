#!/usr/bin/env python3
"""Bounded, route-first refinement for the captured GanonA slash clip.

The supplied movie is authoritative.  This tool first diagnoses the action it
actually dispatches, then changes only controller rows that can affect the cut
old pose.  Every accepted result is replayed through ``enter_cut_from_move``
and the exact movable-BG seam collision predicate.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import struct
from dataclasses import dataclass
from pathlib import Path

from harness.collision.offline_moving_drop import _step
from harness.rollstab.current_route_slash import (
    _mesh,
    _preceding_rows,
    _route,
    replay,
)
from harness.rollstab.recorded_route import install_route_movie
from harness.rollstab.seamgeo import SeamGeo
from tww_sim.core.camera.camera_manual import CameraManual
from tww_sim.land.constants import ATN_MOVE, CUT_F, MOVE
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.land.walls import _mk_tri as make_wall


VARIABLE_ROWS = tuple(range(17, 25))
DISPATCH_ROW = 26
FORWARD_SELECT_ROW = DISPATCH_ROW - 2
REPLACEMENT_ROWS = tuple(range(17, 26))
REPLACEMENT_DISPATCH_ROW = 27
REPLACEMENT_SELECT_ROW = REPLACEMENT_DISPATCH_ROW - 2
CAMERA_HANDOFF_ROW = 19

_START = None
_ROUTE = None
_SEAM = None
_DUST_TARGETS = None
_DUST_DYNAMICS = None


@dataclass(frozen=True)
class Result:
    exact: bool
    score: float
    controls: tuple[int, ...]
    old: tuple[float, float]
    new: tuple[float, float]
    state: int
    facing: int
    travel: int
    speedf: float
    aim_error: int
    ray_error: float
    reach_error: float


def _load(root: Path):
    global _START, _ROUTE, _SEAM, _DUST_TARGETS, _DUST_DYNAMICS
    source = root / "source"
    seed = json.loads((root / "start_seed.json").read_text(encoding="ascii"))
    geometry = json.loads((root / "geometry.json").read_text(encoding="ascii"))
    trace = json.loads((source / "live_trace.json").read_text(encoding="ascii"))
    route = _route(source / "source.dtm", source / "slot5.sav")
    walls = _mesh(geometry["wall_mesh"]["polys"], make_wall)
    _START = replay(
        seed,
        walls,
        (),
        prior_rows=_preceding_rows(route.movie, route.start_vi),
        camera_angles=[frame["camera"] for frame in trace],
    )[0]
    _ROUTE = route
    _SEAM = SeamGeo(geometry["geo"], int(trace[0]["camera"]))
    dust_path = root / "replacement_dust.json"
    if dust_path.exists():
        payload = json.loads(dust_path.read_text(encoding="ascii"))
        _DUST_TARGETS = [tuple(point) for point in payload["old"]]
        _DUST_DYNAMICS = (
            int(payload["facing"]), int(payload["travel"]),
            int(payload["speed_bits"]),
        )


def _init_worker(root: str):
    _load(Path(root))


def controls_from_rows(rows) -> tuple[int, ...]:
    values = []
    for index in VARIABLE_ROWS:
        values.extend((int(rows[index]["stickX"]), int(rows[index]["stickY"])))
    return tuple(values)


def rows_from_controls(controls):
    rows = [dict(row) for row in _ROUTE.rows]
    for offset, index in enumerate(VARIABLE_ROWS):
        rows[index]["stickX"] = int(controls[offset * 2])
        rows[index]["stickY"] = int(controls[offset * 2 + 1])
    return rows


def replacement_controls_from_rows(rows) -> tuple[int, ...]:
    values = []
    for index in REPLACEMENT_ROWS:
        values.extend((int(rows[index]["stickX"]), int(rows[index]["stickY"])))
    return tuple(values)


def replacement_rows_from_controls(controls):
    rows = [dict(row) for row in _ROUTE.rows]
    for offset, index in enumerate(REPLACEMENT_ROWS):
        rows[index]["stickX"] = int(controls[offset * 2])
        rows[index]["stickY"] = int(controls[offset * 2 + 1])
    # Move the initial B edge from row 21 to the already-held B on row 22.
    rows[21]["buttons"] &= ~0x200
    return rows


def camera_controls_from_main(controls):
    values = []
    for offset in range(len(REPLACEMENT_ROWS)):
        values.extend((controls[offset * 2], controls[offset * 2 + 1], 128, 128))
    return tuple(values)


def camera_rows_from_controls(controls):
    rows = [dict(row) for row in _ROUTE.rows]
    for offset, index in enumerate(REPLACEMENT_ROWS):
        base = offset * 4
        rows[index]["stickX"] = int(controls[base])
        rows[index]["stickY"] = int(controls[base + 1])
        rows[index]["substickX"] = int(controls[base + 2])
        rows[index]["substickY"] = int(controls[base + 3])
    rows[21]["buttons"] &= ~0x200
    return rows


def _signed_angle_distance(a: int, b: int) -> int:
    return ((int(a) - int(b) + 0x8000) & 0xFFFF) - 0x8000


def _finish_result(controls, state, old, source_state, source_facing):
    new = (state.pos_x, state.pos_z)
    dx, dz = new[0] - old[0], new[1] - old[1]
    length = math.hypot(dx, dz) or 1.0
    sx, sz = _SEAM.S
    along = ((sx - old[0]) * dx + (sz - old[1]) * dz) / length
    reach_error = max(0.0, -along) + max(0.0, along - length)
    ray_error = abs(_SEAM.perp_to_ray(old, new))
    aim_error = abs(_signed_angle_distance(state.target, source_facing))
    valid_action = state.state == CUT_F and aim_error < state.CUT_DIR_FWD
    valid_source = source_state in (MOVE, ATN_MOVE)
    exact = (valid_action and valid_source and reach_error == 0.0
             and ray_error <= 0.01 and _SEAM.genuine_clip(old, new))
    action_penalty = 0.0 if valid_action and valid_source else 100000.0 + aim_error
    return Result(
        exact, action_penalty + reach_error * 10.0 + ray_error,
        tuple(int(value) for value in controls), old, new, int(state.state),
        int(state.facing), int(state.travel), float(state.speedF), aim_error,
        ray_error, reach_error,
    )


# Authoritative evaluator definitions.  Kept adjacent so future route modes do
# not split the shared dispatch tail across function insertions.
def evaluate(controls) -> Result:
    rows = rows_from_controls(controls)
    node = _START
    for index in range(DISPATCH_ROW):
        node = _step(node, rows[index])
    state = node.state
    old = (state.pos_x, state.pos_z)
    source_state, source_facing = int(state.state), int(state.facing)
    dispatch = rows[DISPATCH_ROW]
    state.enter_cut_from_move(
        dispatch["stickX"], dispatch["stickY"],
        csx=dispatch.get("substickX", 128), csy=dispatch.get("substickY", 128),
    )
    return _finish_result(controls, state, old, source_state, source_facing)


def evaluate_dust_target(controls) -> Result:
    result = evaluate_replacement(controls)
    if result.exact:
        return result
    if not _DUST_TARGETS or _DUST_DYNAMICS is None:
        raise RuntimeError("replacement_dust.json is missing or empty")
    dynamics = (result.facing, result.travel, _bits(result.speedf))
    if dynamics != _DUST_DYNAMICS:
        return Result(
            result.exact, 100000.0 + result.score, result.controls,
            result.old, result.new, result.state, result.facing, result.travel,
            result.speedf, result.aim_error, result.ray_error, result.reach_error,
        )
    nearest = min(
        _DUST_TARGETS,
        key=lambda point: (result.old[0] - point[0]) ** 2
        + (result.old[1] - point[1]) ** 2,
    )
    distance = math.hypot(result.old[0] - nearest[0], result.old[1] - nearest[1])
    return Result(
        result.exact, distance, result.controls, result.old, result.new,
        result.state, result.facing, result.travel, result.speedf,
        result.aim_error, result.ray_error, result.reach_error,
    )


def evaluate_replacement(controls) -> Result:
    rows = replacement_rows_from_controls(controls)
    node = _START
    for index in range(REPLACEMENT_DISPATCH_ROW):
        node = _step(node, rows[index])
    state = node.state
    old = (state.pos_x, state.pos_z)
    source_state, source_facing = int(state.state), int(state.facing)
    dispatch = rows[REPLACEMENT_DISPATCH_ROW]
    state.enter_cut_from_move(
        dispatch["stickX"], dispatch["stickY"],
        csx=dispatch.get("substickX", 128), csy=dispatch.get("substickY", 128),
    )
    return _finish_result(controls, state, old, source_state, source_facing)


def evaluate_camera(controls) -> Result:
    rows = camera_rows_from_controls(controls)
    node = _START
    for index in range(REPLACEMENT_DISPATCH_ROW):
        if index == CAMERA_HANDOFF_ROW:
            node.state._cam = CameraManual(node.state._cam.csangle)
        node = _step(node, rows[index])
    state = node.state
    old = (state.pos_x, state.pos_z)
    source_state, source_facing = int(state.state), int(state.facing)
    dispatch = rows[REPLACEMENT_DISPATCH_ROW]
    state.enter_cut_from_move(
        dispatch["stickX"], dispatch["stickY"],
        csx=dispatch.get("substickX", 128), csy=dispatch.get("substickY", 128),
    )
    return _finish_result(controls, state, old, source_state, source_facing)


def _bits(value: float) -> int:
    return struct.unpack(">I", struct.pack(">f", float(value)))[0]


def _signature(result: Result):
    return (
        _bits(result.old[0]), _bits(result.old[1]),
        result.facing, result.travel, _bits(result.speedf),
        _bits(result.new[0]), _bits(result.new[1]),
    )


def exact_dust_for(result: Result, along_step=0.02, perp_step=0.00002,
                   perp_width=0.001):
    """Enumerate the exact accepted old-position lattice for one cut family."""
    dx, dz = result.new[0] - result.old[0], result.new[1] - result.old[1]
    length = math.hypot(dx, dz)
    ux, uz = dx / length, dz / length
    px, pz = -uz, ux
    hits = []
    along = 30.0
    while along <= length:
        perp = -perp_width
        while perp <= perp_width:
            old = (
                struct.unpack(">f", struct.pack(">f", _SEAM.S[0] - along * ux + perp * px))[0],
                struct.unpack(">f", struct.pack(">f", _SEAM.S[1] - along * uz + perp * pz))[0],
            )
            # The displacement is translation invariant for fixed facing,
            # travel, and speed; rebuild it through SeamGeo for exact f32 adds.
            new = _SEAM.cut_new(
                old, facing=result.facing, travel=result.travel,
                speedf=result.speedf,
            )
            if _SEAM.genuine_clip(old, new):
                hits.append((old, new, _SEAM.perp_to_ray(old, new)))
            perp += perp_step
        along += along_step
    return hits


def _forward_repair(controls, baseline: Result):
    """Choose a full stick aimed along the captured pre-cut facing."""
    repaired = list(controls)
    offset = (FORWARD_SELECT_ROW - VARIABLE_ROWS[0]) * 2
    rows = rows_from_controls(controls)
    node = _START
    for index in range(DISPATCH_ROW):
        node = _step(node, rows[index])
    camera = node.state._cam.csangle
    repaired[offset], repaired[offset + 1] = stick_for_bearing(
        node.state.facing, camera, 1.0,
    )
    return tuple(repaired)


def influential_axes(base, delta=32):
    reference = evaluate(base)
    signature = _signature(reference)
    axes = []
    for axis, value in enumerate(base):
        for amount in (-delta, delta):
            trial = list(base)
            trial[axis] = max(0, min(255, value + amount))
            if _signature(evaluate(tuple(trial))) != signature:
                axes.append(axis)
                break
    # The direction-selecting poll must remain searchable even if the chosen
    # delta aliases to the same quantized target.
    direction_offset = (FORWARD_SELECT_ROW - VARIABLE_ROWS[0]) * 2
    axes.extend((direction_offset, direction_offset + 1))
    return tuple(sorted(set(axes)))


def _replacement_repair(controls):
    rows = replacement_rows_from_controls(controls)
    node = _START
    for index in range(REPLACEMENT_DISPATCH_ROW):
        node = _step(node, rows[index])
    repaired = list(controls)
    offset = (REPLACEMENT_SELECT_ROW - REPLACEMENT_ROWS[0]) * 2
    repaired[offset], repaired[offset + 1] = stick_for_bearing(
        node.state.facing, node.state._cam.csangle, 1.0,
    )
    return tuple(repaired)


def replacement_influential_axes(base, delta=32):
    reference = evaluate_replacement(base)
    signature = _signature(reference)
    axes = []
    for axis, value in enumerate(base):
        for amount in (-delta, delta):
            trial = list(base)
            trial[axis] = max(0, min(255, value + amount))
            if _signature(evaluate_replacement(tuple(trial))) != signature:
                axes.append(axis)
                break
    offset = (REPLACEMENT_SELECT_ROW - REPLACEMENT_ROWS[0]) * 2
    axes.extend((offset, offset + 1))
    return tuple(sorted(set(axes)))


def camera_influential_axes(base, delta=8):
    reference = evaluate_camera(base)
    signature = _signature(reference)
    axes = []
    for axis, value in enumerate(base):
        for amount in (-delta, delta):
            trial = list(base)
            trial[axis] = max(0, min(255, value + amount))
            if _signature(evaluate_camera(tuple(trial))) != signature:
                axes.append(axis)
                break
    return tuple(axes)


def _mutations(parent, axes, radius, rng, random_count=24):
    yield parent
    for axis in axes:
        for amount in (-radius, radius):
            trial = list(parent)
            trial[axis] = max(0, min(255, trial[axis] + amount))
            yield tuple(trial)
    for _ in range(random_count):
        trial = list(parent)
        count = 1 + rng.randrange(min(4, len(axes)))
        for axis in rng.sample(axes, count):
            trial[axis] = max(0, min(255, trial[axis] + rng.randint(-radius, radius)))
        yield tuple(trial)


def refine(root: Path, workers: int, beam_width: int, evaluation_cap: int,
           seed: int, log=print):
    _load(root)
    trace = json.loads((root / "source" / "live_trace.json").read_text(encoding="ascii"))
    live_cut = next((frame for frame in trace if frame["state"] in (CUT_F, 0x44, 0x45)), None)
    manual_action = int(live_cut["state"]) if live_cut else -1
    base = controls_from_rows(_ROUTE.rows)
    baseline = evaluate(base)
    log(f"Manual route dispatch: proc {manual_action} (CUT_F is {CUT_F}).")
    repaired = _forward_repair(base, baseline)
    repaired_result = evaluate(repaired)
    axes = influential_axes(repaired)
    log(
        "Forward repair: old=(%.9f, %.9f), new=(%.9f, %.9f), "
        "ray=%.6f, reach=%.6f; %d/%d analog bytes influence the transition."
        % (*repaired_result.old, *repaired_result.new, repaired_result.ray_error,
           repaired_result.reach_error, len(axes), len(repaired))
    )
    rng = random.Random(seed)
    pool = mp.Pool(max(1, workers), initializer=_init_worker, initargs=(str(root),))
    cache = {repaired: repaired_result}
    beam = [repaired]
    evaluations = 1
    best = repaired_result
    try:
        for generation, radius in enumerate(
                (128, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1, 1), 1):
            candidates = set()
            for parent in beam:
                candidates.update(_mutations(
                    parent, axes, radius, rng,
                    random_count=1500 if generation == 1 else 24,
                ))
                if len(candidates) >= max(beam_width * 40, 1000):
                    break
            unseen = [candidate for candidate in candidates if candidate not in cache]
            remaining = evaluation_cap - evaluations
            if remaining <= 0:
                break
            unseen = unseen[:remaining]
            for candidate, result in zip(
                    unseen, pool.map(evaluate, unseen, chunksize=8)):
                cache[candidate] = result
            evaluations += len(unseen)
            ranked = sorted((cache[candidate] for candidate in candidates if candidate in cache),
                            key=lambda item: (not item.exact, item.score))
            if ranked and (ranked[0].exact or ranked[0].score < best.score):
                best = ranked[0]
            log(
                "radius=%3d evals=%d best=%.9f old=(%.9f, %.9f) "
                "CUT_F=%s exact=%s" %
                (radius, evaluations, best.score, *best.old,
                 best.state == CUT_F, best.exact)
            )
            if best.exact:
                return best, manual_action, axes, evaluations
            diverse = {}
            for result in ranked:
                diverse.setdefault(_signature(result), result.controls)
                if len(diverse) >= beam_width:
                    break
            beam = list(diverse.values())
        return best, manual_action, axes, evaluations
    finally:
        pool.close()
        pool.join()


def synthesize_replacement(root: Path, workers: int, beam_width: int,
                           evaluation_cap: int, seed: int, log=print,
                           initial_controls=None, fine_only: bool = False):
    """Search the one-row-later CUT_F family after the manual route is rejected."""
    _load(root)
    initial = (tuple(int(value) for value in initial_controls)
               if initial_controls is not None
               else _replacement_repair(replacement_controls_from_rows(_ROUTE.rows)))
    initial_result = evaluate_replacement(initial)
    axes = replacement_influential_axes(initial)
    log(
        "Replacement timing: old=(%.9f, %.9f), new=(%.9f, %.9f), "
        "ray=%.6f, reach=%.6f, source/action valid=%s; %d/%d influential bytes."
        % (*initial_result.old, *initial_result.new, initial_result.ray_error,
           initial_result.reach_error, initial_result.score < 100000.0,
           len(axes), len(initial))
    )
    rng = random.Random(seed)
    pool = mp.Pool(max(1, workers), initializer=_init_worker, initargs=(str(root),))
    cache = {initial: initial_result}
    beam = [initial]
    evaluations = 1
    best = initial_result
    try:
        radii = ((2, 1, 1, 1, 1, 1)
                 if fine_only else
                 (128, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1, 1))
        for generation, radius in enumerate(radii, 1):
            candidates = set()
            for parent in beam:
                candidates.update(_mutations(
                    parent, axes, radius, rng,
                    random_count=1800 if generation == 1 else 28,
                ))
                if len(candidates) >= max(beam_width * 48, 1200):
                    break
            remaining = evaluation_cap - evaluations
            if remaining <= 0:
                break
            unseen = [candidate for candidate in candidates if candidate not in cache][:remaining]
            for candidate, result in zip(
                    unseen, pool.map(evaluate_replacement, unseen, chunksize=8)):
                cache[candidate] = result
            evaluations += len(unseen)
            ranked = sorted(
                (cache[candidate] for candidate in candidates if candidate in cache),
                key=lambda item: (not item.exact, item.score),
            )
            if ranked and (ranked[0].exact or ranked[0].score < best.score):
                best = ranked[0]
            log(
                "replacement radius=%3d evals=%d best=%.9f old=(%.9f, %.9f) exact=%s"
                % (radius, evaluations, best.score, *best.old, best.exact)
            )
            if best.exact:
                return best, axes, evaluations
            diverse = {}
            for result in ranked:
                diverse.setdefault(_signature(result), result.controls)
                if len(diverse) >= beam_width:
                    break
            beam = list(diverse.values())
        return best, axes, evaluations
    finally:
        pool.close()
        pool.join()


def refine_camera(root: Path, workers: int, beam_width: int,
                  evaluation_cap: int, seed: int, main_controls, log=print):
    """Add C-stick variation only after the captured camera has settled."""
    _load(root)
    initial = camera_controls_from_main(main_controls)
    initial_result = evaluate_camera(initial)
    captured_result = evaluate_replacement(main_controls)
    if _signature(initial_result) != _signature(captured_result):
        raise RuntimeError(
            "C-stick search disabled: neutral CameraManual does not reproduce "
            "the captured target-camera slash transition bit-exactly"
        )
    axes = camera_influential_axes(initial)
    log(
        "Camera refinement baseline: ray=%.9f old=(%.9f, %.9f); "
        "%d/%d main/C-stick bytes influence the transition."
        % (initial_result.ray_error, *initial_result.old, len(axes), len(initial))
    )
    rng = random.Random(seed)
    pool = mp.Pool(max(1, workers), initializer=_init_worker, initargs=(str(root),))
    cache = {initial: initial_result}
    beam = [initial]
    evaluations = 1
    best = initial_result
    try:
        for generation, radius in enumerate((8, 6, 4, 3, 2, 1, 1, 1), 1):
            candidates = set()
            for parent in beam:
                candidates.update(_mutations(
                    parent, axes, radius, rng,
                    random_count=1200 if generation == 1 else 24,
                ))
                if len(candidates) >= max(beam_width * 44, 1200):
                    break
            remaining = evaluation_cap - evaluations
            if remaining <= 0:
                break
            unseen = [candidate for candidate in candidates if candidate not in cache][:remaining]
            for candidate, result in zip(
                    unseen, pool.map(evaluate_camera, unseen, chunksize=8)):
                cache[candidate] = result
            evaluations += len(unseen)
            ranked = sorted(
                (cache[candidate] for candidate in candidates if candidate in cache),
                key=lambda item: (not item.exact, item.score),
            )
            if ranked and (ranked[0].exact or ranked[0].score < best.score):
                best = ranked[0]
            log(
                "camera radius=%2d evals=%d best=%.9f old=(%.9f, %.9f) exact=%s"
                % (radius, evaluations, best.score, *best.old, best.exact)
            )
            if best.exact:
                return best, axes, evaluations
            diverse = {}
            for result in ranked:
                diverse.setdefault(_signature(result), result.controls)
                if len(diverse) >= beam_width:
                    break
            beam = list(diverse.values())
        return best, axes, evaluations
    finally:
        pool.close()
        pool.join()


def prepare_replacement_dust(root: Path, controls):
    _load(root)
    result = evaluate_replacement(controls)
    hits = exact_dust_for(result)
    payload = {
        "facing": result.facing,
        "travel": result.travel,
        "speed_bits": _bits(result.speedf),
        "old": [list(hit[0]) for hit in hits],
    }
    (root / "replacement_dust.json").write_text(
        json.dumps(payload, indent=2), encoding="ascii"
    )
    _load(root)
    return result, hits


def refine_dust_target(root: Path, workers: int, beam_width: int,
                       evaluation_cap: int, seed: int, initial, log=print):
    """Move the route onto exact dust while preserving its cut dynamics bits."""
    baseline, hits = prepare_replacement_dust(root, initial)
    if not hits:
        raise RuntimeError("current CUT_F dynamics have no exact seam dust")
    axes = replacement_influential_axes(initial)
    ranked_initial = evaluate_dust_target(initial)
    log(
        "Dust-target refinement: %d exact old points; route distance=%.9f; "
        "%d influential bytes." % (len(hits), ranked_initial.score, len(axes))
    )
    rng = random.Random(seed)
    pool = mp.Pool(max(1, workers), initializer=_init_worker, initargs=(str(root),))
    cache = {tuple(initial): ranked_initial}
    beam = [tuple(initial)]
    evaluations = 1
    best = ranked_initial
    try:
        for generation, radius in enumerate((16, 12, 8, 6, 4, 3, 2, 1, 1, 1), 1):
            candidates = set()
            for parent in beam:
                candidates.update(_mutations(
                    parent, axes, radius, rng,
                    random_count=1200 if generation == 1 else 24,
                ))
                if len(candidates) >= max(beam_width * 44, 1200):
                    break
            remaining = evaluation_cap - evaluations
            if remaining <= 0:
                break
            unseen = [candidate for candidate in candidates if candidate not in cache][:remaining]
            for candidate, result in zip(
                    unseen, pool.map(evaluate_dust_target, unseen, chunksize=8)):
                cache[candidate] = result
            evaluations += len(unseen)
            ranked = sorted(
                (cache[candidate] for candidate in candidates if candidate in cache),
                key=lambda item: (not item.exact, item.score),
            )
            if ranked and (ranked[0].exact or ranked[0].score < best.score):
                best = ranked[0]
            log(
                "dust radius=%2d evals=%d distance=%.9f ray=%.9f exact=%s"
                % (radius, evaluations, best.score, best.ray_error, best.exact)
            )
            if best.exact:
                return best, axes, evaluations
            diverse = {}
            for result in ranked:
                diverse.setdefault(_signature(result), result.controls)
                if len(diverse) >= beam_width:
                    break
            beam = list(diverse.values())
        return best, axes, evaluations
    finally:
        pool.close()
        pool.join()


def export(root: Path, result: Result, output: Path):
    rows = rows_from_controls(result.controls)
    return install_route_movie(_ROUTE, rows, output, short=False)


def export_replacement(root: Path, result: Result, output: Path):
    rows = replacement_rows_from_controls(result.controls)
    return install_route_movie(_ROUTE, rows, output, short=False)


def export_camera(root: Path, result: Result, output: Path):
    rows = camera_rows_from_controls(result.controls)
    return install_route_movie(_ROUTE, rows, output, short=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path("_generated/slash_clip_current"))
    parser.add_argument("--workers", type=int,
                        default=max(1, min(10, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--beam", type=int, default=96)
    parser.add_argument("--evaluation-cap", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=615507812)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replacement", action="store_true",
                        help="search the one-row-later replacement CUT_F family")
    parser.add_argument("--resume", action="store_true",
                        help="resume replacement refinement from route_refine_result.json")
    parser.add_argument("--camera", action="store_true",
                        help="add bit-exact settled manual-camera/C-stick refinement")
    parser.add_argument("--dust-target", action="store_true",
                        help="refine onto exact dust while preserving CUT_F dynamics")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.dust_target:
        previous = json.loads(
            (root / "route_refine_result.json").read_text(encoding="ascii")
        )
        initial = tuple(value for pair in previous["controls"] for value in pair)
        result, axes, evaluations = refine_dust_target(
            root, args.workers, args.beam, args.evaluation_cap, args.seed, initial,
        )
        manual_action = None
        variable_rows = REPLACEMENT_ROWS
    elif args.camera:
        previous = json.loads(
            (root / "route_refine_result.json").read_text(encoding="ascii")
        )
        main_controls = tuple(
            value for pair in previous["controls"] for value in pair
        )
        result, axes, evaluations = refine_camera(
            root, args.workers, args.beam, args.evaluation_cap, args.seed,
            main_controls,
        )
        manual_action = None
        variable_rows = REPLACEMENT_ROWS
    elif args.replacement:
        initial_controls = None
        if args.resume:
            previous = json.loads(
                (root / "route_refine_result.json").read_text(encoding="ascii")
            )
            initial_controls = tuple(
                value for pair in previous["controls"] for value in pair
            )
        result, axes, evaluations = synthesize_replacement(
            root, args.workers, args.beam, args.evaluation_cap, args.seed,
            initial_controls=initial_controls, fine_only=args.resume,
        )
        manual_action = None
        variable_rows = REPLACEMENT_ROWS
    else:
        result, manual_action, axes, evaluations = refine(
            root, args.workers, args.beam, args.evaluation_cap, args.seed,
        )
        variable_rows = VARIABLE_ROWS
    payload = {
        "exact": result.exact,
        "manual_action": manual_action,
        "evaluations": evaluations,
        "influential_axes": list(axes),
        "variable_rows": list(variable_rows),
        "controls": [list(result.controls[i:i + 2])
                     for i in range(0, len(result.controls), 2)],
        "old": list(result.old),
        "new": list(result.new),
        "state": result.state,
        "facing": result.facing,
        "travel": result.travel,
        "speedF": result.speedf,
        "ray_error": result.ray_error,
        "reach_error": result.reach_error,
    }
    result_path = root / "route_refine_result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="ascii")
    print(f"wrote {result_path}")
    if not result.exact:
        family = ("dust-target replacement" if args.dust_target else
                  "camera replacement" if args.camera else
                  "replacement" if args.replacement else "manual route")
        raise SystemExit(f"{family} remained non-exact within the bounded budget")
    output = args.output or root / "slash_clip_refined.dtm"
    exporter = (export_camera if args.camera else export_replacement
                if args.replacement or args.dust_target else export)
    print(f"exported {exporter(root, result, output)}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
