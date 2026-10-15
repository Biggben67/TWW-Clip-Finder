"""Live spot-check of the C-up-cancel FREEZE (reach_freeze) -- confirms the frozen pos_z matches the
sim's freeze_pos.z BYTE-FOR-BYTE (0 ULP) for reachable on-axis targets.

The sim models the freeze as `_freeze_pos` = the walk pos FREEZE_LATENCY(3) neutral steps on. Live
realizes it with the C-up speed cancel: while walking, one half-L frame (ends manual cam) then neutral
stick + C-stick FULL UP, and position LOCKS 3 frames later (link_state -> 1). See
knowledge/mechanics/land-movement.md. The cancel is constructed so the two acting cruise frames deliver
prefix[-2], prefix[-1] (matching the sim's 2-frame INPUT_DELAY):

    LIVE = prefix[:-1] + halfL(stick=prefix[-1], triggerL=100) + (neutral + C-UP full)*K

CAVEAT -- the sim has NO collision, so a plan can silently target past a wall. The land_flatwalk
anchor's +z corridor ends at a WALL at pos_z ~= 2932.43; a target beyond it freezes AT the wall (not
the requested z) and reads as a spurious FAIL. Keep on-axis targets in (764.08, 2932.43) on this anchor.

Usage:
  python spotcheck_freeze.py                 # default reachable targets: 1500 2000 2500
  python spotcheck_freeze.py 1800 2200 2900  # custom on-axis +z targets (all below the wall)
  python spotcheck_freeze.py --min 2000      # the FEWEST-FRAME start-crawl freeze (reach_freeze min_frames)
Requires Dolphin running with twwgz booted (see tests/dolphin/README.md). Loads land_flatwalk@twwgz.sav.

The --min plan is the START-crawl fewest-frame freeze: a few from-rest reduced-magnitude frames then
full cruise + C-up. Its seq has the SAME shape (walk prefix + FREEZE_LATENCY tail) as the robust plan,
so the live cancel below drives it unchanged; it just travels ~+7 over the full-up floor (vs +19..32)
and freezes BIT-EXACTLY (0 ULP). Requires the anchor at REST (the crawl starts from a standstill).
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
READS = ["link_state", "potential_speed", "pos_x", "pos_z", "shape_angle_y",
         "travel_angle", "csangle", "anim_frame"]


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _read(h, m):
    return {k: D.read_named(h, m, k) for k in READS}


def _el(sx, sy, substickY=0, triggerL=0):
    return {"stickX": sx, "stickY": sy, "substickX": 128, "substickY": substickY,
            "buttons": 0, "triggerL": triggerL, "frames": 1}


def spotcheck(tz, cups=6, min_frames=False):
    """Plan + live-drive a freeze at reachable on-axis target z=tz. Returns True iff 0 ULP + pos_x~0.
    `min_frames` selects the fewest-frame START-crawl plan (else the robust slow-approach plan)."""
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace("\\", "/")})
    h, m = D.attach()
    s = _read(h, m)
    seed = LandState(pos_z=s["pos_z"], facing=int(s["shape_angle_y"]), travel=int(s["travel_angle"]),
                     csangle=int(s["csangle"]), state=int(s["link_state"]),
                     nspeed=s["potential_speed"], idle_frame=s["anim_frame"])
    r = reach_freeze(seed, seed.pos_x, tz, min_frames=min_frames)
    prefix = r["seq"][:-FREEZE_LATENCY]
    sim_fz = r["freeze_pos"][1]

    # approach = prefix[:-1] (free cam = C-down); then the cancel, one frame per advanceseq.
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [_el(sx, sy) for sx, sy in prefix[:-1]]})
    px, py = prefix[-1]
    tail = [_el(px, py, triggerL=100)] + [_el(128, 128, substickY=255) for _ in range(cups)]
    frozen = None
    for e in tail:
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": [e]})
        h, m = D.attach()
        t = _read(h, m)
        if int(t["link_state"]) == 1 and frozen is None:
            frozen = t
    end = frozen if frozen is not None else t
    live_fz, live_x = end["pos_z"], end["pos_x"]
    ulp = abs(bits(live_fz) - bits(sim_fz))
    ok = (ulp == 0) and abs(live_x) < 1e-4
    print(f"{'PASS' if ok else 'FAIL'} z={tz:<7.1f} {'[min]' if min_frames else '     '} "
          f"sim {sim_fz!r} (0x{bits(sim_fz):08x}) / "
          f"live {live_fz!r} (0x{bits(live_fz):08x})  {ulp} ULP  pos_x={live_x:.5f}"
          f"  [{len(prefix)}f, dist {r['freeze_dist']:.6f}]")
    return ok


def main():
    args = sys.argv[1:]
    min_frames = "--min" in args
    targets = [float(x) for x in args if x != "--min"] or [1500.0, 2000.0, 2500.0]
    res = [spotcheck(tz, min_frames=min_frames) for tz in targets]
    npass = sum(res)
    print(f"\n{npass} passed (0 ULP), {len(res) - npass} failed")
    sys.exit(0 if npass == len(res) else 1)


if __name__ == "__main__":
    main()
