"""Characterize the lone-neu pump re-entry timing across a whole swim, race-free.

For each lone-neu (a 'neu' with non-neu neighbors), measure the LIVE wait-duration
(consecutive state-54 frames after the exit before re-entry to 55) and log the regime
vars at the exit frame: air, anim, stick_distance, mDirection. Goal: find what flips
the wait from 1 to 2 frames (the bug2 pump-transition timing, ess-pumps memory).

Each probe = one race-free advanceseq prefix replay from the slate (no per-frame
advancewith -> no dropped inputs). 3 probes per pump (exit, +1, +2). Slow but reliable.

Usage: python scan_pumps.py [seq=test_pumptrans_seq.txt] [slot=10] [out=scan_pumps.txt]
Writes one line per pump to <out>, flushed, so progress is readable while running.
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
from tww_sim.swim import actions as A
from harness import live as L

D.NAMED_ADDRS['mdir'] = {'base': 0x803AD860, 'offsets': [0x33E0], 'type': 'u8'}


def main():
    opts = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    slot = int(opts.get('slot', '10'))
    seqfile = opts.get('seq', 'test_pumptrans_seq.txt')
    outpath = opts.get('out', 'scan_pumps.txt')
    acts = A.expand(open(seqfile).read())
    seq = A.acts_to_seq(acts)
    N = len(acts)

    lone = [i + 1 for i in range(1, N - 1)
            if acts[i] == 'neu' and acts[i - 1] != 'neu' and acts[i + 1] != 'neu']

    def state_at(k):
        D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
        D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                             "substickY": 0, "frames": 1}); h, m = D.attach()
        L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
        if k > 0:
            D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq[:k]})
        return (D.read_named(h, m, "link_state"), D.read_named(h, m, "air"),
                D.read_named(h, m, "anim_frame"), D.read_named(h, m, "stick_distance"),
                D.read_named(h, m, "mdir"), D.read_named(h, m, "potential_speed"))

    out = open(outpath, "w")
    hdr = f"# lone-neu pumps in {seqfile}: {len(lone)} pumps (frames {lone[:3]}...{lone[-3:]})"
    print(hdr); out.write(hdr + "\n"); out.flush()
    hdr2 = "# pump@neu  prevact  exitF  wait  air  anim     stickD   mDir   v"
    print(hdr2); out.write(hdr2 + "\n"); out.flush()

    for n in lone:
        # exit lands at n+1 (first state 54); count consecutive 54s up to 3
        st1 = state_at(n + 1)
        if st1[0] != 54:
            line = f"  neu@{n:<4} {acts[n-2]:4} exit@{n+1} NO-EXIT st={st1[0]}"
            print(line); out.write(line + "\n"); out.flush(); continue
        st2 = state_at(n + 2)
        wait = 1 if st2[0] == 55 else (2 if state_at(n + 3)[0] == 55 else 3)
        _, air, anim, sd, md, v = st1
        line = (f"  neu@{n:<4} {acts[n-2]:4} exit@{n+1} wait={wait}  air={air} "
                f"anim={anim:8.4f} sd={sd:.4f} dir={md} v={v:.2f}")
        print(line); out.write(line + "\n"); out.flush()

    out.close()
    print(f"\nDONE -> {outpath}")


if __name__ == "__main__":
    main()
