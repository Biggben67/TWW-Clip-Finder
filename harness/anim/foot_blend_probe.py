"""foot_blend_probe.py - validate the ported blended-foot FK (fk.foot_toe_blend) against live.

Drives the walk from land_flatwalk@twwgz and, per frame, dumps the two under-body frame-controller
frames/rates, the blend ratio (walk weight = getRatio(1)), the oldframe-morf rate, and the live
model-local toe (spB0: rtoe 0x3CF8 / ltoe 0x3E10). Then it evaluates foot_toe_blend(dash,walk,...)
for the planted foot and compares to live. Target: bit-exact (or <=1 ULP).

Player member offset -> pointer offset = struct_offset - 0xD8 (P = deref 0x803AD860).
  mFrameCtrlUnder[0] (dash=MOVE0) @struct 0x302C: mEnd 0x3034 mRate 0x3038 mFrame 0x303C
  mFrameCtrlUnder[1] (walk=MOVE1) @struct 0x3040: mEnd 0x3044 mRate 0x304C mFrame 0x3050
  mAnmRatioUnder[0] @struct 0x2FB4: mRatio 0x2FB4 mAnmTransform 0x2FB8
  mAnmRatioUnder[1] @struct 0x2FBC: mRatio 0x2FBC mAnmTransform 0x2FC0
  m_old_fdata @struct 0x31B4 (ptr); OldFrame: mOldFrameFlg +0x0 mOldFrameMorfCounter +0x4 mOldFrameRate +0xC
DEV tool; reads gitignored _generated anim/skeleton data.
"""
import os, sys, math, struct
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

# pointer offsets (struct - 0xD8)
O = dict(
    rtoe=0x3CF8, ltoe=0x3E10, m34BC=0x33E4,
    d_end=0x2F5C, d_rate=0x2F60, d_frame=0x2F64,   # dash frame ctrl
    w_end=0x2F6C, w_rate=0x2F74, w_frame=0x2F78,   # walk frame ctrl
    r0=0x2EDC, a0=0x2EE0, r1=0x2EE4, a1=0x2EE8,    # AnmRatio packs
    oldp=0x30DC,                                    # m_old_fdata ptr
    m3598=0x34C0, m359C=0x34C4,
)

def f32(x): return struct.unpack('>f', struct.pack('>f', float(x)))[0]

def main():
    h, mem1 = dm.attach()
    anm_all, sk = fk.load()
    anm_dash, anm_walk = anm_all['dash'], anm_all['walk']

    def P(): return struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    p = P()
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, p+o, 4))[0]
    def ru(o): return struct.unpack('>I', dm.read_bytes(h, mem1, p+o, 4))[0]
    def ri(o, sz): return struct.unpack('>h' if sz == 2 else '>B', dm.read_bytes(h, mem1, p+o, sz))[0]
    def vec(o): return (rf(o), rf(o+4), rf(o+8))
    def oldrate():
        op = ru(O['oldp'])
        flg = struct.unpack('>B', dm.read_bytes(h, mem1, op+0x0, 1))[0]
        morf = struct.unpack('>f', dm.read_bytes(h, mem1, op+0x4, 4))[0]
        rate = struct.unpack('>f', dm.read_bytes(h, mem1, op+0xC, 4))[0]
        return flg, morf, rate

    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\", "/")})
    p = P()

    CDOWN = {"substickX": 128, "substickY": 0, "buttons": 0}
    UP = {"stickX": 128, "stickY": 255, **CDOWN}
    NEUT = {"stickX": 128, "stickY": 128, **CDOWN}
    seq = [("up", UP)]*15 + [("neut", NEUT)]*12

    print(" f  ph   pl | dfr/drt   wfr/wrt   ratio | oldflg morf rate | "
          "live toe[pl] x,z        recon x,z            err(x,z)")
    snap0 = dict(ph="rest", pl=ri(O['m34BC'], 1),
                 dfr=rf(O['d_frame']), wfr=rf(O['w_frame']), ratio=rf(O['r1']),
                 rt=vec(O['rtoe']), lt=vec(O['ltoe']))
    print("rest      pl=%d dfr=%.4f wfr=%.4f ratio=%.4f" % (snap0['pl'], snap0['dfr'], snap0['wfr'], snap0['ratio']))

    maxerr = 0.0
    for i, (phase, inp) in enumerate(seq):
        dm.control_pipe_quiet("advancewith", {**inp, "frames": 1})
        pl = ri(O['m34BC'], 1)
        dfr, drt = rf(O['d_frame']), rf(O['d_rate'])
        wfr, wrt = rf(O['w_frame']), rf(O['w_rate'])
        ratio = rf(O['r1'])
        flg, morf, orate = oldrate()
        rt, lt = vec(O['rtoe']), vec(O['ltoe'])
        live = rt if pl == 0 else lt
        foot_jnt = 39 if pl == 0 else 34
        recon = fk.foot_toe_blend(anm_dash, anm_walk, sk, dfr, wfr, ratio, foot_jnt=foot_jnt)
        ex, ez = f32(live[0]-recon[0]), f32(live[2]-recon[2])
        maxerr = max(maxerr, abs(ex), abs(ez))
        print("%2d %-4s %d | %6.3f/%.2f %6.3f/%.2f %.4f | %d %.3f %.3f | "
              "(%9.4f,%9.4f) (%9.4f,%9.4f) (%+.1e,%+.1e)" % (
                  i, phase, pl, dfr, drt, wfr, wrt, ratio, flg, morf, orate,
                  live[0], live[2], recon[0], recon[2], ex, ez))
    print("max |err| xz = %.3e" % maxerr)

if __name__ == "__main__":
    main()
