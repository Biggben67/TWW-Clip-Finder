#include "jump_land_replay.h"

#include "player_rig.h"
#include "roll_replay.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

namespace tww_engine {
namespace testing {
namespace {

//: cPadInfo +0x30 / +0x32's bits (roll_replay.cpp).
enum : int { kCpadB = 0x0080 };

//: The two pairs.
const JumpLandPair kPairs[kJumpLandPairs] = {
    //: The backflip: four runs in rows 449..785. voiceStart(7) is procBackJump_init's.
    {"BACK_JUMP", daPy_lk_c::daPyProc_BACK_JUMP_e, daPy_lk_c::daPyProc_BACK_JUMP_LAND_e,
     400, 800, 4, 48, 16, 7, true, false},
    //: The jump slash: three runs in rows 520..691, landing frames split 14/1/1. voiceStart(1) is
    //: procJumpCut_init's.
    {"JUMP_CUT", daPy_lk_c::daPyProc_JUMP_CUT_e, daPy_lk_c::daPyProc_JUMP_CUT_LAND_e,
     500, 750, 3, 54, 16, 1, false, true},
};

//: The proc the port entered, or the proc it named (cut_replay.h).
int exit_proc_of(const daPy_lk_c& lk, const JumpLandPair& pair, bool* was_named) {
    if (lk.mCurProc != pair.jump_proc && lk.mCurProc != pair.land_proc) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

/// Whether the collision pass said ground on frame `f`, off `speed_y` and `gravity`.
///
/// CrrPos zeroes speed.y in the pass that raises the flag, so a zero is its signature, except
/// where gravity alone gives the same zero (27.0 stepped by -3.0 hits 0.0 at the apex):
///
///     zero, and `speed_y[f-1] + gravity[f-1]` is not also zero
///
/// Over all 849 rows the second term removes exactly the three jump-slash apexes. Not the `proc`
/// column, which is the answer. The caller reads it one frame behind: execute() runs the proc
/// before posMove/CrrPos.
bool console_ground_hit(const Json& g, int f, bool naive) {
    if (f < 0 || g[size_t(f)]["speed_y"].as_f32_bits() != f32_bits(0.0f)) {
        return false;
    }
    if (naive || f < 1) {
        return true;
    }
    const f32 fell = g[size_t(f - 1)]["speed_y"].as_f32() + g[size_t(f - 1)]["gravity"].as_f32();
    return f32_bits(fell) != f32_bits(0.0f);
}

//: The pair's entry init. procJumpCut_init(0) is the ground route (d_a_player_main.cpp:4176, the
//: only call site ported); 1 is checkJumpCutFromButton's airborne press. All three captured runs
//: enter from the ground, so the other half of the HIO row is unexercised.
void enter(daPy_lk_c& lk, int pair_id) {
    if (pair_id == kPairBackJump) {
        lk.procBackJump_init();
    } else {
        lk.procJumpCut_init(0);
    }
}

}  // namespace

const JumpLandPair& jump_land_pair(int id) {
    return kPairs[id];
}

std::vector<int> jump_land_entry_frames(const Json& golden, const JumpLandPair& pair) {
    std::vector<int> out;
    for (int f = pair.first_frame; f <= pair.last_frame; f++) {
        const bool here = golden[size_t(f)]["proc"].as_int() == pair.jump_proc;
        const bool before = golden[size_t(f - 1)]["proc"].as_int() == pair.jump_proc;
        if (here && !before) {
            out.push_back(f);
        }
    }
    return out;
}

std::vector<JumpLandRun> run_jump_land_replay(const Json& golden, int pair_id,
                                              const JumpLandReplayOptions& opt) {
    // The console's sin table, as cut_replay installs it.
    JMA_useConsoleSinTable();

    const JumpLandPair& pair = kPairs[pair_id];
    std::vector<JumpLandRun> runs;
    for (int entry : jump_land_entry_frames(golden, pair)) {
        JumpLandRun run;
        run.entry = entry;

        // A fresh rig per run; nothing between runs is claimed.
        Rig rig;
        daPy_lk_c& lk = rig.lk;

        const Json& seed = golden[size_t(entry - 1)];
        run.from_proc = int(seed["proc"].as_int());

        // Enter the console's proc through the port's commonProcInit: it latches m3688 and m35F0
        // only on a ground-to-midair change, and resets gravity to -2.5 as the seed row reads.
        lk.commonProcInit(run.from_proc);

        lk.current.pos.x = seed["pos_x"].as_f32();
        lk.current.pos.y = seed["pos_y"].as_f32();
        lk.current.pos.z = seed["pos_z"].as_f32();
        lk.mStickDistance = seed["msd"].as_f32();
        // Every init writes current.angle.y from shape_angle.y, so the facing seeds from
        // shape_angle_y.
        lk.shape_angle.y = (s16)(opt.wrong_seed_shape_angle ? seed["travel_angle"].as_int()
                                                            : seed["shape_angle_y"].as_int());
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = seed["potential_speed"].as_f32();
        lk.speedF = seed["true_speed"].as_f32();
        lk.m34E8 = (s16)seed["target_angle"].as_int();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        lk.stub_attention_lock = seed["lock_l"].as_int() ? TRUE : FALSE;
        lk.stub_heavy_state = opt.heavy_state ? TRUE : FALSE;
        lk.stub_cut_reverse = opt.cut_reverse_true ? TRUE : FALSE;

        if (!opt.no_sword) {
            lk.mEquipItem = daPyItem_SWORD_e;
            lk.stub_select_equip[0] = dItemNo_SWORD_e;
        }

        // execute()'s posMove: 11394 dispatches the proc and 11400 calls posMove, so it runs after
        // the body on every frame including the entry, where the body is the init (19.0 -> 16.0).
        auto integrate = [&](daPy_lk_c& p) {
            if (opt.no_pos_move) {
                return;
            }
            // mDoExt_MtxCalcOldFrame has onOldFrameFlg() and no `off`, so the low state is a second
            // object that was never raised.
            mDoExt_MtxCalcOldFrame not_ready(p.port_old_trans, p.port_old_quat);
            mDoExt_MtxCalcOldFrame* const saved = p.m_old_fdata;
            if (opt.skeleton_not_ready) {
                p.m_old_fdata = &not_ready;
            }
            pos_move(p);
            p.m_old_fdata = saved;
            if (opt.integrate_before_gravity) {
                // `current.pos += speed` run ahead of `speed.y += gravity`: one gravity step back.
                p.current.pos.y -= p.gravity;
            }
        };

        enter(lk, pair_id);
        integrate(lk);
        // Read at the init: a spin's exit fires procCutTurn_init's own voiceStart.
        run.voice_id = lk.voice_id;

        // m3688 feeds procBackJump's drop arm, m35F0 procJumpCutLand_init's fall damage.
        if (opt.no_launch_pos) {
            lk.m3688.x = lk.m3688.y = lk.m3688.z = 0.0f;
        }
        if (opt.no_launch_height) {
            lk.m35F0 = 0.0f;
        }
        // The airborne .bck's attribute replaced by EMode_LOOP.
        if (opt.loop_jump_anim) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setAttribute(J3DFrameCtrl::EMode_LOOP);
        }

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            JumpLandFrame r;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.gravity_bits = f32_bits(lk.gravity);
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.speed_y_bits = f32_bits(lk.speed.y);
            r.pos_x_bits = f32_bits(lk.current.pos.x);
            r.pos_y_bits = f32_bits(lk.current.pos.y);
            r.pos_z_bits = f32_bits(lk.current.pos.z);
            r.foot_delta_bits = f32_bits(lk.m359C);
            r.blend_bits = f32_bits(lk.m3598);
            r.stick_rotation = lk.m3578;
            run.rows.push_back(r);
        };
        emit(entry);

