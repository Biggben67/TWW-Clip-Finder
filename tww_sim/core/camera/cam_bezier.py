"""cam_bezier.py - BIT-EXACT port of dCamMath::rationalBezierRatio (JP/GZLJ01 @ 0x800aca94)
plus the dCamera_c::manualCamera C-stick -> camera-yaw-rate command (the LAND free/behind cam).

WHY: camera_exact/camera_arbitrary model omega_cmd(csx,csy) as a LIVE-CAPTURED integer table.
That table was captured on the SWIM (subject) camera; the LAND camera (manualCamera) rotates a
per-STYLE scale faster (MM83 style: 8.0 deg/frame vs the subject cam's ~3), and the whole curve
scales -- but the scale-multiplied table is NOT bit-exact because omega is truncated (e.g. swim
(166,0)=3 but land=9, not 3*2.6685=8: the swim 3 hides a real ~3.4 that scales to ~9). So LAND
needs the exact real-valued ratio, recomputed with the land scale. This module is that port.

MECHANISM (decompiled, JP main.dol):
  ratio = rationalBezierRatio(_16276 * stickX, _9006)   # stickX = mStickCPosXLast (normalized C-stick X)
          saturating to +/-1 (=_5125/_6068) beyond |stickX| >= 0.75 (_8358/_16275)
  omega recurrence (cSGlobe::Val writes cam_target; azimuth s16):
    curDeg   = Degree(cam_target)              # (360/65536) * s16, single
    inc_deg  = f32(ratio * scale)              # (float)(dVar10 * dVar15); scale = styleParam[24]
    new_s16  = trunc( f32(182.04444885 * f32(curDeg + inc_deg)) )   # fctiwz, (short)
  omega = (s16)(new_cam_target - cam_target).

The bezier itself is double precision with a 4-iteration frsqrte-seeded Newton sqrt; math.sqrt
is correctly-rounded to double and matches the Newton result to <=1 ULP (validated live).

Constants (SDA2/d_cam_param + d_camera, read from the DOL via Ghidra):
"""
from __future__ import annotations
import math, struct

# f32 rounding: the shared fp primitive (native _fpc when built, else ctypes) -- bit-identical to the
# old struct round-trip but ~5x cheaper, and this runs ~11x per camera frame. See fp-faithfulness.md.
from ..fp import f32

# --- dCamMath::rationalBezierRatio consts (d_cam_param::_4103.._4113) ---
_B_SIGN0 = 0.0        # _4103 (float; also the "flat"/degenerate return)
_B_ONE   = 1.0        # _4104
# _4105 = -1.0 (sign for p1<0), _4106=2, _4107=4, _4108=0, _4109=0.5, _4110=3
_B_TWO   = 2.0        # _4106
_B_FOUR  = 4.0        # _4107
_B_ZERO  = 0.0        # _4108
_B_EPS_P = 1e-7               # _4111
_B_EPS_N = -1e-7              # _4112
_B_EPS_D = 1.00000001168610e-7  # _4113

# --- d_camera consts feeding the stick->ratio map (manualCamera) ---
DEG2S16   = 182.04444885253906   # d_camera::_8357  (== cAngle::Degree_to_SAngle factor)
S162DEG   = 360.0 / 65536.0      # cSAngle::Degree factor (0.0054931640625, exact in f32)
STICK_SAT = 0.75                 # _8358 (+sat threshold)  / _16275 = -0.75
STICK_NRM = struct.unpack(">f", bytes.fromhex("3faaaaa8"))[0]  # _16276 = 1.3333333 (exact DOL f32)
BEZ_W     = 2.0                  # _9006 (bezier param2 / curve weight)
RATIO_SAT_POS = 1.0              # _5125
RATIO_SAT_NEG = -1.0             # _6068


# --- C-stick byte -> normalized float (dolphin/pad/Padclamp.c + JUTGamePad::CStick::update) ---
# Substick ClampRegion (Padclamp.c): min=15, max=59, xy=31. CStick divisor (sub) = 42.
_CLAMP_MIN = 15
_CLAMP_MAX = 59
_CLAMP_XY = 31
_CSTICK_DIV = 42.0


def _clamp_stick(x: int, y: int):
    """PADClamp ClampStick for the substick (min=15,max=59,xy=31). x,y are s8 (raw byte-128)."""
    sx = 1 if x >= 0 else -1
    sy = 1 if y >= 0 else -1
    x = abs(x); y = abs(y)
    x = 0 if x <= _CLAMP_MIN else x - _CLAMP_MIN
    y = 0 if y <= _CLAMP_MIN else y - _CLAMP_MIN
    if x == 0 and y == 0:
        return 0, 0
    xy = _CLAMP_XY; mx = _CLAMP_MAX
    if xy * y <= xy * x:
        d = xy * x + (mx - xy) * y
    else:
        d = xy * y + (mx - xy) * x
    if xy * mx < d:                       # octagonal clamp (C integer div; operands >=0 -> // == trunc)
        x = (xy * mx * x) // d
        y = (xy * mx * y) // d
    return sx * x, sy * y


