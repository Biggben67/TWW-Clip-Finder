#!/usr/bin/env python3
"""_TurnMixin: the ground-reversal turn family (WAIT_TURN 23 / MOVE_TURN 24 / SLIP 25).

procWaitTurn (pivot in place from a standstill), procMoveTurn (turn-around reversal, low speed /
post-slip), procSlip (high-speed reversal skid that hands to MoveTurn). Decomp: d_a_player_main.cpp
6569/6584/6611/6632/6642/6658. The arbiter (_MoveMixin._check_next_mode) routes reversals here.
"""
from __future__ import annotations
from ...core.mathlib import f32, cLib_addCalc, s16_signed
from ..constants import WAIT_TURN, MOVE_TURN, SLIP, MOVE, cLib_addCalcAngleS


class _TurnMixin:
    # --- ground-reversal turn procs (WaitTurn 23 / MoveTurn 24 / Slip 25) ------------------
    def _proc_wait_turn_init(self):
        """procWaitTurn_init (6569): pivot in place. Capture the stick target (mProcVar2.m34D4 = m34E8)
        as the fixed pivot goal, snap travel onto facing (current.angle.y = shape_angle.y), reset the
        (ANM_ROT) anim. mNormalSpeed is already ~0. Position is frozen (speedF 0) through the pivot."""
        self.state = WAIT_TURN
        self.turn_target = self.target
        self.travel = self.facing
        # setSingleMoveAnime(ANM_ROT, mBasic.field_0x4, 0, -1, mBasic.field_0xC) (6574): pose the pivot
        # anim through WAIT_TURN so the toe stream is warm for the WAIT idle-proc re-pose + walk-off.
        if self._foot is not None:
            self._foot.enter_single('rot', self.MOVE_REENTRY_MORF, rate=self.WAIT_TURN_ANIM_RATE)

    def _proc_wait_turn(self, l_held):
        """procWaitTurn (6584): bleed mNormalSpeed toward 0, pivot facing toward the captured target at
        the mTurn rate (min step ~0x1F40 rules -> ~8000/frame), keep travel == facing. When the pivot
        residual reaches 0 -> checkNextMode(0): the stick is now aligned so it hands off to WAIT (then
        MOVE next frame). No translation while pivoting (speedF 0)."""
        self.nspeed = cLib_addCalc(self.nspeed, 0.0, self.F24, self.F1C, self.F20)
        self.facing = cLib_addCalcAngleS(self.facing, self.turn_target,
                                         self.TURN_SCALE, self.TURN_MAX, self.TURN_MIN)
        self.travel = self.facing
        if s16_signed(self.turn_target - self.facing) == 0:   # sVar1 == 0 (pivot complete)
            self._check_next_mode(l_held)

    def _proc_move_turn_init(self, param_1):
        """procMoveTurn_init (6611): set up the facing sweep. param_1!=0 (the 1 path, low-speed reversal):
        snap travel to the stick target (current.angle.y = m34E8), halve mNormalSpeed, sweep params
        (scale 2, max F0*4+0x4A56, min F0*2). param_1==0 (the slip-exit path): travel already flipped by
        procSlip; sweep params (scale 3, max F0*2, min F0). The body then re-accelerates while facing
        catches up to the (reversed) travel."""
        self.state = MOVE_TURN
        # procMoveTurn_init calls setBlendMoveAnime(mBasic.field_0xC) -> re-triggers the oldframe-morf
        # (same 2.4 as the roll->walk re-entry), so the walk blend re-warms from the pre-turn pose.
        if self._foot is not None:
            self._foot._pending_morf = self.MOVE_REENTRY_MORF
        if param_1 != 0:
            self.turn_shape_max = (self.F0 * 4 + 0x4A56) & 0xFFFF
            self.turn_shape_min = (self.F0 * 2) & 0xFFFF
            self.turn_shape_scale = 2
            self.travel = self.target
            # setBlendMoveAnime (6616) poses the walk anim at the PRE-halving speed; 6623 then halves
            # what posMoveFromFootPos integrates with (pose at _anim_nspeed, integrate at the halved).
            self._anim_nspeed = self.nspeed
            self.nspeed = f32(self.nspeed * 0.5)
        else:
            self.turn_shape_max = (self.F0 * 2) & 0xFFFF
            self.turn_shape_min = self.F0 & 0xFFFF
            self.turn_shape_scale = 3

    def _proc_move_turn(self, l_held):
        """procMoveTurn (6632): setSpeedAndAngleNormal re-accelerates along the (fixed) reversed travel
        (its reversal + facing-chase branches are both suppressed while mCurProc==MOVE_TURN), then sweep
        facing toward travel via cLib_addCalcAngleS(scale/max/min from init). checkNextMode keeps us in
        MOVE_TURN until facing == travel, then routes to MOVE. Position is walk-anim driven (fallback)."""
        self._set_speed_and_angle_normal(self.F0, attention_lock=l_held)
        self.facing = cLib_addCalcAngleS(self.facing, self.travel,
                                         self.turn_shape_scale, self.turn_shape_max, self.turn_shape_min)
        self._check_next_mode(l_held)
        # MOVE_TURN -> MOVE exit routes through procMove_init, which re-triggers the oldframe-morf
        # (setBlendMoveAnime(field_0xC), 6215) -- the walk re-warms from the turn's final pose.
        if self.state == MOVE and self._foot is not None:
            self._foot._pending_morf = self.MOVE_REENTRY_MORF

    def _proc_slip_init(self):
        """procSlip_init (6642): the skid seed. mNormalSpeed = speedF * mSlip.field_0x8 (1.1); field_0x0==0
        so no cap clamp -> the skid speed can exceed mMaxNormalSpeed (e.g. 17 -> 18.7). The skid is pure
        momentum (speedF == mNormalSpeed); ANM_SLIP is posed each frame to warm the toe stream, which feeds
        the MoveTurn walk tail bit-exact (ANM_SLIP scales jnt37 -> the FK now applies scale, see foot_fk)."""
        self.state = SLIP
        self.nspeed = f32(self.speedF * self.SLIP_ENTRY)
        # setSingleMoveAnime(ANM_SLIP, rate=mSlip.field_0xC, morf=mSlip.field_0x1C) (6646): pose the
        # skid anim through the slip so the toe stream is warm for the MoveTurn/walk tail.
        if self._foot is not None:
            self._foot.enter_single('slip', self.SLIP_MORF, rate=self.SLIP_ANIM_RATE)

    def _proc_slip(self, l_held):
        """procSlip (6658): bleed mNormalSpeed toward 0 at the mSlip decel (~-1.25/frame) while travel is
        held (skids FORWARD). When |mNormalSpeed| reaches ~0: with the stick still pushed, flip travel by
        0x8000, nudge facing +0x100, re-seed mNormalSpeed = mMaxNormalSpeed*0.5, and hand to procMoveTurn(0);
        with a neutral stick, checkNextMode(0). Flat/wall-free: the wall-hit branches are omitted."""
        self.nspeed = cLib_addCalc(self.nspeed, 0.0, self.SLIP_DEC_SCALE, self.SLIP_DEC_MAX, self.SLIP_DEC_MIN)
        if abs(self.nspeed) <= 0.001:                    # fabsf(0 - mNormalSpeed) <= 0.001 (6662)
            if self.msd > 0.05:
                self.travel = (self.facing + 0x8000) & 0xFFFF
                self.facing = (self.facing + 0x100) & 0xFFFF
                self.nspeed = f32(self.max_nspeed * self.MT_SLIP_SEED)
                self._proc_move_turn_init(0)
            else:
                self._check_next_mode(l_held)
