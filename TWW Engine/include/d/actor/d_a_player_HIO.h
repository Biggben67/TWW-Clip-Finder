// d_a_player_HIO.h - the player HIO tables the ported bodies read, trimmed from the decomp's
// include/d/actor/d_a_player_HIO.h. Each carried table keeps the decomp's layout; tables no
// ported body reads are left out. The data is generated/d/actor/d_a_player_HIO_data.inc, read out
// of the shipped DOL and checked against the decomp's initialiser and symbol sizes.
//
// A `field_0xNN` is renamed only where a decomp call site settles its meaning
// (d_a_player_main.cpp line numbers):
//   6807  setSingleMoveAnime(ANM_ROLLF,    mAnmRate,  param_1,             mAnmEndFrame,      mAnmMorf)
//   6880  setSingleMoveAnime(ANM_ROLLFMIS, 0.0f,      mCrashAnmStartFrame, mCrashAnmEndFrame, mCrashAnmMorf)
//         ...against setSingleMoveAnime(anm, rate, start, end, i_morf) at 12788.
//   4311  procFrontRoll_init(mAnmStartFrame)
//   6808  mNormalSpeed = speedF * mSpeedMul + mSpeedAdd
//   6812  mNormalSpeed < mSpeedMin  /  6849  mNormalSpeed -= mSpeedMin
//   6853  getFrame() > mEarlyEndFrame
//   6826, 6862  cLib_distanceAngleS(...) <= mWallHitAngleRange
//   6856  speedF >= mWallHitSpeedMin  /  6863-4  mWallHitFrameMin <= getFrame() <= mWallHitFrameMax
//   6881  mNormalSpeed = speedF * mCrashSpeedMul   /  6882  speed.y = mCrashSpeedY
//   6906  getFrame() > mCrashEarlyEndFrame
//   6913  setRate(mCrashLandAnmRate)
//   3326, 4432, 12194  move_c1 field_0x18 -> mMaxNormalSpeed
//   2816, 6810, 6818, 6954, 10636  move_c1 field_0x80, only under checkHeavyStateOn()

#ifndef TWW_PORT_D_A_PLAYER_HIO_H
#define TWW_PORT_D_A_PLAYER_HIO_H

#include "dolphin/types.h"

class daPy_HIO_move_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0A */ s16 field_0xA;
    /* 0x0C */ s16 field_0xC;
    /* 0x0E */ s16 field_0xE;
    /* 0x10 */ s16 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 mMaxNormalSpeed;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
    /* 0x54 */ f32 field_0x54;
    /* 0x58 */ f32 field_0x58;
    /* 0x5C */ f32 field_0x5C;
    /* 0x60 */ f32 field_0x60;
    /* 0x64 */ f32 field_0x64;
    /* 0x68 */ f32 field_0x68;
    /* 0x6C */ f32 field_0x6C;
    /* 0x70 */ f32 field_0x70;
    /* 0x74 */ f32 field_0x74;
    /* 0x78 */ f32 field_0x78;
    /* 0x7C */ f32 field_0x7C;
    /* 0x80 */ f32 mHeavyStateScale;
    /* 0x84 */ f32 field_0x84;
};  // Size: 0x88

class daPy_HIO_move_c0 {
public:
    static daPy_HIO_move_c1 const m;
};

class daPy_HIO_basic_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 mAnmMorf;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
};  // Size: 0x20

class daPy_HIO_basic_c0 {
public:
    static daPy_HIO_basic_c1 const m;
};

class daPy_HIO_atnMove_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 mMaxNormalSpeed;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
};  // Size: 0x30

class daPy_HIO_atnMove_c0 {
public:
    static daPy_HIO_atnMove_c1 const m;
};

/// The backward table (setSpeedAndAngleAtnBack), 0x34 not 0x30: field_0x2C / field_0x30 are
/// setBlendAtnMoveAnime's two cosine thresholds for forward / backward / side.
class daPy_HIO_atnMoveB_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_atnMoveB_c0 {
public:
    static daPy_HIO_atnMoveB_c1 const m;
};

/// setBlendMoveAnime's ice-slip arm (unreached here; copied, so the constants are real).
class daPy_HIO_iceSlip_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0A */ s16 field_0xA;
    /* 0x0C */ s16 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
    /* 0x54 */ f32 field_0x54;
    /* 0x58 */ f32 field_0x58;
    /* 0x5C */ f32 field_0x5C;
    /* 0x60 */ f32 field_0x60;
    /* 0x64 */ f32 field_0x64;
    /* 0x68 */ f32 field_0x68;
    /* 0x6C */ f32 field_0x6C;
    /* 0x70 */ f32 field_0x70;
};  // Size: 0x74

class daPy_HIO_iceSlip_c0 {
public:
    static daPy_HIO_iceSlip_c1 const m;
};

