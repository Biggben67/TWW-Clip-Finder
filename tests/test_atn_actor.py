#!/usr/bin/env python3
"""Offline invariants for the ATN_ACTOR path (procs 8/9) + the attention lock-on state machine.

The Courtyard Tetra-push untarget brakeslide: a roll exits into ATN_ACTOR_MOVE (proc 9) while the
lock-on reticle is still fading out after L-release, and setSpeedAndAngleAtnActor's DIR_BACKWARD
negation flips the roll's +26 to a backward slide -- retaining ~-25.7 EBS instead of the plain roll's
-23.5. These gate the MECHANIC decomp-faithfully; full 0-ULP position validation vs a clean live
free-run capture is the follow-on (the single-stepped fixture's per-frame position deltas are
jitter-corrupted, so it is scalar-ground-truth only).
See knowledge/mechanics/attention-lock-lifetime.md.
"""
from tww_sim.land.attention import AttentionLock, NONE, LOCK, RELEASE
from tww_sim.land.state import LandState
from tww_sim.land.constants import (FRONT_ROLL, ATN_ACTOR_MOVE, ATN_ACTOR_WAIT, ATN_MOVE, MOVE, WAIT)
from tww_sim.core.mathlib import s16_signed, cM_atan2s


def _mk(**kw):
    s = LandState(native=False, use_anim=False)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# --- AttentionLock state machine (dAttention_c hold mode) ----------------------------------------
def test_attention_lock_acquire_release_fade():
    a = AttentionLock(fade_frames=2)
    assert a.state == NONE and not a.locked
    a.update(l_held=True, target_present=True)          # L rising + target -> LOCK
    assert a.state == LOCK and a.locked
    a.update(l_held=True, target_present=True)          # held -> stays LOCK
    assert a.state == LOCK
    a.update(l_held=False, target_present=True)         # released -> RELEASE, fade starts
    assert a.state == RELEASE and a.locked              # still "locked" (LockonTruth) during the fade
    a.update(l_held=False, target_present=True)         # fade tick, still holding
    assert a.state == RELEASE and a.locked
    a.update(l_held=False, target_present=True)         # fade complete -> NONE
    assert a.state == NONE and not a.locked


def test_attention_lock_relock_during_release():
    a = AttentionLock(fade_frames=5)
    a.update(True, True)                                # LOCK
    a.update(False, True)                               # RELEASE (fade)
    assert a.state == RELEASE
    a.update(True, True)                                # L re-pressed mid-fade -> re-LOCK
    assert a.state == LOCK and a.locked


def test_attention_lock_target_loss():
    a = AttentionLock(fade_frames=5)
    a.update(True, True)                                # LOCK
    a.update(True, False)                               # target gone while locked -> NONE
    assert a.state == NONE and not a.locked


def test_release_survives_leaving_the_front_cone_but_lock_does_not():
    """The two gates are DIFFERENT, and conflating them cost the tier-2 gate frames 68-70 (session 57).

    `chaseAttention` -- and with it `check_flontofplayer`'s front cone -- is consulted by NONE
    (acquire, d_attention.cpp:810) and by LOCK (`judgementLostCheck`, 816). RELEASE (835-841) does
    NOT: it tests `LockonTarget(0) == NULL || !AttnFlag_40000000`, i.e. the FROZEN list entry plus the
    reticle-fade flag. So a target that swings out of the cone mid-fade keeps driving the ATN_ACTOR
    procs until the fade runs out -- which is exactly what the console's second untarget brakeslide
    does -- while the same target leaving the cone while still LOCKed drops it that frame."""
    a = AttentionLock(fade_frames=4)
    a.update(True, True)                                # LOCK
    a.update(False, True)                               # -> RELEASE, fade armed
    for _ in range(3):                                  # cone lost, but the entry still exists
        a.update(False, target_present=False, target_exists=True)
        assert a.state == RELEASE and a.locked, "the front cone must not end RELEASE"
    a.update(False, target_present=False, target_exists=True)
    assert a.state == NONE and not a.locked, "the fade running out is what ends RELEASE"

    b = AttentionLock(fade_frames=4)                    # ... and the LOCK gate DOES watch the cone
    b.update(True, True)
    b.update(True, target_present=False, target_exists=True)
    assert b.state == NONE, "judgementLostCheck must still drop a LOCK on the cone"

    c = AttentionLock(fade_frames=4)                    # a DELETED target still ends RELEASE at once
    c.update(True, True)
    c.update(False, True)
    c.update(False, target_present=True, target_exists=False)
    assert c.state == NONE and not c.locked


def test_attention_lock_inert_without_target():
    """No lock-on target ever presented -> the machine can never leave NONE (so `locked` stays False
    and every single-actor land path is byte-identical). This is the additive-safety guarantee."""
    a = AttentionLock()
    for _ in range(50):
        a.update(l_held=True, target_present=False)
        assert a.state == NONE and not a.locked


# --- checkNextMode roll-exit routing -------------------------------------------------------------
def test_roll_exit_routes_to_atn_actor_when_locked():
    s = _mk(state=FRONT_ROLL, nspeed=26.0)
    s._atn_actor_pos = (100.0, 0.0)
    s._atn.state = LOCK
    s._check_next_mode(l_held=False)                    # L already released, reticle still holds the lock
    assert s.state == ATN_ACTOR_MOVE                    # proc 9 (moving), not proc 6/7


def test_roll_exit_atn_actor_wait_when_stopped():
    s = _mk(state=FRONT_ROLL, nspeed=0.0)
    s._atn_actor_pos = (100.0, 0.0)
    s._atn.state = LOCK
    s._check_next_mode(l_held=False)
    assert s.state == ATN_ACTOR_WAIT                    # proc 8 (|speed| ~ 0)


