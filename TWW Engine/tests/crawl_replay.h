// crawl_replay.h - drive a crawl across both captures that hold one, entry to exit, as one
// unbroken run each.
//
// procCrawlStart calls procCrawlEnd_init from its own body on the frame R is released, so a crawl
// is entered once and followed across the proc change with nothing re-seeded. Neither half is
// midair, so nothing is delivered; every fork is the pad.
//
//     setup_finder_demo_live        2 runs   39 CRAWL_START frames + 13 CRAWL_END
//     setup_finder_crawl_wall_live  1 run    18 CRAWL_START frames +  5 CRAWL_END
//
// The columns differ: the demo has `target_angle`, the wall capture has `polled` and `btn_hold`,
// and neither has `lock_r`/`lock_l`. So the replay builds the R latch itself (kRLatchOn) and falls
// back to `csangle` for m34E8, with `m34E8_far` as the control on that fallback.
//
// The console settles:
//   * procCrawlStart_init's setSingleMoveAnime(ANM_LIE, rate 1.0, start 0.0, end 9, morf 3.0),
//     read back by the entry row's fc_rate, fc_end and anim_frame.
//   * procCrawlEnd_init's clamp: the clock stopped at `9 - 0.001f` = 8.99899959564209 and the
//     init writes `field_0xE - 0.001f` = 7.999000072479248 over it, read on the first CRAWL_END row.
//   * procCrawlEnd's exit, checkNextMode(1)'s early return
//     `r29 != 0 && !(mStickDistance > 0.05f) && !spActionButton()`: with R released the crawl-up
//     runs to its clock's end (8 frames, once); with R held it ends on the first frame below
//     field_0x48 = 3.0 (5 frames, twice).
//   * procCrawlStart's stick exit to procCrawlMove_init never firing: no frame is in proc 0x10,
//     with each of its two terms true on some rows.
//
// Position is compared on the wall capture only (Kaisen r0, the disc test_ground_pos.cpp uses).
// The crawl has zero speed on all 75 frames, so all its travel is root motion: posMove's
// m34C2 == 1 arm over ANM_LIE's joint-0 track. The demo capture's room is not settled by any
// column, so its position stays unrecorded; `cap.room` says which.
//
// `push_frames`/`push_total` snapshot current.pos either side of the proc dispatch. Nothing else in
// procCrawlStart or procCrawlEnd writes current.pos (integration and collision run after, in
// `integrate()`), so any movement there is crawlBgCheck's push.

#ifndef TWW_ENGINE_TESTS_CRAWL_REPLAY_H
#define TWW_ENGINE_TESTS_CRAWL_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

/// Which capture. The id indexes the table crawl_capture() returns.
enum CrawlCaptureId {
    kCrawlDemo = 0,
    kCrawlWall = 1,
    kCrawlCaptures = 2,
};

/// Everything that differs between the two captures.
struct CrawlCapture {
    const char* name;
    const char* golden;      //: the file in tests/goldens
    const char* rows_key;    //: NULL if the file is the array; "log" for the wall capture
    //: The room this capture was recorded in, or NULL if no column settles it. With NULL the rig
    //: has an empty dBgS, the collision pass does not run and position is not recorded.
    const char* room;
    int runs;                //: what the capture's own proc column holds
    int start_frames;        //: ...total rows in proc 0x0F
    int end_frames;          //: ...and in proc 0x12
    bool has_target_angle;   //: whether `target_angle` is a column, or csangle stands in
};

const CrawlCapture& crawl_capture(int id);

/// The rows of a capture, whichever shape the file has.
const Json& crawl_rows(const Json& doc, const CrawlCapture& cap);

struct CrawlReplayOptions {
    int pad_lead = 1;           //: as roll_replay.h

    //: Deliberately wrong twins, one at a time.
    //:
    //: R read as a bare `trigR >= 1.0` instead of the game's latch (m_Do_controller_pad.cpp:122-131:
    //: on above g_HIO.mTriggerThreshLo = 0.9f, off below mTriggerThreshHi = 0.6f). Demo run 1
    //: releases through 0.95, so the naive rule ends that crawl one frame early.
    bool naive_r_threshold = false;
    //: R held for the whole run: procCrawlStart's `!spActionButton()` exit never fires.
    bool r_held_forever = false;
    //: R held from the frame the port entered procCrawlEnd: demo run 1's eight crawl-up frames
    //: become five. The control on checkNextMode(1)'s early return.
    bool r_held_through_crawl_up = false;
    //: procCrawlEnd_init's `param_1 == 0` setFrame clamp undone, leaving field_0x44 = 0.0: the
    //: crawl-up begins at 0.0 instead of 7.999 and ends on its first body frame.
    bool no_crawl_end_clamp = false;
    //: ANM_LIE forced to EMode_LOOP instead of the .bck's EMode_NONE: the crawl-up clock wraps,
    //: `getRate() > -0.01f` never fires, and that run never leaves.
    bool loop_crawl_anim = false;
    //: Stick at full deflection every frame: procCrawlStart's stick exit fires when its clock stops
    //: and the replay stops on procCrawlMove, which has no body here.
    bool stick_held = false;
    //: `dComIfGp_checkCameraAttentionStatus` answered true, as on the console (d_camera.cpp:4264
    //: raises 0x80 from daPyStts0_CRAWL_e). Not a red control: every compared column must match
    //: both ways, since setDoStatusCrawl's camera arm writes only mBodyAngle and two status words.
    //: It moves a_status and body_angle_calls.
    bool camera_attn = false;
    //: m34E8 driven 0x8000 away from the facing, showing the `csangle` stand-in cannot reach a
    //: compared column: both m34E8 arms of checkNextMode need `mStickDistance > 0.05f`, and the
    //: stick is centred on every frame that dispatches.
    bool m34E8_far = false;
    //: Attention lock held: checkNextMode's `r24` takes the targeting branch on the exit frame.
    //: Neither capture has a `lock_l` column.
    bool attention_lock = false;
    //: execute():11400 removed - posMove not run, so the position holds the seed row.
    bool no_pos_move = false;
    //: execute():11406 removed - dBgS_Acch::CrrPos not run, so nothing pushes Link out of the
    //: z = 800 wall.
    bool no_crr_pos = false;
    //: execute():11544 removed - setWorldMatrix not run, so getBaseTRMtx() answers an unwritten
    //: matrix, crawlBgCheck casts both probes from the origin, getCrawlMoveVec answers false and
    //: the crawl's wall push disappears.
    bool no_world_matrix = false;
};

