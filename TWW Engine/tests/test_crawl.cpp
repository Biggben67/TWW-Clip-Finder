// test_crawl.cpp - procCrawlStart / procCrawlEnd against two console captures, and the controls.
//
// Position is compared in test_crawl_pos.cpp. setDoStatusCrawl's camera arm writes only
// mBodyAngle, which nothing here reads; the_camera_arm_moves_no_column checks that.
// Neither capture has `lock_r`, so the R latch is built from the decomp's 0.9 on / 0.6 off band
// (f_ap_game.cpp:54-55).

#include <string>
#include <vector>

#include "crawl_replay.h"
#include "player_rig.h"
#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"
#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CrawlCapture;
using tww_engine::testing::CrawlFrame;
using tww_engine::testing::CrawlReplayOptions;
using tww_engine::testing::CrawlRun;
using tww_engine::testing::Json;

/// procCrawlEnd_init's clamp, spelled as the f32 subtraction so a port that rounds it differently
/// (in double, say) fails.
f32 crawl_end_clamp(const daPy_HIO_c& hio) {
    return hio.mCrouch.m.field_0xE - 0.001f;
}

std::string at(int frame, const char* column) {
    return "frame " + std::to_string(frame) + " " + column;
}

std::string run_at(const CrawlRun& run) {
    return " in the run entered at " + std::to_string(run.entry);
}

const Json& rows_of(int id) {
    const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
    return tww_engine::testing::crawl_rows(tww_engine::testing::golden(cap.golden), cap);
}

std::vector<CrawlRun> replay(int id, const CrawlReplayOptions& opt) {
    const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
    return tww_engine::testing::run_crawl_replay(rows_of(id), cap, opt);
}

/// The port's frames against every run of every capture; position is not compared here.
/// `perturb` moves the expected anim_frame by one ULP on that (capture, frame).
void compare(Case& c, const std::vector<std::vector<CrawlRun>>& all,
             int perturb_capture = -1, int perturb_frame = -1) {
    int compared = 0;
    std::string first_bad;
    int bad = 0;
    auto watch = [&](bool ok, const std::string& where) {
        if (!ok) {
            bad++;
            if (first_bad.empty()) {
                first_bad = where;
            }
        }
    };
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        const tww_engine::testing::Tier tier = tww_engine::testing::golden_tier(cap.golden);
        const Json& g = rows_of(id);
        for (const CrawlRun& run : all[size_t(id)]) {
            for (const CrawlFrame& row : run.rows) {
                const Json& want = g[size_t(row.frame)];
                const int want_proc = int(want["proc"].as_int());
                const std::string tag = std::string(cap.name) + " ";

                uint32_t want_anim = want["anim_frame"].as_f32_bits();
                if (id == perturb_capture && row.frame == perturb_frame) {
                    want_anim += 1;   // the red control: one ULP, on one frame
                }
                REQUIRE_BITS_RAW(c, row.anim_bits, want_anim, tag + at(row.frame, "anim_frame"));
                watch(row.anim_bits == want_anim, tag + at(row.frame, "anim_frame"));
                REQUIRE_BITS_RAW(c, row.rate_bits, want["fc_rate"].as_f32_bits(),
                                 tag + at(row.frame, "fc_rate"));
                watch(row.rate_bits == want["fc_rate"].as_f32_bits(),
                      tag + at(row.frame, "fc_rate"));
                REQUIRE_BITS_RAW(c, row.nspeed_bits, want["potential_speed"].as_f32_bits(),
                                 tag + at(row.frame, "mNormalSpeed"));
                watch(row.nspeed_bits == want["potential_speed"].as_f32_bits(),
                      tag + at(row.frame, "mNormalSpeed"));
                REQUIRE_BITS_RAW(c, row.speedf_bits, want["true_speed"].as_f32_bits(),
                                 tag + at(row.frame, "speedF"));
                watch(row.speedf_bits == want["true_speed"].as_f32_bits(),
                      tag + at(row.frame, "speedF"));
                REQUIRE_INT(c, row.end, want["fc_end"].as_int(), tag + at(row.frame, "fc_end"));
                watch(row.end == want["fc_end"].as_int(), tag + at(row.frame, "fc_end"));
                REQUIRE_INT(c, row.proc, want_proc, tag + at(row.frame, "proc"));
                watch(row.proc == want_proc, tag + at(row.frame, "proc"));
                REQUIRE_INT(c, row.shape_angle_y, want["shape_angle_y"].as_int(),
                            tag + at(row.frame, "shape_angle_y"));
                watch(row.shape_angle_y == want["shape_angle_y"].as_int(),
                      tag + at(row.frame, "shape_angle_y"));
                REQUIRE_INT(c, row.travel_angle, want["travel_angle"].as_int(),
                            tag + at(row.frame, "travel_angle"));
                watch(row.travel_angle == want["travel_angle"].as_int(),
                      tag + at(row.frame, "travel_angle"));

                // 4 bit comparisons and 4 integer ones per frame.
                tww_engine::testing::ledger_record(want_proc, tier, 4, 4);
                compared++;
            }

            // The exit, against the capture's proc on the first frame that is neither crawl proc.
            REQUIRE_INT(c, run.exit_proc, run.console_exit_proc,
                        std::string(cap.name) + " " +
                            at(run.exit, "the proc the port left the crawl for"));
            watch(run.exit_proc == run.console_exit_proc,
                  std::string(cap.name) + " " +
                      at(run.exit, "the proc the port left the crawl for"));
        }
    }
    c.note("compared " + std::to_string(compared) +
           " CRAWL_START / CRAWL_END frame(s) over both captures");
    if (bad > 0) {
        c.note(std::to_string(bad) + " column(s) disagree, first at " + first_bad);
    }
}

