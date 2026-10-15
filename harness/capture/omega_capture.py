"""omega_capture.py - capture the EXACT camera-rate command omega_cmd(csx,csy) for a set of
C-stick (csx,csy) values, live from Dolphin, cached in omega_table.csv.

WHY: the camera yaw is csangle = (cam_yaw + 0x8000) & 0xFFFF, where cam_yaw chases an
accumulator cam_target via cam_yaw += int((s16)(cam_target - cam_yaw) / 2) and
    cam_target += omega_cmd(csx, csy)     (1-frame input lag)
(verified bit-exact, see camera_exact.py / knowledge/mechanics/camera.md). The original
camera_exact omega_cmd was a function of csx ONLY (with a csy<=64 'freeze'); that is WRONG
for arbitrary csy. Live RE shows omega depends on the WHOLE C-stick vector: csy modulates the
horizontal rate (e.g. csx=255: csy in [32,220] -> 546, but csy=255 -> 199, csy=0 -> 173; the
csy<=64 'freeze=0' was never real). So omega_cmd is a 2-D function captured here exactly.

HOW: omega_cmd is a pure function of (csx,csy). We loadstate, hold each C-stick with a NEUTRAL
main stick (facing constant -> no confound) for ~11 frames so the k=0.5 omega ramp fully
settles, and read the steady d(cam_target)/frame -- the exact per-frame omega. Verified ==
the live per-frame omega in cap_randcharge/cap_camchaos (0 cells differ). Cached so any new
capture's C-sticks get their exact omega once; re-runs only capture uncached cells.

Usage:
  python omega_capture.py <capture_csv> [<capture_csv> ...]
  python omega_capture.py --sticks 187,84 170,196 ...
"""
import sys, os, csv, struct

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

TABLE = os.path.join(HERE, "omega_table.csv")
READS = ["cam_target"]


def load_table():
    t = {}
    if os.path.exists(TABLE):
        for r in csv.DictReader(open(TABLE)):
            t[(int(r["csx"]), int(r["csy"]))] = int(r["omega"])
    return t


def save_table(t):
    with open(TABLE, "w", newline="") as f:
        f.write("csx,csy,omega\n")
        for (csx, csy), o in sorted(t.items()):
            f.write(f"{csx},{csy},{o}\n")


def wnamed(h, m, name, value):
    e = dm.NAMED_ADDRS[name]; addr = dm.resolve_chain(h, m, e["base"], e["offsets"])
    tp = e["type"]; fmt, sz = dm.FMT[tp]
    data = (struct.pack(fmt, float(value)) if tp in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    dm.write_bytes(h, m, addr, data)


def _d16(a, b):
    x = (a - b) & 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def capture(sticks, slot=10, hold=11):
    """sticks: iterable of (csx,csy). Returns {(csx,csy): omega}. Fresh loadstate per stick so
    cam_target starts at rest; hold the stick `hold` frames (omega ramp settles) and read the
    steady d(cam_target)."""
    want = [s for s in dict.fromkeys((int(a), int(b)) for a, b in sticks)]
    out = {}
    for (csx, csy) in want:
        dm.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = dm.attach()
        dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                              "substickY": 0, "frames": 1}); h, m = dm.attach()
        wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", -700.0)
        prev = dm.read_named(h, m, "cam_target"); last = 0
        for _ in range(hold):
            dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                                  "substickX": csx, "substickY": csy, "frames": 1})
            cur = dm.read_named(h, m, "cam_target")
            last = _d16(cur, prev); prev = cur
        out[(csx, csy)] = last
    dm.control_pipe_quiet("clearinput")
    return out


def sticks_from_csv(path):
    rows = list(csv.DictReader(open(path)))
    return [(int(r["csx"]), int(r["csy"])) for r in rows[1:] if r["csx"] != ""]


def main():
    args = sys.argv[1:]
    sticks = []
    if args and args[0] == "--sticks":
        for tok in args[1:]:
            a, b = tok.split(","); sticks.append((int(a), int(b)))
    else:
        for p in args:
            sticks += sticks_from_csv(p)
    if not sticks:
        print(__doc__); sys.exit(1)
    table = load_table()
    need = [s for s in dict.fromkeys(sticks) if s not in table]
    print(f"{len(set(sticks))} unique C-sticks; {len(need)} need live capture")
    if need:
        got = capture(need)
        table.update(got)
        save_table(table)
        print(f"captured {len(got)} cells -> {TABLE} (now {len(table)} total)")
    else:
        print("all cached already")


if __name__ == "__main__":
    main()
