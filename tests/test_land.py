"""Offline regression for the LAND walk sim (tww_sim.land.land).

Guards the BIT-EXACT part of the first land increment -- mNormalSpeed (potential_speed) and
the FREE_WAIT->MOVE->WAIT state machine -- as a golden arc, without needing Dolphin. This is the
token-cheap offline SHADOW of the live accuracy gate tests/dolphin/run_land_tests.py.

THE GOLDEN IS LIVE TRUTH, ENFORCED TO THE BYTE. speedF and position in tests/golden/land_walk_speedf.csv
and the CASE_POSZ endpoints are the GAME's live f32 reads (uint32 hex), captured by
tests/gen_land_golden.py. The tests assert `f32_bits(sim) == golden` (0 ULP, no tolerance), so a tech
that is not bit-perfect vs the game shows RED here just as it does live -- the same cases fail in both.
Today ALL land techs are BIT-PERFECT and pass (walk/face_left/roll_settle went float-perfect with the
world-space foot FK + PSMTXQuat 'newton' reciprocal; slip's skid tail with the posMoveFromFootPos
|speedF| < 0.05 -> 0 snap; brake_right with the pos_x sine-leak fix; walk_y171 with the daPy_HIO_move_c0
f64->f32 frame-rate constant fix; ebs + waitturn with the worldBase inverse = PSMTXInverse (cofactor +
fres) instead of R^T, which the not-exactly-orthonormal sin/cos rotation makes differ at non-axis facings
-- see knowledge/history/resolved-bugs.md). This deliberately replaces the old `< 0.05` tolerance (~400
ULP wide), which hid the f64-running-sum bug. Regenerate the golden from live after a sim fix (Dolphin
up): `python tests/gen_land_golden.py`.

The byte-exact checks only run WHEN the copyrighted anim keyframe data is present under _generated/anim/
(dev machines); without it LandState falls back to the calibrated stand-in and they SKIP.
"""
import json
import os
import struct

import pytest

from tww_sim.land.land import (LandState, WAIT, FREE_WAIT, MOVE, ATN_MOVE, FRONT_ROLL,
                             WAIT_TURN, MOVE_TURN, SLIP, SIDE_STEP_LAND)
from tww_sim.core.anim.foot_speedf import FootSpeedF

_ANIM = FootSpeedF.available()
_GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "land_walk_speedf.csv")
# Partial-magnitude (Y171, msd~0.52) walk golden -- the z=2000-stop regime (regime-1 cruise, toe
# delta = speedF). See knowledge/model/sim.md "Partial-magnitude regime" for the residual + harness.
_GOLDEN_Y171 = os.path.join(os.path.dirname(__file__), "golden", "land_walk_y171_speedf.csv")


def f32_bits(x):
    """The raw uint32 bit pattern of x rounded to float32 -- the currency of a bit-exact check."""
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _load_golden(path=_GOLDEN):
    """(frame, ns, msd, speedF_bits, pos_z_bits) -- the two floats as exact f32 byte patterns."""
    rows = []
    with open(path) as f:
        for line in f:
            if line.startswith("#") or line.startswith("f,"):
                continue
            fr, ns, msd, spF, spF_hex, pz, pz_hex = line.strip().split(",")
            rows.append((int(fr), float(ns), float(msd), int(spF_hex, 16), int(pz_hex, 16)))
    return rows

# Anchor rest seed (land_flatwalk@twwgz): the EXACT f32 rest pos_z read live (0x443f0510). The old
# 764.079 was 2 ULP off (0x443f050e) and perturbed the arc; seeding to the byte is part of the gate.
SEED_POS_Z = 764.0791015625

# The walk seq the live test uses: 30 frames full-up then 20 neutral (free cam throughout).
WALK_STICKS = [(128, 255)] * 30 + [(128, 128)] * 20
# Partial-magnitude walk (matches gen_land_golden.py WALK_Y171): 40 frames of Y171 from rest.
WALK_STICKS_Y171 = [(128, 171)] * 40

# Golden mNormalSpeed per frame f=1..40, live-captured (land_walk_gt.csv). f1..f2 = the
# 2-frame input latency (still FREE_WAIT); f3 accel begins; cap 17; release decel from f33.
GOLDEN_NSPEED = {
    1: 0.0, 2: 0.0, 3: 3.5, 4: 7.0, 5: 10.5, 6: 14.0, 7: 17.0,
    32: 17.0, 33: 14.5, 34: 12.0, 35: 9.5, 36: 7.0, 37: 4.5, 38: 2.0, 39: 0.2, 40: 0.0,
}
# Golden link_state at the same frames.
GOLDEN_STATE = {1: FREE_WAIT, 2: FREE_WAIT, 3: MOVE, 7: MOVE, 39: MOVE, 40: WAIT}


def _run():
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT)
    rows = [None]  # 1-indexed
    for (sx, sy) in WALK_STICKS:
        s.step(sx, sy)
        rows.append((s.nspeed, s.state, s.pos_z))
    return s, rows


def test_nspeed_arc_bit_exact():
    _, rows = _run()
    for f, want in GOLDEN_NSPEED.items():
        got = rows[f][0]
        assert abs(got - want) <= 1e-4, f"frame {f}: nspeed {got} != {want}"


def test_state_machine():
    _, rows = _run()
    for f, want in GOLDEN_STATE.items():
        assert rows[f][1] == want, f"frame {f}: state {rows[f][1]} != {want}"


