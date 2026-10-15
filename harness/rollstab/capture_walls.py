"""Capture a room's WALL mesh in WallCorrect traversal order -> a sim fixture (ROADMAP Phase W).

The single-face wall gates feed the sim a hand-picked handful of tris (`kaze_r11_geo.json`); a
CORNER gate needs EVERY wall the cylinder can touch, in the exact order the game corrects against
them, so a two-wall corner resolves in game order. This reads the running room's DZB and emits the
full ordered wall mesh (stored planes, bit-exact) to a fixture the sim loads via
`land.walls.load_ordered_mesh`.

    python -m harness.rollstab.capture_walls                 # room Link stands on -> default fixture
    python -m harness.rollstab.capture_walls out=<path> bg=<n>
    python -m harness.rollstab.capture_walls floors=1 out=<path>   # Phase G GROUND mesh instead

`floors=1` emits the room's GroundCross CANDIDATE set instead (ROADMAP Phase G, loaded via
`land.floors.load_floor_mesh`): per block-grid leaf, the GROUND-list polys (ny >= 0.5,
cBgW_CheckBGround) then the WALL-list polys with ny >= 0.014 (cBgW::RwgGroundCheckGnd/Wall,
c_bg_w.cpp:470-512), groups/octree walked in GroundCrossRp's child order. GroundCross takes the
MAX cross y so order only breaks exact coplanar ties -- kept faithful anyway.

Live-only (needs Dolphin up; see ../tools/DOLPHIN_CONTROL.md). Reads RAM via `dolphin_mem`
(../tools/) only -- self-contained, no dependency on any sibling repo.

The WallCorrect visitation order (d_bg_w.cpp: `WallCorrectGrpRp` -> `WallCorrectRp` octree DFS ->
`RwgWallCorrect`) is reconstructable STATICALLY from the DZB header tables, because `ClassifyPlane`
(c_bg_w.cpp:145) builds each block's wall rwg list in ASCENDING poly index -- so the runtime
pm_rwg/pm_blk linked lists need not be read; a block's wall polys, sorted, ARE its list. See
`knowledge/mechanics/wall-response.md` (corner-ordering section).
"""
import json
import os
import struct
import sys

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

DEFAULT_OUT = os.path.join(_rb, 'fixtures', 'kaze_r11_walls_ordered.json')

# JP/GZLJ01 addresses + struct offsets (see collision.md / c_bg_w.h). dBgS registry, the runtime
# cBgW wrapper, and the loaded cBgD_t (DZB header) block-grid/group tables.
DBGS = 0x803B93A8          # cBgS_ChkElm m_chk_element[256], stride 0x14 (+0 cBgW*, +4 flags bit0=used)
LINK_ACCH = 0x803BD910     # -> dBgS_LinkAcch; +0x554 gnd polyIdx u16, +0x556 gnd bgIdx u16
STAGE_NAME = 0x803BD23C
PLANE_ABS_MIN = 1.0e-5     # G_CM3D_F_ABS_MIN (cM3d_IsZero), matches ClassifyPlane's zero test


def _reader():
    import dolphin_mem as dm
    h, mem1 = dm.attach()

    class R:
        def block(self, a, n):
            return dm.read_bytes(h, mem1, a, n)

        def u8(self, a):
            return self.block(a, 1)[0]

        def u16(self, a):
            return struct.unpack('>H', self.block(a, 2))[0]

        def s32(self, a):
            return struct.unpack('>i', self.block(a, 4))[0]

        def u32(self, a):
            return struct.unpack('>I', self.block(a, 4))[0]
    return R()


def _stage(r):
    return r.block(STAGE_NAME, 11).split(b'\x00')[0].decode('ascii', 'replace')


