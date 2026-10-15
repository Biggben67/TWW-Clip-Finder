"""The NOVEL 152-deg corner S=(10555.1904, 190.6696), interior 151.68, walls 840 x 845 -- the second
seam delivered end-to-end by the GENERALIZED roll path (session 54), and the first with BOTH an
OFF-BISECTOR declared aim (`aim_deg=163.08` in `fixtures/kaze_r11_seam152_geo.json`; the bisector
132.3 has no reachable dust) and a PANNED-camera anchor (`mint_novel` C-stick pan; the local auto-cam
TRACKS Link's position until a pan arms the manual cam, after which csangle is frozen -- the
constant-csangle rest model's precondition).

Anchor `kaze_r11_rollstab_seam152@twwgz`: minted ON the F-through-S line (perp -3.99u; the solver's
arc reach is ~+-15u, so an off-line anchor -- the first mint drifted 117u off -- finds 0 hits), rest
d2S 584u, facing 25794 (~22 deg off F=29729: the anchor need NOT face F -- solve_focused's arc
bracket absorbs the initial misaim; REST bit-exactness is what matters).

Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam152_rest_golden.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / seam152 golden unavailable")

ANCHOR = 'kaze_r11_rollstab_seam152@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam152_rest_bitexact():
    """The panned-camera novel-seam anchor is REST BIT-EXACT (0 ULP) from rest through the walk
    approach -- straight prefix at the anchor facing (25794), then the aim cruise at F=29729 (a real
    ~22-deg MOVE turn, modeled). Delivered C-down every frame + seed=0 (noops = rest_noops(1) + 1).
    csangle 22603 held frozen live through the whole walk (the mint's C-stick pan armed the manual
    cam; without it the local auto-cam tracks Link's position and no constant-cs sim can match).
    Index-aligned vs the live golden."""
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
    assert not bad, "seam152 from-rest diverged at rows %s" % bad


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam152_roll_ship_golden.json')


@pytest.mark.skipif(not os.path.exists(_SHIP), reason="seam152 ship golden unavailable")
def test_seam152_clip_delivered():
    """Session 54: the 152-deg-corner roll-stab clip, found by the generalized `solver.solve_focused`
    (1 wall-faithful hit in 80s, margin 14) and delivered LIVE 0-ULP via a clean DTM at seed=0:
    old=(10542.6318359, 232.2424469) -> new=(10556.8652344, 185.1252899), CUT_F then OOB (proc 0x24).

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
