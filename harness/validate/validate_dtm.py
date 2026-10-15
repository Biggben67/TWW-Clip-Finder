"""Faithful, pipe-artifact-free validator: author a clean DTM for a plan seq, play it
via the movie system, and compare the live endpoint to the SwimState sim.

NOTE: this is the original single-purpose validator (action-seq files, the cold anchor, a
SwimState compare, free-run-to-exhaustion read that races on short movies). For new work
prefer the generalized engine **`harness/dtm/run_dtm.py`** — it takes arbitrary sticks +
expected values, derives the iso from a test-owned anchor's `@<isokey>` name, validates
facing too, and frame-steps short movies deterministically. This file is kept for the
existing cruise_pump300k regression flow.

Why this and not the advanceseq pipe (pt-21): the external pipe's FrameAdvance-listener
jitters SI polls on dense back-to-back dips, slipping inputs (dense cruise_pump300k bled
to ~127k live vs the sim's ~300k). Movie playback flips WantDeterminism on and polls at
the game's NATURAL cadence -- a clean DTM reproduces the sim BIT-EXACT. So a DTM round
trip is the trustworthy live check for dense-pump plans; advanceseq is not.

Flow: (kill+relaunch Dolphin to a stopped game list) -> make_dtm clean cadence ->
copy the cold-start .sav anchor -> playmovie -> wait boot -> play to byte-exhaustion ->
read endpoint -> compare v/anim/air/state to the sim seeded at the same cold start.

The compare is on v/anim/air/state (deterministic, the right yardstick -- same as
run_tests). Net distance is reported as a sanity scalar only (x/z are wave-affected).

Assumes a COLD-START-from-slot-10 plan (v0, air900, state54) using the shared anchor
cruise_pump300k_rec.dtm.sav; seed=1 leading neutral poll matches that anchor. The sim is
seeded at COLD_ANIM (the post-seed-neutral cold-start anim baked into that .sav).

Usage: python validate_dtm.py seq=cruise_pump300k_seq.txt [game=<iso>]
       [anchor=cruise_pump300k_rec.dtm.sav] [tol=0.02] [norelaunch=0] [bootsecs=150]
"""
import sys, os, time, math, json, shutil, subprocess
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
from harness.dtm import make_dtm as M

X0, Z0 = 42222.0, -158781.0                 # slot-10 slate origin
COLD_ANIM = 0.06392288208007812             # cold-start anim in cruise_pump300k_rec.dtm.sav
HERE = os.path.dirname(os.path.abspath(__file__))
# Dolphin-Zelda-TAS-Edition is a sibling of this repo under speedrunning/ (override via env).
EXE = os.environ.get("DOLPHIN_EXE", os.path.join(
    os.path.dirname(_rb), "Dolphin-Zelda-TAS-Edition", "Binary", "x64", "Release", "Dolphin.exe"))
DEFAULT_ISO = os.environ.get("TWWGZ_ISO", "twwgz.iso")  # set TWWGZ_ISO to your GZLJ01 image path


def status():
    try:
        return json.loads(D.control_pipe_quiet("status"))
    except Exception:
        return {}


def relaunch():
    subprocess.run(["taskkill", "/F", "/IM", "Dolphin.exe"],
                   capture_output=True)
    time.sleep(1.0)
    subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(30):
        if status().get("ok"):
            print("Dolphin relaunched (game list)")
            return
        time.sleep(1.0)
    raise SystemExit("Dolphin did not come up after relaunch")


def sim_endpoint(seqfile):
    acts = A.expand(open(seqfile).read())
    sim = S.SwimState(v=0.0, anim=COLD_ANIM, air=900); sim.state = 54
    sim._entry_tax = False
    for a in acts:
        sim.step(a)
    return sim, len(acts)


def play_and_read(dtm, game, bootsecs, playsecs):
    D.control_pipe_quiet("playmovie", {"path": dtm, "game": game})
    print(f"playmovie {os.path.basename(dtm)}")
    t0 = time.time(); booted = False
    while time.time() - t0 < bootsecs:
        s = status()
        if s.get("playing"):
            try:
                h, m = D.attach()
                if D.read_named(h, m, "link_state") in (54, 55) and D.read_named(h, m, "air") >= 800:
                    booted = True
                    print(f"booted after {time.time()-t0:.1f}s")
                    break
            except BaseException:
                pass
        time.sleep(1)
    if not booted:
        raise SystemExit("never reached booted cold start")
    D.control_pipe_quiet("resume")           # defensive; movie usually auto-runs
    t1 = time.time(); ended = False
    while time.time() - t1 < playsecs:
        if not status().get("playing"):
            ended = True; break
        time.sleep(0.3)
    D.control_pipe_quiet("pause")
    h, m = D.attach()
    end = {k: D.read_named(h, m, k) for k in
           ("potential_speed", "anim_frame", "air", "link_state", "link_x", "link_z")}
    end["net"] = math.hypot(end["link_x"] - X0, end["link_z"] - Z0)
    end["ended"] = ended
    return end


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    seqfile = o.get('seq', 'cruise_pump300k_seq.txt')
    game = o.get('game', DEFAULT_ISO).replace('\\', '/')
    anchor = o.get('anchor', 'cruise_pump300k_rec.dtm.sav')
    tol = float(o.get('tol', '0.02'))
    bootsecs = int(o.get('bootsecs', '150'))
    playsecs = int(o.get('playsecs', '180'))
    norelaunch = o.get('norelaunch') in ('1', 'true', 'yes')

    out = os.path.join(HERE, seqfile.rsplit('.', 1)[0] + '_clean.dtm')
    info = M.build_dtm(os.path.join(HERE, seqfile), out)
    shutil.copyfile(os.path.join(HERE, anchor), out + '.sav')
    print(f"{seqfile}: {info['frames']} frames -> {os.path.basename(out)} "
          f"({info['polls']} polls, {info['rows']} rows)")

    sim, nframes = sim_endpoint(os.path.join(HERE, seqfile))

    if not norelaunch:
        relaunch()
    end = play_and_read(out, game, bootsecs, playsecs)

    cyc = 26.0 if end["link_state"] == 54 else 23.0
    dv = end["potential_speed"] - sim.v
    dan = A.animdiff(end["anim_frame"], sim.anim, cyc)
    air_ok = (end["air"] == sim.air)
    ok = abs(dv) <= tol and dan <= tol and end["link_state"] == sim.state and air_ok
    tag = "PASS " if ok else "FAIL "
    print(f"--- {seqfile} ({nframes} frames) ---")
    print(f"  SIM : v={sim.v:.3f} anim={sim.anim:.4f} air={sim.air} st={sim.state}")
    print(f"  LIVE: v={end['potential_speed']:.3f} anim={end['anim_frame']:.4f} "
          f"air={end['air']} st={end['link_state']}  net={end['net']:.0f}"
          + ("" if end["ended"] else "  [TIMEOUT-still-playing]"))
    print(f"{tag} dv={dv:+.3f} dan={dan:.3f} air {end['air']}/{sim.air} "
          f"st {end['link_state']}/{sim.state}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
