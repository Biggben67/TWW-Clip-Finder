#!/usr/bin/env python3
"""_CrashMixin: the roll bonk (FRONT_ROLL_CRASH).

procFrontRollCrash_init/procFrontRollCrash (d_a_player_main.cpp 6891/6914): a mid-roll wall hit
(see _RollMixin's trigger) reverses travel, launches Link airborne backward (speed.y = 7, the
reversed momentum at 0.4x), freezes the ANM_ROLLFMIS pose at frame 6 until the landing, then
plays it out at 0.7/frame to the WAIT/MOVE exit. Positions through the crash are pure momentum
(m3598 == 0), so they are exact without the ROLLFMIS keyframes; the toe stream is NOT warmed
(rollfmis is absent from the anim dump), so a post-crash WALK's blend frames are a flagged gap
-- same class as the late-roll drawn poses (README Status).
"""
from __future__ import annotations
from ...core.mathlib import f32
from ..constants import FRONT_ROLL_CRASH


class _CrashMixin:
    def _crash_init(self):
        """procFrontRollCrash_init (6891): mNormalSpeed = speedF*0.4, speed.y = 7, travel
        reversed (current.angle.y += 0x8000; shape/facing unchanged -- Link flies backward).
        setSingleMoveAnime(ANM_ROLLFMIS, rate=0.0, start=6.0, end=24, morf=1.0): the pose
        FREEZES at frame 6 while airborne; the landing sets the rate. commonProcInit resets
        gravity to the autoJump -2.5."""
        self.state = FRONT_ROLL_CRASH
        self.nspeed = f32(self.speedF * self.CRASH_SPEED_MUL)
        self.speed_y = f32(self.CRASH_VY)
        self.gravity = self.GRAVITY
        self.ground_y = f32(self.pos_y)
        self.travel = (self.travel + 0x8000) & 0xFFFF
        self.crash_frame = f32(self.CRASH_ANIM_START)
        self._crash_rate = 0.0
        self._crash_air = True                   # ModeFlg_MIDAIR until the landing frame
        self._crash_entered = True

    def _proc_crash(self, l_held):
        """One FRONT_ROLL_CRASH frame (procFrontRollCrash 6914). Airborne: no exits, pose
        frozen. Landing (last frame's CrrPos ground hit while MIDAIR): mNormalSpeed = 0,
        anim rate = 0.7 (mRoll.field_0x24), MIDAIR off. Grounded: the anim plays 6 -> 24;
        frame > 20 (field_0x30) fires checkNextMode(1) (stick/action-gated like the roll's
        early exit), the end clamp (rate < 0.01) fires checkNextMode(0) unconditionally."""
        if self._crash_entered:                  # init frame: ctrl was set after animeUpdate
            self._crash_entered = False
            return
        self.crash_frame = f32(self.crash_frame + self._crash_rate)
        if not self._crash_air:
            if self.crash_frame >= self.CRASH_ANIM_END:      # getRate() < 0.01
                self._crash_exit(l_held)
            elif self.crash_frame > self.CRASH_EARLY and (self.msd > 0.05 or self._b_trig):
                self._crash_exit(l_held)
        if self.ground_hit and self._crash_air:  # mAcch.ChkGroundHit() && MIDAIR (6924)
            self.nspeed = 0.0
            self._crash_rate = self.CRASH_ANIM_RATE          # setRate(mRoll.field_0x24)
            self._crash_air = False

    def _crash_exit(self, l_held):
        from ..constants import MOVE
        self._check_next_mode(l_held)
        if self.state == MOVE and self._foot is not None:
            self._foot._pending_morf = self.MOVE_REENTRY_MORF
