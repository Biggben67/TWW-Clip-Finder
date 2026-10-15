"""stick_angle.py - EXACT mMainStickAngle(sx,sy) (s16) for the superswim predictor.

The game's main-stick -> angle is atan2f of the GC-clamped stick vector (JUTGamePad::CStick::update:
mAngle = 10430.379f * atan2f(mPosX, -mPosY)), but the vector itself is Dolphin's byte->analog mapping
+ deadzone/octagon clamp, which diverges from both the naive atan2 (swim.sim.stick_angle_deg,
good only to ~0.86deg) AND the pure SDK PADClamp (a decomp port disagrees at ~17.6% of cells; that is
Dolphin's input layer, not the game math). So the sim MUST match Dolphin, and the angle is captured
live for all 65536 cells in stick_angle_table.csv (harness/capture/stick_grid_redump.py: settle+verify
gold dump, 2026-07 — replaced a corrupt 1-frame-pipeline dump; see knowledge/history).

angle_s16(sx,sy) returns the exact s16 angle from the cache, or None for a neutral stick.
If a stick is NOT cached it raises KeyError -- run stick_angle_capture.py on the capture first
(so a missing cell is loud, never silently approximated). This is the `stickAngle` term in
    m34E8 = stickAngle + 0x8000 + camAngle.
"""
from __future__ import annotations
import os, csv
from .. import sim as S

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core", "tables")
# Complete live grid (65536 cells) of MAIN_STICK_ANGLE (0x80398314), gold-dumped via
# harness/capture/stick_grid_redump.py; integrity locked by tests/test_stick_table_integrity.py.
_TABLE_PATH = os.path.join(_HERE, "stick_angle_table.csv")
# Only the `angle` column is used here. The `stick_dist`/`value` magnitude columns both equal
# mMainStickValue (== the closed-form /54 gain magnitude the sim uses); the sim reads neither column.

_TABLE: dict[tuple[int, int], int] = {}
if os.path.exists(_TABLE_PATH):
    for _r in csv.DictReader(open(_TABLE_PATH)):
        _TABLE[(int(_r["sx"]), int(_r["sy"]))] = int(_r["angle"]) & 0xFFFF

_COMPLETE = len(_TABLE) >= 256 * 256


def is_neutral(sx: int, sy: int) -> bool:
    """A stick reads as neutral (no swim input) exactly when mStickDistance <= 0.05 -- the
    game's swim-input gate (see sim.stick_angle_deg; bit-identical to the gold table's
    `value <= 0.05` on all 65536 cells)."""
    return S.stick_angle_deg(sx, sy) is None


def angle_s16(sx: int, sy: int) -> int | None:
    """Exact s16 stick angle, or None for neutral. Resolution order:
      1. neutral gate (closed-form dead-zone) -> None (no swim input this frame);
      2. the COMPLETE live grid (stick_angle_table.csv): exact for every (sx,sy);
      3. for an ON-AXIS stick (sx == 128) the closed form is exact (covers anything the grid
         might somehow lack);
      4. otherwise KeyError -- never silently approximated."""
    sx, sy = int(sx), int(sy)
    if is_neutral(sx, sy):
        return None
    if (sx, sy) in _TABLE:
        return _TABLE[(sx, sy)]
    if sx == 128:                                   # on-axis: closed form is exact
        return S.deg_to_s16(S.stick_angle_deg(sx, sy))
    raise KeyError(f"stick ({sx},{sy}) missing (table complete={_COMPLETE}); "
                   f"re-run harness/capture/stick_grid_redump.py to rebuild the full grid")


def has(sx: int, sy: int) -> bool:
    return (int(sx), int(sy)) in _TABLE
