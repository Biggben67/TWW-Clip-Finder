"""Leg 1 of the DTM experiment: record a superswim plan into a .dtm (savestate-anchored)
and report the recording-run endpoint vs the sim.

Seeds the cold start exactly like ab_replay/run_tests (loadstate slot, 1 neutral, write
air=900/v=0), then `record start` (companion .sav captured at this frame = the cold start),
advanceseq the plan (race-free), `record stop` -> writes <dtm> + <dtm>.sav.

If the recording reaches dest bit-exact to the sim, the advanceseq-during-record path did
NOT drop for this plan and we have a clean, replayable artifact. If it falls short, the
record leg dropped in the cruise (-> use the synthesized make_dtm.py movie instead).

Usage: python dtm_record.py seq=cruise_pump300k_seq.txt [dtm=cruise_pump300k_rec.dtm] [slot=10]
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


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    seqfile = o.get('seq', 'cruise_pump300k_seq.txt')
    dtm = o.get('dtm', seqfile.rsplit('.', 1)[0] + '_rec.dtm').replace('\\', '/')
    slot = int(o.get('slot', '10'))

    acts = A.expand(open(seqfile).read())
    seq = A.acts_to_seq(acts)

    # seed cold start (identical to ab_replay)
    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1}); h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    x0 = D.read_named(h, m, "link_x"); z0 = D.read_named(h, m, "link_z")
    print(f"seed: v={v0:.5f} anim={anim0:.6f} air={air0} state={st0}  ({len(acts)} frames)")

    sim = S.SwimState(v=v0, anim=anim0, air=air0); sim.state = st0
    sim._entry_tax = False
    for a in acts:
        sim.step(a)

    # record the plan
    print(f"record start -> {dtm}")
    D.control_pipe_quiet("recordstart", {"path": dtm}); h, m = D.attach()
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq}); h, m = D.attach()
    vl = D.read_named(h, m, "potential_speed"); anl = D.read_named(h, m, "anim_frame")
    airl = D.read_named(h, m, "air"); stl = D.read_named(h, m, "link_state")
    xl = D.read_named(h, m, "link_x"); zl = D.read_named(h, m, "link_z")
    D.control_pipe_quiet("recordstop", {"path": dtm})

    net = math.hypot(xl - x0, zl - z0)
    cyc = 26.0 if stl == 54 else 23.0
    dan = A.animdiff(anl, sim.anim, cyc)
    print(f"  LIVE net dist = {net:.1f}   sim reached -x = {-sim.x:.1f}")
    print(f"  end live:  v={vl:.3f} anim={anl:.3f} air={airl} state={stl}")
    print(f"  end sim:   v={sim.v:.3f} anim={sim.anim:.3f} air={sim.air} state={sim.state}")
    print(f"  delta:     dv={vl-sim.v:+.3f} dan={dan:.3f} "
          f"air {'OK' if airl==sim.air else f'{airl}/{sim.air}'} "
          f"state {'OK' if stl==sim.state else f'{stl}/{sim.state}'}")
    D.control_pipe_quiet("clearinput")


if __name__ == "__main__":
    main()
