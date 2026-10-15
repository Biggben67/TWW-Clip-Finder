// stubs.cpp - the boundary: everything the ported bodies call and do not implement.
//
// Each definition opens with its grade, strongest first:
//   READ     - the decomp body was read; it writes nothing a ported body reads.
//   MEASURED - the capture shows the console took the path assumed. Holds for that run only.
//   PARTIAL  - some of the decomp's own lines are kept; the rest is cut.
//   STUB     - answers a constant and records that it was asked.
//   SCOPE    - real, outside the slice; nothing ported depends on it. The weakest claim.
//   UNREACHED - with SCOPE: never called on the ported path; each bumps a counter tests require 0.
//   HARNESS  - test instrumentation, not a claim about the game.

#include "d/actor/d_a_player_main.h"

// c_xyz.cpp:9. The one cXyz constant a copied body names: cBgS_LinChk::ct reads it.
const cXyz cXyz::Zero(0, 0, 0);
const cXyz cXyz::BaseX(1, 0, 0);
const cXyz cXyz::BaseZ(0, 0, 1);

#include "boundary/game_boundary.h"

#include "d/actor/proc_flags.inc"
#include "engine/link_assets.h"

// =============================================================================================
// HARNESS. The port-wide census behind boundary_reached() (see game_boundary.h). Defined first
// so every later stub can bump it. A fixed per-thread array: names are literals compared by
// pointer, and overflow is counted in boundary_dropped().
namespace {
struct BoundaryRow {
    const char* who;
    const char* grade;
    int hits;
};
thread_local BoundaryRow s_boundary_rows[256];
thread_local int s_boundary_row_count = 0;
thread_local int s_boundary_total = 0;
thread_local int s_boundary_dropped = 0;
}  // namespace

void boundary_reached(const char* who, const char* grade) {
    s_boundary_total++;
    for (int i = 0; i < s_boundary_row_count; i++) {
        if (s_boundary_rows[i].who == who) {
            s_boundary_rows[i].hits++;
            return;
        }
    }
    if (s_boundary_row_count < static_cast<int>(ARRAY_SIZE(s_boundary_rows))) {
        s_boundary_rows[s_boundary_row_count].who = who;
        s_boundary_rows[s_boundary_row_count].grade = grade;
        s_boundary_rows[s_boundary_row_count].hits = 1;
        s_boundary_row_count++;
    } else {
        s_boundary_dropped++;
    }
}

void boundary_reset() {
    s_boundary_row_count = 0;
    s_boundary_total = 0;
    s_boundary_dropped = 0;
}

int boundary_hits_total() { return s_boundary_total; }

int boundary_names() { return s_boundary_row_count; }

const char* boundary_name(int i) { return s_boundary_rows[i].who; }

const char* boundary_name_grade(int i) { return s_boundary_rows[i].grade; }

int boundary_name_hits(int i) { return s_boundary_rows[i].hits; }

int boundary_dropped() { return s_boundary_dropped; }

/// The precondition checker, defined further down (search `given(`).
static BOOL given(const daPy_lk_c* lk, bool condition);

/// The player the free game-info accessors route to, as the decomp's g_dComIfG_gameInfo does.
/// Declared first so free stubs can bump its counters; set by `set_dComIfG_player`. Per thread,
/// so each walker thread answers off its own player.
thread_local daPy_lk_c* s_player = 0;

// ---------------------------------------------------------------------------------------------
// READ. d_a_player_main.cpp commonProcInit. The rest of its body writes nothing a ported proc
// reads before initialising it itself. Carried, each because a ported body reads it:
//   mModeFlg, from the decomp's proc table (proc_flags.inc);
//   gravity, the default reset on every proc entry (5813);
//   m3688 and m35F0, the launch position and height latched on a ground-to-midair entry
//   (5843-5847), read by procBackJump's drop arm and procJumpCutLand_init's fall damage.
// m35F4, in the same group, has no reader and is not carried.
void daPy_lk_c::commonProcInit(int proc) {
    const bool was_midair = checkModeFlg(ModeFlg_MIDAIR) != 0;
    mCurProc = proc;
    m3598 = 0.0f;
    if (proc >= 0 && (size_t)proc < sizeof(daPy_procInitFlags) / sizeof(daPy_procInitFlags[0])) {
        mModeFlg = daPy_procInitFlags[proc];
    } else {
        precondition_broken++;    // a proc id the decomp's table does not have
    }
    gravity = m_HIO->mAutoJump.m.field_0xC;
    // 5817: clears the buffered sword re-press, so it fires once.
    m34C5 = 0;
    // 5825: the stair offset is dropped on every proc entry.
    m35C4 = 0.0f;
    if (!was_midair && checkModeFlg(ModeFlg_MIDAIR)) {
        m3688 = current.pos;
        m35F0 = m3688.y;
    }
    // 5899, the real function's last line: the wall cylinders for the new proc's mode flags.
    setBgCheckParam();
}

// ---------------------------------------------------------------------------------------------
// PARTIAL. d_a_player_main.cpp:593-602. The real body loads a .bck from the game's archive.
// Kept: the mIdx cache, which checkUpperAnime and setBlendMoveAnime read. Replaced: the load, by
// frameMax/attribute lookups in engine/link_assets.h (from LkAnm.arc). An index with no row bumps
// anm_meta_missing instead of defaulting. bufferSize is unused; kept so call sites stay copies.
J3DAnmTransform* daPy_lk_c::getAnimeResource(daPy_anmHeap_c* anmHeap, u16 index, u32 bufferSize) {
    boundary_reached("daPy_lk_c::getAnimeResource", "PARTIAL");
    (void)bufferSize;
    daPy_portAnm_c* slot = NULL;
    BOOL upper = FALSE;
    for (int i = 0; i < 2; i++) {
        if (anmHeap == &m_anm_heap_under[i]) {
            slot = &port_anm_under[i];
        }
    }
    for (int i = 0; i < 3; i++) {
        if (anmHeap == &m_anm_heap_upper[i]) {
            slot = &port_anm_upper[i];
            upper = TRUE;
        }
    }
    if (slot == NULL) {
        // A heap the player does not own; nothing in this slice produces one.
        precondition_broken++;
        return &port_anm_under[UNDER_MOVE0_e];
    }
    const daPy_portAnmMeta* meta = tww_engine::linkAnimationMeta(index);
    // Separate from the metadata: upper animations have a frameMax but no baked root track.
    const daPy_portAnmTrack* track = tww_engine::linkAnimationTrack(index);
    if (meta == NULL) {
        if (upper) {
            anm_meta_missing_upper++;
        } else {
            anm_meta_missing++;
        }
        anm_meta_missing_idx = index;
        slot->load(0, J3DFrameCtrl::EMode_NONE, track);
    } else {
        slot->load(meta->mFrameMax, meta->mAttribute, track);
    }
    anmHeap->mIdx = index;
    anm_resource_loads++;
    return slot;
}

// SCOPE, UNREACHED. The Deku Leaf fan's morf, on a pointer that is always NULL here.
BOOL mDoExt_McaMorf::play(Vec*, u32, s8) {
    return FALSE;
}

// ---------------------------------------------------------------------------------------------
// PARTIAL. d_a_player_main.cpp:4539-4780. The guards are ported; the collision tail is not.
// `wall_type_scan_reached` counts entries past the guards and must stay 0.
void daPy_lk_c::setFrontWallType() {
    boundary_reached("daPy_lk_c::setFrontWallType", "PARTIAL");
    wall_type_calls++;
    if (mFrontWallType != 0) {
        return;
    }
    mFrontWallType = 1;
    if (!mAcch.ChkWallHit() && !checkModeFlg(ModeFlg_HOOKSHOT | ModeFlg_PUSHPULL)) {
        return;
    }
    if (checkGrabWear()) {
        return;
    }
    wall_type_scan_reached++;   // the collision tail starts here
}

// ---------------------------------------------------------------------------------------------
// PARTIAL. d_a_player_main.cpp:4770-4880. Ported down to the guard that returns FALSE on the
// ground when the stick is centred or the wall type is outside 3..9, the range every grounded
// arm tests. `given` checks it.
// Not carried: `m3544 = sVar5 + 1` (4863); m3544 only guards arms that need a wall.
// This is a second setFrontWallType call site: a no-op, but it counts in wall_type_calls.
BOOL daPy_lk_c::changeFrontWallTypeProc() {
    boundary_reached("daPy_lk_c::changeFrontWallTypeProc", "PARTIAL");
    front_wall_proc_calls++;
    setFrontWallType();                              // 4771
    s16 sVar5 = m3544;                               // 4772-4773, both carried: the write is this
    m3544 = 0;                                       // function's, the read belongs past the cut
    (void)sVar5;
    return given(this, (mStickDistance <= 0.05f && !checkModeFlg(ModeFlg_MIDAIR)) ||
                           (!checkModeFlg(ModeFlg_MIDAIR) &&
                            (mFrontWallType < 3 || mFrontWallType > 9)));
}

// ---------------------------------------------------------------------------------------------
// PARTIAL. d_a_player_main.cpp:4513-4538. The one TRUE return needs the ice-slip vector m36A0
// over a threshold; only a slip polygon sets it, so the precondition is "no ice". The else arm's
// `mProcVar0.m34D0 = 20` is carried.
BOOL daPy_lk_c::checkIceSlipFall() {
    boundary_reached("daPy_lk_c::checkIceSlipFall", "PARTIAL");
    const f32 slip_needed = (m34C3 == 1) ? 169.0f : 49.0f;   // 4518-4524, the decomp's own pair
    BOOL r = given(this, m36A0.abs2XZ() < slip_needed);
    mProcVar0.m34D0 = 20;                            // 4535
    return r;
}

// ---------------------------------------------------------------------------------------------
// SCOPE, driven by the test. d_a_player_main.cpp 5617: a heavy object or the iron boots. A flag
// so the ported heavy branch can be tested.
BOOL daPy_lk_c::checkHeavyStateOn() {
    return stub_heavy_state;
}

// ---------------------------------------------------------------------------------------------
// MEASURED. A slide polygon would decay mNormalSpeed in procFrontRoll; the capture holds 5.0 on
// all sixteen roll frames (43..58). changeSlideProc takes its else arm off the same NULL.
cM3dGPla* daPy_lk_c::getSlidePolygon() {
    return stub_slide_polygon;
}