def _room_bg(r):
    """The bg-registry slot Link's floor is on (== the static room mesh); fall back to the largest
    GLOBAL_e mesh if Link has no floor poly."""
    acch = r.u32(LINK_ACCH)
    if 0x80000000 <= acch < 0x81800000:
        poly = r.u16(acch + 0x554)
        bg = r.u16(acch + 0x556)
        if poly != 0xFFFF and bg != 0x100:
            return bg
    best, best_t = None, -1
    for i in range(256):
        e = DBGS + i * 0x14
        if not (r.u32(e + 0x04) & 1):
            continue
        bgw = r.u32(e + 0x00)
        if not (0x80000000 <= bgw < 0x81800000):
            continue
        if not (r.u8(bgw + 0x6C) & 0x20):          # GLOBAL_e
            continue
        t = r.s32(r.u32(bgw + 0x94) + 0x08)
        if t > best_t:
            best, best_t = i, t
    return best


def active_bg_slots(r):
    """Return valid, currently registered background-collision slots in game order."""
    slots = []
    for i in range(256):
        e = DBGS + i * 0x14
        if not (r.u32(e + 0x04) & 1):
            continue
        bgw = r.u32(e + 0x00)
        if 0x80000000 <= bgw < 0x81800000:
            slots.append(i)
    return slots


def _is_wall(n):
    if all(abs(c) < PLANE_ABS_MIN for c in n[:3]):     # degenerate plane: ClassifyPlane skips
        return False
    return -0.8 <= n[1] < 0.5                           # not roof (ny<-0.8), not ground (ny>=0.5)


def _ground_traversal_order(r, pm_bgd, planes):
    """cBgW::GroundCross's candidate visitation: group DFS -> octree DFS in GroundCrossRp's
    child order (2,3,6,7,0,1,4,5) -> at a leaf, the GROUND polys (ny >= 0.5) ascending, then the
    WALL polys with ny >= 0.014 ascending (RwgGroundCheckGnd/RwgGroundCheckWall)."""
    t_num = r.s32(pm_bgd + 0x08)
    b_num = r.s32(pm_bgd + 0x10); b_tbl = r.u32(pm_bgd + 0x14)
    tree_tbl = r.u32(pm_bgd + 0x1C)
    g_num = r.s32(pm_bgd + 0x20); g_tbl = r.u32(pm_bgd + 0x24)
    starts = [r.u16(b_tbl + i * 2) for i in range(b_num)]
    order = []

    def block_polys(bi):
        lo = starts[bi]
        hi = starts[bi + 1] - 1 if bi != b_num - 1 else t_num - 1
        rng = range(lo, hi + 1)
        for j in rng:                                   # ground list (ClassifyPlane ny >= 0.5)
            n = planes[j]
            if not all(abs(c) < PLANE_ABS_MIN for c in n[:3]) and n[1] >= 0.5:
                order.append(j)
        for j in rng:                                   # wall list, RwgGroundCheckWall ny gate
            if _is_wall(planes[j]) and planes[j][1] >= 0.014:
                order.append(j)

    def tree_rp(i):
        a = tree_tbl + i * 0x14
        if r.u16(a) & 1:
            blk = r.u16(a + 0x04)
            if blk != 0xFFFF:
                block_polys(blk)
        else:
            kids = struct.unpack('>8H', r.block(a + 0x04, 16))
            for ci in (2, 3, 6, 7, 0, 1, 4, 5):         # GroundCrossRp child order
                if kids[ci] != 0xFFFF:
                    tree_rp(kids[ci])

    def grp_rp(gi):
        a = g_tbl + gi * 0x34
        tree_idx = r.u16(a + 0x2E)
        if tree_idx != 0xFFFF:
            tree_rp(tree_idx)
        c = r.u16(a + 0x28)
        while c != 0xFFFF:
            grp_rp(c)
            c = r.u16(g_tbl + c * 0x34 + 0x26)

    root = next(gi for gi in range(g_num) if r.u16(g_tbl + gi * 0x34 + 0x24) == 0xFFFF)
    grp_rp(root)
    return order


