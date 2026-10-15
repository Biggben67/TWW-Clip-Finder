#!/usr/bin/env python3
"""
tww_sim/swim/plan.py - Unified-DP full-swim planner (skeleton).

ONE shortest-path / forward-DP search over the whole swim, replacing the stacked
per-phase optimizers in tww_sim/swim/optimize.py. Phases are *transition functions*
on a shared SwimState (tww_sim/swim/sim.py), NOT nested search loops: adding a phase
== adding actions, ~free. See HANDOFF.md "NEXT BIG ITEM" and KNOWLEDGE.md
§5 for the agreed design.

WHY THIS IS A DAG (clean forward DP):
  `air` decreases by exactly 1 on every action (SwimState.step does `self.air -= 1`),
  so it is a monotone time axis. Layer t of the DP == all reachable states at
  air = air0 - t. No cycles, no negative edges -> a plain forward sweep, one layer
  per frame, is optimal. Because the whole layer shares the same air, `air` is NOT
  in the dominance key (sig()); only the within-layer physical state is.

DOMINANCE (the pruning that makes it tractable):
  Two states in the same layer with the same sig() (anim phase, potential speed,
  heading parity, and all the 54<->55 transition-lag fields) evolve identically
  forever. For min-frames-to-dest, among same-sig states the one with greater
  forward progress (-x) reaches the destination no later, so we keep only that one.
  sig() is reused verbatim from swim.optimize so the skeleton can't silently
  diverge from the validated min-frames optimizer (see selfcheck below).

THE BLOWUP RISK IS x598, NOT PHASE COUNT (HANDOFF):
  The neutral->ESS pump scrambles the ESS-start anim through a x598 multiply
  (setSwimMoveAnime). Do NOT globally fine-grid `anim` to chase it. The scramble is
  DETERMINISTIC: SwimState already computes the exact landed anim for each pump, so
  a pump is just a discrete branch (the 'neu'->'ess' action sequence), not a search
  dimension. We keep anim coarse on smooth ESS/neutral stretches (sig() rounds anim
  to 0.03) and let the pump branches carry their own exact anim. Frontier size is
  instrumented per layer; if a layer exceeds `max_frontier`, we prune by forward
  progress and LOG it, so a blowup is visible rather than silent.

ACTIONS / PHASES (pluggable):
  CRUISE   = ess, chg     ESS cruise + reboost turnaround (state 55)
  ENDGAME  = neu          drag-free |v| neutral dash; also encodes the ESS->neutral
                          EXIT and the neutral->ESS PUMP via the 1-frame state lag in
                          SwimState. Keeping 'neu' in the set prices the exit-phase
                          penalty automatically (KNOWLEDGE PLANNING PRINCIPLE:
                          the search holds ESS to a good exit phase when that beats
                          dashing immediately).
  FRONTEND = arrow*       charge / arrow-swim toward the target (cos-penalised charge,
                          45deg=0x2000 instant-turnaround snap). NOT YET ENABLED -
                          the sim models only a 1-D travel axis; arrow swimming needs
                          2-D heading + live validation first. See ARROW_TODO below.

Usage:
  python -m tww_sim.swim.plan dest=D [v=-1630] [air=900] [anim=18.148]
                       [phases=cruise,endgame] [max_frontier=8000] [selfcheck=1]
                       [viz=plan.html]
  Prints: per-layer frontier stats, the min-frames schedule, a dolphin seq string.
"""
import sys, math
from . import sim as S
from .coldstart import ColdStartSwimState
from .optimize import sig, seq_string, schedule, frames_to_dest_pure_ess

# ---------------------------------------------------------------------------
# Action / phase registry. A "phase" is just a named bundle of actions on the
# shared SwimState. Adding a phase = registering more action strings here.
# ---------------------------------------------------------------------------
PHASES = {
    'cruise':  ('ess', 'chg'),   # ESS hold + reboost turnaround
    'endgame': ('neu',),         # neutral dash / ESS exit / pump entry (1-frame lag)
    # 'frontend': arrow-swim PREFIX -- composed hierarchically, see plan_with_frontend.
}

ARROW_DESIGN = """\
FRONTEND is composed HIERARCHICALLY (the design's sanctioned escape hatch), NOT merged
into the per-frame cruise DP. Reason: arrow swimming needs 2-D position + facing, which
cannot be collapsed by sig() dominance (the documented x598/heading blowup). And it
NEED NOT be merged: arrow yields only disp*sin(alpha) progress/frame vs ESS's full disp,
so once speed is built it is never worth interleaving arrow back into cruise. The optimal
swim is therefore a strict PREFIX (charge/arrow + reorients) then a cruise/dash SUFFIX.
plan_with_frontend() searches the prefix (alpha-gear x arrow length), prices both
hand-off reorients via the facing-BFS (reorient_chain), and composes with the validated
plan_min_frames() cruise. Front-end per-frame physics are the live-validated arrow
formulas (arrow_charge_rate / arrow_cross_drift). See KNOWLEDGE §5.3."""


def resolve_actions(phase_names):
    acts = []
    for name in phase_names:
        if name not in PHASES:
            raise ValueError(f"unknown phase {name!r}; known: {', '.join(PHASES)}")
        for a in PHASES[name]:
            if a not in acts:
                acts.append(a)
    return tuple(acts)


