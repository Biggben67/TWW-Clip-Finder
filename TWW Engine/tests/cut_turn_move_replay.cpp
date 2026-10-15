#include "cut_turn_move_replay.h"

#include <algorithm>

#include "player_rig.h"
#include "roll_replay.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {
namespace {

//: cPadInfo +0x30 / +0x32's bit for B, in roll_replay.cpp's 12-bit word.
enum : int { kCpadB = 0x0080 };

//: The procs procCutTurnMove_init is called from: one live call site, procCutTurnCharge's
//: rate-expired arm (d_a_player_sword.inc:1681).
const int kTurnMoveEntries[] = {
    0x58 /* daPyProc_CUT_TURN_CHARGE_e - d_a_player_sword.inc:1681 */,
};

//: As in cut_replay: the proc the port entered, or the proc it named.
int exit_proc_of(const daPy_lk_c& lk, bool* was_named) {
    if (lk.mCurProc != daPy_lk_c::daPyProc_CUT_TURN_MOVE_e) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

}  // namespace

std::vector<int> cut_turn_move_entry_frames(const Json& golden, int first, int last) {
    std::vector<int> out;
    for (int f = first; f <= last; f++) {
        const int kProc = daPy_lk_c::daPyProc_CUT_TURN_MOVE_e;
        const bool here = golden[size_t(f)]["proc"].as_int() == kProc;
        const bool before = golden[size_t(f - 1)]["proc"].as_int() == kProc;
        if (here && !before) {
            out.push_back(f);
        }
    }
    return out;
}

bool cut_turn_move_entry_is_known(int from_proc) {
    for (int p : kTurnMoveEntries) {
        if (p == from_proc) {
            return true;
        }
    }
    return false;
}

std::vector<CutTurnMoveRun> run_cut_turn_move_replay(const Json& golden,
                                                     const CutTurnMoveReplayOptions& opt) {
    // The console's sin table, as the other replays install it on the shared rig.
    JMA_useConsoleSinTable();

    std::vector<CutTurnMoveRun> runs;
    for (int entry : cut_turn_move_entry_frames(golden, kTurnMoveFirstFrame, kTurnMoveLastFrame)) {
        CutTurnMoveRun run;
        run.entry = entry;

        // A fresh rig per run: the frames between the holds (CUT_TURN, WAIT with the lock, the
        // charge) are not all dispatchable.
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

        // procCutTurnMove_init's hurricane chain tests mEquipItem against SWORD; the BOKO arm
        // beside it is unreached, as in the spin's init.
        lk.mEquipItem = daPyItem_SWORD_e;
        lk.stub_select_equip[0] = dItemNo_SWORD_e;

        // procCutTurnMove reads mMaxNormalSpeed without a proc having written it (procMove's
        // setSpeedAndAngleNormal writes it in a walk), so it is seeded with the boot default,
        // daPy_lk_c::create's `m_HIO->mMove.m.field_0x18` (d_a_player_main.cpp:12194). The body
        // only uses `mNormalSpeed / mMaxNormalSpeed` with mNormalSpeed 0.0, so the capture can only
        // check that it is not zero.
        if (opt.zero_max_speed) {
            lk.mMaxNormalSpeed = 0.0f;
        } else if (opt.atn_max_speed) {
            lk.mMaxNormalSpeed = rig.hio.mAtnMove.m.mMaxNormalSpeed;
        } else {
            lk.mMaxNormalSpeed = rig.hio.mMove.m.mMaxNormalSpeed;
        }

        // The fork the capture cannot see. Both save flags and the meter together, since the
        // decomp reads them in one `&&` chain.
        lk.stub_event_bit = opt.hurricane ? TRUE : FALSE;
        lk.stub_tmp_bit = FALSE;
        lk.stub_magic = opt.hurricane ? 16 : 0;

        lk.procCutTurnMove_init();

        if (opt.no_init_blend) {
            lk.m3598 = 0.0f;
        }

        // Read at the init: the exit frame runs procCutTurn_init, which writes both emitter
        // recorders, the same status word and the same anim slot.
        run.charge_countdown = lk.mProcVar0.m34D0;
        run.particle_ids[0] = lk.particle_toe_id;
        run.particle_ids[1] = lk.particle_ground_id;
        run.particle_joint = lk.last_anm_mtx_joint;
        run.player_status0 = lk.player_status0;
        run.anim_idx = (int)lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx;

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            CutTurnMoveFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.blend_bits = f32_bits(lk.m3598);
            r.direction = (int)lk.mDirection;
            r.mode_flg_bit0 = lk.checkModeFlg(ModeFlg_00000001) ? 1 : 0;
            run.rows.push_back(r);
        };
        emit(entry);

        int f = entry + 1;
        while (f < int(golden.size()) &&
               golden[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CUT_TURN_MOVE_e) {
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
        run.system_se = lk.system_se;
        run.system_se_calls = lk.system_se_calls;
        run.se_anime_inits = lk.se_anime_inits;
        run.player_status1 = lk.player_status1;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
