#!/usr/bin/env python3
"""Regenerate the OFFLINE land golden(s) from LIVE (the source of truth). NEEDS Dolphin running with
twwgz booted -- this captures the game's own pos_z / speedF, which tests/test_land.py then pins so the
offline unit tests fail exactly where the live gate (tests/dolphin/run_land_tests.py) fails.

The golden is the GAME's values, not the sim's: every pos_z/speedF is the live f32 read, stored as its
exact uint32 bytes. test_land.py asserts `f32_bits(sim) == golden`, so a tech that is not bit-perfect
vs the game shows RED offline too (no tolerance). When the sim is fixed to reproduce a value, that
test goes green; there is nothing to "re-lock" because the reference is the game, not the sim.

Run (with Dolphin up + twwgz in-game):
    python tests/gen_land_golden.py            > tests/golden/land_walk_speedf.csv
    python tests/gen_land_golden.py endpoints          # prints CASE_POSZ (live endpoint bytes)

The walk per-frame arc is captured by replaying prefixes of the walk seq live (load anchor ->
advanceseq the first n frames -> read). WARM UP first: the very first advanceseq after a cold boot
returns garbage, so a throwaway run precedes the capture.
"""
import os
import struct
import sys

# >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)

import dolphin_mem as D
from harness.dtm.run_dtm import resolve_anchor
from tww_sim.land.land import LandState, FREE_WAIT

ANCHOR = resolve_anchor("land_flatwalk@twwgz")
IDLE_FRAME = 70.0

# --- sequences, as advanceseq elements (free cam: C-stick full down). Mirror tests/test_land.py. ----
def _els(rows):
    return [{"stickX": sx, "stickY": sy, "substickX": 128, "substickY": 0,
             "buttons": b, "triggerL": tl, "frames": 1} for (sx, sy, b, tl) in rows]

_UP = (128, 255, 0, 0)
_NE = (128, 128, 0, 0)
_LDN = (128, 0, 0x40, 255)          # L-target + full down
_A = (128, 255, 0x100, 0)           # A + up
_DN = (128, 0, 0, 0)                # full-down, no L
_Y171 = (128, 171, 0, 0)            # partial-magnitude up (msd~0.52) -- the z=2000-stop cruise regime

WALK = _els([_UP] * 30 + [_NE] * 20)
# Partial-magnitude walk from rest (Y171, msd~0.52) -- the z=2000-stop regime (regime-1 cruise, not
# covered by the msd-0/1 WALK golden). See knowledge/model/sim.md "Partial-magnitude regime".
WALK_Y171 = _els([_Y171] * 40)

CASE_SEQS = {
    "brakeslide":  _els([_UP] * 10 + [_LDN] + [(128, 110, 0x40, 255)] * 10),
    "ebs":         _els([_UP] * 10 + [_LDN] + [(128, 110, 0, 0)] * 30),
    "face_left":   _els([_UP] * 10 + [_LDN] + [(128, 110, 0, 0)] + [(110, 128, 0, 0)] * 60),
    "brake_right": _els([_UP] * 10 + [_LDN] + [(128, 110, 0, 0)] + [(146, 128, 0, 0)] * 60),
    "roll_run":    _els([_UP] * 15 + [_A] + [_NE] * 5),
    "roll_slow":   _els([_UP] * 2 + [_A] + [_NE] * 5),
    "roll_settle": _els([_UP] * 15 + [_A] + [_NE] * 40),
    "roll_ebs":    _els([_UP] * 15 + [_A] + [(128, 0, 0x40, 255)] * 17 + [(128, 110, 0, 0)] * 14),
    "waitturn":    _els([_DN] * 15),
    "moveturn":    _els([_UP] + [_DN] * 18),
    "moveturn_pos": _els([_UP] + [_DN] * 20),   # test_moveturn_position_bit_exact's longer seq
    "slip":        _els([_UP] * 15 + [_DN] * 30),
}


def f32_bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _load(seq):
    D.control_pipe_quiet("clearinput")
    D.control_pipe_quiet("savestate", {"action": "load", "path": ANCHOR.replace('\\', '/')})
    if seq:
        D.control_pipe_quiet("advanceseq", {"port": 0, "seq": seq})
    h, m = D.attach()
    return {k: D.read_named(h, m, k) for k in
            ("link_state", "potential_speed", "true_speed", "pos_z", "anim_frame")}


def _warm():
    _load(WALK[:3])                       # discard the cold-boot first advanceseq


def _emit_walk(seq, seqdesc):
    """Per-frame walk golden for `seq`: msd from the sim (deterministic), ns/speedF/pos_z from LIVE
    (prefix-replay: reload + advanceseq(seq[:n]) each frame -- the trustworthy method, no per-frame
    stepping desync). Emits the CSV test_land.py pins."""
    _warm()
    seed = _load([])
    sim = LandState(pos_z=seed["pos_z"], state=FREE_WAIT, idle_frame=IDLE_FRAME)
    msd = []
    for el in seq:
        sim.step(el["stickX"], el["stickY"])
        msd.append(sim.msd)
    print("# land_flatwalk@twwgz walk golden (FULL float32 precision, LIVE capture = source of truth).")
    print(f"# seed_pos_z={seed['pos_z']!r} (0x{f32_bits(seed['pos_z']):08x}) idle_frame={IDLE_FRAME:.3f}"
          f"  seq={seqdesc} (free cam)")
    print("# speedF/pos_z are the GAME's live f32 bytes. test_land.py asserts f32_bits(sim)==these, so a")
    print("# not-yet-bit-perfect walk shows RED offline too. Regenerate (Dolphin up): python tests/gen_land_golden.py")
    # ns/msd use repr() (full f32), NOT %g: a truncated nspeed shifts the WAITS<->WALK blend ratio
    # and desyncs the foot pose by tens of ULP (see knowledge/model/sim.md "Partial-magnitude regime").
    print("f,ns,msd,speedF,speedF_hex,pos_z,pos_z_hex")
    for n in range(1, len(seq) + 1):
        lv = _load(seq[:n])
        print(f"{n},{lv['potential_speed']!r},{msd[n-1]!r},{lv['true_speed']!r},"
              f"0x{f32_bits(lv['true_speed']):08x},{lv['pos_z']!r},0x{f32_bits(lv['pos_z']):08x}")


def emit_walk_csv():
    _emit_walk(WALK, "30 up + 20 neutral")


def emit_walk_y171_csv():
    _emit_walk(WALK_Y171, "40 x Y171 (partial magnitude, msd~0.52)")


def emit_endpoints():
    _warm()
    print("# Paste into tests/test_land.py::CASE_POSZ (label -> LIVE endpoint pos_z bytes).")
    print("CASE_POSZ = {")
    for label, seq in CASE_SEQS.items():
        lv = _load(seq)
        print(f"    {label!r:14s}: 0x{f32_bits(lv['pos_z']):08x},   # {lv['pos_z']!r} (state {int(lv['link_state'])})")
    print("}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "endpoints":
        emit_endpoints()
    elif arg == "y171":
        emit_walk_y171_csv()
    else:
        emit_walk_csv()
