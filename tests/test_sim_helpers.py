"""Unit tests for the pure leaf helpers in tww_sim.swim.sim.

These assert specific derived values where the decomp pins exact constants/laws
(documented in KNOWLEDGE.md and the sim's own comments). They are the
finest-grained regression lock: a change to any physics primitive trips here with a
precise message before it propagates into a golden trace.

Pure offline. 3.7-compatible.
"""
import math
import pytest

from tww_sim.swim import sim as S


# ---------------------------------------------------------------------------
# f32: the ctypes IEEE-754 bit-exactness guarantee.
# ---------------------------------------------------------------------------
class TestF32:
    def test_known_single_precision_values(self):
        # 0.1 has no exact f32 rep; the nearest f32 is this exact double.
        assert S.f32(0.1) == 0.10000000149011612
        assert S.f32(1.0) == 1.0
        assert S.f32(0.5) == 0.5  # exactly representable

    def test_round_half_to_even(self):
        # 2**24 = 16777216 is the last integer with unit f32 spacing; above it,
        # spacing is 2, so ties round to the even neighbour.
        assert S.f32(16777217.0) == 16777216.0   # 16777217 -> down to even
        assert S.f32(16777219.0) == 16777220.0   # tie -> up to even
        assert S.f32(16777218.0) == 16777218.0   # exact

    def test_overflow_to_inf(self):
        assert S.f32(1e40) == math.inf
        assert S.f32(-1e40) == -math.inf

    def test_signed_zero_preserved(self):
        nz = S.f32(-0.0)
        assert nz == 0.0
        assert math.copysign(1.0, nz) == -1.0      # sign bit preserved
        assert math.copysign(1.0, S.f32(0.0)) == 1.0

    def test_idempotent(self):
        for x in (-1630.123, 0.06392288208007812, 18.148, -0.5):
            assert S.f32(S.f32(x)) == S.f32(x)


# ---------------------------------------------------------------------------
# nfmod / fc_update
# ---------------------------------------------------------------------------
def test_nfmod():
    assert S.nfmod(25.0, 23.0) == 2.0
    assert S.nfmod(-1.0, 23.0) == 22.0
    assert S.nfmod(0.0, 23.0) == 0.0
    assert S.nfmod(23.0, 23.0) == 0.0


def test_fc_update_single_loop_matches_nfmod():
    # For a frame already in [0, end+rate) one loop-subtraction == nfmod (the baseline
    # bit-exactness property the docstring guarantees).
    f = S.fc_update(22.5, 1.0, 23.0)   # 23.5 -> -23 -> 0.5
    assert f == 0.5
    f2 = S.fc_update(10.0, 0.5, 23.0)  # no loop
    assert f2 == 10.5


def test_fc_update_no_loop_when_in_range():
    assert S.fc_update(0.0, 0.5, 23.0) == 0.5


# ---------------------------------------------------------------------------
# cLib_addCalc: the three step regimes (neutral speed decay).
# ---------------------------------------------------------------------------
class TestCLibAddCalc:
    def test_high_speed_flat_max_step(self):
        # |v|>100: step 0.02*1630 = 32.6 > maxStep 2.0 -> clamp to 2.0.
        assert S.cLib_addCalc(-1630.0, 0.0, 0.02, 2.0, 0.5) == -1628.0
        assert S.cLib_addCalc(-100.5, 0.0, 0.02, 2.0, 0.5) == -98.5

    def test_proportional_band(self):
        # 25<|v|<100: 0.02*|v| is between minStep and maxStep -> apply as-is.
        assert S.cLib_addCalc(-50.0, 0.0, 0.02, 2.0, 0.5) == -49.0   # 0.02*50 = 1.0
        assert S.cLib_addCalc(-90.0, 0.0, 0.02, 2.0, 0.5) == pytest.approx(-88.2, abs=1e-4)

    def test_low_speed_min_step_snap(self):
        # |v|<25: step 0.02*|v| < minStep 0.5 -> move by exactly minStep, no overshoot.
        assert S.cLib_addCalc(-10.0, 0.0, 0.02, 2.0, 0.5) == -9.5
        # below 0.5 from target -> snaps exactly to target (no overshoot past 0).
        assert S.cLib_addCalc(-0.3, 0.0, 0.02, 2.0, 0.5) == 0.0
        assert S.cLib_addCalc(0.4, 0.0, 0.02, 2.0, 0.5) == 0.0

    def test_at_target_is_noop(self):
        assert S.cLib_addCalc(0.0, 0.0, 0.02, 2.0, 0.5) == 0.0


# ---------------------------------------------------------------------------
# ess_decay: stick raw -> potential-speed decay (the /54 gate).
# ---------------------------------------------------------------------------
class TestEssDecay:
    def test_raw_110_is_optimal_min(self):
        # raw=110 (off 18): (18-15)/54*3 = 3/18 = 1/6, the provable cruise minimum.
        assert S.ess_decay(110) == pytest.approx(1.0 / 6.0, abs=1e-6)
        assert S.ess_decay(110) == S.f32(S.ess_decay(110))   # already f32

    def test_neutral_stick_zero(self):
        assert S.ess_decay(128) == 0.0

    def test_full_deflection_clamps_to_three(self):
        assert S.ess_decay(255) == 3.0
        assert S.ess_decay(0) == 3.0

    def test_deadzone_edge(self):
        # off 15 == dead-zone edge -> 0.
        assert S.ess_decay(128 + 15) == 0.0
        assert S.ess_decay(128 - 15) == 0.0

    def test_swim_move_gate_neighbourhood(self):
        # mStickDistance = (off-15)/54; gate is >0.05. raw110 -> 0.0556 (clears),
        # raw111 -> 0.0370, raw112 -> 0.0185 (both below). ess_decay just reports the
        # decay; the values around the gate are pinned for reference.
        assert (110 - 128) and abs(S.ess_decay(110) / 3.0) > 0.05
        assert abs(S.ess_decay(111) / 3.0) < 0.05
        assert abs(S.ess_decay(112) / 3.0) < 0.05


