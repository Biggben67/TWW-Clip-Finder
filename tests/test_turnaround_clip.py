"""Gate the LIVE follow-enabled turnaround-roll seam clip (session 24, "kill the glitched Tetra").

The session-22 push-aside clip needed a GLITCHED no-follow Tetra. This is the successor with a NORMAL
following (type-5) Tetra: on slot 7 she idles in the corner, Link (moved +110u NE) does a from-rest
DOWN-walk then a one-frame A+diagonal TURNAROUND roll ([[turnaround-roll-tech]]) that plows her aside;
her CC push steers the roll-stab ``CUT_F`` lunge through the seam at the (-1727,-990) corner. Delivered
live by a clean DTM and reproduced BIT-EXACT for BOTH actors on every frame, entry through cut.

Fixture ``fixtures/hyrule_turnaround_clip_live.json`` (the live per-frame log + the sim prediction).
Offline (no Dolphin): the log is replayed and the coupled engine re-run, seeded at the DTM's MEASURED
live roll entry (the from-rest walk is not yet bit-exact, so the entry is measured, not modelled).
"""
import json
import os

import pytest


from tests._anim_data import CUTS, require
require(CUTS, "cut keyframe data")
from harness.rollstab import turnaround as T

_HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(_HERE, os.pardir, 'fixtures', 'hyrule_turnaround_clip_live.json')

CUT_F_PROC = 66
FALL_PROC = 39
FRONT_ROLL = 30


@pytest.fixture(scope='module')
def clip():
    return json.load(open(FIX))


@pytest.fixture(scope='module')
def sim(clip):
    entry = tuple(clip['roll_entry'])
    tetra = tuple(clip['tetra_start'])
    res, steps, sch = T.sim_at(tetra, entry, clip['entry_facing'], clip['entry_m351C'],
                               T.GROUND_Y, clip['thrust_sim_step'])
    return res, steps, sch


def test_sim_predicts_the_clip_at_the_live_entry(clip, sim):
    """The coupled engine, seeded at the DTM's MEASURED live roll entry, calls this placement GENUINE
    and lands the documented old/new/push. The genuine region is f32-dust sensitive to the entry, so
    it is located AT the measured entry (not the sim's from-rest entry, which is ~2.6u off)."""
    res, _, sch = sim
    assert res['genuine'] is True
    assert res['old'] == tuple(clip['sim_old'])
    assert res['new'] == tuple(clip['sim_new'])
    assert res['push'] == tuple(clip['sim_push'])
    assert sch['cut_step'] == clip['cut_sim_step']


def test_live_cut_endpoint_is_bit_exact(clip):
    """LIVE: the CUT_F fires and lands EXACTLY on the sim's predicted `new`, and Link then falls
    (proc 39) -- i.e. he is THROUGH the seam behind the corner."""
    rows = clip['frames']
    cut = [r for r in rows if r['proc'] == CUT_F_PROC]
    assert cut, "no CUT_F frame in the live log"
    assert (cut[0]['lx'], cut[0]['lz']) == tuple(clip['sim_new'])          # bit-for-bit
    fall = [r for r in rows if r['proc'] == FALL_PROC and r['f'] > cut[0]['f']]
    assert fall, "Link never fell through the seam after the cut"


def test_live_old_is_bit_exact(clip):
    """The pre-cut frame (the plow-perturbed `old`) is bit-exact vs the sim -- the razor pin."""
    rows = clip['frames']
    cut = [r for r in rows if r['proc'] == CUT_F_PROC][0]
    pre = [r for r in rows if r['f'] == cut['f'] - 1][0]
    assert (pre['lx'], pre['lz']) == tuple(clip['sim_old'])


def test_roll_is_bit_exact_for_both_actors(clip, sim):
    """Every roll frame (entry+1 .. cut) matches the coupled sim 0-ULP for BOTH Link and Tetra --
    the plow-aside AND the push-steered cut lunge (alignment: sim step k == live frame entry+1+k)."""
    _, steps, _ = sim
    rows = clip['frames']
    e = next(r['f'] for r in rows if r['proc'] == FRONT_ROLL)
    checked = 0
    for r in rows:
        k = r['f'] - e - 1
        if 0 <= k < len(steps) and r['proc'] in (FRONT_ROLL, CUT_F_PROC):
            sx, sz, tx, tz = steps[k]
            assert (r['lx'], r['lz']) == (sx, sz), "Link diverged at k%d (frame %d)" % (k, r['f'])
            assert (r['tx'], r['tz']) == (tx, tz), "Tetra diverged at k%d (frame %d)" % (k, r['f'])
            checked += 1
    assert checked >= 15, "expected the whole roll checked, only %d frames" % checked


def test_tetra_start_is_on_walkable_floor(clip):
    """Tetra's START must be in front of BOTH seam walls (pushaside truth #1). Off it she falls OOB
    and there is NO push -- the clip cannot fire."""
    from harness.rollstab import geometry_tetra as GT
    tx, tz = clip['tetra_start']
    p = GT.p32(tx, tz)
    assert GT.wA.pla.func(p) > 0
    assert GT.wB.pla.func(p) > 0


def test_following_tetra_initial_condition(clip):
    """Slot 7, a NORMAL following Tetra, placed as an INITIAL condition (no mid-run write / no glitch)."""
    assert clip['slot'] == 7
    assert 'following' in clip['note']
    assert 'INITIAL condition' in clip['note']
    assert clip['bit_exact'] is True
    assert clip['live_fell'] is True
