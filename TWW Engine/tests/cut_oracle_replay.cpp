#include "cut_oracle_replay.h"

#include <cstdlib>
#include <cstring>

#include "player_rig.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {

namespace {

//: The five procs' constants; only `run_init` switches on the kind. Each control value is another
//: shipped row's field, so a control means "the body indexed the wrong HIO row": the end control
//: is the slash's 19 for CUT_L and CUT_L's 18 elsewhere; each ender's rate control is the other
//: ender's rate (a fixed 1.0 would be inert on procCutEA, whose rate is 1.0).
const CutSpec kSpecs[] = {
    {CutKind::L, "cut_l_oracle.json", "procCutL", daPy_lk_c::daPyProc_CUT_L_e,
     daPy_lk_c::CUT_TYPE_CUT_L, dRes_INDEX_LKANM_BCK_CUTLA_e, dRes_INDEX_LKANM_BCK_CUTLMS_e,
     dRes_INDEX_LKANM__CUTL_POS_e, 18, 19, 1.0f, daPy_lk_c::DIR_LEFT, 4, false, true, -1},
    {CutKind::F, "cut_f_oracle.json", "procCutF", daPy_lk_c::daPyProc_CUT_F_e,
     daPy_lk_c::CUT_TYPE_CUT_F, dRes_INDEX_LKANM_BCK_CUTFA_e, dRes_INDEX_LKANM_BCK_CUTFMS_e,
     -1, 19, 18, 1.0f, daPy_lk_c::DIR_RIGHT, 2, true, true, -1},
    {CutKind::R, "cut_r_oracle.json", "procCutR", daPy_lk_c::daPyProc_CUT_R_e,
     daPy_lk_c::CUT_TYPE_CUT_R, dRes_INDEX_LKANM_BCK_CUTRA_e, dRes_INDEX_LKANM_BCK_CUTRMS_e,
     dRes_INDEX_LKANM__CUTR_POS_e, 19, 18, 1.0f, daPy_lk_c::DIR_RIGHT, 3, false, true, -1},
    {CutKind::EA, "cut_ea_oracle.json", "procCutEA", daPy_lk_c::daPyProc_CUT_EA_e,
     daPy_lk_c::CUT_TYPE_CUT_EA, dRes_INDEX_LKANM_BCK_CUTEAA_e, dRes_INDEX_LKANM_BCK_CUTEAMS_e,
     dRes_INDEX_LKANM__CUTEA_POS_e, 19, 18, 0.9f, daPy_lk_c::DIR_RIGHT, 0, false, false, 0},
    {CutKind::EB, "cut_eb_oracle.json", "procCutEB", daPy_lk_c::daPyProc_CUT_EB_e,
     daPy_lk_c::CUT_TYPE_CUT_EB, dRes_INDEX_LKANM_BCK_CUTEBA_e, dRes_INDEX_LKANM_BCK_CUTEBMS_e,
     dRes_INDEX_LKANM__CUTEB_POS_e, 19, 18, 1.0f, daPy_lk_c::DIR_LEFT, 0, false, false, 0},
};

//: The golden's float columns are hex bit patterns, so no decimal round trip is involved.
uint32_t hex_bits(const Json& v) {
    return uint32_t(std::strtoul(v.str.c_str(), nullptr, 16));
}

f32 hex_f32(const Json& v) {
    const uint32_t u = hex_bits(v);
    f32 f;
    std::memcpy(&f, &u, 4);
    return f;
}

//: As in cut_replay.cpp: an exit into a ported proc moves mCurProc; one into an unported proc
//: runs a proc-init stub that records the id and leaves mCurProc alone.
int exit_proc_of(const daPy_lk_c& lk, const CutSpec& spec, bool* was_named) {
    if (lk.mCurProc != spec.proc_id) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

//: The one switch on the kind. The inits and their signatures are the decomp's: the enders take
//: no argument (`CutSpec::has_aim`).
void run_init(daPy_lk_c& lk, CutKind kind, s16 aim) {
    switch (kind) {
    case CutKind::L:
        lk.procCutL_init(aim);
        return;
    case CutKind::F:
        lk.procCutF_init(aim);
        return;
    case CutKind::R:
        lk.procCutR_init(aim);
        return;
    case CutKind::EA:
        lk.procCutEA_init();
        return;
    case CutKind::EB:
        lk.procCutEB_init();
        return;
    }
}

}  // namespace

const CutSpec& cut_spec(CutKind kind) {
    for (const CutSpec& s : kSpecs) {
        if (s.kind == kind) {
            return s;
        }
    }
    return kSpecs[0];
}

std::vector<CutOracleRun> run_cut_oracle_replay(CutKind kind, const Json& golden,
                                                const CutOracleOptions& opt) {
    // JMANewSinTable(12) (m_Do_machine.cpp:614) with the console's table in its place;
    // cLib_addCalcAngleS is every cut's angle half.
    JMA_useConsoleSinTable();

    const CutSpec& spec = cut_spec(kind);
    std::vector<CutOracleRun> runs;
    const Json& scenarios = golden["scenarios"];
    for (size_t s = 0; s < scenarios.size(); s++) {
        const Json& sc = scenarios[s];
        const Json& rows = sc["frames"];
        const int entry = int(sc["entry"].as_int());
        const int exit = int(sc["exit"].as_int());

        CutOracleRun run;
        run.cut = spec.fn;
        run.name = sc["name"].str;
        run.covers = sc["covers"].str;
        run.entry = entry;
        run.exit = exit;

        // A fresh rig per scenario: each is its own old-sim run from its own initial state.
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        // Seeded from the entry row: these inits write no angle or speed (cut_oracle_replay.h),
        // so the entry row's columns are what the init saw.
        const Json& seed = rows[size_t(entry)];
        lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = hex_f32(seed["nspeed_hex"]);
        lk.speedF = hex_f32(seed["speedF_hex"]);
        lk.mStickDistance = hex_f32(seed["msd_hex"]);
        lk.m34E8 = (s16)seed["target_angle"].as_int();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        // The attention lock, driven: only `aim_locked` holds L, the one place changeCutProc's
        // argument is the facing rather than the stick target.
        lk.stub_attention_lock = seed["btn_l"].as_int() ? TRUE : FALSE;

        // checkNextActionFromButton's sword arm sits behind `mEquipItem == daPyItem_SWORD_e`, and
        // `b_held` leaves through it (`no_sword_equipped` is the control).
        lk.mEquipItem = opt.no_sword_equipped ? daPyItem_NONE_e : daPyItem_SWORD_e;
        lk.stub_select_equip[0] = dItemNo_SWORD_e;   // checkNormalSwordEquip reads slot 0

        // changeCutProc's argument, read from the golden: changeCutProc is not ported, and the
        // oracle recorded which of facing and stick target it chose. Enders take none
        // (`cut_target` is null) and it stays 0.
        const s16 aim = spec.has_aim
            ? (opt.wrong_init_aim ? lk.m34E8 : (s16)seed["cut_target"].as_int())
            : (s16)0;
        run_init(lk, kind, aim);
        run.hold_after_init = (int)lk.mProcVar0.m34D0;

        // The blade-flash animators before a body frame: procCutF_init seeds both from
        // field_0x8, the other inits leave reset_boundary's -1.
        run.cutf_bpk_init_bits = f32_bits(lk.mpCutfBpk->getFrame());
        run.cutf_btk_init_bits = f32_bits(lk.mpCutfBtk->getFrame());

        // Controls on the controller the init seeded, not on the copied body: field_0x2 is the
        // anim end (18 for CUT_L, 19 otherwise), field_0x4 the rate.
        if (opt.wrong_anim_end) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setEnd((s16)spec.wrong_end);
        }
        if (opt.wrong_anim_rate) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setRate(spec.wrong_rate);
        }
        lk.stub_cut_reverse = opt.cut_reverse_true ? TRUE : FALSE;