// ---------------------------------------------------------------------------------------------
// SCOPE. Particle/effect calls; recorded so a test can see the frame-6 effect point.
void daPy_lk_c::setFootEffectPosType(int type) {
    mFootEffectPosType = (u8)type;
    foot_effect_type = type;
}

void daPy_lk_c::endFlameDamageEmitter() {
}

// SCOPE. Audio.
void daPy_lk_c::voiceStart(int id) {
    voice_id = id;
}

// SCOPE, UNREACHED. The roll bonk; `crash_called` checks it did not run.
BOOL daPy_lk_c::procFrontRollCrash_init() {
    crash_called++;
    return true;
}

// ---------------------------------------------------------------------------------------------
// checkNextMode's own boundary.
// ---------------------------------------------------------------------------------------------

// MEASURED. checkNextMode's `r24` fork into the targeting arm (procs 7-9). The real body is
// `mpAttention->Lockon()` (d_a_player_main.h:1920); driven from the capture's `lock_l` column
// (cPadInfo+0x35). The console read proc 6 at frame 59.
BOOL daPy_lk_c::checkAttentionLock() {
    return stub_attention_lock;
}

// MEASURED, same argument. d_a_player_main.cpp 1364: four upper-body anim tests, each needing an
// item drawn.
BOOL daPy_lk_c::checkUpperReadyThrowAnime() const {
    return stub_upper_ready_throw;
}

// Every UNREACHED stub bumps this; the gate requires the total to be 0.
static void unreached(const daPy_lk_c* lk) {
    const_cast<daPy_lk_c*>(lk)->unreached_called++;
}

// ---------------------------------------------------------------------------------------------
// setBlendMoveAnime / setMoveAnime's callees.

// SCOPE. d_a_player_main.cpp:760. Link's eye and mouth texture animation. m3530 is not written;
// its only readers (procWait_init, procWait) pass it straight back here.
void daPy_lk_c::setTextureAnime(u16 btpIdx, int r31) {
    (void)btpIdx;
    (void)r31;
    texture_anime_calls++;
}

// SCOPE. Both are audio: setSeAnime arms the footstep/cloth sound track against a frame ctrl,
// seStartMapInfo starts one positioned in the room. Neither writes a word a ported body reads.
void daPy_lk_c::setSeAnime(daPy_anmHeap_c* heap, J3DFrameCtrl* ctrl) {
    (void)heap;
    (void)ctrl;
}

void daPy_lk_c::seStartMapInfo(u32 se) {
    (void)se;
}

// SCOPE. d_a_player_main.cpp:12937-12940. Sets the hand model indices; nothing here reads them.
void daPy_lk_c::setHandModel(daPy_ANM anmIdx) {
    (void)anmIdx;
}

// SCOPE. Clears the foot dust/splash emitter state.
void daPy_lk_c::resetFootEffect() {
}

// SCOPE, UNREACHED. setBlendMoveAnime reaches it only in the ice-slip arm.
void daPy_lk_c::freeGrabItem() {
    unreached(this);
}



// ---------------------------------------------------------------------------------------------
// The proc-init dispatch: each records which proc checkNextMode chose, the capture's `proc`
// column. TRUE, as a proc init that starts its proc returns.
static BOOL record(daPy_lk_c* lk, int proc) {
    lk->next_init = proc;
    lk->next_init_calls++;
    return TRUE;
}

// ---------------------------------------------------------------------------------------------
// procBackJump / procBackJumpLand's boundary.
// ---------------------------------------------------------------------------------------------

// SCOPE, UNREACHED-BY-ANSWER. d_a_player_fan.inc:390, the Deku Leaf glide. Asked on every
// airborne frame, so counted (`fan_glide_calls`) and answered FALSE. Precondition: no Deku Leaf.
BOOL daPy_lk_c::checkFanGlideProc(int param) {
    (void)param;
    fan_glide_calls++;
    if (mEquipItem == dItemNo_DEKU_LEAF_e) {
        precondition_broken++;
    }
    return FALSE;
}

// SCOPE, UNREACHED. The drop arm into procFall. Every captured flip lands at its launch height,
// so it stays shut only while commonProcInit latches m3688.
BOOL daPy_lk_c::procFall_init(int type, f32 param) {
    (void)param;
    fall_init_calls++;
    return record(this, 0x2300 + type);
}

// SCOPE, UNREACHED. d_com_inf_game.h. Reached only during an event; no capture has one.
void dComIfGp_evmng_cutEnd(int staffIdx) {
    (void)staffIdx;
    if (s_player != 0) {
        s_player->evmng_cut_end_calls++;
        s_player->unreached_called++;
    }
}

// SCOPE, UNREACHED. The landing's rumble, behind checkHeavyStateOn(); the heavy fork's only
// observable.
bool dVibration_c::StartShock(int type, int power, cXyz dir) {
    (void)type;
    (void)power;
    (void)dir;
    if (s_player != 0) {
        s_player->shock_calls++;
    }
    return false;
}

dVibration_c& dComIfGp_getVibration() {
    thread_local dVibration_c s_vibration;
    return s_vibration;
}

// SCOPE, UNREACHED (and MEASURED). The vomit/whirlpool jumps, checked first in checkNextMode;
// the console's frame-59 proc was MOVE.
BOOL daPy_lk_c::procVomitJump_init(int type) { return record(this, 0x2000 + type); }

// SCOPE, UNREACHED. changeSlideProc reaches these only on a slide polygon, and there is none.
BOOL daPy_lk_c::procSlideFront_init(s16 angle) { (void)angle; return record(this, 0x2100); }
BOOL daPy_lk_c::procSlideBack_init(s16 angle) { (void)angle; return record(this, 0x2101); }

// SCOPE, UNREACHED. The checkNext*Mode dispatchers the targeting branch's item arms reach.
BOOL daPy_lk_c::checkNextBoomerangMode() { return record(this, 0x2200); }
BOOL daPy_lk_c::checkNextBowMode() { return record(this, 0x2201); }
BOOL daPy_lk_c::checkNextHookshotMode() { return record(this, 0x2202); }
BOOL daPy_lk_c::checkNextRopeMode() { return record(this, 0x2203); }
BOOL daPy_lk_c::procAtnActorWait_init() { return record(this, 0x08); }
BOOL daPy_lk_c::procAtnActorMove_init() { return record(this, 0x09); }

// READ. d_a_player_vomit.inc:18, checkNextMode's last line, run whenever the chosen init
// returned FALSE. TRUE only on a jump-flower co-hit. Precondition: no such hit;
// `jump_flower_calls` counts the asks.
BOOL daPy_lk_c::checkJumpFlower() {
    jump_flower_calls++;
    return stub_jump_flower;
}

// SCOPE, UNREACHED. "Is a cutscene driving Link". Driven by `stub_event_run`, default FALSE: a
// demo movie played through the pad is not an in-game event. Read by procWait_init (6049),
// procWait (6084, 6136) and procFreeWait (6189). No bump; no player answers FALSE.
BOOL dComIfGp_event_runCheck() { return s_player != 0 ? s_player->stub_event_run : FALSE; }

// ---------------------------------------------------------------------------------------------
// SCOPE, UNREACHED. `&g_dComIfG_gameInfo.play.mBgS`, the collision world. The roll bonk asks it
// only for GetMtrlSndId, the wall's sound material.
thread_local dBgS* s_bgs = 0;

dBgS* dComIfG_Bgsp() {
    return s_bgs;
}

// HARNESS. How a test wires the collision world in.
void set_dComIfG_Bgsp(dBgS* bgs) {
    s_bgs = bgs;
}

// SCOPE, UNREACHED. The wall's sound material id; only the roll bonk asks. The decomp's own
// signature. Answers off the player, since a dBgS has nowhere to keep a test's value.
u32 dBgS::GetMtrlSndId(cBgS_PolyInfo& poly) {
    (void)poly;
    return s_player ? s_player->stub_mtrl_snd_id : 0u;
}

// =============================================================================================
// checkNextActionFromButton's boundary. Most entries are one-line recorders for arms the measured
// path never takes. Several are READ with a precondition: the function cannot return TRUE while
// it holds, for any game state. Each tests its own and bumps `precondition_broken`, which the gate
// requires to be 0.
// =============================================================================================

/// The precondition checker. Call it with the condition the stub's proof rests on.
static BOOL given(const daPy_lk_c* lk, bool condition) {
    if (!condition) {
        const_cast<daPy_lk_c*>(lk)->precondition_broken++;
    }
    return FALSE;
}

// ---------------------------------------------------------------------------------------------
// READ. d_a_player_main.cpp:4020-4073. Every TRUE path needs talkTrigger() or itemTriggerX/Y/Z.
// Precondition: those four bits (BTN_A, X, Y, Z) of mItemTrigger are clear.
int daPy_lk_c::orderTalk() {
    return given(this, (mItemTrigger & (BTN_A | BTN_X | BTN_Y | BTN_Z)) == 0) || stub_order_talk;
}

// Sword-equipping side effect from d_a_player_main.cpp:3838. Other item changes
// remain boundary calls and must not silently become a valid simulated route.
BOOL daPy_lk_c::checkItemChangeFromButton() {
    button_dispatch_fellthrough++;   // counts the runs that fell through the dispatcher
    if (checkModeFlg(ModeFlg_00000004) && !checkEquipAnime() &&
        getGrabActorID() == fpcM_ERROR_PROCESS_ID_e && !checkPlayerGuard() && !stub_curse &&
        swordTrigger() &&
        (dComIfGs_getSelectEquip(0) != dItemNo_NONE_e || checkSwordMiniGame()) &&
        mEquipItem != daPyItem_SWORD_e) {
        setAnimeEquipSword(TRUE);
    } else {
        given(this, (mItemTrigger & (BTN_A | BTN_X | BTN_Y | BTN_Z)) == 0);
    }
    return stub_item_change;
}

// READ. d_a_player_battle.inc:56, the Orca / sword-training battle modes. Precondition:
// mpAttnActorLockOn == NULL, its own first test; nothing in this slice assigns it.
BOOL daPy_lk_c::changeSpecialBattle() {
    return given(this, mpAttnActorLockOn == NULL) || stub_special_battle;
}

