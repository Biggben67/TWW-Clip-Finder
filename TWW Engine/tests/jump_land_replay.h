// jump_land_replay.h - replay a launch-and-land pair across the sword capture, entry to exit, as
// one run each.
//
// The midair proc calls its own landing's init from its body, so the proc changes mid-run with
// nothing re-seeded, and the landing can leave for CUT_TURN on its first body frame by spending
// mProcVar6.m3570:
//
//     BACK_JUMP / BACK_JUMP_LAND     the backflip,    4 runs, 48 + 16 console frames
//     JUMP_CUT  / JUMP_CUT_LAND      the jump slash,  3 runs, 54 + 16 console frames
//
// Both landings read `mAcch.ChkGroundHit()`, which is collision; the rig's dBgS is empty, so
// ground-hit is delivered from the capture's `speed_y` and `gravity` columns (never `proc`, which
// would be circular): a zero in `speed_y` that gravity alone explains is the apex, one it cannot
// is the clamp. The jump slash passes through exactly 0.0 at its apex.
//
// The quickspin: the landing's m3570 arm is reached only on its first body frame, and turns
// `abs(m3578) > 0xF800` into procCutTurn_init(TRUE). m3578 is setStickData's accumulator, with no
// column; the harness computes it from `stick_angle_raw` (player_rig.h).

#ifndef TWW_ENGINE_TESTS_JUMP_LAND_REPLAY_H
#define TWW_ENGINE_TESTS_JUMP_LAND_REPLAY_H

#include <cstdint>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

/// Which pair. The id is an index into the table jump_land_pair() returns.
enum JumpLandPairId {
    kPairBackJump = 0,
    kPairJumpCut = 1,
    kJumpLandPairs = 2,
};

/// Everything that differs between the two pairs.
struct JumpLandPair {
    const char* name;
    int jump_proc;              //: daPyProc_BACK_JUMP_e / daPyProc_JUMP_CUT_e
    int land_proc;
    int first_frame;            //: the span of the capture this pair's entries are looked for in
    int last_frame;
    int runs;                   //: ...and what the capture's own proc column holds inside it
    int jump_frames;
    int land_frames;
    int voice;                  //: the id the entry init's voiceStart() fires
    /// procBackJump has two arms procJumpCut does not: checkFanGlideProc (the Deku Leaf, asked
    /// every airborne frame) and the drop to procFall. On procJumpCut both counts are 0 by the
    /// body.
    bool has_fan_and_fall;
    /// procJumpCut's changeCutReverseProc (the sword bounce), asked every airborne frame because
    /// the init writes the equality that guards it.
    bool asks_cut_reverse;
};

/// The two pairs. `id` is a JumpLandPairId.
const JumpLandPair& jump_land_pair(int id);

struct JumpLandReplayOptions {
    int pad_lead = 1;           //: see roll_replay.h

    //: The deliberately wrong twins, one at a time.
    //:
    //: Ground-hit delivered one frame late: moves every landing frame.
    bool late_ground_hit = false;
    //: Ground-hit never delivered: the port stays in the airborne proc past the console's change.
    bool no_ground_hit = false;
    //: The delivery rule without its gravity term (a bare `speed_y == 0`). Accepted on the
    //: backflip, whose rows the two rules agree on; lands the jump slash's runs nine frames early.
    bool naive_ground_hit = false;
    //: m3688 zeroed after the init (commonProcInit's launch position). Read only by procBackJump's
    //: drop arm.
    bool no_launch_pos = false;
    //: m35F0 zeroed after the init (commonProcInit's launch height). Read only by
    //: procJumpCutLand_init's drop `m35F0 - current.pos.y`; with the floor at y = -6534 every
    //: landing takes fall damage.
    bool no_launch_height = false;
    //: shape_angle.y seeded from the previous row's `travel_angle`. Every init writes
    //: current.angle.y from shape_angle.y, so this makes those writes no-ops.
    bool wrong_seed_shape_angle = false;
    //: The stick-rotation accumulator frozen at 0: the quickspin arm's input removed.
    bool no_stick_rotation = false;
    //: No sword. procBackJumpLand_init tests `mEquipItem == daPyItem_SWORD_e`, procJumpCutLand_init
    //: `!= daPyItem_NONE_e`, and each body tests again: the same exits as above, by another line.
    bool no_sword = false;
    //: The heavy state on. On the backflip it forks the init (mNormalSpeed halves, ROLLB rate 1.2)
    //: and turns on the landing's rumble; procJumpCut_init has no heavy fork.
    bool heavy_state = false;
    //: The airborne anim's attribute forced to EMode_LOOP. The backflip never lands; inert on the
    //: jump slash, whose JATTACK clock never reaches its frameMax inside a run.
    bool loop_jump_anim = false;
    //: The landing anim's attribute forced the same way. JATTACKLAND wraps at 14, so the two
    //: jump-slash runs that do not quickspin never end.
    bool loop_land_anim = false;
    //: posMoveFromFootPos skipped: position holds the seed row and speed.y the init's launch.
    bool no_pos_move = false;
    //: m_old_fdata->getOldFrameFlg() driven false, the arm the game takes once after Link's model
    //: is built: speedF goes to 0 and nothing integrates.
    bool skeleton_not_ready = false;
    //: `current.pos += speed` moved ahead of `speed.y += gravity`: every y is one gravity step off.
    bool integrate_before_gravity = false;
    //: changeCutReverseProc answered TRUE (the sword bounce). procJumpCut then flips
    //: current.angle.y by 0x8000, writes mNormalSpeed = 27.0, and runs the `else if` cLib_addCalc
    //: after. procBackJump has no such arm.
    bool cut_reverse_true = false;
};

