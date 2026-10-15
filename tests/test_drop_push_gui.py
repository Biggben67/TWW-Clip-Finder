from types import SimpleNamespace
import os
import queue
import struct
import threading
import time
import pytest

from harness.collision import drop_push_gui

from harness.collision.drop_push_gui import (
    DropPushApp,
    ensure_drop_animation_data,
    load_settings,
    parse_facing_spec,
    parse_seam_coordinates,
    save_settings,
)


def test_push_coordinate_triplet_paste():
    assert parse_seam_coordinates(
        "-584.995605, 16.695562, -1413.985596"
    ) == ("-584.995605", "16.695562", "-1413.985596")


def test_push_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = {
        "seam_x": "-584.995605",
        "seam_y": "16.695562",
        "seam_z": "-1413.985596",
        "use_live": "True",
        "stage": "GanonM",
        "room": "0",
        "object_type": "pot_small",
        "frames": "5,11,51",
        "facings": "12000-52000",
        "max_results": "6",
        "stop_first": "False",
        "oob_landing": "True",
        "oob_tolerance": "0.005",
        "collision_path": r"C:\games\custom.iso",
        "teleport_on_result": "True",
    }
    save_settings({**expected, "ignored": "value"}, str(path))
    assert load_settings(str(path)) == expected
    assert not (tmp_path / "settings.json.tmp").exists()


def _teleport_test_reader(monkeypatch, *, mismatch=False, starting_state="running"):
    player = 0x80400000
    memory = {}
    calls = []

    class Reader:
        def u32(self, address):
            assert address == drop_push_gui.live_slash.PLAYER_PTR
            return player

        def read_bytes(self, address, size):
            return bytes(memory.get(address + offset, 0xA5) for offset in range(size))

        def write_bytes(self, address, data):
            for offset, value in enumerate(data):
                memory[address + offset] = value

        def close(self):
            calls.append("close")

    reader = Reader()
    def command(name):
        calls.append(name)
        if name == "status":
            return {"state": starting_state, "playing": True}
        if name == "resume":
            return {"ok": True}
        pytest.fail("unexpected movie command")

    control = SimpleNamespace(
        pause=lambda: calls.append("pause"),
        command=command,
        advance_with=lambda **kwargs: pytest.fail("teleport must not advance the movie"),
        load_state=lambda path: pytest.fail("teleport must not load a state"),
    )
    monkeypatch.setattr(drop_push_gui, "DolphinControl", lambda pid: control)
    monkeypatch.setattr(drop_push_gui.live_slash, "open_dolphin", lambda *args, **kwargs: reader)

    def read_state(current_reader):
        x, y, z = struct.unpack(">fff", current_reader.read_bytes(player + 0x120, 12))
        facing = struct.unpack(">H", current_reader.read_bytes(player + 0x136, 2))[0]
        return SimpleNamespace(x=x + (1 if mismatch else 0), y=y, z=z, facing=facing)

    monkeypatch.setattr(drop_push_gui.live_slash, "read_state", read_state)
    return reader, memory, calls, player


@pytest.mark.parametrize("starting_state, expected_calls", [
    ("running", ["status", "pause", "close", "resume"]),
    ("paused", ["status", "close"]),
])
def test_static_teleport_preserves_emulation_state(monkeypatch, starting_state, expected_calls):
    reader, memory, calls, player = _teleport_test_reader(
        monkeypatch, starting_state=starting_state)
    candidate = SimpleNamespace(old=(1.0, 2.0, 3.0), facing=43)
    result = drop_push_gui.teleport_static_candidate(123, candidate)
    assert (result.x, result.y, result.z, result.facing) == (1.0, 2.0, 3.0, 43)
    assert reader.read_bytes(player + 0x120, 12) == struct.pack(">fff", 1.0, 2.0, 3.0)
    assert reader.read_bytes(player + 0x136, 2) == struct.pack(">H", 43)
    assert calls == expected_calls


def test_static_teleport_restores_bytes_on_failed_verification(monkeypatch):
    reader, memory, calls, player = _teleport_test_reader(monkeypatch, mismatch=True)
    candidate = SimpleNamespace(old=(1.0, 2.0, 3.0), facing=43)
    with pytest.raises(RuntimeError, match="did not retain"):
        drop_push_gui.teleport_static_candidate(123, candidate)
    assert reader.read_bytes(player + 0x120, 12) == b"\xA5" * 12
    assert reader.read_bytes(player + 0x136, 2) == b"\xA5" * 2
    assert calls == ["status", "pause", "close", "resume"]


def test_existing_drop_animation_data_needs_no_iso(tmp_path):
    (tmp_path / "link_anim_grab.json").write_text("{}")
    (tmp_path / "link_skeleton.json").write_text("{}")
    assert ensure_drop_animation_data("", tmp_path) == []


def test_missing_drop_animation_data_explains_iso_requirement(tmp_path):
    try:
        ensure_drop_animation_data("", tmp_path)
    except FileNotFoundError as exc:
        assert "Select your Wind Waker ISO" in str(exc)
    else:
        raise AssertionError("missing animation data should require an ISO")


