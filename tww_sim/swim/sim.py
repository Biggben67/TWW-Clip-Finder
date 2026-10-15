#!/usr/bin/env python3
"""
tww_sim/swim/sim.py - Offline physics sim for TWW superswimming (Phase A + B).

Pure-python reproduction of the swim physics validated live against Dolphin
(see KNOWLEDGE.md). Lets us test reboost / peak-hold theories in
milliseconds before burning Dolphin frames. Mirrors the `seq` and `essloop`
commands in dolphin_mem.py so results are directly A/B-comparable.

Physics (all live-validated to ~0.05%):
  anim increment   incr = |v|/36 + 3/5 + (1 - (air+1)/900)      (mod 23, state 55)
  af_drag(v,anim)  = (2v/5)|cos(pi*anim/23)| + 3v/5             (head-bob drag)
  air_drag(v,air)  = 18000 v / (24300 - 7 air)
  true_disp        = air_drag(af_drag(v, anim), air)            (ESS/charge move dist)
  ESS decay        = clamp((|raw-128|-15)/54, 0, 1) * 3   (ESS-down stick 110 -> 1/6)
  charge gain      = +3 / frame (on-axis full deflection)
  neutral          = decay -2, move == v (drag-free); anim ~0.83/frame mod 26 (approx)

Heading model (Phase B, live-calibrated 2026-06-26):
  Each CHARGE frame schedules a 180-deg facing flip that takes effect on the NEXT
  frame. Movement each frame follows the current facing. So an N-frame charge burst
  yields floor of alternating reversed frames -> the net-vs-path penalty of reboost.
  ESS/neutral never flip facing.

Usage:
  python -m tww_sim.swim.sim seq "<act,n;act,n;...>" [v=-1630] [air=900] [anim=0] [every=0]
      acts: ess (stick=110), ess:<rawY>, chg, neu     e.g. "ess,150" or
            "ess,20;chg,1;chg,1" (reboost). Mirrors dolphin_mem.py seq.
  python -m tww_sim.swim.sim essloop frames=N trig=LO,HI [boost=B] [v=..][air=..][anim=..]
      Closed-loop phase-triggered reboost, identical policy to dolphin essloop.
  Add  viz=out.html   to either to emit a self-contained animated movement viewer.
  Add  json=out.json  to dump the raw per-frame trace.

Both print a SUMMARY line matching dolphin_mem.py:  frames path net path/fr net/fr.
"""
import sys, math, json, struct
from ..core.fp import f32
from ..core.mathlib import (  # console math primitives, re-exported for `import sim as S` callers
    nfmod, fc_update, cLib_addCalc, cM_ssin_s16, cM_scos, cM_scos_s16,
    deg_to_s16, s16_signed, _F32_PI, _RAD2IDX, _GAME_TWOPI,
    ARROW_STICK_DEADZONE, angdiff_deg, _deadzone, stick_angle_deg,
    _COS_TABLE, _SIN_TABLE,
)

MAX_AIR = 900


# decomp constants (d_a_player_HIO.h: mSwim field_0x50/54/74 = 0.6/1.1/1.0).
_RATE_SLOPE = f32(f32(1.1) - f32(0.6))           # (0x54 - 0x50) in f32 = 0.5
_MAX_NSPEED = f32(18.0)                            # mMaxNormalSpeed (0.5/18 == 1/36)
_TIMER_K = f32(0.0011111111)                       # getSwimTimerRate per-air coefficient


def incr(v, air):
    # SWIMING anim rate = setSwimMoveAnime: |v|*(0x54-0x50)/mMaxNormalSpeed + 0x50
    #                     + getSwimTimerRate()*0x74   (all f32, decomp order)
    rate = f32(f32(f32(abs(f32(v))) * _RATE_SLOPE) / _MAX_NSPEED)
    rate = f32(rate + f32(0.6))
    timer = f32(1.0 - f32(f32(air + 1) * _TIMER_K))   # getSwimTimerRate (itemTimeCount=air+1)
    return f32(rate + f32(timer * f32(1.0)))

_F60 = f32(0.4)                 # field_0x60 (HIO mSwim.m.field_0x60)

def af_drag(v, anim):
    # head-bob: (speedF*(1-0x60) + 0x60*speedF*|cM_scos(rad2s(pi*moveFrame/moveEnd))|)
    # with field_0x60 = 0.4 -> 0.6*v + 0.4*v*|cM_scos(pi*anim/23)|. (d_a_player_main.cpp:
    # 2424-2428; moveEnd = 23.) Used only for DISPLACEMENT (an ignored wave-affected
    # byproduct), so its exact f32 order is not validated. The v-setting EXIT release uses
    # release_ess_speed below, which matches the (different) procSwimWait_init f32 order.
    # cos arg is SINGLE on console (fdivs anim/23 then fmuls lfs M_PI = _F32_PI; posMoveFromFootPos
    # JP @0x80106134/5c/60). Omits the /(1+0x7C*timerRate) divisor -- see predict/swim_exact.
    c = f32(abs(cM_scos(f32(f32(anim / 23.0) * _F32_PI))))
    return f32(f32(f32(f32(2.0 * v / 5.0)) * c) + f32(3.0 * v / 5.0))

