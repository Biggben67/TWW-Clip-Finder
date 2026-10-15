#include "engine/session.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include "boundary/game_boundary.h"
#include "engine/jma_console_table.h"
#include "engine/ppc_fp.h"
#include "SSystem/SComponent/c_lib.h"

namespace tww_engine {

uint32_t f32_bits(f32 f) {
    uint32_t u;
    std::memcpy(&u, &f, 4);
    return u;
}

namespace {

/// daPy_lk_c::create's collision lines (d_a_player_main.cpp:12188-12196). `create` itself is not
/// ported; the world-dependent parts are left to the caller.
void player_create_collision(daPy_lk_c& lk) {
    lk.mAcch.Set(&lk.current.pos, &lk.old.pos, NULL, ARRAY_SIZE(lk.mAcchCir), lk.mAcchCir,
                 &lk.speed, &lk.current.angle, &lk.shape_angle);
    lk.mAcch.ClrWaterNone();
    lk.mAcch.SetWaterCheckOffset(500.0f);
    lk.mAcch.OnLineCheck();
    lk.mAcch.ClrRoofNone();
    lk.mAcch.SetRoofCrrHeight(125.0f);
    // -175.0 from the HIO table; only FAN_GLIDE and SLOW_FALL rewrite it and neither is ported.
    lk.maxFallSpeed = lk.m_HIO->mAutoJump.m.field_0x10;
    lk.mAcchCir[0].SetWall(30.1f, 35.0f);
    lk.mAcchCir[1].SetWall(89.9f, 35.0f);
    lk.mAcchCir[2].SetWall(125.0f, 35.0f);
}

/// fopAcM_GetID's answer for this player. Must differ from the room's id, or every collision walk
/// would reject the room as the actor's own collision.
const fpc_ProcID kSessionPlayerPid = kLinkPid;

}  // namespace

Session::Session() : Session((const RoomDzb*)NULL) {}

Session::Session(const RoomDzb& dzb) : Session(&dzb) {}

/// Process-wide, not per thread: `built()` checks a claim about the whole process.
namespace {
std::atomic<unsigned long long> g_sessions_built(0);
}  // namespace

unsigned long long Session::built() { return g_sessions_built.load(std::memory_order_relaxed); }

Session::Session(const RoomDzb* dzb, const RunOptions& options) : Session(dzb, NULL, options) {}

Session::Session(Room& shared, const RunOptions& options) : Session(NULL, &shared, options) {}

Session::Session(const RoomDzb* dzb, Room* shared, const RunOptions& options) : opts(options) {
    g_sessions_built.fetch_add(1, std::memory_order_relaxed);
    // `jmaSinTable`, which the game fills at boot (m_Do_machine.cpp:614, `JMANewSinTable(12)`);
    // every JMASSin/JMASCos reads it. Shared read-only data, so installed once for all threads.
    static std::once_flag s_sin_table_installed;
    std::call_once(s_sin_table_installed, JMA_useConsoleSinTable);
    bgs.Ct();
    lk.reset_boundary();
    lk.m_HIO = &hio;
    player_create_collision(lk);
    lk.mAcch.SetActorPid(kSessionPlayerPid);
    // CrrPos tests these itself (d_bg_s_acch.cpp:267, :275, :288). After player_create_collision,
    // which clears the roof flag (:12192).
    if (!opts.wall_correct) {
        lk.mAcch.SetWallNone();
    }
    if (!opts.roof_chk) {
        lk.mAcch.SetRoofNone();
    }
    if (opts.ground == RunOptions::Ground::None) {
        lk.mAcch.SetGrndNone();
    }

    if (shared != NULL && opts.ground == RunOptions::Ground::Supplied) {
        std::fprintf(stderr, "Session: RunOptions::Ground::Supplied builds its own floor, so it "
                             "cannot also run in a shared room\n");
        std::abort();
    }
    if (shared != NULL) {
        // A lent room: nothing to build.
    } else if (opts.ground == RunOptions::Ground::Supplied) {
        if (dzb != NULL) {
            std::fprintf(stderr,
                         "Session: RunOptions::Ground::Supplied builds the world out of a floor "
                         "at %f, so it cannot also take a room - see flat_floor_dzb in "
                         "engine/room.h\n",
                         opts.floor_y);
            std::abort();
        }
        room.reset(new Room(flat_floor_dzb(opts.floor_y)));
    } else if (dzb != NULL) {
        room.reset(new Room(*dzb));
    }
    world = shared != NULL ? shared : room.get();
    bind();
    // Every session gets one: reset_boundary() raises mOldFrameFlg, so posMoveFromFootPos
    // concatenates m37B4 onto mpCLModel->getAnmMtx(), which must exist. Never posed, the joint
    // matrices are zero and mFootData is m37B4's translation column four times.
    attachSkeleton();

    // Seated here for sessions without an `Init`; the `Init` constructors re-seat once Link has
    // a position.
    if (opts.camera) {
        seatCamera(opts.camera_yaw, opts.camera_type, opts.camera_radius);
    }
}

/// The one line of setAtnList this port needs (d_a_player_main.cpp:2066): while the lock is held,
/// `m34E6 = shape_angle.y` every frame. `setSpeedAndAngleAtn` ends with `shape_angle.y = m34E6`,
/// so without this every locked move snaps Link to facing 0. setAtnList runs before
/// animeUpdate() and the proc (:11315, :11344).
static void stub_set_atn_list(daPy_lk_c& lk) {
    if (lk.stub_attention_lock) {
        lk.m34E6 = lk.shape_angle.y;
    }
}

Session::Session(const Init& init, const RoomDzb* dzb, const RunOptions& options)
    : Session(dzb, options) {
    seed(init);
}

Session::Session(const Init& init, Room& shared, const RunOptions& options)
    : Session(shared, options) {
    seed(init);
}

/// The ground code in `m3580` and the slope along the facing in `m34E2`, as execute()'s grounded
/// tail records them (d_a_player_main.cpp:11451, 11486-11492, 11501, 11528-11531); -1 and 0 with
/// no floor.
void ground_under(daPy_lk_c& lk) {
    if (lk.mAcch.GetGroundH() == -G_CM3D_F_INF) {
        lk.m3580 = -1;
        lk.m34E2 = 0;
        return;
    }
    lk.m3580 = dComIfG_Bgsp()->GetGroundCode(lk.mAcch.m_gnd);
    if (lk.mAcch.ChkGroundHit() &&!lk.checkNoResetFlg0(daPyFlg0_UNK80000000)) {
        lk.m34E2 = lk.getGroundAngle(&lk.mAcch.m_gnd, lk.shape_angle.y);
    } else {
        lk.m34E2 = 0;
    }
}

/// A standstill exactly on its floor, read as standing on it - see Session::seed.
static void seat_on_floor(daPy_lk_c& lk) {
    dBgS_Acch& acch = lk.mAcch;
    if (!acch.ChkGroundHit() && acch.GetGroundH() != -G_CM3D_F_INF &&
        acch.field_0xb8 == lk.current.pos.y) {
        acch.m_pla = *dComIfG_Bgsp()->GetTriPla(acch.m_gnd);
        acch.SetGroundFind();
        acch.SetGroundHit();
    }
}

void Session::seed(const Init& init) {
    // Before the init: commonProcInit reads the equip.
    lk.mEquipItem = init.equip_item;
    lk.stub_select_equip[0] = init.select_equip_0;

    if (!run_proc_init(lk, init.proc)) {
        std::fprintf(stderr,
                     "Session: proc %d has no argument-free _init, so this port cannot start in "
                     "it - see run_proc_init in engine/session.h\n",
                     init.proc);
        std::abort();
    }

    // After the init, which writes angles and speeds of its own.
    lk.current.pos = init.pos;
    lk.old.pos = lk.current.pos;
    lk.shape_angle.y = init.shape_angle_y;
    lk.current.angle.y = init.travel_angle_y;
    lk.mNormalSpeed = init.normal_speed;
    lk.speedF = init.speed_f;
    lk.m34DC = init.pad.stick_angle_raw;
    lk.m34E8 = init.pad.target_angle;
    lk.mStickDistance = init.pad.stick_distance;
    lk.mItemButton = init.pad.item_button;
    lk.mItemTrigger = init.pad.item_trigger;
    lk.stub_attention_lock = init.pad.attention_lock;
    stub_set_atn_list(lk);

    // The previous frame's collision pass, which a standing player has already run: without it
    // frame 1 reads "not on the ground" and takes the level-ground speed on a slope.
    //
    // GroundCheck sets the hit only for a floor strictly above the feet; on console a standing
    // player sinks under gravity and is lifted back each frame. A seed exactly on the floor has
    // not sunk, so seat_on_floor sets the hit for that equal case only.
    //
    // The wall pass lifts its cut height by the previous frame's floor (GetWallAddY), so the pass
    // runs first with walls off to find the floor, then again with them on.
    if (world != NULL) {
        dBgS_Acch& acch = lk.mAcch;
        const bool walls_off = (acch.m_flags & dBgS_Acch::WALL_NONE) != 0;
        acch.SetWallNone();
        crr_pos();
        if (!walls_off) acch.ClrWallNone();
        lk.old.pos = lk.current.pos;
        seat_on_floor(lk);
        crr_pos();
        lk.old.pos = lk.current.pos;
        seat_on_floor(lk);
        // Frame 1 reads the ground code and slope before its own tail writes them.
        ground_under(lk);
    }

    // Re-seated now that Link has a position: the camera is centred on him.
    if (opts.camera) {
        seatCamera(opts.camera_yaw, opts.camera_type, opts.camera_radius);
    }
}

/// `dCamera_c` built by placement-new over zeroed bytes - see the member's note.
struct Session::CameraHome {
    alignas(dCamera_c) unsigned char bytes[sizeof(dCamera_c)];
    dCamera_c* cam;