# ---------------------------------------------------------------------------
# Forward DP.
# ---------------------------------------------------------------------------
class Layer:
    """One air-layer of the DP frontier: sig -> best node, plus stats."""
    __slots__ = ('nodes', 'index_of', 'capped')

    def __init__(self):
        self.nodes = []        # list of (forward, state, parent_idx, action)
        self.index_of = {}     # sig -> position in self.nodes
        self.capped = False

    def offer(self, fwd, state, parent_idx, action):
        """Insert with dominance: keep the max-forward node per sig bucket. The pump
        count is part of the key so a low-pump state isn't merged away by a higher-
        forward high-pump state at the same physical sig (preserves the pump-capped
        option). When pumps aren't tracked (_pumps absent) this collapses to plain sig."""
        k = (sig(state), getattr(state, '_pumps', 0), getattr(state, '_dipped', False))
        j = self.index_of.get(k)
        if j is None:
            self.index_of[k] = len(self.nodes)
            self.nodes.append((fwd, state, parent_idx, action))
        elif fwd > self.nodes[j][0]:
            self.nodes[j] = (fwd, state, parent_idx, action)


def _hcost(st, dest):
    """A* future-value estimate: optimistic frames remaining to reach `dest`.
    remaining_dist / best-case per-frame displacement AT THE CURRENT SPEED
    (|cos|=1, current air). Smaller = nearer the goal accounting for the speed
    you're holding -> ranking the prune by ASCENDING hcost keeps fast, far-along
    states and stops the myopic 'farthest-now' beam from discarding speed-holding
    ESS in favour of neutral states that are ahead this instant but decaying -2/fr.
    Not a strict lower bound (you could charge to go faster), so it's a PRUNING
    priority, not an admissibility certificate -- termination is still '-x>=dest'."""
    rem = dest - (-st.x)
    if rem <= 0:
        return -1.0e18                      # already there: highest priority
    best_disp = abs(S.air_drag(S.af_drag(st.v, 0.0), st.air))
    return rem / max(best_disp, 1e-6)


