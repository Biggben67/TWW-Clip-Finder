"""swim_predict_full.py - FULL bit-exact superswim predictor: cold-start BUILD -> ESS cruise
-> camera-steer, predicting camera (csangle) AND position (link_x/z) from inputs alone.

Extends the unified cruise predictor (swim_predict_exact) with the LOGGED-mRate cold start
(swim_coldstart.ColdStartSwimState) so the speed-BUILD phase is bit-exact too -- the piece
that was blocked under the base sim's f32(anim+1.0) scramble assumption.

Imports swim.sim / swim_exact / camera_exact / swim_coldstart READ-ONLY. Modifies none.

Per-frame ordering is identical to swim_predict_exact.predict (the camera updates LATER in the
frame, so the heading consumes cam[f-1]):
  1. snapshot cam_prev (= cam[f-1])
  2. ColdStartSwimState.step  -> this frame's v/anim/air/state (cold-start scramble exact)
  3. direction chase (m34E8 = mMainStickAngle + 0x8000 + cam_prev) + exact disp magnitude
  4. CameraExact.step (advance camera for next frame)

SEEDING (run_tests-style, read live at the seed frame): loadstate 10 -> neutral pre-advance
(substickY=0) -> write air/speed -> read v0/anim0/air0/st0 AND mRate0 (move0_mrate) AND
cam0(csangle)/facing0/x0/z0. Pass mrate0 into predict_full.
"""
from __future__ import annotations
import sys, csv, math

from .. import sim as S
from . import swim_exact as E
from ...core.camera.camera_exact import CameraExact
from ..coldstart import ColdStartSwimState
from .swim_predict_exact import stick_to_action


def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def predict_full(frames, v0, anim0, air0, st0, cam0, facing0, mrate0,
                 x0=0.0, z0=0.0):
    """Predict per-frame state from inputs only, through the cold-start build.
    frames: list of (sx,sy,csx,csy). mrate0: logged move0_mrate at the seed (cold-start).

    Direction model (live-pinned on the full BUILD->cruise->steer run):
      - A DIR_BACKWARD snap (the per-frame 180-deg charge flip) lands NEXT frame: the move on
        the snap frame uses the OLD heading; the new heading applies the following frame. This
        is the same 1-frame facing-snap lag the base SwimState models with _pending_facing,
        and it is what makes the charge BUILD displacement bit-exact (without it the build
        oscillation is 180-deg out of phase -> ~30-unit error).
      - A gradual chase (cruise / steady steer) applies the SAME frame (no lag) -> bit-exact
        cruise/steer (matches swim_predict_exact's validated cruise path).
    """
    s = ColdStartSwimState(v=v0, anim=anim0, air=air0, mrate=mrate0)
    s.state = st0
    s._entry_tax = False
    s.cam = cam0
    s.facing = facing0
    cam = CameraExact(csangle=cam0)
    shape_y = facing0 & 0xFFFF
    cur_y = facing0 & 0xFFFF
    x, z = x0, z0
    pending_snap = None              # deferred 180-deg charge snap (lands next frame)
    out = []
    for (sx, sy, csx, csy) in frames:
        cam_prev = cam.csangle
        s.cam = cam_prev
        d, tag = s.step(stick_to_action(sx, sy))
        # A charge SNAP scheduled last frame lands now (the 180-deg flip is 1-frame lagged).
        if pending_snap is not None:
            shape_y = cur_y = pending_snap
            pending_snap = None
        # GRADUAL chase applies THIS frame BEFORE the move (live-pinned: the move samples this
        # frame's updated facing -- move_dxdz(f1, live_facing[f]) reproduces live dx/dz to f32
        # noise). A DIR_BACKWARD snap instead DEFERS to next frame (the charge flip lag).
        sa = S.stick_angle_deg(sx, sy)
        if sa is not None:
            m34e8 = (S.deg_to_s16(sa) + 0x8000 + cam_prev) & 0xFFFF
            if abs(_s16(m34e8 - shape_y)) > E.SNAP_CONE:     # DIR_BACKWARD -> snap NEXT frame
                pending_snap = m34e8 & 0xFFFF
            else:                                            # gradual chase -> applies now
                shape_y = E.cLib_addCalcAngleS(shape_y, m34e8, E.SHAPE_SCALE, E.SHAPE_MAX, E.SHAPE_MIN)
                cur_y = E.cLib_addCalcAngleS(cur_y, shape_y, E.CUR_SCALE, E.CUR_MAX, E.CUR_MIN)
        # move uses the heading (post gradual-chase this frame; pre any deferred snap)
        f1 = E.disp_magnitude(s.v, s.anim, s.air)
        dx, dz = E.move_dxdz(f1, cur_y)
        x = S.f32(x + dx); z = S.f32(z + dz)
        cam.step(csx, csy)
        out.append({"cam": cam.csangle, "x": x, "z": z, "v": s.v, "anim": s.anim,
                    "air": s.air, "state": s.state, "facing": s.facing, "cur_y": cur_y,
                    "dx": dx, "dz": dz, "tag": tag})
    return out


def validate_full(csv_path, verbose=False):
    """Validate a full BUILD->cruise->steer capture. CSV must carry a header row of the seed
    plus per-frame (sx,sy,csx,csy) and ground-truth cols. The seed row may carry mrate0 in a
    'move0_mrate' column; otherwise it falls back to 1.0+anim (= base sim, will fail)."""
    rows = list(csv.DictReader(open(csv_path)))
    f0 = rows[0]
    frames = [(int(r["sx"]), int(r["sy"]), int(r["csx"]), int(r["csy"])) for r in rows[1:]]
    mrate0 = float(f0.get("move0_mrate", "nan"))
    if math.isnan(mrate0):
        print(f"{csv_path}: WARNING no move0_mrate in seed row -> cold start will NOT be exact")
        mrate0 = None
    pred = predict_full(frames, v0=float(f0["potential_speed"]), anim0=float(f0["anim_frame"]),
                        air0=int(f0["air"]), st0=int(f0["link_state"]), cam0=int(f0["csangle"]),
                        facing0=int(f0["facing"]), mrate0=mrate0,
                        x0=float(f0["link_x"]), z0=float(f0["link_z"]))
    wcam = nbad = 0
    wv = wa = wpos = 0.0
    worst_pos_f = worst_v_f = worst_a_f = -1
    if verbose:
        print(f"{'f':>4} {'tag':>3} {'cam_err':>7} {'v_err':>10} {'anim_err':>10} {'pos_err':>10}")
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
            wv, worst_v_f = abs(ve), int(r["f"])
        if ae > wa:
            wa, worst_a_f = ae, int(r["f"])
        if pe > wpos:
            wpos, worst_pos_f = pe, int(r["f"])
        if verbose:
            print(f"{int(r['f']):>4} {p['tag']:>3} {ce:>7} {ve:>10.5f} {ae:>10.5f} {pe:>10.4f}")
    print(f"{csv_path}: {len(frames)}fr  cam worst={wcam}hw ({nbad} off)  "
          f"v={wv:.5f}@f{worst_v_f}  anim={wa:.5f}@f{worst_a_f}  POS={wpos:.4f}@f{worst_pos_f}")
    return wcam, wv, wa, wpos


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    for p in args or ["cap_full.csv"]:
        try:
            validate_full(p, verbose=("-v" in sys.argv))
        except FileNotFoundError:
            print(f"{p}: (missing)")
