"""Offline controller tests. These do not stand in for a live Dolphin replay."""

from collections import deque
from dataclasses import replace
from pathlib import Path
import runpy
import random
import json
import sys
import types
import unittest
from unittest.mock import patch

from harness.dolphin_scripts import extended_ess_core as core


def seed(**changes):
    return replace(core.State(-25.0, 0, 14000, 0, 32768, 32768,
                              17.0, 8.0, core.f32(0.66)), **changes)


class CoreTests(unittest.TestCase):
    def regression_rows(self):
        path = Path(__file__).parents[1] / "fixtures/extended_ess_margin_regression.json"
        return json.loads(path.read_text())["rows"]

    def test_user_start_does_not_sacrifice_speed_for_large_clearance(self):
        row = self.regression_rows()[0]
        for margin in (16, 1024, 8192):
            plan = core.choose_camera(core.State(**row["live"]), core.Pad(**row["held"]),
                                      (core.Pad(**row["queued"]),), margin=margin)
            self.assertIsNotNone(plan)
            self.assertEqual(plan.cx, 128)
            self.assertEqual(plan.loss, plan.neutral_loss)

    def test_all_user_trace_states_are_compared_with_neutral(self):
        steering = 0
        for row in self.regression_rows():
            state, held, queued = (core.State(**row["live"]), core.Pad(**row["held"]),
                                   core.Pad(**row["queued"]))
            plan = core.choose_camera(state, held, (queued,))
            if plan is None:
                continue
            seed_state = core.advance(state, queued).state
            baseline = core.evaluate_sequence(seed_state, held, (128,) * plan.evaluated_frames)
            actual = core.evaluate_sequence(seed_state, held, plan.sequence)
            self.assertIsNotNone(actual)
            self.assertEqual(plan.sequence[1:], (128,) * (plan.evaluated_frames - 1))
            self.assertEqual(plan.loss, actual[0][-1])
            if baseline is not None:
                self.assertEqual(plan.neutral_loss, baseline[0][-1])
                self.assertTrue(all(a <= b for a, b in zip(actual[0], baseline[0])))
                if plan.cx != 128:
                    self.assertLess(plan.loss, plan.neutral_loss)
                    steering += 1
        self.assertGreater(steering, 0)

    def test_user_start_closed_loop_never_loses_more_than_neutral_in_model(self):
        row = self.regression_rows()[0]
        live = baseline = core.State(**row["live"])
        held = core.Pad(**row["held"])
        pending = neutral_pending = core.Pad(**row["queued"])
        for _ in range(96):
            plan = core.choose_camera(live, held, (pending,))
            self.assertIsNotNone(plan)
            live = core.advance(live, pending).state
            baseline = core.advance(baseline, neutral_pending).state
            pending = replace(held, cx=plan.cx)
            neutral_pending = replace(held, cx=128)
            self.assertLessEqual(live.velocity, baseline.velocity)

    def test_captured_live_queue_and_camera_pulse_trace(self):
        path = Path(__file__).parents[1] / "fixtures/extended_ess_camera_pulses.json"
        rows = json.loads(path.read_text())["rows"]
        largest_camera_error = 0
        wrong_queue_errors = []
        for i, (before, after) in enumerate(zip(rows, rows[1:])):
            expected = core.advance(core.State(**before["state"]), core.Pad(*before["queued"])).state
            live = core.State(**after["state"])
            self.assertEqual((expected.velocity, expected.travel, expected.facing, expected.target_yaw),
                             (live.velocity, live.travel, live.facing, live.target_yaw))
            largest_camera_error = max(largest_camera_error,
                                      abs(core.s16_signed(live.controlled - expected.controlled)))
            if i:
                stale = core.advance(core.State(**before["state"]), core.Pad(*rows[i-1]["queued"])).state
                wrong_queue_errors.append(abs(core.s16_signed(live.target_yaw - stale.target_yaw)))
        self.assertEqual(largest_camera_error, 40)
        self.assertGreater(max(wrong_queue_errors), 0)

    def test_player_branch_matches_existing_sim(self):
        from tww_sim.land.procs.move import _MoveMixin
        rng = random.Random(123)
        for _ in range(100):
            pad = core.Pad(rng.choice((108, 110, 146, 148)), 128)
            angle, msd = core.decode(pad.x, pad.y)
            travel = rng.randrange(65536)
            target = (travel + rng.randint(-28000, 28000)) & 0xFFFF
            state = seed(velocity=core.f32(-rng.uniform(13, 100)), travel=travel,
                         facing=rng.randrange(65536), max_speed=rng.choice((12., 17.)),
                         controlled=(target - angle - 0x8000) & 0xFFFF)
            reference = _MoveMixin()
            for key, value in dict(
                msd=msd, target=target, travel=travel, facing=state.facing,
                nspeed=state.velocity, speedF=state.velocity, max_nspeed=state.max_speed,
                state=6, wall_hit=False, F4=100, F6=5, F14=3.5,
                F24=core.f32(.6), F1C=2.5, F20=core.f32(1.8),
            ).items():
                setattr(reference, key, value)
            reference._set_speed_and_angle_normal(3000)
            result = core.advance(state, pad).state
            self.assertEqual((result.velocity, result.travel, result.facing),
                             (reference.nspeed, reference.travel, reference.facing))

    def test_speed_loss_cliff(self):
        safe = core.advance(seed(), core.Pad(110, 128))
        brake = core.advance(seed(controlled=100), core.Pad(110, 128))
        self.assertLess(safe.loss, 0.0001)
        self.assertEqual(brake.loss, 2.5)
        self.assertLess(brake.clearance, 0)

    def test_facing_snap_is_rejected(self):
        # Crossing the signed half-turn boundary relative to travel snaps
        # shape_angle to travel, even though the incremental chase is small.
        step = core.advance(seed(travel=32788, facing=62001, controlled=0),
                            core.Pad(110, 128))
        self.assertIn("snap", step.reason)

    def test_camera_does_not_change_same_frame_speed(self):
        left = core.advance(seed(), core.Pad(110, 128, 90))
        right = core.advance(seed(), core.Pad(110, 128, 166))
        self.assertEqual(left.loss, right.loss)
        self.assertNotEqual(left.state.controlled, right.state.controlled)

    def test_neutral_camera_still_chases_target(self):
        s = seed(target_yaw=33000)
        step = core.advance(s, core.Pad(110, 128))
        self.assertNotEqual(step.state.view_yaw, s.view_yaw)
        self.assertLess(abs(core.s16_signed(step.state.target_yaw - step.state.view_yaw)),
                        abs(core.s16_signed(s.target_yaw - s.view_yaw)))

    def test_committed_yaw_offset_is_retained(self):
        result = core.advance(seed(controlled=40), core.Pad(110, 128, 152)).state
        self.assertEqual(core.s16_signed(result.controlled - result.view_yaw - 0x8000), 40)

    def test_larger_margin_can_be_reached_in_stages(self):
        self.assertIsNotNone(core.choose_camera(seed(), core.Pad(110, 128), margin=2048))

    def test_all_cstick_effects_retained(self):
        for cy in (0, 100, 128, 255):
            all_effects = {core.cstick_normalize(cx, cy)[0] for cx in range(256)}
            retained = {core.cstick_normalize(cx, cy)[0] for cx in core.camera_options(cy)}
            self.assertEqual(all_effects, retained)

    def test_ess_gate(self):
        self.assertTrue(core.ess_input(core.Pad(110, 128)))
        self.assertTrue(core.ess_input(core.Pad(146, 128)))
        self.assertFalse(core.ess_input(core.Pad(128, 128)))
        self.assertFalse(core.ess_input(core.Pad(255, 128)))

    def test_closed_loop_with_two_queued_frames_preserves_speed(self):
        initial = seed()
        live, baseline = initial, initial
        held = core.Pad(110, 128)
        pending = deque([held, held])
        for _ in range(24):
            plan = core.choose_camera(live, held, pending)
            self.assertIsNotNone(plan)
            delivered = pending.popleft()
            pending.append(replace(held, cx=plan.cx))
            step = core.advance(live, delivered)
            self.assertFalse(step.reason)
            self.assertLess(step.loss, 0.001)
            live = step.state
            baseline = core.advance(baseline, held).state
        self.assertLess(live.velocity - initial.velocity,
                        (baseline.velocity - initial.velocity) / 3)

    def test_both_ess_sides_can_be_planned(self):
        self.assertIsNotNone(core.choose_camera(seed(), core.Pad(110, 128)))
        self.assertIsNotNone(core.choose_camera(seed(facing=51536), core.Pad(146, 128)))


