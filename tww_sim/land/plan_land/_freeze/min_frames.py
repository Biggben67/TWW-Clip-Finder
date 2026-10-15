#!/usr/bin/env python3
"""plan_land/_freeze/min_frames.py - the fewest-frame bit-exact START-crawl freeze.

`_reach_freeze_min`: from-rest fine crawl + full cruise + C-up, ~+7 over the full-up floor. A cheap
reference cruise builds a freeze predictor (coast table + pos/fc0 rates + fc0 wrap) so the start-crawl
DFS skips leaves that can't land the target; the survivors get an exact bit-confirm. See land-planner.md.
Also owns `_freeze_start_lattice` (shared with the roll variant).
"""
from __future__ import annotations

from .._primitives import (world_angle_s16, stick_for_bearing, dist2d, _f32_bits,
                           _freeze_pos, FREEZE_LATENCY, NEUTRAL)
from ...state import LandState

# Fewest-frame bit-exact freeze -- the START crawl (`reach_freeze(min_frames=True)`): from-rest fine crawl
# + full cruise + C-up, ~+7 over the full-up floor. Model + delta-prediction filter: land-planner.md.

_FREEZE_PRED_BAND = 0.5          # predicted |freeze - T| under this -> exact-check (coast model err <=~0.3u)
_FREEZE_CAP_SCAN = 16            # frames to reach the 17u cap from the slowest start crawl


