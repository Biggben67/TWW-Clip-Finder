#!/usr/bin/env python3
"""_AtnMixin: the targeting-move (ATN_MOVE) speed/angle + direction state machine.

setSpeedAndAngleAtn dispatch (FORWARD reuses the Normal walk path; BACKWARD is the steady
brakeslide; side chases travel + snaps facing to the lock) and setBlendAtnMoveAnime's mDirection
update. The C-stick posY read for the C-up-freeze gate lives here too. Decomp: d_a_player_main.cpp.
"""
from __future__ import annotations
from ...core import mathlib as S
from ...core.mathlib import f32, cM_scos_s16, s16_signed
from ..constants import DIR_FORWARD, DIR_BACKWARD, DIR_LEFT, DIR_RIGHT, cLib_addCalcAngleS, _cM_ssin_s16


class _AtnMixin:
    def _cstick_posy(self, csx, csy):
        """Normalized C-stick posY (same cstick_normalize the yaw path uses): >0 up (subjective-view
        request, d_camera.cpp:1096), <0 down (0x2000 subject-exit, 4230). See camera_manual."""
        from ...core.camera import cam_bezier as CB
        return CB.cstick_normalize(int(csx), int(csy))[1]

    def _set_speed_and_angle_atn(self, attention_lock=True):
        """procAtnMove speed/angle. Branches on mDirection: FORWARD reuses the Normal walk path
        (with attention lock -> facing frozen); BACKWARD is the steady brakeslide (setSpeedAndAngleAtnBack,
        mAtnMoveB constants); the side branch chases travel toward the stick and snaps facing to the
        captured lock m34E6. The BACKWARD-flip (getDirectionFromCurrentAngle) reflects travel by 0x8000
        and negates mNormalSpeed so a backward slide is represented as a negative speed on a flipped
        heading -- the sign convention that makes the brake a slow positive accel toward 0. (2851)"""
        if self.direction == DIR_FORWARD:
            return self._set_speed_and_angle_normal(
                self.F0, attention_lock=attention_lock
            )
        if self.direction == DIR_BACKWARD:
            return self._set_speed_and_angle_atn_back()
        # side (DIR_LEFT / DIR_RIGHT)
        if self.msd > 0.05:
            if self._get_dir_from_angle(self.target - self.travel) == DIR_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = cLib_addCalcAngleS(self.travel, self.target, self.ATN_TURN_SCALE,
                                             self.ATN_TURN_MAX, self.ATN_TURN_MIN)
            fVar2 = f32(f32(self.ATN_SPD * self.msd) * cM_scos_s16(s16_signed(self.travel - old)))
        else:
            fVar2 = 0.0
        self.facing = self.m34E6                 # shape_angle.y = m34E6 (facing lock)
        self._set_normal_speed_f(fVar2, self.ATN_SCL, self.ATN_ACC, self.ATN_DEC)

    def _set_speed_and_angle_atn_back(self):
        """setSpeedAndAngleAtnBack (2882): the steady brakeslide. Same shape as the side branch
        but with the mAtnMoveB constants (cap 15, speed scale 2.5, cLib 0.5/8.0/2.0). Facing stays
        locked at m34E6; travel chases the (backward) stick target; the negative speed bleeds toward
        0 via the accel-inject branch of setNormalSpeedF (~-0.14/frame observed)."""
        if self.msd > 0.05:
            if self._get_dir_from_angle(self.target - self.travel) == DIR_BACKWARD:
                self.travel = (self.travel + 0x8000) & 0xFFFF
                self.nspeed = f32(self.nspeed * -1.0)
            old = self.travel
            self.travel = cLib_addCalcAngleS(self.travel, self.target, self.ATN_TURN_SCALE,
                                             self.ATN_TURN_MAX, self.ATN_TURN_MIN)
            f1 = f32(f32(self.ATNB_SPD * self.msd) * cM_scos_s16(s16_signed(self.travel - old)))
        else:
            f1 = 0.0
        self.facing = self.m34E6
        self._set_normal_speed_f(f1, self.ATNB_SCL, self.ATNB_ACC, self.ATNB_DEC)

    def _update_atn_direction(self):
        """setBlendAtnMoveAnime's mDirection state machine (3280), the flat subset.
        Runs AFTER checkNextMode each ATN frame (and at ATN entry) to pick next frame's direction
        from cos/sin(travel - facing): within ~8deg of facing -> FORWARD, of the opposite -> BACKWARD,
        else a side (sin sign). Also sets mMaxNormalSpeed for the chosen direction (17/15/12).

        The FORWARD/BACKWARD branch is gated on `mpAttnActorLockOn == NULL` (3299): with a live
        actor-lock the direction can only go to a SIDE, so the proc-9 untarget tier keeps posing the
        ATN{L,R} strafe family even while travel reads dead-ahead/behind (the courtyard f19-21 pose)."""
        iVar6 = s16_signed(self.travel - self.facing)   # current.angle.y - shape_angle.y
        f2 = _cM_ssin_s16(iVar6)
        fVar4 = S.cM_scos_s16(iVar6)
        uVar1 = self.direction
        atn = getattr(self, "_atn", None)
        locked_actor = atn is not None and atn.locked   # mpAttnActorLockOn != NULL
        if self.msd > 0.05:
            if not locked_actor and (fVar4 <= self.ATNB_COS_BACK or fVar4 >= self.ATNB_COS_FWD):
                self.direction = DIR_BACKWARD if fVar4 <= self.ATNB_COS_BACK else DIR_FORWARD
            else:
                if uVar1 in (DIR_BACKWARD, DIR_FORWARD):
                    self.direction = DIR_RIGHT
                    self.max_nspeed = self.ATN_MAX
                if f2 > 0.0:
                    self.direction = DIR_LEFT
                elif f2 < 0.0:
                    self.direction = DIR_RIGHT
        if self.direction == DIR_BACKWARD:
            self.max_nspeed = self.ATNB_MAX
        elif self.direction == DIR_FORWARD:
            self.max_nspeed = f32(self.MAX_NSPEED)
        elif self.direction not in (DIR_RIGHT, DIR_LEFT):
            self.direction = DIR_RIGHT
