// d_a_player_main.h - daPy_lk_c trimmed to the fields and methods the ported bodies name.
// Field offsets are the decomp's and agree with the JP disassembly where the ported procs touch
// them; they are documentation, not layout (nothing maps this class onto console RAM).
//
// Everything past `// ---- the boundary ----` is a stub, defined in boundary/stubs.cpp.

#ifndef TWW_PORT_D_A_PLAYER_MAIN_H
#define TWW_PORT_D_A_PLAYER_MAIN_H

#include "dolphin/types.h"
#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "m_Do/m_Do_ext.h"
#include "global.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "d/actor/LkAnm.h"
#include "d/actor/LinkJnt.h"
#include "d/actor/d_a_player_mode_flg.h"
#include "m_Do/m_Do_mtx.h"
#include "d/d_bg_s_lin_chk.h"
#include "SSystem/SComponent/c_m3d_g_pla.h"
#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_math.h"
#include "JSystem/JMath/JMath.h"
#include "d/d_bg_s_acch.h"
#include "d/d_bg_s.h"
#include "d/d_bg_s_gnd_chk.h"
#include "d/actor/d_a_player_HIO.h"
#include "d/d_camera.h"


/// daPy_FLG0 / daPy_FLG1 / daPy_RFLG0 - picked out of d_a_player.h by name, not typed here.
#include "d/actor/daPy_flags.inc"

/// JAZelAudio_SE.h:460. The sound calls are stubs; the constants keep the copied call sites.
enum { JA_SE_LK_SLIP_SUS = 0x205A, JA_SE_LK_RUN_SLIP = 0x280D };

/// JAZelAudio_SE.h:467.
enum { JA_SE_LK_SW_KAZEKIRI_S = 0x2800 };

/// JAZelAudio_SE.h:504. The recorded id shows procCutTurn's `3.0 <= frame < 18.5` window was entered.
enum { JA_SE_LK_KAITENGIRI = 0x282B };

/// JAZelAudio_SE.h:453. The recorded id shows which of procCutTurnMove_init's two forks ran.
enum { JA_SE_LK_SWORD_CHARGE = 0x203B };

/// d_bg_s.h:33, :44 and :48. GRASS / WATER pick procCutTurn_init's dust plume and m35A0.
enum {
    dBgS_Attr_GRASS_e = 0x04,
    dBgS_Attr_ICE_e = 0x0F,
    dBgS_Attr_WATER_e = 0x13,
};

/// d_com_inf_game.h:2944-3009, the entries the ported bodies name, at the decomp's values.
enum dActionStatus_e {
    dActStts_BLANK_e = 0x00,
    dActStts_LIFT_e = 0x04,
    dActStts_CLIMB_e = 0x05,
    dActStts_PUT_AWAY_e = 0x08,
    dActStts_DROP_e = 0x09,
    dActStts_OPEN_e = 0x0B,
    dActStts_ATTACK_e = 0x0C,
    dActStts_THROW_e = 0x0E,
    dActStts_CROUCH_e = 0x0F,
    dActStts_SIDLE_e = 0x10,
    dActStts_GRAB_e = 0x11,
    dActStts_JUMP_e = 0x12,
    dActStts_PICK_UP_e = 0x1B,
    dActStts_GET_IN_SHIP_e = 0x1C,
    dActStts_PARRY_e = 0x1A,
    dActStts_CALL_e = 0x24,
    dActStts_ba_sake__dupe_31 = 0x31,
    dActStts_DEFEND_e = 0x36,
    dActStts_UNK43 = 0x43,
};

/// d_item_data.h and d_a_player_main.h:930-945. The item ids the dispatcher branches on.
enum {
    /// d_item_data.h:63. checkNormalSwordEquip compares equip slot 0 against it.
    dItemNo_SWORD_e = 0x38,
    dItemNo_TELESCOPE_e = 0x20,
    dItemNo_WIND_WAKER_e = 0x22,
    dItemNo_GRAPPLING_HOOK_e = 0x25,
    dItemNo_BOOMERANG_e = 0x2D,
    dItemNo_HOOKSHOT_e = 0x2F,
    dItemNo_SKULL_HAMMER_e = 0x33,
    dItemNo_DEKU_LEAF_e = 0x34,
    dItemNo_EMPTY_BOTTLE_e = 0x50,
    dItemNo_NONE_e = 0xFF,
    daPyItem_NONE_e = 0x100,
    daPyItem_BOKO_e = 0x101,
    daPyItem_SWORD_e = 0x103,
};

/// f_op_actor.h:63-70. The attention-entry types setDoStatus branches on.
enum {
    fopAc_Attn_TYPE_CARRY_e = 0x4,
    fopAc_Attn_TYPE_DOOR_e = 0x5,
    fopAc_Attn_TYPE_TREASURE_e = 0x6,
    fopAc_Attn_TYPE_SHIP_e = 0x7,
};

/// d_com_inf_game.h:2953, the A-button prompt setDoStatusCrawl posts.
enum { dActStts_RETURN_e = 0x07 };
enum { dItemBtn_X_e = 0, dItemBtn_Y_e = 1, dItemBtn_Z_e = 2 };

/// daPy__PlayerStatus0 and daPy__PlayerStatus1, copied whole from d_com_inf_game.h.
#include "d/player_status.inc"

enum { fopAcStts_CARRY_e = 0x00000001 };
enum { fpcNm_BOKO_e = 0x58 };
/// f_pc_name.h:178. Names are typed singly (the enum has 700-odd entries) and only compared for
/// equality.
enum { fpcNm_PLAYER_e = 0xA9 };

/// f_pc_name.h:381, Medli (nextMode).
enum { fpcNm_NPC_MD_e = 0x171 };

/// f_pc_name.h:471 and :477, the pot and the bomb flower (bumpCheck; unreached, grab id is -1).
enum { fpcNm_TSUBO_e = 0x1CB };
enum { fpcNm_Obj_Try_e = 0x1D0 };

/// c_cc_d.h:366 through dCcD_Stts, trimmed to `m_cc_move`, the push the actor-vs-actor collision
/// system accumulates. Nothing in the port writes it (no dCcS), so posMove adds zero.
class dCcD_Stts {
public:
    /// Not inline, so the boundary can count calls (`cc_move_asks`).
    cXyz* GetCCMoveP();

    cXyz m_cc_move;
};

/// f_op_actor.h:176 and :276, trimmed to checkCommandDoor. There is no event manager; mCommand
/// is a field a test can set.
class dEvt_info_c {
public:
    /// f_op_actor.h:135-140.
    enum { dEvtCmd_NONE_e = 0x0000, dEvtCmd_INDOOR_e = 0x0003 };

    BOOL checkCommandDoor() { return mCommand == dEvtCmd_INDOOR_e; }

    /* 0x08 */ u16 mCommand;
};

/// d_a_ship.h. The ship arms are dead: dComIfGp_getShipActor answers NULL.
class daShip_c;

/// jointBeforeCB's ship arm; unreached stubs in stubs.cpp.
fpc_ProcID fopAcM_GetID(daShip_c* ship);
BOOL fpcM_IsCreating(fpc_ProcID id);

/// f_op_actor.h:219-223, whole, so `position` is at its real offset.
struct actor_attention_types {
    /* 0x00 */ u8 distances[8];
    /* 0x08 */ cXyz position;
    /* 0x14 */ u32 flags;
};

/// f_op_actor.h:206-297, trimmed. Complete rather than forward-declared because daBoko_c derives
/// from it.
class fopAc_ac_c {
public:
    /// f_pc_manager.h:24 through base_process_class, flattened onto the actor; fopAcM_GetName
    /// reads it. reset_boundary seeds the player's to fpcNm_PLAYER_e; unseeded reads 0.
    /* ----- */ s16 mProcName;
    /// f_op_actor.cpp:196 runs `old = current` before execute(); the line check's segment is
    /// old.pos -> current.pos.
    /* 0x1E4 */ actor_place old;
    /* 0x1F8 */ actor_place current;
    /* 0x20C */ csXyz shape_angle;
    /// reset_boundary seeds (1, 1, 1), as fopAcM_create leaves it for the player.
    /* 0x214 */ cXyz scale;
    /* 0x260 */ cXyz eyePos;
    /// f_op_actor.h:305, the lock-on point (dCamera_c::attentionPos). Its writer, setAttentionPos
    /// (d_a_player_main.cpp:10220-10266), is ported but only execute() calls it, and execute() is
    /// not ported, so it stays zero.
    /* 0x26C */ actor_attention_types attention_info;
};

/// d_a_ship.h:97-98, trimmed to the flag word getFlyFlg reads. Both ship arms are dead.
class daShip_c : public fopAc_ac_c {
public:
    enum daSHIP_SFLG {
        daSFLG_FLY_e = 0x00000001,
    };

    u32 checkStateFlg(daSHIP_SFLG flag) const { return mStateFlag & flag; }
    BOOL getFlyFlg() { return checkStateFlg(daSFLG_FLY_e); }

    u32 mStateFlag;
};

/// d_com_inf_game.h:2872. Stub; answers NULL.
daShip_c* dComIfGp_getShipActor();

/// f_op_actor_mng.h:531. Stub, unreached: getCutDirection calls it only under
/// `mpAttnActorLockOn != NULL`, which nothing sets.
s16 fopAcM_searchActorAngleY(fopAc_ac_c* p_actorA, fopAc_ac_c* p_actorB);

/// d_a_boko.h:25-35 and :72, trimmed. daBoko_c is an enemy weapon Link can wield; its arm is behind
/// `mEquipItem != daPyItem_SWORD_e` and unreached. getAtPoint is stubbed: its table is in the boko
/// REL, not the DOL.
class daBoko_c : public fopAc_ac_c {
public:
    enum {
        /* 0x0 */ Type_BOKO_STICK_e = 0x0,
        /* 0x1 */ Type_MACHETE_e = 0x1,
        /* 0x2 */ Type_STALFOS_MACE_e = 0x2,
        /* 0x3 */ Type_DARKNUT_SWORD_e = 0x3,
        /* 0x4 */ Type_MOBLIN_SPEAR_e = 0x4,
        /* 0x5 */ Type_PGANON_SWORD_e = 0x5,
    };

    s32 getAtPoint();
    /// d_a_boko.h:74-75, stubbed for the same reason.
    f32 getJumpBlurRate();
    f32 getBlurRate();
};

/// d_particle_name.h:63-66. A struct because the copied sites spell `dPa_name::ID_...`.
struct dPa_name {
    enum {
        ID_AK_JN_ROUNDATTACKTOE = 0x001E,
        ID_AK_JT_ROUNDATTACKSMOKE = 0x201F,
        ID_AK_JN_ROUNDATTACKSHIBUKI = 0x0020,
        ID_AK_JN_ROUNDATTACKKUSA = 0x0021,
        /// d_particle_name.h:74-75, procCutTurnMove_init's charge pair.
        ID_AK_JN_CHARGEPOWER00 = 0x0029,
        ID_AK_JN_CHARGEPOWER01 = 0x002A,
    };
};

/// d_save.h, trimmed to the two hurricane-spin bits procCutTurnMove_init reads
/// (d_save_event_flag.inc:37 and :84). Driven at the boundary.
class dSv_event_flag_c {
public:
    enum { UNK_0B20 = 0x0B20 };
};
class dSv_event_tmp_flag_c {
public:
    enum { UNK_0402 = 0x0402 };
};

/// d_com_inf_game.h:1356, :1368 and :2077. Driven at the boundary.
BOOL dComIfGs_isEventBit(u16 id);
BOOL dComIfGs_isTmpBit(u16 id);
u8 dComIfGs_getMagic();

class JPABaseEmitter;

