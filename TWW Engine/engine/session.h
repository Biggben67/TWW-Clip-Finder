// session.h - the library's entry point: a player, a world, and one frame at a time.
//
// The engine has no file format: `Session` takes a `RoomDzb` (engine/room.h) by const reference,
// or no room at all. `run_proc` is the only switch on `mCurProc`; a newly ported proc goes there.

#ifndef TWW_ENGINE_SESSION_H
#define TWW_ENGINE_SESSION_H

#include <cstdint>
#include <memory>
#include <vector>

#include "d/actor/d_a_player_main.h"
#include "d/d_bg_s.h"
#include "d/d_camera.h"
#include "engine/link_model.h"
#include "engine/room.h"

namespace tww_engine {

/// One frame's input: the outputs of `daPy_lk_c::setStickData`, not controller bytes. The pad
/// decode itself (`mDoCPd_*`) is not ported; a caller with raw controller bytes decodes them.
struct Pad {
    /// m34DC. Raw world-space stick angle (s16), before the deadzone snap.
    s16 stick_angle_raw = 0;
    /// m34E8. The angle the procs steer toward. The game derives it camera-relative; here the
    /// caller supplies it, camera or not (turn a bearing against `Session::cameraYaw()`).
    s16 target_angle = 0;
    /// mStickDistance. 0.0 at centre, 1.0 at the gate.
    f32 stick_distance = 0.0f;
    /// mItemButton - the game's latches (cPadInfo +0x37 / +0x35), not the digital button word.
    /// `daPy_lk_c::BTN_R` and friends.
    u8 item_button = 0;
    /// mItemTrigger - the same latches, rising edge only. Set only together with `item_button`.
    u8 item_trigger = 0;
    /// Whether L-targeting is held (dAttention_c is a boundary stub).
    BOOL attention_lock = FALSE;
};

/// Initial conditions. Every field defaults to what `reset_boundary()` leaves.
struct Init {
    /// `current.pos`. `old.pos` is set to match, so the first frame starts from a standstill.
    cXyz pos{0.0f, 0.0f, 0.0f};
    /// `shape_angle.y` - which way Link faces.
    s16 shape_angle_y = 0;
    /// `current.angle.y` - which way he travels. Set both for "standing still facing X".
    s16 travel_angle_y = 0;
    /// mNormalSpeed, the potential speed the move procs accelerate and decelerate.
    f32 normal_speed = 0.0f;
    /// speedF, the true speed posMove integrates. Independent of `normal_speed`.
    f32 speed_f = 0.0f;
    /// mEquipItem. The sword arm of `checkNextActionFromButton` needs `daPyItem_SWORD_e`.
    /// `u16` because `daPyItem_NONE_e` is 0x100 (d_a_player_main.h:122); a `u8` truncates it.
    u16 equip_item = daPyItem_NONE_e;
    /// `stub_select_equip[0]` - the equip slot, in the field's own type.
    int select_equip_0 = dItemNo_NONE_e;
    /// The pad delivered before the first `step`, so `frame_top` has a previous m34DC to carry.
    Pad pad;

    /// The proc Link starts in. Its `_init` runs at construction, because it is what loads the
    /// animation `animeUpdate()` dereferences unconditionally (d_a_player_main.cpp:2439). Only
    /// argument-free inits are accepted - see `run_proc_init`; any other proc aborts.
    int proc = daPy_lk_c::daPyProc_WAIT_e;
};

/// What a run may skip. Each collision arm is a `dBgS_Acch` flag the game already has, not an
/// edit to a copied body. Defaults reproduce the full engine bit for bit; `camera` is the only
/// arm off by default. Largest saving first: `pose_skeleton`, `Ground::Supplied`, `wall_correct`,
/// `roof_chk`.
struct RunOptions {
    /// Where the floor comes from.
    enum class Ground {
        /// `dBgS_Acch::GroundCheck`'s own descent through the room's octree.
        Descent,
        /// The world is a floor at `floor_y` and nothing else (`flat_floor_dzb` in room.h),
        /// still run through the decomp's descent. No walls, no ceiling. Aborts if a `RoomDzb`
        /// or shared room is also given.
        Supplied,
        /// `dBgS_Acch`'s GRND_NONE (d_bg_s_acch.h:113): no ground check, so Link falls every
        /// frame. Not a cheap floor - that is `Supplied`.
        None,
    };
    Ground ground = Ground::Descent;

