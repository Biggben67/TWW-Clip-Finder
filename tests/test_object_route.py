import copy
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.collision.object_route import DropFamily, DropResult, lower_pose, release_row, rounded_frame
from harness.collision import object_route
from harness.collision.object_route_capture import (
    object_kind, ObjectObserver, validate_live_object_outcome, verification_row_count,
)
from harness.collision.object_route_gui import MovingObjectGUI
from harness.rollstab.native_route_gui import NativeRouteGUI
from harness.rollstab.route_constraints import FacingRanges
from tww_sim.core import fp
from tww_sim.core import drop_release as dr


def test_oob_search_progress_reports_landing_gap_and_clip_speed():
    item = SimpleNamespace(ray_error=0.001, reach_error=0., landing_distance=14.2,
                           landing_error=13.2, grounded=True, landing_speed=12.6,
                           collision_error=57.8)
    normal = object_route.search_progress(item)
    oob = object_route.search_progress(item, True)
    assert "landing" not in normal
    assert "landing 14.200000" in oob
    assert "clip speed 12.600000" in oob
    assert "collision correction 57.800000" in normal


@pytest.mark.parametrize("process,parameters,kind", [(0x128, 0, "bomb"), (0x1CB, 0x70000000, "pot_small")])
def test_detect_supported_object(process, parameters, kind):
    assert object_kind(process, parameters) == kind


@pytest.mark.parametrize("process,parameters,status", [(0x1CB, 0x71000000, 0), (0x128, 0, 0x10000), (1, 0, 0)])
def test_reject_unmodeled_or_heavy_object(process, parameters, status):
    with pytest.raises(ValueError):
        object_kind(process, parameters, status)


def test_release_row_is_gameplay_index_not_observation_index():
    assert release_row({"extra": [{"holding": True}, {"holding": True}, {"holding": False}]}) == 1
    with pytest.raises(RuntimeError):
        release_row({"extra": [{"holding": True}]})


@pytest.mark.parametrize("mode,after", [(2, True), (4, False)])
def test_pot_mode_identifies_release_order_even_when_position_is_unchanged(mode, after):
    held = dict(prop_mode=4, prop_pos=[0., 100., 0.])
    released = dict(prop_mode=mode, prop_pos=list(held["prop_pos"]))
    assert object_route.release_executes_after_link("pot_small", held, released) is after


def test_pot_release_order_rejects_throw_mode_and_preserves_old_captures():
    held = dict(prop_mode=4, prop_pos=[0., 100., 0.])
    with pytest.raises(RuntimeError, match="carry-to-wait"):
        object_route.release_executes_after_link("pot_small", held, dict(prop_mode=5))
    assert not object_route.release_executes_after_link("pot_small", held, dict(prop_pos=held["prop_pos"]))
    assert object_route.release_executes_after_link("pot_small", held, dict(prop_pos=[1., 100., 0.]))


def test_pot_observer_captures_the_full_actor_mode_word():
    address = 0x81000000
    words = {address + 0xB0: 0x70000000, address + 0x1C4: 0, address + 0x678: 4}
    reader = SimpleNamespace(u16=lambda _: 0x1CB, u32=words.__getitem__, f32=lambda _: 0.)
    snapshot = SimpleNamespace(grab_actor=address, cc_move=(0., 0., 0.),
                               link_co_center=(0., 0., 0.), link_co_radius=30., link_co_height=100.)
    observer = ObjectObserver()
    held = observer(reader, snapshot)
    words[address + 0x678] = 2
    snapshot.grab_actor = 0
    released = observer(reader, snapshot)
    assert held["holding"] and held["prop_mode"] == 4
    assert not released["holding"] and released["prop_mode"] == 2


def test_live_retained_clip_survives_internal_pose_model_mismatch():
    plane = SimpleNamespace(func=lambda pos: 5. - pos[0])
    context = SimpleNamespace(facing_ranges=FacingRanges(), roll_on_clip=True,
                              roll_facing_ranges=FacingRanges.parse("37000-43000"),
                              oob_min_speed=0., require_oob=False)
    f = SimpleNamespace(dispatch_row=1, context=context,
                        seam=SimpleNamespace(S=(5., 0.), wA=SimpleNamespace(pla=plane),
                                             wB=SimpleNamespace(pla=plane)))
    records = [dict(pos=[0., 0., 0.], facing=0, state=6,
                    extra=dict(holding=True, prop_pos=[1., 2., 3.])),
               dict(pos=[0., 0., 0.], facing=0, state=6, speed=15.,
                    extra=dict(holding=False, prop_pos=[4., 5., 6.], cc_move=[10., 0., 0.])),
               dict(pos=[10., 0., 0.], facing=40000, state=30, speed=16.),
               dict(pos=[11., 0., 0.], facing=40000, state=36)]
    probe = dict(pose=SimpleNamespace(held_prop_pos=(1., 2., 4.)),
                 prop=(4., 5., 6.), push=(10., 0., 0.))
    assert validate_live_object_outcome(f, records, probe, dict(pos=[10., 0., 0.])) == (False, 1)
    assert validate_live_object_outcome(f, records, probe, dict(pos=[9., 0., 0.])) == (False, 1)
    records[2]["pos"] = [10., 0., 3.]
    with pytest.raises(RuntimeError, match="missed seam"):
        validate_live_object_outcome(f, records, probe, dict(pos=[10., 0., 0.]))
    records[2]["pos"] = [10., 0., 0.]
    records[-1]["pos"] = [0., 0., 0.]
    with pytest.raises(RuntimeError, match="popped back"):
        validate_live_object_outcome(f, records, probe, dict(pos=[10., 0., 0.]))


