"""Canonical planner-benchmark cases + known-best table.

A "case" is a fully-specified, reproducible planner invocation: a planner function
name plus the COMPLETE kwargs it is called with. Because the planner is deterministic
(no RNG), the param dict is a reproduction recipe -- re-running it on the same code
yields the identical plan (see record.reproduce). Every field the planner reads must
live in `params` so the record is self-contained.

Tiers (which cases run, by intent -- NOT a difference in what's recorded):
  smoke  fast pump-mode cases; run after any planner change. Small dests still exercise
         the pump path (frontier saturation, and dips where present) at low runtime.
  full   the real destinations in pump mode -- the mode that produces the SHIPPED
         optimal plan. Slow (200k pump ~8 min); run before shipping / when chasing
         frames or search speed. `known_best` is asserted here.

`known_best` (frames) seeds the regression gate. Values below are from the 2026-07-02
handoff table (seed = cold anchor, mrate 0.5). The FIRST full run records measured
actuals; if an actual disagrees with the table it is a signal (code drift or a config
mismatch), surfaced by the runner -- NOT silently reconciled. None = no baseline yet
(recorded anyway; the dataset wants the data regardless).

Cold anchor (the real cold-start savestate seed):
  ColdStartSwimState v=0 anim=0.06392288208007812 air=900 mrate=0.5
"""

# --- Cold-start anchor: one canonical definition, referenced by every cold case. ---
COLD_ANIM = 0.06392288208007812
COLD_MRATE = 0.5
COLD_AIR = 900

# Shared planner knobs held constant across the benchmark so cross-case / cross-run
# comparisons are apples-to-apples. Overridable per case via the params merge below.
_COMMON = dict(
    v=0.0, anim=COLD_ANIM, air=COLD_AIR, cold_start=True, cold_mrate=COLD_MRATE,
    rank='astar', cap=4000, speed_gate=0.98, speed_gate_end=0.90,
    verbose=False,
)

# max_frontier lever. full=2000 = DOMINANT frontier (optimal in 10/10 swept dests, ~4x faster than
# 8000, non-monotone so bigger can be WORSE; 400k 812 vs 814). See knowledge/model/planner.md.
_TIER_FRONTIER = {'smoke': 1000, 'full': 2000, 'refill': 1000, 'grid': 1000}

# Air-refill model (user-specified 1-D approx, NOT DTM-verified): air pinned 900 while -x <=
# REFILL_UNTIL (pinned-back build), then one fresh-budget cruise. See model/planner.md, README.
REFILL_UNTIL = 3000.0


def _case(name, tier, dest, allow_pump, known_best, xfail_live=False, note=None,
          **overrides):
    """xfail_live: this plan is KNOWN to desync live (DTM verification fails) -- an expected
    failure tracked until the underlying sim/pump issue is fixed. verify_dtm flags an xfail_live
    case that starts PASSING (the signal it's resolved -> clear the flag). `note` documents why."""
    params = dict(_COMMON, dest=dest, allow_pump=allow_pump,
                  max_frontier=_TIER_FRONTIER[tier])
    if allow_pump:
        params['pump_chg'] = False        # CLEAN ESS pump (bit-exact v+anim); see plan.py
    params.update(overrides)
    return {
        'name': name,
        'tier': tier,
        'planner': 'plan_min_frames',
        'params': params,
        'known_best': known_best,
        'xfail_live': xfail_live,
        'note': note,
    }


