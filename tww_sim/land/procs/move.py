#!/usr/bin/env python3
"""_MoveMixin: the shared ground-locomotion arbiter + normal-speed integrator.

setNormalSpeedF (accel/decel) + setSpeedAndAngleNormal (target speed + two-angle chase) +
getDirectionFromAngle + checkNextMode (the transition arbiter that routes reversals to the turn
procs). This is the base of LandState's MRO. Decomp: d_a_player_main.cpp procMove/checkNextMode.
"""
from __future__ import annotations
from ...core.mathlib import f32, cLib_addCalc, cM_scos_s16, s16_signed
from ..constants import (MOVE, MOVE_TURN, WAIT, FREE_WAIT, WAIT_TURN, ATN_MOVE,
                         ATN_ACTOR_MOVE, ATN_ACTOR_WAIT,
                         DIR_FORWARD, DIR_BACKWARD, DIR_LEFT, DIR_RIGHT, DIR_NONE,
                         cLib_addCalcAngleS, _is_zero, _dist_angle_s)


class _MoveMixin:
    # --- setNormalSpeedF (2301), walk path -------------------------------------------------
    def _set_normal_speed_f(self, param_1, param_2, param_3, param_4):
        """The accel/decel integrator. Flat ground => no event/heavy/grab (dVar10 =
        msd * (max*msd)), no slide polygon. dVar10 is the speed cap this frame; below it the
        cLib_addCalc chases up (param_1 injects the accel step directly), above it (release)
        it cLib-decays down. A wall hit (last frame's CrrPos flags, 2311) scales the cap by
        1 - cos(travel+0x8000 - wallAngleY)*0.6 when heading into the wall (|diff| < 0x4000)
        -- the wall-hold: a head-on walk targets 0.4x. Inert without a walls mesh."""
        dVar10 = f32(self.msd * f32(self.max_nspeed * self.msd))   # target/cap speed
        if self.wall_hit:
            uVar2 = 0
            for i in range(3):                  # first wall-hit cylinder's angle (2313)
                if self.wall_cir_hit[i]:
                    uVar2 = s16_signed((self.travel + 0x8000) - self.wall_angle[i])
                    break
            if abs(uVar2) < 0x4000:
                dVar10 = f32(dVar10 * f32(1.0 - f32(cM_scos_s16(uVar2) * self.WALL_SPEED_DOWN)))
        if dVar10 < self.nspeed:                # decelerating toward the (lower) cap
            temp_f0 = f32(self.nspeed - dVar10)
            temp_f3 = param_3 if temp_f0 > param_3 else temp_f0
            if temp_f3 < param_4:
                temp_f3 = param_4
            param_1 = 0.0
            dVar6 = dVar10
        else:
            temp_f3 = param_3
            dVar6 = 0.0
        if not _is_zero(param_1):               # accel: inject dVar9 straight in, clamp to cap
            self.nspeed = f32(self.nspeed + param_1)
            if self.nspeed > dVar10:
                self.nspeed = dVar10
        else:                                   # cLib chase toward dVar6 (0 on release)
            self.nspeed = cLib_addCalc(self.nspeed, dVar6, param_2, temp_f3, param_4)

    # --- setSpeedAndAngleNormal (2751), walk path ------------------------------------------
    def _set_speed_and_angle_normal(self, param_1, attention_lock=False):
        """Compute the target-speed scalar dVar9 from the stick + the facing/travel-vs-target
        angle, chase the two angles toward m34E8, then hand dVar9 to setNormalSpeedF. Walk
        path (+ the ATN DIR_FORWARD sub-case). The near-reversal branch (2763) and the facing
        chase (2834) are both guarded by !checkAttentionLock() in the decomp, so `attention_lock`
        (L held) suppresses them -- the ATN-forward call keeps facing frozen (set by the caller
        to m34E6) and never takes the reversal/slip branch. No MOVE_TURN/event/heavy/grab."""
        if self.msd > 0.05:
            bVar2 = False
            dVar11 = f32(self.msd * self.msd)
            # >0x7800 near-reversal branch (2763), skipped under attention lock or during MOVE_TURN.
            if (not attention_lock and _dist_angle_s(self.target, self.travel) > 0x7800
                    and self.state != MOVE_TURN):
                # ModeFlg_00000001 (WAIT/FREE_WAIT/WAIT_TURN): a reversal is INERT while idle -- return
                # with speed/angles untouched so checkNextMode sees the full reversal -> procWaitTurn (2766).
                if self.state in (WAIT, FREE_WAIT, WAIT_TURN):
                    return
                if self.state == MOVE:
                    sp_ratio = f32(self.speedF / self.max_nspeed)
                    # fast + a genuine stick flip -> leave everything for checkNextMode -> procSlip (2770).
                    if (sp_ratio > self.SLIP_THRESH
                            and self._get_dir_from_angle(s16_signed(self.m34ea - self.m34dc)) == DIR_BACKWARD):
                        return
                    # slow -> chase travel toward the reverse (dropping the dist below 0x7800) and
                    # return; checkNextMode then routes via the DIR_BACKWARD branch -> procMoveTurn (2775).
                    if sp_ratio <= self.SLIP_THRESH:
                        self.travel = cLib_addCalcAngleS(self.travel, self.target, self.F6, param_1, self.F4)
                        return
                    bVar2 = True             # fast + not a flip: skip the speed scale, keep sliding
                else:
                    self.travel = cLib_addCalcAngleS(self.travel, self.target, self.F6, param_1, self.F4)
            else:
                # sVar6/sVar7 are s16 = (f32 product) truncated (decomp 2792/2796): quantize before
                # int() -- an f64 product can truncate 1 unit off at a boundary, drifting the travel angle.
                sVar6 = int(f32(param_1 * dVar11))
                if sVar6 < 10:
                    sVar6 = 10
                sVar7 = int(f32(self.F4 * dVar11))
                if sVar7 < 1:
                    sVar7 = 1
                self.travel = cLib_addCalcAngleS(self.travel, self.target, self.F6, sVar6, sVar7)
            if not bVar2:
                dVar9 = cM_scos_s16(s16_signed(self.target - self.travel))
                if self.nspeed > f32(0.5 * self.max_nspeed):
                    if dVar9 < 0.7:
                        dVar9 = f32(0.7)
                elif dVar9 < 0.0:
                    dVar9 = 0.0
                dVar10 = f32(0.5 - f32(0.5 * abs(f32(self.nspeed / self.max_nspeed))))
                if self.msd > dVar10:
                    dVar9 = f32(dVar9 * f32(self.F14 * dVar11))
                else:
                    dVar9 = 0.0
            else:
                # the bVar2 slide arm (2828): keep sliding, with NO acceleration.
                dVar9 = 0.0
        else:
            dVar9 = 0.0
        # facing (shape_angle.y) chases m34E8 at DOUBLE travel's rate (<<1), snapping on if it crosses
        # travel. On-axis: no-op. Skipped under attention lock (facing frozen to m34E6) + in MOVE_TURN. (2834)
        if not attention_lock and self.state != MOVE_TURN and self.msd > 0.05:
            sVar6 = self.facing
            self.facing = cLib_addCalcAngleS(self.facing, self.target, self.F6,
                                             (param_1 << 1) & 0xFFFF, (self.F4 << 1) & 0xFFFF)
            temp = s16_signed(sVar6 - self.travel)
            temp2 = s16_signed(self.facing - self.travel)
            if temp * temp2 <= 0:
                self.facing = self.travel
        self._set_normal_speed_f(dVar9, self.F24, self.F1C, self.F20)

    # --- setSpeedAndAngleAtn (2851): the targeting-move dispatch ----------------------------
    def _get_dir_from_angle(self, angle):
        """getDirectionFromAngle (2278): bucket a signed s16 heading delta into a direction."""
        a = s16_signed(angle)
        if abs(a) > 0x6000:
            return DIR_BACKWARD
        if a >= 0x2000:
            return DIR_LEFT
        if a <= -0x2000:
            return DIR_RIGHT
        return DIR_FORWARD

    def _check_next_mode(self, l_held):
        """checkNextMode (4424) transition arbiter, flat/no-enemy subset: sets mMaxNormalSpeed from
        the attention state, then picks next frame's proc. r24 (L held) -> ATN_MOVE while moving,
        WAIT when stopped. The non-attention branch (4483) is the full ground-reversal machine:
          * stopped + >0x7800 stick reversal -> procWaitTurn (pivot in place)
          * already MOVE_TURN with facing!=travel -> stay MOVE_TURN (init is a no-op, 6612)
          * moving + >0x7800 reversal -> procSlip (fast + genuine stick flip) else procMoveTurn(1)
          * moving + the (post-travel-chase) heading now reads BACKWARD -> procMoveTurn(1)
          * otherwise procMove.
        The reversal-branch travel chase in setSpeedAndAngleNormal runs BEFORE this, so a slow MOVE
        reversal arrives here already below 0x7800 and routes via the DIR_BACKWARD branch instead."""
        cur = self.state                                  # mCurProc (dispatch-time proc)
        # r24 = checkAttentionLock() = Lockon(): L held OR the reticle still fading (RELEASE keeps the
        # actor locked -- attention.py). No actor => `_atn.locked` always False => r24 == l_held.
        atn = getattr(self, "_atn", None)
        locked_actor = atn is not None and atn.locked      # mpAttnActorLockOn != NULL
        if l_held or locked_actor:                        # r24 true
            self.max_nspeed = self.ATN_MAX
            if locked_actor:                              # actor-lock -> ATN_ACTOR_WAIT / ATN_ACTOR_MOVE
                self.state = ATN_ACTOR_WAIT if abs(self.nspeed) <= 0.001 else ATN_ACTOR_MOVE
            else:                                         # attention, no actor -> ATN_MOVE / WAIT
                self.state = WAIT if abs(self.nspeed) <= 0.001 else ATN_MOVE
            return
        self.max_nspeed = f32(self.MAX_NSPEED)
        self.direction = DIR_NONE
        dist = _dist_angle_s(self.target, self.travel)
        if abs(self.nspeed) <= 0.001:
            if dist > 0x7800 and self.msd > 0.05:
                self._proc_wait_turn_init()
            else:
                # changeWaitProc -> procWait_init: a no-op while already idle (FREE_WAIT keeps
                # playing its rest anim, 6062), so a resting stand stays FREE_WAIT rather than WAIT.
                self.state = self.state if self.state in (WAIT, FREE_WAIT) else WAIT
        elif cur == MOVE_TURN and self.travel != self.facing:
            self.state = MOVE_TURN                        # procMoveTurn_init(0) no-op: keep sweeping
        elif dist > 0x7800 and self.msd > 0.05:
            if (f32(self.speedF / self.max_nspeed) > self.SLIP_THRESH
                    and self._get_dir_from_angle(s16_signed(self.m34ea - self.m34dc)) == DIR_BACKWARD):
                self._proc_slip_init()
            else:
                self._proc_move_turn_init(1)
        elif (self._get_dir_from_angle(s16_signed(self.target - self.travel)) == DIR_BACKWARD
              and self.msd > 0.05):
            self._proc_move_turn_init(1)                  # getDirectionFromCurrentAngle == BACKWARD
        else:
            self.state = MOVE
