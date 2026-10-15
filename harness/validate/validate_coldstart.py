"""validate_coldstart.py - bit-exact gate for the LOGGED-mRate cold-start.

Reproduces the 3 run_tests baselines (cold-start 3k, 4-pump, 8-pump) LIVE via advanceseq,
seeded run_tests-style PLUS the logged seed mRate, and compares the final state to
ColdStartSwimState (swim_coldstart.py). Target: dv ~= 0 AND dan ~= 0 (bit-exact), unlike
run_tests' base SwimState which fails the anim at the current slate's controller phase.

Does NOT modify run_tests.py or superswim_sim.py. New file.

  python validate_coldstart.py            # the 3 baselines
  python validate_coldstart.py only=pump_seq.txt
"""
import sys, struct
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import sim as S
from tww_sim.swim.coldstart import ColdStartSwimState
from tww_sim.swim.actions import expand, acts_to_seq, animdiff
from harness.live import wnamed

SUITE = [
    ("plan3k_exact_seq.txt", "cold-start 3k"),
    ("pump_seq.txt",         "4-pump"),
    ("pump_seq8.txt",        "8-pump"),
]


def run_one(seqfile, slot, tol):
    acts = expand(open(seqfile).read())
    seq = acts_to_seq(acts)

    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1})
    h, m = D.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    mr0 = D.read_named(h, m, "move0_mrate")               # the logged controller rate

    sim = ColdStartSwimState(v=v0, anim=anim0, air=air0, mrate=mr0)
    sim.state = st0; sim._entry_tax = False
    for a in acts:
        sim.step(a)

    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    vl = D.read_named(h, m, "potential_speed"); anl = D.read_named(h, m, "anim_frame")
    airl = D.read_named(h, m, "air"); stl = D.read_named(h, m, "link_state")

    cyc = 26.0 if stl == 54 else 23.0
    dv = vl - sim.v
    dan = animdiff(anl, sim.anim, cyc)
    air_ok = (airl == sim.air)
    passed = abs(dv) <= tol and dan <= tol and stl == sim.state and air_ok
    return dict(frames=len(acts), passed=passed, air_ok=air_ok, mr0=mr0,
                vl=vl, vs=sim.v, dv=dv, anl=anl, ans=sim.anim, dan=dan,
                airl=airl, airs=sim.air, stl=stl, sts=sim.state)


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, v = tok.partition('='); opts[k] = v
    slot = int(opts.get('slot', '10'))
    tol = float(opts.get('tol', '0.02'))
    only = opts.get('only')
    suite = [t for t in SUITE if only is None or t[0] == only]

    print(f"COLD-START (logged-mRate) BIT-EXACT GATE  (slot {slot}, tol {tol})")
    n_pass = n_fail = 0
    for seqfile, label in suite:
        try:
            r = run_one(seqfile, slot, tol)
        except Exception as e:
            print(f"ERROR {label:<14} {seqfile}: {e}"); n_fail += 1; continue
        tag = "PASS " if r["passed"] else "FAIL "
        n_pass += r["passed"]; n_fail += (not r["passed"])
        print(f"{tag} {label:<14} {r['frames']:>4}f  mRate0={r['mr0']:.6f}  "
              f"dv={r['dv']:+.5f} dan={r['dan']:.5f}  "
              f"v {r['vl']:.4f}/{r['vs']:.4f} anim {r['anl']:.4f}/{r['ans']:.4f} "
              f"air {r['airl']}/{r['airs']} st {r['stl']}/{r['sts']}")
    D.control_pipe_quiet("clearinput")
    print(f"---\n{n_pass}/{n_pass+n_fail} cold-start baselines bit-exact")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
