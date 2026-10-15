"""Live spot-check of a min-frames-to-destination schedule.

Flow: loadstate 10 -> settle -> seed (v, air) -> hold ESS a few frames to reach
STEADY state-55 ESS (the neutral->ESS pump happens here) -> read the REAL
(v, anim, air) -> plan with beam_search_to_dest from those real values -> replay
the schedule live, measuring cumulative forward (net) distance each frame -> compare
the live crossing frame against the sim's crossing frame and the optimizer's count.

Usage: python spotcheck_minframes.py [v=-1630] [air=510] [dest=20000] [beam=3000]
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
from tww_sim.swim import optimize as O
from tww_sim.swim import plan as P

ESS = (128, 110)
NEU = (128, 128)
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

def act_to_stick(a):
    if a == 'ess': return ESS
    if a == 'neu': return NEU
    raise ValueError(f"live replay does not map action {a!r} (charge not supported here)")

def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    v = float(opts.get('v', '-1630')); air_seed = int(opts.get('air', '510'))
    dest = float(opts.get('dest', '20000')); beam = int(opts.get('beam', '3000'))
    use_plan = opts.get('plan', '0') != '0'   # route through superswim_plan's DP

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
    if use_plan:
        res = P.plan_min_frames(dest, v0, anim0, air0, actions=('ess', 'chg', 'neu'),
                                entry_tax=False)
        acts, nfr, reached = res['actions'], res['frames'], res['reached']
        print(f"[superswim_plan DP] capped layers: {len(res['capped_layers'])}")
    else:
        acts, nfr, reached, _ = O.beam_search_to_dest(
            dest, v0, anim0, air0, beam=beam, actions=('ess', 'chg', 'neu'),
            entry_tax=False)
    if nfr is None:
        print(f"planner did not reach dest within cap; got {reached:.0f}"); return
    if 'chg' in acts:
        print("schedule contains charge frames; this spot-check only maps ess/neu. "
              "Pick a (v,air,dest) that yields no charge."); return
    print(f"optimizer: {nfr} frames, reaches {reached:.0f}  seq={O.seq_string(acts)}")

    # sim per-frame net (same seed + schedule)
    sim_rows = S.run_trace(acts, v0, anim0, air0, entry_tax=False)
    sim_cross = next((row['f'] for row in sim_rows if row['net'] >= dest), None)

    # live replay, measuring net distance from the replay-start position
    x0 = r(h, mem1, "link_x"); z0 = r(h, mem1, "link_z")
    live_cross = None
    print("\nf   act   live_net   sim_net   d(live-sim)")
    for i, a in enumerate(acts, 1):
        adv(*act_to_stick(a))
        x = r(h, mem1, "link_x"); z = r(h, mem1, "link_z")
        live_net = math.hypot(x - x0, z - z0)
        sim_net = sim_rows[i-1]['net']
        if live_cross is None and live_net >= dest:
            live_cross = i
        print(f"{i:<3} {a:<4}  {live_net:9.1f} {sim_net:9.1f}  {live_net - sim_net:+8.1f}")

    print(f"\nCROSSING dest={dest:.0f}:  optimizer={nfr}  sim={sim_cross}  live={live_cross}")
    print("RESULT:", "MATCH" if live_cross == sim_cross == nfr
          else f"MISMATCH (opt {nfr} / sim {sim_cross} / live {live_cross})")
    D.cmd_control_pipe("clearinput")

if __name__ == "__main__":
    main()
