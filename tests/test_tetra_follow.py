#!/usr/bin/env python3
"""Phase-C regression: Tetra's FOLLOW model is bit-exact live, + her lock-on/talk avoid region.

Fixture = fixtures/hyrule_tetra_follow.json -- a live capture (flooded Hyrule, savestate slot 3;
harness/rollstab/capture_tetra_follow.py) of the type-5 following Tetra chasing a stationary Link
back from a teleported far spot: idle -> turn-to-face -> accelerate (1 u/f) -> distance-capped
cruise -> decelerate -> stop at ~130. This replays `tww_sim.core.npc_zl1.Zl1FollowState` frame by
frame against that capture and asserts 0-ULP on position / facing / speedF / action-state.

Seed offset: the capture's frame 0 is the raw post-teleport write and frame 1 is identical to it
(the game's actor logic hasn't acted on the teleport yet -- the one-frame post-write settle, like
the documented first-post-load transient). The follow logic first runs on frame 1->2, so the gate
seeds from frame 1 and replays 1->N. Link is stationary here, so the read-lag is not exercised (a
moving-Link capture would pin it, like the foot 1-frame lag) -- that is a follow-up, noted in the
handoff. If a sim change breaks the follow integrator this goes RED at the first diverging frame.

The attention tests pin the L-target / talk / speak AVOID region a planner must respect
(dist_table[0xAB]: XZ < 300, |dy| < 300, Link facing within +-90 deg of Tetra) at its exact
decomp boundaries.
"""
import json
import os

from tww_sim.core.npc_zl1 import (Zl1FollowState, zl1_attention_active,
                                   ATTN_XZ_MAX, ATTN_FRONT_HALF_ANGLE, WALL_R, WALL_H)
from tww_sim.core.collision import acch_crr_pos
from tww_sim.land.walls import load_ordered_mesh

_rb = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(_rb, 'fixtures', 'hyrule_tetra_follow.json')
WALLS_FIX = os.path.join(_rb, 'fixtures', 'hyrule_tetra_walls_ordered.json')
WC_FIX = os.path.join(_rb, 'fixtures', 'hyrule_tetra_wallcorrect.json')


def _fix():
    with open(FIX) as f:
        return json.load(f)


def _ang_diff(a, b):
    return ((a - b + 32768) % 65536) - 32768


def test_follow_bitexact_vs_live():
    fix = _fix()
    assert fix['stage'] == 'Hyrule' and fix['tetra_type'] == 5
    rows = fix['frames']
    gy = fix['ground_y']
    s = rows[1]['tetra']                       # seed from frame 1 (post-teleport settle)
    sim = Zl1FollowState(s['pos'][0], s['pos'][1], s['pos'][2],
                         s['angle_y'], s['speedF'], rows[1]['tetra_stt'])
    assert len(rows) > 60, 'capture too short to exercise engage->cruise->stop'
    for i in range(2, len(rows)):
        sim.step(rows[i]['link']['pos'], ground_y=gy)
        t = rows[i]['tetra']
        assert sim.x == t['pos'][0], (i, 'x', sim.x, t['pos'][0])
        assert sim.z == t['pos'][2], (i, 'z', sim.z, t['pos'][2])
        assert _ang_diff(sim.angle_y, t['angle_y']) == 0, (i, 'angle', sim.angle_y, t['angle_y'])
        assert sim.speedF == t['speedF'], (i, 'speedF', sim.speedF, t['speedF'])
        assert sim.stt == rows[i]['tetra_stt'], (i, 'stt', sim.stt, rows[i]['tetra_stt'])


def test_follow_exercises_full_cycle():
    """The capture must actually cover engage (stt 3->4), the speed cap, and stop (4->3) -- else
    a bit-exact replay proves little."""
    rows = _fix()['frames']
    stts = [r['tetra_stt'] for r in rows]
    speeds = [r['tetra']['speedF'] for r in rows]
    assert 3 in stts and 4 in stts, 'capture never engaged/idled'
    assert stts[-1] == 3, 'capture did not settle back to idle'
    assert max(speeds) > 9.0, 'capture never reached the distance-scaled speed plateau'


def test_wallcorrect_bitexact_vs_live():
    """Her BG WallCorrect (mObjAcch.CrrPos, R=50/half-H=30) ejects her from a corner-wall overlap
    to the exact live position -- the wall-brace MECHANIC (a wedged Tetra's CC recoil is canceled so
    she holds in place). Whether corner-bracing helps the clip is a separate, open question (it pushes
    the wrong way; see the rollstab README ## Status). Fixture from capture_tetra_wallcorrect.py; on
    the flat floor/water she floats with speed.y == 0 (live), so the pass runs speed_y = 0."""
    wc = json.load(open(WC_FIX))
    walls = load_ordered_mesh(WALLS_FIX)
    pos, info = acch_crr_pos(tuple(wc['old']), tuple(wc['new']), walls,
                             speed_y=0.0, wall_h=WALL_H, wall_r=WALL_R)
    assert info['wall_hit'] is True
    assert pos[0] == wc['ejected'][0], ('x', pos[0], wc['ejected'][0])
    assert pos[2] == wc['ejected'][2], ('z', pos[2], wc['ejected'][2])


def test_attention_region_boundaries():
    """L-target / talk / speak eligibility at the exact dist_table[0xAB] boundaries."""
    # Link at origin facing +Z (s16 0 -> cM_atan2s convention: +Z is angle 0), Tetra straight ahead.
    assert zl1_attention_active((0.0, 0.0, 0.0), 0, (0.0, 0.0, ATTN_XZ_MAX - 1.0)) is True
    assert zl1_attention_active((0.0, 0.0, 0.0), 0, (0.0, 0.0, ATTN_XZ_MAX + 1.0)) is False
    # Facing exactly away (180 deg) -> outside the +-90 front cone.
    assert zl1_attention_active((0.0, 0.0, 0.0), 0x8000, (0.0, 0.0, 100.0)) is False
    # Front cone edge (0x4000 = 90 deg): just-inside active, just-outside rejected.
    assert zl1_attention_active((0.0, 0.0, 0.0), ATTN_FRONT_HALF_ANGLE - 0x400, (0.0, 0.0, 100.0)) is True
    assert zl1_attention_active((0.0, 0.0, 0.0), ATTN_FRONT_HALF_ANGLE + 0x400, (0.0, 0.0, 100.0)) is False
    # Y gate: Tetra 400 u above (attention adds 140) -> |dy| >= 300 -> not active despite XZ<300.
    assert zl1_attention_active((0.0, 0.0, 0.0), 0, (0.0, 400.0, 100.0)) is False