std::vector<std::vector<CrawlRun>> replay_all(const CrawlReplayOptions& opt) {
    std::vector<std::vector<CrawlRun>> out;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        out.push_back(replay(id, opt));
    }
    return out;
}

// --------------------------------------------------------------------------- 0. what is in there

TWWE_TEST(the_two_captures_hold_three_crawls_and_both_of_the_crawl_ups_two_lengths,
          "the gate could pass on three runs that all left the crawl-up the same way") {
    int start_frames = 0, end_frames = 0, runs = 0, long_ups = 0, short_ups = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        const Json& g = rows_of(id);
        std::vector<int> entries = tww_engine::testing::crawl_entry_frames(g);
        REQUIRE_INT(c, (long long)entries.size(), cap.runs,
                    std::string(cap.name) + ": CRAWL_START runs its proc column holds");
        int s = 0, e = 0;
        for (int entry : entries) {
            int f = entry;
            while (f < int(g.size()) &&
                   g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_START_e) {
                s++;
                f++;
            }
            int up = 0;
            while (f < int(g.size()) &&
                   g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_END_e) {
                up++;
                f++;
            }
            e += up;
            // checkNextMode(1): R released, the clock runs out (8 frames); R held, it dispatches
            // on the first frame below field_0x48 = 3.0 (5 frames).
            if (up >= 8) {
                long_ups++;
            } else {
                short_ups++;
            }
            runs++;
        }
        REQUIRE_INT(c, s, cap.start_frames, std::string(cap.name) + ": CRAWL_START frames");
        REQUIRE_INT(c, e, cap.end_frames, std::string(cap.name) + ": CRAWL_END frames");
        start_frames += s;
        end_frames += e;
    }
    REQUIRE_INT(c, start_frames, 57, "CRAWL_START frames across both captures");
    REQUIRE_INT(c, end_frames, 18, "CRAWL_END frames across both captures");
    REQUIRE_INT(c, runs, 3, "crawls across both captures");
    // Both exits must occur in the data.
    REQUIRE_TRUE(c, long_ups > 0,
                 "no crawl-up ran its clock out - checkNextMode(1)'s early return is unrun");
    REQUIRE_TRUE(c, short_ups > 0,
                 "every crawl-up ran its clock out - checkNextMode(1)'s dispatch is unrun");
    c.note("crawl-ups: " + std::to_string(long_ups) + " that ran the clock out (R released), " +
           std::to_string(short_ups) + " that dispatched below field_0x48 (R held)");
}

