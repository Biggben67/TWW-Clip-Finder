"""golden_harness.py -- shared fixtures + golden encode/compare/regen for the offline
superswim regression suite.

This is the single source of truth for:
  * the documented SEEDS (canonical cold-start + a few varied phase/air/speed seeds),
  * the (seed-id, seqfile) CASE matrix the golden tests freeze,
  * how a per-frame trace is encoded to a golden JSON (bit-exact: f32 fields as hex
    floats, ints/strings verbatim) and compared to a stored golden,
  * the regeneration entry point (`python -m tests.golden_regen`).

Generating a golden RUNS THE CURRENT SIM AT HEAD and freezes its output. The Dolphin
suite (run_tests.py / validate_coldstart.py) already confirms the current sim matches the
real game, so HEAD's output IS the validated reference -- this just locks it down offline.

Pure offline: imports only the `superswim` package (no dolphin_mem, no harness/).
3.7-compatible.
"""
import os
import json
import math

from tww_sim.swim import sim as S
from tww_sim.swim.coldstart import ColdStartSwimState
from tww_sim.swim.actions import expand

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "fixtures")
GOLDEN_DIR = os.path.join(HERE, "golden")

# ---------------------------------------------------------------------------
# SEEDS. Each seed is a documented physics regime. `kind` selects the state class:
#   'cold'  -> ColdStartSwimState at the DTM anchor cruise_cold@twwgz.sav (state 54, v0, air 900,
#              its OWN mRate 0.5 -- NOT the slate's 0.5472). Mirrors the locked live DTM baselines; see README.
#   'warm'  -> plain SwimState mid-swim (state 55), entry_tax off. Used for cruise /
#              steady-state / neutral-dip / charge-burst characterization where we are
#              already swimming and the cold-start scramble is not under test.
# entry_tax mirrors the slate charge->hold artifact; left off for these characterization
# seeds (run_trace's default True is exercised separately in the seq cases that need it).
# ---------------------------------------------------------------------------
COLD_ANIM = 0.06392288208007812      # true f32 fresh cold-start display anim (both cold starts)
COLD_MRATE = 0.5                     # the DTM anchor's own logged MOVE0 rate (NOT the slate's 0.5472)

SEEDS = {
    # canonical cold start (the run_tests / validate_coldstart seed)
    "cold": dict(kind="cold", v=0.0, anim=COLD_ANIM, air=900, mrate=COLD_MRATE),
    # mid-cruise high speed, high air, anim near the |cos| peak
    "cruise_hi": dict(kind="warm", v=-1630.0, anim=18.148, air=900),
    # mid-cruise high speed, LOW air (air-drag regime; neutral-dip distance edge lives here)
    "cruise_lowair": dict(kind="warm", v=-1630.0, anim=5.0, air=120),
    # low-speed tail: |v| in the cLib_addCalc proportional band, then it bleeds below 25->0
    "lowspeed": dict(kind="warm", v=-60.0, anim=3.0, air=400),
    # different anim phase + mid air (phase-dependent af_drag / scramble coverage)
    "midphase": dict(kind="warm", v=-800.0, anim=11.5, air=500),
}


def make_state(seed_id):
    """Construct a fresh seeded state for `seed_id` (a key of SEEDS)."""
    cfg = SEEDS[seed_id]
    if cfg["kind"] == "cold":
        s = ColdStartSwimState(v=cfg["v"], anim=cfg["anim"], air=cfg["air"],
                               mrate=cfg["mrate"])
        s.state = 54
        s._entry_tax = False
    else:
        s = S.SwimState(v=cfg["v"], anim=cfg["anim"], air=cfg["air"])
        s._entry_tax = False
    return s


# ---------------------------------------------------------------------------
# CASES. (case_id, seed_id, actions_source). actions_source is either:
#   ("file", "<fixture filename>")  -> expand(open(fixture).read())
#   ("inline", [<action>, ...])     -> the literal action list (hand-authored mechanics)
# Each case is run from make_state(seed_id) and its full per-frame trace is frozen.
# ---------------------------------------------------------------------------

