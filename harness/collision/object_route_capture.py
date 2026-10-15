"""Carried actor identity and release observations for the route finder."""
import json
import hashlib
import math
from dataclasses import replace
from pathlib import Path
import tempfile
from harness.rollstab.native_route_playback import capture_native_route


def object_kind(process, parameters=0, status=0):
    if status & 0x10000:
        raise ValueError("heavy objects use a throw rather than the ordinary B-drop")
    if process == 0x128:
        return "bomb"
    if process == 0x1CB:
        subtype = (int(parameters) >> 24) & 15
        if subtype != 0:
            raise ValueError("this pot variant is not the modeled small pot (type %d)" % subtype)
        return "pot_small"
    raise ValueError("unsupported carried actor 0x%03X; carry a bomb or small pot" % process)


class ObjectObserver:
    def __init__(self):
        self.actor = None
        self.identity = None

    def __call__(self, reader, snapshot):
        address = int(snapshot.grab_actor)
        if 0x80000000 <= address < 0x81800000:
            if self.actor is not None and address != self.actor:
                raise RuntimeError("the route switched carried objects")
            if self.actor is None:
                process = reader.u16(address + 8)
                parameters = reader.u32(address + 0xB0)
                status = reader.u32(address + 0x1C4)
                self.identity = dict(object_type=object_kind(process, parameters, status),
                                     actor=address, process=process, parameters=parameters)
                self.actor = address
        return dict(holding=bool(self.actor is not None and address == self.actor),
                    identity=self.identity,
                    prop_pos=[reader.f32(self.actor + 0x1F8 + i * 4) for i in range(3)]
                    if self.actor is not None else None,
                    prop_mode=reader.u32(self.actor + 0x678)
                    if self.identity and self.identity["object_type"] == "pot_small" else None,
                    cc_move=list(snapshot.cc_move),
                    link_co_center=list(snapshot.link_co_center),
                    link_co_radius=snapshot.link_co_radius,
                    link_co_height=snapshot.link_co_height)


def capture_object_route(pid, target, route, output_dir, log=print, cancelled=lambda: False):
    observer = ObjectObserver()
    trace = capture_native_route(pid, target, route, output_dir, log=log,
                                 cancelled=cancelled, capture_extra=observer)
    from harness.collision.storage_walk import storage_active
    stored_walk = storage_active(trace)
    if observer.identity is None and not stored_walk:
        raise RuntimeError("the selected route never carries a bomb or small pot; "
                           "a storage walk requires persistent disabled wall correction")
    observations = trace.get("extra", ())
    released = any(before["holding"] and not after["holding"]
                   for before, after in zip(observations, observations[1:]))
    trace["object"] = (observer.identity if observer.identity and released
                       else {"object_type": "storage_walk"} if stored_walk
                       else observer.identity)
    trace["storage_walk"] = stored_walk
    (Path(output_dir) / "manual_route_trace.json").write_text(
        json.dumps(trace, indent=2), encoding="ascii")
    if stored_walk:
        log("Detected persistent WALL_NONE collision across the captured route; "
            "native replay will preserve chest-storage wall behavior.")
    if observer.identity:
        log("Detected carried %s; preserving the original movie's controller lane and poll timing."
            % observer.identity["object_type"])
    if trace["object"]["object_type"] == "storage_walk":
        log("No B-release required: searching a direct storage walk through the selected seam.")
    return trace


def verify_drop_constraints(family, released, consume):
    from harness.collision.object_route import landing_errors
    from harness.rollstab.route_constraints import FacingRanges

    allowed = getattr(family.context, "facing_ranges", FacingRanges())
    if allowed.distance(released["facing"]):
        raise RuntimeError("live pre-push facing is outside the accepted range")
    if getattr(family.context, "roll_on_clip", False):
        if consume["state"] != 30:
            raise RuntimeError("live push frame did not enter front roll")
        if family.context.roll_facing_ranges.distance(consume["facing"]):
            raise RuntimeError("live push-frame roll facing is outside the accepted range")
        if released["speed"] < getattr(family.context, "oob_min_speed", 0.):
            raise RuntimeError("live pre-push speed is below the selected minimum")
    if getattr(family.context, "require_oob", False):
        _, landing, speed = landing_errors(
            family.seam, consume["pos"], consume.get("grounded", False),
            consume["speed"], family.context.oob_tolerance,
            getattr(family.context, "oob_min_speed", 14.5))
        if landing or speed:
            raise RuntimeError("live OoB seam landing or minimum clip speed requirement was not met")