def release_ess_speed(v, rel_anim):
    # ESS->neutral EXIT release v (procSwimWait_init, d_a_player_swim.inc:414-415):
    #   fVar2 = getFrame() / getEnd()            # rel_anim / 23 (SWIMING end), in f32
    #   mNormalSpeed = speedF*(1.0 - field_0x60) + speedF*|cM_fcos(fVar2 * M_PI)|*field_0x60
    # This is a DIFFERENT f32 order than the head-bob af_drag: the cos term is (v*c)*0.4
    # (multiply by |cos| BEFORE the 0.4 coeff), the coeffs are the HIO 0.4 / runtime
    # (1.0-0.4), and fVar2 = rel_anim/23 is taken in f32 BEFORE the *pi. The old af_drag
    # used 2v/5 * c + 3v/5 with pi*anim/23 in f64 -> ~2 ULP (3e-5) low at v~-180; that
    # constant v offset fed incr (~7e-7/frame) and the anim drift x598-amplified at pumps.
    # CRITICAL: `fVar2 * M_PI` compiles to lfs M_PI + fmuls = SINGLE pi (_F32_PI); double pi
    # flips the truncated cos-cell at knife-edges (was the pump-300k desync; memory superswim-gekko-fp).
    fVar2 = f32(rel_anim / 23.0)
    c = f32(abs(cM_scos(f32(fVar2 * _F32_PI))))
    term2 = f32(v * f32(1.0 - _F60))            # speedF * (1.0 - field_0x60)
    term1 = f32(f32(v * c) * _F60)              # speedF * |cos| * field_0x60
    return f32(term2 + term1)

def air_drag(v, air):
    return 18000.0 * v / (24300.0 - 7.0 * air)

def true_disp(v, anim, air):
    return air_drag(af_drag(v, anim), air)

# Charge frames move ~5.3% LESS than ESS at the identical (v,anim,air) — measured
# live (band 2): ESS 1463.60 vs charge 1385.44 at v=-1632,anim=17.66,air=895 ->
# 0.9466. Same heading, pure magnitude reduction (full-deflection stick path).
# Empirical, band-2 only; revalidate across speeds before trusting far from -1630.
CHARGE_DISP_FACTOR = 0.9466

# gradual (non-snap) facing turn cap, deg/frame (cLib_addCalcAngleS approx); used by both
# SwimState._swim_facing (core) and the arrow front-end (arrow.py imports it). See arrow.py.
ARROW_TURN_RATE = 7.0


def ess_decay(rawY):
    # potential-speed decay magnitude for a cardinal stick offset (raw 0..255), f32.
    return f32(min(max(f32(f32(abs(rawY - 128) - 15) / f32(54.0)), 0.0), 1.0) * f32(3.0))

def neutral_anim_rate(air):
    # neutral (state 54) SWIMWAIT anim rate/frame, mod 26 = procSwimWait setRate
    # (d_a_player_swim.inc:478): getSwimTimerRate()*field_0x70 + field_0x40, with
    # field_0x70=2.5, field_0x40=0.5. getSwimTimerRate (inc:283) is
    #   f32(1.0 - itemTimeCount * 0.0011111111f)  [itemTimeCount = air+1]
    # -- a MULTIPLY by the f32 1/900 constant, NOT a divide by 900. It is the SAME
    # getSwimTimerRate incr() uses (the *_TIMER_K term). The old divide-by-900 form
    # rounded 1 ULP HIGH at certain air (e.g. air=615: 3fa4fa50 vs decomp 3fa4fa4f);
    # since the warm-pump oldframe = fc_update(anim, this_rate, 26) is then *598-
    # scrambled, that 1 ULP compounded across pump cycles into a bad-phase exit
    # (HANDOFF pt17). Rounding structure mirrors incr() (product f32'd, then +0.5).
    timer = f32(1.0 - f32(f32(air + 1) * _TIMER_K))     # getSwimTimerRate()
    return f32(f32(0.5) + f32(f32(2.5) * timer))

