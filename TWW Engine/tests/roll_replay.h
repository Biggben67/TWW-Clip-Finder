// roll_replay.h - drive the ported procs across a console capture and hand back the rows.
//
// Frame numbers are the capture's. The deliberately wrong twins live beside the replay so they
// move with the code they guard.

#ifndef TWW_ENGINE_TESTS_ROLL_REPLAY_H
#define TWW_ENGINE_TESTS_ROLL_REPLAY_H

#include <cstdint>
#include <string>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: The capture's frame numbers. 42 is the last pre-roll frame (the state procFrontRoll_init
//: reads), 43 the first roll frame, 58 the last; at 59 the console is in MOVE. 119 is the last.
enum : int { kSeedFrame = 42, kFirstFrame = 43, kLastRollFrame = 58, kLastFrame = 119 };

//: How many frames the capture's pad columns lead its player-state columns by. The hook samples
//: cPadInfo after the pad is refreshed for the next frame and the player struct after execute()
//: for this one, so row N's input shows in the player state at N+1 (demo capture: frame 110's
//: `cpad_val` is 1.0 while its `msd` 0.18519 is the decode of frame 109's pad). Player-state
//: columns (`msd`, `true_speed`, `target_angle`, `stick_angle_raw`) are not shifted. An option,
//: so the wrong value stays runnable as a red control.
enum : int { kPadLead = 1 };

struct RollReplayOptions {
    int pad_lead = kPadLead;
    int through = kLastFrame;

    //: The deliberately wrong twins, one at a time.
    bool wrong_anim = false;   //: the anim clock accumulated in double rather than f32
    bool wrong_decel = false;  //: cLib_addCalc's minStep arm written as "snap to the target"
    bool wrong_move1 = false;  //: MOVE1 accumulated rather than re-slaved to MOVE0's phase
    bool wrong_blend = false;  //: blend_move read as the MOVE1 blend ratio instead of m3598
    bool wrong_order = false;  //: the proc run before the anim clocks rather than after

    //: The collision frame's twins, each removing one statement of execute():11400-11406.
    bool no_pos_move = false;  //: posMove skipped - the position holds the seed row
    bool no_crr_pos = false;   //: the collision pass skipped - nothing clamps him to the floor
    //: `old = current` (f_op_actor.cpp:196) never run: old.pos holds the seed frame's position
    //: and the line check's segment grows without bound.
    bool stale_old_pos = false;

    //: The skeleton pass skipped (execute():11544 and :11591), so `mpCLModel`'s 42 joint
    //: matrices stay zero. Not a zero answer: concatenating `m37B4` onto a zero matrix leaves its
    //: translation, so `mFootData` becomes that column four times and `m359C` the distance
    //: Link's origin moved - plausible on a walk.
    bool no_pose = false;

    //: m359C before the first frame, the one foot-term input a mid-run replay cannot take from
    //: the capture: posMoveFromFootPos smooths against last frame's (`f31_2*0.3 + 0.7*m359C`).
    //: 0.0f is a fresh player's; an option so two seeds can be compared (carried state vs
    //: arithmetic).
    float foot_seed = 0.0f;
};

struct ReplayFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the capture's `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    uint32_t m1frame_bits = 0;  //: MOVE1's frame - `move1_frame`
    uint32_t m1rate_bits = 0;   //: `move1_rate`
    int m1end = 0;              //: `move1_end`
    //: The foot term. `foot_delta_bits` is m359C, the capture's `foot_delta_prev`, which
    //: posMoveFromFootPos writes last, so row N is frame N's value. `plant` is m34BC, which has
    //: no column: printed, not compared.
    uint32_t foot_delta_bits = 0;
    int plant = -1;
    uint32_t blend_bits = 0;    //: m3598 - `blend_move`
    bool crashed = false;       //: the port ran procFrontRollCrash_init; the console never did
    int anm_meta_missing = 0;   //: an UNDER anim was loaded whose frameMax has never been measured

    //: The position after the integration and the collision pass, execute()'s order.
    uint32_t pos_x_bits = 0;
    uint32_t pos_y_bits = 0;
    uint32_t pos_z_bits = 0;
    //: `ground_poly` is the acch's cBgS_PolyInfo, the capture's `floor_tri`: a second compared
    //: column, so a right height on the wrong triangle fails.
    int ground_poly = 0xFFFF;
    bool ground_hit = false;
    bool wall_hit = false;
    bool line_hit = false;
};

struct ReplayResult {
    std::vector<ReplayFrame> rows;
    //: The proc the replay stopped on for lack of a body, or -1 if it ran to `through`.
    int stopped_on_proc = -1;
    //: Run-wide totals: no compared column may rest on something the capture has no column for.
    int unreached_called = 0;
    int precondition_broken = 0;
    int next_init_calls = 0;
    int button_dispatch_fellthrough = 0;
    int anm_resource_loads = 0;
    //: Frames the wall pass moved Link on. The roll's bonk arm reads mAcchCir[0]'s wall angle,
    //: so this says whether the cylinders (chosen by setBgCheckParam) decided anything.
    int wall_hit_frames = 0;
    //: ...and frames the line check ran on (CrrPos's gate, not its result).
    int line_check_frames = 0;
};

/// mItemTrigger on capture frame `i`, as setStickData builds it (d_a_player_main.cpp:10525-10611).
///
/// The one-frame edge word, not the hold word. `orderTalk`, `checkItemChangeFromButton` and
/// `changeSpecialBattle` are graded READ because they cannot return TRUE without a trigger, so it
/// is computed from the capture. BTN_R comes from mDoCPd_R_LOCK_TRIGGER (the latch at
/// cPadInfo+0x38), not the trigger word's `r` bit; on this capture both fire only on frame 48.
uint8_t item_trigger_for(const Json& golden, int i);

/// Frames whose `btn_trig` holds an A/B/X/Y/Z press, which cannot be mapped without
/// `dComIfGp_getButtonActionMode()` (not captured). Returned as "frame:button" strings.
std::vector<std::string> untranslatable_presses(const Json& golden, int first, int last);

ReplayResult run_roll_replay(const Json& golden, const RollReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_ROLL_REPLAY_H
