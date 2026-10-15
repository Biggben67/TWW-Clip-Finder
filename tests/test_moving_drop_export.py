from types import SimpleNamespace

import pytest

from harness.collision import moving_drop_export


def _result():
    return {
        "start_pos": (590.392333984375, 0.0, -1454.6956787109375),
        "start_facing": 26880,
        "start_animation_phase": 50,
        "rows": [{"stickX": 128, "stickY": 128, "buttons": 0x0200}],
    }


def _snapshot(**changes):
    values = dict(
        x=590.392333984375, y=0.0, z=-1454.6956787109375,
        facing=26880, upper_frame=0.0, upper_rate=0.0,
        state=1, grab_actor=0x80ABB070,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_prepared_start_requires_exact_pose_and_fixed_upper_animation():
    moving_drop_export._check_prepared(_snapshot(), _result(), 0x80ABB070)
    with pytest.raises(RuntimeError, match="coordinates drifted"):
        moving_drop_export._check_prepared(
            _snapshot(x=590.3923950195312), _result(), 0x80ABB070
        )
    with pytest.raises(RuntimeError, match="fixed frame 0"):
        moving_drop_export._check_prepared(
            _snapshot(upper_frame=1.0), _result(), 0x80ABB070
        )
    with pytest.raises(RuntimeError, match="fixed frame 0"):
        moving_drop_export._check_prepared(
            _snapshot(upper_rate=1.0), _result(), 0x80ABB070
        )
    with pytest.raises(RuntimeError, match="lost the carried object"):
        moving_drop_export._check_prepared(
            _snapshot(grab_actor=0), _result(), 0x80ABB070
        )


def test_active_movie_is_left_untouched(monkeypatch, tmp_path):
    class FakeControl:
        def __init__(self, pid):
            assert pid == 19780

        def command(self, name):
            assert name == "status"
            return {"recording": True, "playing": False}

        def pause(self):
            raise AssertionError("active recording must not be paused")

    monkeypatch.setattr(moving_drop_export, "DolphinControl", FakeControl)
    with pytest.raises(RuntimeError, match="Stop the active Dolphin movie"):
        moving_drop_export.export_moving_drop_with_state(
            19780, _result(), tmp_path / "clip.dtm", b"GZLJ11"
        )


def test_recorded_timeline_keeps_movement_after_b_release():
    result = _result()
    result["b_index"] = 0
    rows = moving_drop_export._playback_rows(result)
    assert len(rows) == 5
    assert rows[0]["buttons"] & 0x0200
    assert all(row["buttons"] == 0 for row in rows[1:])
    assert all(row["stickX"] == 128 and row["stickY"] == 128 for row in rows)


def test_live_clip_requires_detach_and_retained_depth():
    trace = [{"depth": -1.0}, {"depth": 0.25}, {"depth": 0.1}]
    assert not moving_drop_export._clip_verified(trace, None)
    assert moving_drop_export._clip_verified(trace, 1)
    assert not moving_drop_export._clip_verified(trace[:-1] + [{"depth": -0.2}], 1)
    assert not moving_drop_export._clip_verified(
        [{"depth": 0.25}, {"depth": -1.0}], 1
    )
