"""Native route refinement for walking through a seam with chest storage."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random

from harness.rollstab.native_route import (
    NativeFamily, NativeWorker, decode_row, extract_assets, f32_equal,
    first_editable_row, infer_input_delay, validate_replay,
)
from harness.rollstab.native_route_timing import align_movie_polls
from harness.rollstab.recorded_route import install_route_movie
from harness.rollstab.route_constraints import FacingRanges
from harness.rollstab.seamgeo import SeamGeo
from harness.rollstab.smart_route_search import RouteResult, _route
from tww_sim.land.plan_land import stick_for_bearing

WALL_NONE = 0x4
WALL_HIT = 0x10
LINE_CHECK_HIT = 0x10000
GROUND_HIT = 0x20
AXES = ("stickX", "stickY", "substickX", "substickY")


def storage_active(trace):
    seeds = trace.get("native", {}).get("seeds", ())
    return bool(seeds and all(seed.get("collision_flags", 0) & WALL_NONE for seed in seeds)
                and any(frame["after"]["state"] in (6, 7, 24)
                        for frame in trace.get("trace", ())))


@dataclass(frozen=True)
class StorageResult(RouteResult):
    target_distance: float = math.inf
    landing_distance: float = math.inf
    landing_speed: float = 0.0
    grounded: bool = False

    @property
    def score(self):
        if self.exact:
            return -1000000.0 + self.dispatch_row * 100.0 - self.speedf
        return (self.target_distance + self.reach_error + self.ray_error * 0.1
                + self.aim_error / 1024.0 + self.retention_error)


def crossing_result(frames, seam, controls, anchor, facing_ranges, require_oob,
                    oob_tolerance, oob_min_speed, roll_on_clip, roll_facing_ranges,
                    phase="storage walk"):
    if not frames:
        return StorageResult(False, phase, anchor + 1, -1, anchor + 1, tuple(controls),
                             (0., 0.), (0., 0.), -1, 0, 0, 0., math.inf,
                             math.inf, 0, target_distance=math.inf)
    sx, sz = seam.S
    planes = (seam.wA.pla, seam.wB.pla)
    best = None
    for index, frame in enumerate(frames):
        old, pos = frame["old"], frame["pos"]
        distance = math.hypot(pos[0] - sx, pos[2] - sz)
        dx, dz = pos[0] - old[0], pos[2] - old[2]
        length = math.hypot(dx, dz)
        if length:
            along = ((sx - old[0]) * dx + (sz - old[2]) * dz) / length
            ray = abs((sx - old[0]) * dz - (sz - old[2]) * dx) / length
            reach = max(0., -along, along - length)
        else:
            ray, reach = distance, distance
        face = max(0., *(plane.func(pos) for plane in planes))
        aim = facing_ranges.distance(frame["facing"])
        flags = int(frame.get("flags", 0))
        retained = (index + 2 < len(frames)
                    and all(all(plane.func(later["pos"]) < 0 for plane in planes)
                            and later.get("flags", 0) & WALL_NONE
                            for later in frames[index + 1:index + 3]))
        crossed = (any(plane.func(old) > 0 for plane in planes)
                   and all(plane.func(pos) < 0 for plane in planes))
        clean = (all(item.get("flags", 0) & WALL_NONE for item in frames[:index + 3])
                 and not flags & (WALL_HIT | LINE_CHECK_HIT)
                 and all(f32_equal(frame["raw"][axis], pos[axis]) for axis in (0, 2)))
        ground_ok = not require_oob or (flags & GROUND_HIT and distance <= oob_tolerance
                                        and frame["speed"] >= oob_min_speed)
        roll_ok = not roll_on_clip or (frame["state"] == 30
                                       and roll_facing_ranges.distance(frame["facing"]) == 0
                                       and frame["speed"] >= oob_min_speed)
        exact = bool(crossed and clean and retained and ray <= 35.0 and reach == 0
                     and aim == 0 and ground_ok and roll_ok)
        result = StorageResult(
            exact, phase, anchor + index + 1, -1, anchor + 1, tuple(controls),
            (old[0], old[2]), (pos[0], pos[2]), frame["state"], frame["facing"],
            frame["travel"], frame["speed"], ray, reach, aim,
            collision_error=math.hypot(frame["raw"][0] - pos[0], frame["raw"][2] - pos[2]),
            retention_error=0. if retained else face,
            target_distance=distance + face * 2., landing_distance=distance,
            landing_speed=frame["speed"], grounded=bool(flags & GROUND_HIT))
        if best is None or result.score < best.score:
            best = result
    return best


class StorageWalkFamily(NativeFamily):
    recipe_axis = roll_axis = False
    mode = "storage walk"

    def __init__(self, trace, worker, cancelled, facing_ranges, require_oob,
                 oob_tolerance, oob_min_speed, roll_on_clip, roll_facing_ranges):
        if not storage_active(trace):
            raise RuntimeError("the recorded route does not retain disabled wall correction")
        self.trace, self.worker, self.cancelled = trace, worker, cancelled
        self.seeds = trace["native"]["seeds"]
        self.route = align_movie_polls(_route(trace), trace["trace"], self.seeds,
                                       decode_row, owned_spans=True)
        self.base_rows = [dict(row) for row in self.route.rows]
        self.input_delay = infer_input_delay(self.base_rows, self.seeds)
        self.seam = SeamGeo(trace["geo"], self.seeds[0]["camera"])
        self.facing_ranges = facing_ranges
        self.require_oob, self.oob_tolerance = require_oob, oob_tolerance
        self.oob_min_speed = oob_min_speed
        self.roll_on_clip, self.roll_facing_ranges = roll_on_clip, roll_facing_ranges
        self.dispatch_row = len(self.base_rows) - 1
        self.button_row = -1
        self.rejections = {}
        failures = []
        for anchor in range(-1, len(self.base_rows) - 2):
            if cancelled():
                raise RuntimeError("search cancelled")
            seed = self.seeds[anchor + 1]
            if seed["proc"] not in (4, 6, 7, 24, 30):
                continue
            self.anchor_row, self.start_seed = anchor, seed
            self.camera = seed["camera"]
            self.variable_start = anchor + 1
            pads = self._effective_rows(self.base_rows, len(self.base_rows))
            replay = worker.replay(seed, [pads], self.camera)[0]
            try:
                if replay.get("error"):
                    raise RuntimeError(replay["error"])
                expected = []
                for row in range(anchor + 1, len(self.base_rows)):
                    captured = dict(trace["trace"][row]["after"])
                    camera = self.seeds[row + 1]["camera_state"]["fields"]
                    captured.update(camera_eye=camera["mEye"], camera_center=camera["mCenter"])
                    expected.append(captured)
                validate_replay(replay["frames"], expected)
                self.baseline_frames = replay["frames"]
                break
            except RuntimeError as exc:
                failures.append(str(exc))
        else:
            raise RuntimeError("chest-storage route has no bit-exact native replay anchor: "
                               + (failures[-1] if failures else "unported starting action"))
        first = first_editable_row(self.anchor_row, self.input_delay)
        self.control_rows = tuple(range(max(first, len(self.base_rows) - 32),
                                        len(self.base_rows)))
        if not self.control_rows:
            raise RuntimeError("the route has no editable movement before the seam")

    def rows_from_controls(self, controls, synthesize_buttons=False, **_):
        if len(controls) != len(self.control_rows) * 4:
            raise ValueError("invalid storage-walk controls")
        rows = [dict(row) for row in self.base_rows]
        for offset, index in enumerate(self.control_rows):
            for axis, key in enumerate(AXES):
                rows[index][key] = int(controls[4 * offset + axis])
        return rows

    def _result(self, controls, replay, phase):
        if replay.get("error") or not replay.get("frames"):
            reason = replay.get("error", "native replay returned no frames")
            self.rejections[reason] = self.rejections.get(reason, 0) + 1
            return crossing_result([], self.seam, controls, self.anchor_row,
                                   self.facing_ranges, self.require_oob, self.oob_tolerance,
                                   self.oob_min_speed, self.roll_on_clip,
                                   self.roll_facing_ranges, phase)
        return crossing_result(replay["frames"], self.seam, controls, self.anchor_row,
                               self.facing_ranges, self.require_oob, self.oob_tolerance,
                               self.oob_min_speed, self.roll_on_clip,
                               self.roll_facing_ranges, phase)

    def guided_controls(self):
        start = self.start_seed["pos"]
        sx, sz = self.seam.S
        a, b = self.seam.wA.pla, self.seam.wB.pla
        ix, iz = -a.nx - b.nx, -a.nz - b.nz
        scale = math.hypot(ix, iz) or 1.
        target_x, target_z = sx + ix * 45. / scale, sz + iz * 45. / scale
        bearing = round(math.atan2(target_x - start[0], target_z - start[2]) * 32768 / math.pi)
        original = self.controls_from_rows()
        for angle_offset in range(-4096, 4097, 512):
            for magnitude in (1., 0.75):
                for delay in (0, 1, 2):
                    values = list(original)
                    for offset, index in enumerate(self.control_rows):
                        if offset < delay:
                            continue
                        camera = self.seeds[min(index + 1, len(self.seeds) - 1)]["camera"]
                        values[4 * offset:4 * offset + 2] = stick_for_bearing(
                            (bearing + angle_offset) & 0xFFFF, camera, magnitude)
                    yield tuple(values)

    def export(self, result, output):
        previous = self.worker.workers
        try:
            self.worker.workers = 1
            checked = self.evaluate(result.controls, phase=result.phase)
        finally:
            self.worker.workers = previous
        if not checked.exact or (checked.old, checked.new, checked.dispatch_row) != (
                result.old, result.new, result.dispatch_row):
            raise RuntimeError("storage walk did not reproduce on the single-worker export check")
        rows = self.rows_from_controls(result.controls)
        movie = install_route_movie(self.route, rows, output, short=False, extend=True,
                                    replace_from=self.control_rows[0])
        Path(output).with_suffix(".inputs.json").write_text(json.dumps(dict(
            controller=self.route.controller, start_vi=self.route.start_vi,
            poll_spans=self.route.poll_spans, rows=rows), indent=2), encoding="ascii")
        return movie


def search_storage_trace(trace, output_dir, *, executable, iso, workers=0,
                         evaluation_cap=30000, random_seed=586023132, log=print,
                         cancelled=lambda: False, facing_ranges="0-65535",
                         require_oob=False, oob_tolerance=1., oob_min_speed=14.5,
                         roll_on_clip=False, roll_facing_ranges="37000-43000"):
    from harness.collision.object_route import coupled_trials

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    assets = extract_assets(iso, output.parent / "assets")
    worker = NativeWorker(executable, assets, trace["native"]["room"], workers, cancelled)
    try:
        family = StorageWalkFamily(trace, worker, cancelled, FacingRanges.parse(facing_ranges),
                                   require_oob, oob_tolerance, oob_min_speed, roll_on_clip,
                                   FacingRanges.parse(roll_facing_ranges))
        log("Verified unchanged storage route from row %d; searching direct walk crossings on %d worker(s)."
            % (family.variable_start, worker.workers))
        cap = max(1, int(evaluation_cap))
        rng = random.Random(random_seed)
        seen = set()
        best = None
        parents = []
        attempts = 0
        axes = tuple(range(len(family.control_rows) * 4))
        initial = [family.controls_from_rows(), *family.guided_controls()]
        for generation in range(max(6, math.ceil(cap / 768))):
            if cancelled():
                raise RuntimeError("search cancelled")
            if generation == 0:
                trials = initial
            else:
                radius = (32, 16, 8, 4, 2, 1)[(generation - 1) % 6]
                trials = []
                for parent in parents[:8]:
                    trials.extend(coupled_trials(parent.controls, axes, rng, 96, radius))
            trials = [item for item in dict.fromkeys(trials) if item not in seen][:cap - attempts]
            seen.update(trials)
            if not trials:
                break
            batch_results = list(family.evaluate_many(trials, "storage walk"))
            attempts += len(batch_results)
            for item in batch_results:
                if best is None or item.score < best.score:
                    best = item
                if item.exact:
                    best = item
                    break
            if best.exact:
                break
            parents = sorted([*parents, *batch_results], key=lambda item: item.score)[:16]
            log("Storage walk: %d/%d trials, nearest seam %.3f, ray %.3f" % (
                attempts, cap, best.target_distance, best.ray_error))
        if best is None:
            raise RuntimeError("no storage-walk route was evaluated")
        payload = dict(asdict(best), score=best.score, evaluations=attempts,
                       backend="tww_engine", object_type="storage_walk",
                       baseline_bit_exact=True, live_verified=False, movie=None,
                       input_file=None, native_rejections=family.rejections)
        if best.exact:
            movie = output / "storage_walk.dtm"
            payload["movie"] = str(family.export(best, movie))
            payload["input_file"] = str(movie.with_suffix(".inputs.json"))
            log("Native storage walk exported; playback has not yet been live-verified.")
        else:
            log("No verified storage crossing within %d evaluations; this is not proof of impossibility."
                % attempts)
        path = output / "storage_walk_result.json"
        payload["result_path"] = str(path)
        path.write_text(json.dumps(payload, indent=2), encoding="ascii")
        return payload
    finally:
        worker.close()
