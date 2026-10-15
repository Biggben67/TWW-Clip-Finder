"""Regression suite for the Dolphin superswim runner + physics sim.

Replays each baseline action sequence LIVE via `advanceseq` (race-free, ONE pipe
call per test) from the slot-10 cold start, then compares the FINAL game state
(potential_speed, anim_frame, air, link_state) against a `tww_sim.swim.SwimState`
seeded identically. One compact line per test, no per-frame dump -> token-cheap.
Dolphin command reference: ../../tools/DOLPHIN_CONTROL.md (the single source of truth).

Why end-state and not per-frame: the game is deterministic, so any per-frame
physics regression propagates into the final speed/anim. A single advanceseq is
race-free (DOLPHIN_CONTROL.md), unlike a per-frame advancewith loop which can drop
inputs under dense charge density. To locate WHERE a failing test diverges, fall
back to verify_state.py (it prints the per-frame table around the first mismatch).

Requires Dolphin running with twwgz.iso booted. The cold-start slate is the vendored
fixtures/savestate/superswim_coldstart_slate.s10, loaded by PATH via the pipe's `loadfile`
(no dependence on Dolphin's own StateSaves / slot 10). See DOLPHIN_CONTROL.md.

Usage:
  python run_tests.py                      # full suite (loads the vendored slate)
  python run_tests.py quick=1              # skip the long 200k target
  python run_tests.py only=pump_seq.txt    # one seq
  python run_tests.py tol=0.02 slot=10     # override: load Dolphin save slot 10 instead

Exit code 0 iff every non-xfail baseline matches (xfail mismatches don't fail the run).
"""
import struct, math
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
from harness import dolphin_env as ENV

FIXTURES = os.path.join(_rb, 'fixtures')  # code-referenced baseline seqs live here
# Cold-start slate, loaded BY PATH via `loadfile`. It dumps copyrighted game RAM so is NOT shipped:
# set TWWGZ_SLATE / dolphin.local.json, or pass slot=<n>. See tests/dolphin/README + dolphin_env.
SLATE = ENV.slate()

# Anchor cruise_cold@twwgz.sav's OWN logged move0_mrate (its cold start != the slate's 0.5472,
# same display anim). Seed with THIS when validating vs the anchor's DTM truth. See README.md.
ANCHOR_MRATE = 0.5

# (seqfile, label, xfail, note[, dtm_truth]). xfail flips to PASS when fixed = the gate. dtm_truth
# (opt 5th elem): sim compared vs clean-DTM truth not advanceseq (run_dtm_truth); see README.md.
# PASS baselines are LOCKED clean-DTM syncs (sim vs recorded truth from cruise_cold@twwgz.sav via
# movie playback, seeded ANCHOR_MRATE). IMMUTABLE -- do not edit values/seq/golden (see README.md).
SUITE = [
    ("plan3k_exact_seq.txt",   "cold-start 3k", False, "clean-DTM sync",
     {"v": -80.6842, "anim": 3.4416, "air": 832, "state": 54}),
    ("pump_seq.txt",           "4-pump",        False, "clean-DTM sync",
     {"v": -102.3921, "anim": 20.6792, "air": 760, "state": 55}),
    ("pump_seq8.txt",          "8-pump",        False, "clean-DTM sync",
     {"v": -19.6456, "anim": 14.3366, "air": 688, "state": 55}),
    ("test_pumptrans_seq.txt", "pump-transition", False, "clean-DTM sync (dense pump tail)",
     {"v": -775.375, "anim": 0.7674, "air": 475, "state": 55}),
    ("partial_hold77_seq.txt", "bug3 partial hold", False, "clean-DTM sync (uniform-lag fix)",
     {"v": -92.0, "anim": 21.9570, "air": 861, "state": 55}),
    # XFAIL, known-open, still on advanceseq/slate (no clean-DTM anchor yet). See open-questions.md.
    ("plan200k_seq.txt",       "200k target",   True, "post-death anim tail (swim bit-exact)"),
    ("test_lowspeed_seq.txt",  "bug1 v>=0 tail", True, "v>=0 forward-swim gain (setNormalSpeedF)"),
]

