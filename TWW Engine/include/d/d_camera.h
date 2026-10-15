// d_camera.h - dCamera_c trimmed to the fields and methods the ported camera bodies name
// (d_camera.cpp:675-912, :2617-3293 and on). Field offsets are the decomp's, as documentation
// only: nothing maps this class onto console RAM.
//
// `engine_tbl` takes the address of all twenty algorithms, so all are declared; those not ported
// are stubbed in boundary/stubs.cpp.

#ifndef TWW_PORT_D_CAMERA_H
#define TWW_PORT_D_CAMERA_H

#include "dolphin/types.h"
#include "SSystem/SComponent/c_angle.h"
#include "d/d_cam_param.h"
// A complete type: `mBG` holds two dBgS_CamGndChk.
#include "d/d_bg_s_gnd_chk.h"
#include "d/d_bg_s_lin_chk.h"
#include "global.h"

class fopAc_ac_c;

/// d_com_inf_game.h:2328 and the camera-attention accessors, all at the boundary, declared before
/// the class whose inline members call them. dComIfGp_getPlayer answers the player named with
/// set_dComIfG_player, or NULL.
fopAc_ac_c* dComIfGp_getPlayer(int idx);

void dComIfGp_onCameraAttentionStatus(int idx, u32 status);
void dComIfGp_offCameraAttentionStatus(int idx, u32 status);
u32 dComIfGp_getCameraAttentionStatus(int idx);

/// d_com_inf_game.h, at the boundary.
void dComIfGp_setCameraZoomScale(int idx, f32 scale);

/// d_com_inf_game.h:2594, at the boundary.
void dComIfGp_setCameraZoomForcus(int idx, f32 focus);

/// d_com_inf_game.h:2778, at the boundary: which scope is up, or 0.
u8 dComIfGp_getScopeType();

/// m_Do_graphic.h:63-70, trimmed to the one call subjectCamera makes; recorded at the boundary.
class mDoGph_gInf_c {
public:
    static void offAutoForcus();
};

/// d_com_inf_game.h:2790, at the boundary; the decomp reads the game-info field directly.
f32 dComIfGp_getItemScopeWipeScale();

/// d_com_inf_game.h:102-117, whole.
enum dCamera__AttentionStatus {
    dCamAttnStts_00000001_e = 0x00000001, // just locked on?
    dCamAttnStts_SUBJECT_e = 0x00000002, // First person
    dCamAttnStts_00000004_e = 0x00000004,
    dCamAttnStts_TELESCOPE_LOOK_e = 0x00000008,
    dCamAttnStts_00000010_e = 0x00000010,
    dCamAttnStts_00000020_e = 0x00000020,
    dCamAttnStts_PICTO_BOX_AIM_e = 0x00000040,
    dCamAttnStts_00000080_e = 0x00000080,
    dCamAttnStts_00000100_e = 0x00000100,
    dCamAttnStts_00000400_e = 0x00000400, // manual camera control, as opposed to free camera control?
    dCamAttnStts_00001000_e = 0x00001000, // just pressed c-stick up to enter first person?
    dCamAttnStts_00002000_e = 0x00002000,
};

/// d_camera.h:29-32. `types[mCurType].mStyles[mCurMode]` maps (type, mode) to a style.
struct dCamera__Type {
    /* 0x00 */ char name[24];
    /* 0x18 */ s16 mStyles[20];
};  // Size: 0x40

class dCamera_c;
typedef bool (dCamera_c::*engine_fn)(s32);

/// d_camera.h:49-71, trimmed to `Off()` (at the boundary); the rest is draw state.
class dCamForcusLine {
public:
    bool Off();
};

class dCamera_c {
public:
    /// d_camera.h:97-101.
    struct dCamera_monitoring_things {
        /* 0x00 */ cXyz mPos;
        /* 0x0C */ cXyz field_0x0C;
        /* 0x18 */ int field_0x18;
        /* 0x1C */ f32 field_0x1C;
    };

