#!/usr/bin/env python3
"""setup_finder.py - the LAND setup finder: start + target -> ranked human-consistent input sequences.

The TWW analogue of the Twilight-Princess subset-sum setup tool, but FLOAT-PERFECT: instead of summing
fixed per-move displacement constants (which drift by ULPs with position magnitude + f32 non-associativity),
it composes discrete human-consistent BLOCKS (blocks.py) by RE-SIMULATING each through the bit-exact
`LandState` from the exact float state. Every reported endpoint is the sim's 0-ULP position, so a setup
the tool says lands at X really lands at X on console.

    node   = a full LandState (position + facing + anim state), reached by a sequence of blocks
    edge   = apply_block(node, block)  -> child LandState + exact frame COST
    goal   = within `tol` of the world target (tx, tz)
    rank   = total frame count, then |diff| (like the TP tool's ranked list, but cost-weighted)

Search is A* over LandState nodes: priority = frames-so-far + optimistic frames-to-target, with
dominance dedup on quantized (pos_x, pos_z, facing) so the frontier can't blow up. It collects EVERY
within-tolerance node it pops and returns them ranked, capped to `max_results`.

SCOPE (v1): 1-D-friendly (give a target on the axis) but the state + search are 2-D-native, so a full
2-D relaxation is a later change, not a rewrite. Open ground only (no collision -- the sim has none).
Ballistic block displacements are pending live 0-ULP calibration; the optimizer machinery is independent
of the exact numbers. See knowledge/model/land-setup-finder.md.
"""
from __future__ import annotations
import heapq
import itertools
import math
from dataclasses import dataclass
from typing import List, Optional

from .land import LandState
from .blocks import Block, apply_block, default_catalog, new_state, NEUTRAL

# Optimistic per-frame ground coverage (u/frame) for the A* heuristic: the fastest block's
# displacement/frame. Sidehop ~323/22 ~ 14.7; keep a hair above so the heuristic stays admissible.
_BEST_PER_FRAME = 15.0


@dataclass
class Setup:
    """One found setup: the block-name sequence, its total frame COST, the exact resulting world
    position, and the (exact) residual distance to the target."""
    blocks: List[str]
    frames: int
    pos_x: float
    pos_z: float
    diff: float
    facing: int


def _hcost(st, tx, tz):
    return math.hypot(tx - st.pos_x, tz - st.pos_z) / _BEST_PER_FRAME


def find_setups(start: LandState, tx: float, tz: float, catalog: Optional[List[Block]] = None,
                tol: float = 5.0, max_frames: int = 300, max_depth: int = 8,
                max_results: int = 50, pos_bucket: float = 1.0,
                bounds=None) -> List[Setup]:
    """A* over block sequences from `start` to within `tol` of (tx, tz), ranked by frame cost then
    |diff|. `bounds` = optional (xlo, xhi, zlo, zhi) corridor every intermediate rest must stay inside
    (the sim has no collision, so this keeps a plan off a wall). Returns up to `max_results` Setups."""
    if catalog is None:
        catalog = default_catalog()
    cnt = itertools.count()
    # frontier entries: (priority, tiebreak, cost_frames, state, path)
    pq = [(_hcost(start, tx, tz), next(cnt), 0, start, [])]
    best_cost = {}                       # dominance: sig -> lowest cost seen
    results: List[Setup] = []

    def sig(st):
        return (round(st.pos_x / pos_bucket), round(st.pos_z / pos_bucket), (st.facing >> 10) & 0x3F)

    def in_bounds(st):
        if bounds is None:
            return True
        xlo, xhi, zlo, zhi = bounds
        return xlo <= st.pos_x <= xhi and zlo <= st.pos_z <= zhi

    while pq:
        _, _, cost, st, path = heapq.heappop(pq)
        diff = math.hypot(tx - st.pos_x, tz - st.pos_z)
        if diff <= tol and path:                     # a within-tolerance placement (need >=1 block)
            results.append(Setup(list(path), cost, st.pos_x, st.pos_z, diff, st.facing))
            if len(results) >= max_results * 4:       # gathered plenty of candidates -> stop early
                break
        s = sig(st)
        if s in best_cost and best_cost[s] <= cost:  # dominated: a cheaper path already owns this cell
            continue
        best_cost[s] = cost
        if len(path) >= max_depth:
            continue
        for b in catalog:
            r = apply_block(st, b)
            nc = cost + r["frames"]
            if nc > max_frames or not in_bounds(r["state"]):
                continue
            child = r["state"]
            heapq.heappush(pq, (nc + _hcost(child, tx, tz), next(cnt), nc, child, path + [b.name]))

    results.sort(key=lambda r: (r.frames, r.diff))
    # de-dup identical block sequences that slipped through, keep order
    seen, out = set(), []
    for r in results:
        key = tuple(r.blocks)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:max_results]


def expand_path(start: LandState, block_names: List[str],
                catalog: Optional[List[Block]] = None) -> List[tuple]:
    """Expand a Setup's block-name sequence into the full per-frame controller input list
    (sx, sy, buttons, triggerL, csx, csy) -- the action frames of each block plus its neutral coast --
    for driving/verifying the plan live (DTM). Re-simulates to reproduce exactly what the search did."""
    if catalog is None:
        catalog = default_catalog()
    by_name = {b.name: b for b in catalog}
    from .land import WAIT, FREE_WAIT
    st = start.clone()
    seq: List[tuple] = []
    for name in block_names:
        b = by_name[name]
        c = st
        for inp in b.build(c):
            c.step(*inp)
            seq.append(inp)
        for _ in range(96):
            if c.state in (WAIT, FREE_WAIT) and abs(c.nspeed) < 1e-6:
                break
            c.step(*NEUTRAL)
            seq.append((*NEUTRAL, 0, 0, 128, 128))
        st = c
    return seq


def _fmt(r: Setup) -> str:
    return (f"  {r.frames:4d}f  diff={r.diff:8.4f}  pos=({r.pos_x:+.4f}, {r.pos_z:+.4f})  "
            f"[{' + '.join(r.blocks)}]")


def _main(argv):
    """CLI: python -m tww_sim.land.setup_finder tz=1500 [sz=764.079 sx=0 sy=0 facing=0 tx=0 tol=5
    maxf=300 depth=8 n=25]. Reports the ranked setups. `facing` (s16, 0=+z) orients the block frame."""
    kw = dict(tok.split("=", 1) for tok in argv if "=" in tok)
    f = lambda k, d: float(kw.get(k, d))
    i = lambda k, d: int(float(kw.get(k, d)))
    start = new_state(pos_x=f("sx", 0.0), pos_z=f("sz", 764.079),
                      pos_y=f("sy", 0.0), facing=i("facing", 0))
    tx, tz = f("tx", start.pos_x), f("tz", 1500.0)
    cat = default_catalog()
    print(f"target=({tx:.4f}, {tz:.4f})  tol={f('tol',5.0)}  catalog=[{', '.join(b.name for b in cat)}]")
    setups = find_setups(start, tx, tz, catalog=cat, tol=f("tol", 5.0),
                         max_frames=i("maxf", 300), max_depth=i("depth", 8),
                         max_results=i("n", 25))
    if not setups:
        print("  (no setups within tolerance -- widen tol / raise depth,maxf, or set facing= so a hop "
              "reaches the target; forward-axis targets need the turn/roll/crawl blocks, still pending)")
    for r in setups:
        print(_fmt(r))
    return setups


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