def verification_row_count(family, rows):
    if family.dispatch_row + 2 >= len(rows):
        raise RuntimeError("the route ends before a post-clip retention frame")
    count = min(len(rows), family.dispatch_row + 4)
    runtime_polls = getattr(family.context, "runtime_polls", None)
    if runtime_polls is not None and family.route.poll_spans[count - 1][1] > runtime_polls:
        raise RuntimeError("the original DTM ends before the required live follow-through")
    return count


def validate_live_object_outcome(family, records, probe, projected):
    from harness.rollstab.native_route import f32_equal

    held, released = records[family.dispatch_row - 1], records[family.dispatch_row]
    if not held["extra"]["holding"] or released["extra"]["holding"]:
        raise RuntimeError("live B-drop did not release the carried object")
    consume = records[family.dispatch_row + 1]
    model_pose_verified = (
        all(f32_equal(a, b) for a, b in zip(
            held["extra"]["prop_pos"], probe["pose"].held_prop_pos))
        and all(f32_equal(a, b) for a, b in zip(
            released["extra"]["prop_pos"], probe["prop"]))
        and all(f32_equal(a, b) for a, b in zip(
            released["extra"]["cc_move"], probe["push"]))
        and all(f32_equal(a, b) for a, b in zip(consume["pos"], projected["pos"])))
    sx, sz = family.seam.S
    old, new = released["pos"], consume["pos"]
    dx, dz = new[0] - old[0], new[2] - old[2]
    length = math.hypot(dx, dz)
    if not length:
        raise RuntimeError("live push had no horizontal displacement")
    along = ((sx - old[0]) * dx + (sz - old[2]) * dz) / length
    ray = abs((sx - old[0]) * dz - (sz - old[2]) * dx) / length
    if along < 0 or along > length or ray >= 0.02:
        raise RuntimeError("live push missed seam: ray %.9f, reach %.9f" %
                           (ray, max(0., -along, along - length)))
    planes = (family.seam.wA.pla, family.seam.wB.pla)
    if not all(plane.func(old) > 0 for plane in planes):
        raise RuntimeError("live pre-push position was not in front of both seam walls")
    if not any(plane.func(new) < 0 for plane in planes):
        raise RuntimeError("live push did not cross a seam wall")
    verify_drop_constraints(family, released, consume)
    follow = records[family.dispatch_row + 2:]
    if any(not any(plane.func(record["pos"]) < 0 for plane in planes) for record in follow):
        raise RuntimeError("live candidate popped back to the front of the seam")
    return model_pose_verified, len(follow)