// SCOPE, UNREACHED. f_op_actor_mng.h:531, the Y bearing from actor A to B. Only getCutDirection
// calls it, behind `mpAttnActorLockOn == NULL` (see changeSpecialBattle). What is missing is the
// second actor, not the arithmetic.
s16 fopAcM_searchActorAngleY(fopAc_ac_c* p_actorA, fopAc_ac_c* p_actorB) {
    (void)p_actorA;
    (void)p_actorB;
    if (s_player) {
        s_player->unreached_called++;
    }
    return 0;
}

// ---------------------------------------------------------------------------------------------
// MEASURED. The defend sibling of the crouch arm: true with a shield, frame 63 would be proc 12
// (CROUCH_DEFENSE), not 14.
BOOL daPy_lk_c::checkGuardAccept() {
    return stub_guard_accept;
}

// MEASURED. daPy_dmEcallBack_c::checkCurse is the "no sword, no items" curse state. The capture's
// own run swings a sword four frames before the roll, which the curse forbids.
BOOL daPy_dmEcallBack_c::checkCurse() {
    return s_player ? s_player->stub_curse : FALSE;
}

// MEASURED. Slot 1 is the shield. The crouch arm needs no shield or no item equipped, and the
// console took it at frame 63. Driven so a red control can turn proc 14 into proc 12.
int dComIfGs_getSelectEquip(int slot) {
    if (!s_player) {
        return dItemNo_NONE_e;
    }
    if (slot < 0 || slot > 1) {
        s_player->precondition_broken++;    // a slot this port has no driven answer for
        return dItemNo_NONE_e;
    }
    return s_player->stub_select_equip[slot];
}

// MEASURED. The running minigame's id; 2 is the Outset sword school, which makes
// checkNormalSwordEquip true whatever is equipped. The capture is in no minigame.
int dComIfGp_getMiniGameType() {
    return s_player ? s_player->stub_mini_game_type : 0;
}

// SCOPE. Save-data life in quarter-hearts. Low life opens setBlendMoveAnime's WAITB arm; the
// capture has no life column, so it is driven.
int dComIfGs_getLife() {
    return s_player ? s_player->stub_life : 0;
}

// SCOPE. The item in each of the three item-button slots. Only reached from getReadyItem and
// checkItemChangeFromButton, both of which are trigger-gated above.
int dComIfGp_getSelectItem(int btn) {
    (void)btn;
    return s_player ? s_player->stub_select_item : dItemNo_NONE_e;
}

int daPy_lk_c::getReadyItem() {
    return stub_ready_item;
}

// MEASURED. The C-stick-up edge into first person: true at frame 59 would give proc 1, and the
// console read 6. Masks `status` as the decomp does, so the crawl camera bit (0x80) and this one
// (0x1000) answer separately.
BOOL dComIfGp_checkCameraAttentionStatus(int idx, u32 status) {
    (void)idx;
    return (s_player && (s_player->stub_camera_attn & status)) ? TRUE : FALSE;
}

// SCOPE. The player's STATUS0 word (boat riding, among others), masked as the decomp does so
// nextMode's ladder arms get separate answers.
BOOL dComIfGp_checkPlayerStatus0(int idx, u32 status) {
    (void)idx;
    return (s_player && (s_player->stub_player_status0 & status)) ? TRUE : FALSE;
}

// SCOPE. The STATUS1 word, on its own field: nextMode asks a STATUS0 and a STATUS1 bit in one
// `||`.
BOOL dComIfGp_checkPlayerStatus1(int idx, u32 status) {
    (void)idx;
    return (s_player && (s_player->stub_player_status1 & status)) ? TRUE : FALSE;
}

// MEASURED. `!= this` means something else drives Link; the capture is the player's own input.
// Returns daPy_lk_c* where the decomp returns the base daPy_py_c*; the copied expressions read
// the same.
daPy_lk_c* daPy_getPlayerActorClass() {
    return (s_player && s_player->stub_is_player_actor) ? s_player : 0;
}

// ---------------------------------------------------------------------------------------------
// SCOPE. setDoStatus's callees: attention-target overrides and the special-battle prompt. They
// only write the do-status, which nothing reads while `doTrigger()` is 0.
BOOL daPy_lk_c::setHintActor() {
    return stub_hint_actor;
}

BOOL daPy_lk_c::setTalkStatus() {
    return stub_talk_status;
}

void daPy_lk_c::setSpecialBattle(int type) {
    (void)type;
}

// SCOPE. d_a_player_bow.inc:64 and d_a_player_rope.inc:22, files this slice does not extract
// from. Each is two checkUpperAnime calls.
BOOL daPy_lk_c::checkBowAnime() const {
    return stub_bow_anime;
}

BOOL daPy_lk_c::checkRopeAnime() const {
    return stub_rope_anime;
}

// Movement reads the upper animation when equipping a sword or changing actions.
BOOL daPy_lk_c::setActAnimeUpper(u16 index, daPy_UPPER slot, f32 rate, f32 start, s16 end, f32 morf) {
    J3DAnmTransform* bck = getAnimeResource(&m_anm_heap_upper[slot], index, 0x2400);
    mAnmRatioUpper[slot].setAnmTransform(bck);
    mAnmRatioUpper[slot].setRatio(1.0f);
    if (end < 0) end = bck->getFrameMax();
    const f32 frame = rate < 0.0f ? end - 0.001f : start;
    setFrameCtrl(&mFrameCtrlUpper[slot], bck->getAttribute(), start, end, rate, frame);
    bck->setFrame(frame);
    if (morf >= 0.0f) m_old_fdata->initOldFrameMorf(morf, CL_JNT_BODY_CHN_e, CL_JNT_WAIST_CHN_e);
    return TRUE;
}

void daPy_lk_c::setAnimeEquipSword(BOOL immediate) {
    m3562 = daPyItem_SWORD_e;
    const auto& cut = m_HIO->mCut.m;
    setActAnimeUpper(dRes_INDEX_LKANM_BCK_REST_e, UPPER_MOVE2_e,
                    cut.field_0x8, cut.field_0xC, cut.field_0x0, cut.field_0x10);
    stub_player_status0 &= ~daPyStts0_BOOMERANG_WAIT_e;
    if (immediate) offNoResetFlg1(daPyFlg1_UNK4000000);
    else onNoResetFlg1(daPyFlg1_UNK4000000);
}

BOOL daPy_lk_c::resetActAnimeUpper(daPy_UPPER slot, f32 i_morf) {
    mAnmRatioUpper[slot].setAnmTransform(NULL);
    mAnmRatioUpper[slot].setRatio(0.0f);
    m_anm_heap_upper[slot].mIdx = (u16)-1;
    mFrameCtrlUpper[slot].init(0);
    if (i_morf >= 0.0f) {
        m_old_fdata->initOldFrameMorf(i_morf, CL_JNT_BODY_CHN_e, CL_JNT_WAIST_CHN_e);
    }
    return TRUE;
}

void daPy_lk_c::deleteEquipItem(BOOL param_1) {
    (void)param_1;
}

// SCOPE. Range tests over the item enum, which the port does not carry. Precondition: the item
// is daPyItem_NONE_e, in neither class.
BOOL daPy_lk_c::checkBowItem(int item) const {
    return given(this, item == daPyItem_NONE_e);
}

BOOL daPy_lk_c::checkPhotoBoxItem(int item) const {
    return given(this, item == daPyItem_NONE_e);
}

// READ. d_a_player_main.cpp:4402, the bow or boomerang aimed mid-air; both arms need one of them
// equipped. Stubbed because a copy would ask checkBowItem with the sword equipped. Precondition:
// nothing or the sword in hand.
void daPy_lk_c::checkNextActionItemFly() {
    given(this, mEquipItem == daPyItem_NONE_e || mEquipItem == daPyItem_SWORD_e);
}

// SCOPE. The actor's packed parameter word, and the event orders (a door, a chest, a hint)
// below, all behind `doTrigger()`, which is 0.
u32 fopAcM_GetParam(fopAc_ac_c* actor) {
    (void)actor;
    return 0;
}

// MEASURED. A definition: fpcM_GetName is a read of mProcName, which reset_boundary seeds to
// fpcNm_PLAYER_e. An unseeded actor reads 0, "not the player".
u32 fopAcM_GetName(fopAc_ac_c* actor) {
    return (u32)(u16)actor->mProcName;
}

BOOL fopAcM_CheckStatus(fopAc_ac_c* actor, u32 status) {
    (void)actor;
    (void)status;
    return FALSE;
}

int dComIfGp_att_getZHint() {
    return 0;
}

void fopAcM_orderZHintEvent(daPy_lk_c* lk, int hint) {
    (void)hint;
    unreached(lk);
}

void fopAcM_orderDoorEvent(daPy_lk_c* lk, fopAc_ac_c* actor) {
    (void)actor;
    unreached(lk);
}

void fopAcM_orderTreasureEvent(daPy_lk_c* lk, fopAc_ac_c* actor) {
    (void)actor;
    unreached(lk);
}

// ---------------------------------------------------------------------------------------------
// READ. d_com_inf_game.h:508-509. The R-status and do-status words live on g_dComIfG_gameInfo;
// the player clears both once per frame (d_a_player_main.cpp:11283-11284). Routed to the
// player's own copy so a test can read them.
u8 dComIfGp_getRStatus() {
    return s_player ? (u8)s_player->r_status : (u8)dActStts_BLANK_e;
}

void dComIfGp_setRStatus(u8 status) {
    if (s_player) {
        s_player->r_status = status;
    }
}

u8 dComIfGp_getDoStatus() {
    return s_player ? (u8)s_player->do_status : (u8)dActStts_BLANK_e;
}

// READ. d_com_inf_game.h:506-507, the third word of the group. setDoStatusCrawl's camera arm
// posts dActStts_RETURN_e here, its one observable.
u8 dComIfGp_getAStatus() {
    return s_player ? (u8)s_player->a_status : (u8)dActStts_BLANK_e;
}

void dComIfGp_setAStatus(u8 status) {
    if (s_player) {
        s_player->a_status = status;
    }
}