    /// d_camera.h:103-108.
    struct dCamera_DMC_system {
        /* 0x0 */ u8 field_0x0;
        /* 0x1 */ u8 field_0x1;
        /* 0x2 */ cSAngle field_0x2;
        /* 0x4 */ cSAngle field_0x4;
    };

    /* 0x006 */ cSAngle m006;
    /* 0x008 */ cSGlobe mDirection;
    /* 0x010 */ cXyz mCenter;
    /* 0x01C */ cXyz mEye;
    /* 0x028 */ cXyz mUp;
    /* 0x034 */ cSAngle mBank;
    /* 0x038 */ f32 mFovy;

    /// d_camera.h:141-157. The algorithm's working copy; Run's tail promotes it onto mCenter /
    /// mFovy / mBank through the floor-margin clamp.
    class {
    public:
        /* 0x00 */ cSGlobe mDirection;
        /* 0x08 */ cXyz mCenter;
        /* 0x14 */ cXyz mEye;
        /* 0x20 */ cSAngle mBank;
        /* 0x24 */ f32 mFovy;
    } mViewCache;

    /* 0x068 */ int m068;
    /* 0x070 */ cXyz m070;
    /* 0x06C */ cSAngle mAngleY;
    /* 0x07C */ u32 m07C;
    /* 0x080 */ u32 m080;
    /// d_camera.h:180 and :182. Read only on subjectCamera's minigame arm (m3C0 == 2); nothing
    /// in the port writes them.
    /* 0x0EC */ cXyz mExtendedPos;
    /* 0x0FA */ s16 m0FA;
    /* 0x100 */ u8 m100;
    /* 0x101 */ u8 m101;
    /* 0x102 */ u8 m102;
    /* 0x108 */ u32 m108;
    /* 0x10C */ int m10C;
    /* 0x110 */ u8 m110;
    /* 0x118 */ u32 m118;
    /* 0x11C */ u32 m11C;
    /* 0x120 */ int mCameraID;
    /* 0x124 */ int mPadId;
    /* 0x128 */ fopAc_ac_c* mpPlayerActor;
    /* 0x12C */ fopAc_ac_c* mpLockonTarget;
    /* 0x130 */ fpc_ProcID mLockOnActorId;

    /// d_camera.h:200. Nothing in the port writes it (checkForceLockTarget is a stub).
    /* 0x134 */ fopAc_ac_c* mpLockonActor;
    /* 0x138 */ int mForceLockTimer;
    /* 0x13C */ int mCurMode;
    /* 0x140 */ int mNextMode;
    /* 0x144 */ int m144;
    /* 0x148 */ cSAngle m148;
    /* 0x14C */ f32 m14C;
    /// Written by updatePad. The stick deltas are `new - last` and the trigger deltas
    /// `last - new`, as in the decomp.
    /* 0x154 */ f32 mStickMainPosXLast;
    /* 0x158 */ f32 mStickMainPosYLast;
    /* 0x15C */ f32 mStickMainValueLast;
    /* 0x160 */ f32 mStickMainPosXDelta;
    /* 0x164 */ f32 mStickMainPosYDelta;
    /* 0x168 */ f32 mStickMainValueDelta;
    /* 0x16C */ f32 mStickCPosXLast;
    /* 0x170 */ f32 mStickCPosYLast;
    /* 0x174 */ f32 mStickCValueLast;
    /* 0x178 */ f32 mStickCPosXDelta;
    /* 0x17C */ f32 mStickCPosYDelta;
    /* 0x180 */ f32 mStickCValueDelta;

    /// m184 is nextMode's C-stick-up latch; m254's two bits are what nextMode and onModeChange
    /// pass on to updateMonitor.
    /* 0x184 */ int m184;

    /// updatePad's trigger edges: m19A is "L was over mCamSetup.m0A0 last frame" and m19B is up
    /// for one frame per press. m1A6 / m1A7 are the same for R.
    /* 0x190 */ f32 mTriggerLeftLast;
    /* 0x194 */ f32 mTriggerLeftDelta;
    /* 0x198 */ u8 mHoldLockL;
    /* 0x199 */ u8 mTrigLockL;
    /* 0x19A */ u8 m19A;
    /* 0x19B */ u8 m19B;
    /* 0x19C */ f32 mTriggerRightLast;
    /* 0x1A0 */ f32 mTriggerRightDelta;
    /* 0x1A4 */ u8 mHoldLockR;
    /* 0x1A5 */ u8 mTrigLockR;
    /* 0x1A6 */ u8 m1A6;
    /* 0x1A7 */ u8 m1A7;

