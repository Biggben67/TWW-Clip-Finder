import copy
import math
from types import SimpleNamespace

import pytest

from harness.rollstab.native_route import approach_anchor_rows, decode_row, f32_equal, validate_replay


@pytest.mark.parametrize("from_start,validation_end", [(False, 14), (True, 13)])
def test_last_pre_dispatch_anchor_is_included(from_start, validation_end):
    trace = {"native": {"seeds": [{}] * 16}, "trace": []}
    anchors = approach_anchor_rows(trace, 11, validation_end, from_start)
    assert 10 in anchors
    assert 11 not in anchors


def test_native_pad_maps_gc_not_gba_buttons():
    row = decode_row({"stickX": 128, "stickY": 252, "buttons": 0x100 | 0x200 | 0x40})
    assert row["item_button"] == 1 | 2 | 32
    assert not row["target"]
    assert row["lock_l"] == 0
    assert row["hold"] & 0x200
    assert row["angle"] == 0
    assert row["distance"] == 1.0


def test_native_analog_target_and_neutral_decode():
    row = decode_row({"stickX": 128, "stickY": 128, "triggerL": 255})
    assert row["target"]
    assert row["distance"] == 0.0
    assert row["item_button"] == 32


def _expected():
    return {"state": 6, "x": 596.7720947265625, "y": 0.0, "z": -1378.4049072265625,
            "facing": 36256, "speed_f": 17.0}


def _actual():
    e = _expected()
    return {"state": e["state"], "pos": [e["x"], e["y"], e["z"]],
            "facing": e["facing"], "speed": e["speed_f"]}


def test_native_baseline_requires_bit_exact_float_not_tolerance():
    validate_replay([_actual()], [_expected()])
    altered = copy.deepcopy(_actual())
    altered["pos"][0] += 0.00006103515625
    assert not f32_equal(altered["pos"][0], _expected()["x"])
    with pytest.raises(RuntimeError, match="position diverged"):
        validate_replay([altered], [_expected()])


@pytest.mark.parametrize("field,value", [("state", 30), ("facing", 36257), ("speed", 16.999998)])
def test_native_baseline_rejects_wrong_action_or_speed(field, value):
    actual = _actual()
    actual[field] = value
    with pytest.raises(RuntimeError, match="diverged"):
        validate_replay([actual], [_expected()])


def test_native_baseline_rejects_missing_frame():
    with pytest.raises(RuntimeError, match="length differs"):
        validate_replay([], [_expected()])


def test_native_camera_obstruction_state_requires_bit_exact_view():
    expected, actual = _expected(), _actual()
    expected["camera_eye"] = actual["camera_eye"] = [600.0, 100.0, -1000.0]
    validate_replay([actual], [expected])
    actual["camera_eye"] = [600.0 + 2 ** -14, 100.0, -1000.0]
    with pytest.raises(RuntimeError, match="camera_eye diverged"):
        validate_replay([actual], [expected])


def test_stale_camera_actor_pointer_does_not_block_native_replay():
    import struct
    from harness.rollstab.native_route_capture import camera_actor_references

    ram = bytearray(0x340)
    struct.pack_into(">II", ram, 0x130, 0xFFFFFFFF, 0x80AA9A68)
    assert not any(camera_actor_references(ram).values())
    struct.pack_into(">I", ram, 0x130, 123)
    assert camera_actor_references(ram)["forced"]
    struct.pack_into(">I", ram, 0x130, 0xFFFFFFFF)
    struct.pack_into(">I", ram, 0x12C, 0x80AA9A68)
    assert camera_actor_references(ram)["lockon"]
    struct.pack_into(">I", ram, 0x12C, 0)
    struct.pack_into(">I", ram, 0x33C, 0x80AA9A68)
    assert camera_actor_references(ram)["bg_owner"]


def _native_family():
    from harness.rollstab.native_route import NativeFamily
    family = object.__new__(NativeFamily)
    plane = SimpleNamespace(func=lambda p: -p[0])
    family.seam = SimpleNamespace(S=(0.0, 0.0), wA=SimpleNamespace(pla=plane),
                                  wB=SimpleNamespace(pla=plane))
    family.mode = "walking"
    family.dispatch_row = 5
    family.anchor_row = 0
    family.variable_start = 1
    family.validation_end = 6
    family.start_seed = {"proc": 6}
    family.input_delay = 2
    family.base_rows = [dict(stickX=128, stickY=252, substickX=128,
                             substickY=100, buttons=0) for _ in range(6)]
    family.control_rows = (0, 1, 2)
    family.button_row = 3
    return family


def _grounded_crossing():
    return {"frames": [dict(before=6 if i == 0 else 68, state=68, facing=0, travel=0,
                            speed=17.0, old=[-1.0, 0.0, 0.0], raw=[1.0, -2.5, 0.0],
                            pos=[1.0, 0.0, 0.0], flags=0x20) for i in range(4)]}


def test_native_accepts_ground_height_correction_but_not_wall_correction():
    family = _native_family()
    replay = _grounded_crossing()
    assert family._result((), replay, "test").exact
    replay["frames"][0]["flags"] |= 0x10
    assert not family._result((), replay, "test").exact


@pytest.mark.parametrize("before", [6, 7, 24])
def test_native_accepts_valid_walking_slash_during_move_turn(before):
    replay = _grounded_crossing()
    replay["frames"][0]["before"] = before
    assert _native_family()._result((), replay, "test").exact


def test_native_move_turn_port_does_not_relax_rolling_acceptance():
    replay = _grounded_crossing()
    replay["frames"][0]["before"] = 24
    family = _native_family()
    family.mode = "rolling"
    assert not family._result((), replay, "test").exact


def test_native_rejects_one_ulp_horizontal_correction():
    replay = _grounded_crossing()
    replay["frames"][0]["pos"][0] += 2 ** -23
    assert not _native_family()._result((), replay, "test").exact


def test_native_near_seam_ranking_prefers_clean_retained_path_over_smaller_ray():
    from dataclasses import replace
    trapped = replace(_native_family()._result((), _grounded_crossing(), "test"),
                      exact=False, ray_error=0.000045, collision_error=42.95,
                      retention_error=35.0)
    clean = replace(trapped, ray_error=0.01, collision_error=0.0, retention_error=0.0)
    outside = replace(clean, ray_error=0.021)
    assert clean.score < outside.score < trapped.score


def test_native_near_seam_ranking_prioritizes_less_wall_correction():
    from dataclasses import replace
    broad = replace(_native_family()._result((), _grounded_crossing(), "test"),
                    exact=False, ray_error=0.004, collision_error=42.0,
                    retention_error=35.0)
    narrower = replace(broad, ray_error=0.003, collision_error=42.1)
    dust = replace(broad, ray_error=0.00001, collision_error=43.0)
    assert broad.score < narrower.score < dust.score
    assert replace(broad, ray_error=0.003).score < broad.score


def test_native_float32_dust_does_not_outrank_a_cleaner_route():
    from dataclasses import replace
    candidate = replace(_native_family()._result((), _grounded_crossing(), "test"),
                        exact=False, old=(604.0, -1467.0), new=(622.0, -1503.0),
                        collision_error=43.0, retention_error=35.0)
    dust = replace(candidate, ray_error=0.0001)
    outside = replace(candidate, ray_error=0.0003, collision_error=42.0)
    assert outside.score < dust.score


def test_native_beam_keeps_a_clean_approach_when_blocked_rays_dominate():
    from dataclasses import replace
    base = replace(_native_family()._result((), _grounded_crossing(), "test"), exact=False)
    blocked = [replace(base, controls=(index,), ray_error=index / 10000.,
                       collision_error=40., retention_error=35.,
                       old=(float(index), 0.)) for index in range(80)]
    clean = replace(base, controls=(99,), ray_error=20., collision_error=0.,
                    retention_error=0., old=(99., 0.))
    ordered = _native_family().beam_order([*blocked, clean], 72)
    assert clean in ordered[:72]
    assert clean.score > blocked[0].score