void dComIfGp_setDoStatus(u8 status) {
    if (s_player) {
        s_player->do_status = status;
    }
}

// ---------------------------------------------------------------------------------------------
// SCOPE, UNREACHED. The exits of checkNextActionFromButton the port does not follow. Each
// records which fired; the 0x24xx codes name exits that are not a plain proc (an item
// dispatcher, a cut, a swing). The gate requires `unreached_called` to be 0.
// The first four are the cut chain's 5th/6th-press extensions (m34C4 >= 5).
BOOL daPy_lk_c::procCutExA_init() { return record(this, 0x2410); }
BOOL daPy_lk_c::procCutExB_init() { return record(this, 0x2411); }
BOOL daPy_lk_c::procCutExMJ_init(int param) { (void)param; return record(this, 0x2412); }
BOOL daPy_lk_c::procCutKesa_init() { return record(this, 0x2413); }
BOOL daPy_lk_c::procScope_init(int item) { (void)item; return record(this, 0x00); }
BOOL daPy_lk_c::procFanSwing_init() { return record(this, 0x2401); }
BOOL daPy_lk_c::procTactWait_init(int param) { (void)param; return record(this, 0x2402); }
BOOL daPy_lk_c::checkNextActionGrab() {
    // The external object solver owns the actor/Co step. Keep the player's
    // ordinary B/DROP exit real: skipping it changes the lower blend and camera.
    if (stub_carried_movement_only && stub_carried_release_model &&
        (mItemTrigger & BTN_B) && !(mItemTrigger & ~(BTN_B | BTN_L)) &&
        checkGrabAnimeLight()) {
        resetActAnimeUpper(UPPER_MOVE2_e, m_HIO->mBasic.m.mAnmMorf);
        field_0x2b0 = 0.0f;
        offNoResetFlg0(static_cast<daPy_FLG0>(0x400));
        stub_player_status1 &= ~0x40000;
        setAnimeEquipSword(FALSE);
        port_carried_released = TRUE;
        return TRUE;
    }
    // Throws and other item edges remain explicit unsupported transitions.
    if (stub_carried_movement_only && !(mItemTrigger & ~BTN_L)) return FALSE;
    return record(this, 0x2403);
}
BOOL daPy_lk_c::checkNextActionHookshotReady() { return record(this, 0x2404); }
BOOL daPy_lk_c::checkNextActionBowReady() { return record(this, 0x2405); }
BOOL daPy_lk_c::checkNextActionBoomerangReady() { return record(this, 0x2406); }
BOOL daPy_lk_c::checkNextActionRopeReady() { return record(this, 0x2407); }
BOOL daPy_lk_c::procPushPullWait_init(int param) { (void)param; return record(this, 0x32); }
BOOL daPy_lk_c::procShipReady_init() { return record(this, 0x2408); }
BOOL daPy_lk_c::procHangWallCatch_init() { return record(this, 0x31); }
BOOL daPy_lk_c::procVerticalJump_init() { return record(this, 0x2A); }
BOOL daPy_lk_c::procGrabReady_init() { return record(this, 0x2409); }

BOOL daPy_lk_c::procWHideReady_init(cM3dGPla* pla, cXyz* pos) {
    (void)pla;
    (void)pos;
    return record(this, 0x13);
}

BOOL daPy_lk_c::procWeaponNormalSwing_init() { return record(this, 0x240D); }
BOOL daPy_lk_c::procWeaponSideSwing_init() { return record(this, 0x240E); }
BOOL daPy_lk_c::procWeaponFrontSwingReady_init() { return record(this, 0x240F); }
BOOL daPy_lk_c::procWeaponThrow_init() { return record(this, 0x2410); }
BOOL daPy_lk_c::procBottleSwing_init(int param) { (void)param; return record(this, 0x2411); }
BOOL daPy_lk_c::procHammerSideSwing_init() { return record(this, 0x2412); }
BOOL daPy_lk_c::procHammerFrontSwingReady_init() { return record(this, 0x2413); }
BOOL daPy_lk_c::procCall_init() { return record(this, 0x02); }
BOOL daPy_lk_c::procCrouchDefense_init() { return record(this, 0x0C); }

BOOL daPy_lk_c::procSubjectivity_init(BOOL param) { (void)param; return record(this, 0x01); }
BOOL daPy_lk_c::procGrabWait_init() { return record(this, 0x2414); }
BOOL daPy_lk_c::procBoomerangCatch_init() { return record(this, 0x2415); }
BOOL daPy_lk_c::procControllWait_init() { return record(this, 0x03); }

// ---------------------------------------------------------------------------------------------
// procCutA's boundary, the slash. Only changeCutReverseProc can affect its output
// (mNormalSpeed, shape_angle.y, current.angle.y), so it alone is driven.
// ---------------------------------------------------------------------------------------------

// PARTIAL. d_a_player_main.cpp:583. The real body loads the sword model's animation from the
// archive. procCutA_init only hands it to mSwordAnim.changeBckOnly, which nothing reads back, so
// it returns NULL and records the index, which shows checkNormalSwordEquip's fork.
J3DAnmTransform* daPy_lk_c::getItemAnimeResource(u16 index) {
    boundary_reached("daPy_lk_c::getItemAnimeResource", "PARTIAL");
    sword_anim_idx = (int)index;
    return NULL;
}

// STUB. m_Do_ext.cpp. Swaps the sword's animation; nothing in this slice reads it.
void mDoExt_bckAnm::changeBckOnly(J3DAnmTransform* i_bck) {
    boundary_reached("mDoExt_bckAnm::changeBckOnly", "STUB");
    (void)i_bck;
}

// STUB. d_a_player_main.cpp:578. The sword trail's position buffer, rendering only. The index is
// recorded.
void daPy_lk_c::setBlurPosResource(u16 index) {
    boundary_reached("daPy_lk_c::setBlurPosResource", "STUB");
    blur_pos_idx = (int)index;
}

// STUB. d_a_player_sword.inc:298. The attack collision's parameters (m35FC, setAtParam); this
// port has no attack collision and trims daPy_HIO_cut_c0::m. Records the cut type.
void daPy_lk_c::setNormalCutAtParam(u8 cutType) {
    boundary_reached("daPy_lk_c::setNormalCutAtParam", "STUB");
    cut_at_param_type = (int)cutType;
}

// STUB. d_a_player_sword.inc:314, the combo enders' version of setNormalCutAtParam. Shares
// `cut_at_param_type`: the two are exclusive, and CUT_TYPE_CUT_EA/EB are only passed here.
void daPy_lk_c::setFinishCutAtParam(u8 cutType) {
    boundary_reached("daPy_lk_c::setFinishCutAtParam", "STUB");
    cut_at_param_type = (int)cutType;
}

// STUB. d_a_player_main.cpp:164, audio at the sword tip. Fires inside the attack window (5.0 to
// 11.0 on the slash), so the recorded id shows the window was entered.
void daPy_lk_c::seStartSwordCut(u32 se) {
    boundary_reached("daPy_lk_c::seStartSwordCut", "STUB");
    sword_cut_se = (int)se;
}

// STUB, DRIVEN. d_a_player_sword.inc:469, the sword bounce off a shield or wall into
// CUT_REVERSE. The one entry that can end procCutA early, so `stub_cut_reverse` drives it. The
// real body needs the attack collision and a line check. FALSE is measured: the capture never
// reads CUT_REVERSE (0x5A). Counted, because procJumpCut asks on every airborne frame.
int daPy_lk_c::changeCutReverseProc(daPy_ANM anm) {
    boundary_reached("daPy_lk_c::changeCutReverseProc", "STUB");
    (void)anm;
    cut_reverse_calls++;
    return stub_cut_reverse;
}

// ---------------------------------------------------------------------------------------------
// procJumpCut / procJumpCutLand's boundary.
// ---------------------------------------------------------------------------------------------

// PARTIAL. Keeps the decomp's `mCutCount = 0`; the attack collision and its radius lookup
// (daPy_HIO_cut_c0::m, not carried) are cut, and m35FC has no reader. Records the cut type,
// which only this function passes as CUT_TYPE_JUMPCUT_*.
void daPy_lk_c::setJumpCutAtParam() {
    boundary_reached("daPy_lk_c::setJumpCutAtParam", "PARTIAL");
    mCutCount = 0;
    if (mEquipItem == daPyItem_SWORD_e) {
        cut_at_param_type = CUT_TYPE_JUMPCUT_SWORD;
    } else if (mEquipItem == dItemNo_SKULL_HAMMER_e) {
        cut_at_param_type = CUT_TYPE_JUMPCUT_HAMMER;
    } else if (mActorKeepEquip.getActor()) {
        // setEnemyWeaponAtParam(TRUE), the one arm with no cut type to record.
        unreached(this);
    } else {
        cut_at_param_type = CUT_TYPE_JUMPCUT_MACHETE;
    }
}

// STUB, UNREACHED-BY-ANSWER. d_a_player_main.cpp:4982. Link's health, kept in the save file,
// which the port does not model. procJumpCutLand_init's two fall-damage arms call it; every
// captured jump slash lands at its launch height, so neither fires. Counted, with the amount
// (-2.0 or -1.0) naming which arm. TRUE is the real answer when damage is taken.
BOOL daPy_lk_c::setDamagePoint(f32 amount) {
    boundary_reached("daPy_lk_c::setDamagePoint", "STUB");
    damage_calls++;
    damage_amount = amount;
    return TRUE;
}

// STUB, UNREACHED. d_a_player_hammer.inc:34, the Skull Hammer quake. Every capture equips the
// sword. Counted so the equip fork has an observable on both sides.
void daPy_lk_c::setHammerQuake(cBgS_PolyInfo* poly, const cXyz* pos, int param) {
    boundary_reached("daPy_lk_c::setHammerQuake", "STUB");
    (void)poly;
    (void)pos;
    (void)param;
    hammer_quake_calls++;
    unreached(this);
}

