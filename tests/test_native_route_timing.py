from dataclasses import replace
import struct

import pytest

from harness.rollstab.native_route import NativeFamily, decode_row, infer_input_delay
from harness.rollstab.native_route_timing import align_movie_polls, pad_matches
from harness.rollstab.recorded_route import (
    RecordedRoute, encode_controller_row, patch_route_movie, read_dtm_poll_rows,
    read_dtm_vi_rows,
)


def capture(tmp_path):
    # Includes a one-VI gameplay update and an L+B pulse hidden by VI downsampling.
    rows = [dict(stickX=31, stickY=205, substickX=133, substickY=3,
                 buttons=0, triggerL=0, triggerR=0) for _ in range(32)]
    rows[8:12] = [dict(rows[0], stickX=179, stickY=240)] * 4
    rows[12:18] = [dict(rows[8], buttons=0x40, triggerL=255)] * 6
    rows[18:20] = [dict(rows[8], stickX=224, stickY=217, buttons=0x240, triggerL=255)] * 2
    rows[20:] = [dict(rows[8], stickX=224, stickY=217, buttons=0x200)] * 12
    header = bytearray(256)
    header[:4], header[11] = b"DTM\x1a", 3
    struct.pack_into("<Q", header, 13, 16)
    movie = tmp_path / "movie.dtm"
    other = encode_controller_row(dict(stickX=128, stickY=128))
    movie.write_bytes(header + b"".join(other + encode_controller_row(r) for r in rows))
    frames = [{"emu_frame": vi} for vi in (3, 5, 7, 9, 10, 12)]
    seeds = [{"pad": decode_row(rows[0])}]
    seeds += [{"pad": decode_row(rows[f["emu_frame"] * 2 - 6])} for f in frames]
    route = RecordedRoute(movie, tmp_path / "base.sav", 0, 12, 1,
                          tuple(rows[i * 4 + 1] for i in range(6)))
    return route, frames, seeds


