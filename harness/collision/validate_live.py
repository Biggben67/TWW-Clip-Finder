"""Live validator: sim (harness.collision.seam_model) vs the running game, by position-hacking.

For each (initial, end) pair it replicates the two-step swept workflow that produces a seam clip:
  1. hack Link's debug pos (0x803D78FC xyz) to `initial`, advance a few neutral frames to settle
     (so the game carries the settled pos as pm_old_pos),
  2. hack to `end`, advance a few frames,
  3. clip == the final pos stays at `end` (drift < 1 u); block == collision pushed Link back.
Then compares to predict_clip fed the SAME live-settled old_pos.

Requires a running Dolphin with the GanonL seam savestate in slot 1. Target the instance with
DOLPHIN_PID (see ../tools/DOLPHIN_CONTROL.md). Read-only apart from the pos hack + savestate reload.

    DOLPHIN_PID=<pid> python -m harness.collision.validate_live [N]

Result on GZLJ01 2026-07-06: 24/24 live cases agree (20-row boundary sweep + 4 offline-miss rows);
port matches the game bit-for-bit whenever fed the game's actual old_pos.
"""
import os, sys, struct, subprocess

_TOOLS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools")  # speedrunning/tools
sys.path.insert(0, os.path.abspath(_TOOLS))
import dolphin_mem as dm  # noqa: E402
from harness.collision.seam_model import predict_clip  # noqa: E402

XA, YA, ZA = 0x803D78FC, 0x803D7900, 0x803D7904
_TSV = os.path.join(os.path.dirname(__file__), "..", "..", "_generated",
                    "grandstaircase_clip_solutions.tsv")


def _cli(*a):
    return subprocess.run([sys.executable, os.path.join(os.path.abspath(_TOOLS), "dolphin_mem.py"), *a],
                          capture_output=True, text=True, env=os.environ).stdout.strip()


def _rf(a):
    h, m = dm.attach(); return struct.unpack(">f", dm.read_bytes(h, m, a, 4))[0]


def _wf(a, v):
    h, m = dm.attach(); dm.write_bytes(h, m, a, struct.pack(">f", v))


def live_clip(initial, end, settle_frames=4, watch_frames=3):
    """Drive the game; return (clipped_bool, settled_initial_xz, final_y)."""
    _cli("loadstate", "1")
    y0 = _rf(YA)
    _wf(XA, initial[0]); _wf(YA, y0); _wf(ZA, initial[1])
    for _ in range(settle_frames):
        _cli("advancewith", "stickX=128", "stickY=128", "frames=1")
    sx, sy, sz = _rf(XA), _rf(YA), _rf(ZA)
    _wf(XA, end[0]); _wf(YA, sy); _wf(ZA, end[1])
    for _ in range(watch_frames):
        _cli("advancewith", "stickX=128", "stickY=128", "frames=1")
    fx, fz = _rf(XA), _rf(ZA)
    drift = ((fx - end[0]) ** 2 + (fz - end[1]) ** 2) ** 0.5
    return drift < 1.0, (sx, sz), sy


def _parse(s):
    s = s.strip(); return float(s.replace(",", ".")) if s else None


def main(n=20):
    rows = []
    with open(_TSV) as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            v = [_parse(x) for x in p[:4]]
            if None in v:
                continue
            rows.append(((v[0], v[1]), (v[2], v[3])))
    idxs = [int(i * (len(rows) - 1) / (n - 1)) for i in range(n)]
    agree = liveclip = 0
    for j in idxs:
        ini, end = rows[j]
        lc, settled, sy = live_clip(ini, end)
        pc, _ = predict_clip(settled, end, y=sy)   # feed the game's ACTUAL settled old_pos
        liveclip += lc; agree += (lc == pc)
        print(f"row{j:5d} live={'CLIP' if lc else 'block'} port={'CLIP' if pc else 'block'} "
              f"{'OK' if lc == pc else 'X'}")
    print(f"\nlive clips {liveclip}/{n}  agree {agree}/{n}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