// STUB. d_a_player_main.h:319, the sword trail (rendering). Its arguments come from copied
// bodies, so they are recorded; the matrix is counted only.
void daPy_swBlur_c::initSwBlur(MtxP mtx, int frames, f32 top_rate, int color) {
    boundary_reached("daPy_swBlur_c::initSwBlur", "STUB");
    (void)mtx;
    if (s_player != 0) {
        s_player->sw_blur_calls++;
        s_player->sw_blur_frames = frames;
        s_player->sw_blur_top_rate = top_rate;
        s_player->sw_blur_color = color;
    }
}

// READ. J3DModel.h:113, `return mBaseTransformMtx;`, which the ported setWorldMatrix fills.
// Kept here for the count the crawl gate reads.
Mtx& J3DModel::getBaseTRMtx() {
    if (s_player != 0) {
        s_player->base_tr_mtx_calls++;
    }
    return mBaseTransformMtx;
}

// SCOPE. d_com_inf_game.h:2872, the King of Red Lions. Answers NULL: the port's world has no
// ship, so setWorldMatrix's ship arm cannot be taken whatever the status bit says.
// `ship_actor_calls` keeps the ask visible.
daShip_c* dComIfGp_getShipActor() {
    if (s_player != 0) {
        s_player->ship_actor_calls++;
    }
    return 0;
}

