"""Read a room's collision (DZB) straight from the extracted game disc, with NO Dolphin and no need to
load the room in-game. Feeds the same ``region_tris`` the live reader (``seam_scan.read_region_tris``)
produces, so the seam-clip scanner runs on any room offline.

Pipeline: RARC archive (Yaz0-decompress if needed) -> ``room.dzb`` -> vertices + triangles ->
per-triangle planes via the bit-exact :func:`tww_sim.core.collision.calc_pla` (the DZB stores NO
planes; the game computes them at load with the same ``cM3d_CalcPla``, so calc_pla reproduces the RAM
planes exactly). DZB vertices are ALREADY in world coordinates — the stage ``MULT`` room placement is
NOT applied (verified: every non-identity-MULT room in the game is a ``sea`` room whose raw DZB centroid
already equals its MULT; applying it double-offset the sea. Dungeons are MULT-identity). See
:func:`region_from_dzb`.

Disc layout (extracted): ``<extract>/files/res/Stage/<Stage>/Room<N>.arc`` (collision ``room.dzb``)
and ``Stage.arc`` (``stage.dzs``, the ``MULT`` room-placement chunk). The extract dir is read from
``dolphin.local.json`` (``tww_extract_dir``).

    python -m harness.collision.dzb_iso stage=M_Dai room=18            # scan a room for clips
    python -m harness.collision.dzb_iso stage=M_Dai room=18 no-standable
"""
import json
import os
import struct
import sys

from tww_sim.core.collision import Tri, calc_pla, bg_is_wall

GROUND_NY_MIN = 0.5


def yaz0_decompress(src):
    """Yaz0 (Nintendo LZ) decompress; returns ``src`` unchanged if not Yaz0-tagged."""
    if src[:4] != b"Yaz0":
        return src
    n = struct.unpack_from(">I", src, 4)[0]
    p, dst = 16, bytearray()
    while len(dst) < n:
        code = src[p]; p += 1
        for i in range(8):
            if len(dst) >= n:
                break
            if code & (0x80 >> i):
                dst.append(src[p]); p += 1
            else:
                b1, b2 = src[p], src[p + 1]; p += 2
                dist = ((b1 & 0xF) << 8) | b2
                cnt = b1 >> 4
                if cnt == 0:
                    cnt = src[p] + 0x12; p += 1
                else:
                    cnt += 2
                r = len(dst) - dist - 1
                for _ in range(cnt):
                    dst.append(dst[r]); r += 1
    return bytes(dst)


def read_rarc(path):
    """Parse a RARC archive (Yaz0-aware) into ``{filename: bytes}`` (files only, flat by name)."""
    b = yaz0_decompress(open(path, "rb").read())
    return read_rarc_bytes(b, path)


def read_rarc_bytes(data, label="<bytes>"):
    """Parse raw RARC/Yaz0 bytes into ``{filename: bytes}`` (files only, flat by name)."""
    b = yaz0_decompress(data)
    if b[:4] != b"RARC":
        raise ValueError("not a RARC: %s" % label)
    info = struct.unpack_from(">I", b, 8)[0]                 # header size == info-block start
    data_off = struct.unpack_from(">I", b, 0x0C)[0]
    _, _, n_files, file_off, _, str_off = struct.unpack_from(">IIIIII", b, info)
    file_off += info; str_off += info
    out = {}
    for i in range(n_files):
        idx, _, tn, doff, dsize = struct.unpack_from(">HHIII", b, file_off + i * 0x14)
        end = b.index(b"\x00", str_off + (tn & 0xFFFFFF))
        nm = b[str_off + (tn & 0xFFFFFF):end].decode("shift_jis", "replace")
        if idx != 0xFFFF:                                   # 0xFFFF == subdirectory entry
            out[nm] = b[0x20 + data_off + doff:0x20 + data_off + doff + dsize]
    return out


def gcm_read_file(iso_path, disc_path):
    """Read one file from a GameCube ISO/GCM by walking the FST. ``disc_path`` is relative to the
    disc root, for example ``files/res/Stage/GanonM/Room0.arc``. This is intentionally tiny and
    read-only so collision tools can use a local disc dump without the optional wwrando dependency."""
    want = disc_path.replace("\\", "/").strip("/")
    with open(iso_path, "rb") as f:
        f.seek(0x424)
        fst_off = struct.unpack(">I", f.read(4))[0]
        f.seek(0x428)
        fst_size = struct.unpack(">I", f.read(4))[0]
        f.seek(fst_off)
        fst = f.read(fst_size)

        root_next = struct.unpack_from(">I", fst, 8)[0]
        names_base = root_next * 12

        def name_at(off):
            start = names_base + off
            end = fst.index(b"\x00", start)
            return fst[start:end].decode("shift_jis", "replace")

        stack = [("", root_next)]
        for i in range(1, root_next):
            while stack and i >= stack[-1][1]:
                stack.pop()
            typ_name, off, size_next = struct.unpack_from(">III", fst, i * 12)
            name = name_at(typ_name & 0x00FFFFFF)
            parent = stack[-1][0] if stack else ""
            path = ("%s/%s" % (parent, name)).strip("/")
            if typ_name & 0x01000000:
                stack.append((path, size_next))
            elif path == want:
                f.seek(off)
                return f.read(size_next)
    raise FileNotFoundError("%s in %s" % (disc_path, iso_path))


def parse_dzb(data):
    """DZB (== in-RAM ``cBgD``) -> ``(verts, tris)``. Header: v_num@0, v_off@4, t_num@8, t_off@0xC;
    vertex = 3x f32 (12 B); triangle = ``u16 v0,v1,v2, plane_id, group`` (10 B). All big-endian."""
    v_num, v_off, t_num, t_off = struct.unpack_from(">IIII", data, 0)
    verts = [struct.unpack_from(">fff", data, v_off + i * 12) for i in range(v_num)]
    tris = [struct.unpack_from(">5H", data, t_off + i * 10) for i in range(t_num)]
    return verts, tris


