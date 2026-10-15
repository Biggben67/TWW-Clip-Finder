"""Phase 2: fix the build (up to the point of cruise) from a no-pump plan, then search
the cruise+dash WITH pumps and compare frames.

build end = end of the last charge-run of length >= 10 (the in-place speed build). From
that handoff state, run the forward DP over {ess,chg,neu}: once with allow_pump=False
(reboosts + one-way neutral dash = the Phase-1 regime) and once with allow_pump=True
(adds neutral->ESS pumps). Reports the frame delta and writes the full +pump plan.

Usage: python cruise_pump_search.py [prefix=ab_nopump300k_seq.txt] [dest=300000]
                                    [frontier=2000] [pump_chg=0] [out=cruise_pump300k_seq.txt]
"""
import sys
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S
from tww_sim.swim import plan as P
from tww_sim.swim import optimize as O
from tww_sim.swim import actions as A
from tww_sim.swim.coldstart import ColdStartSwimState

# Slot-10 cold-start seed, full f32 precision (live-pinned, DOLPHIN_CONTROL.md "Slot 10 test
# slate"). The handoff MUST be built from THIS so the cruise search runs in the live anim
# PHASE -- the x598 scramble at each re-entry is bit-exact only when the controller frame is
# bit-exact from the start. The old plain-SwimState seed (anim=0.06392, +1.0 scramble rule)
# was internally consistent but anim-phase-DECOUPLED from live: at f509 of synced200k it had
# v=-727/anim=7.2 vs live v=-0.49/anim=23.6 (dphase 9.6). Pumps placed in that fantasy phase
# space don't transfer live -> the phantom 554 (pump_chg=1) the search used to mine. With the
# live-aligned cold start the handoff is BIT-EXACT to live (synced200k @f265: v=-782.50,
# anim=2.1092, dphase 0.00000), so the search prices pump exit-phases correctly.
COLDSTART_ANIM0  = 8.941699028015137    # anim_frame after the entry-tax frame (0x410f1133)
COLDSTART_MRATE0 = 0.5472222566604614   # move0_mrate / fc_rate at the seed (0x3f0c16c2)


def build_handoff(prefix_file):
    acts = A.expand(open(prefix_file).read())
    runs, i = [], 0
    while i < len(acts):
        j = i
        while j < len(acts) and acts[j] == acts[i]:
            j += 1
        runs.append((acts[i], i, j - i)); i = j
    be = 0
    for a, s, l in runs:
        if a == 'chg' and l >= 10:
            be = s + l
    # Live-aligned cold start (ColdStartSwimState): the logged-mRate scramble makes the
    # controller frame bit-exact, so the cruise anim PHASE matches the real game.
    H = ColdStartSwimState(v=0.0, anim=COLDSTART_ANIM0, air=900, mrate=COLDSTART_MRATE0)
    H.state = 54; H._entry_tax = False
    for a in acts[:be]:
        H.step(a)
    return acts, be, H


def main():
    o = dict(t.split('=', 1) for t in sys.argv[1:] if '=' in t)
    pf = o.get('prefix', 'ab_nopump300k_seq.txt')
    dest = float(o.get('dest', '300000'))
    front = int(o.get('frontier', '2000'))
    pump_chg = o.get('pump_chg', '0') != '0'
    out = o.get('out', 'cruise_pump300k_seq.txt')

    acts, be, H = build_handoff(pf)
    print(f"build (point of cruise) = {be} frames; Phase-1 total = {len(acts)}")
    print(f"cruise handoff: v={H.v:.2f} anim={H.anim:.2f} air={H.air} state={H.state} "
          f"progress={-H.x:.1f} remaining={dest-(-H.x):.1f}")
    print(f"Phase-1 cruise+dash (no pump) = {len(acts)-be} frames\n")

    base = P.plan_min_frames(dest, H.v, H.anim, H.air, seed_state=H,
                             actions=('ess', 'chg', 'neu'), allow_pump=False,
                             max_frontier=front, verbose=False)
    print(f"no-pump cruise from handoff:        {base['frames']} frames "
          f"-> total {be+base['frames']}")

    res = P.plan_min_frames(dest, H.v, H.anim, H.air, seed_state=H,
                            actions=('ess', 'chg', 'neu'), allow_pump=True,
                            pump_chg=pump_chg, max_frontier=front, verbose=False)
    a = res['actions']
    npump = sum(1 for k in range(1, len(a)) if a[k] != 'neu' and a[k-1] == 'neu')
    print(f"+pumps cruise (frontier={front}, pump_chg={pump_chg}): {res['frames']} frames "
          f"-> total {be+res['frames']}")
    print(f"   frontier max={max(res['frontier_sizes'])}  capped_layers={len(res['capped_layers'])}")
    print(f"   {a.count('chg')} chg, {a.count('neu')} neu, {a.count('ess')} ess; "
          f"{npump} pump-cycles")
    print(f"   saving vs no-pump cruise: {base['frames']-res['frames']} frames")

    full = acts[:be] + list(a)
    open(out, 'w').write(';'.join(f"{x},1" for x in full) + "\n")
    print(f"   wrote {len(full)}-frame plan -> {out}; "
          f"equal-frame arrival candidates={len(res.get('arrival', []))}")


if __name__ == '__main__':
    main()