    /// The floor height `Ground::Supplied` builds. Read by no other arm.
    f32 floor_y = 0.0f;

    /// The wall pass. false raises WALL_NONE (d_bg_s_acch.h:114), tested by CrrPos at
    /// d_bg_s_acch.cpp:267. Most likely arm to change an answer: off, nothing bonks.
    bool wall_correct = true;

    /// The ceiling. false raises ROOF_NONE (d_bg_s_acch.h:115), tested at d_bg_s_acch.cpp:275;
    /// `m_roof_height` keeps its value and `field_0xC4` stays G_CM3D_F_INF.
    bool roof_chk = true;

    /// The J3D joint walk - `setWorldMatrix()` and the 42-joint pose (d_a_player_main.cpp:11544,
    /// :11591). Not a game flag. Off, the joint matrices stay zero and `m359C` (the planted-toe
    /// delta) becomes the origin's displacement, so `current.pos` on walking frames is wrong.
    bool pose_skeleton = true;

    /// The foot IK - footBgCheck, setLegAngle, setWaistAngle and the three joint callbacks
    /// (d_a_player_main.cpp:11545-11548, :12134-12141). Not a game flag. Exact to turn off on
    /// level ground; on a slope it moves `current.pos` via posMoveFromFootPos. Ignored without
    /// `pose_skeleton`.
    bool foot_ik = true;

    /// The camera - `dCamera_c::Run`, once at the end of every frame. Enables
    /// `Session::cameraYaw()`. Does not affect the player.
    bool camera = false;
    /// Initial yaw, in `dCam_getControledAngleY` units. Read only while `camera` is true.
    s16 camera_yaw = 0;
    /// Camera type, an index into `dCamera_c::types` (7 is `Field`). A room with no camera id
    /// uses the stage's type, e.g. Kaisen's 57, `Room`. Read only while `camera` is true.
    int camera_type = 7;
    /// Initial eye-to-centre distance, or 0 for the style's parameter 10. The follow camera
    /// keeps whatever radius it starts at while inside its two limits.
    f32 camera_radius = 0.0f;
};

/// Why a frame stopped.
enum class StepResult {
    /// The whole frame ran.
    Ok,
    /// `run_proc` has no body for `state().mCurProc`; nothing after the dispatch ran.
    NoProcBody,
    /// An UNDER animation has no length (`anm_meta.inc` has no row for its .bck), so its clock
    /// would never leave `J3DFrameCtrl::update`'s wrap loop. `state().anm_meta_missing_idx`
    /// names the .bck. Nothing after the load ran.
    NoAnimation,
};

uint32_t f32_bits(f32 f);

/// One boundary definition a run reached, and how often (see `boundary/game_boundary.h`).
/// `grade` is "STUB" (arithmetic not ported) or "PARTIAL" (real for some inputs); several
/// PARTIAL bodies run on every clean frame, so a row is not by itself an alarm. Both strings
/// have static storage.
struct BoundaryHit {
    const char* name;
    const char* grade;
    int hits;
};

/// A player, a world, and the stages of one frame.
///
/// Not copyable in practice: `daPy_lk_c` holds at least twelve pointers into this object (the six
/// `mAcch.pm_*`, `m_HIO`, `mpCLModel`, `m_old_fdata`, both `m_pbCalc`, and their `mOldFrame`),
/// and the constructor registers `&lk` in a thread-local global, so a Session must never be
/// moved or built as a temporary. To branch, construct another from the same `Init` and re-run.
///
/// `lk{}` is value-initialisation, not memset: J3DFrameCtrl has a virtual destructor
/// (J3DAnimation.h:844), and zeroing its vtable pointer crashes g++ builds on scope exit.
struct Session {
    daPy_lk_c lk{};
    daPy_HIO_c hio;
    /// The real dBgS (d/d_bg_s.h) with no collision registered: the room-less world.
    dBgS bgs;

