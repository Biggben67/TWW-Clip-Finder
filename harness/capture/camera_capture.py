"""camera_capture.py — drive a per-frame (main-stick + C-stick) input sequence on the
LIVE game from a savestate and log ground-truth state to a CSV, one row per frame.

This is the reusable validator for the camera/position predictor. Unlike dolphin_mem's
`seq` (which forces substickY=0 / frozen camera), this passes the C-stick through so we
can probe and validate camera rotation + the resulting curved swim path.

Attaches ONCE and reads memory natively each frame (fast). Drives input over the pipe
with advancewith frames=1 (fine for cruise/steer; for DENSE charge alternation use a DTM
instead — the pt-21 pipe-jitter artifact only affects back-to-back dips).

Usage:
  python camera_capture.py <seq_file> [out=cap.csv] [slot=10] [speed=] [air=]

seq_file lines (";"/"#" comments and blanks ignored), each:
    stickX,stickY,substickX,substickY[,count]
  count defaults to 1. Values 0..255, center 128.
Optional speed=/air= write potential_speed/air once after loadstate (test-point seeding).
"""
import sys, os, subprocess

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

READS = ["csangle", "cam_yaw", "cam_target", "facing", "shape_angle_y", "travel_angle",
         "link_state", "potential_speed", "anim_frame", "air", "link_x", "link_z"]
# cam_yaw/cam_target = dCamera_c manual-cam internals (csangle == (cam_yaw+0x8000)&0xFFFF); with
# travel_angle/shape_angle_y this shows a csangle move as C-stick pan vs bumpCheck wall collision.


def parse_seq(path):
    frames = []
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            sx, sy, csx, csy = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            n = int(parts[4]) if len(parts) > 4 else 1
            for _ in range(n):
                frames.append((sx, sy, csx, csy))
    return frames


def mem_cli(*args):
    """One-shot dolphin_mem.py call (for loadstate/writename which need their own logic)."""
    subprocess.run([sys.executable, os.path.join(HERE, "dolphin_mem.py"), *args],
                   check=True, capture_output=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    seq_file = sys.argv[1]
    opts = {}
    for tok in sys.argv[2:]:
        k, _, v = tok.partition("=")
        opts[k] = v
    out = opts.get("out", "cap.csv")
    slot = opts.get("slot", "10")
    frames = parse_seq(seq_file)

    mem_cli("loadstate", slot)
    if "speed" in opts:
        mem_cli("writename", "potential_speed", opts["speed"])
    if "air" in opts:
        mem_cli("writename", "air", opts["air"])

    h, mem1 = dm.attach()

    def snap():
        return {nm: dm.read_named(h, mem1, nm) for nm in READS}

    rows = []
    prev = snap()
    rows.append({"f": 0, "sx": "", "sy": "", "csx": "", "csy": "",
                 "dx": 0.0, "dz": 0.0, **prev})
    for i, (sx, sy, csx, csy) in enumerate(frames, 1):
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": csx, "substickY": csy,
                                              "frames": 1})
        cur = snap()
        dx = cur["link_x"] - prev["link_x"]
        dz = cur["link_z"] - prev["link_z"]
        rows.append({"f": i, "sx": sx, "sy": sy, "csx": csx, "csy": csy,
                     "dx": dx, "dz": dz, **cur})
        prev = cur

    cols = ["f", "sx", "sy", "csx", "csy", *READS, "dx", "dz"]
    with open(os.path.join(HERE, out), "w", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"wrote {out}: {len(rows)} rows ({len(frames)} frames)")
    # compact tail
    for r in rows[:1] + rows[-6:]:
        print(f"f{r['f']:>3} cam={r['csangle']} fac={r['facing']} st={r['link_state']} "
              f"v={r['potential_speed']:.2f} anim={r['anim_frame']:.3f} air={r['air']} "
              f"x={r['link_x']:.1f} z={r['link_z']:.1f} dx={r['dx']:.2f} dz={r['dz']:.2f}")


if __name__ == "__main__":
    main()
