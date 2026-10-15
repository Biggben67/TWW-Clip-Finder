// cut_turn_charge_replay.h - drive procCutTurnCharge across the capture's two spin wind-ups.
//
// The body has no arithmetic, so the claim is the run's length: ten rows of proc 88 then one of
// 89, twice. That is the quotient of the init's anim arguments:
//
//     (field_0x4 - field_0x10) / field_0xC  =  (9 - 1) / 0.8  =  10
//
// ANM_CUTTURNP is EMode_NONE, so the clock clamps at `end - 0.001` and the rate drops to 0 on the
// frame after the last full step, where `getRate() < 0.01f` fires. The morf argument has no column.
//
// Not settled by the capture:
//   * `mNormalSpeed = 0.0f` and `current.angle.y = shape_angle.y` write values the seed row already
//     holds, so they are copied and unobserved.
//   * Whether the clock took `end` or `frameMax`: both are 9. `anim_idx` pins the .bck asked for.
//   * Pad lead: the pad is constant across both runs (btn_hold 640 on rows 227-238 and 301-312).
//
// Each run is seeded from its own row.

#ifndef TWW_ENGINE_TESTS_CUT_TURN_CHARGE_REPLAY_H
#define TWW_ENGINE_TESTS_CUT_TURN_CHARGE_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: The span read: two runs, 20 frames (rows 228-237 and 302-311).
enum : int { kChargeFirstFrame = 228, kChargeLastFrame = 340, kChargeRuns = 2,
             kChargeFrames = 20 };

struct CutTurnChargeReplayOptions {
    int pad_lead = 1;           //: see roll_replay.h

    //: The B hold dropped. `!swordButton()` is the body's first test, so nine of each run's ten
    //: rows become the wrong proc. Red.
    bool no_b_hold = false;

    //: daPy_dmEcallBack_c::checkCurse() answers true - the other half of the same `||`. Red.
    bool cursed = false;

    //: The proc run before animeUpdate, so the exit test reads the previous frame's rate and each
    //: run becomes eleven frames. Red.
    bool proc_before_anim = false;

    //: The anim clock started at 0.0 instead of mCutTurnR.field_0x10 (1.0), the init's third
    //: argument. Moves anim_frame on every row and makes the run twelve frames. Red.
    bool start_at_zero = false;

    //: The rate forced to 1.0 instead of field_0xC (0.8), the init's second argument. Moves
    //: fc_rate on every row and makes the run nine frames. Red.
    bool rate_one = false;
};

struct CutTurnChargeFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    int shape_angle_y = 0;      //: shape_angle.y - the capture's `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`
    uint32_t blend_bits = 0;    //: m3598 - the capture's `blend_move`
};

//: One wind-up, entry to exit.
struct CutTurnChargeRun {
    int entry = 0;              //: the capture's first CUT_TURN_CHARGE frame of this run
    int exit = 0;               //: ...and the first frame after it that is not CUT_TURN_CHARGE
    int from_proc = 0;          //: the proc the console was in on the row before the entry
    std::vector<CutTurnChargeFrame> rows;

    //: The proc the port entered, or the one it named. Both runs enter CUT_TURN_MOVE.
    int exit_proc = -1;
    bool exit_was_named = false;

    //: The port's own exit frame, or -1 if it never left inside the span. The length check needs
    //: this beside the capture's `exit`, or it could not go red on a port regression.
    int port_exit_frame = -1;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws_compared = 0;
    int rnd_draws = 0;
    int anm_meta_missing = 0;
    int next_init_calls = 0;

    //: Read at the init: the exit frame's procCutTurnMove_init overwrites the same anim slot and
    //: status word.
    int anim_idx = -1;          //: the .bck sitting in UNDER_MOVE0 after the init
    uint32_t player_status0 = 0;
};

/// The frames whose `proc` is CUT_TURN_CHARGE and whose predecessor's is not.
std::vector<int> cut_turn_charge_entry_frames(const Json& golden, int first, int last);

/// Whether `from_proc` is a proc this slice has a body for. The decomp gives no predecessor list:
/// both of procCutTurnCharge_init's call sites are arms of checkNextActionFromButton, reachable
/// from any proc that ends in checkNextMode.
bool cut_turn_charge_entry_is_known(int from_proc);

std::vector<CutTurnChargeRun> run_cut_turn_charge_replay(const Json& golden,
                                                         const CutTurnChargeReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CUT_TURN_CHARGE_REPLAY_H
