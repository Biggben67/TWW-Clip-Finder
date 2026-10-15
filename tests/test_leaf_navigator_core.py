import unittest
from pathlib import Path
import sys
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "dolphin_scripts"))

from leaf_navigator_core import (
    choose_stick, glide_speed_step, glide_turn_step, pump_due, s16, world_angle,
)


class LeafNavigatorCoreTests(unittest.TestCase):
    def test_world_angles(self):
        self.assertEqual(world_angle(0, 10), 0)
        self.assertEqual(world_angle(10, 0), 0x4000)
        self.assertEqual(world_angle(0, -10), 0x8000)
        self.assertEqual(s16(0xFFFF), -1)

    def test_speed_and_turn_constraints(self):
        self.assertAlmostEqual(glide_speed_step(12, 1, 0), 12)
        self.assertLess(glide_speed_step(12, 1, 0x2000), 12)
        self.assertGreater(glide_turn_step(0, 1, 0x2000), 0)
        self.assertLessEqual(glide_turn_step(0, 1, 0x2000), 64)

    def test_controller_turns_towards_destination_above_speed_floor(self):
        x, y, target, speed, distance = choose_stick(
            0, 0, 100, 100, 0, 0, 0, 12, 9.0,
        )
        self.assertTrue(0 <= x <= 255 and 0 <= y <= 255)
        self.assertGreater(s16(target), 0)
        self.assertGreaterEqual(speed, 11.5 - 1e-6)
        self.assertAlmostEqual(distance, 100 * 2 ** 0.5)

    def test_stronger_turn_than_old_per_frame_budget(self):
        old = 0x600  # About the maximum first turn at the old 0.08 default.
        _, _, target, _, _ = choose_stick(0, 0, 100, 0, 0, 0, 0, 12)
        self.assertGreater(s16(target), old)

    def test_perpendicular_destination_turns_within_80_frames(self):
        x = z = 0.0
        facing = rate = 0
        speed = 12.0
        for _ in range(80):
            _, _, target, _, _ = choose_stick(
                x, z, 1000, 0, facing, 0, rate, speed,
            )
            offset = s16(target - facing)
            speed = glide_speed_step(speed, 1.0, offset)
            rate = glide_turn_step(rate, 1.0, offset)
            facing = (facing + rate) & 0xFFFF
            x += speed * math.sin(facing / (65536 / (2 * math.pi)))
            z += speed * math.cos(facing / (65536 / (2 * math.pi)))
        self.assertGreater(facing, 0x2000)
        self.assertGreater(x, 300)

    def test_camera_change_keeps_world_turn(self):
        one = choose_stick(0, 0, 100, 100, 0, 0, 0, 12)
        two = choose_stick(0, 0, 100, 100, 0, 0x2000, 0, 12)
        self.assertLess(abs(s16(one[2] - two[2])), 128)

    def test_pump_only_when_actionable_at_three(self):
        self.assertTrue(pump_due(3, 0, True))
        self.assertFalse(pump_due(4, 0, True))
        self.assertFalse(pump_due(2, 0, True))
        self.assertFalse(pump_due(3, 1, True))
        self.assertFalse(pump_due(3, 0, False))


if __name__ == "__main__":
    unittest.main()