    /// An owned room, or null.
    std::unique_ptr<Room> room;
    /// The world this session runs in: `room`, a lent one, or null. Every collision query uses it.
    Room* world = nullptr;

    /// Fixed at construction; the collision arms are acch flags the constructor raises.
    RunOptions opts;
    /// Position after pos_move, before CrrPos; observation only, no physics change.
    cXyz last_raw_position{0.0f, 0.0f, 0.0f};

    /// No room.
    Session();
    /// With a room. The `RoomDzb` is copied, so the caller's may go out of scope.
    explicit Session(const RoomDzb& dzb);
    /// Either: null `dzb` is the room-less shape.
    explicit Session(const RoomDzb* dzb, const RunOptions& options = RunOptions());

    /// The main entry point: initial conditions and a world (null `dzb` for none). The `Init`'s
    /// pad is delivered, not stepped.
    Session(const Init& init, const RoomDzb* dzb, const RunOptions& options = RunOptions());

    /// The same, in a room built once and lent. The room must outlive the session, and one room
    /// serves one thread at a time.
    Session(const Init& init, Room& shared, const RunOptions& options = RunOptions());
    explicit Session(Room& shared, const RunOptions& options = RunOptions());

    /// Link's skeleton. Outside the player because the game's `mpCLModel` is a pointer to
    /// heap-allocated model data (~7 KB here). Null until `attachSkeleton()`; until then
    /// `mpCLModel` points at the player's own `port_cl_model`, whose `getAnmMtx` answers null.
    std::unique_ptr<LinkModel> skeleton;

    /// A freshly constructed old-frame object and its two arrays (d_a_player_main.cpp:12019-12020),
    /// the only way to reach `getOldFrameFlg() == false`. Allocated only by
    /// `attachSkeleton(false)`; otherwise the player's own `port_old_fdata` is used.
    struct FreshOldFrame {
        J3DTransformInfo info[0x2A];
        Quaternion quat[0x2A];
        mDoExt_MtxCalcOldFrame old_frame{info, quat};
    };
    std::unique_ptr<FreshOldFrame> fresh_old;

    /// The camera, or null until seated. Held over zeroed storage because `dCamera_c`'s
    /// user-provided constructor leaves fields `Run` reads uninitialised.
    struct CameraHome;
    std::unique_ptr<CameraHome> camera;

    // ------------------------------------------------------------------ the public frame API

    /// One frame, in `daPy_lk_c::execute()`'s order (d_a_player_main.cpp line numbers):
    ///
    ///   actor_old_set      f_op_actor.cpp:196, one call further out than execute()
    ///   frame_top          11280-11295, before the inputs: it carries m34DC into m34EA
    ///   <the pad>          setStickData's outputs
    ///   stick_accumulate   10651-10667, setStickData's tail
    ///   animeUpdate        11346
    ///   cut_window         11382-11386
    ///   run_proc           11394, `(this->*mCurProcFunc)()`
    ///   pos_move           11400-11401
    ///   crr_pos            11405-11406, only with a room
    ///   poseSkeleton       11544 and 11591, unless `opts.pose_skeleton` is false
    ///   setAttentionPos    11640
    ///   the camera         dCamera_c::Run, only when seated
    ///
    /// The pose runs after the proc, so `posMoveFromFootPos` on frame N reads frame N-1's joints.
    /// The camera runs after the actor, as the camera manager does.
    StepResult step(const Pad& pad);

    /// The whole player.
    const daPy_lk_c& state() const { return lk; }

    /// Seat (or re-seat) a camera at `yaw`, replacing any existing one. `RunOptions::camera` is
    /// the usual way; this is for placing it mid-run.
    ///
    /// `yaw` is `dCam_getControledAngleY`'s value (`csangle`); the globe is seeded at
    /// `yaw + 0x8000` because `mAngleY = mDirection.U().Inv()` (d_camera.cpp:315). Mode 12, style
    /// `types[type].mStyles[12]`, radius and fovy from that style unless `radius` > 0. Entry
    /// counters (`m100`, `m101`, `m102`, `m110`) are set to 1: a camera that has already arrived.
    void seatCamera(s16 yaw, int type = 7, f32 radius = 0.0f);

