"""speedf_driver_probe.py - validate tww_sim.core.anim.foot_speedf.FootSpeedF vs live over a full
walk arc INCLUDING the standing->walk entry and the stop. This is the packaged-driver check that
supersedes speedf_probe.py's inline pipeline (which used the wrong REST prevStored at the entry).

Drives the flat walk from land_flatwalk@twwgz with the same 2-frame input latency land.py applies,
so the (nspeed, msd) fed to the driver matches what LandState will feed it. DEV tool.
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
from tww_sim.core.anim.foot_speedf import FootSpeedF

def main():
    h, mem1 = dm.attach()
    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ridx(o): return struct.unpack('>h', dm.read_bytes(h, mem1, P+o, 2))[0]
    idle_frame = rf(0x2F64)               # live FREEB frame-ctrl value at the anchor
    print("anchor idle FREEB frame = %.3f  loaded idx0=%d" % (idle_frame, ridx(0x2F04)))

    UP = {"stickX": 128, "stickY": 255, "substickX": 128, "substickY": 0, "buttons": 0}
    NEUT = {"stickX": 128, "stickY": 128, "substickX": 128, "substickY": 0, "buttons": 0}
    seq = [UP]*30 + [NEUT]*20

    live = []
    for inp in seq:
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        live.append(dict(ns=rf(0x34E4), speedF=rf(0x17C), msd=rf(0x34D8)))

    drv = FootSpeedF(idle_frame=idle_frame)
    print(" f  ns     msd  | speedF   live     err")
    mx = 0.0
    for i, L in enumerate(live, 1):
        spF = drv.step(L['ns'], L['msd'])
        e = abs(spF - L['speedF'])
        if L['ns'] > 0.0:
            mx = max(mx, e)
        tag = '' if e < 1e-3 else '  <--'
        print("%2d %6.3f %5.3f | %8.4f %8.4f %+.2e%s" % (i, L['ns'], L['msd'], spF, L['speedF'], spF-L['speedF'], tag))
    print("max |speedF err| over moving frames = %.2e" % mx)

if __name__ == "__main__":
    main()