class Control:
    def __init__(self, value=None, checked=False):
        self.value = value
        self.checked = checked
    def set(self, value):
        self.value = value


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.buttons = dict(StickX=110, StickY=128, CStickX=128, CStickY=128,
                            A=False, L=False, TriggerLeft=0, Connected=True)
        self.frame = 10
        window = types.SimpleNamespace(
            checkbox=lambda label, checked: Control(checked=checked),
            input_text=lambda label, value: Control(value),
            text=lambda value: Control(value),
            button=lambda label: types.SimpleNamespace(clicked=False),
        )
        dolphin = types.ModuleType("dolphin")
        dolphin.gui = types.SimpleNamespace(window=lambda name: window)
        dolphin.event = types.SimpleNamespace(**{name: lambda fn: fn for name in (
            "on_hostupdate", "on_savestateload", "on_frameadvance")})
        dolphin.controller = types.SimpleNamespace(
            get_gc_buttons=lambda port: dict(self.buttons),
            set_gc_buttons=lambda port, data: self.writes.append(dict(data)),
        )
        dolphin.memory = types.SimpleNamespace(read_u32=lambda addr: self.frame)
        path = Path(__file__).parents[1] / "harness/dolphin_scripts/Extended ESS.py"
        with patch.dict(sys.modules, {"dolphin": dolphin, "extended_ess_core": core}):
            self.module = runpy.run_path(str(path))
        # run_path returns a shallow copy; functions retain the executing globals.
        self.g = self.module["update"].__globals__
        self.g["snapshot"] = lambda: seed()
        self.queued = core.Pad(110, 128, 101, 128)
        self.g["polled_pad"] = lambda: self.queued
        self.g["save_trace"] = lambda: "mock diagnostics"
        self.g["choose_camera"] = lambda *a, **k: core.Plan(152, .001, 16, (152,) * 4)

    def enable(self):
        self.g["_toggle"].checked = True
        self.g["host_update"]()

    def test_disabled_does_not_touch_controller(self):
        self.g["update"]()
        self.assertEqual(self.writes, [])

    def test_only_cstick_x_changes_and_duplicate_vi_reissues(self):
        self.enable()
        self.g["update"]()
        self.g["update"]()
        self.assertEqual(len(self.writes), 2)
        for output in self.writes:
            self.assertEqual(output, dict(self.buttons, CStickX=152))

    def test_targeting_and_neutral_immediately_release(self):
        self.enable()
        self.buttons["L"] = True
        self.g["update"]()
        self.buttons["L"] = False
        self.buttons["StickX"] = 128
        self.g["update"]()
        self.assertEqual(self.writes, [])

    def test_real_polled_input_replaces_guessed_queue_without_wait(self):
        self.enable()
        calls = []
        def choose(live, held, pending, **kwargs):
            calls.append(pending)
            return core.Plan(152, .001, 16, (152,) * 4)
        self.g["choose_camera"] = choose
        self.g["update"]()
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(calls, [(self.queued,)])
        self.assertEqual(self.g["_expected"], core.advance(seed(), self.queued).state)

    def test_load_resets_pending_predictions(self):
        self.enable()
        self.g["update"]()
        self.g["state_loaded"](True, 4)
        self.assertIsNone(self.g["_expected"])
        self.assertIsNone(self.g["_output"])

    def test_repeated_prediction_mismatch_latches_stop(self):
        self.enable()
        for _ in range(3):
            self.g["_expected"] = seed(velocity=-40)
            self.g["update"]()
            self.frame += 1
        self.assertIn("prediction mismatch", self.g["_fault"])
        count = len(self.writes)
        self.g["update"]()
        self.assertEqual(len(self.writes), count)


if __name__ == "__main__":
    unittest.main()
