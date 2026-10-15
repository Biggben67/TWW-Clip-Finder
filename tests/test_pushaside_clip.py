"""Gate the LIVE push-aside seam clip (session 22, the Phase-T north star).

Tetra stands from the START (``placed_step=0`` -- an initial condition, NO mid-run write); Link's
roll PLOWS her aside, and her CC push steers the roll-stab ``CUT_F`` lunge through the seam at the
flooded-Hyrule corner (-1727,-990). Delivered live by a clean DTM and reproduced BIT-EXACT.

The two facts this locks down (fixture ``fixtures/hyrule_pushaside_clip_live.json``):

1. Seeded at the DTM's ACTUAL roll entry (the calibrated-walk entry -- NOT the capture fixture's;
   they differ by ~0.004u, which on f32 dust is block-vs-clip), the coupled engine reproduces the
   live run and predicts ``genuine``.
2. The engine's cut endpoint ``new`` == the LIVE cut endpoint, bit-for-bit.

Offline (no Dolphin): the live per-frame log is replayed from the fixture.
"""
import json
import os

import pytest


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from harness.rollstab import fast_shove as FS

_HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(_HERE, os.pardir, 'fixtures', 'hyrule_pushaside_clip_live.json')

CUT_F_PROC = 66
FALL_PROC = 39


@pytest.fixture(scope='module')
def clip():
    return json.load(open(FIX))


@pytest.fixture(scope='module')
def engine():
    fix = FS.load_fixture()
    walls = FS.load_walls(fix)
    inputs = FS.make_inputs(14)
    ctx, sch = FS.build_ctx(fix, walls, inputs)
    return fix, walls, inputs, ctx, sch


def test_sim_predicts_the_clip_at_the_live_entry(clip, engine):
    """The coupled engine, seeded at the DTM's real roll entry, calls this placement GENUINE and
    lands the documented old/new. (Seeded at the capture fixture's entry it does NOT -- that 0.004u
    entry difference is exactly what made the first live attempt miss.)"""
    _, _, _, ctx, sch = engine
    ex, ez = clip['roll_entry']
    tx, tz = clip['tetra_start']
    res = ctx.run_one(tx, tz, 0, link_x0=ex, link_z0=ez)
    assert res['genuine'] is True
    assert res['old'] == tuple(clip['sim_old'])
    assert res['new'] == tuple(clip['sim_new'])
    assert res['push'] == tuple(clip['sim_push'])
    assert sch['cut_step'] == clip['cut_sim_step']


def test_native_matches_python_reference(clip, engine):
    """The native engine is bit-identical to the live-validated Python coupled engine here."""
    fix, walls, inputs, ctx, _ = engine
    ex, ez = clip['roll_entry']
    tx, tz = clip['tetra_start']
    res = ctx.run_one(tx, tz, 0, link_x0=ex, link_z0=ez)
    ref, _ = FS.py_reference(fix, walls, inputs, (tx, tz), 0, link_entry=(ex, ez))
    assert ref['genuine'] == res['genuine']
    assert ref['old'] == res['old']
    assert ref['new'] == res['new']
    assert ref['push'] == res['push']


def test_live_cut_endpoint_is_bit_exact(clip):
    """LIVE: the CUT_F fires and lands EXACTLY on the sim's predicted `new`, and Link then falls
    (proc 39) -- i.e. he is THROUGH the seam, behind the corner."""
    rows = clip['frames']
    cut = [r for r in rows if r['proc'] == CUT_F_PROC]
    assert cut, "no CUT_F frame in the live log"
    assert (cut[0]['lx'], cut[0]['lz']) == tuple(clip['sim_new'])      # bit-for-bit
    fall = [r for r in rows if r['proc'] == FALL_PROC and r['f'] > cut[0]['f']]
    assert fall, "Link never fell through the seam after the cut"


def test_live_old_is_bit_exact(clip):
    """The pre-cut frame (the plow-perturbed `old`) is bit-exact vs the sim -- the razor."""
    rows = clip['frames']
    cut = [r for r in rows if r['proc'] == CUT_F_PROC][0]
    pre = [r for r in rows if r['f'] == cut['f'] - 1][0]
    assert (pre['lx'], pre['lz']) == tuple(clip['sim_old'])


def test_tetra_start_is_on_walkable_floor(clip):
    """Tetra's START must be in front of BOTH seam walls. Off it she falls OOB and there is NO push
    -- that is exactly how the first live attempt failed (she was behind wall B, fB<0)."""
    from harness.rollstab import geometry_tetra as GT
    tx, tz = clip['tetra_start']
    p = GT.p32(tx, tz)
    assert GT.wA.pla.func(p) > 0
    assert GT.wB.pla.func(p) > 0


def test_tetra_is_an_initial_condition():
    """placed_step == 0: she stands there from the start. No mid-run teleport (the rejected hack)."""
    clip_ = json.load(open(FIX))
    assert 'placed_step' not in clip_ or clip_.get('placed_step', 0) == 0
    assert 'INITIAL condition' in clip_['note']
