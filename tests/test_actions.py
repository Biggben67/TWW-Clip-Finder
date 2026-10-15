"""Unit tests for tww_sim.swim.actions: expand / acts_to_seq / animdiff.

Pure offline. 3.7-compatible.
"""
import pytest

from tww_sim.swim import actions as A


# ---------------------------------------------------------------------------
# expand: run-length seq string -> flat action list.
# ---------------------------------------------------------------------------
class TestExpand:
    def test_basic(self):
        assert A.expand("ess,3;chg,2;neu,1") == [
            "ess", "ess", "ess", "chg", "chg", "neu"]

    def test_empty_segments_skipped(self):
        assert A.expand("ess,2;;neu,1") == ["ess", "ess", "neu"]
        assert A.expand(";ess,1;") == ["ess"]

    def test_whitespace_stripped(self):
        assert A.expand("  ess,2;neu,1  \n") == ["ess", "ess", "neu"]

    def test_empty_string(self):
        assert A.expand("") == []
        assert A.expand("   ") == []

    def test_single_segment(self):
        assert A.expand("chg,5") == ["chg"] * 5

    def test_does_not_validate_action_name(self):
        # expand is a pure run-length parse; it does NOT reject unknown actions
        # (acts_to_seq does). Frozen so callers know which layer validates.
        assert A.expand("bogus,2") == ["bogus", "bogus"]


# ---------------------------------------------------------------------------
# acts_to_seq: action list -> advanceseq stick element list (charge parity).
# ---------------------------------------------------------------------------
class TestActsToSeq:
    def test_ess_neu_sticks(self):
        out = A.acts_to_seq(["ess", "neu"])
        assert out[0] == {"stickX": 128, "stickY": 110, "substickY": 0, "frames": 1}
        assert out[1] == {"stickX": 128, "stickY": 128, "substickY": 0, "frames": 1}

    def test_charge_alternates_up_down_by_parity(self):
        out = A.acts_to_seq(["chg", "chg", "chg", "chg"])
        # chg#1 = UP (odd), chg#2 = DN, chg#3 = UP, chg#4 = DN.
        assert (out[0]["stickX"], out[0]["stickY"]) == A.CHG_UP
        assert (out[1]["stickX"], out[1]["stickY"]) == A.CHG_DN
        assert (out[2]["stickX"], out[2]["stickY"]) == A.CHG_UP
        assert (out[3]["stickX"], out[3]["stickY"]) == A.CHG_DN

    def test_charge_parity_counts_only_charges(self):
        # ESS frames between charges must not change the charge parity.
        out = A.acts_to_seq(["chg", "ess", "chg"])
        assert (out[0]["stickX"], out[0]["stickY"]) == A.CHG_UP
        assert (out[2]["stickX"], out[2]["stickY"]) == A.CHG_DN

    def test_partial_ess_hold_stick(self):
        # 'ess:<rawY>' = a partial on-axis hold: literal stick (128, rawY), no parity.
        out = A.acts_to_seq(["ess:77", "ess:95"])
        assert (out[0]["stickX"], out[0]["stickY"]) == (128, 77)
        assert (out[1]["stickX"], out[1]["stickY"]) == (128, 95)

    def test_partial_charge_mirrors_down_stroke_about_128(self):
        # 'chg:<up>' alternates like 'chg' but the DOWN stroke mirrors (256-up), matching
        # SwimState._chg_stick(up_raw). chg#1=UP=(128,up), chg#2=DN=(128,256-up).
        out = A.acts_to_seq(["chg:200", "chg:200"])
        assert (out[0]["stickX"], out[0]["stickY"]) == (128, 200)
        assert (out[1]["stickX"], out[1]["stickY"]) == (128, 56)

    def test_partial_charge_shares_parity_with_full_charge(self):
        # a full 'chg' and a partial 'chg:<up>' both advance the same charge counter.
        out = A.acts_to_seq(["chg", "chg:190"])
        assert (out[0]["stickX"], out[0]["stickY"]) == A.CHG_UP          # chg#1 = UP
        assert (out[1]["stickX"], out[1]["stickY"]) == (128, 256 - 190)  # chg#2 = DN mirror

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError):
            A.acts_to_seq(["ess", "bad"])

    def test_empty(self):
        assert A.acts_to_seq([]) == []

    def test_all_elements_one_frame(self):
        for el in A.acts_to_seq(["ess", "chg", "neu"]):
            assert el["frames"] == 1
            assert el["substickY"] == 0


# ---------------------------------------------------------------------------
# animdiff: shortest cyclic distance on a period-n controller.
# ---------------------------------------------------------------------------
class TestAnimDiff:
    def test_simple(self):
        assert A.animdiff(1.0, 2.0, 23.0) == 1.0
        assert A.animdiff(5.0, 3.0, 23.0) == 2.0

    def test_wraparound_is_shortest(self):
        # 0 and 22 on a 23-cycle are 1 apart, not 22.
        assert A.animdiff(0.0, 22.0, 23.0) == 1.0
        assert A.animdiff(22.0, 0.0, 23.0) == 1.0

    def test_handles_unreduced_inputs(self):
        # 25 mod 23 = 2, diff to 1 is 1.
        assert A.animdiff(1.0, 25.0, 23.0) == 1.0

    def test_half_cycle(self):
        assert A.animdiff(0.0, 11.5, 23.0) == 11.5

    def test_period_26(self):
        assert A.animdiff(0.0, 25.0, 26.0) == 1.0

    def test_zero_distance(self):
        assert A.animdiff(7.0, 7.0, 23.0) == 0.0