TWWE_TEST(the_crawl_move_arm_is_asked_with_each_of_its_two_terms_live,
          "procCrawlMove_init's zero would be a default rather than a measurement") {
    // `mStickDistance > 0.05f && (getRate() < 0.01f || getFrame() > field_0x28)` never fires on
    // either capture; each half must still be true somewhere the other is false.
    int stick_live = 0, clock_live = 0, both = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const Json& g = rows_of(id);
        for (size_t i = 0; i < g.size(); i++) {
            if (g[i]["proc"].as_int() != daPy_lk_c::daPyProc_CRAWL_START_e) {
                continue;
            }
            const bool stick = g[i]["msd"].as_f32() > 0.05f;
            const bool clock = g[i]["fc_rate"].as_f32() < 0.01f ||
                               g[i]["anim_frame"].as_f32() > 7.0f;   // field_0x28
            if (stick && !clock) {
                stick_live++;
            }
            if (clock && !stick) {
                clock_live++;
            }
            if (stick && clock) {
                both++;
            }
        }
    }
    REQUIRE_TRUE(c, stick_live > 0, "the stick term is never true on a frame the clock term is not");
    REQUIRE_TRUE(c, clock_live > 0, "the clock term is never true on a frame the stick term is not");
    REQUIRE_INT(c, both, 0, "the capture does take the crawl-move arm - the port list is wrong");
    c.note("crawl-move arm: stick alone on " + std::to_string(stick_live) +
           " row(s), clock alone on " + std::to_string(clock_live) +
           " row(s), both on 0 - so the arm is asked with each half live and answers no");
}

// ------------------------------------------------------------------------------- 1. the replay

TWWE_TEST(the_crawl_and_its_crawl_up_are_bit_exact_against_the_console,
          "the ported pair no longer reproduces either console capture, bit for bit") {
    std::vector<std::vector<CrawlRun>> all = replay_all(CrawlReplayOptions{});
    daPy_HIO_c hio;

    int runs = 0, frames = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        REQUIRE_INT(c, (long long)all[size_t(id)].size(), cap.runs,
                    std::string(cap.name) + ": runs replayed");
        for (const CrawlRun& run : all[size_t(id)]) {
            const std::string where = std::string(cap.name) + run_at(run);
            runs++;
            frames += int(run.rows.size());

            REQUIRE_INT(c, run.stopped_on_proc, -1,
                        "the replay stopped on a proc with no body" + where);
            REQUIRE_INT(c, (long long)run.rows.size(), run.exit - run.entry,
                        "frames replayed" + where);
            REQUIRE_INT(c, run.unreached_called, 0, "UNREACHED stubs called" + where);
            REQUIRE_INT(c, run.precondition_broken, 0,
                        "stubs called outside their proof's regime" + where);
            REQUIRE_INT(c, run.rnd_draws_compared, 0, "RNG draws over the compared frames" + where);

            // procCrawlStart calls procCrawlEnd_init on the frame R goes, so this checks the latch.
            REQUIRE_INT(c, run.crawl_up, run.console_crawl_up,
                        "the frame the port entered the crawl-up on" + where);

            // The console holds the clamp on the first crawl-up row of every run.
            REQUIRE_TRUE(c, run.clamped, "the port never entered the crawl-up" + where);
            REQUIRE_BITS_RAW(c, run.clamp_bits,
                             tww_engine::testing::f32_bits(crawl_end_clamp(hio)),
                             "the frame procCrawlEnd_init clamped to" + where);

            // In the game this bit makes the camera raise 0x80 a frame later.
            REQUIRE_TRUE(c, (run.player_status0 & daPyStts0_CRAWL_e) != 0,
                         "procCrawlStart_init did not raise daPyStts0_CRAWL_e" + where);

            // Four fetches per body frame: two for procCrawlStart's own offsets, two in
            // crawlBgCheck.
            const int body_frames = run.crawl_up - run.entry;
            REQUIRE_INT(c, run.base_tr_mtx_calls, 4 * body_frames,
                        "getBaseTRMtx fetches" + where);
            // crawlBgCheck's push on current.pos: none on the demo (no room loaded), some on the
            // wall capture (Kaisen r0).
            c.note("crawlBgCheck pushed current.pos on " + std::to_string(run.push_frames) +
                   " frame(s), " + std::to_string(run.push_total) + " units in total" + where);
            REQUIRE_INT(c, run.push_frames > 0 ? 1 : 0, cap.room ? 1 : 0,
                        "crawlBgCheck's push against whether this run's rig has a room at all"
                            + where);
            REQUIRE_INT(c, run.crawl_move_init_calls, 0,
                        "procCrawlMove_init was called - the stick arm fired" + where);
            // procCrawlEnd_init's one call, plus posMove's one per frame when a room is loaded.
            REQUIRE_INT(c, run.anm_transform_calls, cap.room ? body_frames + 1 : 1,
                        "getTransform calls at the crawl-up's init" + where);

            // `stub_camera_attn` is false here; the_camera_arm_moves_no_column drives it true.
            REQUIRE_INT(c, run.body_angle_calls, 0,
                        "setBodyAngleToCamera was called with the camera status false" + where);
            REQUIRE_INT(c, run.subject_end_calls, 0, "checkSubjectEnd asks" + where);
            REQUIRE_INT(c, run.subject_mode_calls, 0, "setSubjectMode asks" + where);
        }
    }
    REQUIRE_INT(c, runs, 3, "crawls replayed across both captures");
    REQUIRE_INT(c, frames, 57 + 18,
                "frames replayed - every crawl row of both captures, the exit row excluded "
                "because it is compared as exit_proc instead");
    compare(c, all);
}

