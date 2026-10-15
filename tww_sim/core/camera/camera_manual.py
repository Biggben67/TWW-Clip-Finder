"""camera_manual.py - BIT-EXACT LAND camera (dCamera_c::manualCamera) csangle predictor.

Same s16 chase recurrence as CameraExact/CameraArbitrary, but the cam_target accumulator is the
manualCamera azimuth RECOMPUTE (analytic dCamMath::rationalBezierRatio * per-style scale) rather
than the swim-captured omega_cmd table. The swim table rotates a different (subject) camera and is
NOT scale-multipliable to land (truncation), so land needs the exact real-valued ratio. Validated
bit-exact vs live Dolphin (33/33 cells, incl. 2-D off-axis csy!=128) -- see cam_bezier.py.

  ratio      = rationalBezierRatio(_16276 * mStickCPosX, 2)      # +/-1 saturated beyond |stick|>=0.75
  cam_target = trunc(182.0444 * (Degree(cam_target) + f32(ratio * scale)))   # cSGlobe::Val azimuth
  cam_yaw   += int((s16)(cam_target - cam_yaw) / 2)              # shared chase (== CameraExact)
  csangle    = (cam_yaw + 0x8000) & 0xFFFF

scale = styles[mCurStyle].styleParam[24] (deg/frame). LAND walk (MM83, style 61) = 8.0; the swim
subject cam is ~3 (hence the ~2.67x the swim table was off). 1-frame input lag as CameraExact.
Neutral (csx=128 -> ratio 0) is a bit-exact identity round-trip for ALL 65536 targets, so a
centered C-stick leaves csangle frozen == the pre-wiring / frozen-cam behaviour.
"""
from __future__ import annotations
from .camera_exact import CameraExact, _s16
from . import cam_bezier as CB

# Per-style horizontal C-stick yaw scale (styleParam[24], deg/frame). MM83 (land walk) = 8.0.
LAND_SCALE = 8.0


class CameraManual(CameraExact):
    """CameraExact whose cam_target evolves by the manualCamera (land) azimuth recompute."""

    def __init__(self, csangle: int = 49152, target: int | None = None,
                 pending_cmd: int = 0, scale: float = LAND_SCALE):
        super().__init__(csangle, target, pending_cmd)
        self.scale = float(scale)
        self._pending_posx = 0.0     # normalized C-stick X applied NEXT frame (1-frame lag)

    def step(self, csx: int = 128, csy: int = 128) -> int:
        self.target = CB.step_cam_target(self.target, self._pending_posx, self.scale)
        diff = _s16(self.target - self.yaw)
        self.yaw = (self.yaw + int(diff / 2)) & 0xFFFF
        self._pending_posx = CB.cstick_normalize(csx, csy)[0]
        return self.csangle

    def clone(self) -> "CameraManual":
        c = CameraManual.__new__(CameraManual)
        c.yaw = self.yaw
        c.target = self.target
        c._pending = self._pending
        c.scale = self.scale
        c._pending_posx = self._pending_posx
        return c
