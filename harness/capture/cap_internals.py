"""Live per-frame capture of the MOVE0 J3DFrameCtrl internals through a superswim seq.

Strategy: load slot 10, run_tests-style seed (1 neutral frame + write air=900,speed=0),
then replay the seq. The BUILD prefix (dense charge) is replayed in ONE race-free advanceseq
call; from there each cruise frame is single-stepped via advancewith (cruise = ess/neu, not
dense, so single-step is race-free) and the controller internals are read after each frame.

Logs per frame: link_state, fc_end(mEnd s16), fc_rate(mRate), anim_frame(mFrame RAW),
potential_speed(v), air, msd(mStickDistance).

Usage:
  python cap_internals.py seq=plan200k_seq.txt build=264 to=420 [slot=10] [pid=N] out=cap.tsv
    build = #frames replayed in the dense advanceseq (rest single-stepped)
    to     = last frame to capture (default: full seq)
"""
import struct, json
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import actions as A

ESS=(128,110); NEU=(128,128); CHG_UP,CHG_DN=(128,255),(128,0)

def stick_for(a, chgcount):
    if a=='ess': return ESS,chgcount
    if a=='neu': return NEU,chgcount
    if a=='chg':
        chgcount+=1
        return (CHG_UP if chgcount%2==1 else CHG_DN), chgcount
    raise ValueError(a)

def wnamed(h,m,name,value):
    e=D.NAMED_ADDRS[name]; addr=D.resolve_chain(h,m,e["base"],e["offsets"])
    t=e["type"]; fmt,sz=D.FMT[t]
    data=(struct.pack(fmt,float(value)) if t in("f32","f64")
          else struct.pack(">"+{1:"B",2:"H",4:"I",8:"Q"}[sz], int(value)&((1<<(sz*8))-1)))
    D.write_bytes(h,m,addr,data)

def readrow(h,m):
    return dict(
        state=D.read_named(h,m,"link_state"),
        end=D.read_named(h,m,"fc_end"),
        rate=D.read_named(h,m,"fc_rate"),
        mframe=D.read_named(h,m,"anim_frame"),
        v=D.read_named(h,m,"potential_speed"),
        air=D.read_named(h,m,"air"),
        msd=D.read_named(h,m,"msd"),
    )

def main():
    o=dict(t.split('=',1) for t in sys.argv[1:] if '=' in t)
    seqfile=o['seq']; slot=int(o.get('slot','10'))
    acts=A.expand(open(seqfile).read())
    to=int(o.get('to',str(len(acts))))
    acts=acts[:to]
    build=int(o.get('build','0'))
    outpath=o.get('out')

    D.control_pipe_quiet("savestate",{"action":"load","slot":slot})
    h,m=D.attach()
    D.control_pipe_quiet("advancewith",{"stickX":128,"stickY":128,"substickY":0,"frames":1})
    h,m=D.attach()
    wnamed(h,m,"air",900); wnamed(h,m,"potential_speed",0.0)

    rows=[]
    chg=0
    # dense build prefix in one advanceseq
    if build>0:
        seq=[]
        for a in acts[:build]:
            (sx,sy),chg=stick_for(a,chg)
            seq.append({"stickX":sx,"stickY":sy,"substickY":0,"frames":1})
        D.control_pipe_quiet("advanceseq",{"port":0,"seq":seq})
        h,m=D.attach()
        r=readrow(h,m); r['f']=build; r['act']=acts[build-1]
        rows.append(r)
    # single-step the rest
    for i in range(build, len(acts)):
        a=acts[i]
        (sx,sy),chg=stick_for(a,chg)
        D.control_pipe_quiet("advancewith",{"stickX":sx,"stickY":sy,"substickY":0,"frames":1})
        h,m=D.attach()
        r=readrow(h,m); r['f']=i+1; r['act']=a
        rows.append(r)
    D.control_pipe_quiet("clearinput")

    hdr="f\tact\tstate\tend\trate\tmframe\tv\tair\tmsd"
    lines=[hdr]
    for r in rows:
        lines.append(f"{r['f']}\t{r['act']}\t{r['state']}\t{r['end']}\t{r['rate']:.6f}\t"
                     f"{r['mframe']:.5f}\t{r['v']:.4f}\t{r['air']}\t{r['msd']:.5f}")
    out="\n".join(lines)
    print(out)
    if outpath:
        open(outpath,'w').write(out)
        sys.stderr.write(f"\nwrote {outpath} ({len(rows)} rows)\n")

if __name__=="__main__":
    main()