def family():
    f = object.__new__(DropFamily)
    f.base_rows = [dict(stickX=128, stickY=240, substickX=128, substickY=100,
                        buttons=0, triggerL=0, triggerR=0) for _ in range(10)]
    f.base_rows[0]["buttons"] = 0x100
    f.base_rows[4]["buttons"] = 0x200
    f.control_rows = (3, 4, 5, 6)
    f.anchor_row, f.input_delay = 4, 2
    f.dispatch_row, f.button_row = 7, 5
    f.replay_cache = OrderedDict()
    f.cache_hits = f.native_replays = 0
    f.archive = []
    f.rejections = {}
    f.export_check = False
    f.live_proofs = {}
    f.context = SimpleNamespace()
    return f


def test_authored_rows_retime_b_preserve_prefix_and_edit_all_four_axes():
    f = family()
    original = copy.deepcopy(f.base_rows)
    values = tuple(range(64, 80))
    rows = f.rows_from_controls(values)
    assert f.base_rows == original
    assert rows[0] == original[0]
    assert [i for i, row in enumerate(rows) if row["buttons"] & 0x200] == [5]
    assert [rows[3][key] for key in ("stickX", "stickY", "substickX", "substickY")] == list(values[:4])
    with pytest.raises(ValueError):
        f.rows_from_controls((300,) * 16)
    with pytest.raises(ValueError):
        f.rows_from_controls((128,) * 15)


def test_roll_input_follows_drop_edge_without_changing_original_mode():
    f = family()
    f.base_rows[5]["buttons"] |= 0x100
    f.base_rows[7].update(stickX=0, stickY=0)
    f.base_rows[8].update(stickX=255, stickY=255)
    ordinary = f.rows_from_controls(f.controls_from_rows())
    assert ordinary[5]["buttons"] & 0x100
    f.context.roll_on_clip = True
    rows = f.rows_from_controls(f.controls_from_rows())
    assert rows[5]["buttons"] == 0x200
    assert rows[6]["buttons"] & 0x100
    assert rows[0]["buttons"] & 0x100
    assert rows[7]["buttons"] & 0x100 == 0
    assert (rows[7]["stickX"], rows[7]["stickY"]) == (rows[6]["stickX"], rows[6]["stickY"])
    assert (rows[8]["stickX"], rows[8]["stickY"]) == (rows[6]["stickX"], rows[6]["stickY"])


def test_roll_search_seeds_the_requested_push_frame_headings():
    f = family()
    f.camera = 33458
    f.context.path_archive = []
    f.context.warm = None
    f.context.roll_on_clip = True
    f.context.roll_facing_ranges = FacingRanges.parse("37000-43000")
    starts = list(f.local_starts(5, 0))
    assert len(starts) == 5
    assert len({item[-4:-2] for item in starts}) == 5
    assert all(item[:-4] == starts[0][:-4] for item in starts)


def test_movement_replay_keeps_b_target_and_throw_edges_for_native_dispatch():
    f = family()
    pad = dict(item_button=1 | 2 | 32, hold=0x100 | 0x80 | 0x800, target=True)
    f._effective_rows = lambda rows, end: [dict(pad)]
    effective = f.movement_rows(f.controls_from_rows())
    assert effective == [pad]


def test_native_roundtrip_restores_float32():
    frame = rounded_frame(dict(pos=[591.940247, 0, -1378.40344], speed=17., under=[]))
    assert frame["pos"] == [591.9402465820312, 0., -1378.4034423828125]


def test_rooted_drop_pose_accepts_only_one_vertical_float32_step():
    live = (-119986.21875, 1215.372802734375, 99950.75)
    one_step = (-119986.21875, 1215.3729248046875, 99950.75)
    two_steps = (-119986.21875, 1215.373046875, 99950.75)
    assert object_route.release_position_y_ulp_error(live, live) == 0
    assert object_route.release_position_y_ulp_error(one_step, live, rooted=True) == 1
    assert object_route.release_position_y_ulp_error(one_step, live) is None
    assert object_route.release_position_y_ulp_error(two_steps, live, rooted=True) is None
    assert object_route.release_position_y_ulp_error(
        (one_step[0] + 0.0078125, one_step[1], one_step[2]), live, rooted=True) is None


def test_moving_drop_replay_tolerates_only_bounded_speed_rounding():
    frame = dict(state=6, pos=[1., 2., 3.], facing=100, speed=17.,
                 camera_eye=[4., 5., 6.], camera_center=[7., 8., 9.])
    captured = dict(state=6, x=1., y=2., z=3., facing=100,
                    speed_f=fp.f32(17.00002098083496),
                    camera_eye=frame["camera_eye"], camera_center=frame["camera_center"])
    assert object_route.validate_drop_replay([frame], [captured]) == 11
    with pytest.raises(RuntimeError, match="speed diverged"):
        object_route.validate_drop_replay([frame], [dict(captured, speed_f=17.001)])
    with pytest.raises(RuntimeError, match="position diverged"):
        object_route.validate_drop_replay([frame], [dict(captured, x=2.)])