// SCOPE, UNREACHED. jointBeforeCB's ship-tiller arm; it needs a ship actor, and
// dComIfGp_getShipActor answers NULL.
fpc_ProcID fopAcM_GetID(daShip_c* ship) {
    (void)ship;
    unreached(s_player);
    return (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
}

BOOL fpcM_IsCreating(fpc_ProcID id) {
    (void)id;
    unreached(s_player);
    return FALSE;
}

BOOL daPy_lk_c::checkShipNotNormalMode() {
    unreached(this);
    return FALSE;
}

void daPy_lk_c::setShipRideArmAngle(int jnt_no, J3DTransformInfo* param_2) {
    (void)jnt_no;
    (void)param_2;
    unreached(this);
}

// SCOPE, UNREACHED. d_a_boko.h:74-75. Tables in the boko actor's REL, not the DOL. getBlurTopRate
// reaches them only with daPyItem_BOKO_e equipped; every capture equips the sword.
f32 daBoko_c::getJumpBlurRate() {
    unreached(s_player);
    return 0.0f;
}

f32 daBoko_c::getBlurRate() {
    unreached(s_player);
    return 0.0f;
}

// SCOPE. d_com_inf_game.h:2846. Raises a bit other actors read (e.g. SWORD_SWING). Nothing here
// reads it back; it accumulates so the gate can assert the bit arrived.
void dComIfGp_setPlayerStatus0(int idx, u32 status) {
    if (idx != 0) {
        if (s_player) {
            s_player->precondition_broken++;    // this port models player 0 only
        }
        return;
    }
    if (s_player) {
        s_player->player_status0 |= status;
    }
}

// SCOPE. The clearing half of the above: setDoStatusCrawl clears daPyStts0_SUBJECT_e.
// In the game the CRAWL bit raises camera attention 0x80 (d_camera.cpp:4264), which
// setDoStatusCrawl tests a frame later; the port drives that through `stub_camera_attn`.
void dComIfGp_clearPlayerStatus0(int idx, u32 status) {
    if (idx != 0) {
        if (s_player) {
            s_player->precondition_broken++;
        }
        return;
    }
    if (s_player) {
        s_player->player_status0 &= ~status;
    }
}

// ---------------------------------------------------------------------------------------------
// The crawl's boundary.
//
// READ. d_a_player_main.cpp:2690, the camera body angle: a 31-function, 1,445-instruction closure.
// Its whole output is mBodyAngle, whose readers (d_a_player_main.cpp:290, :2656, :10235 and the
// hook, rope and boomerang procs) are all outside this slice. Counted: it is reached on every
// crawl frame.
void daPy_lk_c::setBodyAngleToCamera() {
    body_angle_calls++;
}

// SCOPE. d_a_player_main.h:1980, "has first-person been left". Only picks whether
// daPyStts0_SUBJECT_e is raised or cleared, a bit with no reader here. FALSE with
// `stub_camera_attn`.
BOOL daPy_lk_c::checkSubjectEnd(BOOL param_1) {
    (void)param_1;
    subject_end_calls++;
    return FALSE;
}

// SCOPE, UNREACHED. The entry to first person; setDoStatusCrawl reaches it only on the C-stick-up
// edge, FALSE on every captured frame.
void daPy_lk_c::setSubjectMode() {
    subject_mode_calls++;
    unreached(this);
}

// STUB. d_a_player_crawl.inc:316. No captured frame is in proc 0x10, though both terms of the arm
// that names it are exercised: the stick clears 0.05 on 9 rows and the clock term holds on 28.
// The gate holds the count at 0.
BOOL daPy_lk_c::procCrawlMove_init(s16 param_1, s16 param_2) {
    boundary_reached("daPy_lk_c::procCrawlMove_init", "STUB");
    (void)param_1;
    (void)param_2;
    crawl_move_init_calls++;
    return record(this, daPyProc_CRAWL_MOVE_e);
}



// PARTIAL. The real J3DAnmKeyLoader_v15 parses an ANK1 chunk from the archive; this takes the
// baked track (port/gen_anm_track.py) for all 42 joints. Missing: the ANK1 header and the texture
// and colour animations. As a friend it sets the base's data pointers, so the copied classes stay
// copies. `mAnmTable` is cast from const because the decomp field is non-const and only read.
void J3DAnmKeyLoader_v15::load(J3DAnmTransformKey* dst, const daPy_portAnmTrack* track) {
    boundary_reached("J3DAnmKeyLoader_v15::load", "PARTIAL");
    if (track == NULL) {
        dst->mDecShift = 0;
        dst->mAnmTable = NULL;
        dst->mScaleData = NULL;
        dst->mRotData = NULL;
        dst->mTransData = NULL;
        return;
    }
    dst->mDecShift = track->mDecShift;
    dst->mAnmTable = const_cast<J3DAnmTransformKeyTable*>(track->mAnmTable);
    dst->mScaleData = const_cast<f32*>(track->mScaleData);
    dst->mRotData = const_cast<s16*>(track->mRotData);
    dst->mTransData = const_cast<f32*>(track->mTransData);
}

// HARNESS. The suite's accessors for the installed tracks.
size_t daPy_portAnmTrackTableSize() {
    return tww_engine::linkAnimationCount();
}

const daPy_portAnmTrack* daPy_portAnmTrackTableAt(size_t i) {
    return tww_engine::linkAnimationTrackAt(i);
}

void daPy_portAnm_c::load(s16 frameMax, u8 attribute, const daPy_portAnmTrack* track) {
    mFrameMax = frameMax;
    mAttribute = attribute;
    mFrame = 0.0f;
    mTrack = track;
    mKey.setFrame(0.0f);
    J3DAnmKeyLoader_v15::load(&mKey, track);
}

// PARTIAL. Real for every baked animation; every upper animation has no track and answers zeros,
// counted in anm_track_missing. A joint past the .bck's mJointNum is counted as an overrun.
// The frame is synced at the call because calcTransform samples getFrame() of this object.
// `anm_transform_calls` and `anm_track_nonroot` are read by tests/test_crawl*.cpp.
void daPy_portAnm_c::getTransform(u16 joint, J3DTransformInfo* out) const {
    boundary_reached("daPy_portAnm_c::getTransform", "PARTIAL");
    if (s_player) {
        s_player->anm_transform_calls++;
        if (joint != 0) {
            s_player->anm_track_nonroot++;
        }
    }
    if (out == NULL) {
        return;
    }
    if (mTrack == NULL || joint >= static_cast<u16>(mTrack->mJointNum)) {
        if (s_player) {
            if (mTrack != NULL) {
                s_player->anm_track_overrun++;
            } else {
                s_player->anm_track_missing++;
                s_player->anm_track_missing_idx = mFrameMax;
            }
        }
        out->mScale.x = out->mScale.y = out->mScale.z = 0.0f;
        out->mRotation.x = out->mRotation.y = out->mRotation.z = 0;
        out->mTranslate.x = out->mTranslate.y = out->mTranslate.z = 0.0f;
        return;
    }
    mKey.setFrame(mFrame);
    mKey.getTransform(joint, out);
}

// d_a_player_main_data.inc:28-35, the crawl-probe offsets.
const Vec l_crawl_front_offset = {0.0f, 10.0f, 80.0f};
const Vec l_crawl_top_up_offset = {0.0f, 50.0f, 0.0f};

// ---------------------------------------------------------------------------------------------
// procCutTurn's boundary, the spin attack.
//
// procCutTurn writes no speed or angle; its output is the anim clock, the exit and m35A4, the
// attack cylinder's target radius. These stubs record their arguments so the gate can see which
// arm of each init fork ran.
// ---------------------------------------------------------------------------------------------

// SCOPE. d_a_player.h:18-19. Particle emitters that follow a joint; the port has no particle
// system. Records the id and which emitter asked, told apart by address: m32E4 is the toe plume,
// m32F0 the ground one.
static void record_emitter(daPy_mtxFollowEcallBack_c* self, u16 id, MtxP mtx) {
    if (!s_player) {
        return;
    }
    // The joint was recorded by J3DModel::getAnmMtx; the pointer is NULL.
    (void)mtx;
    if (self == &s_player->m32E4) {
        s_player->particle_toe_id = (int)id;
        s_player->particle_toe_joint = s_player->last_anm_mtx_joint;
    } else if (self == &s_player->m32F0) {
        s_player->particle_ground_id = (int)id;
        s_player->particle_ground_joint = s_player->last_anm_mtx_joint;
    } else {
        s_player->precondition_broken++;    // an emitter this port does not own
    }
}

JPABaseEmitter* daPy_mtxFollowEcallBack_c::makeEmitter(u16 id, MtxP mtx, const cXyz* pos,
                                                       const cXyz* scale) {
    (void)pos; (void)scale;
    record_emitter(this, id, mtx);
    return NULL;
}

JPABaseEmitter* daPy_mtxFollowEcallBack_c::makeEmitterColor(u16 id, MtxP mtx, const cXyz* pos,
                                                            const GXColor* c0, const GXColor* k0) {
    (void)pos; (void)c0; (void)k0;
    record_emitter(this, id, mtx);
    return NULL;
}

// SCOPE. Stops the emitter. procCutTurn calls it on two clocks (frame 17.0 and m35A0), so the
// count reads the ground fork back out of the body.
void daPy_mtxFollowEcallBack_c::end() {
    if (s_player) {
        s_player->particle_ends++;
    }
}

// SCOPE. d_particle.h:72. Ends the smoke trail on the same test as end() above; counted
// separately so the gate can tell one line from neither.
void dPa_smokeEcallBack::remove() {
    if (s_player) {
        s_player->smoke_removes++;
    }
}

// SCOPE. J3DModel.h:75, `return mpNodeMtx[idx];`. Records the joint asked for. The player's model
// has no node matrices, so it answers NULL; both callers pass the result to stubs that ignore it.
MtxP J3DModel::getAnmMtx(int idx) {
    if (s_player) {
        s_player->last_anm_mtx_joint = idx;
    }
    // A model with node matrices gets the decomp's own read.
    if (mpNodeMtx) {
        return mpNodeMtx[idx];
    }
    return NULL;
}

// SCOPE, UNREACHED. d_kankyo_rain.cpp, the sea colours. Only procCutTurn_init's WATER arm calls
// it; the gate checks the SMOKE arm ran through `particle_ground_id`.
void dKy_get_seacolor(GXColor* amb, GXColor* dif) {
    unreached(s_player);
    if (amb) {
        amb->r = amb->g = amb->b = amb->a = 0;
    }
    if (dif) {
        dif->r = dif->g = dif->b = dif->a = 0;
    }
}

// SCOPE. d_com_inf_game.h. A toon-shaded particle; procCutTurn_init's default ground arm, the one
// the capture takes. Records the id.
void dComIfGp_particle_setToonP1(u16 id, const cXyz* pos, const csXyz* angle, const cXyz* scale,
                                 u8 alpha, dPa_smokeEcallBack* callback, s8 which, const void* a,
                                 const void* b, const void* c) {
    (void)pos; (void)angle; (void)scale; (void)alpha; (void)which; (void)a; (void)b; (void)c;
    if (!s_player) {
        return;
    }
    if (callback != &s_player->mSmokeEcallBack) {
        s_player->precondition_broken++;    // a callback this port does not own
    }
    s_player->particle_ground_id = (int)id;
}

// SCOPE, UNREACHED. d_a_boko.h:72, attack power per weapon type, from a table in the boko REL.
// Reached only with something other than the sword equipped.
s32 daBoko_c::getAtPoint() {
    unreached(s_player);
    return 0;
}

// ---------------------------------------------------------------------------------------------
// procCutTurnMove's boundary, the spin's steered hold.
//
// procCutTurnMove_init's save-data chain (Hurricane Spin learned, 2+ magic) picks a 47-frame
// countdown or -1; both captured runs are shorter, so both answers give the same rows. All three
// inputs are driven and the gate runs the chain both ways.
// ---------------------------------------------------------------------------------------------

// SCOPE, and DRIVEN. d_com_inf_game.h:1356, :1368. One save-file event bit each; both name the
// Hurricane Spin. The id is checked so a second bit cannot take this one's answer.
BOOL dComIfGs_isEventBit(u16 id) {
    if (!s_player) {
        return FALSE;
    }
    if (id != dSv_event_flag_c::UNK_0B20) {
        s_player->precondition_broken++;    // a flag this driver does not stand for
    }
    return s_player->stub_event_bit;
}

BOOL dComIfGs_isTmpBit(u16 id) {
    if (!s_player) {
        return FALSE;
    }
    if (id != dSv_event_tmp_flag_c::UNK_0402) {
        s_player->precondition_broken++;
    }
    return s_player->stub_tmp_bit;
}

// SCOPE, and DRIVEN. d_com_inf_game.h:2077, the magic meter. The init wants >= 2.
u8 dComIfGs_getMagic() {
    return s_player ? s_player->stub_magic : 0;
}

// SCOPE. A looping system cue, called on every frame of the charge countdown, so
// `system_se_calls` counts the frames that took the hurricane arm.
void daPy_lk_c::seStartSystem(u32 se) {
    system_se = (int)se;
    system_se_calls++;
}

// READ. d_a_player_main.cpp:12692. Writes only mJAIZelAnime and m_sanm_buffer, which nothing
// ported reads. Counted: it runs last in procCutTurnMove's B-held arm, so a count shows that arm
// ran through.
void daPy_lk_c::initSeAnime() {
    se_anime_inits++;
}

// SCOPE. d_com_inf_game.h:2848. procCutTurnMove raises daPyStts1_UNK20000_e when its 47-frame
// countdown ends; the longest captured run is 12, so the gate holds this word at 0.
void dComIfGp_setPlayerStatus1(int idx, u32 status) {
    if (idx != 0) {
        if (s_player) {
            s_player->precondition_broken++;    // this port models player 0 only
        }
        return;
    }
    if (s_player) {
        s_player->player_status1 |= status;
    }
}

// SCOPE, UNREACHED. d_a_player_sword.inc:1512, the dizzy roll after a full hurricane spin, 47
// frames in. Records the real proc id.
BOOL daPy_lk_c::procCutRoll_init() {
    unreached(this);
    return record(this, daPyProc_CUT_ROLL_e);
}

// ---------------------------------------------------------------------------------------------
// procWait's boundary: what procWait_init and procCrouch_init call.

// SCOPE, UNREACHED. d_a_player_main.cpp:7597, the tip-over on ice. procWait's guard on m36A0 and
// m36AC is copied, and both vectors are zero on the capture's floor.
BOOL daPy_lk_c::procIceSlipAlmostFall_init() { return record(this, 0x2500); }

// SCOPE. d_a_player_main.cpp:849, the face texture swap. procWait_init calls it only on the
// DEMO_KM_WAIT arm, which the gate's demo sweep drives.
void daPy_lk_c::changeTextureAnime(u16 btp, u16 btk, int r5) {
    (void)btp; (void)btk; (void)r5;
    texture_anime_calls++;
}

// SCOPE. d_a_player_main.h:292, the face's eye-move flag. Read only by procWait's idle-countdown
// guard, whose other terms already fail on the measured path. Driven.
u8 daPy_matAnm_c::getEyeMoveFlg() { return s_player->stub_eye_move_flg; }

// ---------------------------------------------------------------------------------------------
// procCrouch's boundary. Its crawl arm needs mStickDistance > 0.05f, and the stick is 0.0 on
// every compared frame; the crawl stubs bump `unreached_called`.

// SCOPE. d_camera.cpp:384: a cutscene-camera test and a lookup in the camera's mode table. It
// gates `onResetFlg0(daPyRFlg0_SUBJECT_ACCEPT)`, read only by the HUD (d_meter.cpp:7685), and
// procSubjectivity_init(1), behind the C-stick-up edge. The gate replays it forced both ways.
bool dCamera_c::ChangeModeOK(s32 param_1) {
    (void)param_1;
    return s_player ? (bool)s_player->stub_change_mode_ok : false;
}

dCamera_c* dCam_getBody() {
    thread_local dCamera_c s_camera;
    return &s_camera;
}

// d_a_player_main_data.inc:18-19, the foot offsets.
const Vec l_heel_pos = {-6.0f, 3.25f, 0.0f};
const Vec l_toe_pos = {6.0f, 3.25f, 0.0f};

// d_a_player_main_data.inc:13. Read only by setAttentionPos's IN_SHIP arm, dead with no ship.
const Vec l_ship_offset = {0.0f, 15.0f, -35.0f};

// READ. d_a_player_main.cpp:11053 and :11080, posMoveFromFootPos's last two calls. They write
// only m36B8, m3730 and m373C; left zero, posMove adds no conveyor or wind term, and the jump
// pairs' 134 captured rows agree. Counted.
void daPy_lk_c::setBeltConveyerPower() {
    belt_conveyer_calls++;
}

void daPy_lk_c::setWindAtPower() {
    wind_at_power_calls++;
}

// SCOPE, UNREACHED. d_a_player_swim.inc:280. Called only from posMoveFromFootPos's SWIM_MOVE arm;
// no swim proc is in the block catalog.
f32 daPy_lk_c::getSwimTimerRate() {
    unreached(this);
    return 0.0f;
}

// d_a_player_main_data.inc:28 and :31, the crawl-start probe offsets.
const Vec l_crawl_start_front_offset = {0.0f, 10.0f, 112.0f};
const Vec l_crawl_top_offset = {0.0f, 10.0f, 0.0f};

// SCOPE, and deliberately not a port. c_math.cpp:177-186. The seeds are game-wide state no
// capture records, so a port would only look answered. Draws are counted in `rnd_draws`, which
// the gate requires to be 0 on compared frames.
float cM_rnd(void) {
    s_player->rnd_draws++;
    return s_player->stub_rnd;
}

float cM_rndF(float f) { return cM_rnd() * f; }

void cM_initRnd(int p0, int p1, int p2) { (void)p0; (void)p1; (void)p2; }

// HARNESS. How a test names the player the free accessors route to.
void set_dComIfG_player(daPy_lk_c* lk) {
    s_player = lk;
}

// MEASURED. d_com_inf_game.h:2328, the game-info player table. The port has one player, so every
// index answers it; dCamera_c's constructor asks for 0. Unlike daPy_getPlayerActorClass this does
// not test stub_is_player_actor.
fopAc_ac_c* dComIfGp_getPlayer(int idx) {
    (void)idx;
    return s_player;
}

// =============================================================================================
// dBgS_Acch::CrrPos's boundary, d_bg_s_acch.cpp:209-329.
//
// Its water and sea stages are copied, so their four calls exist. Neither stage writes pm_pos,
// so these cannot move Link; they answer "no water, no sea".
// =============================================================================================

#include "boundary/game_boundary.h"

#include "d/d_bg_s.h"
#include "d/d_bg_s_spl_grp_chk.h"

/// READ. f_op_actor_mng.h, `fpcM_GetID(actor)`, fed to SetActorPid. Callers pass NULL
/// (engine/room.h builds the acch without an actor); fpcM_ERROR_PROCESS_ID_e is the no-actor id.
fpc_ProcID fopAcM_GetID(fopAc_ac_c* actor) {
    (void)actor;
    return (fpc_ProcID)fpcM_ERROR_PROCESS_ID_e;
}


/// READ. d_com_inf_game.h. This engine has no room-control table. NULL takes CrrPos's `if (bgw)`
/// skip (d_bg_s_acch.cpp:282), so the water state stays clear: wrong for a room with water.
dBgW* dComIfGp_roomControl_getBgW(int room_no) {
    (void)room_no;
    return NULL;
}

/// READ. Both sit behind `ChkSeaCheckOn()` (d_bg_s_acch.cpp:305), which no player path sets.
/// The camera's checkGroundInfo calls daSea_ChkArea unconditionally: `false` is right while no
/// ocean actor is loaded, wrong on the sea. Not in the camera census.
bool daSea_ChkArea(f32 x, f32 z) {
    (void)x;
    (void)z;
    return false;
}

f32 daSea_calcWave(f32 x, f32 z) {
    (void)x;
    (void)z;
    return 0.0f;
}

/// SCOPE, UNREACHED. d_bg_w.cpp, the water query's octree descent, named by dBgS::SplGrpChk's
/// copied body. CrrPos's water stage returns at the NULL bgW first.
bool dBgW::SplGrpChkGrpRp(dBgS_SplGrpChk* chk, int grp_id, int depth) {
    (void)chk;
    (void)grp_id;
    (void)depth;
    return false;
}

// ---- posMove's three boundary crossings ------------------------------------------------------

// MEASURED, and counted rather than stubbed. The actor-vs-actor collision push; this port
// registers no second collider, so it is zero. The jump pairs' 134 rows agree, and the crawl's
// wall push comes from dBgS_Acch, which is ported.
cXyz* dCcD_Stts::GetCCMoveP() {
    if (s_player) {
        s_player->cc_move_asks++;
    }
    return &m_cc_move;
}

// SCOPE, UNREACHED. posMove's whirlpool arm. mWhirlId is set only by daWhirlpool, so it is
// fpcM_ERROR_PROCESS_ID_e and the else (`m3610 = 0.0f`) runs.
fopAc_ac_c* fopAcM_SearchByID(fpc_ProcID id) {
    (void)id;
    if (s_player) {
        s_player->unreached_called++;
    }
    return NULL;
}

// SCOPE, UNREACHED. The whirlpool drowning restart, two guards deep in the arm above.
void daPy_lk_c::startRestartRoom(int param_1, int param_2, f32 param_3, int param_4) {
    (void)param_1;
    (void)param_2;
    (void)param_3;
    (void)param_4;
    unreached(this);
}


// ---------------------------------------------------------------------------------------------
// The skeleton's one boundary: J3DJointFactory's constructor.
// ---------------------------------------------------------------------------------------------
#include "JSystem/J3DGraphLoader/J3DJointFactory.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"
#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "boundary/game_boundary.h"
#include "m_Do/m_Do_controller_pad.h"

// PARTIAL. The decomp's JSUConvertOffsetToPtr truncates the base pointer to 32 bits, garbage on
// x64. The port's J3DJointBlock holds pointers instead of offsets, and this is the two
// assignments that leaves. The archive reader that fills a real block is not ported.
J3DJointFactory::J3DJointFactory(const J3DJointBlock& jointBlock) {
    boundary_reached("J3DJointFactory::J3DJointFactory", "PARTIAL");
    mJointInitData = jointBlock.mpJointInitData;
    mIndexTable = jointBlock.mpIndexTable;
}

thread_local int j3d_boundary_hits = 0;
thread_local const char* j3d_boundary_last = "";

// HARNESS. The J3D counter.
void j3d_boundary_reached(const char* who) {
    j3d_boundary_hits++;
    j3d_boundary_last = who;
    // Also into the port-wide census; the subsystem counter is unchanged.
    boundary_reached(who, "SCOPE");
}

// SCOPE. J3DJoint's three draw-side virtuals: entryIn queues display lists; recursiveCalc is
// unused (J3DModel::calcAnmMtx goes through J3DMtxCalcBasic); J3DMtxCalcSoftimage::calcTransform
// is /* Nonmatching */ and Link's cl.bdl is Maya. Defined because each fills a vtable slot; each
// traps.
void J3DJoint::entryIn() { j3d_boundary_reached("J3DJoint::entryIn"); }
void J3DJoint::recursiveCalc() { j3d_boundary_reached("J3DJoint::recursiveCalc"); }
void J3DMtxCalcSoftimage::calcTransform(u16, const J3DTransformInfo&) {
    j3d_boundary_reached("J3DMtxCalcSoftimage::calcTransform");
}

// =============================================================================================
// dCamera_c::Run's boundary. Run is copied; its callees are here, and most dispatch entries answer
// FALSE. Each stub bumps `cam_boundary_hits` and names itself. Camera grades:
//   SCOPE, UNPORTED - the decomp body exists; this slice did not take it.
//   SCOPE, EMPTY    - the decomp body is empty at the pinned commit.
//   SCOPE           - a real subsystem behind the call (draw list, audio, process manager, weather).
thread_local int cam_boundary_hits = 0;
thread_local const char* cam_boundary_last = "";

// The camera census: one count per name. Names are literals compared by pointer.
namespace {
struct CamBoundaryRow {
    const char* who;
    int hits;
};
thread_local CamBoundaryRow cam_rows[128];
thread_local int cam_row_count = 0;
}  // namespace

// HARNESS. The camera census's five functions.
void cam_boundary_reached(const char* who) {
    cam_boundary_hits++;
    cam_boundary_last = who;
    // Also into the port-wide census; the camera's own table is reset separately.
    boundary_reached(who, "SCOPE");
    for (int i = 0; i < cam_row_count; i++) {
        if (cam_rows[i].who == who) {
            cam_rows[i].hits++;
            return;
        }
    }
    if (cam_row_count < static_cast<int>(sizeof(cam_rows) / sizeof(cam_rows[0]))) {
        cam_rows[cam_row_count].who = who;
        cam_rows[cam_row_count].hits = 1;
        cam_row_count++;
    }
}

void cam_boundary_reset() {
    cam_boundary_hits = 0;
    cam_boundary_last = "";
    cam_row_count = 0;
}

int cam_boundary_names() { return cam_row_count; }

const char* cam_boundary_name(int i) { return cam_rows[i].who; }

int cam_boundary_name_hits(int i) { return cam_rows[i].hits; }

// SCOPE. A draw-list effect line; Run's first line turns it off.
bool dCamForcusLine::Off() {
    cam_boundary_reached("dCamForcusLine::Off");
    return false;
}

// ---------------------------------------------------------------- Run's own eleven helpers
//
// SCOPE. Real bodies in d_camera.cpp this slice did not span. Run chases m148 toward
// forwardCheckAngle() at FwdCushion() a frame, so with the target stubbed m148 decays toward a
// constant.
void dCamera_c::updateMonitor() { cam_boundary_reached("dCamera_c::updateMonitor"); }
void dCamera_c::Att() { cam_boundary_reached("dCamera_c::Att"); }
void dCamera_c::checkSpecialArea() { cam_boundary_reached("dCamera_c::checkSpecialArea"); }

// MEASURED. A definition, not a stub: d_camera.h:653 writes it inline, but this port's
// d_camera.h cannot include d_a_player_main.h, which includes it. Not in the census.
f32 dCamera_c::footHeightOf(fopAc_ac_c* i_actor) { return i_actor->current.pos.y; }

// SCOPE. Two dComIfG_Ccsp() reads; this port has no dCcS. Unreached: both checkGroundInfo call
// sites are inside `if (m360)`, which is 0 on an empty dBgS.
u32 dCamera_c::lineCollisionCheckBush(cXyz* i_start, cXyz* i_end) {
    (void)i_start;
    (void)i_end;
    cam_boundary_reached("dCamera_c::lineCollisionCheckBush");
    return 0;
}

// SCOPE, UNREACHED. Behind `if (m364)` inside `if (m360)`; m364 is the stub above's 0. Writes
// nothing to m36C, so it cannot pass for a port.
void dCcS::GetMassCamTopPos(cXyz* o_pos) {
    (void)o_pos;
    cam_boundary_reached("dCcS::GetMassCamTopPos");
}

// SCOPE, UNREACHED. The collision-check system, a real object so `dComIfG_Ccsp()->...` is a
// call and not a crash.
dCcS* dComIfG_Ccsp() {
    thread_local dCcS ccs;
    return &ccs;
}

bool dCamera_c::checkForceLockTarget() {
    cam_boundary_reached("dCamera_c::checkForceLockTarget");
    return false;
}

// SCOPE. The type half of the deciders (nextMode, onModeChange, onStyleChange are copies). A
// camera type comes from the stage's camera table, which this port does not load. nextType
// returns its input: a 0 would be a spurious type change.
int dCamera_c::nextType(s32 i_cur) {
    cam_boundary_reached("dCamera_c::nextType");
    return i_cur;
}

bool dCamera_c::onTypeChange(s32, s32) {
    cam_boundary_reached("dCamera_c::onTypeChange");
    return false;
}

cSAngle dCamera_c::getDMCAngle(cSAngle) {
    cam_boundary_reached("dCamera_c::getDMCAngle");
    return cSAngle::_0;
}

int dCamera_c::defaultTriming() {
    cam_boundary_reached("dCamera_c::defaultTriming");
    return 0;
}

cSAngle dCamera_c::forwardCheckAngle() {
    cam_boundary_reached("dCamera_c::forwardCheckAngle");
    return cSAngle::_0;
}

// bumpCheck's helpers. Each sits behind an arm the copied bumpCheck evaluates: on an empty dBgS
// `lineBGCheck` misses, so four are in the branch not taken; the fifth needs
// `chkFlag(0x2000) && mpLockonTarget`.
//
// SCOPE, UNREACHED. d_camera.cpp:1668 and :1677, the lock-on arm; the census seeds no lock-on.
// 0.0f is the decomp's "not in sight".
f32 dCamera_c::radiusActorInSight(fopAc_ac_c*, fopAc_ac_c*) {
    cam_boundary_reached("dCamera_c::radiusActorInSight");
    return 0.0f;
}

// SCOPE, UNREACHED. c_m3d.cpp, the corner arm; needs both line checks to hit. FALSE falls
// through to `curr_hit_type = 2`, as an unsolvable corner does.
bool cM3d_2PlaneLinePosNearPos(const cM3dGPla&, const cM3dGPla&, const Vec*, Vec*) {
    cam_boundary_reached("cM3d_2PlaneLinePosNearPos");
    return false;
}

// SCOPE. The grab-actor arm, the one part of bumpCheck that runs here. The decomp's
// `mActorKeepGrab.getID()`; the port has no actor-keep list, so it answers the holding-nothing
// default. Everything past `grab_actor_id != -1` is dead by this value, which nothing measures.
fpc_ProcID daPy_lk_c::getGrabActorID() const {
    cam_boundary_reached("daPy_lk_c::getGrabActorID");
    return fpcM_ERROR_PROCESS_ID_e;
}

f32 dCamera_c::shakeCamera() {
    cam_boundary_reached("dCamera_c::shakeCamera");
    return 0.0f;
}

// ------------------------------------------------------- followCamera's remaining three
//
// SCOPE. followCamera's other callees are copied (src/d/d_camera.cpp). attention_info.position
// is still unwritten (setAttentionPos's caller, execute(), is not ported), so followCamera's four
// reads of it answer (0, 0, 0) into its line checks.
cSAngle dCamera_c::calcPeepAngle() {
    cam_boundary_reached("dCamera_c::calcPeepAngle");
    return cSAngle::_0;
}

// ---------------------------------------------------------------- the dispatch table's twenty
//
// SCOPE, UNPORTED for the nine the decomp writes out; SCOPE, EMPTY for the seven whose body is
// empty at this pin. All are modes the land scope never enters. followCamera, followCamera2,
// manualCamera and subjectCamera are copied.
bool dCamera_c::letCamera(s32) { cam_boundary_reached("dCamera_c::letCamera"); return false; }
bool dCamera_c::lockonCamera(s32) { cam_boundary_reached("dCamera_c::lockonCamera"); return false; }
bool dCamera_c::talktoCamera(s32) { cam_boundary_reached("dCamera_c::talktoCamera"); return false; }
bool dCamera_c::crawlCamera(s32) { cam_boundary_reached("dCamera_c::crawlCamera"); return false; }
bool dCamera_c::nonOwnerCamera(s32) { cam_boundary_reached("dCamera_c::nonOwnerCamera"); return false; }
bool dCamera_c::fixedFrameCamera(s32) { cam_boundary_reached("dCamera_c::fixedFrameCamera"); return false; }
bool dCamera_c::fixedPositionCamera(s32) { cam_boundary_reached("dCamera_c::fixedPositionCamera"); return false; }
bool dCamera_c::eventCamera(s32) { cam_boundary_reached("dCamera_c::eventCamera"); return false; }
bool dCamera_c::demoCamera(s32) { cam_boundary_reached("dCamera_c::demoCamera"); return false; }

bool dCamera_c::towerCamera(s32) { cam_boundary_reached("dCamera_c::towerCamera"); return false; }
bool dCamera_c::hookshotCamera(s32) { cam_boundary_reached("dCamera_c::hookshotCamera"); return false; }
bool dCamera_c::tornadoCamera(s32) { cam_boundary_reached("dCamera_c::tornadoCamera"); return false; }
bool dCamera_c::rideCamera(s32) { cam_boundary_reached("dCamera_c::rideCamera"); return false; }
bool dCamera_c::hungCamera(s32) { cam_boundary_reached("dCamera_c::hungCamera"); return false; }
bool dCamera_c::vomitCamera(s32) { cam_boundary_reached("dCamera_c::vomitCamera"); return false; }
bool dCamera_c::shieldCamera(s32) { cam_boundary_reached("dCamera_c::shieldCamera"); return false; }

// ---------------------------------------------------------------- the free calls on Run's lines

// SCOPE. The camera-attention word lives in the game-info block, which the port does not have;
// Run never reads back what it posts. Kept apart from the player's driven copy
// (dComIfGp_checkCameraAttentionStatus) so one gate's output is not another's input.
void dComIfGp_onCameraAttentionStatus(int, u32) {
    cam_boundary_reached("dComIfGp_onCameraAttentionStatus");
}

// SCOPE. followCamera's NPC flags: the Komali/Medli companion flying, Medli's mirror, a
// controlled seagull. Each is a flag only that NPC writes; false is the game's answer while none
// is loaded, and wrong in a room that loads one (Earth Temple, Dragon Roost).
bool daNpc_Cb1_c::isFlying() {
    cam_boundary_reached("daNpc_Cb1_c::isFlying");
    return false;
}

bool daNpc_Md_c::isFlying() {
    cam_boundary_reached("daNpc_Md_c::isFlying");
    return false;
}

bool daNpc_Md_c::isMirror() {
    cam_boundary_reached("daNpc_Md_c::isMirror");
    return false;
}

// A `static bool` in the decomp, so a definition; false for the reason above. Uncounted.
bool daNpc_kam_c::m_hyoi_kamome = false;

// SCOPE. followCamera's fovy jitter. A copy would draw from seeds this engine cannot know (see
// cM_rnd), so it answers 0 and the port's camera does not jitter.
float cM_rndFX(float) {
    cam_boundary_reached("cM_rndFX");
    return 0.0f;
}

// SCOPE. `m080 + cM_rndFX(m084) * dKyw_get_wind_pow()` in the decomp; manualCamera calls it. The
// random half is zero here, so m080 is the whole answer.
f32 dCamSetup_c::FanBank() {
    cam_boundary_reached("dCamSetup_c::FanBank");
    return m080;
}

// SCOPE. d_bg_s.h. Carries the camera through a moving room's matrix, behind followCamera's
// `m31D != 0`. No loaded room moves, and the decomp's body does nothing without a bg index.
void dBgS::MoveBgMatrixCrrPos(cBgS_PolyInfo&, bool, cXyz*, csXyz*, csXyz*) {
    cam_boundary_reached("dBgS::MoveBgMatrixCrrPos");
}

void dComIfGp_offCameraAttentionStatus(int, u32) {
    cam_boundary_reached("dComIfGp_offCameraAttentionStatus");
}

u32 dComIfGp_getCameraAttentionStatus(int) {
    cam_boundary_reached("dComIfGp_getCameraAttentionStatus");
    return 0;
}

// SCOPE. Posts the zoom scale to the game-info block. subjectCamera calls it every frame
// dCamPrmFlg_UNK010 is up, which the C up turn reaches.
void dComIfGp_setCameraZoomScale(int, f32) {
    cam_boundary_reached("dComIfGp_setCameraZoomScale");
}

// SCOPE. The zoom focus, posted beside the scale; neither reaches the yaw the finder reads.
void dComIfGp_setCameraZoomForcus(int, f32) {
    cam_boundary_reached("dComIfGp_setCameraZoomForcus");
}

// SCOPE. The scope type. A nonzero answer raises m3BC, which can reach the yaw; 0 is no
// telescope or picto box up, as on every land move.
u8 dComIfGp_getScopeType() {
    cam_boundary_reached("dComIfGp_getScopeType");
    return 0;
}

// SCOPE. The graphics auto-focus flag; nothing draws or reads it.
void mDoGph_gInf_c::offAutoForcus() {
    cam_boundary_reached("mDoGph_gInf_c::offAutoForcus");
}

// SCOPE. The telescope iris wipe, behind dCamPrmFlg_UNK010, which the finder's style does not
// raise. 0 is the wipe not started.
f32 dComIfGp_getItemScopeWipeScale() {
    cam_boundary_reached("dComIfGp_getItemScopeWipeScale");
    return 0.0f;
}

// SCOPE. The viewport rectangle; onModeChange calls it only for the telescope (mode 0xe).
void dCamera_c::setView(f32, f32, f32, f32) { cam_boundary_reached("dCamera_c::setView"); }

// SCOPE. "Is a cutscene driving the camera"; FALSE lets Run take its normal path.
int dComIfGp_evmng_cameraPlay() {
    cam_boundary_reached("dComIfGp_evmng_cameraPlay");
    return 0;
}

// SCOPE. The demo camera object; NULL is the no-cutscene answer.
dDemo_camera_c* dComIfGp_demo_getCamera() {
    cam_boundary_reached("dComIfGp_demo_getCamera");
    return 0;
}

// SCOPE. The attention system. Run asks only whether anything is locked on.
thread_local bool cam_stub_lockon = false;
thread_local bool cam_stub_lockon_truth = false;

bool dAttention_c::Lockon() {
    cam_boundary_reached("dAttention_c::Lockon");
    return cam_stub_lockon;
}

// SCOPE. A second stub, not derived from Lockon: the decomp's Lockon is an inline over this, and
// nextMode branches on both. FALSE falls through the mode ladder to the land path.
bool dAttention_c::LockonTruth() {
    cam_boundary_reached("dAttention_c::LockonTruth");
    return cam_stub_lockon_truth;
}

dAttention_c& dComIfGp_getAttention() {
    thread_local dAttention_c s_attention;
    return s_attention;
}

// SCOPE. One arm of the event-camera interrupt test, behind `chkFlag(0x200000)`; not copied, as
// its body reads the whole pad block (see d_camera.h).
BOOL push_any_key(int) {
    cam_boundary_reached("push_any_key");
    return FALSE;
}

// The pad block: a definition, not a stub. The game's driver fills it once a frame; here a caller
// seeds it, and every copied CPad_* macro (m_Do_controller_pad.h) reads it. Not in the camera
// census. The player's mStickAngle/mStickDistance are seeded separately (setStickData is not
// ported), so a caller must keep the two consistent.
thread_local interface_of_controller_pad g_mDoCPd_cpadInfo[4];

// SCOPE. The audio engine. Run fires one of three cues when a bit of m254 goes up that was down
// last frame; the real one returns JAISound** and Run discards it.
void mDoAud_seStart(u32) {
    cam_boundary_reached("mDoAud_seStart");
}

// SCOPE. The pirate ship's deck height, behind `m530`; the land scope has no ship.
namespace daObjPirateship {
f32 getShipOffsetY(s16*, s16*, f32) {
    cam_boundary_reached("daObjPirateship::getShipOffsetY");
    return 0.0f;
}
}
