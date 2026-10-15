"""Bind native CPAD samples to exact movie polls, including uneven VI updates."""
from dataclasses import replace
import struct

from harness.rollstab.recorded_route import POLLS_PER_VI, movie_poll_bias, read_dtm_poll_rows


def pad_matches(decoded, captured):
    for key in ("mx", "my", "cx", "cy", "distance", "cvalue", "tl", "tr"):
        if struct.pack(">f", decoded[key]) != struct.pack(">f", captured[key]):
            return False
    # CPAD retains its last angle when a stick returns to neutral.
    for angle, magnitude in (("angle", "distance"), ("cangle", "cvalue")):
        if decoded[magnitude] and decoded[angle] & 65535 != captured[angle] & 65535:
            return False
    return all(decoded[key] == captured[key] for key in ("item_button", "target"))


def _variable_poll_sources(frames, seeds, start_poll, matches, bias=0):
    """Align samples through lag VIs without fitting each input edge independently."""
    previous = {}
    paths = []
    for index in range(2, len(seeds)):
        vi = int(frames[index - 1]["emu_frame"])
        clock = vi * POLLS_PER_VI + bias
        candidates = [clock - lag for lag in range(3, 13)
                      if clock - lag >= start_poll
                      and matches(clock - lag, seeds[index]["pad"])]
        current = {}
        for poll in candidates:
            lag_cost = abs(clock - poll - 7)
            if index == 2:
                current[poll] = (lag_cost, None)
                continue
            expected_stride = (vi - int(frames[index - 2]["emu_frame"])) * POLLS_PER_VI
            options = [(cost + lag_cost + 4 * abs(poll - prior - expected_stride), prior)
                       for prior, (cost, _) in previous.items() if poll > prior]
            if options:
                current[poll] = min(options)
        if not current:
            return None
        paths.append(current)
        previous = current
    if not paths:
        return None
    poll = min(previous, key=lambda source: (previous[source][0], source))
    sources = []
    for current in reversed(paths):
        sources.append(poll)
        poll = current[poll][1]
    return list(reversed(sources))


def align_movie_polls(route, frames, seeds, decode, *, owned_spans=False):
    """Return logical search rows with independently verified export poll spans.

    Two leading native updates retain the original input pipeline. Editable rows
    start at seed 2; their source polls are derived from measured VI timestamps,
    not from an assumed constant number of VIs per gameplay update.
    """
    if not frames or any("emu_frame" not in f for f in frames):
        return route
    if len(seeds) != len(frames) + 1 or len(route.rows) != len(frames):
        raise RuntimeError("controller capture length does not match the gameplay trace")
    polls = read_dtm_poll_rows(route.movie, route.controller)
    bias = movie_poll_bias(route.movie)
    start_poll = route.start_vi * POLLS_PER_VI + bias
    decoded = {}
    def matches(index, pad):
        if not 0 <= index < len(polls):
            return False
        if index not in decoded:
            decoded[index] = decode(polls[index])
        return pad_matches(decoded[index], pad)
    if owned_spans:
        # A matching sample inside a held four-poll block does not identify its
        # beginning. Owning the whole suffix requires the original block phase,
        # otherwise new edges are exported one gameplay update too late.
        candidates = []
        # A saved state can open with extra lag VIs before its first update.
        # Include that measured delay, still verifying a single poll clock
        # against every captured CPAD rather than fitting individual edges.
        opening_lag_polls = max(0, int(frames[0]["emu_frame"]) - route.start_vi - 2) * POLLS_PER_VI
        for phase in range(4 + opening_lag_polls):
            first = start_poll + phase
            sources = [first + 4 * i for i in range(len(route.rows) + 1)]
            if not all(matches(sources[i - 2], seeds[i]["pad"])
                       for i in range(2, len(seeds))):
                continue
            splits = sum(polls[index] != polls[start]
                         for start, end in zip(sources, sources[1:])
                         if start < len(polls)
                         for index in range(start, min(end, len(polls))))
            candidates.append((splits, phase, sources))
        if candidates:
            _, _, sources = min(candidates)
            rows = tuple(dict(polls[p] if p < len(polls) else route.rows[-1]) for p in sources[:-1])
            return replace(route, rows=rows, poll_spans=tuple(zip(sources, sources[1:])))
    # Gameplay polls can stay four apart while VIs vary (render/lag phases).
    # Verify that clock against every CPAD sample before falling back to VI time.
    first = start_poll + 2
    game_sources = [first + 4 * i for i in range(len(route.rows) + 1)]
    if all(matches(game_sources[i - 2], seeds[i]["pad"])
           for i in range(2, len(seeds))):
        spans = tuple(zip(game_sources, game_sources[1:]))
        rows = tuple(dict(polls[p] if p < len(polls) else route.rows[-1])
                     for p in game_sources[:-1])
        return replace(route, rows=rows, poll_spans=spans)
    if route.poll_spans:
        return route
    # Select a single poll-clock latency that explains every observed input.
    # Do not independently pick a convenient matching row at each transition.
    lags = [lag for lag in (6, 5, 7, 8, 4, 9, 10, 3, 2, 1, 0, 11, 12)
            if all(matches(int(f["emu_frame"]) * POLLS_PER_VI + bias - lag, seed["pad"])
                   for f, seed in zip(frames, seeds[1:]))]
    if not lags:
        sources = _variable_poll_sources(
            frames, seeds, start_poll, matches, bias)
        if sources is None:
            raise RuntimeError("controller capture cannot be matched to the original DTM polls; "
                               "the selected controller or movie differs from the live input")
        while len(sources) <= len(route.rows):
            sources.append(sources[-1] + 4)
        spans = tuple(zip(sources, sources[1:]))
        rows = tuple(dict(polls[p] if p < len(polls) else route.rows[-1])
                     for p in sources[:-1])
        return replace(route, rows=rows, poll_spans=spans)
    lag = lags[0]
    sources = [int(f["emu_frame"]) * POLLS_PER_VI + bias - lag for f in frames[1:]]
    if not sources or sources[0] < start_poll:
        raise RuntimeError("editable controller polls precede the saved starting state")
    if any(b <= a for a, b in zip(sources, sources[1:])):
        raise RuntimeError("captured movie poll clock did not advance monotonically")
    while len(sources) <= len(route.rows):
        sources.append(sources[-1] + 4)
    spans = tuple(zip(sources, sources[1:]))
    rows = tuple(dict(polls[p] if p < len(polls) else route.rows[-1])
                 for p in sources[:-1])
    return replace(route, rows=rows, poll_spans=spans)
