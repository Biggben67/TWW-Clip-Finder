"""Live spot-check of a full superswim_plan schedule (ESS + charge + neutral + pump).

Unlike spotcheck_minframes.py (ess/neu only), this replays charge frames too, so it
can validate a real reboost+pump+dash plan from superswim_plan.

Flow: loadstate 10 -> settle -> seed (v, air) -> hold ESS to steady state 55 -> read
the REAL (v, anim, air) -> plan with superswim_plan.plan_min_frames FROM THOSE REAL
VALUES -> run the sim from the same real seed -> replay live, measuring cumulative
forward (net) distance each frame -> compare live vs sim per frame and the dest
crossing frame vs the planner's count.

Charge mapping: a 'chg' frame = full-deflection alternation (superswim charging is
back/forth every frame). We toggle stickY 255/0 across consecutive charge frames.

Usage: python spotcheck_plan.py [v=-806] [air=900] [dest=200000] [max_frontier=8000]
"""
import sys, struct, math
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)
import dolphin_mem as D
from tww_sim.swim import sim as S
from tww_sim.swim import plan as P

ESS = (128, 110)
NEU = (128, 128)
CHG_UP, CHG_DN = (128, 255), (128, 0)
SETTLE = 6  # ESS frames to reach steady state 55 before the comparison starts

def adv(sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})

def wnamed(h, mem1, name, value):
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, mem1, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1:"B",2:"H",4:"I",8:"Q"}[sz],
                             int(value) & ((1 << (sz*8)) - 1)))
    D.write_bytes(h, mem1, addr, data)

def r(h, mem1, name):
    return D.read_named(h, mem1, name)

def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    v = float(opts.get('v', '-806')); air_seed = int(opts.get('air', '900'))
    dest = float(opts.get('dest', '200000'))
    max_frontier = int(opts.get('max_frontier', '8000'))

    D.cmd_control_pipe("savestate", {"action": "load", "slot": 10})
    h, mem1 = D.attach(); adv(*NEU); h, mem1 = D.attach()   # settle + re-attach
    wnamed(h, mem1, "air", air_seed); wnamed(h, mem1, "potential_speed", v)
    print(f"seeded pot={r(h,mem1,'potential_speed'):.1f} air={r(h,mem1,'air')} "
          f"state={r(h,mem1,'link_state')}")

    for _ in range(SETTLE):                # reach steady state-55 ESS
        adv(*ESS)
    v0 = r(h, mem1, "potential_speed"); anim0 = r(h, mem1, "anim_frame")
    air0 = r(h, mem1, "air"); st0 = r(h, mem1, "link_state")
    print(f"comparison start: v={v0:.2f} anim={anim0:.4f} air={air0} state={st0}")
    if st0 != 55:
        print("WARN: not in steady ESS (state 55); results may not match sim seed")

    # plan from the REAL live state (already steady ESS -> entry_tax=False)
    res = P.plan_min_frames(dest, v0, anim0, air0, actions=('ess', 'chg', 'neu'),
                            max_frontier=max_frontier, entry_tax=False)
    acts, nfr, reached = res['actions'], res['frames'], res['reached']
    if nfr is None:
        print(f"planner did not reach dest within cap; got {reached:.0f}"); return
    nb, nn = acts.count('chg'), acts.count('neu')
    print(f"plan: {nfr} frames (-> {reached:.0f}); {nb} chg, {nn} neu, "
          f"{nfr-nb-nn} ess; capped layers={len(res['capped_layers'])}")
    print("seq:", P.seq_string(acts))

    # baseline pure-ESS frames to dest from the same seed (context)
    bn, _ = P.frames_to_dest_pure_ess(dest, v0, anim0, air0, entry_tax=False)
    print(f"baseline pure ESS from same seed: {bn} fr  (plan saves {bn-nfr:+d})")

    # sim per-frame net (same seed + schedule)
    sim_rows = S.run_trace(acts, v0, anim0, air0, entry_tax=False)
    sim_cross = next((row['f'] for row in sim_rows if row['net'] >= dest), None)

    # live replay, measuring net distance from the replay-start position
    x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
    live_cross = None
    chg_toggle = 0
    worst = 0.0
    print("\nf   act   live_net    sim_net   d(live-sim)   v_live")
    for i, a in enumerate(acts, 1):
        if a == 'ess':
            adv(*ESS)
        elif a == 'neu':
            adv(*NEU)
        else:                              # chg: alternate full deflection
            adv(*(CHG_UP if chg_toggle == 0 else CHG_DN)); chg_toggle ^= 1
        x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z")
        live_net = math.hypot(x - x0, z - z0)
        sim_net = sim_rows[i-1]['net']
        worst = max(worst, abs(live_net - sim_net))
        if live_cross is None and live_net >= dest:
            live_cross = i
        if i <= 20 or a != 'ess' or i % 20 == 0 or (live_cross == i):
            print(f"{i:<3} {a:<4}  {live_net:9.1f} {sim_net:9.1f}  {live_net-sim_net:+8.1f}"
                  f"      {r(h,mem1,'potential_speed'):.1f}")

    print(f"\nCROSSING dest={dest:.0f}:  plan={nfr}  sim={sim_cross}  live={live_cross}")
    print(f"worst per-frame |live-sim| net error: {worst:.1f} "
          f"({worst/max(dest,1)*100:.4f}% of dest)")
    print("RESULT:", "MATCH" if live_cross == sim_cross
          else f"sim/live crossing differ (sim {sim_cross} / live {live_cross})")
    D.cmd_control_pipe("clearinput")

if __name__ == "__main__":
    main()
