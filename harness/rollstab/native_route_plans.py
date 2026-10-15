"""Coherent alternative routes for native replay, rather than isolated byte edits."""
import itertools
import math
import random

from tww_sim.land.plan_land import stick_for_bearing
from tww_sim.core.mathlib import main_stick_decode


def ground_start(seeds, start):
    for index in range(start, len(seeds)):
        if seeds[index]["proc"] in (4, 6, 7, 24):
            return index
    return start


def actor_push_prefix_end(trace):
    """Keep recorded actor contact intact until the native scene can replace it."""
    frames = trace.get("trace", ())
    first_cut = min((frame["row"] for frame in frames
                     if 65 <= int(frame.get("after", {}).get("state", -1)) <= 69
                     and not 65 <= int(frame.get("before", {}).get("state", -1)) <= 69), default=len(frames))
    # Co moves are read during posMove, before the wall pass. Reusing recorded
    # pushes with changed movement would not simulate the contacted actor.
    return max((int(frame["row"]) + 1 for frame in frames if frame["row"] < first_cut
                and any(frame.get("before", {}).get("cc_move", ()))), default=0)


def replan_dispatches(trace, mode):
    seeds = trace["native"]["seeds"]
    # First-person exit precedes the recorded jump. Plan from its landing,
    # without assuming a particular room, hop duration or slash timing.
    air = [i for i, seed in enumerate(seeds) if seed["proc"] in (10, 11, 30)]
    ready = ground_start(seeds, max(air, default=0) + 1)
    ready = max(ready, actor_push_prefix_end(trace))
    offsets = (1, 2, 3, 4, 5, 6, 7, 8, 11, 15, 20) if mode == "walking" else (6, 9, 12, 16, 24, 36)
    dispatches = [ready + offset for offset in offsets]
    cuts = [int(frame["row"]) for frame in trace.get("trace", ())
            if 65 <= int(frame.get("after", {}).get("state", -1)) <= 69
            and not 65 <= int(frame.get("before", {}).get("state", -1)) <= 69]
    if cuts:
        for offset in (0, -1, 1, -2, 2, -3, 3):
            row = cuts[0] + offset
            if row > ready and row not in dispatches:
                dispatches.append(row)
        dispatches.sort(key=lambda row: (abs(row - cuts[0]), row))
    return tuple(dispatches)


def roll_button_row(family, controls):
    _, delay = route_recipe(family, controls)
    if delay is not None:
        rolls = recorded_roll_rows(family)
        if rolls:
            return rolls[-1] + delay
    lead = max(1, min(20, int(controls[-1]))) if getattr(family, "roll_axis", False) else 16
    return max(getattr(family, "walk_row", family.variable_start), family.button_row - lead)


