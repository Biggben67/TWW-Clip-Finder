// test_ground_pos.cpp - the grounded position: a proc, posMoveFromFootPos and
// dBgS_Acch::CrrPos against Kaisen r0, one frame at a time, compared with the console's next row
// (setup_finder_rollfree_live.json).
//
// The room is settled by the data: `floor_tri` names triangle 303 of kaisen_r0_bgd.json, whose
// plane holds each row's position; `ground_poly` is compared per frame, so a right height on the
// wrong polygon fails. speedF is fed from the capture (test_roll_replay.cpp holds it); this file
// holds the integration and the collision pass.
//
// posMoveFromFootPos splits the travel: `mNormalSpeed * (1 - m3598)` is the player's own and
// `f31_2 * m3598` the planted foot's, read through the posed skeleton. On the three MOVE frames
// m3598 = 1.0, so the foot term carries all of it. x, z and the ground polygon are compared on
// all 77 frames.
//
// Known gap: pos.y on those three MOVE frames. Triangle 303's plane at each frame's own x,z gives
// the capture's y on the other 74 frames and the port's on these three; the console's is the
// plane one frame's travel further along. The FRONT_ROLL frames travel as far and match, so the
// gap is about the proc, and it points into the collision frame, not the animation.
//
// Not gated: the wall push (`wall_hit_frames` is 0, asserted; walls are in test_crawl_pos.cpp),
// and the roof and water stages (both run, neither hits in this room).

#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/json.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "roll_replay.h"

namespace tww_engine {
namespace testing {
namespace {

const char* kCapture = "setup_finder_rollfree_live.json";

/// One place, so a twin differs from the gate only in the field it names.
ReplayResult run(const RollReplayOptions& opt) {
    return run_roll_replay(golden(kCapture), opt);
}

/// The capture row for the same frame number: its position columns are read after execute().
const Json& row_for(const ReplayFrame& r) {
    return golden(kCapture)[size_t(r.frame)];
}

/// Every compared column of one frame, shared by the gate and the twins. `compare_y` is false
/// on the MOVE frames (the known gap in the header).
void compare_frame(Case& c, const ReplayFrame& r, bool compare_y = true) {
    const Json& want = row_for(r);
    char where[96];
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X) pos.x", r.frame, r.proc);
    c.check_bits(r.pos_x_bits, bits(want["pos_x"].as_f32()), where);
    if (compare_y) {
        std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X) pos.y", r.frame, r.proc);
        c.check_bits(r.pos_y_bits, bits(want["pos_y"].as_f32()), where);
    }
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X) pos.z", r.frame, r.proc);
    c.check_bits(r.pos_z_bits, bits(want["pos_z"].as_f32()), where);
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X) floor_tri", r.frame, r.proc);
    c.check_int(r.ground_poly, want["floor_tri"].as_int(), where);
}

/// Whether the foot term owns this frame's travel, off the capture's `blend_move`: the three
/// MOVE frames here.
bool foot_driven(int frame) {
    return golden(kCapture)[size_t(frame)]["blend_move"].as_f32() != 0.0f;
}

/// The first such frame.
int first_foot_driven_frame() {
    const Json& g = golden(kCapture);
    for (int i = kFirstFrame; i < int(g.size()); i++) {
        if (foot_driven(i)) {
            return i;
        }
    }
    return int(g.size());
}

}  // namespace

TWWE_TEST(the_grounded_position_is_the_consoles,
          "a frame of a grounded proc - the proc, posMove and dBgS_Acch::CrrPos against Kaisen r0 "
          "- leaves current.pos where the console left it, on every frame of the capture, with "
          "the ground polygon the console named") {
    RollReplayOptions opt;
    const ReplayResult res = run(opt);

    c.require(res.stopped_on_proc < 0,
              "the replay stopped on a proc this port has no body for");
    c.require(!res.rows.empty(), "the replay produced no rows");

    int compared = 0, y_compared = 0, y_gap = 0;
    for (size_t i = 0; i < res.rows.size(); i++) {
        const ReplayFrame& r = res.rows[i];
        const bool foot = foot_driven(r.frame);
        // The port's m3598 against the console's, which decides which half of the travel each
        // frame tests.
        char where[96];
        std::snprintf(where, sizeof(where), "frame %d m3598 (the foot term's weight)", r.frame);
        c.check_bits(r.blend_bits, bits(row_for(r)["blend_move"].as_f32()), where);

        compare_frame(c, r, !foot);
        compared++;
        y_compared += foot ? 0 : 1;
        // The known gap: the port's y is the floor plane at this frame's x,z, the console's the
        // plane one step further along.
        if (foot) {
            EXPECT_KNOWN_GAP(c, r.pos_y_bits == bits(row_for(r)["pos_y"].as_f32()),
                             "a MOVE frame's pos.y - the console's ground stage answers at a "
                             "position Link is not recorded at, and the port's is the floor "
                             "plane at the recorded one");
            y_gap++;
        }
    }
    c.require(compared > 0, "no frame of this capture was comparable");
    c.require(y_gap > 0,
              "no frame of this capture is foot-driven, so nothing here is evidence about the "
              "term that owns the walk's travel");

    // The wall stage decided nothing, so the positions are the ground stage's answer.
    int wall = 0, ground = 0, line = 0;
    for (size_t i = 0; i < res.rows.size(); i++) {
        wall += res.rows[i].wall_hit ? 1 : 0;
        ground += res.rows[i].ground_hit ? 1 : 0;
        line += res.rows[i].line_hit ? 1 : 0;
    }
    c.check_int(wall, 0, "frames the wall pass corrected - this run is meant to have none");
    c.check_int(res.wall_hit_frames, 0, "the acch's own WALL_HIT count over the whole run");
    c.check_int(ground, compared,
                "frames the ground stage hit - it must be every compared one, or a frame's y is "
                "the integration's and not the floor's");

    const Json& g = golden(kCapture);
    const int cut = first_foot_driven_frame();
    char note[240];
    std::snprintf(note, sizeof(note),
                  "%d of %d frame(s) compared on x, z and floor_tri (%d..%d); pos.y on %d of "
                  "them; ground hit on %d, wall on %d, line check ran on %d", compared,
                  (int)res.rows.size(), res.rows.front().frame, res.rows.back().frame, y_compared,
                  ground, wall, res.line_check_frames);
    c.note(note);
    if (cut < int(g.size())) {
        std::snprintf(note, sizeof(note),
                      "the walk's travel, which this port answers zero for without the posed "
                      "skeleton: the console moves %.3f in x on frame %d at true_speed %.3f, "
                      "and %d foot-driven frame(s) match it bit for bit",
                      (double)(g[size_t(cut)]["pos_x"].as_f32() -
                               g[size_t(cut - 1)]["pos_x"].as_f32()),
                      cut, (double)g[size_t(cut)]["true_speed"].as_f32(), y_gap);
        c.note(note);
    }
    std::snprintf(note, sizeof(note), "line-check hits (a crossing, not the gate): %d", line);
    c.note(note);
}