def test_native_replans_near_recorded_slash_before_early_timings():
    from harness.rollstab.native_route_plans import replan_dispatches
    trace = {"native": {"seeds": [{"proc": 6}] * 22},
             "trace": [{"row": 11, "before": {"state": 6}, "after": {"state": 66}}]}
    choices = replan_dispatches(trace, "walking")
    assert choices[:3] == (11, 10, 12)
    assert choices.index(11) < choices.index(2)


def test_native_rejects_clip_that_pops_back_out():
    replay = _grounded_crossing()
    replay["frames"][1]["pos"][0] = -1.0
    assert not _native_family()._result((), replay, "test").exact


def test_native_checks_later_slash_after_preparatory_slash():
    replay = _grounded_crossing()
    missed = dict(replay["frames"][0], pos=[-1.0, 0.0, 0.0], flags=0x10)
    recovery = dict(missed, before=68, state=6)
    replay["frames"] = [missed, recovery, *replay["frames"]]
    result = _native_family()._result((), replay, "test")
    assert result.exact and result.dispatch_row == 3
    assert result.button_row == 3  # Authored B row, not dispatch minus inferred delay.


def test_native_zero_displacement_is_not_a_perfect_ray():
    replay = _grounded_crossing()
    replay["frames"][0]["raw"] = [-1.0, 0.0, 0.0]
    result = _native_family()._result((), replay, "test")
    assert not result.exact
    assert result.ray_error == result.reach_error == 1.0


@pytest.mark.parametrize("recipe,frames", [(0, ()), (1, (2,)), (2, (1, 2)), (3, (1, 2))])
def test_native_target_recipes_include_analog_trigger_and_camera(recipe, frames):
    family = _native_family()
    family.recipe_axis = True
    family.walk_row = 2
    controls = (*family.controls_from_rows()[:-1], recipe)
    rows = family.rows_from_controls(controls, True)
    assert tuple(i for i, row in enumerate(rows) if row["buttons"] & 0x40) == frames
    for index in frames:
        assert rows[index]["triggerL"] == (255 if recipe == 3 else 0)
        assert rows[index]["substickY"] == (100 if recipe == 3 else 89)


@pytest.mark.parametrize("equipped", [True, False])
def test_rolling_route_does_not_slash_early_when_sword_is_already_drawn(equipped):
    family = _native_family()
    family.mode = "rolling"
    family.walk_row = 0
    family.button_row = 10
    family.base_rows *= 4
    family.control_rows = tuple(range(13))
    family.roll_axis = True
    family.recipe_axis = True
    family.start_seed = {"fields": {"mEquipItem": 0x103 if equipped else 0xFF}}
    controls = (*family.controls_from_rows()[:-1], 2)
    rows = family.rows_from_controls(controls, True)
    assert rows[8]["buttons"] & 0x100
    assert tuple(i for i, row in enumerate(rows) if row["buttons"] & 0x200) == ((10,) if equipped else (1, 10))


def test_native_skips_analog_only_roll_refinement_without_a_roll_press():
    family = _native_family()
    family.mode = "rolling"
    assert not family.refinement_possible()
    family.base_rows[1]["buttons"] = 0x100
    assert family.refinement_possible()


def test_active_roll_anchor_can_refine_without_another_a_press():
    family = _native_family()
    family.mode = "rolling"
    family.start_seed["proc"] = 30
    assert family.refinement_possible()


def test_local_slash_retiming_moves_b_but_preserves_other_buttons_and_pads():
    family = _native_family()
    family.base_rows *= 2
    family.base_rows[0]["buttons"] = 0x100 | 0x40
    family.base_rows[8]["buttons"] = 0x200
    rows = family.rows_from_controls(family.controls_from_rows(), retime_slash=True)
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x200] == list(range(3, 8))
    assert rows[0]["buttons"] == 0x100 | 0x40
    assert rows[8]["buttons"] == 0
    assert all((row["stickX"], row["substickY"]) == (128, 100) for row in rows)


def test_native_batch_reuses_identical_clamped_pads_without_losing_authored_inputs():
    family = _native_family()
    family.cancelled = lambda: False
    family.seeds = []
    family.start_seed = {}
    family.camera = 0
    submitted = []
    def replay(seed, rows, camera):
        submitted.append(len(rows))
        return [_grounded_crossing() for _ in rows]
    family.worker = SimpleNamespace(replay=replay)
    original = family.controls_from_rows()
    alternate = list(original)
    alternate[1] = 254  # Same saturated perfect-up decode as 252.
    results = list(family.evaluate_many([original, tuple(alternate)]))
    assert submitted == [1]
    assert [result.controls for result in results] == [original, tuple(alternate)]


@pytest.mark.parametrize("key,value", [("rate", 1.0 + 2 ** -23), ("frame", 3.0),
                                     ("ratio", 0.5), ("pose_frame", 2.0)])
def test_native_validation_rejects_animation_drift(key, value):
    expected, actual = _expected(), _actual()
    animation = dict(index=285, active=True, ratio=1.0, frame=0.0, rate=1.0, pose_frame=0.0)
    expected["under"] = [animation]
    actual["under"] = [dict(animation, **{key: value})]
    with pytest.raises(RuntimeError, match="animation clock 0 diverged"):
        validate_replay([actual], [expected])


def test_native_validation_requires_requested_animation_diagnostics():
    expected, actual = _expected(), _actual()
    expected["under"] = [{"index": 285}]
    with pytest.raises(RuntimeError, match="animation clocks are missing"):
        validate_replay([actual], [expected])


def test_native_controls_round_trip_both_sticks_and_synthesize_b():
    family = _native_family()
    controls = list(family.controls_from_rows())
    assert len(family.axes) == 12
    controls[3] = 89
    rows = family.rows_from_controls(controls, True)
    assert rows[0]["substickY"] == 89
    assert rows[3]["buttons"] == 0x200
    assert family.controls_from_rows(rows) == tuple(controls)


def test_native_checks_raw_movie_to_live_pad_phase():
    from harness.rollstab.native_route import infer_input_delay
    rows = [dict(stickX=x, stickY=200, substickX=60, substickY=89, buttons=0)
            for x in (70, 80, 90, 100, 110, 120)]
    seeds = [{"pad": decode_row(rows[0])}, {"pad": decode_row(rows[0])}]
    seeds.extend({"pad": decode_row(row)} for row in rows)
    # Console angles are signed whereas JSON pad decoding uses their unsigned bits.
    for seed in seeds:
        seed["pad"]["cangle"] -= 65536
    assert infer_input_delay(rows, seeds) == 2
    seeds[4]["pad"]["mx"] += 0.001
    with pytest.raises(RuntimeError, match="P1 pad timing"):
        infer_input_delay(rows, seeds)


@pytest.mark.parametrize("synthesis,end", [(False, 28), (True, 27)])
def test_failed_recorded_rebound_does_not_gate_alternative_routes(synthesis, end):
    from harness.rollstab.native_route import approach_validation_end
    trace = {"route": {"rows": [{}] * 31}, "trace": [
        {"row": 27, "before": {"state": 6}, "after": {"state": 66}},
        {"row": 29, "before": {"state": 66}, "after": {"state": 90}},
    ]}
    assert approach_validation_end(trace, 60, synthesis) == end
    assert approach_validation_end(trace, 15, synthesis) == 20


def test_approach_validation_does_not_bypass_route_without_a_slash():
    from harness.rollstab.native_route import approach_validation_end
    trace = {"route": {"rows": [{}] * 31}, "trace": []}
    assert approach_validation_end(trace, 60, True) == 31


def test_recorded_slash_buffer_measures_equip_delay_from_live_b_edge():
    from harness.rollstab.native_route import recorded_slash_buffer
    seeds = [{"pad": {"item_button": 2 if i >= 24 else 0}} for i in range(32)]
    trace = {"native": {"seeds": seeds}, "trace": [
        {"row": 27, "before": {"state": 6}, "after": {"state": 66}}]}
    assert recorded_slash_buffer(trace) == 3
    seeds[24]["pad"]["item_button"] = 0
    assert recorded_slash_buffer(trace) == 2
    trace["trace"] = []
    assert recorded_slash_buffer(trace) == 0


