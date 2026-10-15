"""Sub-frame check: can ESS pumps in the neutral tail cross dest FRACTIONALLY earlier
than pure neutral, even if the integer frame count ties?

Method: from the 555-plan neutral handoff, compute per frame F the MAX forward progress
reachable by ANY {ess,neu} sequence (forward-DP, dominance by sig, large frontier) =
the 'envelope' M[F]. Pure neutral gives Pn[F]. No action can move more than |v| in a
frame and neutral moves exactly |v|, so the test is whether holding speed (ESS) ever lets
cumulative progress overtake neutral within the tail. Continuous arrival to dest =
(F-1) + (dest - prog[F-1]) / step[F]. Envelope arrival is the EARLIEST any sequence can
arrive (optimistic upper bound for pumps); if neutral ties it, pumps save 0 sub-frames.

Usage: python partial_frame_check.py [prefix=ab_synced_seq.txt] [dest=200000] [front=120000]
"""
import sys
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S
from tww_sim.swim import plan as P            # noqa (keeps sig import path consistent)
from tww_sim.swim.optimize import sig
from tww_sim.swim import actions as A


def handoff(prefix_file):
    acts = A.expand(open(prefix_file).read())
    i = len(acts)
    while i > 0 and acts[i - 1] == 'neu':
        i -= 1
    H = S.SwimState(v=0.0, anim=0.06392288208007812, air=900)
    H.state = 54; H._entry_tax = False
    for a in acts[:i]:
        H.step(a)
    return i, H


def arrival(prog, dest):
    for F in range(1, len(prog)):
        if prog[F] >= dest:
            return (F - 1) + (dest - prog[F - 1]) / (prog[F] - prog[F - 1]), F
    return None, None


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    pf = o.get('prefix', 'ab_synced_seq.txt')
    dest = float(o.get('dest', '200000'))
    front = int(o.get('front', '120000'))
    N = int(o.get('N', '60'))

    K, H = handoff(pf)
    print(f"handoff frame {K}: v={H.v:.2f} anim={H.anim:.2f} air={H.air} "
          f"progress={-H.x:.1f} remaining={dest-(-H.x):.1f}\n")

    # pure neutral trajectory
    s = H.clone(); Pn = [-s.x]
    for _ in range(N):
        s.step('neu'); Pn.append(-s.x)

    # max-forward envelope over {ess,neu} (pump rules: both actions always allowed)
    cur = {sig(H): (H.clone(), -H.x)}
    Mf = [-H.x]
    maxbucket = 1
    for _ in range(N):
        nxt = {}
        for st, _fwd in cur.values():
            for act in ('ess', 'neu'):
                c = st.clone(); c.step(act)
                k = sig(c); fc = -c.x
                if k not in nxt or fc > nxt[k][1]:
                    nxt[k] = (c, fc)
        maxbucket = max(maxbucket, len(nxt))
        items = sorted(nxt.values(), key=lambda t: -t[1])[:front]
        cur = {sig(t[0]): t for t in items}
        Mf.append(max(t[1] for t in items))

    an, Fn = arrival(Pn, dest)
    am, Fm = arrival(Mf, dest)
    print(f"frontier max bucket/layer = {maxbucket}  (front cap = {front})")
    print(f"pure-neutral continuous arrival : {an:.4f} frames (crosses in frame {Fn})")
    print(f"envelope (best any ess/neu seq) : {am:.4f} frames (crosses in frame {Fm})")
    print(f"sub-frame saving from pumps (optimistic upper bound): {an-am:+.4f} frames\n")

    print(f"{'F':>4} {'neutral_prog':>13} {'envelope_max':>13} {'gap(env-neu)':>13}")
    for F in range(max(0, Fn - 8), min(len(Pn), Fn + 2)):
        print(f"{F:>4} {Pn[F]:13.2f} {Mf[F]:13.2f} {Mf[F]-Pn[F]:+13.4f}")

    if abs(an - am) < 1e-6:
        print("\n=> Pure neutral IS the max-forward envelope at every frame: "
              "ESS pumps save 0 sub-frames (they can only arrive later).")


if __name__ == '__main__':
    main()