/// d_a_player.h:13-31, trimmed. At the boundary; each records the particle id it was asked for.
class daPy_mtxFollowEcallBack_c {
public:
    JPABaseEmitter* makeEmitter(u16 id, MtxP mtx, const cXyz* pos, const cXyz* scale);
    JPABaseEmitter* makeEmitterColor(u16 id, MtxP mtx, const cXyz* pos, const GXColor* c0,
                                     const GXColor* k0);
    void end();
};

/// d_particle.h:72.
class dPa_smokeEcallBack {
public:
    void remove();
};

/// d_particle.h:318-343, trimmed. Real inline accessors, as in the decomp; nothing renders them.
class dPa_cutTurnEcallBack_c {
public:
    u8 getAlpha() { return mAlpha; }
    void setAlpha(u8 alpha) { mAlpha = alpha; }

    /* 0x04 */ u8 mAlpha;
};

/// d_a_player_main.h:317-320, trimmed. The sword trail; rendering only.
class daPy_swBlur_c {
public:
    void initSwBlur(MtxP mtx, int frames, f32 top_rate, int color);
};

/// d_kankyo.h:109-113, trimmed. Nothing writes it.
class dKy_tevstr_c {
public:
    /* 0x80 */ GXColorS10 mColorC0;
    /* 0x88 */ GXColor mColorK0;
};

/// d_kankyo_rain.h. The sea's ambient and diffuse colours, for the WATER arm's splash.
void dKy_get_seacolor(GXColor* amb, GXColor* dif);

/// d_com_inf_game.h.
void dComIfGp_particle_setToonP1(u16 id, const cXyz* pos, const csXyz* angle, const cXyz* scale,
                                 u8 alpha, dPa_smokeEcallBack* callback, s8 which, const void* a,
                                 const void* b, const void* c);

/// d_attention.h:105-115, the one field setDoStatus and checkNextActionFromButton read.
class dAttList_c {
public:
    /* 0x8 */ u32 mType;
};

/// d_a_player_main.h:18-26, verbatim. One animation object per slot: two slots holding the same
/// animation have independent frames.
class daPy_anmHeap_c {
public:
    /* 0x0 */ u16 mIdx;
    /* 0x6 */ u16 field_0x6;   ///< procWait_init's DEMO_KM_WAIT arm reads it on m_tex_scroll_heap
};

/// d_a_player_main.h:266-300, trimmed to the static procWait's idle arm reads (stubs.cpp).
class daPy_matAnm_c {
public:
    static u8 getEyeMoveFlg();
    static void offMabaFlg() {} // Texture blinking only; no movement effect.
};

/// One animation's frameMax and attribute, read off its ANK1 header by engine/link_assets.cpp.
struct daPy_portAnmMeta {
    u16 mBckIdx;
    s16 mFrameMax;
    u8 mAttribute;
};

/// One animation's keyframe tracks for every joint, verbatim from its .bck in LkAnm.arc.
/// `mAnmTable` is indexed `mAnmTable[joint*3 + axis]`, as the game's loader leaves it.
struct daPy_portAnmTrack {
    u16 mBckIdx;
    int mDecShift;
    int mJointNum;
    const J3DAnmTransformKeyTable* mAnmTable;
    const f32* mScaleData;
    const s16* mRotData;
    const f32* mTransData;
    /// The three arrays' lengths, as the ANK1 header counts them.
    u16 mScaleNum;
    u16 mRotNum;
    u16 mTransNum;
};

/// Stands in for a loaded .bck. The J3DAnmTransform half carries the metadata; getTransform
/// delegates to a copied J3DAnmTransformKey holding the baked tracks, at the frame set through
/// setFrame(). One per anim-heap slot.
class daPy_portAnm_c : public J3DAnmTransform {
public:
    daPy_portAnm_c() : J3DAnmTransform(0, NULL, NULL, NULL) { mAttribute = 0; mTrack = NULL; }

    void load(s16 frameMax, u8 attribute, const daPy_portAnmTrack* track);

    /// J3DAnimation.h:60 is an empty virtual. This syncs the frame, counts the call, and answers
    /// for an animation with no baked track.
    void getTransform(u16 joint, J3DTransformInfo* out) const override;

private:
    /// Mutable because getTransform is const in the decomp's signature.
    mutable J3DAnmTransformKey mKey;
    const daPy_portAnmTrack* mTrack;
};

/// Named after the decomp's loader because J3DAnmTransformKey befriends it (J3DAnimation.h:356).
/// It installs pre-parsed tracks rather than parsing ANK1 bytes.
class J3DAnmKeyLoader_v15 {
public:
    static void load(J3DAnmTransformKey* dst, const daPy_portAnmTrack* track);
};

/// The installed tracks (engine/link_assets.h), reachable from the suite.
size_t daPy_portAnmTrackTableSize();
const daPy_portAnmTrack* daPy_portAnmTrackTableAt(size_t i);

/// d_a_player_main.h:365-369, verbatim.
class daPy_anmIndex_c {
public:
    /* 0x00 */ u16 mUnderBckIdx;
    /* 0x02 */ u16 mUpperBckIdx;
};

/// m_Do_ext.h:323, 340. NULL unless Link hangs from the Deku Leaf.
class mDoExt_McaMorf {
public:
    BOOL play(Vec*, u32, s8);
};

/// m_Do_ext.h:110-129, trimmed to changeBckOnly (the sword model's animation). stubs.cpp records
/// the index, which shows the checkNormalSwordEquip arm taken.
class mDoExt_bckAnm {
public:
    void changeBckOnly(J3DAnmTransform* i_bck);
};

/// J3DAnimation.h:624 and :394, trimmed to their J3DAnmBase: the thrust's blade flash. Only
/// setFrame / getFrame are used.
class J3DAnmColor : public J3DAnmBase {
public:
    J3DAnmColor() : J3DAnmBase(0) {}
};

class J3DAnmTextureSRTKey : public J3DAnmBase {
public:
    J3DAnmTextureSRTKey() : J3DAnmBase(0) {}
};

/// c_cc_d.h:420-430, trimmed to SetAtp.
class cCcD_ObjAtInf {
public:
    void SetAtp(int atp) { mAtp = atp; }

    /* 0x08 */ int mAtp;
};

/// d_cc_d.h:502 and c_cc_d.h:544, trimmed. Derives from cM3dGCyl so SetR / GetRP are real
/// (cLib_chaseF writes through GetRP). Nothing collides: the radius is computed, the hit is not.
class dCcD_Cyl : public cM3dGCyl {
public:
    void SetAtAtp(int atp) { mObjAt.SetAtp(atp); }

    cCcD_ObjAtInf mObjAt;
};

/// Also declared here because inline members (checkShieldEquip) cannot see declarations that
/// come after the class.
int dComIfGs_getSelectEquip(int slot);

/// d_com_inf_game.h, declared here for checkSwordMiniGame.
int dComIfGp_getMiniGameType();

/// d_a_player_main_data.inc:26-27 and d_a_player_main_data.h:11. setAttentionPos keeps the
/// decomp's `!@bug(?)` on l_ship_offset: both the X and the Z line multiply by `.z`.
extern const Vec l_ship_offset;
extern const Vec l_toe_pos;
extern const Vec l_heel_pos;

/// d_a_player_main.h:336-352, whole: posMoveFromFootPos's toe/heel positions and the foot IK state.
class daPy_footData_c {
public:
    /* 0x000 */ u8 field_0x000;
    /* 0x001 */ u8 field_0x001;
    /* 0x002 */ s16 field_0x002;
    /* 0x004 */ s16 field_0x004;
    /* 0x006 */ s16 field_0x006;
    /* 0x008 */ s16 field_0x008;
    /* 0x00A */ s16 field_0x00A;
    /* 0x00C */ cXyz field_0x00C;
    /* 0x018 */ cXyz field_0x018;
    /* 0x024 */ cXyz field_0x024;
    /* 0x030 */ f32 field_0x030;
    /* 0x034 */ dBgS_LinkGndChk field_0x034;
    /* 0x088 */ Mtx field_0x088[3];
};

/// d_a_player_main_data.inc:28 and :31, verbatim.
extern const Vec l_crawl_start_front_offset;
extern const Vec l_crawl_top_offset;
/// d_a_player_main_data.inc:29 and :35.
extern const Vec l_crawl_front_offset;
extern const Vec l_crawl_top_up_offset;


/// d_a_player.h. One static predicate, called on checkNextActionFromButton's main path.
class daPy_dmEcallBack_c {
public:
    static BOOL checkCurse();
};

/// d_a_player_main.h:75-89, verbatim apart from unread fields.
class daPy_actorKeep_c {
public:
    fpc_ProcID getID() const { return mID; }
    fopAc_ac_c* getActor() { return mActor; }

    /// The decomp's layout is mID then mActor, size 0x8.
    /* 0x0 */ fpc_ProcID mID;
    /* 0x4 */ fopAc_ac_c* mActor;
};

/// d_a_player.h:44-133, trimmed. DEMO_N_WALK_e has no capture column, so the gate flips it in the
/// sensitivity sweep.
class daPy_demo_c {
public:
    enum Type_e {
        /* 0x0 */ TYPE_NONE_e,
        /* 0x1 */ TYPE_TOOL_e,
        /* 0x3 */ TYPE_ORIGINAL_e = 3,
    };

    enum Mode_e {
        /* 0x002 */ DEMO_N_WALK_e = 2,
        /* 0x005 */ DEMO_WAIT_TURN_e = 5,
        /* 0x00A */ DEMO_OPEN_TREASURE_e = 10,
        /* 0x00E */ DEMO_KEEP_e = 14,
        /* 0x012 */ DEMO_UNK_018_e = 18,
        /* 0x017 */ DEMO_A_WAIT_e = 23,
        /* 0x01E */ DEMO_UNK_030_e = 30,
        /* 0x02A */ DEMO_KM_WAIT_e = 42,
        /* 0x02B */ DEMO_CUT_ROLL_e = 43,
    };

    u32 getDemoMode() const { return mDemoMode; }
    /// d_a_player.h:143. Read only on setBlendAtnMoveAnime's DEMO_A_WAIT_e arm.
    int getParam0() const { return mParam0; }
    int getDemoType() const { return mDemoType; }

    u32 mDemoMode;
    int mParam0;
    int mDemoType;
};