def test_native_neutral_pad_retains_previous_angles():
    from harness.rollstab.native_route_timing import pad_matches
    row = decode_row(dict(stickX=128, stickY=128))
    captured = dict(row, angle=57611, cangle=-19000)
    assert pad_matches(row, captured)
    assert not pad_matches(decode_row(dict(stickX=129, stickY=252)), captured)


def test_analog_edit_preserves_captured_lock_edge_and_unedited_c_stick():
    family = _native_family()
    family.anchor_row = 1
    family.base_rows[0].update(buttons=0x40, triggerL=255)
    saved = dict(decode_row(family.base_rows[0]), trig_l=1)
    family.seeds = [{"pad": decode_row(dict(stickX=128, stickY=128))}] * 2 + [{"pad": saved}]
    rows = copy.deepcopy(family.base_rows)
    rows[0]["stickX"] = 80
    pad = family._effective_rows(rows, 3)[0]
    assert pad["mx"] == decode_row(rows[0])["mx"]
    assert pad["trig_l"] == 1
    assert pad["cx"] == saved["cx"] and pad["cy"] == saved["cy"]


def test_synthesized_target_generates_camera_lock_edge():
    family = _native_family()
    family.anchor_row = 1
    neutral = decode_row(dict(stickX=128, stickY=128))
    family.seeds = [{"pad": neutral}] * 4
    rows = copy.deepcopy(family.base_rows)
    rows[0].update(buttons=0x40, triggerL=255)
    rows[1].update(buttons=0x40, triggerL=255)
    pads = family._effective_rows(rows, 4)
    assert [pad["trig_l"] for pad in pads] == [1, 0]


def test_native_timing_includes_final_captured_input():
    from harness.rollstab.native_route import infer_input_delay
    rows = [dict(stickX=x, stickY=200) for x in (70, 80, 90, 100, 110)]
    seeds = [{"pad": decode_row(rows[0])}] * 2 + [{"pad": decode_row(r)} for r in rows[:-1]]
    assert infer_input_delay(rows, seeds) == 2
    seeds[-1] = {"pad": dict(seeds[-1]["pad"], item_button=2)}
    with pytest.raises(RuntimeError, match="pad timing"):
        infer_input_delay(rows, seeds)


def test_native_does_not_edit_the_pad_already_in_the_anchor_seed():
    from harness.rollstab.native_route import first_editable_row

    # Seed 4 follows gameplay row 3; raw row 3 is already latched for the
    # first post-anchor update, despite CPAD displaying it afterward.
    assert first_editable_row(anchor_row=3, input_delay=2) == 4
    assert first_editable_row(anchor_row=3, input_delay=3) == 3


def test_search_honors_total_evaluation_budget(tmp_path, monkeypatch):
    from harness.rollstab import smart_route_search as search
    result = search.RouteResult(False, "test", 4, 2, 1, (), (0, 0), (0, 0),
                                68, 0, 0, 17.0, 1.0, 0.0, 0)
    calls = []
    def beam(family, initial, **kwargs):
        calls.append(kwargs["cap"])
        return result, kwargs["cap"]
    family = SimpleNamespace(controls_from_rows=lambda: (), evaluate=lambda _: result,
                             family_has_dust=lambda _: False)
    monkeypatch.setattr(search, "_beam_search", beam)
    payload = search.search_trace({}, tmp_path, evaluation_cap=17, strict_budget=True,
                                  family_factory=lambda *a, **kw: family,
                                  dispatch_factory=lambda _: (4, 5, 6), log=lambda _: None)
    assert sum(calls) == payload["evaluations"] == 17


def test_search_preserves_native_baseline_scoring(tmp_path, monkeypatch):
    from harness.rollstab import smart_route_search as search
    from harness.rollstab.native_route import FacingRouteResult
    baseline = FacingRouteResult(False, "route refinement", 4, 2, 1, (),
                                 (-1., 0.), (1., 0.), 68, 0, 0, 17.,
                                 0.001, 0., 0, collision_error=42., retention_error=35.)
    family = SimpleNamespace(controls_from_rows=lambda: (), evaluate=lambda _: baseline,
                             family_has_dust=lambda _: True)
    monkeypatch.setattr(search, "_beam_search", lambda *a, **kw: (kw.get("initial_result", baseline), 1))
    result = search.search_trace({}, tmp_path, evaluation_cap=3, strict_budget=True,
                                 family_factory=lambda *a, **kw: family,
                                 dispatch_factory=lambda _: (4,),
                                 synthesis_dispatch_factory=lambda _: (), log=lambda _: None)
    assert result["score"] == baseline.score


def test_search_reserves_budget_for_one_unit_refinement():
    from harness.rollstab.smart_route_search import _beam_search, RouteResult
    phases = []
    result = RouteResult(False, "test", 4, 2, 1, (128, 128), (0, 0), (1, 0),
                         68, 0, 0, 17.0, 1.0, 0.0, 0)
    def evaluate(controls, **kw):
        return type(result)(**{**result.__dict__, "controls": controls})
    family = SimpleNamespace(axes=(0, 1), dispatch_row=4, evaluate=evaluate)
    _, count = _beam_search(family, result.controls, cap=70, seed=1,
                            phase="test", broad=False, log=phases.append,
                            cancelled=lambda: False)
    assert count <= 70
    assert any("radius 1," in line for line in phases)


def test_search_reserves_final_trials_for_best_branch(tmp_path, monkeypatch):
    from harness.rollstab import smart_route_search as search
    result = search.RouteResult(False, "route synthesis", 10, 8, 1, (), (0, 0), (1, 0),
                                68, 0, 0, 17.0, 0.01, 0.0, 0)
    polished = []
    def finish(results, cap, phase, synthesis, log):
        polished.append((results, cap, phase, synthesis))
        return result, cap
    family = SimpleNamespace(controls_from_rows=lambda: (), evaluate=lambda _: result,
                             family_has_dust=lambda _: False, polish=finish)
    monkeypatch.setattr(search, "_beam_search", lambda *a, **kw: (result, kw["cap"]))
    payload = search.search_trace({}, tmp_path, evaluation_cap=40, strict_budget=True,
                                  family_factory=lambda *a, **kw: family,
                                  dispatch_factory=lambda _: (4,), final_refinement=True,
                                  log=lambda _: None)
    assert payload["evaluations"] == 40
    assert polished == [([result], 10, "route synthesis", True)]


def test_native_worker_failure_is_not_reported_as_exhausted_search(tmp_path):
    from harness.rollstab.native_route import NativeWorkerError
    from harness.rollstab.smart_route_search import search_trace
    def broken(*args, **kwargs):
        raise NativeWorkerError("worker died")
    with pytest.raises(NativeWorkerError, match="worker died"):
        search_trace({}, tmp_path, family_factory=broken, dispatch_factory=lambda _: (4, 5),
                     log=lambda _: None, strict_budget=True)


def test_native_worker_rejects_closed_pipe_without_writing():
    from harness.rollstab.native_route import NativeWorker, NativeWorkerError
    worker = object.__new__(NativeWorker)
    worker.cancelled = lambda: False
    worker.process = SimpleNamespace(poll=lambda: None, stdin=SimpleNamespace(closed=True))
    with pytest.raises(NativeWorkerError, match="no longer running"):
        worker.request({})


def test_native_cancel_interrupts_wait_for_batch():
    import io
    import queue
    from harness.rollstab.native_route import NativeWorker
    worker = object.__new__(NativeWorker)
    worker.process = SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
    worker.responses = queue.Queue()
    # Cancel arrives after writing the request, before a worker has responded.
    worker.cancelled = lambda: bool(worker.process.stdin.getvalue())
    closed = []
    worker.close = lambda: closed.append(True)
    with pytest.raises(RuntimeError, match="search cancelled"):
        worker.request({})
    assert closed == [True]