    bool hasCamera() const { return camera != NULL; }

    /// Sessions built by this process, all threads (relaxed atomic). Lets a caller check that a
    /// code path never constructs one, by reading it before and after.
    static unsigned long long built();

    /// Raw camera state, each field named after its `d_camera.cpp` source.
    struct CameraFacts {
        int mode = -1;
        int next_mode = -1;
        int style = -1;
        /// `m100` - the entry is finished. `m108` - frames it has been running.
        int entry_done = 0;
        int entry_frame = 0;
        /// `m144` - the manual camera has been given up. `m184` - the C-stick-up latch.
        int manual_given_up = 0;
        int cstick_latch = 0;
        int yaw = 0;
        /// `mDirection.R()`, `mCamSetup.m098` and the C-stick value: `nextMode` case 12 gives up
        /// the manual camera when the radius is inside that gate with the C-stick centred.
        float radius = 0.0f;
        float gate_radius = 0.0f;
        float cstick = 0.0f;
        /// `mViewCache.mEye` and `mViewCache.mCenter`. A NaN in either crashes `cM_atan2s`,
        /// whose table index is unguarded.
        float eye[3] = {0.0f, 0.0f, 0.0f};
        float center[3] = {0.0f, 0.0f, 0.0f};
        /// The camera's own ground check (`mBG.m5C`) as `checkGroundInfo` left it:
        /// `mRoomMapToolCameraIdx` (0xFF none, 0x1FF player too far above the floor),
        /// `mRoomNo` (-1 when the id indexes the stage's list) and `m350`, the cam-move BG.
        int room_cam_idx = 0xFF;
        int room_no = -1;
        int cam_move_bg = 0;
    };

    /// Aborts with no camera seated.
    CameraFacts cameraFacts() const;

    /// Run only the camera, `frames` times, leaving the player untouched. Returns frames run.
    /// Aborts with no camera. A mode change here reaches `followCamera`'s `m100 == 0` entry arm,
    /// which no test covers.
    int runCamera(int frames);

    /// `dCam_getControledAngleY` as of this frame - what a caller's stick bearing is measured
    /// against. Aborts with no camera seated, since 0 is a valid yaw.
    s16 cameraYaw() const;

    /// Typed import of a console camera snapshot; console/native layouts differ.
    dCamera_c& cameraBody();

    /// Enter the first-person view without stepping the player: raises `daPyStts0_SUBJECT_e`,
    /// runs `dCamera_c::Run` until the entry ends (`m100`) or `frames` run, then clears the
    /// status. Returns frames run. The entry lands exactly on the facing; leaving the view is not
    /// modelled (on console the camera keeps moving ~20 frames, by up to 54 units). Aborts with
    /// no camera seated.
    int runFirstPersonCamera(int frames);

    /// Total hits across every STUB and PARTIAL boundary definition since the last reset.
    int boundary_hits() const;

    /// What this run reached, by name, in first-reached order. SCOPE-graded stubs are not
    /// reported, so an empty report means nothing graded as a bug was reached, not that nothing
    /// unported was. `state().next_init` / `next_init_calls` record the dispatch arms that land
    /// in SCOPE; a caller driving arbitrary input reads both.
    std::vector<BoundaryHit> boundary_report() const;

    /// True if the report was clipped (the table holds 256 names; see `boundary_dropped()`).
    bool boundary_report_truncated() const;

    /// Clear the boundary table. It is per thread, not per Session: two sessions on one thread
    /// share it, and a run on a worker must be reported from that worker.
    static void boundary_reset();

    // ------------------------------------------------------------------ the frame's own stages
    //
    // Public so replays can drive and gate each stage separately.

    /// Point the player at a real skeleton, with `m_pbCalc[PART_UNDER_e]` as every joint's mtx
    /// calc (d_a_player_main.cpp:12023), and install the foot-IK callbacks when enabled.
    ///
    /// `alreadyCalculated` is `mDoExt_MtxCalcOldFrame`'s flag. true (as `reset_boundary` assumes)
    /// means the skeleton has been posed before, so posMoveFromFootPos takes its foot-term arm;
    /// false swaps in `fresh_old` for both `m_old_fdata` and the blend tables' `mOldFrame`.
    void attachSkeleton(bool alreadyCalculated = true);