def plan_min_frames(dest, v, anim, air, actions=('ess', 'chg', 'neu'),
                    max_frontier=8000, cap=4000, entry_tax=True, rank='astar',
                    allow_pump=False, pump_chg=False, cold_start=False, verbose=True,
                    seed_state=None, max_pumps=None, refill_air=False, refill_until=0.0,
                    pump_eff_gate=0.0, dip_latch=False, allow_drown=False,
                    speed_gate=0.98, speed_gate_end=0.90, end_window_frames=40,
                    gate_coeff=None, cold_mrate=None):
    """Forward DP: fewest frames to reach forward distance `dest` (= -x).

    HYBRID frontier control. A layer whose dominated frontier fits in
    `max_frontier` is kept in FULL (pure dominance -> optimal for that layer).
    A layer that exceeds it is pruned to `max_frontier` and FLAGGED. So the search
    is optimal where tractable and degrades visibly (not silently) where the x598
    pump scramble blows the frontier up. Default 8000 matches the optimizer's beam.

    `rank` selects the prune priority for capped layers:
      'astar'   (default) keep smallest _hcost -> rewards holding speed; required
                for long (300+ frame) horizons or the myopic prune returns plans
                WORSE than pure ESS (neutral-heavy, speed bled off -2/fr).
      'forward' keep farthest -x -> matches swim.optimize.beam_search_to_dest
                exactly (use for selfcheck / short windows that don't cap hard).
    `cap` bounds the horizon (max frames before giving up).

    `speed_gate` (default 0.98) prunes any successor that keeps < speed_gate of the parent's |v|,
      relaxing to `speed_gate_end` (0.90) inside the last ~`end_window_frames` estimated frames so the
      terminal neutral dash still enters. Only prunes speed LOSSES (charge/reboost build |v| so are
      untouched; the only >(1-gate) losses are neutral-dip/exit af_drag frames). For the min-frames
      objective this is loss-free (speed compounds over remaining frames, so a big one-frame dump only
      pays near the end) -- validated byte-identical on the golden suite + cruise 200k/400k/500k +
      full build+reboost, ~3-7x fewer nodes on cruise. Set 0.0 to disable.
    `cold_mrate`: for a real cold start, the savestate's LOGGED move0 mRate (anchor 0.5, slate 0.5472;
      history-dependent, measure live). Seeds the bit-exact ColdStartSwimState scramble; without it a
      cold_start build uses the base +1.0 approximation and falls short live. See coldstart.py.
    `allow_drown` (default False): if False, a successor whose `air` would go < 0 is dropped -- the swim
      can only last within its ~900-frame air budget (air refill pins air to 900 in the refill zone).
      Prevents the planner emitting far-dest plans (~450k+ non-refill) that actually drown; such dests
      then correctly return frames=None (need a refill). Set True to allow the old unbounded behaviour.
    `gate_coeff` (default None): if set, the speed-gate threshold becomes CONTINUOUS -- clamp(1 -
      gate_coeff/est_frames, speed_gate_end, speed_gate) -- instead of the 2-step (speed_gate far,
      speed_gate_end inside end_window_frames). Derived from how a 1-frame |v| loss compounds over the
      remaining frames; loosens the gate smoothly as the destination nears. On tested cases it is
      loss-free but equivalent to the 2-step (the 0.98 floor is already well-placed); kept as an option.
    `dip_latch` (default False): EXPERIMENTAL fast mode -- once a state takes a neutral dip, forbid
      `chg` for the rest of that path (dipped states never re-charge in known optima). ~12-13% fewer
      expansions but LOSSY at some dests (100k: 397->398); an optional speed/quality knob, not a default.

    Returns dict: actions, frames, reached, end_state, frontier_sizes, capped_layers, stats.
    """
    rank_key = ((lambda b: _hcost(b[1], dest)) if rank == 'astar'
                else (lambda b: -b[0]))
    if seed_state is not None:
        # Continue a swim from a FULL live state (preserves facing/_warm/pending flags
        # that a pump leaves behind). `dest` is still absolute (= -x target); the caller
        # passes a state whose x already reflects progress so far. Used by the hierarchical
        # planner to re-plan the cruise SUFFIX after an inserted pump (plan_hierarchical).
        seed = seed_state.clone()
    else:
        seed = _seed_for(v, anim, air, entry_tax, cold_start, cold_mrate)
    if max_pumps is not None:
        seed._pumps = 0
    if refill_air:
        seed._refill_air = True
        seed._refill_until = refill_until
    gens = [[(0.0, seed, -1, None)]]
    frontier_sizes = [1]
    capped_layers = []
    # Search-work counters (always on, ~free): nodes_expanded = successors GENERATED (real work),
    # vs frontier_sizes = states RETAINED; breakdown by gate/dominance/cap. See tests/benchmark.
    stats = {'nodes_expanded': 0, 'nodes_gate_pruned': 0, 'nodes_dominated': 0,
             'nodes_capped': 0, 'ungated_retries': 0}

    if -seed.x >= dest:
        return _result([], 0, -seed.x, seed, gens, frontier_sizes, capped_layers, stats)

    def _build_layer(cur, apply_speed_gate):
        """Returns (layer, expanded, gate_pruned) for the caller to account only the
        layer it actually keeps (an ungated retry discards the gated attempt)."""
        layer = Layer()
        expanded = gate_pruned = 0
        for pi, (_, st, _, act_in) in enumerate(cur):
            # LIVE-FIDELITY CONSTRAINT (allow_pump=False, default): once we drop to
            # neutral we may only stay neutral -> 'neu' is a one-way terminal dash,
            # never a reversible mid-swim pump. A pump re-enters ESS, which re-scrambles
            # the anim x598; the sim CANNOT predict that landed phase, so it under-prices
            # the exit af_drag cut and the optimizer exploits phantom-cheap pumps that
            # bleed ~25% speed LIVE (spotcheck_plan.py, 2026-06-27). A single terminal
            # exit from sustained ESS has a PREDICTABLE anim and is live-frame-exact.
            # Re-enable pumps only after the pump-anim is validated live per entry-frame.
            # After a 'neu', re-entry options depend on the pump mode:
            #   allow_pump=False        -> only 'neu' (terminal dash; the old default)
            #   allow_pump, pump_chg=F  -> 'neu' or 'ess' only (CLEAN ESS pump: bit-exact
            #                              for v AND anim; charge re-entry is excluded because
            #                              its facing/setNormalSpeedF transients aren't yet
            #                              modelled to the x598-exact level pumps need).
            #   allow_pump, pump_chg=T  -> full action set (charge re-entry allowed too).
            if act_in == 'neu' and not allow_pump:
                allowed = ('neu',)
            elif (max_pumps is not None and act_in == 'neu'
                  and getattr(st, '_pumps', 0) >= max_pumps):
                allowed = ('neu',)          # pump cap reached -> terminal dash only
            elif act_in == 'neu' and not pump_chg:
                allowed = tuple(a for a in actions if a != 'chg')
            else:
                allowed = actions
            # EXPERIMENTAL dip-latch: once a path dips, forbid chg for the rest of it (optima
            # never re-charge after dipping). ~13% fewer nodes, lossy at some dests. See planner.md.
            if dip_latch and getattr(st, '_dipped', False):
                allowed = tuple(a for a in allowed if a != 'chg')
            # EXPERIMENTAL: gate ESS-pump re-entry on the predicted x598-landed efficiency (peak =
            # 2nd-order robust to the scramble). 2-frame lookahead. See model/planner.md.
            if (pump_eff_gate > 0.0 and act_in == 'neu' and st.state == 54
                    and any(a != 'neu' for a in allowed)):
                probe = st.clone(); probe.step('ess'); probe.step('ess')
                landed_eff = 0.6 + 0.4 * abs(math.cos(math.pi * probe.anim / 23.0))
                if landed_eff < pump_eff_gate:
                    allowed = ('neu',)          # off-peak landing -> forbid pump, stay neutral
            for act in allowed:
                c = st.clone()
                c.step(act)
                expanded += 1
                # AIR BUDGET: swim lasts only while air >= 0 (~900-frame budget; refill pins 900 in
                # the refill zone). Drop air<0 successors -- they'd drown. See model/planner.md.
                if not allow_drown and c.air < 0:
                    continue
                # Speed-retention prune: drop successors keeping < speed_gate of parent |v| (relax to
                # speed_gate_end near the end). Prunes only losses. See model/planner.md.
                if apply_speed_gate and speed_gate > 0.0 and abs(st.v) > 1.0 and abs(c.v) < abs(st.v):
                    remaining = dest - (-c.x)
                    est_frames = remaining / max(abs(c.v), 1.0)
                    if gate_coeff is not None:
                        # CONTINUOUS gate: clamp(1 - gate_coeff/est_frames, end, gate) -- loosens as
                        # dest nears (a loss compounds over est_frames). See model/planner.md.
                        thr = min(speed_gate, max(speed_gate_end,
                                                  1.0 - gate_coeff / max(est_frames, 1.0)))
                    else:
                        thr = speed_gate_end if est_frames < end_window_frames else speed_gate
                    if abs(c.v) < thr * abs(st.v):
                        gate_pruned += 1
                        continue
                if max_pumps is not None:
                    # a pump = re-entry from neutral back into a swim input (neu -> ess/chg)
                    c._pumps = getattr(st, '_pumps', 0) + (1 if act_in == 'neu' and act != 'neu' else 0)
                if dip_latch and (act == 'neu' or getattr(st, '_dipped', False)):
                    c._dipped = True        # sticky: latch persists through the dip's ess re-entry
                layer.offer(-c.x, c, pi, act)
        return layer, expanded, gate_pruned

    for t in range(1, cap + 1):
        cur = gens[-1]
        layer, expanded, gate_pruned = _build_layer(cur, speed_gate > 0.0)
        if not layer.nodes and speed_gate > 0.0:
            # gate would dead-end the frontier -> retry ungated (discard the gated attempt's counts)
            layer, expanded, gate_pruned = _build_layer(cur, False)
            stats['ungated_retries'] += 1
        if not layer.nodes:
            # Frontier died (all successors drowned, air<0) -> dest unreachable within the air
            # budget: stop and report not-reached (frames=None). Needs a refill. See planner.md.
            break
        stats['nodes_expanded'] += expanded
        stats['nodes_gate_pruned'] += gate_pruned
        # offered (= expanded - gate_pruned) minus unique sigs kept = merged by dominance
        stats['nodes_dominated'] += (expanded - gate_pruned) - len(layer.nodes)
        ranked = sorted(layer.nodes, key=rank_key)
        if len(ranked) > max_frontier:
            stats['nodes_capped'] += len(ranked) - max_frontier
            ranked = ranked[:max_frontier]
            layer.capped = True
            capped_layers.append((t, len(layer.nodes)))
        gens.append(ranked)
        frontier_sizes.append(len(ranked))

        best_i = max(range(len(ranked)), key=lambda i: ranked[i][0])
        if ranked[best_i][0] >= dest:
            acts = _backtrack(gens, best_i)
            res = _result(acts, t, ranked[best_i][0], ranked[best_i][1],
                          gens, frontier_sizes, capped_layers, stats)
            # ARRIVAL FRONTIER: every node in the terminating layer that reached `dest`,
            # with its full state and action path. The crossover hierarchical planner
            # continues each of these pump-free toward the real (far) destination, so it is
            # NOT locked into the single min-frames build endpoint (a fast build endpoint
            # may carry a worse cruise phase than a 1-frame-slower one). Built lazily.
            res['arrival'] = [(gens[t][i][0], gens[t][i][1], _backtrack(gens, i))
                              for i in range(len(gens[t])) if gens[t][i][0] >= dest]
            return res

    best_i = max(range(len(gens[-1])), key=lambda i: gens[-1][i][0])
    res = _result(_backtrack(gens, best_i), None, gens[-1][best_i][0],
                  gens[-1][best_i][1], gens, frontier_sizes, capped_layers, stats)
    res['arrival'] = []
    return res


