"""Recorded moving B-drop refinement using native movement and collision.

The carried-object release pose is evaluated by the existing decomp FK/Co
model. Both it and the native approach must reproduce the captured release
before any changed inputs can be exported. No endpoint calibration is used.
"""
from dataclasses import asdict, dataclass, replace
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from harness.anim.parse_bck import parse_bck, to_jsonable
from harness.anim.parse_bmd import parse_bmd
from harness.rollstab.native_route import (
    NativeFamily, NativeWorker, NativeWorkerError, decode_row, extract_assets,
    f32_equal, infer_input_delay, validate_replay,
)
from harness.rollstab.native_route_timing import align_movie_polls
from harness.rollstab.recorded_route import install_route_movie, read_dtm_poll_rows
from harness.rollstab.route_constraints import BoundedBands, FacingRanges, search_facing_passes
from harness.rollstab.seamgeo import SeamGeo
from harness.rollstab.smart_route_search import RouteResult, _route
from tww_sim.core import drop_release as dr, fp
from tww_sim.core.cc_push import WEIGHT_LINK, co_push_link
from tww_sim.land.plan_land import stick_for_bearing

AXES = ("stickX", "stickY", "substickX", "substickY")
B = 0x200
A = 0x100
LIVE_SETUP_ERRORS = (
    "runtime DTM row", "cannot edit runtime DTM row", "cannot restore runtime DTM row",
    "Dolphin did not acknowledge the diagnostic input edit",
    "Dolphin did not attach the route movie",
    "the original DTM ends before the required live follow-through",
)

_pose_assets = None


def _init_pose_worker(anims, skeleton, kind):
    global _pose_assets
    _pose_assets = (anims, skeleton, kind)


def _compute_drop_pose(frames):
    held, release, consume = frames[-3:]
    if held.get("released") or not release.get("released") or any(
            frame.get("pose_morf", 0) > 0 for frame in (held, release)):
        return None
    anims, skeleton, kind = _pose_assets
    return dr.decomp_moving_b_drop_pose(
        held["pos"], release["pos"], held["facing"], lower_pose(held), lower_pose(release),
        held["upper_frame"], kind, lower_anims=anims, upper_anims=anims,
        skeleton=skeleton, held_lean=held["draw_lean"],
        collision_lean=release["draw_lean"], held_body_lean=held["body_lean"],
        collision_body_lean=release["body_lean"], collision_facing=release["facing"],
        held_root_matrix=held.get("draw_root_matrix"),
        collision_root_matrix=release.get("draw_root_matrix"))