def _stage_dir(stage, extract_dir=None):
    if extract_dir is None:
        cfg = os.path.join(os.path.dirname(__file__), "..", "..", "dolphin.local.json")
        extract_dir = json.load(open(cfg))["tww_extract_dir"]
    return os.path.join(extract_dir, "files", "res", "Stage", stage)


def room_world_transform(stage, room, extract_dir=None):
    """The room's world placement ``(tx, tz, angY_deg)`` from the stage ``MULT`` chunk (identity if
    absent). Dungeon rooms are commonly identity; sea/overworld rooms carry a real translate+rotate."""
    st = read_rarc(os.path.join(_stage_dir(stage, extract_dir), "Stage.arc"))
    dzs = next(st[k] for k in st if k.lower().endswith(".dzs"))
    nch = struct.unpack_from(">I", dzs, 0)[0]
    for i in range(nch):
        tag, cnt, off = struct.unpack_from(">4sII", dzs, 4 + i * 12)
        if tag == b"MULT":
            for j in range(cnt):
                tx, tz, ang, rm, _ = struct.unpack_from(">ffhBB", dzs, off + j * 0xC)
                if rm == room:
                    return tx, tz, ang * 360.0 / 65536.0
    return 0.0, 0.0, 0.0


def region_from_dzb(dzb_bytes, tx=0.0, tz=0.0, ang=0.0):
    """Build ``(region_tris, box)`` from raw DZB bytes. ``region_tris`` matches
    ``seam_scan.read_region_tris``: ``dict(poly, v, n, T)`` with ``T`` carrying the bit-exact calc_pla
    plane and ``n`` its normal. Returns ``([], None)`` for an empty DZB.

    DZB vertices are stored in WORLD coordinates — the stage ``MULT`` room placement is NOT applied.
    Verified across every non-identity-MULT room in the game (all 50 are the ``sea`` grid): each room's
    raw DZB centroid already matches its MULT (tx,tz) exactly (sea Room44 raw ~(-200000,+300000) ==
    MULT), so applying MULT double-offsets it (the old bug: sea world coords ~2x out). Dungeon rooms are
    MULT-identity, so this was a silent no-op for them. ``(tx,tz,ang)`` are accepted (callers still pass
    the read MULT for the report header) but intentionally ignored here."""
    verts, tris = parse_dzb(dzb_bytes)
    region = []
    for poly, (a, b, c, _tid, _grp) in enumerate(tris):
        v0, v1, v2 = verts[a], verts[b], verts[c]
        T = Tri(v0, v1, v2)                                 # plane via bit-exact calc_pla
        region.append(dict(poly=poly, v=[v0, v1, v2], n=(T.pla.nx, T.pla.ny, T.pla.nz), T=T))
    if not region:
        return [], None
    xs = [c for t in region for c in (t["v"][0][0], t["v"][1][0], t["v"][2][0])]
    ys = [c for t in region for c in (t["v"][0][1], t["v"][1][1], t["v"][2][1])]
    zs = [c for t in region for c in (t["v"][0][2], t["v"][1][2], t["v"][2][2])]
    return region, (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def load_room_region(stage, room, extract_dir=None, transform=True):
    """``(region_tris, box, stage)`` for a room's collision, world-transformed and Dolphin-free."""
    arc = read_rarc(os.path.join(_stage_dir(stage, extract_dir), "Room%d.arc" % room))
    dzb = next(arc[k] for k in arc if k.lower().endswith(".dzb"))
    tx, tz, ang = room_world_transform(stage, room, extract_dir) if transform else (0.0, 0.0, 0.0)
    region, box = region_from_dzb(dzb, tx, tz, ang)
    return region, box, stage


def load_room_region_from_iso(iso_path, stage, room, transform=True):
    """``(region_tris, box, stage)`` for a room's collision read directly from a local GameCube ISO."""
    def disc_file(path):
        try:
            return gcm_read_file(iso_path, path)
        except FileNotFoundError:
            if path.startswith("files/"):
                return gcm_read_file(iso_path, path[6:])
            raise

    room_arc = read_rarc_bytes(
        disc_file("files/res/Stage/%s/Room%d.arc" % (stage, room)),
        "%s/Room%d.arc" % (stage, room))
    dzb = next(room_arc[k] for k in room_arc if k.lower().endswith(".dzb"))
    # DZB vertices are already in world coordinates; keep this read only to mirror load_room_region's
    # validation/reporting path and to catch malformed stage archives early.
    if transform:
        read_rarc_bytes(disc_file("files/res/Stage/%s/Stage.arc" % stage),
                        "%s/Stage.arc" % stage)
    region, box = region_from_dzb(dzb)
    return region, box, stage


def main(argv):
    from harness.collision.seam_locator import scan_region     # the shipped scanner
    stage, room, standable = "M_Dai", 18, True
    for a in argv:
        if a.startswith("stage="):
            stage = a[6:]
        elif a.startswith("room="):
            room = int(a[5:])
        elif a == "no-standable":
            standable = False
    region, box, _ = load_room_region(stage, room)
    walls = sum(1 for t in region if bg_is_wall(t["n"][1]))
    grounds = sum(1 for t in region if t["n"][1] >= GROUND_NY_MIN)
    print("stage=%s room=%d: %d tris (%d walls, %d ground) box=%s"
          % (stage, room, len(region), walls, grounds,
             tuple(round(x, 1) for x in box)), flush=True)
    scan_region(region, box, require_standable=standable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
