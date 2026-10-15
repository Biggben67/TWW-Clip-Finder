"""Sheathed roll-stab CLIP regression (kaze r11; sessions 39-44).

Milestone (DONE, session 44): route a NOT-DRAWN (sheathed) anchor's ROLL verdict to a from-rest
roll-stab clip at the kaze roll seam, DELIVERED LIVE 0-ULP. Session 38 made
`kaze_r11_rollstab_sheathed@twwgz` REST BIT-EXACT; session 39 SOLVED a from-rest genuine clip (found
in the sim, warm-started from the same-seam idle13 recipe). The recipe (pure sim, from the anchor seed
only -- no calibration): A_proj=-500, draw_at=3, a K=2 crawl + arc + 2 fines.

DELIVERY ROOT CAUSE (session 42, RAM-CONFIRMED) + FIX (session 44):
  * The live miss was a make_dtm DELIVERY DROP, NOT a physics/decode gap. Reading
    `g_mDoCPd_cpadInfo[0].mMainStickValue` per game frame proved the decomp physics + decode are
    faithful and the ship's row-18 band fine was simply never RECEIVED: the pipeline default
    `make_dtm(polls=4, seed=1)` prepends one leading NEUTRAL POLL whose sub-frame phase drops a
    1-frame partial fine that is clustered after other partials (dead-end #34). `seed=0` (no leading
    neutral poll) delivers every fine at the SAME timing.
  * seed=0 shifts the leading-poll layout, so the from-rest sim needs one MORE leading no-op
    (`noops = rest_noops + (1 - dtm_seed)`, measured live session 43 -> REST bit-exact at noops=2,
    test_sheathed_roll_rest::test_sheathed_rest_bitexact_seed0). That extra leading no-op was silently
    EATING the crawl's first frame `start[0]` -- a GENERAL seed-0 crawl-composition bug (dead-end #35).
  * FIX (session 44, GENERAL -- no tuned constants): `solver.run` prepends `(1 - dtm_seed)` neutral
    ABSORBER frames so `start[0]` always lands on the first LIVE frame; the absorber is a full frame
    (a polls multiple) so seed-0's correct poll phase is preserved. With this, the SAME session-39
    recipe re-composed under `dtm_seed=0` reproduces the genuine clip bit-for-bit AND delivers live.

The live golden `fixtures/sheathed_roll_ship_seed0_golden.json` (game_frame-tagged, IMMUTABLE) is the
successful seed=0 ship -- the sim reproduces it bit-for-bit through the CUT_F entry (the post-cut OOB
fall proc 0x24 is the known-unmodeled CUT tail, ROADMAP Phase C, moot for the clip). The seed=1 golden
`fixtures/sheathed_roll_ship_jitterproof.json` (also immutable) records the BUGGY seed=1 delivery (band
dropped); the strict-xfail test below keeps that bug gated. NEVER edit either golden to make a test pass.
"""
import json
import os
import struct

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FX = os.path.join(os.path.dirname(_HERE), 'fixtures', 'sheathed_roll_ship_jitterproof.json')
_FX0 = os.path.join(os.path.dirname(_HERE), 'fixtures', 'sheathed_roll_ship_seed0_golden.json')

try:
    from harness.rollstab import solver as SV
    from harness.rollstab import geometry as G
    from harness.rollstab import rest as C
    from tww_sim.land.land import CUT_F, CUT_A
    from tww_sim.core.fp import f32 as _f
    _HAVE = os.path.exists(_FX) and os.path.exists(_FX0)
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness / sheathed goldens unavailable")

ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'
A_PROJ = -500.0
DRAW_AT = 3
DTM_SEED = 0        # the SHIPPED delivery seed (the make_dtm fix, sessions 42-44)
MOVES = ((9, (73, 254), 2), (10, (99, 183)), (4, (96, 192)), (6, (98, 188)))
START = ((77, 249), (98, 191))
MARGIN_Z = 0.0002


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _run(dtm_seed=DTM_SEED):
    return SV.run(ANCHOR, MOVES, A_proj=A_PROJ, start=START, draw_at=DRAW_AT, dtm_seed=dtm_seed)


