"""The NOVEL 824 corner S=(9689.1406, 123.4604) (interior 157.33, walls 824 x 826) -- the fifth
novel seam delivered end-to-end by the GENERALIZED roll path (session 60), queued by the
session-58 room-wide density screen (n=725, band_dense 0.024u, corridor 1400u).

Two session-60 lessons live in this delivery:
  * The approach corridor has a FIXED camera-trigger band at d2S ~588..384 (csangle dips ~-300 s16
    and recovers, road-triggered -- verified by a shifted-start probe): the default pan target's cam
    track clips it and REST can never be bit-exact. The fix is the CAM-TARGET SCREEN: probe alternate
    `target_csangle` pan targets at the park and pick one whose csangle stays FROZEN through the
    whole corridor walk (here 37512 -> frozen 41530). The value is measured per seam, not tuned.
  * The anchor rests at d2S 580.0 exactly (mint_online 2 iters, baseline |old perp| 0.114).

Anchor `kaze_r11_rollstab_seam824@twwgz`: pan-minted ON the F-through-S line by `mint.mint_online`
(target_csangle=37512 from the cam screen; csangle 41530 frozen; facing 45634 vs F 45566 -- the arc
absorbs the misaim). Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT
hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam824_rest_golden.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / seam824 golden unavailable")

ANCHOR = 'kaze_r11_rollstab_seam824@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam824_rest_bitexact():
    """The pan-minted anchor is REST BIT-EXACT (0 ULP) from rest through the walk approach,
    delivered C-down every frame + seed=0. Index-aligned vs the live golden."""
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
    assert not bad, "seam824 from-rest diverged at rows %s" % bad


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam824_roll_ship_golden.json')


@pytest.mark.skipif(not os.path.exists(_SHIP), reason="seam824 ship golden unavailable")
def test_seam824_clip_delivered():
    """Session 60: the 824-corner roll-stab clip, found by the generalized `solver.solve_focused`
    (2 wall-faithful hits in one DEFAULT 112s draw, top margin 27) and delivered LIVE 0-ULP via a
    clean DTM at seed=0: old=(9731.271484375, 138.69970703125) ->
    new=(9684.986328125, 121.95780944824219), CUT_F then OOB (proc 0x24).

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
