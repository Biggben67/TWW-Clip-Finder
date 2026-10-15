#!/usr/bin/env python3
"""plan_land/_freeze/roll.py - the fewest-frame bit-exact freeze via a ROLL approach.

`_reach_freeze_roll`: from-rest start crawl + full cruise + chained forward rolls (26 u/frame) + a
short walk tail + C-up; ~15-30 frames below the walk floor. The roll's anim reset makes the per-leaf
freeze prediction exact, so a fast guided DFS (pos_cap prune + optional partial-speed tuning-roll
densifier) finds it with no precomputed table. Model + the analytic solve: land-planner.md.
"""
from __future__ import annotations

from .._primitives import (world_angle_s16, stick_for_bearing, dist2d, _f32_bits,
                           _freeze_pos, FREEZE_LATENCY, NEUTRAL)
from ...state import LandState
from ...constants import FRONT_ROLL, MOVE
from .min_frames import _freeze_start_lattice

# Fewest-frame bit-exact freeze via a ROLL approach (`reach_freeze(roll=True)`): start crawl + rolls (26
# u/frame) + walk tail + C-up; ~15-30 frames below the walk floor. Model + the analytic solve: land-planner.md.
_ROLL_RMAX = 30                 # walk-tail scan depth after the last roll (the fine freeze straddle)
_ROLL_PC_BAND = 0.02            # predicted |freeze - tz| (via pos_cap) -> bit-confirm (>> 1-ULP wobble)
_ROLL_PC_MARGIN = 0.05          # pos_cap prune safety margin (>> the ~1-ULP pos_cap-vs-δ wobble)


def _roll_accel(s, full, stream=None):
    """Full-forward until nspeed holds the run cap for 2 frames (post-accel MOVE cruise)."""
    prev = False
    for _ in range(16):
        at = (s.nspeed == float(LandState.MAX_NSPEED))
        if at and prev:
            return
        prev = at
        s.step(*full)
        if stream is not None:
            stream.append((full[0], full[1], 0))


def _roll_pos_cap(state, full):
    """Position at the run cap from `state` (clone) -- the leaf's freeze offset δ equals this pos-at-cap
    offset to ~1 ULP (the whole post-roll downstream is history-independent), so it is the cheap
    (~5-step) predictor + a clean monotone scalar to prune the start-crawl DFS on. `state` untouched."""
    s = state.clone()
    _roll_accel(s, full)
    return s.pos_z


def _roll_cycle(s, full, stream=None):
    """One chained forward roll: press A (0x100) from a MOVE frame, hold full through the roll until it
    exits back to MOVE. A re-rolls only from MOVE and carries the 2-frame input delay, so a cycle is
    ~19 frames (+486.5u at the run cap); the roll's setSingleMoveAnime leaves m34C3==0, so the walk
    blend re-inits its frame ctrl to 0 on exit -- the canonical-phase RESET that makes the freeze
    analytic (land-movement.md Roll section)."""
    s.step(full[0], full[1], buttons=0x100)
    if stream is not None:
        stream.append((full[0], full[1], 0x100))
    entered = False
    for _ in range(40):
        if s.state == FRONT_ROLL:
            entered = True
        if entered and s.state == MOVE:
            return
        s.step(*full)
        if stream is not None:
            stream.append((full[0], full[1], 0))


# The chained-roll speed cap: clamp(speedF*1.5 + 0.5) with speedF at the walk cap = 0.5 + 17*1.5 = 26.
_ROLL_CAP = float(LandState.ROLL_ADD + LandState.MAX_NSPEED * LandState.ROLL_SPD)


