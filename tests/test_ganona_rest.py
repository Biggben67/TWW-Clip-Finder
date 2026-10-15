"""The GanonA r0 TAS corner seam_0255_0256 (S=(615.5078, 948.859436035, -2383.9854), Dereck's
named target) -- the Phase G FLOORS-MODE REST gate plus the delivered clip: the from-rest walk
on the micro-incline corridor must be bit-exact INCLUDING pos_y following the floor, and the
shipped roll-stab stream must reproduce the live CUT_F old/new 0-ULP.

REST GREEN as of session 66: the corridor PROC_STONE (ledger #52) is AVOIDED, never touched --
the geo fixture declares aim_deg=186.5 (the stone sits 16u off the interior-bisector line but
77.8u off this one) -- the anchor is minted at the cam-screened frozen pan target 25951, and
the last two ground terms were modeled decomp-first: setStepsOffset's m35C4 walk base-Y lift
(0.7 * per-frame downhill dy rides the draw base, d_a_player_main.cpp:9524/:9561) and
footBgCheck's non-plant field_0x030 CLOTCH leg lift (0.3f * ground clearance, :8816, consumed
by jointBeforeCB :276/:282).

CLIP DELIVERED session 67: the anchor re-minted ON-LINE (baseline |old perp| 1.783) from the
sword-DRAWN base `ganona_r0_base_drawn@twwgz` (ledger #55: a sheathed base's baseline roll can
never CUT, so mint_online never accepts), cam frozen at csangle 22577; `solve_focused` default
draw found 1 wall-faithful clip (margin 1, B2 fine) and it landed LIVE 0-ULP:
old=(620.3892822265625, -2340.420166015625) -> new=(614.9080810546875, -2389.334228515625),
CUT_F, drift (0,0).
Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIX = os.path.join(os.path.dirname(_HERE), 'fixtures')
_GOLD = os.path.join(_FIX, 'seam255_rest_golden.json')
_FLOORS = os.path.join(_FIX, 'ganona_r0_floors.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_FLOORS)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / GanonA floors mesh unavailable")

ANCHOR = 'ganona_r0_rollstab_seam255@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam255_rest_bitexact():
    """Floors-mode from-rest 0-ULP on the GanonA incline corridor, pos_y included."""
    assert os.path.exists(_GOLD), "REST golden not shipped (stone prop, ledger #52)"
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    stream = ([tuple(golden['straight'])] * golden['NPREF']
              + [tuple(golden['aim'])] * golden['NCRUISE'])
    s = C.rest_state(ANCHOR, dtm_seed=0, floors=_FLOORS)
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
        if lf.get('pos_y') is not None:
            ok = ok and _bits(s.pos_y) == _bits(lf['pos_y'])
        if not ok:
            bad.append(k)
    assert matched >= 24, "too few rows matched (%d)" % matched
    assert not bad, "seam255 floors-mode from-rest diverged at rows %s" % bad


_SHIP = os.path.join(_FIX, 'seam255_roll_ship_golden.json')


@pytest.mark.skipif(not os.path.exists(_SHIP), reason="seam255 ship golden unavailable")
def test_seam255_clip_delivered():
    """The seam255-corner roll-stab clip, found by `solver.solve_focused` (default family, B2
    fine) and delivered LIVE 0-ULP via a clean DTM at seed=0 -- the first clip on a SLOPED
    (micro-incline) corridor. The flat-model solve is exact here by the zero-cell fact
    (cM_atan2s truncates ratio*1024: getGroundAngle == 0, so floors mode changes no x/z byte;
    A/B-verified on the shipped stream). Live-captured golden, never edited."""
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
    for nm, s, l in (('old', sim_old, g['live_old']), ('new', sim_new, g['live_new'])):
        assert _bits(s[0]) == _bits(l[0]) and _bits(s[1]) == _bits(l[1]), \
            "%s not 0-ULP: sim=%s live=%s" % (nm, s, l)

    lc = g['live_cut_frame']
    assert g['live'][lc]['proc'] == (CUT_F & 0xFF), "live cut proc not CUT_F"