def _backtrack(gens, end_i):
    actions = []
    i = end_i
    for t in range(len(gens) - 1, 0, -1):
        _, _, pi, act = gens[t][i]
        actions.append(act)
        i = pi
    actions.reverse()
    return actions


def _result(actions, frames, reached, end_state, gens, frontier_sizes, capped_layers,
            stats=None):
    sizes = frontier_sizes or [0]
    st = dict(stats or {})
    st['frontier_max'] = max(sizes)
    st['frontier_peak_layer'] = sizes.index(max(sizes))
    st['frontier_sum'] = sum(sizes)          # states RETAINED (cf. nodes_expanded = generated)
    st['layers'] = len(sizes)
    st['capped_layers'] = len(capped_layers)
    return {
        'actions': actions, 'frames': frames, 'reached': reached,
        'end_state': end_state, 'frontier_sizes': frontier_sizes,
        'capped_layers': capped_layers, 'stats': st,
    }


# ---------------------------------------------------------------------------
# HIERARCHICAL pump planner (the design's sanctioned escape hatch) — CROSSOVER design.
#
# WHY the flat allow_pump DP is intractable: the x598 pump scramble lands a DISTINCT anim
# phase per pump entry, so the frontier saturates at max_frontier on EVERY layer and
# dominance cannot merge them (genuinely distinct futures — empirically confirmed 2026-06-27:
# coarsening sig()'s anim AND v buckets leaves the frontier pinned at 8000). So pumps cannot
# be priced by dominance; the flat pump DP just runs the saturated frontier for the WHOLE
# horizon (cold dest=100000: 511s, 388/396 layers capped) and is far too slow for 200k.
#
# KEY EMPIRICAL FACT that makes the decomposition work: pumps only pay off in the LOW-SPEED
# BUILD. At sustained cruise (v≈-1630) pumps save ZERO frames (measured: cruise dest=60000
# pump vs no-pump both 41 fr). The flat DP wastes its entire long-cruise horizon carrying a
# saturated pumped frontier for nothing. (Also empirically: greedily INSERTING pumps into the
# pump-free optimum never improves it — the gain needs co-designed charge+pump timing, not a
# perturbation. So insert-into-baseline is the WRONG decomposition; crossover is the right one.)
#
# CROSSOVER: run the expensive pumped DP ONLY over a short build distance `build_dist` (the
# low-speed regime where pumps live), then continue PUMP-FREE (fast, near-unsaturated) over
# the long cruise remainder. The build's whole arrival frontier is carried forward (a slightly
# slower build endpoint can carry a better cruise phase), screened with the pure-ESS surrogate,
# and only the top `refine` get the exact cruise DP. Bounded build horizon => bounded cost;
# pumps are still priced by the exact pumped DP where they matter.
# ---------------------------------------------------------------------------
def _seed_for(v, anim, air, entry_tax, cold_start, cold_mrate=None):
    """Build the DP seed. For a real cold start, pass the savestate's LOGGED move0 mRate as
    `cold_mrate` to seed the bit-exact ColdStartSwimState scramble (the anchor's is 0.5, the slate's
    0.5472 -- it is history-dependent and must be measured live, see coldstart.py). Without it the
    seed falls back to the base SwimState's approximate +1.0 scramble (builds fall short live)."""
    if cold_start and cold_mrate is not None:
        seed = ColdStartSwimState(v=v, anim=anim, air=air, mrate=cold_mrate)
    else:
        seed = S.SwimState(v=v, anim=anim, air=air)
    seed._entry_tax = entry_tax
    if cold_start:
        seed.state = 54
        seed._entry_tax = False
    return seed