def _freeze_coast_model(seed, stick_full, ncruise=260):
    """Build the freeze predictor from a STEADY full-speed reference cruise off `seed`: the coast table
    (sorted `anim_fc0` -> freeze coast) plus the per-frame pos rate (+17), the fc0 rate (+2.3), and the
    fc0 wrap (`anim_fc0` loops at the walk anim's frameMax ~32). One cheap cruise, reused across every
    candidate. The cruise must be seeded PAST the accel ramp (the from-rest idle/accel frames run a
    different anim phase, fc0 ~70 -> they'd corrupt the steady-walk table + wrap). See land-planner.md."""
    s = seed.clone()
    cap = float(LandState.MAX_NSPEED)
    prev = False
    for _ in range(_FREEZE_CAP_SCAN):        # cruise to the steady 17u cap first
        at_cap = (s.nspeed == cap)
        if at_cap and prev:
            break
        prev = at_cap
        s.step(*stick_full)
    fcs, coasts, poss = [], [], []
    for _ in range(ncruise):
        fcs.append(s.anim_fc0)
        coasts.append(_freeze_pos(s).pos_z - s.pos_z)
        poss.append(s.pos_z)
        s.step(*stick_full)
    pos_rate = sorted(poss[i + 1] - poss[i] for i in range(len(poss) - 1))[len(poss) // 2]
    # fc0 advances +fc0_rate/frame then wraps at frameMax; read both from consecutive deltas.
    ups = [fcs[i + 1] - fcs[i] for i in range(len(fcs) - 1) if fcs[i + 1] >= fcs[i]]
    fc0_rate = sorted(ups)[len(ups) // 2]
    fc0_max = max(fcs) + fc0_rate            # a wrap resets to ~0, so max+one step ~= frameMax
    for i in range(len(fcs) - 1):            # refine from an observed wrap: max = prev + rate - next
        if fcs[i + 1] < fcs[i]:
            fc0_max = fcs[i] + fc0_rate - fcs[i + 1]
            break
    order = sorted(range(len(fcs)), key=lambda i: fcs[i])
    return ([fcs[i] for i in order], [coasts[i] for i in order], pos_rate, fc0_rate, fc0_max)


def _freeze_coast_of(model, fc0):
    """Nearest-neighbour freeze coast for a phase `fc0` (wrap-aware) from the reference model."""
    import bisect as _bisect
    fc0s, coasts, _, _, fc0_max = model
    fc0 %= fc0_max
    i = _bisect.bisect_left(fc0s, fc0)
    best_d, best_c = 1e18, coasts[0]
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(fc0s):
            d = abs(fc0s[j] - fc0)
            if d < best_d:
                best_d, best_c = d, coasts[j]
    for fj, cj in ((fc0s[0] + fc0_max, coasts[0]), (fc0s[-1] - fc0_max, coasts[-1])):
        if abs(fj - fc0) < best_d:
            best_d, best_c = abs(fj - fc0), cj
    return best_c


def _freeze_start_lattice(seed, tx, tz):
    """The from-rest start-crawl stick lattice aimed at the target bearing, FAST->slow (so the DFS's
    first exact hit is the fewest-frame plan): the full corner, then every distinct live-valid partial
    down to the movement gate (msd 0.52..0.889 -> stick Y 171..191 on-axis). msd>0.5 is required to
    move from a standstill; the (0.889, 1) band is skipped (live-divergent). See land-planner.md."""
    th = world_angle_s16(tx - seed.pos_x, tz - seed.pos_z)
    full = stick_for_bearing(th, seed.csangle, 1.0)
    out = [full]
    seen = {full}
    for j in range(889, 519, -1):            # msd 0.889 -> 0.520, fast->slow
        stick = stick_for_bearing(th, seed.csangle, j / 1000.0)
        if stick not in seen:
            seen.add(stick)
            out.append(stick)
    return full, out


def _freeze_cap_state(state, stick_full, cap_scan=_FREEZE_CAP_SCAN):
    """Cruise `state` (end of start crawl) full-forward until nspeed is at the cap for 2 frames; return
    (cap_clone, pos_cap, fc0_cap). The cap frame is where the +17/+2.3 rates hold, so the freeze is
    predictable from there. `state` untouched (works on a clone)."""
    s = state.clone()
    cap = float(LandState.MAX_NSPEED)
    prev = False
    for _ in range(cap_scan):
        at_cap = (s.nspeed == cap)
        if at_cap and prev:
            break
        prev = at_cap
        s.step(*stick_full)
    return s, s.pos_z, s.anim_fc0


def _freeze_predict(model, pos_cap, fc0_cap, T):
    """Min predicted |freeze - T| over the full cruise from a characterized cap state, and the cruise
    offset m (frames past cap) achieving it. freeze(m) ~= pos_cap + 17m + coast(fc0_cap + 2.3m)."""
    _, _, pos_rate, fc0_rate, _ = model
    best_e, best_m, m = 1e18, 0, 0
    while pos_cap + pos_rate * m <= T + 2.0:
        e = abs(pos_cap + pos_rate * m + _freeze_coast_of(model, fc0_cap + fc0_rate * m) - T)
        if e < best_e:
            best_e, best_m = e, m
        m += 1
    return best_e, best_m


def _freeze_exact_from_cap(cap_state, stick_full, m_hint, T):
    """From the characterized cap state, cruise to the freeze frame and bit-check the predicted window
    (the +-0.3u coast model can be off by a frame near a coast sawtooth jump). Returns the winning cap
    state clone (positioned so `_freeze_pos` is bit-exact at T) or None."""
    TB = _f32_bits(T)
    lo = max(0, m_hint - 2)
    s = cap_state.clone()
    for _ in range(lo):
        s.step(*stick_full)
    for _ in range(lo, m_hint + 3):
        if _f32_bits(_freeze_pos(s).pos_z) == TB:
            return s.clone()
        s.step(*stick_full)
    return None


def _reach_freeze_min(seed, tx, tz, kmax=5, max_frames=4000):
    """Fewest-frame bit-exact C-up freeze via the START crawl (see the block comment above). Grows the
    start window k=2..kmax; per k, DFS the crawl sticks FAST->slow (first exact hit = fewest frames),
    reusing the clone at each depth so a start PREFIX is never re-simulated. Each leaf is characterized
    cheaply (cruise to the cap) and the analytic predictor skips leaves that can't land T. Returns the
    plan dict (same shape as reach_freeze) on a bit-exact hit, else None (caller falls back to robust)."""
    full, lattice = _freeze_start_lattice(seed, tx, tz)
    model = _freeze_coast_model(seed, full)
    TB = _f32_bits(tz)
    root = seed.clone()

    def search(k):
        def rec(state, seq):
            if len(seq) == k:
                cap_s, pos_cap, fc0_cap = _freeze_cap_state(state, full)
                e, m = _freeze_predict(model, pos_cap, fc0_cap, tz)
                if e > _FREEZE_PRED_BAND:
                    return None
                hit = _freeze_exact_from_cap(cap_s, full, m, tz)
                return (seq, hit) if hit is not None else None
            for stick in lattice:
                child = state.clone()
                child.step(*stick)
                got = rec(child, seq + [stick])
                if got:
                    return got
            return None
        return rec(root.clone(), [])

    for k in range(2, kmax + 1):
        got = search(k)
        if got is None:
            continue
        start_seq, hit_cap = got
        # Rebuild the authoritative plan by re-simulating start + full cruise to the bit-exact freeze.
        s = seed.clone()
        seq = []
        for stick in start_seq:
            s.step(*stick)
            seq.append(stick)
        for _ in range(max_frames):
            e = _freeze_pos(s)
            if _f32_bits(e.pos_z) == TB:
                seq = list(seq) + [NEUTRAL] * FREEZE_LATENCY
                return {'seq': seq, 'freeze_dist': dist2d(e, tx, tz),
                        'freeze_pos': (e.pos_x, e.pos_z), 'end': e, 'n_frames': len(seq),
                        'start_frames': len(start_seq)}
            s.step(*full)
            seq.append(full)
        return None
    return None
