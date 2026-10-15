"""A/B live replay + measure for the 200k pump-vs-no-pump comparison.

Seeds EXACTLY like run_tests.run_one (loadstate 10, 1 neutral advancewith, write
air=900 + potential_speed=0, read cold start), records link_x/z, advanceseq the
plan, then reports frames, live net Euclidean distance, and the end-state vs the
sim (v/anim/air/state). Race-free single advanceseq.

Usage: python ab_replay.py seq=ab_nopump_seq.txt [slot=10]
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
from tww_sim.swim import sim as S
from tww_sim.swim import actions as A
from harness import live as L


def replay(seqfile, slot):
    acts = A.expand(open(seqfile).read())
    seq = A.acts_to_seq(acts)

    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1})
    h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    x0 = D.read_named(h, m, "link_x"); z0 = D.read_named(h, m, "link_z")

    # sim from identical seed
    sim = S.SwimState(v=v0, anim=anim0, air=air0); sim.state = st0
    sim._entry_tax = False
    for a in acts:
        sim.step(a)

    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    vl = D.read_named(h, m, "potential_speed"); anl = D.read_named(h, m, "anim_frame")
    airl = D.read_named(h, m, "air"); stl = D.read_named(h, m, "link_state")
    xl = D.read_named(h, m, "link_x"); zl = D.read_named(h, m, "link_z")

    net = math.hypot(xl - x0, zl - z0)
    cyc = 26.0 if stl == 54 else 23.0
    dan = A.animdiff(anl, sim.anim, cyc)
    print(f"{seqfile}: {len(acts)} frames")
    print(f"  seed: v={v0:.5f} anim={anim0:.5f} air={air0} state={st0} pos=({x0:.1f},{z0:.1f})")
    print(f"  LIVE net dist = {net:.1f}   sim reached -x = {-sim.x:.1f}")
    print(f"  end live:  v={vl:.3f} anim={anl:.3f} air={airl} state={stl}")
    print(f"  end sim:   v={sim.v:.3f} anim={sim.anim:.3f} air={sim.air} state={sim.state}")
    print(f"  delta:     dv={vl-sim.v:+.3f} dan={dan:.3f} "
          f"air {'OK' if airl==sim.air else f'{airl}/{sim.air}'} "
          f"state {'OK' if stl==sim.state else f'{stl}/{sim.state}'}")
    return len(acts), net, vl, anl, airl, stl, sim


def main():
    opts = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    slot = int(opts.get('slot', '10'))
    replay(opts.get('seq', 'ab_nopump_seq.txt'), slot)
    D.control_pipe_quiet("clearinput")


if __name__ == "__main__":
    main()