class daPy_HIO_slip_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 mSpeedRatioMin;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
};  // Size: 0x24

class daPy_HIO_slip_c0 {
public:
    static daPy_HIO_slip_c1 const m;
};

class daPy_HIO_slide_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 mFrontAngleRange;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
};  // Size: 0x4C

class daPy_HIO_slide_c0 {
public:
    static daPy_HIO_slide_c1 const m;
};

class daPy_HIO_roll_c1 {
public:
    /* 0x00 */ s16 mAnmEndFrame;
    /* 0x02 */ s16 mCrashAnmEndFrame;
    /* 0x04 */ s16 mWallHitAngleRange;
    /* 0x08 */ f32 mAnmRate;
    /* 0x0C */ f32 mAnmStartFrame;
    /* 0x10 */ f32 mEarlyEndFrame;
    /* 0x14 */ f32 mAnmMorf;
    /* 0x18 */ f32 mSpeedMul;
    /* 0x1C */ f32 mSpeedAdd;
    /* 0x20 */ f32 mSpeedMin;
    /* 0x24 */ f32 mCrashLandAnmRate;
    /* 0x28 */ f32 mCrashAnmStartFrame;
    /* 0x2C */ f32 mCrashAnmMorf;
    /* 0x30 */ f32 mCrashEarlyEndFrame;
    /* 0x34 */ f32 mWallHitFrameMin;
    /* 0x38 */ f32 mWallHitFrameMax;
    /* 0x3C */ f32 mWallHitSpeedMin;
    /* 0x40 */ f32 mCrashSpeedMul;
    /* 0x44 */ f32 mCrashSpeedY;
};  // Size: 0x48

class daPy_HIO_roll_c0 {
public:
    static daPy_HIO_roll_c1 const m;
};

/// d_a_player_HIO.h:1371-1401. field_0x18 is the crouch anim rate (0.8), field_0x1C its morf.
class daPy_HIO_crouch_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0A */ s16 field_0xA;
    /* 0x0C */ s16 field_0xC;
    /* 0x0E */ s16 field_0xE;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
};  // Size: 0x50

class daPy_HIO_crouch_c0 {
public:
    static daPy_HIO_crouch_c1 const m;
};

/// d_a_player_HIO.h:116-143, verbatim. procCutA's facing chase reads field_0x0/0x2/0x4.
class daPy_HIO_turn_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6; // 0x4
    /* 0x08 */ s16 field_0x8; // 0x1000
    /* 0x0A */ s16 field_0xA; // 0x200
    /* 0x0C */ s16 field_0xC;
    /* 0x0E */ s16 field_0xE;
    /* 0x10 */ s16 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
};  // Size: 0x40

class daPy_HIO_turn_c0 {
public:
    static daPy_HIO_turn_c1 const m;
};

/// d_a_player_HIO.h:593-615, verbatim - the backflip, read by both procs of the pair.
/// Jump: field_0x0 anim end, 0x4/0x8/0xC the ROLLB clock, 0x10 mNormalSpeed, 0x14 speed.y,
/// 0x18 gravity, 0x1C/0x20 the procFall drop and its argument.
/// Landing: field_0x2 anim end, 0x24/0x28/0x2C the ROLLBLAND clock, 0x30 the checkNextMode(1) frame.
class daPy_HIO_backJump_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_backJump_c0 {
public:
    static daPy_HIO_backJump_c1 const m;
};

/// d_a_player_HIO.h:618-640, verbatim, for one field: commonProcInit sets
/// `gravity = mAutoJump.field_0xC` (-2.5, d_a_player_main.cpp:5813), the default gravity.
class daPy_HIO_autoJump_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
};  // Size: 0x44

class daPy_HIO_autoJump_c0 {
public:
    static daPy_HIO_autoJump_c1 const m;
};

/// d_a_player_HIO.h:1261-1284, verbatim - the sidehop, read by both procs of the pair.
/// Hop: field_0x0 lock-on tracking switch, 0x2 launch angle, 0x4/0xC/0x10/0x14 the ATNJL/ATNJR
/// clock, 0x8 launch speed, 0x18 gravity, 0x2C/0x30 the procFall drop.
/// Landing: field_0x6/0x1C/0x20/0x24 the clock, 0x28 the checkNextMode(1) frame.
class daPy_HIO_sideStep_c1 {
public:
    /* 0x00 */ u8 field_0x0;
    /* 0x01 */ u8 field_0x1;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_sideStep_c0 {
public:
    static daPy_HIO_sideStep_c1 const m;
};

/// d_a_player_HIO.h:436-459, verbatim - the jump slash. procJumpCut_init's argument picks
/// field_0x8..0x1C (0, ground, d_a_player_main.cpp:4176) or field_0x20..0x34 (1, midair, :4014):
/// anim rate, start, morf, mNormalSpeed, speed.y, gravity. Landing: field_0x38..0x40 and 0x2 its
/// animation, 0x4 the post-anim hold. Shared: 0x44 the early-end poll, 0x48/0x4C the cut-sound
/// window.
class daPy_HIO_cutJump_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
};  // Size: 0x50

