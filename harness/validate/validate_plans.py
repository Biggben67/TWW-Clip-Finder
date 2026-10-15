"""Multi-solution live filter for pump plans (the 'try equal-frame solutions until one
syncs' strategy).

Rationale: with pumps on, the planner finds MANY action sequences that reach `dest` in
the SAME minimal frame count (plan_min_frames builds them all in res['arrival']). The sim
cannot predict the x598 pump-transition timing for every one (bug #2 is chaotic in pump
history), so SOME of these equal-frame plans die live (speed bled, fall short) while others
reproduce exactly. Rather than make the sim bit-exact for pumps, we LIVE-TEST the candidates
and keep the first that actually reaches `dest` in `frames` frames on the emulator.

Each candidate is replayed once via a race-free advanceseq from the slot-10 cold start;
we read the final position (net displacement = live progress) and the end state. A plan
"SYNCS" if it reaches dest live (within tol) AND the sim end-state matches live (v/anim/
air/state) -- i.e. the sim predicted this plan correctly. We try candidates fewest-pumps
first (fewest chaotic transitions => most likely to sync), stop at the first sync, and
write its seq to `out`.

Usage:
  python validate_plans.py dest=20000 [pump_chg=0] [max_frontier=2000] [maxtests=40]
                           [tol=0.01] [slot=10] [out=synced_seq.txt] [slack=0]
"""
import sys, math
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
from tww_sim.swim import actions as A
from harness import live as L


def pump_cycles(acts):
    """A pump = a neutral->swim re-entry (neu followed by a non-neu). Counts the
    chaotic transitions (NOT neu frames; a pump can sit in neutral several frames,
    and the trailing terminal dash is a neu run with no re-entry after it)."""
    return sum(1 for i in range(1, len(acts)) if acts[i] != 'neu' and acts[i - 1] == 'neu')


def net_of(actions, sim_seed):
    """Sim-side end state + predicted net forward (-x)."""
    s = sim_seed.clone()
    for a in actions:
        s.step(a)
    return s, -s.x


def live_replay(actions, slot):
    """Replay actions live from cold start; return (net, v, anim, air, state, frames)."""
    seq = A.acts_to_seq(actions)
    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1}); h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    x0 = D.read_named(h, m, "link_x"); z0 = D.read_named(h, m, "link_z")
    D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq}); h, m = D.attach()
    xf = D.read_named(h, m, "link_x"); zf = D.read_named(h, m, "link_z")
    net = math.hypot(xf - x0, zf - z0)
    return (net, D.read_named(h, m, "potential_speed"), D.read_named(h, m, "anim_frame"),
            D.read_named(h, m, "air"), D.read_named(h, m, "link_state"))


def main():
    o = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('='); o[k] = val
    dest = float(o.get('dest', '20000'))
    slot = int(o.get('slot', '10'))
    pump_chg = o.get('pump_chg', '0') != '0'
    max_frontier = int(o.get('max_frontier', '2000'))
    maxtests = int(o.get('maxtests', '40'))
    tol = float(o.get('tol', '0.01'))            # fractional shortfall allowed
    slack = int(o.get('slack', '0'))             # accept frames up to min+slack (0 = strict)
    maxpumps = int(o['maxpumps']) if 'maxpumps' in o else None  # cap pumps in the plan
    out = o.get('out', 'synced_seq.txt')

    # cold-start seed, identical to the live setup (loadstate 10, neutral, air=900, v=0)
    D.control_pipe_quiet("savestate", {"action": "load", "slot": slot}); h, m = D.attach()
    D.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                         "substickY": 0, "frames": 1}); h, m = D.attach()
    L.wnamed(h, m, "air", 900); L.wnamed(h, m, "potential_speed", 0.0)
    v0 = D.read_named(h, m, "potential_speed"); anim0 = D.read_named(h, m, "anim_frame")
    air0 = D.read_named(h, m, "air"); st0 = D.read_named(h, m, "link_state")
    sim_seed = S.SwimState(v=v0, anim=anim0, air=air0); sim_seed.state = st0
    sim_seed._entry_tax = False
    print(f"cold start: v={v0:.4f} anim={anim0:.4f} air={air0} state={st0}")

    print(f"planning dest={dest:.0f} allow_pump=True pump_chg={pump_chg} "
          f"max_frontier={max_frontier} max_pumps={maxpumps} ...")
    res = P.plan_min_frames(dest, v0, anim0, air0, actions=('ess', 'chg', 'neu'),
                            max_frontier=max_frontier, allow_pump=True, pump_chg=pump_chg,
                            cold_start=True, verbose=False, max_pumps=maxpumps)
    fr = res['frames']
    if fr is None:
        print("planner did not reach dest within cap"); return
    arrival = res.get('arrival', [])
    # candidate action sequences: the arrival frontier (all `fr`-frame, reach dest in sim)
    cands = [acts for (_fwd, _st, acts) in arrival] or [res['actions']]
    # de-dup, rank by fewest pumps (neu count) then fewest charges -> fewest chaotic transitions
    seen = set(); uniq = []
    for a in cands:
        key = tuple(a)
        if key not in seen:
            seen.add(key); uniq.append(a)
    uniq.sort(key=lambda a: (pump_cycles(a), a.count('chg')))
    print(f"min frames={fr}; {len(uniq)} distinct equal-frame candidates; "
          f"testing up to {maxtests} (fewest pump-cycles first)\n")

    print(" #  pumps chg  sim_net   live_net  reach%  end v/anim/air/st (live)        sync")
    best = None
    for idx, acts in enumerate(uniq[:maxtests]):
        s_end, sim_net = net_of(acts, sim_seed)
        net, vl, anl, airl, stl = live_replay(acts, slot)
        reach = 100.0 * net / dest
        reached = net >= dest * (1 - tol)
        cyc = 26.0 if stl == 54 else 23.0
        synced = (reached and abs(vl - s_end.v) <= 0.05
                  and A.animdiff(anl, s_end.anim, cyc) <= 0.05
                  and airl == s_end.air and stl == s_end.state)
        tag = "SYNC" if synced else ("reach" if reached else "")
        print(f"{idx:>2}  {pump_cycles(acts):>4} {acts.count('chg'):>4} "
              f"{sim_net:8.0f}  {net:8.0f}  {reach:5.1f}  "
              f"v={vl:8.2f} an={anl:5.2f} air={airl} st={stl}   {tag}")
        if synced and best is None:
            best = acts
            print(f"   -> FIRST SYNC at candidate {idx}; stopping.")
            break
        if reached and best is None:
            best = acts          # keep a reached-but-not-bit-exact fallback, keep searching
    D.control_pipe_quiet("clearinput")

    if best is not None:
        seqstr = ';'.join(f"{a},1" for a in best)
        with open(out, 'w') as f:
            f.write(seqstr + "\n")
        print(f"\nwrote best plan ({len(best)} frames, {pump_cycles(best)} pump-cycles) -> {out}")
    else:
        print("\nNO candidate reached dest live. Raise max_frontier/maxtests or slack.")


if __name__ == "__main__":
    main()
