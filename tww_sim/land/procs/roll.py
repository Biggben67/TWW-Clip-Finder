#!/usr/bin/env python3
"""_RollMixin: the A-button forward roll (FRONT_ROLL).

procFrontRoll_init/procFrontRoll (d_a_player_main.cpp 6817/6851): speed set once from the pre-roll
speedF, constant-momentum coast timed by the ANM_ROLLF frame ctrl, two exits (anim-complete /
pushed-stick early-turn). The roll->cut ("roll stab") hand-off lives in _roll_exit -> _CutMixin.
"""
from __future__ import annotations
from ...core.mathlib import f32
from ..constants import FRONT_ROLL, MOVE, CUT_A, CUT_F, _dist_angle_s


class _RollMixin:
    # --- roll (procFrontRoll_init 6817 / procFrontRoll 6851) -------------------------------
    def _roll_init(self):
        """A-button forward roll entry. Speed is set ONCE from the pre-roll speedF (true_speed):
        clamp(speedF*1.5 + 0.5, 5.0, cap) where cap = 0.5 + mMaxNormalSpeed*1.5 = 26. Facing snaps
        to the stick target (shape_angle.y = m34E8, set by the caller when moving), and travel
        follows facing (current.angle.y = shape_angle.y, 6837). Anim frame ctrl starts at 0."""
        v = f32(f32(self.speedF * self.ROLL_SPD) + self.ROLL_ADD)
        if v < self.ROLL_MIN:
            v = f32(self.ROLL_MIN)
        else:
            cap = f32(self.ROLL_ADD + f32(self.MAX_NSPEED * self.ROLL_SPD))
            if v > cap:
                v = cap
        self.nspeed = v
        self.facing = self.target                # shape_angle.y = m34E8 (already snapped when moving)
        self.travel = self.facing                # current.angle.y = shape_angle.y (6837)
        # m3570 latch (6838): a roll STARTED already wall-hit facing the wall (within
        # mRoll.field_0x4) disables the mid-roll crash -- it grinds instead of bonking.
        self._roll_m3570 = not (
            self.wall_cir_hit[0]
            and _dist_angle_s((self.travel + 0x8000) & 0xFFFF, self.wall_angle[0])
            <= self.ROLL_BONK_ANGLE)
        self.state = FRONT_ROLL
        self.roll_frame = 0.0
        self._roll_entered = True
        # setSingleMoveAnime(ANM_ROLLF, ...): the foot engine poses rollf through the roll (m34C3=0)
        # so the toe stream is warm for the post-roll walk tail. morf = mRoll.field_0x14 = 2.0.
        if self._foot is not None:
            self._foot.enter_roll(morf=self.ROLL_ENTRY_MORF)

    def _proc_roll(self, l_held):
        """One FRONT_ROLL frame (procFrontRoll 6851): speed is constant momentum (position uses
        speedF = mNormalSpeed, NO foot-plant), the ANM_ROLLF frame ctrl advances at ROLL_RATE from 0.
        Two exits: (a) the anim completes (getRate()<0.01, frame reaches ROLL_END) -> if the stick is
        neutral, mNormalSpeed -= field_0x20 (the 26->21 drop, 6862), then checkNextMode(0); (b) with a
        PUSHED stick the getFrame()>field_0x10 early-turn fires checkNextMode(1) one frame sooner (no
        -field_0x20), routing to ATN_MOVE while L is held -- the roll-EBS that catches the full 26
        before the decel. checkNextMode picks the next proc (ATN if L else MOVE). Entry frame: no advance."""
        if self._roll_entered:                   # entry frame: ctrl stays at 0, no exit check
            self._roll_entered = False
            return
        self.roll_frame = f32(self.roll_frame + self.ROLL_RATE)
        if self.roll_frame >= self.ROLL_END:     # getRate()<0.01: anim complete
            if self.msd <= 0.05:
                self.nspeed = f32(self.nspeed - self.ROLL_MIN)
            self._roll_exit(l_held)
        elif self.roll_frame > self.ROLL_EARLY and (self.msd > 0.05 or (self._b_trig and self.sword_drawn)):
            # getFrame()>field_0x10 -> checkNextMode(1) (procFrontRoll 6866); inert only when neutral AND no
            # action -- a pushed stick (roll-EBS) or a B RISING EDGE (swordTrigger; a HELD B is not an edge) fires it.
            self._roll_exit(l_held)
        elif (self.speedF >= self.ROLL_BONK_SPEED and self._roll_m3570
              and self.wall_hit and self.wall_cir_hit[0]
              and _dist_angle_s((self.travel + 0x8000) & 0xFFFF, self.wall_angle[0])
              <= self.ROLL_BONK_ANGLE
              and self.ROLL_BONK_FMIN <= self.roll_frame <= self.ROLL_BONK_FMAX):
            # The roll bonk (6869): a mid-roll head-on wall hit (last frame's CrrPos flags)
            # at speedF >= 10 inside frames [6, 15] crashes -- procFrontRollCrash_init.
            self._crash_init()

    def _roll_exit(self, l_held):
        """The roll's checkNextMode transition. With a buffered sword button (B) and the sword drawn it
        routes to a CUT (the "roll stab": L held -> CUT_A vertical slash, else CUT_F forward thrust),
        carrying the roll's full speedF into the cut's first-frame lunge. Otherwise -> ATN_MOVE if L
        held (procAtnMove_init), else MOVE (procMove_init) with the walk re-entry morf; the walk blend
        re-inits its frame ctrl to 0 because the roll left m34C3==0 (see enter_roll)."""
        if self._b_trig and self.sword_drawn:
            # swordTrigger() || m34C5 (checkNextActionFromButton 4203): the B RISING EDGE this frame dispatches
            # changeCutProc. aim = mProcVar2.m34D4 = sVar2 (changeCutProc): the stick target m34E8 when pushed & unlocked,
            # else shape_angle.y. A diagonal stick at the thrust rotates the cut tail (see _cut_init).
            aim = self.target if (self.msd > 0.05 and not l_held) else self.facing
            self._cut_init(CUT_A if l_held else CUT_F, aim=aim)
            return
        self._check_next_mode(l_held)            # sets state (MOVE/ATN_MOVE) + mMaxNormalSpeed
        if self.state == MOVE and self._foot is not None:
            self._foot._pending_morf = self.MOVE_REENTRY_MORF
