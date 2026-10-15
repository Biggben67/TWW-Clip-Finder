"""Live Dolphin front end for the exact roll-stab and walk-stab planners.

The live contract is intentionally narrow: Dolphin must be paused with Link stationary in WAIT and
with the sword drawn. Arbitrary mid-walk foot/animation history is not reconstructible from the
small public state vector, so accepting it would produce plausible-looking but unproved inputs.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
from ctypes import wintypes
import math
import os
import shutil
import struct
import time
from dataclasses import asdict, dataclass

from harness.live_mem_probe import ProcReader
from harness.dolphin_control import DolphinControl
from harness.rollstab.capture_walls import active_bg_slots, _room_bg, read_mesh
from harness.rollstab.seamgeo import SeamGeo
from harness.collision.seam_scan import GATHER_R, WALL_H, _tri_xz_edge_dist, enumerate_seams

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GEN = os.path.join(_ROOT, "_generated")
SEED_PATH = os.path.join(_GEN, "live_slash.seed.json")
GEO_PATH = os.path.join(_GEN, "live_slash_geo.json")
RESULT_PATH = os.path.join(_GEN, "live_slash_results.json")
ANCHOR_DIR = os.path.join(_GEN, "live_slash_anchors")
BASE_SAV = os.path.join(ANCHOR_DIR, "room_base.sav")
ANCHOR_SAV = os.path.join(ANCHOR_DIR, "prepared.sav")
FINAL_ANCHOR_SAV = os.path.join(ANCHOR_DIR, "prepared_final.sav")
CLIP_STATE_DIR = os.path.join(_GEN, "live_slash_states")
CANDIDATE_DIR = os.path.join(_GEN, "live_slash_candidates")
FACING_CACHE_PATH = os.path.join(_GEN, "live_slash_facing_cache.json")
FACING_CACHE_VERSION = 1

PLAYER_PTR = 0x803AD860
STAGE_NAME = 0x803BD23C
CAMERA_ROOT = 0x803AD380
SWORD_ITEM = 0x103
WAIT_STATES = (4, 5)
LIFE_ADDR = 0x803B810B
ROOM_NO_ADDR = 0x803E9F48
LOW_LIFE_THRESHOLD = 6
STEADY_WAITS_RATE = 1.1
STEADY_WAITB_RATE = 0.4
REST_MODE_BLEND = 2


@dataclass
class LiveState:
    pid: int
    stage: str
    player: int
    x: float
    y: float
    z: float
    facing: int
    travel: int
    csangle: int
    state: int
    speedF: float
    nspeed: float
    stick_distance: float
    animation_frame: float
    target_facing: int
    equip_item: int
    sword_drawn: bool
    room: int = -1
    life: int = 255
    rest_mode: int = REST_MODE_BLEND
    rest_d_rate: float = STEADY_WAITS_RATE


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def dolphin_pids() -> list[int]:
    """Return Dolphin PIDs through Toolhelp, without psutil or shelling out to tasklist."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap == wintypes.HANDLE(-1).value:
        return []
    found = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in ("dolphin.exe", "dolphinqt2.exe"):
                found.append(int(entry.th32ProcessID))
            ok = kernel.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snap)
    return sorted(set(found))

def open_dolphin(pid: int | None = None, writable: bool = False) -> ProcReader:
    candidates = [int(pid)] if pid else dolphin_pids()
    if not candidates:
        raise RuntimeError("no running Dolphin process was found")
    errors = []
    for candidate in candidates:
        try:
            reader = ProcReader(candidate, writable=writable)
            if reader.read_bytes(0x80000000, 4) != b"GZLJ":
                reader.close()
                errors.append(f"PID {candidate}: running game is not JP Wind Waker (GZLJ)")
                continue
            return reader
        except Exception as exc:
            errors.append(f"PID {candidate}: {exc}")
    raise RuntimeError("could not attach to JP Wind Waker; " + "; ".join(errors))


def _camera_angle(reader: ProcReader) -> int:
    root = reader.u32(CAMERA_ROOT)
    if not 0x80000000 <= root < 0x81800000:
        raise RuntimeError("camera root pointer is not valid")
    camera = reader.u32(root + 0x34)
    if not 0x80000000 <= camera < 0x81800000:
        raise RuntimeError("camera pointer is not valid")
    return reader.u16(camera + 0x2B0)


def read_state(reader: ProcReader) -> LiveState:
    p = reader.u32(PLAYER_PTR)
    if not 0x80000000 <= p < 0x81800000:
        raise RuntimeError("Link player pointer is not valid; load into gameplay first")
    stage = reader.read_bytes(STAGE_NAME, 11).split(b"\0")[0].decode("ascii", "replace")
    equip = reader.u16(p + 0x3488)
    return LiveState(
        pid=reader.pid,
        stage=stage,
        player=p,
        x=reader.f32(p + 0x120),
        y=reader.f32(p + 0x124),
        z=reader.f32(p + 0x128),
        travel=reader.u16(p + 0x12E),
        facing=reader.u16(p + 0x136),
        csangle=_camera_angle(reader),
        state=reader.u32(p + 0x3100),
        speedF=reader.f32(p + 0x17C),
        animation_frame=reader.f32(p + 0x2F64),
        target_facing=reader.u16(p + 0x3410),
        stick_distance=reader.f32(p + 0x34D8),
        nspeed=reader.f32(p + 0x34E4),
        equip_item=equip,
        sword_drawn=equip == SWORD_ITEM,
        room=reader.s8(ROOM_NO_ADDR),
        life=reader.u8(LIFE_ADDR),
        rest_mode=reader.u8(p + 0x33EB),
        rest_d_rate=reader.f32(p + 0x2F60),
    )


def validate_rest_pose(state: LiveState) -> None:
    """Accept only WAIT variants that the exact from-rest runway model can seed."""
    if state.life <= LOW_LIFE_THRESHOLD:
        # procWait_init uses ANM_WAITATOB as a mode-0 single at rate 0.6. Once it ends, procWait
        # settles into a mode-2 WAITB/WALK blend at mMove.field_0x3C (0.4).
        if state.rest_mode == 0 and abs(state.rest_d_rate - 0.6) <= 1e-4:
            return
        if state.rest_mode == REST_MODE_BLEND and abs(state.rest_d_rate - STEADY_WAITB_RATE) <= 1e-4:
            return
        raise RuntimeError(
            f"Link's critical-health WAIT pose is between modeled phases "
            f"(mode={state.rest_mode}, d_rate={state.rest_d_rate:.7f}). "
            "Let the idle transition settle for a frame, pause, and scan again."
        )
    if state.rest_mode != REST_MODE_BLEND or abs(state.rest_d_rate - STEADY_WAITS_RATE) > 1e-4:
        raise RuntimeError(
            f"Link is not in the steady WAITS rest pose (mode={state.rest_mode}, "
            f"d_rate={state.rest_d_rate:.7f}; expected mode={REST_MODE_BLEND}, "
            f"d_rate={STEADY_WAITS_RATE:.1f}). Let the idle transition finish, pause, and scan again."
        )


def ensure_paused_rest(reader: ProcReader) -> LiveState:
    first = read_state(reader)
    time.sleep(0.18)
    second = read_state(reader)
    moving_clock = first.animation_frame != second.animation_frame
    moved = (first.x, first.y, first.z) != (second.x, second.y, second.z)
    if moving_clock or moved:
        raise RuntimeError("pause Dolphin before capturing the setup")
    if second.state not in WAIT_STATES:
        raise RuntimeError(
            f"Link state is {second.state}, not stationary WAIT; finish the action, then pause"
        )
    if abs(second.speedF) > 1e-6 or abs(second.nspeed) > 1e-6 or abs(second.stick_distance) > 1e-6:
        raise RuntimeError(
            "Link still has movement state; release the stick, settle completely, then pause"
        )
    if not second.sword_drawn:
        raise RuntimeError("draw the sword, return to WAIT, then pause Dolphin")
    validate_rest_pose(second)
    return second


def parse_game_id(value: bytes | str | None) -> bytes:
    """Validate the user-selected six-byte ID written to exported DTM headers."""
    if value in (None, ""):
        value = "GZLJ01"
    if isinstance(value, str):
        try:
            value = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("DTM game ID must contain exactly 6 ASCII characters") from exc
    if len(value) != 6 or any(byte < 0x20 or byte > 0x7E for byte in value):
        raise ValueError("DTM game ID must contain exactly 6 printable ASCII characters")
    return bytes(value)


def ensure_cut_animation(iso_path: str | None, log=print) -> str:
    """Generate the private CUT_F/CUT_A root-motion cache from the user's own JP ISO once."""
    path = os.path.join(_ROOT, "_generated", "anim", "link_anim_cuts.json")
    if os.path.isfile(path):
        return path
    if not iso_path:
        raise RuntimeError("select a JP Wind Waker ISO once to build the slash animation cache")
    iso_path = os.path.abspath(iso_path)
    if not os.path.isfile(iso_path):
        raise RuntimeError("the selected JP ISO does not exist")
    with open(iso_path, "rb") as disc:
        if disc.read(4) != b"GZLJ":
            raise RuntimeError("the selected disc is not JP Wind Waker (GZLJ)")
    log("Building the CUT_F/CUT_A animation cache from the selected JP ISO...")
    from harness.anim import parse_bck
    raw = parse_bck._gcm_read_object_arc(iso_path, "LkAnm")
    names = parse_bck._OUTPUTS["link_anim_cuts.json"]
    anims = parse_bck.load_from_lkanm(raw, names=names)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({name: parse_bck.to_jsonable(anim) for name, anim in anims.items()}, f)
    log(f"Animation cache written to {path}")
    return path

def _tri(poly: dict) -> dict:
    return dict(poly=poly["poly"], v=poly["v"], n=poly["n"], d=poly["d"])


def resolve_geo(mesh: dict, target: tuple[float, float, float], max_xz_error: float = 1.5) -> tuple[dict, dict]:
    tx, ty, tz = target
    verts = [v for p in mesh["polys"] for v in p["v"]]
    ymin = min(v[1] for v in verts) - 1.0
    ymax = max(v[1] for v in verts) + 1.0
    box = (tx - max_xz_error, tx + max_xz_error, ymin, ymax,
           tz - max_xz_error, tz + max_xz_error)
    seams = enumerate_seams(mesh["polys"], box)
    if not seams:
        raise RuntimeError("no vertical wall seam was found near the supplied X/Z coordinates")
    seam = min(seams, key=lambda s: math.hypot(s["S"][0] - tx, s["S"][2] - tz))
    error = math.hypot(seam["S"][0] - tx, seam["S"][2] - tz)
    if error > max_xz_error:
        raise RuntimeError(f"nearest seam is {error:.3f} units from the supplied coordinates")

    by_poly = {p["poly"]: p for p in mesh["polys"]}
    incident = [by_poly[p] for p in seam["polys"] if p in by_poly]
    groups = {}
    for p in incident:
        groups.setdefault((round(p["n"][0], 4), round(p["n"][2], 4)), []).append(p)
    ranked = sorted(groups.values(), key=len, reverse=True)
    if len(ranked) >= 2:
        wall_a, wall_b = ranked[0][0], ranked[1][0]
    elif len(incident) >= 2:
        wall_a, wall_b = incident[0], incident[1]
    else:
        raise RuntimeError("the seam does not have two incident wall triangles in the live mesh")

    n_a = (wall_a["n"][0], wall_a["n"][2])
    n_b = (wall_b["n"][0], wall_b["n"][2])
    bx, bz = -(n_a[0] + n_b[0]), -(n_a[1] + n_b[1])
    if abs(bx) + abs(bz) < 1e-9:
        bx, bz = -n_a[0], -n_a[1]
    bisector_deg = math.degrees(math.atan2(bx, bz)) % 360.0
    link_y = float(ty)
    lo, hi = link_y - 5.0, link_y + WALL_H[-1] + 5.0
    barrier = []
    for p in mesh["polys"]:
        ys = [v[1] for v in p["v"]]
        if max(ys) < lo or min(ys) > hi:
            continue
        if _tri_xz_edge_dist(p["v"], seam["S"][0], seam["S"][2]) < GATHER_R:
            barrier.append(_tri(p))
    if not barrier:
        raise RuntimeError("no collision walls overlap Link's standing cylinder at the target Y")

    geo = dict(
        stage=mesh.get("stage"),
        bg=mesh.get("bg"),
        source="live Dolphin ordered DZB wall mesh",
        S=list(seam["S"]),
        requested_S=[tx, ty, tz],
        seam_xz_error=error,
        interior=seam["interior"],
        bisector_deg=bisector_deg,
        link_y=link_y,
        wallA=_tri(wall_a),
        wallB=_tri(wall_b),
        barrier=barrier,
        tris=barrier,
    )
    os.makedirs(_GEN, exist_ok=True)
    with open(GEO_PATH, "w") as f:
        json.dump(geo, f, indent=1)
    return geo, seam