def test_roll_exit_unchanged_without_actor():
    """No locked actor -> the routing is exactly as before: neutral exit -> MOVE, L-held -> ATN_MOVE."""
    s = _mk(state=FRONT_ROLL, nspeed=26.0)
    s._check_next_mode(l_held=False)
    assert s.state == MOVE
    s2 = _mk(state=FRONT_ROLL, nspeed=26.0)
    s2._check_next_mode(l_held=True)
    assert s2.state == ATN_MOVE                         # attention, no actor -> proc 7 (never proc 9)


# --- setSpeedAndAngleAtnActor physics (the untarget brakeslide) ----------------------------------
def _flip(msd, max_nspeed=12.0):
    s = _mk(state=ATN_ACTOR_MOVE, nspeed=26.0, speedF=26.0)
    s.pos_x, s.pos_z = 0.0, 0.0
    s.travel = 0x2000
    s.facing = 0x2000
    s.target = (0x2000 + 0x8000) & 0xFFFF               # slight-backward stick (ESS-down) -> DIR_BACKWARD
    s.msd = msd
    s._atn_actor_pos = (0.0, 100.0)                     # actor straight ahead (+z): bearing 0
    s._atn.state = LOCK                                 # re-aim requires mpAttnActorLockOn != NULL (2627)
    s.max_nspeed = max_nspeed
    before_facing = s.facing
    s._set_speed_and_angle_atn_actor()
    return s, before_facing


def test_untarget_negation_flip():
    """A backward stick fires the DIR_BACKWARD negation: +26 flips to a backward slide, travel turns
    EXACTLY 0x8000, and facing re-aims at the locked actor (setShapeAngleToAtnActor). All exact."""
    s, bf = _flip(0.5)
    assert s.nspeed < 0.0                               # +26 flipped to a backward slide (sign exact)
    assert s16_signed(s.travel - 0x2000) == -0x8000     # travel reversed exactly 180 deg
    # facing chased from 0x2000 toward the actor bearing (0) by the scale-2 step (0x2000-0)/2 = 0x1000.
    assert bf == 0x2000 and cM_atan2s(0.0, 100.0) == 0
    assert s.facing == 0x1000


def test_untarget_flip_model_regression():
    """BIT-EXACT (0-ULP) regression lock on the ATN_ACTOR flip physics for FIXED SYNTHETIC inputs --
    it catches unintended model drift, and asserts the qualitative tech (smaller stick retains more of
    the roll speed, monotone). It is NOT a live validation: the inputs are synthetic, so these are the
    MODEL's own deterministic outputs, NOT the live -25.727. The live 0-ULP gate (exact per-frame live
    inputs + a clean free-run capture) is a SEPARATE, still-PENDING milestone -- see the handoff."""
    small, _ = _flip(0.056)
    big, _ = _flip(0.5)
    assert small.nspeed == -25.719999313354492          # exact f32 (0 ULP vs the pinned model output)
    assert big.nspeed == -23.5                          # exact f32
    assert small.nspeed < big.nspeed                    # smaller stick -> more of the roll speed retained


def test_chase_attention_front_cone():
    """chaseAttention's front-of-player cone gate (`_atn_target_present`, check_flontofplayer): the
    lock-on actor is only chaseable within +-0x4000 (90 deg) of shape_angle.y. This is why the
    Courtyard lock acquires MID-ROLL (Tetra swings into the front cone) and never at the first held L
    (she is ~122 deg behind Link at state 2)."""
    s = _mk(facing=0)
    s.pos_x, s.pos_z = 0.0, 0.0
    assert s._atn_target_present() is False              # no actor driven -> inert (goldens)
    s._atn_actor_pos = (0.0, 100.0)                      # straight ahead (bearing 0) -> in cone
    assert s._atn_target_present() is True
    s._atn_actor_pos = (100.0, 0.0)                      # exactly 90 deg to the side (0x4000) -> in cone (<=)
    assert s._atn_target_present() is True
    s._atn_actor_pos = (10.0, -100.0)                    # behind (~174 deg) -> out of cone
    assert s._atn_target_present() is False
    s._atn_actor_pos = (100.0, -10.0)                    # ~96 deg behind the side -> out of cone
    assert s._atn_target_present() is False
    # the force override (bare non-coupled replay injects the known acquisition)
    s._atn_force_present = True
    assert s._atn_target_present() is True               # behind actor, but forced present
    s._atn_force_present = False
    s._atn_actor_pos = (0.0, 100.0)
    assert s._atn_target_present() is False              # in cone, but forced absent


def test_atn_actor_reaim_noop_without_actor_pos():
    """With no locked-actor position the re-aim is a no-op (mpAttnActorLockOn == NULL guard)."""
    s = _mk(state=ATN_ACTOR_MOVE, nspeed=5.0, facing=0x1234)
    s.msd = 0.0                                          # neutral: only the re-aim would move facing
    s._atn_actor_pos = None
    s._set_speed_and_angle_atn_actor()
    assert s.facing == 0x1234                            # facing untouched


# --- end-to-end additive safety: a real roll-EBS never enters proc 8/9 without an actor ----------
def test_no_actor_stepping_never_enters_atn_actor():
    s = LandState(native=False, use_anim=False)
    # Drive several frames of L-held slide input; without a lock-on actor the attention machine stays
    # NONE and the proc never becomes ATN_ACTOR_*.
    for _ in range(30):
        s.step(sx=128, sy=40, buttons=0x40, triggerL=200, csx=128, csy=128)   # stick back + L held
        assert s.state not in (ATN_ACTOR_MOVE, ATN_ACTOR_WAIT)
        assert s._atn.state == NONE
