from copy import deepcopy
from types import SimpleNamespace
import runpy
import sys

import pytest

from harness.rollstab.native_route import decode_row
from harness.validate.native_live_movement import runtime_movie_rows, validate_consumed_pads


def test_live_diagnostic_rejects_ignored_movie_mutations():
    old = decode_row(dict(stickX=128, stickY=252, buttons=0))
    new = decode_row(dict(stickX=252, stickY=128, buttons=0))
    with pytest.raises(RuntimeError, match="ignored or changed"):
        validate_consumed_pads([old], [new])


def test_live_diagnostic_rejects_a_single_float_ulp():
    pad = decode_row(dict(stickX=128, stickY=252, buttons=0))
    live = dict(pad, my=pad["my"] - 2 ** -24)
    with pytest.raises(RuntimeError, match="ignored or changed"):
        validate_consumed_pads([live], [pad])
    validate_consumed_pads([pad], [pad])


@pytest.mark.parametrize("fail_capture", [False, True])
def test_runtime_input_edits_restore_both_polls_without_touching_other_lane(tmp_path, monkeypatch, fail_capture):
    original = dict(StickX=128, StickY=128, CStickX=128, CStickY=128,
                    TriggerLeft=0, TriggerRight=0, B=False, Connected=True)
    original.update((name, False) for name in
                    ("Start", "A", "B", "X", "Y", "Z", "Up", "Down", "Left", "Right", "L", "R"))
    states = {(row, port): deepcopy(original) for row in range(80, 84) for port in range(2)}
    saved = deepcopy(states)

    def get(row, port):
        return deepcopy(states.get((row, port)))

    def put(row, port, state):
        states[row, port].update(state)
        return True

    monkeypatch.setitem(sys.modules, "dolphin_dtm", SimpleNamespace(get_gc=get, set_gc=put))

    class Control:
        def command(self, command, values):
            if command == "enablescript":
                runpy.run_path(values["path"])
            else:
                assert command == "disablescript"

    route = SimpleNamespace(controller=1, start_vi=40)
    row = dict(stickX=92, stickY=252, substickX=128, substickY=100,
               triggerL=150, triggerR=0, buttons=0x1000 | 1 | 0x200)

    def capture():
        with runtime_movie_rows(Control(), route, [row], tmp_path):
            for poll in range(80, 84):
                assert states[poll, 0] == saved[poll, 0]
                actual = states[poll, 1]
                assert actual["Start"] and actual["Up"] and actual["B"]
                assert not actual["Right"]
                assert actual["StickX"] == 92 and actual["CStickY"] == 100
            if fail_capture:
                raise RuntimeError("capture failed")

    if fail_capture:
        with pytest.raises(RuntimeError, match="capture failed"):
            capture()
    else:
        capture()
    assert states == saved
