"""cam_angle.py - fp-faithful cSAngle / cSGlobe / cSPolar + the camera vector helpers.

The s16-angle classes and globe<->vector conversions the dCamera_c port (land_cam.py) runs
on, ported from the JP binary (c_angle.cpp is matched source; the frsqrte-Newton sqrt,
cM_atan2f round-trip, and MSL double sin/cos are the console-exact paths). Split out of
land_cam.py (one topic per module).

NOTE the zeldaret decomp header's cSGlobe SETTER U/V bindings are wrong; the binary truth is
U == yaw (mInclination, +6), V == elevation (mAzimuth, +4), for getters AND setters.
"""
from __future__ import annotations

import math
import struct

from ..fp import f32
from ..collision import frsqrte, sqrtf_c
from ..mathlib import cM_atan2s

# ---------------------------------------------------------------- constants (live-read DOL)
DEG2S16 = 182.04444885253906        # SComponent::_2211 / d_camera::_8357
S162DEG = 360.0 / 65536.0           # cSAngle::Degree factor (exact f32)
S162RAD = f32(9.58738e-5)           # cSAngle::Radian factor (header literal 9.58738E-5f)
RAD2S16 = f32(10430.378)            # SComponent::_2657

# ---------------------------------------------------------------- small fp helpers
def _s16(x):
    x = int(x) & 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def _trunc(x):
    return int(x)                   # fctiwz: truncate toward zero


def sang_deg(a):
    """cSAngle::Degree: f32(S162DEG * s16) (the int->double conversion is exact)."""
    return f32(S162DEG * _s16(a))


def sang_rad(a):
    return f32(S162RAD * _s16(a))


def sang_from_deg(deg):
    """cSAngle::Val(float): (short)(int)(182.0444.. * deg) -- f32 multiply, trunc."""
    return _s16(_trunc(f32(DEG2S16 * f32(deg))))


def sang_sin(a):
    return f32(math.sin(sang_rad(a)))


def sang_cos(a):
    return f32(math.cos(sang_rad(a)))


def sang_mul(a, f):
    """cSAngle::operator*(float): (short)(mAngle * f1) -- f32 multiply, trunc."""
    return _s16(_trunc(f32(_s16(a) * f32(f))))


def msl_sqrt(x):
    """MSL double sqrt (math.h:53): frsqrte + 4 Newton iterations, all double."""
    if x > 0.0:
        g = frsqrte(x)
        g = .5 * g * (3.0 - g * g * x)
        g = .5 * g * (3.0 - g * g * x)
        g = .5 * g * (3.0 - g * g * x)
        g = .5 * g * (3.0 - g * g * x)
        return x * g
    return 0.0 if x == 0 else float("nan")


def cM_atan2f(y, x):
    """cM_atan2f (c_math.cpp:163): f32(9.58738E-5f * (s16)cM_atan2s(y, x))."""
    return f32(S162RAD * _s16(cM_atan2s(y, x)))


def _vsub(a, b):
    return (f32(a[0] - b[0]), f32(a[1] - b[1]), f32(a[2] - b[2]))


def _vadd(a, b):
    return (f32(a[0] + b[0]), f32(a[1] + b[1]), f32(a[2] + b[2]))


def _vscale(a, s):
    return (f32(a[0] * s), f32(a[1] * s), f32(a[2] * s))


def xyz_abs(v):
    """cXyz::abs: std::sqrtf(x*x + y*y + z*z) (single-precision accumulation)."""
    return sqrtf_c(f32(f32(f32(v[0] * v[0]) + f32(v[1] * v[1])) + f32(v[2] * v[2])))


def horiz_dist(a, b):
    """dCamMath::xyzHorizontalDistance: double dx/dz, double sqrt, f32 result."""
    x = float(a[0]) - float(b[0])
    z = float(a[2]) - float(b[2])
    return f32(msl_sqrt(x * x + z * z))