/// Derives from fopAc_ac_c, as the decomp's does through daPy_py_c and daPy_c.
class daPy_lk_c : public fopAc_ac_c {
public:
    /// d_a_player_main.h:446, :688 and :1120.
    enum {
        daPyProc_WAIT_e = 0x04,
        daPyProc_FREE_WAIT_e = 0x05,
        daPyProc_MOVE_e = 0x06,
        /// d_a_player_main.h:423. The targeting sidestep.
        daPyProc_ATN_MOVE_e = 0x07,
        daPyProc_CROUCH_DEFENSE_e = 0x0C,
        daPyProc_CROUCH_DEFENSE_SLIP_e = 0x0D,
        daPyProc_CROUCH_e = 0x0E,
        /// d_a_player_main.h:431-434. CRAWL_MOVE is recorded, not run (stubs.cpp).
        daPyProc_CRAWL_START_e = 0x0F,
        daPyProc_CRAWL_MOVE_e = 0x10,
        daPyProc_CRAWL_END_e = 0x12,
    /// Named only by setBgCheckParam's comparisons.
    daPyProc_LARGE_DAMAGE_WALL_e = 0x6A,
    daPyProc_ROPE_SWING_START_e = 0x7C,
        /// d_a_player_main.h:439. The pivot in place.
        daPyProc_WAIT_TURN_e = 0x17,
        daPyProc_MOVE_TURN_e = 0x18,
        daPyProc_SLIP_e = 0x19,
        /// d_a_player_main.h:481.
        daPyProc_CUT_A_e = 0x41,
        /// d_a_player_main.h:482. The thrust (changeCutProc's DIR_FORWARD arm).
        daPyProc_CUT_F_e = 0x42,
        /// d_a_player_main.h:483. The right slash.
        daPyProc_CUT_R_e = 0x43,
        /// d_a_player_main.h:484. The left slash, and the unlocked neutral B press.
        daPyProc_CUT_L_e = 0x44,
        /// d_a_player_main.h:485. The combo ender for a fourth press forward or right.
        daPyProc_CUT_EA_e = 0x45,
        /// d_a_player_main.h:486. The other ender: neutral, left or backward.
        daPyProc_CUT_EB_e = 0x46,
        /// d_a_player_main.h:501. The spin attack.
        daPyProc_CUT_TURN_e = 0x55,
        /// d_a_player_main.h:504. The spin-attack charge; no body here (stubs.cpp).
        daPyProc_CUT_TURN_CHARGE_e = 0x58,
        /// d_a_player_main.h:505. The spin's steered hold.
        daPyProc_CUT_TURN_MOVE_e = 0x59,
        /// d_a_player_main.h:502. The spin's dizzy roll-out; no body here (stubs.cpp).
        daPyProc_CUT_ROLL_e = 0x56,
        /// d_a_player_main.h:471. No body here; named by posMoveFromFootPos's unreached stroke arm.
        daPyProc_SWIM_MOVE_e = 0x37,
        /// d_a_player_main.h:458. The backflip, the only ported proc with ModeFlg_MIDAIR.
        daPyProc_BACK_JUMP_e = 0x22,
        /// d_a_player_main.h:459. Its landing, entered by procBackJump.
        daPyProc_BACK_JUMP_LAND_e = 0x23,
        /// d_a_player_main.h:426. The sidehop (L + A, stick left or right).
        daPyProc_SIDE_STEP_e = 0x0A,
        /// d_a_player_main.h:427. Its landing, entered by procSideStep itself.
        daPyProc_SIDE_STEP_LAND_e = 0x0B,
        /// d_a_player_main.h:507. The jump slash.
        daPyProc_JUMP_CUT_e = 0x5B,
        /// d_a_player_main.h:508. Its landing, entered by procJumpCut.
        daPyProc_JUMP_CUT_LAND_e = 0x5C,
        /// d_a_player_main.h:632. The ending-blow cutscene; no body here.
        daPyProc_DEMO_LAST_COMBO_e = 0xD8,
        /// d_a_player_main.h:458, :463, :549, :563, :567 and :609. No body here; named by
        /// checkNoCollisionCorret's and posMove's comparisons.
        daPyProc_VERTICAL_JUMP_e = 0x2A,
        daPyProc_HANG_MOVE_e = 0x2F,
        daPyProc_HOOKSHOT_FLY_e = 0x85,
        daPyProc_FAN_GLIDE_e = 0x93,
        daPyProc_VOMIT_WAIT_e = 0x97,
        daPyProc_DEMO_DOOR_OPEN_e = 0xC1,
        /// d_a_player_main.h:585. The tool demo; no body here.
        daPyProc_DEMO_TOOL_e = 0xA9,
        daPyProc_FRONT_ROLL_e = 0x1E,
        daPyProc_FRONT_ROLL_CRASH_e = 0x1F,
        daPyProc_GUARD_SLIP_e = 0x6D,
        daPyProc_ROPE_SWING_e = 0x78,
    };
    /// All 234, copied whole.
#include "d/actor/anm_enum.inc"

    /// All 174, copied whole: they subscript mTexAnmIndexTable.
#include "d/actor/face_enum.inc"

    /// d_a_player_main.h:881-890, verbatim. getUnderUpperAnime casts its `r7` back to these.
    enum daPy_UNDER {
        UNDER_MOVE0_e = 0,
        UNDER_MOVE1_e = 1,
    };

    enum daPy_UPPER {
        UPPER_MOVE0_e = 0,
        UPPER_MOVE1_e = 1,
        UPPER_MOVE2_e = 2,
    };

    /// d_a_player_main.h:892-895, verbatim. Subscripts m_pbCalc.
    enum {
        PART_UNDER_e = 0,
        PART_UPPER_e = 1,
    };

    /// d_a_player_main.h:2361-2368, trimmed of the two hand-joint columns (setHandModel is at the
    /// boundary).
    struct AnmDataTableEntry {
        /* 0x00 */ daPy_anmIndex_c mAnmIdx;
        /* 0x06 */ u16 mTexAnmIdx;
    };

    static const daPy_anmIndex_c mSwordAnmIndexTable[];
    static const daPy_anmIndex_c mBokoAnmIndexTable[];
    static const daPy_anmIndex_c mHammerAnmIndexTable[];
    static const AnmDataTableEntry mAnmDataTable[];

    /// d_a_player_main.h:2351-2355, verbatim. tex_anm_table.inc generates the rows.
    struct TexAnmTableEntry {
        /* 0x00 */ u16 mBtpIdx;
        /* 0x02 */ u16 mBtkIdx;
    };  // Size: 0x04
    static const TexAnmTableEntry mTexAnmIndexTable[];
    /// d_a_player.h:444-453, trimmed. daPy_py_c's enum, flattened into daPy_lk_c.
    enum daPy_CUT_TYPE {
        /* 0x01 */ CUT_TYPE_CUT_A = 0x01,
        /* 0x02 */ CUT_TYPE_CUT_F = 0x02,      ///< d_a_player.h:447 - the forward thrust
        /* 0x03 */ CUT_TYPE_CUT_R = 0x03,      ///< d_a_player.h:448 - the right slash
        /* 0x04 */ CUT_TYPE_CUT_L = 0x04,      ///< d_a_player.h:449 - the left slash
        /* 0x06 */ CUT_TYPE_CUT_EA = 0x06,     ///< d_a_player.h:451 - "4 slash combo while
                                               ///< holding a direction", in the decomp's words
        /* 0x07 */ CUT_TYPE_CUT_EB = 0x07,     ///< d_a_player.h:452 - ...and while not
        /* 0x08 */ CUT_TYPE_CUT_TURN = 0x08,   ///< d_a_player.h:453 - the spin attack
        /* 0x0A */ CUT_TYPE_JUMPCUT_SWORD = 0x0A,    ///< d_a_player.h:455 - the jump slash's
        /* 0x0E */ CUT_TYPE_JUMPCUT_MACHETE = 0x0E,  ///< d_a_player.h:459 - ...with no weapon
        /* 0x13 */ CUT_TYPE_JUMPCUT_HAMMER = 0x13,   ///< d_a_player.h:464 - ...with the hammer
    };

    /// d_a_player_main.h:960-965, verbatim.
    enum daPy_lk_DIR {
        /* 0x0 */ DIR_FORWARD,
        /* 0x1 */ DIR_BACKWARD,
        /* 0x2 */ DIR_LEFT,
        /* 0x3 */ DIR_RIGHT,
        /* 0x4 */ DIR_NONE,
    };
    /// d_a_player_main.h:947-955, verbatim.
    enum daPy_lk_ITEM_BTN {
        /* 0x01 */ BTN_A = (1 << 0),
        /* 0x02 */ BTN_B = (1 << 1),
        /* 0x04 */ BTN_X = (1 << 2),
        /* 0x08 */ BTN_Y = (1 << 3),
        /* 0x10 */ BTN_Z = (1 << 4),
        /* 0x20 */ BTN_L = (1 << 5),
        /* 0x40 */ BTN_R = (1 << 6),
    };

    // ---- the fields the two roll procs touch, in the decomp's own spelling ----
    // old, current, shape_angle and scale are fopAc_ac_c's and are inherited above.
    /* 0x220 */ cXyz speed;
    /* 0x254 */ f32 speedF;
    /* 0x29C */ u32 mNoResetFlg0;
    /* 0x2A0 */ u32 mNoResetFlg1;
    /* 0x3AC */ dBgS_AcchCir mAcchCir[3];
    /// dBgS_LinkAcch (d_a_player_main.h:2011): its constructor's `SetLink()` gives every query
    /// Link's pass-checks.
    /* 0x484 */ dBgS_LinkAcch mAcch;
    /// dBgS_LinkLinChk, a member as in the decomp: getCrawlMoveVec reads the crossing back out of
    /// it after LineCross.
    /* 0x630 */ dBgS_LinkLinChk mLinkLinChk;
    /* 0x950 */ daPy_HIO_c* m_HIO;
    /* 0x302C*/ J3DFrameCtrl mFrameCtrlUnder[2];
    /* 0x2FB4*/ mDoExt_AnmRatioPack mAnmRatioUnder[2];
    /* 0x2FC4*/ mDoExt_AnmRatioPack mAnmRatioUpper[3];
    /* 0x2FDC*/ daPy_anmHeap_c m_anm_heap_under[2];
    /* 0x3054*/ J3DFrameCtrl mFrameCtrlUpper[3];
    /// The port's own: one loaded-animation stand-in per heap slot (the game keeps them in the anim
    /// heap).
    /* 0x2EAC*/ mDoExt_McaMorf* mpParachuteFanMorf;
    /* ----- */ daPy_portAnm_c port_anm_under[2];
    /* ----- */ daPy_portAnm_c port_anm_upper[3];
    /// The port's own: mpCLModel points here, and procCutTurn_init dereferences it unchecked.
    /* ----- */ J3DModel port_cl_model;
    /* 0x34BE*/ u8 mFootEffectPosType;
    /* 0x3570*/ struct { s32 m3570; } mProcVar6;
    /* 0x34D4*/ struct { s16 m34D4; } mProcVar2;
    /* 0x34D6*/ struct { s16 m34D6; } mProcVar3;
    /* 0x35B0*/ f32 mStickDistance;
    /* 0x35BC*/ f32 mNormalSpeed;
    /* 0x3620*/ u32 m3620;
    /// setWorldMatrix's offsets, all zero here with no writer in scope: m35C4 (setStepsOffset,
    /// d_a_player_main.cpp:11029), m3608 (:5856) and m34EC (leans outside the block catalog).
    /// m353C / m353E are the ship arm's lean angles.
    /* 0x353C*/ s16 m353C;
    /* 0x353E*/ s16 m353E;
    /* 0x34EC*/ s16 m34EC;
    /* 0x35C4*/ f32 m35C4;
    /* 0x3608*/ f32 m3608;
    /* ----- */ s32 mCurProc;

    // ---- the 12 checkNextMode adds ----
    /* 0x2A8 */ f32 mMaxNormalSpeed;      ///< d_a_player.h:488
    /* 0x2B0 */ f32 field_0x2b0;          ///< d_a_player.h:596, read only by checkGrabWear()
    /* 0x3184*/ daPy_actorKeep_c mActorKeepThrow;
    /* 0x319C*/ fopAc_ac_c* mpAttnActorLockOn;
    /* 0x34B8*/ u8 mDirection;
    /* 0x34B9*/ u8 mFrontWallType;
    /* 0x34C9*/ u8 mItemButton;
    /* 0x34D0*/ struct { s16 m34D0; } mProcVar0;
    /* 0x34DC*/ s16 m34DC;
    /* 0x34E8*/ s16 m34E8;
    /* 0x34EA*/ s16 m34EA;
    /* 0x3526*/ s16 m3526;
    /* 0x3544*/ s16 m3544;                ///< changeFrontWallTypeProc writes it; the read is past its cut
    /* 0x3584*/ int mCurrAttributeCode;
    /* 0x3618*/ u32 mModeFlg;
    /* ----- */ daPy_demo_c mDemo;
    /* ----- */ u8 m34C3;                 ///< d_a_player_main.h:2143, read by changeSlideProc

