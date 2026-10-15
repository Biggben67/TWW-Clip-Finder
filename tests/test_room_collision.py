"""Room collision cache naming and validation guards."""
import json
from types import SimpleNamespace

import pytest

from harness.collision.room_collision import (
    _load_checked_cache,
    load_live_room_collision,
    region_from_live_meshes,
    room_cache_path,
)
from harness.collision.seam_scan import dump_region_tris, enumerate_seams, load_region_tris


def test_room_cache_path_is_specific_to_stage_and_room():
    assert room_cache_path("GanonM", 0).name == "ganonm_r0_iso_region.json"
    assert room_cache_path("M_NewD2", 3).name == "m_newd2_r3_iso_region.json"
    assert room_cache_path("GanonM", 0) != room_cache_path("GanonM", 1)


def test_explicit_cache_rejects_wrong_room(tmp_path):
    cache = tmp_path / "room.json"
    cache.write_text(json.dumps({"stage": "GanonM", "room": 0, "tris": []}))
    with pytest.raises(ValueError, match="room 0, not room 1"):
        _load_checked_cache(cache, "GanonM", 1)


def test_explicit_cache_rejects_missing_room_metadata(tmp_path):
    cache = tmp_path / "legacy.json"
    cache.write_text(json.dumps({"stage": "GanonM", "tris": []}))
    with pytest.raises(ValueError, match="does not identify its room"):
        _load_checked_cache(cache, "GanonM", 0)


def test_live_mesh_region_keeps_wall_order_and_adds_unique_floors():
    wall = {
        "polys": [
            {"poly": 7, "v": [(0, 0, 0), (0, 10, 0), (0, 0, 10)],
             "n": (1, 0, 0), "d": 0},
            {"poly": 3, "v": [(5, 0, 0), (5, 10, 0), (5, 0, 10)],
             "n": (-1, 0, 0), "d": 5},
        ]
    }
    floor = {
        "polys": [
            wall["polys"][1],
            {"poly": 11, "v": [(0, 0, 0), (10, 0, 0), (0, 0, 10)],
             "n": (0, 1, 0), "d": 0},
        ]
    }

    region = region_from_live_meshes(wall, floor)

    assert [triangle["poly"] for triangle in region] == [7, 3, 11]
    assert all("T" in triangle for triangle in region)


def _mesh(bg, polys):
    return {"bg": bg, "polys": polys}


def _actor_walls():
    # World-space actor corner, separate from Link's stage floor at BG 0.
    return [
        {"poly": 7, "v": [(100, 0, 200), (100, 100, 200), (100, 0, 240)],
         "n": (1, 0, 0), "d": -100},
        {"poly": 8, "v": [(100, 0, 200), (140, 0, 200), (100, 100, 200)],
         "n": (0, 0, 1), "d": -200},
    ]


def test_movebg_seam_survives_stage_polygon_id_collision(tmp_path):
    floor = {"poly": 7, "v": [(0, 0, 0), (300, 0, 0), (0, 0, 500)],
             "n": (0, 1, 0), "d": 0}
    actor = _mesh(3, _actor_walls())
    region = region_from_live_meshes(_mesh(0, []), actor, _mesh(0, [floor]), actor)

    assert [t["poly"] for t in region] == [(3 << 16) | 7, (3 << 16) | 8, 7]
    assert [t["source_bg"] for t in region] == [3, 3, 0]
    assert region[0]["T"].pla.d == -100
    box = (99, 101, 0, 100, 199, 201)
    seam, = enumerate_seams(region, box)
    assert seam["S"] == (100, 0, 200)
    assert seam["source_bg"] == 3
    assert seam["polys"] == [(3 << 16) | 7, (3 << 16) | 8]

    cache = tmp_path / "actor.json"
    dump_region_tris(region, "Test", cache, room=0)
    restored, stage = load_region_tris(cache)
    assert stage == "Test"
    assert enumerate_seams(restored, box) == [seam]
    assert [t["source_poly"] for t in restored] == [7, 8, 7]


def test_separate_bgs_do_not_merge_into_a_false_corner():
    a, b = _actor_walls()
    region = region_from_live_meshes(_mesh(2, [a]), _mesh(3, [b]))
    seams = enumerate_seams(region, (99, 101, 0, 100, 199, 201))
    assert len(seams) == 2
    assert all(seam["coplanar"] for seam in seams)
    assert {seam["source_bg"] for seam in seams} == {2, 3}


def test_live_capture_reads_all_bg_walls_and_actor_floors(monkeypatch):
    from harness.rollstab import capture_walls, live_slash

    floor = {"poly": 7, "v": [(0, 0, 0), (300, 0, 0), (0, 0, 500)],
             "n": (0, 1, 0), "d": 0}
    reader = SimpleNamespace(close=lambda: closed.append(True))
    state = SimpleNamespace(stage="Test", room=0)
    closed, calls, statuses = [], [], []

    def read_mesh(_reader, bg=None, floors=False):
        calls.append((bg, floors))
        polys = [dict(floor, poly=11)] if floors else (_actor_walls() if bg == 3 else [])
        return _mesh(bg, polys)

    monkeypatch.setattr(live_slash, "open_dolphin", lambda pid: reader)
    monkeypatch.setattr(live_slash, "read_state", lambda _reader: state)
    monkeypatch.setattr(capture_walls, "_room_bg", lambda _reader: 0)
    monkeypatch.setattr(capture_walls, "active_bg_slots", lambda _reader: [0, 3])
    monkeypatch.setattr(capture_walls, "read_mesh", read_mesh)

    region, captured, floor_bg = load_live_room_collision(123, status=statuses.append)
    assert captured is state
    assert floor_bg == 0
    assert calls == [(0, False), (3, False), (0, True), (3, True)]
    assert [t["source_bg"] for t in region] == [3, 3, 0, 3]
    assert closed == [True]
    assert "2 collision BGs" in statuses[-1]
