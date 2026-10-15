from types import SimpleNamespace
from pathlib import Path

import pytest

from harness.rollstab.native_route import NativeFamily, native_dispatch_rows
from harness.rollstab.native_route_plans import actor_push_prefix_end, replan_dispatches
from harness.rollstab.recorded_route import RecordedRoute


def contacted_route():
    trace = dict(route=dict(rows=[{} for _ in range(21)]), geo=dict(S=[0., 0., 0.]),
                 native=dict(seeds=[dict(proc=6) for _ in range(22)]))
    trace["trace"] = [dict(row=i, before=dict(state=6, cc_move=[1. if 1 <= i <= 4 else 0., 0., 0.]),
                           after=dict(state=68 if i == 8 else 6, x=0., y=0., z=float(i)))
                      for i in range(21)]
    return trace


def test_actor_pushes_preserve_their_consumption_frames_not_the_following_slash():
    trace = contacted_route()
    trace["trace"][10]["before"]["cc_move"] = [9., 0., 0.]
    assert actor_push_prefix_end(trace) == 5
    assert min(native_dispatch_rows(trace)) > 5


@pytest.mark.parametrize("mode", ["walking", "rolling"])
def test_synthesis_timing_is_relative_to_the_editable_state_after_contact(mode):
    trace = contacted_route()
    dispatches = replan_dispatches(trace, mode)
    assert min(dispatches) > 5
    assert max(dispatches) > len(trace["route"]["rows"])
    if mode == "walking":
        assert 10 in dispatches and 13 in dispatches and 25 in dispatches


def test_routes_without_actor_contact_keep_the_original_timing_options():
    trace = contacted_route()
    for frame in trace["trace"]:
        frame["before"]["cc_move"] = [0., 0., 0.]
    assert actor_push_prefix_end(trace) == 0
    assert replan_dispatches(trace, "walking")[0] == 2
    assert actor_push_prefix_end({}) == 0


def test_unknown_actor_contact_is_not_fitted_or_injected_into_changed_inputs(monkeypatch):
    from harness.rollstab import native_route as module

    trace = contacted_route()
    trace["native"]["seeds"] = [dict(proc=6, camera=0, camera_state=dict(fields=dict(mEye=[0., 0., 0.],
                                                                               mCenter=[0., 0., 0.])),
                                    under=[]) for _ in range(22)]
    route = RecordedRoute(movie=Path("route.dtm"), start_state=Path("start.sav"),
                          start_vi=0, end_vi=42, controller=0, rows=tuple(trace["route"]["rows"]), poll_spans=())
    monkeypatch.setattr(module, "_route", lambda _: route)
    monkeypatch.setattr(module, "align_movie_polls", lambda *a: route)
    monkeypatch.setattr(module, "infer_input_delay", lambda *a: 2)
    monkeypatch.setattr(module, "recorded_slash_buffer", lambda *a: 0)
    monkeypatch.setattr(module, "SeamGeo", lambda *a: None)
    called = []
    monkeypatch.setattr(NativeFamily, "_effective_rows", lambda self, *a: called.append(self.anchor_row) or [])
    worker = SimpleNamespace(replay=lambda *a, **k: [dict(frames=[])])
    monkeypatch.setattr(module, "validate_replay", lambda *a: None)
    family = NativeFamily(trace, 8, worker=worker, from_start=True)
    assert called == [4]
    assert family.variable_start == 5 and family.actor_push_prefix == 5
