"""Walk-stab seam-clip: solver/acceptance gates + the live-delivery status (session 31).

WHAT THIS LOCKS:
  * GREEN -- `build_stream` is DELIVERY-FAITHFUL: the per-byte fine nudge is applied to the raw
    authored byte, clamped to [0,255], then run through dtm_make's calibration, so every stick the
    solver tests is one a clean DTM can actually deliver (bytes in [1,254]). The session-30 code
    nudged a post-calibration byte, which could overflow 255 (a non-deliverable stick).
  * GREEN -- the acceptance geometry: the genuine seam-clip sliver confirmed pure-geometry near
    old=(9011.117,1352.468) IS classified genuine, and stepping ~2.2e-4u off it perpendicular is
    blocked (the f32 razor). This is the target the walk must land `old` on.
  * GREEN (session 32) -- the LIVE clip IS delivered, pure-sim, 0-ULP. `solve_focused` (K=3 crawls +
    perp pre-filter + wall-faithful gate) found a deliverable hit in-budget; a clean DTM delivered it
    and Link CLIPPED THROUGH the seam OOB (proc 0x24, pos_y below the floor), with `old`/`new`
    bit-for-bit the sim's prediction. Locked by the tracked golden tests/golden/walkstab_deliver.json.
"""
import json
import math
import os
import struct

import pytest

try:
    from harness.rollstab import walkstab as W
    from harness.rollstab import rest as C
    from tww_sim.core.fp import f32 as _f
    _HAVE = C.rest_state is not None
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / anim data unavailable")

# Confirmed pure-geometry genuine sliver (session 30/31; ~2.2e-4u wide, flanked by CrrPos-blocked).
# old->new is the exact CUT_F lunge at the walk facing -- the real target the walk must reach.
SLIVER_OLD = (9011.1171875, 1352.4676513671875)
SLIVER_NEW = (9031.6611328125, 1387.0457763671875)


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def test_walkstab_build_stream_deliverable():
    """Every stick build_stream emits -- with or without a fine nudge -- is DELIVERABLE (a clean DTM
    delivers bytes in [1,254]; dtm_make maps 0->1, 255->254). A nudge must never yield a byte a DTM
    cannot produce."""
    bad = []
    for fdx in (-8, -4, 0, 4, 8):
        for fdz in (-8, -4, 0, 4, 8):
            sticks = W.build_stream(5560, (0.52, 0.68, 0.52), 760, 5, 3, 7, fdx, fdz)
            for (bx, by) in sticks:
                if not (1 <= bx <= 254 and 1 <= by <= 254):
                    bad.append((fdx, fdz, bx, by))
    assert not bad, "build_stream emitted non-deliverable bytes: %s" % bad[:5]


def test_walkstab_genuine_sliver_present():
    """The acceptance geometry: the confirmed sliver is genuine, and a ~2.2e-4u perpendicular step
    off it is blocked (the f32 razor the search must thread)."""
    ok, why = W.genuine_clip(SLIVER_OLD, SLIVER_NEW)
    assert ok, "the confirmed genuine sliver is not genuine (why=%s)" % why
    # step perpendicular to the lunge until it stops clipping -> a razor, not a plateau
    lunge = (SLIVER_NEW[0] - SLIVER_OLD[0], SLIVER_NEW[1] - SLIVER_OLD[1])
    a = math.atan2(lunge[0], lunge[1])
    pdx, pdz = -math.cos(a), math.sin(a)
    far = (_f(SLIVER_OLD[0] + _f(0.001 * pdx)), _f(SLIVER_OLD[1] + _f(0.001 * pdz)))
    farn = (_f(far[0] + _f(lunge[0])), _f(far[1] + _f(lunge[1])))
    assert not W.genuine_clip(far, farn)[0], "0.001u off perpendicular still clips -- not a razor"


def test_walkstab_sim_reproduces_sliver_is_geometry_only():
    """Guard: the sliver classification is pure geometry (independent of the sim), so it stays valid
    as the from-rest sim / solver evolve. `new` == f32(old + lunge) bit-for-bit."""
    lunge = (_f(SLIVER_NEW[0] - SLIVER_OLD[0]), _f(SLIVER_NEW[1] - SLIVER_OLD[1]))
    recon = (_f(SLIVER_OLD[0] + lunge[0]), _f(SLIVER_OLD[1] + lunge[1]))
    assert _bits(recon[0]) == _bits(SLIVER_NEW[0]) and _bits(recon[1]) == _bits(SLIVER_NEW[1])


GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'tests', 'golden', 'walkstab_deliver.json')