class SwimState:
    """One Link, stepped frame by frame. Tracks 2D position so we can draw it.
    heading is the movement direction (radians); absolute orientation is arbitrary
    (we init 0) since net/path are rotation-invariant — only the 180 flips matter."""
    def __init__(self, v=-1630.0, anim=0.0, air=900, heading=0.0):
        self.v = float(v)
        self.anim = float(anim)
        self.air = int(air)
        self.x = 0.0
        self.z = 0.0
        self.heading = heading      # radians
        self.state = 55             # 55 = moving (ESS/charge), 54 = neutral
        self._pending_flip = False  # set by a charge frame; applied next frame start
        self._pending_gain = 0.0    # charge +3 lags 1 frame; lands on (and replaces the
                                    # decay of) the NEXT frame, even if that frame is ESS
        # The first held-ESS frame after a charge->hold entry (e.g. writename speed then
        # hold ESS, as in the Dolphin test slate) shows a one-time -3 facing-flip transient
        # instead of the normal decay. Set entry_tax=True to replicate that exactly.
        self._entry_tax = False
        # Air refill (opt-in): while forward progress -x <= _refill_until, air is pinned to
        # 900 (the "refill before cruising" tech). Default off -> baselines unchanged.
        self._refill_air = False
        self._refill_until = 0.0
        # state 54<->55 transitions lag 1 frame: the first input frame runs the OLD
        # state's physics, the transition (and its release/scramble effect) lands next.
        self._pending_state = None
        self._just_released = False
        self._skip_advance = False  # scramble frame loads anim directly at ess_start
        # oldFrame for the next neutral->ESS scramble = the MOVE0 (SWIMWAIT) controller frame
        # at setSwimMoveAnime time. TWO cases (live-pinned, both bit-exact):
        #  - COLD START (first swim, fresh/rested controller): the swim-INITIATION frame
        #    advances MOVE0 by exactly +1.0, so oldFrame = (display anim at the trigger
        #    frame START) + 1.0. Stashed in _scramble_oldframe at the trigger frame.
        #  - WARM PUMP (re-entry mid-swim, running controller): procSwimWait runs one more
        #    neutral update() on the landing frame before procSwimMove_init, so
        #    oldFrame = (display anim after the trigger frame, = self.anim at landing start)
        #    + neutral_anim_rate(self.air). No stash needed.
        # setSwimMoveAnime then does setFrame(oldFrame*26*23) -> anim = 598*oldFrame.
        self._scramble_oldframe = None
        self._warm = False          # True once the swim has been in state 55 (=> pumps, not
                                    # the cold-start initiation, drive subsequent entries).
        # FACING (shape_angle.y) — tracked per decomp so the charge gain SIGN is exact.
        # setSpeedAndAngleSwim (d_a_player_swim.inc:27-41): each swim frame with stick,
        #   if |m34E8 - facing| > 0x6000 (135 deg):  facing SNAPS to m34E8
        #   else:                                     facing turns gradually toward m34E8
        #   gain = mStickDistance * 3 * cM_scos(facing_new - facing_old)
        # So a charge whose stick OPPOSES facing snaps (cos~-1 -> -3 gain) and one ALIGNED
        # with facing turns ~0 (cos~+1 -> +3 LOSS = the spin-up). The blind "-3 every chg"
        # was only right when the charge snaps; warm pump re-entries can be aligned -> +3.
        # Tracked in s16 (the game's shape_angle.y units) for bit-exact cM_scos at the
        # cardinal angles. Slate: facing 16384 (east), csangle 49152 (west).
        self.facing = 16384           # shape_angle.y, s16
        self.cam = 49152              # csangle, s16
        self._pending_facing = None   # facing snap/turn lands next frame (1-frame lag)
        self._chg_count = 0           # charge up/down parity (replay: chg#1=UP=odd)
        # Post-burst facing transient: when an ESS frame's own facing-snap gain is
        # preempted by a landing charge gain (the frame a charge burst ends), that
        # transient is not lost -- it lands the NEXT frame (1-frame lag, like charges),
        # matching live setSpeedAndAngleSwim. For EVEN bursts facing is already
        # re-aligned so the carried value == +1/6 == the next frame's own gain (no-op,
        # keeps the 200k/even baselines bit-exact); for ODD bursts it carries the -1/6
        # opposed transient that the old code dropped (the t_chgexit -1/3 residual).
        self._post_burst_transient = None

    def clone(self):
        s = SwimState.__new__(SwimState)
        s.__dict__.update(self.__dict__)
        return s

    def _advance_anim_55(self):
        # SWIMING controller: end=23. Faithful loop-subtract (fc_update) so the post-scramble
        # raw mFrame (~15232) loops down with the GAME's f32 rounding, not nfmod's f64 modulo.
        self.anim = fc_update(self.anim, incr(self.v, self.air), 23.0)

    def _swim_facing(self, sx, sy):
        """Decomp facing update for a swim-input frame (setSpeedAndAngleSwim, s16 math).
        Schedules the snap/gradual facing change for NEXT frame (1-frame lag) and returns
        the speed gain = mStickDistance*3*cM_scos(d_turn). Caller decides whether to use
        the gain (charge) or keep its own decay (ESS). All angles s16:
          m34E8 = stickAngle + 0x8000 + camAngle;  snap iff |m34E8 - facing| > 0x6000."""
        sa = stick_angle_deg(sx, sy)
        if sa is None:                             # neutral stick: no swim input, no turn
            return 0.0
        m = (deg_to_s16(sa) + 0x8000 + self.cam) & 0xFFFF      # m34E8 (s16)
        d = s16_signed(m - self.facing)            # signed s16 difference
        if abs(d) > 0x6000:                        # 135 deg backward cone -> instant snap
            d_turn = d
        else:                                      # aligned -> gradual chase (cardinal: 0)
            cap = deg_to_s16(ARROW_TURN_RATE)
            d_turn = max(-cap, min(cap, d))
        self._pending_facing = (self.facing + d_turn) & 0xFFFF
        # mStickDistance uses the /54 gate (== ess_decay's normalization): ESS(110)=0.0556,
        # full charge deflection (0/255) clamps to 1.0. (NOT stick_dist's /113 gate, which
        # would give 0.991 for a full charge -> -2.97 instead of the live-exact -3.0.)
        mag = math.hypot(_deadzone(sx), _deadzone(sy))   # _deadzone already removed the 15
        md = min(mag / 54.0, 1.0)
        return f32(md * 3.0 * cM_scos_s16(d_turn))

    def _chg_stick(self, up_raw=None):
        """The concrete charge stick for this charge frame, matching the replay parity
        (verify_state/spotcheck: chg#1=UP, then alternating). UP=(128,255), DN=(128,0).
        PARTIAL charge ('chg:<up_raw>'): the UP stroke is (128, up_raw) and the DOWN stroke
        mirrors it about 128 -> (128, 256-up_raw), so a deflection shallower than full still
        snaps (same on-axis direction) but gains less than 3 via the /54 law. up_raw=None
        keeps the full-charge sticks BIT-EXACT (default path, baselines untouched)."""
        self._chg_count += 1
        if up_raw is None:
            return (128, 255) if (self._chg_count % 2 == 1) else (128, 0)
        return (128, up_raw) if (self._chg_count % 2 == 1) else (128, 256 - up_raw)

    def _move(self, dist):
        self.x += dist * math.cos(self.heading)
        self.z += dist * math.sin(self.heading)
        return dist

    def _move(self, dist):
        self.x += dist * math.cos(self.heading)
        self.z += dist * math.sin(self.heading)
        return dist

    def step(self, action):
        """action: 'ess' | 'ess:<rawY>' | 'chg' | 'neu'. Returns (step_dist, tag).
        State 54 (neutral) <-> 55 (ESS/charge) transitions lag 1 frame (live-pinned):
        the first input frame runs the OLD state; the new state + its effect land next.
        - ESS->neutral: on the 54 frame, v := release_ess_speed = af_drag(v, anim+incr).
        - neutral->ESS (pump): 1-frame neutral tax, then ESS with a scrambled anim start."""
        if action not in ('chg', 'neu') and not action.startswith(('ess', 'chg:')):
            raise ValueError(f"unknown action {action!r}")
        # PARTIAL charge: 'chg:<up_raw>' charges with a shallower on-axis deflection (still
        # snaps/flips, gains <3 via /54). chg_up=None -> full charge (existing 'chg', exact).
        chg_up = int(action[4:]) if action.startswith('chg:') else None
        is_chg = (action == 'chg') or (chg_up is not None)
        # 180-deg turnaround flip (charge), applied at frame start
        if self._pending_flip:
            self.heading += math.pi
            self._pending_flip = False
        if self._pending_facing is not None:      # facing snap/turn lands now (1-frame lag)
            self.facing = self._pending_facing
            self._pending_facing = None
        # pending 54<->55 state transition (1-frame lag), with its one-time effect
        if self._pending_state is not None:
            if self._pending_state == 54:        # ESS -> neutral exit: release_ess_speed
                # procSwimWait_init(TRUE) (d_a_player_swim.inc:406-424): fVar2 =
                # getFrame()/getEnd (SWIMING end=23); release speed = af_drag(|cos(pi*fVar2)|),
                # THEN the SAME MOVE0 controller is re-scaled to SWIMWAIT (end 26):
                # setFrame(fVar2 * 26). So the post-exit neutral DISPLAY anim =
                # (swiming/23)*26 -- the exact mirror of the entry's *598 scramble, NOT a
                # separate parallel controller. swiming = the SWIMING frame advanced one more
                # step on the transition frame (= self.anim + incr, wrapped mod 23; getFrame()
                # is the looped frame in [0,23)). |cos| is mod-23 periodic so the wrap leaves
                # the release v bit-identical.
                rel_anim = fc_update(self.anim, incr(self.v, self.air), 23.0)
                self.v = release_ess_speed(self.v, rel_anim)
                # setFrame(fVar2 * getEnd()), fVar2 = getFrame()/getEnd (procSwimWait_init,
                # d_a_player_swim.inc:415,421): DIVIDE-then-multiply in f32, i.e.
                # f32(f32(rel_anim/23.0) * 26.0) -- NOT a precomputed f32(26/23) multiply
                # (different f32 rounding). Feeds oldframe for the next x598 scramble, so the
                # 1-ULP difference is amplified ~600x across pump cycles.
                self.anim = f32(f32(rel_anim / 23.0) * 26.0)
                self._just_released = True
            else:                                # neutral -> ESS pump: anim scramble
                # DECOMP-DERIVED (setSwimMoveAnime, d_a_player_swim.inc:264 +
                # J3DFrameCtrl, J3DAnimation.h:853-860). The pump re-inits the move
                # controller:
                #   endFrame = oldFrame * oldEnd       # oldEnd = getEnd() = 26 (ANM_SWIMWAIT)
                #   <load ANM_SWIMING: mEnd <- 23, mFrame <- start=0>
                #   setFrame(endFrame * getEnd())      # mFrame = oldFrame*26*23 = oldFrame*598
                # setFrame is a RAW float store (no wrap). Drag samples |cos(pi*mFrame/23)|,
                # period 23, and 598 = 26*23 ≡ 0 (mod 23) -> only frac(oldFrame) survives,
                # scaled x598 (the hypersensitivity). Then the first ESS update() adds one
                # mRate = incr(v,air) BEFORE the drag read, so the displayed start is:
                #   anim_ESS_start = (oldFrame*598 + incr(v,air)) mod 23
                # oldFrame = the MOVE0 (SWIMWAIT) controller frame at the instant
                # setSwimMoveAnime runs. procSwimWait runs ONE MORE neutral update() on the
                # landing frame BEFORE procSwimMove_init fires, so getFrame = (display anim
                # after the trigger frame, = self.anim here at the landing-frame START) +
                # one more neutral step. This is the UNIFIED rule for BOTH cold-start and
                # pump entries (the old "+1.0 from trigger-frame-start" only COINCIDENTALLY
                # matched cold start: 0.064+1.0 == display_after_f1 + neutral_rate; it broke
                # for pumps where neutral_rate != 0.5). Live-pinned on the pump cycle:
                # f93 display 24.716 -> oldFrame 24.716+0.756 = 25.472 -> 598*25.472 mod 23
                # = live raw 15232.17 / 598. The +incr lands the NEXT frame (skip_advance).
                if self._scramble_oldframe is not None:   # COLD START: stashed start+1.0
                    oldframe = self._scramble_oldframe
                    self._scramble_oldframe = None
                else:                                     # WARM PUMP: display_after + neut rate
                    # procSwimWait's update() runs (and LOOPS mod 26) before procSwimMove_init
                    # reads getFrame(), so oldframe is the LOOPED SWIMWAIT frame -- fc_update,
                    # not a raw add. If the sum exceeds 26 a raw add would *598 a value 26
                    # larger; 26*598 == 0 (mod 23) so v is unaffected, but the RAW magnitude
                    # (and thus the faithful f32 loop-down) would differ -> anim drift.
                    oldframe = fc_update(self.anim, neutral_anim_rate(self.air), 26.0)
                # setSwimMoveAnime (d_a_player_swim.inc:265,275): endFrame = getFrame()*getEnd()
                # (oldEnd=26, SWIMWAIT still loaded) THEN setFrame(endFrame * getEnd()) with the
                # NEW end=23 (SWIMING). So it is TWO sequential f32 multiplies x26 then x23 --
                # NOT f32(598*oldframe). f32(f32(x*26)*23) != f32(x*598) by ~1 ULP at this
                # magnitude (~15232); that ULP carried forward and re-amplified x598 each pump.
                self.anim = f32(f32(oldframe * 26.0) * 23.0)   # RAW setFrame -- stays raw
                # (~15232) like the live mFrame; the next _advance_anim_55 loops it down with
                # the game's f32 repeated-subtraction (fc_update), NOT an nfmod single modulo.
                self._skip_advance = True                  # +incr lands NEXT frame via the
                #   normal update() advance, NOT baked into the scramble. Live-pinned:
                #   frame2 = 598*oldFrame mod 23 (no incr); frame3 = +incr.
            trans_to = self._pending_state
            self.state = self._pending_state
            self._pending_state = None
            if trans_to == 55:                    # now swimming -> subsequent entries are
                self._warm = True                 # WARM pumps, not the cold-start initiation.
            if trans_to == 54:                    # ESS->neutral EXIT wipes stale charge
                self._pending_gain = 0.0          # gain; the neutral->ESS pump KEEPS a
                                                  # freshly-scheduled cold-start charge.
        desired = 54 if action == 'neu' else 55

        if self.state == 54:                      # NEUTRAL physics (drag-free)
            if desired == 55 and not self._warm:  # COLD-START initiation frame: stash
                self._scramble_oldframe = f32(self.anim + 1.0)  # oldFrame = display(start)+1.0
            if self._just_released:               # exit-release frame: display anim was just
                self._just_released = False        # set to (swiming/23)*26 by the exit branch;
                                                  # the neutral rate lands NEXT frame (live-
                                                  # pinned: post[1] == rescaled value exactly,
                                                  # no neutral advance) and v keeps the release.
            else:
                self.anim = fc_update(self.anim, neutral_anim_rate(self.air), 26.0)  # SWIMWAIT end=26
                # NEUTRAL speed decay = setNormalSpeedF's cLib_addCalc chase toward 0
                # (d_a_player_main.cpp:2348, swim.inc:81 with param_1==0): NOT a flat -2.
                # cLib_addCalc(v, 0, scale=0.02, maxStep=2.0, minStep=0.5): |v|>100 -> step 2.0
                # (the old flat-2, so 200k/high-speed dash unchanged), 25<|v|<100 -> 0.02*|v|
                # (proportional), |v|<25 -> snaps 0.5/frame to 0. Live-pinned (scale 0.02 exact,
                # maxStep 2.0, minStep 0.5, reaches 0 with no overshoot). HIO mSwim field_0x18/
                # 1C/20. The old flat -2 was right only above |v|=100 -> wrong on the low-speed
                # tail and after many pumps bleed v, where it x598-compounded into divergence.
                self.v = cLib_addCalc(self.v, 0.0, 0.02, 2.0, 0.5)
            if is_chg:                            # charging FROM neutral (cold start / pump
                self._pending_gain = self._swim_facing(*self._chg_stick(chg_up))  # decomp gain:
                self._pending_flip = True         # snap (opposing facing) -> -3, aligned ->
                                                  # +3 (the warm-pump spin-up). gain+flip land
                                                  # next frame (when state has become 55).
            d = self._move(self.v)                # move == potential (|step| == |v|)
            tag = 'NEU'
        else:                                     # STATE 55: ESS / charge
            # action 'neu' here = the held ESS exit frame; is_chg/chg_up computed above.
            rawY = int(action.split(':')[1]) if action.startswith('ess') and ':' in action else 110
            if self._skip_advance:                # scramble frame: anim already = ess_start
                self._skip_advance = False
            else:
                self._advance_anim_55()           # anim rate lags 1 frame: uses pre-update v
            # Compute this frame's facing-based swim gain (= mStickDistance*3*cM_scos(d_turn),
            # setSpeedAndAngleSwim) and schedule the facing snap/turn. ESS aligned -> +1/6;
            # ESS just after a snapping charge (facing not yet re-aligned) -> -1/6 (the live
            # transient the old fixed +1/6 ess_decay missed). A 'neu' held-exit frame has a
            # neutral stick -> no swim input -> facing frozen.
            if is_chg:
                swim_gain = self._swim_facing(*self._chg_stick(chg_up))
            elif action.startswith('ess'):
                swim_gain = self._swim_facing(128, rawY)
            else:                                 # 'neu' held-exit frame (neutral stick)
                swim_gain = ess_decay(rawY)       # validated exit-frame decay (facing frozen)
            # setSpeedAndAngleSwim gain lags ONE frame UNIFORMLY for ESS and charge (lands
            # next frame via _pending_gain). See history/resolved-bugs.md#bug3.
            if self._pending_gain:                # gain scheduled last frame lands now,
                self.v = f32(self.v + self._pending_gain)   # replacing this frame's decay
                self._pending_gain = 0.0
            elif self._entry_tax and not is_chg:  # one-time -3 facing-flip transient (slate)
                self.v = f32(self.v - 3.0)
                self._entry_tax = False
            elif is_chg:                          # 1st charge of a cold burst: no pending
                self.v = f32(self.v + ess_decay(rawY))   # gain yet; this frame still decays
            elif self._post_burst_transient is not None:  # legacy carry (now unused; kept
                self.v = f32(self.v + self._post_burst_transient)   # for safety/no-op)
                self._post_burst_transient = None
            else:
                self.v = f32(self.v + swim_gain)  # 1st ESS of a cold burst (no pending): the
                #   facing-based gain lands this frame (no prior frame scheduled one).
            if action.startswith('ess') or is_chg:   # schedule THIS frame's gain for next
                self._pending_gain = swim_gain        # frame (uniform 1-frame lag, decomp).
            if is_chg:
                self._pending_flip = True         # charge facing flip also lands next frame
            fac = CHARGE_DISP_FACTOR if is_chg else 1.0
            d = self._move(fac * true_disp(self.v, self.anim, self.air))
            tag = 'CHG' if is_chg else 'ESS'

        if desired != self.state:                 # schedule the lagged transition
            self._pending_state = desired
        # AIR REFILL (opt-in, default off so baselines are untouched): while the swim has
        # not yet committed forward progress (distance to dest still == initial, i.e. the
        # in-place charge build), air is refilled to 900 -- modelling the real "air refill
        # before cruising" so the ESS cruise/pumps run at low drag (high air). Free reset
        # (user-specified model). Once -x passes refill_until (cruise begins), air depletes.
        if self._refill_air and (-self.x) <= self._refill_until:
            self.air = 900
        else:
            self.air -= 1
        return d, tag