# Ordered fastest-first so a smoke run surfaces failures early.
CASES = [
    # --- smoke: fast, pump-mode, exercises the pump/saturation path ---
    _case('cold_pump_20k',  'smoke',  20000, True,  177),   # DTM-verified 2026-07-02
    _case('cold_pump_30k',  'smoke',  30000, True,  218),   # DTM-verified 2026-07-02
    _case('cold_pump_50k',  'smoke',  50000, True,  280),
    # no-pump companions: cheap, exercise the shared cruise-DP core (NOT the shipped
    # optimum -- 50k no-pump is 282, not 280 -- so recorded, but not the quality gate).
    _case('cold_nopump_50k', 'smoke', 50000, False, 282),

    # --- full: the real destinations; pump = the shipped optimal mode ---
    _case('cold_nopump_100k', 'full', 100000, False, 401),
    _case('cold_pump_100k',   'full', 100000, True,  397),   # DTM-verified 2026-07-02 (untested @ handoff)
    _case('cold_nopump_200k', 'full', 200000, False, 561),
    _case('cold_pump_200k',   'full', 200000, True,  555),
    # long-haul: also probes the 900-frame air budget (a cold swim can only last ~900 frames).
    _case('cold_nopump_300k', 'full', 300000, False, 711),   # DTM-verified 2026-07-02
    _case('cold_pump_300k',   'full', 300000, True,  705),   # DTM-verified 2026-07-02 (705fr/
    # 39dips -> 300941 live); prior desync was a double-vs-single-pi release-cos bug (superswim-gekko-fp).
    _case('cold_nopump_400k', 'full', 400000, False, 819),   # DTM-verified 2026-07-02 (pending air-delta fix)
    _case('cold_pump_400k',   'full', 400000, True,  812),   # DTM-verified 2026-07-03 @mf=2000 (was 814@8000; dv/dan=0.000)
    # 400k is the map-edge/air ceiling for THIS anchor WITHOUT refill (Link hits the edge before
    # the ~900-frame air budget). Air refill lifts it (cases below). Extend when a farther anchor exists.

    # Non-refill drowning boundary: 500k returns NOREACH (frames=None) -- every completion needs
    # air<0 (~900-frame budget). Physical proof far swims REQUIRE a refill. See model/planner.md.
    _case('cold_pump_500k_nodrown', 'refill', 500000, True, None,
          note='non-refill 500k drowns (air budget) -> NOREACH; needs refill'),

    # Air-refill regime (real 200k-600k TAS range, SIM-MODEL not DTM-verified): pinned-back free
    # build + fresh-budget cruise. BASELINE sim predictions at mf=1000 (refill tier). See README.
    _case('refill_pump_200k', 'refill', 200000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_300k', 'refill', 300000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_400k', 'refill', 400000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_500k', 'refill', 500000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_600k', 'refill', 600000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    # granularity fill (100k-step gaps) + reach-ceiling probe (does refill still fit the budget at 700/800k?)
    _case('refill_pump_250k', 'refill', 250000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_350k', 'refill', 350000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_450k', 'refill', 450000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_550k', 'refill', 550000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_700k', 'refill', 700000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_800k', 'refill', 800000, True, None, refill_air=True, refill_until=REFILL_UNTIL),

    # --- grid: non-refill gap-fill data at mf=1000 (BASELINE, sim-only). Breadth for mining. ---
    # small dests (low end)
    _case('cold_pump_5k',  'grid',  5000, True, None),
    _case('cold_pump_10k', 'grid', 10000, True, None),
    _case('cold_pump_15k', 'grid', 15000, True, None),
    # mid-gaps between the existing 100k-step points (pump + no-pump)
    _case('cold_pump_150k',   'grid', 150000, True,  None),
    _case('cold_pump_250k',   'grid', 250000, True,  None),
    _case('cold_pump_350k',   'grid', 350000, True,  None),
    _case('cold_nopump_150k', 'grid', 150000, False, None),
    _case('cold_nopump_250k', 'grid', 250000, False, None),
    _case('cold_nopump_350k', 'grid', 350000, False, None),
    # no-pump refill (shared cruise-DP under refill; pump benefit WITH refill vs refill_pump_*)
    _case('refill_nopump_200k', 'grid', 200000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_400k', 'grid', 400000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_600k', 'grid', 600000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    # drowning-boundary map (non-refill, allow_drown default): 400k reaches (air 84), 500k drowns.
    # Which of these still reach within the ~900-frame budget? NOREACH = drowns.
    _case('cold_pump_425k', 'grid', 425000, True, None),
    _case('cold_pump_450k', 'grid', 450000, True, None),
    _case('cold_pump_475k', 'grid', 475000, True, None),
    # refill_until sensitivity at 400k (baseline ru=3000 -> 797fr): bigger zone = air stays 900
    # deeper into the cruise = fewer frames. Quantifies the refill model's key knob.
    _case('refill_pump_400k_ru500',   'grid', 400000, True, None, refill_air=True, refill_until=500.0),
    _case('refill_pump_400k_ru1000',  'grid', 400000, True, None, refill_air=True, refill_until=1000.0),
    _case('refill_pump_400k_ru5000',  'grid', 400000, True, None, refill_air=True, refill_until=5000.0),
    _case('refill_pump_400k_ru10000', 'grid', 400000, True, None, refill_air=True, refill_until=10000.0),
    # frontier sensitivity under refill: 200k @mf=8000 == 535 == @mf=1000 -> refill is
    # FRONTIER-INSENSITIVE (converges at 1000, like non-refill), and air-in-sig doesn't blow up.
    _case('refill_pump_200k_f8000', 'grid', 200000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=8000),
    # refill far-ceiling probe: does refill ITSELF eventually drown (cruise > ~900-frame budget
    # even at max buildable speed)? 800k reached at 1132fr; push to find the refill reach limit.
    _case('refill_pump_1000k', 'grid', 1000000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_1200k', 'grid', 1200000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_1500k', 'grid', 1500000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    # tiny dests (low end of the curve)
    _case('cold_pump_1k', 'grid', 1000, True, None),
    _case('cold_pump_2k', 'grid', 2000, True, None),
    _case('cold_pump_3k', 'grid', 3000, True, None),
    # complete the no-pump refill curve (have 200/400/600k) to clarify pump-benefit-under-refill
    _case('refill_nopump_300k', 'grid', 300000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_500k', 'grid', 500000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_700k', 'grid', 700000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_800k', 'grid', 800000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    # non-refill no-pump toward the drowning boundary (parallel to the pump curve): where does
    # no-pump drown vs pump (475k pump reaches @887fr, air ~13)?
    _case('cold_nopump_425k', 'grid', 425000, False, None),
    _case('cold_nopump_450k', 'grid', 450000, False, None),
    _case('cold_nopump_475k', 'grid', 475000, False, None),
    _case('cold_nopump_500k', 'grid', 500000, False, None),
    # finer refill no-pump (parallel to refill_pump 50k granularity) + 1M no-pump ceiling check
    _case('refill_nopump_250k',  'grid', 250000,  False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_350k',  'grid', 350000,  False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_450k',  'grid', 450000,  False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_550k',  'grid', 550000,  False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_1000k', 'grid', 1000000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    # smooth the primary non-refill pump curve to ~50k granularity in the mid-range
    _case('cold_pump_75k',  'grid',  75000, True, None),
    _case('cold_pump_125k', 'grid', 125000, True, None),
    _case('cold_pump_175k', 'grid', 175000, True, None),
    _case('cold_pump_225k', 'grid', 225000, True, None),
    _case('cold_pump_275k', 'grid', 275000, True, None),
    _case('cold_pump_325k', 'grid', 325000, True, None),
    _case('cold_pump_375k', 'grid', 375000, True, None),
    # refill pump fine granularity (match the non-refill curve density at ~50k steps)
    _case('refill_pump_225k', 'grid', 225000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_275k', 'grid', 275000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_325k', 'grid', 325000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_375k', 'grid', 375000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_425k', 'grid', 425000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_475k', 'grid', 475000, True, None, refill_air=True, refill_until=REFILL_UNTIL),
    # non-refill no-pump fine granularity (complete the parallel pump/nopump curves)
    _case('cold_nopump_75k',  'grid',  75000, False, None),
    _case('cold_nopump_125k', 'grid', 125000, False, None),
    _case('cold_nopump_175k', 'grid', 175000, False, None),
    _case('cold_nopump_225k', 'grid', 225000, False, None),
    _case('cold_nopump_275k', 'grid', 275000, False, None),
    _case('cold_nopump_325k', 'grid', 325000, False, None),
    _case('cold_nopump_375k', 'grid', 375000, False, None),
    # mf-convergence study at 200k pump (have 1000=556, 8000=555): frames-vs-frontier curve
    _case('cold_pump_200k_f250',  'grid', 200000, True, None, max_frontier=250),
    _case('cold_pump_200k_f500',  'grid', 200000, True, None, max_frontier=500),
    _case('cold_pump_200k_f2000', 'grid', 200000, True, None, max_frontier=2000),
    _case('cold_pump_200k_f4000', 'grid', 200000, True, None, max_frontier=4000),
    # confirm mf=2000 convergence generalizes at 400k (cold_pump_400k = 814 @mf=8000)
    _case('cold_pump_400k_f1000', 'grid', 400000, True, None, max_frontier=1000),
    _case('cold_pump_400k_f2000', 'grid', 400000, True, None, max_frontier=2000),
    _case('cold_pump_400k_f4000', 'grid', 400000, True, None, max_frontier=4000),
    # map the non-monotonic region around the mf=2000 minimum (812) to find the best frames
    _case('cold_pump_400k_f1500', 'grid', 400000, True, None, max_frontier=1500),
    _case('cold_pump_400k_f2500', 'grid', 400000, True, None, max_frontier=2500),
    _case('cold_pump_400k_f3000', 'grid', 400000, True, None, max_frontier=3000),
    # does the non-monotonic valley generalize? 300k pump sweep vs base truth 705 @mf=8000
    _case('cold_pump_300k_f1000', 'grid', 300000, True, None, max_frontier=1000),
    _case('cold_pump_300k_f1500', 'grid', 300000, True, None, max_frontier=1500),
    _case('cold_pump_300k_f2000', 'grid', 300000, True, None, max_frontier=2000),
    _case('cold_pump_300k_f2500', 'grid', 300000, True, None, max_frontier=2500),
    _case('cold_pump_300k_f3000', 'grid', 300000, True, None, max_frontier=3000),
    # does refill also have a non-monotonic valley? refill_pump_400k sweep vs mf=1000 (797)
    _case('refill_pump_400k_f1500', 'grid', 400000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=1500),
    _case('refill_pump_400k_f2000', 'grid', 400000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=2000),
    _case('refill_pump_400k_f2500', 'grid', 400000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=2500),
    _case('refill_pump_400k_f3000', 'grid', 400000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=3000),
    # converge the grid curve at the mf=2500 sweet spot (vs mf=1000): catch improvements like 400k
    _case('cold_pump_150k_f2500', 'grid', 150000, True, None, max_frontier=2500),
    _case('cold_pump_250k_f2500', 'grid', 250000, True, None, max_frontier=2500),
    _case('cold_pump_350k_f2500', 'grid', 350000, True, None, max_frontier=2500),
    _case('cold_pump_450k_f2500', 'grid', 450000, True, None, max_frontier=2500),
    # extend refill curves to the LOW end (refill only covered >=200k) -- refill benefit is
    # small here (little air depletion over a short swim) but non-zero; completes the curves.
    _case('refill_pump_50k',   'grid',  50000, True,  None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_100k',  'grid', 100000, True,  None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_pump_150k',  'grid', 150000, True,  None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_50k', 'grid',  50000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_100k','grid', 100000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    _case('refill_nopump_150k','grid', 150000, False, None, refill_air=True, refill_until=REFILL_UNTIL),
    # mf=2000-optimality check: does 2000 capture the 2500 best (250k=640, 350k=763, 450k=861)?
    _case('cold_pump_250k_f2000', 'grid', 250000, True, None, max_frontier=2000),
    _case('cold_pump_350k_f2000', 'grid', 350000, True, None, max_frontier=2000),
    _case('cold_pump_450k_f2000', 'grid', 450000, True, None, max_frontier=2000),
    # broaden the mf=2000-optimality evidence: 100k non-refill (base truth 397 @8000) + refill far
    _case('cold_pump_100k_f2000',   'grid', 100000, True, None, max_frontier=2000),
    _case('refill_pump_500k_f2000', 'grid', 500000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=2000),
    _case('refill_pump_600k_f2000', 'grid', 600000, True, None, refill_air=True, refill_until=REFILL_UNTIL, max_frontier=2000),
    # fine-grained 400k sweep inside the valley (2000-2500=812): does the jitter dip below 812?
    _case('cold_pump_400k_f1800', 'grid', 400000, True, None, max_frontier=1800),
    _case('cold_pump_400k_f2100', 'grid', 400000, True, None, max_frontier=2100),
    _case('cold_pump_400k_f2200', 'grid', 400000, True, None, max_frontier=2200),
    _case('cold_pump_400k_f2300', 'grid', 400000, True, None, max_frontier=2300),
    _case('cold_pump_400k_f2400', 'grid', 400000, True, None, max_frontier=2400),
    # fine-sweep 350k (have 1000=765, 2000/2500=763): plateau like 400k? band edges?
    _case('cold_pump_350k_f1500', 'grid', 350000, True, None, max_frontier=1500),
    _case('cold_pump_350k_f1800', 'grid', 350000, True, None, max_frontier=1800),
    _case('cold_pump_350k_f2200', 'grid', 350000, True, None, max_frontier=2200),
    _case('cold_pump_350k_f2400', 'grid', 350000, True, None, max_frontier=2400),
    _case('cold_pump_350k_f3000', 'grid', 350000, True, None, max_frontier=3000),
]

CASES_BY_NAME = {c['name']: c for c in CASES}
TIERS = ('smoke', 'full', 'refill', 'grid')


def cases_for(tiers):
    """Cases whose tier is in `tiers` (a set/tuple of tier names)."""
    return [c for c in CASES if c['tier'] in tiers]
