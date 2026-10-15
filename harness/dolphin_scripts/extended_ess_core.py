"""Short-horizon camera controller for JP land MOVE brakeslides.

Speed/turn branches: d_a_player_main.cpp, setSpeedAndAngleNormal and
setNormalSpeedF. Camera yaw: the binary-derived land_cam.manualCamera port.
This is not a collision, animation, target-camera, or complete movement model.
"""

from dataclasses import dataclass, replace
from functools import lru_cache
import math

from tww_sim.core.mathlib import (
    cLib_addCalc, cM_scos_s16, f32, main_stick_decode, s16_signed,
)
from tww_sim.core.camera.cam_bezier import cstick_normalize, step_cam_target
from tww_sim.land.constants import cLib_addCalcAngleS


@dataclass(frozen=True)
class State:
    velocity: float
    travel: int
    facing: int
    controlled: int
    view_yaw: int
    target_yaw: int
    max_speed: float
    yaw_scale: float
    cushion: float


@dataclass(frozen=True)
class Pad:
    x: int
    y: int
    cx: int = 128
    cy: int = 128


@dataclass(frozen=True)
class Step:
    state: State
    loss: float
    clearance: int
    reason: str = ""


@dataclass(frozen=True)
class Plan:
    cx: int
    loss: float
    clearance: int
    sequence: tuple
    neutral_loss: float = 0.0
    evaluated_frames: int = 6


@lru_cache(maxsize=1024)
def decode(x, y):
    angle, magnitude = main_stick_decode(x, y)
    return angle, f32(magnitude)


def ess_input(pad):
    angle, magnitude = decode(pad.x, pad.y)
    return angle is not None and 0.05 < magnitude <= 0.3


@lru_cache(maxsize=65536)
def camera_target(target, cx, cy, scale):
    nx, _ = cstick_normalize(cx, cy)
    return step_cam_target(target, nx, scale)


def advance(state, pad):
    """One delivered game input; Link runs before the camera yaw update."""
    angle, msd = decode(pad.x, pad.y)
    if angle is None or not ess_input(pad):
        return Step(state, 0.0, 0, "Main stick is outside ESS range")
    if not all(math.isfinite(v) for v in (
        state.velocity, state.max_speed, state.yaw_scale, state.cushion,
    )) or state.max_speed <= 0 or state.velocity >= 0:
        return Step(state, 0.0, 0, "Not a finite negative-speed MOVE state")
    target = (angle + 0x8000 + state.controlled) & 0xFFFF
    if abs(s16_signed(target - state.travel)) > 0x7800:
        return Step(state, 0.0, 0, "Turnaround branch")
    msd2 = f32(msd * msd)
    travel = cLib_addCalcAngleS(
        state.travel, target, 5,
        max(10, int(f32(3000 * msd2))), max(1, int(f32(100 * msd2))),
    )
    gap = abs(s16_signed(target - travel))
    cosine = max(0.0, cM_scos_s16(target - travel))
    threshold = f32(0.5 - f32(0.5 * abs(f32(state.velocity / state.max_speed))))
    acceleration = f32(cosine * f32(3.5 * msd2)) if msd > threshold else 0.0
    if abs(acceleration) < 1.0e-5:
        velocity = cLib_addCalc(state.velocity, 0.0, f32(0.6), 2.5, f32(1.8))
    else:
        cap = f32(msd * f32(state.max_speed * msd))
        velocity = min(cap, f32(state.velocity + acceleration))
    facing = cLib_addCalcAngleS(state.facing, target, 5, 6000, 200)
    if s16_signed(state.facing - travel) * s16_signed(facing - travel) <= 0:
        facing = travel
    reason = ""
    if abs(s16_signed(facing - state.facing)) > 21845:
        reason = "Predicted facing snap over 120 degrees"
    elif gap > 0x6000:
        reason = "Predicted MOVE_TURN transition"
    elif velocity >= 0:
        reason = "Brakeslide ended"
    target_yaw = camera_target(state.target_yaw, pad.cx, pad.cy, state.yaw_scale)
    yaw = (state.view_yaw + int(f32(
        s16_signed(target_yaw - state.view_yaw) * state.cushion
    ))) & 0xFFFF
    return Step(
        replace(state, velocity=velocity, travel=travel, facing=facing,
                # The committed/control yaw can differ from view-cache yaw
                # (observed +40 BAM during the M2tower camera trace). Carry
                # that measured offset and re-seed it from RAM every frame.
                controlled=(yaw + state.controlled - state.view_yaw) & 0xFFFF,
                view_yaw=yaw, target_yaw=target_yaw),
        velocity - state.velocity, 0x4000 - gap, reason,
    )


@lru_cache(maxsize=256)
def camera_options(cy):
    # PADClamp/saturation give many bytes identical effects. Keep the smallest
    # magnitude representative, including neutral; still cover every effect.
    unique = {}
    for cx in sorted(range(256), key=lambda x: (abs(x - 128), x)):
        nx, _ = cstick_normalize(cx, cy)
        unique.setdefault(nx, cx)
    return tuple(unique.values())


def evaluate_sequence(state, held, sequence):
    """Return cumulative speed losses and clearances, or None on a turn/end."""
    origin = state.velocity
    losses, clearances = [], []
    for cx in sequence:
        step = advance(state, replace(held, cx=cx))
        if step.reason:
            return None
        state = step.state
        losses.append(state.velocity - origin)
        clearances.append(step.clearance)
    return tuple(losses), tuple(clearances)


def choose_camera(state, held, pending=(), margin=16, horizon=6):
    """Compare every distinct one-frame C pulse against neutral, then coast.

    A pulse must improve total loss without worsening any evaluated prefix.
    It cannot depend on a later compensating pulse to earn that improvement.
    This comparison is within the model, not a live/collision guarantee.
    """
    for pad in pending:
        step = advance(state, pad)
        if step.reason:
            return None
        state = step.state
    neutral_path = (128,) * horizon
    neutral = evaluate_sequence(state, held, neutral_path)
    neutral_loss = neutral[0][-1] if neutral else math.inf
    best = (Plan(128, neutral_loss, neutral[1][-1], neutral_path,
                 neutral_loss, horizon) if neutral else None)
    for cx in camera_options(held.cy):
        if cx == 128:
            continue
        path = (cx,) + (128,) * (horizon - 1)
        evaluation = evaluate_sequence(state, held, path)
        if evaluation is None:
            continue
        losses, clearances = evaluation
        if neutral and any(a > b for a, b in zip(losses, neutral[0])):
            continue
        # A buffer must not force Link away from an already better neutral
        # trajectory. Only require as much clearance as neutral would have.
        required = (tuple(min(margin, max(0, c)) for c in neutral[1])
                    if neutral else (margin,) * horizon)
        if any(c < minimum for c, minimum in zip(clearances[1:], required[1:])):
            continue
        if best is None or losses[-1] < best.loss - 1.0e-7:
            best = Plan(cx, losses[-1], clearances[-1], path, neutral_loss, horizon)
    return best
