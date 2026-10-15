#!/usr/bin/env python3
"""plan_land - LAND input planner: init LandState + world target (x, z) -> input seq.

Given a `LandState` and a target world position (x, z) as an arbitrary float, produce a controller
stick sequence that walks/steers Link there. The bit-exact forward model is `tww_sim.land.state.
LandState.step`; this is the search/planning layer on top of it. Split into single-topic modules:
  * `_primitives`   -- world-bearing <-> stick inverse, freeze read, seq/bit helpers
  * `_reach_walk`   -- `reach_straight` (full-speed release sweep) + `reach_precise` (proportional glide)
  * `_freeze/`      -- the FLOAT-PERFECT C-up-cancel freeze: `reach_freeze` (robust / min_frames / roll)

STATUS + scope (open +z ground; collision/off-axis/A* are follow-ups) and the LIVE-FAITHFUL stick
rules live in `_primitives` + knowledge/model/land-planner.md. This module re-exports the public API
so `from tww_sim.land.plan_land import reach_freeze, stick_for_bearing, ...` keeps working unchanged.
"""
from ._primitives import (stick_for_bearing, world_angle_s16, dist2d, seq_string,  # noqa: F401
                          FREEZE_LATENCY, NEUTRAL)
from ._reach_walk import reach_straight, reach_precise  # noqa: F401
from ._freeze.dispatch import reach_freeze  # noqa: F401
