from pathlib import Path
import struct
import pytest

from harness.dtm.writer import _controller_row
from harness.rollstab.recorded_route import (
    decode_controller_row,
    extract_route,
    movie_poll_bias,
    movie_vi_from_savestate,
    nearest_route_start,
    patch_route_movie,
    read_dtm_frames,
    read_dtm_poll_rows,
    read_dtm_vi_rows,
)


def _state(path: Path, vi: int):
    data = bytearray(0x80)
    struct.pack_into("<Q", data, 0x5D, vi)
    path.write_bytes(data)


def _movie(path: Path, p1, p2):
    header = bytearray(256)
    header[:4] = b"DTM\x1a"
    header[11] = 3
    rows = []
    for left, right in zip(p1, p2):
        for _ in range(4):
            rows.extend((_controller_row(left), _controller_row(right)))
    path.write_bytes(header + b"".join(rows))


def test_decode_controller_row_round_trip():
    row = {
        "stickX": 42, "stickY": 231, "substickX": 94, "substickY": 128,
        "buttons": 0x0100 | 0x0200 | 0x0040, "triggerL": 255, "triggerR": 7,
    }
    assert decode_controller_row(_controller_row(row)) == row


def test_extract_two_controller_route(tmp_path):
    movie = tmp_path / "route.dtm"
    left = [{"stickX": 128 + i} for i in range(5)]
    right = [{"stickX": 40 + i, "buttons": 0x0200 if i == 3 else 0}
             for i in range(5)]
    _movie(movie, left, right)
    start = tmp_path / "start.sav"
    end = tmp_path / "end.sav"
    _state(start, 3)
    _state(end, 9)

    assert [row["stickX"] for row in read_dtm_vi_rows(movie, controller=1)] == [
        40, 40, 41, 41, 42, 42, 43, 43, 44, 44,
    ]
    assert [row["stickX"] for row in read_dtm_frames(movie, controller=1)] == [40, 41, 42, 43, 44]
    route = extract_route(movie, start, end, controller=1)
    assert movie_vi_from_savestate(start) == 3
    assert [row["stickX"] for row in route.rows] == [41, 42, 43]
    assert route.rows[-1]["buttons"] == 0x0200


def test_shifted_savestate_cursor_and_long_movie_poll_clock(tmp_path):
    movie = tmp_path / "route.dtm"
    left = [{"stickX": 128 + i} for i in range(5)]
    right = [{"stickX": 40 + i} for i in range(5)]
    _movie(movie, left, right)
    data = bytearray(movie.read_bytes())
    struct.pack_into("<Q", data, 13, 1010)
    movie.write_bytes(data)
    start = tmp_path / "start.sav"
    state = bytearray(0x80)
    state[0x5B] = 4
    struct.pack_into("<I", state, 0x5C, 1003)
    state[0x60] = 1
    start.write_bytes(state)
    end = tmp_path / "end.sav"
    _state(end, 1009)

    assert movie_vi_from_savestate(start) == 1003
    assert movie_poll_bias(movie) == -2000
    route = extract_route(movie, start, end, controller=1)
    assert [row["stickX"] for row in route.rows] == [41, 42, 43]
    edited = [dict(row) for row in route.rows]
    edited[0]["stickX"] = 99
    output = patch_route_movie(route, edited, tmp_path / "edited.dtm")
    polls = read_dtm_poll_rows(output, 1)
    assert [poll["stickX"] for poll in polls[6:10]] == [99] * 4
    assert read_dtm_poll_rows(output, 0) == read_dtm_poll_rows(movie, 0)


def test_old_shifted_cursor_uses_companion_movie_to_discard_flag(tmp_path):
    state = tmp_path / "GZLJ11.s05"
    data = bytearray(0x80)
    data[0x5B] = 4
    struct.pack_into("<I", data, 0x5C, 0x0100CAEC)
    state.write_bytes(data)
    movie = Path(str(state) + ".dtm")
    header = bytearray(256)
    header[:4] = b"DTM\x1a"
    struct.pack_into("<Q", header, 13, 51962)
    movie.write_bytes(header)
    assert movie_vi_from_savestate(state) == 51948


