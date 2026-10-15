// cut_turn_move_replay.h - drive procCutTurnMove across the spin's two steered holds, one run at
// a time.
//
// procCutTurnMove_init takes no argument and has one live call site (procCutTurnCharge,
// d_a_player_sword.inc:1681), so the predecessor column is only a membership check.
//
// What this capture adds:
//   * `blend_move`, m3598 (0x3598): the init sets 1.0, and the body's `if (mNormalSpeed <=
//     0.001f) { onModeFlg(ModeFlg_00000001); m3598 = 0.0f; }` zeroes it on every later frame.
//   * a live B hold: swordButton() is the three-way exit fork, and the console's `btn_hold`
//     drops B on each run's last frame (rows 249 and 321).
//   * pad_lead checked a second way: a B release one frame before the exit.
//
// procCutTurnMove_init's hurricane fork (two save flags and the magic meter: a 47-frame countdown
// to CUT_ROLL, or -1) cannot be settled: the runs are 12 and 10 frames. `hurricane` drives it the
// other way and the gate requires identical columns (test_cut_turn_move.cpp).
//
// Per run because the frames between (CUT_TURN_CHARGE, CUT_TURN, WAIT with the lock, the jump
// family) are not all ported; each run is seeded from its own row.

#ifndef TWW_ENGINE_TESTS_CUT_TURN_MOVE_REPLAY_H
#define TWW_ENGINE_TESTS_CUT_TURN_MOVE_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: The span of the capture this gate reads: the first CUT_TURN_MOVE frame and the last. Two runs,
//: 22 frames (rows 238-249 and 312-321), and nothing between them is claimed.
enum : int { kTurnMoveFirstFrame = 238, kTurnMoveLastFrame = 340, kTurnMoveRuns = 2,
             kTurnMoveFrames = 22 };

struct CutTurnMoveReplayOptions {
    int pad_lead = 1;           //: roll_replay.h's kPadLead

    //: procCutTurnMove_init's hurricane chain answered TRUE (both save flags, full meter). Not a
    //: red control: the capture cannot see this fork, so the columns must be identical.
    bool hurricane = false;

    //: mMaxNormalSpeed seeded with the attention walk cap. Not a red control: the body divides
    //: mNormalSpeed (0.0 on all 22 frames) by it, so no nonzero value reaches a column.
    bool atn_max_speed = false;
    //: ...and mMaxNormalSpeed left at 0: `mNormalSpeed / mMaxNormalSpeed` is 0/0, the rate NaN,
    //: against the console's fc_rate 0.0. A red control.
    bool zero_max_speed = false;

    //: The B hold dropped: the port takes the exit arm on the first body frame. A red control
    //: (cut_turn_replay's `no_b_hold` is a no-change check).
    bool no_b_hold = false;

    //: m3598 zeroed right after the init; moves exactly the two entry frames. A red control.
    bool no_init_blend = false;
};

struct CutTurnMoveFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    int shape_angle_y = 0;      //: shape_angle.y - the capture's `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`
    uint32_t blend_bits = 0;    //: m3598 - the capture's `blend_move`

    //: PORT-INTERNAL, no console column: mDirection (DIR_FORWARD from the init; the body changes
    //: it only inside a stick test the capture never passes) and mModeFlg bit 0 (raised with the
    //: m3598 zeroing).
    int direction = 0;
    int mode_flg_bit0 = 0;
};

//: One steered hold, entry to exit.
struct CutTurnMoveRun {
    int entry = 0;              //: the capture's first CUT_TURN_MOVE frame of this run
    int exit = 0;               //: ...and the first frame after it that is not CUT_TURN_MOVE
    int from_proc = 0;          //: the proc the console was in on the row before the entry
    std::vector<CutTurnMoveFrame> rows;

    //: The proc the port entered, or the proc it named (cut_replay.h). Both runs enter CUT_TURN.
    int exit_proc = -1;
    bool exit_was_named = false;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws_compared = 0;
    int rnd_draws = 0;
    int anm_meta_missing = 0;

    //: procCutTurnMove_init's boundary, read at the init: the exit frame runs procCutTurn_init,
    //: which writes the same emitter recorders and status word.
    int charge_countdown = 0;   //: mProcVar0.m34D0 - the hurricane fork's whole output
    int particle_ids[2] = {-1, -1};   //: m32E4's and m32F0's, or -1 when the charge is not live
    int particle_joint = -1;    //: ...and the joint index getAnmMtx was asked for
    uint32_t player_status0 = 0;
    //: The .bck index in the UNDER_MOVE0 slot after the init: ANM_CUTTURNPWFB (its `fc_end` 10
    //: is shared by three other .bcks).
    int anim_idx = -1;

    //: ...and what the body recorded, safe to read at the end since nothing later writes it.
    int system_se = -1;
    int system_se_calls = 0;
    int se_anime_inits = 0;
    uint32_t player_status1 = 0;
};

/// The frames whose `proc` is CUT_TURN_MOVE and whose predecessor's is not; derived from the
/// capture.
std::vector<int> cut_turn_move_entry_frames(const Json& golden, int first, int last);

/// Whether `from_proc` is a proc the decomp calls procCutTurnMove_init from (there is one).
bool cut_turn_move_entry_is_known(int from_proc);

std::vector<CutTurnMoveRun> run_cut_turn_move_replay(const Json& golden,
                                                     const CutTurnMoveReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CUT_TURN_MOVE_REPLAY_H
