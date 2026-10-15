"""Live-validate scanner clips on a running Dolphin: for each clippable seam the scanner reports,
drive the game to ``old`` and step the one clip frame to ``new``, and confirm Link ends up at ``new``
(a real clip) rather than being shoved back (a block).

CLEAN PLACEMENT (critical — see DOLPHIN_CONTROL.md "Clean-placement teleport"). Naively hacking the
debug pos to ``old`` and advancing leaves ``pm_old_pos`` at Link's ORIGINAL savestate position; the
next CrrPos then sweeps that long line and, if it crosses a wall, snaps Link ~100 u away — a false
BLOCK. So we write BOTH player class-pos triples (``[base]+0x10c`` and ``+0x120``) AND the debug
``link_x/y/z`` to ``old`` first, making the placement sweep zero-length. Then set ``pm_pos = new`` and
advance exactly one neutral frame = the clip frame. clip == final pos stays at ``new`` (drift < 1 u).

Also feed full f32 precision (a razor clip flips on sub-0.001 u; never round the coords).

    DOLPHIN_PID=<pid> python -m harness.collision.validate_clips box=xmin,xmax,ymin,ymax,zmin,zmax
    DOLPHIN_PID=<pid> python -m harness.collision.validate_clips slot=1 box=...    # loadstate first
"""
import os
import struct
import subprocess
import sys

_TOOLS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools")
sys.path.insert(0, os.path.abspath(_TOOLS))
import dolphin_mem as dm  # noqa: E402
from harness.collision.seam_scan import read_region_tris  # noqa: E402
from harness.collision.seam_clip_check import scan_region  # noqa: E402

XA, YA, ZA = 0x803D78FC, 0x803D7900, 0x803D7904
PBASE = 0x803AD860                # [PBASE] -> daPy_lk_c; +0x10c / +0x120 = the two pos triples


def _cli(*a):
    subprocess.run([sys.executable, os.path.join(os.path.abspath(_TOOLS), "dolphin_mem.py"), *a],
                   capture_output=True, text=True, env=os.environ)


def _rf(a):
    h, m = dm.attach(); return struct.unpack(">f", dm.read_bytes(h, m, a, 4))[0]


def _wf(a, v):
    h, m = dm.attach(); dm.write_bytes(h, m, a, struct.pack(">f", v))


def _setpos(off, p):
    h, m = dm.attach()
    b = struct.unpack(">I", dm.read_bytes(h, m, PBASE, 4))[0]
    for k, c in enumerate(p):
        dm.write_bytes(h, m, b + off + 4 * k, struct.pack(">f", c))


def live_clip(old, new, slot=None):
    """Clean-place at ``old``, step one clip frame to ``new``; return (clipped, old_slid, drift)."""
    if slot is not None:
        _cli("loadstate", str(slot))
    for off in (0x10c, 0x120):
        _setpos(off, old)
    _wf(XA, old[0]); _wf(YA, old[1]); _wf(ZA, old[2])
    _cli("advancewith", "stickX=128", "stickY=128", "frames=1")   # zero-length settle, no snap
    sx, sy, sz = _rf(XA), _rf(YA), _rf(ZA)
    old_slid = ((sx - old[0]) ** 2 + (sz - old[2]) ** 2) ** 0.5
    _wf(XA, new[0]); _wf(YA, sy); _wf(ZA, new[2])                 # pm_pos = new; old_pos held = old
    _cli("advancewith", "stickX=128", "stickY=128", "frames=1")   # THE clip frame
    fx, fz = _rf(XA), _rf(ZA)
    drift = ((fx - new[0]) ** 2 + (fz - new[2]) ** 2) ** 0.5
    return drift < 1.0, old_slid, drift


def main(argv):
    box = slot = None
    for a in argv:
        if a.startswith("box="):
            box = tuple(float(x) for x in a[4:].split(","))
        elif a.startswith("slot="):
            slot = int(a[5:])
    if box is None:
        print("usage: python -m harness.collision.validate_clips box=xmin,xmax,ymin,ymax,zmin,zmax [slot=N]")
        return 2
    if slot is not None:
        _cli("loadstate", str(slot))
    region, stage = read_region_tris(box)
    res = scan_region(region, box, verbose=False)
    print("stage=%s: %d clippable seams" % (stage, len(res)), flush=True)
    agree = 0
    for r in res:
        clipped, old_slid, drift = live_clip(r["old"], r["new"], slot=slot)
        agree += clipped
        print("  S=(%.1f,%.1f) disp=%.2f  live=%-5s old_slid=%.3f drift=%.3f"
              % (r["S"][0], r["S"][2], r["disp"], "CLIP" if clipped else "BLOCK",
                 old_slid, drift), flush=True)
    print("=== %d/%d predicted clips confirmed live ===" % (agree, len(res)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
