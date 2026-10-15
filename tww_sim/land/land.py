#!/usr/bin/env python3
"""land.py - compatibility shim for the split land package.

The land procs now live in ``state.LandState`` (the class + ``step`` dispatcher) composed from the
proc mixins in ``procs/*``; constants + leaf helpers are in ``constants.py``. This module re-exports
the whole former public surface so every ``from tww_sim.land.land import LandState, MOVE, CUT_F, ...``
call site keeps working unchanged. New code may import from ``.state`` / ``.constants`` directly.
"""
from .constants import *  # noqa: F401,F403  (proc enums, DIR_*, C-up gates, SPEEDF_CHASE, ...)
from .constants import (_STATE_TAG, _is_zero, _dist_angle_s, _cM_ssin_s16,  # noqa: F401
                        cLib_addCalcAngleS)
from .state import *  # noqa: F401,F403  (LandState, run_walk, + the re-exported constants)
from .state import LandState, run_walk, _LAND_CONSTS  # noqa: F401