def test_layered_pose_can_start_at_native_root_matrix(monkeypatch):
    identity = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.]]
    monkeypatch.setattr(dr, "_layered_local_joint", lambda *args, **kwargs:
                        (identity, (1., 1., 1.)))
    root = [[1., 0., 0., 7.], [0., 1., 0., 12.], [0., 0., 1., -3.]]
    skeleton = {"joints": [{"index": 0, "parent": -1}]}
    result = dr._layered_joint_translation(
        {}, {}, {}, "grabwait", 0., skeleton, (0., 0., 0.), 0, 0,
        root_matrix=root)
    assert result == (7., 12., -3.)


def test_lower_pose_uses_draw_clocks_and_active_blend():
    pose = lower_pose(dict(under=[dict(name="walk.bck", active=True, pose_frame=1.5),
                                  dict(name="dash.bck", active=True, pose_frame=2.5, ratio=0.75)]))
    assert pose == dict(move0="walk", move1="dash", f0=1.5, f1=2.5, ratio=0.75)


class Plane:
    def func(self, position):
        return -position[2]


def probe():
    return dict(release=dict(pos=[0., 0., -1.], state=6, facing=0, travel=0, speed=17.),
                raw=[0., -2., 1.], push=[0., 0., 1.], pose=SimpleNamespace(held_prop_pos=(0., 100., -1.)))


def test_native_collision_not_ray_proximity_is_the_acceptance_authority():
    f = family()
    f.variable_start = 5
    f.seam = SimpleNamespace(S=(0., 0.), wA=SimpleNamespace(pla=Plane()), wB=SimpleNamespace(pla=Plane()))
    projection = dict(pos=[0., 0., 1.], wall_hit=False, line_hit=False)
    assert f.result((), probe(), projection, "test").exact
    for field in ("wall_hit", "line_hit"):
        assert not f.result((), probe(), dict(projection, **{field: True}), "test").exact
    assert not f.result((), probe(), dict(projection, pos=[fp.f32(1e-6), 0., 1.]), "test").exact
    other = probe()
    other["raw"] = [0., 0., -0.5]
    assert not f.result((), other, dict(projection, pos=other["raw"]), "test").exact


def test_drop_ranking_does_not_require_a_sword_slash_state():
    item = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., .1, 0., 0)
    assert item.score < 1
    assert replace(item, state=-1).score > 100000


def test_clean_near_miss_beats_ray_perfect_wall_collision():
    near = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., .19, 0., 0)
    blocked = replace(near, ray_error=.00001, collision_error=57.8)
    assert near.score < blocked.score
    assert replace(near, ray_error=4.).score > blocked.score
    assert replace(blocked, collision_error=36.).score < blocked.score


def test_drop_beam_keeps_clean_route_among_many_blocked_near_rays():
    base = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., 0., 0., 0)
    blocked = [replace(base, controls=(index,), ray_error=index / 10000.,
                       collision_error=36., facing=index * 128) for index in range(40)]
    clean = replace(base, controls=(99,), ray_error=50., collision_error=0.)
    chosen = object_route.diverse_results([*blocked, clean], 24)
    assert clean in chosen


def test_non_oob_drop_timings_keep_neighboring_releases_even_when_ray_is_worse():
    frontier = []
    for dispatch, ray in ((14, 10.), (15, .1), (16, .01), (17, 6.), (18, 8.), (29, .02)):
        result = DropResult(False, "test", dispatch + 1, dispatch, 3, (), (0., 0.),
                            (0., 1.), 6, 0, 0, 17., ray, 0., 0)
        frontier.append((result, SimpleNamespace(dispatch_row=dispatch, from_start=True)))
    chosen = object_route.drop_plan_choices(frontier, False, 15)
    assert {family.dispatch_row for _, family in chosen} >= {14, 15, 16, 17}


def test_drop_gui_keeps_all_route_settings_in_a_separate_file():
    assert MovingObjectGUI.settings_path != NativeRouteGUI.settings_path
    assert set(MovingObjectGUI.setting_keys) == (set(NativeRouteGUI.setting_keys) - {"mode"}
                                                | {"require_oob", "oob_tolerance", "oob_min_speed",
                                                   "roll_on_clip", "roll_facing_ranges"})
    assert "moving_object_route" in str(MovingObjectGUI.settings_path)


def constrained_family():
    f = family()
    f.variable_start = 5
    f.seam = SimpleNamespace(S=(0., 0.), wA=SimpleNamespace(pla=Plane()), wB=SimpleNamespace(pla=Plane()))
    return f


def test_drop_uses_release_facing_not_travel_or_later_facing():
    f = constrained_family()
    f.context.facing_ranges = FacingRanges.parse("65000-100")
    p = probe()
    p["release"].update(facing=65535, travel=32768)
    projection = dict(pos=[0., 0., 1.], flags=0x20, wall_hit=False, line_hit=False)
    assert f.result((), p, projection, "test").exact
    p["release"]["facing"] = 101
    item = f.result((), p, projection, "test")
    assert not item.exact and item.aim_error == 1