    // ---- the 14 setBlendMoveAnime / setMoveAnime add ----
    /* 0x34DE*/ s16 m34DE;                ///< the shape angle the ATN re-pose arm chases
    /* 0x34E2*/ s16 m34E2;                ///< the ground slope; cM_scos of it scales the speed
    /* 0x3580*/ int m3580;                ///< == 8 skips the slope term entirely
    /* 0x3598*/ f32 m3598;                ///< the WALK<->DASH speedF blend; the capture's blend_move
    /* 0x3640*/ s16 m3640;                ///< the wind/current direction the DASHKAZE arm tests
    /* 0x3644*/ f32 m3644;                ///< ...and its magnitude
    /* 0x36A0*/ cXyz m36A0;               ///< the three slip vectors: ice, ground, and the wall
    /* 0x36B8*/ cXyz m36B8;
    /* 0x3730*/ cXyz m3730;
    /* 0x373C*/ cXyz m373C;               ///< the heavy-boots arm's own wind vector

    // ---- the 17 checkNextActionFromButton / setDoStatus / setDoStatusBasic add ----
    /* 0x2A4 */ u32 mResetFlg0;           ///< d_a_player.h:487; cleared every frame by execute()
    /* 0x2FFC*/ daPy_anmHeap_c m_anm_heap_upper[3];
    /* 0x317C*/ daPy_actorKeep_c mActorKeepEquip;
    /* 0x31A4*/ fopAc_ac_c* mpAttnActorA;
    /* 0x31B4*/ mDoExt_MtxCalcOldFrame* m_old_fdata;
    /* 0x3484*/ dAttList_c* mpAttnEntryA;
    /* 0x34BD*/ u8 mReadyItemBtn;
    /* 0x3562 */ u16 m3562 = daPyItem_NONE_e;
    /* 0x34C5*/ u8 m34C5;
    /* 0x34C8*/ u8 mItemTrigger;
    /* 0x3560*/ u16 mEquipItem;
    /* 0x356C*/ int mCameraInfoIdx;
    /* 0x3578*/ int m3578;
    /* 0x3724*/ cXyz m3724;

    // ---- the 10 procWait / procWait_init / procCrouch_init add ----------------------------
    /* 0x31B8*/ daPy_anmHeap_c m_tex_anm_heap;  ///< the low-life arm's face-texture identity
    /* 0x31C8*/ daPy_anmHeap_c m_tex_scroll_heap;   ///< ...and the DEMO_KM_WAIT arm's
    /* 0x3530*/ u16 m3530;                ///< the btk index setTextureAnime is handed
    /* 0x3564*/ csXyz m3564;              ///< the idle timer's "has the head moved" test
    /* 0x34D2*/ struct { s16 m34D2; } mProcVar1;   ///< WAIT's own idle countdown
    /* 0x34E6*/ s16 m34E6;                ///< the facing the L-trigger wall snap writes
    /* 0x35A0*/ f32 m35A0;                ///< the turn rate procWait's re-pose arm feeds the anim
    /* 0x36AC*/ cXyz m36AC;               ///< the ice-slip arm's second vector

    // ---- the 2 procCrouch adds ------------------------------------------------------------
    /* 0x0774*/ dBgS_LinkGndChk mGndChk;  ///< the crawl probe's ground-line query object
    /* 0x35D0*/ f32 mWaterY;              ///< the water surface height; both of procCrouch's
                                          ///< first two arms compare current.pos.y against it

    // ---- the 6 procCutA / procCutA_init add --------------------------------------------------
    // Five of the six are write-only here: no ported body reads them back.
    /* 0x2E9C*/ mDoExt_bckAnm mSwordAnim;  ///< the sword model's own animation; changeBckOnly only
    /* 0x34C2*/ u8 m34C2;                 ///< posMove's arm selector; 0 or 1 on every frame here
    /* 0x351E*/ s16 m351E;                ///< the raw stick angle the slash was started from
    /* 0x3522*/ s16 m3522;                ///< an execute() countdown (11382), not read by a proc
    /* 0x35EC*/ f32 m35EC;                ///< the anim clock mirrored for the sword trail
    /* 0x3700*/ cXyz m3700;               ///< the slash's accumulated push, zeroed by the init

    // ---- the 6 posMove adds ------------------------------------------------------------------
    /// d_a_player_main.h:2078, one blend table per body half, over mAnmRatioUnder / mAnmRatioUpper.
    /// reset_boundary does what commonDataInit (d_a_player_main.cpp:12023) does.
    /* 0x2FAC*/ mDoExt_MtxCalcAnmBlendTblOld* m_pbCalc[2];
    /// The port's own, as commonDataInit arranges them on the heap: one blend table per half and
    /// one shared old-frame object, over two arrays of numCLJoints (0x2A, d_a_player_main.cpp:12019).
    /* ----- */ J3DTransformInfo port_old_trans[0x2A] = {};
    /* ----- */ Quaternion port_old_quat[0x2A] = {};
    /* ----- */ mDoExt_MtxCalcOldFrame port_old_fdata{port_old_trans, port_old_quat};
    /* ----- */ mDoExt_MtxCalcAnmBlendTblOld port_pbcalc_under{&port_old_fdata, 2, mAnmRatioUnder};
    /* ----- */ mDoExt_MtxCalcAnmBlendTblOld port_pbcalc_upper{&port_old_fdata, 3, mAnmRatioUpper};
    /// d_a_player_main.h:2281. The climb arm's latched root height; unreached.
    /* 0x35E0*/ f32 m35E0;
    /// d_a_player_main.h:2293. The whirlpool pull; mWhirlId is fpcM_ERROR_PROCESS_ID_e here, so the
    /// else arm zeroes it every frame.
    /* 0x3610*/ f32 m3610;
    /* 0x3634*/ fpc_ProcID mWhirlId;
    /* 0x3FE8*/ dCcD_Stts mStts;
    /* 0x0F4 */ dEvt_info_c eventInfo;

    // ---- the 2 procCutF / procCutF_init add --------------------------------------------------
    // The thrust's blade flash: frames set on two texture animators the renderer plays. Pointers
    // as in the decomp (d_a_player_main.h:2060-2061); the port owns the objects because procCutF
    // dereferences them unconditionally.
    /* 0x2EF0*/ J3DAnmColor* mpCutfBpk;
    /* 0x2EF4*/ J3DAnmTextureSRTKey* mpCutfBtk;
    /* ----- */ J3DAnmColor port_cutf_bpk;
    /* ----- */ J3DAnmTextureSRTKey port_cutf_btk;

    // ---- the 10 procCutTurn / procCutTurn_init add -------------------------------------------
    // m35A0 (the frame past which the ground plume ends) and m35A4 (the attack cylinder's target
    // radius) are read back; the rest are write-only here.
    /* 0x32E4*/ daPy_mtxFollowEcallBack_c m32E4;  ///< the toe plume; ended past frame 17.0
    /* 0x32F0*/ daPy_mtxFollowEcallBack_c m32F0;  ///< the ground plume; ended past m35A0
    /* 0x32FC*/ dPa_smokeEcallBack mSmokeEcallBack;
    /* 0x331C*/ dPa_cutTurnEcallBack_c m331C;     ///< the three blur ribbons, alpha'd on
    /* 0x332C*/ dPa_cutTurnEcallBack_c m332C;     ///< ...checkPass(field_0x34) and off after it
    /* 0x333C*/ dPa_cutTurnEcallBack_c m333C;
    /* 0x34C4*/ u8 m34C4;                 ///< the combo counter the init tests against 6
    /* 0x0290*/ u8 mCutType;              ///< daPy_py_c's; which cut is running - write-only here
    /* 0x0291*/ u8 mCutCount;             ///< ...and its own counter, zeroed off the same fork
    /* 0x35A4*/ f32 m35A4;                ///< the attack cylinder's target radius
    /* 0x010C*/ dKy_tevstr_c tevStr;      ///< fopAc_ac_c's, read by the GRASS arm
    /* 0x032C*/ J3DModel* mpCLModel;      ///< daPy_py_c's; the joint matrices come off it
    /* 0x4284*/ dCcD_Cyl mAtCyl;          ///< the attack collision cylinder
    /// d_a_player_main.h:2334. Read only by setAttentionPos's dead HANG arm; nothing writes it.
    /* 0x4024*/ dCcD_Cyl mCyl;            ///< the body collision cylinder

    // ---- the 3 procBackJump / procBackJumpLand add -------------------------------------------
    // gravity is fopAc_ac_c's (f_op_actor.h:302).
    /* 0x0258*/ f32 gravity;
    /// The launch position, latched by commonProcInit on a ground->MIDAIR entry
    /// (d_a_player_main.cpp:5844); procBackJump's drop test reads it.
    /* 0x3688*/ cXyz m3688;
    /// Read only behind dComIfGp_event_runCheck(), false here.
    /* 0x358C*/ int mStaffIdx;
    /// The grace on the stick-rotation accumulator, seeded from mCutTurnR.field_0x2 and counted
    /// down. Written by the harness's accumulator (tests/player_rig.cpp), not by a ported proc.
    /* 0x3524*/ s16 m3524;

    // ---- the 3 procJumpCut / procJumpCutLand add ---------------------------------------------
    /// The launch height, latched beside m3688 (d_a_player_main.cpp:5845). procJumpCutLand_init's
    /// drop is `m35F0 - current.pos.y`.
    /* 0x35F0*/ f32 m35F0;
    /// The stun, from mDam.field_0x0 (30). Write-only here: execute()'s damage path spends it.
    /* 0x3556*/ s16 mDamageWaitTimer;
    /// The sword trail, for procJumpCutLand_init's one call.
    /* 0x37E4*/ daPy_swBlur_c mSwBlur;

    // ---- the 2 procCrawlStart / procCrawlEnd add ---------------------------------------------
    /// The crawl's phase, 0 to 1 over the animation. procCrawlStart reads it back the same frame
    /// to scale the wall probe (`l_crawl_front_offset.z * m35E4`).
    /* 0x35E4*/ f32 m35E4;
    /// d_a_player.h:491. The body's aim, written by setDoStatusCrawl's camera arm; no ported body
    /// reads it.
    /* 0x02B4*/ csXyz mBodyAngle;

    // ---- the 8 posMoveFromFootPos adds -------------------------------------------------------
    /// Which foot is planted: 0 right, 1 left, 2 not yet calculated. Only indexes the foot delta.
    /* 0x34BC*/ u8 m34BC;
    /// The waist heading of the foot-height comparison; written only by procs outside the port.
    /* 0x34E0*/ s16 m34E0;
    /// Last frame's foot delta (the capture's `foot_delta_prev`), for the 0.3/0.7 smoothing.
    /* 0x359C*/ f32 m359C;
    /// The previous frame's mStickDistance, copied at the top of execute()
    /// (d_a_player_main.cpp:11281); the rig's frame_top carries that line.
    /* 0x35B4*/ f32 m35B4;
    /// The speed the previous frame ended with, copied by execute() after posMove; read only by the
    /// ICE arm. The rig carries the copy.
    /* 0x3694*/ cXyz mOldSpeed;
    /// The joint matrix each foot's is concatenated onto; a member because the decomp's line is
    /// `cMtx_concat(m37B4, ...)`.
    /* 0x37B4*/ Mtx m37B4;
    /// Both feet's toe and heel positions, carried forward one frame.
    /* 0x3DB8*/ daPy_footData_c mFootData[2];