struct JumpLandFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;   //: mNormalSpeed - the capture's `potential_speed`
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - `anim_frame`
    uint32_t rate_bits = 0;     //: ...its rate - `fc_rate`
    int end = 0;                //: ...its end - `fc_end`
    uint32_t gravity_bits = 0;  //: gravity - `gravity`
    int shape_angle_y = 0;      //: shape_angle.y - `shape_angle_y`
    int travel_angle = 0;       //: current.angle.y - `travel_angle`

    //: speed.y - the capture's `speed_y`.
    uint32_t speed_y_bits = 0;
    //: current.pos - `pos_x`, `pos_y`, `pos_z`; posMoveFromFootPos's last statement.
    uint32_t pos_x_bits = 0;
    uint32_t pos_y_bits = 0;
    uint32_t pos_z_bits = 0;
    //: Port-internal: the foot term before m3598 multiplies it. It comes from an empty skeleton.
    uint32_t foot_delta_bits = 0;
    //: m3598 - the capture's `blend_move`.
    uint32_t blend_bits = 0;
    //: ...and the stick-rotation accumulator the harness computes.
    int stick_rotation = 0;
};

//: One jump: the airborne proc's entry through the landing's exit, with no seed in between.
struct JumpLandRun {
    int entry = 0;              //: the capture's first airborne-proc frame of this run
    int land = -1;              //: ...its first landing frame, per the port
    int console_land = -1;      //: ...and per the capture's own proc column
    int exit = 0;               //: the first frame after the run that is neither proc
    int from_proc = 0;          //: the proc the console was in on the row before the entry
    std::vector<JumpLandFrame> rows;

    //: The proc the port entered, or the proc it named (cut_replay.h).
    int exit_proc = -1;
    bool exit_was_named = false;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws = 0;
    //: ...and as of the last compared frame. A quickspin leaves through procCutTurn_init (no draw),
    //: a clock-out through procWait_init (one draw), so the total depends on the exit.
    int rnd_draws_compared = 0;
    /// Anims with no measured metadata, as of the last compared frame: a quickspin's exit asks for
    /// ANM_CUTTURN, which has no anm_meta.inc row.
    int anm_meta_missing = 0;
    /// m3578 as the quickspin arm saw it, on the one frame it is reached. On a spin that frame is
    /// the exit and has no row.
    int rotation_at_poll = 0;
    bool polled = false;        //: ...and whether that frame happened at all

    //: What the pair's own boundary recorded.
    int fan_glide_calls = 0;    //: the backflip's Deku Leaf arm; asked once per airborne frame
    int fall_init_calls = 0;    //: ...and its drop arm; 0 says m3688 was written
    int cut_reverse_calls = 0;  //: the jump slash's sword-bounce arm, asked the same way
    int evmng_cut_end_calls = 0;
    int shock_calls = 0;
    int voice_id = -1;          //: the entry init's voiceStart
    int foot_effect_type = -1;  //: the landing's init setFootEffectPosType(3)
    uint32_t reset_flg0 = 0;    //: ...and the two foot bits it raises, read at the init
    int m3570_at_land = -1;     //: mProcVar6.m3570 as the landing's init left it
    int cut_at_param_type = -1; //: ...and the cut type its setJumpCutAtParam recorded

    //: procJumpCutLand_init's fall damage and the sword trail it starts, read at the init.
    int damage_calls = 0;
    float damage_amount = 0.0f;
    int sw_blur_calls = 0;
    int sw_blur_frames = 0;
    float sw_blur_top_rate = 0.0f;
    int sw_blur_color = 0;
    int base_tr_mtx_calls = 0;
    int hammer_quake_calls = 0;
};

/// The frames whose `proc` is the pair's airborne one and whose predecessor's is not.
std::vector<int> jump_land_entry_frames(const Json& golden, const JumpLandPair& pair);

std::vector<JumpLandRun> run_jump_land_replay(const Json& golden, int pair_id,
                                              const JumpLandReplayOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_JUMP_LAND_REPLAY_H