    CameraHome() {
        std::memset(bytes, 0, sizeof(bytes));
        cam = new (static_cast<void*>(bytes)) dCamera_c();
    }
    ~CameraHome() { cam->~dCamera_c(); }

    CameraHome(const CameraHome&);
    CameraHome& operator=(const CameraHome&);
};

/// The manual camera's mode.
static const int kFinderMode = 12;

void Session::seatCamera(s16 yaw, int type, f32 seat_radius) {
    // The camera's constructor reads `dComIfGp_getPlayer(0)`.
    bind();
    // The lock-on point the centre is read from; outside a frame nothing else has set it.
    lk.setAttentionPos();
    camera.reset(new CameraHome());
    dCamera_c& cam = *camera->cam;

    cam.mPadId = 0;
    cam.mpPlayerActor = static_cast<fopAc_ac_c*>(static_cast<void*>(&lk));
    cam.mCurType = type;
    cam.mCurMode = kFinderMode;
    cam.mCurStyle = dCamera_c::types[type].mStyles[kFinderMode];
    cam.mCamParam.Change(static_cast<s16>(cam.mCurStyle));

    // Style parameter 10 is the globe radius the algorithms chase; 25 is the fovy.
    const f32 radius = seat_radius > 0.0f ? seat_radius : cam.mCamParam.Val(cam.mCurStyle, 10);
    // `mAngleY = mDirection.U().Inv()` and `Inv()` is `- 0x8000`. Level elevation.
    const s16 inclination = static_cast<s16>(yaw + 0x8000);
    cam.mDirection.Val(radius, static_cast<s16>(0), inclination);
    cam.mViewCache.mDirection.Val(radius, static_cast<s16>(0), inclination);

    // Centre on the attention point, eye = centre + globe, the relation Run maintains.
    cam.mViewCache.mCenter = lk.attention_info.position;
    cam.mViewCache.mEye = cam.mViewCache.mCenter + cam.mViewCache.mDirection.Xyz();
    cam.mCenter = cam.mViewCache.mCenter;
    cam.mEye = cam.mViewCache.mEye;
    cam.mFovy = cam.mCamParam.Val(cam.mCurStyle, 25);
    cam.mViewCache.mFovy = cam.mFovy;
    cam.mAngleY = cam.mDirection.U().Inv();

    // Past the entry transition; `followCamera`'s entry guard reads `m100`.
    cam.m100 = 1;
    cam.m101 = 1;
    cam.m102 = 1;
    cam.m110 = 1;
    cam.m108 = 0;
    cam.m11C = 0;
    cam.m068 = 0;
    cam.mEventFlags = 0;
    cam.m144 = 0;
    cam.m184 = 0;
    cam.m19A = 0;
    cam.m19B = 0;

    // No lock-on target and no force-lock actor.
    cam.mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    cam.mpLockonActor = 0;
    cam.mpLockonTarget = 0;
}

s16 Session::cameraYaw() const {
    if (camera == NULL) {
        std::fprintf(stderr,
                     "Session::cameraYaw: no camera is seated - call seatCamera() first, or read "
                     "hasCamera() rather than treating 0 as an answer\n");
        std::abort();
    }
    return camera->cam->mAngleY.Val();
}

dCamera_c& Session::cameraBody() {
    if (!camera) std::abort();
    return *camera->cam;
}

Session::CameraFacts Session::cameraFacts() const {
    if (camera == NULL) {
        std::fprintf(stderr,
                     "Session::cameraFacts: no camera is seated - call seatCamera() first, or "
                     "read hasCamera()\n");
        std::abort();
    }
    const dCamera_c& cam = *camera->cam;
    CameraFacts f;
    f.mode = cam.mCurMode;
    f.next_mode = cam.mNextMode;
    f.style = cam.mCurStyle;
    f.entry_done = cam.m100;
    f.entry_frame = static_cast<int>(cam.m108);
    f.manual_given_up = cam.m144;
    f.cstick_latch = cam.m184;
    f.yaw = cam.mAngleY.Val();
    f.radius = cam.mDirection.R();
    f.gate_radius = cam.mCamSetup.m098;
    f.cstick = cam.mStickCValueLast;
    f.eye[0] = cam.mViewCache.mEye.x;
    f.eye[1] = cam.mViewCache.mEye.y;
    f.eye[2] = cam.mViewCache.mEye.z;
    f.center[0] = cam.mViewCache.mCenter.x;
    f.center[1] = cam.mViewCache.mCenter.y;
    f.center[2] = cam.mViewCache.mCenter.z;
    f.room_cam_idx = cam.mRoomMapToolCameraIdx;
    f.room_no = cam.mRoomNo;
    f.cam_move_bg = cam.m350;
    return f;
}

int Session::runCamera(int frames) {
    if (camera == NULL) {
        std::fprintf(stderr,
                     "Session::runCamera: no camera is seated - call seatCamera() first, or read "
                     "hasCamera()\n");
        std::abort();
    }
    bind();
    int ran = 0;
    while (ran < frames) {
        camera->cam->Run();
        ran++;
    }
    return ran;
}

int Session::runFirstPersonCamera(int frames) {
    if (camera == NULL) {
        std::fprintf(stderr,
                     "Session::runFirstPersonCamera: no camera is seated - call seatCamera() "
                     "first, or read hasCamera()\n");
        std::abort();
    }
    bind();
    dCamera_c& cam = *camera->cam;

    // `nextMode` answers 4 (first person) off this status alone. Restored below.
    const u32 was = lk.stub_player_status0;
    lk.stub_player_status0 |= daPyStts0_SUBJECT_e;

    int ran = 0;
    while (ran < frames) {
        cam.Run();
        ran++;
        // `m100` ends the entry; past it the body takes the walk arm.
        if (cam.m100) {
            break;
        }
    }

    lk.stub_player_status0 = was;
    return ran;
}

void Session::bind() {
    // The room's world when there is one, otherwise the empty member.
    set_dComIfG_Bgsp(world ? &world->bgs() : &bgs);
    set_dComIfG_player(&lk);
}

/// The three joint-callback trampolines. The decomp's (d_a_player_main.cpp:385-388, 417-420,
/// 547-555) recover the player from a `u32` user area, which cannot hold a 64-bit pointer, so
/// these read the bound player instead.
static int player_joint_before(u32, u16 jnt_no, J3DTransformInfo* info, Quaternion* quat) {
    return static_cast<daPy_lk_c*>(dComIfGp_getPlayer(0))->jointBeforeCB(jnt_no, info, quat);
}

static int player_joint_after(u32, u16 jnt_no, J3DTransformInfo* info, Quaternion* quat) {
    return static_cast<daPy_lk_c*>(dComIfGp_getPlayer(0))->jointAfterCB(jnt_no, info, quat);
}

static int player_joint_cb1(J3DNode*, int calcTiming) {
    if (calcTiming == J3DNodeCBCalcTiming_In) {
        static_cast<daPy_lk_c*>(dComIfGp_getPlayer(0))->jointCB1();
    }
    return TRUE;
}

void Session::attachSkeleton(bool alreadyCalculated) {
    skeleton.reset(new LinkModel());
    // create's own line (d_a_player_main.cpp:12023).
    skeleton->setMtxCalcOnAllJoints(lk.m_pbCalc[daPy_lk_c::PART_UNDER_e]);
    lk.mpCLModel = skeleton->model();
    // create hands one `m_old_fdata` to the player and both blend tables
    // (d_a_player_main.cpp:12020-12026).
    mDoExt_MtxCalcOldFrame* old_frame = &lk.port_old_fdata;
    if (!alreadyCalculated) {
        fresh_old.reset(new FreshOldFrame());
        old_frame = &fresh_old->old_frame;
    }
    lk.m_old_fdata = old_frame;
    lk.m_pbCalc[daPy_lk_c::PART_UNDER_e]->mOldFrame = old_frame;
    lk.m_pbCalc[daPy_lk_c::PART_UPPER_e]->mOldFrame = old_frame;
    // playerInit's joint callbacks (d_a_player_main.cpp:12134-12141), the foot IK's way into the
    // pose. jointCallback0's eight upper-body joints are not installed: they only re-weigh
    // PART_UPPER's blend, and this skeleton poses every joint off PART_UNDER.
    if (opts.foot_ik && opts.pose_skeleton) {
        for (int i = 0; i < 2; i++) {
            lk.m_pbCalc[i]->setBeforeCalc(player_joint_before);
            lk.m_pbCalc[i]->setAfterCalc(player_joint_after);
        }
        skeleton->joint(CL_JNT_RTOE_JNT_e)->setCallBack(player_joint_cb1);
    }
}

void Session::setSingleAnim(J3DAnmTransform* anm) {
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE0_e].setAnmTransform(anm);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE0_e].setRatio(1.0f);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE1_e].setAnmTransform(NULL);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE1_e].setRatio(0.0f);
}

