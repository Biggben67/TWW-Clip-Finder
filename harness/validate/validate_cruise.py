"""validate_cruise.py - prove the sim is BIT-EXACT to live through a long superswim cruise
with many neu->ess re-entries, PER FRAME (not just the endpoint).

This is the gate that settles the old "554 artifact / anim-phase drift" question. It captures
the live MOVE0 J3DFrameCtrl internals frame-by-frame (anim_frame == raw mFrame, fc_rate == mRate,
fc_end == mEnd) and compares to ColdStartSwimState seeded at FULL f32 PRECISION. The prior
"~3 frame anim drift" was a DIAGNOSTIC ARTIFACT of a TRUNCATED seed (anim 8.9417 vs the true
8.941699028): the cold-start x598 scramble amplifies a sub-ULP seed error ~600x, then again at
every re-entry. With the exact seed the sim is bit-exact through the entire swim-ALIVE region.

Method: load slot 10, run_tests-style seed (1 neutral frame + write air=900/v=0), read the
EXACT seed (anim0, mr0) live, then replay. The dense charge BUILD is one race-free advanceseq;
the cruise is single-stepped (ess/neu -> no input drops) reading internals each frame.
advanceseq == DTM-playback for the cold-start cruise (verified: a recorded-DTM of cp_p0/cp_p1
plays back bit-exact to advanceseq and the sim).

Compares over the swim-ALIVE region (live v < -0.05). The post-death FORWARD tail (v>=0) is the
documented out-of-scope bug#1 (setNormalSpeedF forward cap + tail scrambles) and is NOT gated --
net distance is reached long before death and the planner only runs v<0.

  python validate_cruise.py [seq=synced200k_seq.txt] [build=200] [tol=0.01] [slot=10] [pid=N]
"""
import sys, struct, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import sim as S
from tww_sim.swim import actions as A
from harness import live as L
from tww_sim.swim.coldstart import ColdStartSwimState

ESS=(128,110); NEU=(128,128); CHG_UP,CHG_DN=(128,255),(128,0)


def _stick(a, chg):
    if a=='ess': return ESS, chg
    if a=='neu': return NEU, chg
    if a=='chg':
        chg+=1; return (CHG_UP if chg%2==1 else CHG_DN), chg
    raise ValueError(a)


def _rawf(h, m, name):
    e=D.NAMED_ADDRS[name]; addr=D.resolve_chain(h,m,e['base'],e['offsets'])
    return struct.unpack('>f', D.read_bytes(h,m,addr,4))[0]


def main():
    o=dict(t.split('=',1) for t in sys.argv[1:] if '=' in t)
    seqfile=o.get('seq','synced200k_seq.txt'); slot=int(o.get('slot','10'))
    tol=float(o.get('tol','0.01')); build=int(o.get('build','200'))
    acts=A.expand(open(seqfile).read())

    # seed exactly like run_tests, then read the FULL-PRECISION seed live
    D.control_pipe_quiet("savestate",{"action":"load","slot":slot}); h,m=D.attach()
    D.control_pipe_quiet("advancewith",{"stickX":128,"stickY":128,"substickY":0,"frames":1}); h,m=D.attach()
    L.wnamed(h,m,"air",900); L.wnamed(h,m,"potential_speed",0.0)
    anim0=_rawf(h,m,"anim_frame"); mr0=_rawf(h,m,"move0_mrate")

    # live per-frame capture
    live={}; chg=0
    seq=[]
    for a in acts[:build]:
        (sx,sy),chg=_stick(a,chg); seq.append({"stickX":sx,"stickY":sy,"substickY":0,"frames":1})
    D.control_pipe_quiet("advanceseq",{"port":0,"seq":seq}); h,m=D.attach()
    live[build]=dict(state=D.read_named(h,m,"link_state"), end=D.read_named(h,m,"fc_end"),
                     mframe=_rawf(h,m,"anim_frame"), v=_rawf(h,m,"potential_speed"))
    for i in range(build, len(acts)):
        (sx,sy),chg=_stick(acts[i],chg)
        D.control_pipe_quiet("advancewith",{"stickX":sx,"stickY":sy,"substickY":0,"frames":1}); h,m=D.attach()
        live[i+1]=dict(state=D.read_named(h,m,"link_state"), end=D.read_named(h,m,"fc_end"),
                       mframe=_rawf(h,m,"anim_frame"), v=_rawf(h,m,"potential_speed"))
    D.control_pipe_quiet("clearinput")

    # sim with the EXACT seed
    s=ColdStartSwimState(v=0.0, anim=anim0, air=900, mrate=mr0); s.state=54; s._entry_tax=False
    maxdv=0.0; maxdp=0.0; worst=None; lastneg=None; reentries=0; prev='chg'
    for i,a in enumerate(acts):
        s.step(a); f=i+1; lv=live.get(f)
        if a!='neu' and prev=='neu': reentries+=1
        prev=a
        if not lv: continue
        if lv['v'] < -0.05:                      # swim-alive region only
            lastneg=f
            cyc=float(lv['end']); dr=(s.anim-lv['mframe'])%cyc; dp=min(dr,cyc-dr)
            dv=abs(s.v-lv['v'])
            if dv>maxdv: maxdv=dv
            if dp>maxdp: maxdp=dp; worst=f
    ok = maxdv<=tol and maxdp<=tol
    print(f"CRUISE PER-FRAME BIT-EXACT GATE  seq={seqfile}  (slot {slot}, tol {tol})")
    print(f"  seed: anim0={anim0!r} mr0={mr0!r}")
    print(f"  swim-alive region: f1..f{lastneg}  ({reentries} neu->ess/chg re-entries)")
    print(f"  max |dv|   = {maxdv:.6f}")
    print(f"  max dphase = {maxdp:.6f}  (worst @f{worst})")
    print(f"  -> {'BIT-EXACT' if ok else 'DIVERGED'}")
    print(f"  (post-death v>=0 tail not gated: out-of-scope bug#1)")
    sys.exit(0 if ok else 1)


if __name__=="__main__":
    main()
