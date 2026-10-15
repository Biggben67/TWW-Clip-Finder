"""Live gate for the INPUT-DRIVEN subjectivity freeze -- the whole cruise -> C-up freeze -> B-cancel ->
re-walk cycle driven by a RAW controller stream, byte-for-byte (0 ULP) vs Dolphin, every frame.

LandState.step() models the B button + C-up cancel gesture itself (no enter_freeze/hold_freeze/
resume_walk API), so a plan is just an input sequence and the SAME el(...) stream drives sim + live.
This is the decisive regression for that model. See knowledge/mechanics/land-movement.md (subjectivity
freeze) and knowledge/model/land-planner.md.

Latency model (all validated 0 ULP here):
  * C-up routes through the CAMERA -> subjectivity engages 3 frames after the C-up poll (2-frame stick
    delay + 1 camera frame); the last MOVE frame still decelerates.
  * B/A trigger or L held ends the freeze (checkSubjectEnd); position stays frozen (WAITS anim advances).
  * a forward stick, once the freeze has ended, re-walks with the WAITS phase carried (m34C3=2).

Usage:
  python spotcheck_subj_inputdriven.py            # fused native LandCore
  python spotcheck_subj_inputdriven.py --python   # pure-Python land.py step
Requires Dolphin running with twwgz booted (see tests/dolphin/README.md). Loads land_flatwalk@twwgz.sav.
"""
import os, sys, struct  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from harness.dtm.run_dtm import resolve_anchor
from tww_sim.land.land import LandState, FREE_WAIT

ANCHOR = resolve_anchor("land_flatwalk@twwgz")


def bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


# substickY BYTE: 128 = C-stick CENTER, 255 = C-UP (freeze entry), 0 = C-DOWN (0x2000 exit). All
# non-C-up frames use csy=128 so the modeled exit is UNAMBIGUOUS (a stray C-DOWN is a separate exit).
def el(sx, sy, csy=128, tl=0, btn=0):
    return {"stickX": sx, "stickY": sy, "substickX": 128, "substickY": csy,
            "buttons": btn, "triggerL": tl, "frames": 1}


def make(ncruise, ncup, nB, ngap, nwalk):
    """cruise -> C-up freeze -> B-cancel -> re-walk. `halfL` re-issues the approach stick while ending
    the manual cam; C-up = neutral main + csy=255; B = neutral main + BTN_B (neutral C-stick)."""
    return ([el(128, 255)] * ncruise + [el(128, 255, tl=100)]
            + [el(128, 128, csy=255)] * ncup + [el(128, 128, btn=0x200)] * nB
            + [el(128, 128)] * ngap
            + [el(128, 255, btn=0x200 if i == 0 else 0) for i in range(nwalk)])


def make_cdown():
    """C-DOWN exit: after the freeze, push C-stick DOWN (csy=0). The camera reports 0x2000 only past
    the SUBJ_VIEW_IN floor (~frame 13); then (release, brief gap) a forward stick re-walks with the
    carried phase. NOTE: holding forward *simultaneously through* the C-DOWN exit leaves a ~0.15u
    residual (a procMove_init-vs-body 1-frame subtlety), so the tech separates the exit from the walk."""
    return ([el(128, 255)] * 22 + [el(128, 255, tl=100)]
            + [el(128, 128, csy=255)] * 6                 # C-up freeze
            + [el(128, 128, csy=0)] * 10                  # C-DOWN (neutral main) -> floored 0x2000 exit
            + [el(128, 128)] * 3                          # brief neutral gap (release C-down)
            + [el(128, 255) for _ in range(8)])           # forward -> re-walk with carried phase


def make_heldB():
    """FIAT GUARD: B held from the FIRST C-up frame -- its mItemTrigger edge fires BEFORE
    procSubjectivity's body runs, so checkSubjectEnd misses it and the freeze NEVER exits (live). A
    forward stick is then held: the sim must STAY FROZEN (no re-walk), not resume on a stale held B."""
    return ([el(128, 255)] * 22 + [el(128, 255, tl=100)]
            + [el(128, 128, csy=255, btn=0x200)] * 6      # C-up + B together (B edge pre-lock)
            + [el(128, 128, btn=0x200)] * 4               # keep B held, drop C-up (neutral C-stick)
            + [el(128, 255)] * 8)                         # forward stick -- must NOT re-walk


def make_reentry():
    """RE-ENTRY GUARD: press B while STILL holding C-up -> the exit fires but C-up re-requests the
    freeze (re-enter cup-cam); with C-up never cleanly released + no fresh trigger, a forward stick
    must NOT re-walk (live: stuck frozen). The sim must stay frozen the whole time."""
    return ([el(128, 255)] * 22 + [el(128, 255, tl=100)]
            + [el(128, 128, csy=255)] * 6                 # C-up freeze
            + [el(128, 128, csy=255, btn=0x200)] * 3      # B while holding C-up -> exits then re-enters
            + [el(128, 255)] * 10)                        # release C-up + forward -> stuck frozen


def load():
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace("\\", "/")})
    h, m = D.attach()
    return D.read_named(h, m, "pos_z")


def spotcheck(name, stream, native):
    pz0 = load()
    live = []
    for e in stream:
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [e]})
        h, m = D.attach()
        live.append(D.read_named(h, m, "pos_z"))
    s = LandState(native=native, foot_native=native, pos_z=pz0, facing=0, travel=0,
                  csangle=0, state=FREE_WAIT, nspeed=0.0, idle_frame=70.0)
    worst = 0
    for e, lp in zip(stream, live):
        s.step(e["stickX"], e["stickY"], buttons=e["buttons"], triggerL=e["triggerL"],
               csx=e["substickX"], csy=e["substickY"])
        worst = max(worst, abs(bits(lp) - bits(s.pos_z)))
    ok = worst == 0
    print(f"{'PASS' if ok else 'FAIL'} {name:14} frames={len(stream):>3}  "
          f"final live={live[-1]:.4f} sim={s.pos_z:.4f}  WORST={worst} ULP")
    return ok


def main():
    native = "--python" not in sys.argv
    cases = [("calibration", make(22, 6, 4, 0, 8)),
             ("short-cruise", make(10, 5, 3, 2, 8)),
             ("long-hold", make(30, 8, 6, 0, 7)),
             ("tight-B", make(18, 4, 2, 3, 6)),
             ("cdown-exit", make_cdown()),
             ("held-B-fiat", make_heldB()),
             ("reentry-fiat", make_reentry())]
    print(f"(sim path: {'fused native LandCore' if native else 'pure-Python land.py step'})")
    res = [spotcheck(n, st, native) for n, st in cases]
    npass = sum(res)
    print(f"\n{npass} passed (0 ULP), {len(res) - npass} failed")
    sys.exit(0 if npass == len(res) else 1)


if __name__ == "__main__":
    main()
