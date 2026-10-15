"""capture_cull.py — read the LIVE culling frustum + actor cull verdicts from a running TWW.

Memory-source-agnostic: every read goes through a small ``rd`` reader object exposing
``read_bytes(gc_addr, n)`` (big-endian GameCube memory). Two adapters use the SAME cull-scan:
  * :class:`HostReader` — host process, via ``dolphin_mem`` (ReadProcessMemory). Used by this
    CLI and by harness/cull_viewer/server.py.
  * an in-Dolphin ``dolphin.memory`` reader — an in-Dolphin ``cull_viewer`` runs this same logic
    *inside* Dolphin (no attach; frame-synced).

What it reads (JP/GZLJ01, confirmed live 2026-07-05 vs the .dmw watch file + US decomp layout;
see knowledge/mechanics/culling.md):
  * camera_class ``[[0x803AD380]+0x34]`` — view matrix (world->camera), eye/center/up, and the
    view_class fovy/aspect/near (== US f_op_view.h offsets).
  * ``mDoLib_clipper`` singleton (static ``0x80398bfc``) — the EXACT culling frustum: fovy/aspect/
    near, the **cull-point far** (``GetCullPoint``; distinct from the render far), and 4 planes.
  * the actor list (head ``0x803654CC``): each frustum-culled (``fopAcStts_CULL_e``) ``fopAc_ac_c``'s
    cullType/cullMtx/box/cullSizeFar + the game's own ``fopAcCnd_NODRAW_e``.

Per box-culled actor we run OUR port (:mod:`tww_sim.core.camera.frustum` ``clip_box``) on the live
view*cullMtx and cull box, and report ``agree`` = (our verdict == the game's NODRAW flag). Live-
validated: 60/60 box actors agreed, 0 mismatches.

Usage:
  python -m harness.capture.capture_cull            # camera+clipper snapshot (plane cross-check)
  python -m harness.capture.capture_cull actors     # full actor cull table
  python -m harness.capture.capture_cull full out=cull.json
"""
import os, sys, json, struct

import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
from tww_sim.core.camera.frustum import build_frustum, mtx_concat, transform_point

# --- JP/GZLJ01 addresses -----------------------------------------------------------------
CAM_BASE = 0x803AD380            # [[CAM_BASE]+0x34] = camera_class (: camera_process_class : view_class)
CAM_PTR_OFF = 0x34

# view_class fields (offsets from camera_class; == US f_op_view.h, verified live on JP)
VC = {"near": 0xC8, "far": 0xCC, "fovy": 0xD0, "aspect": 0xD4,
      "eye": 0xD8, "center": 0xE4, "up": 0xF0, "viewMtx": 0x140}

# mDoLib_clipper::mClipper singleton (JP static). Fields per JSystem/J3DU/J3DUClipper.h:
#   +0x04 Vec mPlane[4]   +0x4C mFovY   +0x50 mAspect   +0x54 mNear   +0x58 mFar (cull point)
CLIPPER_ADDR = 0x80398bfc
CLIPPER_FP = struct.pack(">fff", 60.0, 1.28, 1.0)  # fovy/aspect/near fingerprint (fallback locator)

# actor list / fopAc_ac_c (JP)
ACTOR_LIST_HEAD = 0x803654CC     # u32 -> head node of the intrusive actor list
NODE_NEXT = 0x00                 # node->next
NODE_GPTR = 0x0C                 # node->actor (fopAc_ac_c*)
AC = {"pid": 0x08, "cullType": 0x1BF, "status": 0x1C4, "condition": 0x1C8,
      "pos": 0x1F8, "cullMtx": 0x22C, "boxMin": 0x230, "boxMax": 0x23C, "cullFar": 0x248}
FOP_STTS_CULL = 0x100            # fopAcStts_CULL_e — actor participates in frustum culling
FOP_CND_NODRAW = 0x04            # fopAcCnd_NODRAW_e — game set "culled this frame"

