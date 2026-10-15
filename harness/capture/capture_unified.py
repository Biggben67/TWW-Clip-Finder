"""capture_unified.py — capture a full build+cruise+steer run with run_tests-style seeding,
logging per-frame ground truth for the unified predictor. Robust to mid-run Dolphin closes.

Seeding mirrors run_tests.py (so SwimState's cold-start path matches): loadstate; neutral
pre-advance (substickY=0); write air/speed; then drive the per-frame (sx,sy,csx,csy) seq.

seq file lines: sx,sy,csx,csy[,count]   (count default 1).  ; / # comments ok.
Usage: python capture_unified.py <seq> [out=capU.csv] [slot=10] [air=900] [speed=0]
"""
import sys, os, struct, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as dm
from tww_sim.swim import actions as A
from harness import live as L

READS = ["csangle", "facing", "link_state", "potential_speed", "anim_frame", "air", "link_x", "link_z"]
ISO = os.environ.get("TWWGZ_ISO", "twwgz.iso")  # set TWWGZ_ISO to your GZLJ01 image path


def ensure_game():
    s = json.loads(dm.control_pipe_full("status", {}))
    if s.get("state") not in ("paused", "running"):
        dm.control_pipe_full("boot", {"path": ISO, "wait": True})


def parse_seq(path):
    fr = []
    for line in open(path):
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        p = [int(x) for x in line.split(",")]
        n = p[4] if len(p) > 4 else 1
        for _ in range(n):
            fr.append((p[0], p[1], p[2], p[3]))
    return fr


def main():
    seq_file = sys.argv[1]
    opts = dict(t.split("=", 1) for t in sys.argv[2:] if "=" in t)
    out = opts.get("out", "capU.csv"); slot = opts.get("slot", "10")
    frames = parse_seq(seq_file)

    ensure_game()
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    h, m = dm.attach()
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1})
    h, m = dm.attach()
    L.wnamed(h, m, "air", int(opts.get("air", "900")))
    L.wnamed(h, m, "potential_speed", float(opts.get("speed", "0")))

    def snap():
        for _ in range(6):
            try:
                return {nm: dm.read_named(h, m, nm) for nm in READS}
            except OSError:
                _h, _m = dm.attach()
        return {nm: dm.read_named(h, m, nm) for nm in READS}

    rows = []
    prev = snap()
    rows.append({"f": 0, "sx": "", "sy": "", "csx": "", "csy": "", "dx": 0.0, "dz": 0.0, **prev})
    for i, (sx, sy, csx, csy) in enumerate(frames, 1):
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": csx, "substickY": csy, "frames": 1})
        cur = snap()
        rows.append({"f": i, "sx": sx, "sy": sy, "csx": csx, "csy": csy,
                     "dx": cur["link_x"] - prev["link_x"], "dz": cur["link_z"] - prev["link_z"], **cur})
        prev = cur

    cols = ["f", "sx", "sy", "csx", "csy", *READS, "dx", "dz"]
    with open(os.path.join(HERE, out), "w", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"wrote {out}: {len(rows)} rows")
    for r in rows[:1] + rows[-4:]:
        print(f"f{r['f']:>3} cam={r['csangle']} st={r['link_state']} v={r['potential_speed']:.2f} "
              f"anim={r['anim_frame']:.3f} air={r['air']} x={r['link_x']:.1f} z={r['link_z']:.1f}")


if __name__ == "__main__":
    main()
