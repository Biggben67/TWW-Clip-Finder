from pathlib import Path
from types import SimpleNamespace

from harness.rollstab import smart_route_gui
from harness.rollstab.smart_route_search import find_dispatch_rows
from harness.rollstab.smart_route_search import _mutations


def test_validated_game_id_is_filename_text_not_header_bytes():
    game_id = smart_route_gui.validated_game_id("GZLJ01")
    assert game_id == "GZLJ01"
    assert isinstance(game_id, str)


def test_all_editable_settings_are_persisted():
    assert set(smart_route_gui.SETTING_KEYS) == {
        "pid", "seam_x", "seam_y", "seam_z", "state_dir", "game_id",
        "base_slot", "final_slot", "controller", "evaluation_cap",
        "random_seed", "auto_route",
    }


def test_zero_axis_family_does_not_call_empty_randrange():
    parent = (128, 128)
    assert list(_mutations(parent, (), 8, __import__("random").Random(1), 20)) == [parent]


def test_find_dispatch_rows_prefers_observed_cut_then_adjacent_timings():
    rows = [
        {"buttons": 0}, {"buttons": 0}, {"buttons": 0}, {"buttons": 0},
        {"buttons": 0x0200}, {"buttons": 0}, {"buttons": 0}, {"buttons": 0},
    ]
    trace = {
        "route": {"rows": rows},
        "trace": [
            {"row": 6, "before": {"state": 7}, "after": {"state": 0x44}},
            {"row": 7, "before": {"state": 0x44}, "after": {"state": 0x44}},
        ],
    }
    assert find_dispatch_rows(trace) == (6, 5, 7)


def test_find_dispatch_rows_uses_buffered_b_without_observed_cut():
    rows = [{"buttons": 0} for _ in range(9)]
    rows[4]["buttons"] = 0x0200
    trace = {"route": {"rows": rows}, "trace": []}
    assert find_dispatch_rows(trace) == (6,)


def test_route_from_slots_uses_requested_files_and_controller(tmp_path, monkeypatch):
    for name in ("GZLJ01.s05", "GZLJ01.s10", "GZLJ01.s10.dtm"):
        (tmp_path / name).write_bytes(b"x")
    captured = {}

    def fake_extract(movie, start, end, controller):
        captured.update(movie=movie, start=start, end=end, controller=controller)
        return SimpleNamespace(rows=({"stickX": 128, "stickY": 128},), controller=controller)

    monkeypatch.setattr(smart_route_gui, "extract_route", fake_extract)
    monkeypatch.setattr(smart_route_gui, "_active_controllers", lambda _header: (0,))
    route = smart_route_gui.route_from_slots(tmp_path, "GZLJ01", 5, 10, 0)
    assert route.controller == 0
    assert captured == {
        "movie": tmp_path / "GZLJ01.s10.dtm",
        "start": tmp_path / "GZLJ01.s05",
        "end": tmp_path / "GZLJ01.s10",
        "controller": 0,
    }


def test_route_from_slots_falls_back_from_zeroed_gba_lane(tmp_path, monkeypatch):
    for name in ("GZLJ01.s05", "GZLJ01.s10", "GZLJ01.s10.dtm"):
        (tmp_path / name).write_bytes(b"x")

    def fake_extract(_movie, _start, _end, controller):
        rows = ({"stickX": 0, "stickY": 0},) if controller == 0 else (
            {"stickX": 96, "stickY": 59, "buttons": 0},
        )
        return SimpleNamespace(rows=rows, controller=controller)

    monkeypatch.setattr(smart_route_gui, "extract_route", fake_extract)
    monkeypatch.setattr(smart_route_gui, "_active_controllers", lambda _header: (0, 1))
    route = smart_route_gui.route_from_slots(tmp_path, "GZLJ01", 5, 10, 0)
    assert route.controller == 1


def test_route_from_slots_reports_missing_files(tmp_path):
    try:
        smart_route_gui.route_from_slots(tmp_path, "GZLJ01", 5, 10, 0)
    except RuntimeError as exc:
        assert "GZLJ01.s05" in str(exc)
        assert "GZLJ01.s10.dtm" in str(exc)
    else:
        raise AssertionError("missing route files were accepted")
