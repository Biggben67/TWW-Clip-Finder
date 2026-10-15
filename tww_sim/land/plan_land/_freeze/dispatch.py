#!/usr/bin/env python3
"""plan_land/_freeze/dispatch.py - the public `reach_freeze` entry + variant selection.

Branches roll -> min_frames -> robust: the two fewest-frame analytic variants each fall back to the
always-succeeds robust drill when no exact hit is found within kmax. See knowledge/model/land-planner.md.
"""
from __future__ import annotations

from .roll import _reach_freeze_roll
from .min_frames import _reach_freeze_min
from .robust import _reach_freeze_robust


def reach_freeze(seed, tx, tz, coarse_gap=60.0, max_frames=4000, drill_back=8, beam_width=96,
                 min_frames=False, kmax=5, roll=False, roll_speed_min=26.0):
    """FLOAT-PERFECT reach via the C-up speed cancel: place the FROZEN float within a ULP or two of
    (tx, tz). Issue the cancel (one half-L frame, then neutral stick + C-stick full up) mid-motion and
    Link's position locks FREEZE_LATENCY frames later -- which the sim reads with zero new code
    (`_freeze_pos`). Because the freeze truncates the ~49u decel coast to a hard lock, a slow approach
    can place the frozen float almost anywhere.

    THREE phases, each O(1)-per-candidate on the bit-exact mid-walk clone:
      1. cruise full-speed until the freeze is within `coarse_gap` of the target;
      2. a sustained msd-0.5 crawl (`MSD_CRAWL`, the min STABLE crawl ~1u/frame), snapshotting each
         frame until the freeze crosses the target. This gives a uniform fine straddle for ANY target
         -- unlike a proportional glide, which overshoots-at-speed on short trips and stalls to a dead
         stop on long ones (the freeze coast scales with speed, so you must arrive SLOW to arrive fine);
      3. a dedup-by-freeze-position beam drill from `drill_back` crawl frames before the crossing:
         branch over `_drill_candidates` (neutral + the live-valid integer sticks), evaluate a freeze
         after each, and keep a frontier deduped by quantized freeze position and capped to those
         nearest the target. This fills the ~1u crawl step down to the float floor.

    Robust on the open +z corridor: every target rests within ~1-4 ULP (< 0.0006u), all sticks
    live-valid (msd<=0.889 or the full corner), and the whole seq re-simulates to the reported freeze.

    SCOPE: on-axis / +z corridor (like milestone 1). An OFF-AXIS target's crawl emits full-deflection
    DIAGONAL sticks that need the octagon clamp -- the separate open decode issue (see the
    advancewith-off-axis lesson) -- so off-axis freeze plans are not yet live-valid.

    The approach + cancel hold a FROZEN camera (centered C-stick) so csangle stays put. Returns dict:
    seq (approach prefix + the FREEZE_LATENCY cancel tail), freeze_dist, freeze_pos (x, z), end
    (LandState frozen), n_frames. Mechanics: knowledge/mechanics/land-movement.md; model:
    knowledge/model/land-planner.md.

    `min_frames=True` selects the FEWEST-FRAME bit-exact variant instead (`_reach_freeze_min`): a from-
    rest START crawl + full cruise, ~+7 over the pure full-up floor vs this robust approach's +19..32.
    It requires the seed AT REST (the crawl's low speeds are the free fine grid) and returns 0-ULP
    (exact float), so its plan is bit-exact live. Slower to SOLVE (an unlucky target needs a k=5 start,
    tens of seconds) and on-axis only; if no exact hit is found up to `kmax` it falls back to the robust
    phases below. See the START-crawl block comment above and land-planner.md.

    `roll=True` selects the FEWEST-FRAME analytic ROLL-approach variant (`_reach_freeze_roll`): a from-rest
    start crawl + full cruise + chained forward rolls (26 u/frame) + a short walk tail + C-up. Rolls cover
    ~25.6 vs 17 u/frame, so it rests ~15-30 frames BELOW the pure full-up walk floor, and the roll's anim
    reset makes the per-leaf freeze prediction exact (fast, per-call guided DFS -- no precomputed table).
    Its `seq` frames are (sx, sy, buttons) 3-tuples (A=0x100 on each roll's press frame). On-axis / +z, seed
    AT REST; 0-ULP live when `seed` is seeded from the live anchor. Falls back to min_frames/robust if no
    exact hit up to `kmax`. See land-planner.md.

    `roll_speed_min` (with `roll=True`, default 26.0 = the cap = FULL rolls only) is the DENSIFIER knob:
    lower it (e.g. 20, 15) to admit partial-speed tuning rolls (mNormalSpeed in [roll_speed_min, 26]) as
    the last roll, densifying the coarse grid so hard exact targets hit at a SHALLOWER start crawl (faster
    solve) -- trading a few frames for solve speed. 26.0 preserves the frame-optimal full-only plan.
    """
    if roll:
        got = _reach_freeze_roll(seed, tx, tz, kmax=kmax, max_frames=max_frames,
                                 roll_speed_min=roll_speed_min)
        if got is not None:
            return got
        # no exact roll hit within kmax -> fall through to the walk start-crawl / robust approach.
    if min_frames:
        got = _reach_freeze_min(seed, tx, tz, kmax=kmax, max_frames=max_frames)
        if got is not None:
            return got
        # no exact hit within kmax -> fall through to the robust (always-succeeds) approach.
    return _reach_freeze_robust(seed, tx, tz, coarse_gap, max_frames, drill_back, beam_width)
