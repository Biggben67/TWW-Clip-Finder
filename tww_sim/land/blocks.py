#!/usr/bin/env python3
"""blocks.py - the human-consistent land "block" catalog + the float-perfect composition primitive.

A **block** is a discrete, human-consistent ground action that starts and ends at a standstill and
that a runner can perform WITHOUT frame-perfect timing (e.g. a targeted backflip = hold L + press A
+ hold the stick back). The setup finder composes blocks to place Link at a precise world position.

FLOAT-PERFECT BY RE-SIMULATION (not additive constants). A block's net displacement is NOT a stored
number: it depends, at the float32 level, on the exact position it starts from (position accumulates
per-frame as `pos = f32(pos + f32(d*cos))`, so the same move from a different f32 position nets a
slightly different displacement -- the world-magnitude foot-FK lesson, knowledge/model/land-sim.md).
So `apply_block` re-simulates the block through the bit-exact `LandState.step` from the actual state
and reads the resulting position from the sim (0 ULP vs console). The optimizer composes blocks by
chaining `apply_block` on cloned states -- never by summing displacements.

Because the ballistic hops (sidehop/backflip) live only on the PYTHON `LandState` path for now (the
native C twin doesn't implement them), block states are built with `native=False` (still bit-exact
via the `_foot` anim engine). See knowledge/model/land-setup-finder.md.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Tuple

from .land import LandState, WAIT, FREE_WAIT
from .plan_land import stick_for_bearing, NEUTRAL

# GC button masks (match land.LandState.step): L-target engages the JUMP do-status, A is the "do".
_L = 0x40
_A = 0x100
_TRIG_L = 255

# Frames to HOLD an action input so the 2-frame controller latency (INPUT_DELAY) delivers it and the
# proc triggers; after entry the proc leaves the grounded set so the held input can't re-trigger.
_HOLD = 3

Input = Tuple[int, int, int, int, int, int]   # (sx, sy, buttons, triggerL, csx, csy)


@dataclass
class Block:
    """One human-consistent ground action. `build(state)` returns the ACTION-phase per-frame inputs
    (before the neutral coast-to-rest) for performing the block from `state` (camera-relative, so it
    aims off the state's facing/csangle). Metadata drives filtering + honest reporting, NOT the math."""
    name: str
    family: str                          # 'backflip' | 'sidehop' | 'walk' | ...
    build: Callable[[LandState], List[Input]]
    consistency: str = "exact"           # 'exact' = one button combo, timing-free (ballistic hops);
    #                                      'timed' = depends on a release/press frame (walk-N, rolls)
    validated: bool = False              # 0-ULP live-validated against Dolphin yet?
    notes: str = ""


# --- action macros (camera-relative off the current facing) --------------------------------------
def _ballistic(state: LandState, delta_facing: int) -> List[Input]:
    """Hold L + A + a full stick aimed at `facing + delta_facing` so `getDirectionFromShapeAngle`
    buckets to the wanted hop (0x8000 back -> backflip; +-0x4000 -> sidehop L/R). Held `_HOLD` frames."""
    bearing = (state.facing + delta_facing) & 0xFFFF
    sx, sy = stick_for_bearing(bearing, state.csangle, 1.0)
    return [(sx, sy, _L | _A, _TRIG_L, 128, 128)] * _HOLD


# --- the catalog ---------------------------------------------------------------------------------

# Plain WALK is deliberately NOT a block: no way to stop it without a frame-perfect input. The
# consistent movers are the ballistic hops (below) + rolls/crawl (follow-ups). See land-setup-finder.md.
BACKFLIP = Block("backflip", "backflip", lambda s: _ballistic(s, 0x8000),
                 consistency="exact", notes="L+A+back; ~270u opposite facing, facing unchanged")
SIDEHOP_LEFT = Block("sidehop_l", "sidehop", lambda s: _ballistic(s, 0x4000),
                     consistency="exact", notes="L+A+left; ~323u left-perp of facing (2-D)")
SIDEHOP_RIGHT = Block("sidehop_r", "sidehop", lambda s: _ballistic(s, -0x4000 & 0xFFFF),
                      consistency="exact", notes="L+A+right; ~323u right-perp of facing (2-D)")


def default_catalog() -> List[Block]:
    """The v1 block set: the fully-consistent ballistic hops. Rolls (need a consistent entry speed),
    crawl, and the ESS+C-down facing turn are follow-ups -- see the module note above + land-setup-finder.md."""
    return [BACKFLIP, SIDEHOP_LEFT, SIDEHOP_RIGHT]


# --- the float-perfect composition primitive -----------------------------------------------------
def apply_block(state: LandState, block: Block, coast_max: int = 96) -> dict:
    """Re-simulate `block` from `state` (a CLONE -- the source is untouched) and coast to a standstill.
    Returns the child state + exact frame count + net (dx, dz). Bit-exact: the position is read from
    the sim, not a stored constant. `frames` = the action frames + the neutral coast to rest (the
    block's true frame COST, the setup finder's optimization target)."""
    c = state.clone()
    frames = 0
    for inp in block.build(c):
        c.step(*inp)
        frames += 1
    for _ in range(coast_max):
        if c.state in (WAIT, FREE_WAIT) and abs(c.nspeed) < 1e-6:
            break
        c.step(*NEUTRAL)
        frames += 1
    return {"state": c, "frames": frames,
            "dx": c.pos_x - state.pos_x, "dz": c.pos_z - state.pos_z}


def new_state(pos_x=0.0, pos_z=764.079, pos_y=0.0, facing=0, csangle=0, **kw) -> LandState:
    """A standstill LandState on the Python (ballistic-capable) path, seeded at a world position.
    Seed `pos_y` from the live anchor for a bit-exact ballistic airtime (the vertical f32 rounding is
    magnitude-dependent). `facing` sets the block orientation frame (s16, 0 = +z)."""
    return LandState(pos_x=pos_x, pos_z=pos_z, pos_y=pos_y, facing=facing, travel=facing,
                     csangle=csangle, native=False, **kw)
