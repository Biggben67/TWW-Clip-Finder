"""Recover a short controller route from a Dolphin movie and its savestates.

Zelda TAS Edition stores the current movie VI in a savestate header.  Wind Waker
runs at 30 game frames per second while the movie clock runs at 60 VI/s, so the
cursor identifies the corresponding four-poll controller frame without loading
the state in Dolphin.  This module is deliberately read-only; playback remains
the responsibility of the live solver.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import struct


DTM_HEADER_SIZE = 256
CONTROLLER_ROW_SIZE = 8
SAVESTATE_MOVIE_VI_OFFSET = 0x5D
POLLS_PER_VI = 2


@dataclass(frozen=True)
class RecordedRoute:
    movie: Path
    start_state: Path
    start_vi: int
    end_vi: int
    controller: int
    rows: tuple[dict, ...]
    poll_spans: tuple[tuple[int, int], ...] = ()


def movie_vi_from_savestate(path: str | Path) -> int:
    """Read Zelda TAS Edition's saved movie VI cursor."""
    with Path(path).open("rb") as source:
        source.seek(SAVESTATE_MOVIE_VI_OFFSET - 2)
        raw = source.read(11)
    if len(raw) != 11:
        raise ValueError(f"savestate header is truncated: {path}")
    # The serialized 4-byte cursor is preceded by a 0x04 size tag. The tag
    # shifts one byte left in states saved with a different movie mode.
    offset = 1 if raw[0] == 4 and raw[1] != 4 else 2
    vi = struct.unpack_from("<I", raw, offset)[0]
    if vi >= 1 << 24:
        companion = Path(str(path) + ".dtm")
        if companion.is_file():
            with companion.open("rb") as movie:
                header = movie.read(DTM_HEADER_SIZE)
            if len(header) == DTM_HEADER_SIZE and header[:4] == b"DTM\x1a":
                movie_vi = struct.unpack_from("<Q", header, 13)[0]
                masked = vi & 0xFFFFFF
                if abs(movie_vi - masked) < abs(movie_vi - vi):
                    return masked
    return vi


def movie_poll_bias(path: str | Path) -> int:
    """Map the DTM's VI clock to controller polls at its recorded endpoint."""
    path = Path(path)
    with path.open("rb") as source:
        header = source.read(DTM_HEADER_SIZE)
    if len(header) != DTM_HEADER_SIZE or header[:4] != b"DTM\x1a":
        raise ValueError(f"invalid DTM: {path}")
    frame_count = struct.unpack_from("<Q", header, 13)[0]
    if not frame_count:
        return 0
    width = len(_active_controllers(header))
    polls = (path.stat().st_size - DTM_HEADER_SIZE) // (width * CONTROLLER_ROW_SIZE)
    return polls - frame_count * POLLS_PER_VI


def decode_controller_row(raw: bytes) -> dict:
    if len(raw) != CONTROLLER_ROW_SIZE:
        raise ValueError("a GameCube controller row must contain exactly 8 bytes")
    first, second, trigger_l, trigger_r, stick_x, stick_y, sub_x, sub_y = raw
    buttons = 0
    for mask, value in (
        (0x01, 0x1000), (0x02, 0x0100), (0x04, 0x0200), (0x08, 0x0400),
        (0x10, 0x0800), (0x20, 0x0010), (0x40, 0x0008), (0x80, 0x0004),
    ):
        if first & mask:
            buttons |= value
    for mask, value in ((0x01, 0x0001), (0x02, 0x0002),
                        (0x04, 0x0040), (0x08, 0x0020)):
        if second & mask:
            buttons |= value
    return {
        "stickX": stick_x,
        "stickY": stick_y,
        "substickX": sub_x,
        "substickY": sub_y,
        "buttons": buttons,
        "triggerL": trigger_l,
        "triggerR": trigger_r,
    }


def encode_controller_row(row: dict) -> bytes:
    """Encode one controller poll using the inverse of ``decode_controller_row``."""
    buttons = int(row.get("buttons", 0))
    first = 0
    for value, mask in (
        (0x1000, 0x01), (0x0100, 0x02), (0x0200, 0x04),
        (0x0400, 0x08), (0x0800, 0x10), (0x0010, 0x20),
        (0x0008, 0x40), (0x0004, 0x80),
    ):
        if buttons & value:
            first |= mask
    second = 0x40
    for value, mask in (
        (0x0001, 0x01), (0x0002, 0x02),
        (0x0040, 0x04), (0x0020, 0x08),
    ):
        if buttons & value:
            second |= mask

    def byte(name: str, default: int = 0) -> int:
        return max(0, min(255, int(row.get(name, default))))

    return bytes((
        first, second,
        byte("triggerL"), byte("triggerR"),
        byte("stickX", 128), byte("stickY", 128),
        byte("substickX", 128), byte("substickY", 128),
    ))


