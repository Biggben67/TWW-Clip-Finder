"""swim_predict_exact.py — UNIFIED bit-exact superswim predictor.

From slot 10 and a per-frame list of (main-stick sx,sy + C-stick csx,csy), predict every frame:
  - csangle (camera yaw)      -- camera_exact.CameraExact          (BIT-EXACT)
  - potential_speed / anim / air / link_state  -- swim.sim.SwimState (BIT-EXACT physics)
  - link_x / link_z           -- swim_exact (exact direction chase + exact disp magnitude)

Does NOT modify tww_sim/swim/sim.py or any planner (imports them read-only).

Per-frame ordering (matches the game; the "1-frame lags" are deterministic update ORDER, NOT
SI-poll timing -- bug#2 is a pipe artifact, see memory):
  1. setStickData reads the camera -> the heading uses cam[f-1] (the camera updates LATER in
     the frame). So we snapshot cam BEFORE stepping the camera.
  2. SwimState.step advances physics+anim and gives this frame's v/anim/air.
  3. movement direction: m34E8 = mMainStickAngle(sx,sy) + 0x8000 + cam[f-1]; chase shape_angle.y
     then current.angle.y (swim_exact.step_direction). dx = f1*sin(cur_y), dz = f1*cos(cur_y),
     f1 = swim_exact.disp_magnitude(v, anim, air) (signed; v<0 -> reversed bearing).
  4. CameraExact.step advances the camera for next frame.

Seeding mirrors run_tests.py: loadstate; neutral pre-advance (substickY=0); write air/speed;
read v0/anim0/air0/state0; SwimState(...).state=st0; _entry_tax=False.
"""
from __future__ import annotations
import sys, csv, math

from .. import sim as S
from . import swim_exact as E
from ...core.camera.camera_exact import CameraExact


def stick_to_action(sx, sy):
    """Map a raw main-stick (sx,sy) to a SwimState action token (same rule swim_predict uses)."""
    if sx == 128 and sy == 128:
        return 'neu'
    if sx == 128 and sy in (0, 255):
        return 'chg'
    if sy < 128:
        return 'ess' if sy == 110 else f'ess:{sy}'
    return 'ess'


def predict(frames, v0, anim0, air0, st0, cam0, facing0, x0=0.0, z0=0.0, entry_tax=False):
    """Predict per-frame state from inputs only. frames: list of (sx,sy,csx,csy).
    Returns list of dicts with cam,x,z,v,anim,air,state,facing,cur_y."""
    s = S.SwimState(v=v0, anim=anim0, air=air0)
    s.state = st0
    s._entry_tax = entry_tax
    s.cam = cam0                     # keep the sim's facing/charge-axis camera in sync (it uses
                                     # self.cam for the charge-gain sign); we drive it each frame.
    s.facing = facing0
    cam = CameraExact(csangle=cam0)
    shape_y = facing0 & 0xFFFF
    cur_y = facing0 & 0xFFFF
    x, z = x0, z0
    out = []
    for (sx, sy, csx, csy) in frames:
        cam_prev = cam.csangle               # cam[f-1] (camera updates LATER this frame)
        s.cam = cam_prev                     # sim uses self.cam for the facing/charge-gain sign
        # --- physics (bit-exact) ---
        d, tag = s.step(stick_to_action(sx, sy))
        # --- movement direction (exact s16 chase) + magnitude (exact) ---
        sa = S.stick_angle_deg(sx, sy)
        if sa is None:                       # neutral main stick: no swim input -> no turn
            pass                              # cur_y/shape_y unchanged
        else:
            m34e8 = (S.deg_to_s16(sa) + 0x8000 + cam_prev) & 0xFFFF
            shape_y, cur_y = E.step_direction(shape_y, cur_y, m34e8)
        f1 = E.disp_magnitude(s.v, s.anim, s.air)
        dx, dz = E.move_dxdz(f1, cur_y)
        x = S.f32(x + dx)
        z = S.f32(z + dz)
        # --- camera advance (for next frame) ---
        cam.step(csx, csy)
        out.append({"cam": cam.csangle, "x": x, "z": z, "v": s.v, "anim": s.anim,
                    "air": s.air, "state": s.state, "facing": s.facing, "cur_y": cur_y,
                    "dx": dx, "dz": dz, "tag": tag})
    return out


