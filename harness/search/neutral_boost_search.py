"""Exhaustive (uncapped) search for ESS pumps DURING the neutral-boost phase only.

Fix the whole swim up to the neutral boost (build + ESS cruise + reboosts, taken
from the no-pump baseline), then from that exact handoff state run a forward DP over
{ess, neu} with NO frontier cap -> full dominance (exact under sig()'s 0.03-anim /
0.1-v buckets). We compare:
  - pure neutral boost   (allow_pump=False -> the plain drag-free dash)
  - +ESS pumps           (allow_pump=True  -> traditional 'tap ESS while neutral')
and re-run with a FINER sig bucket to prove the frame count isn't a bucket artifact.

Usage: python neutral_boost_search.py [prefix=ab_nopump_seq.txt] [dest=200000]
"""
import sys, math
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S
from tww_sim.swim import plan as P
from tww_sim.swim import optimize as O
from tww_sim.swim import actions as A

def fine_sig(st):
    """Much finer than O.sig (0.005 anim / 0.02 v) to test bucket sensitivity."""
    return (round(st.anim / 0.005), round(st.v / 0.02),
            st._pending_flip, round(st._pending_gain, 1),
            int(round(st.heading / math.pi)) & 1, st._entry_tax,
            st.state, st._pending_state, st._just_released, st._skip_advance)


def handoff(prefix_file):
    acts = A.expand(open(prefix_file).read())
    i = len(acts)
    while i > 0 and acts[i - 1] == 'neu':      # strip trailing neutral dash
        i -= 1
    prefix = acts[:i]
    H = S.SwimState(v=0.0, anim=0.06392288208007812, air=900)
    H.state = 54; H._entry_tax = False
    for a in prefix:
        H.step(a)
    return prefix, H, len(acts)


def search(H, dest, allow_pump, frontier=10**9):
    return P.plan_min_frames(dest, H.v, H.anim, H.air, seed_state=H,
                             actions=('ess', 'neu'), allow_pump=allow_pump,
                             pump_chg=False, max_frontier=frontier, verbose=False)


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    pf = o.get('prefix', 'ab_nopump_seq.txt')
    dest = float(o.get('dest', '200000'))
    frontier = int(o.get('frontier', 10**9))

    prefix, H, total_ref = handoff(pf)
    prog = -H.x
    print(f"prefix (up to neutral boost) = {len(prefix)} frames; reference total = {total_ref}")
    print(f"handoff state: v={H.v:.3f} anim={H.anim:.3f} air={H.air} state={H.state} "
          f"progress={prog:.1f}  remaining={dest-prog:.1f}  (frontier cap={frontier})\n")

    base = search(H, dest, allow_pump=False, frontier=frontier)
    print(f"PURE neutral boost (no pumps): {base['frames']} frames  -> total {len(prefix)+base['frames']}")

    res = search(H, dest, allow_pump=True, frontier=frontier)
    a = res['actions']
    npump = sum(1 for k in range(1, len(a)) if a[k] != 'neu' and a[k-1] == 'neu')
    print(f"+ESS pumps (uncapped DP):      {res['frames']} frames  -> total {len(prefix)+res['frames']}")
    print(f"   frontier max={max(res['frontier_sizes'])}  capped_layers={len(res['capped_layers'])} "
          f"(0 = fully exhaustive, no pruning)")
    print(f"   boost mix: {a.count('ess')} ess(pump), {a.count('neu')} neu, {npump} pump-cycles")
    print(f"   saving vs pure neutral: {base['frames']-res['frames']} frames")

    # robustness: finer sig bucket
    orig = P.sig
    P.sig = fine_sig
    try:
        resf = search(H, dest, allow_pump=True, frontier=frontier)
    finally:
        P.sig = orig
    print(f"\nrobustness (finer 0.005/0.02 sig): {resf['frames']} frames "
          f"(frontier max={max(resf['frontier_sizes'])}) "
          f"-> {'STABLE' if resf['frames']==res['frames'] else 'CHANGED'}")

    if res['frames'] < base['frames']:
        seq = O.seq_string(a)
        print("\nwinning boost seq:", seq)
        full = ';'.join(f"{x},1" for x in (prefix + list(a)))
        open('boost_search_seq.txt', 'w').write(full + "\n")
        print(f"wrote full plan ({len(prefix)+len(a)} frames) -> boost_search_seq.txt")
        print(f"distinct equal-frame boost solutions: {len(res.get('arrival', []))}")
    else:
        print("\n=> Exhaustive search finds NO pump beats the pure neutral boost here.")


if __name__ == '__main__':
    main()
