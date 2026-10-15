"""speedf_probe.py - CAPSTONE: the full OFFLINE foot-speedF pipeline vs live, over a flat walk arc.

Chain (all offline except the mNormalSpeed input, which land.py produces bit-exact):
  UnderAnimState.step(nspeed)            -> MOVE0/MOVE1 anim, frame ctrls, ratio, m3598 (f32-exact)
  FootFK.step_feet(...)  [1-FRAME DELAY] -> model-local toe+heel both feet; spB0_N = FK(state N-1)
  posMoveFromFootPos (below, offline)    -> plant / f31_2 / speedF

Result: bit-exact (float, ~1e-5) vs live for the walk INTERIOR (frames 3..end-of-move). Two proc
boundaries are approximate and flagged: walk-entry f2 (fixed rest-offset handoff not yet nailed) and
the fully-stopped frame (nspeed=0 -> speedF=0 anyway). See handoff 2026-07-04d.

posMoveFromFootPos facts reproduced (d_a_player_main.cpp:2353):
  - plant m34BC = lower foot midpoint-Y (flat: sp0C = sp80.y);  idx0=RIGHT(jnt39), idx1=LEFT(jnt34).
  - f31_2 = absXZ(spB0[plant] - prevStored[plant]) on the DELAYED toe stream.
  - smoothing (RECURSIVE): f31_2 = raw*0.3 + 0.7*f31_2_prev, gated by m3598<1 AND |m35B4-msd|<0.2
    (m35B4 = PREVIOUS frame's mStickDistance).
  - speedF = nspeed*(1-m3598) +/- f31_2*m3598 (+ if nspeed>=0); *cos(groundAngle)=1 flat; 0 if |.|<0.05.
  - walk ENTRY prevStored spB0 = fixed rest offset {-14.05,0,5.02} (mirror x for left).
DEV tool; reads gitignored _generated anim/skeleton data.
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
from tww_sim.core.anim import fk
from tww_sim.core.anim.anim_state import UnderAnimState
from tww_sim.core.anim.foot_fk import FootFK

def f32(x): return struct.unpack('>f', struct.pack('>f', float(x)))[0]

def plant_of(feet):
    """m34BC on flat ground: index of the foot with the lower toe/heel midpoint Y."""
    midY = [f32((feet['toe'][k][1] + feet['heel'][k][1]) * 0.5) for k in (0, 1)]
    return 0 if midY[0] < midY[1] else 1

def main():
    h, mem1 = dm.attach()
    anm, sk = fk.load()
    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput"); dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ri(o, sz): return struct.unpack('>h' if sz == 2 else '>B', dm.read_bytes(h, mem1, P+o, sz))[0]

    UP = {"stickX": 128, "stickY": 255, "substickX": 128, "substickY": 0, "buttons": 0}
    NEUT = {"stickX": 128, "stickY": 128, "substickX": 128, "substickY": 0, "buttons": 0}
    seq = [UP]*24 + [NEUT]*10

    live = []
    for inp in seq:
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        live.append(dict(ns=rf(0x34E4), plant=ri(0x33E4, 1), f312=rf(0x34C4),
                         speedF=rf(0x17C), m3598=rf(0x34C0), msd=rf(0x34D8)))

    st = UnderAnimState(move0_anim='freeb', move0_frame=70.0, m34C3=0)
    ff = FootFK(anm, sk); ff.seed('freeb', 72.0)
    REST = {'toe': [(-14.05, 0.0, 5.02), (14.05, 0.0, 5.02)]}   # oldFrameFlg==false rest offsets
    t1 = ff.step_feet('freeb', 'freeb', 72.0, 72.0, 0.0, -1.0)
    t2 = REST
    prev_f312 = 0.0
    m35B4 = 1.0
    prevstate = None
    print(" f  ns    | pl L/S | f31_2   live     err   | speedF   live     err")
    mxf = mxs = 0.0
    for i, L in enumerate(live):
        if L['ns'] <= 0.0 and prevstate is None:
            m35B4 = L['msd']; continue
        morf = 2.4 if prevstate is None else -1.0          # oldframe-morf triggers at walk entry
        state = st.step(L['ns']); prevstate = state
        cur = ff.step_feet(state['move0'], state['move1'], state['f0'], state['f1'],
                           state['ratio'], i_morf=morf)
        plant = plant_of(t1)                                # spB0_N = t1 (drawn last frame)
        dx = f32(t1['toe'][plant][0] - t2['toe'][plant][0])
        dz = f32(t1['toe'][plant][2] - t2['toe'][plant][2])
        f312 = f32(math.hypot(dx, dz))
        m = state['m3598']; msd = L['msd']
        if m < 1.0 and abs(f32(m35B4 - msd)) < 0.2:
            f312 = f32(f32(f312 * 0.3) + f32(0.7 * prev_f312))
        ns = L['ns']
        spz = f32(ns * f32(1.0 - m))
        spz = f32(spz + f32(f312 * m)) if ns >= 0 else f32(spz - f32(f312 * m))
        speedF = 0.0 if abs(spz) < 0.05 else spz
        ef = abs(f312 - L['f312']); es = abs(speedF - L['speedF'])
        if ns > 0: mxf = max(mxf, ef); mxs = max(mxs, es)
        tag = '' if ef < 1e-3 else '  <-- boundary' if (ns == 0 or prevstate is state and i < 3) else '  *'
        print("%2d %5.2f | %d/%d %-4s| %7.4f %7.4f %+.1e | %8.4f %8.4f %+.1e%s" % (
            i, ns, plant, L['plant'], 'OK' if plant == L['plant'] else 'PL!',
            f312, L['f312'], f312-L['f312'], speedF, L['speedF'], speedF-L['speedF'], tag))
        m35B4 = msd; t2 = t1; t1 = cur; prev_f312 = f312
    print("max |f31_2 err| moving = %.2e ; max |speedF err| moving = %.2e "
          "(interior bit-exact; boundaries f2/stop approximate)" % (mxf, mxs))

if __name__ == "__main__":
    main()