class daPy_HIO_cutJump_c0 {
public:
    static daPy_HIO_cutJump_c1 const m;
};

/// d_a_player_HIO.h:693-718, verbatim, for procJumpCutLand_init: the drop
/// `m35F0 - current.pos.y` against field_0x10 (60.0) and field_0x14 (20.0), each scaled by 100.0.
class daPy_HIO_fall_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0A */ s16 field_0xA;
    /* 0x0C */ s16 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
};  // Size: 0x54

class daPy_HIO_fall_c0 {
public:
    static daPy_HIO_fall_c1 const m;
};

/// d_a_player_HIO.h:726-761, verbatim, for posMoveFromFootPos's unreached SWIM_MOVE arm:
/// field_0x60 (0.4) the stroke phase, field_0x7C the swim-timer term.
class daPy_HIO_swim_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
    /* 0x54 */ f32 field_0x54;
    /* 0x58 */ f32 field_0x58;
    /* 0x5C */ f32 field_0x5C;
    /* 0x60 */ f32 field_0x60;
    /* 0x64 */ f32 field_0x64;
    /* 0x68 */ f32 field_0x68;
    /* 0x6C */ f32 field_0x6C;
    /* 0x70 */ f32 field_0x70;
    /* 0x74 */ f32 field_0x74;
    /* 0x78 */ f32 field_0x78;
    /* 0x7C */ f32 field_0x7C;
};  // Size: 0x80

class daPy_HIO_swim_c0 {
public:
    static daPy_HIO_swim_c1 const m;
};

/// d_a_player_HIO.h:882-915, verbatim, for setBgCheckParam's unreached ModeFlg_WHIDE arm:
/// field_0x50 is the first wall cylinder's radius.
class daPy_HIO_wall_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0A */ s16 field_0xA;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
    /* 0x54 */ f32 field_0x54;
    /* 0x58 */ f32 field_0x58;
    /* 0x5C */ f32 field_0x5C;
    /* 0x60 */ f32 field_0x60;
    /* 0x64 */ f32 field_0x64;
};  // Size: 0x68

class daPy_HIO_wall_c0 {
public:
    static daPy_HIO_wall_c1 const m;
};

/// d_a_player_HIO.h:1221-1225, verbatim. field_0x0 (30) is the stun after a hard landing
/// (mDamageWaitTimer). daPy_HIO_dam_c0's four damage tables are left out.
class daPy_HIO_dam_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
};

class daPy_HIO_dam_c0 {
public:
    static daPy_HIO_dam_c1 const m;
};

/// d_a_player_HIO.h:145-166, verbatim - the slash (procCutA).
class daPy_HIO_cutA_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_cutA_c0 {
public:
    static daPy_HIO_cutA_c1 const m;
};

/// d_a_player_HIO.h:168-184, verbatim - the forward thrust.
class daPy_HIO_cutF_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_cutF_c0 {
public:
    static daPy_HIO_cutF_c1 const m;
};

/// d_a_player_HIO.h:191-207, verbatim - the right slash.
class daPy_HIO_cutR_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_cutR_c0 {
public:
    static daPy_HIO_cutR_c1 const m;
};

/// d_a_player_HIO.h:214-230, verbatim - the left slash.
class daPy_HIO_cutL_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
};  // Size: 0x34

class daPy_HIO_cutL_c0 {
public:
    static daPy_HIO_cutL_c1 const m;
};

/// d_a_player_HIO.h:237-252, verbatim - the first combo ender, 0x30: field_0x0 is the anim end
/// and field_0x2 the post-anim hold (the basic cuts keep their end at field_0x2).
class daPy_HIO_cutEA_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
};  // Size: 0x30

class daPy_HIO_cutEA_c0 {
public:
    static daPy_HIO_cutEA_c1 const m;
};

/// d_a_player_HIO.h:259-274, verbatim - the second combo ender, the same 0x30 shape.
class daPy_HIO_cutEB_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
};  // Size: 0x30

class daPy_HIO_cutEB_c0 {
public:
    static daPy_HIO_cutEB_c1 const m;
};

