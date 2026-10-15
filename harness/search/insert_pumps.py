"""Re-test the claim (superswim_plan.py:276) that greedily INSERTING pumps into the
pump-free optimum never improves it.

Method (pure sim, fast): plan the no-pump baseline (charge-build + ESS cruise + terminal
neutral dash). Then GREEDILY insert NEUTRAL-BOOST pumps into the ESS cruise -- flip a run
of `ess` to `neu` (the cruise-pump tech, superswim-cruise-pumps memory: a neutral frame
moves drag-free = full |v|, faster than a drag'd ESS frame, at the cost of -2 speed decay
vs -1/6; on a favorable anim phase it nets forward). After each flip the whole plan is
re-simulated (speed/anim change downstream) and we measure frames-to-`dest`. If ANY
insertion reaches dest in FEWER frames than the baseline, the claim is wrong.

Usage: python insert_pumps.py [dest=50000] [Lmax=6] [out=inserted_seq.txt] [verbose=1]
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
from tww_sim.swim import plan as P


REFILL = False


def frames_to_dest(acts, dest):
    """Simulate acts from the cold-start seed; return 1-based frame where -x first
    reaches dest, or None."""
    s = P._seed_for(0.0, 0.0639, 900, entry_tax=False, cold_start=True)
    if REFILL:
        s._refill_air = True
    for i, a in enumerate(acts, 1):
        s.step(a)
        if -s.x >= dest:
            return i
    return None


def main():
    global REFILL
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    dest = float(o.get('dest', '50000'))
    Lmax = int(o.get('Lmax', '6'))
    verbose = o.get('verbose', '1') != '0'
    REFILL = o.get('refill', '0') != '0'
    out = o.get('out', 'inserted_seq.txt')

    base = P.plan_min_frames(dest, 0.0, 0.0639, 900, allow_pump=False,
                             cold_start=True, verbose=False, max_frontier=2000,
                             refill_air=REFILL)
    base_frames = base['frames']
    # padded action list so a faster plan (fewer frames to dest) is representable
    best = list(base['actions']) + ['neu'] * 60
    best_f = frames_to_dest(best, dest)
    ess_n = base['actions'].count('ess')
    print(f"baseline: {base_frames} frames ({ess_n} ess in cruise); "
          f"re-sim reaches dest in {best_f} (sanity)\n")

    pumps = 0
    while True:
        cand_best = None       # (frames, acts, p, L)
        for p in range(1, len(best)):
            if best[p] != 'ess':
                continue
            for L in range(1, Lmax + 1):
                if p + L > len(best) or any(best[p + k] != 'ess' for k in range(L)):
                    break                          # only flip a run of pure ess
                cand = list(best)
                for k in range(L):
                    cand[p + k] = 'neu'            # neutral-boost pump
                f = frames_to_dest(cand, dest)
                if f is not None and (cand_best is None or f < cand_best[0]):
                    cand_best = (f, cand, p, L)
        if cand_best is None or cand_best[0] >= best_f:
            break
        best_f, best, p, L = cand_best
        pumps += 1
        if verbose:
            print(f"  +boost #{pumps} at frame {p} len {L} -> {best_f} frames")

    print(f"\nBEST: {best_f} frames vs baseline {base_frames}  => "
          + (f"IMPROVED by {base_frames - best_f} frame(s) -- CLAIM IS WRONG"
             if best_f < base_frames else "no improvement -- claim holds (in sim)"))
    if best_f < base_frames:
        full = best[:best_f]
        with open(out, 'w') as f:
            f.write(';'.join(f"{a},1" for a in full) + "\n")
        npump = sum(1 for i in range(1, len(full)) if full[i] != 'neu' and full[i-1] == 'neu')
        print(f"wrote {len(full)}-frame plan ({npump} pump-cycles) -> {out}")


if __name__ == "__main__":
    main()
