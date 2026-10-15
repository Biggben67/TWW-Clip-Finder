"""stick_grid_gen.py — pure-Python (NO Dolphin) closed-form generator of TWW's
main-stick -> (angle, x, y, value) mapping, bit-exact from the decompiled game code.

This is a CROSS-CHECK against the live capture (harness/capture/stick_grid_redump.py):
faithfulness to the decomp is the whole point, so every float op is forced to f32 and the
integer clamp mirrors the C source's `(s8)` truncations and toward-zero division.

Pipeline (matches the game for the MAIN stick):
  A. origin:   x0 = sx-128, y0 = sy-128  (PADStatus.stickX/Y, signed about center 128)
  B. PADClamp::ClampStick  (tww/src/dolphin/pad/Padclamp.c), MAIN ClampRegion
     min=15, max=72, xy=40 -> octagonal clamp, s8 integer arithmetic
  C. JUTGamePad::CStick::update (tww/src/JSystem/JUtility/JUTGamePad.cpp), clamp=54,
     STICK_MODE_1 (the normal in-game mode): /54, radial clamp to 1.0, angle via atan2f.

Output CSV schema == the live dump: sx,sy,angle,x,y,value,stick_dist  (angle=u16, stick_dist=value).

Usage:
    python stick_grid_gen.py            # writes _generated/stick_grid_gen.csv, prints cell count
"""
import os, sys, csv, math, ctypes

# >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
from tww_sim.swim import sim as S   # S.f32 = ctypes c_float round; S._RAD2IDX = 10430.3779296875

f32 = S.f32
_RAD2IDX = S._RAD2IDX            # f32 value of 10430.379f (65536/2pi), already in sim.py

# --- MAIN stick constants (from ClampRegion / CStick::update) ---------------------------
CLAMP_MIN = 15
CLAMP_MAX = 72
CLAMP_XY  = 40
CSTICK_CLAMP = 54.0

OUT_CSV = os.path.join(_rb, "_generated", "stick_grid_gen.csv")


def s8(v):
    """Emulate a C (s8) cast: wrap into [-128, 127]. (Values here never overflow, but the
    decomp writes through s8* so we mirror it exactly.)"""
    return ((int(v) + 128) & 0xFF) - 128


def _tdiv(a, b):
    """C integer division truncating toward zero. Operands here are non-negative so // works,
    but int(a/b)-style truncation is used to be faithful regardless of sign."""
    q = a / b
    return int(q)  # int() truncates toward zero


def clamp_stick(px, py, max_=CLAMP_MAX, xy=CLAMP_XY, min_=CLAMP_MIN):
    """Port of PADClamp's static ClampStick(s8* px, s8* py, s8 max, s8 xy, s8 min).
    Integer arithmetic throughout; returns (px, py) as s8 ints."""
    x = int(px); y = int(py)
    if 0 <= x:
        signX = 1
    else:
        signX = -1; x = -x
    if 0 <= y:
        signY = 1
    else:
        signY = -1; y = -y

    if x <= min_:
        x = 0
    else:
        x -= min_
    if y <= min_:
        y = 0
    else:
        y -= min_

    if x == 0 and y == 0:
        return 0, 0

    if xy * y <= xy * x:
        d = xy * x + (max_ - xy) * y
        if xy * max_ < d:
            x = s8(_tdiv(xy * max_ * x, d))
            y = s8(_tdiv(xy * max_ * y, d))
    else:
        d = xy * y + (max_ - xy) * x
        if xy * max_ < d:
            x = s8(_tdiv(xy * max_ * x, d))
            y = s8(_tdiv(xy * max_ * y, d))

    return s8(signX * x), s8(signY * y)


def sqrtf_ppc(x):
    """PPC/MSL sqrtf: frsqrte seed for 1/sqrt(x) + 3 Newton-Raphson refinements in f64, then
    result = x * (1/sqrt(x)); cast to f32.

    Only `value`/`stick_dist` and the `mValue > 1.0` clamp-branch decision depend on this, and
    the angle (the one column the sim reads) is invariant to it (radial normalization preserves
    direction). We seed with the exact 1/sqrt(x) (a reasonable frsqrte stand-in); 3 NR iterations
    in f64 converge to full f32 precision regardless of a sane seed, matching the game to f32."""
    if x <= 0.0:
        return f32(0.0)
    guess = 1.0 / math.sqrt(x)          # frsqrte-style seed for 1/sqrt(x) (f64)
    for _ in range(3):                  # 3 Newton-Raphson refinements, f64
        guess = 0.5 * guess * (3.0 - guess * guess * x)
    return f32(x * guess)               # sqrt(x) = x / sqrt(x); cast to f32


def cstick_update(x_val, y_val):
    """Port of JUTGamePad::CStick::update for the main stick (clamp=54, STICK_MODE_1).
    x_val,y_val are the s8 clamped ints from clamp_stick. Returns (angle_u16, px, py, value)."""
    px = f32(f32(x_val) / f32(CSTICK_CLAMP))
    py = f32(f32(y_val) / f32(CSTICK_CLAMP))
    value = sqrtf_ppc(f32(f32(px * px) + f32(py * py)))

    if value > f32(1.0):                # STICK_MODE_1: radial clamp to unit circle
        px = f32(px / value)
        py = f32(py / value)
        value = f32(1.0)

    angle = 0
    if value > f32(0.0):
        if py == f32(0.0):
            angle = 0x4000 if px > f32(0.0) else -0x4000
        else:
            # atan2f = (f32)atan2((f64)px, (f64)-py); px,py already f32
            a = f32(math.atan2(px, -py))
            angle = int(f32(_RAD2IDX * a))   # (s16)(float): truncate toward zero
    return angle & 0xFFFF, px, py, value


def gen_cell(sx, sy):
    x0 = sx - 128
    y0 = sy - 128
    cx, cy = clamp_stick(x0, y0)
    angle, px, py, value = cstick_update(cx, cy)
    return angle, px, py, value


def main():
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    n = 0
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sx", "sy", "angle", "x", "y", "value", "stick_dist"])
        for sx in range(256):
            for sy in range(256):
                angle, px, py, value = gen_cell(sx, sy)
                # x,y,value,stick_dist are f32; repr for full round-trip precision
                w.writerow([sx, sy, angle, repr(px), repr(py), repr(value), repr(value)])
                n += 1
    print(f"wrote {n} cells -> {OUT_CSV}")
    return n


if __name__ == "__main__":
    main()