def read_live_target_collision(reader: ProcReader, target, link_y: float,
                               max_xz_error: float = 1.5,
                               local_radius: float = 650.0):
    """Capture the BG that owns ``target`` plus nearby walls and Link's floor BG.

    Link normally stands on the static room BG, but seams can belong to a MoveBG actor.  Selecting
    collision from Link's ground index alone silently drops those seams.  The returned wall mesh is
    assembled in dBgS slot order and uses composite polygon ids so equal local ids from different
    BGs cannot alias in ``resolve_geo``.
    """
    tx, _ty, tz = (float(value) for value in target)
    floor_bg = _room_bg(reader)
    if floor_bg is None:
        raise RuntimeError("could not resolve Link's current floor collision BG")

    meshes = []
    owners = []
    for bg in active_bg_slots(reader):
        try:
            mesh = read_mesh(reader, bg=bg)
        except (RuntimeError, StopIteration, ValueError):
            continue
        meshes.append((bg, mesh))
        vertices = [vertex for poly in mesh["polys"] for vertex in poly["v"]]
        if not vertices:
            continue
        ymin = min(vertex[1] for vertex in vertices) - 1.0
        ymax = max(vertex[1] for vertex in vertices) + 1.0
        box = (
            tx - max_xz_error, tx + max_xz_error, ymin, ymax,
            tz - max_xz_error, tz + max_xz_error,
        )
        for seam in enumerate_seams(mesh["polys"], box):
            error = math.hypot(seam["S"][0] - tx, seam["S"][2] - tz)
            if error <= max_xz_error:
                owners.append((error, bg))

    if not owners:
        raise RuntimeError("no active static or movable BG seam was found near the supplied X/Z")
    _error, target_bg = min(owners)

    lo = float(link_y) - 5.0
    hi = float(link_y) + WALL_H[-1] + 5.0
    polygons = []
    for bg, mesh in meshes:
        for source in mesh["polys"]:
            ys = [vertex[1] for vertex in source["v"]]
            if max(ys) < lo or min(ys) > hi:
                continue
            if _tri_xz_edge_dist(source["v"], tx, tz) > local_radius:
                continue
            poly = dict(source)
            poly["source_bg"] = bg
            poly["source_poly"] = int(source["poly"])
            poly["poly"] = (int(bg) << 16) | int(source["poly"])
            polygons.append(poly)

    wall_mesh = {
        "stage": meshes[0][1].get("stage") if meshes else None,
        "bg": target_bg,
        "room": None,
        "polys": polygons,
    }
    floor_mesh = read_mesh(reader, bg=floor_bg, floors=True)
    return wall_mesh, floor_mesh, target_bg, floor_bg


def _angle_span(lo: int, hi: int) -> int:
    return (hi - lo) & 0xFFFF


def angle_in_range(angle: int, lo: int, hi: int) -> bool:
    return ((angle - lo) & 0xFFFF) <= _angle_span(lo, hi)


def parse_angle_range(lo, hi) -> tuple[int, int]:
    if lo in (None, "") and hi in (None, ""):
        return 0, 0xFFFF
    if lo in (None, "") or hi in (None, ""):
        raise ValueError("enter both angle bounds, or leave both blank for the full circle")
    a, b = int(lo, 0) & 0xFFFF, int(hi, 0) & 0xFFFF
    return a, b


def _circular_distance(a: int, b: int) -> int:
    return abs(((int(a) - int(b) + 0x8000) & 0xFFFF) - 0x8000)


def roll_aim_candidates(geo: dict, csangle: int, lo: int, hi: int, log=print):
    """Enumerate full-stick slash facings in range, ordered around the locator direction."""
    from harness.rollstab import rest as rest_model
    from tww_sim.core.mathlib import main_stick_decode
    from tww_sim.land.plan_land import stick_for_bearing

    clean_geo = dict(geo)
    clean_geo.pop("aim_deg", None)
    probe = SeamGeo(clean_geo, csangle)
    reachable = probe.roll_reachable()
    if reachable is None:
        raise RuntimeError("this seam has no WallCorrect-standable rolling-slash approach")
    old, new = reachable["old"], reachable["new"]
    dx, dz = new[0] - old[0], new[2] - old[2]
    goal = round(math.atan2(dx, dz) / (2.0 * math.pi) * 65536.0) & 0xFFFF

    requested = set(range(0, 0x10000, 32))
    requested.update((goal, lo, hi))
    requested.update((goal + delta) & 0xFFFF for delta in range(-256, 257))

    by_facing = {}
    for aim in requested:
        seam = SeamGeo(clean_geo, csangle, aim_deg=aim / 65536.0 * 360.0)
        if not angle_in_range(seam.F, lo, hi):
            continue
        item = (_circular_distance(seam.F, goal), _circular_distance(aim, goal), seam)
        previous = by_facing.get(seam.F)
        if previous is None or item[:2] < previous[:2]:
            by_facing[seam.F] = item
    for facing, item in list(by_facing.items()):
        delivered = rest_model.dtm_stick(stick_for_bearing(facing, csangle, 1.0))
        stick_angle, _magnitude = main_stick_decode(*delivered)
        delivered_facing = (stick_angle + 0x8000 + csangle) & 0xFFFF
        if delivered_facing != facing:
            del by_facing[facing]

    if not by_facing:
        raise RuntimeError("no DTM-stable slash facing falls inside the selected range")

    choices = sorted(by_facing.values(), key=lambda item: item[:2])
    log(
        f"Locator direction {goal}; {len(by_facing)} DTM-stable facing(s) in range, "
        "all retained for trajectory screening."
    )
    return goal, [item[2] for item in choices]


def _iter_genuine_roll_olds(seam):
    """Yield every coarse-grid old that passes the exact f32 cut predicate for this facing."""
    from tww_sim.core.fp import f32

    lo, hi = seam.search_band()
    sx, sz = seam.S
    along = -hi
    while along <= -lo:
        perp = -0.5
        while perp <= 0.5:
            old = (
                f32(sx + along * seam.DIRX + perp * seam.PX),
                f32(sz + along * seam.DIRZ + perp * seam.PZ),
            )
            if seam.pred_genuine(old):
                yield old
            perp += 0.001
        along += 0.05


def _screen_roll_candidate(payload):
    index, geo, csangle, roll_speedf, aim_deg = payload
    seam = SeamGeo(geo, csangle, roll_speedf=roll_speedf, aim_deg=aim_deg)
    return index, list(_iter_genuine_roll_olds(seam))