def test_roll_range_is_checked_on_push_frame_not_release_frame():
    f = constrained_family()
    f.context.roll_on_clip = True
    f.context.roll_facing_ranges = FacingRanges.parse("37000-43000")
    p = probe()
    p["consume"] = dict(facing=40000, state=30)
    projection = dict(pos=[0., 0., 1.], flags=0x20, wall_hit=False, line_hit=False)
    result = f.result((), p, projection, "test")
    assert result.exact and result.roll_facing == 40000
    p["consume"]["facing"] = 36000
    result = f.result((), p, projection, "test")
    assert not result.exact and result.roll_error == 1000
    p["consume"]["facing"] = 40000
    f.context.oob_min_speed = 13.
    p["release"]["speed"] = 12.
    result = f.result((), p, projection, "test")
    assert not result.exact and result.speed_error == 1.


def test_live_roll_checks_pre_push_speed_even_without_oob_landing():
    from harness.collision.object_route_capture import verify_drop_constraints

    f = constrained_family()
    f.context.roll_on_clip = True
    f.context.roll_facing_ranges = FacingRanges.parse("37000-43000")
    f.context.oob_min_speed = 13.
    consume = dict(state=30, facing=40000, pos=[0., 0., 1.], speed=26.)
    verify_drop_constraints(f, dict(facing=0, speed=13.), consume)
    with pytest.raises(RuntimeError, match="pre-push speed"):
        verify_drop_constraints(f, dict(facing=0, speed=12.), consume)


def test_roll_mode_requires_front_roll_on_consuming_frame(monkeypatch):
    f = family()
    f.dispatch_row = 6
    f.context.roll_on_clip = True
    f.context.kind = "pot_small"
    f.context.anims = {}
    f.context.skeleton = None
    f.context.prop_executes_after_link = False
    monkeypatch.setattr(object_route, "lower_pose", lambda _: {})
    monkeypatch.setattr(object_route.dr, "decomp_moving_b_drop_pose", lambda *a, **kw: object())
    held = dict(released=False, pose_morf=0, pos=[0., 0., 0.], facing=0,
                upper_frame=0, draw_lean=0, body_lean=0)
    released = dict(held, released=True, state=6, speed=17.)
    consume = dict(released, state=30)
    assert f._release_pose([held, released, consume])["consume"]["state"] == 30
    with pytest.raises(RuntimeError, match="post-drop roll"):
        f._release_pose([held, released, dict(consume, state=6)])


def test_oob_landing_requires_ground_both_wall_sides_proximity_and_clip_speed_floor():
    f = constrained_family()
    f.context.require_oob = True
    f.context.oob_tolerance = 1.
    p = dict(probe(), consume_speed=17.)
    projection = dict(pos=[0., 0., 1.], flags=0x20, wall_hit=False, line_hit=False)
    result = f.result((), p, projection, "test")
    assert result.exact and result.landing_distance == 1. and result.landing_speed == 17.
    assert not f.result((), p, dict(projection, flags=0), "test").exact
    f.context.oob_tolerance = .99
    assert not f.result((), p, projection, "test").exact
    f.context.oob_tolerance = 1.
    assert not f.result((), dict(p, consume_speed=14.49999), projection, "test").exact
    p["release"]["speed"] = 1.
    slower = f.result((), dict(p, consume_speed=14.5), projection, "test")
    assert slower.exact and slower.score > result.score
    for speed in (14.5, 15., 16.5, 17., 18.):
        assert f.result((), dict(p, consume_speed=speed), projection, "test").exact
    f.context.oob_min_speed = 0.
    assert f.result((), dict(p, consume_speed=12.), projection, "test").exact
    f.context.oob_min_speed = 14.5
    p["release"]["speed"] = 17.
    f.seam.wB.pla = SimpleNamespace(func=lambda pos: -pos[2] if pos[2] < 0 else .01)
    assert not f.result((), p, projection, "test").exact


def test_live_verification_rechecks_angle_ground_and_landing_speed():
    from harness.collision.object_route_capture import verify_drop_constraints

    f = constrained_family()
    f.context.facing_ranges = FacingRanges.parse("100-200")
    f.context.require_oob, f.context.oob_tolerance = True, 1.
    released = dict(facing=150, speed=1.)
    consume = dict(pos=[0., 0., 1.], speed=14.5, grounded=True)
    verify_drop_constraints(f, released, consume)
    for record in (dict(consume, speed=14.4), dict(consume, grounded=False),
                   dict(consume, pos=[0., 0., 1.1])):
        with pytest.raises(RuntimeError, match="minimum clip speed"):
            verify_drop_constraints(f, released, record)
    with pytest.raises(RuntimeError, match="pre-push facing"):
        verify_drop_constraints(f, dict(released, facing=201), consume)


def test_live_verifier_only_patches_through_required_follow_through():
    owner = SimpleNamespace(dispatch_row=26,
                            context=SimpleNamespace(runtime_polls=194604),
                            route=SimpleNamespace(poll_spans=[(194466 + 4 * i, 194470 + 4 * i)
                                                               for i in range(36)]))
    assert verification_row_count(owner, [{}] * 36) == 30
    owner.context.runtime_polls = owner.route.poll_spans[29][1] - 1
    with pytest.raises(RuntimeError, match="original DTM ends"):
        verification_row_count(owner, [{}] * 36)


