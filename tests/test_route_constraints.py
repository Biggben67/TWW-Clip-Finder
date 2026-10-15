import json
from pathlib import Path

import pytest

from harness.rollstab.route_constraints import BoundedBands, FacingRanges, search_facing_passes


def test_bounded_bands_match_top_ranked_interleaving():
    candidates = [
        (band, abs(index - 7) / 10, (index, band))
        for index in range(30) for band in range(3)
    ]
    selector = BoundedBands(3, 4)
    for band, distance, trial in candidates:
        selector.add(band, distance, trial)
    expected_bands = [sorted((distance, trial) for group, distance, trial in candidates
                             if group == band)[:4] for band in range(3)]
    expected = [bucket[index][1] for index in range(4) for bucket in expected_bands]
    assert selector.interleaved(12) == expected
    assert all(len(heap) <= 4 for heap in selector.heaps)


def test_bounded_bands_skip_unpromising_trials_and_deduplicate_output():
    selector = BoundedBands(2, 1)
    selector.add(0, 0.5, (1, 2))
    selector.add(0, 0.1, (3, 4))
    selector.add(0, 0.2, (5, 6))
    selector.add(1, 0.1, (3, 4))
    assert not selector.promising(0, 0.2)
    assert selector.interleaved(2) == [(3, 4)]
    assert selector.interleaved(0) == []


def test_bounded_bands_replace_a_duplicate_with_its_better_prediction():
    selector = BoundedBands(1, 2)
    selector.add(0, 0.5, (1, 2))
    selector.add(0, 0.4, (3, 4))
    selector.add(0, 0.1, (1, 2))
    assert selector.interleaved(2) == [(1, 2), (3, 4)]


@pytest.mark.parametrize("text,angle,distance", [
    ("0-65535", 32768, 0), ("65000-1000", 65535, 0), ("65000-1000", 0, 0),
    ("65000-1000", 1001, 1), ("0", 65535, 1), ("100-200,300-400", 350, 0),
    ("100-200,300-400", 250, 50), ("30000-34000", -32768, 0),
])
def test_circular_facing_ranges(text, angle, distance):
    assert FacingRanges.parse(text).distance(angle) == distance


@pytest.mark.parametrize("text", ["", "-1", "65536", "a", "1-2-3", "1,", "1.5"])
def test_invalid_ranges_are_rejected_before_capture(text):
    with pytest.raises(ValueError):
        FacingRanges.parse(text)


def test_expansion_wraps_and_merges_without_excluding_requested_angles():
    ranges = FacingRanges.parse("10-20, 35-50")
    grown = ranges.expanded(10)
    assert str(grown) == "0-60"
    wrapped = FacingRanges.parse("0").expanded(128)
    assert str(wrapped) == "0-128, 65408-65535"
    assert ranges.expanded(32768) == FacingRanges()


def fake_search(tmp_path, success_at):
    calls = []

    def search(allowed, index):
        calls.append(allowed)
        return dict(exact=not allowed.distance(success_at), evaluations=10,
                    result_path=str(tmp_path / "result.json"), facing=success_at)

    return calls, search


def test_search_exhausts_preference_then_widens_and_records_total_work(tmp_path):
    calls, search = fake_search(tmp_path, 201)
    result = search_facing_passes(search, "100-200", True, lambda _: None, lambda: False)
    assert len(calls) == 2 and calls[0].distance(201) == 1
    assert result["exact"] and result["facing_range_widened"]
    assert result["evaluations"] == 20 and result["range_evaluations"] == 10
    assert result["requested_facing_ranges"] == "100-200"
    assert json.loads(Path(result["result_path"]).read_text()) == result


@pytest.mark.parametrize("text,widen", [("0-65535", True), ("100-200", False)])
def test_full_range_and_strict_mode_have_only_one_pass(tmp_path, text, widen):
    calls, search = fake_search(tmp_path, 30000)
    search_facing_passes(search, text, widen, lambda _: None, lambda: False)
    assert len(calls) == 1


def test_widening_is_bounded_at_full_circle_even_without_a_hit(tmp_path):
    calls = []

    def search(allowed, index):
        calls.append(allowed)
        return dict(exact=False, evaluations=5, result_path=str(tmp_path / "result.json"))

    result = search_facing_passes(search, "100", True, lambda _: None, lambda: False)
    assert len(calls) == 6 and calls[-1] == FacingRanges()
    assert result["evaluations"] == 30


def test_cancellation_stops_before_next_range(tmp_path):
    calls, search = fake_search(tmp_path, 30000)
    with pytest.raises(RuntimeError, match="cancelled"):
        search_facing_passes(search, "100", True, lambda _: None, lambda: bool(calls))
    assert len(calls) == 1


def test_slash_constraint_uses_slash_facing_not_travel():
    from test_native_route import _native_family, _grounded_crossing

    family = _native_family()
    family.facing_ranges = FacingRanges.parse("65000-1000")
    replay = _grounded_crossing()
    replay["frames"][0].update(facing=65535, travel=30000)
    assert family._result((), replay, "test").exact
    replay["frames"][0]["facing"] = 1001
    result = family._result((), replay, "test")
    assert not result.exact and result.aim_error == 1
    assert not family.family_has_dust(result)
