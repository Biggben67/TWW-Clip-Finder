"""seam_0352_0353 (kaze r11, S=(9344.82,-373.61), interior 155.4) -- the WALK-stab novel-anchor
tier, session 72. This locks what IS done and flags what is NOT:

  * GREEN -- the from-rest WALK is BIT-EXACT (0-ULP) for a FRESHLY-MINTED novel walk-stab anchor,
    28/28 rows including the seam wall-SLIDE (the verification walk reaches the corner wall at
    d2S ~34 and slides; the gate sim runs WITH the seam walls, so it matches live -- the
    walls-aware REST gate, session 72). This proves the novel-anchor mint (mint.mint_walkstab, the
    sub-580u pan mint + the check_runway guard) + the from-rest model generalize to a novel corner:
    the earlier "camera-dirty corridor" alarm was a false positive (a pan/settle transient, NOT a
    wall collision -- the arm converges cleanly to nominal and csangle holds).

  * GREEN (session 75) -- the live 0-ULP CLIP IS DELIVERED (the 11th seam), unblocked by the
    DISPATCH-FRAME CUT fix: a buffered-B walk-stab cut fires AFTER procMove's setSpeedAndAngleNormal
    travel chase that frame, and the entry foot term lunges along the CHASED travel, not facing
    (captured live via posMove-boundary breakpoints on a movie-faithful playback; the rawcut gate
    below locks it 0-ULP). The old travel==facing model was ~0.026u off -- a phantom clip cell on
    this ~1-ULP-acceptance razor corner, which is why every earlier solve/delivery missed: the model
    searched dust the real cut could not reach. Golden: tests/golden/walkstab_seam352_deliver.json.

Live-captured golden -- NEVER edit the fixture to make the sim pass (tests/dolphin/README.md).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIX = os.path.join(os.path.dirname(_HERE), 'fixtures')
_GOLD = os.path.join(_FIX, 'seam352_rest_golden.json')
_GEO = os.path.join(_FIX, 'kaze_r11_seam352_geo.json')

try:
    from harness.rollstab import rest as C
    from harness.rollstab.seamgeo import SeamGeo
    from harness.rollstab.geometry import load_seed
    _HAVE = C.rest_state is not None and os.path.exists(_GEO)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness unavailable")

ANCHOR = 'kaze_r11_walkstab_seam352@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _seam():
    return SeamGeo(json.load(open(_GEO)), load_seed(ANCHOR)['csangle'] & 0xFFFF)


def test_seam352_rest_bitexact():
    """From-rest walk-stab walk 0-ULP vs live, WITH the seam walls (the walk slides the corner
    wall) -- the novel-anchor mint + from-rest model generalize (session 72)."""
    assert os.path.exists(_GOLD), "seam352 REST golden not shipped"
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    sg = _seam()
    stream = ([tuple(golden['straight'])] * golden['NPREF']
              + [tuple(golden['aim'])] * golden['NCRUISE'])
    s = C.rest_state(ANCHOR, dtm_seed=0, walls=sg.TRIS)
    frames = golden['frames']
    matched, bad = 0, []
    for k, (sx, sy) in enumerate(stream):
        s.step(sx, sy)
        if k >= len(frames):
            break
        lf = frames[k]
        st = s._foot.st
        matched += 1
        ok = (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])
              and _bits(st.fc0.frame) == _bits(lf['d_frame'])
              and _bits(st.fc1.frame) == _bits(lf['w_frame'])
              and _bits(s._foot.prev_f312) == _bits(lf['m359C']))
        if not ok:
            bad.append(k)
    assert matched >= 24, "too few rows matched (%d)" % matched
    assert not bad, "seam352 walls-aware from-rest diverged at rows %s" % bad


_RAWCUT = os.path.join(_FIX, 'seam352_rawcut_golden.json')


def test_seam352_rawcut_dispatch_frame_bitexact():
    """The walk->cut DISPATCH-frame model is 0-ULP vs the LIVE RAW (pre-collision) CUT_F endpoint
    (session 75, captured via movie-faithful playback + JP posMove-boundary breakpoints, fixture
    `seam352_rawcut_golden.json`). Locks the session-75 fix: procMove's setSpeedAndAngleNormal
    travel chase runs BEFORE the buffered-B cut dispatches, and the entry foot term fires along
    that CHASED travel (64961 here), not facing (64946) -- `_cut_init` must NOT snap travel, and
    `enter_cut_from_move` must run the dispatch prefix. The old travel==facing model was 0.026u
    off: a phantom clip cell on this ~1-ULP razor seam."""
    assert os.path.exists(_RAWCUT), "seam352 rawcut golden not shipped"
    g = json.load(open(_RAWCUT))
    assert g['anchor'] == ANCHOR and g['dtm_seed'] == 0
    sticks = [tuple(sk) for sk in g['sticks']]
    N = g['N']
    s = C.rest_state(ANCHOR, dtm_seed=g['dtm_seed'])
    for k in range(N):
        s.step(sticks[k][0], sticks[k][1], csx=128, csy=0)
    # the walk delivers `old` 0-ULP (already locked by the REST gate; re-assert at the cut frame)
    assert _bits(s.pos_x) == int(g['live_old_bits'][0], 16)
    assert _bits(s.pos_z) == int(g['live_old_bits'][1], 16)
    dstk = sticks[N] if N < len(sticks) else sticks[-1]
    s.enter_cut_from_move(dstk[0], dstk[1], csx=128, csy=0)
    # dispatch-frame state: the chased travel, unchanged facing, capped speedF
    assert (s.travel & 0xFFFF) == g['cut_frame']['travel']
    assert (s.facing & 0xFFFF) == g['cut_frame']['facing']
    assert s.speedF == g['cut_frame']['nspeed']
    # the RAW CUT_F endpoint, bit-for-bit the live posMove output
    assert _bits(s.pos_x) == int(g['live_raw_new_bits'][0], 16), \
        "raw cut endpoint x diverged from the live capture"
    assert _bits(s.pos_z) == int(g['live_raw_new_bits'][1], 16), \
        "raw cut endpoint z diverged from the live capture"


_SHIP = os.path.join(os.path.dirname(_HERE), 'tests', 'golden', 'walkstab_seam352_deliver.json')


def test_seam352_clip_delivered():
    """The seam352 walk-stab clip IS delivered live, 0-ULP (session 75, the 11th seam): live
    old/new == the sim's from-rest prediction bit-for-bit, the clip is genuine, and Link goes OOB
    (proc 0x24, pos_y below the floor). Unblocked by the dispatch-frame cut fix (the rawcut gate
    above): the corrected model's re-solve found a razor-true hit the phantom model could not.
    Re-sims the delivered sticks from rest (pure sim, no calibration) and reproduces the golden."""
    assert os.path.exists(_SHIP), "seam352 ship golden missing"
    g = json.load(open(_SHIP))
    assert g['anchor'] == ANCHOR and g['genuine'] is True and g['oob'] is True
    for a, b in (('live_old', 'sim_old'), ('live_new', 'sim_new')):
        assert _bits(g[a][0]) == _bits(g[b][0]) and _bits(g[a][1]) == _bits(g[b][1])
    tail = g['live_tail']
    assert tail[0]['proc'] == 0x42
    assert any(f['proc'] == 0x24 and f['pos_y'] < -6536.0 for f in tail)
    # pure-sim recomposition: the delivered sticks reproduce the golden bit-for-bit from rest
    h = g['hit']
    sticks = [tuple(sk) for sk in h['sticks']]
    N = h['N']
    s = C.rest_state(ANCHOR, dtm_seed=0)
    for k in range(N):
        s.step(sticks[k][0], sticks[k][1], csx=128, csy=0)
    assert _bits(s.pos_x) == _bits(g['sim_old'][0]) and _bits(s.pos_z) == _bits(g['sim_old'][1])
    dstk = sticks[N] if N < len(sticks) else sticks[-1]
    s.enter_cut_from_move(dstk[0], dstk[1], csx=128, csy=0)
    assert _bits(s.pos_x) == _bits(g['sim_new'][0]) and _bits(s.pos_z) == _bits(g['sim_new'][1])
    assert s.speedF == 17.0