    /// mHoldZ and mTrigZ read the B bits; the decomp's names are kept.
    /* 0x1A8 */ u8 mHoldX;
    /* 0x1A9 */ u8 mTrigX;
    /* 0x1AA */ u8 mHoldY;
    /* 0x1AB */ u8 mTrigY;
    /* 0x1AC */ u8 mHoldZ;
    /* 0x1AD */ u8 mTrigZ;
    /* 0x1AE */ u8 m1AE;
    /* 0x1B0 */ dCamForcusLine mForcusLine;
    /* 0x220 */ dCamera_DMC_system mDMCSystem;
    /* 0x228 */ dCamera_monitoring_things mMonitor;
    /* 0x248 */ int m248[3];
    /* 0x254 */ int m254;
    /* 0x258 */ int m258;

    /// d_camera.h:112-124, whole. The queries are run by checkGroundInfo.
    struct BG {
        struct {
            /* 0x00 */ bool m00;
            /* 0x04 */ dBgS_CamGndChk m04;
            /* 0x58 */ f32 m58;
        } m00;
        struct {
            /* 0x00 */ bool m00;
            /* 0x04 */ dBgS_CamGndChk m04;
            /* 0x58 */ f32 m58;
        } m5C;
    };  // Size: 0xB8

    /* 0x25C */ BG mBG;

    /// d_camera.h:252-272, written by checkGroundInfo. On an empty world both ground crosses
    /// miss: the m58 heights are -G_CM3D_F_INF, m360 is 0 and the room is 0x1FF. m314 / m318 are
    /// the sea, and daSea_ChkArea is a stub returning false.
    /* 0x314 */ u8 m314;
    /* 0x318 */ f32 m318;
    /* 0x31C */ u8 m31C;
    /* 0x31D */ u8 m31D;
    /* 0x320 */ cXyz m320;
    /* 0x32C */ cXyz m32C;
    /* 0x338 */ cSAngle m338;
    /* 0x33A */ cSAngle m33A;
    /* 0x33C */ fopAc_ac_c* m33C;
    /* 0x350 */ int m350;
    /* 0x354 */ f32 m354;
    /* 0x358 */ int mRoomNo;
    /* 0x35C */ int mRoomMapToolCameraIdx;
    /* 0x360 */ u8 m360;
    /* 0x364 */ int m364;
    /* 0x368 */ f32 m368;
    /* 0x36C */ cXyz m36C;

    /// d_camera.h:273-379, trimmed to the arms the port runs; still a union so the copied
    /// `mWork.follow.mXXX` sites need no edit. It persists between frames and is not seeded at
    /// construction, so a gate must seed it or run the entry frame.
    union Work {
        struct {
            /* 0x378 */ int m378;
            /* 0x37C */ int m37C;
            /* 0x380 */ f32 m380;
            /* 0x384 */ f32 m384;
            /* 0x388 */ int m388;
            /* 0x38C */ int m38C;
            /* 0x390 */ s16 m390;
            /* 0x392 */ s16 m392;
            /* 0x394 */ f32 m394;
            /* 0x398 */ f32 m398;
            /* 0x39C */ f32 m39C;
            /* 0x3A0 */ f32 m3A0;
            /* 0x3A4 */ f32 m3A4;
            /* 0x3A8 */ f32 m3A8;
            /* 0x3AC */ f32 m3AC;
            /* 0x3B0 */ f32 m3B0;
            /* 0x3B4 */ int m3B4;
            /* 0x3B8 */ f32 m3B8;
            /* 0x3BC */ f32 m3BC;
            /* 0x3C0 */ cXyz m3C0;
            /* 0x3CC */ cXyz m3CC;
            /* 0x3D8 */ u8 m3D8;
            /* 0x3D9 */ u8 m3D9;
            /* 0x3DA */ u8 m3DA;
            /* 0x3DB */ u8 m3DB;
            /* 0x3DC */ f32 m3DC;
            /* 0x3E0 */ f32 m3E0;
            /* 0x3E4 */ f32 m3E4;
            /* 0x3E8 */ f32 m3E8;
            /* 0x3EC */ f32 m3EC;
            /* 0x3F0 */ f32 m3F0;
            /* 0x3F4 */ u8 m3F4[0x3F8 - 0x3F4];
        } follow;