def diverse_results(results, limit=32):
    """Keep accurate paths without collapsing all speed/heading/push families."""
    ranked = sorted((item for item in results if item.state in (6, 24)), key=lambda item: item.score)
    selected, seen, controls = [], set(), set()
    for item in sorted(ranked, key=lambda candidate: (candidate.collision_error, candidate.score)):
        if item.controls in controls:
            continue
        selected.append(item)
        controls.add(item.controls)
        if len(selected) >= max(1, limit // 8):
            break
    for item in ranked:
        if item.controls in controls:
            continue
        key = (item.facing // 128, item.travel // 128, round(item.speedf * 4),
               tuple(round(value * 4) for value in item.push),
               item.new[0] < item.old[0], item.new[1] < item.old[1])
        if key in seen or item.controls in controls:
            continue
        selected.append(item)
        seen.add(key)
        controls.add(item.controls)
        if len(selected) >= limit:
            return selected
    for item in ranked:
        if item.controls not in controls:
            selected.append(item)
            controls.add(item.controls)
        if len(selected) >= limit:
            break
    return selected


def coupled_trials(parent, axes, rng, count, radius):
    """Mutate short input blocks and both sticks, not only isolated bytes."""
    if not axes:
        return []
    allowed = set(axes)
    trials = set()
    for index in range(count):
        values = list(parent)
        first = rng.choice(axes)
        row = first // 4
        if index % 3 == 0:
            chosen = [axis for offset in range(rng.randint(1, 3))
                      for axis in (4 * (row + offset), 4 * (row + offset) + 1) if axis in allowed]
        elif index % 3 == 1:
            chosen = [axis for axis in range(row * 4, row * 4 + 4) if axis in allowed]
        else:
            chosen = rng.sample(list(axes), min(len(axes), rng.randint(2, 3)))
        delta = rng.choice((-radius, -1, 1, radius))
        for axis in chosen:
            step = delta if index % 3 == 0 else rng.randint(-radius, radius)
            values[axis] = max(0, min(255, values[axis] + step))
        trial = tuple(values)
        if trial != tuple(parent):
            trials.add(trial)
    return sorted(trials)


def release_row(trace):
    observations = trace.get("extra", ())
    for i in range(1, len(observations)):
        if observations[i - 1]["holding"] and not observations[i]["holding"]:
            return i - 1
    raise RuntimeError("the selected route does not contain a carried bomb/pot release")


def release_executes_after_link(kind, held, released):
    if kind == "pot_small" and released.get("prop_mode") is not None:
        # A pot executing after freeGrabItem has already left mode_carry (4).
        # If it executed before Link, mode_wait_init (2) happens next frame.
        if held.get("prop_mode") != 4 or released["prop_mode"] not in (2, 4):
            raise RuntimeError("the pot release is not an ordinary carry-to-wait transition")
        return released["prop_mode"] == 2
    # Older captures did not record the actor mode.
    return released["prop_pos"] != held["prop_pos"]


def rounded_frame(frame):
    result = dict(frame)
    for key in ("pos", "old", "raw", "camera_eye", "camera_center"):
        if key in result:
            result[key] = [fp.f32(value) for value in result[key]]
    for key in ("speed", "upper_frame"):
        if key in result:
            result[key] = fp.f32(result[key])
    result["under"] = [dict(clock, **{key: fp.f32(clock[key]) for key in
                        ("frame", "pose_frame", "ratio", "rate")})
                       for clock in frame.get("under", ())]
    return result


def lower_pose(frame):
    clocks = frame["under"]
    if not clocks[0]["active"] or not clocks[0].get("name"):
        raise RuntimeError("native worker did not identify the lower animation")
    first, second = clocks
    ratio = second["ratio"] if second["active"] else 0.0
    return dict(move0=Path(first["name"]).stem,
                move1=Path(second["name"]).stem if ratio else Path(first["name"]).stem,
                f0=first["pose_frame"], f1=second["pose_frame"] if ratio else first["pose_frame"],
                ratio=ratio)


def _float32_ulp_distance(a, b):
    if not math.isfinite(a) or not math.isfinite(b):
        return None

    def ordered_bits(value):
        bits = struct.unpack("<I", struct.pack("<f", fp.f32(value)))[0]
        return 0xFFFFFFFF - bits if bits & 0x80000000 else bits + 0x80000000

    return abs(ordered_bits(a) - ordered_bits(b))


def validate_drop_replay(frames, captured):
    if len(frames) != len(captured):
        raise RuntimeError("native replay length differs from the captured route")
    normalized = []
    maximum_speed_ulp = 0
    for index, (frame, expected) in enumerate(zip(frames, captured)):
        speed_ulp = _float32_ulp_distance(frame["speed"], expected["speed_f"])
        if speed_ulp is None or speed_ulp > 16:
            raise RuntimeError("native speed diverged at replay frame %d" % index)
        maximum_speed_ulp = max(maximum_speed_ulp, speed_ulp)
        normalized.append(dict(expected, speed_f=frame["speed"]))
    validate_replay(frames, normalized)
    return maximum_speed_ulp


def release_position_y_ulp_error(predicted, observed, *, rooted=False):
    if all(f32_equal(a, b) for a, b in zip(predicted, observed)):
        return 0
    if not rooted or any(not math.isfinite(value) for value in (*predicted, *observed)):
        return None
    if not f32_equal(predicted[0], observed[0]) or not f32_equal(predicted[2], observed[2]):
        return None

    distance = _float32_ulp_distance(predicted[1], observed[1])
    return distance if distance <= 1 else None


@dataclass(frozen=True)
class DropResult(RouteResult):
    push: tuple[float, ...] = ()
    held_prop: tuple[float, ...] = ()
    resolved: tuple[float, ...] = ()
    landing_distance: float = 0.0
    landing_speed: float = 0.0
    landing_error: float = 0.0
    speed_error: float = 0.0
    speed_preference: float = 0.0
    grounded: bool = False
    roll_facing: int = 0
    roll_error: int = 0

    @property
    def score(self):
        if self.exact:
            return -1000000.0 + self.speed_preference / 1000.
        return ((0 if self.state in (6, 24) else 100000.0)
                + self.reach_error * 10 + self.ray_error
                + self.collision_error * 0.05 + self.aim_error / 1024.0
                + self.roll_error / 1024.0 + self.landing_error
                + self.speed_error * 10 + self.speed_preference * 0.01)


def landing_errors(seam, position, grounded, landing_speed, tolerance, minimum_speed=14.5):
    """Ground-supported OoB seam landing with a configurable clip-speed floor."""
    distance = math.hypot(position[0] - seam.S[0], position[2] - seam.S[1])
    planes = (seam.wA.pla, seam.wB.pla)
    depth_error = sum(max(0., plane.func(position)) for plane in planes)
    if not all(plane.func(position) < 0 for plane in planes):
        depth_error = max(0.000001, depth_error)
    landing_error = max(0., distance - tolerance) + depth_error + (0. if grounded else 50.)
    speed_error = max(0., minimum_speed - landing_speed)
    return distance, landing_error, speed_error


def search_progress(item, require_oob=False):
    summary = "ray %.9f, reach %.6f, collision correction %.6f" % (
        item.ray_error, item.reach_error, item.collision_error)
    if hasattr(item, "speedf"):
        summary += ", pre-push speed %.3f" % item.speedf
    if require_oob:
        summary += (", landing %.6f (error %.6f), grounded=%s, clip speed %.6f"
                    % (item.landing_distance, item.landing_error, item.grounded, item.landing_speed))
    return summary


def drop_plan_choices(frontier, require_oob, recorded_dispatch):
    ranked = sorted(frontier, key=lambda pair: pair[0].score)
    choices = ranked[:4]
    choices += [pair for pair in ranked if pair[1].from_start and pair not in choices][:2]
    # A later release can move the old position onto the clear side of a
    # corner even when its unmodified ray is much worse than an earlier hit.
    nearby = [pair for pair in frontier if pair not in choices
              and abs(pair[1].dispatch_row - recorded_dispatch) <= 2]
    choices += sorted(nearby, key=lambda pair: (
        abs(pair[1].dispatch_row - recorded_dispatch), pair[1].from_start, pair[0].score))
    if require_oob:
        # A slightly delayed B press can move the landing by far more than
        # thousands of byte-level stick tweaks at the recorded release.
        later = [pair for pair in frontier if pair[1].from_start and pair not in choices
                 and 0 < pair[1].dispatch_row - recorded_dispatch <= 8]
        choices += sorted(later, key=lambda pair: pair[1].dispatch_row)
        earlier = [pair for pair in frontier if pair[1].from_start and pair not in choices
                   and 0 < recorded_dispatch - pair[1].dispatch_row <= 4]
        choices += sorted(earlier, key=lambda pair: -pair[1].dispatch_row)
    return choices


def drop_replan_choices(frontier, recorded_dispatch, limit=10):
    viable = [pair for pair in frontier if pair[0].state in (6, 24)]
    selected, seen = [], set()

    def add(pair):
        if id(pair[1]) not in seen and len(selected) < limit:
            selected.append(pair)
            seen.add(id(pair[1]))

    for key in (lambda pair: pair[0].score,
                lambda pair: pair[0].collision_error,
                lambda pair: -pair[0].speedf):
        if viable:
            add(min(viable, key=key))
    broad = [pair for pair in viable if pair[1].from_start]
    for offset in (0, 2, 4, 6, 8, 10, 12, -2, -4):
        if broad:
            add(min(broad, key=lambda pair: (
                abs(pair[1].dispatch_row - recorded_dispatch - offset), pair[0].score)))
    return selected


def drop_path_archive(choices, limit=32):
    paths, seen = [], set()
    for candidate, family in choices:
        variants = [candidate]
        archive = [item for item in family.archive if item.state in (6, 24)]
        if archive:
            variants.extend((min(archive, key=lambda item: item.score),
                             min(archive, key=lambda item: item.collision_error),
                             max(archive, key=lambda item: item.speedf)))
        for item in variants:
            if item.state not in (6, 24) or (family.dispatch_row, item.controls) in seen:
                continue
            seen.add((family.dispatch_row, item.controls))
            paths.append(dict(asdict(item), **family.control_metadata()))
            if len(paths) >= limit:
                return paths
    return paths


class ObjectWorker(NativeWorker):
    def __init__(self, *args, **kwargs):
        # NativeWorker initializes through this override, so retain capabilities.
        self.capabilities = {}
        super().__init__(*args, **kwargs)
        if (not self.capabilities.get("collision_queries")
                or int(self.capabilities.get("carried_movement", 0)) < 3):
            self.close()
            raise RuntimeError("rebuild the C++ worker: moving object support is missing")

    def request(self, payload, timeout=120):
        result = super().request(payload, timeout)
        if result.get("ready"):
            self.capabilities = result
        return result

    def movement(self, seed, routes):
        results = self.request(dict(seed=seed, routes=routes, workers=self.workers,
                                    diagnostics=True, drop_diagnostics=True))["results"]
        if len(results) != len(routes):
            raise NativeWorkerError("carried movement batch length differs")
        for result in results:
            result["frames"] = [rounded_frame(frame) for frame in result.get("frames", ())]
        return results

    def project(self, queries):
        results = self.request(dict(collisions=queries, workers=self.workers))["results"]
        if len(results) != len(queries):
            raise NativeWorkerError("collision batch length differs")
        for result in results:
            if "pos" in result:
                result["pos"] = [fp.f32(value) for value in result["pos"]]
        return results


class DropContext:
    """One baseline gate shared by all drop timing/approach families."""
    def __init__(self, trace, worker, assets, cancelled, log):
        self.trace, self.worker, self.assets = trace, worker, Path(assets)
        self.cancelled = cancelled
        self.log = log
        self.failed_live_movies = set()
        self.live_failure_counts = {}
        self.live_attempts = 0
        self.max_live_attempts = 20
        self.diagnostic_path = None
        self.dispatch = release_row(trace)
        self.kind = trace["object"]["object_type"]
        # Match the captured baseline's post-release action before applying
        # the user's requested action to newly synthesized routes.
        self.roll_on_clip = trace["trace"][self.dispatch + 1]["after"]["state"] == 30
        self.prop_executes_after_link = False
        if self.kind not in ("bomb", "pot_small"):
            raise RuntimeError("only ordinary small-pot and bomb B-drops are supported")
        self.route = align_movie_polls(_route(trace), trace["trace"], trace["native"]["seeds"],
                                      decode_row, owned_spans=True)
        self.seeds = trace["native"]["seeds"]
        self.input_delay = infer_input_delay(self.route.rows, self.seeds)
        edges = [i for i, row in enumerate(self.route.rows)
                 if row.get("buttons", 0) & B and (not i or not self.route.rows[i - 1].get("buttons", 0) & B)]
        self.button = max((i for i in edges if i <= self.dispatch - self.input_delay), default=-1)
        if self.button < 0 or self.button + self.input_delay != self.dispatch:
            raise RuntimeError("this release is buffered or is a throw; record an ordinary moving B-drop")
        # Parse the same disc assets the C++ movement worker uses, not stale CSVs.
        self.anims = {path.stem: to_jsonable(parse_bck(path.read_bytes()))
                      for path in self.assets.glob("*.bck")}
        self.skeleton = parse_bmd((self.assets / "cl.bdl").read_bytes())
        self.pose_pool = None
        self.seam = SeamGeo(trace["geo"], self.seeds[0]["camera"])
        log("Validating native movement and the carried object's release ordering...")
        failures = []
        for anchor in range(-1, self.dispatch - 1):
            if cancelled():
                raise RuntimeError("search cancelled")
            start = self.seeds[anchor + 1]
            if start["proc"] not in (6, 7, 24) or not trace["extra"][anchor + 1]["holding"]:
                continue
            self.anchor = anchor
            slant = trace["seeds"][anchor].get("movement_history", {}).get("m351c", 0) if anchor >= 0 else 0
            self.start = dict(start, carried_movement_only=True, carried_release_model=True, carried_slant=slant)
            family = DropFamily(self, self.dispatch, validate=False)
            replay = worker.movement(self.start, [family.movement_rows(family.controls_from_rows())])[0]
            try:
                if replay.get("error"):
                    raise RuntimeError(replay["error"])
                previous = trace["extra"][self.dispatch]
                extra = trace["extra"][self.dispatch + 1]
                self.prop_executes_after_link = release_executes_after_link(self.kind, previous, extra)
                expected = []
                for i in range(anchor + 1, self.dispatch + 1):
                    captured = dict(trace["trace"][i]["after"], under=self.seeds[i + 1]["under"])
                    camera = self.seeds[i + 1]["camera_state"]["fields"]
                    captured.update(camera_eye=camera["mEye"], camera_center=camera["mCenter"])
                    expected.append(captured)
                speed_ulp = validate_drop_replay(replay["frames"][:-1], expected)
                for offset, frame in enumerate(replay["frames"][:-1]):
                    captured_upper = self.seeds[anchor + offset + 2]["upper"][2]
                    if not f32_equal(frame["upper_frame"], captured_upper["frame"]):
                        raise RuntimeError("upper animation timing does not match the captured carry/drop")
                probe, query = family.release_probe(replay["frames"])
                rooted = replay["frames"][-3].get("draw_root_matrix") is not None
                held_ulp = release_position_y_ulp_error(
                    probe["pose"].held_prop_pos, previous["prop_pos"], rooted=rooted)
                if held_ulp is None:
                    raise RuntimeError("carried hand pose does not match the last live held pose")
                if not all(f32_equal(a, b) for a, b in zip(probe["push"], extra["cc_move"])):
                    raise RuntimeError("release push does not match the captured Co correction")
                prop_ulp = release_position_y_ulp_error(
                    probe["prop"], extra["prop_pos"], rooted=rooted)
                if prop_ulp is None:
                    raise RuntimeError("the object's first-release movement does not match its live execution order")
                projection = worker.project([query])[0]
                actual = trace["trace"][self.dispatch + 1]["after"]
                if not all(f32_equal(projection["pos"][axis], actual[key])
                           for axis, key in enumerate(("x", "y", "z"))):
                    raise RuntimeError("the post-release native collision does not reproduce the live route")
                self.baseline = family.result(family.controls_from_rows(), probe, projection, "route refinement")
                self.baseline_pose_y_ulp_error = max(held_ulp, prop_ulp)
                self.baseline_speed_ulp_error = speed_ulp
                log("Verified native positions, facing, camera, animation, release push and next "
                    "collision bit-for-bit; speed differs by at most %d and held/released height "
                    "by at most %d float32 step(s). Editable gameplay approach starts at row %d." %
                    (speed_ulp, self.baseline_pose_y_ulp_error, anchor + 1))
                break
            except (RuntimeError, KeyError) as exc:
                failures.append(str(exc))
        else:
            raise RuntimeError("no verified moving-drop approach: " + (failures[-1] if failures else "unported carry state"))
        identity = json.dumps([trace["native"]["seeds"][0], trace["geo"], trace["object"],
                               self.route.start_vi, self.route.rows, self.route.poll_spans],
                              sort_keys=True, separators=(",", ":")).encode("ascii")
        self.identity = hashlib.sha256(identity).hexdigest()
        self.warm = None
        self.path_archive = []
        self.accept_exact = None

    def parallel_poses(self, frames):
        if len(frames) < 64 or self.worker.workers < 2:
            return None
        if self.pose_pool is None:
            self.pose_pool = ProcessPoolExecutor(
                max_workers=self.worker.workers, initializer=_init_pose_worker,
                initargs=(self.anims, self.skeleton, self.kind))
        return self.pose_pool.map(_compute_drop_pose, frames, chunksize=16)

    def close(self):
        if self.pose_pool is not None:
            self.pose_pool.shutdown(wait=True, cancel_futures=True)
            self.pose_pool = None


class DropFamily(NativeFamily):
    mode = "moving drop"
    recipe_axis = roll_axis = False
    feasibility_label = "moving drop seam reach"

    @property
    def axes(self):
        # The consume frame's camera runs after the accepted push transition.
        return tuple(range(max(0, len(self.control_rows) * 4 - 2)))

    def __init__(self, context, dispatch, from_start=False, validate=True):
        self.context = context
        self.trace, self.route, self.worker = context.trace, context.route, context.worker
        self.seeds, self.input_delay = context.seeds, context.input_delay
        self.base_rows = [dict(row) for row in self.route.rows]
        self.dispatch_row, self.button_row = int(dispatch), int(dispatch) - self.input_delay
        self.anchor_row, self.start_seed = context.anchor, context.start
        self.camera, self.seam = self.start_seed["camera"], context.seam
        self.variable_start = self.anchor_row + 1
        self.cancelled = context.cancelled
        self.from_start = from_start
        if self.dispatch_row <= self.anchor_row + 1 or self.button_row < 0:
            raise ValueError("drop timing precedes the verified moving approach")
        if self.dispatch_row + 1 >= len(self.base_rows):
            raise ValueError("drop timing needs a recorded follow-through row")
        start = max(0, self.anchor_row + 1 - self.input_delay)
        if not from_start and validate:
            start = max(start, self.button_row - 5)
        self.control_rows = tuple(range(start, self.button_row + 2))
        self.rejections = {}
        self.archive = []
        self.replay_cache = OrderedDict()
        self.cache_hits = self.native_replays = 0
        self.export_check = False
        self.live_proofs = {}
        self._batch_prop_projection = True

    def rows_from_controls(self, controls, synthesize_buttons=False, **unused):
        if len(controls) != len(self.control_rows) * 4:
            raise ValueError("moving-drop controls require both sticks for each editable row")
        rows = [dict(row) for row in self.base_rows]
        for offset, index in enumerate(self.control_rows):
            for axis, key in enumerate(AXES):
                value = int(controls[offset * 4 + axis])
                if not 0 <= value <= 255:
                    raise ValueError("stick bytes must be in 0..255")
                rows[index][key] = value
        # Move the B edge rather than adding another edge to the recorded drop.
        for row in rows[max(0, self.anchor_row + 1 - self.input_delay):]:
            row["buttons"] = int(row.get("buttons", 0)) & ~B
        rows[self.button_row]["buttons"] |= B
        if getattr(self.context, "roll_on_clip", False):
            roll_row = self.button_row + 1
            for row in rows[max(0, self.anchor_row + 1 - self.input_delay):roll_row + 1]:
                row["buttons"] = int(row.get("buttons", 0)) & ~A
            rows[roll_row]["buttons"] |= A
            for index in (roll_row + 1, roll_row + 2):
                if index < len(rows):
                    rows[index]["stickX"] = rows[roll_row]["stickX"]
                    rows[index]["stickY"] = rows[roll_row]["stickY"]
        return rows

    def movement_rows(self, controls):
        rows = self.rows_from_controls(controls)
        # The native player must execute B/DROP too: it freezes this frame's
        # lower blend and switches the upper pose before the camera updates.
        # The external release model supplies the actor's pending Co push.
        return self._effective_rows(rows, self.dispatch_row + 2)

    def _release_pose(self, frames, pose=None):
        if len(frames) != self.dispatch_row + 1 - self.anchor_row:
            raise RuntimeError("incomplete native moving-drop replay")
        held, release, consume = frames[-3:]
        if held.get("released") or not release.get("released"):
            raise RuntimeError("the native B input did not release on the planned frame")
        if any(frame.get("pose_morf", 0) > 0 for frame in (held, release)):
            raise RuntimeError("release during an active old-pose morph is not modeled")
        consume_states = (30,) if getattr(self.context, "roll_on_clip", False) else (6, 24)
        if release["state"] not in (6, 24) or consume["state"] not in consume_states or release["speed"] <= 0:
            raise RuntimeError("B-drop or requested post-drop roll is not actionable")
        if pose is None:
            pose = dr.decomp_moving_b_drop_pose(
                held["pos"], release["pos"], held["facing"], lower_pose(held), lower_pose(release),
                held["upper_frame"], self.context.kind, lower_anims=self.context.anims,
                upper_anims=self.context.anims, skeleton=self.context.skeleton,
                held_lean=held["draw_lean"], collision_lean=release["draw_lean"],
                held_body_lean=held["body_lean"], collision_body_lean=release["body_lean"],
                collision_facing=release["facing"],
                held_root_matrix=held.get("draw_root_matrix"),
                collision_root_matrix=release.get("draw_root_matrix"))
        obj = dr.DROP_OBJECTS[self.context.kind]
        prop_query = None
        if self.context.prop_executes_after_link:
            # Tsubo mode_carry calls mode_wait_init, not mode_wait: CrrPos
            # runs on release, but posMoveF/gravity starts next execution.
            vertical_step = 0. if self.context.kind == "pot_small" else obj.gravity
            prop = list(pose.held_prop_pos)
            raw_prop = [prop[0], fp.fadds(prop[1], vertical_step), prop[2]]
            prop_query = dict(old=prop, raw=raw_prop, speed=[0., vertical_step, 0.],
                              object_type=self.context.kind)
        return dict(pose=pose, release=release, consume=consume, prop_query=prop_query)

    def _finish_release(self, prepared, projected_prop=None):
        pose, release, consume = prepared["pose"], prepared["release"], prepared["consume"]
        if prepared["prop_query"] is not None and projected_prop is None:
            raise RuntimeError("missing first-release prop collision")
        prop = list(projected_prop if projected_prop is not None else pose.held_prop_pos)
        obj = dr.DROP_OBJECTS[self.context.kind]
        center = list(prop)
        center[1] = fp.fadds(center[1], obj.co_y_offset)
        # Bombs expose a sphere to the Link cylinder query; use its cylinder envelope.
        if obj.co_y_offset:
            center[1] = fp.fsubs(center[1], obj.prop_spec.radius)
        push = co_push_link(pose.link_co_center, pose.link_co_radius, pose.link_co_height,
                            center, obj.prop_spec.radius, obj.prop_spec.height,
                            link_w=WEIGHT_LINK, other_w=obj.prop_spec.weight)
        raw = [fp.fadds(consume["raw"][axis], push[axis]) for axis in range(3)]
        query = dict(old=release["pos"], raw=raw,
                     speed=[fp.fsubs(consume["raw"][i], release["pos"][i]) for i in range(3)])
        return dict(pose=pose, prop=prop, push=push, release=release, consume=consume, raw=raw,
                    consume_speed=consume["speed"]), query

    def release_probe(self, frames):
        prepared = self._release_pose(frames)
        query = prepared["prop_query"]
        prop = self.worker.project([query])[0]["pos"] if query is not None else None
        return self._finish_release(prepared, prop)

    def result(self, controls, probe, projection, phase):
        frame, raw = probe["release"], probe["raw"]
        old3, resolved = frame["pos"], projection["pos"]
        old, new = (old3[0], old3[2]), (raw[0], raw[2])
        dx, dz = new[0] - old[0], new[1] - old[1]
        length = math.hypot(dx, dz)
        sx, sz = self.seam.S
        if length:
            along = ((sx - old[0]) * dx + (sz - old[1]) * dz) / length
            reach = max(0., -along) + max(0., along - length)
            ray = abs((sx - old[0]) * dz - (sz - old[1]) * dx) / length
        else:
            reach = ray = math.hypot(sx - old[0], sz - old[1])
        planes = (self.seam.wA.pla, self.seam.wB.pla)
        aim_error = getattr(self.context, "facing_ranges", FacingRanges()).distance(frame["facing"])
        roll_enabled = getattr(self.context, "roll_on_clip", False)
        roll_facing = probe["consume"]["facing"] if roll_enabled else 0
        roll_error = (getattr(self.context, "roll_facing_ranges", FacingRanges()).distance(roll_facing)
                      if roll_enabled else 0)
        grounded = bool(projection.get("flags", 0) & 0x20)
        landing_speed = probe.get("consume_speed", frame["speed"])
        distance = math.hypot(resolved[0] - sx, resolved[2] - sz)
        landing_error = speed_error = speed_preference = 0.
        if getattr(self.context, "require_oob", False):
            landing_speed = probe["consume_speed"]
            distance, landing_error, speed_error = landing_errors(
                self.seam, resolved, grounded, landing_speed,
                self.context.oob_tolerance, getattr(self.context, "oob_min_speed", 14.5))
            speed_preference = max(0., 17. - landing_speed)
        if getattr(self.context, "roll_on_clip", False):
            speed_error = max(speed_error, getattr(self.context, "oob_min_speed", 0.) - frame["speed"])
            speed_preference = max(speed_preference, max(0., 17. - frame["speed"]))
        clean = all(f32_equal(raw[axis], resolved[axis]) for axis in (0, 2))
        exact = bool(clean and not projection["wall_hit"] and not projection["line_hit"]
                     and aim_error == 0 and roll_error == 0 and landing_error == 0 and speed_error == 0
                     and reach == 0 and ray < 0.02 and any(probe["push"])
                     and all(plane.func(old3) > 0 for plane in planes)
                     and any(plane.func(resolved) < 0 for plane in planes))
        collision = math.hypot(raw[0] - resolved[0], raw[2] - resolved[2])
        return DropResult(exact, phase, self.dispatch_row + 1, self.button_row, self.variable_start,
                          tuple(controls), old, new, frame["state"], frame["facing"], frame["travel"],
                          frame["speed"], ray, reach, aim_error, collision_error=collision,
                          push=tuple(probe["push"]), held_prop=tuple(probe["pose"].held_prop_pos),
                          resolved=tuple(resolved), landing_distance=distance, landing_speed=landing_speed,
                          landing_error=landing_error, speed_error=speed_error,
                          speed_preference=speed_preference, grounded=grounded,
                          roll_facing=roll_facing, roll_error=roll_error)

    def evaluate_many(self, controls, phase="route refinement", synthesize_buttons=False):
        batch_size = getattr(self, "batch_size", 1024)
        for start in range(0, len(controls), batch_size):
            batch = controls[start:start + batch_size]
            unique, slots, lookup, keys = [], [], {}, []
            for values in batch:
                pads = self.movement_rows(values)
                key = json.dumps(pads, sort_keys=True, separators=(",", ":"))
                if key not in lookup:
                    lookup[key] = len(unique)
                    unique.append(pads)
                    keys.append(key)
                slots.append(lookup[key])
            entries = {index: self.replay_cache[key] for index, key in enumerate(keys)
                       if key in self.replay_cache}
            missing = [index for index in range(len(unique)) if index not in entries]
            replayed = self.worker.movement(self.start_seed, [unique[index] for index in missing]) if missing else []
            replays = dict(zip(missing, replayed))
            self.native_replays += len(missing)
            self.cache_hits += len(batch) - len(missing)
            probes, queries, valid = {}, [], []
            prepared, prop_queries, prop_indices = {}, [], []
            pose_indices = [index for index, replay in replays.items()
                            if not replay.get("error") and len(replay.get("frames", ())) >= 3
                            and replay["frames"][-2].get("state") in (6, 24)
                            and replay["frames"][-1].get("state") in (
                                (30,) if getattr(self.context, "roll_on_clip", False) else (6, 24))]
            parallel_poses = getattr(self.context, "parallel_poses", None)
            pose_values = parallel_poses([replays[index]["frames"][-3:] for index in pose_indices]) \
                if parallel_poses else None
            poses = dict(zip(pose_indices, pose_values)) if pose_values is not None else {}
            for index, replay in replays.items():
                try:
                    if replay.get("error"):
                        raise RuntimeError(replay["error"])
                    if getattr(self, "_batch_prop_projection", False):
                        prepared[index] = (self._release_pose(replay["frames"], poses[index])
                                           if index in poses else self._release_pose(replay["frames"]))
                        prop_query = prepared[index]["prop_query"]
                        if prop_query is not None:
                            prop_indices.append(index)
                            prop_queries.append(prop_query)
                    else:
                        probe, query = self.release_probe(replay["frames"])
                        probes[index] = probe
                        valid.append(index)
                        queries.append(query)
                except (RuntimeError, KeyError) as exc:
                    reason = str(exc)
                    self.rejections[reason] = self.rejections.get(reason, 0) + 1
            prop_positions = dict(zip(prop_indices, (item["pos"] for item in
                self.worker.project(prop_queries)))) if prop_queries else {}
            for index, setup in prepared.items():
                try:
                    probe, query = self._finish_release(setup, prop_positions.get(index))
                    probes[index] = probe
                    valid.append(index)
                    queries.append(query)
                except (RuntimeError, KeyError) as exc:
                    reason = str(exc)
                    self.rejections[reason] = self.rejections.get(reason, 0) + 1
            projected = dict(zip(valid, self.worker.project(queries))) if queries else {}
            for index, replay in replays.items():
                if index in projected:
                    item = self.result((), probes[index], projected[index], phase)
                else:
                    item = DropResult(False, phase, self.dispatch_row + 1, self.button_row,
                                      self.variable_start, (), (0, 0), (0, 0), -1, 0, 0, 0., 1e10, 1e10, 0)
                entries[index] = (item, replay.get("frames", ()))
            for index, entry in entries.items():
                self.replay_cache[keys[index]] = entry
                self.replay_cache.move_to_end(keys[index])
            while len(self.replay_cache) > 256:
                self.replay_cache.popitem(last=False)
            prefer_speed = getattr(self.context, "require_oob", False)
            selected = None
            if prefer_speed:
                # Keep output order for finite-difference probes, but test the
                # fastest exact landing first. No extra native trials are needed.
                choices = sorted((slot for slot in entries if entries[slot][0].exact),
                                 key=lambda slot: -entries[slot][0].landing_speed)
                for slot in choices:
                    values = batch[slots.index(slot)]
                    candidate = replace(entries[slot][0], controls=tuple(values), phase=phase)
                    checked = self._verify_exact(candidate)
                    if checked.exact:
                        selected = slot
                        break
                    entries[slot] = (replace(entries[slot][0], exact=False), entries[slot][1])
                    self.replay_cache[keys[slot]] = entries[slot]
            for values, slot in zip(batch, slots):
                cached, self.latest_frames = entries[slot]
                item = replace(cached, controls=tuple(values), phase=phase)
                if prefer_speed:
                    if item.exact and slot != selected:
                        item = replace(item, exact=False)
                else:
                    checked = self._verify_exact(item)
                    if item.exact and not checked.exact:
                        entries[slot] = (replace(cached, exact=False), self.latest_frames)
                        self.replay_cache[keys[slot]] = entries[slot]
                    item = checked
                if item.state in (6, 24):
                    self.archive.append(item)
                    if len(self.archive) > 256:
                        self.archive = diverse_results(self.archive, 64)
                    yield item
                else:
                    yield item

    def _verify_exact(self, item):
        verify = getattr(self.context, "accept_exact", None)
        if item.exact and verify and not self.export_check:
            rows = self.rows_from_controls(item.controls)
            movie_key = hashlib.sha256(json.dumps(
                rows[:self.dispatch_row + 2], sort_keys=True,
                separators=(",", ":")).encode("ascii")).digest()
            failed = getattr(self.context, "failed_live_movies", None)
            if failed is not None and movie_key in failed:
                return replace(item, exact=False)
            attempts = getattr(self.context, "live_attempts", None)
            if attempts is not None:
                if attempts >= self.context.max_live_attempts:
                    raise RuntimeError("stopped after %d distinct live tests without a retained clip; "
                                       "native exact candidates are not predicting the live outcome. "
                                       "Tested inputs are saved under %s" %
                                       (attempts, Path(self.context.diagnostic_path).parent / "tested_inputs"))
                self.context.live_attempts += 1
            try:
                self.live_proofs[item.controls] = verify(self, item)
            except RuntimeError as exc:
                if self.cancelled():
                    raise
                if any(message in str(exc) for message in LIVE_SETUP_ERRORS):
                    raise RuntimeError("live movie verification cannot continue: " + str(exc)) from exc
                reason = "live candidate rejected: " + str(exc)
                self.rejections[reason] = self.rejections.get(reason, 0) + 1
                if failed is not None:
                    failed.add(movie_key)
                counts = getattr(self.context, "live_failure_counts", None)
                if counts is not None:
                    counts[reason] = counts.get(reason, 0) + 1
                    count = counts[reason]
                    self.context.log("%s (live check %d/%d)." %
                                     (reason, getattr(self.context, "live_attempts", count),
                                      getattr(self.context, "max_live_attempts", count)))
                path = getattr(self.context, "diagnostic_path", None)
                if path is not None:
                    Path(path).write_text(json.dumps(dict(
                        reason=str(exc), dispatch_row=self.dispatch_row,
                        button_row=self.button_row, control_rows=self.control_rows,
                        controls=item.controls, old=item.old, new=item.new,
                        facing=item.facing, roll_facing=getattr(item, "roll_facing", 0),
                        ray_error=item.ray_error, collision_error=item.collision_error,
                        native_replays=self.native_replays), indent=2), encoding="ascii")
                return replace(item, exact=False)
        return item

    def refinement_possible(self):
        return True

    def family_has_dust(self, result):
        return (result.state in (6, 24) and result.reach_error == 0 and result.ray_error < 0.02
                and result.aim_error == 0 and result.roll_error == 0
                and result.landing_error == 0 and result.speed_error == 0)

    def local_starts(self, limit, seed):
        if getattr(self.context, "roll_on_clip", False):
            initial = self.controls_from_rows()
            roll_offset = self.control_rows.index(self.button_row + 1) * 4
            for angle in self.roll_bearings():
                if limit <= 0:
                    return
                values = list(initial)
                values[roll_offset:roll_offset + 2] = stick_for_bearing(angle, self.camera, 1.)
                yield tuple(values)
                limit -= 1
        paths = list(self.context.path_archive)
        if self.context.warm and self.context.warm.get("route_identity") == self.context.identity:
            paths.append(self.context.warm)
            paths.extend(self.context.warm.get("near_paths", ()))
        for warm in paths:
            if limit <= 0:
                return
            values = dict(zip(warm.get("control_rows", ()),
                              [warm["controls"][i:i + 4] for i in range(0, len(warm["controls"]), 4)]))
            rows = [dict(row) for row in self.base_rows]
            for index, axes in values.items():
                if 0 <= index < len(rows):
                    rows[index].update(zip(AXES, axes))
            yield self.controls_from_rows(rows)
            limit -= 1
        initial = self.controls_from_rows()
        for offset in range(len(self.control_rows)):
            for scale in (0.9, 0.75, 0.5):
                if limit <= 0:
                    return
                values = list(initial)
                for axis in (0, 1):
                    value = values[offset * 4 + axis]
                    values[offset * 4 + axis] = round(128 + (value - 128) * scale)
                yield tuple(values)
                limit -= 1

    def roll_bearings(self):
        if not getattr(self.context, "roll_on_clip", False):
            return ()
        angles = []
        for lo, hi in self.context.roll_facing_ranges.intervals:
            angles.extend((lo, (3 * lo + hi) // 4, (lo + hi) // 2,
                           (lo + 3 * hi) // 4, hi))
        return tuple(dict.fromkeys(angles))

    def route_starts(self, limit, seed):
        yield from self.local_starts(limit // 4, seed)
        rng = random.Random(seed)
        initial = self.controls_from_rows()
        bearing = round(math.atan2(self.seam.S[0] - self.start_seed["pos"][0],
                                   self.seam.S[1] - self.start_seed["pos"][2]) * 32768 / math.pi)
        roll_bearings = self.roll_bearings()
        # Piecewise world headings plus independent short camera pulses.
        for plan in range(limit - limit // 4):
            values = list(initial)
            turn = (0, -2048, 2048, -4096, 4096, -8192, 8192,
                    -12288, 12288)[plan % 9]
            magnitude = (1., 0.9, 0.75, 0.5, 0.35)[plan // 9 % 5]
            switch = rng.randrange(max(1, len(self.control_rows)))
            second_switch = rng.randrange(switch, max(switch + 1, len(self.control_rows)))
            pulse = rng.randrange(max(1, len(self.control_rows) - 1))
            pulse_length = rng.randint(1, 3)
            nudge = rng.choice((-24, -12, -6, -3, 3, 6, 12, 24))
            fine = rng.randrange(max(1, len(self.control_rows)))
            for offset, row in enumerate(self.control_rows):
                speed = magnitude if offset < switch else 1.
                if plan % 3 == 0 and fine <= offset < fine + 2:
                    speed = (0.35, 0.55, 0.75)[plan // 3 % 3]
                heading = (turn if offset < switch else
                           -turn // 2 if offset < second_switch and plan % 2 else 0)
                x, y = stick_for_bearing((bearing + heading) & 65535,
                                        self.camera, speed)
                values[offset * 4:offset * 4 + 2] = x, y
                if pulse <= offset < pulse + pulse_length:
                    axis = 2 + plan % 2
                    values[offset * 4 + axis] = max(0, min(255, values[offset * 4 + axis] + nudge))
            if roll_bearings:
                offset = self.control_rows.index(self.button_row + 1) * 4
                values[offset:offset + 2] = stick_for_bearing(
                    roll_bearings[plan % len(roll_bearings)], self.camera, 1.)
            yield tuple(values)

    def reaim_controls(self, controls):
        values = list(controls)
        for offset, row in enumerate(self.control_rows):
            if getattr(self.context, "roll_on_clip", False) and row == self.button_row + 1:
                continue
            previous = row + self.input_delay - self.variable_start - 1
            if previous < 0:
                frame = dict(pos=self.start_seed["pos"], camera=self.camera)
            elif previous < len(self.latest_frames):
                frame = self.latest_frames[previous]
            else:
                continue
            bearing = round(math.atan2(self.seam.S[0] - frame["pos"][0],
                                       self.seam.S[1] - frame["pos"][2]) * 32768 / math.pi)
            magnitude = decode_row(dict(stickX=values[offset * 4], stickY=values[offset * 4 + 1]))["distance"]
            x, y = stick_for_bearing(bearing & 65535, frame["camera"], magnitude)
            values[offset * 4:offset * 4 + 2] = x, y
        return tuple(values)

    def polish(self, results, cap, phase, synthesis, log):
        # Coupled sensitivities guide proposals, but never replace native replay.
        def residual(item):
            dx, dz = item.new[0] - item.old[0], item.new[1] - item.old[1]
            length = math.hypot(dx, dz)
            return (((self.seam.S[0] - item.old[0]) * dz -
                     (self.seam.S[1] - item.old[1]) * dx) / length) if length else 1e10
        candidates = [item for item in results if item.state in (6, 24) and item.reach_error == 0]
        if not candidates or cap <= 0:
            return None, 0
        pool = diverse_results(candidates, 24)
        best = min(pool, key=lambda item: item.score)
        require_oob = getattr(self.context, "require_oob", False)
        best_landing = min(item.landing_error for item in pool) if require_oob else 0.
        last_progress = 0
        seen, count = {item.controls for item in results}, 0
        # Probe the float32 band around the double-precision seam ray.
        spacing = max(struct.unpack("<f", struct.pack("<I", struct.unpack("<I", struct.pack("<f", abs(value)))[0] + 1))[0]
                      - abs(fp.f32(value)) for value in self.seam.S) / 4
        targets = [index * spacing for index in range(-8, 9)]
        rng = random.Random(getattr(self, "search_seed", 0))
        attempts = {}
        while count < cap:
            if self.cancelled():
                raise RuntimeError("search cancelled")
            landing_ready = not require_oob or best_landing == 0.
            # A stalled best ray must not prevent other headings and poses from
            # reaching different float32 wall-test branches.
            parent = min(pool, key=lambda item: (attempts.get(item.controls, 0), item.score))
            attempt = attempts.get(parent.controls, 0)
            attempts[parent.controls] = attempt + 1
            probes = []
            if landing_ready:
                for axis in self.axes:
                    for delta in (-1, 1, -4, 4):
                        values = list(parent.controls)
                        values[axis] = max(0, min(255, values[axis] + delta))
                        if tuple(values) not in seen:
                            probes.append((axis, values[axis] - parent.controls[axis], tuple(values)))
                            seen.add(tuple(values))
            probes = probes[:max(0, cap - count)]
            slopes = {}
            discovered = []
            for (axis, delta, values), item in zip(probes, self.evaluate_many(
                    [probe[2] for probe in probes], phase, synthesis)):
                count += 1
                if item.exact:
                    return item, count
                if item.score < best.score:
                    best = item
                    if landing_ready:
                        last_progress = count
                if item.state in (6, 24) and item.reach_error == 0 and delta:
                    discovered.append(item)
                    if require_oob and item.landing_error < best_landing - 0.1:
                        best_landing = item.landing_error
                        last_progress = count
                    slope = (residual(item) - residual(parent)) / delta
                    if math.isfinite(slope) and abs(slope) > 1e-9:
                        if axis not in slopes or abs(delta) < slopes[axis][0]:
                            slopes[axis] = (abs(delta), slope)
            guided = []
            if landing_ready:
                proposals = BoundedBands(len(targets), 64)
                error = residual(parent)
                sensitivities = sorted(((axis, value[1]) for axis, value in slopes.items()),
                                       key=lambda pair: abs(pair[1]))[:24]
                for axis, slope in sensitivities:
                    for other, other_slope in sensitivities:
                        if other <= axis:
                            continue
                        for delta in range(-6, 7):
                            for band, target in enumerate(targets):
                                change = round((target - error - slope * delta) / other_slope)
                                if abs(change) > 24:
                                    continue
                                for extra in (-1, 0, 1):
                                    first = max(0, min(255, parent.controls[axis] + delta))
                                    second = max(0, min(255, parent.controls[other] + change + extra))
                                    predicted = abs(error + slope * (first - parent.controls[axis])
                                                    + other_slope * (second - parent.controls[other]) - target)
                                    if not proposals.promising(band, predicted):
                                        continue
                                    values = list(parent.controls)
                                    values[axis], values[other] = first, second
                                    trial = tuple(values)
                                    if trial not in seen:
                                        proposals.add(band, predicted, trial)
                guided = proposals.interleaved(64 * len(targets))
            escape = coupled_trials(parent.controls, self.axes, rng, 256,
                                    ((1, 2, 4, 8) if landing_ready else (4, 8, 16, 32))[attempt % 4])
            # Interleave guided pairs with three-axis/block changes even if a
            # one-byte probe is inert under stick clamping or angle rounding.
            trials = []
            for index in range(max(len(guided), len(escape))):
                for source in (guided, escape):
                    if index < len(source) and source[index] not in seen:
                        seen.add(source[index])
                        trials.append(source[index])
                if len(trials) >= min(512, cap - count):
                    break
            trials = trials[:max(0, cap - count)]
            seen.update(trials)
            for item in self.evaluate_many(trials, phase, synthesis):
                count += 1
                if item.exact:
                    return item, count
                if item.score < best.score:
                    best = item
                    if landing_ready:
                        last_progress = count
                if item.state in (6, 24) and item.reach_error == 0:
                    discovered.append(item)
                    if require_oob and item.landing_error < best_landing - 0.1:
                        best_landing = item.landing_error
                        last_progress = count
            pool = diverse_results([*pool, best, *discovered], 24)
            log("%s: drop camera/stick polish %d/%d, %s" % (
                phase, count, cap, search_progress(best, getattr(self.context, "require_oob", False))))
            if not probes and not trials:
                break
            near_ray = any(item.ray_error < 0.02 and item.reach_error == 0 for item in pool)
            stalled_limit = 4000 if not landing_ready else (12000 if near_ray else 2048)
            if count - last_progress >= stalled_limit:
                log("%s: release %d stalled; testing a different drop timing or approach" %
                    (phase, self.dispatch_row))
                break
        return best, count

    def control_metadata(self):
        return dict(control_schema="native-moving-drop-v1", control_rows=list(self.control_rows),
                    planned_release_row=self.dispatch_row, route_identity=self.context.identity,
                    roll_input_row=self.button_row + 1 if getattr(self.context, "roll_on_clip", False) else None,
                    export_poll_spans=list(self.route.poll_spans),
                    validated_approach=dict(start=self.variable_start, end=self.context.dispatch + 1))

    def export(self, result, output):
        previous = self.worker.workers
        try:
            self.worker.workers = 1
            self.export_check = True
            # Export is a fresh single-worker replay, never a memoized result.
            self.replay_cache.clear()
            checked = self.evaluate(result.controls, phase=result.phase)
        finally:
            self.worker.workers = previous
            self.export_check = False
        if not checked.exact or checked != result:
            raise RuntimeError("moving-drop clip did not reproduce on the single-worker export check")
        rows = self.rows_from_controls(result.controls)
        movie = install_route_movie(self.route, rows, output, short=False, extend=True,
                                    replace_from=max(0, self.anchor_row + 1 - self.input_delay))
        Path(output).with_suffix(".inputs.json").write_text(json.dumps(dict(
            controller=self.route.controller, start_vi=self.route.start_vi,
            poll_spans=self.route.poll_spans, rows=rows), indent=2), encoding="ascii")
        return movie


def search_drop_family(family, cap, seed, log):
    """Object-specific beam: retain different poses and mutate input blocks."""
    rng = random.Random(seed)
    family.search_seed = seed
    phase = "route synthesis" if family.from_start else "route refinement"
    pool = list(family.archive)
    initial = family.controls_from_rows()
    starts = (family.route_starts if family.from_start else family.local_starts)(
        min(192, cap // 5), seed)
    seen = {item.controls for item in pool}
    trials = list(dict.fromkeys([initial, *starts]))
    trials = [trial for trial in trials if trial not in seen][:cap]
    count = 0
    for item in family.evaluate_many(trials, phase):
        count += 1
        pool.append(item)
        if item.exact:
            return item, count
    seen.update(trials)
    best = min(pool, key=lambda item: item.score)
    radii = (32, 16, 8, 4, 2, 1) if not family.from_start else (64, 32, 16, 8, 4, 2, 1)
    movement_cap = max(count, cap // 2)
    for generation, radius in enumerate(radii):
        if family.cancelled():
            raise RuntimeError("search cancelled")
        budget = max(0, (movement_cap - count) // (len(radii) - generation))
        if not budget:
            continue
        parents = diverse_results(pool, 32) or [best]
        proposals = []
        for parent in parents:
            proposals.extend(coupled_trials(parent.controls, family.axes, rng,
                                            max(24, budget // len(parents) * 2), radius))
        proposals = sorted(set(proposals) - seen)
        if len(proposals) > budget:
            proposals = rng.sample(proposals, budget)
        for item in family.evaluate_many(proposals, phase):
            count += 1
            pool.append(item)
            if item.score < best.score:
                best = item
            if item.exact:
                return item, count
        seen.update(proposals)
        pool = diverse_results(pool, 96) or [best]
        log("%s: release %d, coupled radius %d, trials %d, %s"
            % (phase, family.dispatch_row, radius, count,
               search_progress(best, getattr(family.context, "require_oob", False))))
        if (generation >= 1 and not any(item.state in (6, 24) for item in pool)
                and count >= min(2000, max(128, cap // 5))):
            log("%s: release %d did not reach an actionable B-drop; testing the next timing"
                % (phase, family.dispatch_row))
            return best, count
    refined, used = family.polish(pool, cap - count, phase, family.from_start, log)
    if refined is not None and refined.score < best.score:
        best = refined
    return best, count + used


def search_object_trace(trace, output_dir, *, executable, iso, workers=0, evaluation_cap=30000,
                        random_seed=586023132, log=print, cancelled=lambda: False,
                        verify_candidate=None, facing_ranges="0-65535", widen_facing=True,
                        require_oob=False, oob_tolerance=1.0, oob_min_speed=14.5,
                        roll_on_clip=False, roll_facing_ranges="37000-43000"):
    oob_tolerance = float(oob_tolerance)
    if not math.isfinite(oob_tolerance) or not 0 < oob_tolerance <= 1:
        raise ValueError("OoB seam tolerance must be greater than 0 and at most 1 unit")
    oob_min_speed = float(oob_min_speed)
    if not math.isfinite(oob_min_speed) or not 0 <= oob_min_speed <= 17:
        raise ValueError("minimum clip speed must be between 0 and 17")
    return search_facing_passes(
        lambda allowed, index: _search_object_trace(
            trace, output_dir, executable=executable, iso=iso, workers=workers,
            evaluation_cap=evaluation_cap, random_seed=random_seed + index * 9973,
            log=log, cancelled=cancelled, verify_candidate=verify_candidate,
            facing_ranges=allowed, require_oob=require_oob, oob_tolerance=oob_tolerance,
            oob_min_speed=oob_min_speed, roll_on_clip=roll_on_clip,
            roll_facing_ranges=FacingRanges.parse(roll_facing_ranges)),
        facing_ranges, widen_facing, log, cancelled)


def _search_object_trace(trace, output_dir, *, executable, iso, workers=0, evaluation_cap=30000,
                         random_seed=586023132, log=print, cancelled=lambda: False,
                         verify_candidate=None, facing_ranges=FacingRanges(),
                         require_oob=False, oob_tolerance=1.0, oob_min_speed=14.5,
                         roll_on_clip=False, roll_facing_ranges=FacingRanges()):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    assets = extract_assets(iso, output.parent / "assets")
    worker = ObjectWorker(executable, assets, trace["native"]["room"], workers, cancelled)
    try:
        context = DropContext(trace, worker, assets, cancelled, log)
        context.accept_exact = verify_candidate
        context.diagnostic_path = output / "last_live_rejection.json"
        context.runtime_polls = (len(read_dtm_poll_rows(context.route.movie, context.route.controller))
                                 if verify_candidate else None)
        context.facing_ranges = facing_ranges
        context.roll_on_clip = roll_on_clip
        context.roll_facing_ranges = roll_facing_ranges
        context.require_oob, context.oob_tolerance = require_oob, oob_tolerance
        context.oob_min_speed = oob_min_speed
        if require_oob:
            log("Requiring a grounded OoB seam landing within %.6f units, clip speed at least %.6f; "
                "preferring faster landings without constraining release speed."
                % (oob_tolerance, oob_min_speed))
        if roll_on_clip:
            log("Pressing A on the input row after B; requiring a front roll on the push frame "
                "with facing in %s and pre-push speed at least %.6f."
                % (roll_facing_ranges.intervals, oob_min_speed))
        prior = output / "moving_object_result.json"
        if prior.is_file():
            try:
                context.warm = json.loads(prior.read_text(encoding="ascii"))
            except (ValueError, OSError):
                pass
        cap, used = max(1, int(evaluation_cap)), 0
        best = family_best = None
        frontier = []
        plan_cap = max(1, cap // 3)
        base = context.dispatch
        local = [value for value in (base, base - 1, base + 1, base - 2, base + 2)
                 if context.anchor + 1 < value < len(context.route.rows) - 1]
        broad = list(dict.fromkeys(local + [value for value in range(
            context.anchor + 2, len(context.route.rows) - 1)]))
        if context.runtime_polls is not None:
            def verifiable(dispatch):
                end = min(len(context.route.rows), dispatch + 4)
                return context.route.poll_spans[end - 1][1] <= context.runtime_polls

            skipped = sum(not verifiable(value) for value in broad)
            local = [value for value in local if verifiable(value)]
            broad = [value for value in broad if verifiable(value)]
            if skipped:
                log("Skipping %d release timing(s) whose live follow-through exceeds the "
                    "original DTM's %d controller polls." % (skipped, context.runtime_polls))
            if not broad:
                raise RuntimeError("the original DTM ends before any release timing can be live-verified")
        plans = [(value, False) for value in local] + [(value, True) for value in broad]
        log("Searching %s movement, camera paths and B timing on %d native workers." % (context.kind, worker.workers))
        screen_cap = max(1, min(128, cap // max(1, len(plans) * 8)))
        for index, (dispatch, synthesize) in enumerate(plans):
            if used >= cap or best and best.exact:
                break
            family = DropFamily(context, dispatch, from_start=synthesize)
            family.search_seed = random_seed + index * 257
            initial = family.controls_from_rows()
            factory = family.route_starts if synthesize else family.local_starts
            trials = list(dict.fromkeys([initial, *factory(screen_cap - 1, family.search_seed)]))[:cap - used]
            candidate = None
            for item in family.evaluate_many(trials, "route synthesis" if synthesize else "route refinement"):
                used += 1
                if candidate is None or item.score < candidate.score:
                    candidate = item
                if item.exact:
                    break
            frontier.append((candidate, family))
            if best is None or candidate.score < best.score:
                best, family_best = candidate, family
            log("Drop timing screen: release %d, %s, %s"
                % (dispatch, "new approach" if synthesize else "recorded approach",
                   search_progress(candidate, require_oob)))
        # Screening is a ranking heuristic, not a declaration that any timing
        # is impossible. Include broad paths even if the local ray starts best.
        choices = drop_plan_choices(frontier, require_oob, base)
        if require_oob:
            log("Screened %d nearby B timings; testing up to %d movement variants per timing before fine polish."
                % (len(choices), min(6000, plan_cap)))
        for index, (candidate, family) in enumerate(choices):
            if best.exact or used >= plan_cap:
                break
            context.path_archive = drop_path_archive(
                sorted(frontier, key=lambda pair: pair[0].score)[:12])
            budget = max(1, (plan_cap - used) // (len(choices) - index))
            budget = min(budget, 6000 if require_oob else 20000)
            refined, count = search_drop_family(family, budget, family.search_seed, log)
            used += count
            frontier = [(refined, owner) if owner is family else (item, owner) for item, owner in frontier]
            if refined.score < best.score:
                best, family_best = refined, family
        if not best.exact and used < cap:
            log("No exact drop in the local approach. Replanning walking headings, speed schedules, "
                "camera pulses and B timing before more float-level polishing.")
            replan_cap = min(cap, used + max(12000, cap // 3))
            round_index = 0
            while not best.exact and used < replan_cap:
                choices = drop_replan_choices(frontier, base)
                if not choices:
                    break
                context.path_archive = drop_path_archive(choices)
                for candidate, family in choices:
                    if best.exact or used >= replan_cap:
                        break
                    budget = min(6000, replan_cap - used)
                    family.search_seed = random_seed + (round_index + 1) * 104729 + family.dispatch_row * 257
                    refined, count = search_drop_family(family, budget, family.search_seed, log)
                    used += count
                    frontier = [(refined, owner) if owner is family else (item, owner)
                                for item, owner in frontier]
                    if refined.score < best.score:
                        best, family_best = refined, family
                round_index += 1
                log("Replan round %d: %d evaluations, best %s" % (
                    round_index, used, search_progress(best, require_oob)))
        choices = sorted(frontier, key=lambda pair: pair[0].score)[:4]
        for index, (candidate, family) in enumerate(choices):
            if best.exact or used >= cap:
                break
            budget = min(max(1, (cap - used) // (len(choices) - index)),
                         20000 if require_oob else 50000)
            refined, count = family.polish([candidate, *family.archive], budget, candidate.phase,
                                            candidate.phase == "route synthesis", log)
            used += count
            if refined is not None and refined.score < best.score:
                best, family_best = refined, family
        payload = dict(asdict(best), **family_best.control_metadata(), score=best.score, evaluations=used,
                       backend="tww_engine + decomp drop release", object_type=context.kind,
                       baseline_bit_exact=(context.baseline_pose_y_ulp_error == 0
                                           and context.baseline_speed_ulp_error == 0),
                       baseline_pose_y_ulp_error=context.baseline_pose_y_ulp_error,
                       baseline_speed_ulp_error=context.baseline_speed_ulp_error,
                       live_verified=False, retention_verified=False,
                       proof_scope="first push transition", model_version=4,
                       movie=None, input_file=None, dispatch_candidates=local,
                       synthesis_dispatch_candidates=broad, require_oob=require_oob,
                       oob_tolerance=oob_tolerance, oob_min_speed=oob_min_speed,
                       roll_on_clip=roll_on_clip, roll_facing_ranges=roll_facing_ranges.intervals,
                       facing_frame="before push displacement")
        if best.exact and best.controls in family_best.live_proofs:
            payload.update(family_best.live_proofs[best.controls])
        payload["search_version"] = 2
        payload["export_timing_version"] = 3
        payload["native_replays"] = sum(owner.native_replays for _, owner in frontier)
        payload["normalized_route_cache_hits"] = sum(owner.cache_hits for _, owner in frontier)
        payload["near_paths"] = [dict(asdict(item), control_rows=list(owner.control_rows))
                                 for item, owner in sorted(frontier, key=lambda pair: pair[0].score)[:12]
                                 if item.state in (6, 24)]
        reasons = {}
        for _, family in frontier:
            for reason, count in family.rejections.items():
                reasons[reason] = reasons.get(reason, 0) + count
        payload["native_rejections"] = reasons
        if best.exact:
            movie = output / "moving_object_clip.dtm"
            payload["movie"] = str(family_best.export(best, movie))
            payload["input_file"] = str(movie.with_suffix(".inputs.json"))
            log("Live-verified moving drop exported." if payload["live_verified"] else
                "Exact first push transition exported. Follow-through has not been live-verified.")
        else:
            log("No exact clip after %d evaluations (cap %d), not a proof that the seam is impossible. "
                "Best %s; saved this route for the next search seed."
                % (used, cap, search_progress(best, require_oob)))
        payload["result_path"] = str(prior)
        prior.write_text(json.dumps(payload, indent=2), encoding="ascii")
        return payload
    finally:
        if "context" in locals():
            context.close()
        worker.close()
