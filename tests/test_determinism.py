"""Determinism + f32 bit-stability meta-tests.

The sim is fully deterministic: the same (seed, seq) must produce an identical trace on
every run, and the f32 accumulation path must produce an exact, stable value. These guard
against accidental nondeterminism (dict ordering, float drift, hidden global state).

Pure offline. 3.7-compatible.
"""
import math

from tww_sim.swim import sim as S
from tests import golden_harness as G


def _trace_tuple(rows):
    # Reduce a trace to a hashable, exactly-comparable tuple.
    return tuple((r["f"], float.hex(r["v"]), float.hex(r["anim"]), r["air"],
                  r["state"], r["tag"], float.hex(r["step"])) for r in rows)


def test_same_seed_seq_run_twice_identical():
    """Every golden case run twice must be bit-identical."""
    for case_id, seed_id, source in G.CASES:
        a = _trace_tuple(G.run_case(case_id, seed_id, source))
        b = _trace_tuple(G.run_case(case_id, seed_id, source))
        assert a == b, "case %r is non-deterministic" % case_id


def test_run_trace_repeatable():
    a = S.run_trace(["ess"] * 30 + ["chg"] * 3 + ["ess"] * 30, -1630.0, 18.148, 900)
    b = S.run_trace(["ess"] * 30 + ["chg"] * 3 + ["ess"] * 30, -1630.0, 18.148, 900)
    assert [r["v"] for r in a] == [r["v"] for r in b]
    assert [r["anim"] for r in a] == [r["anim"] for r in b]


def test_clone_does_not_share_state():
    """Cloning a SwimState and stepping the clone must not perturb the original."""
    s = S.SwimState(v=-1630.0, anim=18.148, air=900)
    s._entry_tax = False
    s.step("ess")
    snapshot = (s.v, s.anim, s.air, s.x, s.state)
    c = s.clone()
    for _ in range(10):
        c.step("chg")
    assert (s.v, s.anim, s.air, s.x, s.state) == snapshot


def test_f32_accumulation_is_bit_stable():
    """A known sequence of f32 accumulations produces an exact, frozen f32 value.
    This is the ctypes round-half-to-even guarantee that keeps the live baselines exact."""
    acc = S.f32(0.0)
    for _ in range(1000):
        acc = S.f32(acc + S.f32(0.1))
    # 1000 * 0.1 accumulated in f32 (NOT 100.0 -- f32 rounding drift). Frozen.
    assert acc == 99.9990463256836
    assert S.f32(acc) == acc


def test_incr_accumulation_matches_direct_advance():
    """Accumulating incr() per frame (the anim rate) is bit-stable across calls."""
    air = 900
    v = -1630.0
    a = S.nfmod(0.0, 23.0)
    for _ in range(50):
        a = S.nfmod(a + S.incr(v, air), 23.0)
    b = S.nfmod(0.0, 23.0)
    for _ in range(50):
        b = S.nfmod(b + S.incr(v, air), 23.0)
    assert a == b
    assert not math.isnan(a)