def _trajectory(seed, actions):
    """Return the list of states BEFORE each action (states[i] is the state from which
    actions[i] is taken), plus the final state. states[0] is a clone of the seed."""
    st = seed.clone()
    states = []
    for a in actions:
        states.append(st.clone())
        st.step(a)
    states.append(st.clone())          # terminal state (after the last action)
    return states


def plan_hierarchical(dest, v, anim, air, cold_start=False, entry_tax=None,
                      build_dist=None, max_frontier=8000, cruise_frontier=4000,
                      cap=4000, rank='astar', refine=16, verbose=True, cold_mrate=None):
    """Crossover hierarchical plan: pumped low-speed BUILD + pump-free cruise SUFFIX.
    Returns the plan_min_frames result-dict shape plus 'baseline_frames' (pure-ESS-to-dest),
    'build_frames'/'build_dist', and 'cruise_frames'.

    build_dist: distance over which pumps are searched (the low-speed regime). Default scales
        with the seed: cold start needs ~the first few k to reach cruise; a fast cruise seed
        needs none. If build_dist >= dest the whole swim is the pumped DP (small dest)."""
    if entry_tax is None:
        entry_tax = not cold_start
    if build_dist is None:
        # Cold start floats at v=0 and reaches cruise by ~a few thousand units; a fast seed is
        # already cruising so pumps never help (build_dist 0 -> pure cruise DP). Heuristic, and
        # overridable. Capped so a small dest just runs the whole thing as the pumped DP.
        build_dist = 6000 if (cold_start or abs(v) < 800) else 0
    build_dist = min(build_dist, dest)

    bn, _ = frames_to_dest_pure_ess(dest, v, anim, air)   # pure-ESS baseline for reporting

    # --- BUILD: full pumped DP over the bounded low-speed distance ---
    if build_dist > 0:
        build = plan_min_frames(build_dist, v, anim, air, actions=('ess', 'chg', 'neu'),
                                max_frontier=max_frontier, cap=cap, rank=rank,
                                entry_tax=entry_tax, cold_start=cold_start, cold_mrate=cold_mrate,
                                allow_pump=True, pump_chg=True, verbose=False)
        if build['frames'] is None:
            return build
        if build_dist >= dest:                # build covered the whole swim
            build['baseline_frames'] = bn
            build['build_frames'] = build['frames']
            build['build_dist'] = build_dist
            build['cruise_frames'] = 0
            return build
        arrival = build.get('arrival') or [(build['reached'], build['end_state'],
                                            build['actions'])]
        build_frames_best = build['frames']
    else:
        seed = _seed_for(v, anim, air, entry_tax, cold_start, cold_mrate)
        arrival = [(-seed.x, seed, [])]
        build_frames_best = 0

    # --- CRUISE: continue each build endpoint pump-free; screen then exact top-refine ---
    scr = []                                   # (surrogate_total, build_frames, state, acts)
    for fwd, st, acts in arrival:
        if -st.x >= dest:
            scr.append((len(acts), len(acts), st, acts))
            continue
        sn, _ = frames_to_dest_pure_ess(dest, st.v, st.anim, st.air)
        if sn is None:
            continue
        scr.append((len(acts) + sn, len(acts), st, acts))
    scr.sort(key=lambda c: c[0])

    best = None                                # (total, build_acts, cruise_acts, cruise_fr)
    for surro, bfr, st, acts in scr[:int(refine)]:
        if best is not None and surro >= best[0]:
            break
        if -st.x >= dest:
            total = len(acts)
            if best is None or total < best[0]:
                best = (total, acts, [], 0)
            continue
        cr = plan_min_frames(dest, st.v, st.anim, st.air, seed_state=st,
                             actions=('ess', 'chg', 'neu'), max_frontier=cruise_frontier,
                             cap=cap, rank=rank, allow_pump=False, verbose=False)
        if cr['frames'] is None:
            continue
        total = len(acts) + cr['frames']
        if best is None or total < best[0]:
            best = (total, acts, list(cr['actions']), cr['frames'])
        if verbose:
            print(f"  build={len(acts)}fr -> cruise={cr['frames']}fr total={total}")
    if best is None:
        return {'actions': None, 'frames': None, 'reached': 0.0, 'end_state': None,
                'frontier_sizes': [], 'capped_layers': [], 'baseline_frames': bn}

    total, build_acts, cruise_acts, cruise_fr = best
    seed = _seed_for(v, anim, air, entry_tax, cold_start, cold_mrate)
    end = _trajectory(seed, build_acts + cruise_acts)[-1]
    out = _result(build_acts + cruise_acts, total, -end.x, end, None, [], [])
    out['baseline_frames'] = bn
    out['build_frames'] = len(build_acts)
    out['build_dist'] = build_dist
    out['cruise_frames'] = cruise_fr
    return out