def cstick_normalize(csx: int, csy: int):
    """Raw C-stick bytes (0..255, center 128) -> (mStickCPosX, mStickCPosY) exactly as the game
    sees them: PADClamp(substick) then CStick::update (/42 + unit-circle clamp, STICK_MODE_1)."""
    px, py = _clamp_stick(int(csx) - 128, int(csy) - 128)
    posx = f32(px / _CSTICK_DIV)
    posy = f32(py / _CSTICK_DIV)
    val = f32(math.sqrt(f32(posx * posx) + f32(posy * posy)))
    if val > 1.0:
        posx = f32(posx / val)
        posy = f32(posy / val)
    return posx, posy


def rationalBezierRatio(param1: float, param2: float) -> float:
    """Port of dCamMath::rationalBezierRatio(f32 param1, f32 param2) -> f32.
    Returns the S-curve ratio in [-1, 1] (double math internally, single-rounded result)."""
    p1 = float(param1)
    p2 = float(param2)
    if p1 >= _B_SIGN0:            # fcmpo f1,0 ; cror eq,gt,eq ; bne  -> f1>=0 keeps +1
        sign = _B_ONE
    else:
        sign = -_B_ONE
        p1 = -p1
    dVar4 = (_B_TWO * p1 * p2 - _B_TWO * p1) - _B_TWO * p2
    dVar3 = -dVar4 - _B_ONE
    dVar5 = dVar4 * dVar4 - _B_FOUR * dVar3 * p1
    sq = math.sqrt(dVar5) if dVar5 > _B_ZERO else 0.0
    num = -dVar4 - sq                 # b88: f0(=-dVar4) - f1(=sqrt)
    denom0 = _B_TWO * dVar3
    if denom0 > _B_EPS_P:
        pass                          # compute
    elif denom0 >= _B_EPS_N:
        return _B_SIGN0               # |2*dVar3| ~ 0 -> flat
    # else denom0 < -1e-7 -> compute
    t = num / denom0
    tt = t * t
    om = _B_ONE - t
    bez_denom = tt + (om * om + p2 * (_B_TWO * om * t))
    if bez_denom <= _B_EPS_D:
        return _B_SIGN0
    return f32(sign * (tt / bez_denom))   # frsp


def stick_ratio(stick_x: float) -> float:
    """C-stick X (normalized mStickCPosXLast, ~[-1,1]) -> yaw ratio, with the +/-0.75 saturation."""
    s = float(stick_x)
    if s >= STICK_SAT:
        return RATIO_SAT_POS
    if s <= -STICK_SAT:               # _16275 = -0.75 (strict: s < -0.75 uses bezier boundary)
        return RATIO_SAT_NEG
    return rationalBezierRatio(f32(STICK_NRM * s), BEZ_W)


def step_cam_target(cam_target_s16: int, stick_x: float, scale: float) -> int:
    """One manualCamera azimuth update: cam_target_s16 -> new cam_target_s16 (both s16, wrapped).
    scale = styles[mCurStyle].styleParam[24] (LAND MM83 = 8.0)."""
    ratio = stick_ratio(stick_x)
    cur_deg = f32(S162DEG * _s16(cam_target_s16))
    inc_deg = f32(ratio * float(scale))          # (float)(dVar10 * dVar15)
    total = f32(cur_deg + inc_deg)
    new = _trunc_toward_zero(f32(DEG2S16 * total))
    return new & 0xFFFF


def omega_from(cam_target_s16: int, stick_x: float, scale: float) -> int:
    new = step_cam_target(cam_target_s16, stick_x, scale)
    return _s16(new - cam_target_s16)


def _s16(x: int) -> int:
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _trunc_toward_zero(x: float) -> int:
    return int(x)   # Python int() truncates toward zero == PPC fctiwz


# Optional native (bit-exact) camera math (anim/_anmc.pyx). cstick_normalize + step_cam_target run
# every land frame; the native ports inline the bezier / clamp / s16 recompute. See fp-faithfulness.md.
try:
    from ..anim import _anmc as _N
    _N.init_cam(STICK_NRM, DEG2S16, S162DEG)
    cstick_normalize = _N.cstick_normalize      # noqa: F811
    step_cam_target = _N.cam_step_target         # noqa: F811
except ImportError:
    pass
