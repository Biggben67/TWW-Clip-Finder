import random

from harness.dolphin_scripts.barrier_magic_rng_core import (
    build_schedule,
    eligible_pulse_rows,
    schedule_signature,
)


def _rows(first, last):
    return {
        row: {"A": False, "B": False}
        for row in range(first - 1, last + 2)
    }


def test_eligible_rows_require_negative_speed_and_clean_button_edges():
    base = _rows(100, 140)
    base[119]["A"] = True
    assert eligible_pulse_rows({101, 110, 118, 120, 130, 141}, base, 100, 140) == [110, 130]


def test_schedule_is_spaced_and_ends_with_draw_safety_pulse():
    schedule = build_schedule(list(range(100, 301)), random.Random(7), minimum_gap=14)
    rows = [pulse.row for pulse in schedule]
    assert rows[-1] == 300
    assert schedule[-1].ensure_drawn
    assert all(right - left >= 14 for left, right in zip(rows, rows[1:]))


def test_seeded_schedule_is_reproducible():
    eligible = list(range(100, 301))
    first = build_schedule(eligible, random.Random(1234))
    second = build_schedule(eligible, random.Random(1234))
    assert schedule_signature(first) == schedule_signature(second)
