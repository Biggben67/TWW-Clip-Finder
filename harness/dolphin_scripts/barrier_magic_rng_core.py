"""Pure scheduling helpers for Barrier Grass Magic Brute Force."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Pulse:
    row: int
    ensure_drawn: bool = False


def row_has_button(state: Mapping[str, object], button: str) -> bool:
    return bool(state.get(button, False))


def eligible_pulse_rows(
    negative_rows: Iterable[int],
    base_rows: Mapping[int, Mapping[str, object]],
    start_row: int,
    deadline_row: int,
    edge_padding: int = 2,
) -> list[int]:
    """Return negative-speed rows where an isolated A/B rising edge is safe to author."""
    result = []
    for row in sorted(set(int(value) for value in negative_rows)):
        if row < start_row + edge_padding or row > deadline_row:
            continue
        states = (base_rows.get(row - 1), base_rows.get(row), base_rows.get(row + 1))
        if any(state is None for state in states):
            continue
        if any(row_has_button(state, button) for state in states for button in ("A", "B")):
            continue
        result.append(row)
    return result


def _spaced(rows: Sequence[int], minimum_gap: int) -> list[int]:
    selected = []
    for row in sorted(rows):
        if not selected or row - selected[-1] >= minimum_gap:
            selected.append(row)
    return selected


def build_schedule(
    eligible_rows: Sequence[int],
    rng: random.Random,
    minimum_gap: int = 14,
    maximum_random_pulses: int = 10,
) -> list[Pulse]:
    """Build random toggle opportunities plus a final draw-safety opportunity."""
    rows = sorted(set(int(row) for row in eligible_rows))
    if not rows:
        return []

    ensure_row = rows[-1]
    random_pool = [row for row in rows if ensure_row - row >= minimum_gap]
    rng.shuffle(random_pool)
    desired = rng.randint(1, max(1, min(maximum_random_pulses, len(random_pool)))) if random_pool else 0

    chosen = []
    for row in random_pool:
        if all(abs(row - other) >= minimum_gap for other in chosen):
            chosen.append(row)
            if len(chosen) >= desired:
                break

    chosen = _spaced(chosen, minimum_gap)
    return [Pulse(row) for row in chosen] + [Pulse(ensure_row, ensure_drawn=True)]


def schedule_signature(schedule: Sequence[Pulse]) -> tuple[int, ...]:
    return tuple(pulse.row for pulse in schedule)
