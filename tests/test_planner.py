"""Planner / optimizer characterization tests.

Freezes the OUTPUT of plan.plan_min_frames and optimize.beam_search* on small, fast
fixed-seed cases. The frame count / net distance is the primary regression signal; the
action-sequence hash is also frozen (a secondary signal -- the discrete game has many
equal-frame solutions, so a hash change with the SAME frame count is a tie-break shift,
not necessarily a physics regression; the frame count is the load-bearing assert).

Default-collected cases run in a few seconds total. The 20k cold-start plan is marked
`slow` and excluded from the default run.

Pure offline. 3.7-compatible.
"""
import hashlib
import pytest

from tww_sim.swim import plan, optimize

COLD_ANIM = 0.06392288208007812


def _ahash(actions):
    return hashlib.sha1(";".join(actions).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# plan.plan_min_frames
# ---------------------------------------------------------------------------
def test_plan_cruise_small_dest():
    # From a fast cruise seed, 3000 units is reached in a tiny number of frames.
    r = plan.plan_min_frames(3000, v=-1630.0, anim=18.148, air=900,
                             verbose=False, max_frontier=500)
    assert r["frames"] == 3
    assert optimize.seq_string(r["actions"]) == "neu,3"
    assert r["reached"] >= 3000


@pytest.mark.slow
def test_plan_cold_start_3k():
    # Real cold start (state 54, entry off): build speed from v=0 to cover 3000 units.
    r = plan.plan_min_frames(3000, v=0.0, anim=COLD_ANIM, air=900, cold_start=True,
                             verbose=False, max_frontier=1000)
    assert r["frames"] == 70
    assert r["reached"] >= 3000
    assert _ahash(r["actions"]) == "0be91a94e21620cb"
    assert len(r["actions"]) == 70


@pytest.mark.slow
def test_plan_cold_start_20k():
    r = plan.plan_min_frames(20000, v=0.0, anim=COLD_ANIM, air=900, cold_start=True,
                             verbose=False, max_frontier=1000)
    assert r["frames"] == 178
    assert r["reached"] >= 20000


# ---------------------------------------------------------------------------
# optimize.beam_search_to_dest / beam_search / helpers
# ---------------------------------------------------------------------------
def test_beam_search_to_dest_small():
    acts, nfr, reached, _ = optimize.beam_search_to_dest(
        8000, -1630.0, 18.148, 900, beam=2000, cap=2000)
    assert nfr == 6
    assert optimize.seq_string(acts) == "neu,5;ess,1"
    assert reached >= 8000


def test_beam_search_fixed_window():
    acts, net, _ = optimize.beam_search(40, -1630.0, 18.148, 900, beam=500)
    assert net == 58752.1359669393
    assert acts.count("chg") == 2
    assert _ahash(acts) == "e7b9d9b9d1b7b9d4"


def test_frames_to_dest_pure_ess():
    nfr, reached = optimize.frames_to_dest_pure_ess(8000, -1630.0, 18.148, 900)
    assert isinstance(nfr, int)
    assert reached >= 8000


def test_seq_string_roundtrip():
    from tww_sim.swim.actions import expand
    seq = "ess,3;chg,2;neu,1"
    assert optimize.seq_string(expand(seq)) == seq


def test_schedule_extracts_bursts():
    acts = ["ess", "chg", "chg", "ess", "ess", "chg"]
    # bursts are (1-based start, length): chg at index 1-2 -> (2,2); chg at index 5 -> (6,1).
    assert optimize.schedule(acts) == [(2, 2), (6, 1)]
