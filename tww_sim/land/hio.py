#!/usr/bin/env python3
"""_LandHIO: the shipped HIO constant block for LandState (d_a_player_HIO_data.inc).

`m_HIO` (the player's tunable parameter tables) is never mutated in normal play, so these are
shipped literals -- no live dump. Split out of state.py as a single-topic base class LandState
inherits: the proc mixins read them as ``self.<NAME>`` through the MRO, so relocating them here is
transparent (no import churn, no behaviour change). One family per block, offsets cited per the
decomp HIO layout. See design-note 5b + knowledge/reference/constants.md for the canonical values.
"""
from __future__ import annotations
from ..core.mathlib import f32
from .constants import CUT_F, CUT_A


class _LandHIO:
    # HIO m_HIO->mMove walk constants (d_a_player_HIO_data.inc:8). See design-note 5b table.
    MAX_NSPEED = f32(17.0)          # mMaxNormalSpeed (= mMove.field_0x18)
    F0 = 3000                       # base angle-turn rate (param_1 to setSpeedAndAngleNormal)
    F4 = 100                        # angle-approach max-delta (cLib_addCalcAngleS clamp)
    F6 = 5                          # angle-approach scale/mode arg
    F14 = f32(3.5)                  # target-speed scale (dVar9 *= field_0x14 * dist^2)
    F1C = f32(2.5)                  # accel rate -> setNormalSpeedF param_3 (cLib maxStep)
    F20 = f32(1.8)                  # decel rate -> setNormalSpeedF param_4 (cLib minStep)
    F24 = f32(0.6)                  # speed cLib scale -> setNormalSpeedF param_2

    # HIO mAtnMove (targeting-move) constants (d_a_player_HIO_data.inc:14, daPy_HIO_atnMove_c1). Used by
    # setSpeedAndAngleAtn's side branch, setSpeedAndAngleAtnActor (procs 8/9), + the FORWARD->Normal cap.
    ATN_MAX = f32(12.0)             # field_0xC  = mMaxNormalSpeed under attention lock
    ATN_TURN_MAX = 3000             # field_0x0  = travel-chase max step (s16)
    ATN_TURN_MIN = 2000             # field_0x2  = travel-chase min step (s16)
    ATN_TURN_SCALE = 6              # field_0x4  = travel-chase scale (s16)
    ATN_SPD = f32(5.0)             # field_0x8  = target-speed scale (fVar2 = *msd*cos)
    ATN_ACC = f32(7.5)             # field_0x10 = setNormalSpeedF maxStep
    ATN_DEC = f32(4.0)             # field_0x14 = setNormalSpeedF minStep
    ATN_SCL = f32(0.5)             # field_0x18 = setNormalSpeedF cLib scale
    # HIO mAtnMoveB (targeting-move BACKWARD) constants, d_a_player_HIO_data.inc:18. The
    # steady-state brakeslide runs here (facing locked, travel ~180, speed negative bleeding up).
    ATNB_MAX = f32(15.0)            # field_0xC  = mMaxNormalSpeed when DIR_BACKWARD
    ATNB_SPD = f32(2.5)             # field_0x8  = target-speed scale
    ATNB_ACC = f32(8.0)             # field_0x10 = setNormalSpeedF maxStep
    ATNB_DEC = f32(2.0)             # field_0x14 = setNormalSpeedF minStep
    ATNB_SCL = f32(0.5)             # field_0x18 = setNormalSpeedF cLib scale
    ATNB_COS_FWD = f32(0.99)        # field_0x2C = cos(travel-facing) >= this -> DIR_FORWARD
    ATNB_COS_BACK = f32(-0.99)      # field_0x30 = cos(travel-facing) <= this -> DIR_BACKWARD

    # HIO mRoll (forward roll) constants, d_a_player_HIO_data.inc:97 (daPy_HIO_roll_c1). The roll
    # speed is set ONCE at entry from the pre-roll speedF; the anim frame ctrl (ANM_ROLLF) times it.
    ROLL_SPD = f32(1.5)             # field_0x18 = speedF multiplier
    ROLL_ADD = f32(0.5)             # field_0x1C = base add
    ROLL_MIN = f32(5.0)             # field_0x20 = speed floor (standstill roll) + neutral-exit -= this
    ROLL_END = f32(19.0)            # field_0x0 = ANM_ROLLF end frame; anim completes (rate->0) here
    ROLL_RATE = f32(1.1)            # field_0x8 = ANM_ROLLF frame-ctrl rate (mFrameCtrlUnder[MOVE0])
    ROLL_ENTRY_MORF = 2.0           # field_0x14 = setSingleMoveAnime i_morf at roll entry
    MOVE_REENTRY_MORF = 2.4         # mBasic.field_0xC = procMove_init setBlendMoveAnime morf (roll->walk)
    ROLL_EARLY = f32(17.0)          # field_0x10 = getFrame()>this -> checkNextMode(1) moving-stick exit
    # A neutral stick leaves checkNextMode(1) inert (4457: msd<=0.05, no action button) so the roll runs
    # to ROLL_END; a held stick exits a frame early -- the roll-EBS.
    ATTACK_MSD_MIN = f32(0.75)      # mBasic.field_0x1C
    # The ROLL's own stick gate (setDoStatusBasic 2220 -> 4318), not the 0.05 locomotion floor: at or
    # below it the A-press sheathes. Console-bracketed: mechanics/roll-attack-threshold.md.
    ATTACK_MSD_HEAVY = f32(0.5)     # mMove.field_0x80: scales it while carrying (never, in this model)

    # HIO mCut sword-thrust cuts (roll stab). d_a_player_HIO_data.inc:31/27, procCutF/A sword.inc:660/430;
    # the roll-stab lunge model + why 49.22u: knowledge/mechanics/land-movement.md + reference/constants.md.
    CUT_ANIM = {CUT_F: 'cutf', CUT_A: 'cuta'}
    CUT_RATE = f32(1.2)             # field_0x4  = ANM_CUT frame-ctrl rate (mFrameCtrlUnder[MOVE0])
    CUT_START = f32(4.0)            # field_0x8  = setSingleMoveAnime start frame (fc begins here)
    CUT_END = f32(19.0)            # bck frameMax (EMode_NONE end); rate->0 clamp at end-0.001
    CUT_PASS = f32(6.0)            # field_0x28 = checkPass frame -> set mNormalSpeed launch
    CUT_LAUNCH_MUL = f32(0.2)      # field_0x10 = mNormalSpeed = |speedF|*this + <add>
    CUT_DEC_SCALE = f32(0.7)       # field_0x20 = cLib_addCalc decel scale
    CUT_DEC_MIN = f32(0.5)         # field_0x1C = cLib_addCalc decel minStep
    # per-cut fields: field_0xC (getFrame()> -> checkNextMode(1) exit) / field_0x14 (add) / field_0x18 (max)
    CUT_EARLY = {CUT_F: f32(17.0), CUT_A: f32(16.0)}   # field_0xC
    CUT_LAUNCH_ADD = {CUT_F: f32(8.0), CUT_A: f32(10.0)}  # field_0x14
    CUT_DEC_MAX = {CUT_F: f32(0.95), CUT_A: f32(2.6)}     # field_0x18
    # Diagonal-thrust aim turn: procCutF/A snap shape=travel to the latched m34D4 aim on the 1st cut
    # proc frame (cLib min-step 0x1F40 >> any in-range diff). See knowledge/mechanics/roll-stab.md.
    CUT_TURN_SCALE = 30            # mTurn.field_0x4 (cLib_addCalcAngleS scale)
    CUT_TURN_MAX = 0x3CDF          # mTurn.field_0x0 (maxStep)
    CUT_TURN_MIN = 0x1F40          # mTurn.field_0x2 (minStep; >> any in-range diff -> 1-frame snap)
    CUT_DIR_FWD = 0x2000          # getDirectionFromAngle FORWARD band: |aim - facing| < this stays CUT_F

    # HIO mTurn (ground reversal turns), d_a_player_HIO_data.inc:22. WaitTurn pivots facing toward the
    # captured stick target; the min step (0x1F40) dominates -> ~8000/frame. (MoveTurn sweep: see its init.)
    TURN_MAX = 0x3CDF               # field_0x0 = cLib_addCalcAngleS max step (WaitTurn facing pivot)
    TURN_MIN = 0x1F40               # field_0x2 = min step
    TURN_SCALE = 30                 # field_0x4 = scale (diff/scale; << min so the min step rules)
    WAIT_TURN_ANIM_RATE = f32(1.0)  # mBasic.field_0x4 = ANM_ROT frame-ctrl rate (pivot pose)
    # HIO mSlip (high-speed reversal skid), d_a_player_HIO_data.inc:106 (daPy_HIO_slip_c1). Entry from a
    # MOVE frame whose speedF/mMaxNormalSpeed exceeds the threshold AND the stick genuinely flipped.
    SLIP_THRESH = f32(0.6)          # field_0x4 = speedF/mMaxNormalSpeed slip-entry threshold
    SLIP_ENTRY = f32(1.1)           # field_0x8 = entry-speed multiplier (mNormalSpeed = speedF * this)
    SLIP_DEC_SCALE = f32(0.6)       # field_0x18 = cLib_addCalc decel scale
    SLIP_DEC_MAX = f32(1.25)        # field_0x10 = cLib_addCalc decel maxStep (~-1.25/frame skid bleed)
    SLIP_DEC_MIN = f32(0.1875)      # field_0x14 = cLib_addCalc decel minStep
    SLIP_ANIM_RATE = f32(0.4)       # field_0xC = ANM_SLIP frame-ctrl rate (skid pose)
    SLIP_MORF = f32(1.7)            # field_0x1C = ANM_SLIP setSingleMoveAnime oldframe-morf
    # MoveTurn slip-exit re-accel seed = mMaxNormalSpeed * this (procSlip 6666); shape nudge = 0x100.
    MT_SLIP_SEED = f32(0.5)

    # HIO mSideStep (targeted sidehop), d_a_player_HIO_data.inc:223. Ballistic launch perp to facing;
    # lands on the first ground-hit frame. Mechanics: knowledge/mechanics/land-movement.md.
    SIDESTEP_ANGLE = 6200          # field_0x2 = s16 launch angle (fed to cM_scos/cM_ssin, >>4 table)
    SIDESTEP_SPEED = f32(30.0)     # field_0x8 = launch speed magnitude
    SIDESTEP_GRAV = f32(-2.4)      # field_0x18 = gravity per frame
    SIDESTEP_LAND_END = f32(5.0)   # field_0x6 = land anim end frame (recovery duration)
    SIDESTEP_LAND_RATE = f32(0.85) # field_0x1C = land anim frame-ctrl rate
    SIDESTEP_LAND_EARLY = f32(1.5) # field_0x28 = getFrame()> threshold for checkNextMode(1)
    # HIO mBackJump (targeted backflip), d_a_player_HIO_data.inc:102. Ballistic backward launch; lands
    # once ground-hit AND the ROLLB anim finishes. Mechanics: knowledge/mechanics/land-movement.md.
    BACKJUMP_SPEED = f32(22.5)     # field_0x10 = mNormalSpeed (backward horizontal)
    BACKJUMP_VY = f32(19.0)        # field_0x14 = speed.y launch
    BACKJUMP_GRAV = f32(-3.0)      # field_0x18 = gravity per frame
    BACKJUMP_ANIM_START = f32(2.0) # field_0x8 = ROLLB frame-ctrl start
    BACKJUMP_ANIM_END = f32(11.0)  # field_0x0 = ROLLB frame-ctrl end (getRate()<0.01 gates the land)
    BACKJUMP_ANIM_RATE = f32(0.8)  # field_0x4 = ROLLB frame-ctrl rate
    BACKJUMP_LAND_END = f32(5.0)   # field_0x2 = land anim end frame (recovery duration)
    BACKJUMP_LAND_RATE = f32(0.8)  # field_0x24 = land anim frame-ctrl rate
    BACKJUMP_LAND_EARLY = f32(2.0) # field_0x30 = getFrame()> threshold for checkNextMode(1)
    # Terminal fall velocity (mAutoJump.field_0x10 global default, d_a_player_HIO_data.inc:116): speed.y
    # is clamped to this after gravity each frame (posMoveFromFootPos 2472). Never reached on a flat hop.
    MAX_FALL = f32(-175.0)
    # The default per-frame gravity, mAutoJump.field_0xC, reset by commonProcInit on EVERY proc
    # change (5826) -- the grounded speed.y at CrrPos time (the hop procs override at entry).
    GRAVITY = f32(-2.5)

    # Wall interaction (ROADMAP Phase W; active only with a `walls=` mesh -- flags stay False
    # without one, leaving every wall-free path byte-identical).
    WALL_SPEED_DOWN = f32(0.6)     # mBasic.field_0x14: setNormalSpeedF wall-hit target *= 1-cos*this
    ROLL_BONK_ANGLE = 5000         # mRoll.field_0x4:  |travel+0x8000 - wallAngleY| bonk/latch window
    ROLL_BONK_FMIN = f32(6.0)      # mRoll.field_0x34: bonk anim-frame window lo
    ROLL_BONK_FMAX = f32(15.0)     # mRoll.field_0x38: bonk anim-frame window hi
    ROLL_BONK_SPEED = f32(10.0)    # mRoll.field_0x3C: speedF floor for the crash
    CRASH_SPEED_MUL = f32(0.4)     # mRoll.field_0x40: crash mNormalSpeed = speedF * this (reversed)
    CRASH_VY = f32(7.0)            # mRoll.field_0x44: crash speed.y launch
    CRASH_ANIM_START = f32(6.0)    # mRoll.field_0x28: ANM_ROLLFMIS start (rate 0 while airborne)
    CRASH_ANIM_END = f32(24.0)     # mRoll.field_0x2:  ANM_ROLLFMIS end (rate<0.01 exit)
    CRASH_ANIM_RATE = f32(0.7)     # mRoll.field_0x24: rate set at the landing
    CRASH_EARLY = f32(20.0)        # mRoll.field_0x30: getFrame()> -> checkNextMode(1) exit
    # Mid-walk sword pull-out: acted-frame delay from the B rising edge to the foot anim-set flip
    # (=5 after the raw B feed, live-pinned). See FootSpeedF.draw_sword + knowledge/model/anim-engine.md.
    DRAW_DELAY = 3
