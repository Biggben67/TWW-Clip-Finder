"""tww_sim.swim — the superswimming component.

Models the swim procs ``SWIM_UP_e`` (0x35) / ``SWIM_WAIT_e`` (0x36) / ``SWIM_MOVE_e`` (0x37)
(``sim``), plus the route planner (``plan``/``optimize``), cold-start seeding (``coldstart``),
the action-sequence vocabulary (``actions``), and the position/camera predictors (``predict/``).
Depends only on :mod:`tww_sim.core` — never on ``tww_sim.land``.
"""
from .sim import SwimState, ArrowState, run_trace, run_arrow  # noqa: F401
from .plan import plan_min_frames, plan_hierarchical  # noqa: F401
from .optimize import beam_search, beam_search_to_dest  # noqa: F401
from .actions import expand, acts_to_seq, animdiff, ESS, NEU, CHG_UP, CHG_DN  # noqa: F401

__all__ = [
    "SwimState", "ArrowState", "run_trace", "run_arrow",
    "plan_min_frames", "plan_hierarchical", "beam_search", "beam_search_to_dest",
    "expand", "acts_to_seq", "animdiff", "ESS", "NEU", "CHG_UP", "CHG_DN",
]