void Session::setBlendAnim(J3DAnmTransform* move0, J3DAnmTransform* move1, f32 ratio) {
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE0_e].setAnmTransform(move0);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE0_e].setRatio(1.0f - ratio);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE1_e].setAnmTransform(move1);
    lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE1_e].setRatio(ratio);
}

void Session::poseSkeleton() {
    lk.setWorldMatrix();
    // execute():11545-11548. footBgCheck reads last frame's leg matrices, so it waits for one pose.
    if (opts.foot_ik) {
        lk.setWaistAngle();
        if (lk.m_old_fdata->getOldFrameFlg()) {
            lk.footBgCheck();
        }
    }
    lk.mpCLModel->calcAnmMtx();
}

Room::FrameResult Session::crr_pos() {
    if (world == NULL) {
        std::fprintf(stderr, "crr_pos: this Session has no room; construct it with a RoomDzb\n");
        std::abort();
    }
    lk.mAcch.ClrGroundHit();
    return world->CrrPos(lk.mAcch, lk.mAcchCir, ARRAY_SIZE(lk.mAcchCir));
}

int Session::boundary_hits() const {
    // The census total: the j3d and cam counters also bump the census, so adding them would
    // double-count.
    return ::boundary_hits_total();
}

std::vector<BoundaryHit> Session::boundary_report() const {
    std::vector<BoundaryHit> out;
    const int n = ::boundary_names();
    out.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; i++) {
        BoundaryHit row;
        row.name = ::boundary_name(i);
        row.grade = ::boundary_name_grade(i);
        row.hits = ::boundary_name_hits(i);
        out.push_back(row);
    }
    return out;
}

