"""The NOVEL 157-deg corner S=(9689.1406, -150.3137), interior 157.14, walls 456 x 459 -- the third
novel seam delivered end-to-end by the GENERALIZED roll path (session 58), and the first picked by
the room-wide DENSITY SCREEN (all 159 enumerated seams dust-scanned; this corner's genuine dust
counts 1480 samples / 50% along rows / 0.33u perp band -- the delivered 152's class, vs the
undelivered 97m's 84/13%): `solve_focused` found 2 wall-faithful clips in one default 112s draw.

Anchor `kaze_r11_rollstab_seam157@twwgz`: pan-minted ON the F-through-S line by `mint.mint_online`
(baseline |old perp| 0.092u, rest d2S 580u, facing == F == 52792). The mint needed two session-58
harness fixes, both general: the walk-settle runs UNTIL csangle freezes (a fixed frame count
under-settles at some seams and the cam creeps through the approach), and the re-park loop steps by
a SECANT gain (the perp response per unit park shift is ~1.8 at a large settle misaim, so the 1:1
step oscillates). csangle 57546 held frozen live through the whole approach.

Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam157_rest_golden.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / seam157 golden unavailable")

ANCHOR = 'kaze_r11_rollstab_seam157@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam157_rest_bitexact():
    """The pan-minted anchor is REST BIT-EXACT (0 ULP) from rest through the walk approach. The
    anchor faces F exactly (mint_online parks at the aim), so straight == aim and the cruise is one
    bearing. Delivered C-down every frame + seed=0. Index-aligned vs the live golden."""
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
    assert not bad, "seam157 from-rest diverged at rows %s" % bad


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam157_roll_ship_golden.json')


@pytest.mark.skipif(not os.path.exists(_SHIP), reason="seam157 ship golden unavailable")
def test_seam157_clip_delivered():
    """Session 58: the 157-deg-corner roll-stab clip, found by the generalized `solver.solve_focused`
    (2 wall-faithful hits in one default 112s draw, top margin 60) and delivered LIVE 0-ULP via a
    clean DTM at seed=0: old=(9734.5458984, -166.6959534) -> new=(9688.2480469, -149.9900513),
    CUT_F then OOB (proc 0x24).

    The from-rest sim (rest_state on the shipped hit's exact stream) reproduces the live CUT_F entry
    old/new BIT-FOR-BIT (0 ULP). Live-captured golden, never edited to make the sim pass."""
    from harness.rollstab.deliver import replay
    from tww_sim.land.land import CUT_F, CUT_A
    g = json.load(open(_SHIP))
    assert g['anchor'] == ANCHOR and g.get('dtm_seed') == 0
    assert g['threads'] and g['behindA'] and g['behindB'], "golden did not confirm a live clip"

    stream = [tuple(fr) for fr in g['stream']]
    rows = replay(ANCHOR, stream, dtm_seed=0)
    ci = next((i for i, rr in enumerate(rows) if rr[0] in (CUT_F, CUT_A)), None)
    assert ci and ci > 0, "sim CUT never fired"
    sim_old, sim_new = (rows[ci - 1][1], rows[ci - 1][2]), (rows[ci][1], rows[ci][2])
    for name, s, l in (('old', sim_old, g['live_old']), ('new', sim_new, g['live_new'])):
        assert _bits(s[0]) == _bits(l[0]) and _bits(s[1]) == _bits(l[1]), \
            "%s not 0-ULP: sim=%s live=%s" % (name, s, l)

    lc = g['live_cut_frame']
    assert g['live'][lc]['proc'] == (CUT_F & 0xFF), "live cut proc not CUT_F"
    assert any(f['proc'] == 0x24 for f in g['live'][lc:]), "no OOB fall after the cut"
