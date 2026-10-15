"""capture_full.py - capture a FULL cold-start BUILD -> ESS cruise -> camera-steer run live,
run_tests-style seeded, logging the seed mRate0 so swim_predict_full can reproduce it exactly.

Seeding mirrors run_tests / validate_coldstart EXACTLY (so the cold-start scramble matches):
  loadstate <slot> -> neutral pre-advance (substickY=0) -> write air/speed -> read seed
  v0/anim0/air0/st0 AND mRate0(move0_mrate) AND cam0/facing0/x0/z0.

Then drives the input list per-frame (advancewith frames=1; the C-stick passes through for the
steer phase). Per the in-session check (advancewith == advanceseq for the dense 8-pump build),
per-frame advancewith is race-free here for the charge build too, so we get per-frame ground
truth across the whole run in one attach.

The seed row of the CSV carries move0_mrate so swim_predict_full.validate_full uses it.

Usage:
  python capture_full.py <seq_file> [out=cap_full.csv] [slot=10] [speed=0] [air=900]

seq_file lines (csv: sx,sy,csx,csy[,count]; '#'/';' comments, blanks ignored), 0..255 center 128.
"""
import sys, os, struct

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

READS = ["csangle", "facing", "link_state", "potential_speed", "anim_frame", "air",
         "link_x", "link_z", "move0_mrate"]


def parse_seq(path):
    frames = []
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            if not line:
                continue
            p = [x.strip() for x in line.split(",")]
            sx, sy, csx, csy = int(p[0]), int(p[1]), int(p[2]), int(p[3])
            n = int(p[4]) if len(p) > 4 else 1
            frames += [(sx, sy, csx, csy)] * n
    return frames


def wnamed(h, m, name, value):
    e = dm.NAMED_ADDRS[name]; addr = dm.resolve_chain(h, m, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = dm.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    dm.write_bytes(h, m, addr, data)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    seq_file = sys.argv[1]
    opts = {}
    for tok in sys.argv[2:]:
        k, _, v = tok.partition("="); opts[k] = v
    out = opts.get("out", "cap_full.csv")
    slot = int(opts.get("slot", "10"))
    speed = float(opts.get("speed", "0"))
    air = int(opts.get("air", "900"))
    frames = parse_seq(seq_file)

    # run_tests-style seed
    dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot})
    h, m = dm.attach()
    dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                          "substickY": 0, "frames": 1})
    h, m = dm.attach()
    wnamed(h, m, "air", air); wnamed(h, m, "potential_speed", speed)

    def snap():
        return {nm: dm.read_named(h, m, nm) for nm in READS}

    rows = []
    seed = snap()
    rows.append({"f": 0, "sx": "", "sy": "", "csx": "", "csy": "", "dx": 0.0, "dz": 0.0, **seed})
    prev = seed
    for i, (sx, sy, csx, csy) in enumerate(frames, 1):
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": csx, "substickY": csy, "frames": 1})
        cur = snap()
        dx = cur["link_x"] - prev["link_x"]; dz = cur["link_z"] - prev["link_z"]
        rows.append({"f": i, "sx": sx, "sy": sy, "csx": csx, "csy": csy,
                     "dx": dx, "dz": dz, **cur})
        prev = cur
    dm.control_pipe_quiet("clearinput")

    cols = ["f", "sx", "sy", "csx", "csy", *READS, "dx", "dz"]
    with open(os.path.join(HERE, out), "w", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"wrote {out}: {len(rows)} rows ({len(frames)} frames)")
    s = rows[0]
    print(f"SEED: v={s['potential_speed']:.5f} anim={s['anim_frame']:.5f} air={s['air']} "
          f"st={s['link_state']} mRate={s['move0_mrate']:.6f} cam={s['csangle']} fac={s['facing']}")
    for r in rows[-4:]:
        print(f"f{r['f']:>4} cam={r['csangle']} st={r['link_state']} v={r['potential_speed']:.2f} "
              f"anim={r['anim_frame']:.3f} air={r['air']} x={r['link_x']:.1f} z={r['link_z']:.1f}")


if __name__ == "__main__":
    main()
