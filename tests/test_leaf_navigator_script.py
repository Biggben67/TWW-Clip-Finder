"""Frame-order regression tests for the live Leaf Navigator input sequence."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Control:
    def __init__(self, value=None, checked=False):
        self.value = value
        self.checked = checked

    def set(self, value):
        self.value = value


class Window:
    def checkbox(self, label, checked=False):
        return Control(checked=checked)

    def input_text(self, label, value):
        return Control(value=value)

    def text(self, value):
        return Control(value=value)


class LeafNavigatorScriptTests(unittest.TestCase):
    def test_pump_queues_a_then_z_on_adjacent_game_frames(self):
        rows = []
        controller = types.SimpleNamespace(
            get_gc_buttons=lambda pad: {},
            set_gc_buttons=lambda pad, buttons: rows.append(dict(buttons)),
        )
        passthrough = lambda fn: fn
        dolphin = types.SimpleNamespace(
            controller=controller,
            event=types.SimpleNamespace(
                on_hostupdate=passthrough,
                on_frameadvance=passthrough,
                on_savestateload=passthrough,
            ),
            gui=types.SimpleNamespace(window=lambda title: Window()),
            memory=types.SimpleNamespace(),
        )
        path = (Path(__file__).resolve().parents[1] / "harness" /
                "dolphin_scripts" / "Leaf Navigator.py")
        spec = importlib.util.spec_from_file_location("test_live_leaf_navigator", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"dolphin": dolphin}):
            spec.loader.exec_module(module)
            module._enabled_control.checked = True
            module._pump_control.checked = True
            module._leaf_button_control.value = "Z"
            module._x_control.value = "1000"
            base = dict(x=0.0, z=0.0, facing=0, camera=0,
                        turn_rate=0, normal_speed=12.0, cancel_lockout=0)
            states = iter([
                dict(base, frame=1, action=147, countdown=3),
                dict(base, frame=2, action=147, countdown=2),
                dict(base, frame=3, action=39, countdown=1),
                dict(base, frame=4, action=147, countdown=40),
            ])
            module._state = lambda: next(states)
            for _ in range(4):
                module.update()

        self.assertEqual([(row["A"], row["Z"]) for row in rows],
                         [(True, False), (False, True), (False, False),
                          (False, False)])
        self.assertEqual(module._phase, "steer")


if __name__ == "__main__":
    unittest.main()