def _traversal_order(r, pm_bgd, planes):
    """Reconstruct dBgW::WallCorrect's WALL-poly visitation order from the DZB header tables:
    group tree DFS (m_tree_idx first, then m_first_child/m_next_sibling) -> octree DFS (mChild[0..7])
    -> at a leaf, the block's wall polys in ascending index. Returns the ordered poly-index list."""
    t_num = r.s32(pm_bgd + 0x08)
    b_num = r.s32(pm_bgd + 0x10); b_tbl = r.u32(pm_bgd + 0x14)   # cBgD_Blk_t startTri, stride 2
    tree_tbl = r.u32(pm_bgd + 0x1C)                              # cBgD_Tree_t, stride 0x14
    g_num = r.s32(pm_bgd + 0x20); g_tbl = r.u32(pm_bgd + 0x24)   # cBgD_Grp_t, stride 0x34
    starts = [r.u16(b_tbl + i * 2) for i in range(b_num)]
    order = []

    def block_walls(bi):
        lo = starts[bi]
        hi = starts[bi + 1] - 1 if bi != b_num - 1 else t_num - 1
        for j in range(lo, hi + 1):
            if _is_wall(planes[j]):
                order.append(j)

    def tree_rp(i):
        a = tree_tbl + i * 0x14
        if r.u16(a) & 1:                              # leaf: mBlock @ +0x04
            blk = r.u16(a + 0x04)
            if blk != 0xFFFF:
                block_walls(blk)
        else:                                         # branch: mChild[8] @ +0x04
            for c in struct.unpack('>8H', r.block(a + 0x04, 16)):
                if c != 0xFFFF:
                    tree_rp(c)

    def grp_rp(gi):
        a = g_tbl + gi * 0x34
        tree_idx = r.u16(a + 0x2E)
        if tree_idx != 0xFFFF:
            tree_rp(tree_idx)
        c = r.u16(a + 0x28)                           # m_first_child
        while c != 0xFFFF:
            grp_rp(c)
            c = r.u16(g_tbl + c * 0x34 + 0x26)        # m_next_sibling

    root = next(gi for gi in range(g_num) if r.u16(g_tbl + gi * 0x34 + 0x24) == 0xFFFF)
    grp_rp(root)
    return order


def read_mesh(r, bg=None, floors=False):
    """Read an ordered room mesh from a block/u8/u16/s32/u32-compatible reader."""
    if bg is None:
        bg = _room_bg(r)
    if bg is None:
        raise RuntimeError('could not resolve the current room collision registry slot')
    bgw = r.u32(DBGS + bg * 0x14 + 0x00)
    pm_bgd = r.u32(bgw + 0x94)
    v_num = r.s32(pm_bgd + 0x00)
    t_num = r.s32(pm_bgd + 0x08); t_tbl = r.u32(pm_bgd + 0x0C)
    pm_vtx = r.u32(bgw + 0x90)                        # WORLD-space verts (12B x,y,z)
    pm_tri = r.u32(bgw + 0x88)                        # runtime planes (stride 0x18: nx,ny,nz,d)
    vbytes = r.block(pm_vtx, v_num * 12)
    verts = [struct.unpack_from('>3f', vbytes, i * 12) for i in range(v_num)]
    tbytes = r.block(t_tbl, t_num * 10)
    tris = [struct.unpack_from('>3H', tbytes, i * 10) for i in range(t_num)]   # vtx0,vtx1,vtx2
    pbytes = r.block(pm_tri, t_num * 0x18)
    planes = [struct.unpack_from('>4f', pbytes, i * 0x18) for i in range(t_num)]
    order = (_ground_traversal_order if floors else _traversal_order)(r, pm_bgd, planes)
    polys = []
    for j in order:
        a, b, c = tris[j]
        n = planes[j]
        polys.append({'poly': j,
                      'v': [list(verts[a]), list(verts[b]), list(verts[c])],
                      'n': [n[0], n[1], n[2]], 'd': n[3]})
    return {'stage': _stage(r), 'bg': bg, 'room': None, 'polys': polys}


def capture(out=DEFAULT_OUT, bg=None, floors=False):
    mesh = read_mesh(_reader(), bg=bg, floors=floors)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(mesh, f)
    print('wrote %d ordered %s polys (stage=%s bg=%d) -> %s'
          % (len(mesh['polys']), 'ground-candidate' if floors else 'wall', mesh['stage'],
             mesh['bg'], out), flush=True)
    return 0


if __name__ == '__main__':
    kw = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
    sys.exit(capture(out=kw.get('out', DEFAULT_OUT),
                     bg=int(kw['bg']) if 'bg' in kw else None,
                     floors=bool(int(kw.get('floors', '0')))))
