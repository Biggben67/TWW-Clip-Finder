"""Phase-2 multi-solution live filter: fixed build + pumped cruise candidates.

Mirrors validate_plans.py (the 'try equal-frame solutions until one syncs' strategy)
but for the TWO-PHASE plan. The BUILD is fixed (pump-free by construction -- you can't
neutral-dip while charging from cold), so we take the build prefix verbatim from a
no-pump Phase-1 plan, then plan ONLY the cruise+dash WITH pumps from the build handoff
and live-filter the equal-frame arrival candidates.

For each candidate the live plan is `build_prefix + cruise_candidate`; we replay it once
via a race-free advanceseq from the slot-10 cold start, read final position (net forward
progress) + end state, and keep the first candidate that both reaches dest live and whose
sim end-state matches live (v/anim/air/state). Candidates ranked fewest-pump-cycles first
(fewest chaotic bug#2 transitions => most likely to sync).

The cruise->dash boundary is NOT bounded from Phase 1 -- only the BUILD is fixed; the DP
searches the whole cruise+dash with pumps (see superswim-phase-strategy memory).

Usage:
  python cruise_pump_validate.py [prefix=ab_nopump300k_seq.txt] [dest=300000]
        [max_frontier=2000] [pump_chg=0] [maxtests=40] [tol=0.01] [slot=10]
        [maxpumps=N] [out=cruise_pump_synced300k_seq.txt]
"""
import sys
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import sim as S
from tww_sim.swim import plan as P
from tww_sim.swim import actions as A
from harness import live as L
from harness.validate import validate_plans as V
from harness.search import cruise_pump_search as C


def main():
    o = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); o[k] = val
    prefix = o.get('prefix', 'ab_nopump300k_seq.txt')
    dest = float(o.get('dest', '300000'))
    slot = int(o.get('slot', '10'))
    pump_chg = o.get('pump_chg', '0') != '0'
    max_frontier = int(o.get('max_frontier', '2000'))
    maxtests = int(o.get('maxtests', '40'))
    tol = float(o.get('tol', '0.01'))
    maxpumps = int(o['maxpumps']) if 'maxpumps' in o else None
    out = o.get('out', 'cruise_pump_synced300k_seq.txt')

    # fixed build prefix (pump-free) from the no-pump Phase-1 plan
    acts, be, H = C.build_handoff(prefix)
    build = acts[:be]
    print(f"build (point of cruise) = {be} frames (FIXED); Phase-1 total = {len(acts)}")
    print(f"cruise handoff: v={H.v:.2f} anim={H.anim:.4f} air={H.air} state={H.state} "
          f"progress={-H.x:.1f} remaining={dest-(-H.x):.1f}")

    # cold-start sim seed, identical to the live setup (loadstate, neutral, air=900, v=0)
    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1}); h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    sim_seed = S.SwimState(v=v0, anim=anim0, air=air0); sim_seed.state = st0
    sim_seed._entry_tax = False
    print(f"cold start: v={v0:.4f} anim={anim0:.6f} air={air0} state={st0}")

    # Phase-2: search cruise+dash WITH pumps from the build handoff
    print(f"\nplanning cruise dest={dest:.0f} allow_pump=True pump_chg={pump_chg} "
          f"max_frontier={max_frontier} max_pumps={maxpumps} ...")
    res = P.plan_min_frames(dest, H.v, H.anim, H.air, seed_state=H,
                            actions=('ess', 'chg', 'neu'), max_frontier=max_frontier,
                            allow_pump=True, pump_chg=pump_chg, verbose=False,
                            max_pumps=maxpumps)
    fr = res['frames']
    if fr is None:
        print("planner did not reach dest within cap"); return
    arrival = res.get('arrival', [])
    cands = [a for (_fwd, _st, a) in arrival] or [res['actions']]
    seen = set(); uniq = []
    for a in cands:
        key = tuple(a)
        if key not in seen:
            seen.add(key); uniq.append(list(a))
    uniq.sort(key=lambda a: (V.pump_cycles(a), a.count('chg')))
    total = be + fr
    print(f"cruise min frames={fr} -> TOTAL {total}; {len(uniq)} distinct equal-frame "
          f"cruise candidates; testing up to {maxtests} (fewest pump-cycles first)\n")

    print(" #  pumps chg  sim_net   live_net  reach%  end v/anim/air/st (live)        sync")
    best = None
    for idx, cruise in enumerate(uniq[:maxtests]):
        full = build + cruise
        s_end, sim_net = V.net_of(full, sim_seed)
        net, vl, anl, airl, stl = V.live_replay(full, slot)
        reach = 100.0 * net / dest
        reached = net >= dest * (1 - tol)
        cyc = 26.0 if stl == 54 else 23.0
        synced = (reached and abs(vl - s_end.v) <= 0.05
                  and A.animdiff(anl, s_end.anim, cyc) <= 0.05
                  and airl == s_end.air and stl == s_end.state)
        tag = "SYNC" if synced else ("reach" if reached else "")
        print(f"{idx:>2}  {V.pump_cycles(cruise):>4} {cruise.count('chg'):>4} "
              f"{sim_net:8.0f}  {net:8.0f}  {reach:5.1f}  "
              f"v={vl:8.2f} an={anl:5.2f} air={airl} st={stl}   {tag}")
        if synced and best is None:
            best = full
            print(f"   -> FIRST SYNC at candidate {idx}; stopping.")
            break
        if reached and best is None:
            best = full          # reached-but-not-bit-exact fallback; keep searching
    D.control_pipe_quiet("clearinput")

    if best is not None:
        with open(out, 'w') as f:
            f.write(';'.join(f"{a},1" for a in best) + "\n")
        print(f"\nwrote best plan ({len(best)} frames total, "
              f"{V.pump_cycles(best)} pump-cycles) -> {out}")
    else:
        print("\nNO candidate reached dest live. Raise max_frontier/maxtests.")


if __name__ == '__main__':
    main()