def test_native_truncated_batch_is_fatal():
    from harness.rollstab.native_route import NativeWorker, NativeWorkerError
    worker = object.__new__(NativeWorker)
    worker.request = lambda _: {"results": []}
    worker.workers = 1
    closed = []
    worker.close = lambda: closed.append(True)
    with pytest.raises(NativeWorkerError, match="response length"):
        worker.replay({}, [[{}]], 0)
    assert closed == [True]


def test_already_exact_route_returns_before_mutating():
    from types import SimpleNamespace
    from harness.rollstab.smart_route_search import _beam_search

    exact = SimpleNamespace(exact=True)
    family = SimpleNamespace(evaluate=lambda *args, **kwargs: exact)
    result, count = _beam_search(family, (), cap=1000, seed=1, phase="test", broad=False,
                                log=lambda line: None, cancelled=lambda: False)
    assert result is exact and count == 1


def test_speed_priority_continues_past_slower_exact_hit():
    from dataclasses import replace
    from harness.rollstab.smart_route_search import _beam_search, RouteResult

    slow = RouteResult(True, "test", 5, 3, 1, (0,), (0, 0), (1, 0),
                       66, 0, 0, 14.5, 0.0, 0.0, 0)
    fast = replace(slow, controls=(1,), speedf=17.0)
    family = SimpleNamespace(
        axes=(0,), dispatch_row=5, evaluate=lambda *_a, **_kw: slow,
        evaluate_many=lambda controls, **_kw: (fast for _ in controls),
        local_starts=lambda *_a: [(1,)],
        result_rank=lambda result: (result.score, -result.speedf),
        preferred_exact=lambda result: result.exact and result.speedf >= 16.9,
    )
    result, count = _beam_search(family, slow.controls, cap=30, seed=1,
                                 phase="test", broad=False, log=lambda _: None,
                                 cancelled=lambda: False)
    assert result is fast and count == 2


def test_speed_priority_keeps_slower_exact_as_fallback(tmp_path, monkeypatch):
    from harness.rollstab import smart_route_search as search

    def factory(_trace, dispatch, **_kw):
        speed = 14.5 if dispatch == 4 else 16.0
        result = search.RouteResult(True, "test", dispatch, dispatch - 2, 1, (),
                                    (0, 0), (1, 0), 66, 0, 0, speed, 0.0, 0.0, 0)
        return SimpleNamespace(
            controls_from_rows=lambda: (), evaluate=lambda _: result,
            family_has_dust=lambda _: True, export=lambda _r, path: path,
            result_rank=lambda item: (item.score, -item.speedf, item.dispatch_row),
            preferred_exact=lambda item: item.exact and item.speedf >= 16.9,
        )

    monkeypatch.setattr(search, "_beam_search", lambda family, initial, **kw:
                        (kw["initial_result"], 1))
    result = search.search_trace({}, tmp_path, evaluation_cap=2, strict_budget=True,
                                 family_factory=factory, dispatch_factory=lambda _: (4, 5),
                                 synthesis_dispatch_factory=lambda _: (), log=lambda _: None)
    assert result["exact"] and result["dispatch_row"] == 5
    assert result["speedf"] == 16.0


def test_native_speed_rank_prefers_speed_then_earlier_frame():
    from harness.rollstab.native_route import native_result_rank

    slow = {"exact": True, "speedf": 14.5, "dispatch_row": 4, "score": -1000000.0}
    fast = dict(slow, speedf=16.9, dispatch_row=6)
    earlier = dict(fast, dispatch_row=5)
    assert native_result_rank(earlier, True) < native_result_rank(fast, True)
    assert native_result_rank(fast, True) < native_result_rank(slow, True)
    assert native_result_rank(slow) == native_result_rank(fast)


def test_native_search_tries_early_near_seam_windows_before_distant_ones():
    from harness.rollstab.native_route import prioritize_dispatches

    trace = {"geo": {"S": (0, 0, 0)}, "trace": [
        {"row": 3, "after": {"x": 200, "z": 0}},
        {"row": 9, "after": {"x": 60, "z": 0}},
        {"row": 11, "after": {"x": 30, "z": 0}},
        {"row": 12, "after": {"x": 90, "z": 0}},
    ]}
    assert prioritize_dispatches(trace, (13, 12, 4, 10, 8)) == (10, 12, 13, 4, 8)


def test_native_screen_defers_slash_windows_far_from_collision_without_speed_priority():
    from dataclasses import replace
    from harness.rollstab.smart_route_search import _beam_search, RouteResult

    far = RouteResult(False, "test", 4, 2, 1, (0,), (0, 0), (40, 0),
                      66, 0, 0, 17.0, 100.0, 0.0, 0)
    family = _native_family()
    family.prioritize_full_speed = False
    assert not family.screen_promising([far])
    assert family.screen_distance == 100.0
    assert family.screen_promising([replace(far, ray_error=30.0)])
    assert family.screen_promising([replace(far, exact=True)])

    log = []
    search_family = SimpleNamespace(
        axes=(0,), dispatch_row=4, evaluate=lambda *_a, **_kw: far,
        evaluate_many=lambda controls, **_kw: (far for _ in controls),
        local_starts=lambda *_a: [(1,)],
        screen_promising=lambda results: False, screen_distance=100.0,
    )
    _, count = _beam_search(search_family, far.controls, cap=1000, seed=1,
                            phase="test", broad=False, log=log.append,
                            cancelled=lambda: False)
    assert count == 2
    assert any("skipped heavy refinement" in line for line in log)


def test_native_search_proximity_ignores_expected_wall_push():
    from dataclasses import replace
    family = _native_family()
    base = replace(family._result((), _grounded_crossing(), "test"), exact=False)
    blocked = replace(base, ray_error=0.001, collision_error=35.0)
    clean = replace(base, ray_error=0.5, collision_error=0.0)
    assert family.search_proximity([blocked]) == 0.001
    assert family.search_proximity([blocked, clean]) == 0.001


@pytest.mark.parametrize("approaches_seam", [False, True])
def test_native_far_window_gets_exploration_budget_until_replay_approaches_seam(approaches_seam):
    from dataclasses import replace
    from harness.rollstab.smart_route_search import _beam_search, RouteResult

    initial = (128,) * 100
    far = RouteResult(False, "route synthesis", 20, 18, 1, initial,
                      (0.0, 0.0), (1.0, 0.0), 66, 0, 0, 17.0,
                      25.0, 0.0, 0, collision_error=35.0)
    near = replace(far, ray_error=0.5)

    def evaluate_many(trials, **_kwargs):
        for controls in trials:
            source = near if approaches_seam and controls != initial else far
            position = float(sum((axis + 1) * value for axis, value in enumerate(controls)))
            yield replace(source, controls=controls, old=(position, 0.0))

    family = SimpleNamespace(
        axes=tuple(range(len(initial))), dispatch_row=20,
        evaluate=lambda controls, **_kwargs: replace(far, controls=controls),
        evaluate_many=evaluate_many,
        search_proximity=lambda results: min(
            (math.hypot(item.ray_error, item.reach_error)
             for item in results), default=math.inf),
    )
    log = []
    _, count = _beam_search(family, initial, cap=30000, seed=3,
                            phase="route synthesis", broad=True, log=log.append,
                            cancelled=lambda: False)
    if approaches_seam:
        assert count > 4096
        assert not any("deferred after" in line for line in log)
    else:
        assert count <= 4097
        assert any("deferred after" in line for line in log)


def test_native_blocked_dust_polish_is_not_capped_by_wall_push():
    from dataclasses import replace
    family = _native_family()
    seed = replace(family._result(family.controls_from_rows(), _grounded_crossing(), "test"),
                   exact=False, controls=(128,) * 400, ray_error=0.0001, collision_error=35.0)
    family.control_rows = tuple(range(100))
    def replay(trials, **_kw):
        for trial in trials:
            x = float(hash(trial) % 10000000)
            yield replace(seed, controls=trial, old=(x, 0.0), new=(x + 1, 0.0))
    family.evaluate_many = replay
    log = []
    _, count = family.polish([seed], 5000, "test", True, log.append)
    assert count > 4096
    assert not any("limiting float dust polish" in line for line in log)
    assert family.precision_candidates