def test_export_refuses_a_nonreproducing_clip(tmp_path):
    f = family()
    f.worker = SimpleNamespace(workers=6)
    item = DropResult(True, "test", 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., 0., 0., 0)
    f.evaluate = lambda values, phase: replace(item, exact=False)
    with pytest.raises(RuntimeError, match="single-worker"):
        f.export(item, tmp_path / "clip.dtm")
    assert f.worker.workers == 6
    assert not (tmp_path / "clip.dtm").exists()


def release_frames():
    under = [dict(name="walk.bck", active=True, pose_frame=1., ratio=1.),
             dict(name="dash.bck", active=False, pose_frame=1., ratio=0.)]
    common = dict(state=6, speed=17., facing=0, under=under, upper_frame=0.,
                  draw_lean=0, body_lean=0, pose_morf=0.)
    return [dict(common, pos=[0., 0., -2.], released=False),
            dict(common, pos=[0., 0., -1.], released=True),
            dict(common, pos=[20., 0., 20.], raw=[0., -2., 1.], released=True)]


def test_release_adds_push_to_uncorrected_native_motion_before_collision(monkeypatch):
    f = family()
    f.anchor_row = 5
    f.context = SimpleNamespace(kind="pot_small", anims={}, skeleton={}, prop_executes_after_link=False)
    pose = SimpleNamespace(held_prop_pos=(0., 100., -1.), link_co_center=(0., 0., -1.),
                           link_co_radius=30., link_co_height=100.)
    monkeypatch.setattr(object_route.dr, "decomp_moving_b_drop_pose", lambda *args, **kwargs: pose)
    monkeypatch.setattr(object_route, "co_push_link", lambda *args, **kwargs: (2., 0., 40.))
    probe, query = f.release_probe(release_frames())
    assert probe["raw"] == [2., -2., 41.]
    assert query["old"] == [0., 0., -1.]
    assert query["speed"] == [0., -2., 2.]
    assert query["raw"] != [22., 0., 60.]


@pytest.mark.parametrize("change", ["early", "not_released", "morph", "nonmoving"])
def test_release_rejects_unmodeled_or_wrong_timing(change):
    f = family()
    f.anchor_row = 5
    frames = release_frames()
    if change == "early":
        frames[0]["released"] = True
    elif change == "not_released":
        frames[1]["released"] = False
    elif change == "morph":
        frames[0]["pose_morf"] = .5
    else:
        frames[1]["speed"] = 0.
    with pytest.raises(RuntimeError):
        f.release_probe(frames)


def test_first_free_prop_execution_order_is_simulated_not_calibrated(monkeypatch):
    f = family()
    f.anchor_row = 5
    f.context = SimpleNamespace(kind="bomb", anims={}, skeleton={}, prop_executes_after_link=True)
    pose = SimpleNamespace(held_prop_pos=(0., 100., -1.), link_co_center=(0., 0., -1.),
                           link_co_radius=30., link_co_height=100.)
    monkeypatch.setattr(object_route.dr, "decomp_moving_b_drop_pose", lambda *args, **kwargs: pose)
    queries = []
    f.worker = SimpleNamespace(project=lambda q: queries.extend(q) or [{"pos": [0., fp.fadds(100., -2.9), -1.]}])
    monkeypatch.setattr(object_route, "co_push_link", lambda *args, **kwargs: (0., 0., 40.))
    f.release_probe(release_frames())
    assert queries[0]["object_type"] == "bomb"
    assert queries[0]["raw"] == [0., fp.fadds(100., -2.9), -1.]


def test_pot_release_corrects_walls_without_advancing_gravity(monkeypatch):
    f = family()
    f.anchor_row = 5
    f.context = SimpleNamespace(kind="pot_small", anims={}, skeleton={}, prop_executes_after_link=True)
    pose = SimpleNamespace(held_prop_pos=(0., 100., -1.), link_co_center=(0., 0., -1.),
                           link_co_radius=30., link_co_height=100.)
    monkeypatch.setattr(object_route.dr, "decomp_moving_b_drop_pose", lambda *args, **kwargs: pose)
    queries, centers = [], []
    f.worker = SimpleNamespace(project=lambda q: queries.extend(q) or [{"pos": [4., 100., -3.]}])
    monkeypatch.setattr(object_route, "co_push_link",
                        lambda *args, **kwargs: centers.append(args[3]) or (0., 0., 40.))
    probe, _ = f.release_probe(release_frames())
    assert queries == [dict(old=[0., 100., -1.], raw=[0., 100., -1.],
                           speed=[0., 0., 0.], object_type="pot_small")]
    assert probe["prop"] == [4., 100., -3.]
    assert centers == [[4., 100., -3.]]


def test_camera_plans_are_short_pulses_and_have_varied_speed_schedules():
    f = family()
    f.context = SimpleNamespace(warm=None, path_archive=[], identity="test")
    f.start_seed = dict(pos=[0., 0., 0.])
    f.seam = SimpleNamespace(S=(0., 100.))
    f.camera = 0
    plans = list(f.route_starts(120, 17))
    initial = f.controls_from_rows()
    assert plans == list(f.route_starts(120, 17))
    camera_shapes = {tuple(plan[i + 2:i + 4] for i in range(0, len(plan), 4)) for plan in plans}
    assert len(camera_shapes) > 12
    assert any(1 <= sum(plan[i + 2:i + 4] != initial[i + 2:i + 4]
                       for i in range(0, len(plan), 4)) <= 3 for plan in plans)
    assert any(len(set(plan[i:i + 2] for i in range(0, len(plan), 4))) > 1 for plan in plans)


