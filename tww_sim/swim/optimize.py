#!/usr/bin/env python3
"""
tww_sim/swim/optimize.py - Beam-search the optimal ESS/charge (reboost) schedule.

Uses the frame-exact physics in tww_sim/swim/sim.py to search the full per-frame
decision space {ESS, charge} over a window, maximizing NET forward displacement
(signed position along the swim axis, so reboost reversal frames are penalized
exactly). Discovers boost count / timing / length as a solved optimum rather than
hand-tuned guesses. Outputs the schedule + a dolphin_mem.py seq string to verify
the winner live.

Two objectives:
  - MAX-DISTANCE (fixed window): maximize forward progress over `frames` frames.
  - MIN-FRAMES (dest=D): fewest frames to reach forward distance D. Adds 'neu' to the
    action set so the endgame can switch to a drag-free |v| neutral dash once holding
    speed stops paying (neutral moves full |v| but decays -2/fr; ESS holds speed but
    af_drag/air_drag cut its per-frame move, especially at low air).

Usage:
  python -m tww_sim.swim.optimize [frames=200] [v=-1630] [air=900] [anim=18.148]
                           [beam=4000] [viz=opt.html]
  python -m tww_sim.swim.optimize dest=D [v=] [air=] [anim=] [beam=] [cap=2000]
                           [neu=0|1] [viz=opt.html]

Net forward progress = -x (sim ESS moves toward -x at heading 0; charge flips heading
180 with the 1-frame lag, so reversed frames subtract). Air = start_air - t each frame.
"""
import sys, math
from . import sim as S

def sig(st):
    """Bucket key: distinct physical state. Keeps anim-phase diversity so a state
    that just paid a boost cost (lower x, but better anim) isn't pruned by raw x.
    Includes the 54<->55 transition-lag fields so neutral/ESS/pump states that look
    alike in (anim,v) but carry different pending transitions are NOT merged.
    Air IS in the key. Without refill every action decrements air by 1 so the whole
    layer shares one air value -> air is a per-layer constant and adding it to the key
    is a no-op (bucketing byte-identical, all validated baselines unchanged). WITH air
    refill (air pinned to 900 while -x <= refill_until) air is NO LONGER layer-constant:
    states that crossed the refill boundary at different frames carry different air and
    different futures, so omitting air would unsoundly MERGE them. Keeping air in the key
    makes the refill regime correct at zero cost to the non-refill case."""
    return (round(st.anim / 0.03), round(st.v / 0.1),
            st._pending_flip, round(st._pending_gain),
            int(round(st.heading / math.pi)) & 1, st._entry_tax,
            st.state, st._pending_state, st._just_released, st._skip_advance, st.air)

def beam_search(frames, v, anim, air, beam=4000, entry_tax=True):
    seed = S.SwimState(v=v, anim=anim, air=air); seed._entry_tax = entry_tax
    # forward progress = -x (negative speed swims toward -x). Maximize forward.
    # nodes: (forward, state, parent_idx, action)
    gens = [[(0.0, seed, -1, None)]]
    for _ in range(frames):
        cur = gens[-1]
        buckets = {}  # sig -> (forward, state, parent_idx, action)
        for pi, (fwd, st, _, _) in enumerate(cur):
            for act in ('ess', 'chg'):
                c = st.clone()
                c.step(act)
                k = sig(c)
                fwd_c = -c.x
                prev = buckets.get(k)
                if prev is None or fwd_c > prev[0]:
                    buckets[k] = (fwd_c, c, pi, act)
        ranked = sorted(buckets.values(), key=lambda t: -t[0])[:beam]
        gens.append([(fwd, st, pi, act) for (fwd, st, pi, act) in ranked])
    best_i = max(range(len(gens[-1])), key=lambda i: gens[-1][i][0])
    actions = []
    i = best_i
    for t in range(len(gens) - 1, 0, -1):
        x, st, pi, act = gens[t][i]
        actions.append(act)
        i = pi
    actions.reverse()
    return actions, gens[-1][best_i][0], gens[-1][best_i][1]

def _backtrack(gens, end_i):
    """Walk parent pointers from gens[-1][end_i] back to the seed; return actions."""
    actions = []
    i = end_i
    for t in range(len(gens) - 1, 0, -1):
        _, _, pi, act = gens[t][i]
        actions.append(act)
        i = pi
    actions.reverse()
    return actions

def frames_to_dest_pure_ess(dest, v, anim, air, cap=5000, entry_tax=True):
    """Baseline: how many pure-ESS frames to cover forward distance `dest`."""
    s = S.SwimState(v=v, anim=anim, air=air); s._entry_tax = entry_tax
    for t in range(1, cap + 1):
        s.step('ess')
        if -s.x >= dest:
            return t, -s.x
    return None, -s.x