def test_native_precision_seeds_keep_distinct_wall_hit_positions():
    from dataclasses import replace
    family = _native_family()
    base = replace(family._result((128,) * 12, _grounded_crossing(), "test"), exact=False)
    near = [replace(base, controls=(index,) + base.controls[1:],
                    old=(-1.0 + index * 0.1, 0.001), new=(1.0, 0.001),
                    ray_error=0.001, collision_error=35.0 + index)
            for index in range(20)]
    seeds = family.precision_seeds(near)
    assert len(seeds) == 20
    assert len({round(item.old[0], 1) for item in seeds[:16]}) == 16


def test_native_proposes_slash_for_approach_without_b():
    from harness.rollstab.native_route import native_dispatch_rows

    trace = {"route": {"rows": [{"buttons": 0} for _ in range(12)]},
             "geo": {"S": [10, 0, 0]},
             "trace": [{"row": i, "after": {"state": 6, "x": i, "z": 0}}
                       for i in range(12)]}
    assert native_dispatch_rows(trace) == (8, 7, 6)


def test_exact_result_outranks_any_near_miss():
    from dataclasses import replace
    result = _native_family()._result((), _grounded_crossing(), "test")
    miss = replace(result, exact=False, ray_error=0.0)
    exact = replace(result, ray_error=0.019, collision_error=0.0)
    assert exact.score < miss.score


def test_new_native_routes_do_not_require_slashing_before_recording_ends():
    from harness.rollstab.native_route_plans import replan_dispatches
    trace = {"native": {"seeds": [{"proc": 10}] * 14 + [{"proc": 11}, {"proc": 4}, {"proc": 6}]}}
    assert max(replan_dispatches(trace, "walking")) > len(trace["native"]["seeds"])
    assert max(replan_dispatches(trace, "rolling")) > len(trace["native"]["seeds"])


def test_route_plans_change_whole_approaches_and_camera_paths():
    from harness.rollstab.native_route_plans import route_starts
    family = _native_family()
    family.base_rows *= 5
    family.control_rows = tuple(range(25))
    family.seeds = [{"proc": 10, "pos": [0, 0, -200], "camera": 0}] * 12
    family.seeds += [{"proc": 4, "pos": [0, 0, -100], "camera": 0}] * 20
    seeds = list(route_starts(family, 100, 3))
    assert seeds == list(route_starts(family, 100, 3))
    assert len(set(row[2:4] for row in seeds)) > 3
    assert any(len({row[i:i + 2] for i in range(40, 100, 4)}) > 1 for row in seeds)
    assert all(len(row) == 100 for row in seeds)


def test_grounded_route_plans_really_pulse_camera_instead_of_only_before_walk():
    from harness.rollstab.native_route_plans import route_starts
    family = _native_family()
    family.seeds = [{"proc": 6, "pos": [0, 0, -200], "camera": 0}] * 8
    controls = list(route_starts(family, 5, 3))
    assert len({row[2:4] for row in controls}) == 5


def _pre_roll_family():
    family = _native_family()
    family.mode = "rolling"
    family.roll_axis = family.recipe_axis = True
    family.walk_row = 0
    family.button_row = 36
    family.base_rows *= 8
    family.control_rows = tuple(range(38))
    family.seeds = [{"proc": 6, "pos": [0, 0, -200], "camera": 0}] * 50
    return family


def test_pre_roll_slow_windows_preserve_camera_buttons_and_full_speed_launch_input():
    from harness.rollstab.native_route_plans import pre_roll_starts, roll_button_row
    from tww_sim.core.mathlib import main_stick_decode
    family = _pre_roll_family()
    original = family.controls_from_rows()
    roll = roll_button_row(family, original)
    trials = list(pre_roll_starts(family, original))
    assert len(trials) > 100 and len(trials) == len(set(trials))
    assert trials == list(pre_roll_starts(family, original))
    authored = family.rows_from_controls(original, True)
    for trial in trials:
        assert len(trial) == len(original) and trial[-2:] == original[-2:]
        rows = family.rows_from_controls(trial, True)
        slow = [i for i in family.control_rows
                if main_stick_decode(rows[i]["stickX"], rows[i]["stickY"])[1] < 0.7]
        assert slow and all(i < roll for i in slow)
        assert main_stick_decode(rows[roll]["stickX"], rows[roll]["stickY"])[1] == 1.0
        assert rows[roll]["buttons"] & 0x100
        assert rows[roll + 1:] == authored[roll + 1:]
        assert all((row["buttons"], row["substickX"], row["substickY"]) ==
                   (base["buttons"], base["substickX"], base["substickY"])
                   for row, base in zip(rows, authored))


def test_pre_roll_windows_include_adjacent_byte_precision_and_acceleration_lengths():
    from harness.rollstab.native_route_plans import pre_roll_starts, roll_button_row
    family = _pre_roll_family()
    original = family.controls_from_rows()
    trials = list(pre_roll_starts(family, original))
    assert sum(abs(a - b) for a, b in zip(trials[0], trials[1])) == 1
    roll = roll_button_row(family, original)
    endings = {max(i for i in family.control_rows
                   if trial[i * 4:i * 4 + 2] != original[i * 4:i * 4 + 2]) for trial in trials}
    assert endings == {family.walk_row, family.walk_row + 1, family.walk_row + 3,
                       roll - 7, roll - 5, roll - 3}


@pytest.mark.parametrize("mode,proc,walk", [("walking", 6, 0), ("rolling", 30, 0),
                                           ("rolling", 6, 20)])
def test_pre_roll_does_not_invent_a_positioning_phase_when_unavailable(mode, proc, walk):
    from harness.rollstab.native_route_plans import pre_roll_starts
    family = _pre_roll_family()
    family.mode, family.start_seed["proc"], family.walk_row = mode, proc, walk
    if proc == 30:
        family.seeds = [dict(seed, proc=30) for seed in family.seeds]
    assert list(pre_roll_starts(family, family.controls_from_rows())) == []


def test_pre_roll_can_position_for_a_new_roll_after_the_recorded_roll_lands():
    from harness.rollstab.native_route_plans import pre_roll_starts
    family = _pre_roll_family()
    family.start_seed["proc"] = 30
    family.seeds[:8] = [dict(seed, proc=30) for seed in family.seeds[:8]]
    family.walk_row = 8 - family.input_delay
    original = family.controls_from_rows()
    trials = list(pre_roll_starts(family, original))
    assert trials
    assert all(trial[:family.walk_row * 4] == original[:family.walk_row * 4] for trial in trials)


def test_rolling_plans_interleave_slow_positioning_without_changing_walking_plans():
    from harness.rollstab.native_route_plans import _approach_starts, route_starts
    from tww_sim.core.mathlib import main_stick_decode
    family = _pre_roll_family()
    trials = list(route_starts(family, 100, 3))
    assert len(trials) == len(set(trials)) == 100
    assert trials == list(route_starts(family, 100, 3))
    assert trials[0] == next(_approach_starts(family, 100, 3))
    assert len(set(trials) & set(_approach_starts(family, 100, 3))) >= 75
    assert any(main_stick_decode(*trial[i * 4:i * 4 + 2])[1] < 0.7
               for trial in trials[1:3] for i in family.control_rows)
    assert list(route_starts(family, 0, 3)) == []
    family.mode = "walking"
    assert list(route_starts(family, 100, 3)) == list(_approach_starts(family, 100, 3))


def test_native_resume_retains_explicit_control_rows_and_target_recipe():
    family = _native_family()
    family.recipe_axis = True
    family.roll_axis = False
    family.seeds = [{"proc": 6, "pos": [0, 0, -100], "camera": 0}] * 8
    family.trace = {"geo": {}, "route": {"start_vi": 100}}
    family.route = SimpleNamespace(rows=tuple(family.base_rows), poll_spans=())
    family.warm_result = dict(control_schema="native-route-v2", variable_start=1,
                              control_rows=[0, 1], controls=[90, 252, 174, 89] * 2 + [3])
    controls = next(family.route_starts(1, 1))
    assert controls[:8] == (90, 252, 174, 89) * 2
    assert controls[-1] == 3
    family.warm_result["route_identity"] = "wrong-room-or-state"
    assert next(family.route_starts(1, 1)) != controls