def test_coupled_variance_changes_multiple_rows_and_sticks_without_invalid_bytes():
    import random
    initial = (128,) * 24
    axes = tuple(range(22))
    plans = object_route.coupled_trials(initial, axes, random.Random(12), 400, 4)
    assert any(sum(a != b for a, b in zip(initial, plan)) >= 3 for plan in plans)
    assert any(any(plan[i] != 128 for i in (2, 3)) and any(plan[i] != 128 for i in (0, 1)) for plan in plans)
    assert all(plan[-2:] == (128, 128) for plan in plans)
    assert all(0 <= value <= 255 for plan in plans for value in plan)
    assert object_route.coupled_trials(initial, (), random.Random(1), 3, 2) == []


def test_frontier_keeps_other_headings_not_just_the_smallest_rays():
    item = DropResult(False, "test", 7, 5, 3, (128,) * 16,
                      (0., -1.), (0., 1.), 6, 0, 0, 17., .001, 0., 0)
    nearby = [replace(item, controls=(i,) * 16, ray_error=.001 + i * .00001) for i in range(10)]
    different = replace(item, controls=(200,) * 16, facing=512, ray_error=.01)
    chosen = object_route.diverse_results([*nearby, different], 3)
    assert nearby[0] in chosen and different in chosen


def test_polish_continues_after_flat_one_byte_probes_and_uses_remaining_budget():
    f = family()
    f.seam = SimpleNamespace(S=(0., 0.))
    f.cancelled = lambda: False
    initial = (128,) * 16
    item = DropResult(False, "test", 7, 5, 3, initial,
                      (0.001, -1.), (0.001, 1.), 6, 0, 0, 17., .001, 0., 0)
    tried = []

    def evaluate(values, *args):
        tried.extend(values)
        return (replace(item, controls=tuple(value)) for value in values)

    f.evaluate_many = evaluate
    best, count = f.polish([item], 900, "test", False, lambda message: None)
    assert best == item
    assert count == len(tried) == 900
    assert len(set(tried)) == len(tried)
    assert any(sum(a != b for a, b in zip(initial, value)) >= 3 for value in tried)


def test_oob_polish_yields_when_landing_is_stalled():
    f = family()
    f.context.require_oob = True
    f.seam = SimpleNamespace(S=(0., 0.))
    f.cancelled = lambda: False
    initial = (128,) * 16
    item = DropResult(False, "test", 7, 5, 3, initial,
                      (0., -1.), (0., 1.), 6, 0, 0, 17., .00001, 0., 0,
                      landing_error=62., grounded=False)
    tried = []

    def evaluate(values, *args):
        tried.extend(values)
        return (replace(item, controls=tuple(value)) for value in values)

    f.evaluate_many = evaluate
    best, count = f.polish([item], 10000, "test", False, lambda message: None)
    assert best == item and count == len(tried)
    assert 4000 <= count < 5000


def test_blocked_drop_polish_yields_to_other_timings():
    f = family()
    f.seam = SimpleNamespace(S=(0., 0.))
    f.cancelled = lambda: False
    item = DropResult(False, "test", 7, 5, 3, (128,) * 16,
                      (0., -1.), (0., 1.), 6, 0, 0, 17., 1., 0., 0,
                      collision_error=42.)
    f.evaluate_many = lambda values, *args: (
        replace(item, controls=tuple(value)) for value in values)
    best, count = f.polish([item], 10000, "test", False, lambda message: None)
    assert best == item
    assert 2048 <= count < 3000


def test_near_ray_drop_keeps_float_precision_budget_despite_wall_correction():
    f = family()
    f.seam = SimpleNamespace(S=(0., 0.))
    f.cancelled = lambda: False
    item = DropResult(False, "test", 7, 5, 3, (128,) * 16,
                      (0., -1.), (0., 1.), 6, 0, 0, 17., .00001, 0., 0,
                      collision_error=42.)
    f.evaluate_many = lambda values, *args: (
        replace(item, controls=tuple(value)) for value in values)
    _, count = f.polish([item], 3000, "test", False, lambda message: None)
    assert count == 3000


def test_near_ray_alternate_keeps_precision_budget_when_fast_path_scores_best():
    f = family()
    f.seam = SimpleNamespace(S=(0., 0.))
    f.cancelled = lambda: False
    fast = DropResult(False, "test", 7, 5, 3, (128,) * 16,
                      (0., -1.), (0., 1.), 6, 0, 0, 17., .1, 0., 0)
    near = replace(fast, controls=(127,) * 16, ray_error=.0001,
                   collision_error=42., speedf=4., speed_preference=13.)
    f.evaluate_many = lambda values, *args: (
        replace(fast, controls=tuple(value)) for value in values)
    _, count = f.polish([fast, near], 3000, "test", False, lambda message: None)
    assert count == 3000


def test_replan_families_cover_speed_and_delayed_drop_timings():
    base = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.),
                      6, 0, 0, 17., .01, 0., 0)
    frontier = [(replace(base, ray_error=.01 + dispatch, speedf=float(dispatch)),
                 SimpleNamespace(dispatch_row=dispatch, from_start=True))
                for dispatch in range(10, 25, 2)]
    choices = object_route.drop_replan_choices(frontier, 10)
    assert {owner.dispatch_row for _, owner in choices} >= {10, 14, 18, 22}
    assert len(choices) == len({id(owner) for _, owner in choices})