def validate(csv_path, verbose=True):
    rows = list(csv.DictReader(open(csv_path)))
    f0 = rows[0]
    frames = [(int(r["sx"]), int(r["sy"]), int(r["csx"]), int(r["csy"])) for r in rows[1:]]
    x0, z0 = float(f0["link_x"]), float(f0["link_z"])
    pred = predict(frames, v0=float(f0["potential_speed"]), anim0=float(f0["anim_frame"]),
                   air0=int(f0["air"]), st0=int(f0["link_state"]), cam0=int(f0["csangle"]),
                   facing0=int(f0["facing"]), x0=x0, z0=z0)
    wcam = 0
    wv = wa = wpos = wdx = 0.0
    nbad_cam = 0
    if verbose:
        print(f"{'f':>3} {'cam_err':>7} {'v_err':>9} {'anim_err':>9} {'x_err':>9} {'z_err':>9} {'dxz_err':>8}")
    for r, p in zip(rows[1:], pred):
        ce = ((p["cam"] - int(r["csangle"]) + 0x8000) & 0xFFFF) - 0x8000
        ve = p["v"] - float(r["potential_speed"])
        ae = p["anim"] - float(r["anim_frame"])
        xe = p["x"] - float(r["link_x"])
        ze = p["z"] - float(r["link_z"])
        dxe = math.hypot(p["dx"] - float(r["dx"]), p["dz"] - float(r["dz"]))
        if ce:
            nbad_cam += 1
        wcam = max(wcam, abs(ce))
        wv = max(wv, abs(ve)); wa = max(wa, abs(ae))
        wpos = max(wpos, math.hypot(xe, ze)); wdx = max(wdx, dxe)
        f = int(r["f"])
        if verbose and (f <= 4 or f % 5 == 0):
            print(f"{f:>3} {ce:>7} {ve:>9.4f} {ae:>9.4f} {xe:>9.3f} {ze:>9.3f} {dxe:>8.4f}")
    print(f"{csv_path}: cam worst={wcam}hw ({nbad_cam} off)  v={wv:.4f}  anim={wa:.4f}  "
          f"pos={wpos:.3f}  per-frame dxz={wdx:.4f}")
    return wcam, wv, wa, wpos


def validate_from_cruise(csv_path):
    """BIT-EXACT cruise/steer validation. Runs the camera from f0 (rest seed, where it's
    bit-exact) but seeds the SWIM physics from the first state-55 (cruise) frame using LIVE
    values -- avoiding the cold-start/pump anim scramble (a separate sub-model, currently
    blocked by the clobbered slate 10). This is the steering regime: camera + position.
    Result on capB/capC/cap_hold160/cap_ramp/cap_reversal/cap_tap = 0hw / 0.0000 pos."""
    rows = list(csv.DictReader(open(csv_path)))
    k = next((i for i, r in enumerate(rows) if int(r["link_state"]) == 55), None)
    if k is None:
        print(f"{csv_path}: no state-55 frame"); return None
    cam = CameraExact(csangle=int(rows[0]["csangle"]))
    s = rows[k]
    sim = S.SwimState(v=float(s["potential_speed"]), anim=float(s["anim_frame"]), air=int(s["air"]))
    sim.state = 55; sim._entry_tax = False
    shape_y = cur_y = int(s["facing"]) & 0xFFFF
    x, z = float(s["link_x"]), float(s["link_z"])
    wc = wv = wa = wpos = 0
    for i, r in enumerate(rows[1:], 1):
        cam_prev = cam.csangle
        sx, sy, csx, csy = int(r["sx"]), int(r["sy"]), int(r["csx"]), int(r["csy"])
        if i >= k + 1:
            sim.cam = cam_prev
            d, tag = sim.step(stick_to_action(sx, sy))
            sa = S.stick_angle_deg(sx, sy)
            if sa is not None:
                m = (S.deg_to_s16(sa) + 0x8000 + cam_prev) & 0xFFFF
                shape_y, cur_y = E.step_direction(shape_y, cur_y, m)
            f1 = E.disp_magnitude(sim.v, sim.anim, sim.air)
            dx, dz = E.move_dxdz(f1, cur_y)
            x = S.f32(x + dx); z = S.f32(z + dz)
            wc = max(wc, abs(((cam_prev - int(rows[i-1]["csangle"]) + 0x8000) & 0xFFFF) - 0x8000))
            wv = max(wv, abs(sim.v - float(r["potential_speed"])))
            wa = max(wa, abs(sim.anim - float(r["anim_frame"])))
            wpos = max(wpos, math.hypot(x - float(r["link_x"]), z - float(r["link_z"])))
        cam.step(csx, csy)
    print(f"{csv_path}: seed@f{k} st55, {len(rows)-1-k}fr  cam={wc}hw  v={wv:.5f}  "
          f"anim={wa:.5f}  POS={wpos:.4f}")
    return wpos


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--cruise" in sys.argv:
        for p in args or ["capB.csv", "capC.csv", "cap_hold160.csv", "cap_ramp.csv",
                          "cap_reversal.csv", "cap_tap.csv"]:
            try:
                validate_from_cruise(p)
            except FileNotFoundError:
                print(f"{p}: (missing)")
    else:
        for p in args or ["capA.csv", "capB.csv", "cap_hold160.csv", "cap_hold170.csv",
                          "cap_tap.csv", "cap_reversal.csv", "cap_ramp.csv"]:
            try:
                validate(p, verbose=("-v" in sys.argv))
            except FileNotFoundError:
                print(f"{p}: (missing)")
