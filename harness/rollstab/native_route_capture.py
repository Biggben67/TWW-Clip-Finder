"""Pointer-free, JP player/room snapshots for the native route worker."""
from pathlib import Path
import re
import struct
from functools import lru_cache

from harness.rollstab.capture_walls import DBGS, _room_bg, active_bg_slots
from harness.collision.live_moving_drop import ACTOR_PTR

ROOT = Path(__file__).resolve().parents[2]
FORMATS = {"u8": ">B", "u16": ">H", "s16": ">h", "u32": ">I", "s32": ">i", "f32": ">f"}


@lru_cache(maxsize=1)
def camera_schema():
    sections = {}
    section = None
    for line in (ROOT / "native/slash_route/camera_fields.inc").read_text().splitlines():
        if line.startswith("#if defined(CAMERA_"):
            section = line.split("CAMERA_")[1].split(")")[0]
            sections[section] = []
        match = re.fullmatch(r"CAM_(FIELD|VEC|GLOBE)\(([^,]+), (0x[\dA-F]+)(?:, (\w+))?\)", line)
        if match:
            macro, name, offset, kind = match.groups()
            fmt = FORMATS[kind] if macro == "FIELD" else {"VEC": ">3f", "GLOBE": ">fhh"}[macro]
            sections[section].append((name, int(offset, 16), fmt, macro == "FIELD"))
    return sections


def camera_actor_references(ram):
    lockon = struct.unpack_from(">I", ram, 0x12C)[0]
    actor_id = struct.unpack_from(">I", ram, 0x130)[0]
    forced = struct.unpack_from(">I", ram, 0x134)[0]
    bg_owner = struct.unpack_from(">I", ram, 0x33C)[0]
    return {"lockon": bool(lockon),
            "forced": bool(forced and actor_id != 0xFFFFFFFF),
            "bg_owner": bool(bg_owner)}


def capture_camera(reader):
    body = _pointer(reader, _pointer(reader, 0x803AD380) + 0x34) + 0x244
    ram = reader.read_bytes(body, 0x78C)
    style = struct.unpack_from(">I", ram, 0x750)[0]
    algorithm = reader.u32(style + 4) if 0x80000000 <= style < 0x81800000 else -1
    arm = {1: "FOLLOW", 10: "MANUAL", 4: "SUBJECT"}.get(algorithm)
    result = {"algorithm": algorithm, "arm": arm, "fields": {}}
    for name, offset, fmt, scalar in camera_schema()["COMMON"] + camera_schema().get(arm, []):
        value = struct.unpack_from(fmt, ram, offset)
        result["fields"][name] = value[0] if scalar else value
    # mpLockonActor can retain a pointer after its process ID is cleared. Only
    # active references require an actor in the native camera scene.
    result["actor_references"] = camera_actor_references(ram)
    result["external_target"] = any(result["actor_references"].values())
    # JP omits three pointers before this common play-data tail (US offsets - 12).
    play = 0x803B8108 + 0x12A0
    if reader.u32(play + 0x4870 - 12) != body - 0x244:
        raise RuntimeError("JP camera-info layout does not match the active camera")
    result["attention"] = reader.u32(play + 0x4878 - 12)
    result["status0"] = reader.u32(play + 0x4A28 - 12)
    result["status1"] = reader.u32(play + 0x4A2C - 12)
    return result


def capture_pad(reader):
    """The normalized P1 pad consumed by TWW, not a guessed DTM lane."""
    ram = reader.read_bytes(0x80398308, 0x3C)
    fields = {}
    for name, offset in (("mx", 0), ("my", 4), ("distance", 8),
                         ("cx", 16), ("cy", 20), ("cvalue", 24),
                         ("analog_a", 32), ("analog_b", 36), ("tl", 40), ("tr", 44)):
        fields[name] = struct.unpack_from(">f", ram, offset)[0]
    fields["angle"] = (struct.unpack_from(">h", ram, 12)[0] + 0x8000) & 0xFFFF
    fields["cangle"] = struct.unpack_from(">h", ram, 28)[0]
    fields["hold"] = struct.unpack_from(">H", ram, 48)[0]
    fields["trigger"] = struct.unpack_from(">H", ram, 50)[0]
    fields["lock_l"], fields["lock_r"] = ram[53], ram[55]
    fields["trig_l"], fields["trig_r"] = ram[54], ram[56]
    fields["item_button"] = sum(native for mask, native in
                                ((0x100, 1), (0x80, 2), (0x40, 4), (0x20, 8),
                                 (0x800, 16), (0x200, 32), (0x400, 64)) if fields["hold"] & mask)
    fields["target"] = bool(fields["lock_l"])
    return fields


