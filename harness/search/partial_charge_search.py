"""Partial-charge search: let the build planner pick PARTIAL on-axis charge ('chg:<rawY>')
throughout the charge phase, not just full UP/DOWN. Measures BOTH frames saved AND the
frontier cost (the branching-factor blowup we were worried about).

IDEA (user, 2026-06-30): a full charge builds |v| at -3/fr; a partial charge still snaps
(180 flip) but gains <3 via the /54 law (sim.py chg:<rawY>), so it builds speed slower while
shifting the anim trajectory (incr(v,air)). Giving the optimizer the whole continuum of
build rates throughout the charge phase could let it land head-bob phase better for free.
This is the NATIVE-search version (the optimizer chooses partials), unlike partial_postpass
(post-hoc on frozen ESS frames only).

Method: run plan_min_frames cold-start with the baseline action set vs an action set that
adds a small partial-charge palette. Report frames, max frontier, capped layers, wall time.
The palette stays inside the live-validated decay band (offset 18..63 -> rawY 146..191 up,
mirrored down by _chg_stick). NOTE: acts_to_seq does NOT emit 'chg:<rawY>' for live replay --
wire that only if a gain appears here.

Usage: python partial_charge_search.py [dest=20000] [max_frontier=1000]
"""
import sys, time
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim.plan import plan_min_frames

COLD_ANIM = 0.06392288208007812          # live fresh cold-start display anim (golden_harness)

# Partial-charge UP-stroke raw Y, giving build rates ~0.25/0.5/0.75/0.9 of full (md=(off-15)/54).
PARTIAL_CHG = ['chg:156', 'chg:170', 'chg:183', 'chg:191']


def run(dest, actions, max_frontier):
    t0 = time.time()
    r = plan_min_frames(dest, v=0.0, anim=COLD_ANIM, air=900, actions=actions,
                        cold_start=True, entry_tax=False, max_frontier=max_frontier,
                        verbose=False)
    r['_time'] = time.time() - t0
    return r


def report(name, r):
    if r['frames'] is None:
        print(f"{name}: NOT REACHED"); return None
    a = r['actions']
    nfull = a.count('chg')
    npart = sum(1 for x in a if x.startswith('chg:'))
    nneu = a.count('neu')
    ness = len(a) - nfull - npart - nneu
    mxf = max(r['frontier_sizes'])
    ncap = len(r['capped_layers'])
    print(f"{name}: {r['frames']} frames  [{nfull} chg, {npart} partial-chg, {nneu} neu, "
          f"{ness} ess]")
    print(f"    frontier max={mxf}  capped layers={ncap}  time={r['_time']:.1f}s")
    return r['frames']


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    dest = float(o.get('dest', '20000'))
    mf = int(o.get('max_frontier', '1000'))

    print(f"dest={dest:.0f}  max_frontier={mf}\n")
    base = run(dest, ('ess', 'chg', 'neu'), mf)
    bf = report('baseline (ess,chg,neu)', base)

    exp = run(dest, ('ess', 'chg', 'neu') + tuple(PARTIAL_CHG), mf)
    ef = report(f'+partial charge ({len(PARTIAL_CHG)} buckets)', exp)

    if bf is not None and ef is not None:
        print(f"\n=> {bf - ef:+d} frames vs baseline; "
              f"frontier {max(base['frontier_sizes'])} -> {max(exp['frontier_sizes'])}, "
              f"time {base['_time']:.1f}s -> {exp['_time']:.1f}s")
        if ef >= bf:
            print("   No frame gain: partial charge throughout the build does not beat full "
                  "charge + ESS sync. (Building |v| slower never pays back on-axis.)")


if __name__ == '__main__':
    main()
