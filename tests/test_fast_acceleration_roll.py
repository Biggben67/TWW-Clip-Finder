from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch

from harness.dolphin_scripts import fast_acceleration_roll_core as core


class CoreTests(unittest.TestCase):
    def test_aligned_camera_selects_documented_best_gate(self):
        gate = core.choose_gate(0, 0)
        self.assertEqual((gate.stick_x, gate.stick_y), (151, 199))
        self.assertEqual(gate.offset, -1481)
        self.assertAlmostEqual(gate.potential_roll_speed, 25.923810958862305)

    def test_ranked_candidates_interleave_both_turn_directions(self):
        rows = core.ranked_gate_candidates(30583, 21332, 8)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(abs(row.offset) < 0x2000 for row in rows))
        self.assertEqual([row.offset > 0 for row in rows[:4]], [True, False, True, False])
        self.assertEqual(len({row.target for row in rows}), len(rows))

    def test_world_target_inverse_compensates_for_camera_motion(self):
        gate = core.choose_gate(12000, 9000)
        for camera in (9000, 9400, 30000):
            x, y, error = core.stick_for_world_target(gate.target, camera)
            self.assertTrue(1 <= x <= 254 and 1 <= y <= 254)
            self.assertLess(abs(error), 220)

    def test_roll_formula_caps_at_26(self):
        self.assertAlmostEqual(core.roll_speed(16.949207306), 25.923810958862305)
        self.assertEqual(core.roll_speed(17.0), 26.0)


class Control:
    def __init__(self, value=None, checked=False, clicked=False):
        self.value = value
        self.checked = checked
        self.clicked = clicked

    def set(self, value):
        self.value = value


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.loads = []
        self.saves = []
        self.buttons = dict(StickX=128, StickY=128, CStickX=128, CStickY=128,
                            A=False, B=False, X=False, Y=False, Z=False, Start=False,
                            L=False, R=False, TriggerLeft=0, TriggerRight=0, Connected=True)
        window = types.SimpleNamespace(
            checkbox=lambda label, checked=False: Control(checked=checked),
            input_text=lambda label, value="": Control(value=value),
            button=lambda label: Control(clicked=False),
            text=lambda value: Control(value=value),
        )
        dolphin = types.ModuleType("dolphin")
        dolphin.gui = types.SimpleNamespace(window=lambda name: window)
        dolphin.event = types.SimpleNamespace(**{name: lambda fn: fn for name in (
            "on_hostupdate", "on_savestateload", "on_frameadvance")})
        dolphin.controller = types.SimpleNamespace(
            get_gc_buttons=lambda port: dict(self.buttons),
            set_gc_buttons=lambda port, data: self.writes.append(dict(data)),
        )
        dolphin.memory = types.SimpleNamespace()
        dolphin.savestate = types.SimpleNamespace(
            load_from_slot=self.loads.append,
            save_to_slot=self.saves.append,
        )
        path = Path(__file__).parents[1] / "harness/dolphin_scripts/Fast Acceleration Roll.py"
        with patch.dict(sys.modules, {"dolphin": dolphin,
                                      "fast_acceleration_roll_core": core}):
            module = runpy.run_path(str(path))
        self.g = module["update"].__globals__
        self.state = dict(frame=100, state=66, speed_f=1.9, normal_speed=1.9,
                          facing=30583, camera=21332, life=3)
        self.g["_snapshot"] = lambda: dict(self.state)
        self.g["_camera_angle"] = lambda: self.state["camera"]

    def start(self):
        self.g["_enabled_control"].checked = True
        self.g["host_update"]()
        self.g["update"]()

    def test_start_loads_slot5_and_authors_ranked_candidate(self):
        self.start()
        self.assertEqual(self.loads, [5])
        self.assertTrue(self.writes[-1]["L"])
        self.assertEqual((self.writes[-1]["CStickX"], self.writes[-1]["CStickY"]),
                         (128, 100))
        self.assertEqual(self.g["_trial_index"], 0)
        self.assertEqual(self.g["_trial"].offset,
                         core.ranked_gate_candidates(30583, 21332, 1)[0].offset)

    def test_left_only_search_excludes_right_gate_candidates(self):
        self.g["_left_gate_control"].checked = True
        self.g["_right_gate_control"].checked = False
        self.start()
        self.assertTrue(self.g["_trials"])
        self.assertTrue(all(trial.offset > 0 for trial in self.g["_trials"]))

    def test_right_only_search_excludes_left_gate_candidates(self):
        self.g["_left_gate_control"].checked = False
        self.g["_right_gate_control"].checked = True
        self.start()
        self.assertTrue(self.g["_trials"])
        self.assertTrue(all(trial.offset < 0 for trial in self.g["_trials"]))

    def test_duplicate_30hz_counter_reissues_same_row_at_60hz(self):
        self.start()
        first = self.writes[-1]
        count = len(self.writes)
        self.g["update"]()
        self.assertEqual(len(self.writes), count + 1)
        self.assertEqual(
            (self.writes[-1]["StickX"], self.writes[-1]["StickY"], self.writes[-1]["L"]),
            (first["StickX"], first["StickY"], first["L"]),
        )
        self.assertEqual(self.g["_trial_frame"], 0)

    def test_measured_17_acceleration_is_saved_to_slot4_and_stops(self):
        self.start()
        self.state.update(frame=101, state=7, speed_f=1.5, normal_speed=4.94)
        self.g["update"]()
        for frame, speed in ((102, 9.94), (103, 13.44), (104, 17.0)):
            self.state.update(frame=frame, state=6, speed_f=speed,
                              normal_speed=speed)
            self.g["update"]()
        self.assertEqual(self.saves, [4])
        self.assertFalse(self.g["_running"])
        self.assertIn("measured 17 acceleration speed", self.g["_message"])
        self.assertTrue(all(not row["A"] for row in self.writes))

    def test_submaximal_acceleration_saves_best_then_requests_clean_reload(self):
        self.start()
        self.state.update(frame=101, state=7, speed_f=1.5, normal_speed=4.94)
        self.g["update"]()
        for frame, speed in ((102, 8.44), (103, 11.94), (104, 15.44)):
            self.state.update(frame=frame, state=6, speed_f=speed,
                              normal_speed=speed)
            self.g["update"]()
        self.assertEqual(self.saves, [4])
        self.assertTrue(self.g["_reload_requested"])
        self.assertEqual(self.g["_trial_index"], 1)
        self.assertAlmostEqual(self.g["_best_speed"], 15.44)


if __name__ == "__main__":
    unittest.main()