def _pointer(reader, address):
    value = reader.u32(address)
    if not 0x80000000 <= value < 0x81800000:
        raise RuntimeError("invalid native capture pointer at 0x%08X" % address)
    return value


def capture_room(reader, bg=None):
    bg = _room_bg(reader) if bg is None else int(bg)
    wrapper = _pointer(reader, DBGS + bg * 0x14)
    header = _pointer(reader, wrapper + 0x94)
    tables = []
    for offset, width, maximum in ((0, 12, 65535), (8, 10, 65535),
                                   (16, 2, 65535), (24, 20, 65535),
                                   (32, 52, 65535), (40, 16, 65535)):
        count = reader.u32(header + offset)
        if not 0 < count <= maximum:
            raise RuntimeError("invalid native collision table count")
        address = _pointer(reader, header + offset + 4)
        # The runtime vertex buffer includes room placement; preserve that buffer.
        if offset == 0:
            address = _pointer(reader, wrapper + 0x90)
        tables.append(reader.read_bytes(address, count * width))
    vertices, triangles, blocks, trees, groups, attrs = tables
    result = {
        "bg": bg, "vertices": list(struct.iter_unpack(">3f", vertices)),
        "triangles": list(struct.iter_unpack(">5H", triangles)),
        "blocks": [r[0] for r in struct.iter_unpack(">H", blocks)],
        "trees": list(struct.iter_unpack(">10H", trees)),
        "attributes": list(struct.iter_unpack(">4I", attrs)), "groups": [],
    }
    for offset in range(0, len(groups), 52):
        result["groups"].append({
            "scale": struct.unpack_from(">3f", groups, offset + 4),
            "rotation": struct.unpack_from(">3h", groups, offset + 16),
            "translation": struct.unpack_from(">3f", groups, offset + 24),
            "links": struct.unpack_from(">6H", groups, offset + 36),
            "info": struct.unpack_from(">I", groups, offset + 48)[0],
        })
    def buffer(offset, count, stride):
        return reader.read_bytes(_pointer(reader, wrapper + offset), count * stride)
    planes = buffer(0x88, len(result["triangles"]), 0x18)
    links = buffer(0x8C, len(result["triangles"]), 8)
    block_heads = buffer(0x98, len(result["blocks"]), 6)
    nodes = buffer(0xA0, len(result["trees"]), 0x1C)
    bounds = buffer(0x9C, len(result["groups"]), 0x20)
    result["runtime"] = {
        "planes": [struct.unpack_from(">4f", planes, i * 0x18) for i in range(len(result["triangles"]))],
        "links": [struct.unpack_from(">H", links, i * 8)[0] for i in range(len(result["triangles"]))],
        "blocks": list(struct.iter_unpack(">3H", block_heads)),
        "nodes": [struct.unpack_from(">6f", nodes, i * 0x1C) for i in range(len(result["trees"]))],
        "groups": [struct.unpack_from(">6f", bounds, i * 0x20 + 4) for i in range(len(result["groups"]))],
        "root": reader.u32(wrapper + 0xA4), "flags": reader.u8(wrapper + 0x6C),
        "move_counter": reader.u8(wrapper + 0x74), "priority": reader.u8(wrapper + 0x75),
        "ignore_plane": reader.u32(wrapper + 0x78),
    }
    return result


def capture_world(reader):
    """Keep separate BG slots, live planes and traversal tables; never weld actor meshes."""
    rooms = [capture_room(reader, bg) for bg in active_bg_slots(reader)]
    if not rooms:
        raise RuntimeError("Dolphin has no registered background collision")
    return {"backgrounds": rooms}


def collision_signature(reader):
    """Detect geometry changes during capture instead of freezing a moving actor silently."""
    import hashlib
    digest = hashlib.sha256()
    for bg in active_bg_slots(reader):
        wrapper = _pointer(reader, DBGS + bg * 0x14)
        header = _pointer(reader, wrapper + 0x94)
        digest.update(struct.pack(">III", bg, wrapper, header))
        for offset, count_at, stride in ((0x90, 0, 12), (0x88, 8, 0x18)):
            count = reader.u32(header + count_at)
            if not 0 < count <= 65535:
                raise RuntimeError("invalid live collision signature table")
            digest.update(reader.read_bytes(_pointer(reader, wrapper + offset), count * stride))
    return digest.digest()