    // ---- the foot IK's (footBgCheck, setLegAngle, the three joint callbacks) ------------------
    /// The body lowering: footBgCheck chases it onto the lower foot's floor minus current.pos.y and
    /// adds it to the base matrix's height; m37B4 takes the opposite.
    /* 0x35B8*/ f32 m35B8;
    /// jointBeforeCB's save of what it edits (bit 1: quaternion into m3658, bit 2: transform into
    /// m3668); jointAfterCB restores both.
    /* 0x34C6*/ u8 m34C6;
    /* 0x3668*/ J3DTransformInfo m3668;
    /* 0x3658*/ Quaternion m3658;
    /// The upper-body guard pose's root rotation; used only under guard, grab and held-weapon upper
    /// animations, which the block catalog does not reach.
    /* 0x3648*/ Quaternion m3648;
    /// jointBeforeCB's other angle inputs (chest twist, MOMI joints, body lift, waist, hat).
    /// Nothing ported writes them, so they are zero.
    /* 0x3516*/ s16 m3516;
    /* 0x3518*/ s16 m3518;
    /* 0x351A*/ s16 m351A;
    /* 0x34E4*/ s16 m34E4;
    /* 0x35D8*/ f32 m35D8;
    /* 0x34F2*/ s16 m34F2;
    /* 0x34F4*/ s16 m34F4;
    /* 0x34F6*/ s16 m34F6;
    /* 0x34F8*/ s16 m34F8;
    /* 0x34FA*/ s16 m34FA;
    /* 0x34FC*/ s16 m34FC;
    /* 0x34FE*/ s16 m34FE;
    /* 0x3500*/ s16 m3500;
    /* 0x350E*/ s16 m350E;
    /* 0x3510*/ s16 m3510;
    /* 0x3512*/ s16 m3512;
    /* 0x3528*/ s16 m3528;
    /// fopAc_ac_c's, +0x25C. Seeded to mAutoJump.field_0x10 (-175.0) at d_a_player_main.cpp:12196;
    /// rewritten only by FAN_GLIDE and SLOW_FALL.
    /* 0x25C */ f32 maxFallSpeed;

    // ---- the 1 dCamera_c::heightOf adds ------------------------------------------------------
    /// d_a_player.h:489, daPy_py_c's. A constant in the game: `mHeight = 125.0f` in commonDataInit
    /// (d_a_player_main.cpp:12201), seeded by reset_boundary.
    /* 0x2AC */ f32 mHeight;

    // ---- verbatim from the decomp ----
    // d_a_player.h:529-531, 549, 596; d_a_player_main.h:1885, 1898.
    void onNoResetFlg0(daPy_FLG0 flag) { mNoResetFlg0 |= flag; }
    void offNoResetFlg0(daPy_FLG0 flag) { mNoResetFlg0 &= ~flag; }
    u32 checkNoResetFlg0(daPy_FLG0 flag) const { return mNoResetFlg0 & flag; }
    /// d_a_player_main.h:1954-1966, verbatim but for `virtual`: the grounded tail skips the stair
    /// offset for a player in any of these eight states.
    u32 checkPlayerFly() const {
        // Note: These flags combine into 0x10452822.
        return checkModeFlg(
            ModeFlg_MIDAIR |
            ModeFlg_HANG |
            ModeFlg_ROPE |
            ModeFlg_IN_SHIP |
            ModeFlg_CLIMB |
            ModeFlg_SWIM |
            ModeFlg_LADDER |
            ModeFlg_CAUGHT
        );
    }
    u32 checkNoResetFlg1(daPy_FLG1 flag) const { return mNoResetFlg1 & flag; }
    u32 checkModeFlg(u32 flag) const { return mModeFlg & flag; }
    // d_a_player_main.h:1883-1884.
    void onModeFlg(u32 flag) { mModeFlg |= flag; }
    void offModeFlg(u32 flag) { mModeFlg &= ~flag; }
    // d_a_player_main.h:1908. The L trigger (a one-frame edge), not the hold.
    BOOL spLTrigger() const { return mItemTrigger & BTN_L; }
    BOOL checkGrabWear() const { return field_0x2b0 < 0.0f; }
    // d_a_player.h:506, verbatim; daPy_py_c's, flattened.
    f32 getHeight() const { return mHeight; }
    // d_a_player.h:507, verbatim.
    s16 getBodyAngleX() const { return mBodyAngle.x; }
    // d_a_player_main.h:1977, verbatim but for `virtual`: daPy_py_c is flattened away, and a
    // vtable would move every offset.
    fpc_ProcID getThrowBoomerangID() const { return mActorKeepThrow.getID(); }
    // d_a_player_main.h:1978, without `virtual`. Stubbed: its field, mActorKeepGrab, is not
    // carried.
    fpc_ProcID getGrabActorID() const;
    BOOL spActionButton() const { return mItemButton & BTN_R; }

    // d_a_player_main.h:1874 and :1927, verbatim. checkShieldEquip is the shield slot alone, not
    // the crouch arm's longer test.
    BOOL checkShieldEquip() const { return dComIfGs_getSelectEquip(1) != dItemNo_NONE_e; }
    BOOL checkCrawlWaterIn() { return mWaterY > current.pos.y + 15.0f; }