def test_replan_archive_keeps_faster_path_even_when_ray_score_is_worse():
    base = DropResult(False, "test", 7, 5, 3, (1,), (0., 0.), (0., 1.),
                      6, 0, 0, 4., .001, 0., 0)
    fast = replace(base, controls=(2,), speedf=17., ray_error=.1)
    owner = SimpleNamespace(dispatch_row=6, archive=[base, fast],
                            control_metadata=lambda: {"control_rows": [5]})
    paths = object_route.drop_path_archive([(base, owner)])
    assert {tuple(path["controls"]) for path in paths} == {(1,), (2,)}


def test_roll_drop_score_prefers_speed_without_excluding_slow_exact_clips():
    slow = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.),
                      6, 0, 0, 4., .0001, 0., 0, speed_preference=13.)
    fast = replace(slow, speedf=13., ray_error=.001, speed_preference=4.)
    assert fast.score < slow.score
    assert replace(slow, exact=True).score < fast.score


def test_inactionable_release_stops_before_full_timing_budget():
    item = DropResult(False, "test", 7, 5, 3, (128,) * 16,
                      (0., -1.), (0., 1.), -1, 0, 0, 0., 1e10, 1e10, 0)
    f = SimpleNamespace(from_start=False, archive=[], axes=tuple(range(16)),
                        dispatch_row=6, context=SimpleNamespace(require_oob=False),
                        cancelled=lambda: False, controls_from_rows=lambda: item.controls,
                        local_starts=lambda limit, seed: (),
                        evaluate_many=lambda values, *args: (
                            replace(item, controls=tuple(value)) for value in values),
                        polish=lambda *args: pytest.fail("inactionable release was polished"))
    best, count = object_route.search_drop_family(f, 10000, 1, lambda message: None)
    assert best.state == -1
    assert count < 4000


def test_oob_plan_choices_include_delayed_drop_frames():
    base = DropResult(False, "test", 7, 5, 3, (), (0., 0.), (0., 1.),
                      6, 0, 0, 17., .01, 0., 0)
    frontier = [(replace(base, landing_error=float(dispatch)),
                 SimpleNamespace(dispatch_row=dispatch, from_start=True))
                for dispatch in range(10, 21)]
    choices = object_route.drop_plan_choices(frontier, True, 10)
    assert {owner.dispatch_row for _, owner in choices} >= set(range(11, 19))
    assert len(choices) == len({id(owner) for _, owner in choices})


def test_near_paths_transfer_into_a_different_drop_timing():
    f = family()
    f.context = SimpleNamespace(identity="same", warm=None, path_archive=[dict(
        control_rows=[3, 4], controls=[130, 200, 140, 100, 132, 201, 130, 100])])
    values = next(f.local_starts(1, 10))
    assert values[:8] == (130, 200, 140, 100, 132, 201, 130, 100)


def test_normalized_route_cache_skips_replay_but_preserves_authored_controls_and_phase():
    f = family()
    f.variable_start = 5
    f.start_seed = {}
    f.seam = SimpleNamespace(S=(0., 0.), wA=SimpleNamespace(pla=Plane()), wB=SimpleNamespace(pla=Plane()))
    calls = []
    f.worker = SimpleNamespace(
        movement=lambda seed, rows: calls.append("movement") or [dict(frames=[dict(camera=0)]) for _ in rows],
        project=lambda queries: calls.append("project") or [dict(pos=[0., 0., 1.], wall_hit=False, line_hit=False)])
    f.movement_rows = lambda controls: [dict(angle=0, distance=1)]
    f.release_probe = lambda frames: (probe(), {})
    first = next(f.evaluate_many([(128,) * 16], "first"))
    second = next(f.evaluate_many([(129,) * 16], "second"))
    assert first.exact and second.exact
    assert second.controls == (129,) * 16 and second.phase == "second"
    assert calls == ["movement", "project"]
    assert f.native_replays == f.cache_hits == 1
    assert f.latest_frames == [dict(camera=0)]


def test_prop_collision_queries_are_batched_before_link_projection():
    f = family()
    f._batch_prop_projection = True
    f.variable_start = 5
    f.start_seed = {}
    f.context.require_oob = False
    f.movement_rows = lambda controls: [dict(angle=controls[0])]
    f._release_pose = lambda frames: dict(prop_query=dict(old=[frames[0]["angle"], 0., 0.]))
    f._finish_release = lambda setup, prop: (probe(), dict(old=prop))
    f.result = lambda controls, prepared, projected, phase: DropResult(
        False, phase, 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., .1, 0., 0)
    calls = []

    def project(queries):
        calls.append(len(queries))
        return [dict(pos=[query["old"][0], 0., 0.]) for query in queries]

    f.worker = SimpleNamespace(
        movement=lambda seed, rows: [dict(frames=[dict(angle=row[0]["angle"])]) for row in rows],
        project=project)
    results = list(f.evaluate_many([(128,) * 16, (129,) * 16]))
    assert [item.controls[0] for item in results] == [128, 129]
    assert calls == [2, 2]