# preset cull boxes l_cullSizeBox[14] (min,max), from f_op_actor_mng.cpp
L_CULLBOX = [((-40,0,-40),(40,125,40)),((-25,0,-25),(25,50,25)),((-50,0,-50),(50,100,50)),
             ((-75,0,-75),(75,150,75)),((-100,0,-100),(100,800,100)),((-125,0,-125),(125,250,125)),
             ((-150,0,-150),(150,300,150)),((-200,0,-200),(200,400,200)),((-600,0,-600),(600,900,600)),
             ((-250,0,-50),(250,450,50)),((-60,0,-20),(40,130,150)),((-75,0,-75),(75,210,75)),
             ((-70,-100,-80),(70,240,100)),((-60,-20,-60),(60,160,60))]
CULLBOX_CUSTOM = 0x0E            # cullType <= this is a box; 0x0F.. are spheres
LINK_X = 0x803D78FC              # link_x/y/z static f32 (y=+4, z=+8)


# --- reader-agnostic memory helpers ------------------------------------------------------
def _u32(rd, a): return struct.unpack(">I", rd.read_bytes(a, 4))[0]
def _u16(rd, a): return struct.unpack(">H", rd.read_bytes(a, 2))[0]
def _u8(rd, a):  return rd.read_bytes(a, 1)[0]
def _f32(rd, a): return struct.unpack(">f", rd.read_bytes(a, 4))[0]
def _vec3(rd, a): return list(struct.unpack(">fff", rd.read_bytes(a, 12)))
def _mtx34(rd, a):
    f = struct.unpack(">12f", rd.read_bytes(a, 48))
    return [list(f[0:4]), list(f[4:8]), list(f[8:12])]
def _valid(p): return 0x80000000 <= p < 0x81800000


class HostReader:
    """Host-side reader over dolphin_mem (ReadProcessMemory). Lazy-imports dolphin_mem so this
    module stays importable inside Dolphin's embedded Python (which has no dolphin_mem)."""
    def __init__(self):
        import dolphin_mem as dm
        self._dm = dm
        self.h, self.mem1 = dm.attach()
    def read_bytes(self, addr, n):
        return self._dm.read_bytes(self.h, self.mem1, addr, n)


# --- camera / clipper --------------------------------------------------------------------
def read_camera(rd):
    cam = _u32(rd, _u32(rd, CAM_BASE) + CAM_PTR_OFF)   # [[0x803AD380]+0x34]
    return {
        "camera_class": cam,
        "fovy": _f32(rd, cam + VC["fovy"]), "aspect": _f32(rd, cam + VC["aspect"]),
        "near": _f32(rd, cam + VC["near"]), "render_far": _f32(rd, cam + VC["far"]),
        "eye": _vec3(rd, cam + VC["eye"]), "center": _vec3(rd, cam + VC["center"]),
        "up": _vec3(rd, cam + VC["up"]), "viewMtx": _mtx34(rd, cam + VC["viewMtx"]),
    }


def _locate_clipper(rd):
    try:
        fovy, aspect, near = struct.unpack(">fff", rd.read_bytes(CLIPPER_ADDR + 0x4C, 12))
        if 10.0 < fovy < 170.0 and 0.5 < aspect < 3.0 and near > 0.0:
            return CLIPPER_ADDR
    except Exception:
        pass
    # fallback: scan MEM1 for the fovy/aspect/near fingerprint (address is stable per build)
    data = rd.read_bytes(0x80000000, 0x2000000)
    i = data.find(CLIPPER_FP)
    if i < 0:
        raise RuntimeError("mDoLib_clipper not found (fingerprint fovy=60/aspect=1.28/near=1.0)")
    return 0x80000000 + i - 0x4C


def read_clipper(rd):
    c = _locate_clipper(rd)
    return {
        "clipper_addr": c,
        "fovy": _f32(rd, c + 0x4C), "aspect": _f32(rd, c + 0x50), "near": _f32(rd, c + 0x54),
        "far": _f32(rd, c + 0x58),   # cull point (GetCullPoint), NOT the render far
        "planes": [_vec3(rd, c + 0x04 + p * 12) for p in range(4)],
    }