    // d_a_player.h:574-576 and d_a_player_main.h:1899-1909, verbatim. mItemTrigger is the
    // one-frame edge word setStickData builds (d_a_player_main.cpp:10525-10611).
    void onResetFlg0(daPy_RFLG0 flag) { mResetFlg0 |= flag; }
    void offResetFlg0(daPy_RFLG0 flag) { mResetFlg0 &= ~flag; }
    u32 checkResetFlg0(daPy_RFLG0 flag) const { return mResetFlg0 & flag; }
    // d_a_player.h:581-583, verbatim. The blend functions write both foot flags, so the read sees
    // this frame's arm.
    u32 getRightFootOnGround() const { return checkResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND); }
    u32 getLeftFootOnGround() const { return checkResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND); }
    u32 getFootOnGround() const { return getRightFootOnGround() || getLeftFootOnGround(); }
    BOOL doTrigger() const { return mItemTrigger & BTN_A; }
    BOOL talkTrigger() const { return mItemTrigger & BTN_A; }
    BOOL swordTrigger() const { return mItemTrigger & BTN_B; }
    /// d_a_player_main.h:1894, verbatim: the B hold word, a different field from swordTrigger's.
    BOOL swordButton() const { return mItemButton & BTN_B; }
    BOOL itemTriggerX() const { return mItemTrigger & BTN_X; }
    BOOL itemTriggerY() const { return mItemTrigger & BTN_Y; }
    BOOL itemTriggerZ() const { return mItemTrigger & BTN_Z; }
    BOOL spActionTrigger() const { return mItemTrigger & BTN_R; }

    // d_a_player_main.h:1807-1828, verbatim. All read `m_anm_heap_upper[UPPER_MOVE2_e].mIdx`.
    BOOL checkUpperAnime(u16 i_idx) const { return m_anm_heap_upper[UPPER_MOVE2_e].mIdx == i_idx; }
    BOOL checkNoUpperAnime() const { return m_anm_heap_upper[UPPER_MOVE2_e].mIdx == 0xFFFF; }
    BOOL checkGrabAnime() const { return checkGrabAnimeLight() || checkGrabAnimeHeavy(); }
    BOOL checkGrabAnimeLight() const { return checkUpperAnime(dRes_INDEX_LKANM_BCK_GRABWAIT_e); }
    BOOL checkGrabAnimeHeavy() const { return checkUpperAnime(dRes_INDEX_LKANM_BCK_GRABWAITB_e); }
    BOOL checkBoomerangThrowAnime() const { return checkUpperAnime(dRes_INDEX_LKANM_BCK_BOOMTHROW_e); }
    BOOL checkBoomerangReadyAnime() const { return checkUpperAnime(dRes_INDEX_LKANM_BCK_BOOMWAIT_e); }
    BOOL checkHookshotReadyAnime() const { return checkUpperAnime(dRes_INDEX_LKANM_BCK_HOOKSHOTWAIT_e); }
    BOOL checkGuardSlip() const {
        return mCurProc == daPyProc_GUARD_SLIP_e ||
            mCurProc == daPyProc_CROUCH_DEFENSE_SLIP_e;
    }
    BOOL checkUpperGuardAnime() const {
        return checkUpperAnime(dRes_INDEX_LKANM_BCK_ATNG_e) ||
            checkUpperAnime(dRes_INDEX_LKANM_BCK_ATNGHAM_e);
    }

    void setFrameCtrl(J3DFrameCtrl* frameCtrl, u8 attribute, s16 start, s16 end, f32 rate, f32 frame);
    void setNormalSpeedF(f32 param_1, f32 param_2, f32 param_3, f32 param_4);
    void setSpeedAndAngleNormal(s16 param_1);
    // The targeting twin and its DIR_BACKWARD tail call.
    void setSpeedAndAngleAtn();
    void setSpeedAndAngleAtnBack();
    // The ground slope along the travel heading (setBlendAtnMoveAnime).
    s16 getGroundAngle(cBgS_PolyInfo* param_1, s16 param_2);
    // posMoveFromFootPos writes speedF, speed and current.pos; posMove is the root-motion half
    // (the m34C2 machine, carry push, wind, conveyor, whirlpool).
    void posMoveFromFootPos();
    void posMove();
    // The foot IK (`RunOptions::foot_ik`): footBgCheck runs after setWorldMatrix and before the
    // skeleton pass (d_a_player_main.cpp:11545-11548); the joint callbacks carry its answer.
    BOOL jointBeforeCB(int jnt_no, J3DTransformInfo* param_2, Quaternion* param_3);
    BOOL jointAfterCB(int jnt_no, J3DTransformInfo* param_2, Quaternion* param_3);
    BOOL jointCB1();
    int setLegAngle(f32 param_1, int param_2, s16* param_3, s16* param_4);
    void footBgCheck();
    void setWaistAngle();
    void setStepsOffset();
    // jointBeforeCB's ship arm; unreached.
    BOOL checkShipNotNormalMode();
    void setShipRideArmAngle(int jnt_no, J3DTransformInfo* param_2);
    // TRUE skips posMove's collision push, wind, slip and conveyor. False for every ported proc
    // (`no_collision_corret_true`).
    BOOL checkNoCollisionCorret();
    // posMove's whirlpool arm; unreached stub.
    void startRestartRoom(int param_1, int param_2, f32 param_3, int param_4);
    // At the boundary (stubs.cpp).
    void setBeltConveyerPower();
    void setWindAtPower();
    f32 getSwimTimerRate();
    BOOL procMove();
    BOOL itemTrigger() const;
    BOOL checkPlayerGuard() const;
    void setDoStatusBasic();
    void setDoStatus();
    int getDirectionFromAngle(s16 angle);
    int getDirectionFromShapeAngle();
    int getDirectionFromCurrentAngle();
    BOOL checkSingleItemEquipAnime() const;
    BOOL checkItemEquipAnime() const;
    BOOL checkEquipAnime() const;
    BOOL checkNextActionFromButton();
    BOOL checkNextMode(int r29);
    int changeSlideProc();
    BOOL changeWaitProc();
    BOOL procMove_init();
    BOOL procFrontRoll_init(f32 param_1);
    BOOL procFrontRoll();
    void setBlendMoveAnime(f32 param_1);
    // The targeting blends. setBlendAtnMoveAnime writes mDirection and mMaxNormalSpeed, which
    // setSpeedAndAngleAtn reads next frame.
    void setBlendAtnMoveAnime(f32 f30);
    void setBlendAtnBackMoveAnime(f32 param_1);
    int setMoveAnime(f32 f27, f32 f28, f32 f25, daPy_ANM r27, daPy_ANM r28, int r29, f32 i_morf);
    void getUnderUpperAnime(const daPy_anmIndex_c* anmIndex, J3DAnmTransform** pUnderBck,
                            J3DAnmTransform** pUpperBck, int r7, u32 bufferSize);
    const daPy_anmIndex_c* getAnmData(daPy_ANM) const;
    BOOL checkRestHPAnime();
    BOOL setSingleMoveAnime(daPy_ANM anm, f32 rate, f32 start, s16 end, f32 i_morf);
    void animeUpdate();
    BOOL procWait_init();
    BOOL procWait();
    BOOL procFreeWait_init();
    BOOL procFreeWait();
    BOOL procCrouch_init();
    BOOL procCrouch();
    // The pivot: latches the heading at entry (mProcVar2.m34D4 = m34E8) and exits when the
    // cLib_addCalcAngleS residual reaches zero.
    BOOL procWaitTurn_init();
    BOOL procWaitTurn();
    // The targeting sidestep: no clock; it exits only through checkNextMode, the wall-type change
    // or the ice-slip fall.
    BOOL procAtnMove_init();
    BOOL procAtnMove();
    // changeCutProc turns a B press into one of ten procs, counting the chain in m34C4.
    // getCutDirection returns the bucket plus one (0: no direction yet); changeCutProc takes the
    // 1 back off.
    int getCutDirection();
    int changeCutProc();
    BOOL procCutA_init(s16 param_0);
    BOOL procCutA();
    BOOL procCutF_init(s16 param_0);
    BOOL procCutF();
    BOOL procCutR_init(s16 param_0);
    BOOL procCutR();
    BOOL procCutL_init(s16 param_0);
    BOOL procCutL();
    // The enders take no aim: changeCutProc drops sVar2 on that arm (d_a_player_sword.inc:425).
    BOOL procCutEA_init();
    BOOL procCutEA();
    BOOL procCutEB_init();
    BOOL procCutEB();
    // The crawl. procCrawlStart calls procCrawlEnd_init; setDoStatusCrawl and crawlBgCheck are
    // copies.
    void crawlBgCheck(cXyz* param_0, cXyz* param_1);
    /// Copied.
    int getCrawlMoveVec(cXyz* top, cXyz* front, cXyz* out);
    /// Copied. Runs at execute():11544, after posMove and the collision pass, so a proc on frame N
    /// reads frame N-1's matrix.
    void setWorldMatrix();
    /// Copied. Only execute() (:11640) calls it, and execute() is not ported.
    void setAttentionPos();
    void setDoStatusCrawl();
    BOOL procCrawlStart();
    BOOL procCrawlEnd_init(int param_1, s16 param_2, s16 param_3);
    BOOL procCrawlEnd();
    // Copies, for the jump slash landing's sword-trail arguments (the trail itself is a stub).
    BOOL checkChanceMode();
    int getSwordBlurColor();
    f32 getBlurTopRate();
    /// The three wall cylinders, from the current proc. commonProcInit's last line calls it
    /// (d_a_player_main.cpp:5899).
    void setBgCheckParam();
    // The backflip and its landing, sharing mBackJump. procBackJumpLand_init is entered only by
    // procBackJump.
    BOOL procBackJump_init();
    BOOL procBackJump();
    BOOL procBackJumpLand_init();
    BOOL procBackJumpLand();
    // The sidehop and its landing, sharing mSideStep. procSideStepLand_init is entered by
    // procSideStep.
    BOOL procSideStep_init(int param_1);
    BOOL procSideStep();
    BOOL procSideStepLand_init();
    BOOL procSideStepLand();
    /// The mid-air jump slash procSideStep asks for on every airborne frame. Copied.
    BOOL checkJumpCutFromButton();
    /// Stub: the bow and boomerang's mid-air aim.
    void checkNextActionItemFly();
    BOOL procCutTurn_init(BOOL param_0);
    BOOL procCutTurn();
    BOOL procCutTurnCharge_init();
    BOOL procCutTurnCharge();
    BOOL procCutTurnMove_init();
    BOOL procCutTurnMove();
    /// d_a_player_main.cpp:2625. Copied.
    void setShapeAngleToAtnActor();
    /// d_a_player_boomerang.inc:19. Copied.
    BOOL checkBoomerangAnime() const;

    /// d_a_player.h:597 and :611, verbatim. checkNormalSwordEquip asks equip slot 0.
    BOOL checkSwordMiniGame() const { return dComIfGp_getMiniGameType() == 2; }
    BOOL checkNormalSwordEquip() const {
        return dComIfGs_getSelectEquip(0) == dItemNo_SWORD_e || checkSwordMiniGame();
    }

    // d_a_player_main.h:1890-1891 and 1913, verbatim.
    J3DAnmTransform* getNowAnmPackUnder(daPy_UNDER idx) { return mAnmRatioUnder[idx].getAnmTransform(); }
    J3DAnmTransform* getNowAnmPackUpper(daPy_UPPER idx) { return mAnmRatioUpper[idx].getAnmTransform(); }
    BOOL checkPlayerDemoMode() const { return mDemo.getDemoType() != daPy_demo_c::TYPE_NONE_e; }

    // d_a_player.h:547-548, verbatim.
    void onNoResetFlg1(daPy_FLG1 flag) { mNoResetFlg1 |= flag; }
    void offNoResetFlg1(daPy_FLG1 flag) { mNoResetFlg1 &= ~flag; }

    // ---- the boundary ----------------------------------------------------------------------
    // Called by ported bodies and defined in boundary/stubs.cpp; the flags below drive them.

    void commonProcInit(int proc);             ///< STUB: records mCurProc. See stubs.cpp.
    void setFrontWallType();                   ///< PARTIAL: the decomp's guard chain only.
    BOOL checkHeavyStateOn();                  ///< STUB, driven by `stub_heavy_state`.
    cM3dGPla* getSlidePolygon();               ///< STUB, driven by `stub_slide_polygon`.
    void setFootEffectPosType(int type);       ///< STUB: effects only.
    void endFlameDamageEmitter();              ///< STUB: effects only.
    void voiceStart(int id);                   ///< STUB: audio only.
    BOOL procFrontRollCrash_init();            ///< STUB: records the crash. See stubs.cpp.

    // procBackJump's own boundary: the two arms that are not the landing.
    BOOL checkFanGlideProc(int param);         ///< STUB, UNREACHED: no Deku Leaf. See stubs.cpp.
    BOOL procFall_init(int type, f32 param);   ///< STUB, UNREACHED: the drop past field_0x1C.

    // checkNextMode's own boundary.
    BOOL checkAttentionLock();                 ///< STUB, driven by `stub_attention_lock`.
    BOOL checkUpperReadyThrowAnime() const;    ///< STUB, driven by `stub_upper_ready_throw`.
    BOOL procVomitJump_init(int type);         ///< STUB: records which init the dispatch chose.
    BOOL procSlideFront_init(s16 angle);       ///< ditto
    BOOL procSlideBack_init(s16 angle);        ///< ditto
    BOOL checkNextBoomerangMode();             ///< ditto
    BOOL checkNextBowMode();                   ///< ditto
    BOOL checkNextHookshotMode();              ///< ditto
    BOOL checkNextRopeMode();                  ///< ditto
    BOOL procAtnActorWait_init();              ///< ditto
    BOOL procAtnActorMove_init();              ///< ditto
    BOOL procMoveTurn_init(int param);
    BOOL procMoveTurn();
    BOOL procSlip_init();
    BOOL procSlip();
    BOOL checkJumpFlower();                    ///< ditto

    // procMove's own boundary: the two tests between checkNextMode and the anim blend.
    BOOL changeFrontWallTypeProc();            ///< STUB: the wall-type proc change. See stubs.cpp.
    BOOL checkIceSlipFall();                   ///< STUB: the ice-slip fall. See stubs.cpp.

    // setBlendMoveAnime / setMoveAnime's own boundary.
    J3DAnmTransform* getAnimeResource(daPy_anmHeap_c* anmHeap, u16 index, u32 bufferSize);
                                               ///< PARTIAL: the archive load, as metadata only.
    void setTextureAnime(u16 btpIdx, int r31); ///< STUB: the texture animation.
    void setSeAnime(daPy_anmHeap_c* heap, J3DFrameCtrl* ctrl);  ///< STUB: audio.
    void seStartMapInfo(u32 se);               ///< STUB: audio.
    void freeGrabItem();                       ///< STUB, UNREACHED: the ice-slip arm only.
    void setHandModel(daPy_ANM anmIdx);        ///< STUB: the hand-joint columns this port drops.
    void resetFootEffect();                    ///< STUB: effects only.

    // checkNextActionFromButton's own boundary; most entries are arms the measured path never
    // takes.
    BOOL checkBowAnime() const;                ///< d_a_player_bow.inc:64, not ported
    BOOL checkRopeAnime() const;               ///< d_a_player_rope.inc:22, ditto
    BOOL setHintActor();
    BOOL setTalkStatus();
    void setSpecialBattle(int type);
    int orderTalk();
    BOOL checkItemChangeFromButton();
    BOOL changeSpecialBattle();
    BOOL checkGuardAccept();
    int getReadyItem();
    BOOL checkBowItem(int item) const;
    BOOL checkPhotoBoxItem(int item) const;
    BOOL resetActAnimeUpper(daPy_UPPER slot, f32 i_morf);
    BOOL setActAnimeUpper(u16 index, daPy_UPPER slot, f32 rate, f32 start, s16 end, f32 morf);
    void setAnimeEquipSword(BOOL immediate);
    void deleteEquipItem(BOOL param_1);
    // The chain's 5th- and 6th-press extensions (m34C4 >= 5): record stubs, named by `next_init`.
    BOOL procCutExA_init();
    BOOL procCutExB_init();
    BOOL procCutExMJ_init(int param);
    BOOL procCutKesa_init();
    BOOL procScope_init(int item);
    BOOL procFanSwing_init();
    BOOL procTactWait_init(int param);
    BOOL checkNextActionGrab();
    BOOL checkNextActionHookshotReady();
    BOOL checkNextActionBowReady();
    BOOL checkNextActionBoomerangReady();
    BOOL checkNextActionRopeReady();
    BOOL procPushPullWait_init(int param);
    BOOL procShipReady_init();
    BOOL procHangWallCatch_init();
    BOOL procVerticalJump_init();
    BOOL procGrabReady_init();
    BOOL procJumpCut_init(int param_0);
    BOOL procJumpCut();
    BOOL procJumpCutLand_init();
    BOOL procJumpCutLand();
    BOOL procWHideReady_init(cM3dGPla* pla, cXyz* pos);
    BOOL procCutRoll_init();
    BOOL procWeaponNormalSwing_init();
    BOOL procWeaponSideSwing_init();
    BOOL procWeaponFrontSwingReady_init();
    BOOL procWeaponThrow_init();
    BOOL procBottleSwing_init(int param);
    BOOL procHammerSideSwing_init();
    BOOL procHammerFrontSwingReady_init();
    BOOL procCall_init();
    BOOL procCrouchDefense_init();
    BOOL procSubjectivity_init(BOOL param);
    BOOL procGrabWait_init();
    BOOL procBoomerangCatch_init();
    BOOL procControllWait_init();

    // procCrouch's crawl arm.
    BOOL procCrawlStart_init();
    /// Stub: the crawl's steered continuation; no banked frame is in it.
    BOOL procCrawlMove_init(s16 param_1, s16 param_2);
    /// Stub: setDoStatusCrawl's camera arm. It writes only mBodyAngle, which nothing ported reads.
    void setBodyAngleToCamera();
    /// Stub: "has first-person been left", asked only inside setDoStatusCrawl's 0x80 arm.
    BOOL checkSubjectEnd(BOOL param_1);
    /// Stub: the entry to first-person, behind dCamAttnStts_00001000_e.
    void setSubjectMode();

    // procCutA's own boundary. Only changeCutReverseProc (the sword bounce) can end the proc early.
    J3DAnmTransform* getItemAnimeResource(u16 index);  ///< PARTIAL: records the index, loads nothing
    void setBlurPosResource(u16 index);        ///< STUB: the sword-trail position buffer
    void setNormalCutAtParam(u8 cutType);      ///< STUB: the attack collision's parameters
    /// PARTIAL: keeps the counter it zeroes; the setAtParam and radius lookup under it are not.
    void setJumpCutAtParam();
    /// Stub: Link's health (the save file). The amount is recorded.
    BOOL setDamagePoint(f32 amount);
    /// Stub, unreached: the Skull Hammer's ground quake, behind `mEquipItem == SKULL_HAMMER`.
    void setHammerQuake(cBgS_PolyInfo* poly, const cXyz* pos, int param);
    void setFinishCutAtParam(u8 cutType);      ///< STUB: the enders' own, one table over
    void seStartSwordCut(u32 se);              ///< STUB: audio
    int changeCutReverseProc(daPy_ANM anm);    ///< STUB, driven by `stub_cut_reverse`
    void seStartSystem(u32 se);                ///< STUB: audio
    void initSeAnime();                        ///< STUB: the animation's own sound track

    // procCutTurn's own boundary: emitters, the smoke callback, the sea colour, the BOKO attack
    // power and the joint matrices. Each records its argument; m35A0 is a field, not a stub.

    // procWait's own boundary: four arms and one texture call, none of them on the measured path.
    BOOL procIceSlipAlmostFall_init();          ///< STUB: the ice-slip fall, records the arm.
    void changeTextureAnime(u16 btp, u16 btk, int r5);  ///< STUB: the texture animation.

    // ---- how a test drives the boundary -----------------------------------------------------
    BOOL stub_heavy_state;      ///< what checkHeavyStateOn() returns
    cM3dGPla* stub_slide_polygon;   ///< what getSlidePolygon() returns
    u32 stub_mtrl_snd_id;       ///< what dComIfG_Bgsp()->GetMtrlSndId(mAcchCir[0]) returns
    BOOL stub_attention_lock;   ///< what checkAttentionLock() returns
    BOOL stub_upper_ready_throw;///< what checkUpperReadyThrowAnime() returns
    BOOL stub_bow_anime;        ///< what checkBowAnime() returns
    BOOL stub_rope_anime;       ///< what checkRopeAnime() returns
    BOOL stub_hint_actor;       ///< what setHintActor() returns
    BOOL stub_talk_status;      ///< what setTalkStatus() returns
    BOOL stub_order_talk;       ///< what orderTalk() returns
    BOOL stub_item_change;      ///< what checkItemChangeFromButton() returns
    BOOL stub_special_battle;   ///< what changeSpecialBattle() returns
    BOOL stub_guard_accept;     ///< what checkGuardAccept() returns
    BOOL stub_curse;            ///< what daPy_dmEcallBack_c::checkCurse() returns
    /// The camera attention-status word as a mask, as the decomp tests it
    /// (`status & mAttentionStatus`): the ported bodies ask about 0x1000 (C-stick up) and 0x80
    /// (crawl camera).
    u32 stub_camera_attn;       ///< the bits dComIfGp_checkCameraAttentionStatus() answers yes to
    /// The status0 word, masked (`status & mPlayerStatus0`).
    u32 stub_player_status0;    ///< the bits dComIfGp_checkPlayerStatus0() answers yes to
    /// The status1 word; nextMode asks both words on one arm.
    u32 stub_player_status1;    ///< the bits dComIfGp_checkPlayerStatus1() answers yes to
    /// What dComIfGs_getSelectEquip(slot) returns, by slot (0 sword, 1 shield).
    int stub_select_equip[2];
    int stub_mini_game_type;    ///< what dComIfGp_getMiniGameType() returns
    /// What changeCutReverseProc() returns: the sword bounce. The gate runs it both ways.
    BOOL stub_cut_reverse;
    int stub_select_item;       ///< what dComIfGp_getSelectItem(btn) returns
    int stub_ready_item;        ///< what getReadyItem() returns
    BOOL stub_is_player_actor;  ///< whether daPy_getPlayerActorClass() == this
    BOOL stub_jump_flower;      ///< what checkJumpFlower() returns
    BOOL stub_carried_movement_only; ///< Opt-in light-object movement, with actor Co evaluated externally.
    BOOL stub_carried_release_model;
    BOOL port_carried_released;
    s16 port_carried_slant;
    s16 port_carried_draw_lean;
    f32 port_carried_pose_morf;
    int stub_life;              ///< what dComIfGs_getLife() returns, in quarter-hearts
    u8 stub_eye_move_flg;       ///< what daPy_matAnm_c::getEyeMoveFlg() returns
    f32 stub_rnd;               ///< what cM_rnd() returns; the RNG is not ported
    BOOL stub_event_run;        ///< what dComIfGp_event_runCheck() returns
    BOOL stub_change_mode_ok;   ///< what dCam_getBody()->ChangeModeOK(4) returns
    /// The hurricane spin's save-data questions (procCutTurnMove_init): learned (either flag) and
    /// magic. The capture cannot separate the answers, so the gate runs both.
    BOOL stub_event_bit;        ///< what dComIfGs_isEventBit(UNK_0B20) returns
    BOOL stub_tmp_bit;          ///< what dComIfGs_isTmpBit(UNK_0402) returns
    u8 stub_magic;              ///< what dComIfGs_getMagic() returns; the init wants >= 2

    // ---- what the boundary recorded, so a gate can assert on it ------------------------------
    /// The proc-init the dispatch chose, as a daPyProc id, or -1.
    int next_init;
    int next_init_calls;        ///< how many inits were reached (must be 0 or 1)
    /// Times setFrontWallType was entered. Only checkNextMode calls it, so this is checkNextMode's
    /// call count.
    int wall_type_calls;
    /// ...of which came from changeFrontWallTypeProc (procMove's second call site).
    int front_wall_proc_calls;
    int wall_type_scan_reached; ///< ...and how many times it got past the guards into collision
    /// Calls to stubs graded unreachable on the measured path. The gate requires 0.
    int unreached_called;
    int crash_called;           ///< how many times procFrontRollCrash_init() was reached
    int voice_id;               ///< the last voiceStart() id
    int foot_effect_type;       ///< the last setFootEffectPosType() type
    /// Anims asked for whose frameMax is not in anm_meta.inc, by slot. An under miss gives a wrong
    /// rate on every later frame, so the gate requires 0; an upper miss only fills
    /// mFrameCtrlUpper, which nothing reads, so the gate prints those.
    int anm_meta_missing;
    int anm_meta_missing_upper;
    int anm_meta_missing_idx;   ///< ...and the last index it was asked for, so the gate can name it
    /// .bck loads. getUnderUpperAnime loads only when a slot's mIdx changes, so this counts
    /// animation changes.
    int anm_resource_loads;
    /// Calls to a stub with its stated precondition broken. The gate requires 0.
    int precondition_broken;
    /// Times checkNextActionFromButton reached its tail return (a copy cannot count its entries).
    int button_dispatch_fellthrough;
    int jump_flower_calls;      ///< how many times checkJumpFlower() was asked
    int texture_anime_calls;    ///< setTextureAnime + changeTextureAnime entries
    /// Draws from the game's RNG. The RNG is not ported (its seeds are boot-time globals), so the
    /// gate requires 0 on every compared frame.
    int rnd_draws;
    int r_status;               ///< dComIfGp_setRStatus's last value; execute() clears it to BLANK
    int do_status;              ///< dComIfGp_setDoStatus's, likewise

    // ---- what procCutA's boundary recorded --------------------------------------------------
    /// The .bck index the last changeBckOnly was handed, or -1: which arm of procCutA_init's
    /// checkNormalSwordEquip fork ran.
    int sword_anim_idx;
    int blur_pos_idx;           ///< ...and the index setBlurPosResource was handed
    int cut_at_param_type;      ///< ...and the daPy_CUT_TYPE setNormalCutAtParam was handed
    int sword_cut_se;           ///< ...and the last seStartSwordCut id
    u32 player_status0;         ///< the bits dComIfGp_setPlayerStatus0(0, ...) has raised

    // ---- what procCutTurn's boundary recorded -----------------------------------------------
    /// The particle id of the last makeEmitter / makeEmitterColor / setToonP1, or -1: which arm
    /// of procCutTurn_init's ground fork ran.
    int particle_toe_id;        ///< m32E4's, always spawned
    int particle_ground_id;     ///< m32F0's / the smoke's - whichever arm the attribute picked
    int particle_toe_joint;     ///< ...and the joint index getAnmMtx was asked for
    int particle_ground_joint;
    int particle_ends;          ///< how many times either emitter's end() was called
    int smoke_removes;          ///< ...and mSmokeEcallBack.remove()
    /// The joint index the last getAnmMtx was asked for.
    int last_anm_mtx_joint;
    // ---- what the integration's boundary recorded --------------------------------------------
    /// The two power terms' calls.
    int belt_conveyer_calls;
    int wind_at_power_calls;
    // ---- what procCutTurnMove's boundary recorded --------------------------------------------
    /// The bits dComIfGp_setPlayerStatus1(0, ...) has raised. procCutTurnMove raises one only when
    /// its charge countdown reaches 0.
    u32 player_status1;
    /// The last seStartSystem id and how many frames asked: the only observable of
    /// procCutTurnMove_init's hurricane fork.
    int system_se;
    int system_se_calls;
    int se_anime_inits;         ///< how many times initSeAnime() was entered
    // procCutTurnMove_init's emitters land in `particle_toe_id` / `particle_ground_id` (the same
    // members), so read them at the init. The attack power is mAtCyl.mObjAt.mAtp.

    // ---- what procBackJump's boundary recorded ------------------------------------------------
    /// Times checkFanGlideProc(0) was asked: every airborne backflip frame.
    int fan_glide_calls;
    /// ...and procFall_init (also in `unreached_called`): the drop arm stayed shut.
    int fall_init_calls;
    int evmng_cut_end_calls;    ///< procBackJumpLand's event arm; `unreached_called` counts it too
    int shock_calls;            ///< the landing's heavy-state rumble; likewise
    /// procJumpCutLand_init's fall damage: the count and the amount (-2.0 or -1.0).
    int damage_calls;
    f32 damage_amount;
    /// The sword trail's scalar arguments as procJumpCutLand_init computed them.
    int sw_blur_calls;
    int sw_blur_frames;
    f32 sw_blur_top_rate;
    int sw_blur_color;
    /// ...and whether the base matrix was fetched for it.
    int base_tr_mtx_calls;
    /// setHammerQuake, the other side of the landing's equip fork. Unreached.
    int hammer_quake_calls;
    /// changeCutReverseProc's asks; procJumpCut asks on every airborne frame.
    int cut_reverse_calls;

    // ---- what the crawl's boundary recorded ---------------------------------------------------
    /// The A-status setDoStatusCrawl posts, or BLANK: the first statement of its 0x80 arm.
    int a_status;
    /// setBodyAngleToCamera's calls (it writes only mBodyAngle).
    int body_angle_calls;
    /// ...and how many times the other two arms of the same test were asked.
    int subject_end_calls;
    int subject_mode_calls;
    /// procCrawlMove_init's calls; the gate holds it at 0.
    int crawl_move_init_calls;
    /// J3DAnmTransform::getTransform's calls (procCrawlEnd_init's root-motion seed, and posMove's
    /// every frame).
    int anm_transform_calls;
    /// ...of which asked for a non-root joint.
    int anm_track_nonroot;
    /// ...of which asked for an animation with no baked track. The gate requires 0.
    int anm_track_missing;
    /// ...of which asked for a joint past the .bck's mJointNum, which would read the next
    /// animation's keytables.
    int anm_track_overrun;
    /// The frameMax of the last such animation, which identifies it.
    int anm_track_missing_idx;

    // ---- posMove's boundary counter ----------------------------------------------------------
    /// Every `mStts.GetCCMoveP()` ask: four per frame on the main path, three on the
    /// checkNoCollisionCorret fork. posMove's other arms all write
    /// `getOldFrameTransInfo(0)->mTranslate`, which `the_old_frame_transform_is_untouched` checks.
    int cc_move_asks;

    /// setWorldMatrix's calls; the harness drives it.
    int world_matrix_calls;
    /// dComIfGp_getShipActor's calls. setWorldMatrix asks every frame, so this equals
    /// `world_matrix_calls`.
    int ship_actor_calls;

    void reset_boundary() {
        stub_heavy_state = FALSE;
        stub_slide_polygon = 0;
        stub_mtrl_snd_id = 0;
        stub_attention_lock = FALSE;
        stub_upper_ready_throw = FALSE;
        stub_bow_anime = stub_rope_anime = FALSE;
        stub_hint_actor = stub_talk_status = stub_order_talk = FALSE;
        stub_item_change = stub_special_battle = stub_guard_accept = FALSE;
        stub_curse = FALSE;
        stub_player_status0 = stub_player_status1 = 0;
        stub_camera_attn = 0;
        stub_select_equip[0] = stub_select_equip[1] = dItemNo_NONE_e;
        stub_mini_game_type = 0;
        // No shield or wall in the sword's line check: the capture's regime.
        stub_cut_reverse = FALSE;
        sword_anim_idx = blur_pos_idx = cut_at_param_type = sword_cut_se = -1;
        player_status0 = 0;
        particle_toe_id = particle_ground_id = -1;
        particle_toe_joint = particle_ground_joint = -1;
        particle_ends = smoke_removes = 0;
        last_anm_mtx_joint = -1;
        belt_conveyer_calls = wind_at_power_calls = 0;
        player_status1 = 0;
        system_se = -1;
        system_se_calls = se_anime_inits = 0;
        // No hurricane spin and no magic: the charge arm is shut. The capture cannot confirm it
        // (47 frames outlast either run), so the gate also runs it the other way.
        stub_event_bit = stub_tmp_bit = FALSE;
        stub_magic = 0;
        mAtCyl.SetAtAtp(-1);
        // Link's own model; procCutTurn_init dereferences mpCLModel unconditionally.
        mpCLModel = &port_cl_model;
        // The thrust's blade-flash animators, dereferenced unconditionally. Seeded to -1 so an init
        // that wrote field_0x8 is distinguishable from one that was skipped.
        mpCutfBpk = &port_cutf_bpk;
        mpCutfBtk = &port_cutf_btk;
        mpCutfBpk->setFrame(-1.0f);
        mpCutfBtk->setFrame(-1.0f);
        // The blur ribbons start transparent; procCutTurn reads the alpha back.
        m331C.setAlpha(0); m332C.setAlpha(0); m333C.setAlpha(0);
        // Not the game's starting radius (dCcD_Cyl::Set's source is not carried); the gate checks
        // the chase's step count from this seed.
        mAtCyl.SetR(0.0f);
        m35A0 = m35A4 = 0.0f;
        m34C4 = 0;
        mCutType = mCutCount = 0;
        stub_select_item = dItemNo_NONE_e;
        stub_ready_item = dItemNo_NONE_e;
        stub_is_player_actor = TRUE;
        stub_jump_flower = FALSE;
        stub_carried_movement_only = FALSE;
        stub_carried_release_model = port_carried_released = FALSE;
        port_carried_slant = port_carried_draw_lean = 0;
        port_carried_pose_morf = 0.0f;
        stub_life = 80;         // twenty hearts; the capture has no life column - see stubs.cpp
        stub_eye_move_flg = 0;
        stub_rnd = 0.0f;
        rnd_draws = 0;
        // The camera lets the mode change: the permissive side, which the sweep flips.
        stub_change_mode_ok = TRUE;
        // The skeleton has been calculated, as in every banked capture; the old-frame rate stays
        // at its constructor's 0.0.
        port_old_fdata.onOldFrameFlg();
        // No cutscene is driving Link.
        stub_event_run = FALSE;
        // No water: the game's own -G_CM3D_F_INF (c_m3d.h:25), which setWaterY leaves when
        // mAcch.m_wtr has no plane. setWaterY runs after the proc dispatch (execute():11405), so
        // mWaterY carries across frames.
        mWaterY = -1000000000.0f;
        m_tex_anm_heap.mIdx = m_tex_scroll_heap.mIdx = 0xFFFF;
        m_tex_scroll_heap.field_0x6 = 0;
        m3530 = 0;
        mProcVar1.m34D2 = 0;
        next_init = -1;
        next_init_calls = crash_called = 0;
        wall_type_calls = wall_type_scan_reached = unreached_called = 0;
        front_wall_proc_calls = 0;
        precondition_broken = button_dispatch_fellthrough = jump_flower_calls = 0;
        texture_anime_calls = 0;
        anm_meta_missing = anm_meta_missing_upper = anm_resource_loads = 0;
        mpParachuteFanMorf = NULL;
        anm_meta_missing_idx = -1;
        voice_id = foot_effect_type = -1;
        r_status = do_status = dActStts_BLANK_e;
        // The game's "this slot holds no animation", so a run's first getUnderUpperAnime loads.
        m_anm_heap_under[UNDER_MOVE0_e].mIdx = m_anm_heap_under[UNDER_MOVE1_e].mIdx = 0xFFFF;
        m_anm_heap_upper[UPPER_MOVE0_e].mIdx = m_anm_heap_upper[UPPER_MOVE1_e].mIdx = 0xFFFF;
        m_anm_heap_upper[UPPER_MOVE2_e].mIdx = 0xFFFF;   // checkNoUpperAnime()'s own sentinel
        mEquipItem = daPyItem_NONE_e;
        mReadyItemBtn = dItemBtn_X_e;
        fan_glide_calls = fall_init_calls = evmng_cut_end_calls = shock_calls = 0;
        damage_calls = sw_blur_calls = sw_blur_frames = sw_blur_color = 0;
        base_tr_mtx_calls = hammer_quake_calls = cut_reverse_calls = 0;
        damage_amount = sw_blur_top_rate = 0.0f;
        a_status = dActStts_BLANK_e;
        body_angle_calls = subject_end_calls = subject_mode_calls = 0;
        crawl_move_init_calls = 0;
        anm_transform_calls = anm_track_nonroot = anm_track_missing = 0;
        anm_track_overrun = 0;
        anm_track_missing_idx = -1;
        cc_move_asks = 0;
        world_matrix_calls = 0;
        // fopAcM_create's: Link is not scaled.
        scale.x = scale.y = scale.z = 1.0f;
        m34EC = m353C = m353E = 0;
        m35C4 = m3608 = 0.0f;
        m35B8 = 0.0f;
        m34C6 = 0;
        m3668 = J3DTransformInfo();
        m3658.x = m3658.y = m3658.z = m3658.w = 0.0f;
        m3648 = m3658;
        m3516 = m3518 = m351A = m34E4 = 0;
        m35D8 = 0.0f;
        m34F2 = m34F4 = m34F6 = m34F8 = m34FA = m34FC = m34FE = m3500 = 0;
        m350E = m3510 = m3512 = m3528 = 0;
        for (int i = 0; i < 2; i++) {
            daPy_footData_c& foot = mFootData[i];
            foot.field_0x000 = foot.field_0x001 = 0;
            foot.field_0x002 = foot.field_0x004 = foot.field_0x006 = 0;
            foot.field_0x008 = foot.field_0x00A = 0;
            foot.field_0x00C = foot.field_0x018 = foot.field_0x024 = cXyz(0.0f, 0.0f, 0.0f);
            foot.field_0x030 = 0.0f;
        }
        ship_actor_calls = 0;
        m_old_fdata = &port_old_fdata;
        m_pbCalc[PART_UNDER_e] = &port_pbcalc_under;
        m_pbCalc[PART_UPPER_e] = &port_pbcalc_upper;
        mWhirlId = (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
        eventInfo.mCommand = dEvt_info_c::dEvtCmd_NONE_e;
        mBodyAngle.x = mBodyAngle.y = mBodyAngle.z = 0;
        m35E4 = 0.0f;
        // fopAcM_create sets the name from the process profile; d_camera.cpp's is_player
        // compares it.
        mProcName = fpcNm_PLAYER_e;
        // commonDataInit's, d_a_player_main.cpp:12201, and the decomp's only write to it.
        mHeight = 125.0f;
        // attention_info is left unseeded: its writer, setAttentionPos, is never called here.
    }
};

