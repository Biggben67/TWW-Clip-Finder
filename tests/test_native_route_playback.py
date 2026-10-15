from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.rollstab import native_route_playback as playback


class Control:
    def __init__(self, playing=True, stride=1):
        self.frame = 40
        self.playing = playing
        self.stride = stride
        self.advances = []

    def command(self, cmd):
        assert cmd == "status"
        return {"frame": self.frame, "playing": self.playing, "recording": False}

    def pause(self):
        pass

    def advance(self, frames):
        self.advances.append(frames)
        self.frame += self.stride
        return self.command("status")


def test_endpoint_requires_exact_f32_not_nearby_coordinates():
    pose = dict(x=585.0, y=0.0, z=-1413.0, speed_f=17.0, state=66, facing=32000)
    expected = SimpleNamespace(**pose)
    playback.validate_endpoint(SimpleNamespace(**pose), expected)
    pose["x"] += 0.00006103515625
    with pytest.raises(RuntimeError, match="final slot"):
        playback.validate_endpoint(SimpleNamespace(**pose), expected)


@pytest.mark.parametrize("playing", [False, True])
def test_attaches_full_movie_and_restores_even_after_failure(tmp_path, monkeypatch, playing):
    start = tmp_path / "slot5.sav"
    movie = tmp_path / "slot10.dtm"
    start.write_bytes(b"base state")
    movie.write_bytes(b"full movie")
    Path(str(start) + ".dtm").write_bytes(b"truncated base movie")
    control = Control(playing=playing)
    loaded = []

    def save(_control, path):
        path.write_bytes(b"original paused state")

    def load(_control, path):
        loaded.append(path.name)
        if path.name == "start.sav":
            assert Path(str(path) + ".dtm").read_bytes() == b"full movie"
            control.playing = True
        else:
            assert path.read_bytes() == b"original paused state"

    monkeypatch.setattr(playback, "_save_state_settled", save)
    monkeypatch.setattr(playback, "_load_state_settled", load)
    monkeypatch.setattr(playback, "_stop_active_recording",
                        lambda *args: pytest.fail("playback must not be stopped"))
    route = SimpleNamespace(movie=movie, start_state=start, start_vi=40)
    with pytest.raises(ValueError, match="capture failure"):
        with playback.attached_route(control, route, tmp_path / "capture", lambda _: None):
            raise ValueError("capture failure")
    assert loaded == ["start.sav", "restore.sav"]
    assert Path(str(start) + ".dtm").read_bytes() == b"truncated base movie"
    assert not list((tmp_path / "capture").iterdir())


def test_native_gui_accepts_existing_playback(monkeypatch):
    from harness.rollstab import native_route_gui as gui
    instance = object.__new__(gui.NativeRouteGUI)
    instance._prepare_capture(Control(playing=True), lambda _: None)
    # The inherited Start handler launches its worker without synchronous pipe I/O.
    assert gui.NativeRouteGUI.search is gui.SmartRouteGUI.search


def test_capture_steps_by_game_counter_through_lag():
    control = Control()
    counters = iter((100, 100, 100, 101))
    reader = SimpleNamespace(u32=lambda _: next(counters))
    assert playback.advance_game_frame(control, reader)["frame"] == 43
    assert control.advances == [1, 1, 1]


def test_capture_rejects_skipped_game_update():
    counters = iter((100, 102))
    reader = SimpleNamespace(u32=lambda _: next(counters))
    with pytest.raises(RuntimeError, match="skipped a TWW gameplay"):
        playback.advance_game_frame(Control(), reader)


def test_stopped_movie_never_falls_back_to_injected_inputs():
    reader = SimpleNamespace(u32=lambda _: 100)
    with pytest.raises(RuntimeError, match="movie ended"):
        playback.advance_game_frame(Control(playing=False), reader)


def test_native_gui_does_not_stop_recording_or_capture_without_playback(monkeypatch):
    from harness.rollstab import native_route_gui as gui
    instance = object.__new__(gui.NativeRouteGUI)
    with pytest.raises(RuntimeError, match="read-only playback"):
        instance._prepare_capture(Control(playing=False), lambda _: None)