        // Read before a frame runs.
        {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            run.anim_attribute = (int)c0.getAttribute();
            run.anim_start = (int)c0.getStart();
            run.anim_end = (int)c0.getEnd();
        }

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            CutOracleFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.cutf_bpk_bits = f32_bits(lk.mpCutfBpk->getFrame());
            r.cutf_btk_bits = f32_bits(lk.mpCutfBtk->getFrame());
            run.rows.push_back(r);
        };
        emit(entry);

        for (int i = entry + 1; i <= exit; i++) {
            const Json& r = rows[size_t(i)];
            // Pad lead 0: the oracle takes inputs as arguments to the frame that acts on them.
            // `wrong_pad_lead` is the console replays' alignment.
            const Json& p = rows[size_t(opt.wrong_pad_lead ? i - 1 : i)];

            frame_top(lk);  // before the inputs: it carries m34DC forward into m34EA

            // speedF is the previous row's: posMove writes it (d_a_player_main.cpp:2422) after
            // the dispatch (11394, then 11400). The `moving` scenario tells the alignments apart.
            lk.speedF = hex_f32(rows[size_t(opt.wrong_speedf_lead ? i : i - 1)]["speedF_hex"]);
            lk.mStickDistance = hex_f32(r["msd_hex"]);
            lk.m34E8 = (s16)r["target_angle"].as_int();
            lk.m34DC = (s16)r["stick_angle_raw"].as_int();

            const bool b = !opt.no_b_hold && p["btn_b"].as_int() != 0;
            const bool rr = !opt.no_r_hold && p["btn_r"].as_int() != 0;
            lk.mItemButton = (u8)((b ? daPy_lk_c::BTN_B : 0) | (rr ? daPy_lk_c::BTN_R : 0));
            // The one-frame edge words, from the golden's columns: B's press started the cut, R's
            // is mDoCPd_R_LOCK_TRIGGER, the hold's rising edge.
            const bool b_was = rows[size_t(i - 1)]["btn_b"].as_int() != 0;
            const bool r_was = rows[size_t(i - 1)]["btn_r"].as_int() != 0;
            lk.mItemTrigger = (u8)(((b && !b_was) ? daPy_lk_c::BTN_B : 0) |
                                   ((rr && !r_was) ? daPy_lk_c::BTN_R : 0));
            lk.stub_attention_lock = p["btn_l"].as_int() ? TRUE : FALSE;

            // animeUpdate() (d_a_player_main.cpp:11346, 12881) advances the clocks before the
            // proc; each body reads the clock three times (rate test, `> field_0xC` exit,
            // checkPass).
            if (opt.proc_before_anim) {
                if (!run_proc(lk)) {
                    break;
                }
                lk.animeUpdate();
            } else {
                lk.animeUpdate();
                if (!run_proc(lk)) {
                    // A proc with no body: inside a run that is a disagreement, left as one.
                    break;
                }
            }
            if (i < exit) {
                emit(i);
                run.rnd_draws_compared = lk.rnd_draws;
            }
        }

        run.exit_proc = exit_proc_of(lk, spec, &run.exit_was_named);
        run.unreached_called = lk.unreached_called;
        run.precondition_broken = lk.precondition_broken;
        run.rnd_draws = lk.rnd_draws;
        run.anm_meta_missing = lk.anm_meta_missing;
        run.sword_anim_idx = lk.sword_anim_idx;
        run.blur_pos_idx = lk.blur_pos_idx;
        run.cut_at_param_type = lk.cut_at_param_type;
        run.sword_cut_se = lk.sword_cut_se;
        run.player_status0 = lk.player_status0;
        run.m34C5 = lk.m34C5;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
