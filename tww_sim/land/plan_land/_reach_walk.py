#!/usr/bin/env python3
"""plan_land/_reach_walk.py - the straight-walk + precise-glide reach.

`reach_straight` (full-deflection glide, release-frame sweep for min resting distance; live-confirmed
bit-exact) and `reach_precise` (proportional-speed glide into a crawl, then a truncation search picks
the release). Both are target-SENSITIVE (0.1-9u); sub-0.1u exact stops use the freeze reach. The
bit-exact forward model IS `state.LandState.step`; this is the search layer on top of it.
"""
from __future__ import annotations
import math
from collections import deque

from ._primitives import NEUTRAL, world_angle_s16, dist2d, stick_for_bearing
from ..state import LandState
from ..constants import WAIT, FREE_WAIT

_CUT_SPAN = 60          # Phase-C / freeze sweep window: the last _CUT_SPAN+1 crawl frames near arrival


def _live_valid_msd(msd):
    """Snap msd out of the live-divergent band (0.889, 1): those map to stick Y in [192,254], where
    the sim's /54 magnitude over-reads live PADClamp -- to the nearest live-valid magnitude (a <=0.889
    partial, or 1.0 = the true full corner). See land-movement.md "Live-valid stick magnitudes"."""
    if msd <= 0.889:
        return msd
    return 1.0 if msd >= 0.9445 else 0.889


def _coast_to_rest(state, tx, tz, coast_max=48):
    """Feed neutral from a CLONE of `state` until Link comes to rest (or `coast_max`), leaving the
    source untouched. Mid-walk clone is bit-exact, so the coast is identical to re-simulating the
    whole prefix. Returns (resting_dist, coast_frames, end_state)."""
    c = state.clone()
    n = 0
    for _ in range(coast_max):
        c.step(*NEUTRAL)
        n += 1
        if c.state in (WAIT, FREE_WAIT) and abs(c.nspeed) < 1e-6:
            break
    return dist2d(c, tx, tz), n, c


def reach_straight(seed, tx, tz, max_walk=240, coast_max=48):
    """STRAIGHT-WALK reach: return the input sequence whose RESTING position is closest to the
    target (tx, tz). Walk the live-bearing full-deflection glide ONCE; at each release frame clone
    the walk state and coast that clone to rest, keeping the minimum resting distance. Because the
    walk is one deterministic trajectory and clone() is bit-exact mid-walk, this is identical to the
    old per-release re-simulation but O(n) instead of O(n^2) in walk steps.

    Returns dict: seq, resting_dist, n_walk, end (LandState), n_frames.
    """
    walk = seed.clone()
    walk_seq = []
    best = None
    for n in range(1, max_walk + 1):
        th = world_angle_s16(tx - walk.pos_x, tz - walk.pos_z)
        sx, sy = stick_for_bearing(th, walk.csangle)
        walk.step(sx, sy)
        walk_seq.append((sx, sy))
        d, coast_n, end = _coast_to_rest(walk, tx, tz, coast_max)
        if best is None or d < best[0]:
            best = (d, n, coast_n, end)
        # Resting distance is unimodal up to the first overshoot; past it the live-bearing re-aim
        # orbits/reverses back (messy). Stop at the FIRST local minimum -- the clean straight reach.
        elif n > best[1] + 8 and d > best[0] + 5.0:
            break
    d, n_walk, coast_n, end = best
    seq = list(walk_seq[:n_walk]) + [NEUTRAL] * coast_n
    return {'seq': seq, 'resting_dist': d, 'n_walk': n_walk, 'end': end, 'n_frames': len(seq)}


def _glide(seed, tx, tz, k, min_crawl, turnback, max_frames, clamp_msd=False):
    """Proportional-speed glide toward (tx, tz): aim the live bearing each frame, scaling the stick
    magnitude so the target speed tracks k*remaining -- Link stays in MOTION into a crawl (~min_crawl
    u/frame) and feeds PAST the target (the 2-frame latency overshoots). Speed cap = 17*msd^2, so
    msd = sqrt(target_speed/17), floored at the movement gate and capped at 1. `clamp_msd` keeps every
    emitted stick live-valid (snaps out of the Y192-254 band) for plans that must run on console.
    Snapshots a clone each frame into a rolling buffer (the last _CUT_SPAN+1 frames straddling closest
    approach -- bounds memory for any walk length; mid-walk clone is bit-exact). Returns (walk, snaps)."""
    s = seed.clone()
    walk = []
    snaps = deque([s.clone()], maxlen=_CUT_SPAN + 1)   # snaps[i] = state after applying walk[:i]
    prev = dist2d(s, tx, tz)
    near = False
    while len(walk) < max_frames:
        rem = dist2d(s, tx, tz)
        if rem < turnback:
            near = True
        if near and rem > prev:                    # first turnback after arriving = crawl overshoot;
            break                                  # stop before the controller limit-cycles around it
        prev = rem
        target_speed = min(max(k * rem, min_crawl), float(LandState.MAX_NSPEED))
        msd = min(max(math.sqrt(target_speed / float(LandState.MAX_NSPEED)), 0.051), 1.0)
        if clamp_msd:
            msd = _live_valid_msd(msd)
        th = world_angle_s16(tx - s.pos_x, tz - s.pos_z)
        stick = stick_for_bearing(th, s.csangle, msd)
        s.step(*stick)
        walk.append(stick)
        snaps.append(s.clone())
    return walk, snaps


def reach_precise(seed, tx, tz, eps=0.05, k=0.5, min_crawl=0.043, turnback=1.0,
                  max_frames=4000):
    """PRECISE reach: rest within ~eps of (tx, tz) (sub-unit), where whole-frame full-speed
    `reach_straight` is limited to ~15u release granularity. A proportional-speed feedback
    controller (the exact sim IS the model) glides into a crawl, then a truncation search picks the
    release: cut the glide at each candidate frame + coast to rest, keep the min-distance rest.

    Why not brake to a stop then creep: from a STANDSTILL the walk needs msd > 0.5 to move at all
    (the setSpeedAndAngleNormal speed-scale gate 0.5 - 0.5*|v|/max), so a slow crawl can't be
    RESTARTED from rest -- it must be sustained by never fully stopping. And a full-speed neutral
    release coasts ~49u (the whole 17->0 decel arc). Rests ~0.10u from target (the smooth-walk floor);
    sub-0.1u needs the C-up freeze (`reach_freeze`) or tap-inch hops.

    Returns dict: seq, resting_dist, end (LandState), n_frames.
    """
    walk, snaps = _glide(seed, tx, tz, k, min_crawl, turnback, max_frames)
    # Truncation search -- the crawl tail advances ~min_crawl u/frame, so cutting the walk + coasting
    # lands within a crawl step. Clone each snapshot, coast, keep the min. O(n), bit-exact vs re-sim.
    cut_base = len(walk) - (len(snaps) - 1)     # rolling buffer's leftmost snapshot's cut index
    best = None
    for off, snap in enumerate(snaps):
        t = snap.clone()
        coast = 0
        for _ in range(30):
            if t.state in (WAIT, FREE_WAIT) and abs(t.nspeed) < 1e-6:
                break
            t.step(*NEUTRAL)
            coast += 1
        d = dist2d(t, tx, tz)
        if best is None or d < best[0]:
            best = (d, cut_base + off, coast, t)
    d, cut, coast, t = best
    seq = list(walk[:cut]) + [NEUTRAL] * coast
    return {'seq': seq, 'resting_dist': d, 'end': t, 'n_frames': len(seq)}