def run_trace(actions, v, anim, air, entry_tax=True):
    """actions: iterable of action strings. Returns list of per-frame dict rows."""
    s = SwimState(v=v, anim=anim, air=air)
    s._entry_tax = entry_tax
    rows = []
    x0, z0 = s.x, s.z
    path = 0.0
    for i, act in enumerate(actions):
        d, tag = s.step(act)
        path += abs(d)
        net = math.hypot(s.x - x0, s.z - z0)
        rows.append({"f": i + 1, "x": s.x, "z": s.z, "v": s.v, "anim": s.anim,
                     "air": s.air, "state": s.state, "step": d, "tag": tag,
                     "path": path, "net": net,
                     "eff": 0.6 + 0.4 * abs(math.cos(math.pi * s.anim / 23.0))})
    return rows

def parse_seq(spec):
    acts = []
    for part in spec.split(';'):
        part = part.strip()
        if not part:
            continue
        a, n = part.rsplit(',', 1)
        acts.extend([a.strip()] * int(n))
    return acts

def essloop_actions(frames, lo, hi, boost):
    """Replicates dolphin essloop: hold ESS, fire a `boost`-frame charge burst when
    anim enters [lo,hi] (wraps if lo>hi), with cooldown (must leave window to refire)."""
    def in_win(a):
        return (lo <= a <= hi) if lo <= hi else (a >= lo or a <= hi)
    return _ClosedLoop(frames, in_win, boost)

