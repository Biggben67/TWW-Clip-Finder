"""Small, dependency-free DTM author for savestate-backed JP Wind Waker movies.

The land planners operate at one 30 fps game step per input dictionary. Wind Waker polls
the GameCube controller four times during that step, so every authored input is repeated
four times in the DTM body. This is the clean movie path used by the slash verifier; it
does not use ControlPipe input injection.
"""
from __future__ import annotations

import os
import shutil
import struct


HEADER_SIZE = 256
CONTROLLER_STATE_SIZE = 8
DEFAULT_POLLS = 4

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TEMPLATE = os.path.join(
    _ROOT, "tests", "dolphin", "anchors", "wiggle_ebs_roll@twwgz.dtm.sav.dtm"
)


def _u8(value, default=0):
    return max(0, min(255, int(default if value is None else value)))


def _controller_row(stick: dict) -> bytes:
    buttons = int(stick.get("buttons", 0))
    # GCPadStatus constants used by the simulator/control pipe -> DTM bitfields.
    first = 0
    first |= 0x01 if buttons & 0x1000 else 0  # Start
    first |= 0x02 if buttons & 0x0100 else 0  # A
    first |= 0x04 if buttons & 0x0200 else 0  # B
    first |= 0x08 if buttons & 0x0400 else 0  # X
    first |= 0x10 if buttons & 0x0800 else 0  # Y
    first |= 0x20 if buttons & 0x0010 else 0  # Z
    first |= 0x40 if buttons & 0x0008 else 0  # D-pad up
    first |= 0x80 if buttons & 0x0004 else 0  # D-pad down

    second = 0x40  # is_connected
    second |= 0x01 if buttons & 0x0001 else 0  # D-pad left
    second |= 0x02 if buttons & 0x0002 else 0  # D-pad right
    second |= 0x04 if buttons & 0x0040 else 0  # L
    second |= 0x08 if buttons & 0x0020 else 0  # R

    return bytes((
        first,
        second,
        _u8(stick.get("triggerL")),
        _u8(stick.get("triggerR")),
        _u8(stick.get("stickX"), 128),
        _u8(stick.get("stickY"), 128),
        _u8(stick.get("substickX", stick.get("cstickX", 128)), 128),
        _u8(stick.get("substickY", stick.get("cstickY", 128)), 128),
    ))


def build_dtm_from_sticks(sticks, out: str, template: str | None = None,
                          polls: int = DEFAULT_POLLS, seed: int = 0,
                          game_id: bytes | str = b"GZLJ01") -> dict:
    """Write a from-savestate DTM and return its frame/row metadata.

    ``seed`` is a count of leading neutral controller *polls*, matching the historical
    unbundled dtm_make tool. New slash plans use seed=0 and are simulated for that layout.
    """
    sticks = list(sticks)
    polls = int(polls)
    seed = int(seed)
    if polls <= 0:
        raise ValueError("polls must be positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if isinstance(game_id, str):
        try:
            game_id = game_id.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("game ID must contain exactly 6 ASCII characters") from exc
    if len(game_id) != 6 or any(byte < 0x20 or byte > 0x7E for byte in game_id):
        raise ValueError("game ID must contain exactly 6 printable ASCII characters")

    template = template or DEFAULT_TEMPLATE
    if not os.path.isfile(template):
        raise FileNotFoundError(f"DTM header template not found: {template}")
    with open(template, "rb") as source:
        header = bytearray(source.read(HEADER_SIZE))
    if len(header) != HEADER_SIZE or header[:4] != b"DTM\x1a":
        raise ValueError(f"invalid DTM header template: {template}")

    header[4:10] = game_id
    header[10] = 0
    header[11] = 1
    header[12] = 1

    neutral = _controller_row({})
    rows = [neutral] * seed
    for stick in sticks:
        rows.extend([_controller_row(stick)] * polls)

    # These counters are informational for from-savestate playback; the byte stream is
    # authoritative. Keep them consistent with the fork's 60 VI/s and input accounting.
    frame_count = max(1, len(sticks) * 2 + (1 if seed else 0))
    input_count = max(1, len(rows) * 2)
    struct.pack_into("<Q", header, 13, frame_count)
    struct.pack_into("<Q", header, 21, input_count)
    struct.pack_into("<Q", header, 29, 0)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    body = b"".join(rows)
    with open(out, "wb") as output:
        output.write(header)
        output.write(body)
    return {
        "frames": len(sticks),
        "rows": len(rows),
        "bytes": HEADER_SIZE + len(body),
        "polls": polls,
        "seed": seed,
    }


def install_savestate_companions(movie: str, savestate: str) -> str:
    """Install the state and companion DTM required by deep-session playback."""
    movie = os.path.abspath(movie)
    movie_state = movie + ".sav"
    shutil.copy2(savestate, movie_state)
    shutil.copy2(movie, movie_state + ".dtm")
    return movie_state

