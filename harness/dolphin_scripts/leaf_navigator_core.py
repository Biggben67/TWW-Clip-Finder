"""Deku Leaf steering policy using the glide speed and yaw equations.

The policy is receding-horizon: each game frame selects the fastest admissible
turn, then replans from the observed state. Wind and collision are observed in
the next position; this is not a collision-free global path planner.
"""
from __future__ import annotations

from bisect import bisect_left
from functools import lru_cache
import math

from tww_sim.core.mathlib import main_stick_decode


ANGLE_SCALE = 65536.0 / (2.0 * math.pi)
FAN_TARGET_SPEED = 12.0  # daPy_HIO_fan_c0::m.field_0x48


def s16(value: int) -> int:
    value = int(value) & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def world_angle(dx: float, dz: float) -> int:
    return round(math.atan2(dx, dz) * ANGLE_SCALE) & 0xFFFF


def glide_speed_step(speed: float, stick_distance: float, offset: int) -> float:
    target = FAN_TARGET_SPEED * stick_distance * math.cos(offset / ANGLE_SCALE)
    step = max(-0.1 - 0.4 * stick_distance,
               min(0.1 + 0.4 * stick_distance, 0.5 * (target - speed)))
    if abs(target - speed) <= 0.02:
        return target
    return speed + step


def glide_turn_step(rate: int, stick_distance: float, offset: int) -> int:
    target = int(512.0 * stick_distance * math.sin(offset / ANGLE_SCALE))
    diff = target - rate
    step = int(diff / 5)
    if abs(step) <= 8:
        step = min(8, diff) if diff >= 0 else max(-8, diff)
    return rate + max(-64, min(64, step))


@lru_cache(maxsize=1)
def _full_sticks() -> tuple[tuple[int, int, int], ...]:
    by_angle = {}
    for x in range(1, 255):
        for y in range(1, 255):
            angle, distance = main_stick_decode(x, y)
            if angle is None or distance < 0.999:
                continue
            old = by_angle.get(angle)
            if old is None or (x, y) < old:
                by_angle[angle] = (x, y)
    return tuple((angle, *by_angle[angle]) for angle in sorted(by_angle))


@lru_cache(maxsize=1)
def _angles() -> tuple[int, ...]:
    return tuple(row[0] for row in _full_sticks())


def _stick_for_world_angle(world: int, camera: int) -> tuple[int, int, int]:
    stick_angle = (world - camera - 0x8000) & 0xFFFF
    rows = _full_sticks()
    at = bisect_left(_angles(), stick_angle)
    choices = (rows[(at - 1) % len(rows)], rows[at % len(rows)])
    angle, x, y = min(choices, key=lambda r: abs(s16(r[0] - stick_angle)))
    return x, y, (angle + camera + 0x8000) & 0xFFFF


def choose_stick(
    x: float, z: float, destination_x: float, destination_z: float,
    facing: int, camera: int, turn_rate: int, speed: float,
    minimum_glide_speed: float = 9.0,
) -> tuple[int, int, int, float, float]:
    """Return stick X/Y, resulting world target, predicted speed and distance.

    Minimize the heading error six frames ahead, subject to a floor on the
    decomp's steady glide speed target. The actual state is
    sampled again next frame, so moving camera and wind are corrected live.
    """
    dx, dz = destination_x - x, destination_z - z
    distance = math.hypot(dx, dz)
    desired = world_angle(dx, dz)
    error = s16(desired - facing)
    best = None
    # A one-frame loss budget constrains the *first* yaw input much more than
    # the eventual speed. Bound the steady target instead, so the controller
    # can turn promptly without settling below the requested speed.
    for offset in range(-0x4000, 0x4001, 96):
        sx, sy, actual = _stick_for_world_angle((facing + offset) & 0xFFFF, camera)
        delta = s16(actual - facing)
        steady_speed = FAN_TARGET_SPEED * math.cos(delta / ANGLE_SCALE)
        if steady_speed < minimum_glide_speed - 1e-6:
            continue
        next_speed = glide_speed_step(speed, 1.0, delta)
        next_rate = glide_turn_step(turn_rate, 1.0, delta)
        remaining = abs(error - 6 * next_rate)
        # Prefer retaining speed between turns with identical useful yaw.
        key = (remaining, -steady_speed, abs(delta))
        if best is None or key < best[0]:
            best = (key, sx, sy, actual, next_speed)
    if best is None:
        sx, sy, actual = _stick_for_world_angle(facing, camera)
        next_speed = glide_speed_step(speed, 1.0, s16(actual - facing))
    else:
        _, sx, sy, actual, next_speed = best
    return sx, sy, actual, next_speed, distance


def pump_due(countdown: int, cancel_lockout: int, enabled: bool) -> bool:
    # The current countdown is the value after this game's update. A submitted
    # input reaches the action one update later. Live tests show 3 is the last
    # countdown that avoids the periodic magic charge before A cancels glide.
    return bool(enabled and countdown == 3 and cancel_lockout == 0)