        /// manualCamera's arm, as on the pinned decomp branch. Seeded by its `m11C == 0` arms.
        struct Manual {
            /* 0x378 */ int m378;
            /* 0x37C */ cXyz m37C;
            /* 0x388 */ cXyz m388;
            /* 0x394 */ f32 m394;
            /* 0x398 */ f32 m398;
            /* 0x39C */ u8 m39C[0x3A0 - 0x39C];
            /* 0x3A0 */ u8 m3A0;
            /* 0x3A1 */ u8 m3A1[0x3A4 - 0x3A1];
            /* 0x3A4 */ f32 m3A4;
            /* 0x3A8 */ cSGlobe m3A8;
            /* 0x3B0 */ f32 m3B0;
            /* 0x3B4 */ f32 m3B4;
            /* 0x3B8 */ int m3B8;
        } manual;

        /// d_camera.h:306-330, whole. Seeded when `m108 == 0`.
        struct {
            /* 0x378 */ int m378;
            /* 0x37C */ u8 m37C;
            /* 0x37D */ u8 m37D;
            /* 0x380 */ int m380;
            /* 0x384 */ f32 m384;
            /* 0x388 */ f32 m388;
            /* 0x38C */ f32 m38C;
            /* 0x390 */ f32 m390;
            /* 0x394 */ f32 m394;
            /* 0x398 */ f32 m398;
            /* 0x39C */ f32 m39C;
            /* 0x3A0 */ f32 m3A0;
            /* 0x3A4 */ u8 m3A4[0x3A8 - 0x3A4];
            /* 0x3A8 */ int m3A8;
            /* 0x3AC */ u8 m3AC[0x3B8 - 0x3AC];
            /* 0x3B8 */ cSAngle m3B8;
            /* 0x3BA */ cSAngle m3BA;
            /* 0x3BC */ u8 m3BC;
            /* 0x3BD */ u8 m3BD;
            /* 0x3BE */ u8 m3BE;
            /* 0x3BF */ u8 m3BF;
            /* 0x3C0 */ u32 m3C0;
            /* 0x3C4 */ int m3C4;
        } subject;
    } mWork;

    /* 0x50C */ u32 mEventFlags;
    /* 0x510 */ int mCurStyle;
    /* 0x514 */ int m514;
    /* 0x518 */ int mCurType;
    /* 0x51C */ int mNextType;
    /* 0x530 */ int m530;
    /* 0x534 */ s16 m534;
    /* 0x536 */ s16 m536;
    /* 0x538 */ f32 m538;
    /* 0x53C */ f32 m53C;
    /* 0x540 */ f32 m540;
    /* 0x600 */ int mTrimTypeForce;
    /* 0x60C */ dCamSetup_c mCamSetup;
    /* 0x750 */ dCamParam_c mCamParam;

    /// d_camera.h:448-458, the four type ids nextMode's mode-12 arm names. Set by initialize(),
    /// which the port does not run, so they are uninitialised. mCamTypeRestrict is
    /// `#if VERSION > VERSION_DEMO` in the decomp and is declared unconditionally here.
    /* 0x760 */ int mCamTypeEvent;
    /* 0x76C */ int mCamTypeBoat;
    /* 0x770 */ int mCamTypeBoatBattle;
    /* 0x77C */ int mCamTypeRestrict;
    /* 0x780 */ u8 m780;
    /* 0x784 */ u8 m784;
    /* 0x785 */ u8 m785;
    /* 0x787 */ u8 m787;
    /* 0x788 */ u8 m788;
    /* 0x78B */ u8 m78B;

public:
    /// d_camera.h:614-616.
    bool chkFlag(u32 flag) { return (mEventFlags & flag) ? true : false; }
    BOOL setFlag(u32 flag) { return mEventFlags |= flag; }
    void clrFlag(u32 flag) { mEventFlags &= ~flag; }