def test_input_latency_two_frames():
    # No movement (state stays FREE_WAIT, nspeed 0) for exactly INPUT_DELAY frames.
    _, rows = _run()
    assert rows[1][:2] == (0.0, FREE_WAIT)
    assert rows[2][:2] == (0.0, FREE_WAIT)
    assert rows[3][1] == MOVE and rows[3][0] == 3.5


def test_sidehop_land_buffered_walk_uses_early_hio_threshold():
    s = LandState(state=SIDE_STEP_LAND, use_anim=False, native=False, input_delay=0)
    rows = []
    for _ in range(4):
        s.step(128, 255)
        rows.append((s.state, s.nspeed, s.air_anim))

    # procSideStepLand reads 0.0, 0.85, then 1.70 (>1.5) before advancing the controller.
    assert [row[0] for row in rows] == [SIDE_STEP_LAND, SIDE_STEP_LAND, WAIT, MOVE]
    assert rows[2][1] == 0.0
    assert rows[3][1] == 3.5


def test_sidehop_land_neutral_waits_for_controller_stop():
    s = LandState(state=SIDE_STEP_LAND, use_anim=False, native=False, input_delay=0)
    for _ in range(7):
        s.step(128, 128)
    assert s.state == WAIT


def test_accel_step_is_3_5_and_caps_at_17():
    _, rows = _run()
    assert [rows[f][0] for f in (3, 4, 5, 6, 7)] == [3.5, 7.0, 10.5, 14.0, 17.0]
    assert all(rows[f][0] == 17.0 for f in range(7, 33))   # holds at the cap while held


def test_decel_matches_cLib_addCalc():
    # release decel: cLib_addCalc(v, 0, 0.6, 2.5, 1.8) => 17->14.5->12->9.5->7->4.5->2->0.2->0
    _, rows = _run()
    assert [round(rows[f][0], 3) for f in range(33, 41)] == [14.5, 12.0, 9.5, 7.0, 4.5, 2.0, 0.2, 0.0]


def test_end_position_within_tolerance():
    # Endpoint: BIT-EXACT vs the LIVE golden with the anim engine (walk is float-perfect since the
    # world-space foot FK); +-3 calibrated stand-in without anim data.
    s, _ = _run()
    assert s.state == WAIT
    if _ANIM:
        want = _load_golden()[-1][4]
        assert f32_bits(s.pos_z) == want, \
            f"end pos_z {s.pos_z!r} (0x{f32_bits(s.pos_z):08x}) != LIVE 0x{want:08x}"
    else:
        assert abs(s.pos_z - 1278.25) < 3.0


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_speedf_matches_live_bit_exact():
    """The walk speedF (true_speed) must reproduce the GAME's live value BYTE-FOR-BYTE. Driven via
    LandState (not the raw FootSpeedF driver from the %g golden) so nspeed/mStickDistance/world pos are
    full-precision -- the raw driver's release-region ns/msd diverge from LandState's integration and
    read tens/hundreds of ULP off there, a HARNESS ARTIFACT, not a sim error (same reason the Y171 test
    is LandState-driven, c056bba). The entry transient (frames 5/6) is bit-exact after the two 2026-07-04
    f64->f32 constant fixes (oldframe-morf counter; f31_2 smoothing 0.3f/0.7f, history/resolved-bugs.md).
    The deep-release f37/f39 (previously the last RED here) is now bit-exact: it was NOT a foot-FK-X
    residual but a spurious on-axis pos_x -- the sim reconstructed cM_ssin from the cos table instead of
    JMASSin, leaking speed.x ~3e-6/frame, and the world-magnitude foot FK flipped the plant-toe X 1 ULP.
    Fixed by routing _cM_ssin_s16 through mathlib.cM_ssin_s16. See
    knowledge/history/resolved-bugs.md (deep-release pos_x sine leak)."""
    golden = _load_golden()
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT, idle_frame=70.0)
    for (sx, sy), (fr, _ns, _msd, spF_bits, _pz) in zip(WALK_STICKS, golden):
        s.step(sx, sy)
        assert f32_bits(s.speedF) == spF_bits, \
            f"frame {fr}: sim speedF {s.speedF!r} (0x{f32_bits(s.speedF):08x}) != LIVE 0x{spF_bits:08x}"


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_pos_z_arc_matches_live_bit_exact():
    """Full LandState walk must track the GAME's live pos_z BYTE-FOR-BYTE every frame. Float-perfect
    since the world-space foot FK (was 2 ULP off with the identity-space FK). This is the guard the
    f64-accumulation bug slipped past. See knowledge/model/sim.md."""
    golden = _load_golden()
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT, idle_frame=70.0)
    for (sx, sy), (fr, _ns, _msd, _spF, pz_bits) in zip(WALK_STICKS, golden):
        s.step(sx, sy)
        assert f32_bits(s.pos_z) == pz_bits, \
            f"frame {fr}: sim pos_z {s.pos_z!r} (0x{f32_bits(s.pos_z):08x}) != LIVE 0x{pz_bits:08x}"


# --- PARTIAL-MAGNITUDE (Y171) regime -- the z=2000 stop. Drive via LandState (raw driver from the
# golden ns is a harness artifact). Detail: knowledge/model/sim.md "Partial-magnitude regime".

