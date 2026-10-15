#!/usr/bin/env python3
"""Exact mechanics and seed-specific calculator for the fast standstill roll launch.

The one-frame-early family has four acceleration frames before A acts:

* frame 1: L + a full-magnitude stick just outside the ATN forward bucket;
* frame 2: release L, keep the same stick (the already-selected SIDE branch adds 5);
* frames 3-4: keep the same stick in MOVE (each adds the normal maximum 3.5);
* next frame: press A to enter FRONT_ROLL.

This module separates the decomp-provable potential-speed ceiling from the animation-dependent
``speedF`` that ``procFrontRoll_init`` actually consumes. Use an exact captured rest seed when the
roll value itself must be bit-exact; critical health changes that seed through ANM_WAITATOB and the
steady WAITB idle.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from functools import lru_cache

from tww_sim.core.mathlib import cM_scos_s16, f32, main_stick_decode, s16_signed
from tww_sim.land.constants import FREE_WAIT, FRONT_ROLL, WAIT
from tww_sim.land.land import LandState


ATN_FORWARD_COS = f32(0.99)
ATN_SIDE_ACCEL = f32(5.0)
MOVE_ACCEL = f32(3.5)


@dataclass(frozen=True)
class GateInput:
    delivered: tuple[int, int]
    authored: tuple[int, int]
    target_offset: int
    cosine: float


@lru_cache(maxsize=1)
def gate_inputs() -> tuple[GateInput, ...]:
    """Return one clean-DTM byte pair for every full-magnitude SIDE-gate target.

    Every delivered interior byte 1..254 is directly authorable. The DTM edge calibration is why
    0 and 255 are excluded here: they arrive as 1 and 254 and therefore add only aliases.
    """
    by_offset = {}
    for x in range(1, 255):
        for y in range(1, 255):
            angle, magnitude = main_stick_decode(x, y)
            if angle is None or magnitude != 1.0:
                continue
            offset = s16_signed((angle + 0x8000) & 0xFFFF)
            cosine = cM_scos_s16(offset)
            if abs(offset) < 0x4000 and cosine < ATN_FORWARD_COS:
                by_offset.setdefault(offset, GateInput(
                    delivered=(x, y), authored=(x, y), target_offset=offset, cosine=cosine,
                ))
    return tuple(by_offset.values())


def best_gate_input() -> GateInput:
    """Return the potential-speed-optimal clean-DTM stick that selects SIDE on frame 2."""
    candidates = gate_inputs()
    if not candidates:
        raise RuntimeError("the main-stick decoder exposed no full-magnitude ATN side-gate input")
    return max(candidates, key=lambda g: (g.cosine, -abs(g.target_offset),
                                          -g.delivered[0], -g.delivered[1]))


def potential_speed_ceiling(gate: GateInput | None = None) -> dict:
    """The f32 HIO upper bound before the early roll, independent of foot animation.

    The first frame must cross the SIDE gate, so its best possible injection is `5*cos(offset)`.
    Keeping the same target makes frame 2's SIDE injection exactly 5 and both MOVE injections 3.5.
    Any target or magnitude change can only lower one of those cosine/magnitude products.
    """
    gate = gate or best_gate_input()
    speeds = [f32(ATN_SIDE_ACCEL * gate.cosine)]
    speeds.append(f32(speeds[-1] + ATN_SIDE_ACCEL))
    speeds.append(f32(speeds[-1] + MOVE_ACCEL))
    speeds.append(f32(speeds[-1] + MOVE_ACCEL))
    roll_upper = f32(f32(speeds[-1] * f32(1.5)) + f32(0.5))
    return {
        "gate": gate,
        "normal_speeds": speeds,
        "pre_roll_normal_speed": speeds[-1],
        "roll_upper_bound": roll_upper,
    }


def _without_input_delay(state: LandState) -> LandState:
    state._input_delay = 0
    state._inbuf = []
    if state._core is not None:
        raise ValueError("roll-launch traces require the Python LandState path (native=False)")
    return state


def trace_fast_launch(state: LandState, gate: GateInput | None = None) -> dict:
    """Run the exact five acted frames from a fully seeded resting ``LandState`` clone."""
    gate = gate or best_gate_input()
    s = _without_input_delay(state.clone())
    trace = []
    sx, sy = gate.delivered
    for frame in range(1, 5):
        s.step(
            sx, sy,
            buttons=0x40 if frame == 1 else 0,
            triggerL=255 if frame == 1 else 0,
        )
        trace.append({
            "frame": frame,
            "state": s.state,
            "normal_speed": s.nspeed,
            "speedF": s.speedF,
            "facing": s.facing,
            "travel": s.travel,
        })
    pre_roll_speedf = s.speedF
    s.step(sx, sy, buttons=0x100)
    if s.state != FRONT_ROLL:
        raise RuntimeError("A did not enter FRONT_ROLL from the supplied seed")
    return {
        "gate": gate,
        "trace": trace,
        "pre_roll_normal_speed": trace[-1]["normal_speed"],
        "pre_roll_speedF": pre_roll_speedf,
        "roll_speed": s.nspeed,
    }


def optimize_constant_gate_launch(state: LandState) -> dict:
    """Find the maximum exact roll speed in the documented repeat-one-stick launch family.

    Potential speed alone is insufficient: nearby gate angles produce different facing, position,
    and delayed toe values. This scans every DTM-deliverable full-magnitude SIDE target through the
    complete animation model for the supplied exact rest seed.
    """
    best = None
    tested = 0
    for gate in gate_inputs():
        result = trace_fast_launch(state, gate)
        tested += 1
        key = (result["roll_speed"], result["pre_roll_speedF"],
               result["pre_roll_normal_speed"], gate.cosine)
        if best is None or key > best[0]:
            best = (key, result)
    if best is None:
        raise RuntimeError("no clean-DTM fast-launch gate entered FRONT_ROLL")
    result = dict(best[1])
    result["candidates_tested"] = tested
    return result


def synthetic_rest(low_life: bool = False, wait_frames: int = 0) -> LandState:
    """Build a deterministic test rest reached through a real walk-to-WAIT transition.

    This is useful for mechanism exploration.  It is not a substitute for a captured seed when an
    absolute console setup is required, because the live toe stream and WAIT phase are part of the
    exact ``speedF`` result.
    """
    s = LandState(
        pos_z=0.0, state=FREE_WAIT, low_life=low_life, input_delay=0,
        use_anim=True, native=False, foot_native=False,
    )
    for _ in range(8):
        s.step(128, 255)
    for _ in range(40):
        s.step(128, 128)
        if s.state == WAIT:
            break
    if s.state != WAIT:
        raise RuntimeError("synthetic launch seed did not settle to WAIT")
    for _ in range(max(0, int(wait_frames))):
        s.step(128, 128)
    return s


def _jsonable(value):
    if isinstance(value, GateInput):
        return {
            "delivered": list(value.delivered),
            "authored": list(value.authored),
            "target_offset": value.target_offset,
            "cosine": value.cosine,
        }
    raise TypeError(type(value).__name__)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--critical", action="store_true", help="seed the synthetic rest at critical health")
    parser.add_argument("--wait-frames", type=int, default=0, help="neutral WAIT frames before the launch")
    args = parser.parse_args(argv)

    seed = synthetic_rest(low_life=args.critical, wait_frames=args.wait_frames)
    result = {
        "potential_ceiling": potential_speed_ceiling(),
        "best_constant_gate_for_seed": optimize_constant_gate_launch(seed),
    }
    print(json.dumps(result, indent=2, default=_jsonable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
