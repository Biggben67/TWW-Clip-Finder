"""tww_sim.land — the land-movement component.

Models the land procs ``WAIT_e`` (0x04) / ``FREE_WAIT_e`` (0x05) / ``MOVE_e`` (0x06) /
``ATN_MOVE_e`` (0x07) / ``WAIT_TURN_e`` (0x17) / ``MOVE_TURN_e`` (0x18) / ``SLIP_e`` (0x19) /
``FRONT_ROLL_e`` (0x1E) (``land``), plus the input/route planner (``plan_land``). Consumes
:mod:`tww_sim.core` (math, camera, the J3D ``anim`` engine) — never :mod:`tww_sim.swim`.
"""
from .land import LandState, run_walk  # noqa: F401

__all__ = ["LandState", "run_walk"]