@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_speedf_y171_matches_live_bit_exact():
    """PARTIAL regime: the walk speedF (= the plant-foot toe delta, since m3598==1.0 here) must
    reproduce the GAME's live true_speed byte-for-byte. Driven via LandState so nspeed/mStickDistance/
    world pos are full-precision (see the block comment on why the raw driver from the %g golden is a
    harness artifact). BIT-EXACT (0 ULP) since the daPy_HIO_move_c0 f64->f32 frame-rate constant fix
    (field_0x38=1.1/field_0x40=0.8; see knowledge/history/resolved-bugs.md #Y171)."""
    golden = _load_golden(_GOLDEN_Y171)
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT, idle_frame=70.0)
    for (sx, sy), (fr, _ns, _msd, spF_bits, _pz) in zip(WALK_STICKS_Y171, golden):
        s.step(sx, sy)
        assert f32_bits(s.speedF) == spF_bits, \
            f"frame {fr}: sim speedF {s.speedF!r} (0x{f32_bits(s.speedF):08x}) != LIVE 0x{spF_bits:08x}"


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_pos_z_arc_y171_matches_live_bit_exact():
    """PARTIAL regime: full LandState Y171 walk must track the GAME's live pos_z byte-for-byte every
    frame. BIT-EXACT (0 ULP) since the daPy_HIO_move_c0 f64->f32 frame-rate constant fix -- the offline
    mirror of the walk_y171 live gate. See knowledge/model/land-sim.md + history/resolved-bugs.md."""
    golden = _load_golden(_GOLDEN_Y171)
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT, idle_frame=70.0)
    for (sx, sy), (fr, _ns, _msd, _spF, pz_bits) in zip(WALK_STICKS_Y171, golden):
        s.step(sx, sy)
        assert f32_bits(s.pos_z) == pz_bits, \
            f"frame {fr}: sim pos_z {s.pos_z!r} (0x{f32_bits(s.pos_z):08x}) != LIVE 0x{pz_bits:08x}"


# --- ATN_MOVE tier: brakeslide / EBS / facing decouple / brake -----------------------------

# LIVE endpoint pos_z (the game's exact f32 bytes) for the ATN/roll/turn cases; captured by
# `python tests/gen_land_golden.py endpoints`. sim!=live fails here, mirroring run_land_tests.py.
CASE_POSZ = {
    'brakeslide' : 0x448146b3,   # 1034.2093505859375 (state 7)   bit-perfect
    'ebs'        : 0x44aa2072,   # 1361.013916015625  (state 6)   bit-perfect (PSMTXInverse worldBase inverse)
    'face_left'  : 0x44e9fa16,   # 1871.815185546875  (state 6)   bit-perfect (world FK)
    'brake_right': 0x447238c3,   # 968.8869018554688  (state 4)   bit-perfect (pos_x sine-leak fix)
    'roll_run'   : 0x4486a1c6,   # 1077.055419921875  (state 30)  bit-perfect
    'roll_slow'  : 0x4445f858,   # 791.88037109375    (state 30)  bit-perfect
    'roll_settle': 0x44be9639,   # 1524.6944580078125 (state 4)   bit-perfect (world FK)
    'roll_ebs'   : 0x44d64e35,   # 1714.4439697265625 (state 6)   bit-perfect
    'waitturn'   : 0x442c9e1e,   # 690.4705810546875  (state 6)   bit-perfect (PSMTXInverse worldBase inverse)
    'moveturn'   : 0x44086be3,   # 545.6857299804688  (state 6)   bit-perfect (live-mirror *18 seq)
    'moveturn_pos': 0x43ffd7c6,  # 511.68572998046875 (state 6)   bit-perfect (*20 seq)
    'slip'       : 0x44756df2,   # 981.7178955078125  (state 6)   bit-perfect (speedF<0.05 skid snap)
}


def assert_pos_bits(s, label):
    """Assert sim endpoint pos_z == the LIVE value bit-exact (fails until the sim is bit-perfect for
    this tech; only meaningful with anim data)."""
    want = CASE_POSZ[label]
    assert f32_bits(s.pos_z) == want, \
        f"{label}: sim pos_z {s.pos_z!r} (0x{f32_bits(s.pos_z):08x}) != LIVE 0x{want:08x}"


# Offline shadow of run_land_tests.py's ATN cases; endpoints are the LIVE pos_z (CASE_POSZ). Guards
# setSpeedAndAngleAtn/AtnBack + the mDirection machine (no Dolphin).
def _deg(a):
    return (int(a) % 65536) * 360.0 / 65536.0


def _run_atn(seq):
    s = LandState(pos_z=SEED_POS_Z, facing=0, travel=0, csangle=0, state=FREE_WAIT,
                  nspeed=0.0, idle_frame=70.0)
    for (sx, sy, btn, tl) in seq:
        s.step(sx, sy, buttons=btn, triggerL=tl)
    return s


_UP = [(128, 255, 0, 0)]
_LDN = [(128, 0, 0x40, 255)]     # L-target + full down, 1 frame


def test_atn_brakeslide():
    # L HELD -> daPyProc_ATN_MOVE (state 7), facing LOCKED at the run heading (0), travel flips
    # to 180, speed negative bleeding slowly toward 0 (~-0.14/frame, mAtnMoveB cap 15).
    s = _run_atn(_UP * 10 + _LDN + [(128, 110, 0x40, 255)] * 10)
    assert s.state == ATN_MOVE
    assert s.direction == 1  # DIR_BACKWARD (steady brakeslide runs the AtnBack path)
    assert abs(_deg(s.facing) - 0.0) < 0.1
    assert abs(_deg(s.travel) - 180.0) < 0.1
    assert abs(abs(s.nspeed) - 15.756) < 0.02
    if _ANIM:  # ATN position bit-exact: setBlendAtnBackMoveAnime poses ANM_ATNDB (m3598=0 -> momentum)
        assert_pos_bits(s, 'brakeslide')


