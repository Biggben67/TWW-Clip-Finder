from harness.rollstab.slash_clip_gui import (
    load_settings, parse_seam_coordinates, save_settings,
)


def test_coordinate_triplet_paste():
    assert parse_seam_coordinates(
        "586.023132, 17.303171, -1413.401733"
    ) == ("586.023132", "17.303171", "-1413.401733")
    assert parse_seam_coordinates("(1e2, -2.5, +3)") == ("1e2", "-2.5", "+3")


def test_single_or_invalid_paste_uses_normal_entry_behavior():
    assert parse_seam_coordinates("586.023132") is None
    assert parse_seam_coordinates("x, 17, -1413") is None
    assert parse_seam_coordinates("1, 2, 3, 4") is None


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = {
        "seam_x": "586.023132",
        "seam_y": "17.303171",
        "seam_z": "-1413.401733",
        "mode": "Walking Setup",
        "angle_lo": "1200",
        "angle_hi": "64000",
        "budget": "300",
        "max_results": "8",
        "iso": r"C:\games\custom.iso",
        "game_id": "GZLJ11",
    }
    save_settings({**expected, "ignored": "value"}, str(path))
    assert load_settings(str(path)) == expected
    assert not (tmp_path / "settings.json.tmp").exists()


def test_corrupt_settings_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_settings(str(path)) == {}