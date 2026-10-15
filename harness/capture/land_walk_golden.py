"""land_walk_golden.py - capture the live land-walk golden arc for the offline speedF regression.

Writes tests/golden/land_walk_speedf.csv with per-frame (f, ns, msd, speedF, pos_z) over the
walk_run seq from land_flatwalk@twwgz, plus the anchor's idle FREEB frame in a header comment.
The offline regression (tests/test_land.py) feeds (ns, msd) into tww_sim.core.anim.foot_speedf and
asserts speedF matches this golden, and runs the full LandState walk and asserts pos_z tracks it.

These are DERIVED scalars (speed/position), not keyframe data -- safe to commit, like the stick
tables. Re-run only after a DELIBERATE change to the walk model. DEV tool (needs Dolphin + twwgz).
"""
import os, sys, struct
# >>> repo bootstrap: find repo root (marker pyproject.toml) so this runs uninstalled from the root.
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(os.path.join(_d, "pyproject.toml")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)
_tools = os.path.join(os.path.dirname(_d), "tools")      # locate tools/
if os.path.isdir(_tools) and _tools not in sys.path:
    sys.path.append(_tools)
# <<< repo bootstrap
import dolphin_mem as dm
from harness.dtm.run_dtm import resolve_anchor

def main():
    h, mem1 = dm.attach()
    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    idle_frame = rf(0x2F64)
    seed_pos_z = rf(0x24)  # pos_z; but read via named to be safe
    seed_pos_z = dm.read_named(h, mem1, "pos_z")

    UP = {"stickX": 128, "stickY": 255, "substickX": 128, "substickY": 0, "buttons": 0}
    NEUT = {"stickX": 128, "stickY": 128, "substickX": 128, "substickY": 0, "buttons": 0}
    seq = [UP]*30 + [NEUT]*20

    rows = []
    for inp in seq:
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        rows.append((rf(0x34E4), rf(0x34D8), rf(0x17C), dm.read_named(h, mem1, "pos_z")))

    here = os.path.dirname(os.path.abspath(__file__))
    rb = here
    while rb != os.path.dirname(rb) and not os.path.exists(os.path.join(rb, 'pyproject.toml')):
        rb = os.path.dirname(rb)
    out = os.path.join(rb, 'tests', 'golden', 'land_walk_speedf.csv')
    with open(out, 'w') as f:
        f.write("# land_flatwalk@twwgz walk_run golden: 30 up + 20 neutral (free cam).\n")
        f.write("# seed_pos_z=%.6f idle_frame=%.3f\n" % (seed_pos_z, idle_frame))
        f.write("f,ns,msd,speedF,pos_z\n")
        for i, (ns, msd, spF, pz) in enumerate(rows, 1):
            f.write("%d,%.7g,%.7g,%.7g,%.7g\n" % (i, ns, msd, spF, pz))
    print("wrote %s (%d frames); seed_pos_z=%.4f idle_frame=%.1f end_pos_z=%.4f" % (
        out, len(rows), seed_pos_z, idle_frame, rows[-1][3]))

if __name__ == "__main__":
    main()