# Hand-authored short seqs isolating specific mechanics (documented inline).
INLINE_SEQS = {
    # cold-start x598 scramble: cold -> first swim-move (charge entry), then a few ESS.
    "coldstart_entry": ["chg", "chg", "ess", "ess", "ess", "ess"],
    # single pump compounding: ESS cruise, one 1-frame neutral dip, re-enter ESS.
    "neutral_dip_single": (["ess"] * 6 + ["neu"] + ["ess"] * 6),
    # two dips spaced out (the inverse-pump cruise; x598 re-scramble between).
    "neutral_dip_double": (["ess"] * 5 + ["neu"] + ["ess"] * 8 + ["neu"] + ["ess"] * 5),
    # charge burst EVEN length (facing re-aligns -> +1/6, no post-burst transient).
    "charge_even": (["ess"] * 3 + ["chg"] * 4 + ["ess"] * 6),
    # charge burst ODD length (facing NOT re-aligned -> the carried -1/6 transient).
    "charge_odd": (["ess"] * 3 + ["chg"] * 3 + ["ess"] * 6),
    # cLib_addCalc low-speed tail: pure neutral dash bleeds |v| below 100, below 25, to 0.
    "neutral_decay_tail": ["neu"] * 60,
    # ESS cruise steady-state (pure ess, no transitions).
    "ess_cruise": ["ess"] * 40,
    # ESS->neutral exit then sustained neutral (release_ess_speed + decay tail).
    "exit_then_dash": (["ess"] * 8 + ["neu"] * 20),
    # PARTIAL on-axis hold block bracketed by charges (BUG #3 regime): the uniform 1-frame
    # swim-gain lag carries the last (128,77) hold's gain onto the following charge frame.
    "partial_hold_boundary": (["chg"] * 4 + ["ess:77"] * 4 + ["chg"] * 4),
    # PARTIAL charge burst (chg:<rawY>): sub-full magnitude, still snaps/flips.
    "partial_charge_burst": (["ess"] * 3 + ["chg:170"] * 4 + ["ess"] * 3),
}

CASES = [
    # --- cold-start regime (canonical seed) ---
    ("cold_entry",        "cold",          ("inline", "coldstart_entry")),
    ("cold_plan3k",       "cold",          ("file", "plan3k_exact_seq.txt")),
    ("cold_pump4",        "cold",          ("file", "pump_seq.txt")),       # 4 pumps
    ("cold_pump8",        "cold",          ("file", "pump_seq8.txt")),      # 8 pumps
    ("cold_coldstartseq", "cold",          ("file", "coldstart_seq.txt")),

    # --- cruise / steady-state / mechanics (warm seeds) ---
    ("cruise_ess",        "cruise_hi",     ("inline", "ess_cruise")),
    ("cruise_dip1",       "cruise_hi",     ("inline", "neutral_dip_single")),
    ("cruise_dip2",       "cruise_hi",     ("inline", "neutral_dip_double")),
    ("cruise_chg_even",   "cruise_hi",     ("inline", "charge_even")),
    ("cruise_chg_odd",    "cruise_hi",     ("inline", "charge_odd")),
    ("cruise_exit_dash",  "cruise_hi",     ("inline", "exit_then_dash")),

    # --- partial deflection (BUG #3 fix: uniform swim-gain lag) ---
    ("cruise_partial_hold",   "cruise_hi", ("inline", "partial_hold_boundary")),
    ("cruise_partial_charge", "cruise_hi", ("inline", "partial_charge_burst")),
    # cold-start partial-hold seq -- SIM output equals the LIVE-validated bug3 gate (v=-92.0).
    ("cold_partial_hold77",   "cold",      ("file", "partial_hold77_seq.txt")),

    # low-air dip (air-drag regime) + low-speed decay tail
    ("lowair_dip2",       "cruise_lowair", ("inline", "neutral_dip_double")),
    ("lowspeed_tail",     "lowspeed",      ("inline", "neutral_decay_tail")),

    # mid-phase charge bursts (different af_drag phase / air)
    ("midphase_chg_odd",  "midphase",      ("inline", "charge_odd")),
    ("midphase_chg_even", "midphase",      ("inline", "charge_even")),

    # --- bug fixtures: SIM output is deterministic and must stay frozen (XFAIL vs LIVE) ---
    ("bug1_lowspeed",     "cold",          ("file", "test_lowspeed_seq.txt")),
    ("bug2_pumptrans",    "cold",          ("file", "test_pumptrans_seq.txt")),
]


