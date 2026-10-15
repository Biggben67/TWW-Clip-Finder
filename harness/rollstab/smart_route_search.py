"""Route-aware slash-clip search built from an exact live trace.

The recorded route is a seed, not a hard requirement.  A search first tests
small analog changes around the recorded slash.  If that slash family cannot
reach exact seam dust, it broadens the approach controls and adjacent buffered
B timings while retaining the captured animation, camera, collision, and input
history.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import copy
import json
import math
from pathlib import Path
import random
from typing import Callable

from harness.collision.offline_moving_drop import _make_seed, _step
from harness.rollstab.live_slash import _mesh_tris
from harness.rollstab.recorded_route import RecordedRoute, install_route_movie
from harness.rollstab.seamgeo import SeamGeo
from tww_sim.land.constants import ATN_MOVE, CUT_F, MOVE, WAIT


BUTTON_B = 0x0200
CUT_STATES = tuple(range(0x41, 0x46))
NEAR_SEAM_SEARCH_DISTANCE = 12.0


@dataclass(frozen=True)
class RouteResult:
    exact: bool
    phase: str
    dispatch_row: int
    button_row: int
    variable_start: int
    controls: tuple[int, ...]
    old: tuple[float, float]
    new: tuple[float, float]
    state: int
    facing: int
    travel: int
    speedf: float
    ray_error: float
    reach_error: float
    aim_error: int
    family_has_dust: bool = False
    collision_error: float = 0.0
    retention_error: float = 0.0

    @property
    def score(self) -> float:
        if self.exact:
            return -1000000.0
        action = 0.0 if self.state in CUT_STATES else 100000.0
        return (action + self.reach_error * 10.0 + self.ray_error
                + self.collision_error * 0.000001 + self.retention_error * 0.0000001)


def _signed_distance(a: int, b: int) -> int:
    return ((int(a) - int(b) + 0x8000) & 0xFFFF) - 0x8000


def _route(trace: dict) -> RecordedRoute:
    item = trace["route"]
    return RecordedRoute(
        movie=Path(item["movie"]),
        start_state=Path(item["start_state"]),
        start_vi=int(item["start_vi"]),
        end_vi=int(item["end_vi"]),
        controller=int(item["controller"]),
        rows=tuple(dict(row) for row in item["rows"]),
        poll_spans=tuple(tuple(map(int, span)) for span in item.get("poll_spans", ())),
    )


def find_dispatch_rows(trace: dict) -> tuple[int, ...]:
    """Return plausible CUT dispatch rows in deterministic priority order."""
    rows = trace["route"]["rows"]
    observed = [
        int(frame["row"]) for frame in trace.get("trace", ())
        if (int(frame["after"]["state"]) in CUT_STATES
            and int(frame["before"]["state"]) not in CUT_STATES)
    ]
    b_rows = []
    previous = 0
    for index, row in enumerate(rows):
        pressed = int(row.get("buttons", 0)) & BUTTON_B
        if pressed and not previous:
            b_rows.append(index)
        previous = pressed
    proposed = observed + [index + 2 for index in b_rows]
    if observed:
        proposed.extend((observed[0] - 1, observed[0] + 1, observed[0] + 2))
    valid = []
    for index in proposed:
        if 4 <= index < len(rows) and index not in valid:
            valid.append(index)
    if not valid:
        raise RuntimeError("the captured route contains no slash or buffered B edge")
    return tuple(valid)


class RouteFamily:
    def __init__(self, trace: dict, dispatch_row: int, window: int = 10,
                 from_start: bool = False):
        self.trace = trace
        self.route = _route(trace)
        self.dispatch_row = int(dispatch_row)
        self.button_row = max(0, self.dispatch_row - 2)
        seeds = trace.get("seeds", ())
        supported = (MOVE, ATN_MOVE)
        before = min(self.dispatch_row - 1, len(seeds) - 1)
        if before < 0:
            raise RuntimeError("the captured route has no state before the slash")
        # A synthetic later slash must still validate from the last captured
        # pre-slash MOVE frame, not against the captured CUT frame occupying
        # its new dispatch slot.
        captured_move_rows = [
            int(frame["row"]) for frame in trace.get("trace", ())
            if int(frame["after"]["state"]) in supported and int(frame["row"]) <= before
        ]
        validation_before = max(captured_move_rows) if captured_move_rows else before
        walls = _mesh_tris(trace["wall_mesh"])
        floors = _mesh_tris(trace["floor_mesh"])
        candidates = [
            index for index in range(
                max(0, validation_before - max(4, int(window))), validation_before + 1
            )
            if int(seeds[index]["snapshot"]["state"]) in supported
        ]
        if not candidates:
            raise RuntimeError("no MOVE/ATN_MOVE simulation anchor precedes the slash")

        # A captured LandState does not contain every private field for every
        # action.  Select the earliest anchor whose unchanged replay actually
        # reproduces the captured pre-slash position.  This preserves the most
        # editable frames without silently searching from a drifting model.
        target_frame = next(
            (frame for frame in trace.get("trace", ())
             if int(frame["row"]) == validation_before),
            None,
        )
        target = (target_frame["after"] if target_frame
                  else seeds[validation_before]["snapshot"])
        anchor = -1
        anchor_error = float("inf")
        anchor_state = None
        for candidate in candidates:
            candidate_seed = dict(seeds[candidate])
            if (candidate > 0
                    and int(candidate_seed["snapshot"]["state"]) == MOVE
                    and int(seeds[candidate - 1]["snapshot"]["state"]) == 30):
                candidate_seed["seed_kind"] = "move_reentry_anchor"
            node = _make_seed(candidate_seed, walls, floors, force_state=None, model_draw=False)
            for index in range(candidate + 1, validation_before + 1):
                node = _step(node, self.route.rows[index])
            error = math.hypot(
                float(node.state.pos_x) - float(target["x"]),
                float(node.state.pos_z) - float(target["z"]),
            )
            state_matches = int(node.state.state) == int(target["state"])
            if state_matches and error < anchor_error:
                anchor, anchor_error, anchor_state = candidate, error, node
            if state_matches and error <= 0.002:
                anchor, anchor_error, anchor_state = candidate, error, node
                break
        if anchor < 0 or anchor_error > 0.01:
            raise RuntimeError(
                f"no trustworthy simulation anchor (best pre-slash drift {anchor_error:.6f})"
            )
        self.anchor_row = anchor
        self.anchor_error = anchor_error
        self.position_offset = (0.0, 0.0)
        self.variable_start = anchor + 1
        self.pending_control_rows = tuple(range(max(0, anchor - 1), anchor + 1))
        queued = range(max(0, anchor - 1), max(0, self.dispatch_row - 2))
        self.control_rows = tuple(dict.fromkeys((*queued, self.dispatch_row)))
        if self.anchor_row >= len(seeds):
            raise RuntimeError("the captured route does not contain a pre-slash simulation seed")
        seed = dict(seeds[self.anchor_row])
        if (self.anchor_row > 0
                and int(seed["snapshot"]["state"]) == MOVE
                and int(seeds[self.anchor_row - 1]["snapshot"]["state"]) == 30):
            seed["seed_kind"] = "move_reentry_anchor"
        self.start = _make_seed(seed, walls, floors, force_state=None, model_draw=False)
        camera = int(seeds[self.anchor_row]["snapshot"]["camera"])
        self.seam = SeamGeo(trace["geo"], camera)
        self.base_rows = [dict(row) for row in self.route.rows]

    @property
    def axes(self) -> tuple[int, ...]:
        return tuple(range(len(self.control_rows) * 3))

    def controls_from_rows(self, rows=None) -> tuple[int, ...]:
        rows = self.base_rows if rows is None else rows
        values = []
        for index in self.control_rows:
            values.extend((
                int(rows[index]["stickX"]), int(rows[index]["stickY"]),
                int(rows[index].get("substickX", 128)),
            ))
        return tuple(values)

    def rows_from_controls(self, controls, synthesize_buttons: bool) -> list[dict]:
        rows = [dict(row) for row in self.base_rows]
        for offset, index in enumerate(self.control_rows):
            base = offset * 3
            rows[index]["stickX"] = int(controls[base])
            rows[index]["stickY"] = int(controls[base + 1])
            rows[index]["substickX"] = int(controls[base + 2])
        if synthesize_buttons:
            for index in range(max(0, self.button_row - 2), self.dispatch_row):
                rows[index]["buttons"] = int(rows[index].get("buttons", 0)) & ~BUTTON_B
            rows[self.button_row]["buttons"] |= BUTTON_B
        return rows

    def evaluate(self, controls, phase="route refinement", synthesize_buttons=False):
        rows = self.rows_from_controls(controls, synthesize_buttons)
        node = copy.copy(self.start)
        node.state = self.start.state.clone()
        # The anchor is a post-frame snapshot. Its pending controller queue is
        # therefore the two raw rows immediately ending at anchor_row. Update
        # that queue alongside the exported DTM rows so simulation and playback
        # optimize the same inputs.
        pending = list(node.state._inbuf)
        for offset, index in enumerate(self.pending_control_rows[-len(pending):]):
            item = list(pending[offset])
            item[0] = int(rows[index]["stickX"])
            item[1] = int(rows[index]["stickY"])
            item[4] = int(rows[index].get("substickX", 128))
            pending[offset] = tuple(item)
        node.state._inbuf = pending
        for index in range(self.variable_start, self.dispatch_row):
            node = _step(node, rows[index])
        state = node.state
        raw_old = (state.pos_x, state.pos_z)
        source_state = int(state.state)
        source_facing = int(state.facing)
        dispatch = rows[self.dispatch_row]
        state.enter_cut_from_move(
            dispatch["stickX"], dispatch["stickY"],
            csx=dispatch.get("substickX", 128), csy=dispatch.get("substickY", 128),
        )
        raw_new = (state.pos_x, state.pos_z)
        old = (raw_old[0] + self.position_offset[0],
               raw_old[1] + self.position_offset[1])
        new = (raw_new[0] + self.position_offset[0],
               raw_new[1] + self.position_offset[1])
        dx, dz = new[0] - old[0], new[1] - old[1]
        length = math.hypot(dx, dz) or 1.0
        sx, sz = self.seam.S
        along = ((sx - old[0]) * dx + (sz - old[1]) * dz) / length
        reach = max(0.0, -along) + max(0.0, along - length)
        ray = abs(self.seam.perp_to_ray(old, new))
        aim_error = abs(_signed_distance(state.target, source_facing))
        # This family starts from a captured route that demonstrably dispatched
        # a slash. ``target`` can be stale during the untargeted MOVE transition
        # and is not an additional legality gate for the captured B edge.
        valid = source_state in (MOVE, ATN_MOVE)
        exact = bool(valid and reach == 0.0 and self.seam.genuine_clip(old, new))
        return RouteResult(
            exact=exact, phase=phase, dispatch_row=self.dispatch_row,
            button_row=self.button_row, variable_start=self.variable_start,
            controls=tuple(int(value) for value in controls), old=old, new=new,
            state=int(state.state), facing=int(state.facing), travel=int(state.travel),
            speedf=float(state.speedF), ray_error=ray, reach_error=reach,
            aim_error=aim_error,
        )

    def family_has_dust(self, result: RouteResult) -> bool:
        dx, dz = result.new[0] - result.old[0], result.new[1] - result.old[1]
        length = math.hypot(dx, dz)
        if length <= 0.0:
            return False
        ux, uz = dx / length, dz / length
        px, pz = -uz, ux
        # This is a feasibility check, not candidate acceptance. Candidate
        # acceptance always uses the exact old/new state produced by replay.
        along = 0.0
        while along <= length + 0.001:
            for perp_i in range(-20, 21):
                perp = perp_i * 0.00005
                old = (sx := self.seam.S[0] - along * ux + perp * px,
                       sz := self.seam.S[1] - along * uz + perp * pz)
                new = (sx + dx, sz + dz)
                if self.seam.genuine_clip(old, new):
                    return True
            along += 0.05
        return False

    def export(self, result: RouteResult, output: str | Path) -> Path:
        rows = self.rows_from_controls(
            result.controls, synthesize_buttons=result.phase == "route synthesis"
        )
        return install_route_movie(self.route, rows, output, short=False)


def _mutations(parent, axes, radius, rng, random_count, broad=False):
    yield parent
    if not axes:
        return
    for axis in axes:
        for delta in (-radius, radius):
            trial = list(parent)
            trial[axis] = max(0, min(255, trial[axis] + delta))
            yield tuple(trial)
    for _ in range(random_count):
        trial = list(parent)
        count = rng.randint(1, min(6 if broad else 3, len(axes)))
        for axis in rng.sample(axes, count):
            if broad and rng.random() < 0.2:
                trial[axis] = rng.randint(0, 255)
            else:
                trial[axis] = max(0, min(255, trial[axis] + rng.randint(-radius, radius)))
        yield tuple(trial)


def _result_rank(family, result):
    return family.result_rank(result) if hasattr(family, "result_rank") else (result.score,)


def _preferred_exact(family, result):
    return (family.preferred_exact(result) if hasattr(family, "preferred_exact")
            else result.exact)


def _beam_search(family: RouteFamily, initial, *, cap: int, seed: int,
                 phase: str, broad: bool, log: Callable[[str], None], cancelled,
                 initial_result=None, near_restart=False, seed_results=()):
    rng = random.Random(seed)
    evaluator = lambda controls: family.evaluate(
        controls, phase=phase, synthesize_buttons=broad
    )
    first = initial_result if initial_result is not None else evaluator(initial)
    best = first
    cache = {tuple(initial): first}
    beam = [tuple(initial)]
    evaluations = 1
    if near_restart and hasattr(family, "precision_seeds"):
        cache.update((item.controls, item) for item in seed_results)
        beam = [item.controls for item in family.precision_seeds(cache.values())] or beam
    if _preferred_exact(family, first) or evaluations >= cap:
        return first, evaluations
    if not family.axes:
        log(
            f"{phase}: dispatch {family.dispatch_row} has no editable analog rows; "
            "evaluated once and continued."
        )
        return first, evaluations
    starts_factory = (None if near_restart else
                      getattr(family, "route_starts" if broad else "local_starts", None))
    if starts_factory:
        starts = list(dict.fromkeys(starts_factory(min(256 if broad else 96, (cap - evaluations) // 6), seed)))
        starts = [item for item in starts if item not in cache]
        steered = []
        for controls, result in zip(starts, family.evaluate_many(
                starts, phase=phase, synthesize_buttons=broad)):
            evaluations += 1
            cache[controls] = result
            if _result_rank(family, result) < _result_rank(family, best):
                best = result
            if _preferred_exact(family, result):
                return result, evaluations
            if broad and hasattr(family, "reaim_controls"):
                steered.append(family.reaim_controls(controls))
        steered = [item for item in dict.fromkeys(steered) if item not in cache]
        for controls, result in zip(steered, family.evaluate_many(
                steered, phase=phase, synthesize_buttons=broad)):
            evaluations += 1
            cache[controls] = result
            if _result_rank(family, result) < _result_rank(family, best):
                best = result
            if _preferred_exact(family, result):
                return result, evaluations
        ordered = (family.beam_order(cache.values(), 72) if hasattr(family, "beam_order")
                   else sorted(cache.values(), key=lambda item: _result_rank(family, item)))
        beam = [item.controls for item in ordered[:72]]
        log(f"{phase}: dispatch {family.dispatch_row}, tested {len(starts)} camera/approach plans "
            f"and {len(steered)} camera-steered variants")
        if (hasattr(family, "screen_promising")
                and not family.screen_promising(cache.values())):
            distance = getattr(family, "screen_distance", math.inf)
            log(f"{phase}: dispatch {family.dispatch_row} skipped heavy refinement after "
                f"{evaluations} probes; closest slash was {distance:.3f} units from the seam.")
            return best, evaluations
    radii = ((64, 32, 16, 8, 4, 2, 1) if near_restart else
             ((128, 96, 64, 48, 32, 16, 8, 4, 2, 1)
              if broad else (24, 12, 6, 3, 2, 1, 1)))
    analog_cap = cap - cap // 4 if hasattr(family, "polish") else cap
    proximity = getattr(family, "search_proximity", None)
    exploratory_cap = analog_cap
    if proximity and proximity(cache.values()) > NEAR_SEAM_SEARCH_DISTANCE:
        exploratory_cap = min(analog_cap, evaluations + 4096)
    for generation, radius in enumerate(radii, 1):
        if cancelled():
            raise RuntimeError("search cancelled")
        candidates = set()
        for parent in beam:
            candidates.update(_mutations(
                parent, family.axes, radius, rng,
                random_count=800 if broad and generation == 1 else 80,
                broad=broad,
            ))
            if len(candidates) >= (5000 if broad else 1800):
                break
        unseen = sorted(item for item in candidates if item not in cache)
        # Reserve trials for every finer radius. Sampling avoids truncation bias
        # toward early rows/axes and makes the seed reproducible across runs.
        generation_cap = max(0, (exploratory_cap - evaluations) // (len(radii) - generation + 1))
        if len(unseen) > generation_cap:
            unseen = rng.sample(unseen, generation_cap)
        results = (family.evaluate_many(unseen, phase=phase, synthesize_buttons=broad)
                   if hasattr(family, "evaluate_many") else map(evaluator, unseen))
        for batch_index, (controls, result) in enumerate(zip(unseen, results), 1):
            cache[controls] = result
            if _result_rank(family, result) < _result_rank(family, best):
                best = result
            if _preferred_exact(family, result):
                return result, evaluations + batch_index
        evaluations += len(unseen)
        ranked = (family.beam_order(cache.values(), 128 if broad else 72)
                  if hasattr(family, "beam_order") else
                  sorted(cache.values(), key=lambda item: _result_rank(family, item)))
        if near_restart and hasattr(family, "precision_seeds"):
            precise = family.precision_seeds(cache.values())
            precise_controls = {item.controls for item in precise}
            ranked = precise + [item for item in ranked if item.controls not in precise_controls]
        seen = set()
        beam = []
        for result in ranked:
            signature = (
                round(result.old[0], 6), round(result.old[1], 6),
                result.facing, result.travel, round(result.speedf, 6),
            )
            if signature in seen:
                continue
            seen.add(signature)
            beam.append(result.controls)
            if len(beam) >= (128 if broad else 72):
                break
        log(
            f"{phase}: dispatch {family.dispatch_row}, radius {radius}, "
            f"evaluations {evaluations}, ray {best.ray_error:.9f}, "
            f"reach {best.reach_error:.6f}, wall correction {best.collision_error:.6f}, "
            f"rebound {best.retention_error:.6f}, exact={best.exact}"
        )
        if proximity and exploratory_cap < analog_cap:
            if proximity(cache.values()) <= NEAR_SEAM_SEARCH_DISTANCE:
                exploratory_cap = analog_cap
        if evaluations >= exploratory_cap:
            break
    if exploratory_cap < analog_cap:
        log(f"{phase}: dispatch {family.dispatch_row} deferred after {evaluations} probes; "
            "the slash segment did not approach the seam. Trying other timings/routes.")
    if hasattr(family, "precision_seeds"):
        family.precision_candidates = family.precision_seeds(cache.values())
    if hasattr(family, "polish") and evaluations < cap:
        candidate, count = family.polish(
                                        getattr(family, "precision_candidates", list(cache.values())),
                                        cap - evaluations,
                                        phase, broad, log)
        evaluations += count
        if candidate is not None and hasattr(family, "precision_seeds"):
            family.precision_candidates = family.precision_seeds(
                [*family.precision_candidates, candidate])
        if candidate is not None and _result_rank(family, candidate) < _result_rank(family, best):
            best = candidate
    return best, evaluations


def search_trace(trace: dict, output_dir: str | Path, *, evaluation_cap=30000,
                 random_seed=615507812, log=print, cancelled=lambda: False,
                 family_factory=RouteFamily, dispatch_factory=find_dispatch_rows,
                 strict_budget=False, synthesis_dispatch_factory=None,
                 final_refinement=False) -> dict:
    """Refine the recorded route, then synthesize a nearby route if necessary."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dispatches = dispatch_factory(trace)
    cap = max(1 if strict_budget else 1000, int(evaluation_cap))
    plan_cap = cap - cap // 4 if strict_budget and final_refinement else cap
    local_cap = max(1 if strict_budget else 500, plan_cap // (len(dispatches) * 3))
    broad_cap = max(1 if strict_budget else 1000, plan_cap // max(1, len(dispatches)))
    best = None
    best_family = None
    evaluated = 0
    frontier = []

    for dispatch in dispatches:
        if strict_budget and evaluated >= plan_cap:
            break
        try:
            family = family_factory(trace, dispatch)
            initial = family.controls_from_rows()
            baseline = family.evaluate(initial)
            has_dust = family.family_has_dust(baseline)
            baseline = replace(baseline, family_has_dust=has_dust)
            log(
                f"Recorded route dispatch {dispatch}: action={baseline.state}, "
                f"ray={baseline.ray_error:.9f}, reach={baseline.reach_error:.6f}, "
                f"{getattr(family, 'feasibility_label', 'exact dust family')}={'yes' if has_dust else 'no'}."
            )
            if (not baseline.exact and hasattr(family, "refinement_possible")
                    and not family.refinement_possible()):
                evaluated += 1
                if best is None or _result_rank(family, baseline) < _result_rank(best_family, best):
                    best, best_family = baseline, family
                log("Recorded controls cannot launch the requested action; reserving trials for replanning.")
                continue
            candidate, count = _beam_search(
                family, initial, cap=min(local_cap, plan_cap - evaluated) if strict_budget else local_cap,
                seed=random_seed + dispatch, initial_result=baseline,
                phase="route refinement", broad=False, log=log, cancelled=cancelled,
            )
            evaluated += count
            frontier.append((candidate, family))
            if best is None or _result_rank(family, candidate) < _result_rank(best_family, best):
                best, best_family = candidate, family
            if _preferred_exact(family, candidate):
                break
        except Exception as exc:
            if str(exc) == "search cancelled" or getattr(exc, "fatal_search", False):
                raise
            log(f"Skipped local dispatch {dispatch}: {exc}")

    if best is None or not _preferred_exact(best_family, best):
        log("No preferred exact local result. Testing alternative approaches, camera paths and slash timings.")
        synthesis_dispatches = (synthesis_dispatch_factory(trace)
                               if synthesis_dispatch_factory else dispatches)
        for dispatch_index, dispatch in enumerate(synthesis_dispatches):
            if strict_budget and evaluated >= plan_cap:
                break
            try:
                family = family_factory(trace, dispatch, from_start=True)
                initial = family.controls_from_rows()
                candidate, count = _beam_search(
                    family, initial, cap=max(1, (plan_cap - evaluated) // (len(synthesis_dispatches) - dispatch_index))
                    if strict_budget else broad_cap,
                    seed=random_seed ^ (dispatch << 8),
                    phase="route synthesis", broad=True, log=log, cancelled=cancelled,
                )
                evaluated += count
                frontier.append((candidate, family))
                if best is None or _result_rank(family, candidate) < _result_rank(best_family, best):
                    best, best_family = candidate, family
                if _preferred_exact(family, candidate):
                    break
            except Exception as exc:
                if str(exc) == "search cancelled" or getattr(exc, "fatal_search", False):
                    raise
                log(f"Skipped synthesized dispatch {dispatch}: {exc}")

    if best is None:
        raise RuntimeError("no searchable slash family was found in the captured route")
    if final_refinement and not best.exact and evaluated < cap:
        choices, seen, seen_families = [], set(), set()
        refinements = [(best, best_family), *frontier]
        refinements.extend((family.precision_candidates[0], family)
                           for _, family in frontier
                           if getattr(family, "precision_candidates", None))
        def refinement_order(pair):
            item, family = pair
            if item.state in CUT_STATES and item.reach_error == 0:
                return (0, item.aim_error, item.ray_error, item.score)
            return (1, *(_result_rank(family, item)))
        for item, family in sorted(refinements, key=refinement_order):
            signature = (item.old, item.new, item.facing, item.travel)
            if (signature not in seen and id(family) not in seen_families
                    and hasattr(family, "polish")):
                choices.append((item, family))
                seen.add(signature)
                seen_families.add(id(family))
            if len(choices) == 4:
                break
        for index, (item, family) in enumerate(choices):
            if evaluated >= cap or best.exact:
                break
            budget = max(1, (cap - evaluated) // (len(choices) - index))
            log("Refining a distinct %s route at dispatch %d with up to %d trials."
                % (getattr(family, "mode", "slash"), item.dispatch_row, budget))
            seeds = getattr(family, "precision_candidates", ())
            candidate, count = family.polish([item, *seeds], budget, item.phase,
                                            item.phase == "route synthesis", log)
            evaluated += count
            if candidate is not None and _result_rank(family, candidate) < _result_rank(best_family, best):
                best, best_family = candidate, family
            current = candidate if candidate is not None and _result_rank(family, candidate) < _result_rank(family, item) else item
            stale = 0
            for retry in range(8):
                remaining = min(budget - count, cap - evaluated)
                if current.exact or not hasattr(family, "restart_near") or remaining < 1000 or stale >= 2:
                    break
                trial, used = family.restart_near(
                    current, min(12000, remaining),
                    random_seed ^ (item.dispatch_row << 8) ^ (retry << 16), log, cancelled,
                )
                count += used
                evaluated += used
                if used == 0:
                    break
                precision = getattr(family, "precision_candidates", ())
                if not trial.exact and precision and hasattr(family, "search_proximity"):
                    near = precision[0]
                    if family.search_proximity((near,)) < family.search_proximity((trial,)):
                        trial = near
                if _result_rank(family, trial) < _result_rank(family, current):
                    current, stale = trial, 0
                    if _result_rank(family, trial) < _result_rank(best_family, best):
                        best, best_family = trial, family
                else:
                    improved_ray = (trial.state in CUT_STATES and trial.reach_error == 0
                                    and trial.ray_error < current.ray_error)
                    if improved_ray:
                        current, stale = trial, 0
                    else:
                        stale += 1
                log("Near-miss restart %d at dispatch %d: ray %.9f, wall correction %.6f, exact=%s"
                    % (retry + 1, item.dispatch_row, current.ray_error,
                       current.collision_error, current.exact))
    if (final_refinement and best.exact and not _preferred_exact(best_family, best)
            and evaluated < cap and hasattr(best_family, "restart_near")):
        log("Improving the exact clip speed while retaining the current result as fallback.")
        candidate, count = best_family.restart_near(
            best, min(12000, cap - evaluated), random_seed ^ 0x5EED, log, cancelled)
        evaluated += count
        if _result_rank(best_family, candidate) < _result_rank(best_family, best):
            best = candidate
    payload = asdict(best)
    if hasattr(best_family, "control_metadata"):
        payload.update(best_family.control_metadata())
    payload["score"] = best.score
    payload["evaluations"] = evaluated
    payload["dispatch_candidates"] = list(dispatches)
    if synthesis_dispatch_factory:
        payload["synthesis_dispatch_candidates"] = list(synthesis_dispatch_factory(trace))
    payload["movie"] = None
    if best.exact:
        movie = output_dir / "slash_clip_refined.dtm"
        payload["movie"] = str(best_family.export(best, movie))
        log(f"{getattr(best_family, 'export_label', 'Exact collision-proved route')} exported to {movie}")
    else:
        log(
            "Search exhausted without an exact clip; no DTM was exported. "
            f"Best ray error was {best.ray_error:.9f}; wall correction "
            f"{best.collision_error:.6f}, rebound {best.retention_error:.6f}."
        )
    result_path = output_dir / "smart_route_result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="ascii")
    payload["result_path"] = str(result_path)
    return payload
