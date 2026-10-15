"""Live-validate a long COLD-START full swim (v=0, air=900, state 54) by replaying a
fixed action sequence and comparing per frame to a SwimState seeded IDENTICALLY (same
v/anim/air AND state 54, so both go through the 54->55 entry transition).

Reports: per-frame net distance (live vs sim), the frame each crosses `dest`, the final
distance, and the worst per-frame error. The cold-start 54->55 transition uses the
x598 pump-anim scramble (the one model piece flagged as not-fully-live-faithful) -- if
the early frames diverge, that's the entry, not the (validated) state-55 cruise.

Usage: python spotcheck_coldstart.py [dest=200000] [slot=10]
  seq is read from coldstart_seq.txt (one 'act,n;act,n;...' line).
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

ESS = (128, 110); NEU = (128, 128); CHG_UP, CHG_DN = (128, 255), (128, 0)


def adv(sx, sy):
    D.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                         "substickY": 0, "frames": 1})


def wnamed(h, m, name, value):
    e = D.NAMED_ADDRS[name]; addr = D.resolve_chain(h, m, e["base"], e["offsets"])
    t = e["type"]; fmt, sz = D.FMT[t]
    data = (struct.pack(fmt, float(value)) if t in ("f32", "f64")
            else struct.pack(">" + {1: "B", 2: "H", 4: "I", 8: "Q"}[sz],
                             int(value) & ((1 << (sz * 8)) - 1)))
    D.write_bytes(h, m, addr, data)


def r(h, m, name):
    return D.read_named(h, m, name)


def expand(seq):
    acts = []
    for seg in seq.strip().split(';'):
        if not seg:
            continue
        a, n = seg.split(','); acts += [a] * int(n)
    return acts


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    dest = float(opts.get('dest', '200000')); slot = int(opts.get('slot', '10'))
    seq = open('coldstart_seq.txt').read()
    acts = expand(seq)

    D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})
    h, m = D.attach(); adv(*NEU); h, m = D.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", 0.0)
    v0 = r(h, m, "potential_speed"); anim0 = r(h, m, "anim_frame")
    air0 = r(h, m, "air"); st0 = r(h, m, "link_state")
    print(f"cold start: v={v0:.2f} anim={anim0:.3f} air={air0} state={st0}  "
          f"({len(acts)} action frames, dest={dest:.0f})")

    # sim seeded IDENTICALLY incl. starting state (54 = neutral) so both cross 54->55
    sim = S.SwimState(v=v0, anim=anim0, air=air0)
    sim.state = st0
    sim_rows = []
    for a in acts:
        sim.step(a)
        sim_rows.append({"net": math.hypot(sim.x, sim.z), "v": sim.v,
                         "anim": sim.anim, "air": sim.air})
    sim_cross = next((i + 1 for i, row in enumerate(sim_rows) if row['net'] >= dest), None)
    print(f"sim trace: {len(acts)} fr -> {sim_rows[-1]['net']:.0f}; "
          f"crosses dest at sim frame {sim_cross}")

    x0 = r(h, m, "link_x"); z0 = r(h, m, "link_z")
    live_cross = None; worst = 0.0; tog = 0
    print("\nf    act  | live_net   sim_net   d(L-S)   v_live   v_sim   st")
    for i, a in enumerate(acts, 1):
        if a == 'ess':
            adv(*ESS)
        elif a == 'neu':
            adv(*NEU)
        else:
            adv(*(CHG_UP if tog == 0 else CHG_DN)); tog ^= 1
        x = r(h, m, "link_x"); z = r(h, m, "link_z")
        lnet = math.hypot(x - x0, z - z0)
        snet = sim_rows[i - 1]['net']
        worst = max(worst, abs(lnet - snet))
        if live_cross is None and lnet >= dest:
            live_cross = i
        if i <= 10 or i % 25 == 0 or i == len(acts) or live_cross == i:
            vl = r(h, m, "potential_speed"); stt = r(h, m, "link_state")
            print(f"{i:<4} {a:<4} | {lnet:9.0f} {snet:9.0f} {lnet-snet:+8.0f} "
                  f"{vl:8.1f} {sim_rows[i-1]['v']:8.1f}  {stt}")

    xf = r(h, m, "link_x"); zf = r(h, m, "link_z")
    fin = math.hypot(xf - x0, zf - z0)
    print(f"\nFINAL: live={fin:.0f}  sim={sim_rows[-1]['net']:.0f}  "
          f"({100*fin/sim_rows[-1]['net']:.2f}% of sim)")
    print(f"CROSSING dest={dest:.0f}: sim={sim_cross}  live={live_cross}")
    print(f"worst per-frame |live-sim|: {worst:.0f} ({worst/dest*100:.3f}% of dest)")
    D.cmd_control_pipe("clearinput")


if __name__ == "__main__":
    main()
