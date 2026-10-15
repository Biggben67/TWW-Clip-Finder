"""Drive Dolphin to replay a plan N times for screen capture.

Each take: loadstate 10 (snaps Link to the cold-start slate), one neutral frame,
write air=900 + potential_speed=0, then one race-free advanceseq of the whole plan
so Link visibly swims the route. Prints the live net distance per take.

Usage: python play_pump.py [seq=ab_synced_seq.txt] [runs=3] [slot=10]
"""
import sys, math
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


def take(seq, acts, slot):
    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1})
    h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    x0 = D.read_named(h, m, "link_x"); z0 = D.read_named(h, m, "link_z")
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    x1 = D.read_named(h, m, "link_x"); z1 = D.read_named(h, m, "link_z")
    return math.hypot(x1 - x0, z1 - z0)


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    seqfile = o.get('seq', 'ab_synced_seq.txt')
    runs = int(o.get('runs', '3'))
    slot = int(o.get('slot', '10'))
    acts = A.expand(open(seqfile).read())
    seq = A.acts_to_seq(acts)
    print(f"Replaying {seqfile} ({len(acts)} frames) x{runs} from slot {slot}\n")
    for i in range(1, runs + 1):
        net = take(seq, acts, slot)
        print(f"  take {i}/{runs}: live net = {net:.0f} units  (target 200000)")
    D.control_pipe_quiet("clearinput")
    print("\ndone.")


if __name__ == "__main__":
    main()