    /// d_camera.h:634-639. They post to the game-info block, keyed by mCameraID, at the boundary.
    void setComStat(u32 i_flag) { dComIfGp_onCameraAttentionStatus(mCameraID, i_flag); }
    void setComZoomScale(f32 i_scale) { dComIfGp_setCameraZoomScale(mCameraID, i_scale); }
    void setComZoomForcus(f32 i_focus) { dComIfGp_setCameraZoomForcus(mCameraID, i_focus); }
    void clrComStat(u32 i_flag) { dComIfGp_offCameraAttentionStatus(mCameraID, i_flag); }
    bool getComStat(u32 i_flag) { return dComIfGp_getCameraAttentionStatus(mCameraID) & i_flag; }

    /// d_camera.cpp:144-146, trimmed: most of `initialize` is cut; retain its
    /// water-only background query setup (224-225). `mCamParam(0)` is required (no default
    /// constructor). The player comes from get_player_actor's inner call, so it is NULL until a
    /// player is named.
    dCamera_c() : mCamParam(0) {
        mpPlayerActor = dComIfGp_getPlayer(0);
        mBG.m00.m04.OffNormalGrp();
        mBG.m00.m04.OnWaterGrp();
    }

    /// Copied, src/d/d_camera.cpp.
    bool Run();

    /// The mode sequencer, copied.
    int nextMode(s32);
    bool onModeChange(s32, s32);
    bool onStyleChange(s32, s32);

    static engine_fn engine_tbl[];
    static const int type_num;
    static const dCamera__Type types[];

    // ---- the boundary ----------------------------------------------------------------------
    // Run's helpers and the dispatch targets; those not ported are defined in boundary/stubs.cpp.

    void updatePad();
    void updateMonitor();
    void Att();
    bool checkForceLockTarget();
    int nextType(s32);
    bool onTypeChange(s32, s32);
    cSAngle getDMCAngle(cSAngle);
    int defaultTriming();
    cSAngle forwardCheckAngle();
    /// Copied. It is what commits `mDirection`.
    bool bumpCheck(u32);
    /// Stubs, unreached on open floor.
    cXyz compWallMargin(cXyz*, f32);
    f32 radiusActorInSight(fopAc_ac_c*, fopAc_ac_c*);
    void checkSpecialArea();
    /// Copied.
    void checkGroundInfo();
    f32 shakeCamera();

    /// d_camera.h:653, `current.pos.y`. Defined in stubs.cpp because this header cannot include
    /// the actor (d_a_player_main.h includes this one); it is not counted as boundary.
    f32 footHeightOf(fopAc_ac_c* i_actor);

    /// d_camera.h:520. Boundary: it needs the collision-check system (dCcS), which is not ported.
    /// Reached only when m360 != 0; it bumps the camera boundary counter.
    u32 lineCollisionCheckBush(cXyz*, cXyz*);

    /// d_camera.h:523. Boundary; reached only for the telescope mode (0xe).
    void setView(f32, f32, f32, f32);

    // The five actor queries, groundHeight, the lineBGCheck overloads, getWaterSurfaceHeight,
    // relationalPos and setDMCAngle are copied. attention_info is never written in the port, and
    // daSea_ChkArea / daSea_calcWave are stubs. relationalPos carries the PR #1193 call-site fix,
    // since the port's cSGlobe setters are swapped against the pinned decomp.
    cSAngle calcPeepAngle();
    /// src/d/d_camera.cpp:1577-1589, :1591-1602, :1645-1649 and :3296-3307.
    cSAngle directionOf(fopAc_ac_c*);
    cXyz positionOf(fopAc_ac_c*);
    cXyz attentionPos(fopAc_ac_c*);
    cXyz eyePos(fopAc_ac_c*);
    f32 heightOf(fopAc_ac_c*);
    cXyz relationalPos(fopAc_ac_c*, cXyz*);
    cXyz relationalPos(fopAc_ac_c*, fopAc_ac_c*, cXyz*, f32);
    void setDMCAngle();
    f32 groundHeight(cXyz*);
    bool lineBGCheck(cXyz*, cXyz*, dBgS_LinChk*, u32);
    bool lineBGCheck(cXyz*, cXyz*, u32);
    bool lineBGCheckBoth(cXyz*, cXyz*, dBgS_LinChk*, u32);
    f32 getWaterSurfaceHeight(cXyz*);