def case_actions(source):
    kind, val = source
    if kind == "file":
        with open(os.path.join(FIXTURES, val)) as fh:
            return expand(fh.read())
    if kind == "inline":
        return list(INLINE_SEQS[val])
    raise ValueError("unknown action source %r" % (source,))


def run_case(case_id, seed_id, source):
    """Run one case through the current sim, returning the list of per-frame rows."""
    s = make_state(seed_id)
    acts = case_actions(source)
    rows = []
    x0, z0 = s.x, s.z
    path = 0.0
    for i, act in enumerate(acts):
        d, tag = s.step(act)
        path += abs(d)
        rows.append({
            "f": i + 1,
            "v": s.v, "anim": s.anim, "air": s.air, "state": s.state,
            "x": s.x, "z": s.z, "step": d, "tag": tag, "path": path,
            "net": math.hypot(s.x - x0, s.z - z0),
        })
    return rows


# ---------------------------------------------------------------------------
# Golden encoding. Float fields are stored as Python hex-float strings (exact,
# stable across runs/platforms) and compared with float.fromhex -> 0 tolerance.
# ints (air, state, frame) and the tag string are stored verbatim.
# ---------------------------------------------------------------------------
_FLOAT_FIELDS = ("v", "anim", "x", "z", "step", "path", "net")
_INT_FIELDS = ("f", "air", "state")


def encode_rows(rows):
    out = []
    for r in rows:
        e = {k: float.hex(float(r[k])) for k in _FLOAT_FIELDS}
        for k in _INT_FIELDS:
            e[k] = int(r[k])
        e["tag"] = r["tag"]
        out.append(e)
    return out


def golden_path(case_id):
    return os.path.join(GOLDEN_DIR, case_id + ".json")


def write_golden(case_id, rows):
    payload = {"case": case_id, "frames": len(rows), "rows": encode_rows(rows)}
    with open(golden_path(case_id), "w") as fh:
        json.dump(payload, fh, indent=0)
        fh.write("\n")


def load_golden(case_id):
    with open(golden_path(case_id)) as fh:
        return json.load(fh)


def compare_rows(rows, golden):
    """Return a list of human-readable mismatch strings (empty == bit-exact match)."""
    grows = golden["rows"]
    errs = []
    if len(rows) != len(grows):
        errs.append("frame count %d != golden %d" % (len(rows), len(grows)))
        return errs
    for r, g in zip(rows, grows):
        f = r["f"]
        for k in _FLOAT_FIELDS:
            want = float.fromhex(g[k])
            got = float(r[k])
            if got != want and not (math.isnan(got) and math.isnan(want)):
                errs.append("f%d %s: got %r (%s) want %r (%s)"
                            % (f, k, got, float.hex(got), want, g[k]))
        for k in _INT_FIELDS:
            if int(r[k]) != g[k]:
                errs.append("f%d %s: got %d want %d" % (f, k, int(r[k]), g[k]))
        if r["tag"] != g["tag"]:
            errs.append("f%d tag: got %r want %r" % (f, r["tag"], g["tag"]))
    return errs


def regen_all():
    if not os.path.isdir(GOLDEN_DIR):
        os.makedirs(GOLDEN_DIR)
    for case_id, seed_id, source in CASES:
        rows = run_case(case_id, seed_id, source)
        write_golden(case_id, rows)
        print("wrote golden %-20s (%d frames)" % (case_id, len(rows)))
    print("regenerated %d goldens in %s" % (len(CASES), GOLDEN_DIR))