def test_rolling_resume_tries_pre_roll_precision_variants_within_its_budget():
    from tww_sim.core.mathlib import main_stick_decode
    family = _pre_roll_family()
    family.trace = {"geo": {}, "route": {"start_vi": 100}}
    family.route = SimpleNamespace(rows=tuple(family.base_rows), poll_spans=())
    original = family.controls_from_rows()
    family.warm_result = dict(control_schema="native-route-v2", mode="rolling",
                              control_rows=list(family.control_rows), controls=original)
    assert list(family.route_starts(1, 1)) == [original]
    trials = list(family.route_starts(13, 1))
    assert len(trials) == 13 and trials[0] == original
    assert all(any(main_stick_decode(*trial[i * 4:i * 4 + 2])[1] < 0.7
                   for i in family.control_rows) for trial in trials[1:])
    assert all(trial[-2:] == original[-2:] for trial in trials)


def _recorded_roll_family():
    family = _pre_roll_family()
    family.mode = "walking"
    family.roll_axis = False
    family.route_recipes = True
    family.button_row = 28
    family.walk_row = 22
    family.base_rows = [dict(row) for row in family.base_rows]
    family.base_rows[5]["buttons"] = 0x100
    family.base_rows[2].update(buttons=0x40, triggerL=255)
    family.seeds[8:24] = [dict(seed, proc=30) for seed in family.seeds[8:24]]
    return family


def test_manual_recipe_preserves_roll_targeting_and_triggers_while_retiming_slash():
    family = _recorded_roll_family()
    controls = family.controls_from_rows()
    assert controls[-1] == 4
    rows = family.rows_from_controls(controls, True)
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x100] == [5]
    assert rows[2]["buttons"] & 0x40 and rows[2]["triggerL"] == 255
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x200] == [28]


def test_synthesized_walking_slash_preserves_recorded_roll_and_varies_early_stick():
    from harness.rollstab.native_route_plans import _approach_starts

    family = _recorded_roll_family()
    family.dispatch_row = 28
    original = family.controls_from_rows()
    trials = list(_approach_starts(family, 100, 3))
    assert trials
    assert all(trial[-1] == 4 for trial in trials)
    assert all(family.rows_from_controls(trial, True)[5]["buttons"] & 0x100
               for trial in trials)
    assert any(trial[:6 * 4:4] != original[:6 * 4:4] for trial in trials)
    assert all(family.rows_from_controls(trial, True)[28]["buttons"] & 0x200
               for trial in trials)


@pytest.mark.parametrize("code,launch", [(8, 6), (12, 7), (16, 8), (20, 4), (24, 3)])
def test_editable_manual_roll_can_be_delayed_or_advanced(code, launch):
    family = _recorded_roll_family()
    controls = (*family.controls_from_rows()[:-1], code)
    rows = family.rows_from_controls(controls, True)
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x100] == [launch]
    assert rows[28]["buttons"] & 0x200
    assert rows[2]["triggerL"] == 255


def test_manual_variants_keep_prefix_and_explore_post_roll_speed_camera_and_timing():
    from harness.rollstab.native_route_plans import recorded_starts
    from tww_sim.core.mathlib import main_stick_decode
    family = _recorded_roll_family()
    original = family.controls_from_rows()
    trials = list(recorded_starts(family, 60, 7))
    assert len(trials) == len(set(trials)) == 60
    assert trials == list(recorded_starts(family, 60, 7))
    assert trials[0] == original
    assert {trial[-1] for trial in trials[:6]} == {4, 8, 12, 16, 20, 24}
    assert all(trial[:family.walk_row * 4] == original[:family.walk_row * 4] for trial in trials)
    assert any(main_stick_decode(*trial[family.walk_row * 4:family.walk_row * 4 + 2])[1] < 0.3
               for trial in trials)
    assert len({trial[family.walk_row * 4 + 2] for trial in trials}) > 3


def test_manual_roll_delay_never_edits_an_immutable_a_press_before_the_anchor():
    from harness.rollstab.native_route_plans import recorded_starts
    family = _recorded_roll_family()
    family.control_rows = tuple(range(20, 38))
    trials = list(recorded_starts(family, 40, 7))
    assert trials and all(trial[-1] == 4 for trial in trials)
    controls = (*family.controls_from_rows()[:-1], 12)
    rows = family.rows_from_controls(controls, True)
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x100] == [5]


def test_post_roll_variants_also_work_when_the_starting_state_is_already_rolling():
    from harness.rollstab.native_route_plans import recorded_starts
    family = _recorded_roll_family()
    family.base_rows[5]["buttons"] = 0
    family.seeds[:8] = [dict(seed, proc=30) for seed in family.seeds[:8]]
    trials = list(recorded_starts(family, 20, 7))
    assert len(trials) == 20 and all(trial[-1] == 4 for trial in trials)
    assert all(not any(row["buttons"] & 0x100 for row in family.rows_from_controls(trial, True))
               for trial in trials)


def test_rolling_search_does_not_spend_template_trials_on_an_immutable_finished_roll():
    from harness.rollstab.native_route_plans import recorded_starts
    family = _recorded_roll_family()
    family.mode = "rolling"
    family.roll_axis = True
    family.control_rows = tuple(range(20, 38))
    assert list(recorded_starts(family, 40, 7)) == []


def test_native_polish_does_not_repeatedly_expand_identical_float_positions():
    from dataclasses import replace
    family = _native_family()
    seed = family._result(family.controls_from_rows(), _grounded_crossing(), "test")
    seed = replace(seed, exact=False, ray_error=0.0001)
    family.evaluate_many = lambda trials, **kw: (replace(seed, controls=trial) for trial in trials)
    result, count = family.polish([seed], 1000, "test", True, lambda _: None)
    assert result == seed and 0 < count < 100


def test_native_polish_skips_opposing_sensitivities_that_average_to_zero():
    from dataclasses import replace
    family = _native_family()
    seed = family._result(family.controls_from_rows(), _grounded_crossing(), "test")
    seed = replace(seed, exact=False, old=(-1.0, 0.0001), new=(1.0, 0.0001), ray_error=0.0001)
    attempts = []

    def evaluate_many(trials, **kwargs):
        for trial in trials:
            attempts.append(trial)
            offset = 0.0001 + sum(abs(a - b) for a, b in zip(trial, seed.controls)) * 0.001
            yield replace(seed, controls=trial, old=(-1.0, offset), new=(1.0, offset), ray_error=offset)

    family.evaluate_many = evaluate_many
    result, count = family.polish([seed], 100, "test", True, lambda _: None)
    assert result == seed
    assert count == len(attempts) == len(family.control_rows) * 8


def test_native_polish_tries_distinct_near_miss_parents_after_first_eight():
    from dataclasses import replace
    family = _native_family()
    seed = family._result(family.controls_from_rows(), _grounded_crossing(), "test")
    seeds = []
    for index in range(1, 10):
        controls = (index * 16, *seed.controls[1:])
        offset = index * 0.0001
        seeds.append(replace(seed, exact=False, controls=controls,
                             old=(-1.0, offset), new=(1.0, offset), ray_error=offset))
    visited = set()

    def evaluate_many(trials, **kwargs):
        for trial in trials:
            visited.add(trial[0])
            yield replace(seed, exact=False, controls=trial, old=(-1.0, 1.0),
                          new=(1.0, 1.0), ray_error=1.0)

    family.evaluate_many = evaluate_many
    family.polish(seeds, 2000, "test", True, lambda _: None)
    assert 143 in visited or 145 in visited