    /// `setSingleMoveAnime`'s blend shape: slot 0 `anm` at ratio 1.0, slot 1 empty
    /// (d_a_player_main.cpp:2340-2342).
    void setSingleAnim(J3DAnmTransform* anm);

    /// `setMoveAnime`'s: slot 0 at `1.0f - ratio`, slot 1 at `ratio`, the MOVE1 weight
    /// (d_a_player_main.cpp:2278-2279, 2291-2292).
    void setBlendAnim(J3DAnmTransform* move0, J3DAnmTransform* move1, f32 ratio);

    /// execute()'s tail (d_a_player_main.cpp:11544, :11591): `setWorldMatrix()` (inverse kept in
    /// `m37B4`), the foot IK if enabled, then the 42-joint pose.
    void poseSkeleton();

    /// execute():11405-11406 - `mAcch.ClrGroundHit(); mAcch.CrrPos(*dComIfG_Bgsp());`. Aborts
    /// without a room. Runs after pos_move.
    Room::FrameResult crr_pos();

    /// Point `dComIfG_player` and `dComIfG_Bgsp` (thread_local, boundary/stubs.cpp) at this
    /// session. Only the bound session on a thread can be stepped; `step()` calls this itself,
    /// so only a caller driving stages by hand across sessions needs it.
    void bind();

    /// The constructor every other one delegates to: `dzb` builds a room, `shared` lends one,
    /// both null is room-less.
    Session(const RoomDzb* dzb, Room* shared, const RunOptions& options);
    /// Writes an `Init` after the world is up.
    void seed(const Init& init);

    /// Clears the two globals `bind()` set, so they never point into a dead Session.
    ~Session();

};

/// The words execute() writes at the top of every frame, before the proc
/// (d_a_player_main.cpp:11280, 11282, 11284-11285, 11295). `m34EA = m34DC` and
/// `m34DE = shape_angle.y` are copies of frame N-1's values, so this runs before the pad is fed.
void frame_top(daPy_lk_c& lk);

/// setStickData's tail - the stick-rotation accumulator m3578 (d_a_player_main.cpp:10651-10667).
/// Computed here because captures never record m3578; it decides procBackJumpLand's quickspin
/// arm (`abs(m3578) > 0xF800`). Runs after frame_top and after this frame's m34DC is delivered.
void stick_accumulate(daPy_lk_c& lk);

/// The combo window (d_a_player_main.cpp:11382-11386): counts m3522 down and resets the chain
/// count m34C4 when it expires. The `m34C4 += 2` on a hit (11377-11381) is not carried: there is
/// no target.
void cut_window(daPy_lk_c& lk);

/// execute()'s two lines after the dispatch: posMove() and `mOldSpeed = speed`. After run_proc.
void pos_move(daPy_lk_c& lk);

/// Run the proc's `_init`, for the argument-free inits only. The rest take an argument the game
/// computes at the transition, so those procs are reached by stepping, not started in. Returns
/// false for any other proc.
bool run_proc_init(daPy_lk_c& lk, int proc);

/// The proc dispatcher, `(this->*mCurProcFunc)()`. Returns false when there is no body for the
/// current proc. The only switch on `mCurProc`: port a proc, add it here.
bool run_proc(daPy_lk_c& lk);

/// f_op_actor.cpp:196 - `actor->old = actor->current`, which the actor manager runs just before
/// execute(). `old.pos -> current.pos` is the line check's segment, so it must run first.
void actor_old_set(daPy_lk_c& lk);
/// execute()'s grounded tail: `m3580`, `m34E2` and setStepsOffset. After the collision pass,
/// only with a room.
void ground_tail(daPy_lk_c& lk, const RunOptions& opts);
/// The ground code and slope alone, which the seed also writes.
void ground_under(daPy_lk_c& lk);

}  // namespace tww_engine

#endif  // TWW_ENGINE_SESSION_H
