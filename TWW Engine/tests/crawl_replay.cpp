#include "crawl_replay.h"

#include "player_rig.h"

#include "JSystem/JMath/JMath.h"
#include "engine/jma_console_table.h"
#include "d/actor/d_a_player_main.h"

#include <cmath>

namespace tww_engine {
namespace testing {
namespace {

const CrawlCapture kCaptures[kCrawlCaptures] = {
    //: The four-move demo. Two crawls, rows 110-137 and 156-179.
    {"demo", "setup_finder_demo_live.json", 0, NULL, 2, 39, 13, true},
    //: A crawl into Kaisen r0's z=800 wall. One crawl, rows 11-33; the only capture where the wall
    //: probe has anything to hit.
    {"crawl_wall", "setup_finder_crawl_wall_live.json", "log", "kaisen_r0_bgd.json",
     1, 18, 5, false},
};

//: g_HIO.mTriggerThreshLo and mTriggerThreshHi (f_ap_game.cpp:54-55): the two ends of the R latch
//: in m_Do_controller_pad.cpp:122-131:
//:
//:     if (trigR > threshold_lo)      { ...; mHoldLockR = true;  }
//:     else if (trigR < threshold_hi) { mHoldLockR = false; }
//:
//: The band between them holds the previous state. Other replays read it from `lock_r`; the crawl
//: captures lack that column.
const f32 kRLatchOn = 0.9f;
const f32 kRLatchOff = 0.6f;

//: The latch over a capture's `trigR` column: a fold, since each frame depends on the ones before.
std::vector<bool> r_latch(const Json& rows, bool naive) {
    std::vector<bool> out(rows.size(), false);
    bool held = false;
    for (size_t i = 0; i < rows.size(); i++) {
        const f32 t = rows[i]["trigR"].as_f32();
        if (naive) {
            held = t >= 1.0f;           // the slip the latch prevents
        } else if (t > kRLatchOn) {
            held = true;
        } else if (t < kRLatchOff) {
            held = false;
        }
        out[i] = held;
    }
    return out;
}

//: As cut_replay: the proc the port entered, or the proc it named.
int exit_proc_of(const daPy_lk_c& lk, bool* was_named) {
    if (lk.mCurProc != daPy_lk_c::daPyProc_CRAWL_START_e &&
        lk.mCurProc != daPy_lk_c::daPyProc_CRAWL_END_e) {
        *was_named = false;
        return lk.mCurProc;
    }
    *was_named = true;
    return lk.next_init;
}

}  // namespace

const CrawlCapture& crawl_capture(int id) {
    return kCaptures[id];
}

const Json& crawl_rows(const Json& doc, const CrawlCapture& cap) {
    return cap.rows_key ? doc[std::string(cap.rows_key)] : doc;
}

std::vector<int> crawl_entry_frames(const Json& rows) {
    std::vector<int> out;
    for (size_t f = 1; f < rows.size(); f++) {
        const bool here = rows[f]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_START_e;
        const bool before = rows[f - 1]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_START_e;
        if (here && !before) {
            out.push_back(int(f));
        }
    }
    return out;
}

std::vector<CrawlRun> run_crawl_replay(const Json& rows, const CrawlCapture& cap,
                                       const CrawlReplayOptions& opt) {
    // The console's own sin table, as cut_replay installs it.
    JMA_useConsoleSinTable();

    const std::vector<bool> held = r_latch(rows, opt.naive_r_threshold);
    std::vector<CrawlRun> runs;

    for (int entry : crawl_entry_frames(rows)) {
        CrawlRun run;
        run.entry = entry;

        // A fresh rig per run; between runs is crouch and wait, which this replay does not claim.
        // With a room only when the capture settles one (the wall capture: Kaisen r0, Link pushed
        // to z = 770.0001 against `wall_z` 800). The demo keeps an empty dBgS.
        Rig rig(cap.room);
        daPy_lk_c& lk = rig.lk;

        const Json& seed = rows[size_t(entry - 1)];
        run.from_proc = int(seed["proc"].as_int());

        // Enter the console's proc through commonProcInit rather than assigning mModeFlg, as
        // jump_land_replay does: checkNextMode reads mModeFlg on the exit frame.
        lk.commonProcInit(run.from_proc);

        lk.current.pos.x = seed["pos_x"].as_f32();
        lk.current.pos.y = seed["pos_y"].as_f32();
        lk.current.pos.z = seed["pos_z"].as_f32();
        // f_op_actor.cpp:196 ran before the seed too, so old.pos is the seed; the line check's
        // segment is old.pos -> current.pos.
        lk.old.pos = lk.current.pos;
        lk.mStickDistance = opt.stick_held ? 1.0f : seed["msd"].as_f32();
        // procCrawlStart_init writes `current.angle.y = shape_angle.y`. The two seed values are
        // equal on all three runs, so a case asserts that instead of a wrong-seed control.
        lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
        lk.current.angle.y = (s16)seed["travel_angle"].as_int();
        lk.mNormalSpeed = seed["potential_speed"].as_f32();
        lk.speedF = seed["true_speed"].as_f32();
        lk.m34DC = (s16)seed["stick_angle_raw"].as_int();
        // Only the crawl camera's bit: dCamAttnStts_00001000_e would take the crawl out through
        // procSubjectivity.
        lk.stub_camera_attn = opt.camera_attn ? (u32)dCamAttnStts_00000080_e : 0u;
        lk.stub_attention_lock = opt.attention_lock ? TRUE : FALSE;
        lk.mEquipItem = daPyItem_SWORD_e;
        lk.stub_select_equip[0] = dItemNo_SWORD_e;

        // execute():11400-11406 - posMove, `mOldSpeed = speed`, then the collision pass, all in
        // integrate() so a twin that removes one removes it everywhere. A room-less rig runs
        // neither: crr_pos() aborts on a null room.
        Room::FrameResult last_frame{};
        // execute():11544 - setWorldMatrix at the end of the frame. crawlBgCheck reads it on the
        // next frame; that one-frame lag is the decomp's. It runs room-less too, so the demo's
        // probe asks an empty dBgS rather than not being asked. Only this replay calls it: the
        // other ported reader, procJumpCutLand_init, hands it to the initSwBlur stub.
        auto world_matrix = [&]() {
            if (opt.no_world_matrix) {
                return;
            }
            lk.setWorldMatrix();
            lk.world_matrix_calls++;
            // Did PSMTXInverse run: a zero m37B4 is a setWorldMatrix whose last line did nothing.
            if (lk.m37B4[0][0] != 0.0f || lk.m37B4[0][1] != 0.0f || lk.m37B4[0][2] != 0.0f ||
                lk.m37B4[2][0] != 0.0f || lk.m37B4[2][1] != 0.0f || lk.m37B4[2][2] != 0.0f) {
                run.world_inverse_frames++;
            }
        };
        auto integrate = [&]() {
            if (!cap.room) {
                world_matrix();
                return;
            }
            run.integrated_frames++;
            // A pure predicate, asked beside posMove because a copied body cannot count itself.
            if (lk.checkNoCollisionCorret()) {
                run.no_collision_corret_frames++;
            }
            if (lk.mCurProc == daPy_lk_c::daPyProc_CRAWL_END_e) {
                run.crawl_end_integrated++;
            }
            if (!opt.no_pos_move) {
                pos_move(lk);
            }
            if (!opt.no_crr_pos) {
                last_frame = crr_pos(rig);
                if (last_frame.wall_hit) {
                    run.wall_hit_frames++;
                }
                if (last_frame.ran_line_check) {
                    run.line_check_frames++;
                }
            }
            world_matrix();
        };

        lk.procCrawlStart_init();
        // The entry frame's own integration: 11394 dispatches into the init and 11400 posMoves
        // in the same frame, so the entry row is after both.
        integrate();

        auto emit = [&](int frame) {
            const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
            const J3DFrameCtrl& c1 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE1_e];
            CrawlFrame r;
            r.pos_recorded = cap.room != NULL;
            r.pos_x_bits = f32_bits(lk.current.pos.x);
            r.pos_y_bits = f32_bits(lk.current.pos.y);
            r.pos_z_bits = f32_bits(lk.current.pos.z);
            r.ground_poly = last_frame.ground_poly;
            r.ground_hit = last_frame.ground_hit;
            r.wall_hit = last_frame.wall_hit;
            r.line_hit = last_frame.line_hit;
            r.m34c2 = (int)lk.m34C2;
            r.frame = frame;
            r.proc = lk.mCurProc;
            r.anim_bits = f32_bits(c0.getFrame());
            r.rate_bits = f32_bits(c0.getRate());
            r.end = (int)c0.getEnd();
            r.nspeed_bits = f32_bits(lk.mNormalSpeed);
            r.speedf_bits = f32_bits(lk.speedF);
            r.shape_angle_y = (int)(u16)lk.shape_angle.y;
            r.travel_angle = (int)(u16)lk.current.angle.y;
            r.m1frame_bits = f32_bits(c1.getFrame());
            r.phase_bits = f32_bits(lk.m35E4);
            r.a_status = lk.a_status;
            r.r_held = frame >= 0 && size_t(frame) < held.size() && held[size_t(frame)];
            run.rows.push_back(r);
        };
        emit(entry);

        if (opt.loop_crawl_anim) {
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setAttribute(J3DFrameCtrl::EMode_LOOP);
        }

        // Where the console's run ends: the first frame that is neither crawl proc.
        int f = entry + 1;
        while (f < int(rows.size())) {
            const int p = int(rows[size_t(f)]["proc"].as_int());
            if (p == daPy_lk_c::daPyProc_CRAWL_END_e && run.console_crawl_up < 0) {
                run.console_crawl_up = f;
            }
            if (p != daPy_lk_c::daPyProc_CRAWL_START_e && p != daPy_lk_c::daPyProc_CRAWL_END_e) {
                break;
            }
            f++;
        }
        run.exit = f;
        if (f < int(rows.size())) {
            run.console_exit_proc = int(rows[size_t(f)]["proc"].as_int());
        }

        for (int i = entry + 1; i <= run.exit; i++) {
            const Json& r = rows[size_t(i)];
            const int pi = i - opt.pad_lead;

            // f_op_actor.cpp:196, one call further out than frame_top and before it.
            actor_old_set(lk);
            frame_top(lk);

            lk.mStickDistance = opt.stick_held ? 1.0f : r["msd"].as_f32();
            lk.m34DC = (s16)r["stick_angle_raw"].as_int();
            // m34E8 is setStickData's target angle. The wall capture has no column, so `csangle`
            // stands in (what the target decays to with the stick centred); `m34E8_far` controls it.
            const s16 target = (s16)(cap.has_target_angle ? r["target_angle"].as_int()
                                                          : r["csangle"].as_int());
            lk.m34E8 = (s16)(opt.m34E8_far ? (int)(target + 0x8000) : (int)target);
            stick_accumulate(lk);

            // The R latch, pad_lead frames behind (as roll_replay.h). mItemTrigger's R is the
            // latch's rising edge (mDoCPd_R_LOCK_TRIGGER).
            bool r_now = pi >= 0 && held[size_t(pi)];
            bool r_prev = pi >= 1 && held[size_t(pi - 1)];
            if (opt.r_held_forever) {
                r_now = r_prev = true;
            }
            if (opt.r_held_through_crawl_up && lk.mCurProc == daPy_lk_c::daPyProc_CRAWL_END_e) {
                r_now = r_prev = true;
            }
            lk.mItemButton = (u8)(r_now ? daPy_lk_c::BTN_R : 0);
            lk.mItemTrigger = (u8)((r_now && !r_prev) ? daPy_lk_c::BTN_R : 0);

            lk.animeUpdate();

            const int before = lk.mCurProc;
            // crawlBgCheck's push: the only write to current.pos inside run_proc.
            const cXyz pos_before_proc = lk.current.pos;
            if (!run_proc(lk)) {
                // A proc with no body here: stop and name it.
                run.stopped_on_proc = lk.mCurProc;
                break;
            }
            if (before == daPy_lk_c::daPyProc_CRAWL_START_e &&
                lk.mCurProc == daPy_lk_c::daPyProc_CRAWL_END_e)
            {
                run.crawl_up = i;
                // Read at the init: a short crawl-up's exit frame re-inits the controller.
                run.clamp_bits = f32_bits(lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].getFrame());
                run.clamped = true;
                run.anm_transform_calls = lk.anm_transform_calls;
                if (opt.no_crawl_end_clamp) {
                    // procCrawlEnd_init's `param_1 == 0` block undone: back to field_0x44 = 0.0.
                    lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setFrame(
                        lk.m_HIO->mCrouch.m.field_0x44);
                }
                if (opt.loop_crawl_anim) {
                    lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setAttribute(
                        J3DFrameCtrl::EMode_LOOP);
                }
            }
            {
                const f32 dx = lk.current.pos.x - pos_before_proc.x;
                const f32 dy = lk.current.pos.y - pos_before_proc.y;
                const f32 dz = lk.current.pos.z - pos_before_proc.z;
                if (dx != 0.0f || dy != 0.0f || dz != 0.0f) {
                    run.push_frames++;
                    run.push_total += std::sqrt(dx * dx + dy * dy + dz * dz);
                }
            }
            integrate();
            if (i < run.exit) {
                emit(i);
                run.rnd_draws_compared = lk.rnd_draws;
                run.anm_meta_missing = lk.anm_meta_missing;
            }
        }

        run.exit_proc = exit_proc_of(lk, &run.exit_was_named);
        run.unreached_called = lk.unreached_called;
        run.precondition_broken = lk.precondition_broken;
        run.rnd_draws = lk.rnd_draws;
        run.body_angle_calls = lk.body_angle_calls;
        run.subject_end_calls = lk.subject_end_calls;
        run.subject_mode_calls = lk.subject_mode_calls;
        run.crawl_move_init_calls = lk.crawl_move_init_calls;
        run.base_tr_mtx_calls = lk.base_tr_mtx_calls;
        run.world_matrix_calls = lk.world_matrix_calls;
            run.ship_actor_calls = lk.ship_actor_calls;
        run.player_status0 = lk.player_status0;
        run.cc_move_asks = lk.cc_move_asks;
        {
            const J3DTransformInfo* t = lk.m_old_fdata->getOldFrameTransInfo(0);
            run.old_frame_trans_bits[0] = f32_bits(t->mTranslate.x);
            run.old_frame_trans_bits[1] = f32_bits(t->mTranslate.y);
            run.old_frame_trans_bits[2] = f32_bits(t->mTranslate.z);
        }
        runs.push_back(run);
    }
    return runs;
}

}  // namespace testing
}  // namespace tww_engine
