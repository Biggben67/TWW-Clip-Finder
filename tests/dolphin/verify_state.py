"""Frame-exact validation of the REAL game state variables (NOT byproduct positions).

The game is deterministic; with the decomp the sim MUST reproduce, every frame:
  potential_speed (v), anim_frame (anim), air, link_state (state)
to full f32 precision. x/z/displacement are wave-height byproducts and are ignored.

Replays a fixed action sequence live from the slot-10 cold start and compares the four
real values per frame to a SwimState seeded identically. Stops-printing-dense around the
FIRST divergence so the offending transition is obvious.

Usage: python verify_state.py [slot=10] [seq=coldstart_seq.txt] [tol=0.02] [maxshow=600]
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
        if seg:
            a, n = seg.split(','); acts += [a] * int(n)
    return acts


def animdiff(a, b, n):
    """minimal circular difference of two anim values on cycle n."""
    d = (a - b) % n
    return min(d, n - d)


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); opts[k] = val
    slot = int(opts.get('slot', '10'))
    tol = float(opts.get('tol', '0.02'))
    maxshow = int(opts.get('maxshow', '600'))
    seqfile = opts.get('seq', 'coldstart_seq.txt')
    if not os.path.exists(seqfile):
        seqfile = os.path.join(_rb, 'fixtures', seqfile)
    acts = expand(open(seqfile).read())

    D.cmd_control_pipe("savestate", {"action": "load", "slot": slot})
    h, m = D.attach(); adv(*NEU); h, m = D.attach()
    wnamed(h, m, "air", 900); wnamed(h, m, "potential_speed", 0.0)
    v0 = r(h, m, "potential_speed"); anim0 = r(h, m, "anim_frame")
    air0 = r(h, m, "air"); st0 = r(h, m, "link_state")
    print(f"cold start: v={v0:.4f} anim={anim0:.4f} air={air0} state={st0}")

    sim = S.SwimState(v=v0, anim=anim0, air=air0); sim.state = st0
    sim._entry_tax = False

    x0 = r(h, m, "link_x"); z0 = r(h, m, "link_z")
    first_div = None
    print("\nf    act  | v_live      v_sim      dv     | an_live  an_sim  dan(cyc)| air L/S | st L/S")
    rows = []
    for i, a in enumerate(acts, 1):
        if a == 'ess':
            adv(*ESS)
        elif a == 'neu':
            adv(*NEU)
        else:
            adv(*(CHG_UP if (i and acts[:i].count('chg') % 2 == 1) else CHG_DN))
        sim.step(a)
        vl = r(h, m, "potential_speed"); anl = r(h, m, "anim_frame")
        airl = r(h, m, "air"); stl = r(h, m, "link_state")
        cyc = 26.0 if stl == 54 else 23.0
        dv = vl - sim.v
        dan = animdiff(anl, sim.anim, cyc)
        rows.append((i, a, vl, sim.v, dv, anl, sim.anim, dan, airl, sim.air, stl, sim.state))
        if airl != sim.air:               # air desync = a DROPPED live frame (emulator
            print(f"\n!! HICCUP: dropped live frame at f{i} (air {airl}/{sim.air}). "
                  f"Re-run for a clean pass.")
            D.cmd_control_pipe("clearinput"); return
        if first_div is None and (abs(dv) > tol or dan > tol or stl != sim.state):
            first_div = i

    # print: all frames up to first_div+5, then sparse, always the divergence region
    lo = (first_div - 3) if first_div else 1
    hi = (first_div + 8) if first_div else 11
    for (i, a, vl, vs, dv, anl, ans, dan, airl, airs, stl, sts) in rows:
        show = (i <= 8 or (lo <= i <= hi) or i % 50 == 0 or i == len(rows))
        if show:
            flag = " <-- DIV" if i == first_div else ""
            print(f"{i:<4} {a:<4} | {vl:9.3f} {vs:9.3f} {dv:+7.3f} | {anl:6.2f} {ans:6.2f} "
                  f"{dan:6.3f} | {airl:3d}/{airs:<3d} | {stl}/{sts}{flag}")

    xf = r(h, m, "link_x"); zf = r(h, m, "link_z")
    net = math.hypot(xf - x0, zf - z0)
    print(f"\nlive net distance (wave-affected byproduct): {net:.0f}")
    if first_div is None:
        print(f"*** ALL {len(rows)} FRAMES MATCH (v/anim within {tol}, air+state exact) ***")
    else:
        print(f"FIRST DIVERGENCE at frame {first_div} (tol={tol}).")
    D.cmd_control_pipe("clearinput")


if __name__ == "__main__":
    main()
