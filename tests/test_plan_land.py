"""Offline regression for the LAND input planner (tww_sim.land.plan_land) -- milestone 1.

Guards the geometry primitives (world bearing <-> full-deflection stick inverse) and the
STRAIGHT-WALK reach: given an init LandState + a world target (x, z), the produced input seq
brings Link to REST within tolerance of the target. Position is bit-exact with the ported foot
anim engine present (tight pins gated on it, like test_land.py); the loose reach bound always runs.

Anchor seed = land_flatwalk@twwgz (flat wall-free room, Link idle at pos_z 764.079, facing +z,
csangle 0) -- the same rest seed the live land tests use.
"""
import math
import struct

import pytest

from tww_sim.land.land import LandState, FREE_WAIT, WAIT
from tww_sim.land.plan_land import (world_angle_s16, stick_for_bearing, dist2d, reach_straight,
                                 reach_precise, reach_freeze)
from tww_sim.swim.sim import _deadzone
import math
from tww_sim.core.anim.foot_speedf import FootSpeedF

# Deselected by default: the reach_* planner sweeps are heavy searches (>90s pure-Python), not
# 0-ULP asserts. Run with `pytest -m slow`; see the slow-offline-tests memory (build native _anmc).
pytestmark = pytest.mark.slow

_ANIM = FootSpeedF.available()

SEED = dict(pos_z=764.079, pos_x=0.0, facing=0, travel=0, csangle=0, state=FREE_WAIT,
            nspeed=0.0, idle_frame=70.0)


def _seed():
    return LandState(**SEED)


# --- geometry primitives (no sim, no anim dep) ---------------------------------------------

def test_world_angle_s16_cardinals():
    # travel is s16 measured FROM +z TOWARD +x: 0 = +z, 0x4000 = +x, 0x8000 = -z, 0xC000 = -x.
    assert world_angle_s16(0, 100) == 0
    assert world_angle_s16(100, 0) == 0x4000
    assert world_angle_s16(0, -100) == 0x8000
    assert world_angle_s16(-100, 0) == 0xC000


def test_stick_for_bearing_cardinals():
    # With a frozen camera (csangle 0) the inverse-stick points the walk at the world bearing:
    # +z = full up, +x = full left, -z = full down (matches the anchor's facing/camera).
    assert stick_for_bearing(world_angle_s16(0, 100), 0) == (128, 255)
    assert stick_for_bearing(world_angle_s16(100, 0), 0) == (1, 128)
    assert stick_for_bearing(world_angle_s16(0, -100), 0) == (128, 1)


def test_stick_for_bearing_roundtrips_through_sim():
    # Feed the inverse-stick into the real stick layer and confirm the walk want-target m34E8
    # lands on the requested bearing (within one dead-zoned-stick quantum).
    for bearing_deg in (0, 30, 90, 150, 210, 300):
        th = int(round(bearing_deg / 360.0 * 65536.0)) & 0xFFFF
        sx, sy = stick_for_bearing(th, 0)
        s = _seed()
        s._set_stick_data(sx, sy)
        err = abs(((s.target - th + 32768) % 65536) - 32768)
        # dead-zone-corrected inverse -> bearing preserved to integer-stick rounding (~1 deg = 182 s16)
        assert err < 200, f"bearing {bearing_deg}: m34E8 {s.target} vs {th} (err {err})"


# --- straight-walk reach (bit-exact position gated on anim data) ----------------------------

def _reach_bound():
    # Whole-frame release granularity limits how close a walk-then-coast can rest to a target;
    # ~15u covers every probed case with the anim engine, looser without it.
    return 15.0 if _ANIM else 20.0


def test_reach_straight_ahead():
    # Target dead ahead (+z): pure full-up walk then coast to rest near it.
    s = _seed()
    r = reach_straight(s, 0.0, 1200.0)
    assert r['end'].state in (WAIT, FREE_WAIT)
    assert r['resting_dist'] < _reach_bound()
    assert abs(r['end'].pos_x) < 1.0                       # no lateral drift on a straight walk


def test_reach_far_straight_is_sub_unit():
    # A far straight target gives fine release positioning -> sub-unit resting distance.
    s = _seed()
    r = reach_straight(s, 0.0, 2000.0)
    assert r['end'].state in (WAIT, FREE_WAIT)
    if _ANIM:
        assert r['resting_dist'] < 1.0
    else:
        assert r['resting_dist'] < 5.0