def route_recipe(family, controls):
    code = int(controls[len(family.control_rows) * 4]) if getattr(family, "recipe_axis", False) else 1
    delays = (None, 0, 1, 2, 3, -1, -2)
    return code % 4, delays[(code // 4) % len(delays)] if getattr(family, "route_recipes", False) else None


def recorded_roll_rows(family):
    presses = [i for i, row in enumerate(family.base_rows) if row.get("buttons", 0) & 0x100
               and (not i or not family.base_rows[i - 1].get("buttons", 0) & 0x100)]
    launches = [i - 1 - family.input_delay for i in range(1, len(family.seeds))
                if family.seeds[i]["proc"] == 30 and family.seeds[i - 1]["proc"] != 30]
    return tuple(i for i in presses if any(abs(i - launch) <= 1 for launch in launches))


def recorded_starts(family, limit, seed, controls=None):
    """Keep the manual route; vary only its landing, approach speed and camera."""
    if limit <= 0 or not getattr(family, "route_recipes", False):
        return
    rolls = recorded_roll_rows(family)
    if not rolls and not any(state["proc"] == 30 for state in family.seeds):
        return
    if family.mode == "rolling":
        dispatch = family.button_row + family.input_delay
        editable_launch = any(family.control_rows[0] <= row < family.button_row for row in rolls)
        active_roll = dispatch < len(family.seeds) and family.seeds[dispatch]["proc"] == 30
        if not editable_launch and not active_roll:
            # A fixed, already-finished roll cannot become a rolling slash by
            # changing post-roll walking. Leave these trials to walking mode.
            return
    controls = family.controls_from_rows() if controls is None else controls
    values = list(controls)
    recipe_axis = len(family.control_rows) * 4
    values[recipe_axis] = 4  # Inherit A/L and triggers; retime only the final slash.
    seen = {tuple(values)}
    yield tuple(values)
    count = 1
    if count >= limit:
        return
    # Try launch delays before spending the budget on analog profiles.
    if rolls and family.control_rows[0] <= rolls[-1] < family.button_row:
        for code in (8, 12, 16, 20, 24):
            trial = list(values)
            trial[recipe_axis] = code
            if family.control_rows[0] <= roll_button_row(family, trial) < family.button_row:
                seen.add(tuple(trial))
                yield tuple(trial)
                count += 1
                if count >= limit:
                    return
    last_roll = max(i for i, state in enumerate(family.seeds) if state["proc"] == 30)
    walk = max(family.control_rows[0], ground_start(family.seeds, last_roll + 1) - family.input_delay)
    end = min(family.button_row, family.control_rows[-1] + 1)
    offsets = {row: offset * 4 for offset, row in enumerate(family.control_rows)}
    profiles = list(itertools.product((1.0, 0.95, 0.85, 0.65, 0.4, 0.2),
                                     (0, -64, 64, -256, 256), (1, 2, 3), ("early", "late")))
    rng = random.Random(seed)
    rng.shuffle(profiles)
    # First preserve full speed and check tiny landing-stick changes.
    profiles = [(magnitude, turn, duration, "early")
                for turn in (0, -64, 64, -256, 256) for duration in (1, 2, 3)
                for magnitude in (1.0, 0.95, 0.65, 0.2)] + profiles
    for profile_index, (magnitude, turn, duration, placement) in enumerate(profiles):
        start = walk if placement == "early" else max(walk, end - duration)
        stop = min(end, start + duration)
        if start >= stop:
            continue
        trial = list(values)
        for row in range(start, stop):
            if row not in offsets:
                continue
            offset = offsets[row]
            angle, distance = main_stick_decode(*controls[offset:offset + 2])
            if angle is not None:
                trial[offset:offset + 2] = stick_for_bearing(
                    (angle + 32768 + turn) & 65535, 0, min(distance, magnitude))
        # Camera yaw needs to clear the dead zone; one-byte changes to a centered
        # C-stick do nothing. Also include genuinely small active-camera edits.
        camera_row = offsets.get(start)
        variants = [tuple(trial)]
        if camera_row is not None:
            delta = (-1, 1, -16, 16, -24, 24)[profile_index % 6]
            moved = list(trial)
            moved[camera_row + 2] = max(0, min(255, moved[camera_row + 2] + delta))
            variants.append(tuple(moved))
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                yield variant
                count += 1
                if count >= limit:
                    return


def pre_roll_starts(family, controls, profile_offset=0):
    """Position slowly, then accelerate before the authored A press.

    These are proposals, not speed guarantees; native replay still decides
    whether the roll launches, reaches the seam and survives collision.
    """
    if family.mode != "rolling":
        return
    if family.start_seed.get("proc") == 30:
        ready = ground_start(family.seeds, family.variable_start)
        if ready >= len(family.seeds) or family.seeds[ready]["proc"] not in (4, 6, 7, 24):
            return
    roll = roll_button_row(family, controls)
    offsets = {row: offset * 4 for offset, row in enumerate(family.control_rows)}
    walk = getattr(family, "walk_row", family.control_rows[0])
    if roll not in offsets or roll >= family.button_row:
        return
    seen = {controls}
    profiles = list(itertools.product((1, 2, 4), (6, 4, 2), (0.12, 0.24, 0.4, 0.6),
                                     ("early", "late")))
    pivot = profile_offset % len(profiles)
    for duration, ramp, magnitude, placement in profiles[pivot:] + profiles[:pivot]:
        # Also position immediately after landing, before the approach can
        # contact another wall and erase a later sub-unit adjustment.
        stop = min(walk + duration, roll - ramp) if placement == "early" else roll - ramp
        start = walk if placement == "early" else max(walk, stop - duration)
        slow = [row for row in family.control_rows if start <= row < stop]
        if not slow:
            continue
        values = list(controls)
        for row in family.control_rows:
            if not start <= row <= roll:
                continue
            offset = offsets[row]
            angle, distance = main_stick_decode(*controls[offset:offset + 2])
            if angle is None:
                break
            if row < stop or distance < 1.0:
                values[offset:offset + 2] = stick_for_bearing(
                    (angle + 32768) & 65535, 0, magnitude if row < stop else 1.0)
        else:
            # Adjacent bytes at low magnitude yield much finer position changes
            # than perturbing a saturated full-stick approach.
            last = offsets[slow[-1]]
            for axis, delta in ((0, 0), (0, -1), (0, 1), (1, -1), (1, 1)):
                trial = list(values)
                trial[last + axis] = max(0, min(255, trial[last + axis] + delta))
                trial = tuple(trial)
                if trial not in seen:
                    seen.add(trial)
                    yield trial


def route_starts(family, limit, seed):
    if family.mode != "rolling":
        yield from _approach_starts(family, limit, seed)
        return
    seen = set()
    for index, controls in enumerate(_approach_starts(family, limit, seed)):
        # Reserve three quarters of the starts for existing broad approaches.
        # Slow windows must not crowd out their wider angle/camera coverage.
        jitter = (index // 3) % 5
        variants = (itertools.islice(pre_roll_starts(family, controls, index * 7), jitter, jitter + 1)
                    if index % 3 == 0 else ())
        for trial in itertools.chain((controls,), variants):
            if trial not in seen:
                seen.add(trial)
                yield trial
                if len(seen) >= limit:
                    return


def _approach_starts(family, limit, seed):
    if limit <= 0:
        return
    rolls = (tuple(row for row in recorded_roll_rows(family) if row < family.button_row)
             if family.mode == "walking" else ())
    preserve_roll = bool(rolls)
    ready = ground_start(family.seeds, family.variable_start)
    if preserve_roll:
        roll_frames = [i for i in range(family.variable_start,
                                        min(family.dispatch_row + 1, len(family.seeds)))
                       if family.seeds[i]["proc"] == 30]
        if roll_frames:
            ready = ground_start(family.seeds, roll_frames[-1] + 1)
    walk = max(family.control_rows[0], ready - family.input_delay)
    start = family.seeds[min(ready, len(family.seeds) - 1)]
    dx, dz = family.seam.S[0] - start["pos"][0], family.seam.S[1] - start["pos"][2]
    bearing = round(math.atan2(dx, dz) * 32768 / math.pi) & 65535
    camera = start["camera"]
    # Hold camera pulses through the first approach segment, including on ground.
    cameras = ((128, 89), (174, 128), (210, 128), (255, 128),
               (82, 128), (46, 128), (0, 128), (174, 89), (82, 89))
    offsets = (0, -1024, 1024, -4096, 4096, -8192, 8192, 16384, 32768)
    plans = list(itertools.product(cameras, offsets, (0, -2048, 2048, -4096, 4096, -8192, 8192),
                                   (2, 4, 8), (0.65, 0.85, 1.0)))
    random.Random(seed).shuffle(plans)
    # Spend the first trials on direct and modest curved approaches, then widen.
    direct = ((cam, turn, bend, split, 1.0)
              for turn, bend, split, cam in itertools.product(
                  (0, -512, 512), (0, -1024, 1024), (2, 4), cameras[:5]))
    ordered = itertools.chain(direct, plans)
    seen = set()
    count = 0
    for cam, turn, bend, split, magnitude in ordered:
        rows = [dict(row) for row in family.base_rows]
        first = stick_for_bearing((bearing + turn) & 65535, camera, magnitude)
        second = stick_for_bearing((bearing + bend) & 65535, camera, magnitude)
        for index in family.control_rows:
            row = rows[index]
            if index < walk:
                row["substickX"], row["substickY"] = cam
                if (preserve_roll and turn and index <= rolls[-1]
                        and index + family.input_delay < len(family.seeds)
                        and family.seeds[index + family.input_delay]["proc"] in (4, 6, 7, 24)):
                    angle, distance = main_stick_decode(row["stickX"], row["stickY"])
                    if angle is not None:
                        row["stickX"], row["stickY"] = stick_for_bearing(
                            (angle + 32768 + turn) & 65535, 0, distance)
            else:
                row["stickX"], row["stickY"] = first if index < walk + split else second
                row["substickX"], row["substickY"] = cam if index < walk + split else (128, 89)
        controls = family.controls_from_rows(rows)
        if getattr(family, "recipe_axis", False):
            controls = list(controls)
            controls[len(family.control_rows) * 4] = (
                4 if preserve_roll else (split + turn // 1024) % 4)
            controls = tuple(controls)
        if family.mode == "rolling":
            lead = (3, 6, 9, 12, 16, 20)[(split + turn // 1024) % 6]
            controls = (*controls[:-1], lead)
        if controls in seen:
            continue
        seen.add(controls)
        yield controls
        count += 1
        if count >= limit:
            return