# ---------------------------------------------------------------------------
# cM_scos / cM_scos_s16: console table, low-4-bits truncated, no interpolation.
# ---------------------------------------------------------------------------
class TestCosTable:
    def test_cardinal_values(self):
        assert S.cM_scos(0.0) == 1.0
        assert S.cM_scos_s16(0) == 1.0
        assert S.cM_scos_s16(0x8000) == -1.0   # pi exactly -> table entry -1.0

    def test_pi_is_table_truncated_not_minus_one(self):
        # cM_scos(pi) uses rad->index truncation, so it is NOT exactly -1 (it's the
        # nearest truncated table entry); this ~5e-4 offset vs math.cos is the documented
        # truncation behavior and must stay frozen.
        c = S.cM_scos(math.pi)
        assert c != -1.0
        assert c == pytest.approx(-1.0, abs=2e-3)

    def test_low_four_bits_truncated(self):
        # s16 angles that share the same >>4 index map to the SAME table value (no interp).
        base = S.cM_scos_s16(0x0100)
        for low in range(16):
            assert S.cM_scos_s16(0x0100 + low) == base

    def test_returns_console_f32(self):
        # table is big-endian f32 console values -> each is exactly an f32.
        v = S.cM_scos_s16(0x1234)
        assert S.f32(v) == v


# ---------------------------------------------------------------------------
# deg_to_s16 / s16_signed
# ---------------------------------------------------------------------------
def test_deg_to_s16():
    assert S.deg_to_s16(0.0) == 0
    assert S.deg_to_s16(90.0) == 16384
    assert S.deg_to_s16(180.0) == 32768
    assert S.deg_to_s16(360.0) == 0
    assert S.deg_to_s16(-90.0) == 49152


def test_s16_signed():
    assert S.s16_signed(0) == 0
    assert S.s16_signed(32767) == 32767
    assert S.s16_signed(0x8000) == -32768
    assert S.s16_signed(65535) == -1
    assert S.s16_signed(49152) == -16384


# ---------------------------------------------------------------------------
# incr / neutral_anim_rate: SWIMING / SWIMWAIT anim rates.
# ---------------------------------------------------------------------------
class TestAnimRates:
    def test_incr_known_values(self):
        # Frozen from the current sim (decomp f32 order). High speed / high air.
        assert S.incr(-1630.0, 900) == 45.87666702270508
        assert S.incr(0.0, 900) == 0.5988888740539551

    def test_incr_air_dependence(self):
        # getSwimTimerRate term: higher air -> lower timer contribution.
        assert S.incr(0.0, 900) != S.incr(0.0, 0)
        assert S.incr(0.0, 0) == pytest.approx(1.5989, abs=1e-3)  # rate 0.6 + timer ~1.0

    def test_incr_is_f32(self):
        for v, air in ((-1630.0, 900), (0.0, 450), (-50.0, 120)):
            r = S.incr(v, air)
            assert S.f32(r) == r

    def test_neutral_anim_rate_known(self):
        assert S.neutral_anim_rate(900) == 0.4972221255302429
        assert S.neutral_anim_rate(0) == 2.9972221851348877

    def test_neutral_anim_rate_is_f32(self):
        for air in (900, 615, 120, 0):
            r = S.neutral_anim_rate(air)
            assert S.f32(r) == r


# ---------------------------------------------------------------------------
# af_drag / release_ess_speed / air_drag / true_disp
# ---------------------------------------------------------------------------
class TestDrag:
    def test_af_drag_peak_is_drag_free(self):
        # anim=0 -> |cos|=1 -> af_drag == v (head-bob peak, lossless).
        assert S.af_drag(-1000.0, 0.0) == -1000.0

    def test_af_drag_offpeak_loss(self):
        # anim 11.5 -> cos(pi*11.5/23)=cos(pi/2)~0 -> 0.6*v.
        assert S.af_drag(-1000.0, 11.5) == pytest.approx(-600.0, abs=1.0)
        assert abs(S.af_drag(-1000.0, 11.5)) < 1000.0

    def test_release_ess_speed_peak(self):
        # rel_anim=0 -> |cos(0)|=1 -> release == v (the neutral-dip lossless exit).
        assert S.release_ess_speed(-1000.0, 0.0) == -1000.0

    def test_release_ess_speed_offpeak_distinct_from_af_drag(self):
        # release_ess_speed uses a DIFFERENT f32 order than af_drag; off-peak they need
        # not be identical, but both lose magnitude.
        r = S.release_ess_speed(-1000.0, 11.5)
        assert abs(r) < 1000.0

    def test_air_drag_high_air_near_lossless(self):
        # air=900: 18000/(24300-6300) = 18000/18000 = 1.0 -> lossless.
        assert S.air_drag(-1000.0, 900) == pytest.approx(-1000.0, abs=1e-6)

    def test_air_drag_low_air_loses(self):
        # air=0: 18000/24300 = 0.7407.
        assert S.air_drag(-1000.0, 0) == pytest.approx(-740.74, abs=0.01)

    def test_true_disp_composition(self):
        v, anim, air = -1234.0, 7.3, 555
        assert S.true_disp(v, anim, air) == S.air_drag(S.af_drag(v, anim), air)