def verify_object_candidate(family, result, pid, output_dir, log=print):
    """Check the authored movie once, then restore the live movie and state."""
    from harness.collision.object_route import validate_drop_replay
    from harness.collision.live_moving_drop import _snapshot
    from harness.dolphin_control import DolphinControl
    from harness.rollstab.live_slash import open_dolphin
    from harness.rollstab.native_route_capture import ACTOR_PTR, capture_seed, collision_signature
    from harness.rollstab.native_route_playback import attached_route, advance_game_frame
    from harness.validate.native_live_movement import runtime_movie_rows, validate_consumed_pads

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = family.rows_from_controls(result.controls)
    candidate_id = hashlib.sha256(json.dumps(rows[:family.dispatch_row + 2],
                                         sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()[:16]
    attempts = output / "tested_inputs"
    attempts.mkdir(exist_ok=True)
    (attempts / (candidate_id + ".json")).write_text(json.dumps(dict(
        source_state=str(family.route.start_state), source_movie=str(family.route.movie),
        controller=family.route.controller, dispatch_row=family.dispatch_row,
        control_rows=family.control_rows, controls=result.controls,
        poll_spans=family.route.poll_spans, authored_rows=rows,
        native_old=result.old, native_new=result.new), indent=2), encoding="ascii")
    verify_rows = verification_row_count(family, rows)
    pads = family.movement_rows(result.controls)
    native = family.worker.movement(family.start_seed, [pads])[0]
    if native.get("error"):
        raise RuntimeError(native["error"])
    probe, query = family.release_probe(native["frames"])
    projected = family.worker.project([query])[0]
    control = DolphinControl(pid)
    records, live_seeds = [], []
    log("Checking the candidate's P%d movie polls, approach, drop and retention in Dolphin..."
        % (family.route.controller + 1))
    with tempfile.TemporaryDirectory(prefix="drop_verify_", dir=output) as directory:
        folder = Path(directory)
        movie = family.export(result, folder / "candidate.dtm")
        route = replace(family.route, movie=movie, rows=tuple(rows))
        def route_log(message):
            if not message.startswith("Attached original DTM at VI"):
                log(message)

        with attached_route(control, route, folder, route_log), runtime_movie_rows(
                control, route, rows[:verify_rows], folder, replace_from=min(family.control_rows)):
            reader = open_dolphin(pid)
            try:
                observer = ObjectObserver()
                initial = _snapshot(reader, 0)
                observer(reader, initial)
                live_seeds.append(capture_seed(reader, initial))
                signature = collision_signature(reader)
                for index in range(verify_rows):
                    if family.cancelled():
                        raise RuntimeError("search cancelled")
                    status = advance_game_frame(control, reader)
                    if collision_signature(reader) != signature:
                        raise RuntimeError("background collision changed during candidate verification")
                    actual = _snapshot(reader, index + 1)
                    seed = capture_seed(reader, actual)
                    live_seeds.append(seed)
                    record = dict(row=index, vi=status["frame"], pos=[actual.x, actual.y, actual.z],
                                  facing=actual.facing, state=actual.state, speed=actual.speed_f,
                                  extra=observer(reader, actual))
                    if getattr(family.context, "require_oob", False):
                        # JP Link's mAcch (0x46C), m_flags (+0x28), GROUND_HIT (0x20).
                        actor = reader.u32(ACTOR_PTR)
                        record["grounded"] = bool(reader.u32(actor + 0x494) & 0x20)
                    records.append(record)
            finally:
                reader.close()
    report = dict(records=records, expected_old=result.old, expected_new=result.new,
                  release_row=family.dispatch_row, poll_spans=family.route.poll_spans,
                  control_rows=family.control_rows, controls=result.controls,
                  authored_rows=rows, source_state=str(family.route.start_state),
                  consumed_pads=[seed["pad"] for seed in live_seeds[
                      family.variable_start:family.dispatch_row + 2]], intended_pads=pads,
                  predicted_held_prop=probe["pose"].held_prop_pos,
                  predicted_released_prop=probe["prop"], predicted_co_push=probe["push"],
                  predicted_push_endpoint=projected["pos"])
    (output / "last_candidate_check.json").write_text(json.dumps(report, indent=2), encoding="ascii")
    # CPAD observed after an update is consumed by the following update.
    validate_consumed_pads([seed["pad"] for seed in live_seeds[
        family.variable_start:family.dispatch_row + 2]], pads)
    expected = []
    for index in range(family.variable_start, family.dispatch_row + 1):
        record, seed = records[index], live_seeds[index + 1]
        camera = seed["camera_state"]["fields"]
        expected.append(dict(x=record["pos"][0], y=record["pos"][1], z=record["pos"][2],
                             facing=record["facing"], state=record["state"], speed_f=record["speed"],
                             under=seed["under"], camera_eye=camera["mEye"], camera_center=camera["mCenter"]))
    try:
        report["live_speed_ulp_error"] = validate_drop_replay(native["frames"][:-1], expected)
    except RuntimeError as exc:
        report["native_replay_mismatch"] = str(exc)
    try:
        model_pose_verified, retention_frames = validate_live_object_outcome(
            family, records, probe, projected)
    except RuntimeError as exc:
        report["live_rejection"] = str(exc)
        (output / "last_candidate_check.json").write_text(
            json.dumps(report, indent=2), encoding="ascii")
        raise
    report["model_pose_verified"] = model_pose_verified
    (output / "last_candidate_check.json").write_text(json.dumps(report, indent=2), encoding="ascii")
    if not model_pose_verified or report.get("native_replay_mismatch"):
        log("Dolphin crossed and retained the seam, but native prediction differed; "
            "exporting the live-proven inputs and recording the discrepancy.")
    consume = records[family.dispatch_row + 1]
    if model_pose_verified:
        log("Verified live approach, hand pose, Co push and first endpoint bit-for-bit; "
            "retained for %d frame(s)." % retention_frames)
    else:
        log("Verified live approach, first endpoint and retention for %d frame(s)."
            % retention_frames)
    return dict(live_verified=True, retention_verified=True, retention_frames=retention_frames,
                model_pose_verified=model_pose_verified,
                oob_landing_verified=bool(getattr(family.context, "require_oob", False)),
                pre_push_facing=records[family.dispatch_row]["facing"],
                push_frame_roll_facing=consume["facing"] if getattr(family.context, "roll_on_clip", False) else None,
                proof_scope="live first push and bounded follow-through",
                verification_report=str(output / "last_candidate_check.json"))
