"""chain_probe.py - end-to-end validation of the OFFLINE foot-position chain against live.

Chain: live mNormalSpeed -> anim_state.UnderAnimState.step (bit-exact frames/ratio/m3598)
       -> fk.foot_toe_blend (1-frame delay: the toe DRAWN at frame N uses the state from step N-1,
          and posMove reads that drawn toe) -> compare model-local toe to live rtoe/ltoe.

Drives the flat walk from land_flatwalk@twwgz. Also dumps the live oldframe-morf rate per frame so we
can see exactly which frames need the oldframe-morf blend (task 4) that this chain does NOT yet apply.
DEV tool; reads gitignored _generated anim/skeleton data.
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
from tww_sim.core.anim import fk
from tww_sim.core.anim.anim_state import UnderAnimState

def f32(x): return struct.unpack('>f', struct.pack('>f', float(x)))[0]

def main():
    h, mem1 = dm.attach()
    anm, sk = fk.load()
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ru(o): return struct.unpack('>I', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ri(o, sz): return struct.unpack('>h' if sz == 2 else '>B', dm.read_bytes(h, mem1, P+o, sz))[0]
    def vec(o): return (rf(o), rf(o+4), rf(o+8))
    def oldrate():
        op = ru(0x30DC)
        return struct.unpack('>f', dm.read_bytes(h, mem1, op+0xC, 4))[0]

    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]

    UP = {"stickX": 128, "stickY": 255, "substickX": 128, "substickY": 0, "buttons": 0}
    NEUT = {"stickX": 128, "stickY": 128, "substickX": 128, "substickY": 0, "buttons": 0}
    seq = [UP]*24 + [NEUT]*12

    # capture live per frame
    live = []
    for inp in seq:
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        live.append(dict(ns=rf(0x34E4), plant=ri(0x33E4, 1), rtoe=vec(0x3CF8), ltoe=vec(0x3E10),
                         orate=oldrate()))

    # offline: start walk state machine at first moving frame (nspeed>0). Init from FREEB single (m34C3=0).
    st = UnderAnimState(move0_anim='freeb', move0_frame=70.0, m34C3=0)
    print(" f  ns    pl orate | live toe x,z          recon x,z            err(x,z)   note")
    prev_state = None
    maxerr_moving = 0.0
    for i, L in enumerate(live):
        if L['ns'] <= 0.0 and prev_state is None:
            continue                                   # not walking yet
        state = st.step(L['ns'])
        # 1-frame delay: the toe live-read at frame i was drawn from the PREVIOUS step's frame/ratio.
        use = prev_state
        prev_state = state
        if use is None:
            continue
        pl = L['plant']; jnt = 39 if pl == 0 else 34
        recon = fk.foot_toe_blend(anm[use['move0']], anm[use['move1']], sk,
                                  use['f0'], use['f1'], use['ratio'], foot_jnt=jnt)
        liveT = L['rtoe'] if pl == 0 else L['ltoe']
        ex, ez = f32(liveT[0]-recon[0]), f32(liveT[2]-recon[2])
        morf = ' MORF' if L['orate'] > 0.0 else ''
        if L['ns'] > 0.0:
            maxerr_moving = max(maxerr_moving, abs(ex), abs(ez))
        print("%2d %5.2f %d %.3f | (%8.3f,%8.3f) (%8.3f,%8.3f) (%+.1e,%+.1e)%s" % (
            i, L['ns'], pl, L['orate'], liveT[0], liveT[2], recon[0], recon[2], ex, ez, morf))
    print("max |err| xz over MOVING frames (no oldframe-morf applied): %.3e" % maxerr_moving)

if __name__ == "__main__":
    main()