bool Session::boundary_report_truncated() const {
    return ::boundary_dropped() != 0;
}

void Session::boundary_reset() {
    ::boundary_reset();
}

StepResult Session::step(const Pad& pad) {
    bind();

    actor_old_set(lk);
    frame_top(lk);

    lk.mStickDistance = pad.stick_distance;
    lk.m34E8 = pad.target_angle;
    lk.m34DC = pad.stick_angle_raw;
    lk.mItemButton = pad.item_button;
    lk.mItemTrigger = pad.item_trigger;
    lk.stub_attention_lock = pad.attention_lock;
    stub_set_atn_list(lk);

    stick_accumulate(lk);

    // animeUpdate() (d_a_player_main.cpp:11346, 12881). An UNDER clock with no length would hang
    // in the wrap loop, so stop first. UPPER clocks are exempt: nothing is posed off PART_UPPER,
    // and a zero-length upper clock is EMode_NONE, which stops rather than wraps (WAIT's is one).
    if (lk.anm_meta_missing != 0) {
        return StepResult::NoAnimation;
    }
    lk.animeUpdate();
    // checkItemAction's sword REST arm (decomp d_a_player_main.cpp:3968-4020).
    // Other item/equip animations remain outside this adapter's supported scope.
    if (lk.checkUpperAnime(dRes_INDEX_LKANM_BCK_REST_e) &&
        (lk.m3562 == daPyItem_NONE_e || lk.m3562 == daPyItem_SWORD_e)) {
        auto& clock = lk.mFrameCtrlUpper[daPy_lk_c::UPPER_MOVE2_e];
        if (std::fabs(clock.getRate()) < 0.01f) {
            lk.resetActAnimeUpper(daPy_lk_c::UPPER_MOVE2_e, lk.m_HIO->mBasic.m.mAnmMorf);
        } else if (clock.checkPass(7.0f)) {
            const bool was_equipped = lk.mEquipItem != daPyItem_NONE_e;
            lk.offNoResetFlg1(daPyFlg1_UNK200000);
            lk.mEquipItem = lk.m3562;
            if ((lk.mEquipItem != daPyItem_SWORD_e || !lk.checkNoResetFlg1(daPyFlg1_UNK4000000)) &&
                (lk.checkAttentionLock() || lk.mEquipItem != daPyItem_SWORD_e || was_equipped))
                lk.onResetFlg0(daPyRFlg0_UNK80);
        }
    }
    cut_window(lk);

    if (!run_proc(lk)) {
        return StepResult::NoProcBody;
    }
    // Again after the dispatch, whose inits load animations posMove and the pose read.
    if (lk.anm_meta_missing != 0) {
        return StepResult::NoAnimation;
    }

    pos_move(lk);
    last_raw_position = lk.current.pos;
    if (world != NULL) {
        crr_pos();
        ground_tail(lk, opts);
    }
    if (opts.pose_skeleton) {
        lk.port_carried_draw_lean=lk.shape_angle.z;
        lk.port_carried_pose_morf=lk.m_old_fdata->getOldFrameRate();
        poseSkeleton();
    }
    if (lk.stub_carried_movement_only) {
        // setMoveSlantAngle runs after the draw, so this tilts the following frame.
        const auto& h=lk.m_HIO->mMove.m;
        const float ratio=std::fabs(ppc::fdivs(lk.speedF,lk.mMaxNormalSpeed));
        if (lk.mCurProc==daPy_lk_c::daPyProc_MOVE_e && ratio>h.field_0x4C) {
            const float scale=ppc::fdivs(ppc::fsubs(ratio,h.field_0x4C),ppc::fsubs(1.0f,h.field_0x4C));
            const s16 target=(s16)ppc::fmuls(ppc::fmuls(h.field_0x50,(s16)(lk.m34DE-lk.shape_angle.y)),scale);
            cLib_addCalcAngleS(&lk.port_carried_slant,target,h.field_0xC,h.field_0x8,h.field_0xA);
        } else {
            const s16 decay=(s16)ppc::fmuls(lk.port_carried_slant,h.field_0x54);
            lk.port_carried_slant=decay ? (s16)(lk.port_carried_slant-decay) : 0;
        }
        lk.shape_angle.z=lk.port_carried_slant>>1;
    }
    // execute():11640, after the pose: the crawl arm reads the point out of the model matrix.
    lk.setAttentionPos();
    if (camera != NULL) {
        camera->cam->Run();
    }
    return StepResult::Ok;
}