class _ClosedLoop:
    """Lazy action generator that needs to see live anim — handled in run_closed."""
    def __init__(self, frames, in_win, boost):
        self.frames, self.in_win, self.boost = frames, in_win, boost

def run_closed(cl, v, anim, air, entry_tax=True):
    s = SwimState(v=v, anim=anim, air=air)
    s._entry_tax = entry_tax
    rows = []
    x0, z0 = s.x, s.z
    path = 0.0
    armed = True
    nboost = 0
    while len(rows) < cl.frames:
        if cl.boost and armed and cl.in_win(s.anim):
            for _ in range(cl.boost):
                if len(rows) >= cl.frames:
                    break
                d, tag = s.step('chg')
                path += abs(d)
                rows.append(_row(s, len(rows) + 1, d, tag, path, x0, z0))
            nboost += 1
            armed = False
            continue
        d, tag = s.step('ess')
        path += abs(d)
        rows.append(_row(s, len(rows) + 1, d, tag, path, x0, z0))
        if not armed and not cl.in_win(s.anim):
            armed = True
    return rows, nboost

def _row(s, f, d, tag, path, x0, z0):
    return {"f": f, "x": s.x, "z": s.z, "v": s.v, "anim": s.anim, "air": s.air,
            "state": s.state, "step": d, "tag": tag, "path": path,
            "net": math.hypot(s.x - x0, s.z - z0),
            "eff": 0.6 + 0.4 * abs(math.cos(math.pi * s.anim / 23.0))}