def beam_search_to_dest(dest, v, anim, air, beam=4000, cap=2000,
                        actions=('ess', 'chg', 'neu'), entry_tax=True):
    """Minimize the number of frames to reach forward distance `dest` (= -x).

    Same beam machinery as beam_search, but the horizon is open: each generation we
    expand the frontier, then STOP as soon as any node has reached `dest`. Ranking by
    forward (-x) within sig-buckets is valid dominance for this objective too: among
    states identical in (anim, v, pending...), the one nearer the destination reaches
    it no later. Adding 'neu' lets the endgame switch to a drag-free |v| dash once
    holding speed no longer pays off (neutral moves full |v| but decays -2/fr)."""
    seed = S.SwimState(v=v, anim=anim, air=air); seed._entry_tax = entry_tax
    if -seed.x >= dest:
        return [], 0, -seed.x, seed
    gens = [[(0.0, seed, -1, None)]]
    for t in range(1, cap + 1):
        cur = gens[-1]
        buckets = {}
        for pi, (_, st, _, _) in enumerate(cur):
            for act in actions:
                c = st.clone()
                c.step(act)
                k = sig(c)
                fwd_c = -c.x
                prev = buckets.get(k)
                if prev is None or fwd_c > prev[0]:
                    buckets[k] = (fwd_c, c, pi, act)
        ranked = sorted(buckets.values(), key=lambda b: -b[0])[:beam]
        gens.append([(fwd, st, pi, act) for (fwd, st, pi, act) in ranked])
        # reached? pick the closest node; if it covers dest we're done at frame t.
        best_i = max(range(len(ranked)), key=lambda i: gens[-1][i][0])
        if gens[-1][best_i][0] >= dest:
            return _backtrack(gens, best_i), t, gens[-1][best_i][0], gens[-1][best_i][1]
    # never reached within cap; return the furthest we got
    best_i = max(range(len(gens[-1])), key=lambda i: gens[-1][i][0])
    return _backtrack(gens, best_i), None, gens[-1][best_i][0], gens[-1][best_i][1]

def schedule(actions):
    """compress action list into boost bursts: list of (start_frame_1based, length)."""
    bursts = []
    i = 0
    while i < len(actions):
        if actions[i] == 'chg':
            j = i
            while j < len(actions) and actions[j] == 'chg':
                j += 1
            bursts.append((i + 1, j - i))
            i = j
        else:
            i += 1
    return bursts

def seq_string(actions):
    """compress to dolphin_mem.py / sim seq form: 'ess,N;chg,M;...'"""
    out = []
    i = 0
    while i < len(actions):
        j = i
        while j < len(actions) and actions[j] == actions[i]:
            j += 1
        out.append(f"{actions[i]},{j - i}")
        i = j
    return ";".join(out)

def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('=')
        opts[k] = val
    frames = int(opts.get('frames', '200'))
    v = float(opts.get('v', '-1630')); air = int(opts.get('air', '900'))
    anim = float(opts.get('anim', '18.148')); beam = int(opts.get('beam', '4000'))

    if 'dest' in opts:
        dest = float(opts['dest'])
        cap = int(opts.get('cap', '2000'))
        allow_neu = opts.get('neu', '1') != '0'
        acts_set = ('ess', 'chg', 'neu') if allow_neu else ('ess', 'chg')

        bn, bx = frames_to_dest_pure_ess(dest, v, anim, air)
        bn_str = f"{bn} fr" if bn is not None else f">cap (reached {bx:.0f})"
        print(f"baseline pure ESS to dest {dest:.0f}: {bn_str}")

        acts, nfr, reached, _ = beam_search_to_dest(
            dest, v, anim, air, beam=beam, cap=cap, actions=acts_set)
        if nfr is None:
            print(f"NOT REACHED within cap={cap} (got {reached:.0f} of {dest:.0f})")
            return
        nb = acts.count('chg'); nn = acts.count('neu')
        saved = (f"  ({bn - nfr:+d} fr vs pure ESS)" if bn is not None else "")
        print(f"OPTIMAL (beam={beam}, actions={'+'.join(acts_set)}): "
              f"{nfr} frames to reach {reached:.0f}{saved}")
        print(f"  {nb} charge frames, {nn} neutral frames, "
              f"{nfr - nb - nn} ESS frames")
        print("bursts (start_frame, length):", schedule(acts))
        print("seq:", seq_string(acts))
        if 'viz' in opts:
            rb = S.run_trace(acts, v, anim, air, entry_tax=True)
            be = S.run_trace(['ess'] * nfr, v, anim, air, entry_tax=True)
            S.emit_viz(opts['viz'],
                       [{"name": "pure ESS", "color": "#58a6ff", "rows": be},
                        {"name": "min-frames", "color": "#3fb950", "rows": rb}])
        return

    base = S.run_trace(['ess'] * frames, v, anim, air, entry_tax=True)
    base_net = -base[-1]['x']  # forward progress (-x)
    print(f"baseline pure ESS: net {base_net:.0f}  net/fr {base_net/frames:.2f}")

    acts, opt_net, _ = beam_search(frames, v, anim, air, beam=beam)
    nb = acts.count('chg')
    print(f"OPTIMAL (beam={beam}): net {opt_net:.0f}  net/fr {opt_net/frames:.2f}  "
          f"gain vs ESS {(opt_net/base_net-1)*100:+.2f}%  ({nb} charge frames)")
    print("bursts (start_frame, length):", schedule(acts))
    print("seq:", seq_string(acts))

    if 'viz' in opts:
        rb = S.run_trace(acts, v, anim, air, entry_tax=True)
        S.emit_viz(opts['viz'], [{"name": "pure ESS", "color": "#58a6ff", "rows": base},
                                 {"name": "optimal", "color": "#3fb950", "rows": rb}])

if __name__ == '__main__':
    main()
