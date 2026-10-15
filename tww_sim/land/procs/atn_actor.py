#!/usr/bin/env python3
"""_AtnActorMixin: the actor-lock targeting move (ATN_ACTOR_MOVE / ATN_ACTOR_WAIT, procs 9 / 8).

``setSpeedAndAngleAtnActor`` (d_a_player_main.cpp:2909) is ``setSpeedAndAngleAtn``'s side branch --
same ``mAtnMove`` speed/angle chase and the same DIR_BACKWARD negation gate -- with two differences:
it has NO forward/backward ``mDirection`` dispatch (procs 8/9 ALWAYS run this actor path), and
instead of locking facing to ``m34E6`` it re-aims ``shape_angle.y`` at the locked actor every frame
(``setShapeAngleToAtnActor``, 2625). Facing the actor keeps ``getDirectionFromCurrentAngle()`` reading
DIR_BACKWARD while sliding away from it, so the negation branch (2913: ``travel += 0x8000;
mNormalSpeed *= -1``) stays engaged -- that is the roll's +26 flipping to ~-26 (the untarget
brakeslide), then decaying with the gentle ``mAtnMove`` params instead of eating the roll's -5.0 decel.

The locked actor's world XZ is supplied by the harness as ``self._atn_actor_pos`` (Tetra, from the
coupled stepper). With none set the re-aim no-ops (``mpAttnActorLockOn == NULL`` guard), so this mixin
is inert unless a lock-on actor is actively driven. KB: mechanics/attention-lock-lifetime.md.
"""
from __future__ import annotations
from ...core import mathlib as S
from ...core.mathlib import f32, cM_scos_s16, s16_signed
from ..constants import DIR_BACKWARD, cLib_addCalcAngleS
from ..attention import FRONT_CONE_HALF

# setShapeAngleToAtnActor's cLib_addCalcAngleS knobs (2629): chase shape_angle.y toward the bearing
# to the actor's eyePos at scale 2, maxStep 0x2000, minStep 0x800. Not HIO -- hard-coded in the decomp.
_SHAPE_SCALE, _SHAPE_MAX, _SHAPE_MIN = 2, 0x2000, 0x800


class _AtnActorMixin:
    def _atn_target_present(self):
        """chaseAttention's per-frame "is the lock-on actor chaseable" gate (d_attention.cpp:563),
        reduced to the binding constraint for the Courtyard push: the actor exists AND is inside the
        front-of-player cone (`check_flontofplayer`, |bearing - shape_angle.y| <= FRONT_CONE_HALF).
        Returns False with no driven actor (`_atn_actor_pos` None) -> the AttentionLock stays NONE, so
        every single-actor land path (goldens) is byte-identical. The bearing is the SAME
        cM_atan2s(actor.x - pos.x, actor.z - pos.z) the re-aim (setShapeAngleToAtnActor) uses."""
        forced = getattr(self, "_atn_force_present", None)
        if forced is not None:                   # bare non-coupled replay: inject the known acquisition
            return bool(forced)
        ap = getattr(self, "_atn_actor_pos", None)
        if ap is None:
            return False
        bearing = S.cM_atan2s(f32(ap[0] - self.pos_x), f32(ap[1] - self.pos_z))
        return abs(s16_signed((bearing - self.facing) & 0xFFFF)) <= FRONT_CONE_HALF

    def _atn_target_exists(self):
        """``LockonTarget(0) != NULL`` -- the LOCKED list entry, which the front cone has no say over
        (d_attention.cpp:836; `stockAttention` cannot re-make the list outside NONE). This is the
        RELEASE-branch gate, deliberately weaker than `_atn_target_present`: a driven actor that
        leaves the cone mid-fade keeps the lock until the reticle anim ends. False with no driven
        actor at all, so the goldens' NONE-forever behaviour is untouched."""
        if getattr(self, "_atn_force_present", None) is not None:
            return bool(self._atn_force_present)
        return getattr(self, "_atn_actor_pos", None) is not None

    def _check_rest_hp_anime(self):
        """``checkRestHPAnime`` (d_a_player_main.cpp:5618) -- "play the low-life idle set".

        Two halves. The LIFE half (``dComIfGs_getLife() <= mMove.field_0xE``, 6 quarter-hearts) is
        not simulated, so it is the seeded `low_life` flag. The half that VARIES inside a run is
        the actor lock: the check requires ``mpAttnActorLockOn == NULL``, so the same low-life Link
        takes the ordinary idle blend while a lock-on is live and the WAITATOB single once it drops.
        (``checkNoUpperAnime`` / ``checkPlayerGuard`` / demo / ship-mode are the remaining terms;
        none of them is modeled and none is reachable on the flat free-walk tier.)

        Only the WAIT proc consults this -- see `wait-stop-pose.md`. Healthy (the default) keeps
        every anchor and golden on the pre-existing path."""
        return bool(getattr(self, 'low_life', False)) and not self._atn.locked

    def _set_shape_angle_to_atn_actor(self):
        """setShapeAngleToAtnActor (2625): chase shape_angle.y toward the bearing to the locked
        actor's EYE position (cLib_targetAngleY(current.pos, mpAttnActorLockOn->eyePos)). No-op while
        `mpAttnActorLockOn == NULL` (2627) -- the proc-9 body can still run one frame past the lock
        drop (the courtyard body2 frame) and must NOT re-aim there (live facing holds bit-for-bit).

        The eye XZ is `self._atn_actor_eye` when driven (Tetra's eyePos = her ANIMATED head-joint
        world pos, d_a_npc_zl1.cpp:1283 -- it leads her feet 16-26 u and wobbles with her look-at
        anim, so aiming at the feet lands the chase short; live-pinned session 15,
        `_notes/tetrapush-eyepos_probe.py`: feet-aim 37364 vs eye-aim 37548 == live at the courtyard
        f20). Falls back to the feet `_atn_actor_pos` when no eye stream is injected."""
        atn = getattr(self, "_atn", None)
        if atn is None or not atn.locked:        # mpAttnActorLockOn == NULL -> no re-aim
            return
        ap = getattr(self, "_atn_actor_eye", None)
        if ap is None:
            ap = getattr(self, "_atn_actor_pos", None)
        if ap is None:
            return
        target_angle = S.cM_atan2s(f32(ap[0] - self.pos_x), f32(ap[1] - self.pos_z))
        self.facing = cLib_addCalcAngleS(self.facing, target_angle, _SHAPE_SCALE, _SHAPE_MAX, _SHAPE_MIN)

    def _set_speed_and_angle_atn_actor(self):
        """setSpeedAndAngleAtnActor (2909): the ATN side-branch chase with the mAtnMove family, no
        mDirection split, re-aiming facing at the actor. The DIR_BACKWARD negation (travel += 0x8000,
        nspeed *= -1) flips a forward carry (the +26 out of a roll) to a backward slide toward 0."""
        if self.msd > 0.05:
            if self._get_dir_from_angle(self.target - self.travel) == DIR_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = cLib_addCalcAngleS(self.travel, self.target, self.ATN_TURN_SCALE,
                                             self.ATN_TURN_MAX, self.ATN_TURN_MIN)
            f1 = f32(f32(self.ATN_SPD * self.msd) * cM_scos_s16(s16_signed(self.travel - old)))
        else:
            f1 = 0.0
        self._set_shape_angle_to_atn_actor()     # shape_angle.y re-aims at the actor (NOT the m34E6 lock)
        self._set_normal_speed_f(f1, self.ATN_SCL, self.ATN_ACC, self.ATN_DEC)
