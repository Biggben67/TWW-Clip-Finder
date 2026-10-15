// turn_atn_replay.h - drive procWaitTurn and procAtnMove across the Python sim's scenarios.
//
// No console capture has a frame in proc 0x17 and only three are in 0x07, so the oracle is the
// Python sim (tier SIM, `_tier: regression`): agreeing with it means "the C++ reproduces the
// Python", not "the engine is right", and a misreading of the decomp both share is invisible.
// It does catch what is not copied arithmetic: exit dispatch, boundary answers, the HIO row each
// body indexes, and the direction machine's forks.
//
// One driver for both procs because they share a stream shape (seed, init, then frame_top,
// deliver, run to an exit row); the per-proc half is `TurnAtnSpec`.
//
// Both seed from `rows[entry - 1]`: procWaitTurn_init writes `mProcVar2.m34D4 = m34E8` and
// `current.angle.y = shape_angle.y`, so the entry row holds the init's own output; procAtnMove_init
// calls setBlendAtnMoveAnime, which reads the previous frame's angles and mDirection.
//
// Pad lead is 0: row i's inputs are what row i's proc read.
//
// m34E6 is an input: the facing lock is latched on the L rising edge in `execute`
// (d_a_player_main.cpp:2067), outside both procs, and setSpeedAndAngleAtn reads it.

#ifndef TWW_ENGINE_TESTS_TURN_ATN_REPLAY_H
#define TWW_ENGINE_TESTS_TURN_ATN_REPLAY_H

#include <cstdint>
#include <string>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

enum class TurnAtnKind { WaitTurn, AtnMove };

//: Everything that differs between the two procs.
struct TurnAtnSpec {
    TurnAtnKind kind;
    const char* golden;
    const char* fn;          //: "procWaitTurn" - used in every failure message
    int proc_id;             //: daPyProc_WAIT_TURN_e / daPyProc_ATN_MOVE_e
    //: procWaitTurn_init latches mProcVar2.m34D4 from m34E8; procAtnMove_init does not, and the
    //: golden's `turn_target` is meaningless on its rows.
    bool latches_turn_target;
    //: procAtnMove_init ends with `mProcVar0.m34D0 = 20`; -1 means the init does not touch it.
    int hold_after_init;
};

//: No `wrong_hio_row` control: `side`, `backward` and `forward` index mAtnMove, mAtnMoveB and
//: mMove (caps 12.0, 15.0, 17.0), so a wrong row is caught by the scenario that reads the right one.

const TurnAtnSpec& turn_atn_spec(TurnAtnKind kind);

struct TurnAtnOptions {
    //: Deliberately wrong twins, one at a time.
    //:
    //: Stick and buttons taken from the previous row (the console replays' alignment).
    bool wrong_pad_lead = false;
    //: speedF from the current row; posMove writes it after the dispatch, so frame N reads N-1's.
    bool wrong_speedf_lead = false;
    //: Pivot goal re-read from m34E8 every frame instead of the latched mProcVar2.m34D4.
    bool turn_target_follows_stick = false;
    //: Attention lock forced false regardless of the golden's btn_l.
    bool no_attention_lock = false;
    //: m34E6 driven to the travel angle instead of the golden's `facing_lock`.
    bool facing_lock_from_travel = false;
    //: mDirection frozen at the seed row's value; inert on steady-state scenarios, hence
    //: `direction_swing`.
    bool freeze_direction = false;
    //: Dispatch run before animeUpdate.
    bool proc_before_anim = false;
};

struct TurnAtnFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t max_nspeed_bits = 0;
    int shape_angle_y = 0;
    int travel_angle = 0;
    int direction = 0;
    //: mProcVar2.m34D4, the pivot's latched goal; checked only on pivot rows.
    int turn_target = 0;
};

struct TurnAtnRun {
    std::string fn;             //: "procWaitTurn"
    std::string name;
    std::string covers;
    int entry = 0;
    int exit = 0;
    std::vector<TurnAtnFrame> rows;
    //: The proc the port entered, or named through a proc-init stub, on the oracle's exit frame.
    int exit_proc = -1;
    bool exit_was_named = false;

    int unreached_called = 0;
    int precondition_broken = 0;
    //: What the init left before a body frame ran.
    int hold_after_init = -1;
    int turn_target_after_init = -1;
    int travel_after_init = -1;
    //: Frames in the proc under test at dispatch time, so an empty run cannot pass.
    int body_frames = 0;
    //: procAtnMove's front-wall stub; must answer false on every frame here.
    int front_wall_proc_calls = 0;
    //: Whether the dispatching frame was replayed (idle-seeded) or seeded past (`from_the_roll`,
    //: whose exit turns on an animation clock no column carries). See `can_replay_dispatch`.
    bool dispatch_replayed = false;
};

std::vector<TurnAtnRun> run_turn_atn_replay(TurnAtnKind kind, const Json& golden,
                                            const TurnAtnOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_TURN_ATN_REPLAY_H
