"""play_sticks.py -- watchable land-walk DTM playback, a thin wrapper over run_dtm.

The single playback path lives in run_dtm (all the relaunch / playmovie / anchor-loaded readiness /
read-at-exhaustion gotchas). This just calls it with the land readiness gate and watch=True so the
movie visibly plays on screen, then verifies the end position. It exists only as a convenience name
for "watch Link walk"; `python run_dtm.py ready=land watch=1 ...` does the same thing.

Default input = the first land walk: C-stick full DOWN (free cam) every frame; hold UP for `up`
frames, then neutral for `neut` (accelerate -> cruise -> decelerate -> stop). Frame-perfect movie
playback (no advanceseq pipe jitter).

Usage:
  python play_sticks.py [anchor=land_flatwalk@twwgz] [up=30] [neut=15] [expect_pos_z=1095.42]
"""
import os, sys

_rb = os.path.dirname(os.path.abspath(__file__))  # >>> repo bootstrap: locate tww_sim/ + ../tools/
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path: sys.path.append(_tb)
from harness.dtm.run_dtm import run_dtm, land_ready, land_walk_sticks


def main():
    o = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    anchor = o.get("anchor", "land_flatwalk@twwgz")
    up = int(o.get("up", 30))
    neut = int(o.get("neut", 15))

    # Only compare if the caller supplies a target; idle Link oscillates between link_state 4/5,
    # so don't assert an end state -- just report it (the printed line shows pos + link_state).
    expected = {}
    if "expect_pos_z" in o: expected["pos_z"] = float(o["expect_pos_z"])
    if "expect_pos_x" in o: expected["pos_x"] = float(o["expect_pos_x"])

    print(f"=== play_sticks: land_walk ({up} up + {neut} neut), anchor={anchor} ===")
    run_dtm(land_walk_sticks(up, neut), expected or None,
            anchor=anchor, ready=land_ready, watch=True,
            out=os.path.join(_rb, "_generated", "land_walk.dtm"),
            pos_tol=float(o.get("pos_tol", "1.0")))


if __name__ == "__main__":
    main()