def capture_seed(reader, snapshot):
    actor = _pointer(reader, ACTOR_PTR)
    def vector(offset):
        return struct.unpack(">3f", reader.read_bytes(actor + offset, 12))
    def matrix(address):
        return struct.unpack(">12f", reader.read_bytes(address, 48))
    schema = ROOT / "native" / "slash_route" / "seed_fields.inc"
    fields = {"mProcVar3.m34D6": struct.unpack(">h", reader.read_bytes(actor + 0x34D6, 2))[0]}
    formats = {"u8": ">B", "u16": ">H", "s16": ">h", "u32": ">I", "s32": ">i", "f32": ">f"}
    for name, offset, kind in re.findall(r"FIELD\(([^,]+),\s*(0x[\dA-Fa-f]+),\s*(\w+)\)", schema.read_text()):
        fmt = formats[kind]
        fields[name] = struct.unpack(fmt, reader.read_bytes(actor + int(offset, 16), struct.calcsize(fmt)))[0]
    model = _pointer(reader, actor + 0x32C)
    joints = _pointer(reader, model + 0x8C)
    old = _pointer(reader, actor + 0x31B4)
    transforms = _pointer(reader, old + 0x1C)
    quats = _pointer(reader, old + 0x20)
    old_frame = {
        "flag": bool(reader.u8(old)), "active": bool(reader.u8(old + 1)),
        "counter": reader.f32(old + 4), "previous": reader.f32(old + 8),
        "rate": reader.f32(old + 12), "value10": reader.f32(old + 16),
        "value14": reader.f32(old + 20), "start": reader.u16(old + 24),
        "end": reader.u16(old + 26), "transforms": [],
    }
    for i in range(42):
        row = reader.read_bytes(transforms + i * 32, 32)
        old_frame["transforms"].append({
            "scale": struct.unpack_from(">3f", row),
            "rotation": struct.unpack_from(">3h", row, 12),
            "translation": struct.unpack_from(">3f", row, 20),
            "quat": struct.unpack(">4f", reader.read_bytes(quats + i * 16, 16)),
        })
    def anim(clock, heap, ratio):
        pointer = reader.u32(actor + ratio + 4)
        return {
            "index": reader.u16(actor + heap),
            "active": bool(pointer), "pointer": pointer,
            "pose_frame": reader.f32(pointer + 8) if pointer else 0.0,
            "ratio": reader.f32(actor + ratio),
            "attribute": reader.u8(actor + clock + 4), "state": reader.u8(actor + clock + 5),
            "start": reader.s16(actor + clock + 6), "end": reader.s16(actor + clock + 8),
            "loop": reader.s16(actor + clock + 10), "rate": reader.f32(actor + clock + 12),
            "frame": reader.f32(actor + clock + 16),
        }
    feet = []
    for offset in (0x3DB8, 0x3ED0):
        feet.append({
            "flag0": reader.u8(actor + offset), "flag1": reader.u8(actor + offset + 1),
            **{"angle%X" % k: reader.s16(actor + offset + k) for k in (2, 4, 6, 8, 10)},
            "toe": vector(offset + 12), "heel": vector(offset + 24),
            "ground": vector(offset + 36), "height": reader.f32(actor + offset + 48),
        })
    under = [anim(0x302C+i*20, 0x2FDC+i*16, 0x2FB4+i*8) for i in range(2)]
    upper = [anim(0x3054+i*20, 0x2FFC+i*16, 0x2FC4+i*8) for i in range(3)]
    for item in upper:
        for index, lower in enumerate(under):
            if item["pointer"] and item["pointer"] == lower["pointer"]:
                item["under_alias"] = index
                break
        if item["index"] == 0xFFFF and "under_alias" not in item:
            if item["ratio"] != 0.0 and item["active"]:
                raise RuntimeError("unresolved live upper animation reference")
            item["active"] = False
    for item in under + upper:
        del item["pointer"]
    return {
        "fields": fields, "proc": snapshot.state, "pos": (snapshot.x, snapshot.y, snapshot.z),
        "collision_flags": reader.u32(actor + 0x494),
        "demo_type": reader.u16(actor + 0x304), "demo_mode": reader.u32(actor + 0x314),
        "old_pos": vector(0x1E4), "speed": vector(0x220), "travel": snapshot.travel,
        "shape": struct.unpack(">3h", reader.read_bytes(actor + 0x20C, 6)),
        "life": reader.u8(0x803B810B), "camera": snapshot.camera,
        "camera_state": capture_camera(reader), "pad": capture_pad(reader),
        "attention_pos": vector(0x274), "eye_pos": vector(0x260),
        "under": under, "upper": upper,
        "old_frame": old_frame, "feet": feet, "inverse": matrix(actor + 0x37B4),
        "joint_matrices": [matrix(joints + i * 48) for i in range(42)],
        "vectors": {name: vector(offset) for name, offset in {
            "mOldSpeed": 0x3694, "m3688": 0x3688, "m36A0": 0x36A0,
            "m36AC": 0x36AC, "m36B8": 0x36B8, "m3700": 0x3700,
            "m3724": 0x3724, "m3730": 0x3730, "m373C": 0x373C,
        }.items()},
    }