# ---------------------------------------------------------------------------
# FRONT-END (charge -> arrow-swim) prefix, composed with the cruise DP.
# ---------------------------------------------------------------------------
# Flat cruise speed (units/fr) for the stage-1 RANKING surrogate only (~380 from full-cruise
# DPs); ranking-only -- the exact cruise DP picks the winner in stage 2, so rough is fine.
_CRUISE_V_EFF = 380.0

def arrow_schedules(n, alpha_max=S.ARROW_ALPHA_MAX_DEG):
    """Candidate alpha SHAPES over n arrow frames. The optimal control (Pontryagin:
    sin a* = c*v/(12*lambda)) is a ramp from ~0 (bank speed early — progress rate
    scales with |v|) up toward the tip-over cap; the exact knee depends on how the
    end-speed trades against the cruise leg, so we offer the family and let the
    end-speed-aware surrogate pick. Shapes: pure-charge (all 0 — degenerate, handled by
    n_arrow=0), flat-max, linear ramps with varied start, and bang-bang splits."""
    if n <= 0:
        return [[]]
    out = [[alpha_max] * n]                                  # flat at the cap
    for s in (0.0, 0.3, 0.6):                                # linear ramp 0->cap from s*n
        k = int(s * n)
        out.append([0.0] * k + [alpha_max * (i / max(1, n - k - 1))
                                for i in range(n - k)])
    for s in (0.4, 0.6, 0.8):                                # bang-bang: charge then cap
        k = int(s * n)
        out.append([0.0] * k + [alpha_max] * (n - k))
    # dedupe identical schedules (rounded)
    seen, uniq = set(), []
    for sch in out:
        key = tuple(round(a, 1) for a in sch)
        if key not in seen:
            seen.add(key)
            uniq.append(sch)
    return uniq


ESS_STICK = (128, 110)          # cruise ESS hold stick (matches spotcheck/dolphin)


ARROW_DRIFT_DOWN = True          # Y-bias side for the slate's WEST drift


def frontend_prefix(v, anim, air, chain_in, arrow_alphas, cruise_facing,
                    facing0, cam_deg, target_bearing):
    """Step the front-end prefix through the LIVE-VALIDATED ArrowState stepper, which
    models the 1-frame snap lag, the arrow spin-up, the per-snap 3·cos(Δ) charge, and
    the tilt drift NATIVELY. Stick sequence:
      reorient-in chain  +  arrow ramp (arrow_sticks per alpha)  +  reorient-out chain
      +  ONE ESS settle frame.
    Two live-pinned subtleties (2026-06-27):
    - TILTED-AXIS hand-off: an alpha-tilt arrow ends facing on the TILTED axis
      (axis +/- alpha), not the nominal axis, so the reorient-OUT chain is computed from
      the ACTUAL post-arrow facing (read off ArrowState, incl. the still-pending last
      snap) -- else a R-out snap mis-fires into a slow gradual turn.
    - 1-FRAME-LAG settle: the final reorient snap lands one frame after its input, so a
      trailing ESS frame is held to let facing reach the cruise heading before SwimState
      cruise begins (clean hand-off).
    Returns (frames, v, anim, air, progress, n_out). progress = net displacement projected
    onto the target bearing (real geometry, includes reorient/arrow drift)."""
    st = S.ArrowState(v=v, anim=anim, air=air, facing_deg=facing0, cam_deg=cam_deg)
    for (sx, sy) in chain_in:
        st.step(sx, sy)
    for i, a in enumerate(arrow_alphas):
        st.step(*S.arrow_sticks(a, drift_down=ARROW_DRIFT_DOWN)[i % 2])
    # reorient OUT from the actual (tilted) facing -- account for the pending last snap
    settled = st._pending_facing if st._pending_facing is not None else st.facing
    chain_out = S.reorient_chain(settled, cruise_facing, cam_deg) or []
    for (sx, sy) in chain_out:
        st.step(sx, sy)
    st.step(*ESS_STICK)                                  # settle: final snap lands -> cruise
    frames = len(chain_in) + len(arrow_alphas) + len(chain_out) + 1
    tb = math.radians(target_bearing)
    prog = st.x * math.cos(tb) + st.z * math.sin(tb)
    return frames, st.v, st.anim, st.air, prog, len(chain_out)