def _active_controllers(header: bytes) -> tuple[int, ...]:
    mask = header[11]
    active = tuple(index for index in range(4) if mask & (1 << index))
    if not active:
        raise ValueError("DTM has no active GameCube controllers")
    return active


def _read_dtm_lane(path: str | Path, controller: int) -> list[bytes]:
    data = Path(path).read_bytes()
    header = data[:DTM_HEADER_SIZE]
    if len(header) != DTM_HEADER_SIZE or header[:4] != b"DTM\x1a":
        raise ValueError(f"invalid DTM: {path}")
    active = _active_controllers(header)
    if controller not in active:
        raise ValueError(f"controller {controller + 1} is not active in {path}")
    lane = active.index(controller)
    width = len(active)
    body = data[DTM_HEADER_SIZE:]
    raw_rows = [body[offset:offset + CONTROLLER_ROW_SIZE]
                for offset in range(0, len(body) - CONTROLLER_ROW_SIZE + 1,
                                    CONTROLLER_ROW_SIZE)]
    lane_rows = raw_rows[lane::width]
    return lane_rows


def read_dtm_poll_rows(path: str | Path, controller: int = 0) -> list[dict]:
    """Read every poll for the selected controller without discarding transitions."""
    return [decode_controller_row(raw) for raw in _read_dtm_lane(path, controller)]


def read_dtm_vi_rows(path: str | Path, controller: int = 0,
                     strict: bool = False) -> list[dict]:
    """Return the last poll per VI; exact native capture uses individual polls."""
    lane_rows = _read_dtm_lane(path, controller)
    rows = []
    for offset in range(0, len(lane_rows), POLLS_PER_VI):
        polls = lane_rows[offset:offset + POLLS_PER_VI]
        if len(polls) < POLLS_PER_VI:
            break
        if strict and any(poll != polls[0] for poll in polls[1:]):
            raise ValueError(
                f"controller {controller + 1} has mixed polls in VI "
                f"{offset // POLLS_PER_VI}"
            )
        rows.append(decode_controller_row(polls[-1]))
    return rows


def read_dtm_frames(path: str | Path, controller: int = 0, phase: int = 0) -> list[dict]:
    """Decode 30-fps game inputs for one of the movie's two VI phases."""
    return read_dtm_vi_rows(path, controller=controller)[int(phase) & 1::2]