def _roll_tune_cycle(s, full, holds, stream=None):
    """One partial-speed 'tuning' roll (the densifier): hold each partial FORWARD stick in `holds` first
    -- decaying speedF below the walk cap 17 so the re-roll clamps to an intermediate mNormalSpeed (< 26)
    -- then press A and hold full through the roll to the MOVE exit (like `_roll_cycle`, with the pre-roll
    partial shave). Post-roll `anim_fc0 == 0` holds (the roll still resets the walk anim), so the freeze
    stays analytic; the shorter roll distance is the extra coarse-grid point. See land-planner.md."""
    for st in holds:
        s.step(*st)
        if stream is not None:
            stream.append((st[0], st[1], 0))
    _roll_cycle(s, full, stream)


def _roll_tuning_catalog(seed, full, th, csangle, roll_speed_min):
    """Distinct partial-speed tuning-roll recipes whose roll mNormalSpeed lands in [roll_speed_min,
    _ROLL_CAP) -- the densifier lattice, cheapest-frames per distinct speed. Each recipe is a `holds`
    tuple of live-valid partial FORWARD sticks (msd 0.52..0.889, aimed at the target bearing) pressed
    before the roll's A. Built from a reference post-accel cruise (identical after any full roll -- the
    roll's anim reset makes it history-independent). Returns [] when the range excludes all partials
    (`roll_speed_min` >= the 26 cap) so the caller's full-only path is byte-for-byte preserved."""
    if roll_speed_min >= _ROLL_CAP - 1e-6:
        return []
    ref = seed.clone()
    _roll_accel(ref, full)
    alph, seen_st = [], set()               # partial forward stick alphabet (dedup, live-valid msd)
    for j in range(520, 890):
        st = stick_for_bearing(th, csangle, j / 1000.0)
        if st not in seen_st:
            seen_st.add(st)
            alph.append(st)
    best = {}                               # speed f32 bits -> (nholds, holds tuple)
    for h in range(1, 7):
        for st in alph:
            c = ref.clone()
            for _ in range(h):
                c.step(*st)
            c.step(full[0], full[1], buttons=0x100)
            sp = None
            for _ in range(40):
                if c.state == FRONT_ROLL:
                    sp = c.nspeed
                    break
                c.step(*full)
            if sp is not None and roll_speed_min <= sp < _ROLL_CAP:
                key = _f32_bits(sp)
                if key not in best or h < best[key][0]:
                    best[key] = (h, tuple([st] * h))
    return [v[1] for v in best.values()]