def test_single_worker_export_bypasses_search_cache(tmp_path):
    f = family()
    f.worker = SimpleNamespace(workers=6)
    f.replay_cache["cached"] = "not a fresh proof"
    item = DropResult(True, "test", 7, 5, 3, (), (0., 0.), (0., 1.), 6, 0, 0, 17., 0., 0., 0)

    def check(values, phase):
        assert f.worker.workers == 1 and not f.replay_cache
        return replace(item, exact=False)

    f.evaluate = check
    with pytest.raises(RuntimeError, match="single-worker"):
        f.export(item, tmp_path / "clip.dtm")


def test_live_failure_rejects_only_that_candidate_and_continues(tmp_path):
    f = family()
    f.variable_start = 5
    f.start_seed = {}
    f.cancelled = lambda: False
    f.seam = SimpleNamespace(S=(0., 0.), wA=SimpleNamespace(pla=Plane()), wB=SimpleNamespace(pla=Plane()))
    f.worker = SimpleNamespace(
        movement=lambda seed, rows: [dict(frames=[]) for row in rows],
        project=lambda queries: [dict(pos=[0., 0., 1.], wall_hit=False, line_hit=False) for query in queries])
    f.movement_rows = lambda controls: [dict(angle=controls[0])]
    f.release_probe = lambda frames: (probe(), {})
    verified = []

    def verify(owner, item):
        verified.append(item.controls[0])
        if item.controls[0] == 128:
            raise RuntimeError("live first push endpoint differs from simulation")
        return dict(live_verified=True)

    messages = []
    f.context = SimpleNamespace(accept_exact=verify, failed_live_movies=set(),
                                live_failure_counts={}, log=messages.append,
                                diagnostic_path=tmp_path / "last_live_rejection.json")
    items = list(f.evaluate_many([(128,) * 16, (129,) * 16]))
    assert not items[0].exact and items[1].exact
    assert verified == [128, 129]
    assert f.live_proofs[(129,) * 16]["live_verified"]
    assert not next(f.evaluate_many([(128,) * 16])).exact
    assert verified == [128, 129]
    f.replay_cache.clear()
    assert not next(f.evaluate_many([(128,) * 16])).exact
    assert verified == [128, 129]
    assert "live first push endpoint differs" in messages[0]
    assert "live first push endpoint differs" in f.context.diagnostic_path.read_text()
    assert any("live candidate rejected" in reason for reason in f.rejections)


def test_unavailable_runtime_movie_aborts_instead_of_reloading_forever():
    f = family()
    f.cancelled = lambda: False
    f.context.accept_exact = lambda owner, item: (_ for _ in ()).throw(
        RuntimeError("runtime DTM row 194605 is unavailable"))
    item = DropResult(True, "test", 7, 5, 3, (128,) * 16,
                      (0., 0.), (0., 1.), 6, 0, 0, 17., 0., 0., 0)
    with pytest.raises(RuntimeError, match="live movie verification cannot continue"):
        f._verify_exact(item)


def test_live_verification_budget_stops_repeated_dolphin_reloads(tmp_path):
    f = family()
    f.cancelled = lambda: False
    attempts = []

    def reject(owner, item):
        attempts.append(item.controls)
        raise RuntimeError("live push missed seam")

    f.context = SimpleNamespace(accept_exact=reject, failed_live_movies=set(),
                                live_failure_counts={}, live_attempts=0, max_live_attempts=2,
                                log=lambda message: None,
                                diagnostic_path=tmp_path / "last_live_rejection.json")
    item = DropResult(True, "test", 7, 5, 3, (128,) * 16,
                      (0., 0.), (0., 1.), 6, 0, 0, 17., 0., 0., 0.)
    assert not f._verify_exact(item).exact
    assert not f._verify_exact(replace(item, controls=(129,) * 16)).exact
    with pytest.raises(RuntimeError, match="stopped after 2 distinct live tests"):
        f._verify_exact(replace(item, controls=(130,) * 16))
    assert len(attempts) == 2


@pytest.mark.parametrize("reject_fastest", [False, True])
def test_oob_batch_prioritizes_fastest_exact_landing_and_keeps_probe_order(reject_fastest):
    f = constrained_family()
    f.start_seed = {}
    f.cancelled = lambda: False
    f.context.require_oob, f.context.oob_tolerance = True, 1.
    speeds = {128: 14.5, 129: 17.}
    f.worker = SimpleNamespace(
        movement=lambda seed, rows: [dict(frames=[dict(speed=speeds[route[0]["angle"]])]) for route in rows],
        project=lambda queries: [dict(pos=[0., 0., 1.], flags=0x20, wall_hit=False, line_hit=False)
                                 for query in queries])
    f.movement_rows = lambda controls: [dict(angle=controls[0])]
    f.release_probe = lambda frames: (dict(probe(), consume_speed=frames[0]["speed"]), {})
    verified = []

    def verify(owner, item):
        verified.append(item.landing_speed)
        if reject_fastest and item.landing_speed == 17.:
            raise RuntimeError("live prediction mismatch")
        return dict(live_verified=True)

    f.context.accept_exact = verify
    items = list(f.evaluate_many([(128,) * 16, (129,) * 16]))
    assert [item.controls[0] for item in items] == [128, 129]
    if reject_fastest:
        assert verified == [17., 14.5] and items[0].exact and not items[1].exact
    else:
        assert verified == [17.] and not items[0].exact and items[1].exact