@pytest.mark.parametrize("schema,expected", [("native-route-v3", 12), ("native-route-v2", 0)])
def test_manual_timing_resume_preserves_new_recipes_and_migrates_old_recipe_values(schema, expected):
    family = _recorded_roll_family()
    family.trace = {"geo": {}, "route": {"start_vi": 100}}
    family.route = SimpleNamespace(rows=tuple(family.base_rows), poll_spans=())
    controls = (*family.controls_from_rows()[:-1], 12)
    family.warm_result = dict(control_schema=schema, mode="walking",
                              control_rows=list(family.control_rows), controls=controls)
    assert next(family.route_starts(1, 1))[-1] == expected


def test_final_refinement_changes_routes_when_the_best_branch_cannot_improve(tmp_path, monkeypatch):
    from dataclasses import replace
    from harness.rollstab import smart_route_search as search
    visited, exports = [], []

    def result(dispatch):
        return search.RouteResult(False, "route refinement", dispatch, dispatch - 2, 1, (),
                                  (-1.0, float(dispatch)), (1.0, float(dispatch)),
                                  68, 0, 0, 17.0, dispatch / 10000, 0.0, 0)

    def factory(trace, dispatch, **kwargs):
        def polish(results, budget, *args):
            visited.append((dispatch, budget))
            return replace(results[0], exact=dispatch == 11), 1

        def export(candidate, path):
            exports.append(dispatch)
            return path

        return SimpleNamespace(controls_from_rows=lambda: (), evaluate=lambda _: result(dispatch),
                               family_has_dust=lambda _: False, polish=polish, export=export)

    monkeypatch.setattr(search, "_beam_search", lambda family, initial, **kw: (kw["initial_result"], 1))
    payload = search.search_trace({}, tmp_path, family_factory=factory, evaluation_cap=20,
                                  strict_budget=True, final_refinement=True,
                                  dispatch_factory=lambda _: (10, 11),
                                  synthesis_dispatch_factory=lambda _: (), log=lambda _: None)
    assert [dispatch for dispatch, budget in visited] == [10, 11]
    assert payload["exact"] and payload["dispatch_row"] == 11
    assert payload["evaluations"] <= 20 and exports == [11]


def test_final_refinement_restarts_from_native_near_miss(tmp_path, monkeypatch):
    from dataclasses import replace
    from harness.rollstab import smart_route_search as search
    initial = search.RouteResult(False, "route refinement", 10, 8, 1, (),
                                 (-1.0, 0.01), (1.0, 0.01), 68, 0, 0, 17.0,
                                 0.01, 0.0, 0)
    restarts = []

    def factory(trace, dispatch, **kwargs):
        def restart(item, budget, seed, log, cancelled):
            restarts.append(budget)
            return replace(item, exact=True), 1

        return SimpleNamespace(controls_from_rows=lambda: (), evaluate=lambda _: initial,
                               family_has_dust=lambda _: False,
                               polish=lambda results, *args: (results[0], 1),
                               restart_near=restart, export=lambda item, path: path)

    monkeypatch.setattr(search, "_beam_search", lambda family, initial, **kw: (kw["initial_result"], 1))
    payload = search.search_trace({}, tmp_path, family_factory=factory,
                                  dispatch_factory=lambda _: (10,),
                                  synthesis_dispatch_factory=lambda _: (),
                                  evaluation_cap=5000, strict_budget=True,
                                  final_refinement=True, log=lambda _: None)
    assert payload["exact"] and len(restarts) == 1
    assert payload["evaluations"] <= 5000


def test_final_refinement_uses_distinct_precision_seeds_and_stops_stale_restarts(tmp_path, monkeypatch):
    from dataclasses import replace
    from harness.rollstab import smart_route_search as search

    initial = search.RouteResult(False, "route refinement", 10, 8, 1, (1,),
                                 (-1.0, 0.001), (1.0, 0.001), 68, 0, 0, 17.0,
                                 0.001, 0.0, 0, collision_error=35.0)
    alternate = replace(initial, controls=(2,), old=(-1.2, -0.001),
                        new=(1.1, -0.001), ray_error=0.0015)
    polished = []
    restarts = []

    def factory(trace, dispatch, **kwargs):
        family = SimpleNamespace(
            controls_from_rows=lambda: initial.controls,
            evaluate=lambda *_args: initial,
            family_has_dust=lambda *_args: True,
            precision_seeds=lambda items: list(items),
            search_proximity=lambda items: min(item.ray_error for item in items),
            polish=lambda items, *args: (polished.append(tuple(item.controls for item in items))
                                         or initial, 1),
            restart_near=lambda *args: (restarts.append(True) or initial, 1),
        )
        return family

    def beam(family, initial_controls, **kwargs):
        family.precision_candidates = [initial, alternate]
        return initial, 1

    monkeypatch.setattr(search, "_beam_search", beam)
    search.search_trace({}, tmp_path, family_factory=factory,
                        dispatch_factory=lambda _: (10,),
                        synthesis_dispatch_factory=lambda _: (),
                        evaluation_cap=5000, strict_budget=True,
                        final_refinement=True, log=lambda _: None)
    assert any((1,) in call and (2,) in call for call in polished)
    assert len(restarts) == 2


def test_native_near_restart_uses_precision_seeds_without_camera_replans(monkeypatch):
    from dataclasses import replace
    from harness.rollstab import native_route

    family = _native_family()
    seed = replace(family._result(family.controls_from_rows(), _grounded_crossing(), "test"),
                   exact=False, ray_error=0.0001, collision_error=38.0)
    family.precision_candidates = [seed]
    called = []

    def beam(*args, **kwargs):
        called.append(kwargs)
        return seed, 1

    monkeypatch.setattr(native_route, "_beam_search", beam)
    family.restart_near(seed, 12000, 5, lambda _: None, lambda: False)
    assert called[0]["cap"] == 12000
    assert called[0]["near_restart"] is True
    assert called[0]["seed_results"] == [seed]


def test_near_restart_mutates_saved_precision_states_without_regenerating_starts():
    from dataclasses import replace
    from harness.rollstab.smart_route_search import RouteResult, _beam_search

    initial = RouteResult(False, "route synthesis", 10, 8, 1, (128,),
                          (-1.0, 0.001), (1.0, 0.001), 68, 0, 0, 17.0,
                          0.001, 0.0, 0)
    saved = replace(initial, controls=(130,), old=(-1.1, 0.001))
    evaluated = []

    def evaluate_many(trials, **kwargs):
        for trial in trials:
            evaluated.append(trial)
            yield replace(initial, controls=trial, old=(-1.0 + trial[0] / 1000, 0.001))

    family = SimpleNamespace(
        axes=(0,), dispatch_row=10,
        evaluate_many=evaluate_many,
        route_starts=lambda *_args: pytest.fail("near restart regenerated broad camera starts"),
        precision_seeds=lambda items: sorted(items, key=lambda item: item.ray_error)[:64],
        search_proximity=lambda items: min(item.ray_error for item in items),
    )
    _beam_search(family, initial.controls, cap=100, seed=9,
                 phase="route synthesis", broad=True, log=lambda _: None,
                 cancelled=lambda: False, initial_result=initial,
                 near_restart=True, seed_results=(saved,))
    assert evaluated
    assert family.precision_candidates
    assert any(item.controls == saved.controls for item in family.precision_candidates)


def test_exact_restart_outranks_a_smaller_near_miss_ray(tmp_path, monkeypatch):
    from dataclasses import replace
    from harness.rollstab import smart_route_search as search

    miss = search.RouteResult(False, "route refinement", 10, 8, 1, (1,),
                              (-1.0, 0.0001), (1.0, 0.0001), 68, 0, 0, 17.0,
                              0.0001, 0.0, 0)
    exact = replace(miss, exact=True, controls=(2,), ray_error=0.01)

    def factory(trace, dispatch, **kwargs):
        return SimpleNamespace(
            controls_from_rows=lambda: miss.controls, evaluate=lambda *_args: miss,
            family_has_dust=lambda *_args: True,
            precision_seeds=lambda items: list(items),
            search_proximity=lambda items: min(item.ray_error for item in items),
            polish=lambda items, *args: (miss, 1),
            restart_near=lambda *args: (exact, 1),
            export=lambda item, path: path,
        )

    def beam(family, initial_controls, **kwargs):
        family.precision_candidates = [miss]
        return miss, 1

    monkeypatch.setattr(search, "_beam_search", beam)
    result = search.search_trace({}, tmp_path, family_factory=factory,
                                 dispatch_factory=lambda _: (10,),
                                 synthesis_dispatch_factory=lambda _: (),
                                 evaluation_cap=5000, strict_budget=True,
                                 final_refinement=True, log=lambda _: None)
    assert result["exact"] and result["controls"] == (2,)