// ------------------------------------------------------------------- the red controls
//
// Statements of execute():11400-11406, removed one at a time; each reaches the compared columns
// by a different line.

TWWE_RED_CONTROL(red_the_integration_not_run,
                 "posMove skipped: the position holds the seed row on every frame while the "
                 "console's moves 23 units") {
    RollReplayOptions opt;
    opt.no_pos_move = true;
    const ReplayResult res = run(opt);
    for (size_t i = 0; i < res.rows.size(); i++) {
        compare_frame(c, res.rows[i], !foot_driven(res.rows[i].frame));
    }
}

TWWE_RED_CONTROL(red_the_collision_pass_not_run,
                 "dBgS_Acch::CrrPos skipped: the integration alone, so nothing clamps Link to "
                 "the floor and the gravity step accumulates through it") {
    RollReplayOptions opt;
    opt.no_crr_pos = true;
    const ReplayResult res = run(opt);
    for (size_t i = 0; i < res.rows.size(); i++) {
        compare_frame(c, res.rows[i], !foot_driven(res.rows[i].frame));
    }
}

// ------------------------------------------------------------------- and one that does not bite
//
// Freezing old_pos (`old = current` never run) changes nothing: old.pos is the line check's far
// end and the wall pass's SetLin input, and on this open floor the line check crosses nothing and
// the wall never hits. So old.pos is unobservable on an open floor, not readerless.

TWWE_TEST(the_old_position_cannot_be_seen_on_an_open_floor,
          "with `old = current` never run - old_pos frozen at the seed frame for the whole run - "
          "every compared column is bit-identical, and the line check crossing nothing on every "
          "frame is what says why") {
    RollReplayOptions gate_opt;
    RollReplayOptions stale_opt;
    stale_opt.stale_old_pos = true;
    const ReplayResult gate = run(gate_opt);
    const ReplayResult stale = run(stale_opt);

    c.check_int((int)stale.rows.size(), (int)gate.rows.size(),
                "the two runs produced a different number of frames");

    int same = 0, crossings = 0;
    for (size_t i = 0; i < gate.rows.size() && i < stale.rows.size(); i++) {
        char where[96];
        std::snprintf(where, sizeof(where), "frame %d pos.x with old_pos frozen",
                      gate.rows[i].frame);
        c.check_bits(stale.rows[i].pos_x_bits, gate.rows[i].pos_x_bits, where);
        std::snprintf(where, sizeof(where), "frame %d pos.y with old_pos frozen",
                      gate.rows[i].frame);
        c.check_bits(stale.rows[i].pos_y_bits, gate.rows[i].pos_y_bits, where);
        std::snprintf(where, sizeof(where), "frame %d pos.z with old_pos frozen",
                      gate.rows[i].frame);
        c.check_bits(stale.rows[i].pos_z_bits, gate.rows[i].pos_z_bits, where);
        crossings += gate.rows[i].line_hit ? 1 : 0;
        same++;
    }
    // A segment that crosses nothing answers the same whatever its length.
    c.check_int(crossings, 0,
                "line-check crossings on the compared frames - the identity above rests on there "
                "being none");

    char note[200];
    std::snprintf(note, sizeof(note),
                  "%d frame(s) identical with old_pos frozen; line check ran on %d frame(s) of "
                  "the run and crossed nothing on any of them", same, gate.line_check_frames);
    c.note(note);
    c.note("the counterfactual that would make old_pos observable is a room where the line check "
           "crosses something - the crawl's wall capture - and its travel is root motion this "
           "port has no archive for");
}

}  // namespace testing
}  // namespace tww_engine

