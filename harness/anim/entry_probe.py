"""entry_probe.py - dissect the walk-ENTRY frames live to nail f31_2 at frame f2.

Reads per frame during the standing->walk handoff:
  ns, speedF, f31_2, m3598, plant, oldFrameFlg, oldFrameRate,
  mFootData[0/1].field_0x018 (STORED spB0 toe = rtoe 0x3CF8 / ltoe 0x3E10).

Goal: see (a) when oldFrameFlg flips true, (b) the exact stored spB0 each frame so we can tell
whether spB0 at the first moving frame is the FREEB pose or the first walk-blend pose, and
(c) confirm raw f31_2(N) = absXZ(stored[N] - stored[N-1]).
DEV tool.
"""
import os, sys, struct, math
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
    def ru(o): return struct.unpack('>I', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ri(o, sz): return struct.unpack('>h' if sz == 2 else '>B', dm.read_bytes(h, mem1, P+o, sz))[0]
    def vec(o): return (rf(o), rf(o+4), rf(o+8))
    def old():
        op = ru(0x30DC)
        flg = struct.unpack('>B', dm.read_bytes(h, mem1, op+0, 1))[0]
        rate = struct.unpack('>f', dm.read_bytes(h, mem1, op+0xC, 4))[0]
        return flg, rate

    def ridx(o): return struct.unpack('>h', dm.read_bytes(h, mem1, P+o, 2))[0]
    UP = {"stickX": 128, "stickY": 255, "substickX": 128, "substickY": 0, "buttons": 0}
    seq = [UP]*6
    prev = None
    flg, rate = old()
    print("initial: oldFrameFlg=%d rate=%.4f idx0=%d idx1=%d f0=%.3f f1=%.3f" % (
        flg, rate, ridx(0x2F04), ridx(0x2F14), rf(0x2F64), rf(0x2F78)))
    print(" f  ns    spF     f31_2  m3598  pl flg rate idx0 idx1  f0     f1    | ltoe(x,z)")
    for i, inp in enumerate(seq, 1):
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        ns = rf(0x34E4); spF = rf(0x17C); f312 = rf(0x34C4); m3598 = rf(0x34C0)
        pl = ri(0x33E4, 1); flg, rate = old()
        rtoe = vec(0x3CF8); ltoe = vec(0x3E10)
        print("%2d %5.2f %7.4f %6.4f %5.3f  %d  %d %.3f %4d %4d %6.3f %6.3f | (%8.3f,%8.3f)" % (
            i, ns, spF, f312, m3598, pl, flg, rate, ridx(0x2F04), ridx(0x2F14),
            rf(0x2F64), rf(0x2F78), ltoe[0], ltoe[2]))
        prev = (rtoe, ltoe)

if __name__ == "__main__":
    main()