def test_native_warm_identity_includes_poll_timing_and_route_inputs():
    family = _native_family()
    family.seeds = [{"proc": 6}]
    family.trace = {"geo": {}, "route": {"start_vi": 100}}
    family.route = SimpleNamespace(rows=tuple(family.base_rows), poll_spans=())
    original = family.control_metadata()["route_identity"]
    family.route.poll_spans = ((204, 208),)
    assert family.control_metadata()["route_identity"] != original


def test_native_polish_respects_budget_and_requires_replayed_acceptance():
    from dataclasses import replace
    family = _native_family()
    seed = family._result(family.controls_from_rows(), _grounded_crossing(), "test")
    seed = replace(seed, exact=False, ray_error=0.0001)
    attempts = []
    def evaluate_many(trials, **kwargs):
        for trial in trials:
            attempts.append(trial)
            yield replace(seed, controls=trial, old=(-1.0, 0.0001), new=(1.0, 0.0001))
    family.evaluate_many = evaluate_many
    result, count = family.polish([seed], 3, "test", True, lambda _: None)
    assert count == len(attempts) == 3
    assert not result.exact


def test_synthesis_runs_when_recorded_windows_are_unusable(tmp_path, monkeypatch):
    from harness.rollstab import smart_route_search as search
    miss = search.RouteResult(False, "test", 10, 8, 1, (), (0, 0), (1, 0),
                             68, 0, 0, 17.0, 1.0, 0.0, 0)
    called = []
    def factory(trace, dispatch, **kwargs):
        called.append(dispatch)
        if not kwargs.get("from_start"):
            raise RuntimeError("unusable original approach")
        return SimpleNamespace(controls_from_rows=lambda: ())
    monkeypatch.setattr(search, "_beam_search", lambda *a, **kw: (miss, 1))
    result = search.search_trace({}, tmp_path, evaluation_cap=10, strict_budget=True,
                                 family_factory=factory, dispatch_factory=lambda _: (4,),
                                 synthesis_dispatch_factory=lambda _: (10,), log=lambda _: None)
    assert called == [4, 10]
    assert not result["exact"]


def test_native_gui_settings_round_trip(tmp_path):
    from harness.rollstab.native_route_gui import NativeRouteGUI

    class TestGUI(NativeRouteGUI):
        settings_path = tmp_path / "settings.json"

    gui = TestGUI()
    try:
        gui.withdraw()
        gui._replace(gui.game_id, "GZLJ11")
        gui._replace(gui.iso, "JP.iso")
        gui._replace(gui.workers, "8")
        gui.mode.set("Rolling")
        gui.prioritize_full_speed.set(True)
        gui._save_settings()
    finally:
        gui.destroy()
    restored = TestGUI()
    try:
        restored.withdraw()
        assert restored.game_id.get() == "GZLJ11"
        assert restored.iso.get() == "JP.iso"
        assert restored.workers.get() == "8"
        assert restored.mode.get() == "Rolling"
        assert restored.prioritize_full_speed.get()
    finally:
        restored.destroy()


@pytest.mark.parametrize('mode', ['Walking', 'Rolling', 'Both'])
def test_gui_selection_never_silently_changes_slash_type(monkeypatch, mode):
    from harness.rollstab import native_route_gui as gui_module
    gui = object.__new__(gui_module.NativeRouteGUI)
    gui.cancelled = SimpleNamespace(is_set=lambda: False)
    captured = []
    monkeypatch.setattr(gui_module, 'search_native_trace', lambda *a, **kw: captured.append(kw))
    options = dict(executable='worker', iso='iso', workers=6, mode=mode, cap=1000, seed=1,
                   allow_mode_fallback=True)
    gui._solve_trace(options, {}, lambda _: None)
    assert captured[0]['mode'] == mode
    assert captured[0]['allow_mode_fallback'] is False


@pytest.mark.parametrize("fallback,modes", [(True, ["rolling", "walking"]), (False, ["rolling"])])
def test_native_other_mode_fallback_shares_budget_and_closes_worker(tmp_path, monkeypatch, fallback, modes):
    from harness.rollstab import native_route as native
    closed, calls = [], []
    route = SimpleNamespace(rows=({},), poll_spans=())
    monkeypatch.setattr(native, "_route", lambda _: route)
    monkeypatch.setattr(native, "align_movie_polls", lambda *a: route)
    monkeypatch.setattr(native, "infer_input_delay", lambda *a: 2)
    monkeypatch.setattr(native, "extract_assets", lambda *a: tmp_path)
    monkeypatch.setattr(native, "NativeWorker", lambda *a, **kw:
                        SimpleNamespace(workers=6, close=lambda: closed.append(True)))
    def search(trace, output, **kwargs):
        calls.append((output.name, kwargs["evaluation_cap"]))
        output.mkdir(parents=True)
        return {"exact": output.name == "walking", "evaluations": kwargs["evaluation_cap"],
                "score": 0, "result_path": str(output / "result.json")}
    monkeypatch.setattr(native, "search_trace", search)
    result = native.search_native_trace({"native": {"seeds": [], "room": "GanonA"}, "route": {}}, tmp_path,
                                       executable="worker", iso="iso", mode="Rolling",
                                       evaluation_cap=8, allow_mode_fallback=fallback, log=lambda _: None)
    assert [mode for mode, cap in calls] == modes
    assert sum(cap for mode, cap in calls) == result["evaluations"] == 8
    assert result["tested_modes"] == modes
    assert result["exact"] == fallback
    assert closed == [True]


def test_native_default_search_orders_near_windows_without_speed_priority(tmp_path, monkeypatch):
    from harness.rollstab import native_route as native

    route = SimpleNamespace(rows=({},), poll_spans=())
    monkeypatch.setattr(native, "_route", lambda _: route)
    monkeypatch.setattr(native, "align_movie_polls", lambda *a: route)
    monkeypatch.setattr(native, "infer_input_delay", lambda *a: 2)
    monkeypatch.setattr(native, "extract_assets", lambda *a: tmp_path)
    monkeypatch.setattr(native, "NativeWorker", lambda *a, **kw:
                        SimpleNamespace(workers=1, close=lambda: None))
    monkeypatch.setattr(native, "native_dispatch_rows", lambda _: (2, 1))
    monkeypatch.setattr(native, "replan_dispatches", lambda *_: (2, 1))
    seen = []

    def search(trace, output, **kwargs):
        seen.append(kwargs["dispatch_factory"](trace))
        seen.append(kwargs["synthesis_dispatch_factory"](trace))
        output.mkdir(parents=True)
        return {"exact": False, "evaluations": 1, "score": 0,
                "result_path": str(output / "result.json")}

    monkeypatch.setattr(native, "search_trace", search)
    trace = {"native": {"seeds": [], "room": "GanonA"}, "route": {},
             "geo": {"S": (0, 0, 0)}, "trace": [
                 {"row": 0, "before": {"state": 4}, "after": {"state": 4, "x": 10, "z": 0}},
                 {"row": 1, "before": {"state": 4}, "after": {"state": 4, "x": 200, "z": 0}},
             ]}
    native.search_native_trace(trace, tmp_path, executable="worker", iso="iso",
                               mode="Walking", evaluation_cap=10,
                               prioritize_full_speed=False, log=lambda _: None)
    assert seen == [(1, 2), (1, 2)]
