"""Offline regression guard for the LAND camera port (superswim/predict/cam_bezier.py +
camera_manual.py). The values below were VALIDATED BIT-EXACT vs live Dolphin on the land anchor
(MM83 style, scale 8.0): 33/33 omega cells (1-D + 2-D off-axis), analytic mStickCPosX == live to
full precision. See _notes handoff + knowledge/mechanics/camera.md. These lock the ported curve so
a future edit can't silently regress it."""
import math
import pytest
from tww_sim.core.camera import cam_bezier as CB
from tww_sim.core.camera.camera_manual import CameraManual, LAND_SCALE


def test_land_scale_is_mm83():
    assert LAND_SCALE == 8.0


# rationalBezierRatio / stick_ratio: the S-curve is target-independent (pure function of stick).
@pytest.mark.parametrize("stick,ratio", [
    (0.0, 0.0),
    (0.14285714, 0.0027216421),
    (0.54761904, 0.0937953889),
    (0.70000000, 0.3352951407),
    (0.75000000, 1.0),           # >= 0.75 saturates to +1 (_5125)
    (1.0, 1.0),
    (-0.54761904, -0.0937953889),
    (-0.75000000, -1.0),         # <= -0.75 saturates to -1 (_6068)
])
def test_stick_ratio(stick, ratio):
    assert CB.stick_ratio(stick) == pytest.approx(ratio, abs=1e-9)


# cstick_normalize: PADClamp(substick min15/max59/xy31) + CStick /42 + unit-circle clamp.
@pytest.mark.parametrize("csx,csy,posx,posy", [
    (128, 128, 0.0, 0.0),                 # centered
    (166, 128, 0.5476190, 0.0),           # x_val=23/42
    (255, 128, 1.0, 0.0),                 # saturated (unit clamp)
    (166, 0, 0.1999601, -0.9798040),      # 2-D off-axis: circle clamp changes the X component
    (255, 255, 0.7071068, 0.7071068),     # diagonal -> unit circle
])
def test_cstick_normalize(csx, csy, posx, posy):
    px, py = CB.cstick_normalize(csx, csy)
    assert px == pytest.approx(posx, abs=2e-6)
    assert py == pytest.approx(posy, abs=2e-6)


# Neutral (csx=128 -> ratio 0) must be an identity round-trip for ALL targets, else the
# frozen-cam land tests would drift.
def test_neutral_roundtrip_identity():
    bad = [T for T in range(0, 65536) if CB.step_cam_target(T, 0.0, LAND_SCALE) != T]
    assert bad == []


# Full byte->omega chain at target=0 (deterministic; matches live within the target-phase +/-1).
LAND_OMEGA_AT0 = {
    (128, 128): 0, (149, 128): 3, (160, 128): 50, (166, 128): 136, (170, 128): 281,
    (175, 128): 1456, (255, 128): 1456, (96, 128): -50, (90, 128): -136, (81, 128): -1456,
    (0, 128): -1456, (166, 64): 56, (166, 0): 8, (255, 0): 463, (255, 255): 531, (210, 30): 236,
}


@pytest.mark.parametrize("cell,omega", list(LAND_OMEGA_AT0.items()))
def test_land_omega_at0(cell, omega):
    px, _ = CB.cstick_normalize(*cell)
    assert CB.omega_from(0, px, LAND_SCALE) == omega


def test_camera_manual_frozen_when_centered():
    """csx=128 held -> csangle pinned at the seed (identity round-trip + chase)."""
    cam = CameraManual(csangle=0x4000)
    for _ in range(40):
        cam.step(128, 128)
    assert cam.csangle == 0x4000


def test_camera_manual_clone_isolated():
    """A clone must not alias the parent's camera state (A* nodes clone per branch)."""
    cam = CameraManual(csangle=0x4000, scale=8.0)
    cam.step(166, 128)          # arm a pending steer
    c2 = cam.clone()
    assert (c2.yaw, c2.target, c2.scale, c2._pending_posx) == (
        cam.yaw, cam.target, cam.scale, cam._pending_posx)
    cam.step(166, 128); cam.step(166, 128)   # advance the parent only
    assert c2.target != cam.target           # clone stayed put