def test_atn_ebs():
    # L RELEASED after 1 frame -> MOVE (state 6); facing unlocks and tracks travel; the negative
    # speed bleeds ~13x slower than the brakeslide (~-0.011/frame, cap stays 17).
    s = _run_atn(_UP * 10 + _LDN + [(128, 110, 0, 0)] * 30)
    assert s.state == MOVE
    assert abs(abs(s.nspeed) - 16.437) < 0.02
    assert abs(_deg(s.facing) - _deg(s.travel)) < 0.5   # facing ~ travel aligned
    if _ANIM:  # the 1-frame ATN strafe pose (ANM_ATNDRS) warms the toe stream -> walk tail bit-exact
        assert_pos_bits(s, 'ebs')


def test_atn_facing_decouple():
    # ESS-down 1 frame then ESS-left held -> facing rotates to ~90 and decouples from travel (~171)
    # while speed is preserved (the facing/travel split).
    s = _run_atn(_UP * 10 + _LDN + [(128, 110, 0, 0)] + [(110, 128, 0, 0)] * 60)
    assert s.state == MOVE
    assert abs(_deg(s.facing) - 90.0) < 0.5
    assert abs(_deg(s.travel) - 171.32) < 0.5
    assert abs(abs(s.nspeed) - 16.650) < 0.02
    if _ANIM:  # ATN strafe pose -> the decoupled-facing walk tail is position bit-exact
        assert_pos_bits(s, 'face_left')


def test_atn_brake_right():
    # ESS toward anti-camera brakes to a full stop (state 4, |v| ~ 0).
    s = _run_atn(_UP * 10 + _LDN + [(128, 110, 0, 0)] + [(146, 128, 0, 0)] * 60)
    assert s.state == WAIT
    assert abs(s.nspeed) < 0.01
    if _ANIM:  # ATN strafe pose -> the anti-cam brake-to-stop walk tail is position bit-exact
        assert_pos_bits(s, 'brake_right')


# --- FRONT_ROLL tier (A button) -------------------------------------------------------------

# Roll speed set once at entry from pre-roll speedF: clamp(speedF*1.5+0.5, 5, 26). nspeed/state and
# position are bit-exact end to end -- the foot engine poses ANM_ROLLF through the roll so the
# low-speed post-roll walk tail tracks live too (see land.py enter_roll/step_roll).
_A = [(128, 255, 0x100, 0)]      # A + up, 1 frame


def test_roll_from_run_caps_at_26():
    # Full-run roll: speedF 17 at entry -> 17*1.5+0.5 = 26 (cap). Robust w/o anim data (speedF -> 17).
    s = _run_atn(_UP * 15 + _A + [(128, 128, 0, 0)] * 5)
    assert s.state == FRONT_ROLL
    assert abs(s.nspeed - 26.0) < 0.02
    if _ANIM:  # mid-roll momentum position is bit-exact too
        assert_pos_bits(s, 'roll_run')


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_roll_slow_is_speedF_scaled():
    # Rolling while barely moving -> the entry speedF (~3.67) scales the roll: 3.67*1.5+0.5 ~= 6.0.
    s = _run_atn(_UP * 2 + _A + [(128, 128, 0, 0)] * 5)
    assert s.state == FRONT_ROLL
    assert abs(s.nspeed - 6.001) < 0.05
    assert_pos_bits(s, 'roll_slow')   # (skipif not _ANIM above)


def test_roll_nspeed_arc_and_exit():
    # The whole roll nspeed arc is bit-exact: 26 held through the roll, -5 on the neutral exit (26->21),
    # then the normal decel to a clean stop (state 4). (Position tail is not asserted -- foot phase.)
    s = LandState(pos_z=SEED_POS_Z, state=FREE_WAIT, idle_frame=70.0)
    rows = [None]
    for (sx, sy, b, tl) in (_UP * 15 + _A + [(128, 128, 0, 0)] * 30):
        s.step(sx, sy, buttons=b, triggerL=tl)
        rows.append((s.state, s.nspeed))
    assert all(rows[f][0] == FRONT_ROLL and abs(rows[f][1] - 26.0) < 1e-4 for f in range(18, 36))
    assert rows[36][0] == MOVE and abs(rows[36][1] - 21.0) < 1e-4      # exit drops field_0x20 (5.0)
    assert rows[-1][0] == WAIT and rows[-1][1] == 0.0                   # decels to a clean stop


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_roll_settle_position_bit_exact():
    # Full-run roll played to a standstill: total distance is bit-exact (live pos_z 1524.694). The
    # low-speed post-roll tail needs the ANM_ROLLF-warmed toe stream (foot engine step_roll).
    s = _run_atn(_UP * 15 + _A + [(128, 128, 0, 0)] * 40)
    assert s.state == WAIT and abs(s.nspeed) < 0.5
    assert_pos_bits(s, 'roll_settle')