def test_sheathed_offline_clip_bitexact():
    """The SOLVE is real: the from-rest sheathed run (composed for the shipped seed=0 delivery) fires a
    genuine, wall-clear roll-stab CUT at the 17-cap (full 49.22 lunge) toward the seam facing, and the
    exact `old` is sliver-robust. Pure sim, from the anchor seed only (session 39; seed-0 compose s44)."""
    r = _run()
    assert r is not None and r.get('fired'), "sheathed roll-stab CUT did not fire from rest"
    assert r['facing'] == G.F
    assert r['spF_at_A'] == 17.0, "walk not at cap at the A press -> shrunken lunge"
    assert r['genuine'] and r['clear'], "not a genuine, wall-clear clip"
    assert abs(r['disp'] - 49.2202) < 1e-3
    # sliver robustness (deliver.py gate): pred_genuine holds at old_z +- MARGIN_Z
    assert G.pred_genuine((r['old'][0], _f(r['old'][1] + MARGIN_Z)))
    assert G.pred_genuine((r['old'][0], _f(r['old'][1] - MARGIN_Z)))


def test_seed0_crawl_frame_acts():
    """The GENERAL seed-0 crawl-composition fix (session 44, dead-end #35): under `dtm_seed=0` the game
    delivers one FEWER leading neutral poll, so rest_state burns one MORE leading no-op -- which, without
    compensation, silently EATS the crawl's first frame `start[0]`. `run` prepends `(1 - dtm_seed)`
    neutral ABSORBER frames to fix it GENERALLY. Locks two invariants:
      1. the seed-0 stream carries exactly one extra LEADING neutral frame (the absorber) vs seed=1;
      2. the crawl composes seed-INVARIANTLY -- `old` is bit-identical under seed=0 and seed=1 (the
         absorber only offsets the dead leading-poll layout; the crawl physics is unchanged). If the
         absorber were missing, `start[0]` would be dropped under seed=0 and `old` would shift."""
    r1 = _run(dtm_seed=1)
    r0 = _run(dtm_seed=0)
    s1 = [tuple(x) for x in r1['stream']]
    s0 = [tuple(x) for x in r0['stream']]
    assert len(s0) == len(s1) + 1, "seed-0 stream must carry exactly one absorber frame"
    assert s0[0] == (128, 128, 0), "the absorber must be a leading NEUTRAL frame"
    assert s0[1:] == s1, "past the absorber the seed-0 and seed-1 streams are identical"
    assert _bits(r0['old'][0]) == _bits(r1['old'][0]) and _bits(r0['old'][1]) == _bits(r1['old'][1]), \
        "crawl composed one frame short under seed=0 (start[0] dropped) -> old shifted"
    assert r0['genuine'] and r0['clear']


