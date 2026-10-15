"""The z-MIRROR 97-deg corner S=(13539.2393, -493.3560), interior 97.01, walls 449 x 450 -- the
session-53 candidate, PAN-MINTED session 55. Two results:

  * The session-54 camera recipe GENERALIZES: this corner sits in the mid-room AUTO-cam regime that
    blocked its unpanned mints (dead-end #36); the `mint.mint_online` pan mint (C-stick pan + on-line
    re-park driving the BASELINE ROLL OLD's perp to ~0, not just the rest's -- the ~23-deg settle
    misaim's MOVE turn adds ~12u perp during the approach) produced a REST BIT-EXACT anchor
    (csangle 5131 frozen, 28/28 rows 0-ULP, seed=0, C-down). That closes the s53/s54 open question.
  * The CLIP is NOT yet delivered: this corner's genuine dust is ~4x THINNER than the delivered
    mirror seam's (84 fine-scan samples vs 360; slivers <=0.0006u in a 0.02u perp band vs the
    152-corner's 1409/0.41u), and `solve_focused`'s chaotic crawl lattice at the 2-minute budget
    gives < 1 expected hit per draw -- 8 independent knob-family draws found 0. Roll-REACHABLE
    (mouth-open dust 35-37u off both walls, `SeamGeo.roll_reachable` accepts), so this is a search
    THROUGHPUT gap, not geometry. See the session-55 handoff for the surfaced options.

Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam97m_rest_golden.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / seam97m golden unavailable")

ANCHOR = 'kaze_r11_rollstab_seam97m@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam97m_rest_bitexact():
    """The pan-minted on-line anchor is REST BIT-EXACT (0 ULP) from rest through the walk approach --
    straight prefix at the anchor facing (4630), then the aim cruise at F=8769 (a ~23-deg MOVE turn,
    modeled). Delivered C-down every frame + seed=0. csangle 5131 held frozen live through the whole
    walk (the mint's C-stick pan armed the manual cam in an AUTO-cam region -- the s54 recipe's
    generalization proof). Index-aligned vs the live golden."""
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    stream = ([tuple(golden['straight'])] * golden['NPREF']
              + [tuple(golden['aim'])] * golden['NCRUISE'])
    s = C.rest_state(ANCHOR, dtm_seed=0)
    frames = golden['frames']
    matched, bad = 0, []
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy)
        if k >= len(frames):
            break
        lf = frames[k]
        st = s._foot.st
        matched += 1
        if not (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])
                and _bits(st.fc0.frame) == _bits(lf['d_frame'])
                and _bits(st.fc1.frame) == _bits(lf['w_frame'])
                and _bits(s._foot.prev_f312) == _bits(lf['m359C'])):
            bad.append(k)
    assert matched >= 24, "too few rows matched (%d)" % matched
    assert not bad, "seam97m from-rest diverged at rows %s" % bad


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam97m_roll_ship_golden.json')


@pytest.mark.xfail(reason="97m clip not yet delivered -- the seam is roll-reachable and the anchor is "
                          "REST bit-exact, but its dust density (~4x thinner than the mirror's) puts "
                          "solve_focused's per-2-min-draw hit expectation below 1 (session 55)",
                   strict=True)
def test_seam97m_clip_delivered():
    """RED until the 97m-corner clip is delivered LIVE 0-ULP. Flip GREEN by producing
    `fixtures/seam97m_roll_ship_golden.json` from a clean-DTM ship (mirror `test_seam152_clip.py::
    test_seam152_clip_delivered` for the assertion shape)."""
    assert os.path.exists(_SHIP), "no seam97m ship golden yet -- the clip is not delivered"
