#include "cut_turn_charge_replay.h"

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

//: Procs this slice has a body for that end in checkNextMode, the route to procCutTurnCharge_init's
//: call sites (d_a_player_main.cpp:4188 and :4198). The port's own list, not the decomp's.
const int kChargeEntries[] = {
    0x41 /* daPyProc_CUT_A_e - the slash, whose B-held exit is checkNextMode(0) */,
};

//: The proc the port entered, or the proc it named.
int exit_proc_of(const daPy_lk_c& lk, bool* was_named) {
    if (lk.mCurProc != daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

}  // namespace

std::vector<int> cut_turn_charge_entry_frames(const Json& golden, int first, int last) {
    std::vector<int> out;
    for (int f = first; f <= last; f++) {
        const int kProc = daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e;
        const bool here = golden[size_t(f)]["proc"].as_int() == kProc;
        const bool before = golden[size_t(f - 1)]["proc"].as_int() == kProc;
        if (here && !before) {
            out.push_back(f);
        }
    }
    return out;
}

bool cut_turn_charge_entry_is_known(int from_proc) {
    for (int p : kChargeEntries) {
        if (p == from_proc) {
            return true;
        }
    }
    return false;
}

std::vector<CutTurnChargeRun> run_cut_turn_charge_replay(const Json& golden,
                                                         const CutTurnChargeReplayOptions& opt) {
    JMA_useConsoleSinTable();

    std::vector<CutTurnChargeRun> runs;
    for (int entry : cut_turn_charge_entry_frames(golden, kChargeFirstFrame, kChargeLastFrame)) {
        CutTurnChargeRun run;
        run.entry = entry;

        // A fresh rig per run: no state is carried across the frames between wind-ups.
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        const Json& seed = golden[size_t(entry - 1)];
        run.from_proc = int(seed["proc"].as_int());

        lk.mStickDistance = seed["msd"].as_f32();
        lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = seed["potential_speed"].as_f32();
        lk.speedF = seed["true_speed"].as_f32();
        lk.m34E8 = (s16)seed["target_angle"].as_int();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        lk.stub_attention_lock = seed["lock_l"].as_int() ? TRUE : FALSE;

        // The exit frame's procCutTurnMove_init tests mEquipItem against SWORD.
        lk.mEquipItem = daPyItem_SWORD_e;
        lk.stub_select_equip[0] = dItemNo_SWORD_e;

        lk.procCutTurnCharge_init();

        // Applied after the init so the copied body stays unedited.
        if (opt.start_at_zero) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setFrame(0.0f);
        }
        if (opt.rate_one) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setRate(1.0f);
        }

        // Read at the init: the exit frame's procCutTurnMove_init overwrites both.
        run.anim_idx = (int)lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx;
        run.player_status0 = lk.player_status0;

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            CutTurnChargeFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.blend_bits = f32_bits(lk.m3598);
            run.rows.push_back(r);
        };
        emit(entry);

        int f = entry + 1;
        while (f < int(golden.size()) &&
               golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e) {
            f++;
        }
        run.exit = f;

        // Runs to the capture's exit even under a control that leaves early, so a control's cost
        // shows as wrong columns rather than missing rows.
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
            lk.stub_curse = opt.cursed ? TRUE : FALSE;

            // The game runs animeUpdate then the proc (daPy_lk_c::execute).
            if (opt.proc_before_anim) {
                if (!run_proc(lk)) {
                    break;
                }
                lk.animeUpdate();
            } else {
                lk.animeUpdate();
                if (!run_proc(lk)) {
                    break;
                }
            }
            if (run.port_exit_frame < 0 &&
                lk.mCurProc != daPy_lk_c::daPyProc_CUT_TURN_CHARGE_e) {
                run.port_exit_frame = i;
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
        run.next_init_calls = lk.next_init_calls;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
