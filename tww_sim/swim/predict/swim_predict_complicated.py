"""swim_predict_complicated.py - FULL bit-exact superswim predictor for COMPLICATED input:
ARBITRARY main-stick directions AND arbitrary C-stick (random csy), predicting camera (csangle)
AND position (link_x/z) AND v/anim/air from inputs alone.

Extends swim_predict_full's cold-start build with:
  - GAP 2: ArbitrarySwimState  -- per-frame speed gain from the ACTUAL stick + the live-exact
           stick->angle table (stick_angle.py), not the ess/neu/chg token. (cruise unchanged.)
  - GAP 1: CameraArbitrary      -- camera yaw under arbitrary (csx,csy) via the live-captured
           2-D omega table (omega_table.csv); no csy<=64 freeze, no auto-follow (disproven).

KEY ORDERING (live-pinned on cap_randcharge, worst 0): the facing/gain m34E8 uses cam[f] (the
CURRENT frame's csangle), NOT cam[f-1]. The camera updates with a 1-frame INPUT lag (csx[f-1]
drives cam[f]), so cam[f] is known before the stick is read. Per frame:
  1. cam.step(csx,csy)  -> cam[f]   (consumes the PREVIOUS frame's pending omega)
  2. s.cam = cam[f];  ArbitrarySwimState.step  -> v/anim/air (gain uses cam[f], facing snaps)
  3. direction chase (m34E8 = stickAngle + 0x8000 + cam[f]) + exact disp magnitude -> dx,dz
(In the clean cruise regime cam barely moves per frame, so cam[f]==cam[f-1] and this matches
swim_predict_exact's validated cruise path -- no regression.)

Imports swim.sim / swim_exact / camera_* / swim_* READ-ONLY. Modifies none.
"""
from __future__ import annotations
import sys, csv, math

from .. import sim as S
from . import swim_exact as E
from . import stick_angle as SA
from ...core.camera.camera_arbitrary import CameraArbitrary
from .swim_arbitrary import ArbitrarySwimState


def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def predict_full(frames, v0, anim0, air0, st0, cam0, facing0, mrate0, x0=0.0, z0=0.0):
    """Predict per-frame state from inputs only, through the cold-start build, for arbitrary
    main + C-stick. frames: list of (sx,sy,csx,csy). mrate0: logged move0_mrate at the seed."""
    s = ArbitrarySwimState(v=v0, anim=anim0, air=air0, mrate=mrate0)
    s.state = st0
    s._entry_tax = False
    s.cam = cam0
    s.facing = facing0
    cam = CameraArbitrary(csangle=cam0)
    shape_y = facing0 & 0xFFFF
    cur_y = facing0 & 0xFFFF
    x, z = x0, z0
    pending_snap = None
    out = []
    cam_prev = cam0
    for (sx, sy, csx, csy) in frames:
        cam_now = cam.step(csx, csy)          # cam[f] (camera consumes csx[f-1])
        s.cam = cam_now                       # facing/gain SNAP target uses cam[f] (live-pinned
                                              # on cap_randcharge: cam[f-1] is wrong by up to 408)
        s.set_stick(sx, sy)
        d, tag = s.step(s.action_for(sx, sy))
        # deferred 180-deg charge snap from last frame lands now
        if pending_snap is not None:
            shape_y = cur_y = pending_snap
            pending_snap = None
        a = SA.angle_s16(sx, sy)
        if a is not None:
            # The MOVE-direction chase (cur_y -> dx/dz) consumes cam[f-1]: the camera updates
            # LATER in the frame than posMove. (In a charge the move comes from the SNAP, which
            # targets cam[f]; in cruise/steer the gradual chase uses cam[f-1] -- matches the
            # validated swim_predict_full cruise path, bit-exact on cap_full*.)
            m_snap = (a + 0x8000 + cam_now) & 0xFFFF      # charge snap target (cam[f])
            m_move = (a + 0x8000 + cam_prev) & 0xFFFF     # gradual move chase (cam[f-1])
            if abs(_s16(m_snap - shape_y)) > E.SNAP_CONE:  # DIR_BACKWARD -> snap NEXT frame
                pending_snap = m_snap & 0xFFFF
            else:                                          # gradual chase -> applies now
                shape_y = E.cLib_addCalcAngleS(shape_y, m_move, E.SHAPE_SCALE, E.SHAPE_MAX, E.SHAPE_MIN)
                cur_y = E.cLib_addCalcAngleS(cur_y, shape_y, E.CUR_SCALE, E.CUR_MAX, E.CUR_MIN)
        cam_prev = cam_now
        f1 = E.disp_magnitude(s.v, s.anim, s.air)
        dx, dz = E.move_dxdz(f1, cur_y)
        x = S.f32(x + dx); z = S.f32(z + dz)
        out.append({"cam": cam_now, "x": x, "z": z, "v": s.v, "anim": s.anim,
                    "air": s.air, "state": s.state, "facing": s.facing, "cur_y": cur_y,
                    "dx": dx, "dz": dz, "tag": tag})
    return out


def validate_full(csv_path, verbose=False):
    rows = list(csv.DictReader(open(csv_path)))
    f0 = rows[0]
    frames = [(int(r["sx"]), int(r["sy"]), int(r["csx"]), int(r["csy"])) for r in rows[1:]]
    mrate0 = float(f0.get("move0_mrate", "nan"))
    pred = predict_full(frames, v0=float(f0["potential_speed"]), anim0=float(f0["anim_frame"]),
                        air0=int(f0["air"]), st0=int(f0["link_state"]), cam0=int(f0["csangle"]),
                        facing0=int(f0["facing"]), mrate0=mrate0,
                        x0=float(f0["link_x"]), z0=float(f0["link_z"]))
    wcam = nbad = 0
    wv = wa = wpos = 0.0
    wvf = waf = wpf = -1
    if verbose:
        print(f"{'f':>4} {'tag':>3} {'cam':>5} {'v':>10} {'anim':>10} {'pos':>10}")
    for r, p in zip(rows[1:], pred):
        ce = ((p["cam"] - int(r["csangle"]) + 0x8000) & 0xFFFF) - 0x8000
        ve = p["v"] - float(r["potential_speed"])
        cyc = 26.0 if int(r["link_state"]) == 54 else 23.0
        ad = (p["anim"] - float(r["anim_frame"])) % cyc
        ae = min(ad, cyc - ad)
        pe = math.hypot(p["x"] - float(r["link_x"]), p["z"] - float(r["link_z"]))
        if ce:
            nbad += 1
        if abs(ce) > wcam:
            wcam = abs(ce)
        if abs(ve) > wv:
            wv, wvf = abs(ve), int(r["f"])
        if ae > wa:
            wa, waf = ae, int(r["f"])
        if pe > wpos:
            wpos, wpf = pe, int(r["f"])
        if verbose:
            print(f"{int(r['f']):>4} {p['tag']:>3} {ce:>5} {ve:>10.5f} {ae:>10.5f} {pe:>10.4f}")
    print(f"{csv_path}: {len(frames)}fr  cam={wcam}hw ({nbad} off)  v={wv:.5f}@f{wvf}  "
          f"anim={wa:.5f}@f{waf}  POS={wpos:.4f}@f{wpf}")
    return wcam, wv, wa, wpos


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    for p in args or ["tests/cap_randcharge.csv", "tests/cap_camchaos.csv"]:
        try:
            validate_full(p, verbose=("-v" in sys.argv))
        except FileNotFoundError:
            print(f"{p}: (missing)")