def summarize(rows, extra=""):
    n = len(rows)
    path = rows[-1]["path"]
    net = rows[-1]["net"]
    last = rows[-1]
    print(f"SUMMARY frames={n} path={path:.2f} net={net:.2f} "
          f"path/fr={path/n:.3f} net/fr={net/n:.3f} "
          f"v={last['v']:.5g} air={last['air']} anim={last['anim']:.4g} {extra}")

def parse_opts(argv):
    opts = {}
    pos = []
    for tok in argv:
        if '=' in tok:
            k, _, v = tok.partition('=')
            opts[k] = v
        else:
            pos.append(tok)
    return pos, opts

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    pos, opts = parse_opts(sys.argv[2:])
    v = float(opts.get('v', '-1630'))
    air = int(opts.get('air', '900'))
    anim = float(opts.get('anim', '0'))
    every = int(opts.get('every', '0'))

    if cmd == 'arrowseq':
        # arrowseq "sx,sy;sx,sy;..." [v=][air=][anim=][facing=90][cam=270]
        sticks = [tuple(int(t) for t in p.split(',')) for p in pos[0].split(';') if p]
        facing = float(opts.get('facing', '90'))
        cam = float(opts.get('cam', '270'))
        rows = run_arrow(sticks, v=v, anim=anim, air=air, facing_deg=facing, cam_deg=cam)
        print("f  stick      facing  tag    v        dx      dz   moveBrg net   netBrg")
        for r in rows:
            print(f"{r['f']:<3}({r['stick'][0]:>3},{r['stick'][1]:<3}) {r['facing']:6.0f}  "
                  f"{r['tag']:<5} {r['v']:8.2f} {r['dx']:+7.0f} {r['dz']:+6.0f} "
                  f"{r['move_brg']:5.0f}  {r['net']:6.0f} {r['net_brg']:5.0f}")
        rl = rows[-1]
        print(f"SUMMARY {len(rows)} frames: net={rl['net']:.0f} bearing={rl['net_brg']:.0f} "
              f"v={rl['v']:.1f} facing={rl['facing']:.0f}")
        return
    if cmd == 'seq':
        rows = run_trace(parse_seq(pos[0]), v, anim, air)
        extra = ""
    elif cmd == 'essloop':
        frames = int(opts.get('frames', '150'))
        lo, hi = (float(x) for x in opts.get('trig', '21,2').split(','))
        boost = int(opts.get('boost', '2'))
        rows, nboost = run_closed(essloop_actions(frames, lo, hi, boost), v, anim, air)
        extra = f"boosts={nboost}"
    elif cmd == 'compare':
        # compare frames=N trig=LO,HI boost=B  -> baseline ESS vs reboost, overlaid
        frames = int(opts.get('frames', '150'))
        lo, hi = (float(x) for x in opts.get('trig', '13,16').split(','))
        boost = int(opts.get('boost', '4'))
        base = run_trace(['ess'] * frames, v, anim, air)
        rb, nboost = run_closed(essloop_actions(frames, lo, hi, boost), v, anim, air)
        print("baseline  ", end=""); summarize(base)
        print(f"reboost   ", end=""); summarize(rb, f"boosts={nboost}")
        out = opts.get('viz', 'swim_compare.html')
        emit_viz(out, [{"name": "pure ESS", "color": "#58a6ff", "rows": base},
                       {"name": f"reboost b{boost}@{lo:.0f}-{hi:.0f}", "color": "#3fb950", "rows": rb}])
        return
    else:
        print(f"unknown cmd {cmd}"); sys.exit(1)

    if every:
        print("f\tv\tanim\tair\teff\ttag\tstep\tnet")
        for r in rows:
            if r["f"] % every == 0:
                print(f"{r['f']}\t{r['v']:.1f}\t{r['anim']:.3g}\t{r['air']}\t"
                      f"{r['eff']*100:.1f}\t{r['tag']}\t{r['step']:.1f}\t{r['net']:.1f}")
    summarize(rows, extra)

    if 'json' in opts:
        json.dump(rows, open(opts['json'], 'w'))
        print(f"wrote {opts['json']}")
    if 'viz' in opts:
        emit_viz(opts['viz'], [{"name": cmd, "color": "#58a6ff", "rows": rows}])

# Re-export the split-out arrow front-end (arrow.py) + viz emitter (_viz.py) so
# `from tww_sim.swim import sim as S` callers keep S.ArrowState / S.run_arrow / S.emit_viz etc.
from .arrow import (  # noqa: E402,F401
    ArrowState, run_arrow, arrow_charge_rate, arrow_cross_drift, stick_dist, m34e8_deg,
    stick_for_m34e8, snap_deltas, arrow_sticks, reorient_chain,
    ARROW_ALPHA_MAX_DEG, ARROW_SPINUP_FRAMES, ARROW_SNAP_DEG, FACING_GATE,
)
from ._viz import emit_viz  # noqa: E402,F401


if __name__ == '__main__':
    main()