def plan_with_frontend(dest, v, anim, air, facing0=90.0, target_bearing=180.0,
                       cam_deg=270.0, arrow_lengths=range(0, 81, 5),
                       max_frontier=8000, cap=4000,
                       rank='astar', refine=4, verbose=True):
    """Plan a WHOLE swim: charge/arrow PREFIX -> reorient -> ESS cruise/dash SUFFIX.

    Searches (alpha-gear x arrow length); for each, prices the two mandatory reorient
    hand-offs via the facing-BFS, steps the front-end with the validated arrow physics,
    then runs the cruise DP (plan_min_frames) on the remaining distance from the built-up
    (v, anim, air). Returns the min-total-frames composite. The n_arrow=0 candidate (no
    arrowing, just the unavoidable reorients) is the natural baseline; arrowing wins only
    when its early progress beats the cruise frames it costs.

    Geometry (rotation-invariant; defaults match the slate): the arrow charge axis is
    PERP to the target so drift runs toward it; cruise faces AWAY from target (ESS travels
    backward toward it). facing/world map: move_bearing = cam - facing."""
    axis_facing = (cam_deg - target_bearing - 90.0) % 360.0   # charge axis _|_ target
    cruise_facing = (cam_deg - target_bearing) % 360.0        # face away -> ESS toward
    chain_in = S.reorient_chain(facing0, axis_facing, cam_deg)
    if chain_in is None:
        if verbose:
            print("frontend: reorient unreachable; falling back to pure cruise")
        return None
    n_in = len(chain_in)

    # Stage 1: rank (length x shape) by a cheap monotone surrogate (prefix frames + flat-speed
    # remainder); the exact cruise DP picks the winner in stage 2. n_arrow=0 is always refined.
    cands = []
    baseline = None
    for n_arrow in arrow_lengths:
        shapes = arrow_schedules(n_arrow) if n_arrow > 0 else [[]]
        for sched in shapes:
            fr, fv, fa, fair, prog, n_out = frontend_prefix(
                v, anim, air, chain_in, sched, cruise_facing, facing0, cam_deg,
                target_bearing)
            if fair <= 0 or prog >= dest:
                continue                       # ran out of air / overshoot in prefix
            surro = fr + (dest - prog) / _CRUISE_V_EFF
            cand = (surro, n_arrow, fr, fv, fa, fair, prog, sched, n_out)
            cands.append(cand)
            if n_arrow == 0 and (baseline is None or surro < baseline[0]):
                baseline = cand
    if not cands:
        return None
    cands.sort()
    refine = int(refine)

    # Stage 2: exact cruise DP on the top candidates + the baseline; keep min exact total.
    to_refine = cands[:refine]
    if baseline is not None and baseline not in to_refine:
        to_refine.append(baseline)
    best = None
    base_total = None
    tried = []
    for surro, n_arrow, fr, fv, fa, fair, prog, sched, n_out in to_refine:
        cr = plan_min_frames(dest - prog, fv, fa, fair, actions=('ess', 'chg', 'neu'),
                             max_frontier=max_frontier, cap=cap, rank=rank,
                             entry_tax=True, allow_pump=False, verbose=False)
        if cr['frames'] is None:
            continue
        total = fr + cr['frames']
        tried.append((total, n_arrow, fr, prog, cr['frames']))
        if n_arrow == 0 and (base_total is None or total < base_total):
            base_total = total          # no-arrow composite = apples-to-apples baseline
        if best is None or total < best['total']:
            best = {'total': total, 'n_arrow': n_arrow, 'schedule': sched,
                    'n_in': n_in, 'n_out': n_out, 'prefix_frames': fr,
                    'progress': prog, 'cruise_frames': cr['frames'],
                    'cruise': cr, 'prefix_end': (fv, fa, fair)}
    if best is None:
        return None
    best['tried'] = sorted(tried)
    best['base_total'] = base_total     # frames for the no-arrow (reorients-only) plan
    best['surrogate_top'] = [c[:7] for c in cands[:refine]]
    return best


# ---------------------------------------------------------------------------
# Reporting / CLI.
# ---------------------------------------------------------------------------
def report_frontier(sizes, capped_layers):
    if not sizes:
        return
    mx = max(sizes)
    mx_layer = sizes.index(mx)
    avg = sum(sizes) / len(sizes)
    print(f"frontier: layers={len(sizes)} max={mx} (@layer {mx_layer}) "
          f"avg={avg:.0f}")
    if capped_layers:
        print(f"  {len(capped_layers)} layer(s) hit max_frontier (A* rank prune) -> heuristic. "
              f"Frame count is empirically INSENSITIVE to the cap (discrete game = many equal-"
              f"frame solutions); raise max_frontier only to chase the last frame or two.")


def selfcheck(dest, v, anim, air):
    """Prove the skeleton hasn't regressed the validated min-frames optimizer:
    the DP (cruise+endgame) must match swim.optimize.beam_search_to_dest frame
    count on the same seed. (That result was live-confirmed frame-exact, 2026-06-27.)"""
    from .optimize import beam_search_to_dest
    r = plan_min_frames(dest, v, anim, air, actions=('ess', 'chg', 'neu'),
                        rank='forward', allow_pump=True, verbose=False)
    _, ofr, _, _ = beam_search_to_dest(dest, v, anim, air, beam=8000)
    ok = (r['frames'] == ofr)
    print(f"selfcheck vs beam_search_to_dest: plan={r['frames']} beam={ofr} "
          f"{'OK' if ok else 'MISMATCH'}")
    return ok