def test_extract_route_accepts_one_game_frame_tail_cursor(tmp_path):
    movie = tmp_path / "route.dtm"
    left = [{"stickX": 128 + i} for i in range(5)]
    right = [{"stickX": 40 + i} for i in range(5)]
    _movie(movie, left, right)
    start = tmp_path / "start.sav"
    end = tmp_path / "end.sav"
    _state(start, 3)
    _state(end, 12)  # DTM has 10 VI rows: the endpoint is exactly two VIs later.

    route = extract_route(movie, start, end, controller=1)
    assert route.end_vi == 10
    assert [row["stickX"] for row in route.rows] == [41, 42, 43, 44]


def test_extract_route_rejects_larger_tail_gap(tmp_path):
    movie = tmp_path / "route.dtm"
    _movie(movie, [{"stickX": 128}] * 5, [{"stickX": 40}] * 5)
    start = tmp_path / "start.sav"
    end = tmp_path / "end.sav"
    _state(start, 3)
    _state(end, 13)

    try:
        extract_route(movie, start, end, controller=1)
    except ValueError as exc:
        assert "DTM ends at VI 10" in str(exc)
    else:
        raise AssertionError("a DTM more than two VIs short was accepted")


def test_nearest_route_start(tmp_path):
    movie = tmp_path / "route.dtm"
    movie.write_bytes(b"")
    end = tmp_path / "end.sav"
    old = tmp_path / "old.sav"
    nearest = tmp_path / "nearest.sav"
    _state(end, 200)
    _state(old, 100)
    _state(nearest, 180)
    assert nearest_route_start(movie, end, [old, nearest]) == nearest


def test_patch_route_movie_preserves_deep_cursor(tmp_path):
    movie = tmp_path / "route.dtm"
    left = [{"stickX": 128 + i} for i in range(5)]
    right = [{"stickX": 40 + i} for i in range(5)]
    _movie(movie, left, right)
    start = tmp_path / "start.sav"
    end = tmp_path / "end.sav"
    _state(start, 3)
    _state(end, 9)
    route = extract_route(movie, start, end, controller=1)

    replacement = [dict(row, stickX=200 + i) for i, row in enumerate(route.rows)]
    output = patch_route_movie(route, replacement, tmp_path / "patched.dtm")
    rows = read_dtm_vi_rows(output, controller=1)
    assert [rows[route.start_vi + i * 2]["stickX"] for i in range(3)] == [200, 201, 202]
    assert rows[0]["stickX"] == 40


def test_extended_route_preserves_prefix_and_other_controller(tmp_path):
    movie = tmp_path / "route.dtm"
    _movie(movie, [{"stickX": 128, "stickY": 128}] * 3,
           [{"stickX": 40 + i} for i in range(3)])
    start, end = tmp_path / "start.sav", tmp_path / "end.sav"
    _state(start, 2)
    _state(end, 6)
    route = extract_route(movie, start, end, controller=1)
    rows = [dict(row, stickX=210) for row in route.rows] + [dict(route.rows[-1], stickX=220)] * 4
    original = movie.read_bytes()
    output = patch_route_movie(route, rows, tmp_path / "long.dtm", extend=True)
    result = output.read_bytes()
    assert movie.read_bytes() == original
    assert result[256:256 + 2 * 2 * 2 * 8] == original[256:256 + 2 * 2 * 2 * 8]
    assert all(row["stickX"] == 128 for row in read_dtm_vi_rows(output, controller=0))
    assert read_dtm_vi_rows(output, controller=1)[-1]["stickX"] == 220
    assert struct.unpack_from("<Q", result, 13)[0] == route.start_vi + len(rows) * 2
    assert struct.unpack_from("<Q", result, 21)[0] == (len(result) - 256) // 8
    assert struct.unpack_from("<Q", result, 237)[0] > struct.unpack_from("<Q", original, 237)[0]


def test_extended_route_rejects_unknown_other_player_actions(tmp_path):
    movie = tmp_path / "route.dtm"
    _movie(movie, [{"buttons": 0x100}] * 3, [{"stickX": 40}] * 3)
    start, end = tmp_path / "start.sav", tmp_path / "end.sav"
    _state(start, 2)
    _state(end, 6)
    route = extract_route(movie, start, end, controller=1)
    with pytest.raises(ValueError, match="another controller"):
        patch_route_movie(route, [route.rows[-1]] * 6, tmp_path / "long.dtm", extend=True)