def test_poll_alignment_handles_one_vi_update_and_hidden_button_pulse(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    assert infer_input_delay(timed.rows, seeds) == 2
    assert timed.poll_spans[:4] == ((4, 8), (8, 12), (12, 14), (14, 18))
    assert timed.rows[4]["buttons"] == 0x240  # Downsampled route row 4 misses B.
    assert align_movie_polls(timed, frames, seeds, decode_row) == timed


def test_poll_alignment_uses_dtm_frame_to_poll_bias(tmp_path):
    route, frames, seeds = capture(tmp_path)
    data = bytearray(route.movie.read_bytes())
    struct.pack_into("<Q", data, 13, 2816)
    route.movie.write_bytes(data)
    shifted = replace(route, start_vi=2800, end_vi=2812)
    frames = [dict(frame, emu_frame=frame["emu_frame"] + 2800) for frame in frames]
    timed = align_movie_polls(shifted, frames, seeds, decode_row)
    assert timed.poll_spans[:4] == ((4, 8), (8, 12), (12, 14), (14, 18))


def test_poll_alignment_never_fits_each_transition_independently(tmp_path):
    route, frames, seeds = capture(tmp_path)
    seeds[-1]["pad"]["mx"] += 0.001
    with pytest.raises(RuntimeError, match="cannot be matched"):
        align_movie_polls(route, frames, seeds, decode_row)


def test_poll_alignment_handles_mid_route_poll_phase_change(tmp_path):
    polls = [dict(stickX=128, stickY=128, substickX=128, substickY=128,
                  buttons=0, triggerL=0, triggerR=0) for _ in range(32)]
    sources = [2, 6, 10, 14, 19]
    for index, source in enumerate(sources):
        polls[source] = dict(polls[source], stickX=150 + index * 10)
    header = bytearray(256)
    header[:4], header[11] = b"DTM\x1a", 1
    movie = tmp_path / "variable_phase.dtm"
    movie.write_bytes(header + b"".join(encode_controller_row(row) for row in polls))
    route = RecordedRoute(movie, tmp_path / "base.sav", 0, 12, 0,
                          tuple(polls[index * 4] for index in range(6)))
    frames = [{"emu_frame": vi} for vi in (2, 4, 6, 8, 10, 12)]
    seeds = [{"pad": decode_row(polls[0])}] * 2 + [
        {"pad": decode_row(polls[source])} for source in sources]
    timed = align_movie_polls(route, frames, seeds, decode_row)
    assert timed.poll_spans[:5] == ((2, 6), (6, 10), (10, 14), (14, 19), (19, 23))
    assert all(pad_matches(decode_row(polls[a]), seeds[index + 2]["pad"])
               for index, (a, _) in enumerate(timed.poll_spans[:5]))


def test_unchanged_timed_movie_export_is_byte_identical(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    output = patch_route_movie(timed, timed.rows, tmp_path / "unchanged.dtm")
    assert output.read_bytes() == route.movie.read_bytes()


def test_timed_patch_preserves_other_lane_and_unedited_field_transitions(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    # A C-stick transition between sampled polls must survive a main-stick edit.
    data = bytearray(route.movie.read_bytes())
    offset = 256 + (5 * 2 + 1) * 8
    data[offset + 6] = 237
    route.movie.write_bytes(data)
    original = read_dtm_poll_rows(route.movie, 1)
    rows = [dict(r) for r in timed.rows]
    rows[0]["stickX"] = 100
    output = patch_route_movie(timed, rows, tmp_path / "edited.dtm")
    actual = read_dtm_poll_rows(output, 1)
    assert actual == [dict(r, stickX=100) if 4 <= i < 8 else r for i, r in enumerate(original)]
    assert read_dtm_poll_rows(output, 0) == read_dtm_poll_rows(route.movie, 0)
    assert actual[5]["substickX"] == 237


def test_search_inputs_equal_exported_polls_after_stick_and_button_edits(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    family = object.__new__(NativeFamily)
    family.anchor_row, family.input_delay = 1, 2
    family.seeds, family.base_rows = seeds, list(timed.rows)
    rows = [dict(r) for r in timed.rows]
    rows[1].update(stickX=100, substickY=89, buttons=0x200)
    output = patch_route_movie(timed, rows, tmp_path / "candidate.dtm")
    polls = read_dtm_poll_rows(output, 1)
    pads = family._effective_rows(rows, len(seeds))
    assert all(pad_matches(decode_row(polls[timed.poll_spans[j][0]]), pad)
               for j, pad in enumerate(pads))


def test_extended_poll_route_uses_contiguous_source_spans(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    rows = list(timed.rows) + [dict(timed.rows[-1], buttons=0, stickX=128)] * 4
    output = patch_route_movie(timed, rows, tmp_path / "long.dtm", extend=True)
    actual = read_dtm_poll_rows(output, 1)
    assert actual[-1]["buttons"] == 0 and actual[-1]["stickX"] == 128
    assert actual[:4] == read_dtm_poll_rows(route.movie, 1)[:4]


def test_timed_export_rejects_overlapping_poll_spans(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    timed = replace(timed, poll_spans=((4, 9), *timed.poll_spans[1:]))
    with pytest.raises(ValueError, match="not contiguous"):
        patch_route_movie(timed, timed.rows, tmp_path / "bad.dtm")


def test_extended_timed_baseline_writes_neutral_tail_instead_of_holding_last_button(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    spans = list(timed.poll_spans)
    while len(spans) < 10:
        spans.append((spans[-1][1], spans[-1][1] + 4))
    neutral = dict(timed.rows[-1], buttons=0, triggerL=0, stickX=128, stickY=128)
    timed = replace(timed, rows=(*timed.rows, *[neutral] * 4), poll_spans=tuple(spans))
    output = patch_route_movie(timed, timed.rows, tmp_path / "tail.dtm", extend=True)
    assert read_dtm_poll_rows(output, 1)[-1] == neutral


def test_strict_vi_reader_still_checks_non_button_movie_flags(tmp_path):
    route, frames, seeds = capture(tmp_path)
    data = bytearray(route.movie.read_bytes())
    data[256 + (1 * 2 + 1) * 8 + 1] ^= 0x10
    route.movie.write_bytes(data)
    with pytest.raises(ValueError, match="mixed polls"):
        read_dtm_vi_rows(route.movie, 1, strict=True)


def test_owned_suffix_removes_hidden_b_edge_even_if_sampled_buttons_unchanged(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    data = bytearray(route.movie.read_bytes())
    # The authored sample says no B; the unsampled poll still has an old B pulse.
    data[256 + (5 * 2 + 1) * 8] |= 0x02
    route.movie.write_bytes(data)
    output = patch_route_movie(timed, timed.rows, tmp_path / 'owned.dtm', replace_from=0)
    actual = read_dtm_poll_rows(output, 1)
    assert all(actual[p] == row for (a, b), row in zip(timed.poll_spans, timed.rows)
               for p in range(a, b))
    assert read_dtm_poll_rows(output, 0) == read_dtm_poll_rows(route.movie, 0)


def test_gameplay_poll_clock_does_not_stretch_inputs_with_lag_vis(tmp_path):
    route, frames, seeds = capture(tmp_path)
    seeds = [seeds[0], seeds[1], *[{'pad': decode_row(read_dtm_poll_rows(route.movie, 1)[2+i*4])}
                                 for i in range(len(frames)-1)]]
    timed = align_movie_polls(route, frames, seeds, decode_row)
    assert timed.poll_spans == tuple((2+4*i, 6+4*i) for i in range(len(frames)))
    assert infer_input_delay(timed.rows, seeds) == 2


def test_owned_suffix_does_not_rewrite_prefix(tmp_path):
    route, frames, seeds = capture(tmp_path)
    timed = align_movie_polls(route, frames, seeds, decode_row)
    output = patch_route_movie(timed, timed.rows, tmp_path / 'prefix.dtm', replace_from=2)
    prefix = 256 + timed.poll_spans[2][0] * 16
    assert output.read_bytes()[:prefix] == route.movie.read_bytes()[:prefix]


def test_owned_export_uses_block_beginning_not_a_matching_poll_inside_it(tmp_path):
    route, frames, seeds = capture(tmp_path)
    header = route.movie.read_bytes()[:256]
    other = encode_controller_row(dict(stickX=128, stickY=128))
    blocks = [dict(stickX=100 + i // 4 * 7, stickY=200, substickX=128, substickY=100,
                   buttons=0x200 if i // 4 == 4 else 0, triggerL=0, triggerR=0) for i in range(32)]
    route.movie.write_bytes(header + b''.join(other + encode_controller_row(row) for row in blocks))
    polls = read_dtm_poll_rows(route.movie, 1)
    seeds = [seeds[0], seeds[1], *[{'pad': decode_row(polls[2 + i * 4])}
                                 for i in range(len(frames) - 1)]]
    sampled = align_movie_polls(route, frames, seeds, decode_row)
    assert sampled.poll_spans[0] == (2, 6)
    owned = align_movie_polls(sampled, frames, seeds, decode_row, owned_spans=True)
    assert owned.poll_spans[0] == (0, 4)
    assert infer_input_delay(owned.rows, seeds) == 2
    rows = [dict(row) for row in owned.rows]
    rows[1].update(stickX=165, stickY=250, buttons=0x200)
    output = patch_route_movie(owned, rows, tmp_path / 'owned_sync.dtm', replace_from=1)
    edited = read_dtm_poll_rows(output, 1)
    assert edited[4:8] == [rows[1]] * 4
    assert edited[:4] == polls[:4]
    assert read_dtm_poll_rows(output, 0) == read_dtm_poll_rows(route.movie, 0)


def test_owned_export_keeps_nonzero_phase_when_captured_inputs_require_it(tmp_path):
    route, frames, seeds = capture(tmp_path)
    data = bytearray(route.movie.read_bytes())
    polls = read_dtm_poll_rows(route.movie, 1)
    shifted = [polls[0], polls[0], *polls[:-2]]
    other = encode_controller_row(dict(stickX=128, stickY=128))
    route.movie.write_bytes(data[:256] + b''.join(other + encode_controller_row(row) for row in shifted))
    seeds = [seeds[0], seeds[1], *[{'pad': decode_row(shifted[2 + i * 4])}
                                 for i in range(len(frames) - 1)]]
    owned = align_movie_polls(route, frames, seeds, decode_row, owned_spans=True)
    assert owned.poll_spans[0] == (2, 6)


def test_owned_export_accounts_for_four_vi_opening_update(tmp_path):
    route, frames, seeds = capture(tmp_path)
    header = route.movie.read_bytes()[:256]
    other = encode_controller_row(dict(stickX=128, stickY=128))
    blocks = [dict(stickX=100 + i // 4 * 7, stickY=200, substickX=128, substickY=100,
                   buttons=0, triggerL=0, triggerR=0) for i in range(32)]
    route.movie.write_bytes(header + b''.join(other + encode_controller_row(row) for row in blocks))
    frames = [{'emu_frame': 4 + 2 * i} for i in range(len(frames))]
    seeds = [seeds[0], seeds[1], *[{'pad': decode_row(blocks[6 + i * 4])}
                                 for i in range(len(frames) - 1)]]
    # The old fallback samples halfway into each held block at poll 6.
    route = replace(route, rows=tuple(blocks[6 + i * 4] for i in range(len(frames))),
                    poll_spans=tuple((6 + i * 4, 10 + i * 4) for i in range(len(frames))))
    owned = align_movie_polls(route, frames, seeds, decode_row, owned_spans=True)
    assert owned.poll_spans[0] == (4, 8)
    assert infer_input_delay(owned.rows, seeds) == 2
    rows = [dict(row) for row in owned.rows]
    rows[1].update(stickX=167, stickY=250, buttons=0x200)
    output = patch_route_movie(owned, rows, tmp_path / 'opening_lag_sync.dtm', replace_from=1)
    polls = read_dtm_poll_rows(output, 1)
    assert polls[8:12] == [rows[1]] * 4
    assert polls[:8] == blocks[:8]
