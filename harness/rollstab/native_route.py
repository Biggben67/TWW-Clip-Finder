"""Native replay/refinement backend; an unchanged live replay is a hard gate."""
from functools import lru_cache
from dataclasses import replace
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import queue
import struct
import subprocess
import threading

from harness.collision.dzb_iso import gcm_read_file, read_rarc_bytes, yaz0_decompress
from harness.rollstab.smart_route_search import (
    RouteFamily, RouteResult, CUT_STATES, NEAR_SEAM_SEARCH_DISTANCE,
    _beam_search, _route, search_trace, find_dispatch_rows,
)
from harness.rollstab.seamgeo import SeamGeo
from harness.rollstab.native_route_plans import (
    actor_push_prefix_end, ground_start, pre_roll_starts, recorded_roll_rows, recorded_starts, replan_dispatches,
    roll_button_row, route_recipe, route_starts,
)
from harness.rollstab.native_route_timing import align_movie_polls, pad_matches
from harness.rollstab.recorded_route import install_route_movie
from harness.rollstab.route_constraints import BoundedBands, FacingRanges, search_facing_passes
from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.core.mathlib import main_stick_decode, clamp_stick, f32, _clamped_angle_s16

SWORD_EQUIP_ITEM = 0x103


class FacingRouteResult(RouteResult):
    @property
    def score(self):
        if self.exact:
            return -1000000.0
        action = 0.0 if self.state in CUT_STATES else 100000.0
        return (action + self.reach_error * 10.0 + self.ray_error
                + 0.05 * (self.collision_error + self.retention_error)
                + self.aim_error / 1024.0)


def extract_assets(iso, output):
    iso, output = Path(iso), Path(output)
    stat = iso.stat()
    identity = {"iso": str(iso.resolve()), "size": stat.st_size, "mtime": stat.st_mtime_ns, "format": 2}
    stamp = output / "source.json"
    if stamp.is_file() and json.loads(stamp.read_text()) == identity:
        return output
    output.mkdir(parents=True, exist_ok=True)
    for archive in ("Link.arc", "LkAnm.arc"):
        try:
            raw = gcm_read_file(iso, "res/Object/" + archive)
        except FileNotFoundError:
            raw = gcm_read_file(iso, "files/res/Object/" + archive)
        for name, data in read_rarc_bytes(raw).items():
            if name == "cl.bdl" or name.lower().endswith(".bck"):
                (output / Path(name).name).write_bytes(yaz0_decompress(data))
    stamp.write_text(json.dumps(identity), encoding="ascii")
    return output


@lru_cache(maxsize=65536)
def _stick(x, y):
    angle, distance = main_stick_decode(x, y)
    return ((angle + 0x8000) & 0xFFFF) if angle is not None else 0, distance


@lru_cache(maxsize=131072)
def normalized_stick(x, y, sub=False):
    cx, cy = clamp_stick(x - 128, y - 128, 59 if sub else 72, 31 if sub else 40, 15)
    divisor = 42.0 if sub else 54.0
    px, py = f32(cx / divisor), f32(cy / divisor)
    value = f32(math.sqrt(f32(f32(px * px) + f32(py * py))))
    if value > 1.0:
        px, py = f32(px / value), f32(py / value)
    angle = _clamped_angle_s16(cx, cy, divisor) if value else 0
    return px, py, min(value, 1.0), angle


def decode_row(row):
    mx, my, distance, angle = normalized_stick(int(row["stickX"]), int(row["stickY"]))
    cx, cy, cvalue, cangle = normalized_stick(int(row.get("substickX", 128)),
                                           int(row.get("substickY", 128)), True)
    buttons = int(row.get("buttons", 0))
    item = sum(native for dtm, native in ((0x100, 1), (0x200, 2), (0x400, 4),
                                         (0x800, 8), (0x10, 16), (0x40, 32), (0x20, 64))
               if buttons & dtm)
    # Digital L sets the item-button bit, but only the analog lock threshold
    # sets CPAD's lock-on flag. They are distinct in live Dolphin captures.
    target = int(row.get("triggerL", 0)) >= 0x80
    if target:
        item |= 32
    if int(row.get("triggerR", 0)) >= 0x80:
        item |= 64
    hold = sum(native for dtm, native in ((1, 0x8000), (2, 0x4000), (4, 0x2000), (8, 0x1000),
                (0x10, 0x800), (0x20, 0x400), (0x40, 0x200), (0x100, 0x100),
                (0x200, 0x80), (0x400, 0x40), (0x800, 0x20), (0x1000, 0x10)) if buttons & dtm)
    return {"angle": (angle + 0x8000) & 0xFFFF, "distance": distance,
            "item_button": item, "target": target, "mx": mx, "my": my,
            "cx": cx, "cy": cy, "cvalue": cvalue, "cangle": cangle,
            "tl": f32(max(0, min(150, int(row.get("triggerL", 0)) - 30)) / 150.0),
            "tr": f32(max(0, min(150, int(row.get("triggerR", 0)) - 30)) / 150.0), "hold": hold,
            "lock_l": int(target), "lock_r": int(bool(item & 64)),
            "trig_l": 0, "trig_r": 0}


def f32_equal(a, b):
    return struct.pack(">f", float(a)) == struct.pack(">f", float(b))


def validate_replay(frames, captured):
    if len(frames) != len(captured):
        raise RuntimeError("native replay length differs from the captured route")
    for index, (actual, expected) in enumerate(zip(frames, captured)):
        if int(actual["state"]) != int(expected["state"]):
            raise RuntimeError("native state diverged at replay frame %d (%s != %s)" %
                               (index, actual["state"], expected["state"]))
        expected_pos = (expected["x"], expected["y"], expected["z"])
        if not all(f32_equal(a, b) for a, b in zip(actual["pos"], expected_pos)):
            distance = math.dist(actual["pos"], expected_pos)
            raise RuntimeError("native position diverged at replay frame %d by %.9f units" % (index, distance))
        if int(actual["facing"]) != int(expected["facing"]) or not f32_equal(actual["speed"], expected["speed_f"]):
            raise RuntimeError("native facing/speed diverged at replay frame %d" % index)
        if "camera" in expected and int(actual.get("camera", -1)) != int(expected["camera"]):
            raise RuntimeError("native camera diverged at replay frame %d (%s != %s)" %
                               (index, actual.get("camera"), expected["camera"]))
        for field in ("camera_eye", "camera_center"):
            if field in expected and (field not in actual or len(actual[field]) != 3 or
                                     not all(f32_equal(a, b) for a, b in zip(actual[field], expected[field]))):
                raise RuntimeError("native %s diverged at replay frame %d" % (field, index))
        if "under" in expected:
            if len(actual.get("under", ())) != len(expected["under"]):
                raise RuntimeError("native animation clocks are missing at replay frame %d" % index)
            for slot, (live, saved) in enumerate(zip(actual["under"], expected["under"])):
                keys = ("frame", "rate", "ratio", "pose_frame")
                if (live["index"] != saved["index"] or live["active"] != saved["active"]
                        or not all(f32_equal(live[key], saved[key]) for key in keys)):
                    raise RuntimeError("native animation clock %d diverged at replay frame %d" % (slot, index))