TWWE_TEST(move1_is_frozen_for_the_whole_crawl_on_both_the_console_and_the_port,
          "setSingleMoveAnime or animeUpdate touched MOVE1, which the console's own column denies") {
    // MOVE1 is never seeded, so only its not moving is checked: animeUpdate skips it while
    // mAnmRatioUnder[1] is NULL, and the console's move1_frame is frozen on every crawl row.
    std::vector<std::vector<CrawlRun>> all = replay_all(CrawlReplayOptions{});
    int checked = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const Json& g = rows_of(id);
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        for (const CrawlRun& run : all[size_t(id)]) {
            const uint32_t console0 = g[size_t(run.entry)]["move1_frame"].as_f32_bits();
            const uint32_t port0 = run.rows.front().m1frame_bits;
            for (const CrawlFrame& row : run.rows) {
                REQUIRE_BITS_RAW(c, g[size_t(row.frame)]["move1_frame"].as_f32_bits(), console0,
                                 std::string(cap.name) + " " +
                                     at(row.frame, "the console's move1_frame moved"));
                REQUIRE_BITS_RAW(c, row.m1frame_bits, port0,
                                 std::string(cap.name) + " " +
                                     at(row.frame, "the port's move1_frame moved"));
                checked++;
            }
        }
    }
    c.note("MOVE1 frozen on " + std::to_string(checked) + " row(s), both engines");
}

// --------------------------------------------------------------- 2. what the pair does not settle