# --- actors ------------------------------------------------------------------------------
_PROC_NAMES = None
def _proc_name(pid):
    global _PROC_NAMES
    if _PROC_NAMES is None:
        _PROC_NAMES = {}
        # Optional proc-id -> name map (falls back to "#<id>"); untracked game data -- supply at
        # _generated/proc_name_structs.csv or via TWW_PROC_NAMES.
        csvp = os.environ.get("TWW_PROC_NAMES") or os.path.join(
            _rb, "_generated", "proc_name_structs.csv")
        try:
            import csv
            with open(csvp, newline="") as f:
                for row in csv.DictReader(f):
                    nm, val = (row.get("ProcName") or "").strip(), (row.get("ProcValue") or "").strip()
                    if nm and val:
                        try: _PROC_NAMES.setdefault(int(val, 0), nm)
                        except ValueError: pass
        except OSError:
            pass
    return _PROC_NAMES.get(pid, f"#{pid}")


def _box_world_corners(bmin, bmax, cullMtx):
    """8 AABB corners mapped to world space by cullMtx (local->world); if cullMtx is None the box
    is world-absolute. Corner order matches frustum.clip_box."""
    corners = [
        (bmax[0], bmax[1], bmin[2]), (bmax[0], bmax[1], bmax[2]),
        (bmin[0], bmax[1], bmax[2]), (bmin[0], bmax[1], bmin[2]),
        (bmax[0], bmin[1], bmin[2]), (bmax[0], bmin[1], bmax[2]),
        (bmin[0], bmin[1], bmax[2]), (bmin[0], bmin[1], bmin[2]),
    ]
    if cullMtx is None:
        return [list(c) for c in corners]
    return [list(transform_point(cullMtx, c)) for c in corners]


def read_actors(rd, cam, clip):
    """Enumerate the live actor list; for each frustum-culled (fopAcStts_CULL_e) BOX actor,
    replicate fopAcM_cullingCheck and report our verdict + the game's fopAcCnd_NODRAW_e."""
    view = cam["viewMtx"]
    base_fr = build_frustum(clip["fovy"], clip["aspect"], clip["near"], clip["far"])
    cullpoint = clip["far"]
    out, seen = [], set()
    node = _u32(rd, ACTOR_LIST_HEAD)
    while _valid(node) and node not in seen and len(seen) < 20000:
        seen.add(node)
        gptr = _u32(rd, node + NODE_GPTR)
        node = _u32(rd, node + NODE_NEXT)
        if not _valid(gptr):
            continue
        if not (_u32(rd, gptr + AC["status"]) & FOP_STTS_CULL):
            continue
        pid = _u16(rd, gptr + AC["pid"])
        cullType = _u8(rd, gptr + AC["cullType"])
        cullMtxP = _u32(rd, gptr + AC["cullMtx"])
        cullFar = _f32(rd, gptr + AC["cullFar"])
        game_culled = bool(_u32(rd, gptr + AC["condition"]) & FOP_CND_NODRAW)
        pos = _vec3(rd, gptr + AC["pos"])
        cullMtx = _mtx34(rd, cullMtxP) if _valid(cullMtxP) else None

        is_box = cullType <= CULLBOX_CUSTOM
        our_culled, corners = None, None
        if is_box:
            if cullType == CULLBOX_CUSTOM:
                bmin, bmax = _vec3(rd, gptr + AC["boxMin"]), _vec3(rd, gptr + AC["boxMax"])
            else:
                bmin = [float(v) for v in L_CULLBOX[cullType][0]]
                bmax = [float(v) for v in L_CULLBOX[cullType][1]]
            pMtx = mtx_concat(view, cullMtx) if cullMtx is not None else view
            fr = base_fr.with_far(cullFar * cullpoint) if cullFar > 0.0 else base_fr
            our_culled = fr.clip_box(pMtx, bmin, bmax)
            corners = _box_world_corners(bmin, bmax, cullMtx)
        out.append({
            "name": _proc_name(pid), "pid": pid, "addr": gptr, "pos": pos,
            "cullType": cullType, "is_box": is_box, "cullFar": cullFar,
            "our_culled": our_culled, "game_culled": game_culled,
            "agree": (our_culled == game_culled) if our_culled is not None else None,
            "corners": corners,
        })
    return out