Session::~Session() {
    set_dComIfG_player(NULL);
    set_dComIfG_Bgsp(NULL);
}

/// execute()'s grounded tail (d_a_player_main.cpp:11447-11522), the parts that reach a position:
/// the ground code `m3580` (8 is stairs), the slope `m34E2`, and the stair offset. The rest -
/// room info, attribute and fall codes, sound ids, moving-floor carry, `m357C` - writes nothing a
/// ported body reads.
void ground_tail(daPy_lk_c& lk, const RunOptions& opts) {
    (void)opts;
    ground_under(lk);
    if (lk.mAcch.GetGroundH() == -G_CM3D_F_INF) {
        return;
    }
    if (!lk.checkPlayerFly() &&
        lk.mCurProc != daPy_lk_c::daPyProc_DEMO_TOOL_e &&
        (lk.m34C3 == 1 || lk.m34C3 == 4 || lk.m34C3 == 0xA || lk.m34C3 == 9)
    ) {
        lk.setStepsOffset();
    }
}

void cut_window(daPy_lk_c& lk) {
    if (lk.m3522 > 0) {
        lk.m3522--;
    } else {
        lk.m34C4 = 0;
    }
}

void actor_old_set(daPy_lk_c& lk) {
    lk.old = lk.current;
}

void frame_top(daPy_lk_c& lk) {
    lk.m34DE = lk.shape_angle.y;
    lk.m34EA = lk.m34DC;
    // 11281: previous frame's stick distance, read by posMoveFromFootPos's smoothing guard.
    lk.m35B4 = lk.mStickDistance;
    lk.do_status = dActStts_BLANK_e;
    lk.r_status = dActStts_BLANK_e;
    // 11286-11292 write SWING, sword_01 or BLANK by equip; only the clear is carried. The one
    // reader asks whether RETURN (0x07) was posted, and none of those three values is RETURN.
    lk.a_status = dActStts_BLANK_e;
    lk.mFrontWallType = 0;
    lk.mResetFlg0 = 0;
    // 11325-11329: the root-motion arm selector, cleared every frame. The `m34C2 == 8` arm is the
    // hookshot's and unreachable here.
    lk.m34C2 = 0;
}

