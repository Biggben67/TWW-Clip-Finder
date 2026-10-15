"""The DISTINCT 97-deg corner S=(13539.24, 493.36), interior 97.0, walls 871 x 899 -- Dereck's target.

Session 51 overturned the "infeasible" ruling GEOMETRICALLY: `SeamGeo.pred_genuine` (the exact sim cut)
confirms a genuine razor at a ~90-deg GRAZING aim (facing 16306 at csangle 29883, ~41deg off the interior
bisector; geo `fixtures/kaze_r11_seam97_geo.json`, which now DECLARES `aim_deg=90`). Session 52 minted a
REST-BIT-EXACT anchor there and ran the solver -- 0 wall-faithful hits so far.

Session 53 RESOLVED the open reachability puzzle -- WITH LIVE DATA, decisively (the SESSION_PROMPT
decomp-first order: the roll's WallCorrect wall_r=35 is the ground-truth constant, verified here against
live RAM). The verified-genuine dust is confined to wallA_d 2.79..5.43u (all 15 f32 razor points sit
INSIDE Link's roll wall-hold). The question was whether the sim's 35u hold is FAITHFUL near this concave
corner or an over-correction. A clean-DTM roll toward the corner (facing 16306, seed=0), read per frame
from RAM, is **BIT-EXACT with the walled sim through the entire roll and wall-slide** (`test_seam97_roll_
wallhold_bitexact`): live holds Link's center at wallA_d==35.00 exactly as it grazes wallA, never closer.
So the reachability gap is REAL GEOMETRY, not a sim bug:
  * The 97-corner's only genuine dust hugs wallA at 2.79..5.43u; the live-faithful roll hold is 35u; a
    500k+-candidate f32 scan of the reachable mouth (>=33u from BOTH walls) across all grazing aims found
    0 genuine. So the dust is NOT reachable by a standard from-rest roll -- it sits ~30u inside the hold.
  * This is NOT "impossible" (Dereck's rule): a position hugging a wall is the kind reached by PUSH-STEERING
    (the standalone Tetra Co-push, which STEERS the lunge and overrides the free-roll hold) or another
    mechanic -- not by a free roll. `test_seam97_clip_delivered` stays RED: the ROLL path cannot deliver
    this corner. The strategic pick (push-steer this corner vs. a different novel roll target) is Dereck's.
  * The other angle (relax `solver.wall_faithful` to reject only bonks) is a correct concave-corner model
    tidy but does NOT unblock: the 35u-held sliders it would admit are all non-genuine (dust is at 3-5u).

Goldens are live-captured, never edited to make the sim pass (SESSION_PROMPT hard rule).
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam97_rest_golden.json')
_GEO = os.path.join(os.path.dirname(_HERE), 'fixtures', 'kaze_r11_seam97_geo.json')

try:
    from harness.rollstab import rest as C
    _HAVE = C.rest_state is not None and os.path.exists(_GOLD)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / seam97 golden unavailable")

ANCHOR = 'kaze_r11_rollstab_seam97@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_seam97_rest_bitexact_walled():
    """The fresh 97-corner anchor is REST BIT-EXACT (0 ULP) from rest through the walk approach WHEN
    WALLS ARE INCLUDED -- the straight +X approach at z~489 grazes wallA (871) near the corner, so the
    wall-less sim diverges at ~row 24 but the WALLED sim (walls=seam.TRIS) reproduces the live clean-DTM
    every row. This is the precondition for any solved clip to deliver 0-ULP. Delivered C-down every
    frame + seed=0 (noops=2). The anchor rests facing F (16306), so straight == aim. Index-aligned vs
    the live golden. NOTE the mint recipe (session 52): a NOVEL anchor at a FIXED-camera seam must be a
    GENUINELY aligned idle (travel_angle == facing); a teleport-rotated idle inherits the base idle's
    travel_angle and arcs off-course. Recipe: align-walk toward F -> settle to idle -> teleport to rest
    (preserves the aligned idle) -> mint_current."""
    from harness.rollstab.seamgeo import SeamGeo
    from harness.rollstab import geometry as G
    golden = json.load(open(_GOLD))
    assert golden['anchor'] == ANCHOR and golden.get('seed') == 0
    cs = G.load_seed(ANCHOR)['csangle'] & 0xFFFF
    seam = SeamGeo(json.load(open(_GEO)), csangle=cs)      # aim_deg=90 read from the fixture
    assert seam.F == golden['F'] == 16306
    sx0, sy0 = golden['straight']
    stream = [(sx0, sy0)] * (golden['NPREF'] + golden['NCRUISE'])
    s = C.rest_state(ANCHOR, walls=seam.TRIS, dtm_seed=0)
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
    assert matched >= 28, "too few rows matched (%d)" % matched
    assert not bad, "seam97 walled from-rest diverged at rows %s" % bad


_WALLHOLD = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam97_roll_wallhold_golden.json')


@pytest.mark.skipif(not os.path.exists(_WALLHOLD), reason="seam97 roll wall-hold golden unavailable")
def test_seam97_roll_wallhold_bitexact():
    """LIVE-VERIFIED (session 53): the walled from-rest roll toward the 97-deg concave corner holds
    Link's center exactly 35u off wallA and is BIT-EXACT vs a clean-DTM live capture through the whole
    roll. This LOCKS the finding that resolves the reachability puzzle -- the 35u WallCorrect hold is
    faithful near this concave corner (NOT a sim over-correction), so the genuine dust at wallA_d 2.79..
    5.43u is genuinely unreachable by a free roll. Reproduces the live golden offline: sim the walled
    rest_state on the captured stream and diff pos bit-for-bit on every FRONT_ROLL (0x1e) frame (the
    load-bearing wall-slide); the post-roll wedge tail (proc back to 0x06) is the known-unmodeled
    roll->MOVE exit, excluded. Also asserts the live wall-hold min == 35.0 (in front of wallA)."""
    from harness.rollstab.seamgeo import SeamGeo
    from harness.rollstab import geometry as G
    from tww_sim.land.land import FRONT_ROLL
    gold = json.load(open(_WALLHOLD))
    assert gold['anchor'] == ANCHOR and gold['dtm_seed'] == 0
    cs = G.load_seed(ANCHOR)['csangle'] & 0xFFFF
    seam = SeamGeo(json.load(open(_GEO)), csangle=cs)

    def wallA_d(x, z):
        return seam.wA.pla.func(seam.p32(x, z))

    stream = [tuple(x) for x in gold['stream']]
    lframes = gold['frames']
    s = C.rest_state(ANCHOR, walls=seam.TRIS, dtm_seed=0)
    n_roll, bad, live_hold = 0, [], []
    for i, (sx, sy, b) in enumerate(stream):
        s.step(sx, sy, buttons=b)
        if i >= len(lframes):
            break
        lf = lframes[i]
        if lf['proc'] == FRONT_ROLL:            # roll frames only (bit-exact region)
            n_roll += 1
            live_hold.append(wallA_d(lf['pos_x'], lf['pos_z']))
            if not (_bits(s.pos_x) == _bits(lf['pos_x']) and _bits(s.pos_z) == _bits(lf['pos_z'])):
                bad.append(i)
    assert n_roll >= 12, "too few live roll frames captured (%d)" % n_roll
    assert not bad, "seam97 walled roll diverged from live at rows %s" % bad
    # The live roll is held exactly 35u in front of wallA -- never reaches the 2.79..5.43u dust.
    assert abs(min(live_hold) - 35.0) < 1e-3, "live roll wall-hold min != 35u (%.4f)" % min(live_hold)


_SHIP = os.path.join(os.path.dirname(_HERE), 'fixtures', 'seam97_ship_golden.json')


@pytest.mark.xfail(reason="97-corner clip not yet delivered -- search has not found a wall-faithful "
                          "reachable path to the verified-genuine dust (see module docstring)", strict=True)
def test_seam97_clip_delivered():
    """RED until the 97-corner clip is delivered LIVE 0-ULP. Flip GREEN by producing a
    `fixtures/seam97_ship_golden.json` from a clean-DTM ship (mirror `test_mirror_clip_delivered`)."""
    assert os.path.exists(_SHIP), "no seam97 ship golden yet -- the clip is not delivered"