def infer_input_delay(rows, seeds):
    """Verify raw movie-to-CPAD timing; never fit movement coordinates to a bad phase."""
    candidates = [delay for delay in (2, 1, 0, 3, 4)
                  if len(rows) > delay and all(pad_matches(decode_row(rows[i - delay]), seeds[i]["pad"])
                      for i in range(delay, min(len(seeds), len(rows) + delay)))]
    if not candidates:
        raise RuntimeError("recorded controller rows do not match the captured P1 pad timing; "
                           "no search or movie export is safe")
    return candidates[0]


def first_editable_row(anchor_row, input_delay):
    # The first post-anchor update has already latched its controller input.
    # Its source movie row is history even if CPAD later displays the new poll.
    return max(0, anchor_row + 3 - input_delay)


def native_dispatch_rows(trace):
    """Keep recorded slash timing, then propose near-seam timing from the approach."""
    count = len(trace["route"]["rows"])
    try:
        proposed = list(find_dispatch_rows(trace))
    except RuntimeError:
        proposed = []
    sx, _, sz = trace["geo"]["S"]
    approaches = [frame for frame in trace.get("trace", ())
                  if frame["after"]["state"] in (6, 7, 24, 30)
                  and 4 <= frame["row"] + 1 < count - 3]
    approaches.sort(key=lambda frame: math.hypot(frame["after"]["x"] - sx,
                                                frame["after"]["z"] - sz))
    for frame in approaches[:3]:
        dispatch = frame["row"] + 1
        if dispatch not in proposed:
            proposed.append(dispatch)
    # Include the last active roll frames, not only the recorded post-roll slash.
    seeds = trace.get("native", {}).get("seeds", ())
    roll_ends = [i for i, seed in enumerate(seeds[:-1])
                 if seed["proc"] == 30 and seeds[i + 1]["proc"] != 30]
    for end in roll_ends:
        for dispatch in range(max(4, end - 3), min(count - 3, end + 1)):
            if dispatch not in proposed:
                proposed.append(dispatch)
    if not proposed:
        raise RuntimeError("the recorded route has no supported slash approach with follow-through frames")
    first_editable = actor_push_prefix_end(trace)
    if first_editable:
        proposed = [dispatch for dispatch in proposed if dispatch > first_editable]
        if not proposed:
            proposed = [first_editable + 1]
    return tuple(proposed)


def prioritize_dispatches(trace, dispatches):
    """Try early recorded near-seam windows first, without dropping alternatives."""
    sx, _, sz = trace["geo"]["S"]
    positions = {int(frame["row"]) + 1: frame["after"] for frame in trace.get("trace", ())}
    near, later = [], []
    for dispatch in dict.fromkeys(dispatches):
        pose = positions.get(dispatch)
        if (pose is not None and math.hypot(pose["x"] - sx, pose["z"] - sz) <= 80):
            near.append(dispatch)
        else:
            later.append(dispatch)
    return tuple(sorted(near) + later)


def approach_validation_end(trace, dispatch, synthesis):
    """Validate the approach, not a failed recorded slash's downstream rebound."""
    count = len(trace["route"]["rows"])
    entries = [int(frame["row"]) for frame in trace.get("trace", ())
               if int(frame["after"]["state"]) in CUT_STATES
               and int(frame["before"]["state"]) not in CUT_STATES]
    # A new route replaces the first slash onward. Local refinement also checks
    # its entry displacement; neither search needs to reproduce the failed end.
    end = min(entries) + int(not synthesis) if entries else count
    return min(count, int(dispatch) + 5, end)


def approach_anchor_rows(trace, dispatch, validation_end, from_start):
    """Include the last pre-dispatch frame as a possible exact replay seed."""
    limit = dispatch - 1
    start = -1 if from_start else max(-1, min(limit, validation_end - 1) - 12)
    start = max(start, actor_push_prefix_end(trace) - 1)
    stop = min(limit + 1, validation_end - 1, len(trace["native"]["seeds"]) - 1)
    return range(start, stop)


def recorded_slash_buffer(trace):
    """Measure the recorded B edge's equip/buffer delay from CPAD, not positions."""
    seeds = trace["native"]["seeds"]
    entries = [int(frame["row"]) for frame in trace.get("trace", ())
               if int(frame["after"]["state"]) in CUT_STATES
               and int(frame["before"]["state"]) not in CUT_STATES]
    if not entries:
        return 0
    entry = min(entries)
    edges = [i for i in range(1, min(entry + 1, len(seeds)))
             if seeds[i]["pad"]["item_button"] & 2
             and not seeds[i - 1]["pad"]["item_button"] & 2]
    return min(8, entry - edges[-1]) if edges else 0


class NativeWorkerError(RuntimeError):
    """The native process cannot continue safely; do not skip it as a bad route."""

    fatal_search = True