# --- frustum geometry (viewer drawing, not the cull test) --------------------------------
def frustum_world_corners(eye, center, up, fovy, aspect, near, far):
    """8 world-space corners of the view frustum: near face [bl,br,tr,tl] then far face."""
    import math
    def sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
    def add(*vs): return [sum(c) for c in zip(*vs)]
    def scale(v, s): return [v[0]*s, v[1]*s, v[2]*s]
    def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
    def norm(v):
        m = math.sqrt(sum(c*c for c in v)) or 1.0
        return [c/m for c in v]
    fwd = norm(sub(center, eye)); right = norm(cross(fwd, up)); up2 = cross(right, fwd)
    tan = math.tan(math.radians(fovy) * 0.5)
    def face(dist):
        c = add(eye, scale(fwd, dist)); hh = dist * tan; hw = hh * aspect
        return [add(c, scale(right, -hw), scale(up2, -hh)), add(c, scale(right,  hw), scale(up2, -hh)),
                add(c, scale(right,  hw), scale(up2,  hh)), add(c, scale(right, -hw), scale(up2,  hh))]
    return face(near) + face(far)


def full_snapshot(rd):
    """Everything the live viewer needs in one pass."""
    cam = read_camera(rd)
    clip = read_clipper(rd)
    actors = read_actors(rd, cam, clip)
    link = [_f32(rd, LINK_X), _f32(rd, LINK_X + 4), _f32(rd, LINK_X + 8)]
    boxed = [a for a in actors if a["our_culled"] is not None]
    fcorners = frustum_world_corners(cam["eye"], cam["center"], cam["up"],
                                     cam["fovy"], cam["aspect"], cam["near"], clip["far"])
    return {
        "camera": {k: cam[k] for k in ("eye", "center", "up", "fovy", "aspect", "near", "render_far")},
        "cull_far": clip["far"], "frustum_corners": fcorners, "link": link, "actors": actors,
        "counts": {"total": len(actors), "boxed": len(boxed),
                   "agree": sum(1 for a in boxed if a["agree"]),
                   "mismatch": sum(1 for a in boxed if not a["agree"])},
    }


def main():
    opts = dict(tok.split("=", 1) for tok in sys.argv[1:] if "=" in tok)
    flags = {tok for tok in sys.argv[1:] if "=" not in tok}
    rd = HostReader()
    if "actors" in flags or "full" in flags:
        snap = full_snapshot(rd)
        if "out" in opts:
            with open(opts["out"], "w") as f: json.dump(snap, f, indent=2)
            print(f"wrote {opts['out']}")
        c = snap["counts"]
        print(f"cull_far={snap['cull_far']}  actors={c['total']}  boxed={c['boxed']}  "
              f"agree={c['agree']}  mismatch={c['mismatch']}")
        for a in sorted(snap["actors"], key=lambda a: (a["our_culled"] is None,
                                                       a["agree"] is False)):
            v = "sphere" if a["our_culled"] is None else ("CULLED" if a["our_culled"] else "visible")
            flag = "" if a["agree"] in (True, None) else "  <-- MISMATCH vs game"
            print(f"  {a['name']:20s} type{a['cullType']:<3d} {v:7s} game_culled={a['game_culled']}{flag}")
        return
    cam = read_camera(rd); clip = read_clipper(rd)
    fr = build_frustum(clip["fovy"], clip["aspect"], clip["near"], clip["far"])
    max_dp = max(abs(a - b) for gp, op in zip(clip["planes"], fr.planes) for a, b in zip(gp, op))
    print(f"camera_class @ 0x{cam['camera_class']:08x}   clipper @ 0x{clip['clipper_addr']:08x}")
    print(f"fovy={clip['fovy']}  aspect={clip['aspect']}  near={clip['near']}  "
          f"cull_far={clip['far']}  (render_far={cam['render_far']})")
    print(f"eye={[round(v,1) for v in cam['eye']]}  center={[round(v,1) for v in cam['center']]}")
    print(f"plane match vs our port (max abs diff): {max_dp:.2e}")


if __name__ == "__main__":
    main()
