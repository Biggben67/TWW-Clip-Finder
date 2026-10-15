"""Dump the DASH-anim model-local toe positions over a long cruise (single anim, blend=0)
to test whether the anim curve is piecewise-LINEAR between integer frames (table+lerp works)
or smooth/Hermite (must port the Bck evaluator)."""
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

OFF = dict(rtoe=0x3CF8, ltoe=0x3E10, m34BC=0x33E4, m0fr=0x2F64, m0rt=0x2F60,
           m0end=0x2F5C, m3598=0x34C0, nspeed=0x34E4)

def main():
    h, mem1 = dm.attach()
    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action":"load","path":sav.replace("\\","/")})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ri(o,sz): return struct.unpack('>h' if sz==2 else '>B', dm.read_bytes(h,mem1,P+o,sz))[0]
    def vec(o): return (rf(o), rf(o+4), rf(o+8))
    UP={"stickX":128,"stickY":255,"substickX":128,"substickY":0,"buttons":0}
    # hold up long enough to reach cruise and sweep the DASH cycle
    print("  n  m0fr  m0rt m0end blend | plant | rtoe(x,z)          ltoe(x,z)")
    rows=[]
    for n in range(90):
        dm.control_pipe_quiet("advancewith", {**UP,"frames":1})
        m0fr=rf(OFF['m0fr']); m0rt=rf(OFF['m0rt']); m0end=ri(OFF['m0end'],2)
        bl=rf(OFF['m3598']); pl=ri(OFF['m34BC'],1)
        rt=vec(OFF['rtoe']); lt=vec(OFF['ltoe'])
        rows.append((n,m0fr,m0rt,m0end,bl,pl,rt,lt))
    # print only cruise frames (blend==0) sorted by anim frame, right toe
    cr=[r for r in rows if r[4]==0.0]
    cr.sort(key=lambda r:r[1])
    print("--- cruise frames sorted by DASH anim frame (blend=0). right-toe z vs frame ---")
    for r in cr:
        n,m0fr,m0rt,m0end,bl,pl,rt,lt=r
        print("f=%2d anim=%7.4f rate=%.3f end=%d | rtoe=(%9.4f,%9.4f) ltoe=(%9.4f,%9.4f)"%(
            n,m0fr,m0rt,m0end,rt[0],rt[2],lt[0],lt[2]))

if __name__=="__main__": main()