def main():
    opts = {}
    for tok in sys.argv[1:]:
        k, _, val = tok.partition('=')
        opts[k] = val

    if 'dest' not in opts:
        print(__doc__)
        print("ARROW_DESIGN:\n" + ARROW_DESIGN)
        sys.exit(1)

    dest = float(opts['dest'])
    v = float(opts.get('v', '-1630'))
    air = int(opts.get('air', '900'))
    anim = float(opts.get('anim', '18.148'))
    # HEURISTIC FRONTIER default 2000 = the DOMINANT sweet spot (optimal in 10/10 swept dests,
    # ~4x faster than 8000, and non-monotone so bigger can be WORSE). See knowledge/model/planner.md.
    max_frontier = int(opts.get('max_frontier', '2000'))
    cap = int(opts.get('cap', '4000'))
    rank = opts.get('rank', 'astar')
    allow_pump = opts.get('pump', '0') != '0'   # mid-swim pumps (NOT live-faithful yet)
    cold_start = opts.get('cold', '0') != '0'   # seed state 54 (real cold start, entry_tax off)
    entry_tax = opts.get('entry_tax', '0' if cold_start else '1') != '0'
    phase_names = opts.get('phases', 'cruise,endgame').split(',')
    actions = resolve_actions(phase_names)

    if opts.get('selfcheck', '0') != '0':
        selfcheck(dest, v, anim, air)

    if opts.get('frontend', '0') != '0':
        facing0 = float(opts.get('facing', '90'))
        tgt = float(opts.get('target', '180'))
        cam = float(opts.get('cam', '270'))
        b = plan_with_frontend(dest, v, anim, air, facing0=facing0,
                               target_bearing=tgt, cam_deg=cam,
                               max_frontier=max_frontier, cap=cap, rank=rank)
        if b is None:
            print("frontend: no composite plan found")
            return
        bn = b.get('base_total')
        if bn is not None:
            print(f"baseline no-arrow composite (reorients + cruise) to dest "
                  f"{dest:.0f}: {bn} fr")
        saved = (f"  ({bn - b['total']:+d} fr vs no-arrow baseline)"
                 if bn is not None else "")
        sch = b['schedule']
        sch_str = (f"{sch[0]:.0f}->{sch[-1]:.0f} deg ramp" if sch else "none")
        print(f"\nFRONTEND PLAN: {b['total']} frames total{saved}")
        print(f"  prefix {b['prefix_frames']} fr = {b['n_in']} reorient-in + "
              f"{b['n_arrow']} arrow (alpha {sch_str}) + {b['n_out']} reorient-out")
        if sch:
            print(f"  alpha schedule: [{', '.join(f'{a:.0f}' for a in sch)}]")
        print(f"  arrow progress toward target: {b['progress']:.0f} units; "
              f"prefix end v={b['prefix_end'][0]:.1f} anim={b['prefix_end'][1]:.2f} "
              f"air={b['prefix_end'][2]}")
        print(f"  cruise {b['cruise_frames']} fr over remaining "
              f"{dest - b['progress']:.0f} units")
        ca = b['cruise']['actions']
        print(f"  cruise: {ca.count('chg')} charge, {ca.count('neu')} neutral, "
              f"{b['cruise_frames'] - ca.count('chg') - ca.count('neu')} ESS")
        print("  cruise seq:", seq_string(ca))
        print("  alt candidates (total,n_arrow,prefix,prog,cruise):", b['tried'][:5])
        return

    bn, bx = frames_to_dest_pure_ess(dest, v, anim, air)
    bn_str = f"{bn} fr" if bn is not None else f">cap (reached {bx:.0f})"
    print(f"baseline pure ESS to dest {dest:.0f}: {bn_str}")
    print(f"phases={'+'.join(phase_names)} actions={actions} "
          f"max_frontier={max_frontier}")

    r = plan_min_frames(dest, v, anim, air, actions=actions,
                        max_frontier=max_frontier, cap=cap, rank=rank,
                        allow_pump=allow_pump, entry_tax=entry_tax, cold_start=cold_start)
    report_frontier(r['frontier_sizes'], r['capped_layers'])

    if r['frames'] is None:
        print(f"NOT REACHED within cap={cap} (got {r['reached']:.0f} of {dest:.0f})")
        return

    acts = r['actions']
    nb, nn = acts.count('chg'), acts.count('neu')
    saved = f"  ({bn - r['frames']:+d} fr vs pure ESS)" if bn is not None else ""
    print(f"PLAN: {r['frames']} frames to reach {r['reached']:.0f}{saved}")
    print(f"  {nb} charge, {nn} neutral, {r['frames'] - nb - nn} ESS frames")
    print("bursts (start_frame, length):", schedule(acts))
    print("seq:", seq_string(acts))

    if 'viz' in opts:
        rb = S.run_trace(acts, v, anim, air, entry_tax=True)
        be = S.run_trace(['ess'] * (bn or r['frames']), v, anim, air, entry_tax=True)
        S.emit_viz(opts['viz'],
                   [{"name": "pure ESS", "color": "#58a6ff", "rows": be},
                    {"name": "plan", "color": "#3fb950", "rows": rb}])


if __name__ == '__main__':
    main()
