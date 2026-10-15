#!/usr/bin/env python3
"""Decisive test: does the SIM reward the neutral-boost + ESS-pump tech at cruise?

Fixed-N max-DISTANCE DP (keep farthest -x per sig each layer, full actions incl pumps),
compared to pure ESS over the same N, at an OSCILLATING cruise seed vs the STROBE seed.
If pumps cover noticeably more distance at the oscillating seed but not the strobe, the
model captures the tech (and the min-frames A* heuristic was hiding it). Forward-rank
prune (NOT the speed-biased _hcost) so the neutral-primary branch isn't penalised."""
import sys, math
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S
from tww_sim.swim.optimize import sig


def maxdist_dp(v, anim, air, N, frontier=4000, allow_pump=True):
    seed = S.SwimState(v=v, anim=anim, air=air); seed._entry_tax = False
    gen = [(0.0, seed, -1, None)]
    gens = [gen]
    for t in range(N):
        buckets = {}
        for pi, (_, st, _, act_in) in enumerate(gen):
            if act_in == 'neu' and not allow_pump:
                allowed = ('neu',)
            else:
                allowed = ('ess', 'chg', 'neu')
            for act in allowed:
                c = st.clone(); c.step(act)
                k = sig(c); fwd = -c.x
                j = buckets.get(k)
                if j is None or fwd > j[0]:
                    buckets[k] = (fwd, c, pi, act)
        ranked = sorted(buckets.values(), key=lambda b: -b[0])[:frontier]
        gens.append(ranked); gen = ranked
    best_i = max(range(len(gen)), key=lambda i: gen[i][0])
    # backtrack actions
    acts = []; i = best_i
    for tt in range(len(gens) - 1, 0, -1):
        _, _, pi, act = gens[tt][i]; acts.append(act); i = pi
    acts.reverse()
    return gen[best_i][0], gen[best_i][1], acts


def pure(action, v, anim, air, N):
    st = S.SwimState(v=v, anim=anim, air=air); st._entry_tax = False
    for _ in range(N):
        st.step(action)
    return -st.x, st.v


if __name__ == '__main__':
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    for v, tag in [(-2000.0, 'oscillate'), (-1600.0, 'STROBE'), (-1200.0, 'oscillate')]:
        de, ve = pure('ess', v, 18.148, 900, N)
        dpump, stp, acts = maxdist_dp(v, 18.148, 900, N, allow_pump=True)
        dno, stn, _ = maxdist_dp(v, 18.148, 900, N, allow_pump=False)
        nn = acts.count('neu'); ne = acts.count('ess'); nc = acts.count('chg')
        print(f'v={v} [{tag}] N={N}: pureESS_dist={de:.0f}(endv{ve:.0f})  '
              f'maxdist_nopump={dno:.0f}  maxdist_PUMP={dpump:.0f}(endv{stp.v:.0f})  '
              f'pump_gain_vs_ESS={dpump-de:+.0f} ({100*(dpump-de)/de:+.2f}%)')
        # pump taper check: neu-fraction in first vs second half
        h = len(acts) // 2
        f1 = acts[:h].count('neu'); f2 = acts[h:].count('neu')
        print(f'        plan: {ne} ess / {nn} neu / {nc} chg; neu 1st-half={f1} 2nd-half={f2}')