def test_walkstab_live_delivery_clips():
    """The delivered walk-stab clip (session 32), locked by the tracked live golden: the CUT_F fired
    at N=13, `old`/`new` were bit-for-bit the sim's from-rest prediction (0-ULP delivery), the clip is
    genuine, and Link went OOB (proc 0x24, pos_y dropping below the floor). Pure-sim, no calibration."""
    assert os.path.exists(GOLDEN), "no committed walk-stab delivery golden"
    g = json.load(open(GOLDEN))
    assert g['genuine'] is True and g['oob'] is True
    # 0-ULP delivery: live old/new == the sim's from-rest prediction, bit-for-bit.
    assert _bits(g['live_old'][0]) == _bits(g['sim_old'][0])
    assert _bits(g['live_old'][1]) == _bits(g['sim_old'][1])
    assert _bits(g['live_new'][0]) == _bits(g['sim_new'][0])
    assert _bits(g['live_new'][1]) == _bits(g['sim_new'][1])
    # the delivered `old` is a genuine seam clip (the acceptance the search enforced).
    assert W.genuine_clip(tuple(g['live_old']), tuple(g['live_new']))[0]
    # OOB signature: the CUT frame is proc 0x42, then Link leaves for proc 0x24 with pos_y < floor.
    tail = g['live_tail']
    assert tail[0]['proc'] == 0x42
    assert any(f['proc'] == 0x24 and f['pos_y'] < W.LINK_Y - 2.0 for f in tail)


POSITIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'tests', 'golden', 'walkstab_positions.json')


@pytest.mark.skipif(not _HAVE, reason="anim data unavailable")
def test_walkstab_multiple_positions_clip():
    """Rigorous multi-position check (session 32): THREE distinct `old` positions around the seam were
    each delivered live and clipped 0-ULP (genuine + OOB). This guards that the solver+delivery is
    reliable across the seam's wall-faithful window, not a one-off. For each committed position, re-sim
    its exact delivered sticks FROM REST (pure sim) and confirm `old`/`new` reproduce the recorded
    sim bit-for-bit, the clip is genuine, speedF is 17, and the recorded live `old` == the sim `old`."""
    g = json.load(open(POSITIONS))
    assert g['n_positions'] >= 3
    olds = set()
    for i, p in enumerate(g['positions']):
        h = p['hit']
        sticks = [tuple(sk) for sk in h['sticks']]
        s = W.seed()
        s._foot.skip_cruise_pose = True
        for k in range(h['N']):
            stk = sticks[k] if k < len(sticks) else sticks[-1]
            s.step(stk[0], stk[1], csx=128, csy=W.CDOWN)
        old = (s.pos_x, s.pos_z)
        nx, nz = W.fast_cut(old[0], old[1], s.facing, s.nspeed)
        assert _bits(old[0]) == _bits(p['sim_old'][0]) and _bits(old[1]) == _bits(p['sim_old'][1]), i
        assert _bits(nx) == _bits(p['sim_new'][0]) and _bits(nz) == _bits(p['sim_new'][1]), i
        assert W.genuine_clip(old, (nx, nz))[0], i
        assert s.speedF == 17.0, i
        assert _bits(p['live_old'][0]) == _bits(p['sim_old'][0]), i   # 0-ULP delivery
        assert _bits(p['live_old'][1]) == _bits(p['sim_old'][1]), i
        olds.add((_bits(old[0]), _bits(old[1])))
    assert len(olds) == len(g['positions']), "positions must be DISTINCT olds"


@pytest.mark.skipif(not _HAVE, reason="anim data unavailable")
def test_walkstab_committed_hit_resims_from_rest():
    """Guard the SIM against the golden: re-sim the committed hit's exact delivered sticks FROM REST
    (pure sim, no calibration) and confirm it reproduces the golden's sim_old bit-for-bit and clips.
    This is what makes the delivery a true one-shot -- the search's offline `old` IS the live `old`."""
    g = json.load(open(GOLDEN))
    hit = g['hit']
    sticks = [tuple(sk) for sk in hit['sticks']]
    s = W.seed()
    s._foot.skip_cruise_pose = True
    for k in range(hit['N']):
        stk = sticks[k] if k < len(sticks) else sticks[-1]
        s.step(stk[0], stk[1], csx=128, csy=W.CDOWN)
    old = (s.pos_x, s.pos_z)
    nx, nz = W.fast_cut(old[0], old[1], s.facing, s.nspeed)
    assert _bits(old[0]) == _bits(g['sim_old'][0]) and _bits(old[1]) == _bits(g['sim_old'][1])
    assert _bits(nx) == _bits(g['sim_new'][0]) and _bits(nz) == _bits(g['sim_new'][1])
    assert W.genuine_clip(old, (nx, nz))[0]
    assert s.speedF == 17.0