struct CrawlFrame {
    int frame = 0;
    int proc = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    uint32_t nspeed_bits = 0;   //: mNormalSpeed - `potential_speed`
    uint32_t speedf_bits = 0;   //: speedF - `true_speed`
    int shape_angle_y = 0;      //: shape_angle.y - `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`

    //: MOVE1's clock, recorded not compared: never seeded, so it should stay at 0. animeUpdate
    //: skips MOVE1 while mAnmRatioUnder[1] is NULL; the console's move1_frame is frozen too.
    uint32_t m1frame_bits = 0;

    //: Port-internal, no console column. m35E4 is the crawl's phase (scales the wall probe);
    //: a_status is what setDoStatusCrawl's camera arm posts.
    uint32_t phase_bits = 0;
    int a_status = 0;
    //: ...and the R latch this replay built.
    bool r_held = false;

    //: Position, on a capture whose room is settled; `pos_recorded` is false otherwise.
    bool pos_recorded = false;
    uint32_t pos_x_bits = 0;
    uint32_t pos_y_bits = 0;
    uint32_t pos_z_bits = 0;
    int ground_poly = -1;       //: the triangle the ground stage landed on
    bool ground_hit = false;
    bool wall_hit = false;
    bool line_hit = false;
    //: posMove's m34C2 arm this frame. The crawl bodies write 1 and the seed frame writes nothing,
    //: so a run reads 0 then 1; any other value is an unreachable arm.
    int m34c2 = -1;
};

//: One crawl: procCrawlStart's entry through procCrawlEnd's exit, with no seed in between.
struct CrawlRun {
    int entry = 0;              //: the capture's first CRAWL_START frame of this run
    int crawl_up = -1;          //: ...its first CRAWL_END frame, per the port
    int console_crawl_up = -1;  //: ...and per the capture's own proc column
    int exit = 0;               //: the first frame after the run that is neither crawl proc
    int from_proc = 0;          //: the proc the console was in on the row before the entry
    std::vector<CrawlFrame> rows;

    //: As cut_replay: the proc the port entered, or the proc it named.
    int exit_proc = -1;
    bool exit_was_named = false;
    int console_exit_proc = -1;

    //: The run stopped because the port has no body for the proc it reached. -1 if it did not.
    int stopped_on_proc = -1;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws = 0;
    int rnd_draws_compared = 0;
    int anm_meta_missing = 0;

    //: What the crawl's own boundary recorded.
    int body_angle_calls = 0;       //: setBodyAngleToCamera - the camera arm
    int subject_end_calls = 0;
    int subject_mode_calls = 0;
    //: Frames crawlBgCheck pushed current.pos, and the total push.
    int push_frames = 0;
    float push_total = 0.0f;
    int crawl_move_init_calls = 0;  //: the stick exit
    int anm_transform_calls = 0;    //: procCrawlEnd_init's root-motion seed; once per crawl-up
    int base_tr_mtx_calls = 0;      //: crawlBgCheck's two matrix fetches per body frame
    int world_matrix_calls = 0;     //: setWorldMatrix, once per frame of the run
    int world_inverse_frames = 0;   //: ...of which left m37B4 a real transform, not zeros
    int ship_actor_calls = 0;       //: ...and the ship the arm it opens does not have
    uint32_t player_status0 = 0;    //: procCrawlStart_init's daPyStts0_CRAWL_e, and SUBJECT

    //: What the collision pass and posMove's boundary recorded over the whole run.
    int wall_hit_frames = 0;
    int line_check_frames = 0;
    int cc_move_asks = 0;
    //: Frames posMove ran on: the emitted rows plus the entry frame, which has no row.
    int integrated_frames = 0;
    //: ...of which took checkNoCollisionCorret's true fork, and how many were the crawl-up
    //: (daPyProc_CRAWL_END_e is one of the four procs it names).
    int no_collision_corret_frames = 0;
    int crawl_end_integrated = 0;
    //: The old-frame joint-0 translate after the run. Arms 11, 10, 2/6 and 4 all write it, so
    //: all-zero proves none of them ran.
    uint32_t old_frame_trans_bits[3] = {0, 0, 0};

    //: The anim frame procCrawlEnd_init left, read at the init; a one-frame crawl-up's exit would
    //: otherwise overwrite it.
    uint32_t clamp_bits = 0;
    bool clamped = false;
};

/// The frames whose `proc` is CRAWL_START and whose predecessor's is not. Derived, as
/// cut_entry_frames is.
std::vector<int> crawl_entry_frames(const Json& rows);

std::vector<CrawlRun> run_crawl_replay(const Json& rows, const CrawlCapture& cap,
                                       const CrawlReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CRAWL_REPLAY_H