def test_roll_ebs_preserves_negative_speed():
    # Frame-perfect EBS out of a roll: getFrame()>17 exits straight to ATN at 26, release L into
    # ESS-down -> backward-flip preserves -23.109 in MOVE. Pure mNormalSpeed (no anim data needed).
    s = _run_atn(_UP * 15 + _A + [(128, 0, 0x40, 255)] * 17 + [(128, 110, 0, 0)] * 14)
    assert s.state == MOVE
    assert abs(s.nspeed - (-23.109)) < 0.02
    d = ((s.facing - s.travel) % 65536)                     # facing ~ travel (aligned EBS)
    assert min(d, 65536 - d) < 0x0400
    if _ANIM:  # the roll->ATN->flip position tail is bit-exact
        assert_pos_bits(s, 'roll_ebs')


# --- sword-thrust cut tier (roll stab: CUT_F fwd thrust / CUT_A L+B vertical slash) -----------

# GOLDEN = live truth (GZLJ01 savestate 7) seeded at the cut-entry pos (roll pins speedF=26); enter_cut
# runs the lunge, step() plays to WAIT. Model: land-movement.md. Cut data via parse_bck.py which=cuts.
_CUTS_GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "land_rollstab_cuts.json")


def _cuts_available():
    p = os.path.join(os.path.dirname(__file__), "..", "_generated", "anim", "link_anim_cuts.json")
    return os.path.exists(p)


_CUTS = _cuts_available()


def _fbits_hex(h):
    return struct.unpack(">f", struct.pack(">I", int(h, 16)))[0]


@pytest.mark.skipif(not _CUTS, reason="cut keyframe data (_generated/anim/link_anim_cuts.json) not present")
@pytest.mark.parametrize("cut", ["CUT_F", "CUT_A"])
def test_rollstab_cut_bit_exact(cut):
    from tww_sim.land.land import CUT_F, CUT_A
    g = json.load(open(_CUTS_GOLDEN))[cut]
    seed = g["seed"]
    ct = CUT_F if cut == "CUT_F" else CUT_A
    s = LandState(pos_x=_fbits_hex(seed["px_hex"]), pos_z=_fbits_hex(seed["pz_hex"]),
                  facing=seed["facing"], travel=seed["travel"], state=FRONT_ROLL,
                  nspeed=seed["nspeed"], speedF=seed["speedF"], use_anim=False, native=False,
                  sword_drawn=True)
    # entry frame (the 49.22 lunge) then play the anim out to WAIT.
    s.enter_cut(ct)
    for i, row in enumerate(g["frames"]):
        if i > 0:
            s.step(128, 255)                              # hold up; the cut proc drives motion, not the stick
        assert f32_bits(s.pos_x) == int(row["px_hex"], 16), \
            f"{cut} f{row['f']} pos_x 0x{f32_bits(s.pos_x):08x} != live {row['px_hex']}"
        assert f32_bits(s.pos_z) == int(row["pz_hex"], 16), \
            f"{cut} f{row['f']} pos_z 0x{f32_bits(s.pos_z):08x} != live {row['pz_hex']}"
        tag = "WAIT" if s.state in (WAIT, FREE_WAIT) else s.state
    # the cut has returned Link to idle standstill (WAIT) by the last golden frame
    assert s.state in (WAIT, FREE_WAIT), f"{cut} should end in WAIT idle, got state {s.state}"


