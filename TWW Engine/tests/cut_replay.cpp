#include "cut_replay.h"

#include <algorithm>

#include "player_rig.h"
#include "roll_replay.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {
namespace {

//: cPadInfo +0x30 / +0x32's B bit in the capture's big-endian `controller_pad_buttons` word (see
//: roll_replay.cpp).
enum : int { kCpadB = 0x0080 };

//: mNormalSpeed over the six frames after each entry, under daPy_HIO_cutA_c1 (field_0x10 0.2,
//: 0x14 10.0, 0x18 2.6, 0x1C 0.5, 0x20 0.7):
//:
//:   entry   0.00   procCutA_init writes no speed; the WAIT before it left 0
//:   +1      7.40   checkPass(6.0) fires -> fabs(0)*0.2 + 10.0 = 10.0, then addCalc's maxStep arm
//:   +2      4.80   maxStep again
//:   +3      2.20   maxStep again
//:   +4      0.66   |0.7 * -2.2| = 1.54 < maxStep -> the unclamped scale arm
//:   +5      0.16   |0.7 * -0.66| = 0.462 < minStep 0.5 -> the minStep arm, 0.66 - 0.5
//:   +6      0.00   0.16 - 0.5 overshoots the target -> the minStep arm's own clamp
//:
//: checkPass looks forward (J3DAnimation.cpp:28, `cur <= pass < cur + rate`), so the lunge lands
//: on the frame whose clock reads 5.2, not 6.4.

//: The proc on the exit frame. A ported exit changes mCurProc; an unported one runs a proc-init
//: STUB that records the id in next_init and leaves mCurProc at CUT_A.
int exit_proc_of(const daPy_lk_c& lk, bool* was_named) {
    if (lk.mCurProc != daPy_lk_c::daPyProc_CUT_A_e) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

}  // namespace

std::vector<int> cut_entry_frames(const Json& golden, int first, int last) {
    std::vector<int> out;
    for (int f = first; f <= last; f++) {
        const bool here = golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_A_e;
        const bool before = golden[size_t(f - 1)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_A_e;
        if (here && !before) {
            out.push_back(f);
        }
    }
    return out;
}

std::vector<int> b_trigger_frames(const Json& golden, int first, int last) {
    std::vector<int> out;
    for (int f = first; f <= last; f++) {
        if (golden[size_t(f)]["btn_trig"].as_int() & kCpadB) {
            out.push_back(f);
        }
    }
    return out;
}

std::vector<CutRun> run_cut_replay(const Json& golden, const CutReplayOptions& opt) {
    // The console's sin table, not JMANewSinTable(12) (m_Do_machine.cpp:614); cLib_addCalcAngleS
    // reads it.
    JMA_useConsoleSinTable();

    std::vector<CutRun> runs;
    for (int entry : cut_entry_frames(golden, kCutFirstFrame, kCutLastFrame)) {
        CutRun run;
        run.entry = entry;

        // A fresh rig per run: the locked WAIT frames between runs are not ported (cut_replay.h).
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        // Seeded from the capture's last row before the slash.
        const Json& seed = golden[size_t(entry - 1)];
        lk.mStickDistance = seed["msd"].as_f32();
        lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = seed["potential_speed"].as_f32();
        lk.speedF = seed["true_speed"].as_f32();
        lk.m34E8 = (s16)seed["target_angle"].as_int();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        lk.stub_attention_lock = seed["lock_l"].as_int() ? TRUE : FALSE;

        // checkNextActionFromButton's sword arm needs `mEquipItem == daPyItem_SWORD_e`, and the
        // capture slashes; `no_sword_equipped` is the control.
        lk.mEquipItem = opt.no_sword_equipped ? daPyItem_NONE_e : daPyItem_SWORD_e;
        // checkNormalSwordEquip reads slot 0.
        lk.stub_select_equip[0] = dItemNo_SWORD_e;

        // changeCutProc's argument is `checkAttentionLock() || mStickDistance <= 0.05f ?
        // shape_angle.y : m34E8` (d_a_player_sword.inc:412), inside `if (checkAttentionLock())`,
        // so shape_angle.y. `wrong_init_angle` is the control.
        lk.procCutA_init(opt.wrong_init_angle ? lk.m34E8 : lk.shape_angle.y);

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            CutFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            run.rows.push_back(r);
        };
        emit(entry);

        // Run until the console leaves CUT_A, plus the exit frame, which is not compared.
        int f = entry + 1;
        while (f < int(golden.size()) &&
               golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_A_e) {
            f++;
        }
        run.exit = f;

        for (int i = entry + 1; i <= run.exit; i++) {
            const Json& r = golden[size_t(i)];
            const Json& p = golden[size_t(i - opt.pad_lead)];

            frame_top(lk);  // before the inputs: it carries m34DC forward into m34EA

            // speedF is the previous row's: posMove() writes it (d_a_player_main.cpp:2422) after
            // the proc (11394 dispatch, 11400 posMove). At the lunge that gives 10.0 then 7.4,
            // matching the capture; the current row's would give 8.88.
            lk.speedF = golden[size_t(opt.wrong_speedf_lead ? i : i - 1)]["true_speed"].as_f32();
            lk.mStickDistance = r["msd"].as_f32();
            lk.m34E8 = (s16)r["target_angle"].as_int();
            lk.m34DC = (s16)r["stick_angle_raw"].as_int();

            // mItemButton is built from lock_r / lock_l (cPadInfo +0x37 / +0x35) and B from
            // btn_hold. setStickData's B hold needs `dComIfGp_getButtonActionMode() & 2`, which no
            // column records; the capture slashing implies it was set.
            lk.mItemButton = (u8)((p["lock_r"].as_int() ? daPy_lk_c::BTN_R : 0) |
                                  ((!opt.no_b_hold && (p["btn_hold"].as_int() & kCpadB))
                                       ? daPy_lk_c::BTN_B : 0));
            lk.mItemTrigger = item_trigger_for(golden, i - opt.pad_lead);
            lk.stub_attention_lock = p["lock_l"].as_int() ? TRUE : FALSE;

            // animeUpdate() (d_a_player_main.cpp:11346, 12881) advances the anim clocks before the
            // proc; checkPass and the `> 16.0` exit read the advanced clock.
            lk.animeUpdate();

            if (!run_proc(lk)) {
                // An unported proc inside a run: a disagreement, left for the comparison to report.
                break;
            }
            if (i < run.exit) {
                emit(i);
                // Before the exit frame, whose procWait_init draw nothing compared depends on.
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
        run.cut_at_param_type = lk.cut_at_param_type;
        run.sword_cut_se = lk.sword_cut_se;
        run.player_status0 = lk.player_status0;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