/// d_a_player.h:437. daPy_py_c is daPy_lk_c's base in the decomp; the port flattens the two, and
/// the typedef keeps copied casts such as heightOf's `((daPy_py_c*)i_actor)` compiling. The copied
/// `is_player` guards that cast.
typedef daPy_lk_c daPy_py_c;

/// d_com_inf_game.h:3441, a free inline in the decomp. Stub.
BOOL dComIfGp_event_runCheck();

/// d_com_inf_game.h: the collision world, set by set_dComIfG_Bgsp; null until set.
dBgS* dComIfG_Bgsp();
void set_dComIfG_Bgsp(dBgS* bgs);

// ---- the game-info accessors the ported bodies call ------------------------------------------
// Free inlines over `g_dComIfG_gameInfo` in the decomp (d_com_inf_game.h:3013-3049), routed here
// to the player's recorded copy. set_dComIfG_player names the one player; a second is asserted.
void set_dComIfG_player(daPy_lk_c* lk);

int dComIfGs_getLife();

u8 dComIfGp_getRStatus();
void dComIfGp_setRStatus(u8 status);
u8 dComIfGp_getDoStatus();
void dComIfGp_setDoStatus(u8 status);
int dComIfGs_getSelectEquip(int slot);
int dComIfGp_getSelectItem(int btn);
BOOL dComIfGp_checkCameraAttentionStatus(int idx, u32 status);
BOOL dComIfGp_checkPlayerStatus0(int idx, u32 status);
/// d_com_inf_game.h, masked against stub_player_status1.
BOOL dComIfGp_checkPlayerStatus1(int idx, u32 status);
void dComIfGp_setPlayerStatus0(int idx, u32 status);
void dComIfGp_clearPlayerStatus0(int idx, u32 status);
void dComIfGp_setPlayerStatus1(int idx, u32 status);
/// d_com_inf_game.h:506-507, routed to the player's recorded copy like r_status and do_status.
u8 dComIfGp_getAStatus();
void dComIfGp_setAStatus(u8 status);
int dComIfGp_att_getZHint();
daPy_lk_c* daPy_getPlayerActorClass();

/// d_com_inf_game.h, a free inline in the decomp. Stub, unreached: procBackJumpLand's event arm.
void dComIfGp_evmng_cutEnd(int staffIdx);

/// d_vibration.h:7 and :70, trimmed to StartShock. A class because the copied call is
/// `dComIfGp_getVibration().StartShock(...)`.
class dVibration_c {
public:
    bool StartShock(int type, int power, cXyz dir);
};

dVibration_c& dComIfGp_getVibration();

u32 fopAcM_GetParam(fopAc_ac_c* actor);
u32 fopAcM_GetName(fopAc_ac_c* actor);
BOOL fopAcM_CheckStatus(fopAc_ac_c* actor, u32 status);
void fopAcM_orderZHintEvent(daPy_lk_c* lk, int hint);
void fopAcM_orderDoorEvent(daPy_lk_c* lk, fopAc_ac_c* actor);
void fopAcM_orderTreasureEvent(daPy_lk_c* lk, fopAc_ac_c* actor);
/// f_op_actor_mng.h. No actor manager here, so it answers NULL. Stub.
fopAc_ac_c* fopAcM_SearchByID(fpc_ProcID id);

#endif
