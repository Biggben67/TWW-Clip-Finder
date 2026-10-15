"""Replay a seq driving ONE frame per advancewith call (no batched advanceseq), to test
whether bug#2's dense-region divergence is an advanceseq BATCH-stepping artifact.

If per-frame delivery transitions correctly at the frame where batched advanceseq took an
extra wait frame (test_pumptrans f397: batch=state54, sim=state55), the batch indexing is
the artifact. If it still takes the extra wait, the effect is real.

Usage: python per_frame_drive.py [seq=test_pumptrans_seq.txt] [upto=400] [readfrom=393] [slot=10]
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


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    slot = int(o.get('slot', '10'))
    seqfile = o.get('seq', 'test_pumptrans_seq.txt')
    upto = int(o.get('upto', '400')); readfrom = int(o.get('readfrom', '393'))
    acts = A.expand(open(seqfile).read())
    seq = A.acts_to_seq(acts)

    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
    h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)

    print("  f   act   st   anim       v")
    for k in range(1, upto + 1):
        s = seq[k - 1]
        D.control_pipe_quiet("advancewith", {"stickX": s["stickX"], "stickY": s["stickY"],
                                             "substickY": 0, "frames": 1})
        if k >= readfrom:
            h, m = D.attach()
            st = D.read_named(h, m, "link_state"); an = D.read_named(h, m, "anim_frame")
            v = D.read_named(h, m, "potential_speed")
            print(f"  {k:<4}{acts[k-1]:5} {st:>4} {an:9.4f} {v:9.2f}")
    D.control_pipe_quiet("clearinput")


if __name__ == "__main__":
    main()