class NativeWorker:
    def __init__(self, executable, assets, room, workers=0, cancelled=lambda: False):
        self.workers = max(1, min(16, workers or os.cpu_count() or 1))
        self.cancelled = cancelled
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        def receive():
            try:
                for line in self.process.stdout:
                    self.responses.put(line)
            finally:
                self.responses.put(None)
        self.reader = threading.Thread(target=receive, daemon=True)
        self.reader.start()
        try:
            ready = self.request({"assets": str(assets), "room": room})
            if ready.get("protocol") != 1 or not ready.get("ready"):
                raise RuntimeError("unsupported native worker protocol")
        except Exception:
            self.close()
            raise

    def request(self, payload, timeout=120):
        import time
        if self.cancelled():
            self.close()
            raise RuntimeError("search cancelled")
        if self.process.poll() is not None or self.process.stdin.closed:
            raise NativeWorkerError("native worker is no longer running; restart the search")
        try:
            self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            self.close()
            raise NativeWorkerError("native worker communication failed: %s" % exc) from exc
        deadline = time.monotonic() + timeout
        while True:
            if self.cancelled():
                self.close()
                raise RuntimeError("search cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise NativeWorkerError("native batch timed out; search stopped without exporting unverified inputs")
            try:
                line = self.responses.get(timeout=min(0.1, remaining))
                break
            except queue.Empty:
                continue
        if line is None:
            raise NativeWorkerError("native worker exited (code %s)" % self.process.poll())
        try:
            response = json.loads(line)
        except (ValueError, TypeError) as exc:
            self.close()
            raise NativeWorkerError("invalid response from native worker") from exc
        if not isinstance(response, dict):
            self.close()
            raise NativeWorkerError("native response is not an object")
        if response.get("error"):
            raise RuntimeError(response["error"])
        return response

    def replay(self, seed, routes, camera, *, diagnostics=False):
        response = self.request({"seed": seed, "routes": routes, "camera": camera,
                                 "workers": self.workers, "diagnostics": diagnostics})
        results = response.get("results")
        if not isinstance(results, list) or len(results) != len(routes):
            self.close()
            raise NativeWorkerError("native batch response length differs from the submitted routes")
        return results

    def close(self):
        if self.process.poll() is None:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=1)


