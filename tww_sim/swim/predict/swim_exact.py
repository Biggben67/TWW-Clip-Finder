"""swim_exact.py — exact (decomp-grounded) movement DIRECTION + displacement MAGNITUDE for
superswim, to make Link's world position bit-exact GIVEN the camera angle. Does NOT modify
tww_sim/swim/sim.py (imports it read-only for f32/cM_scos/cM_ssin/_TIMER_K).

Sources (US line nos; JP logic identical):
  - magnitude: d_a_player_main.cpp::posMoveFromFootPos ~2424-2431  (field_0x60=0.4, field_0x7C=0.35)
  - direction: d_a_player_swim.inc::setSpeedAndAngleSwim ~24-50    (m34E8 + 2x cLib_addCalcAngleS)
  - cLib_addCalcAngleS: c_lib.cpp:160-189
  - getSwimTimerRate: d_a_player_swim.inc:280-294  (== swim.sim _TIMER_K)
See knowledge/history/camera-predict-history.md for the full derivation + validation.
"""
from __future__ import annotations
import math
from .. import sim as S

f32 = S.f32
cM_scos = S.cM_scos              # cos of RADIANS (head-bob)
cM_scos_s16 = S.cM_scos_s16      # cos of an s16 angle (table, >>4 trunc)
_TIMER_K = S._TIMER_K


def cM_ssin_s16(a: int) -> float:
    # sin(x) = cos(x - 90deg); 0x4000 = 90deg in s16
    return cM_scos_s16((a - 0x4000) & 0xFFFF)

FIELD_0x60 = 0.4    # head-bob split
FIELD_0x7C = 0.35   # swim-timer drag denominator coeff (backed out exact from live; 0.35000)
MOVE_END = 23.0     # UNDER_MOVE0 getEnd()


def get_swim_timer_rate(air: int) -> float:
    # d_a_player_swim.inc:283 — itemTimeCount = air+1
    return f32(1.0 - f32(f32(air + 1) * _TIMER_K))


def disp_magnitude(v: float, frame: float, air: int) -> float:
    """Exact per-frame swim displacement magnitude f1 (signed, follows sign of v).
    `frame` must be the LOOPED MOVE0 getFrame() in [0,23) (not the raw post-scramble value).
    f1 = (v*(1-0.4) + 0.4*(v*|cM_scos(pi*frame/23)|)) / (1 + 0.35*getSwimTimerRate(air))."""
    fr = frame - MOVE_END * math.floor(frame / MOVE_END)              # looped [0,23)
    # cos arg is SINGLE precision on console (fdivs fr/MOVE_END then fmuls lfs M_PI = f32 pi;
    # see sim._F32_PI / af_drag). Double pi flips the truncated cos-cell at knife-edge frames.
    c = f32(abs(cM_scos(f32(f32(fr / MOVE_END) * S._F32_PI))))
    num = f32(f32(v * f32(1.0 - FIELD_0x60)) + f32(FIELD_0x60 * f32(v * c)))
    return f32(num / f32(1.0 + f32(FIELD_0x7C * get_swim_timer_rate(air))))


def cLib_addCalcAngleS(value: int, target: int, scale: int, max_step: int, min_step: int):
    """Exact s16 angle chase (c_lib.cpp:160-189). value/target/steps are s16 (we wrap to
    [-0x8000,0x7fff] for the divide/compare). Returns the new value (s16, 0..0xffff masked)."""
    def s16(x):
        x &= 0xFFFF
        return x - 0x10000 if x >= 0x8000 else x
    v = s16(value)
    t = s16(target)
    diff = s16(t - v)
    if v != t:
        step = int(diff / scale)                  # C integer divide, trunc toward 0
        if step > min_step or step < -min_step:
            step = max(-max_step, min(max_step, step))
            v = s16(v + step)
        else:
            if diff >= 0:
                v = s16(v + min_step)
                if s16(t - v) <= 0:
                    v = t
            else:
                v = s16(v - min_step)
                if s16(t - v) >= 0:
                    v = t
    return v & 0xFFFF


# Direction chase constants (HIO mSwim): shape_angle.y chase, then current.angle.y chase.
SHAPE_SCALE, SHAPE_MAX, SHAPE_MIN = 0x11, 0x1388, 0x4B0      # field_0x8 / 0x4 / 0x6
CUR_SCALE, CUR_MAX, CUR_MIN = 2, 0x2000, 0x1000
SNAP_CONE = 0x6000                                          # DIR_BACKWARD (135 deg)


def step_direction(shape_y: int, cur_y: int, m34e8: int):
    """One frame of the swim facing/move-direction chase. Returns (shape_y, cur_y) s16.
    m34e8 = mMainStickAngle + 0x8000 + camAngle (the camera used = cam[f-1], see notes)."""
    def s16(x):
        x &= 0xFFFF
        return x - 0x10000 if x >= 0x8000 else x
    if abs(s16(m34e8 - shape_y)) > SNAP_CONE:        # backward cone -> hard snap
        shape_y = m34e8 & 0xFFFF
        cur_y = m34e8 & 0xFFFF
    else:
        shape_y = cLib_addCalcAngleS(shape_y, m34e8, SHAPE_SCALE, SHAPE_MAX, SHAPE_MIN)
    cur_y = cLib_addCalcAngleS(cur_y, shape_y, CUR_SCALE, CUR_MAX, CUR_MIN)
    return shape_y & 0xFFFF, cur_y & 0xFFFF


def move_dxdz(f1: float, cur_y: int):
    """World displacement from the magnitude f1 (signed; v<0) and move dir current.angle.y (s16).
    speed.x = f1*cM_ssin(cur_y); speed.z = f1*cM_scos(cur_y)  (d_a_player_main.cpp:2430-2431)."""
    return f32(f1 * cM_ssin_s16(cur_y)), f32(f1 * cM_scos_s16(cur_y))


# ---------------------------------------------------------------------------------------
if __name__ == "__main__":
    # self-test: magnitude vs capA (straight cruise, camera fixed -> |dx| == |f1|)
    import csv, sys
    path = sys.argv[1] if len(sys.argv) > 1 else "capA.csv"
    rows = list(csv.DictReader(open(path)))
    worst = wf = 0
    for r in rows[2:]:                                  # skip entry frame
        v = float(r["potential_speed"]); an = float(r["anim_frame"]); air = int(r["air"])
        e = abs(disp_magnitude(v, an, air)) - abs(float(r["dx"]))
        if abs(e) > abs(worst):
            worst, wf = e, int(r["f"])
    print(f"magnitude self-test ({path}): worst |err| = {abs(worst):.6f} at f{wf} "
          f"(vs ~0.28 with the old air_drag)")