@pytest.mark.parametrize("tx,tz", [(300.0, 1400.0), (600.0, 1400.0)])
def test_reach_angled_target(tx, tz):
    # Off-axis target: the live-bearing re-aim curves the main stick to home in (no orbit) and
    # rests within tolerance. Both axes land near the target.
    s = _seed()
    r = reach_straight(s, tx, tz)
    assert r['end'].state in (WAIT, FREE_WAIT)
    assert r['resting_dist'] < _reach_bound()
    assert dist2d(r['end'], tx, tz) == pytest.approx(r['resting_dist'])


# --- FLOAT-PERFECT reach via the C-up speed cancel (reach_freeze) ----------------------------

def _live_valid_stick(sx, sy):
    # Live-valid iff each axis is a <=63-from-center partial (Y<=191) or a true full corner (255/1/0);
    # the ambiguous 192-254 cap band diverges live. See knowledge/mechanics/land-movement.md.
    def axis_ok(v):
        return abs(v - 128) <= 63 or v in (255, 1, 0)
    return axis_ok(sx) and axis_ok(sy)


def test_reach_freeze_seq_live_valid_and_reproduces():
    # On-axis (+z corridor): every emitted stick is live-valid (the msd-0.5 crawl + the <=0.889/1.0
    # drill lattice), and re-simulating the whole seq reproduces the reported freeze position exactly.
    r = reach_freeze(_seed(), 0.0, 2000.0)
    assert all(_live_valid_stick(*st) for st in r['seq']), "non-live-valid stick in freeze plan"
    s = _seed()
    for st in r['seq']:
        s.step(*st)
    assert dist2d(s, 0.0, 2000.0) == pytest.approx(r['freeze_dist'], abs=1e-4)


@pytest.mark.parametrize("tz", [900.0, 1200.0, 2000.0, 3000.0])   # short / mid / lucky / long
def test_reach_freeze_robust_float_perfect(tz):
    # ROBUST float-perfect across the whole corridor (not just lucky targets): rest < 8 f32-ULP-near-tz
    # (~1e-3u), every stick live-valid, and the full seq re-simulates to the reported freeze.
    ulp = 2.0 ** (math.frexp(tz)[1] - 1 - 23)      # float32 ULP near tz
    r = reach_freeze(_seed(), 0.0, tz)
    assert all(_live_valid_stick(*st) for st in r['seq']), "non-live-valid stick in freeze plan"
    assert r['freeze_dist'] < 8 * ulp, "%.6fu = %.1f ULP" % (r['freeze_dist'], r['freeze_dist'] / ulp)
    s = _seed()
    for st in r['seq']:
        s.step(*st)
    assert dist2d(s, 0.0, tz) == pytest.approx(r['freeze_dist'], abs=1e-4)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_reach_freeze_beats_precise_rest():
    # The C-up freeze locks mid-motion, so it places the stop far finer than reach_precise's rest
    # (which itself is target-sensitive, 0.1-9u). On the open +z corridor the freeze rests < 0.001u.
    precise = reach_precise(_seed(), 0.0, 2000.0)
    freeze = reach_freeze(_seed(), 0.0, 2000.0)
    assert freeze['freeze_dist'] < precise['resting_dist']
    assert freeze['freeze_dist'] < 0.001


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_reach_freeze_min_frames_bit_exact_and_fewer():
    # The START-crawl fewest-frame freeze (min_frames=True): 0-ULP freeze, all sticks live-valid, the seq
    # re-simulates to the target, and it travels FEWER frames than robust reach_freeze. See land-planner.md.
    T = 2000.0
    r = reach_freeze(_seed(), 0.0, T, min_frames=True)
    assert _bits(r['freeze_pos'][1]) == _bits(T), "min_frames freeze not bit-exact: %r" % (r['freeze_pos'],)
    assert all(_live_valid_stick(*st) for st in r['seq']), "non-live-valid stick in min_frames plan"
    s = _seed()
    for st in r['seq']:
        s.step(*st)
    assert _bits(s.pos_z) == _bits(T), "min_frames seq re-sim %.6f != %.6f" % (s.pos_z, T)
    robust = reach_freeze(_seed(), 0.0, T)
    assert r['n_frames'] < robust['n_frames'], "min_frames (%d) not fewer than robust (%d)" % (
        r['n_frames'], robust['n_frames'])


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_reach_freeze_roll_bit_exact_and_beats_floor():
    # roll=True: rolls (26 u/frame) rest BELOW the walk floor, freeze bit-exact; seq carries A (3-tuples).
    # z=2222.2 hits at k<=3 (fast). See land-planner.md.
    T = 2222.2
    r = reach_freeze(_seed(), 0.0, T, roll=True, kmax=3)
    assert r is not None and 'rolls' in r, "roll freeze found no hit within k<=3"
    assert _bits(r['freeze_pos'][1]) == _bits(T), "roll freeze not bit-exact: %r" % (r['freeze_pos'],)
    assert all(_live_valid_stick(st[0], st[1]) for st in r['seq']), "non-live-valid stick in roll plan"
    assert any(len(st) > 2 and st[2] & 0x100 for st in r['seq']), "no A-press (roll) in the roll plan"
    # re-simulate the button-carrying seq -> reproduces the freeze bit-exactly
    s = _seed()
    for st in r['seq']:
        s.step(st[0], st[1], buttons=(st[2] if len(st) > 2 else 0))
    assert _bits(s.pos_z) == _bits(T), "roll seq re-sim %.6f != %.6f" % (s.pos_z, T)
    # rolls (25.6 u/frame) beat the pure full-up walk floor ((T - Z0)/17 at 17 u/frame)
    floor17 = (T - 764.079) / 17.0
    assert r['n_frames'] < floor17, "roll %d not below walk floor %.0f" % (r['n_frames'], floor17)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_reach_freeze_roll_densifier_lowers_k():
    # DENSIFIER (roll_speed_min < 26): full-only misses z=2049.404 at k<=3, but admitting partial-speed
    # TUNING rolls surfaces a bit-exact k<=3 hit -- the fast-solve knob. See land-planner.md (ROLL densifier).
    T = 2049.404
    full = reach_freeze(_seed(), 0.0, T, roll=True, kmax=3)
    assert full is None or 'rolls' not in full, "unexpected full-only k<=3 hit (test premise stale)"
    dense = reach_freeze(_seed(), 0.0, T, roll=True, kmax=3, roll_speed_min=10.0)
    assert dense is not None and 'rolls' in dense, "densifier found no k<=3 hit"
    assert dense.get('tuned') is True, "densifier k<=3 hit should use a partial tuning roll"
    assert _bits(dense['freeze_pos'][1]) == _bits(T), "densifier freeze not bit-exact: %r" % (
        dense['freeze_pos'],)
    assert all(_live_valid_stick(st[0], st[1]) for st in dense['seq']), "non-live-valid stick"
    # re-simulate the button-carrying seq -> reproduces the freeze bit-exactly
    s = _seed()
    for st in dense['seq']:
        s.step(st[0], st[1], buttons=(st[2] if len(st) > 2 else 0))
    assert _bits(s.pos_z) == _bits(T), "densifier seq re-sim %.6f != %.6f" % (s.pos_z, T)