def test_static_setup_keeps_inclusive_facing_and_frame_priority():
    class Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    app = SimpleNamespace(
        seam_x=Var("622.715210"), seam_y=Var("0"), seam_z=Var("-1503.366699"),
        frames=Var("1-60"), facings=Var("0-65535"),
        max_results=Var("10"), oob_tolerance=Var("1"),
        collision_path=Var(""), stage=Var(""), room=Var(""),
        object_type=Var("bomb"), oob_landing=Var(False), use_live=Var(True),
        stop_first=Var(True),
        _pid_value=lambda: 19780,
    )
    inputs = DropPushApp._inputs(app)
    assert inputs[1][:3] == [11, 5, 51]
    assert inputs[2] == [(0, 65535, 16)]
    assert parse_facing_spec("36256-36271") == [(36256, 36271, 16)]


def test_progress_is_throttled_but_results_are_not(monkeypatch):
    messages = queue.Queue()
    now = [0.0]
    monkeypatch.setattr(drop_push_gui.time, "monotonic", lambda: now[0])
    sink = drop_push_gui._ProgressMessages(messages)
    sink.put(("progress", 1))
    for index in range(1000):
        sink.put(("status", str(index)))
    sink.put(("hits", ["candidate"]))
    now[0] = 0.11
    sink.put(("progress", 2))
    sink.put(("done", "test", 0, 1))
    assert [messages.get_nowait()[0] for _ in range(4)] == ["progress", "hits", "progress", "done"]
    assert messages.empty()


def test_gui_message_drain_is_bounded():
    messages = queue.Queue()
    for index in range(1000):
        messages.put(("status", str(index)))
    updates, callbacks = [], []
    app = SimpleNamespace(
        messages=messages, closed=False, status=SimpleNamespace(set=updates.append),
        root=SimpleNamespace(after=lambda *args: callbacks.append(args)),
        _drain_messages=lambda: None,
    )
    DropPushApp._drain_messages(app)
    assert 0 < len(updates) <= 64
    assert not messages.empty()
    assert callbacks[0][0] == 75


def test_compact_static_result_text():
    candidate = SimpleNamespace(
        frame=4, old=(-615.609130859375, 300.0, -105.93769073486328),
        facing_range=(42496, 42511),
        resolved=(-653.889892578125, -142.21707153320312),
        oob_landing=False,
    )
    assert DropPushApp._format_candidate(None, candidate) == (
        "Animation Position: 4\n"
        "X: -615.609130859375\n"
        "Y: 300.0\n"
        "Z: -105.93769073486328\n"
        "Angle Range: 42496-42511\n"
        "Endpoint X/Z: -653.889892578125, -142.21707153320312\n"
        "OoB Seam: No"
    )


def test_teleport_accepts_listed_result_while_scan_is_active(monkeypatch):
    dispatched = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            dispatched.append(args)

        def start(self):
            pass

    monkeypatch.setattr(drop_push_gui.threading, "Thread", FakeThread)
    candidate = SimpleNamespace(old=(1.0, 2.0, 3.0), facing=43)
    app = SimpleNamespace(
        worker=SimpleNamespace(is_alive=lambda: True), teleport_worker=None,
        _selected_candidate=lambda: candidate,
        _save_settings=lambda: None,
        scan_button=SimpleNamespace(configure=lambda **kwargs: None),
        teleport_button=SimpleNamespace(configure=lambda **kwargs: None),
        status=SimpleNamespace(set=lambda value: None),
        _pid_value=lambda: 123,
        _teleport_worker=lambda *args: None,
    )
    DropPushApp.teleport_selected(app)
    assert dispatched == [(123, candidate)]


def test_unexpected_worker_exit_is_reported():
    class Source:
        def get(self, timeout):
            raise queue.Empty

        def close(self):
            pass

    messages = queue.Queue()
    worker = SimpleNamespace(is_alive=lambda: False, join=lambda timeout: None, exitcode=7)
    drop_push_gui._relay_scan(worker, Source(), messages, threading.Event())
    message = messages.get_nowait()
    assert message[0] == "error" and "code 7" in message[1]


def _gil_blocking_scan(inputs, messages, cancel_event):
    messages.put(("status", "child PID %d" % os.getpid()))
    if os.name == "nt":
        import ctypes
        # PyDLL holds the child's GIL for the entire native call.
        ctypes.PyDLL("kernel32.dll").Sleep(800)
    else:
        time.sleep(0.8)
    messages.put(("done", "test", 0, 0))


def test_tk_remains_responsive_while_search_holds_child_gil(monkeypatch):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    app = DropPushApp(root)
    monkeypatch.setattr(app, "_inputs", lambda: ("stationary",))
    monkeypatch.setattr(app, "_save_settings", lambda: None)
    monkeypatch.setattr(drop_push_gui, "_scan_process", _gil_blocking_scan)
    ticks = []

    def tick():
        ticks.append(time.monotonic())
        root.after(10, tick)

    try:
        root.after(10, tick)
        app.start_scan()
        assert app.worker.pid != os.getpid()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            root.update()
            if not app.worker.is_alive() and str(app.scan_button["state"]) != "disabled":
                break
            time.sleep(0.003)
        assert not app.worker.is_alive()
        assert len(ticks) >= 30
        assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.35
        assert "0 results" in app.status.get()
    finally:
        app._close()
