"""Session-56 run() throughput: the fast paths are BIT-IDENTICAL to the slow ones.

Three throughput mechanisms landed for the thin-dust 97m draws, each of which must never change a
single output bit:

  1. FAST_POSE -- the lazy cruise-pose defer (`FootSpeedF.skip_cruise_pose` upgraded from
     walkstab's drop-outright shortcut to a defer+drain backlog): at m3598==0 speedF==nspeed
     exactly, so the pose feeds only future composes; skipped poses replay in order on the first
     consumer (an m3598!=0 compose or a stop), so streams with mid-cruise partial-magnitude moves
     -- which the drop-outright path would corrupt -- stay exact.
  2. cross_hint -- seeding run()'s placement fixpoint with a neighbour's cross frame. The accept
     invariant (want == placed on the SIMULATED trajectory) is unchanged.
  3. solve_focused(procs=) -- Phase-B workers evaluate the same exact candidates (equality is
     exercised by the by-hand pool A/B in the session log, not here: spawning workers from pytest
     is slow and environment-dependent).

The A/B here drives run() over a candidate batch that exercises BOTH drain triggers (a partial m2
start crawl and a mid-cruise partial-magnitude fine) on the DEFAULT kaze seam, comparing the full
result -- old/new bits, facing, spF, and the literal stream -- fast vs slow.
"""
import json
import os
import struct

import pytest

try:
    from harness.rollstab import solver as SV
    from harness.rollstab.geometry import load_seed
    _HAVE = True
except Exception:
    _HAVE = False

pytestmark = pytest.mark.skipif(not _HAVE, reason="rollstab harness unavailable")

ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'


def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def _sig(r):
    if not (r and r.get('fired')):
        return ('nofire', r.get('spF_at_A') if r else None)
    return (_bits(r['old'][0]), _bits(r['old'][1]), _bits(r['new'][0]), _bits(r['new'][1]),
            r['facing'], _bits(r['spF_at_A']), tuple(map(tuple, r['stream'])))


def _batch(hint_on):
    from tww_sim.land.plan_land import stick_for_bearing
    cs = load_seed(ANCHOR)['csangle'] & 0xFFFF
    F = SV._KAZE_SEAM.F
    full = SV.C.dtm_stick(stick_for_bearing(F, cs, 1.0))
    arc = SV.C.dtm_stick(stick_for_bearing((F + 600) & 0xFFFF, cs, 1.0))
    fine = SV.C.dtm_stick(stick_for_bearing(F, cs, 0.71))     # mid-cruise partial: drains the backlog
    f2p = SV.C.dtm_stick(stick_for_bearing(F, cs, 0.72))      # partial m2 crawl frame
    out, hint = [], None
    for m2stk in (full, f2p):
        for moves in ([(5, arc, 3)], [(5, arc, 3), (9, fine)]):
            for i in range(6):
                c3 = SV.C.dtm_stick((100 + i, 90 + i))
                r = SV.run(ANCHOR, moves, A_proj=-500.0, start=(full, m2stk, c3), draw_at=3,
                           dtm_seed=0, cross_hint=(hint if hint_on else None))
                if r and r.get('fired'):
                    hint = r.get('cross')
                out.append(_sig(r))
    return out


def test_fast_pose_bitexact_vs_slow():
    """FAST_POSE on == FAST_POSE off, bit-for-bit, over crawl/arc/fine candidates (both drain
    triggers exercised: the m2 partial crawl and the mid-cruise fine both land on frames whose
    compose consumes the deferred toe stream)."""
    was = SV.FAST_POSE
    try:
        SV.FAST_POSE = False
        ref = _batch(False)
        SV.FAST_POSE = True
        fast = _batch(False)
    finally:
        SV.FAST_POSE = was
    assert fast == ref
    assert any(s[0] != 'nofire' for s in ref)         # the batch genuinely fired cuts


def test_cross_hint_bitexact():
    """Threading a neighbour's cross as the fixpoint seed changes nothing in the results."""
    was = SV.FAST_POSE
    try:
        SV.FAST_POSE = True
        ref = _batch(False)
        hinted = _batch(True)
    finally:
        SV.FAST_POSE = was
    assert hinted == ref
