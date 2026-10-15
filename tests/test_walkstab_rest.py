"""From-rest regression for the WALK-stab anchor (kaze r11, item-in-hand/sword-sheathed idle;
session 29-31, 2026-07-13). Live golden: a short straight walk played by a clean DTM with C-down held
(the free-cam pin), per-frame pos/facing/m359C -- tests/golden/walkstab_rest.json.

WHAT THIS LOCKS (the from-rest walk is 0-ULP -- pure sim, no calibration):
  * With the C-down camera pin (substickY=0), the from-rest sim (rest.rest_state) is BIT-EXACT in
    FACING every frame -- the auto-cam would otherwise swing csangle and drift facing (session 28).
  * POSITION is BIT-EXACT every frame too (0 ULP): the session-30 "walk-entry foot toe-stream
    residual" was NOT a foot-FK/lean gap -- it was the wrong anim SET. This anchor holds the Wind
    Waker (mEquipItem 0x22, NOT daPyItem_SWORD_e 0x103), so getAnmData selects the base WALK/DASH
    legs, not the sword-drawn WALKS/DASHS. WALK and WALKS share leg keyframes (a WAITS<->WALK entry
    is identical either way), but DASH and DASHS differ, so the buggy sword-drawn assumption drifted
    the toe ~0.0024u the instant DASH blended in (regime 2). rest.rest_state now seeds sword_drawn
    from the anchor's captured equip state (session 31). See dead-end #28 (corrected).

Live golden -- NEVER edit the fixture to make the sim pass (tests/dolphin/README.md).
"""
import json
import math
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(_HERE, 'golden')

try:
    from harness.rollstab import rest as C
    from harness.rollstab import walkstab as W
    _HAVE = C.rest_state is not None
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / anim data unavailable")

ANCHOR = 'kaze_r11_walkstab@twwgz'
RAZOR = 6e-4        # the seam's perp offset window (gap_search.characterize)


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _gold():
    return json.load(open(os.path.join(_GOLD, 'walkstab_rest.json')))


def _replay():
    """Seed rest_state, replay the golden's straight walk with C-down; yield (k, sim, live)."""
    g = _gold()
    assert g['anchor'] == ANCHOR
    stream = [tuple(g['walk_stick'])] * g['nwalk']
    s = C.rest_state(ANCHOR)
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy, csx=128, csy=W.CDOWN)
        if k >= len(g['frames']):
            break
        yield k, s, g['frames'][k]


def test_walkstab_facing_bitexact_under_cdown():
    """FEASIBILITY: facing is 0-ULP every frame under the C-down camera pin."""
    bad = [k for k, s, lf in _replay() if (int(s.facing) & 0xFFFF) != (lf['facing'] & 0xFFFF)]
    assert not bad, "facing diverged at frames %s (C-down should pin the camera)" % bad


def test_walkstab_perp_residual_inside_razor():
    """The from-rest position residual's PERPENDICULAR component (the razor quantity) stays well
    inside the seam's ~6e-4u offset window, every frame. (Now 0 -- the full position is bit-exact;
    kept as an independent guard on the razor quantity.)"""
    worst = 0.0
    for k, s, lf in _replay():
        a = (lf['facing'] & 0xFFFF) / 65536.0 * 2 * math.pi
        dsin, dcos = math.sin(a), math.cos(a)
        ex, ez = s.pos_x - lf['pos_x'], s.pos_z - lf['pos_z']
        d_perp = ex * (-dcos) + ez * dsin
        worst = max(worst, abs(d_perp))
    assert worst < RAZOR / 3.0, "perp residual %.2e u >= razor/3 (%.2e)" % (worst, RAZOR / 3.0)


def test_walkstab_full_position_bitexact():
    """The FULL position is BIT-EXACT (0 ULP) from rest every frame -- pure sim, no calibration.
    (Was the session-30 "walk-entry foot toe-stream residual"; root-caused session 31 to the wrong
    anim set -- sword-drawn WALKS/DASHS vs the item-holding base WALK/DASH. See the module docstring
    + dead-end #28.)"""
    bad = [k for k, s, lf in _replay()
           if not (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z']))]
    assert not bad, "position diverged at frames %s" % bad
