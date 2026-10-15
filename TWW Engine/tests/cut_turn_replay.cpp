#include "cut_turn_replay.h"

#include <algorithm>

#include "player_rig.h"
#include "roll_replay.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {
namespace {

//: cPadInfo +0x30 / +0x32's bit for B.
enum : int { kCpadB = 0x0080 };

//: Every live caller of procCutTurn_init and the argument its call site passes.
struct TurnEntry {
    int from_proc;
    int arg;
    const char* where;
};

const TurnEntry kTurnEntries[] = {
    //: d_a_player_sword.inc:1808 - the spin charge's release. Starts the animation at 2.0.
    {0x59 /* daPyProc_CUT_TURN_MOVE_e */, FALSE, "d_a_player_sword.inc:1808"},
    //: d_a_player_sword.inc:2025 - landing out of a jump slash.
    {0x5C /* daPyProc_JUMP_CUT_LAND_e */, TRUE, "d_a_player_sword.inc:2025"},
    //: d_a_player_main.cpp:7079 - landing out of a backflip.
    {0x23 /* daPyProc_BACK_JUMP_LAND_e */, TRUE, "d_a_player_main.cpp:7079"},
};

//: The proc the port entered, or the proc it named through next_init.
int exit_proc_of(const daPy_lk_c& lk, bool* was_named) {
    if (lk.mCurProc != daPy_lk_c::daPyProc_CUT_TURN_e) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

}  // namespace

std::vector<int> cut_turn_entry_frames(const Json& golden, int first, int last) {
    std::vector<int> out;
    for (int f = first; f <= last; f++) {
        const bool here = golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        const bool before = golden[size_t(f - 1)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e;
        if (here && !before) {
            out.push_back(f);
        }
    }
    return out;
}

int cut_turn_init_arg(int from_proc) {
    for (const TurnEntry& e : kTurnEntries) {
        if (e.from_proc == from_proc) {
            return e.arg;
        }
    }
    return -1;
}

std::vector<CutTurnRun> run_cut_turn_replay(const Json& golden, const CutTurnReplayOptions& opt) {
    // Not needed by this proc, but keeps the shared rig identical across replays of one capture.
    JMA_useConsoleSinTable();

    std::vector<CutTurnRun> runs;
    for (int entry : cut_turn_entry_frames(golden, kTurnFirstFrame, kTurnLastFrame)) {
        CutTurnRun run;
        run.entry = entry;

        // A fresh rig per run: the gaps between spins are procs this slice has no body for.
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        const Json& seed = golden[size_t(entry - 1)];
        run.from_proc = int(seed["proc"].as_int());
        run.init_arg = cut_turn_init_arg(run.from_proc);

        lk.mStickDistance = seed["msd"].as_f32();
        // procCutTurn_init copies shape_angle.y onto current.angle.y (travel_angle), so each
        // must be seeded from its own column; before runs 4 and 5 they differ by 32768.
        lk.shape_angle.y = (s16)(opt.wrong_seed_shape_angle ? seed["travel_angle"].as_int()
                                                            : seed["shape_angle_y"].as_int());
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = seed["potential_speed"].as_f32();
        lk.speedF = seed["true_speed"].as_f32();
        lk.m34E8 = (s16)seed["target_angle"].as_int();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        lk.stub_attention_lock = seed["lock_l"].as_int() ? TRUE : FALSE;

        // procCutTurn_init's first half is behind `mEquipItem == daPyItem_SWORD_e`.
        lk.mEquipItem = daPyItem_SWORD_e;
        lk.stub_select_equip[0] = dItemNo_SWORD_e;

        // The argument comes from the predecessor proc via kTurnEntries; an unknown predecessor
        // leaves it at -1 and the init is not run, so the gate fails.
        const BOOL arg = (run.init_arg > 0) != (opt.wrong_init_arg != 0) ? TRUE : FALSE;
        if (run.init_arg >= 0) {
            lk.procCutTurn_init(arg);
        }

        // mProcVar0.m34D0 is the exit countdown.
        if (opt.no_exit_countdown) {
            lk.mProcVar0.m34D0 = 0;
        }

        // Read here, not after the run: the exit frame's procWait_init overwrites m35A0.
        run.at_target_bits = f32_bits(lk.m35A4);
        run.plume_end_bits = f32_bits(lk.m35A0);

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            CutTurnFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.at_radius_bits = f32_bits(lk.mAtCyl.GetR());
            r.ribbon_alpha = (int)lk.m331C.getAlpha();
            run.rows.push_back(r);
        };
        emit(entry);

        int f = entry + 1;
        while (f < int(golden.size()) &&
               golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_e) {
            f++;
        }
        run.exit = f;

        for (int i = entry + 1; i <= run.exit; i++) {
            const Json& r = golden[size_t(i)];
            const Json& p = golden[size_t(i - opt.pad_lead)];

            frame_top(lk);

            lk.speedF = golden[size_t(i - 1)]["true_speed"].as_f32();
            lk.mStickDistance = r["msd"].as_f32();
            lk.m34E8 = (s16)r["target_angle"].as_int();
            lk.m34DC = (s16)r["stick_angle_raw"].as_int();

            lk.mItemButton = (u8)((p["lock_r"].as_int() ? daPy_lk_c::BTN_R : 0) |
                                  ((!opt.no_b_hold && (p["btn_hold"].as_int() & kCpadB))
                                       ? daPy_lk_c::BTN_B : 0));
            lk.mItemTrigger = item_trigger_for(golden, i - opt.pad_lead);
            lk.stub_attention_lock = p["lock_l"].as_int() ? TRUE : FALSE;

            lk.animeUpdate();

            if (!run_proc(lk)) {
                break;
            }
            if (i < run.exit) {
                emit(i);
                run.rnd_draws_compared = lk.rnd_draws;
            }
        }

        run.exit_proc = exit_proc_of(lk, &run.exit_was_named);
        run.unreached_called = lk.unreached_called;
        run.precondition_broken = lk.precondition_broken;
        run.rnd_draws = lk.rnd_draws;
        run.anm_meta_missing = lk.anm_meta_missing;
        run.sword_anim_idx = lk.sword_anim_idx;
        run.blur_pos_idx = lk.blur_pos_idx;
        run.sword_cut_se = lk.sword_cut_se;
        run.particle_toe_id = lk.particle_toe_id;
        run.particle_toe_joint = lk.particle_toe_joint;
        run.particle_ground_id = lk.particle_ground_id;
        run.at_atp = lk.mAtCyl.mObjAt.mAtp;
        run.player_status0 = lk.player_status0;
        run.particle_ends = lk.particle_ends;
        run.smoke_removes = lk.smoke_removes;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
