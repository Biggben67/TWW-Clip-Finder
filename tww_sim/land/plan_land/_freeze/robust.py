#!/usr/bin/env python3
"""plan_land/_freeze/robust.py - the always-succeeds 3-phase C-up freeze drill.

`_reach_freeze_robust`: cruise full-speed to within coarse_gap, a sustained msd-0.5 crawl for a
uniform fine straddle, then a dedup-by-freeze-position beam drill down to the float floor. Rests
within ~1-4 ULP of ANY on-axis target, all sticks live-valid. The fallback the dispatcher lands on
when no exact analytic (roll / min_frames) hit is found. See knowledge/model/land-planner.md.
"""
from __future__ import annotations
import math

from .._primitives import (world_angle_s16, stick_for_bearing, NEUTRAL,
                           FREEZE_LATENCY, _freeze_pos)

# The min STABLE crawl: msd 0.5 sustains nspeed~4.25 -> ~1u/frame while moving; below 0.5 the walk
# collapses to rest (movement gate), so Phase 1 cruises first. Why ~1u is the floor: land-movement.md.
MSD_CRAWL = 0.5


def _ulp32(x):
    """The float32 ULP near |x| (positions are f32). Sizes the drill's dedup bucket and early-exit
    floor without assuming a fixed corridor magnitude."""
    if x == 0.0:
        return 2.0 ** -149
    _, e = math.frexp(abs(x))          # 2**(e-1) <= |x| < 2**e  ->  unbiased exponent = e-1
    return 2.0 ** (e - 24)             # ulp = 2**(exp-23) = 2**((e-1)-23)


def _drill_candidates(state, tx, tz):
    """The fine input lattice at a slow near-target state: NEUTRAL (keep decelerating) plus EVERY
    distinct live-valid integer walk stick aimed at the live bearing. The magnitude is scanned finely
    (1/1000) so no distinct integer cell is skipped; the (0.889, 1) band (stick Y in 192-254) is
    excluded -- the sim's /54 magnitude over-reads live PADClamp there (land-movement.md)."""
    th = world_angle_s16(tx - state.pos_x, tz - state.pos_z)
    out = [NEUTRAL]
    seen = {NEUTRAL}
    for j in range(2, 1001):
        msd = j / 1000.0
        if 0.889 < msd < 1.0:
            continue
        stick = stick_for_bearing(th, state.csangle, min(msd, 1.0))
        if stick not in seen:
            seen.add(stick)
            out.append(stick)
    return out


def _reach_freeze_robust(seed, tx, tz, coarse_gap, max_frames, drill_back, beam_width):
    """The robust 3-phase drill (see module docstring). Extracted verbatim from the former inline
    body of reach_freeze; the dispatcher supplies the tuning parameters."""
    dx, dz = tx - seed.pos_x, tz - seed.pos_z
    norm = math.hypot(dx, dz)
    ux, uz = (dx / norm, dz / norm) if norm > 1e-9 else (0.0, 1.0)

    def proj(px, pz):                  # signed distance along the approach dir PAST the target
        return (px - tx) * ux + (pz - tz) * uz

    def fdist(state):
        e = _freeze_pos(state)
        return math.hypot(tx - e.pos_x, tz - e.pos_z), e

    # Phase 1 -- cruise full-speed until the freeze is within coarse_gap of the target.
    s = seed.clone()
    pre = []
    while len(pre) < max_frames:
        _, e = fdist(s)
        if proj(e.pos_x, e.pos_z) >= -coarse_gap:
            break
        th = world_angle_s16(tx - s.pos_x, tz - s.pos_z)
        stick = stick_for_bearing(th, s.csangle, 1.0)
        s.step(*stick)
        pre.append(stick)

    # Phase 2 -- sustained msd-0.5 crawl; snapshot each frame until the freeze crosses the target.
    snaps = [(s.clone(), list(pre))]
    while len(pre) < max_frames:
        th = world_angle_s16(tx - s.pos_x, tz - s.pos_z)
        stick = stick_for_bearing(th, s.csangle, MSD_CRAWL)
        s.step(*stick)
        pre.append(stick)
        snaps.append((s.clone(), list(pre)))
        _, e = fdist(s)
        if proj(e.pos_x, e.pos_z) > 0.0:
            break

    # closest freeze over the crawl, and the last snapshot still SHORT of the target (drill seed).
    best = None
    ci = 0
    for i, (st, p) in enumerate(snaps):
        d, e = fdist(st)
        if best is None or d < best[0]:
            best = (d, e, p)
        if proj(e.pos_x, e.pos_z) <= 0.0:
            ci = i

    # Phase 3 -- dedup-by-freeze-position beam drill from drill_back crawl frames before the crossing.
    ulp = _ulp32(tz)
    bucket = ulp * 0.25                # ~1/4 ULP: dedups true duplicates, keeps distinct freezes apart
    start = max(0, ci - drill_back)
    st0, p0 = snaps[start]
    _, e0 = fdist(st0)
    frontier = {round(proj(e0.pos_x, e0.pos_z) / bucket): (st0, p0)}
    for _ in range(drill_back + 8):
        nxt = {}
        for st, p in frontier.values():
            for stick in _drill_candidates(st, tx, tz):
                c = st.clone()
                c.step(*stick)
                d, e = fdist(c)
                if d < best[0]:
                    best = (d, e, p + [stick])
                pj = proj(e.pos_x, e.pos_z)
                if pj <= 0.02:         # keep the still-short-of-target frontier
                    key = round(pj / bucket)
                    if key not in nxt:
                        nxt[key] = (c, p + [stick])
        if not nxt:
            break
        if len(nxt) > beam_width:      # cap to the freezes nearest the target (key ~ proj/bucket)
            nxt = dict(sorted(nxt.items(), key=lambda kv: abs(kv[0]))[:beam_width])
        frontier = nxt
        if best[0] <= ulp * 1.01:      # hit the float floor -- no point drilling finer
            break

    d, end, prefix = best
    seq = list(prefix) + [NEUTRAL] * FREEZE_LATENCY
    return {'seq': seq, 'freeze_dist': d, 'freeze_pos': (end.pos_x, end.pos_z),
            'end': end, 'n_frames': len(seq)}