def extract_route(movie: str | Path, start_state: str | Path,
                  end_state: str | Path, controller: int = 0) -> RecordedRoute:
    """Extract game-frame rows in ``[start_state cursor, end_state cursor)``."""
    movie = Path(movie)
    start_state = Path(start_state)
    start_vi = movie_vi_from_savestate(start_state)
    end_vi = movie_vi_from_savestate(end_state)
    if end_vi <= start_vi:
        raise ValueError(
            f"{end_state.name} is at VI {end_vi}, not after {start_state.name} "
            f"at VI {start_vi}; save the final slot again after the base slot"
        )
    if start_vi & 1 or end_vi & 1:
        # An odd cursor is the normal TAS-edition boundary. Floor division maps
        # both endpoints to the controller frame that follows the saved state.
        pass
    lane_rows = _read_dtm_lane(movie, controller)
    bias = movie_poll_bias(movie)
    start_poll = start_vi * POLLS_PER_VI + bias
    end_poll = end_vi * POLLS_PER_VI + bias
    if start_poll < 0:
        raise ValueError("the DTM does not contain the route's starting controller poll")
    if end_poll > len(lane_rows) + 4:
        raise ValueError(
            f"DTM ends at VI {(len(lane_rows) - bias) // POLLS_PER_VI}, "
            f"before savestate cursor {end_vi}"
        )
    # TAS Edition can save the endpoint one gameplay update after the recorder's
    # final complete controller row.  Accept that exact two-VI tail condition;
    # larger gaps still indicate the wrong or a truncated movie.
    effective_end_vi = min(end_vi, (len(lane_rows) - bias) // POLLS_PER_VI)
    end_poll = effective_end_vi * POLLS_PER_VI + bias
    return RecordedRoute(
        movie=movie,
        start_state=start_state,
        start_vi=start_vi,
        end_vi=effective_end_vi,
        controller=controller,
        # Keep the exact phase of the starting state. Zelda executes one gameplay
        # update every other VI, so these are the rows the land simulator consumes.
        rows=tuple(decode_controller_row(lane_rows[poll + 1])
                   for poll in range(start_poll, end_poll, 4)),
    )


def patch_route_movie(route: RecordedRoute, rows, output: str | Path, *, extend=False,
                      replace_from=None) -> Path:
    """Patch gameplay rows into a copy of a native multi-controller DTM.

    Captured native routes use their measured poll spans and preserve untouched
    fields/polls. ``replace_from`` instead owns all input fields in a new suffix,
    removing original button pulses hidden between its sampled rows. Legacy
    authored routes replace both VIs of each gameplay row.
    """
    rows = tuple(rows)
    if replace_from is not None and not 0 <= replace_from < len(rows):
        raise ValueError("replacement row is outside the authored route")
    if len(rows) != len(route.rows) and not (extend and len(rows) >= len(route.rows)):
        raise ValueError("patched route must contain the same number of gameplay rows")
    data = bytearray(route.movie.read_bytes())
    header = data[:DTM_HEADER_SIZE]
    active = _active_controllers(header)
    if route.controller not in active:
        raise ValueError("route controller is not active in source DTM")
    lane = active.index(route.controller)
    width = len(active)
    source_polls = (len(data) - DTM_HEADER_SIZE) // (width * CONTROLLER_ROW_SIZE)
    bias = movie_poll_bias(route.movie)
    spans = list(route.poll_spans)
    if spans:
        if len(spans) != len(route.rows) or any(a < route.start_vi * POLLS_PER_VI + bias or b <= a
                                              for a, b in spans):
            raise ValueError("invalid captured controller poll spans")
        if any(a[1] != b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError("captured controller poll spans are not contiguous")
        while len(spans) < len(rows):
            start = spans[-1][1]
            spans.append((start, start + 4))
        changes = [i for i, row in enumerate(rows)
                   if i >= len(route.rows) or row != route.rows[i]
                   or (extend and spans[i][1] > source_polls)
                   or (replace_from is not None and i >= replace_from)]
        end_poll = max((spans[i][1] for i in changes), default=0)
    else:
        end_poll = (route.start_vi + len(rows) * 2) * POLLS_PER_VI + bias
    required = DTM_HEADER_SIZE + end_poll * width * CONTROLLER_ROW_SIZE
    if extend and required > len(data):
        body = data[DTM_HEADER_SIZE:]
        if len(body) % CONTROLLER_ROW_SIZE:
            raise ValueError("source DTM ends inside a controller record")
        stride = width * CONTROLLER_ROW_SIZE
        complete = len(body) // stride
        if not complete:
            raise ValueError("source DTM has no complete controller poll")
        last = body[(complete - 1) * stride:complete * stride]
        for other in range(width):
            if other == lane:
                continue
            raw = bytes(last[other * CONTROLLER_ROW_SIZE:(other + 1) * CONTROLLER_ROW_SIZE])
            decoded = decode_controller_row(raw)
            if (decoded["buttons"] or decoded["triggerL"] or decoded["triggerR"]
                    or any(decoded[key] not in (0, 128) for key in
                           ("stickX", "stickY", "substickX", "substickY"))
                    or raw[1] & 0xB0):
                raise ValueError("cannot extend a route while another controller has active input")
        while len(data) < required:
            other = ((len(data) - DTM_HEADER_SIZE) // CONTROLLER_ROW_SIZE) % width
            data.extend(last[other * CONTROLLER_ROW_SIZE:(other + 1) * CONTROLLER_ROW_SIZE])
        old_end = struct.unpack_from("<Q", data, 13)[0]
        new_end = max(old_end, (end_poll - bias + POLLS_PER_VI - 1) // POLLS_PER_VI)
        struct.pack_into("<Q", data, 13, new_end)
        struct.pack_into("<Q", data, 21, (len(data) - DTM_HEADER_SIZE) // CONTROLLER_ROW_SIZE)
        # Boot-origin movies also stop at tickCount. Use a conservative GC
        # PAL-rate deadline; the exact controller-body endpoint still wins.
        ticks = struct.unpack_from("<Q", data, 237)[0]
        struct.pack_into("<Q", data, 237, ticks + (new_end - old_end + 1) * 9_720_000)
    for frame_index, row in enumerate(rows):
        if spans:
            baseline = route.rows[frame_index] if frame_index < len(route.rows) else None
            if replace_from is not None and frame_index >= replace_from:
                baseline = None
            if baseline is not None and row == baseline and (not extend or spans[frame_index][1] <= source_polls):
                continue
            for poll in range(*spans[frame_index]):
                offset = DTM_HEADER_SIZE + (poll * width + lane) * CONTROLLER_ROW_SIZE
                if offset + CONTROLLER_ROW_SIZE > len(data):
                    raise ValueError("source DTM ends inside the patched route")
                raw = bytearray(data[offset:offset + CONTROLLER_ROW_SIZE])
                encoded = encode_controller_row(row)
                # Preserve intra-update transitions in fields that were not edited.
                authored = baseline if poll < source_polls else None
                for keys, indices in ((("buttons",), (0, 1)), (("triggerL",), (2,)),
                                      (("triggerR",), (3,)), (("stickX", "stickY"), (4, 5)),
                                      (("substickX", "substickY"), (6, 7))):
                    if authored is None or any(row.get(k, 0) != authored.get(k, 0) for k in keys):
                        for byte_index in indices:
                            raw[byte_index] = ((raw[1] & 0xF0) | (encoded[1] & 0x0F)
                                               if byte_index == 1 else encoded[byte_index])
                data[offset:offset + CONTROLLER_ROW_SIZE] = raw
            continue
        encoded = encode_controller_row(row)
        first_vi = route.start_vi + frame_index * 2
        for vi in (first_vi, first_vi + 1):
            for poll in range(POLLS_PER_VI):
                raw_index = (vi * POLLS_PER_VI + bias + poll) * width + lane
                offset = DTM_HEADER_SIZE + raw_index * CONTROLLER_ROW_SIZE
                if offset + CONTROLLER_ROW_SIZE > len(data):
                    raise ValueError("source DTM ends inside the patched route")
                data[offset:offset + CONTROLLER_ROW_SIZE] = encoded
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return output


def build_route_movie(route: RecordedRoute, rows, output: str | Path,
                      polls_per_frame: int = 4) -> Path:
    """Build a frame-zero movie containing only a recorded gameplay route.

    Loading a deep recording's savestate into a newly started movie resets the
    movie cursor to zero.  Copying and patching the original full DTM therefore
    replays its ancient body prefix.  This exporter keeps the native header and
    controller-port layout, but makes the captured route the entire movie body.
    """
    if route.poll_spans:
        raise ValueError("poll-timed routes require full-movie export to preserve controller timing")
    rows = tuple(rows)
    polls_per_frame = int(polls_per_frame)
    if polls_per_frame <= 0:
        raise ValueError("polls_per_frame must be positive")
    source = route.movie.read_bytes()
    header = bytearray(source[:DTM_HEADER_SIZE])
    if len(header) != DTM_HEADER_SIZE or header[:4] != b"DTM\x1a":
        raise ValueError(f"invalid source DTM: {route.movie}")
    active = _active_controllers(header)
    if route.controller not in active:
        raise ValueError("route controller is not active in source DTM")

    target_lane = active.index(route.controller)
    empty_lane = bytes(CONTROLLER_ROW_SIZE)
    body = bytearray()
    for row in rows:
        encoded = encode_controller_row(row)
        for _ in range(polls_per_frame):
            for lane in range(len(active)):
                body.extend(encoded if lane == target_lane else empty_lane)

    # Wind Waker runs one gameplay update per two VIs. Input count is the
    # number of eight-byte controller records across all active ports.
    struct.pack_into("<Q", header, 13, len(rows) * 2)
    struct.pack_into("<Q", header, 21, len(rows) * polls_per_frame * len(active))
    struct.pack_into("<Q", header, 29, 0)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + body)
    return output


def install_route_movie(route: RecordedRoute, rows, output: str | Path,
                        *, short: bool = True, extend=False, replace_from=None) -> Path:
    """Export a route DTM and install the matching savestate companions.

    ``short=True`` is useful when the savestate is loaded into a fresh movie.
    A recorded route normally starts at a deep movie cursor, though, so callers
    that expect to paste or play the inputs in the original movie must use the
    full patched source with ``short=False``.
    """
    output = (
        build_route_movie(route, rows, output)
        if short else patch_route_movie(route, rows, output, extend=extend, replace_from=replace_from)
    )
    state = Path(str(output) + ".sav")
    shutil.copy2(route.start_state, state)
    shutil.copy2(output, Path(str(state) + ".dtm"))
    return output


def nearest_route_start(movie: str | Path, end_state: str | Path,
                        candidates, min_frames: int = 2,
                        max_frames: int = 90) -> Path:
    """Pick the closest earlier movie-attached state in the requested frame window."""
    del movie  # Kept in the signature to make call sites explicit about provenance.
    end_vi = movie_vi_from_savestate(end_state)
    eligible = []
    for candidate in candidates:
        path = Path(candidate)
        try:
            vi = movie_vi_from_savestate(path)
        except (OSError, ValueError):
            continue
        frames = (end_vi - vi) // 2
        if vi < end_vi and min_frames <= frames <= max_frames:
            eligible.append((vi, path))
    if not eligible:
        raise RuntimeError("no earlier savestate brackets the recorded route")
    return max(eligible, key=lambda item: item[0])[1]
