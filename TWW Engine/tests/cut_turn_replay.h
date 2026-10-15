// cut_turn_replay.h - replay procCutTurn across the spin attack's six runs of the sword capture.
//
// CUT_TURN is entered from three different procs, and the predecessor decides procCutTurn_init's
// BOOL: the anim starts at mCutTurn.field_0xC (5.0) or field_0x8 (2.0). The decomp's call sites:
//
//     procCutTurnMove   d_a_player_sword.inc:1808   procCutTurn_init(FALSE)
//     procJumpCutLand   d_a_player_sword.inc:2025   procCutTurn_init(TRUE)
//     procBackJumpLand  d_a_player_main.cpp:7079    procCutTurn_init(TRUE)
//
// The argument is read off the capture's `proc` column on the row before the entry, through
// that table; an unlisted predecessor is a failure, not a default.
//
// Each run is seeded from its own row; the frames between runs are not claimed.
//
//   * The rate-expired arm decrements mProcVar0.m34D0 (field_0x2 = 1) before dispatching, so
//     the turn outlives its clock by one frame.
//   * The clamping frame reads 20.999001 = `mEnd - 0.001`, EMode_NONE's clamp.
//   * `current.angle.y = shape_angle.y`: the two JUMP_CUT_LAND entries arrive with travel 18377
//     against shape 51145, and the console's entry row reads 51145.
//
// Recorded but not console-held: the attack cylinder's radius (cLib_chaseF) and the blur
// ribbons' alpha (J3DFrameCtrl::checkPass), asserted against the decomp's closed form.

#ifndef TWW_ENGINE_TESTS_CUT_TURN_REPLAY_H
#define TWW_ENGINE_TESTS_CUT_TURN_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: The span of the capture this gate reads: six runs, 94 frames.
enum : int { kTurnFirstFrame = 250, kTurnLastFrame = 800, kTurnRuns = 6, kTurnFrames = 94 };

struct CutTurnReplayOptions {
    int pad_lead = 1;           //: see roll_replay.h

    //: The deliberately wrong twins, one at a time.
    //:
    //: The init's BOOL flipped: every run's first anim_frame moves by 3.0.
    bool wrong_init_arg = false;
    //: mProcVar0.m34D0 zeroed after the init: the port leaves on the clamping frame, where the
    //: capture reads 85.
    bool no_exit_countdown = false;
    //: shape_angle.y seeded from the previous row's `travel_angle`; they differ by 32768 before
    //: runs 4 and 5.
    bool wrong_seed_shape_angle = false;
    //: The B hold dropped. Reaches nothing: mProcVar6.m3570 is 0 on every run (m34C4 is not 6), so
    //: `m3570 != 0 && swordButton()` is false. Expected to stay green; not a red control.
    bool no_b_hold = false;
};

struct CutTurnFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    int shape_angle_y = 0;      //: shape_angle.y - the capture's `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`

    //: Port-internal: the attack cylinder's radius, chased toward m35A4 in steps of 18.0 while the
    //: clock is inside [field_0x30, field_0x34).
    uint32_t at_radius_bits = 0;
    //: ...and the blur ribbons' alpha, raised by checkPass(field_0x34) for one frame.
    int ribbon_alpha = 0;
};

//: One spin, entry to exit.
struct CutTurnRun {
    int entry = 0;              //: the capture's first CUT_TURN frame of this run
    int exit = 0;               //: ...and the first frame after it that is not CUT_TURN
    int from_proc = 0;          //: the proc the console was in on the row before the entry
    int init_arg = 0;           //: ...and the argument that predecessor's call site passes
    std::vector<CutTurnFrame> rows;

    //: The proc the port entered, or the proc it named (cut_replay.h).
    int exit_proc = -1;
    bool exit_was_named = false;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws_compared = 0;
    int rnd_draws = 0;
    int anm_meta_missing = 0;

    //: What procCutTurn_init's boundary recorded; the turn writes no speed or angle after entry.
    int sword_anim_idx = -1;
    int blur_pos_idx = -1;
    int sword_cut_se = -1;
    int particle_toe_id = -1;
    int particle_toe_joint = -1;
    int particle_ground_id = -1;
    int at_atp = -1;            //: mAtCyl.mObjAt.mAtp - the game's own word, not a recorder
    uint32_t at_target_bits = 0;    //: m35A4, the radius the chase walks toward
    uint32_t plume_end_bits = 0;    //: m35A0, which the ground fork chose and the body reads back
    uint32_t player_status0 = 0;
    int particle_ends = 0;
    int smoke_removes = 0;
};

/// The frames whose `proc` is CUT_TURN and whose predecessor's is not.
std::vector<int> cut_turn_entry_frames(const Json& golden, int first, int last);

/// The argument procCutTurn_init is called with after `from_proc`, or -1 for a predecessor with
/// no call site.
int cut_turn_init_arg(int from_proc);

std::vector<CutTurnRun> run_cut_turn_replay(const Json& golden, const CutTurnReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CUT_TURN_REPLAY_H
