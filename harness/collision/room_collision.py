"""Resolve and cache room collision for offline collision searches."""
from __future__ import annotations

import re
from pathlib import Path

from harness.collision.dae_region import load_dae_region
from harness.collision.dzb_iso import load_room_region, load_room_region_from_iso
from harness.collision.seam_scan import (
    dump_region_tris,
    load_region_tris,
    region_cache_metadata,
)
from tww_sim.core.collision import Plane, Tri


ROOT = Path(__file__).resolve().parents[2]


def region_from_live_meshes(*meshes):
    """Combine live WallCorrect and GroundCross meshes into one search region.

    Wall polygons retain WallCorrect traversal order. GroundCross contributes floor
    polygons. BG slot plus local polygon index identifies a polygon, so separate
    actors cannot alias stage polygons with the same index.
    """
    region = []
    seen = set()
    for mesh in meshes:
        for source in mesh["polys"]:
            bg = source.get("source_bg", mesh.get("bg"))
            local_poly = int(source.get("source_poly", source["poly"]))
            poly = local_poly if bg is None else (int(bg) << 16) | local_poly
            if poly in seen:
                continue
            seen.add(poly)
            vertices = [tuple(vertex) for vertex in source["v"]]
            normal = tuple(source["n"])
            distance = float(source["d"])
            triangle = {
                "poly": poly,
                "v": vertices,
                "n": normal,
                "T": Tri(
                    vertices[0], vertices[1], vertices[2],
                    plane=Plane(normal[0], normal[1], normal[2], distance),
                ),
            }
            if bg is not None:
                triangle.update(source_bg=int(bg), source_poly=local_poly)
            region.append(triangle)
    return region


def load_live_room_collision(pid=None, status=None):
    """Read static and actor-owned BG collision at its current world-space pose.

    WallCorrect visits BG slots in registry order. Capture every wall mesh first,
    then add all GroundCross candidates, including floors on MoveBG actors.
    The returned BG remains Link's floor BG for existing live-status callers.
    """
    from harness.rollstab.capture_walls import active_bg_slots, _room_bg, read_mesh
    from harness.rollstab.live_slash import open_dolphin, read_state

    reader = open_dolphin(pid)
    try:
        state = read_state(reader)
        if status:
            status("Reading stage and moveable BG collision from Dolphin...")
        floor_bg = _room_bg(reader)
        slots = active_bg_slots(reader)
        if not slots:
            raise RuntimeError("no active background collision is registered in Dolphin")
        walls = [read_mesh(reader, bg=bg) for bg in slots]
        floors = [read_mesh(reader, bg=bg, floors=True) for bg in slots]
        region = region_from_live_meshes(*walls, *floors)
        if status:
            status(
                "Captured %s room %d: %d collision BGs, %d unique polygons"
                % (state.stage, state.room, len(slots), len(region))
            )
        return region, state, floor_bg
    finally:
        reader.close()


def room_cache_path(stage, room):
    """Return the generated cache path for a stage room."""
    safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", stage.strip()).strip("_").lower()
    if not safe_stage:
        raise ValueError("stage must not be empty")
    return ROOT / "_generated" / "collision" / (
        "%s_r%d_iso_region.json" % (safe_stage, int(room))
    )


def _legacy_cache_path(stage, room):
    safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", stage.strip()).strip("_").lower()
    return ROOT / ("_generated_%s_r%d_iso_region.json" % (safe_stage, int(room)))


def _load_checked_cache(path, stage, room, allow_missing_room=False):
    cached_stage, cached_room = region_cache_metadata(path)
    if cached_stage.casefold() != stage.casefold():
        raise ValueError(
            "collision cache is for stage %s, not %s" % (cached_stage, stage)
        )
    if cached_room is None and not allow_missing_room:
        raise ValueError(
            "collision cache does not identify its room; select the game ISO "
            "to generate a stage/room-specific cache"
        )
    if cached_room is not None and int(cached_room) != int(room):
        raise ValueError(
            "collision cache is for room %d, not room %d" % (cached_room, room)
        )
    region, loaded_stage = load_region_tris(path)
    return region, None, loaded_stage


def load_room_collision(opts, status=None):
    """Load requested collision and generate/reuse an ISO room cache.

    Explicit JSON and DAE files remain supported. An explicit ISO is treated as
    the source for ``stage``/``room``; its decoded collision is cached so later
    scans do not reopen the disc image. With no source, a matching generated
    cache is preferred, followed by the configured extracted-disc directory.
    """
    stage = opts["stage"].strip()
    room = int(opts["room"])
    if not stage:
        raise ValueError("stage must not be empty")

    if opts.get("dae"):
        if status:
            status("Loading Collada collision...")
        return load_dae_region(opts["dae"])

    if opts.get("cache"):
        if status:
            status("Loading collision cache...")
        return _load_checked_cache(Path(opts["cache"]), stage, room)

    cache = room_cache_path(stage, room)
    legacy_cache = _legacy_cache_path(stage, room)
    if cache.exists():
        if status:
            status("Loading cached %s room %d collision..." % (stage, room))
        return _load_checked_cache(cache, stage, room)
    if legacy_cache.exists():
        if status:
            status("Loading cached %s room %d collision..." % (stage, room))
        return _load_checked_cache(
            legacy_cache, stage, room, allow_missing_room=True
        )

    if opts.get("iso"):
        if status:
            status("Reading %s room %d from game ISO..." % (stage, room))
        region, box, loaded_stage = load_room_region_from_iso(
            opts["iso"], stage, room
        )
    else:
        if status:
            status("Reading %s room %d from extracted disc..." % (stage, room))
        region, box, loaded_stage = load_room_region(stage, room)

    cache.parent.mkdir(parents=True, exist_ok=True)
    dump_region_tris(region, loaded_stage, cache, room=room)
    if status:
        status("Cached %s room %d collision" % (stage, room))
    return region, box, loaded_stage