# expand / acts_to_seq / animdiff now live in tww_sim.swim.actions; wnamed in harness.live
# (both imported above) so the ~30 scripts that reused them no longer depend on this harness.


def run_dtm_truth(seqfile, dtm_truth, live_dtm):
    """Gate the SIM against a CLEAN-DTM ground truth (movie playback), NOT advanceseq -- advanceseq
    drops polls on dense neu<->ess tails so it is not trustworthy for pump seqs. The sim is seeded
    at the anchor's cold start with the anchor's OWN mrate (ANCHOR_MRATE); it matches dtm_truth
    bit-exact. If live_dtm, ALSO re-run run_dtm live to re-confirm the game still lands on dtm_truth
    (guards the recorded constant). Same result-dict shape as run_one so main() prints it uniformly."""
    from harness.dtm.run_dtm import run_dtm, sticks_from_seq_file, DEFAULT_ANCHOR
    path = seqfile if os.path.exists(seqfile) else os.path.join(FIXTURES, seqfile)
    acts = expand(open(path).read())
    sticks = sticks_from_seq_file(path)

    truth = dict(dtm_truth)
    if live_dtm:
        end = run_dtm(sticks, expected=truth, anchor=DEFAULT_ANCHOR, verbose=True)
        c = end.get("compare", {})
        if not c.get("ok", False):
            print(f"      !! live run_dtm disagrees with recorded dtm_truth "
                  f"(live v={end['potential_speed']:.3f} air={end['air']} st={end['link_state']})")
    # Seed at the anchor cold start with the ANCHOR's mrate (not the slate's) -- the only correct
    # seed for a comparison against the anchor's DTM truth.
    sim = ColdStartSwimState(v=0.0, anim=0.06392288208007812, air=900, mrate=ANCHOR_MRATE)
    sim.state = 54
    sim._entry_tax = False
    for a in acts:
        sim.step(a)

    cyc = 26.0 if truth["state"] == 54 else 23.0
    dv = truth["v"] - sim.v
    dan = animdiff(truth["anim"], sim.anim, cyc)
    air_ok = (truth["air"] == sim.air)
    passed = abs(dv) <= 0.02 and dan <= 0.02 and truth["state"] == sim.state and air_ok
    return {
        "frames": len(acts), "passed": passed, "air_ok": air_ok, "dtm": True,
        "vl": truth["v"], "vs": sim.v, "dv": dv, "anl": truth["anim"], "ans": sim.anim, "dan": dan,
        "airl": truth["air"], "airs": sim.air, "stl": truth["state"], "sts": sim.state,
    }