# ---------------------------------------------------------------- cSGlobe
class SGlobe:
    """cSGlobe: radius f32, az s16 (elevation, +4), inc s16 (yaw, +6)."""
    __slots__ = ("r", "az", "inc")

    def __init__(self, r=0.0, az=0, inc=0, formal=True):
        self.r = f32(r)
        self.az = _s16(az)
        self.inc = _s16(inc)
        if formal:
            self.formal()

    def copy(self):
        g = SGlobe.__new__(SGlobe)
        g.r, g.az, g.inc = self.r, self.az, self.inc
        return g

    def formal(self):
        if self.r < 0.0:
            self.r = f32(-self.r)
            self.az = _s16(-self.az)
            self.inc = _s16(self.inc - 0x8000)
        if self.az < -0x4000 or 0x4000 < self.az:
            self.az = _s16(-0x8000 - self.az)
            self.inc = _s16(self.inc - 0x8000)
        return self

    @classmethod
    def from_vec(cls, v):
        """cSGlobe::Val(cXyz&) via cSPolar::Val(cXyz&) + Globe(): frsqrte-Newton sqrt (4 it,
        double), cM_atan2f angles, trunc(RAD2S16 * rad)."""
        x, y, z = f32(v[0]), f32(v[1]), f32(v[2])
        horiz_sq = float(f32(float(z) * float(z))) + float(f32(float(x) * float(x)))
        # NOTE: the decompile computes (double)(float)(z*z) + (double)(float)(x*x): each square
        # is a single-precision multiply, the sum is double.
        full_sq = horiz_sq + float(f32(float(y) * float(y)))
        horiz = 0.0
        if horiz_sq > 0.0:
            g = frsqrte(horiz_sq)
            for _ in range(3):
                g = 0.5 * g * (3.0 - horiz_sq * g * g)
            horiz = f32(horiz_sq * 0.5 * g * (3.0 - horiz_sq * g * g))
        radial = 0.0
        if full_sq > 0.0:
            g = frsqrte(full_sq)
            for _ in range(3):
                g = 0.5 * g * (3.0 - full_sq * g * g)
            radial = f32(full_sq * 0.5 * g * (3.0 - full_sq * g * g))
        ang1 = _s16(_trunc(f32(RAD2S16 * cM_atan2f(horiz, y))))    # polar angle from +Y
        ang2 = _s16(_trunc(f32(RAD2S16 * cM_atan2f(x, z))))        # heading
        # cSPolar::Formal
        if radial < 0.0:
            radial = f32(-radial)
            ang1 = _s16(-0x8000 - ang1)
            ang2 = _s16(ang2 - 0x8000)
        if ang1 < 0 and ang1 != -0x8000:
            ang1 = _s16(-ang1)
            ang2 = _s16(ang2 - 0x8000)
        # Globe(): az = 0x4000 - ang1, inc = ang2, then cSGlobe::Formal
        return cls(radial, 0x4000 - ang1, ang2)

    def xyz(self):
        """cSGlobe::Xyz via cSPolar (polar angle = 0x4000 - az): MSL double sin/cos on the f32
        radians, mixed single/double products exactly as compiled."""
        pol1 = _s16(0x4000 - self.az)          # cSPolar angle1
        pol2 = self.inc
        # cSPolar::Formal on (r, pol1, pol2)
        r = self.r
        if r < 0.0:
            r = f32(-r)
            pol1 = _s16(-0x8000 - pol1)
            pol2 = _s16(pol2 - 0x8000)
        if pol1 < 0 and pol1 != -0x8000:
            pol1 = _s16(-pol1)
            pol2 = _s16(pol2 - 0x8000)
        s1 = math.sin(sang_rad(pol1))
        c2 = f32(math.cos(sang_rad(pol2)))
        c1 = math.cos(sang_rad(pol1))
        s2 = f32(math.sin(sang_rad(pol2)))
        d2 = float(f32(r * f32(s1)))           # dVar2 = (double)(r * (float)sin1)
        y = f32(r * f32(c1))
        x = f32(d2 * float(s2))
        z = f32(d2 * float(c2))
        return (x, y, z)