void stick_accumulate(daPy_lk_c& lk) {
    const daPy_HIO_cutTurnR_c1& m = lk.m_HIO->mCut.mCutTurnR.m;
    const s16 angle_diff = (s16)(lk.m34DC - lk.m34EA);
    const int abs_v = angle_diff < 0 ? -angle_diff : angle_diff;
    if (abs_v < m.field_0x6 && abs_v > m.field_0x8 && lk.m3578 * angle_diff >= 0) {
        lk.m3578 = lk.m3578 + angle_diff;
        lk.m3524 = m.field_0x2;
    } else if (lk.m3578 * angle_diff < 0) {
        lk.m3578 = angle_diff;
        lk.m3524 = m.field_0x2;
    } else if (m.field_0x0 == 0) {
        if (lk.m3524 > 0) {
            lk.m3524--;
        } else {
            lk.m3578 = 0;
        }
    }
}

/// execute() d_a_player_main.cpp:11400-11401. CrrPos is separate: see Session::crr_pos().
void pos_move(daPy_lk_c& lk) {
    lk.posMove();
    lk.mOldSpeed = lk.speed;
}

bool run_proc_init(daPy_lk_c& lk, int proc) {
    switch (proc) {
    case daPy_lk_c::daPyProc_MOVE_TURN_e:
        lk.procMoveTurn_init(0);
        return true;
    case daPy_lk_c::daPyProc_SLIP_e:
        lk.procSlip_init();
        return true;
    case daPy_lk_c::daPyProc_WAIT_e:
        lk.procWait_init();
        return true;
    case daPy_lk_c::daPyProc_FREE_WAIT_e:
        lk.procFreeWait_init();
        return true;
    case daPy_lk_c::daPyProc_MOVE_e:
        lk.procMove_init();
        return true;
    case daPy_lk_c::daPyProc_CROUCH_e:
        lk.procCrouch_init();
        return true;
    case daPy_lk_c::daPyProc_WAIT_TURN_e:
        lk.procWaitTurn_init();
        return true;
    case daPy_lk_c::daPyProc_ATN_MOVE_e:
        lk.procAtnMove_init();
        return true;
    case daPy_lk_c::daPyProc_CUT_EA_e:
        lk.procCutEA_init();
        return true;
    case daPy_lk_c::daPyProc_CUT_EB_e:
        lk.procCutEB_init();
        return true;
    case daPy_lk_c::daPyProc_BACK_JUMP_e:
        lk.procBackJump_init();
        return true;
    case daPy_lk_c::daPyProc_BACK_JUMP_LAND_e:
        lk.procBackJumpLand_init();
        return true;
    case daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e:
        lk.procCutTurnCharge_init();
        return true;
    case daPy_lk_c::daPyProc_CUT_TURN_MOVE_e:
        lk.procCutTurnMove_init();
        return true;
    case daPy_lk_c::daPyProc_CRAWL_START_e:
        lk.procCrawlStart_init();
        return true;
    default:
        return false;
    }
}

