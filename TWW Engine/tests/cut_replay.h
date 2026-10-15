// cut_replay.h - drive procCutA across the slash capture, one run at a time.
//
// The capture enters CUT_A four times from WAIT, each on a B press the harness cannot translate
// (setStickData gates the B trigger behind dComIfGp_getButtonActionMode(),
// d_a_player_main.cpp:10570, and no column records the mode), so the entries are acted on by name.
//
// Per run because the 61 frames between the slashes are WAIT with the lock held, where procWait
// takes setSpeedAndAngleAtn, an UNREACHED stub. Each run is seeded at its entry row and replayed
// to its exit; the frames between are not claimed.
//
// What this capture adds:
//   * an angle column under a body that writes it: procCutA runs cLib_addCalcAngleS onto
//     shape_angle.y and copies it into current.angle.y (`shape_angle_y`, `travel_angle`).
//   * four arms of cLib_addCalc in six frames (cut_replay.cpp's table).
//   * two exits from one proc: runs 1 and 2 leave to WAIT, runs 3 and 4 to CUT_TURN_CHARGE.
//   * `wrong_speedf_lead`: posMove writes speedF after the proc (execute() 11394 then 11400), so
//     procCutA on frame N reads N-1's value; only the lunge frame tells the alignments apart.

#ifndef TWW_ENGINE_TESTS_CUT_REPLAY_H
#define TWW_ENGINE_TESTS_CUT_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: The span this gate reads: 136 is the first CUT_A frame, 302 the frame after the fourth run.
enum : int { kCutFirstFrame = 136, kCutLastFrame = 302, kCutRuns = 4 };

struct CutReplayOptions {
    int pad_lead = 1;           //: roll_replay.h's kPadLead

    //: The deliberately wrong twins, one at a time.
    //:
    //: speedF fed from the current row instead of the previous one - the harness twin.
    bool wrong_speedf_lead = false;
    //: the B hold dropped: mItemButton's BTN_B never set. On runs 3 and 4 daPyFlg0_UNK4 routes
    //: into the spin charge instead of WAIT, so swordButton() reaches a compared column.
    bool no_b_hold = false;
    //: the slash entered with no sword equipped, which shuts checkNextActionFromButton's sword
    //: arm.
    bool no_sword_equipped = false;
    //: the entry's angle seed from m34E8 (the stick+camera target) instead of shape_angle.y: the
    //: other side of changeCutProc's fork (its CUT_A arm is inside `checkAttentionLock()`).
    bool wrong_init_angle = false;
};

struct CutFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    int shape_angle_y = 0;      //: shape_angle.y - the capture's `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`
};

//: One slash, entry to exit.
struct CutRun {
    int entry = 0;              //: the capture's first CUT_A frame of this run
    int exit = 0;               //: ...and the first frame after it that is not CUT_A
    std::vector<CutFrame> rows;
    //: The exit frame's proc as the port has it: the proc it entered if its dispatch changed
    //: mCurProc, or the proc it named through a proc-init stub if there is no body for it.
    int exit_proc = -1;
    bool exit_was_named = false;  //: ...which of the two

    //: Per run, so a broken claim names its run.
    int unreached_called = 0;
    int precondition_broken = 0;
    //: RNG draws over the compared frames. Must be 0: the generator's seeds are boot-time globals
    //: the capture has no column for.
    int rnd_draws_compared = 0;
    //: ...and including the exit frame: procWait_init draws once for its idle countdown, so the
    //: WAIT exits end on 1 and the spin-charge exits on 0.
    int rnd_draws = 0;
    //: An UNDER animation was loaded whose frameMax nobody has measured. 0 here: ANM_CUTA has an
    //: anm_meta.inc row.
    int anm_meta_missing = 0;
    //: What procCutA_init's boundary recorded, for the two forks with no compared column: the
    //: sword .bck, the blur buffer, the cut type, the wind-cut sound, the player-status bit.
    int sword_anim_idx = -1;
    int blur_pos_idx = -1;
    int cut_at_param_type = -1;
    int sword_cut_se = -1;
    uint32_t player_status0 = 0;
};

/// The frames whose `proc` is CUT_A and whose predecessor's is not; derived, so a capture whose
/// runs move changes the list instead of misaligning the replay.
std::vector<int> cut_entry_frames(const Json& golden, int first, int last);

/// Frames in [first, last] whose `btn_trig` carries B; the gate requires this to be the entry
/// list.
std::vector<int> b_trigger_frames(const Json& golden, int first, int last);

std::vector<CutRun> run_cut_replay(const Json& golden, const CutReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CUT_REPLAY_H