# --- SUBJECTIVITY freeze -> B-cancel -> re-walk-from-rest (the chained-freeze tech) --------------
def _bits(x):
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


# Live-verified (0 ULP, gate_subj_live.py) pos_z bits: the coarse freeze, then the carried-phase
# re-walk (2 frozen input-latency frames first). Mechanics: knowledge/mechanics/land-movement.md.
_FREEZE_BITS = 1150042034   # 1121.990479
_REWALK_BITS = [1150042034, 1150042034, 1150043226, 1150053054, 1150083308, 1150166309, 1150305573]


def _run_subjectivity_freeze(foot_native):
    s = LandState(native=foot_native, foot_native=foot_native, pos_z=764.0791015625, facing=0,
                  travel=0, csangle=0, state=FREE_WAIT, nspeed=0.0, idle_frame=70.0)
    for _ in range(22):
        s.step(128, 255)                  # cruise to full speed
    s.step(128, 255)                      # halfL (re-issues the last approach stick)
    for _ in range(3):
        s.step(128, 128)                  # C-up cancel decel frames (cup0..cup2)
    s.enter_freeze()                      # procSubjectivity_init: freeze + WAITS/WALK blend
    freeze = _bits(s.pos_z)
    for _ in range(8):
        s.hold_freeze()                   # subj + post-B WAIT (position frozen, WAITS advances)
    held = _bits(s.pos_z)
    s.resume_walk()                       # WAIT -> MOVE, carried phase
    walk = [(_bits(s.step(128, 255)[0]), _bits(s.pos_z))[1] for _ in range(len(_REWALK_BITS))]
    return freeze, held, walk


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
@pytest.mark.parametrize("foot_native", [False, True])   # pure-Python AND fused native LandCore
def test_subjectivity_freeze_rewalk_bit_exact(foot_native):
    # Coarse freeze -> hold -> re-walk with the CARRIED anim phase (m34C3=2). Both the pure-Python foot
    # path and the fused native LandCore must reproduce the live-proven pos_z bits (see land-movement.md).
    freeze, held, walk = _run_subjectivity_freeze(foot_native)
    assert freeze == _FREEZE_BITS, hex(freeze)
    assert held == _FREEZE_BITS, hex(held)      # position stays locked through the hold
    assert walk == _REWALK_BITS, [hex(w) for w in walk]
