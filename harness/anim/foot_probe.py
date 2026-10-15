"""foot_probe.py - dump model-local foot toe/heel positions during a walk arc and
reconstruct f31_2 from them, to validate the plant-select + delta + smoothing + absXZ
math (posMoveFromFootPos) independently of the skeleton FK that produces the positions.
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

# pointer offsets (class - 0xD8) into the player object P = deref(0x803AD860)
OFF = dict(
    rtoe=0x3CF8, rheel=0x3CEC, ltoe=0x3E10, lheel=0x3E04,  # cXyz each
    m34BC=0x33E4,     # u8 planted foot idx (0=right,1=left)
    m34E0=0x3408,     # s16 ground angle (plant tilt); flat -> 0
    m3598=0x34C0, m359C=0x34C4, m35B4=0x34DC, msd=0x34D8,
    nspeed=0x34E4, speedF=0x17C,
)

def f32(x): return struct.unpack('>f', struct.pack('>f', float(x)))[0]

def main():
    h, mem1 = dm.attach()
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]
    def rf(o): return struct.unpack('>f', dm.read_bytes(h, mem1, P+o, 4))[0]
    def ri(o, sz, sgn):
        raw = dm.read_bytes(h, mem1, P+o, sz)
        return struct.unpack(('>b','>h','>i')[sz//2] if sgn else ('>B','>H','>I')[sz//2], raw)[0]
    def vec(o): return (rf(o), rf(o+4), rf(o+8))

    sav = resolve_anchor("land_flatwalk@twwgz")
    dm.control_pipe_quiet("clearinput")
    dm.control_pipe_quiet("pause")
    dm.control_pipe_quiet("savestate", {"action": "load", "path": sav.replace("\\","/")})
    # refresh P after load
    P = struct.unpack('>I', dm.read_bytes(h, mem1, 0x803AD860, 4))[0]

    CDOWN = {"substickX":128,"substickY":0,"buttons":0}
    UP   = {"stickX":128,"stickY":255,**CDOWN}
    NEUT = {"stickX":128,"stickY":128,**CDOWN}
    seq = [("rest",None)] + [("up",UP)]*15 + [("neut",NEUT)]*12

    rows=[]
    def snap(phase):
        rows.append(dict(phase=phase, rtoe=vec(OFF['rtoe']), ltoe=vec(OFF['ltoe']),
                         rheel=vec(OFF['rheel']), lheel=vec(OFF['lheel']),
                         plant=ri(OFF['m34BC'],1,False), gang=ri(OFF['m34E0'],2,True),
                         m3598=rf(OFF['m3598']), m359C=rf(OFF['m359C']), m35B4=rf(OFF['m35B4']),
                         msd=rf(OFF['msd']), nspeed=rf(OFF['nspeed']), speedF=rf(OFF['speedF'])))
    snap("rest")
    for phase, inp in seq[1:]:
        dm.control_pipe_quiet("advancewith", {**inp, "frames":1})
        snap(phase)

    # Reconstruct f31_2 from stored toe positions.
    print(" f  ph   pl g |   nspeed  speedF  |  m359C(f31_2)  recon   err   | toe[plant] x,z (local)")
    toes = [ (r['rtoe'], r['ltoe']) for r in rows ]
    for i,r in enumerate(rows):
        pl = r['plant']
        if i==0:
            print("%2d %-4s %d %d | %8.4f %8.4f |  (seed)"%(i,r['phase'],pl,r['gang'],r['nspeed'],r['speedF']))
            continue
        cur = toes[i][pl]; prev = toes[i-1][pl]
        dx = f32(cur[0]-prev[0]); dz = f32(cur[2]-prev[2])
        raw_f312 = f32(math.hypot(dx,dz))  # absXZ = sqrt(x^2+z^2)
        # smoothing: if m3598<1 and |m35B4 - msd|<0.2: f = f*0.3 + 0.7*m359C_prev
        m359C_prev = rows[i-1]['m359C']
        f312 = raw_f312
        if r['m3598'] < 1.0 and abs(f32(r['m35B4'] - r['msd'])) < 0.2:
            f312 = f32(f32(raw_f312*0.3) + f32(0.7*m359C_prev))
        err = r['m359C'] - f312
        print("%2d %-4s %d %d | %8.4f %8.4f |  %8.4f  %8.4f  %+.1e | (%9.4f, %9.4f)"%(
            i, r['phase'], pl, r['gang'], r['nspeed'], r['speedF'], r['m359C'], f312, err, cur[0], cur[2]))

if __name__=="__main__":
    main()