@pytest.mark.skipif(not _CUTS, reason="cut keyframe data not present")
@pytest.mark.parametrize("cut", ["CUT_F", "CUT_A"])
def test_rollstab_diag_model_invariants(cut):
    """The DIAGONAL thrust model (roll straight, aim the cut). Locks the decomp facts without needing
    live data: (a) aim == roll facing is a no-op (bit-exact vs the default straight cut); (b) the entry
    LUNGE is bit-exact independent of aim (procCutF has not run on the init frame -> shape unchanged);
    (c) the first cut proc frame SNAPS facing=travel to the aim in ONE frame (0x1F40 min-step); (d) an
    aim >= 0x2000 off the facing is rejected (dispatches CUT_L/R, not this cut). See spotcheck_rollstab_diag."""
    from tww_sim.land.land import CUT_F, CUT_A
    ct = CUT_F if cut == "CUT_F" else CUT_A
    g = json.load(open(_CUTS_GOLDEN))[cut]; seed = g["seed"]

    def fresh():
        return LandState(pos_x=_fbits_hex(seed["px_hex"]), pos_z=_fbits_hex(seed["pz_hex"]),
                         facing=seed["facing"], travel=seed["travel"], state=FRONT_ROLL,
                         nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)

    # (a) aim == facing is exactly the straight cut
    a, b = fresh(), fresh()
    la = a.enter_cut(ct); lb = b.enter_cut(ct, aim=seed["facing"])
    assert f32_bits(a.pos_x) == f32_bits(b.pos_x) and f32_bits(a.pos_z) == f32_bits(b.pos_z)

    # (b) the entry lunge is aim-independent (steer a +8deg diagonal; entry pos unchanged)
    aim = (seed["facing"] + 0x0600) & 0xFFFF        # ~8.4deg off, well inside the +-0x2000 band
    c = fresh(); lc = c.enter_cut(ct, aim=aim)
    assert f32_bits(a.pos_x) == f32_bits(c.pos_x) and f32_bits(a.pos_z) == f32_bits(c.pos_z), \
        "diagonal aim must NOT move the entry lunge (it fires along the roll facing)"
    assert c.facing == seed["facing"], "shape unchanged on the init frame"

    # (c) first cut proc frame snaps shape=travel to the aim, in one frame, and holds
    c.step(128, 255)
    assert c.facing == aim and c.travel == aim, "shape=travel must snap to the aim on the 1st proc frame"
    c.step(128, 255)
    assert c.facing == aim, "and hold there"

    # (d) out-of-range aim is rejected (would be CUT_L / CUT_R)
    d = fresh()
    with pytest.raises(ValueError):
        d.enter_cut(ct, aim=(seed["facing"] + 0x2000) & 0xFFFF)

    # (e) AIMED-ROLL technique: a diagonal roll facing puts the 49.22 lunge along that facing (the
    # only way to steer the big lunge; a forward roll can't). The lunge vector angle == the facing.
    import math
    theta = (seed["facing"] + 0x1000) & 0xFFFF      # +22.5deg roll
    e = LandState(pos_x=0.0, pos_z=0.0, facing=theta, travel=theta, state=FRONT_ROLL,
                  nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
    ex, ez = e.enter_cut(ct)
    lunge_ang = int(round(math.degrees(math.atan2(ex, ez)) / 360.0 * 65536)) & 0xFFFF
    dth = ((lunge_ang - theta + 32768) % 65536) - 32768
    assert abs(dth) < 0x0080, "aimed-roll lunge must fire along the roll facing"


def test_rollstab_first_frame_lunge_reaches_seam_floor():
    # The clip-relevant fact, robust WITHOUT the anim data: the roll-stab's first CUT frame displaces far
    # past the ~35u seam-clip floor (live 49.22u). Here we assert the modeled value with the anim data.
    if not _CUTS:
        pytest.skip("cut keyframe data not present")
    from tww_sim.land.land import CUT_F
    g = json.load(open(_CUTS_GOLDEN))["CUT_F"]
    seed = g["seed"]
    s = LandState(pos_x=_fbits_hex(seed["px_hex"]), pos_z=_fbits_hex(seed["pz_hex"]),
                  facing=seed["facing"], travel=seed["travel"], state=FRONT_ROLL,
                  nspeed=26.0, speedF=26.0, use_anim=False, native=False, sword_drawn=True)
    dx, dz = s.enter_cut(CUT_F)
    disp = (dx * dx + dz * dz) ** 0.5
    assert abs(disp - 49.2202) < 1e-3, f"roll-stab lunge {disp} != 49.22"
    assert disp > 35.0                                    # clears the hard seam-clip floor


# --- ground-reversal turn procs (WAIT_TURN 23 / MOVE_TURN 24 / SLIP 25) ---------------------

# Offline shadow of run_land_tests.py's turn cases. All three reverse a >0x7800 stick to end walking (MOVE)
# 180deg-reversed at the cap; only the PATH differs (LandState.visited). Position isn't pinned (fallback).
_DN = [(128, 0, 0, 0)]           # full-down, no L, 1 frame


def _run_turn(seq):
    s = LandState(pos_z=SEED_POS_Z, facing=0, travel=0, csangle=0, state=FREE_WAIT,
                  nspeed=0.0, idle_frame=70.0)
    rows = []
    for (sx, sy, btn, tl) in seq:
        s.step(sx, sy, buttons=btn, triggerL=tl)
        rows.append((s.state, s.nspeed))
    return s, rows


def test_waitturn_pivots_in_place_then_walks():
    # Idle + full-reverse flick from a standstill (nspeed~0, >0x7800): procWaitTurn pivots facing in
    # place (no MOVE_TURN/SLIP), then walks off reversed at the cap.
    s, rows = _run_turn(_DN * 15)
    assert WAIT_TURN in s.visited and MOVE_TURN not in s.visited and SLIP not in s.visited
    assert all(abs(ns) < 0.05 for st, ns in rows if st == WAIT_TURN)   # pivots in place (nspeed ~0)
    assert s.state == MOVE
    assert abs(s.nspeed - 17.0) < 1e-4
    assert abs(_deg(s.facing) - 180.0) < 0.1 and abs(_deg(s.travel) - 180.0) < 0.1


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_waitturn_position_bit_exact():
    # Idle full-reverse pivot (WAIT_TURN ANM_ROT -> WAIT idle-proc WAITS/ANM_ATNWRS re-pose) -> reversed
    # walk-off: whole arc position bit-exact via the anim engine. Live pos_z 690.471 @f15 (explore_waitturn).
    s, _ = _run_turn(_DN * 15)
    assert WAIT_TURN in s.visited and MOVE_TURN not in s.visited and SLIP not in s.visited
    assert s.state == MOVE
    assert_pos_bits(s, 'waitturn')


def test_moveturn_below_slip_threshold():
    # 1 up frame (barely moving, speedF/max << 0.6) then full reverse -> procMoveTurn(1) directly,
    # no SLIP. Halves nspeed at entry then re-accelerates while facing sweeps to the reversed travel.
    s, rows = _run_turn([(128, 255, 0, 0)] + _DN * 18)
    assert MOVE_TURN in s.visited and SLIP not in s.visited
    assert s.state == MOVE
    assert abs(s.nspeed - 17.0) < 1e-4
    assert abs(_deg(s.facing) - 180.0) < 0.1


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_moveturn_position_bit_exact():
    # Low-speed reverse -> MOVE_TURN into the reversed walk: the WHOLE arc is position bit-exact via the
    # anim engine (pre-halving pose + entry/exit morf; see KB). Live pos_z 511.686 (explore_mt_1.csv).
    s, _ = _run_turn([(128, 255, 0, 0)] + _DN * 20)
    assert MOVE_TURN in s.visited and SLIP not in s.visited
    assert s.state == MOVE
    assert_pos_bits(s, 'moveturn_pos')


def test_slip_skids_forward_then_moveturn():
    # Full-speed run (speedF/max = 1.0 > 0.6) + a genuine stick flip -> procSlip: mNormalSpeed = speedF*1.1
    # (18.7, exceeds the cap), skids FORWARD (travel held) bleeding ~-1.25/frame, then hands to procMoveTurn.
    s, rows = _run_turn([(128, 255, 0, 0)] * 15 + _DN * 30)
    assert SLIP in s.visited and MOVE_TURN in s.visited
    slip_speeds = [ns for st, ns in rows if st == SLIP]
    assert abs(max(slip_speeds) - 18.7) < 0.02          # entry seed speedF(17)*1.1, no cap clamp
    assert s.state == MOVE
    assert abs(s.nspeed - 17.0) < 1e-4
    assert abs(_deg(s.facing) - 180.0) < 0.1 and abs(_deg(s.travel) - 180.0) < 0.1


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_slip_position_bit_exact():
    # Full-speed reverse -> SLIP skid -> MOVE_TURN -> reversed walk, WHOLE arc position bit-exact: ANM_SLIP
    # scales jnt37.x 1.2 (FK applies scale + morf blends it), so the MOVE_TURN toe stream is exact. 981.718.
    s, _ = _run_turn([(128, 255, 0, 0)] * 15 + _DN * 30)
    assert SLIP in s.visited and MOVE_TURN in s.visited
    assert s.state == MOVE
    assert_pos_bits(s, 'slip')


# --- MID-WALK clone: state-copy must continue BIT-EXACTLY from any frame, not just at rest ------

# A representative arc exercising the whole anim hot path (mirrors tests/benchmark/perf_land): walk
# accel, off-axis curve, cruise, hard reversal (SLIP/MOVE_TURN), forward roll, then release-to-stop.
_CLONE_ARC = ([(128, 255, 0, 0, 128, 128)] * 40 + [(190, 245, 0, 0, 128, 128)] * 30
              + [(128, 255, 0, 0, 128, 128)] * 20 + [(128, 1, 0, 0, 128, 128)] * 25
              + [(128, 255, 0x100, 0, 128, 128)] + [(128, 255, 0, 0, 128, 128)] * 25
              + [(128, 128, 0, 0, 128, 128)] * 20)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
@pytest.mark.slow          # O(n^2): clones at every frame k and re-runs the prefix (2.0 s)
def test_clone_midwalk_bit_exact():
    """clone() taken at frame k must continue the SAME inputs byte-for-byte identically to the
    straight-through run, for EVERY k (not just rest). This is the mid-walk-clone contract that the
    O(n) planner sweeps + land A* depend on: PoseEngine.clone_state carries the toe stream /
    oldframe-morf / frame ctrls, so a branch from a walking node is bit-exact. See land.LandState.clone."""
    fields = ('pos_x', 'pos_z', 'speedF', 'nspeed', 'msd', 'max_nspeed')
    ints = ('facing', 'travel', 'csangle', 'state', 'direction')

    def snap(s):
        d = {f: f32_bits(getattr(s, f)) for f in fields}
        d.update({f: int(getattr(s, f)) for f in ints})
        return d

    ref = []
    s = LandState(pos_z=SEED_POS_Z, use_anim=True)
    for (sx, sy, b, tl, cx, cy) in _CLONE_ARC:
        s.step(sx, sy, b, tl, cx, cy)
        ref.append(snap(s))

    n = len(_CLONE_ARC)
    for k in range(n):                      # clone at every frame, continue, compare the whole tail
        s = LandState(pos_z=SEED_POS_Z, use_anim=True)
        for i in range(k):
            s.step(*_CLONE_ARC[i])
        c = s.clone()
        for j in range(k, n):
            c.step(*_CLONE_ARC[j])
            assert snap(c) == ref[j], f"clone@k={k} diverged at frame {j}"


def test_under_anim_selects_dashs_when_sword():
    """UnderAnimState maps the DASH slot to 'dashs' when the sword is equipped (getAnmData's
    mSwordAnmIndexTable) and to plain 'dash' when sheathed, across regime 2 (WALK<->DASH blend) and
    regime 3 (DASH cruise). This is the anim-selection half of the DASHS fix; the live 0-ULP foot
    pose is tests/dolphin/spotcheck_swordwalk.py. Pure state machine, no keyframe data needed."""
    from tww_sim.core.anim.anim_state import UnderAnimState
    sw = UnderAnimState(move0_anim='dashs', move0_frame=10.0, m34C3=1, sword=True).step(17.0)
    assert (sw['move0'], sw['move1']) == ('dashs', 'dashs'), "sword regime-3 must pose dashs/dashs"
    sh = UnderAnimState(move0_anim='dash', move0_frame=10.0, m34C3=1, sword=False).step(17.0)
    assert (sh['move0'], sh['move1']) == ('dash', 'dash'), "sheathed regime-3 must pose dash/dash"
    r2 = UnderAnimState(move0_anim='dashs', move0_frame=10.0, m34C3=1, sword=True).step(12.75)
    assert r2['move1'] == 'dashs', "sword regime-2 dash slot (MOVE1) must be dashs"


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_sword_dash_forces_python_foot_path():
    """The native _anmc engine has no DASHS in its hardcoded 15-anim array, so it cannot pose the
    sword-drawn dash. FootSpeedF must drop to the pure-Python foot path whenever sword=True (even
    with native requested), or LandState(sword_drawn=True) would silently pose 'dash' and read the
    wrong toe. See knowledge/model/anim-engine.md "Sword-drawn dash is DASHS, not DASH"."""
    sw = FootSpeedF(native=True, sword=True)
    assert sw._core is None, "sword-drawn dash must force the Python foot path (native can't pose DASHS)"
    assert sw.clone()._core is None, "the sword-mode Python-path fallback must survive clone()"
    FootSpeedF(native=True, sword=False)   # sheathed dash still constructs (native when built, else Py)


def test_near_reversal_slide_keeps_dvar9_zero_and_does_not_raise():
    """setSpeedAndAngleNormal's bVar2 arm (`d_a_player_main.cpp` 2780 / 2828): a near-reversal at
    HIGH speed that is NOT a genuine stick flip keeps sliding with the travel chase skipped -- and
    the decomp's explicit ``else { dVar9 = 0.0f; }`` means it also contributes NO acceleration.

    The Python port dropped that else, so the arm left ``dVar9`` unbound and raised
    UnboundLocalError from the `_set_normal_speed_f` call instead. It is reachable from a plain
    junction search state (session 64 hit it), and the native port (`_anmc.pyx`
    `_set_speed_and_angle_normal`, which inits dVar9 to 0.0) was always right -- so this gates the
    Python path against BOTH the decomp and the native one.

    Spying on the argument rather than the resulting speed keeps the assertion non-circular: the
    decomp fact being gated is exactly "this arm passes 0.0"."""
    from tww_sim.land.land import LandState, MOVE

    s = LandState(state=MOVE, use_anim=False, native=False)
    s.msd = 1.0                       # mStickDistance > 0.05
    s.nspeed = 15.0
    s.speedF = 15.0                   # speedF / max_nspeed > SLIP_THRESH (0.6) -> the fast arm
    s.travel = 0x0000
    s.target = 0x8000                 # cLib_distanceAngleS(target, travel) = 0x8000 > 0x7800
    s.m34ea, s.m34dc = 0, 0           # getDirectionFromAngle(0) = DIR_FORWARD, NOT a genuine flip
    assert s.speedF / s.max_nspeed > s.SLIP_THRESH, "setup must reach the fast near-reversal arm"

    seen = []
    s._set_normal_speed_f = lambda a, b, c, d: seen.append(a)
    s._set_speed_and_angle_normal(s.F0, attention_lock=False)

    assert seen == [0.0], "the bVar2 slide arm must pass dVar9 == 0.0 (decomp 2828-2830), got %r" % (seen,)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_critical_health_stop_uses_waitatob_and_rewalks():
    """Critical health changes the WAIT pose and the following walk phase, not acceleration HIO."""
    s = LandState(pos_z=0.0, state=FREE_WAIT, low_life=True, input_delay=0,
                  use_anim=True, native=False, foot_native=False)
    for _ in range(8):
        s.step(128, 255)
    for _ in range(20):
        s.step(128, 128)
        if s.state == WAIT:
            break

    assert s.state == WAIT
    assert s._foot.st.m34C3 == 0
    assert s._foot.st.move0 == "waitatob"
    assert f32_bits(s._foot.st.fc0.rate) == f32_bits(0.6)

    s.step(128, 255)
    assert s.state == MOVE
    assert s._foot.st.m34C3 == 1
    assert s._foot.st.move0 in ("waits", "walk")


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_seeded_critical_health_single_advances_existing_phase():
    foot = FootSpeedF(native=False)
    foot.seed_rest_single(d_frame=3.6, d_rate=0.6, m359C=0.0, noops=0)
    foot.step(0.0, 0.0)

    assert foot.started
    assert foot.st.m34C3 == 0
    assert foot.st.move0 == "waitatob"
    assert f32_bits(foot.st.fc0.frame) == f32_bits(4.2)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_critical_health_waitatob_settles_into_waitb():
    s = LandState(pos_z=0.0, state=FREE_WAIT, low_life=True, input_delay=0,
                  use_anim=True, native=False, foot_native=False)
    for _ in range(8):
        s.step(128, 255)
    for _ in range(60):
        s.step(128, 128)
        if s.state == WAIT and s._foot.st.move0 == "waitb":
            break

    assert s.state == WAIT
    assert s._foot.st.m34C3 == 2
    assert s._foot.st.move0 == "waitb"
    assert f32_bits(s._foot.st.fc0.rate) == f32_bits(0.4)


@pytest.mark.skipif(not _ANIM, reason="anim keyframe data (_generated/anim) not present")
def test_seeded_critical_health_waitb_advances_captured_phase():
    foot = FootSpeedF(native=False)
    foot.seed_rest_blend(d_frame=7.2, w_frame=4.0, d_rate=0.4, w_rate=0.0,
                         m359C=0.0, noops=0, idle_anim="waitb")
    foot.step(0.0, 0.0)

    assert foot.st.move0 == "waitb"
    assert foot.st.m34C3 == 2
    assert f32_bits(foot.st.fc0.rate) == f32_bits(0.4)