TWWE_TEST(the_camera_arm_moves_no_column,
          "setDoStatusCrawl's camera arm reaches a compared column, so the READ grade is wrong") {
    // setBodyAngleToCamera writes only mBodyAngle: with the camera status on and off, every
    // compared column must be bit-identical. On the console the arm is reached (the camera raises
    // 0x80 from daPyStts0_CRAWL_e, d_camera.cpp:4264).
    CrawlReplayOptions on;
    on.camera_attn = true;
    std::vector<std::vector<CrawlRun>> with = replay_all(on);
    std::vector<std::vector<CrawlRun>> without = replay_all(CrawlReplayOptions{});

    int frames = 0, asks = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        REQUIRE_INT(c, (long long)with[size_t(id)].size(),
                    (long long)without[size_t(id)].size(),
                    std::string(cap.name) + ": runs, both ways");
        for (size_t r = 0; r < with[size_t(id)].size(); r++) {
            const CrawlRun& a = with[size_t(id)][r];
            const CrawlRun& b = without[size_t(id)][r];
            const std::string where = std::string(cap.name) + run_at(a);
            REQUIRE_INT(c, (long long)a.rows.size(), (long long)b.rows.size(),
                        "frames, both ways" + where);
            for (size_t i = 0; i < a.rows.size() && i < b.rows.size(); i++) {
                REQUIRE_BITS_RAW(c, a.rows[i].anim_bits, b.rows[i].anim_bits,
                                 at(a.rows[i].frame, "anim_frame, camera on vs off"));
                REQUIRE_BITS_RAW(c, a.rows[i].rate_bits, b.rows[i].rate_bits,
                                 at(a.rows[i].frame, "fc_rate, camera on vs off"));
                REQUIRE_BITS_RAW(c, a.rows[i].nspeed_bits, b.rows[i].nspeed_bits,
                                 at(a.rows[i].frame, "mNormalSpeed, camera on vs off"));
                REQUIRE_BITS_RAW(c, a.rows[i].phase_bits, b.rows[i].phase_bits,
                                 at(a.rows[i].frame, "m35E4, camera on vs off"));
                REQUIRE_INT(c, a.rows[i].proc, b.rows[i].proc,
                            at(a.rows[i].frame, "proc, camera on vs off"));
                REQUIRE_INT(c, a.rows[i].travel_angle, b.rows[i].travel_angle,
                            at(a.rows[i].frame, "travel_angle, camera on vs off"));
                frames++;
            }
            REQUIRE_INT(c, a.exit_proc, b.exit_proc, "the exit, camera on vs off" + where);

            // The arm did run: once per CRAWL_START body frame, since procCrawlEnd does not call
            // setDoStatusCrawl.
            const int body_frames = a.crawl_up - a.entry;
            REQUIRE_INT(c, a.body_angle_calls, body_frames,
                        "setBodyAngleToCamera calls with the camera up" + where);
            REQUIRE_TRUE(c, a.subject_end_calls > 0,
                         "checkSubjectEnd was never asked with the camera up" + where);
            REQUIRE_INT(c, b.body_angle_calls, 0,
                        "setBodyAngleToCamera calls with the camera down" + where);
            // The camera arm's first statement is dComIfGp_setAStatus(dActStts_RETURN_e).
            bool posted = false;
            for (const CrawlFrame& row : a.rows) {
                posted = posted || row.a_status == dActStts_RETURN_e;
            }
            REQUIRE_TRUE(c, posted, "no frame posted dActStts_RETURN_e with the camera up" + where);
            for (const CrawlFrame& row : b.rows) {
                REQUIRE_INT(c, row.a_status, dActStts_BLANK_e,
                            at(row.frame, "a_status with the camera down"));
            }
            asks += a.body_angle_calls;
        }
    }
    c.note("the camera arm ran on " + std::to_string(asks) +
           " frame(s) and moved none of " + std::to_string(frames) +
           " compared row(s) - mBodyAngle has no reader in this port");
}

