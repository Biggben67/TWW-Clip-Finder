"""test_partial_magnitude.py — locks the swim-gain MAGNITUDE model against a live PARTIAL on-axis
charge (pt23, 2026-06-29).

This case exists to settle the disproven "wire the live grid stick_dist as the gain magnitude"
task. partial_onaxis_cap.csv alternates (128,84)/(128,176) with the camera frozen west — both
sticks are ON-AXIS (so the stick ANGLE is exact and not under test) but only PARTIALLY deflected,
so the only thing that drives v is the magnitude model:

    gain = mStickDistance * 3 * cM_scos(d_turn)

Two facts are asserted, live-pinned:
  1. the closed-form magnitude min(hypot(_deadzone15)/54, 1) — what swim_arbitrary actually uses —
     reproduces the live v/anim BIT-EXACT (this is the regression lock);
  2. the grid `stick_dist` column now EQUALS that closed form, so driving the gain from the grid
     column reproduces the live capture too. (Historically this column was CORRUPT — a ~2-row
     latency shift from the old 1-frame-pipeline dump — and this test asserted it did NOT match, to
     guard the fixture's teeth. The 2026-07 gold re-dump (harness/capture/stick_grid_redump.py,
     settle+verify) fixed stick_dist == mMainStickValue == the closed form for all 65536 cells, so
     the assertion is now inverted to LOCK that correctness. See knowledge/history.)

Camera is frozen (csangle constant), so we drive ArbitrarySwimState directly with a fixed cam and
do NOT go through swim_predict_complicated (whose omega camera table is a separate, coarse-grid gap).
"""
import os, csv, math

import pytest

from tww_sim.swim.predict import stick_angle as SA
from tww_sim.swim.predict.swim_arbitrary import ArbitrarySwimState
from tww_sim.swim import sim as S

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "partial_onaxis_cap.csv")

TOL_V = 1e-4
TOL_ANIM = 1e-3


def _run(rows, mag_fn=None):
    """Drive ArbitrarySwimState over the captured sticks with the camera frozen at the seed
    csangle. If mag_fn is given, monkeypatch SA.mstick_dist-equivalent path is not used (the gain
    reads the closed form directly); instead mag_fn lets us swap the magnitude source for the
    discrimination check by patching the closed-form helper. Returns (worst_v_err, worst_anim_err)."""
    f0 = rows[0]
    cam = int(f0["csangle"])
    s = ArbitrarySwimState(v=float(f0["potential_speed"]), anim=float(f0["anim_frame"]),
                           air=int(f0["air"]), mrate=float(f0["move0_mrate"]))
    s.state = int(f0["link_state"])
    s._entry_tax = False
    s.facing = int(f0["facing"])
    wv = wa = 0.0
    for r in rows[1:]:
        sx, sy = int(r["sx"]), int(r["sy"])
        s.cam = cam
        s.set_stick(sx, sy)
        s.step(s.action_for(sx, sy))
        wv = max(wv, abs(s.v - float(r["potential_speed"])))
        cyc = 26.0 if int(r["link_state"]) == 54 else 23.0
        ad = (s.anim - float(r["anim_frame"])) % cyc
        wa = max(wa, min(ad, cyc - ad))
    return wv, wa


def _rows():
    return list(csv.DictReader(open(CAP)))


def test_closed_form_magnitude_bit_exact():
    """The closed-form /54 magnitude (what swim_arbitrary uses) is bit-exact vs the live partial
    on-axis charge."""
    wv, wa = _run(_rows())
    assert wv <= TOL_V and wa <= TOL_ANIM, (
        f"closed-form magnitude regressed: v_err={wv:g} (<= {TOL_V}) anim_err={wa:g} (<= {TOL_ANIM})")


def test_grid_stick_dist_matches_closed_form(monkeypatch):
    """Lock: the grid `stick_dist` column now EQUALS the closed-form /54 magnitude, so driving the
    gain from the grid column reproduces the live capture within tolerance. Guards against the
    column regressing to the old latency-corrupted values (which diverged ~0.22)."""
    # build the live stick_dist lookup straight from the shipped grid
    tbl = {}
    grid = os.path.join(HERE, "..", "tww_sim", "core", "tables", "stick_angle_table.csv")
    for r in csv.DictReader(open(grid)):
        tbl[(int(r["sx"]), int(r["sy"]))] = float(r["stick_dist"])

    def grid_mag(_self, sx=None, sy=None):
        rsx, rsy = _self._stick
        a = SA.angle_s16(rsx, rsy)
        if a is None:
            return 0.0
        m = (a + 0x8000 + _self.cam) & 0xFFFF
        d = S.s16_signed(m - _self.facing)
        if abs(d) > 0x6000:
            d_turn = d
        else:
            cap = S.deg_to_s16(S.ARROW_TURN_RATE)
            d_turn = max(-cap, min(cap, d))
        _self._pending_facing = (_self.facing + d_turn) & 0xFFFF
        return S.f32(tbl[(rsx, rsy)] * 3.0 * S.cM_scos_s16(d_turn))

    monkeypatch.setattr(ArbitrarySwimState, "_swim_facing", grid_mag)
    wv, _ = _run(_rows())
    assert wv <= TOL_V, (
        f"grid stick_dist regressed from the closed form (v_err={wv:g} > {TOL_V}); "
        f"the stick_angle_table.csv stick_dist column may have reverted to latency-corrupted values")
