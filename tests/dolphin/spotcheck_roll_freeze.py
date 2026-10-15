"""Live spot-check of the ROLL-approach C-up FREEZE (reach_freeze(roll=True)) -- confirms the frozen
pos_z matches the sim's freeze_pos.z BYTE-FOR-BYTE (0 ULP) for reachable on-axis targets.

The roll approach (start crawl + chained forward rolls @26 + short walk tail + C-up) rests ~15-30 frames
BELOW the pure full-up walk floor, and the roll's anim reset makes the freeze analytic. Its plan `seq`
carries the A button (0x100) on each roll's press frame -- 3-tuples (sx, sy, buttons) -- so this driver
injects buttons (rolls are already 0-ULP-injectable via advanceseq; see run_land_tests roll cases).

CRITICAL -- seed the planner from the LIVE anchor pos_z: the default LandState rounds pos_z to 764.079,
but the anchor is at 764.0791015625 (2 ULP). A seed mismatch shifts the freeze by 1 ULP (the sim is 0-ULP
vs live when seeded correctly -- root-caused 2026-07-05j). CAVEAT: on-axis +z only, below the wall at
pos_z ~= 2932.43 (the sim has no collision). Some exact targets need a k=5 start (slow solve); pick
reachable ones. Requires Dolphin with twwgz booted; loads land_flatwalk@twwgz.sav.

Usage:
  python spotcheck_roll_freeze.py                 # default: 2222.2 2345.678 (fast, k<=4)
  python spotcheck_roll_freeze.py 1900 2500 [kmax]
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
from tww_sim.land.land import LandState
from tww_sim.land.plan_land import reach_freeze, FREEZE_LATENCY

ANCHOR = resolve_anchor("land_flatwalk@twwgz")
READS = ["link_state", "potential_speed", "pos_x", "pos_z", "shape_angle_y", "travel_angle",
         "csangle", "anim_frame"]


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _read(h, m):
    return {k: D.read_named(h, m, k) for k in READS}


def _el(sx, sy, buttons=0, substickY=0, triggerL=0):
    return {"stickX": sx, "stickY": sy, "substickX": 128, "substickY": substickY,
            "buttons": buttons, "triggerL": triggerL, "frames": 1}


def spotcheck(tz, kmax=5, cups=6, hold=4, roll_speed_min=26.0):
    """Plan (roll=True) + live-drive a freeze at reachable on-axis z=tz. Returns True iff 0 ULP + pos_x~0.
    Also holds `hold` frames after the lock to confirm the freeze stays byte-stable. `roll_speed_min` < 26
    engages the partial-tuning-roll DENSIFIER (a k<=3 fast solve for targets full-only can't crack that
    low) -- its plans carry partial forward sticks + A, all advanceseq-injectable like the full rolls."""
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace("\\", "/")})
    h, m = D.attach()
    s = _read(h, m)
    seed = LandState(pos_z=s["pos_z"], facing=int(s["shape_angle_y"]), travel=int(s["travel_angle"]),
                     csangle=int(s["csangle"]), state=int(s["link_state"]),
                     nspeed=s["potential_speed"], idle_frame=s["anim_frame"])
    r = reach_freeze(seed, seed.pos_x, tz, roll=True, kmax=kmax, roll_speed_min=roll_speed_min)
    if r is None or "rolls" not in r:
        print(f"SKIP z={tz:<7.1f} no roll hit within k<={kmax} (fell back)")
        return None
    prefix = r["seq"][:-FREEZE_LATENCY]                 # 3-tuples (sx, sy, buttons)
    sim_fz = r["freeze_pos"][1]

    # approach = prefix[:-1] (buttons injected); cancel = halfL(prefix[-1]) + neutral+C-up.
    for sx, sy, b in prefix[:-1]:
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [_el(sx, sy, buttons=b)]})
    px, py, pb = prefix[-1]
    tail = [_el(px, py, buttons=pb, triggerL=100)] + [_el(128, 128, substickY=255) for _ in range(cups)]
    frozen = None
    for e in tail:
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [e]})
        h, m = D.attach(); t = _read(h, m)
        if int(t["link_state"]) == 1 and frozen is None:
            frozen = t
    # hold to confirm the freeze stays put
    stable = True
    end = frozen if frozen is not None else t
    for _ in range(hold):
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [_el(128, 128)]})
        h, m = D.attach(); t = _read(h, m)
        if bits(t["pos_z"]) != bits(end["pos_z"]):
            stable = False
    live_fz, live_x = end["pos_z"], end["pos_x"]
    ulp = abs(bits(live_fz) - bits(sim_fz))
    ok = (ulp == 0) and abs(live_x) < 1e-4 and stable
    tuned = " tuned" if r.get("tuned") else ""
    print(f"{'PASS' if ok else 'FAIL'} z={tz:<8.2f} sim {sim_fz!r} (0x{bits(sim_fz):08x}) / "
          f"live {live_fz!r} (0x{bits(live_fz):08x})  {ulp} ULP  pos_x={live_x:.5f}  held={stable}"
          f"  [{r['n_frames']}f: {r['rolls']} rolls{tuned} + {r['tail']} tail + {r['start_frames']} start]")
    return ok


def main():
    # Optional: pass `rmin=<float>` anywhere to engage the densifier (partial tuning rolls, roll speed >=
    # rmin). Default 26 = full-only. Trailing 1-digit int = kmax.
    args = sys.argv[1:]
    kmax = 5
    roll_speed_min = 26.0
    rest = []
    for a in args:
        if a.startswith("rmin="):
            roll_speed_min = float(a[5:])
        else:
            rest.append(a)
    args = rest
    if args and args[-1].isdigit() and float(args[-1]) < 10:
        kmax = int(args[-1]); args = args[:-1]
    targets = [float(x) for x in args] or [2222.2, 2345.678]
    res = [spotcheck(tz, kmax=kmax, roll_speed_min=roll_speed_min) for tz in targets]
    graded = [x for x in res if x is not None]
    npass = sum(graded)
    print(f"\n{npass} passed (0 ULP), {len(graded) - npass} failed, {len(res) - len(graded)} skipped")
    sys.exit(0 if graded and npass == len(graded) else 1)


if __name__ == "__main__":
    main()