def _facing_cache_key(payload) -> str:
    _index, geo, csangle, roll_speedf, aim_deg = payload
    material = {
        "version": FACING_CACHE_VERSION,
        "geo": geo,
        "csangle": int(csangle) & 0xFFFF,
        "roll_speedf": float(roll_speedf),
        "aim_deg": float(aim_deg),
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_facing_cache(path=FACING_CACHE_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as source:
            data = json.load(source)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != FACING_CACHE_VERSION:
        return {}
    entries = data.get("entries")
    return entries if isinstance(entries, dict) else {}


def _save_facing_cache(entries: dict, path=FACING_CACHE_PATH) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump({"version": FACING_CACHE_VERSION, "entries": entries}, output)
    os.replace(temporary, path)


def _cached_witnesses(value):
    if not isinstance(value, list):
        return None
    witnesses = []
    try:
        for point in value:
            if not isinstance(point, list) or len(point) != 2:
                return None
            witnesses.append((float(point[0]), float(point[1])))
    except (TypeError, ValueError):
        return None
    return witnesses


def choose_feasible_roll_aim(candidates, log=print):
    """Rank corridor facings by the density of their exact f32 clip dust."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing

    started = time.monotonic()
    corridor_candidates = candidates[:min(96, len(candidates))]
    payloads = [
        (index, seam.geo, seam.csangle, seam.roll_speedf, seam.aim_deg)
        for index, seam in enumerate(corridor_candidates)
    ]
    cache = _load_facing_cache()
    results = []
    misses = []
    for payload in payloads:
        key = _facing_cache_key(payload)
        witnesses = _cached_witnesses(cache.get(key)) if key in cache else None
        if witnesses is None:
            misses.append(payload)
        else:
            results.append((payload[0], witnesses))
    reused = len(results)
    if reused:
        log(
            f"Exact facing cache reused {reused}/{len(payloads)} candidate(s); "
            f"{len(misses)} require screening."
        )

    if misses:
        workers = max(1, min(10, multiprocessing.cpu_count() - 2, len(misses)))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for completed, (index, witnesses) in enumerate(
                    pool.map(_screen_roll_candidate, misses, chunksize=1), 1):
                results.append((index, witnesses))
                payload = payloads[index]
                cache[_facing_cache_key(payload)] = [
                    [float(point[0]), float(point[1])] for point in witnesses
                ]
                total = reused + completed
                if completed % 64 == 0 or completed == len(misses):
                    best_n = max((len(row[1]) for row in results), default=0)
                    log(
                        f"Exact facing density: {total}/{len(payloads)} available on "
                        f"{workers} workers; best witness count={best_n} "
                        f"({time.monotonic() - started:.1f}s)."
                    )
        try:
            _save_facing_cache(cache)
        except OSError as exc:
            log(f"Exact facing cache could not be saved: {exc}")

    screened = [
        (len(witnesses), -index, witnesses, corridor_candidates[index])
        for index, witnesses in results if witnesses
    ]
    if not screened:
        raise RuntimeError("no exact rolling-slash displacement exists in the selected facing range")
    screened.sort(key=lambda row: (row[0], row[1]), reverse=True)
    ranked = []
    for count, _neg_index, witnesses, seam in screened:
        seam._witness_olds = witnesses
        seam._witness_old = witnesses[0]
        seam._dust_hint = ([seam.perp(witnesses[0])], [seam.along(witnesses[0])])
        ranked.append(seam)
    seam = ranked[0]
    witnesses = seam._witness_olds
    seam._ranked_feasible = ranked
    log(
        f"Selected densest facing {seam.F} in {time.monotonic() - started:.1f}s: "
        f"{len(witnesses)} exact coarse witness(es), first old="
        f"({witnesses[0][0]:.7f}, {witnesses[0][1]:.7f}); "
        f"retained {len(ranked)} exact candidate(s) for physical runway checks."
    )
    return seam
def _roll_rows(hit: dict) -> list[dict]:
    return [dict(frame=i, stickX=row[0], stickY=row[1], cstickX=128, cstickY=0,
                 buttons=row[2]) for i, row in enumerate(hit["stream"])]


def _f32_offset(value: float, ulps: int) -> float:
    """Offset a float32's raw bit pattern, matching the existing dust searches."""
    bits = struct.unpack(">I", struct.pack(">f", float(value)))[0]
    bits = (bits + int(ulps)) & 0xFFFFFFFF
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def _replay_roll_stream(state, stream, seam) -> dict | None:
    """Replay one fixed input stream from a translated REST state and classify its real cut."""
    from tww_sim.land.land import CUT_A, CUT_F, FRONT_ROLL

    roll_points = []
    speed_at_a = None
    old = new = None
    cut_facing = None
    transition_frame = None
    for frame, (sx, sy, buttons) in enumerate(stream):
        before = (state.pos_x, state.pos_z)
        if buttons & seam.A_BTN:
            speed_at_a = state.speedF
        state.step(sx, sy, buttons=buttons)
        proc = state.state & 0xFF
        if proc == FRONT_ROLL:
            roll_points.append((state.pos_x, state.pos_z))
        if proc in (CUT_F, CUT_A):
            old = before
            new = (state.pos_x, state.pos_z)
            cut_facing = state.facing & 0xFFFF
            transition_frame = frame
            break
    if old is None:
        return None
    genuine = seam.genuine_clip(old, new)
    clear = genuine and not any(
        seam.seg_blocked(roll_points[i], roll_points[i + 1])
        for i in range(len(roll_points) - 1)
    )
    return dict(
        fired=True, old=old, new=new, genuine=genuine, clear=clear,
        spF_at_A=speed_at_a, facing=cut_facing,
        disp=math.hypot(new[0] - old[0], new[1] - old[1]),
        n_roll=len(roll_points), stream=list(stream), transition_frame=transition_frame,
    )


def _search_roll_witness_anchors(anchor: str, seam: SeamGeo, stream, seed_x: float,
                                  seed_z: float, baseline_old, witnesses,
                                  ulp_radius=4, log=print, required=True):
    """Invert a roll stream onto exact dust by testing nearby f32 WAIT positions per witness."""
    from harness.rollstab import solver

    base = solver.base(anchor, dtm_seed=0)
    if solver.FAST_POSE and base._foot is not None:
        base._foot.skip_cruise_pose = True
    offsets = [
        (max(abs(ix), abs(iz)), abs(ix) + abs(iz), ix, iz)
        for ix in range(-int(ulp_radius), int(ulp_radius) + 1)
        for iz in range(-int(ulp_radius), int(ulp_radius) + 1)
    ]
    offsets.sort()
    tested = 0
    seen = set()
    for witness in witnesses:
        center_x = seed_x + witness[0] - baseline_old[0]
        center_z = seed_z + witness[1] - baseline_old[1]
        for _ring, _taxicab, ix, iz in offsets:
            x = _f32_offset(center_x, ix)
            z = _f32_offset(center_z, iz)
            key = (x, z)
            if key in seen:
                continue
            seen.add(key)
            state = base.clone()
            state.pos_x = x
            state.pos_z = z
            wait_x, wait_z = state.pos_x, state.pos_z
            hit = _replay_roll_stream(state, stream, seam)
            tested += 1
            if not hit:
                continue
            if (hit["genuine"] and hit["clear"] and hit["spF_at_A"] == 17.0
                    and hit["facing"] == seam.F):
                log(
                    f"Exact anchor inversion found after {tested} replay(s): "
                    f"WAIT=({wait_x:.7f}, {wait_z:.7f}), old={hit['old']}"
                )
                return wait_x, wait_z, hit
    if required:
        raise RuntimeError(
            f"no exact rolling clip was delivered by {tested} witness-centered f32 WAIT positions"
        )
    return None
def _invert_near_roll_streams(anchor: str, seam: SeamGeo, near_runs, seed: dict, log=print):
    """Translate the best exact near streams onto nearby full-resolution dust points."""
    from tww_sim.core.fp import f32
    from harness.rollstab import solver

    witnesses = list(getattr(seam, "_witness_olds", ()))
    if witnesses:
        dust_p = [seam.perp(old) for old in witnesses]
        dust_a = [seam.along(old) for old in witnesses]
    else:
        dust_p, dust_a = solver._dust2d(seam)
    for near in sorted(near_runs, key=lambda row: row.get("d_true", float("inf")))[:16]:
        along = seam.along(near["old"])
        perp = seam.perp(near["old"])
        indices = sorted(
            range(len(dust_p)),
            key=lambda i: math.hypot((dust_p[i] - perp) * solver.DUST_PW,
                                     dust_a[i] - along),
        )[:12]
        witnesses = [
            (
                f32(seam.S[0] + dust_a[i] * seam.DIRX + dust_p[i] * seam.PX),
                f32(seam.S[1] + dust_a[i] * seam.DIRZ + dust_p[i] * seam.PZ),
            )
            for i in indices
        ]
        found = _search_roll_witness_anchors(
            anchor, seam, near["stream"], seed["link_x"], seed["link_z"],
            near["old"], witnesses, ulp_radius=3, log=log, required=False,
        )
        if found is not None:
            log(
                f"Converted near stream d_true={near['d_true']:.6f} into an exact "
                "teleportable WAIT setup."
            )
            return found
    return None

def _walk_rows(hit: dict, tail_frames: int = 45) -> list[dict]:
    sticks = [tuple(s) for s in hit["sticks"]]
    n = int(hit["N"])
    # Prepared-state DTM playback reaches the solver's frame-N old at the end of row N-2.
    # Buffer B on that row so CUT_F dispatches from that old instead of taking another walk step.
    b_frame = n - 2
    rows = []
    for i in range(n + max(2, int(tail_frames))):
        if i <= n:
            sx, sy = sticks[i] if i < len(sticks) else sticks[-1]
        else:
            sx, sy = 128, 128
        rows.append(dict(frame=i, stickX=sx, stickY=sy, cstickX=128, cstickY=0,
                         buttons=0x200 if i == b_frame else 0))
    return rows


def _compact_rows(rows: list[dict]) -> str:
    def tag(row):
        buttons = []
        if row["buttons"] & 0x100:
            buttons.append("A")
        if row["buttons"] & 0x200:
            buttons.append("B")
        return (
            f"stick=({row['stickX']},{row['stickY']}) "
            f"C=({row.get('cstickX', 128)},{row.get('cstickY', 0)}) "
            f"btn={'+'.join(buttons) or '-'}"
        )

    groups = []
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or tag(rows[i]) != tag(rows[start]):
            frame = str(start) if i - 1 == start else f"{start}-{i - 1}"
            groups.append(f"frames {frame}: {tag(rows[start])}")
            start = i
    return "\n".join(groups)


def _f32_equal(left: float, right: float) -> bool:
    return struct.pack(">f", float(left)) == struct.pack(">f", float(right))


def _dtm_sticks(rows: list[dict]) -> list[dict]:
    return [
        dict(
            stickX=int(row["stickX"]), stickY=int(row["stickY"]),
            substickX=int(row.get("cstickX", 128)),
            substickY=int(row.get("cstickY", 0)),
            buttons=int(row.get("buttons", 0)), triggerL=0, triggerR=0,
        )
        for row in rows
    ]


def _export_candidate(hit: dict, index: int, game_id: bytes, log=print) -> None:
    """Write one complete movie package without starting or controlling Dolphin."""
    from harness.dtm.writer import build_dtm_from_sticks

    source = hit.get("setup", {}).get("savestate") or ANCHOR_SAV
    if not os.path.isfile(source):
        raise RuntimeError(f"prepared start savestate is missing: {source}")
    if str(hit.get("mode", "")).lower() == "walking setup":
        setup = hit.get("setup", {})
        if not _savestate_contains_xyz(
            source, setup["x"], setup["y"], setup["z"]
        ):
            raise RuntimeError(
                "refusing export: saved first-person state does not contain "
                "the solved simulation coordinates"
            )
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    movie_path = os.path.join(CANDIDATE_DIR, f"clip_{index + 1:02d}.dtm")
    start_path = movie_path + ".sav"
    companion_path = start_path + ".dtm"
    info = build_dtm_from_sticks(
        _dtm_sticks(hit["input_rows"]), movie_path,
        polls=4, seed=0, game_id=game_id,
    )
    shutil.copyfile(source, start_path)
    shutil.copyfile(movie_path, companion_path)
    seed_path = movie_path + ".seed.json"
    if os.path.isfile(SEED_PATH):
        shutil.copyfile(SEED_PATH, seed_path)
    hit["dtm_path"] = movie_path
    hit["simulation_seed"] = seed_path if os.path.isfile(seed_path) else None
    hit["start_savestate"] = start_path
    hit["dtm_companion"] = companion_path
    hit["dtm_game_id"] = game_id.decode("ascii")
    hit["verification"] = (
        "dolphin_exact" if hit.get("live_verification") else "simulation_candidate"
    )
    log(
        f"Exported complete candidate {index + 1}: {movie_path} "
        f"({info['frames']} game frames, transition frame {hit.get('transition_frame')}, "
        f"game ID {hit['dtm_game_id']})."
    )


_FOOT_OFFSETS = (0x3CF8, 0x3E10, 0x3CEC, 0x3E04)
_FOOT024_OFFSETS = (0x3D04, 0x3E1C)
_FOOT001_OFFSETS = (0x3CE1, 0x3DF9)
_DEBUG_POS = (0x803D78FC, 0x803D7900, 0x803D7904)
_DEBUG_FACING = 0x803EA3D2


def _pack_f32(value: float) -> bytes:
    return struct.pack(">f", float(value))


def _foot_tuple(reader: ProcReader, player: int) -> list[float]:
    values = []
    for offset in _FOOT_OFFSETS:
        values.extend(struct.unpack(">3f", reader.read_bytes(player + offset, 12)))
    return values


def _waist_world(reader: ProcReader, player: int) -> list[float] | None:
    try:
        model = reader.u32(player + 0x254)
        node_mtx = reader.u32(model + 0x8C)
        address = node_mtx + 30 * 0x30
        return [reader.f32(address + 0x0C), reader.f32(address + 0x1C),
                reader.f32(address + 0x2C)]
    except (OSError, ValueError):
        return None


def _ensure_standalone_savestates(control: DolphinControl, log=print) -> None:
    """Detach from an active movie before saving anchors that must load independently."""
    status = control.command("status")
    if status.get("playing"):
        raise RuntimeError(
            "Dolphin is playing a movie. Stop movie playback before scanning so the finder can "
            "create standalone start/end savestates."
        )
    if status.get("recording"):
        os.makedirs(CLIP_STATE_DIR, exist_ok=True)
        backup = os.path.join(
            CLIP_STATE_DIR, time.strftime("pre_search_recording_%Y%m%d_%H%M%S.dtm")
        )
        control.command("recordstop", {"path": backup.replace("\\", "/")})
        time.sleep(0.35)
        status = control.command("status")
        if status.get("recording"):
            raise RuntimeError("Dolphin did not stop the active movie recording")
        log(
            f"Saved and stopped the active Dolphin movie recording at {backup}; "
            "finder savestates will be standalone."
        )

def _load_state(control: DolphinControl, path: str) -> None:
    control.pause()
    control.load_state(path)
    time.sleep(0.35)
    control.pause()


def _teleport_and_step(reader: ProcReader, control: DolphinControl, x: float, y: float,
                       z: float, facing: int) -> LiveState:
    player = reader.u32(PLAYER_PTR)
    actor_base = player - 0xD8
    for offset in (0x10C, 0x120):
        reader.write_bytes(actor_base + offset, _pack_f32(x))
        reader.write_bytes(actor_base + offset + 4, _pack_f32(y))
        reader.write_bytes(actor_base + offset + 8, _pack_f32(z))
    for address, value in zip(_DEBUG_POS, (x, y, z)):
        reader.write_bytes(address, _pack_f32(value))
    reader.write_bytes(_DEBUG_FACING, struct.pack(">H", int(facing) & 0xFFFF))
    control.advance_with(frames=2)
    time.sleep(0.08)
    state = read_state(reader)
    error = math.hypot(state.x - x, state.z - z)
    if error > 8.0 or abs(state.y - y) > 8.0:
        raise RuntimeError(
            f"Dolphin teleport did not settle at the requested position (error {error:.3f}); "
            "make sure the game is paused in normal gameplay"
        )
    return state


def _capture_prepared_anchor(reader: ProcReader, control: DolphinControl, path: str,
                             allow_subjectivity: bool = False) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    control.pause()
    state = read_state(reader)
    _save_state_stable(control, path, state)
    if allow_subjectivity and state.state == 1:
        if not state.sword_drawn:
            raise RuntimeError("the first-person prepared state lost the drawn sword")
    else:
        validate_rest_pose(state)
    player = state.player
    seed = dict(
        stage=state.stage,
        link_x=state.x,
        link_y=state.y,
        link_z=state.z,
        facing=state.facing,
        shape_angle_y=state.facing,
        travel_angle=state.travel,
        csangle=state.csangle,
        link_state=state.state,
        anim_frame=state.animation_frame,
        speedF=state.speedF,
        nspeed=state.nspeed,
        mEquipItem=state.equip_item,
        equip_item=state.equip_item,
        sword_drawn=state.sword_drawn,
        life=state.life,
        low_life=state.life <= LOW_LIFE_THRESHOLD,
        rest_mode=state.rest_mode,
        rest_d_frame=reader.f32(player + 0x2F64),
        rest_w_frame=reader.f32(player + 0x2F78),
        rest_d_rate=reader.f32(player + 0x2F60),
        rest_w_rate=reader.f32(player + 0x2F74),
        rest_m359C=reader.f32(player + 0x34C4),
        rest_m35B4=reader.f32(player + 0x34DC),
        rest_m35B8=reader.f32(player + 0x34E0),
        rest_m35C4=reader.f32(player + 0x34EC),
        rest_foot024=[list(struct.unpack(">3f", reader.read_bytes(player + off, 12)))
                      for off in _FOOT024_OFFSETS],
        rest_foot001=[reader.u8(player + off) for off in _FOOT001_OFFSETS],
        rest_waist=_waist_world(reader, player),
        rest_t2=_foot_tuple(reader, player),
    )
    d0 = seed["rest_d_frame"]
    noops = 0
    for _ in range(3):
        control.advance(1)
        time.sleep(0.06)
        noops += 1
        if reader.f32(player + 0x2F64) != d0:
            break
    seed["rest_noops"] = noops
    seed["rest_t1"] = _foot_tuple(reader, player)
    _load_state(control, path)
    with open(SEED_PATH, "w") as output:
        json.dump(seed, output, indent=1)
    return seed


def _mint_prepared(reader: ProcReader, control: DolphinControl, base_path: str,
                   park_x: float, park_z: float, floor_y: float, facing: int,
                   target_csangle: int, settle_walk: int, log=print, camera_tolerance: int = 800) -> dict:
    from harness.rollstab.rest import dtm_stick
    from tww_sim.land.plan_land import stick_for_bearing

    _load_state(control, base_path)
    _teleport_and_step(reader, control, park_x, floor_y, park_z, facing)

    def camera() -> int:
        return _camera_angle(reader)

    for _ in range(80):
        delta = ((int(target_csangle) - camera() + 0x8000) & 0xFFFF) - 0x8000
        if abs(delta) < max(1, int(camera_tolerance)):
            break
        control.advance_with(substickX=255 if delta > 0 else 0, substickY=128)

    walked = 0
    previous = None
    while walked < settle_walk:
        current = camera()
        if previous is not None and current == previous:
            break
        previous = current
        sx, sy = dtm_stick(stick_for_bearing(int(facing) & 0xFFFF, current, 1.0))
        frames = min(7, settle_walk - walked)
        control.advance_with(stickX=sx, stickY=sy, frames=frames)
        walked += frames

    control.advance_with(frames=20)
    player = reader.u32(PLAYER_PTR)
    for _ in range(8):
        w0 = reader.f32(player + 0x2F78)
        control.advance_with(frames=1)
        if reader.f32(player + 0x2F78) != w0:
            break
        control.advance_with(frames=10)

    settled = read_state(reader)
    if settled.state not in WAIT_STATES or abs(settled.speedF) > 1e-6:
        raise RuntimeError(
            f"prepared position did not settle to WAIT (state={settled.state}, "
            f"speed={settled.speedF:.6f}); the approach floor may be obstructed"
        )
    if not settled.sword_drawn:
        raise RuntimeError("the prepared state lost the drawn sword")
    log(
        f"Prepared WAIT at ({settled.x:.7f}, {settled.y:.7f}, {settled.z:.7f}), "
        f"facing={settled.facing}, camera={settled.csangle}"
    )
    return _capture_prepared_anchor(reader, control, ANCHOR_SAV)


def _prepared_setup(seed: dict, mode: str) -> dict:
    return dict(
        mode=mode,
        x=seed["link_x"], y=seed["link_y"], z=seed["link_z"],
        facing=seed["shape_angle_y"], camera=seed["csangle"],
        savestate=ANCHOR_SAV,
    )


def _prepare_roll_anchor(reader: ProcReader, control: DolphinControl, geo: dict,
                         candidate: SeamGeo, budget: float, log=print) -> tuple[dict, SeamGeo]:
    from harness.rollstab import solver

    witnesses = list(getattr(candidate, "_witness_olds", ()))
    if not witnesses:
        raise RuntimeError("the selected rolling facing has no exact witness positions")
    clean_geo = dict(geo)
    clean_geo.pop("aim_deg", None)
    prepared_geo = dict(clean_geo, aim_deg=float(candidate.aim_deg) % 360.0)
    with open(GEO_PATH, "w") as output:
        json.dump(prepared_geo, output, indent=1)
    angle = math.radians(prepared_geo["aim_deg"])
    facing = round(prepared_geo["aim_deg"] / 360.0 * 65536.0) & 0xFFFF
    park_x = prepared_geo["S"][0] - 580.0 * math.sin(angle)
    park_z = prepared_geo["S"][2] - 580.0 * math.cos(angle)
    target_witnesses = sorted(witnesses, key=candidate.perp)
    target_old = target_witnesses[len(target_witnesses) // 2]
    target_perp = candidate.perp(target_old)

    seed = None
    seam = None
    baseline = None
    for iteration in range(4):
        seed = _mint_prepared(
            reader, control, BASE_SAV, park_x, park_z, prepared_geo["link_y"],
            facing, candidate.csangle, settle_walk=0, log=log,
        )
        seam = SeamGeo(clean_geo, seed["csangle"], aim_deg=candidate.aim_deg)
        if seam.F != candidate.F:
            raise RuntimeError(
                f"prepared camera changed slash facing from {candidate.F} to {seam.F}"
            )
        seam._witness_olds = witnesses
        solver._BASE.clear()
        solver._BASE_WALLED.clear()
        baseline = solver.run(SEED_PATH, [], dtm_seed=0, seam=seam)
        if not (baseline and baseline.get("fired") and baseline.get("old")):
            raise RuntimeError("the prepared full-speed roll did not reach a slash frame")
        actual_perp = seam.perp(baseline["old"])
        error = target_perp - actual_perp
        log(
            f"Anchor centering {iteration + 1}/4: baseline old={baseline['old']}, "
            f"perp={actual_perp:+.5f}, target={target_perp:+.5f}, error={error:+.5f}"
        )
        if abs(error) <= 0.02:
            seam._dust_hint = ([target_perp], [seam.along(target_old)])
            return seed, seam
        # With no settle walk, WAIT translation is position-stable and carries into the roll line.
        park_x = seed["link_x"] + error * seam.PX
        park_z = seed["link_z"] + error * seam.PZ
    raise RuntimeError("could not center the prepared roll on the exact dust band")

def _controller_walk_facings(csangle: int, lo: int, hi: int) -> list[int]:
    """Enumerate facings produced by deliverable full-stick bytes for this fixed camera."""
    from harness.rollstab import rest as rest_model
    from tww_sim.core.mathlib import main_stick_decode
    from tww_sim.land.plan_land import stick_for_bearing

    facings = set()
    for aim in range(0, 0x10000, 32):
        delivered = rest_model.dtm_stick(stick_for_bearing(aim, csangle, 1.0))
        stick_angle, _magnitude = main_stick_decode(*delivered)
        facing = (stick_angle + 0x8000 + csangle) & 0xFFFF
        if angle_in_range(facing, lo, hi):
            facings.add(facing)
    return sorted(facings)


def _refine_walk_feasibility(probe, csangle, lo, hi, coarse, log=print):
    """Replace an arbitrary geometric facing with a facing a clean DTM can actually hold."""
    from harness.rollstab.seam_feasibility import scan_aim

    facings = _controller_walk_facings(csangle, lo, hi)
    facings.sort(key=lambda facing: _circular_distance(facing, coarse[0]))
    for index, facing in enumerate(facings[:32]):
        total, hits = scan_aim(
            probe, facing, speedf=17.0, perp_w=1.5, pstep=0.001, astep=0.3
        )
        safe = [hit for hit in hits if probe.wall_clearance(hit[2], hit[3]) > 35.0]
        if safe:
            log(
                f"Refined geometric facing {coarse[0]} to DTM-stable facing {facing} "
                f"after {index + 1} controller candidate(s): genuine={total}, "
                f"wall-clear={len(safe)}"
            )
            return facing, total, len(safe), safe
    raise RuntimeError(
        "walking-slash displacement exists geometrically, but no nearby controller-reachable "
        "facing has a wall-clear dust point"
    )


def _walking_center_ray(walkstab, target_old=None):
    """Return the k=3 walk frame nearest the target, even if the first runway skips the band."""
    cb = walkstab.search_bearing()
    cs = walkstab.seed().csangle
    c1 = walkstab._sfbd(cb, cs, 0.66)
    c2 = walkstab._sfbd(cb, cs, 0.72)
    c3 = walkstab._dtm(walkstab._sfb(cb, cs, 0.66))
    cruise = walkstab._sfbd(cb, cs, 1.0)
    sticks = walkstab._stream_k([c1, c2], [], c3, cruise)
    bounds = walkstab.bounds()
    rows = [
        row for row in walkstab._walk_fast(sticks, bounds["NHI"])
        if bounds["NLO"] <= row[0] <= bounds["NHI"]
    ]
    if not rows:
        raise RuntimeError("the prepared walking runway produced no candidate slash frames")
    if target_old is None:
        sx, sz = walkstab.SEAM
        target_old = (sx, sz)
    _frame, ox, oz, facing, nspeed, travel = min(
        rows, key=lambda row: math.hypot(row[1] - target_old[0], row[2] - target_old[1])
    )
    nx, nz = walkstab.fast_cut(ox, oz, facing, nspeed, travel)
    return walkstab.perp_ray((ox, oz), (nx, nz)), (ox, oz), (nx, nz), cb


def _shift_walk_park(seed, old, target_old):
    """Translate WAIT by the full simulated old-position error (perpendicular and along)."""
    return (
        seed["link_x"] + target_old[0] - old[0],
        seed["link_z"] + target_old[1] - old[1],
    )


def _invert_walk_wait_dust(walkstab, target_old, radius=8):
    """Find a nearby f32 WAIT whose simulated old is genuine when the ideal old is unreachable."""
    original = walkstab._BASE
    base = walkstab.seed()
    offsets = sorted(
        ((dx, dz) for dx in range(-radius, radius + 1)
         for dz in range(-radius, radius + 1)),
        key=lambda pair: (abs(pair[0]) + abs(pair[1]), abs(pair[0]), abs(pair[1])),
    )
    try:
        for dx, dz in offsets:
            candidate = base.clone()
            candidate.pos_x = _f32_offset(base.pos_x, dx)
            candidate.pos_z = _f32_offset(base.pos_z, dz)
            walkstab._BASE = candidate
            rho, old, new, cb = _walking_center_ray(walkstab, target_old)
            if walkstab.genuine_clip(old, new)[0]:
                return candidate.pos_x, candidate.pos_z, old, new, rho, cb
    finally:
        walkstab._BASE = original
    return None


def _prepare_walk_anchor(reader: ProcReader, control: DolphinControl, geo: dict,
                         csangle: int, lo: int, hi: int, budget: float,
                         log=print) -> tuple[dict, dict, tuple]:
    from harness.rollstab.seam_feasibility import best_walk_aim, post_clip_depth

    probe = SeamGeo(geo, csangle)
    scan_budget = max(25.0, min(60.0, float(budget) * 0.5))
    feasibility = best_walk_aim(
        probe, speedf=17.0, min_clearance=35.0, fstep=2048,
        budget=scan_budget, verbose=False, angle_lo=lo, angle_hi=hi,
        prefer_depth=True,
    )
    facing, ntot, nsafe, safe = feasibility
    if not ntot:
        raise RuntimeError(
            "this seam has no walking-slash clip displacement in the selected angle range"
        )
    if not nsafe:
        raise RuntimeError(
            "walking-slash clip displacement exists, but every scanned point is inside Link's "
            "wall-collision radius; use Rolling slash for this seam or widen the angle range"
        )
    feasibility = _refine_walk_feasibility(
        probe, csangle, lo, hi, feasibility, log=log
    )
    facing, ntot, nsafe, safe = feasibility
    aim_deg = facing / 65536.0 * 360.0
    prepared_geo = dict(geo, aim_deg=aim_deg)
    with open(GEO_PATH, "w") as output:
        json.dump(prepared_geo, output, indent=1)
    angle = math.radians(aim_deg)
    # Build the runway behind a wall-clear exact dust witness, not behind the corner bisector.
    witness = max(safe, key=lambda h: post_clip_depth(probe, facing, h, speedf=17.0))
    park_x = witness[2] - 200.0 * math.sin(angle)
    park_z = witness[3] - 200.0 * math.cos(angle)
    log(
        f"Walking feasibility selected facing {facing}: genuine={ntot}, wall-clear={nsafe}; "
        f"target old=({witness[2]:.7f}, {witness[3]:.7f}), "
        f"post-seam depth={post_clip_depth(probe, facing, witness, speedf=17.0):.3f}"
    )
    from harness.rollstab import walkstab

    target_old = (witness[2], witness[3])
    target_new = probe.cut_new(target_old, facing=facing, speedf=17.0, travel=facing)
    target_rho = probe.perp_to_ray(target_old, target_new)
    seed = None
    for iteration in range(4):
        seed = _mint_prepared(
            reader, control, BASE_SAV, park_x, park_z, prepared_geo["link_y"],
            facing, csangle, settle_walk=0, log=log,
        )
        walkstab.configure(
            SEED_PATH, GEO_PATH, name="live_slash_prepared", dtm_seed=0,
            target_facing=facing, angle_lo=lo, angle_hi=hi, feasibility=feasibility,
            target_old=target_old,
        )
        rho, old, new, cb = _walking_center_ray(walkstab, target_old)
        dx_error = target_old[0] - old[0]
        dz_error = target_old[1] - old[1]
        position_error = math.hypot(dx_error, dz_error)
        rho_error = rho - target_rho
        log(
            f"Walking anchor centering {iteration + 1}/4: cb={cb}, old={old}, "
            f"target={target_old}, delta=({dx_error:+.6f}, {dz_error:+.6f}), "
            f"rho_error={rho_error:+.6f}"
        )
        if position_error <= 0.001:
            if walkstab.genuine_clip(old, new)[0]:
                return seed, prepared_geo, feasibility, target_old
            inverted = _invert_walk_wait_dust(walkstab, target_old)
            if inverted is not None:
                park_x, park_z, inv_old, _inv_new, inv_rho, _inv_cb = inverted
                log(
                    f"Walking f32 inversion found nearby genuine old={inv_old}, "
                    f"rho={inv_rho:+.6f}; reminting exact WAIT=({park_x:.7f}, {park_z:.7f})"
                )
                continue
        park_x, park_z = _shift_walk_park(seed, old, target_old)
    raise RuntimeError("could not center the prepared walking runway on the exact dust band")


# A half-L target pulse clears the manually rotated/free camera before C-up is requested. This is
# the same input-driven camera handoff used by the live subjectivity regression.
_SUBJECTIVITY_ENTRY_ROWS = (
    [(128, 128, 128, 128, 0, 100)]
    + [(128, 128, 128, 255, 0, 0)] * 8
    + [(128, 128, 128, 128, 0, 0)] * 2
)
# Walking Setup savestate movies execute their first game-frame row.  An extra neutral absorber is
# harmless on flat ground but advances GroundCross/foot state on a slope and changes the later XZ
# trajectory. Keep the movie and control-pipe semantic replay on the same zero-offset timeline.
_SUBJECTIVITY_DTM_ABSORBER_FRAMES = 0
_WALK_NORMAL_CAP = 17.0


def _walking_setup_sim(seed_path: str, seam: SeamGeo, walls=None, floors=None):
    """Replay C-down exit, one-frame turnaround, and cut at the first 17-speed frame."""
    from harness.rollstab import rest as rest_model
    from tww_sim.land.constants import INPUT_DELAY, MOVE, SUBJECTIVITY, WAIT, FREE_WAIT, WAIT_TURN

    state = rest_model.rest_state(
        seed_path, walls=walls if walls is not None else seam.TRIS,
        floors=floors, model_draw=False, dtm_seed=0, noops=0
    )
    if state.state != SUBJECTIVITY:
        raise RuntimeError(
            "Walking Setup requires a captured, settled first-person seed"
        )

    down_frame = None
    walk_start_frame = None
    saw_turn = False
    for frame in range(96):
        if state.state == SUBJECTIVITY:
            sx, sy = 128, 128
        elif down_frame is None:
            sx, sy = 128, 1
            down_frame = frame
        elif saw_turn and state.state in (WAIT, FREE_WAIT) and walk_start_frame is None:
            sx, sy = 128, 254
            walk_start_frame = frame
        elif walk_start_frame is not None:
            sx, sy = 128, 254
        else:
            sx, sy = 128, 128
        state.step(sx, sy, buttons=0, csx=128, csy=0)
        if state.state == WAIT_TURN:
            saw_turn = True
        if state.state == MOVE and state.nspeed >= _WALK_NORMAL_CAP:
            if getattr(state, "wall_hit", False):
                raise RuntimeError(
                    "the normalized walking approach touched wall collision before speed 17"
                )
            old = (state.pos_x, state.pos_z)
            speed = state.speedF
            state.enter_cut_from_move(128, 254, csx=128, csy=0, aim=state.facing)
            new = (state.pos_x, state.pos_z)
            semantic_transition = frame + 1
            transition_frame = semantic_transition + _SUBJECTIVITY_DTM_ABSORBER_FRAMES
            candidate = dict(
                old=old, new=new, facing=state.facing, speedF=speed,
                transition_frame=transition_frame,
                turn_down_frame=down_frame,
                walk_start_frame=walk_start_frame,
                # The DTM row is authored INPUT_DELAY frames before the delivered B edge.
                # One frame late lets the approach run into WallCorrect before CUT_F starts.
                b_frame=transition_frame - INPUT_DELAY,
            )
            replayed = _replay_walking_setup_rows(
                seed_path, seam, _walking_setup_rows(candidate, tail_frames=2),
                walls=walls, floors=floors,
            )
            if replayed is None:
                raise RuntimeError(
                    "the authored Walking Setup did not deliver B at the modeled cut frame"
                )
            if (not _f32_equal(replayed["old"][0], old[0])
                    or not _f32_equal(replayed["old"][1], old[1])
                    or not _f32_equal(replayed["new"][0], new[0])
                    or not _f32_equal(replayed["new"][1], new[1])):
                raise RuntimeError(
                    "the authored Walking Setup replay diverged from the modeled cut transition"
                )
            return candidate
    raise RuntimeError("the normalized turnaround setup did not reach speed 17 within 96 frames")


def _walking_setup_rows(hit: dict, tail_frames: int = 45) -> list[dict]:
    transition = int(hit["transition_frame"])
    b_frame = int(hit["b_frame"])
    turn_down = int(hit["turn_down_frame"])
    walk_start = int(hit["walk_start_frame"])
    rows = []
    for frame in range(transition + max(2, int(tail_frames))):
        absorber = frame < _SUBJECTIVITY_DTM_ABSORBER_FRAMES
        semantic_frame = frame - _SUBJECTIVITY_DTM_ABSORBER_FRAMES
        if absorber or semantic_frame < turn_down:
            stick_y = 128
        elif semantic_frame == turn_down:
            stick_y = 1
        elif semantic_frame < walk_start:
            stick_y = 128
        else:
            stick_y = 254
        rows.append(dict(
            frame=frame,
            stickX=128,
            stickY=stick_y,
            cstickX=128,
            cstickY=0,
            buttons=(0x200 if frame == b_frame else 0),
            delivery_absorber=absorber,
        ))
    return rows


def _replay_walking_setup_rows(seed_path: str, seam: SeamGeo,
                               rows: list[dict], walls=None,
                               floors=None) -> dict | None:
    """Replay authored rows and dispatch CUT_F when the delayed B edge reaches the game."""
    from harness.rollstab import rest as rest_model
    from tww_sim.land.constants import MOVE, SUBJECTIVITY

    state = rest_model.rest_state(
        seed_path, walls=walls if walls is not None else seam.TRIS,
        floors=floors, model_draw=False, dtm_seed=0, noops=0
    )
    if state.state != SUBJECTIVITY:
        return None
    for row in rows:
        if row.get("delivery_absorber"):
            continue
        current = (
            int(row["stickX"]), int(row["stickY"]), int(row.get("buttons", 0)),
            0, int(row.get("cstickX", 128)), int(row.get("cstickY", 128)),
        )
        delivered = state._inbuf[0] if state._input_delay and state._inbuf else current
        b_edge = bool(delivered[2] & 0x200) and not bool(state._abtn_prev & 0x200)
        if b_edge:
            if (state.state != MOVE or state.nspeed < _WALK_NORMAL_CAP
                    or getattr(state, "wall_hit", False)):
                return None
            old = (state.pos_x, state.pos_z)
            state.enter_cut_from_move(
                current[0], current[1], csx=current[4], csy=current[5],
                aim=state.facing,
            )
            return dict(old=old, new=(state.pos_x, state.pos_z), facing=state.facing)
        state.step(
            current[0], current[1], buttons=current[2], triggerL=current[3],
            csx=current[4], csy=current[5],
        )
    return None


def _enter_subjectivity_start(reader: ProcReader, control: DolphinControl, log=print) -> LiveState:
    # A previous probe may leave a held override in the TAS control pipe even after loading the
    # clean room anchor. Clear it before issuing the first-person entry gesture.
    control.command("clearinput")
    for sx, sy, csx, csy, buttons, trigger_l in _SUBJECTIVITY_ENTRY_ROWS:
        control.advance_with(
            stickX=sx, stickY=sy, substickX=csx, substickY=csy,
            buttons=buttons, triggerL=trigger_l, frames=1,
        )
    state = read_state(reader)
    if state.state != 1 or abs(state.speedF) > 1e-6:
        raise RuntimeError(
            f"prepared C-up entry did not settle in first person "
            f"(state={state.state}, speed={state.speedF:.6f})"
        )
    control.pause()
    _save_state_stable(control, ANCHOR_SAV, state)
    log(
        f"Prepared first-person start at ({state.x:.7f}, {state.y:.7f}, {state.z:.7f}), "
        f"facing={state.facing}, camera={state.csangle}"
    )
    return state


def _write_subjectivity_pose_paused(reader: ProcReader, x: float, y: float,
                                    z: float, facing: int) -> LiveState:
    """Write a frozen first-person pose without advancing its captured animation phase."""
    player = reader.u32(PLAYER_PTR)
    actor_base = player - 0xD8
    for offset in (0x10C, 0x120):
        reader.write_bytes(actor_base + offset, _pack_f32(x))
        reader.write_bytes(actor_base + offset + 4, _pack_f32(y))
        reader.write_bytes(actor_base + offset + 8, _pack_f32(z))
    # The debug teleport buffers above are consumed only when Dolphin advances. Write
    # Link's live position as well so the captured first-person phase can remain paused.
    reader.write_bytes(player + 0x120, _pack_f32(x))
    reader.write_bytes(player + 0x124, _pack_f32(y))
    reader.write_bytes(player + 0x128, _pack_f32(z))
    for address, value in zip(_DEBUG_POS, (x, y, z)):
        reader.write_bytes(address, _pack_f32(value))
    packed = struct.pack(">H", int(facing) & 0xFFFF)
    reader.write_bytes(_DEBUG_FACING, packed)
    reader.write_bytes(player + 0x12E, packed)
    reader.write_bytes(player + 0x136, packed)
    root = reader.u32(CAMERA_ROOT)
    camera = reader.u32(root + 0x34)
    reader.write_bytes(camera + 0x2B0, packed)
    return read_state(reader)


def _savestate_contains_xyz(path: str, x: float, y: float, z: float) -> bool:
    if not os.path.isfile(path):
        return False
    expected = _pack_f32(x) + _pack_f32(y) + _pack_f32(z)
    with open(path, "rb") as savestate:
        return expected in savestate.read()


def _save_state_stable(control: DolphinControl, path: str, state: LiveState,
                       timeout: float = 10.0) -> str:
    """Save to a fresh path and wait until Dolphin's asynchronous file is complete and stable."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    control.pause()
    control.save_state(path)
    deadline = time.monotonic() + timeout
    last_signature = None
    stable_since = None
    while time.monotonic() < deadline:
        try:
            stat = os.stat(path)
            signature = (stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            signature = None
        now = time.monotonic()
        if signature is not None and signature == last_signature:
            stable_since = stable_since if stable_since is not None else now
            if (now - stable_since >= 0.5
                    and _savestate_contains_xyz(path, state.x, state.y, state.z)):
                return path
        else:
            last_signature = signature
            stable_since = now if signature is not None else None
        time.sleep(0.1)
    raise RuntimeError(f"Dolphin did not finish writing savestate {path}")


_SUBJECTIVITY_FULL_YAW_STEP = 655


def _subjectivity_yaw_plan(current: int, requested: int, lo: int,
                           hi: int) -> tuple[int, int] | None:
    """Choose the nearest controller-stable first-person heading inside the selected range."""
    choices = []
    for steps in range(-51, 52):
        settled = (int(current) + steps * _SUBJECTIVITY_FULL_YAW_STEP) & 0xFFFF
        if angle_in_range(settled, lo, hi):
            choices.append((_circular_distance(settled, requested), abs(steps), steps, settled))
    if not choices:
        return None
    _distance, _turns, steps, settled = min(choices)
    return steps, settled


def _write_subjectivity_pose(reader: ProcReader, control: DolphinControl, x: float,
                              y: float, z: float, facing: int, lo: int = 0,
                              hi: int = 0xFFFF, log=print) -> LiveState:
    """Set a frozen first-person pose and turn to an in-range controller-stable heading."""
    player = reader.u32(PLAYER_PTR)
    if read_state(reader).state != 1:
        raise RuntimeError("cannot set Walking Setup pose before first person is active")

    def write_pose(angle):
        _write_subjectivity_pose_paused(reader, x, y, z, angle)

    requested = int(facing) & 0xFFFF
    # Preserve the camera's live globe heading while teleporting. A direct mAngleY write is rebuilt
    # by the first-person camera on the next update, so heading changes must use the main stick.
    write_pose(_camera_angle(reader))
    control.advance_with(substickX=128, substickY=128, frames=4)

    current = read_state(reader).facing & 0xFFFF
    plan = _subjectivity_yaw_plan(current, requested, lo, hi)
    if plan is None:
        raise RuntimeError(
            "the selected angle range contains no controller-stable first-person facing"
        )
    steps, planned = plan
    turn_x = 0 if steps > 0 else 255
    for _ in range(abs(steps)):
        control.advance_with(
            stickX=turn_x, stickY=128, substickX=128, substickY=128, frames=1
        )

    # Flush the two delayed main-stick samples, then let the first-person camera converge to Link.
    control.advance_with(
        stickX=128, stickY=128, substickX=128, substickY=128, frames=14
    )
    settled = read_state(reader)
    if not angle_in_range(settled.facing, lo, hi):
        raise RuntimeError(
            f"controller-stable first-person facing {settled.facing} fell outside "
            f"the selected range {lo}-{hi} (planned {planned})"
        )
    # Re-apply the frozen position after camera settling; subjectivity keeps speed at zero.
    write_pose(settled.facing)
    control.advance_with(substickX=128, substickY=128, frames=6)
    state = read_state(reader)
    if state.state != 1 or abs(state.speedF) > 1e-6:
        raise RuntimeError(
            f"first-person pose did not remain frozen (state={state.state}, "
            f"speed={state.speedF:.6f})"
        )
    error = math.hypot(state.x - x, state.z - z)
    if error > 0.01:
        raise RuntimeError(f"first-person teleport drifted by {error:.6f} units")
    log(
        f"Settled first-person pose at ({state.x:.7f}, {state.y:.7f}, {state.z:.7f}), "
        f"requested={requested}, facing={state.facing}, camera={state.csangle}"
    )
    return state


def _measure_live_walking_old(reader: ProcReader, control: DolphinControl
                              ) -> tuple[int, LiveState, dict]:
    """Run the phase-normalizing turnaround and return the first speed-cap MOVE frame."""
    from tww_sim.land.constants import SUBJECTIVITY, WAIT, FREE_WAIT, WAIT_TURN

    down_frame = None
    turn_settle_frame = None
    walk_start_frame = None
    saw_turn = False
    for frame in range(96):
        before = read_state(reader)
        if before.state == SUBJECTIVITY:
            stick_y = 128
        elif down_frame is None:
            stick_y = 1
            down_frame = frame
        elif saw_turn and before.state in (WAIT, FREE_WAIT) and walk_start_frame is None:
            stick_y = 254
            walk_start_frame = frame
        elif walk_start_frame is not None:
            stick_y = 254
        else:
            stick_y = 128
        control.advance_with(
            stickX=128,
            stickY=stick_y,
            substickX=128,
            substickY=0,
            buttons=0,
            frames=1,
        )
        state = read_state(reader)
        if state.state == WAIT_TURN:
            saw_turn = True
        if (saw_turn and state.state in (WAIT, FREE_WAIT)
                and turn_settle_frame is None):
            turn_settle_frame = frame
        if state.state == 6 and state.nspeed >= _WALK_NORMAL_CAP:
            if down_frame is None or walk_start_frame is None or turn_settle_frame is None:
                raise RuntimeError("the turnaround normalization did not complete before walking")
            return frame, state, dict(
                turn_down_frame=down_frame,
                turn_settle_frame=turn_settle_frame,
                walk_start_frame=walk_start_frame,
            )
    raise RuntimeError("the normalized turnaround setup did not reach speed 17")


def _matching_exact_dust(old: tuple[float, float], hits: list[tuple]) -> tuple | None:
    """Return the target seam dust row whose old point is bit-exactly the measured old."""
    for hit in hits:
        if _f32_equal(old[0], hit[2]) and _f32_equal(old[1], hit[3]):
            return hit
    return None


def _replay_live_walking_cut(reader: ProcReader, control: DolphinControl,
                             source: str, rows: list[dict]) -> dict | None:
    """Replay one authored B phase and capture the dispatch-frame motion state."""
    _load_state(control, source)
    control.command("clearinput")
    previous = read_state(reader)
    authored_b = None
    for row in rows:
        if row.get("delivery_absorber"):
            continue
        control.advance_with(
            stickX=int(row["stickX"]), stickY=int(row["stickY"]),
            substickX=int(row.get("cstickX", 128)),
            substickY=int(row.get("cstickY", 128)),
            buttons=int(row.get("buttons", 0)), frames=1,
        )
        current = read_state(reader)
        if int(row["buttons"]) & 0x200:
            authored_b = [current.x, current.y, current.z]
        if current.state == 0x42 and previous.state != 0x42:
            return dict(
                frame=int(row["frame"]),
                old=[previous.x, previous.y, previous.z],
                new=[current.x, current.y, current.z],
                facing=current.facing,
                travel=current.travel,
                speedF=current.speedF,
                normal_speed=current.nspeed,
                authored_b=authored_b,
            )
        previous = current
    return None


def _calibrate_live_walking_dispatch(reader: ProcReader, control: DolphinControl,
                                     source: str, hit: dict,
                                     measured: LiveState) -> tuple[dict, list[dict]]:
    """Find the adjacent B row whose CUT dispatch uses the measured speed-cap old point."""
    base_b = int(hit["b_frame"])
    best = None
    try:
        for timing_offset in (0, 1, -1, 2, -2):
            trial_b = base_b + timing_offset
            rows = []
            exists = False
            for original in hit["input_rows"]:
                row = dict(original)
                row["buttons"] = int(row.get("buttons", 0)) & ~0x200
                if int(row["frame"]) == trial_b:
                    row["buttons"] |= 0x200
                    exists = True
                rows.append(row)
            if not exists:
                continue
            transition = _replay_live_walking_cut(reader, control, source, rows)
            if transition is None or transition["normal_speed"] < _WALK_NORMAL_CAP:
                continue
            old = transition["old"]
            distance = math.hypot(old[0] - measured.x, old[2] - measured.z)
            item = (distance, abs(timing_offset), timing_offset, transition, rows)
            if best is None or item[:2] < best[:2]:
                best = item
            if _f32_equal(old[0], measured.x) and _f32_equal(old[2], measured.z):
                break
    finally:
        _load_state(control, source)
    if best is None:
        raise RuntimeError("could not observe a speed-cap CUT_F dispatch near the authored B row")
    distance, _magnitude, timing_offset, transition, rows = best
    if distance > 0.01:
        raise RuntimeError(
            f"nearest live CUT_F dispatch old missed the measured cap point by {distance:.6f}"
        )
    transition["timing_offset"] = timing_offset
    return transition, rows


def _mesh_tris(mesh: dict) -> list:
    """Convert a captured ordered room mesh to collision Tri objects without changing its order."""
    from tww_sim.core.collision import Plane, Tri

    return [
        Tri(poly["v"][0], poly["v"][1], poly["v"][2],
            plane=Plane(poly["n"][0], poly["n"][1], poly["n"][2], poly["d"]))
        for poly in mesh["polys"]
    ]


def _local_floor(floors: list, x: float, z: float, expected_y: float) -> tuple[float, int]:
    """Resolve the same local GroundCross floor Link can snap to from the prepared height."""
    from tww_sim.core.fp import f32, fadds
    from tww_sim.land.floors import ground_cross

    height, index = ground_cross(
        floors, f32(x), fadds(f32(expected_y), f32(60.0)), f32(z)
    )
    if index is None:
        raise RuntimeError(
            f"the prepared Walking Setup has no GroundCross floor at ({x:.7f}, {z:.7f})"
        )
    return float(height), int(index)


def _verify_live_walking_candidate(reader: ProcReader, control: DolphinControl,
                                   hit: dict, seam: SeamGeo,
                                   exact_hits: list[tuple], log=print) -> dict:
    """Replay near B-delivery phases and retain only an exact live CUT_F seam crossing."""
    source = hit["setup"]["savestate"]
    base_b = int(hit["b_frame"])
    failures = []
    try:
        # The savestate's controller delivery phase can differ by one poll from the synthetic
        # seed, especially after subjectivity exits on sloped ground.  This is a bounded timing
        # calibration, not a position search: every accepted row still has to hit exact f32 dust.
        for timing_offset in (0, 1, -1, 2, -2):
            trial_b = base_b + timing_offset
            rows = []
            row_exists = False
            for original in hit["input_rows"]:
                row = dict(original)
                row["buttons"] = int(row.get("buttons", 0)) & ~0x200
                if int(row["frame"]) == trial_b:
                    row["buttons"] |= 0x200
                    row_exists = True
                rows.append(row)
            if not row_exists:
                continue

            _load_state(control, source)
            control.command("clearinput")
            transition = None
            authored_b = None
            previous = read_state(reader)
            for row in rows:
                if row.get("delivery_absorber"):
                    continue
                control.advance_with(
                    stickX=int(row["stickX"]), stickY=int(row["stickY"]),
                    substickX=int(row.get("cstickX", 128)),
                    substickY=int(row.get("cstickY", 128)),
                    buttons=int(row.get("buttons", 0)), frames=1,
                )
                current = read_state(reader)
                if int(row["frame"]) == trial_b:
                    authored_b = [current.x, current.y, current.z]
                if current.state == 0x42 and previous.state != 0x42:
                    transition = dict(
                        frame=int(row["frame"]),
                        old=[previous.x, previous.y, previous.z],
                        new=[current.x, current.y, current.z],
                        facing=current.facing,
                        travel=current.travel,
                        speedF=current.speedF,
                        normal_speed=current.nspeed,
                    )
                    break
                previous = current

            if transition is None:
                failures.append(f"B{timing_offset:+d}: no CUT_F")
                continue
            old_xz = (transition["old"][0], transition["old"][2])
            new_xz = (transition["new"][0], transition["new"][2])
            exact_dust = _matching_exact_dust(old_xz, exact_hits)
            if exact_dust is None or not seam.genuine_clip(old_xz, new_xz):
                failures.append(
                    f"B{timing_offset:+d}: old={old_xz}, new={new_xz}"
                )
                continue

            hit["b_frame"] = trial_b
            hit["transition_frame"] = transition["frame"]
            hit["input_rows"] = rows
            hit["input_summary"] = _compact_rows(rows)
            hit["old"] = old_xz
            hit["new"] = new_xz
            hit["facing"] = transition["facing"]
            hit["travel"] = transition["travel"]
            hit["speedF"] = transition["speedF"]
            hit["normal_speed"] = transition["normal_speed"]
            if timing_offset:
                log(
                    f"Calibrated live B delivery by {timing_offset:+d} authored frame(s); "
                    f"exact CUT_F old=({old_xz[0]:.7f}, {old_xz[1]:.7f})."
                )
            log(
                f"Live verification passed at frame {transition['frame']}: "
                f"old=({old_xz[0]:.7f}, {old_xz[1]:.7f}) -> "
                f"new=({new_xz[0]:.7f}, {new_xz[1]:.7f})."
            )
            return dict(
                authority="Dolphin control-pipe replay",
                authored_b=authored_b,
                **transition,
            )
    finally:
        _load_state(control, source)
    raise RuntimeError(
        "Dolphin did not produce an exact CUT_F seam crossing in the adjacent B-delivery "
        "phases; " + "; ".join(failures)
    )


def _preflight_subjectivity_start(room_walls, x: float, y: float, z: float) -> float:
    """Return the modeled WallCorrect displacement of a proposed stationary teleport."""
    if not room_walls:
        return 0.0
    from tww_sim.core.collision import acch_crr_pos

    start = (float(x), float(y), float(z))
    corrected, info = acch_crr_pos(
        start, start, room_walls, speed_y=0.0, line_check_flag=False
    )
    drift = math.hypot(corrected[0] - start[0], corrected[2] - start[2])
    return drift if info["wall_hit"] else 0.0


def _attempt_simple_walking_setup(reader: ProcReader, control: DolphinControl, geo: dict,
                                  base_csangle: int, lo: int, hi: int, candidate,
                                  attempted_live_facings: set[int],
                                  room_walls: list | None = None,
                                  room_floors: list | None = None, log=print):
    """Try one depth-ranked facing family from the shared settled first-person anchor."""
    from harness.rollstab import seam_feasibility

    clean_geo = dict(geo)
    clean_geo.pop("aim_deg", None)
    probe = SeamGeo(clean_geo, base_csangle)
    facing, total, safe_count, safe = candidate

    angle = facing / 65536.0 * 2.0 * math.pi
    ranked_witnesses = sorted(
        safe,
        key=lambda item: (
            seam_feasibility.cut_tail_outcome(
                probe, facing, item, speedf=17.0, walls=room_walls
            )["next_oob"],
            seam_feasibility.post_clip_depth(
                probe, facing, item, speedf=17.0
            ),
        ),
        reverse=True,
    )
    target_witness = None
    blocked_witnesses = 0
    for witness in ranked_witnesses:
        candidate_x = float(witness[2]) - 70.0 * math.sin(angle)
        candidate_z = float(witness[3]) - 70.0 * math.cos(angle)
        candidate_y = clean_geo["link_y"]
        try:
            if room_floors:
                candidate_y, _floor = _local_floor(
                    room_floors, candidate_x, candidate_z, clean_geo["link_y"]
                )
        except RuntimeError:
            blocked_witnesses += 1
            continue
        if _preflight_subjectivity_start(
            room_walls, candidate_x, candidate_y, candidate_z
        ) > 0.01:
            blocked_witnesses += 1
            continue
        target_witness = witness
        park_x, park_z = candidate_x, candidate_z
        break
    if target_witness is None:
        raise RuntimeError(
            f"all {len(ranked_witnesses)} exact dust runways overlap room collision"
        )
    target_old = target_witness[2:4]
    target_depth = seam_feasibility.post_clip_depth(
        probe, facing, target_witness, speedf=17.0
    )
    log(
        f"Walking Setup selected facing {facing}: genuine={total}, wall-clear={safe_count}, "
        f"usable post-seam depth={target_depth:.3f}"
        + (f" after skipping {blocked_witnesses} obstructed deeper dust point(s)."
           if blocked_witnesses else ".")
    )

    # Normal untargeted camera collision (dCamera_c::bumpCheck) is room-dependent and is not part
    # of CameraManual. Measure the no-B prefix in Dolphin, then invert only its start translation.
    # Every pass reloads the same first-person anchor, so this is deterministic calibration rather
    # than an input brute force. No slash is executed and no movie is started.
    final = None
    solved_seed = None
    prepared_state = None
    seam = None
    dust_cache = {}
    candidate_live_facing = None
    blocked_live_targets = set()
    centering_pairs = set()
    for iteration in range(40):
        _load_state(control, ANCHOR_SAV)
        park_y = clean_geo["link_y"]
        floor_index = None
        if room_floors:
            park_y, floor_index = _local_floor(
                room_floors, park_x, park_z, clean_geo["link_y"]
            )
        modeled_drift = _preflight_subjectivity_start(
            room_walls, park_x, park_y, park_z
        )
        if modeled_drift > 0.01:
            raise RuntimeError(
                f"proposed start overlaps room wall collision "
                f"(modeled push-out {modeled_drift:.6f} units)"
            )
        prepared_state = _write_subjectivity_pose(
            reader, control, park_x, park_y, park_z, facing,
            lo=lo, hi=hi, log=log
        )
        try:
            os.remove(FINAL_ANCHOR_SAV)
        except FileNotFoundError:
            pass
        solved_seed = _capture_prepared_anchor(
            reader, control, FINAL_ANCHOR_SAV, allow_subjectivity=True
        )
        solved_seed["direct_live"] = True
        with open(SEED_PATH, "w", encoding="utf-8") as output:
            json.dump(solved_seed, output, indent=1)

        speed_frame, measured, normalization = _measure_live_walking_old(reader, control)
        from tww_sim.land.constants import INPUT_DELAY
        provisional_transition = (
            speed_frame + 1 + _SUBJECTIVITY_DTM_ABSORBER_FRAMES
        )
        provisional = dict(
            transition_frame=provisional_transition,
            b_frame=provisional_transition - INPUT_DELAY,
            **normalization,
        )
        provisional["input_rows"] = _walking_setup_rows(provisional)
        dispatch, calibrated_rows = _calibrate_live_walking_dispatch(
            reader, control, FINAL_ANCHOR_SAV, provisional, measured
        )
        actual_facing = dispatch["facing"] & 0xFFFF
        actual_travel = dispatch["travel"] & 0xFFFF
        if not angle_in_range(actual_facing, lo, hi):
            raise RuntimeError(
                f"the live walking facing {actual_facing} fell outside the selected range"
            )
        attempted_live_facings.add(actual_facing)
        if candidate_live_facing is not None and actual_facing != candidate_live_facing:
            log(
                f"Turnaround exit facing adjusted during centering "
                f"({candidate_live_facing} -> {actual_facing}); rebuilding exact dust."
            )
        candidate_live_facing = actual_facing
        measured_speedf = dispatch["speedF"]
        # mNormalSpeed reaches the walking cap on slopes, but posMoveFromFootPos projects the
        # actor's integrating speedF onto the ground plane.  Both the cut reach and the wall
        # tests must therefore use the live projected speed and height, not the flat-ground 17.
        live_geo = dict(clean_geo)
        live_geo["link_y"] = dispatch["old"][1]
        seam = SeamGeo(
            live_geo, measured.csangle,
            aim_deg=actual_facing / 65536.0 * 360.0,
        )
        speed_key = struct.pack(">f", float(measured_speedf))
        dust_key = (actual_facing, actual_travel, speed_key)
        if dust_key not in dust_cache:
            _, dust_cache[dust_key] = seam_feasibility.scan_aim(
                seam, actual_facing, speedf=measured_speedf, min_clearance=35.0,
                perp_w=2.0, pstep=0.001, astep=0.2, travel=actual_travel,
            )
        actual_hits = dust_cache[dust_key]
        if not actual_hits:
            raise RuntimeError(
                f"live walking facing {actual_facing} has no wall-clear exact dust; "
                "widen the angle range"
            )

        ranked_actual_hits = sorted(
            actual_hits,
            key=lambda item: (
                seam_feasibility.cut_tail_outcome(
                    seam, actual_facing, item, speedf=measured_speedf,
                    walls=room_walls, travel=actual_travel
                )["next_oob"],
                seam_feasibility.post_clip_depth(
                    seam, actual_facing, item, speedf=measured_speedf,
                    travel=actual_travel
                ),
            ),
            reverse=True,
        )
        target_hit = None
        for possible in ranked_actual_hits:
            possible_key = (
                actual_facing, _pack_f32(possible[2]), _pack_f32(possible[3])
            )
            if possible_key in blocked_live_targets:
                continue
            possible_x = prepared_state.x + float(possible[2]) - dispatch["old"][0]
            possible_z = prepared_state.z + float(possible[3]) - dispatch["old"][2]
            possible_y = clean_geo["link_y"]
            try:
                if room_floors:
                    possible_y, _possible_floor = _local_floor(
                        room_floors, possible_x, possible_z, clean_geo["link_y"]
                    )
            except RuntimeError:
                continue
            if _preflight_subjectivity_start(
                room_walls, possible_x, possible_y, possible_z
            ) <= 0.01:
                target_hit = possible
                break
        if target_hit is None:
            raise RuntimeError(
                f"live facing {actual_facing} has exact dust, but every corresponding "
                "normal-speed-17 runway overlaps room collision"
            )
        target_old = target_hit[2:4]
        desired_semantic_old = (float(target_old[0]), float(target_old[1]))
        deepest_depth = seam_feasibility.post_clip_depth(
            seam, actual_facing, target_hit, speedf=measured_speedf,
            travel=actual_travel
        )
        old = (dispatch["old"][0], dispatch["old"][2])
        new = seam.cut_new(
            old, facing=actual_facing, speedf=measured_speedf, travel=actual_travel
        )
        exact_dust = _matching_exact_dust(old, actual_hits)
        actual_depth = (
            seam_feasibility.post_clip_depth(
                seam, actual_facing, exact_dust, speedf=measured_speedf
                , travel=actual_travel
            ) if exact_dust is not None else float("-inf")
        )
        # scan_aim samples old distance in 0.2-unit rows here. Accept the deepest reachable row,
        # including an adjacent f32 alias from translation inversion, but never a shallow dust hit.
        deep_enough = actual_depth >= deepest_depth - 0.21
        semantic_ready = (
            exact_dust is not None and deep_enough and seam.genuine_clip(old, new)
        )
        if semantic_ready and seam.wall_clearance(*old) > 35.0:
            package_candidate = dict(
                old=old, new=new, facing=actual_facing, speedF=measured_speedf,
                travel=actual_travel, normal_speed=dispatch["normal_speed"],
                transition_frame=dispatch["frame"],
                b_frame=next(
                    int(row["frame"]) for row in calibrated_rows
                    if int(row.get("buttons", 0)) & 0x200
                ),
                transition_state=0x42,
                live_calibrated=True,
                **normalization,
            )
            package_candidate["setup"] = dict(
                mode="walking setup", x=prepared_state.x, y=prepared_state.y,
                z=prepared_state.z, facing=prepared_state.facing,
                camera=prepared_state.csangle, savestate=FINAL_ANCHOR_SAV,
            )
            package_candidate["input_rows"] = _walking_setup_rows(package_candidate)
            package_candidate["live_verification"] = _verify_live_walking_candidate(
                reader, control, package_candidate, seam, actual_hits, log=log
            )
            final = package_candidate
            break
        if iteration == 39:
            raise RuntimeError(
                "the live normalized walking trajectory did not converge onto exact clip dust"
            )

        target_key = (
            actual_facing, _pack_f32(target_old[0]), _pack_f32(target_old[1])
        )
        pair_key = (
            actual_facing,
            _pack_f32(old[0]), _pack_f32(old[1]),
            _pack_f32(desired_semantic_old[0]), _pack_f32(desired_semantic_old[1])
        )
        if pair_key in centering_pairs:
            blocked_live_targets.add(target_key)
            centering_pairs.clear()
            log(
                f"Live f32 centering cycled around dust "
                f"({target_old[0]:.7f}, {target_old[1]:.7f}); trying the next "
                "depth-ranked exact row."
            )
            continue
        centering_pairs.add(pair_key)

        dx = desired_semantic_old[0] - old[0]
        dz = desired_semantic_old[1] - old[1]
        log(
            f"Live camera/exit centering {iteration + 1}/40: "
            f"old=({old[0]}, {old[1]}), facing={actual_facing}, "
            f"semantic target=({desired_semantic_old[0]:.7f}, "
            f"{desired_semantic_old[1]:.7f}), "
            f"delta=({dx:+.6f}, {dz:+.6f})"
        )
        park_x = prepared_state.x + dx
        park_z = prepared_state.z + dz

    # Measurement leaves Dolphin at the no-B old point. Return it to the exact camera-settled start
    # state that was measured and exported.
    _load_state(control, FINAL_ANCHOR_SAV)
    prepared_state = read_state(reader)
    final.update(
        mode="walking setup", clear=True, genuine=True,
        margin=seam.wall_clearance(*final["old"]),
        post_seam_depth=(
            (final["new"][0] - seam.S[0])
            * math.sin((final["facing"] & 0xFFFF) / 65536.0 * 2.0 * math.pi)
            + (final["new"][1] - seam.S[1])
            * math.cos((final["facing"] & 0xFFFF) / 65536.0 * 2.0 * math.pi)
        ),
        collision_mesh=dict(
            walls=len(room_walls or ()), floors=len(room_floors or ()),
            start_floor_index=floor_index,
        ),
        setup=dict(
            mode="walking setup", x=prepared_state.x, y=prepared_state.y,
            z=prepared_state.z, facing=prepared_state.facing,
            camera=prepared_state.csangle, savestate=FINAL_ANCHOR_SAV,
        ),
    )
    final["input_rows"] = _walking_setup_rows(final)
    final["input_summary"] = _compact_rows(final["input_rows"])
    # Recompute every displayed geometric result from the transition Dolphin accepted.
    radians = (final["facing"] & 0xFFFF) / 65536.0 * 2.0 * math.pi
    final["margin"] = seam.wall_clearance(*final["old"])
    final["post_seam_depth"] = (
        (final["new"][0] - seam.S[0]) * math.sin(radians)
        + (final["new"][1] - seam.S[1]) * math.cos(radians)
    )
    tail = seam_feasibility.cut_tail_outcome(
        seam, final["facing"], final["old"], speedf=final["speedF"],
        walls=room_walls, travel=final.get("travel"),
    )
    final["next_frame"] = tail
    if tail["next_oob"]:
        log(
            f"CUT_F tail remains OOB on the following frame at "
            f"({tail['next'][0]:.7f}, {tail['next'][1]:.7f})."
        )
    else:
        log(
            f"Transient clip warning: following frame returns in bounds at "
            f"({tail['next'][0]:.7f}, {tail['next'][1]:.7f}); "
            f"WallCorrect hit={tail['wall_hit']}."
        )
    try:
        modeled = _walking_setup_sim(
            SEED_PATH, seam, walls=room_walls, floors=room_floors
        )
        model_exact = (
            _f32_equal(modeled["old"][0], final["old"][0])
            and _f32_equal(modeled["old"][1], final["old"][1])
            and _f32_equal(modeled["new"][0], final["new"][0])
            and _f32_equal(modeled["new"][1], final["new"][1])
        )
        final["offline_ground_model"] = dict(
            status="bit_exact" if model_exact else "diverged",
            old=list(modeled["old"]), new=list(modeled["new"]),
        )
        if model_exact:
            log("The ordered wall + GroundCross slope model matched live bit-exactly.")
        else:
            log("The offline ground model diverged; requiring Dolphin's exact live gate.")
    except Exception as exc:
        final["offline_ground_model"] = dict(
            status="unsupported", reason=f"{type(exc).__name__}: {exc}",
        )
        log(
            "The offline ground model does not cover this trajectory "
            f"({type(exc).__name__}: {exc}); requiring Dolphin's exact live gate."
        )
    log(
        f"Live-calibrated Walking Setup proved after the phase-normalizing turnaround: "
        f"C-down exit, one-frame down on frame {final['turn_down_frame']}, "
        f"turn settled on frame {final['turn_settle_frame']}, and up began on frame "
        f"{final['walk_start_frame']}. "
        f"B is authored on frame {final['b_frame']}; Link is expected to remain in MOVE there. "
        f"CUT_F begins on frame {final['transition_frame']}, where the reported old coordinate "
        "must be checked."
    )
    return final, seam


def _scan_slope_walk_facing(payload):
    """Process-safe exact-dust worker for one controller-stable slope facing."""
    geo, csangle, facing, speedf = payload
    from harness.rollstab import seam_feasibility

    seam = SeamGeo(geo, csangle, aim_deg=facing / 65536.0 * 360.0)
    _count, hits = seam_feasibility.scan_aim(
        seam, facing, speedf=speedf, min_clearance=35.0,
        perp_w=2.0, pstep=0.001, astep=0.2, travel=facing,
    )
    return facing, speedf, hits


def _rank_slope_walk_facings(geo: dict, csangle: int, stable_origin: int,
                             lo: int, hi: int, room_floors: list,
                             room_walls: list | None = None, log=print):
    """Screen every reachable first-person heading with its local decomp slope speed."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    from tww_sim.core.fp import f32
    from tww_sim.land.floors import GroundState
    from harness.rollstab import seam_feasibility

    clean_geo = dict(geo)
    clean_geo.pop("aim_deg", None)
    probe = SeamGeo(clean_geo, csangle)
    facings = sorted({
        (int(stable_origin) + step * _SUBJECTIVITY_FULL_YAW_STEP) & 0xFFFF
        for step in range(-51, 52)
        if angle_in_range(
            (int(stable_origin) + step * _SUBJECTIVITY_FULL_YAW_STEP) & 0xFFFF,
            lo, hi,
        )
    })
    payloads = []
    for facing in facings:
        radians = facing / 65536.0 * 2.0 * math.pi
        sample_x = probe.S[0] - 42.0 * math.sin(radians)
        sample_z = probe.S[1] - 42.0 * math.cos(radians)
        try:
            _sample_y, floor_index = _local_floor(
                room_floors, sample_x, sample_z, clean_geo["link_y"]
            )
        except RuntimeError:
            continue
        ground = GroundState(
            room_floors, gnd_pla=room_floors[floor_index].pla, ground_hit=True
        )
        speedf = float(ground.scale_speedf(f32(_WALK_NORMAL_CAP), facing))
        payloads.append((clean_geo, csangle, facing, speedf))

    if not payloads:
        return []
    workers = max(1, min(10, multiprocessing.cpu_count() - 2, len(payloads)))
    log(
        f"Slope feasibility: screening {len(payloads)} controller-stable facing(s) "
        f"with per-floor CUT_F speed on {workers} workers."
    )
    with ProcessPoolExecutor(max_workers=workers) as pool:
        screened = list(pool.map(_scan_slope_walk_facing, payloads))

    ranked = []
    for facing, speedf, hits in screened:
        if not hits:
            continue
        seam = SeamGeo(clean_geo, csangle, aim_deg=facing / 65536.0 * 360.0)
        deepest = max(
            seam_feasibility.post_clip_depth(
                seam, facing, hit, speedf=speedf, travel=facing
            )
            for hit in hits
        )
        stable = any(
            seam_feasibility.cut_tail_outcome(
                seam, facing, hit, speedf=speedf, walls=room_walls, travel=facing
            )["next_oob"]
            for hit in hits
        )
        ranked.append(((stable, deepest, len(hits)), (facing, len(hits), len(hits), hits)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        facing, _total, count, _hits = ranked[0][1]
        speed = next(speed for f, speed, _h in screened if f == facing)
        log(
            f"Slope feasibility selected facing {facing}: speedF={speed:.9f}, "
            f"wall-clear exact dust={count}."
        )
    return [candidate for _rank, candidate in ranked]


def _prepare_simple_walking_setup(reader: ProcReader, control: DolphinControl, geo: dict,
                                  base_csangle: int, lo: int, hi: int, budget: float,
                                  room_walls: list | None = None,
                                  room_floors: list | None = None, log=print):
    """Try depth-ranked families until one survives room collision and live camera settling."""
    from harness.rollstab import seam_feasibility

    clean_geo = dict(geo)
    clean_geo.pop("aim_deg", None)
    probe = SeamGeo(clean_geo, base_csangle)
    _load_state(control, BASE_SAV)
    subjectivity = _enter_subjectivity_start(reader, control, log=log)
    if room_floors:
        ranked = _rank_slope_walk_facings(
            clean_geo, base_csangle, subjectivity.facing, lo, hi, room_floors,
            room_walls=room_walls, log=log,
        )
    else:
        ranked = seam_feasibility.best_walk_aim(
            probe, speedf=17.0, min_clearance=35.0, fstep=512,
            budget=max(20.0, min(float(budget), 90.0)), angle_lo=lo, angle_hi=hi,
            prefer_depth=True, prefer_stable=True, return_ranked=True,
        )
    if not ranked:
        raise RuntimeError(
            "no wall-clear slope-adjusted slash displacement exists in the selected angle range"
        )
    attempted_live_facings = set()
    failures = []
    for index, candidate in enumerate(ranked, 1):
        facing = candidate[0]
        log(
            f"Walking Setup candidate {index}/{len(ranked)}: requested facing {facing}."
        )
        try:
            return _attempt_simple_walking_setup(
                reader, control, geo, base_csangle, lo, hi, candidate,
                attempted_live_facings, room_walls=room_walls,
                room_floors=room_floors, log=log,
            )
        except RuntimeError as exc:
            failures.append(f"{facing}: {exc}")
            log(f"Rejected Walking Setup facing {facing}: {exc}; trying the next candidate.")
            _load_state(control, ANCHOR_SAV)

    summary = "; ".join(failures[-4:])
    raise RuntimeError(
        f"all {len(ranked)} depth-ranked Walking Setup candidates were rejected"
        + (f"; last failures: {summary}" if summary else "")
    )

def search_live(target, mode="rolling", angle_lo=None, angle_hi=None, budget=120.0,
                want=4, pid=None, iso_path=None, game_id="GZLJ01", log=print) -> dict:
    game_id = parse_game_id(game_id)
    reader = open_dolphin(pid)
    try:
        log(f"Attached to Dolphin PID {reader.pid}")
        state = ensure_paused_rest(reader)
        log(
            f"Captured room base {state.stage}: pos=({state.x:.7f}, {state.y:.7f}, {state.z:.7f}) "
            f"facing={state.facing} camera={state.csangle}"
        )
        log("Reading active static and movable BG collision in WallCorrect traversal order...")
        mesh, floor_mesh, seam_bg, floor_bg = read_live_target_collision(
            reader, target, state.y
        )
        geo, seam_entry = resolve_geo(mesh, tuple(float(v) for v in target))
        # The supplied Y identifies the vertical seam, not necessarily the walkable floor.
        # Preserve the paused Link state's floor for every prepared runway teleport.
        geo["link_y"] = float(state.y)
        attached_pid = reader.pid
        live_game_id = reader.read_bytes(0x80000000, 6)
    finally:
        reader.close()

    ensure_cut_animation(iso_path, log=log)
    log(
        f"Exported DTM headers will use {game_id.decode('ascii')}; "
        f"the attached game currently reports {live_game_id.decode('ascii', 'replace')}."
    )
    lo, hi = parse_angle_range(angle_lo, angle_hi)
    log(
        f"Resolved seam S=({geo['S'][0]:.7f}, {geo['S'][1]:.7f}, {geo['S'][2]:.7f}), "
        f"interior={geo['interior']:.3f}, seam BG={seam_bg}, floor BG={floor_bg}, "
        f"walls={geo['wallA']['poly']}x{geo['wallB']['poly']}"
    )
    room_walls = _mesh_tris(mesh)
    room_floors = _mesh_tris(floor_mesh)
    log(
        f"Captured complete room collision: {len(room_walls)} ordered wall/roof triangle(s), "
        f"{len(room_floors)} GroundCross candidate triangle(s)."
    )
    floor_delta = abs(state.y - float(target[1]))
    if floor_delta > 1.0:
        log(
            f"Seam vertex Y differs from Link's current floor by {floor_delta:.3f}; "
            f"the prepared runway will preserve captured floor Y={state.y:.7f}."
        )

    mode_key = mode.lower().strip()
    control = DolphinControl(attached_pid)
    control.pause()
    _ensure_standalone_savestates(control, log=log)
    os.makedirs(ANCHOR_DIR, exist_ok=True)
    _save_state_stable(control, BASE_SAV, state)
    log(f"Saved the current room as temporary base {BASE_SAV}")
    reader = open_dolphin(attached_pid, writable=True)
    hits = []
    prepared = None
    try:
        if mode_key.startswith("roll"):
            from harness.rollstab import solver

            _goal, candidates = roll_aim_candidates(geo, state.csangle, lo, hi, log=log)
            candidate = choose_feasible_roll_aim(candidates, log=log)
            candidates = list(getattr(candidate, "_ranked_feasible", (candidate,)))
            candidate_limit = min(32, len(candidates))
            valid_limit = 3
            valid_attempts = 0
            per_facing_budget = float(budget)
            log(
                f"Checking up to {candidate_limit} density-ranked candidate(s) until "
                f"{valid_limit} physical runways are found; each documented family receives "
                f"a {per_facing_budget:.0f}s solver budget."
            )
            attempted = []
            for index, candidate in enumerate(candidates[:candidate_limit], 1):
                log(
                    f"Candidate {index}/{candidate_limit}: requested aim "
                    f"{candidate.aim_deg:.5f} degrees"
                )
                attempted.append(candidate.F)
                try:
                    seed, seam = _prepare_roll_anchor(
                        reader, control, geo, candidate, per_facing_budget, log=log
                    )
                except RuntimeError as exc:
                    log(f"Facing {candidate.F} cannot produce a valid prepared runway: {exc}")
                    continue
                if not angle_in_range(seam.F, lo, hi):
                    log(f"Settled facing {seam.F} fell outside the selected range; skipping it.")
                    continue
                valid_attempts += 1
                log(
                    f"Facing {seam.F} produced physical runway {valid_attempts}/{valid_limit}."
                )
                prepared = _prepared_setup(seed, "rolling")
                solver._BASE.clear()
                solver._BASE_WALLED.clear()
                found = []
                for family in (0.66, 0.78, 0.72, 0.56):
                    log(
                        f"Searching documented c3m={family:.2f} family from centered facing "
                        f"{seam.F}; budget={per_facing_budget:.0f}s."
                    )
                    near_runs = []
                    found = solver.solve_focused(
                        SEED_PATH, seam, dtm_seed=0, budget=per_facing_budget,
                        want=int(want), off_span=1800, verbose=True, procs=None,
                        prefix=(), use_dust=True, c3m=family, near_out=near_runs,
                        dust_hint=getattr(seam, "_dust_hint", None),
                    )
                    if found:
                        break
                    inverted = _invert_near_roll_streams(
                        SEED_PATH, seam, near_runs, seed, log=log
                    )
                    if inverted is None:
                        continue
                    wait_x, wait_z, predicted = inverted
                    wait_facing = round(candidate.aim_deg / 360.0 * 65536.0) & 0xFFFF
                    seed = _mint_prepared(
                        reader, control, BASE_SAV, wait_x, wait_z, geo["link_y"],
                        wait_facing, candidate.csangle, settle_walk=0, log=log,
                    )
                    clean_geo = dict(geo)
                    clean_geo.pop("aim_deg", None)
                    seam = SeamGeo(clean_geo, seed["csangle"], aim_deg=candidate.aim_deg)
                    solver._BASE.clear()
                    solver._BASE_WALLED.clear()
                    fixed = _replay_roll_stream(
                        solver.base(SEED_PATH, dtm_seed=0), predicted["stream"], seam
                    )
                    verified = (
                        fixed and fixed.get("genuine") and fixed.get("clear")
                        and fixed.get("spF_at_A") == 17.0 and fixed.get("facing") == seam.F
                        and solver.wall_faithful(
                            SEED_PATH, fixed["stream"], fixed["old"], seam, 0
                        )
                    )
                    if not verified:
                        log("Inverted near stream failed the live-recaptured wall gate; continuing.")
                        continue
                    fixed["margin"] = solver._perp_margin(
                        seam, fixed["old"], fixed["new"]
                    )
                    prepared = _prepared_setup(seed, "rolling")
                    found = [fixed]
                    log("Near stream converted into an exact wall-faithful rolling clip.")
                    break
                found = [h for h in found if angle_in_range(h.get("facing", seam.F), lo, hi)]
                for hit in found:
                    hit["mode"] = "rolling"
                    hit["setup"] = dict(prepared)
                    hit["input_rows"] = _roll_rows(hit)
                    replayed = _replay_roll_stream(
                        solver.base(SEED_PATH, dtm_seed=0), hit["stream"], seam
                    )
                    if replayed is not None:
                        hit["transition_frame"] = replayed["transition_frame"]
                    hit["input_summary"] = _compact_rows(hit["input_rows"])
                if found:
                    hits.extend(found)
                    geo["aim_deg"] = seam.aim_deg
                    log(f"Exact clip found at prepared facing {seam.F}; Dolphin is at that setup.")
                    break
                if valid_attempts >= valid_limit:
                    log(f"Exhausted {valid_limit} physically valid runway candidate(s).")
                    break
            if not hits:
                log(f"No exact hit in prepared facings: {attempted}")
        elif mode_key.startswith("walking setup"):
            try:
                hit, seam = _prepare_simple_walking_setup(
                    reader, control, geo, state.csangle, lo, hi, budget,
                    room_walls=room_walls, room_floors=room_floors, log=log
                )
            except Exception:
                _load_state(control, BASE_SAV)
                log("Walking Setup failed; restored the original room-base state.")
                raise
            hits = [hit]
            prepared = dict(hit["setup"])
            geo["aim_deg"] = seam.aim_deg
            log("Exact normalized Walking Setup found; Dolphin is paused in first person.")

        elif mode_key.startswith("walk"):
            from harness.rollstab import walkstab

            seed, prepared_geo, feasibility, target_old = _prepare_walk_anchor(
                reader, control, geo, state.csangle, lo, hi, budget, log=log
            )
            prepared = _prepared_setup(seed, "walking")
            geo = prepared_geo
            walkstab.configure(
                SEED_PATH, GEO_PATH, name="live_slash_prepared", dtm_seed=0,
                target_facing=feasibility[0], angle_lo=lo, angle_hi=hi,
                feasibility=feasibility, target_old=target_old,
            )
            log(
                f"Searching walking-slash inputs around physically feasible facing "
                f"{feasibility[0]} from the prepared 200-unit runway..."
            )
            found = walkstab.solve_focused(budget=float(budget), want=int(want), verbose=True)
            hits = [h for h in found if angle_in_range(h.get("facing", 0), lo, hi)]
            for hit in hits:
                hit["mode"] = "walking"
                hit["setup"] = dict(prepared)
                hit["input_rows"] = _walk_rows(hit)
                hit["transition_frame"] = int(hit["N"]) - 1
                hit["input_summary"] = _compact_rows(hit["input_rows"])
            if hits:
                log("Exact walking clip found; Dolphin is paused at the prepared setup.")
        else:
            raise ValueError("mode must be rolling, walking, or Walking Setup")

        if hits:
            for index, hit in enumerate(hits):
                _export_candidate(hit, index, game_id, log=log)
            log(
                "Candidate export complete. Dolphin was not restarted and the DTM was not "
                "played automatically."
            )
    finally:
        reader.close()

    with open(GEO_PATH, "w") as output:
        json.dump(geo, output, indent=1)
    result = dict(
        state=asdict(state),
        prepared=prepared,
        target=list(target),
        angle_range=[lo, hi],
        mode=mode_key,
        seam=seam_entry,
        geo=geo,
        hits=hits,
        limitations=[
            "Walking Setup is exact-gated by a live ControlPipe replay; DTM playback remains manual.",
            "The finder exports a complete DTM and matching start savestate without restarting Dolphin.",
            "The offline ramp foot/waist tier may be unsupported; accepted movement is live-gated.",
            "Walking Setup holds C-down through exit, turnaround, approach, and slash.",
        ],
    )
    os.makedirs(_GEN, exist_ok=True)
    with open(RESULT_PATH, "w") as output:
        json.dump(result, output, indent=1)
    log(f"Search complete: {len(hits)} wall-faithful exact clip setup(s)")
    return result


def status(pid=None) -> LiveState:
    reader = open_dolphin(pid)
    try:
        return read_state(reader)
    finally:
        reader.close()
