"""Circular facing preferences shared by the native route finders."""
from dataclasses import dataclass
import heapq
import json
from pathlib import Path
import re


class BoundedBands:
    """Retain only the best predicted input trials in each float32 target band."""

    def __init__(self, count, width):
        self.heaps = [[] for _ in range(count)]
        self.members = [set() for _ in range(count)]
        self.width = width

    def promising(self, band, distance):
        heap = self.heaps[band]
        return len(heap) < self.width or distance <= -heap[0][0]

    def add(self, band, distance, trial):
        if not self.promising(band, distance):
            return
        heap = self.heaps[band]
        if trial in self.members[band]:
            index = next(index for index, entry in enumerate(heap) if entry[2] == trial)
            if distance >= -heap[index][0]:
                return
            heap.pop(index)
            heapq.heapify(heap)
            self.members[band].remove(trial)
        # Negated bytes make the lexicographically largest equal-distance
        # trial the first one evicted, matching sorted(..., key=(error, trial)).
        entry = (-distance, tuple(-value for value in trial), trial)
        if len(heap) == self.width:
            removed = heapq.heappushpop(heap, entry)
            if removed is entry:
                return
            self.members[band].remove(removed[2])
        else:
            heapq.heappush(heap, entry)
        self.members[band].add(trial)

    def interleaved(self, limit):
        if limit <= 0:
            return []
        bands = [sorted(((-error, trial) for error, _, trial in heap))
                 for heap in self.heaps]
        result, seen = [], set()
        for index in range(self.width):
            for band in bands:
                if index < len(band):
                    trial = band[index][1]
                    if trial not in seen:
                        result.append(trial)
                        seen.add(trial)
                        if len(result) >= limit:
                            return result
        return result


@dataclass(frozen=True)
class FacingRanges:
    intervals: tuple = ((0, 65535),)

    def __post_init__(self):
        if not self.intervals or any(type(a) is not int or type(b) is not int
                                     or not 0 <= a <= b <= 65535 for a, b in self.intervals):
            raise ValueError("invalid facing intervals")

    @classmethod
    def parse(cls, value="0-65535"):
        if isinstance(value, cls):
            return value
        intervals = []
        for part in str(value).strip().split(","):
            match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
            if not match:
                raise ValueError("facing ranges must be angles or ranges, e.g. 30000-34000, 65000-1000")
            a, b = int(match[1]), int(match[2] or match[1])
            if not 0 <= a <= 65535 or not 0 <= b <= 65535:
                raise ValueError("facing angles must be between 0 and 65535")
            intervals.extend(((a, b),) if a <= b else ((0, b), (a, 65535)))
        return cls._merged(intervals)

    @classmethod
    def _merged(cls, intervals):
        merged = []
        for a, b in sorted(intervals):
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        return cls(tuple(merged))

    def distance(self, angle):
        angle = int(angle) & 65535
        if any(a <= angle <= b for a, b in self.intervals):
            return 0
        return min(min((angle - edge) & 65535, (edge - angle) & 65535)
                   for pair in self.intervals for edge in pair)

    def expanded(self, amount):
        intervals = []
        for a, b in self.intervals:
            if b - a + 1 + 2 * amount >= 65536:
                return FacingRanges()
            lo, hi = a - amount, b + amount
            if lo < 0:
                intervals.append((65536 + lo, 65535))
            if hi > 65535:
                intervals.append((0, hi - 65536))
            intervals.append((max(0, lo), min(65535, hi)))
        return self._merged(intervals)

    def __str__(self):
        return ", ".join(str(a) if a == b else "%d-%d" % (a, b) for a, b in self.intervals)


def search_facing_passes(search, ranges, widen, log, cancelled):
    """Exhaust a preference before widening; never loosen clip/landing proof."""
    requested = FacingRanges.parse(ranges)
    stages = [requested]
    if widen:
        for amount in (128, 512, 2048, 8192, 32768):
            expanded = requested.expanded(amount)
            if expanded not in stages:
                stages.append(expanded)
    attempts, total, last = [], 0, None
    for index, allowed in enumerate(stages):
        if cancelled():
            raise RuntimeError("search cancelled")
        if index:
            log("No clip at the previous facings; widening to %s (pass %d/%d)."
                % (allowed, index + 1, len(stages)))
        else:
            log("Searching facing range(s): %s." % allowed)
        last = search(allowed, index)
        count = last["evaluations"]
        total += count
        attempts.append(dict(ranges=str(allowed), evaluations=count, exact=bool(last["exact"])))
        if last["exact"]:
            break
    last.update(requested_facing_ranges=str(requested), applied_facing_ranges=str(allowed),
                facing_range_widened=allowed != requested, facing_search_passes=attempts,
                range_evaluations=last["evaluations"], evaluations=total)
    Path(last["result_path"]).write_text(json.dumps(last, indent=2), encoding="ascii")
    return last