def _reach_freeze_roll(seed, tx, tz, kmax=5, max_frames=4000, roll_speed_min=26.0):
    """Fewest-frame bit-exact C-up freeze via a ROLL approach (see the block comment above). Grows the
    start window k=2..kmax; per k, DFS the from-rest crawl sticks with a **pos_cap prune**: the needed
    pos_cap for each roll config (nr_full full rolls + optional tuning roll + r walk-tail) is
    `ref_pc + (tz - freeze_ref(config))` (history-independent, computed once), and a subtree is skipped
    when its reachable pos_cap range (all-full completion -> max, all-slow -> min) misses every needed
    value. Each surviving leaf's pos_cap (~5-step accel-to-cap) predicts its freeze to ~1 ULP; predicted
    matches get an exact bit-confirm; objective = fewest TOTAL frames (running-best prune over k).
    Returns a plan dict whose `seq` frames are (sx, sy, buttons) 3-tuples (A=0x100 on each roll's press
    frame), else None (caller falls back).

    `roll_speed_min` (default 26.0 = the cap = FULL rolls only, the frame-optimal but sparse grid) is the
    DENSIFIER knob: lowering it admits partial-speed tuning rolls with mNormalSpeed in [roll_speed_min,
    26] as the LAST roll, adding frame-neutral..cheap coarse-grid points so more targets hit the exact
    float at a SHALLOWER start crawl (faster solve). Wider range (lower min) = denser grid = faster/
    lower-k solve, at the cost of a few frames (partial rolls cover less than 26); narrow (=26) preserves
    the full-only fewest-frame plan exactly. See land-planner.md (ROLL densifier).

    ON-AXIS / +z, seed AT REST (the crawl's low speeds are the free fine grid). Because the sim is 0-ULP
    vs live when seeded from the anchor, the returned plan freezes bit-exact on console -- provided the
    caller seeds `seed` from the LIVE anchor (a 2-ULP seed-pos mismatch shifts the freeze by 1 ULP)."""
    if abs(tx - seed.pos_x) > 1e-6:
        return None                         # on-axis only (off-axis needs the octagon clamp)
    full, lattice = _freeze_start_lattice(seed, tx, tz)
    slow = lattice[-1]                       # slowest live-valid start frame (min pos_cap completion)
    TB = _f32_bits(tz)
    ref_pc = _roll_pos_cap(seed, full)       # reference pos-at-cap (delta baseline)
    th = world_angle_s16(tx - seed.pos_x, tz - seed.pos_z)
    catalog = [None] + _roll_tuning_catalog(seed, full, th, seed.csangle, roll_speed_min)

    def ref_after(nr_full, tune):            # reference (no start crawl): accel + full rolls + tune roll
        s = seed.clone()
        _roll_accel(s, full)
        for _ in range(nr_full):
            _roll_cycle(s, full)
        if tune is not None:
            _roll_tune_cycle(s, full, tune)
        return s

    ref_freeze10 = _freeze_pos(ref_after(1, None)).pos_z
    roll_dz = _freeze_pos(ref_after(2, None)).pos_z - ref_freeze10
    nr_lo = max(0, int((tz - ref_freeze10) / roll_dz) - 1)   # tuning rolls shorten -> widen the low end
    nr_hi = nr_lo + 3
    # history-independent downstream, computed ONCE: needed pos_cap = ref_pc + (tz - freeze_ref(config)).
    needed = []                              # (target pos_cap, nr_full, tune, r, nonstart_frames)
    seen_fr = set()
    for nr_full in range(nr_hi, nr_lo - 1, -1):
        for tune in catalog:
            s0 = seed.clone(); stream0 = []
            _roll_accel(s0, full, stream0)
            for _ in range(nr_full):
                _roll_cycle(s0, full, stream0)
            if tune is not None:
                _roll_tune_cycle(s0, full, tune, stream0)
            if s0.state != MOVE:
                continue
            base = len(stream0)
            t = s0.clone()
            for r in range(_ROLL_RMAX):
                if t.state == MOVE:
                    fr = _freeze_pos(t).pos_z
                    if _f32_bits(fr) not in seen_fr:         # dedup identical freeze_ref
                        seen_fr.add(_f32_bits(fr))
                        needed.append((ref_pc + (tz - fr), nr_full, tune, r, base + r))
                t.step(*full)
    if not needed:
        return None
    needed.sort(key=lambda e: e[4])          # fewest non-start frames first
    # A start crawl only pushes the freeze FORWARD (delta >= 0, bounded ~MAXD); keep only configs whose
    # needed pos_cap lands in [ref_pc, ref_pc+MAXD] so the leaf prune stays tight (land-planner.md).
    MAXD = 12.0 * kmax                       # generous bound on the start-crawl forward delta (obs ~7u/fr)
    needed = [e for e in needed
              if (ref_pc - _ROLL_PC_MARGIN) <= e[0] <= (ref_pc + MAXD + _ROLL_PC_MARGIN)]
    if not needed:
        return None
    p_lo = ref_pc - _ROLL_PC_MARGIN
    p_hi = max(e[0] for e in needed) + _ROLL_PC_MARGIN

    def confirm(start_seq, nr_full, tune, r):
        s = seed.clone()
        stream = []
        for st in start_seq:
            s.step(*st); stream.append((st[0], st[1], 0))
        _roll_accel(s, full, stream)
        for _ in range(nr_full):
            _roll_cycle(s, full, stream)
        if tune is not None:
            _roll_tune_cycle(s, full, tune, stream)
        for _ in range(r):
            s.step(*full); stream.append((full[0], full[1], 0))
        if s.state != MOVE:
            return None
        e = _freeze_pos(s)
        return (stream, e) if _f32_bits(e.pos_z) == TB else None

    import bisect as _bisect
    needed_full = [e for e in needed if e[2] is None]      # full-roll configs (fewest-frame at any k)
    needed_tune = [e for e in needed if e[2] is not None]  # partial-tuning-roll configs (the densifier)

    def _prune(state, rem):                  # True -> subtree's reachable pos_cap misses [p_lo, p_hi]
        hf = state.clone()                   # all-full completion (fastest to cap -> MIN pos_cap, delta~0)
        for _ in range(rem):
            hf.step(*full)
        sf = state.clone()                   # all-slow completion (banks low-speed distance -> MAX pos_cap)
        for _ in range(rem):
            sf.step(*slow)
        lo_r, hi_r = sorted((_roll_pos_cap(hf, full), _roll_pos_cap(sf, full)))
        return hi_r < p_lo or lo_r > p_hi

    def _full_first_hit(k):
        """Fast first-hit DFS over FULL configs -- a full config is the fewest-frame at any k, so its
        first bit-exact hit at depth k is optimal there (the committed full-only behavior, ~seconds)."""
        def rec(state, seq):
            rem = k - len(seq)
            if rem > 0 and _prune(state, rem):
                return None
            if len(seq) == k:
                pc = _roll_pos_cap(state, full)
                for p, nr_full, tune, r, cf in needed_full:
                    if abs(pc - p) <= _ROLL_PC_BAND:
                        got = confirm(seq, nr_full, tune, r)
                        if got is not None:
                            return (seq, nr_full, tune, r, got)
                return None
            for stick in lattice:
                child = state.clone(); child.step(*stick)
                got = rec(child, seq + [stick])
                if got:
                    return got
            return None
        return rec(seed.clone(), [])

    def _tune_config_first(k):
        """Reached only when no full config hits at this k (the densifier's point). Enumerate the depth-k
        leaves surviving the prune, then match CONFIG-FIRST (fewest-frames-ordered, bisect on leaf pos_cap)
        -- the fewest-frame TUNING config any leaf hits (first-hit-per-leaf can't: a costlier tuning config
        could match an earlier leaf). Fast: only runs at LOW k where full missed (small leaf set)."""
        if not needed_tune:
            return None
        leaves = []
        def rec(state, seq):
            rem = k - len(seq)
            if rem > 0 and _prune(state, rem):
                return
            if len(seq) == k:
                leaves.append((_roll_pos_cap(state, full), list(seq)))
                return
            for stick in lattice:
                child = state.clone(); child.step(*stick)
                rec(child, seq + [stick])
        rec(seed.clone(), [])
        if not leaves:
            return None
        leaves.sort(key=lambda L: L[0])
        keys = [L[0] for L in leaves]
        for p, nr_full, tune, r, cf in needed_tune:
            i = _bisect.bisect_left(keys, p - _ROLL_PC_BAND)
            while i < len(leaves) and keys[i] <= p + _ROLL_PC_BAND:
                got = confirm(leaves[i][1], nr_full, tune, r)
                if got is not None:
                    return (leaves[i][1], nr_full, tune, r, got)
                i += 1
        return None

    def search(k):
        return _full_first_hit(k) or _tune_config_first(k)

    for k in range(2, kmax + 1):
        got = search(k)
        if got is None:
            continue
        start_seq, nr_full, tune, r, (stream, e) = got
        seq = list(stream) + [(NEUTRAL[0], NEUTRAL[1], 0)] * FREEZE_LATENCY
        return {'seq': seq, 'freeze_dist': dist2d(e, tx, tz), 'freeze_pos': (e.pos_x, e.pos_z),
                'end': e, 'n_frames': len(seq), 'start_frames': len(start_seq),
                'rolls': nr_full + (1 if tune is not None else 0), 'tail': r, 'tuned': tune is not None}
    return None