TWWE_TEST(the_target_angle_this_replay_substitutes_cannot_reach_a_column,
          "m34E8 reaches a compared column, so the wall capture's missing column costs something") {
    // The wall capture has no `target_angle`, so m34E8 is seeded from `csangle`. Both m34E8 arms
    // of checkNextMode need `mStickDistance > 0.05f` and the stick is centred whenever it
    // dispatches, so moving m34E8 by 0x8000 must change nothing.
    CrawlReplayOptions far;
    far.m34E8_far = true;
    std::vector<std::vector<CrawlRun>> a = replay_all(far);
    std::vector<std::vector<CrawlRun>> b = replay_all(CrawlReplayOptions{});
    int frames = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        for (size_t r = 0; r < a[size_t(id)].size() && r < b[size_t(id)].size(); r++) {
            const CrawlRun& x = a[size_t(id)][r];
            const CrawlRun& y = b[size_t(id)][r];
            REQUIRE_INT(c, (long long)x.rows.size(), (long long)y.rows.size(),
                        "frames, m34E8 far vs seeded");
            for (size_t i = 0; i < x.rows.size() && i < y.rows.size(); i++) {
                REQUIRE_BITS_RAW(c, x.rows[i].anim_bits, y.rows[i].anim_bits,
                                 at(x.rows[i].frame, "anim_frame, m34E8 far vs seeded"));
                REQUIRE_INT(c, x.rows[i].proc, y.rows[i].proc,
                            at(x.rows[i].frame, "proc, m34E8 far vs seeded"));
                frames++;
            }
            REQUIRE_INT(c, x.exit_proc, y.exit_proc, "the exit, m34E8 far vs seeded");
        }
    }
    c.note("m34E8 moved by 0x8000 changes none of " + std::to_string(frames) + " row(s)");
}

TWWE_TEST(the_facing_and_the_travel_angle_are_equal_on_every_seed_row,
          "the two columns differ on a seed row, so which one seeds the facing is a live choice") {
    // procCrawlStart_init writes `current.angle.y = shape_angle.y`; on these runs seeding the
    // facing from travel_angle instead would change nothing. test_back_jump.cpp covers a pair
    // whose seed rows differ.
    int checked = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const CrawlCapture& cap = tww_engine::testing::crawl_capture(id);
        const Json& g = rows_of(id);
        for (int entry : tww_engine::testing::crawl_entry_frames(g)) {
            const Json& seed = g[size_t(entry - 1)];
            REQUIRE_INT(c, seed["shape_angle_y"].as_int(), seed["travel_angle"].as_int(),
                        std::string(cap.name) + " " +
                            at(entry - 1, "shape_angle_y against travel_angle"));
            checked++;
        }
    }
    c.note("the facing and the travel angle agree on all " + std::to_string(checked) +
           " seed row(s), so no control over which one seeds the facing can bite here");
}

TWWE_TEST(the_crawls_whole_travel_is_root_motion_and_no_speed_at_all,
          "the crawl moves Link with a speed after all, which would make test_crawl_pos.cpp's "
          "gate a claim about the integration rather than about the animation") {
    // On the console `potential_speed` and `true_speed` are 0.0 on every crawl frame and Link
    // still travels, so the crawl's displacement is root motion alone (posMove's m34C2 arm).
    f32 worst = 0.0f;
    int rows = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        const Json& g = rows_of(id);
        for (int entry : tww_engine::testing::crawl_entry_frames(g)) {
            int f = entry;
            const f32 x0 = g[size_t(entry)]["pos_x"].as_f32();
            const f32 z0 = g[size_t(entry)]["pos_z"].as_f32();
            while (f < int(g.size()) &&
                   (g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_START_e ||
                    g[size_t(f)]["proc"].as_int() == daPy_lk_c::daPyProc_CRAWL_END_e)) {
                REQUIRE_BITS_RAW(c, g[size_t(f)]["true_speed"].as_f32_bits(),
                                 tww_engine::testing::f32_bits(0.0f),
                                 at(f, "the console's speedF during a crawl"));
                REQUIRE_BITS_RAW(c, g[size_t(f)]["potential_speed"].as_f32_bits(),
                                 tww_engine::testing::f32_bits(0.0f),
                                 at(f, "the console's mNormalSpeed during a crawl"));
                const f32 dx = g[size_t(f)]["pos_x"].as_f32() - x0;
                const f32 dz = g[size_t(f)]["pos_z"].as_f32() - z0;
                const f32 d2 = dx * dx + dz * dz;
                if (d2 > worst) {
                    worst = d2;
                }
                rows++;
                f++;
            }
        }
    }
    REQUIRE_TRUE(c, worst > 100.0f,
                 "the console's crawls barely move - the position gap would not be worth naming");
    c.note("over " + std::to_string(rows) +
           " console crawl row(s) mNormalSpeed and speedF are 0.0 and Link still travels up to " +
           std::to_string((double)worst) +
           " square units from where he lay down: that displacement is root motion and nothing "
           "else, which is what test_crawl_pos.cpp holds the port to");
}