def test_sheathed_ship_delivery():
    """GREEN (session 44): the sheathed roll-stab clip DELIVERS live 0-ULP via the make_dtm seed=0 fix +
    the general seed-0 crawl absorber. Replay the seed-0 hit's stream from rest (`rest_state(dtm_seed=0)`)
    and diff bit-for-bit vs the IMMUTABLE game_frame-tagged golden captured from the successful ship
    (`sheathed_roll_ship_seed0_golden.json`). Alignment: sim row i <-> live gf = liveMOVE + 2*(i-simMOVE)
    (the emulator counter ticks twice per game frame; jitter-immune). Bit-exact on EVERY game_frame-
    aligned row THROUGH the CUT_F entry (the decisive old->new); the post-cut OOB fall (proc 0x24) is the
    known-unmodeled CUT tail (ROADMAP Phase C), moot for the clip, so rows past the CUT are not compared.
    This is the objective met: a pure-sim, from-rest, no-calibration clip reproduced live 0-ULP."""
    g = json.load(open(_FX0))
    assert g['anchor'] == ANCHOR and g.get('seed') == 0
    live = {r['game_frame']: r for r in g['rows']}
    r = _run(dtm_seed=0)
    assert r['genuine'] and r['clear'], "the shipped seed-0 recipe must be a genuine, wall-clear clip"
    stream = [tuple(x) for x in r['stream']]
    s = C.rest_state(ANCHOR, dtm_seed=0)
    sim = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        sim.append((s.state & 0xFF, s.pos_x, s.pos_z))
    sim_move = next(i for i, x in enumerate(sim) if x[0] == 6)              # first MOVE proc
    live_move = next(rr['game_frame'] for rr in g['rows'] if rr['proc'] == 6)
    sim_cut = next(i for i, x in enumerate(sim) if x[0] in (CUT_F, CUT_A))  # the decisive CUT frame
    matched, bad = 0, []
    for i, (st, px, pz) in enumerate(sim):
        if i > sim_cut:                          # post-cut OOB fall = unmodeled CUT tail, moot for the clip
            break
        gf = live_move + 2 * (i - sim_move)
        lv = live.get(gf)
        if lv is None:
            continue
        matched += 1
        if not (_bits(pz) == _bits(lv['pos_z']) and _bits(px) == _bits(lv['pos_x'])):
            bad.append((i, gf, round(pz - lv['pos_z'], 5)))
    assert matched >= 20, "too few game_frame-aligned rows through the CUT (%d)" % matched
    assert not bad, "seed-0 delivery diverged from live at %s" % bad
    # the decisive CUT lands bit-for-bit and Link goes OOB (proc 0x24) right after -> the clip threaded
    assert _bits(sim[sim_cut][1]) == _bits(g['hit_new'][0]) and _bits(sim[sim_cut][2]) == _bits(g['hit_new'][1])
    cut_gf = live_move + 2 * (sim_cut - sim_move)
    assert live[cut_gf]['proc'] == CUT_F and live[cut_gf + 2]['proc'] == 0x24


@pytest.mark.xfail(strict=True, reason="Documents the make_dtm seed=1 DELIVERY DROP (dead-end #34): the "
                                       "pipeline OLD default make_dtm(polls=4, seed=1) prepends a leading "
                                       "neutral poll whose sub-frame phase drops the clustered row-18 band "
                                       "fine, so the sim (which acts every authored frame) correctly does "
                                       "NOT match the seed=1 live golden -- it diverges ~1.9u along-track "
                                       "at row 18. The clip now ships via seed=0 (test_sheathed_ship_"
                                       "delivery, GREEN); this xfail keeps the seed=1 bug gated so a "
                                       "regression to the seed=1 default would be caught.")
def test_seed1_delivery_drops_band():
    """The seed=1 delivery drop, kept as a gated negative. Replay the seed=1-composed stream from rest
    (`rest_state()` default seed=1) and compare along-track z to the jitter-immune seed=1 live golden
    (game_frame-aligned). Bit-exact through row 17, then at row 18 the sim acts the band fine make_dtm
    authored while the console held 17 (that fine was DROPPED -- polls=4/seed=1 phase slip)."""
    g = json.load(open(_FX))
    live = {r['gf']: r for r in g['rows']}
    r = _run(dtm_seed=1)
    stream = [tuple(x) for x in r['stream']]
    s = C.rest_state(ANCHOR)
    sim = []
    for sx, sy, b in stream:
        s.step(sx, sy, buttons=b)
        sim.append((s.state & 0xFF, s.pos_x, s.pos_z))
    sim_move = next(i for i, x in enumerate(sim) if x[0] == 6)          # first MOVE proc
    live_move = next(rr['gf'] for rr in g['rows'] if rr['proc'] == 6)
    bad = []
    for i, (st, px, pz) in enumerate(sim):
        gf = live_move + 2 * (i - sim_move)
        lv = live.get(gf)
        if lv is None:
            continue
        if not (_bits(pz) == _bits(lv['z']) and _bits(px) == _bits(lv['x'])):
            bad.append((i, gf, round(pz - lv['z'], 4)))
    assert not bad, "sim along-track diverged from live (seed=1 band drop) at %s" % bad