bool run_proc(daPy_lk_c& lk) {
    switch (lk.mCurProc) {
    case daPy_lk_c::daPyProc_MOVE_TURN_e:
        lk.procMoveTurn();
        return true;
    case daPy_lk_c::daPyProc_SLIP_e:
        lk.procSlip();
        return true;
    case daPy_lk_c::daPyProc_FRONT_ROLL_e:
        lk.procFrontRoll();
        return true;
    case daPy_lk_c::daPyProc_MOVE_e:
        lk.procMove();
        return true;
    case daPy_lk_c::daPyProc_WAIT_e:
        lk.procWait();
        return true;
    case daPy_lk_c::daPyProc_FREE_WAIT_e:
        lk.procFreeWait();
        return true;
    case daPy_lk_c::daPyProc_CROUCH_e:
        lk.procCrouch();
        return true;
    case daPy_lk_c::daPyProc_WAIT_TURN_e:
        lk.procWaitTurn();
        return true;
    case daPy_lk_c::daPyProc_ATN_MOVE_e:
        lk.procAtnMove();
        return true;
    case daPy_lk_c::daPyProc_CUT_A_e:
        lk.procCutA();
        return true;
    case daPy_lk_c::daPyProc_CUT_F_e:
        lk.procCutF();
        return true;
    case daPy_lk_c::daPyProc_CUT_R_e:
        lk.procCutR();
        return true;
    case daPy_lk_c::daPyProc_CUT_L_e:
        lk.procCutL();
        return true;
    case daPy_lk_c::daPyProc_CUT_EA_e:
        lk.procCutEA();
        return true;
    case daPy_lk_c::daPyProc_CUT_EB_e:
        lk.procCutEB();
        return true;
    case daPy_lk_c::daPyProc_BACK_JUMP_e:
        lk.procBackJump();
        return true;
    case daPy_lk_c::daPyProc_BACK_JUMP_LAND_e:
        lk.procBackJumpLand();
        return true;
    case daPy_lk_c::daPyProc_SIDE_STEP_e:
        lk.procSideStep();
        return true;
    case daPy_lk_c::daPyProc_SIDE_STEP_LAND_e:
        lk.procSideStepLand();
        return true;
    case daPy_lk_c::daPyProc_JUMP_CUT_e:
        lk.procJumpCut();
        return true;
    case daPy_lk_c::daPyProc_JUMP_CUT_LAND_e:
        lk.procJumpCutLand();
        return true;
    case daPy_lk_c::daPyProc_CUT_TURN_e:
        lk.procCutTurn();
        return true;
    case daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e:
        lk.procCutTurnCharge();
        return true;
    case daPy_lk_c::daPyProc_CUT_TURN_MOVE_e:
        lk.procCutTurnMove();
        return true;
    // CRAWL_MOVE (0x10) is a stub and deliberately absent, so a run reaching it stops.
    case daPy_lk_c::daPyProc_CRAWL_START_e:
        lk.procCrawlStart();
        return true;
    case daPy_lk_c::daPyProc_CRAWL_END_e:
        lk.procCrawlEnd();
        return true;
    default:
        return false;
    }
}

}  // namespace tww_engine