// --------------------------------------------------------------------------- 3. the red controls

TWWE_RED_CONTROL(red_flip_the_comparator_itself,
                 "the expected anim_frame moved by one ULP on the demo's first crawl entry frame") {
    std::vector<std::vector<CrawlRun>> all = replay_all(CrawlReplayOptions{});
    const int frame = all[tww_engine::testing::kCrawlDemo].empty()
                          ? -1
                          : all[tww_engine::testing::kCrawlDemo].front().entry;
    compare(c, all, tww_engine::testing::kCrawlDemo, frame);
}

TWWE_RED_CONTROL(red_the_naive_r_threshold,
                 "R read as a bare `trigR >= 1.0` instead of the game's own 0.9/0.6 latch") {
    // The replay builds the R latch from m_Do_controller_pad.cpp:122-131. The demo's first run
    // releases R through 0.95 on its last CRAWL_START row, so a bare >= 1.0 ends it a frame early.
    CrawlReplayOptions opt;
    opt.naive_r_threshold = true;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_the_pad_lead_dropped,
                 "the pad read on the frame it was sampled instead of one frame later") {
    CrawlReplayOptions opt;
    opt.pad_lead = 0;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_r_held_for_the_whole_run,
                 "R never released, so procCrawlStart's only exit on this data never fires") {
    CrawlReplayOptions opt;
    opt.r_held_forever = true;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_the_r_held_through_the_crawl_up,
                 "R forced back on once the crawl-up starts, which is checkNextMode(1)'s guard") {
    // checkNextMode(1)'s early return is `r29 != 0 && !(mStickDistance > 0.05f) &&
    // !spActionButton()`. The demo's first run releases R and lasts eight frames; with R forced
    // on it dispatches at five.
    CrawlReplayOptions opt;
    opt.r_held_through_crawl_up = true;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_the_crawl_up_frame_not_clamped,
                 "procCrawlEnd_init's setFrame block dropped - the crawl-up starts at 0.0") {
    // Without the `param_1 == 0` block the crawl-up starts at field_0x44 = 0.0, and at rate -1.0
    // it is below field_0x48 on its first body frame.
    CrawlReplayOptions opt;
    opt.no_crawl_end_clamp = true;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_the_crawl_anim_set_to_loop,
                 "ANM_LIE's attribute forced to EMode_LOOP instead of the .bck's own EMode_NONE") {
    // With the clock wrapping, `getRate() > -0.01f` never becomes true in the crawl-up.
    CrawlReplayOptions opt;
    opt.loop_crawl_anim = true;
    compare(c, replay_all(opt));
}

TWWE_RED_CONTROL(red_the_stick_held_through_the_crawl,
                 "mStickDistance pinned at 1.0, which arms procCrawlStart's other exit") {
    // With the stick held the crawl-move arm fires once the clock stops, and the replay stops on
    // procCrawlMove, which has no body here.
    CrawlReplayOptions opt;
    opt.stick_held = true;
    std::vector<std::vector<CrawlRun>> all = replay_all(opt);
    int stopped = 0, entered = 0;
    for (int id = 0; id < tww_engine::testing::kCrawlCaptures; id++) {
        for (const CrawlRun& run : all[size_t(id)]) {
            stopped += run.stopped_on_proc == daPy_lk_c::daPyProc_CRAWL_MOVE_e ? 1 : 0;
            entered += run.crawl_move_init_calls;
        }
    }
    REQUIRE_TRUE(c, entered > 0, "the arm did not fire even with the stick held");
    REQUIRE_TRUE(c, stopped > 0, "no run left for procCrawlMove");
    compare(c, all);
}

}  // namespace