def run_one(seqfile, slot, tol):
    """Replay seqfile live + sim, compare final state. Returns a result dict.
    Loads the vendored slate by path, or a Dolphin save slot if `slot` is not None."""
    path = seqfile if os.path.exists(seqfile) else os.path.join(FIXTURES, seqfile)
    acts = expand(open(path).read())
    seq = acts_to_seq(acts)

    load = {"action": "load", "slot": slot} if slot is not None else {"action": "load", "path": SLATE}
    D.control_pipe_quiet("savestate", load)
    h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1})
    h, m = D.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    mr0 = D.read_named(h, m, "move0_mrate")  # LOGGED controller rate -> bit-exact cold start

    # Seed the cold-start scramble from the LIVE-LOGGED seed mRate, not the slate-phase-wrong
    # f32(anim+1.0) the base SwimState assumes. The cold-start x598 scramble amplifies a sub-ULP
    # oldframe error ~600x, so anim-only seeding fails the v/anim compare at any slate whose
    # controller phase isn't the canonical 0.0639 (see superswim-554-resolved). ColdStartSwimState
    # corrects ONLY the cold-start oldframe; all other physics are inherited verbatim.
    sim = ColdStartSwimState(v=v0, anim=anim0, air=air0, mrate=mr0); sim.state = st0
    sim._entry_tax = False
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
    return {
        "frames": len(acts), "passed": passed, "air_ok": air_ok,
        "vl": vl, "vs": sim.v, "dv": dv, "anl": anl, "ans": sim.anim, "dan": dan,
        "airl": airl, "airs": sim.air, "stl": stl, "sts": sim.state,
    }


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, v = tok.partition('='); opts[k] = v
    slot = int(opts['slot']) if 'slot' in opts else None  # None => load the slate by path
    tol = float(opts.get('tol', '0.02'))
    only = opts.get('only')
    quick = opts.get('quick') in ('1', 'true', 'yes')
    live_dtm = opts.get('dtm') in ('1', 'true', 'yes')  # dtm=1: re-run run_dtm live for dtm_truth
                                                        # entries (relaunches Dolphin); else offline

    suite = [t for t in SUITE if (only is None or t[0] == only)
             and not (quick and t[2])]
    if not suite:
        print(f"no matching tests (only={only!r})"); sys.exit(2)

    # Warm up Dolphin so this runs from cold in one command (dolphin_env.ensure_running); warmup=0
    # to manage it yourself. Skipped when every selected test is offline (dtm_truth needs no Dolphin).
    needs_dolphin = any(len(t) <= 4 for t in suite) or live_dtm  # run_one/advanceseq or dtm=1
    if opts.get('warmup') not in ('0', 'false', 'no') and needs_dolphin:
        # ready_slate: on a cold boot, wait until this slate actually loads before running
        # advanceseq (else a loadstate at the boot logo screen reads a null player pointer).
        ENV.ensure_running(ready_slate=SLATE if slot is None else None)

    if slot is None and not os.path.exists(SLATE):
        print(f"slate not found: {SLATE}\n"
              "The cold-start slate is not shipped (it dumps copyrighted game RAM). Set TWWGZ_SLATE "
              "to your own slate file, or pass slot=<n> to load a Dolphin save slot.")
        sys.exit(2)

    src = f"slot {slot}" if slot is not None else os.path.basename(SLATE)
    print(f"SUPERSWIM RUNNER REGRESSION  ({src}, tol {tol})")
    n_pass = n_fail = n_xfail = 0
    for entry in suite:
        seqfile, label, xfail, note = entry[:4]
        dtm_truth = entry[4] if len(entry) > 4 else None
        try:
            if dtm_truth is not None:   # bug#2-style: compare sim vs CLEAN-DTM truth, not advanceseq
                r = run_dtm_truth(seqfile, dtm_truth, live_dtm)
            else:
                r = run_one(seqfile, slot, tol)
        except Exception as e:
            print(f"ERROR {label:<14} {seqfile}: {e}"); n_fail += 1; continue
        f = r["frames"]
        if r["passed"]:
            tag = "PASS "; n_pass += 1
            print(f"{tag} {label:<14} {f:>4}f  v={r['vl']:.2f} "
                  f"anim={r['anl']:.2f} air={r['airl']} st={r['stl']}")
        elif xfail:
            tag = "XFAIL"; n_xfail += 1
            print(f"{tag} {label:<14} {f:>4}f  dv={r['dv']:+.3f} dan={r['dan']:.3f} "
                  f"air {r['airl']}/{r['airs']} st {r['stl']}/{r['sts']}  ({note})")
        else:
            tag = "FAIL "; n_fail += 1
            hint = "" if r["air_ok"] else " [air desync = dropped frame; re-run]"
            print(f"{tag} {label:<14} {f:>4}f  dv={r['dv']:+.3f} dan={r['dan']:.3f} "
                  f"air {r['airl']}/{r['airs']} st {r['stl']}/{r['sts']}{hint}")
            print(f"      -> locate: python verify_state.py seq={seqfile}")
    D.control_pipe_quiet("clearinput")

    base = n_pass + n_fail
    print(f"---\n{n_pass}/{base} baselines pass"
          + (f"; {n_xfail} xfail" if n_xfail else ""))
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
