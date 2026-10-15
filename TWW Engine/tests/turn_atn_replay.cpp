#include "turn_atn_replay.h"

#include <cstdlib>
#include <cstring>

#include "player_rig.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {

namespace {

//: The two procs' constants.
const TurnAtnSpec kSpecs[] = {
    {TurnAtnKind::WaitTurn, "procwaitturn_oracle.json", "procWaitTurn",
     daPy_lk_c::daPyProc_WAIT_TURN_e, true, -1},
    {TurnAtnKind::AtnMove, "procatnmove_oracle.json", "procAtnMove",
     daPy_lk_c::daPyProc_ATN_MOVE_e, false, 20},
};

//: The golden's float columns are hex bit patterns.
uint32_t hex_bits(const Json& v) {
    return uint32_t(std::strtoul(v.str.c_str(), nullptr, 16));
}

f32 hex_f32(const Json& v) {
    const uint32_t u = hex_bits(v);
    f32 f;
    std::memcpy(&f, &u, 4);
    return f;
}

//: As cut_replay.cpp: an exit into a ported proc moves mCurProc; one into an unported proc runs
//: a stub that records the id in next_init.
int exit_proc_of(const daPy_lk_c& lk, const TurnAtnSpec& spec, bool* was_named) {
    if (lk.mCurProc != spec.proc_id) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

void run_init(daPy_lk_c& lk, TurnAtnKind kind) {
    if (kind == TurnAtnKind::WaitTurn) {
        lk.procWaitTurn_init();
    } else {
        lk.procAtnMove_init();
    }
}

//: Whether the dispatching frame (the idle proc's, which calls checkNextMode and the init) can be
//: replayed from the seed row. `from_the_roll`'s seed is FRONT_ROLL, whose exit turns on a clock
//: no column carries, so it is seeded at its entry instead.
bool can_replay_dispatch(int seed_proc) {
    return seed_proc == daPy_lk_c::daPyProc_WAIT_e || seed_proc == daPy_lk_c::daPyProc_FREE_WAIT_e;
}

}  // namespace

const TurnAtnSpec& turn_atn_spec(TurnAtnKind kind) {
    for (const TurnAtnSpec& s : kSpecs) {
        if (s.kind == kind) {
            return s;
        }
    }
    return kSpecs[0];
}

std::vector<TurnAtnRun> run_turn_atn_replay(TurnAtnKind kind, const Json& golden,
                                            const TurnAtnOptions& opt) {
    // The game's boot line, JMANewSinTable(12) (m_Do_machine.cpp:614), with the console's table.
    JMA_useConsoleSinTable();

    const TurnAtnSpec& spec = turn_atn_spec(kind);
    std::vector<TurnAtnRun> runs;
    const Json& scenarios = golden["scenarios"];
    for (size_t s = 0; s < scenarios.size(); s++) {
        const Json& sc = scenarios[s];
        const Json& rows = sc["frames"];
        const int entry = int(sc["entry"].as_int());
        const int exit = int(sc["exit"].as_int());

        std::fprintf(stderr, "[probe] scenario %zu %s\n", s, sc["name"].str.c_str());
        TurnAtnRun run;
        run.fn = spec.fn;
        run.name = sc["name"].str;
        run.covers = sc["covers"].str;
        run.entry = entry;
        run.exit = exit;

        // A fresh rig per scenario.
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        // No sword: the old sim's LandState defaults `sword_drawn=False`.
        lk.mEquipItem = daPyItem_NONE_e;

        const Json& before = rows[size_t(entry - 1)];
        const bool replay_dispatch = can_replay_dispatch(int(before["proc"].as_int()));
        run.dispatch_replayed = replay_dispatch;

        // Some init must run first so the frame controllers point at an animation. It is the seed
        // row's own (procWait_init / procFreeWait_init); on `from_the_roll` procWait_init stands
        // in, which is safe because no compared column is an animation and every compared column is
        // re-seeded below.
        if (int(before["proc"].as_int()) == daPy_lk_c::daPyProc_FREE_WAIT_e) {
            lk.procFreeWait_init();
        } else {
            lk.procWait_init();
        }
        // The seed: the row the first replayed frame reads.
        const Json& seed = rows[size_t(replay_dispatch ? entry - 1 : entry)];
        lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = hex_f32(seed["nspeed_hex"]);
        lk.mMaxNormalSpeed = hex_f32(seed["max_nspeed_hex"]);
        lk.mDirection = (u8)seed["direction"].as_int();
        lk.speedF = hex_f32(seed["speedF_hex"]);
        // mCurProc is WAIT on the seeded path: procAtnMove_init returns early if mCurProc is
        // already ATN_MOVE, skipping commonProcInit and leaving the idle mModeFlg
        // (ModeFlg_00000001, which gates checkNextActionFromButton's R arm).
        lk.mCurProc = replay_dispatch ? (int)before["proc"].as_int() : daPy_lk_c::daPyProc_WAIT_e;

        int start = entry;
        if (!replay_dispatch) {
            // The init by hand, with the entry row's inputs, as checkNextMode would hand them.
            frame_top(lk);
            const Json& e = rows[size_t(entry)];
            lk.mStickDistance = hex_f32(e["msd_hex"]);
            lk.m34E8 = (s16)e["target_angle"].as_int();
            lk.m34DC = (s16)e["stick_angle_raw"].as_int();
            lk.m34E6 = (s16)(opt.facing_lock_from_travel ? lk.current.angle.y
                                                         : (s16)e["facing_lock"].as_int());
            lk.stub_attention_lock =
                (!opt.no_attention_lock && e["btn_l"].as_int()) ? TRUE : FALSE;
            run_init(lk, kind);
            run.hold_after_init = (int)lk.mProcVar0.m34D0;
            run.turn_target_after_init = (int)(u16)lk.mProcVar2.m34D4;
            run.travel_after_init = (int)(u16)lk.current.angle.y;
            start = entry + 1;

            TurnAtnFrame r;
            r.frame = entry;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.max_nspeed_bits = f32_bits(lk.mMaxNormalSpeed);
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.direction = (int)lk.mDirection;
            r.turn_target = (int)(u16)lk.mProcVar2.m34D4;
            run.rows.push_back(r);
        }

        for (int i = start; i <= exit; i++) {
            const Json& r = rows[size_t(i)];
            // PAD_LEAD 0: the oracle takes inputs as arguments to the frame that acts on them.
            // `wrong_pad_lead` is the console replays' alignment.
            const Json& p = rows[size_t(opt.wrong_pad_lead ? i - 1 : i)];

            frame_top(lk);  // before the inputs: it carries m34DC into m34EA

            // speedF is the previous row's: posMove writes it (d_a_player_main.cpp:2422) after the
            // dispatch (11394, then 11400).
            lk.speedF = hex_f32(rows[size_t(opt.wrong_speedf_lead ? i : i - 1)]["speedF_hex"]);
            lk.mStickDistance = hex_f32(p["msd_hex"]);
            lk.m34E8 = (s16)p["target_angle"].as_int();
            lk.m34DC = (s16)p["stick_angle_raw"].as_int();
            // m34E6, the facing lock, an input (turn_atn_replay.h); the control takes it from
            // travel.
            lk.m34E6 = (s16)(opt.facing_lock_from_travel ? lk.current.angle.y
                                                        : (s16)p["facing_lock"].as_int());
            lk.stub_attention_lock =
                (!opt.no_attention_lock && p["btn_l"].as_int()) ? TRUE : FALSE;
            lk.mItemButton = (u8)(p["btn_r"].as_int() ? daPy_lk_c::BTN_R : 0);
            const bool r_was = rows[size_t(i - 1)]["btn_r"].as_int() != 0;
            lk.mItemTrigger =
                (u8)((p["btn_r"].as_int() && !r_was) ? daPy_lk_c::BTN_R : 0);

            // The pivot-goal control: m34D4 re-pointed at this frame's stick, not the latched
            // value.
            if (opt.turn_target_follows_stick && spec.latches_turn_target) {
                lk.mProcVar2.m34D4 = lk.m34E8;
            }
            const u8 frozen_dir = lk.mDirection;

            // animeUpdate() (d_a_player_main.cpp:11346, 12881): the clocks advance before the proc.
            if (opt.proc_before_anim) {
                if (!run_proc(lk)) {
                    break;
                }
                lk.animeUpdate();
            } else {
                lk.animeUpdate();
                if (!run_proc(lk)) {
                    // No body for this proc: left as a disagreement.
                    break;
                }
            }
            if (opt.freeze_direction) {
                lk.mDirection = frozen_dir;
            }
            if (i == entry && replay_dispatch) {
                run.hold_after_init = (int)lk.mProcVar0.m34D0;
                run.turn_target_after_init = (int)(u16)lk.mProcVar2.m34D4;
                run.travel_after_init = (int)(u16)lk.current.angle.y;
            }
            if (lk.mCurProc == spec.proc_id) {
                run.body_frames++;
            }

            TurnAtnFrame f;
            f.frame = i;
            f.proc = lk.mCurProc;
            f.nspeed_bits = f32_bits(lk.mNormalSpeed);
            f.max_nspeed_bits = f32_bits(lk.mMaxNormalSpeed);
            f.shape_angle_y = (int)(u16)lk.shape_angle.y;
            f.travel_angle = (int)(u16)lk.current.angle.y;
            f.direction = (int)lk.mDirection;
            f.turn_target = (int)(u16)lk.mProcVar2.m34D4;
            run.rows.push_back(f);
        }

        run.exit_proc = exit_proc_of(lk, spec, &run.exit_was_named);
        run.unreached_called = lk.unreached_called;
        run.precondition_broken = lk.precondition_broken;
        run.front_wall_proc_calls = lk.front_wall_proc_calls;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