/// d_a_player_HIO.h:352-386, verbatim - the spin attack. field_0x0 anim end (21), field_0x2 exit
/// countdown (1); field_0x8 (2.0) / field_0xC (5.0) the two start frames procCutTurn_init picks.
class daPy_HIO_cutTurn_c1 {
public:
    /* 0x00 */ s16 field_0x0;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ f32 field_0x4;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
    /* 0x2C */ f32 field_0x2C;
    /* 0x30 */ f32 field_0x30;
    /* 0x34 */ f32 field_0x34;
    /* 0x38 */ f32 field_0x38;
    /* 0x3C */ f32 field_0x3C;
    /* 0x40 */ f32 field_0x40;
    /* 0x44 */ f32 field_0x44;
    /* 0x48 */ f32 field_0x48;
    /* 0x4C */ f32 field_0x4C;
    /* 0x50 */ f32 field_0x50;
    /* 0x54 */ f32 field_0x54;
    /* 0x58 */ f32 field_0x58;
    /* 0x5C */ f32 field_0x5C;
    /* 0x60 */ f32 field_0x60;
    /* 0x64 */ f32 field_0x64;
    /* 0x68 */ f32 field_0x68;
    /* 0x6C */ f32 field_0x6C;
    /* 0x70 */ f32 field_0x70;
    /* 0x74 */ f32 field_0x74;
};  // Size: 0x78

class daPy_HIO_cutTurn_c0 {
public:
    static daPy_HIO_cutTurn_c1 const m;
};

/// d_a_player_HIO.h:392-407, verbatim - the spin's steered hold (procCutTurnMove). field_0x18 /
/// field_0x20 the wind-up anim rates, field_0x1C / field_0x24 their morfs, field_0x28 the blend
/// floor `m3598 = 1.0f - ((1.0f - field_0x28) * speedRatio)`.
class daPy_HIO_cutTurnR_c1 {
public:
    /* 0x00 */ u8 field_0x0;
    /* 0x01 */ u8 field_0x1;
    /* 0x02 */ s16 field_0x2;
    /* 0x04 */ s16 field_0x4;
    /* 0x06 */ s16 field_0x6;
    /* 0x08 */ s16 field_0x8;
    /* 0x0C */ f32 field_0xC;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ f32 field_0x18;
    /* 0x1C */ f32 field_0x1C;
    /* 0x20 */ f32 field_0x20;
    /* 0x24 */ f32 field_0x24;
    /* 0x28 */ f32 field_0x28;
};  // Size: 0x2C

class daPy_HIO_cutTurnR_c0 {
public:
    static daPy_HIO_cutTurnR_c1 const m;
};

class daPy_HIO_cut_c1 {
public:
    s16 field_0x0, field_0x2, field_0x4, field_0x6;
    f32 field_0x8, field_0xC, field_0x10, field_0x14, field_0x18, field_0x1C;
    f32 field_0x20, field_0x24, field_0x28, field_0x2C, field_0x30, field_0x34;
    f32 field_0x38, field_0x3C, field_0x40, field_0x44, field_0x48, field_0x4C;
    f32 field_0x50, field_0x54, field_0x58, field_0x5C, field_0x60, field_0x64, field_0x68;
};

/// The common sword table includes the equip/unequip animation parameters.
class daPy_HIO_cut_c0 {
public:
    static daPy_HIO_cut_c1 const m;
    static daPy_HIO_cutA_c0 const mCutA;
    static daPy_HIO_cutF_c0 const mCutF;
    static daPy_HIO_cutR_c0 const mCutR;
    static daPy_HIO_cutL_c0 const mCutL;
    static daPy_HIO_cutEA_c0 const mCutEA;
    static daPy_HIO_cutEB_c0 const mCutEB;
    static daPy_HIO_cutTurn_c0 const mCutTurn;
    static daPy_HIO_cutTurnR_c0 const mCutTurnR;
    static daPy_HIO_cutJump_c0 const mCutJump;
};

/// Trimmed: the decomp's daPy_HIO_c has one member per proc family (d_a_player_main.h:371), each an
/// independent static, so leaving families out moves nothing.
class daPy_HIO_c {
public:
    daPy_HIO_basic_c0 mBasic;
    daPy_HIO_move_c0 mMove;
    daPy_HIO_atnMove_c0 mAtnMove;
    daPy_HIO_atnMoveB_c0 mAtnMoveB;
    daPy_HIO_slip_c0 mSlip;
    daPy_HIO_iceSlip_c0 mIceSlip;
    daPy_HIO_slide_c0 mSlide;
    daPy_HIO_roll_c0 mRoll;
    daPy_HIO_crouch_c0 mCrouch;
    daPy_HIO_turn_c0 mTurn;
    daPy_HIO_backJump_c0 mBackJump;
    daPy_HIO_autoJump_c0 mAutoJump;
    daPy_HIO_sideStep_c0 mSideStep;
    daPy_HIO_cut_c0 mCut;
    daPy_HIO_fall_c0 mFall;
    daPy_HIO_swim_c0 mSwim;
    daPy_HIO_wall_c0 mWall;
    daPy_HIO_dam_c0 mDam;
};

#endif