class NativeFamily(RouteFamily):
    feasibility_label = "native seam reach screen"
    export_label = "Native simulation candidate"

    def search_proximity(self, results):
        """Distance of the uncorrected slash segment from the seam."""
        return min((math.hypot(item.ray_error, item.reach_error)
                    for item in results if item.state in CUT_STATES), default=math.inf)

    def signed_ray_error(self, result):
        dx, dz = result.new[0] - result.old[0], result.new[1] - result.old[1]
        length = math.hypot(dx, dz)
        if not length:
            return math.inf
        sx, sz = self.seam.S
        return ((sx - result.old[0]) * dz - (sz - result.old[1]) * dx) / length

    def precision_seeds(self, results, limit=64):
        eligible = [item for item in results if item.state in CUT_STATES
                    and item.reach_error == 0 and item.ray_error < 1.0]
        ranked = sorted(eligible, key=lambda item: (item.aim_error,
                        abs(self.signed_ray_error(item)), item.score))
        if not ranked:
            return []
        spacing = max(self._seam_ulp(value) for value in self.seam.S) / 4
        chosen, controls, regions, bands = [], set(), set(), set()

        def add(item):
            if item.controls not in controls:
                chosen.append(item)
                controls.add(item.controls)

        for item in ranked:
            region = (round(item.old[0], 1), round(item.old[1], 1), item.facing // 128)
            if region not in regions:
                regions.add(region)
                add(item)
                if len(chosen) >= min(16, limit):
                    break
        for item in ranked:
            band = round(self.signed_ray_error(item) / spacing)
            if band not in bands:
                bands.add(band)
                add(item)
                if len(chosen) >= min(32, limit):
                    break
        for item in ranked:
            add(item)
            if len(chosen) >= limit:
                break
        return chosen

    @staticmethod
    def _seam_ulp(value):
        bits = struct.unpack("<I", struct.pack("<f", abs(value)))[0]
        return struct.unpack("<f", struct.pack("<I", bits + 1))[0] - abs(value)

    def screen_promising(self, results):
        slashes = [item for item in results if item.state in CUT_STATES]
        if any(item.exact for item in slashes):
            return True
        self.screen_distance = min(
            (math.hypot(item.ray_error, item.reach_error) for item in slashes), default=math.inf)
        self.screen_slash_length = max(
            (math.hypot(item.new[0] - item.old[0], item.new[1] - item.old[1])
             for item in slashes), default=40.0)
        return self.screen_distance <= max(40.0, self.screen_slash_length)

    def beam_order(self, results, limit):
        ranked = sorted(results, key=self.result_rank)
        reserved, seen, regions = [], set(), set()
        for item in sorted(ranked, key=lambda candidate: (
                candidate.collision_error + candidate.retention_error,
                candidate.reach_error, candidate.ray_error)):
            if item.state not in CUT_STATES or item.reach_error > 20 or item.ray_error > 50:
                continue
            region = (round(item.old[0]), round(item.old[1]), item.facing // 256)
            if region in regions:
                continue
            reserved.append(item)
            seen.add(item.controls)
            regions.add(region)
            if len(reserved) >= max(1, limit // 8):
                break
        if getattr(self, "prioritize_full_speed", False):
            fast = sorted((item for item in ranked if item.state in CUT_STATES
                           and item.reach_error <= 2 and item.ray_error < 5),
                          key=lambda item: (-item.speedf, item.reach_error, item.ray_error))
            for item in fast:
                if item.controls in seen:
                    continue
                reserved.append(item)
                seen.add(item.controls)
                if len(reserved) >= max(2, limit // 4):
                    break
        return reserved + [item for item in ranked if item.controls not in seen]

    def result_rank(self, result):
        if not getattr(self, "prioritize_full_speed", False):
            return (result.score,)
        if result.exact:
            return (result.score, -result.speedf, result.dispatch_row)
        near = result.state in CUT_STATES and result.reach_error <= 2 and result.ray_error < 5
        speed_loss = max(0.0, self.preferred_speed - result.speedf) if near else 0.0
        return (result.score + 0.001 * speed_loss, -result.speedf)

    def preferred_exact(self, result):
        return result.exact and (not getattr(self, "prioritize_full_speed", False)
                                 or result.speedf >= self.preferred_speed)

    def __init__(self, trace, dispatch_row, *, worker, mode="walking", from_start=False,
                 cancelled=lambda: False, prioritize_full_speed=False):
        self.trace = trace
        self.route = _route(trace)
        if trace.get("native"):
            self.route = align_movie_polls(self.route, trace.get("trace", ()),
                                           trace["native"]["seeds"], decode_row)
        self.dispatch_row = int(dispatch_row)
        self.worker = worker
        self.cancelled = cancelled
        self.mode = mode
        self.prioritize_full_speed = bool(prioritize_full_speed)
        self.preferred_speed = 25.9 if mode == "rolling" else 16.9
        self.rejections = {}
        self.base_rows = [dict(row) for row in self.route.rows]
        self.captured_count = len(self.base_rows)
        native = trace.get("native")
        if not native:
            raise RuntimeError("capture this route again with the native finder")
        self.seeds = native["seeds"]
        self.input_delay = infer_input_delay(self.base_rows, self.seeds)
        lag = recorded_slash_buffer(trace) if not from_start or mode == "walking" else 0
        self.button_row = max(0, self.dispatch_row - self.input_delay - lag)
        self.retime_local = not from_start
        self.seam = SeamGeo(trace["geo"], self.seeds[0]["camera"])
        validation_end = approach_validation_end(trace, self.dispatch_row, from_start)
        self.actor_push_prefix = actor_push_prefix_end(trace)
        candidates = approach_anchor_rows(trace, self.dispatch_row, validation_end, from_start)
        failures = []
        for anchor in candidates:
            if cancelled():
                raise RuntimeError("search cancelled")
            start = self.seeds[anchor + 1]
            if int(start["proc"]) not in (4, 6, 7, 10, 11, 23, 24, 25, 30):
                continue
            camera = int(start["camera"])
            if not start.get("camera_state"):
                raise RuntimeError("recapture this route to import the live camera state")
            self.anchor_row = anchor
            self.start_seed = start
            self.camera = camera
            rows = self._effective_rows(self.base_rows, validation_end)
            result = worker.replay(start, [rows], camera, diagnostics=True)[0]
            try:
                if result.get("error"):
                    raise RuntimeError(result["error"])
                expected = []
                for i in range(anchor + 1, validation_end):
                    frame = dict(trace["trace"][i]["after"])
                    fields = self.seeds[i + 1]["camera_state"]["fields"]
                    frame.update(camera_eye=fields["mEye"], camera_center=fields["mCenter"])
                    frame["under"] = self.seeds[i + 1]["under"]
                    expected.append(frame)
                validate_replay(result["frames"], expected)
                break
            except RuntimeError as exc:
                failures.append(str(exc))
        else:
            reason = failures[-1] if failures else (
                "slash timing precedes the preserved actor-push segment" if self.actor_push_prefix else "unported state")
            raise RuntimeError("no bit-exact native approach anchor: " + reason)
        self.anchor_error = 0.0
        self.validation_end = validation_end
        self.variable_start = self.anchor_row + 1
        walk_start = self.variable_start
        if self.mode == "walking":
            roll_frames = [i for i in range(self.variable_start,
                                            min(self.dispatch_row + 1, len(self.seeds)))
                           if self.seeds[i]["proc"] == 30]
            if roll_frames:
                walk_start = roll_frames[-1] + 1
        self.walk_row = max(0, ground_start(self.seeds, walk_start) - self.input_delay)
        self.roll_axis = self.mode == "rolling"
        self.recipe_axis = True
        self.route_recipes = True
        if from_start:
            tail = dict(stickX=128, stickY=128, substickX=128, substickY=89,
                        buttons=0, triggerL=0, triggerR=0)
            self.base_rows.extend(dict(tail) for _ in range(max(0, self.dispatch_row + 9 - len(self.base_rows))))
            spans = list(self.route.poll_spans)
            if spans:
                while len(spans) < len(self.base_rows):
                    start = spans[-1][1]
                    spans.append((start, start + 4))
            self.route = replace(self.route, end_vi=self.route.start_vi + 2 * len(self.base_rows),
                                 rows=tuple(self.base_rows), poll_spans=tuple(spans))
        self.control_rows = tuple(range(first_editable_row(self.anchor_row, self.input_delay),
                                        min(len(self.base_rows), self.dispatch_row + 2)))

    def route_starts(self, limit, seed):
        prior = getattr(self, "warm_result", None)
        if prior and prior.get("route_identity") not in (None, self.control_metadata()["route_identity"]):
            prior = None
        if prior and limit:
            values = prior.get("controls", ())
            rows = [dict(row) for row in self.base_rows]
            raw_start = int(prior.get("variable_start", 0)) - self.input_delay
            indices = prior.get("control_rows", list(range(raw_start, raw_start + len(values) // 4)))
            if indices and min(indices) >= 0 and max(indices) < len(rows):
                for offset, index in enumerate(indices):
                    for axis, key in enumerate(("stickX", "stickY", "substickX", "substickY")):
                        rows[index][key] = int(values[offset * 4 + axis])
                controls = list(self.controls_from_rows(rows))
                schema = prior.get("control_schema")
                recipe = int(values[len(indices) * 4]) if schema in ("native-route-v2", "native-route-v3") else 3
                controls[len(self.control_rows) * 4] = recipe if schema == "native-route-v3" else recipe % 4
                if self.roll_axis and prior.get("mode") == "rolling" and prior.get("control_schema"):
                    controls[-1] = int(values[-1])
                yield tuple(controls)
                limit -= 1
                for trial in itertools.islice(pre_roll_starts(self, tuple(controls)), min(limit, 12)):
                    yield trial
                    limit -= 1
        for trial in recorded_starts(self, min(limit // 2, 96), seed):
            yield trial
            limit -= 1
        yield from route_starts(self, limit, seed)

    def local_starts(self, limit, seed):
        yield from recorded_starts(self, limit, seed)

    def control_metadata(self):
        identity = json.dumps([self.seeds[0], self.trace["geo"], self.trace["route"]["start_vi"],
                               self.route.rows, self.route.poll_spans],
                              sort_keys=True, separators=(",", ":")).encode("ascii")
        return dict(control_schema="native-route-v3" if getattr(self, "route_recipes", False) else "native-route-v2",
                    control_rows=list(self.control_rows),
                    planned_dispatch_row=self.dispatch_row,
                    export_poll_spans=list(self.route.poll_spans),
                    validated_approach=dict(start=self.variable_start, end=self.validation_end),
                    preserved_actor_push_rows=getattr(self, "actor_push_prefix", 0),
                    route_identity=hashlib.sha256(identity).hexdigest())

    def polish(self, results, cap, phase, synthesis, log):
        """Use replay-measured sensitivities to propose coupled camera/stick changes.

        Linear estimates only choose trials: every trial still runs the native
        movement and collision engine, including float32 rounding.
        """
        eligible = self.precision_seeds(results)
        if not eligible or cap <= 0:
            return None, 0
        best = min(eligible, key=lambda item: item.score)
        parents = eligible
        archive = self.precision_seeds([*getattr(self, "precision_candidates", ()), *eligible])
        seen = {item.controls for item in results}
        expanded = set()
        expanded_positions = set()
        # Triangle/plane tests round at float32 precision. The clipping band
        # need not be centered on the double-precision vertex ray.
        spacing = max(self._seam_ulp(value) for value in self.seam.S) / 4
        targets = [i * spacing for i in range(-8, 9)]
        count = 0
        while parents and count < cap:
            parent = parents.pop(0)
            expanded.add(parent.controls)
            expanded_positions.add((parent.old, parent.new, parent.facing, parent.travel, parent.speedf,
                                    parent.collision_error, parent.retention_error))
            base_error = self.signed_ray_error(parent)
            probes = []
            for axis in range(len(self.control_rows) * 4):
                for delta in (-1, 1):
                    controls = list(parent.controls)
                    controls[axis] = max(0, min(255, controls[axis] + delta))
                    trial = tuple(controls)
                    if trial not in seen:
                        probes.append((axis, controls[axis] - parent.controls[axis], trial))
                        seen.add(trial)
            probes = probes[:cap - count]
            gradients = {}
            evaluated = []
            for (axis, delta, controls), result in zip(probes, self.evaluate_many(
                    [item[2] for item in probes], phase=phase, synthesize_buttons=synthesis)):
                count += 1
                evaluated.append(result)
                if result.exact:
                    return result, count
                if result.score < best.score:
                    best = result
                if result.state == parent.state and result.reach_error == 0:
                    slope = (self.signed_ray_error(result) - base_error) / delta
                    if math.isfinite(slope) and abs(slope) > 1e-9:
                        gradients.setdefault(axis, []).append(slope)
            gradients = {axis: sum(values) / len(values) for axis, values in gradients.items()}
            # Opposing one-sided probes can cancel even when neither slope is zero.
            gradients = {axis: slope for axis, slope in gradients.items()
                         if math.isfinite(slope) and abs(slope) > 1e-9}
            proposals = BoundedBands(len(targets), 48)
            for axis, slope in gradients.items():
                for other, other_slope in gradients.items():
                    if other <= axis:
                        continue
                    for delta in range(-4, 5):
                        for bucket, target in enumerate(targets):
                            change = round((target - base_error - slope * delta) / other_slope)
                            if not -12 <= change <= 12:
                                continue
                            for extra in (-1, 0, 1):
                                first = max(0, min(255, parent.controls[axis] + delta))
                                second = max(0, min(255, parent.controls[other] + change + extra))
                                predicted = (base_error + slope * (first - parent.controls[axis])
                                             + other_slope * (second - parent.controls[other]))
                                distance = abs(predicted - target)
                                if not proposals.promising(bucket, distance):
                                    continue
                                controls = list(parent.controls)
                                controls[axis], controls[other] = first, second
                                trial = tuple(controls)
                                if trial not in seen:
                                    proposals.add(bucket, distance, trial)
            trials = proposals.interleaved(cap - count)
            seen.update(trials)
            for result in self.evaluate_many(trials, phase=phase, synthesize_buttons=synthesis):
                count += 1
                evaluated.append(result)
                if result.exact:
                    return result, count
                if result.score < best.score:
                    best = result
            archive = self.precision_seeds([*archive, *evaluated])
            refined = [item for item in evaluated if item.state == parent.state
                       and item.reach_error == 0
                       and item.ray_error < max(parent.ray_error * 2, spacing * 8)
                       and item.aim_error == 0]
            signatures = set()
            available = []
            for item in [*parents, *refined]:
                signature = (item.old, item.new, item.facing, item.travel, item.speedf,
                             item.collision_error, item.retention_error)
                if item.controls in expanded or signature in signatures or signature in expanded_positions:
                    continue
                signatures.add(signature)
                available.append(item)
            parents = self.precision_seeds(available)
            log("%s: coupled camera/stick polish %d/%d, best ray %.9f, wall correction %.6f, "
                "rebound %.6f" % (phase, count, cap, best.ray_error,
                                   best.collision_error, best.retention_error))
        self.precision_candidates = archive
        return best, count

    def restart_near(self, result, cap, seed, log, cancelled):
        near = self.search_proximity((result,)) <= NEAR_SEAM_SEARCH_DISTANCE
        if not near:
            cap = min(cap, 2048)
        return _beam_search(self, result.controls, cap=cap, seed=seed,
                            phase=result.phase, broad=result.phase == "route synthesis",
                            initial_result=result, log=log, cancelled=cancelled,
                            near_restart=near,
                            seed_results=getattr(self, "precision_candidates", ()))

    def reaim_controls(self, controls):
        """Re-steer a planned world-space approach under its simulated camera path."""
        values = list(controls)
        ready = ground_start(self.seeds, self.variable_start)
        landing = self.seeds[min(ready, len(self.seeds) - 1)]
        reference = landing["camera"]
        sx, sz = self.seam.S
        initial_bearing = round(math.atan2(sx - landing["pos"][0], sz - landing["pos"][2]) * 32768 / math.pi)
        for offset, row in enumerate(self.control_rows):
            if row < self.walk_row:
                continue
            index = row + self.input_delay - self.variable_start - 1
            if not 0 <= index < len(self.latest_frames):
                continue
            actual_camera = self.latest_frames[index]["camera"]
            position = self.latest_frames[index]["pos"]
            if self.latest_frames[index]["state"] in CUT_STATES:
                first_cut = next((frame for frame in self.latest_frames[:index + 1]
                                  if frame["state"] in CUT_STATES and frame["before"] not in CUT_STATES), None)
                if first_cut:
                    position = first_cut["old"]
            pad = decode_row(dict(stickX=controls[offset * 4], stickY=controls[offset * 4 + 1]))
            bearing = round(math.atan2(sx - position[0], sz - position[2]) * 32768 / math.pi)
            offset_angle = ((pad["angle"] + reference - initial_bearing + 32768) & 65535) - 32768
            x, y = stick_for_bearing((bearing + offset_angle) & 65535, actual_camera, pad["distance"])
            values[offset * 4:offset * 4 + 2] = x, y
        return tuple(values)

    @property
    def axes(self):
        return tuple(range(len(self.control_rows) * 4 + int(getattr(self, "recipe_axis", False))
                           + int(getattr(self, "roll_axis", False))))

    def refinement_possible(self):
        return (self.mode != "rolling" or self.start_seed["proc"] == 30
                or any(int(self.base_rows[index].get("buttons", 0)) & 0x100
                       for index in self.control_rows))

    def controls_from_rows(self, rows=None):
        rows = self.base_rows if rows is None else rows
        controls = tuple(int(rows[index].get(key, 128)) for index in self.control_rows
                         for key in ("stickX", "stickY", "substickX", "substickY"))
        if getattr(self, "recipe_axis", False):
            controls = (*controls, 4 if getattr(self, "route_recipes", False) else 2)
        return (*controls, 16) if getattr(self, "roll_axis", False) else controls

    def _effective_rows(self, rows, end):
        neutral = {"stickX": 128, "stickY": 128, "buttons": 0}
        result = []
        for index in range(self.anchor_row + 1, end):
            source = index - self.input_delay
            raw = rows[source] if source >= 0 else neutral
            pad = decode_row(raw)
            if index < len(self.seeds) and (source < 0 or raw == self.base_rows[source]):
                pad = dict(self.seeds[index].get("pad", pad))
            else:
                previous = result[-1] if result else (
                    self.seeds[index - 1].get("pad", {}) if 0 < index <= len(self.seeds) else {})
                if index < len(self.seeds) and source >= 0:
                    saved = self.seeds[index].get("pad", {})
                    baseline = self.base_rows[source]
                    groups = (
                        (("stickX", "stickY"), ("mx", "my", "distance", "angle")),
                        (("substickX", "substickY"), ("cx", "cy", "cvalue", "cangle")),
                        (("buttons", "triggerL", "triggerR"),
                         ("hold", "item_button", "target", "lock_l", "lock_r", "trig_l", "trig_r",
                          "tl", "tr", "analog_a", "analog_b")),
                    )
                    for inputs, fields in groups:
                        if all(raw.get(k, 0) == baseline.get(k, 0) for k in inputs):
                            pad.update({k: saved[k] for k in fields if k in saved})
                # Lock-trigger edges and neutral-stick angles depend on prior input.
                for side in ("l", "r"):
                    if source >= 0 and (index >= len(self.seeds) or any(
                            raw.get(k, 0) != self.base_rows[source].get(k, 0)
                            for k in ("buttons", "triggerL", "triggerR"))):
                        pad["trig_" + side] = int(bool(pad["lock_" + side])
                                                  and not previous.get("lock_" + side, 0))
                for angle, magnitude in (("angle", "distance"), ("cangle", "cvalue")):
                    if not pad[magnitude] and angle in previous:
                        pad[angle] = previous[angle]
            result.append(pad)
        return result

    def rows_from_controls(self, controls, synthesize_buttons=False, retime_slash=False):
        if len(controls) != len(self.control_rows) * 4 + int(getattr(self, "recipe_axis", False)) + int(getattr(self, "roll_axis", False)):
            raise ValueError("native controls must contain both main and C-stick axes for each row")
        rows = [dict(row) for row in self.base_rows]
        recipe, roll_delay = route_recipe(self, controls)
        for offset, index in enumerate(self.control_rows):
            for axis, key in enumerate(("stickX", "stickY", "substickX", "substickY")):
                rows[index][key] = int(controls[offset * 4 + axis])
        if retime_slash:
            start = self.control_rows[0]
            for index in range(start, len(rows)):
                rows[index]["buttons"] = int(rows[index].get("buttons", 0)) & ~0x200
            # Preserve held B through sword draw; a one-row pulse is not equivalent
            # to the user's recorded buffered slash when another item is equipped.
            end = min(len(rows), self.button_row + 5)
            for index in range(max(start, self.button_row), end):
                rows[index]["buttons"] |= 0x200
        if synthesize_buttons:
            for index in range(self.control_rows[0], len(rows)):
                removed = 0x200 if roll_delay is not None else 0x100 | 0x200 | 0x40
                rows[index]["buttons"] = int(rows[index].get("buttons", 0)) & ~removed
                if roll_delay is None:
                    rows[index]["triggerL"] = 0
            rows[self.button_row]["buttons"] |= 0x200
            walk = getattr(self, "walk_row", None)
            if self.mode == "rolling" and roll_delay is None:
                roll_row = roll_button_row(self, controls)
                if roll_row < self.button_row:
                    rows[roll_row]["buttons"] |= 0x100
                if (walk is not None and self.start_seed.get("fields", {}).get("mEquipItem") != SWORD_EQUIP_ITEM
                        and walk + 1 < roll_row - 4):
                    rows[walk + 1]["buttons"] |= 0x200
            else:
                roll_row = self.button_row
            if roll_delay is None and walk is not None and walk < roll_row and recipe:
                for index in range(max(self.control_rows[0], walk - int(recipe >= 2)), walk + 1):
                    rows[index]["buttons"] |= 0x40
                    if recipe == 3:
                        rows[index]["triggerL"] = 255
                    if recipe != 3:
                        rows[index]["substickX"], rows[index]["substickY"] = 128, 89
        if roll_delay and (synthesize_buttons or retime_slash):
            for launch in recorded_roll_rows(self):
                moved = launch + roll_delay
                if self.control_rows[0] <= launch < self.button_row and self.control_rows[0] <= moved < self.button_row:
                    stop = launch + 1
                    while stop < self.button_row and self.base_rows[stop].get("buttons", 0) & 0x100:
                        stop += 1
                    for index in range(launch, stop):
                        rows[index]["buttons"] &= ~0x100
                    for index in range(moved, min(stop + roll_delay, self.button_row)):
                        rows[index]["buttons"] |= 0x100
        return rows

    def _result(self, controls, replay, phase):
        if replay.get("error") or not replay.get("frames"):
            reason = replay.get("error", "native replay returned no frames")
            self.rejections[reason] = self.rejections.get(reason, 0) + 1
            return RouteResult(False, phase, self.dispatch_row, self.button_row,
                               self.variable_start, tuple(controls), (0, 0), (0, 0),
                               -1, 0, 0, 0.0, 1e10, 1e10, 0)
        frames = replay["frames"]
        transitions = [i for i, frame in enumerate(frames)
                       if frame["state"] in CUT_STATES and frame["before"] not in CUT_STATES]
        return min((self._transition_result(controls, frames, index, phase)
                    for index in transitions or [None]), key=lambda result: result.score)

    def _transition_result(self, controls, frames, transition, phase):
        frame = frames[transition] if transition is not None else frames[-1]
        old3, new3 = frame["old"], frame["raw"]
        old, new = (old3[0], old3[2]), (new3[0], new3[2])
        dx, dz = new[0] - old[0], new[1] - old[1]
        length = math.hypot(dx, dz)
        sx, sz = self.seam.S
        if length:
            along = ((sx - old[0]) * dx + (sz - old[1]) * dz) / length
            reach = max(0.0, -along) + max(0.0, along - length)
            ray = abs((sx - old[0]) * dz - (sz - old[1]) * dx) / length
        else:
            reach = ray = math.hypot(sx - old[0], sz - old[1])
        mode_ok = frame["before"] == 30 if self.mode == "rolling" else frame["before"] in (6, 7, 24)
        planes = (self.seam.wA.pla, self.seam.wB.pla)
        post = frames[transition:transition + 4] if transition is not None else []
        retained = any(plane.func(old3) > 0 and all(plane.func(item["pos"]) < 0 for item in post)
                       for plane in planes) if len(post) == 4 else False
        allowed = getattr(self, "facing_ranges", FacingRanges())
        aim_error = allowed.distance(frame["facing"])
        exact = bool(transition is not None and mode_ok and reach == 0.0 and ray < 0.02
                     and aim_error == 0
                     and all(plane.func(old3) > 0 for plane in planes)
                     # GroundCross restores Y after gravity even during a clean grounded clip.
                     and all(f32_equal(new3[axis], frame["pos"][axis]) for axis in (0, 2))
                     and not frame.get("flags", 0) & (0x10 | 0x10000) and retained)
        collision_error = math.hypot(new3[0] - frame["pos"][0], new3[2] - frame["pos"][2])
        retention_error = (min(max(max(0.0, plane.func(item["pos"])) for item in post)
                               for plane in planes) if len(post) == 4 else 100.0)
        actual_dispatch = self.anchor_row + 1 + transition if transition is not None else self.dispatch_row
        return FacingRouteResult(exact, phase, actual_dispatch, self.button_row,
                           self.variable_start, tuple(controls), old, new,
                           frame["state"] if mode_ok else -1, frame["facing"], frame["travel"],
                           frame["speed"], ray, reach, aim_error, collision_error=collision_error,
                           retention_error=retention_error)

    def evaluate_many(self, controls, phase="route refinement", synthesize_buttons=False):
        batch_size = getattr(self, "batch_size", 128)
        for start in range(0, len(controls), batch_size):
            if self.cancelled():
                raise RuntimeError("search cancelled")
            batch = controls[start:start + batch_size]
            rows = [self._effective_rows(self.rows_from_controls(c, synthesize_buttons,
                                        retime_slash=(phase == "route refinement" and
                                                      getattr(self, "retime_local", False))),
                                        min(len(self.base_rows), self.dispatch_row + 9)) for c in batch]
            # Different byte sticks often clamp to exactly the same pad trace.
            # Replay that trace once, retaining each candidate's authored bytes.
            unique, lookup, slots = [], {}, []
            for route in rows:
                key = json.dumps(route, sort_keys=True, separators=(",", ":"))
                if key not in lookup:
                    lookup[key] = len(unique)
                    unique.append(route)
                slots.append(lookup[key])
            results = self.worker.replay(self.start_seed, unique, self.camera)
            for c, slot in zip(batch, slots):
                result = results[slot]
                self.latest_frames = result.get("frames", ())
                yield self._result(c, result, phase)

    def evaluate(self, controls, phase="route refinement", synthesize_buttons=False):
        return next(self.evaluate_many([controls], phase, synthesize_buttons))

    def family_has_dust(self, result):
        # Native replay, not a synthetic endpoint, is the acceptance authority.
        return (result.state in CUT_STATES and result.reach_error == 0.0
                and result.ray_error < 0.02 and result.aim_error == 0)

    def export(self, result, output):
        # Recheck the accepted inputs on one lane before writing a movie. A
        # thread-count-sensitive result is not a reproducible simulation proof.
        previous = self.worker.workers
        try:
            self.worker.workers = 1
            checked = self.evaluate(result.controls, phase=result.phase,
                                    synthesize_buttons=result.phase == "route synthesis")
        finally:
            self.worker.workers = previous
        fields = ("controls", "old", "new", "state", "facing", "travel", "speedf",
                  "dispatch_row", "button_row")
        if not checked.exact or any(getattr(checked, key) != getattr(result, key) for key in fields):
            raise RuntimeError("native clip did not reproduce in the single-worker export check")
        rows = self.rows_from_controls(result.controls, synthesize_buttons=result.phase == "route synthesis",
                                       retime_slash=result.phase == "route refinement")
        return install_route_movie(self.route, rows, output, short=False, extend=True,
                                   replace_from=self.control_rows[0])


def search_native_trace(trace, output_dir, *, executable, iso, mode="Both", workers=0,
                        evaluation_cap=30000, random_seed=615507812,
                        log=print, cancelled=lambda: False, allow_mode_fallback=False,
                        facing_ranges="0-65535", widen_facing=True,
                        prioritize_full_speed=False):
    return search_facing_passes(
        lambda allowed, index: _search_native_trace(
            trace, output_dir, executable=executable, iso=iso, mode=mode, workers=workers,
            evaluation_cap=evaluation_cap, random_seed=random_seed + index * 9973,
            log=log, cancelled=cancelled, allow_mode_fallback=allow_mode_fallback,
            facing_ranges=allowed, prioritize_full_speed=prioritize_full_speed),
        facing_ranges, widen_facing, log, cancelled)


def native_result_rank(result, prioritize_full_speed=False):
    if prioritize_full_speed and result["exact"]:
        return (False, -result["speedf"], result["dispatch_row"])
    return (not result["exact"], result["score"])


def _search_native_trace(trace, output_dir, *, executable, iso, mode="Both", workers=0,
                        evaluation_cap=30000, random_seed=615507812,
                        log=print, cancelled=lambda: False, allow_mode_fallback=False,
                        facing_ranges=FacingRanges(), prioritize_full_speed=False):
    native = trace.get("native")
    if not native:
        raise RuntimeError("native capture is missing; capture this route with the C++ finder")
    # Validate controller provenance once, before constructing any search windows.
    route = align_movie_polls(_route(trace), trace.get("trace", ()), native["seeds"], decode_row)
    infer_input_delay(route.rows, native["seeds"])
    trace = dict(trace, route=dict(trace["route"], rows=list(route.rows),
                                  poll_spans=list(route.poll_spans)))
    output_dir = Path(output_dir)
    assets = extract_assets(iso, output_dir / "assets")
    worker = NativeWorker(executable, assets, native["room"], workers, cancelled=cancelled)
    try:
        best = None
        failures = []
        total_evaluations = 0
        tested_modes = []
        modes = ("walking", "rolling") if mode == "Both" else (mode.lower(),)
        if mode == "Both":
            log("Both searches either slash action; roll-to-walk approaches are walking slash candidates.")
        if prioritize_full_speed:
            log("Prioritizing clip-frame speed and earlier slash windows; slower exact clips remain fallback results.")
        if allow_mode_fallback and len(modes) == 1:
            modes = (*modes, "walking" if modes[0] == "rolling" else "rolling")
        original_end = len(route.rows)
        checked_end = approach_validation_end(trace, original_end, True)
        actor_prefix = actor_push_prefix_end(trace)
        if actor_prefix:
            log("Recorded actor collision affects the first %d gameplay rows; preserving that movie segment "
                "and replanning after it. Actor Co pushes are not replaced with fitted offsets." % actor_prefix)
        if checked_end < original_end:
            log("Validating the recorded approach through row %d; the failed slash/rebound is replaced, "
                "not required of alternative routes." % (checked_end - 1))
        for mode_index, selected in enumerate(modes):
            if total_evaluations >= evaluation_cap:
                break
            if selected != modes[0]:
                log("Preferred slash type has no exact hit; trying %s routes automatically." % selected)
            log("Native %s search on %d CPU worker(s)" % (selected, worker.workers))
            families = []
            launch_reported = False
            old_result = output_dir / selected / "smart_route_result.json"
            try:
                warm = json.loads(old_result.read_text()) if old_result.is_file() else None
                if not isinstance(warm, dict):
                    warm = None
                if warm:
                    values = warm.get("controls", ())
                    modern = warm.get("control_schema") in ("native-route-v2", "native-route-v3")
                    indices = warm.get("control_rows", ())
                    valid = (bool(values) and all(type(value) is int and 0 <= value <= 255 for value in values)
                             and type(warm.get("variable_start")) is int)
                    if modern:
                        valid = valid and (bool(indices) and all(type(i) is int and 0 <= i <= 100000 for i in indices)
                            and list(indices) == sorted(set(indices))
                            and len(values) == len(indices) * 4 + 1 + int(warm.get("mode") == "rolling"))
                    else:
                        valid = valid and len(values) % 4 == 0
                    if not valid:
                        warm = None
            except (ValueError, OSError, TypeError):
                warm = None
            def factory(trace, dispatch, **kw):
                nonlocal launch_reported
                family = NativeFamily(trace, dispatch, worker=worker, mode=selected,
                                      cancelled=cancelled,
                                      prioritize_full_speed=prioritize_full_speed, **kw)
                family.facing_ranges = facing_ranges
                families.append(family)
                family.warm_result = warm
                rolls = recorded_roll_rows(family)
                if kw.get("from_start") and rolls and rolls[-1] < family.control_rows[0] and not launch_reported:
                    log("Recorded roll A row %d precedes the exact native window at row %d; "
                        "preserving that launch and varying landing/post-roll inputs instead."
                        % (rolls[-1], family.control_rows[0]))
                    launch_reported = True
                return family
            try:
                result = search_trace(
                    trace, output_dir / selected,
                    evaluation_cap=max(1, (evaluation_cap - total_evaluations) // (len(modes) - mode_index)),
                    strict_budget=True,
                    random_seed=random_seed, log=log, cancelled=cancelled, family_factory=factory,
                    final_refinement=True,
                    dispatch_factory=(lambda data: prioritize_dispatches(data, native_dispatch_rows(data))),
                    synthesis_dispatch_factory=(lambda data: prioritize_dispatches(data, replan_dispatches(data, selected))),
                )
            except RuntimeError as exc:
                if cancelled() or isinstance(exc, NativeWorkerError):
                    raise
                failures.append(str(exc))
                log("Native %s search rejected: %s" % (selected, exc))
                continue
            result.update(backend="tww_engine", mode=selected, baseline_bit_exact=True,
                          live_verified=False, facing_frame="slash displacement",
                          prioritize_full_speed=bool(prioritize_full_speed))
            total_evaluations += result["evaluations"]
            tested_modes.append(selected)
            rejected = {}
            for family in families:
                for reason, count in family.rejections.items():
                    rejected[reason] = rejected.get(reason, 0) + count
            result["native_rejections"] = rejected
            for reason, count in sorted(rejected.items(), key=lambda item: -item[1])[:5]:
                log("Rejected %d native candidate(s): %s" % (count, reason))
            Path(result["result_path"]).write_text(json.dumps(result, indent=2), encoding="ascii")
            if best is None or native_result_rank(result, prioritize_full_speed) < native_result_rank(best, prioritize_full_speed):
                best = result
            if result["exact"] and not prioritize_full_speed:
                break
        if best is None:
            raise RuntimeError("No native search window passed unchanged-route validation. " + "; ".join(failures))
        best["mode_evaluations"] = best["evaluations"]
        best["evaluations"] = total_evaluations
        best["tested_modes"] = tested_modes
        Path(best["result_path"]).write_text(json.dumps(best, indent=2), encoding="ascii")
        return best
    finally:
        worker.close()