    /// d_camera.h:464. The player's one question of the camera (procCrouch's first test). Stub.
    bool ChangeModeOK(s32 param_1);

    /// d_camera.h:537. Copied.
    bool CalcSubjectAngle(s16*, s16*);

    bool followCamera2(s32);
    bool followCamera(s32);
    bool lockonCamera(s32);
    bool talktoCamera(s32);
    bool subjectCamera(s32);
    bool towerCamera(s32);
    bool crawlCamera(s32);
    bool hookshotCamera(s32);
    bool tornadoCamera(s32);
    bool rideCamera(s32);
    bool hungCamera(s32);
    bool vomitCamera(s32);
    bool shieldCamera(s32);
    bool manualCamera(s32);
    bool nonOwnerCamera(s32);
    bool fixedFrameCamera(s32);
    bool fixedPositionCamera(s32);
    bool eventCamera(s32);
    bool demoCamera(s32);
    bool letCamera(s32);
};

/// d_camera.h:686. The one dCamera_c the game has.
dCamera_c* dCam_getBody();

/// d_com_inf_game.h:3732 and :3772, spelled as the decomp spells them. The demo camera is never
/// dereferenced.
class dDemo_camera_c;
int dComIfGp_evmng_cameraPlay();
dDemo_camera_c* dComIfGp_demo_getCamera();

/// d_com_inf_game.h, trimmed to the two methods nextMode calls.
class dAttention_c {
public:
    /// d_attention.h:216: Lockon is `LockonTruth() || chkFlag(AttnFlag_20000000)`. Both at the
    /// boundary; the attention system is not ported.
    bool Lockon();
    bool LockonTruth();
};
dAttention_c& dComIfGp_getAttention();

/// dComIfGp_checkPlayerStatus0/1 and dComIfGp_getMiniGameType are declared in d_a_player_main.h.

/// d_camera.cpp:74-88, not copied: boundary, reached only behind `chkFlag(0x200000)`.
BOOL push_any_key(int pad);

/// m_Do_audio.h:161. Returns JAISound** in the decomp; the result is discarded.
void mDoAud_seStart(u32 i_seNum);

/// d_a_obj_pirateship.h. The ship's deck height when m530 says Link is on it.
namespace daObjPirateship {
f32 getShipOffsetY(s16* x, s16* z, f32 r);
}

/// f_pc_name.h:68. The one actor name a copied body compares against.
enum { fpcNm_Obj_Pirateship_e = 0x3B };

/// d_com_inf_game.h, trimmed to the one method checkGroundInfo names. Collision checking is not
/// ported; reached only behind `if (m360)` and `if (m364)`.
class dCcS {
public:
    void GetMassCamTopPos(cXyz* o_pos);
};
dCcS* dComIfG_Ccsp();

/// d_a_npc_cb1.h:105, d_a_npc_md.h:332/335 and d_a_npc_kamome.h:104, each trimmed to the static
/// followCamera reads. At the boundary: no NPC is ported, and each is false while that NPC is not
/// loaded.
class daNpc_Cb1_c {
public:
    static bool isFlying();
};

class daNpc_Md_c {
public:
    static bool isFlying();
    static bool isMirror();
};

class daNpc_kam_c {
public:
    static bool m_hyoi_kamome;
};

/// c_math.h:28, at the boundary with cM_rnd / cM_rndF: the RNG seed is a file static the port
/// cannot read.
float cM_rndFX(float max);

#endif