        // Where the console's run ends: the first frame that is neither proc.
        int f = entry + 1;
        while (f < int(golden.size())) {
            const int p = int(golden[size_t(f)]["proc"].as_int());
            if (p == pair.land_proc && run.console_land < 0) {
                run.console_land = f;
            }
            if (p != pair.jump_proc && p != pair.land_proc) {
                break;
            }
            f++;
        }
        run.exit = f;

        for (int i = entry + 1; i <= run.exit; i++) {
            const Json& r = golden[size_t(i)];
            const Json& p = golden[size_t(i - opt.pad_lead)];

            frame_top(lk);

            lk.mStickDistance = r["msd"].as_f32();
            lk.m34E8 = (s16)r["target_angle"].as_int();
            lk.m34DC = (s16)r["stick_angle_raw"].as_int();
            if (!opt.no_stick_rotation) {
                stick_accumulate(lk);
            }

            lk.mItemButton = (u8)((p["lock_r"].as_int() ? daPy_lk_c::BTN_R : 0) |
                                  ((p["btn_hold"].as_int() & kCpadB) ? daPy_lk_c::BTN_B : 0));
            lk.mItemTrigger = item_trigger_for(golden, i - opt.pad_lead);
            lk.stub_attention_lock = p["lock_l"].as_int() ? TRUE : FALSE;

            // The one input this replay invents, and the three controls on it.
            const int gh_frame = i - 1 - (opt.late_ground_hit ? 1 : 0);
            if (!opt.no_ground_hit && console_ground_hit(golden, gh_frame, opt.naive_ground_hit)) {
                lk.mAcch.SetGroundHit();
            } else {
                lk.mAcch.ClrGroundHit();
            }

            lk.animeUpdate();

            const int before = lk.mCurProc;
            // The quickspin poll: reached only on the landing's first body frame, which on a spin
            // is also the exit and emits no row, so it is taken here.
            if (before == pair.land_proc && !run.polled) {
                run.polled = true;
                run.rotation_at_poll = lk.m3578;
            }
            if (!run_proc(lk)) {
                break;
            }
            // execute(): posMove after the proc (11394 / 11400), before the row is emitted.
            integrate(lk);
            if (before == pair.jump_proc && lk.mCurProc == pair.land_proc) {
                run.land = i;
                // Read at the landing's init: the exit may call procCutTurn_init, which overwrites
                // these.
                run.foot_effect_type = lk.foot_effect_type;
                run.reset_flg0 = lk.mResetFlg0;
                run.m3570_at_land = lk.mProcVar6.m3570;
                run.cut_at_param_type = lk.cut_at_param_type;
                run.damage_calls = lk.damage_calls;
                run.damage_amount = lk.damage_amount;
                run.sw_blur_calls = lk.sw_blur_calls;
                run.sw_blur_frames = lk.sw_blur_frames;
                run.sw_blur_top_rate = lk.sw_blur_top_rate;
                run.sw_blur_color = lk.sw_blur_color;
                run.base_tr_mtx_calls = lk.base_tr_mtx_calls;
                run.hammer_quake_calls = lk.hammer_quake_calls;
                // The landing's own init installed the controller this perturbs, so it is applied
                // here.
                if (opt.loop_land_anim) {
                    lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setAttribute(
                        J3DFrameCtrl::EMode_LOOP);
                }
            }
            if (i < run.exit) {
                emit(i);
                run.rnd_draws_compared = lk.rnd_draws;
                run.anm_meta_missing = lk.anm_meta_missing;
            }
        }

        run.exit_proc = exit_proc_of(lk, pair, &run.exit_was_named);
        run.unreached_called = lk.unreached_called;
        run.precondition_broken = lk.precondition_broken;
        run.rnd_draws = lk.rnd_draws;
        run.fan_glide_calls = lk.fan_glide_calls;
        run.fall_init_calls = lk.fall_init_calls;
        run.cut_reverse_calls = lk.cut_reverse_calls;
        run.evmng_cut_end_calls = lk.evmng_cut_end_calls;
        run.shock_calls = lk.shock_calls;
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
