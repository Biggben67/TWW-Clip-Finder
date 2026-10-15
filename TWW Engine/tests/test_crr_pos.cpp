// test_crr_pos.cpp - dBgS_Acch::CrrPos (d_bg_s_acch.cpp:209): the order of the line check, wall
// pass, roof and ground stages.
//
// The line check runs when the gate at d_bg_s_acch.cpp:228-232 passes; Link's acch sets
// LINE_CHECK (`OnLineCheck()`), so it always runs for him. It runs again after the wall pass if a
// wall corrected. The roof stage caps `field_0xC4`, which GroundRoofProc applies as a ceiling on
// the ground snap; the ground stage runs last, at the corrected XZ.
//
// The oracle, the old sim's `acch_crr_pos`, is the line->wall->line triple only, so the
// differential sets GRND_NONE | ROOF_NONE | WATER_NONE (a configuration the game uses:
// procFall_init, d_a_player_main.cpp:7298). `Stages::GroundNoRoof` adds the ground stage, which
// the differential composes from the old sim's GroundCross and ground snap. Not reachable that
// way: `dBgS_Acch::LineCheck`'s ground-classed arm runs a GroundCheck inside the line check;
// `staged_ok` marks those frames. The roof stage has no oracle.

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "SSystem/SComponent/c_m3d.h"
#include "framework/golden.h"
#include "framework/json.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "room_dzb.h"
#include "wall_walk.h"

namespace tww_engine {
namespace testing {
namespace {

/// Link's three standing cylinders (d_a_player_main.cpp:12194-12196). The differential carries
/// its own set in the payload, since setBgCheckParam chooses them per proc.
const f32 kStandH[3] = {30.1f, 89.9f, 125.0f};
const f32 kStandR = 35.0f;

//: The four differential rooms, as in tests/test_wall_walk.cpp.
const char* kRooms[] = {"kaze_r11_bgd.json", "ganona_r0_bgd.json", "sea_r41_bgd.json",
                        "kaisen_r0_bgd.json"};
const char* kLabels[] = {"kaze r11", "GanonA r0", "sea r41", "Kaisen r0"};
const int kRoomCount = 4;

/// The stage set, spelled with the acch's own flags.
enum class Stages {
    /// Every stage. What Link runs.
    All,
    /// GRND_NONE | ROOF_NONE | WATER_NONE - the line->wall->line triple.
    WallsOnly,
    /// ROOF_NONE | WATER_NONE - the triple and the ground stage.
    ///
    /// With ROOF_NONE, `field_0xC4` stays G_CM3D_F_INF, so `GroundRoofProc` is a no-op in both
    /// arms. That is a property of the copied body, so `roof_hit` must stay false on every row.
    GroundNoRoof,
};

void apply_stages(dBgS_Acch& acch, Stages s) {
    if (s == Stages::WallsOnly) {
        acch.SetGrndNone();
    }
    if (s == Stages::WallsOnly || s == Stages::GroundNoRoof) {
        acch.SetRoofNone();
        acch.SetWaterNone();
    }
}

/// One derived frame: where Link was and where the integration put him before collision ran.
struct DerivedFrame {
    cXyz old_pos;
    cXyz pos;
    /// The triangle this frame was aimed at, which is what an assertion message names.
    int poly;
};

/// One frame per triangle with a nonzero normal: from 120 units out along the normal from the
/// centroid to 40 behind it, crossing front to back (the acch tests front faces only). The middle
/// cylinder's height is subtracted so that cylinder's line hits the polygon.
std::vector<DerivedFrame> derive_frames(Room& room, const RoomDzb& dzb) {
    std::vector<DerivedFrame> out;
    const int tri_n = room.tri_count();
    for (int poly = 0; poly < tri_n; poly++) {
        cM3dGPla* pla = room.bgw().GetTriPla(poly);
        const cXyz* n = (const cXyz*)pla->GetNP();
        const f32 nlen2 = n->x * n->x + n->y * n->y + n->z * n->z;
        if (nlen2 < 1.0e-10f) {
            continue;  // CalcPlane left this triangle a zero normal; nothing to aim at
        }
        const cBgD_Tri_t& t = dzb.t_tbl[poly];
        const cBgD_Vtx_t& v0 = dzb.v_tbl[t.vtx0];
        const cBgD_Vtx_t& v1 = dzb.v_tbl[t.vtx1];
        const cBgD_Vtx_t& v2 = dzb.v_tbl[t.vtx2];
        const f32 cx = (v0.x + v1.x + v2.x) / 3.0f;
        const f32 cy = (v0.y + v1.y + v2.y) / 3.0f;
        const f32 cz = (v0.z + v1.z + v2.z) / 3.0f;

        DerivedFrame f;
        f.poly = poly;
        f.old_pos.x = cx + n->x * 120.0f;
        f.old_pos.y = (cy + n->y * 120.0f) - kStandH[1];
        f.old_pos.z = cz + n->z * 120.0f;
        f.pos.x = cx - n->x * 40.0f;
        f.pos.y = (cy - n->y * 40.0f) - kStandH[1];
        f.pos.z = cz - n->z * 40.0f;
        out.push_back(f);
    }
    return out;
}

/// Link's standing set, as every case here asks about him.
void stand_cyls(Room::WallCyl* cyls) {
    for (int i = 0; i < 3; i++) {
        cyls[i].h = kStandH[i];
        cyls[i].r = kStandR;
    }
}

/// CrrPos over one derived frame. Writes the end position to `end` and, when asked, the acch's
/// ground-probe fields, so a by-hand staging reads them off the same object.
Room::FrameResult run_frame_stages(Room& room, const DerivedFrame& f, const Room::WallCyl* cyls,
                                   Stages stages, cXyz* end, f32* out_gnd_offset = nullptr,
                                   f32* out_gnd_up_h = nullptr) {
    *end = f.pos;
    cXyz speed;
    speed.x = speed.y = speed.z = 0.0f;
    cXyz old_pos = f.old_pos;
    Room::PlayerAcch player(end, &old_pos, &speed, cyls, 3);
    apply_stages(player.acch(), stages);
    Room::FrameResult res = room.CrrPos(player);
    if (out_gnd_offset != nullptr) {
        *out_gnd_offset = player.acch().m_ground_check_offset;
    }
    if (out_gnd_up_h != nullptr) {
        *out_gnd_up_h = player.acch().m_ground_up_h;
    }
    return res;
}

/// CrrPos over one derived frame, walls only.
Room::FrameResult run_frame(Room& room, const DerivedFrame& f, const Room::WallCyl* cyls,
                            cXyz* end) {
    return run_frame_stages(room, f, cyls, Stages::WallsOnly, end);
}

/// The three stages by hand in CrrPos's order. `carry_latch` hands the first line check's
/// SetWallHDirect latch to the wall pass; without it these are three independent queries.
cXyz stage_by_hand(Room& room, const cXyz& old_pos, const cXyz& pos, const Room::WallCyl* cyls,
                   int tbl_size, f32 speed_y, bool carry_latch, Room::LineResult* out_l1,
                   Room::WallResult* out_w, int* out_ground_branch) {
    cXyz staged = pos;
    Room::LineResult l1;
    room.LineCheck(&staged, old_pos, cyls, tbl_size, &l1);
    Room::WallResult w;
    room.WallCorrect(&staged, old_pos, speed_y, cyls, tbl_size, &w, PassChk::Link,
                     carry_latch ? &l1 : nullptr);
    Room::LineResult l2;
    l2.ground_branch = 0;
    if (w.wall_hit) {
        room.LineCheck(&staged, old_pos, cyls, tbl_size, &l2);
    }
    if (out_l1 != nullptr) {
        *out_l1 = l1;
    }
    if (out_w != nullptr) {
        *out_w = w;
    }
    // Cylinders that reached `dBgS_Acch::LineCheck`'s ground-classed arm
    // (`pm_pos->y -= 1.0f; GroundCheck(i_bgs);`, not gated by GRND_NONE), which Room::LineCheck
    // skips; such a frame is not its staging.
    if (out_ground_branch != nullptr) {
        *out_ground_branch = l1.ground_branch + l2.ground_branch;
    }
    return staged;
}

/// The same, over a derived frame's own pair, which is what the room cases ask.
cXyz stage_by_hand(Room& room, const DerivedFrame& f, const Room::WallCyl* cyls, bool carry_latch,
                   Room::LineResult* out_l1, Room::WallResult* out_w) {
    return stage_by_hand(room, f.old_pos, f.pos, cyls, 3, 0.0f, carry_latch, out_l1, out_w,
                         nullptr);
}

/// dBgS_Acch::GroundCheck (d_bg_s_acch.cpp:122-153) by hand.
///
/// `b4` is field_0xb4, `GetPos()->y` latched at CrrPos entry; the snap tests against it, not the
/// post-wall y. `m_ground_up_h_diff` is omitted: CrrPos reads and zeroes it, and a fresh acch's
/// is 0.
bool apply_ground_check(Room& room, cXyz* pos, f32 b4, f32 offset, f32 up_h, f32* out_h) {
    cXyz probe = *pos;
    probe.y += offset - up_h;
    int gnd_poly = 0;
    const f32 h = room.GroundCross(probe, &gnd_poly);
    if (out_h != nullptr) {
        *out_h = h;
    }
    if (h != -G_CM3D_F_INF) {
        const f32 b8 = h + up_h;
        if (b8 > b4) {
            pos->y = b8;
            return true;
        }
    }
    return false;
}

}  // namespace

// =============================================================================================
// Differential export: the port's answer at every frame in the payload. Not a gate - both sides
// port the same decomp.
// =============================================================================================

TWWE_TEST(the_port_answers_the_frames_a_crrpos_differential_run_asks_for,
          "with TWWE_DIFF_CRR_POINTS set, the port's whole-frame answer at every (old_pos, pos) "
          "the old sim will also be asked about - written out to diff against the old sim") {
    const char* in_path = std::getenv("TWWE_DIFF_CRR_POINTS");
    const char* out_path = std::getenv("TWWE_DIFF_CRR_OUT");
    if (in_path == nullptr || out_path == nullptr) {
        c.note("set TWWE_DIFF_CRR_POINTS=<points.json> and TWWE_DIFF_CRR_OUT=<answers.json> to "
               "run the frame differential (the payload's \"stages\" picks \"walls\", which is "
               "the only shape the old sim can answer, or \"all\"). Unset, this case answers "
               "nothing and asserts nothing");
        REQUIRE_TRUE(c, true, "");
        return;
    }
    Json pts;
    std::string err;
    REQUIRE_TRUE(c, Json::load(in_path, &pts, &err),
                 std::string("TWWE_DIFF_CRR_POINTS could not be read: ") + err);
    const Json& rows = pts["points"];
    const std::string room_name = pts["bgd"].str;

    Room::WallCyl cyls[kMaxWallCyl];
    const Json& hs = pts["wall_h"];
    const int tbl_size = (int)hs.size();
    REQUIRE_TRUE(c, tbl_size > 0 && tbl_size <= kMaxWallCyl,
                 "wall_h names between 1 and " + std::to_string(kMaxWallCyl) + " cylinders");
    const f32 wall_r = pts["wall_r"].as_f32();
    for (int i = 0; i < tbl_size && i < kMaxWallCyl; i++) {
        cyls[i].h = hs[i].as_f32();
        cyls[i].r = wall_r;
    }

    const std::string stage_name = pts["stages"].str.empty() ? "walls" : pts["stages"].str;
    Stages stages;
    if (stage_name == "walls") {
        stages = Stages::WallsOnly;
    } else if (stage_name == "ground") {
        stages = Stages::GroundNoRoof;
    } else if (stage_name == "all") {
        stages = Stages::All;
    } else {
        // Fail rather than fall back to a different stage set.
        REQUIRE_TRUE(c, false,
                     "\"stages\": \"" + stage_name + "\" is not a stage set (walls, ground, all)");
        return;
    }
    const f32 speed_y = pts["speed_y"].as_f32();

    RoomDzb dzb = read_room_dzb(golden(room_name));
    Room fx_room(dzb);
    // A separate room for the staging: dBgS and dBgW keep state between queries.
    Room st_room(dzb);

    //: Frames whose CrrPos is not its staged triple.
    int not_staged = 0;

    std::string body;
    for (size_t i = 0; i < rows.size(); i++) {
        cXyz old_pos, pos;
        old_pos.x = rows[i]["ox"].as_f32();
        old_pos.y = rows[i]["oy"].as_f32();
        old_pos.z = rows[i]["oz"].as_f32();
        pos.x = rows[i]["x"].as_f32();
        pos.y = rows[i]["y"].as_f32();
        pos.z = rows[i]["z"].as_f32();
        cXyz speed;
        speed.x = 0.0f;
        speed.y = speed_y;
        speed.z = 0.0f;

        // A fresh acch per row, matching the oracle; the game keeps one acch for Link's life.
        const cXyz frame_in = pos;
        Room::PlayerAcch player(&pos, &old_pos, &speed, cyls, tbl_size);
        apply_stages(player.acch(), stages);
        Room::FrameResult res = fx_room.CrrPos(player);
        const f32 gnd_offset = player.acch().m_ground_check_offset;
        const f32 gnd_up_h = player.acch().m_ground_up_h;

        // The staged stages beside the frame: the differential attributes a disagreement per
        // stage, which holds only where the frame equals its staging (`staged_ok`). Where
        // RwgWallCorrect reads an unassigned local, agreement means nothing; the wall arm's
        // `undef` flags those. With the ground stage on, the staging adds GroundCheck.
        cXyz staged_end;
        int staged_gb = 0;
        bool staged_ground_ok = true;
        {
            cXyz staged_old = old_pos;
            staged_end = stage_by_hand(st_room, staged_old, frame_in, cyls, tbl_size, speed_y,
                                       true, nullptr, nullptr, &staged_gb);
            if (stages == Stages::GroundNoRoof) {
                // Compare the ground answer too: the mid-line ground arm can raise GROUND_HIT
                // without moving the position.
                f32 staged_h = 0.0f;
                const bool staged_hit = apply_ground_check(st_room, &staged_end, frame_in.y,
                                                           gnd_offset, gnd_up_h, &staged_h);
                staged_ground_ok = (staged_hit == res.ground_hit) &&
                                   (bits(staged_h) == bits(res.ground_h));
            }
        }
        const bool staged_ok = staged_ground_ok && bits(staged_end.x) == bits(pos.x) &&
                               bits(staged_end.y) == bits(pos.y) &&
                               bits(staged_end.z) == bits(pos.z);
        // Roof and water have no by-hand form, so `Stages::All` has no staging.
        const bool staged_means_something = (stages != Stages::All);

        char buf[1024];
        std::snprintf(buf, sizeof(buf),
                      "%s{\"i\": %zu, \"x\": %.9g, \"y\": %.9g, \"z\": %.9g, \"x_bits\": %u, "
                      "\"y_bits\": %u, \"z_bits\": %u, \"line_hit\": %s, \"wall_hit\": %s, "
                      "\"ran_line\": %s, \"cir_hit\": [%s, %s, %s], "
                      "\"cir_angle\": [%d, %d, %d], \"cir_poly\": [%d, %d, %d], "
                      "\"ground_hit\": %s, \"ground_find\": %s, \"ground_landing\": %s, "
                      "\"ground_away\": %s, \"roof_hit\": %s, \"ground_h\": %.9g, "
                      "\"ground_h_bits\": %u, \"ground_poly\": %d, \"staged_gb\": %d",
                      i ? ",\n" : "", i, (double)pos.x, (double)pos.y, (double)pos.z,
                      (unsigned)bits(pos.x), (unsigned)bits(pos.y), (unsigned)bits(pos.z),
                      res.line_hit ? "true" : "false", res.wall_hit ? "true" : "false",
                      res.ran_line_check ? "true" : "false",
                      res.wall.cir_hit[0] ? "true" : "false",
                      res.wall.cir_hit[1] ? "true" : "false",
                      res.wall.cir_hit[2] ? "true" : "false",
                      (int)res.wall.cir_angle[0], (int)res.wall.cir_angle[1],
                      (int)res.wall.cir_angle[2], res.wall.cir_poly[0], res.wall.cir_poly[1],
                      res.wall.cir_poly[2], res.ground_hit ? "true" : "false",
                      res.ground_find ? "true" : "false",
                      res.ground_landing ? "true" : "false",
                      res.ground_away ? "true" : "false", res.roof_hit ? "true" : "false",
                      (double)res.ground_h, (unsigned)bits(res.ground_h), res.ground_poly,
                      staged_gb);
        body += buf;
        if (staged_means_something) {
            body += staged_ok ? ", \"staged_ok\": true}" : ", \"staged_ok\": false}";
            if (!staged_ok) {
                not_staged++;
            }
        } else {
            body += "}";
        }
    }
    std::FILE* f = std::fopen(out_path, "wb");
    REQUIRE_TRUE(c, f != nullptr,
                 std::string("TWWE_DIFF_CRR_OUT could not be opened: ") + out_path);
    if (f != nullptr) {
        // The stage set is written so answers from different sets cannot be confused.
        std::fprintf(f, "{\"bgd\": \"%s\", \"stages\": \"%s\", \"answers\": [\n%s\n]}\n",
                     room_name.c_str(), stage_name.c_str(), body.c_str());
        std::fclose(f);
    }
    c.note(std::to_string(rows.size()) + " frame(s) answered from " + room_name + " with stages=" +
           stage_name +
           (stages == Stages::All
                ? " (no `staged_ok`: the roof and water stages have no by-hand form here)"
                : ", " + std::to_string(not_staged) + " of them not reproduced by the staged " +
                      (stages == Stages::GroundNoRoof ? "quad" : "triple")) +
           " -> " + out_path);
}

// =============================================================================================
// What CrrPos does that the three queries alone do not.
// =============================================================================================

TWWE_TEST(the_frame_is_not_three_independent_queries_and_the_latch_is_why,
          "CrrPos with GRND_NONE | ROOF_NONE | WATER_NONE reproduces LineCheck -> WallCorrect -> "
          "LineCheck bit for bit on every frame whose first line check latched no "
          "SetWallHDirect, and differs on frames where it did - which names the one channel that "
          "makes the frame more than its three stages") {
    RoomDzb dzb = read_room_dzb(golden("kaisen_r0_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    stand_cyls(cyls);

    // dBgS_Acch::LineCheck calls `pm_acch_cir[i].SetWallHDirect(pm_pos->y)` on crossings of a
    // polygon with an XZ normal (d_bg_s_acch.cpp:198), and RwgWallCorrect then cuts at that
    // latched height (d_bg_w.cpp, `ChkWallHDirect`). Nothing clears it between the two. Staged
    // with the latch dropped, frames agree to the bit only where nothing latched.
    int frames = 0, latched = 0, no_latch = 0, no_latch_differed = 0, latch_differed = 0;
    const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
    for (size_t fi = 0; fi < derived.size(); fi++) {
        const DerivedFrame& f = derived[fi];
        frames++;

        cXyz frame_pos;
        Room::FrameResult fr = run_frame(room, f, cyls, &frame_pos);

        Room::LineResult l1;
        Room::WallResult w;
        const cXyz staged = stage_by_hand(room, f, cyls, false, &l1, &w);

        bool any_latch = false;
        for (int k = 0; k < 3; k++) {
            any_latch = any_latch || l1.whd_set[k];
        }
        const bool differed = bits(frame_pos.x) != bits(staged.x) ||
                              bits(frame_pos.y) != bits(staged.y) ||
                              bits(frame_pos.z) != bits(staged.z);
        if (any_latch) {
            latched++;
            if (differed) {
                latch_differed++;
            }
        } else {
            no_latch++;
            if (differed) {
                no_latch_differed++;
            }
            REQUIRE_BITS(c, frame_pos.x, staged.x,
                         "frame " + std::to_string(f.poly) + " x, with nothing latched");
            REQUIRE_BITS(c, frame_pos.y, staged.y,
                         "frame " + std::to_string(f.poly) + " y, with nothing latched");
            REQUIRE_BITS(c, frame_pos.z, staged.z,
                         "frame " + std::to_string(f.poly) + " z, with nothing latched");
            REQUIRE_TRUE(c, fr.wall_hit == w.wall_hit,
                         "frame " + std::to_string(f.poly) + " wall_hit, with nothing latched");
        }
        REQUIRE_TRUE(c, fr.ran_line_check,
                     "frame " + std::to_string(f.poly) +
                         ": OnLineCheck() is up, so the gate's fourth term always fires");
    }

    // Both partitions must be populated.
    c.note(std::to_string(frames) + " frame(s) in kaisen r0: " + std::to_string(no_latch) +
           " latched nothing (" + std::to_string(no_latch_differed) +
           " of them differ from the staged triple), " + std::to_string(latched) +
           " latched SetWallHDirect (" + std::to_string(latch_differed) + " differ)");
    REQUIRE_TRUE(c, no_latch > 100,
                 "there is a population that latched nothing, to hold bit-identical");
    REQUIRE_TRUE(c, latched > 0,
                 "the latch fires somewhere in this room - otherwise the partition above is the "
                 "whole room and this case says nothing about the channel");
    REQUIRE_TRUE(c, latch_differed > 0,
                 "at least one latched frame answers differently from the staged triple - which "
                 "is what makes SetWallHDirect a channel rather than a field nobody reads");
}

TWWE_TEST(the_staged_triple_reproduces_the_frame_once_the_latch_is_carried,
          "CrrPos with GRND_NONE | ROOF_NONE | WATER_NONE is LineCheck -> WallCorrect -> LineCheck "
          "bit for bit on every derived frame in all four differential rooms, latched or not, once "
          "the wall pass is handed the latch the first line check left - which is the claim the "
          "case above leaves open on its latched half, and what makes staging a frame by hand an "
          "instrument") {
    // All four rooms: the differential's per-stage attribution rests on this decomposition.
    int frames = 0, latched = 0, changed_by_latch = 0, second_line = 0, undef_frames = 0;
    for (int r = 0; r < kRoomCount; r++) {
        RoomDzb dzb = read_room_dzb(golden(kRooms[r]));
        Room room(dzb);

        Room::WallCyl cyls[3];
        stand_cyls(cyls);

        // Counts frames where cM3d_Len2dSqPntAndSegLine's degenerate arm leaves RwgWallCorrect
        // reading unassigned locals. `SegAssignsStart`, as in test_wall_correct.cpp, because an
        // unmutated walk can trip cM2d_CrossCirLin's JUT_ASSERT.
        tww_engine::testing::WallWalk undef_walk(room,
                                                 tww_engine::testing::WallVariant::SegAssignsStart);

        // Both latch values run: carried must match the frame, `changed_by_latch` counts where
        // dropped does not.
        const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
        for (size_t fi = 0; fi < derived.size(); fi++) {
            const DerivedFrame& f = derived[fi];
            frames++;

            cXyz frame_pos;
            Room::FrameResult fr = run_frame(room, f, cyls, &frame_pos);

            Room::LineResult l1;
            Room::WallResult w;
            const cXyz carried = stage_by_hand(room, f, cyls, true, &l1, &w);
            const cXyz dropped = stage_by_hand(room, f, cyls, false, nullptr, nullptr);

            for (int k = 0; k < 3; k++) {
                if (l1.whd_set[k]) {
                    latched++;
                    break;
                }
            }
            if (w.wall_hit) {
                second_line++;
            }
            if (bits(carried.x) != bits(dropped.x) || bits(carried.y) != bits(dropped.y) ||
                bits(carried.z) != bits(dropped.z)) {
                changed_by_latch++;
            }
            {
                cXyz u = f.pos;
                cXyz uold = f.old_pos;
                Room::LineResult ul;
                room.LineCheck(&u, uold, cyls, 3, &ul);
                Room::WallResult uw;
                undef_walk.run(&u, uold, 0.0f, cyls, 3, &uw, &ul);
                if (undef_walk.degenerate_reads() > 0) {
                    undef_frames++;
                }
            }

            const std::string at =
                "frame " + std::to_string(f.poly) + " of " + std::string(kLabels[r]);
            REQUIRE_BITS(c, frame_pos.x, carried.x, at + " x");
            REQUIRE_BITS(c, frame_pos.y, carried.y, at + " y");
            REQUIRE_BITS(c, frame_pos.z, carried.z, at + " z");
            REQUIRE_TRUE(c, fr.wall_hit == w.wall_hit, at + " wall_hit");
            for (int k = 0; k < 3; k++) {
                REQUIRE_TRUE(c, fr.wall.cir_hit[k] == w.cir_hit[k],
                             at + " cir_hit[" + std::to_string(k) + "]");
                REQUIRE_TRUE(c, fr.wall.cir_poly[k] == w.cir_poly[k],
                             at + " cir_poly[" + std::to_string(k) + "]");
                REQUIRE_TRUE(c, fr.wall.cir_angle[k] == w.cir_angle[k],
                             at + " cir_angle[" + std::to_string(k) + "]");
            }
        }
    }

    // The latch and the second line check must both be reached.
    c.note(std::to_string(frames) + " frame(s) over " + std::to_string(kRoomCount) + " room(s): " +
           std::to_string(latched) + " latched SetWallHDirect, " + std::to_string(second_line) +
           " corrected a wall and ran the second line check, " + std::to_string(changed_by_latch) +
           " answer differently with the latch dropped, " + std::to_string(undef_frames) +
           " read an unassigned local in the wall pass and have no answer of their own");
    REQUIRE_TRUE(c, latched > 0,
                 "the latch fires somewhere in these rooms - otherwise the argument this case "
                 "gates is never given a value that does anything");
    REQUIRE_TRUE(c, changed_by_latch > 0,
                 "the latch's two values answer differently on at least one frame - otherwise the "
                 "bit assertions above hold whether the wall pass reads it or not");
    REQUIRE_TRUE(c, second_line > 0,
                 "a wall corrects somewhere in these rooms, so the third stage is reached at all");
}

TWWE_TEST(the_frames_ground_stage_is_asked_and_the_staged_quad_reproduces_it,
          "CrrPos with ROOF_NONE | WATER_NONE - the triple and the ground check - is "
          "LineCheck -> WallCorrect(latch) -> LineCheck -> GroundCheck bit for bit on every "
          "derived frame in all four rooms whose line check never took its ground-classed arm, "
          "and it snaps on a stated population, which is what says the stage was asked anything "
          "at all") {
    // `snapped > 0` guards against a stage that never hits: an uninitialised cBgS_GndChk::mFlag
    // makes cBgS::GroundCross's prechecks skip every chain and answer -G_CM3D_F_INF.
    //
    // Frames whose line check took `dBgS_Acch::LineCheck`'s ground-classed arm are not their
    // staged quad (Room::LineCheck runs no query there); they are counted and excluded.
    int frames = 0, mid_line = 0, staged_frames = 0, snapped = 0, no_floor = 0, undef_frames = 0;
    for (int r = 0; r < kRoomCount; r++) {
        RoomDzb dzb = read_room_dzb(golden(kRooms[r]));
        Room room(dzb);
        // A separate room for the staging: dBgS and dBgW keep state between queries.
        Room st_room(dzb);

        Room::WallCyl cyls[3];
        stand_cyls(cyls);

        tww_engine::testing::WallWalk undef_walk(room,
                                                 tww_engine::testing::WallVariant::SegAssignsStart);

        const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
        for (size_t fi = 0; fi < derived.size(); fi++) {
            const DerivedFrame& f = derived[fi];
            frames++;

            cXyz frame_pos;
            f32 gnd_offset = 0.0f;
            f32 gnd_up_h = 0.0f;
            Room::FrameResult fr = run_frame_stages(room, f, cyls, Stages::GroundNoRoof,
                                                    &frame_pos, &gnd_offset, &gnd_up_h);
            // With ROOF_NONE, GroundRoofProc must change nothing.
            REQUIRE_TRUE(c, !fr.roof_hit,
                         std::string("frame ") + std::to_string(f.poly) + " of " + kLabels[r] +
                             ": ROOF_NONE is up, so no roof can be hit");

            cXyz staged_old = f.old_pos;
            int ground_branch = 0;
            cXyz staged = stage_by_hand(st_room, staged_old, f.pos, cyls, 3, 0.0f, true, nullptr,
                                        nullptr, &ground_branch);
            if (ground_branch > 0) {
                mid_line++;
                continue;
            }
            staged_frames++;

            f32 h = 0.0f;
            const bool ground_hit =
                apply_ground_check(st_room, &staged, f.pos.y, gnd_offset, gnd_up_h, &h);
            if (ground_hit) {
                snapped++;
            }
            if (h == -G_CM3D_F_INF) {
                no_floor++;
            }

            {
                cXyz u = f.pos;
                cXyz uold = f.old_pos;
                Room::LineResult ul;
                room.LineCheck(&u, uold, cyls, 3, &ul);
                Room::WallResult uw;
                undef_walk.run(&u, uold, 0.0f, cyls, 3, &uw, &ul);
                if (undef_walk.degenerate_reads() > 0) {
                    undef_frames++;
                }
            }

            const std::string at =
                "frame " + std::to_string(f.poly) + " of " + std::string(kLabels[r]);
            REQUIRE_BITS(c, frame_pos.x, staged.x, at + " x");
            REQUIRE_BITS(c, frame_pos.y, staged.y, at + " y");
            REQUIRE_BITS(c, frame_pos.z, staged.z, at + " z");
            REQUIRE_BITS(c, fr.ground_h, h, at + " m_ground_h");
            REQUIRE_TRUE(c, fr.ground_hit == ground_hit, at + " GROUND_HIT");
            REQUIRE_TRUE(c, fr.wall_hit == fr.wall.wall_hit, at + " wall_hit");
        }
    }

    // Every partition must be populated.
    c.note(std::to_string(frames) + " frame(s) over " + std::to_string(kRoomCount) + " room(s): " +
           std::to_string(mid_line) + " took the line check's ground arm and are not their staged "
           "quad, " + std::to_string(staged_frames) + " were staged (" + std::to_string(snapped) +
           " snapped to a floor, " + std::to_string(no_floor) +
           " found none), " + std::to_string(undef_frames) +
           " read an unassigned local in the wall pass");
    REQUIRE_TRUE(c, snapped > 0,
                 "the ground stage snaps somewhere in these rooms - a run where it never did "
                 "would pass every bit assertion above with the stage answering nothing, which "
                 "is exactly what an uninitialised cBgS_GndChk::mFlag looks like");
    REQUIRE_TRUE(c, no_floor > 0,
                 "and it finds no floor somewhere too, so the -G_CM3D_F_INF arm of the snap test "
                 "is a branch this case takes rather than one it argues about");
    REQUIRE_TRUE(c, mid_line > 0,
                 "the line check's ground arm fires somewhere in these rooms - otherwise the "
                 "exclusion above is a filter that never filters and says nothing about what "
                 "this instrument reaches");
}

TWWE_RED_CONTROL(red_the_staged_quad_reproduces_the_frame_with_the_ground_check_dropped,
         "the same four stages with the ground check left out, which is the staged triple - what "
         "the walls arm stages. It must disagree with a frame that ran the ground stage, or that "
         "stage moves nothing and gating it is gating a no-op") {
    int differed = 0, frames = 0;
    for (int r = 0; r < kRoomCount; r++) {
        RoomDzb dzb = read_room_dzb(golden(kRooms[r]));
        Room room(dzb);
        Room st_room(dzb);
        Room::WallCyl cyls[3];
        stand_cyls(cyls);

        const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
        for (size_t fi = 0; fi < derived.size(); fi++) {
            const DerivedFrame& f = derived[fi];
            cXyz frame_pos;
            run_frame_stages(room, f, cyls, Stages::GroundNoRoof, &frame_pos);
            cXyz staged_old = f.old_pos;
            int ground_branch = 0;
            const cXyz triple = stage_by_hand(st_room, staged_old, f.pos, cyls, 3, 0.0f, true,
                                              nullptr, nullptr, &ground_branch);
            if (ground_branch > 0) {
                continue;
            }
            frames++;
            if (bits(frame_pos.x) != bits(triple.x) || bits(frame_pos.y) != bits(triple.y) ||
                bits(frame_pos.z) != bits(triple.z)) {
                differed++;
            }
        }
    }
    c.note(std::to_string(differed) + " of " + std::to_string(frames) +
           " staged frame(s) answer differently with the ground check dropped");
    REQUIRE_TRUE(c, differed == 0,
                 "staging the frame without the ground check answers what a ground-stage CrrPos "
                 "answers - which would mean the stage never moves anybody");
}

TWWE_RED_CONTROL(red_the_staged_quad_reproduces_the_frame_with_the_snap_test_against_the_end_y,
         "the same four stages with GroundCheck's snap tested against the position the triple "
         "left instead of `field_0xb4`, the y latched at CrrPos entry. They are the same number "
         "on every frame the line and wall stages did not move vertically, so this must find the "
         "frames where they did - otherwise the latch is a field this case never reads") {
    int differed = 0, frames = 0;
    for (int r = 0; r < kRoomCount; r++) {
        RoomDzb dzb = read_room_dzb(golden(kRooms[r]));
        Room room(dzb);
        Room st_room(dzb);
        Room::WallCyl cyls[3];
        stand_cyls(cyls);

        const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
        for (size_t fi = 0; fi < derived.size(); fi++) {
            const DerivedFrame& f = derived[fi];
            cXyz frame_pos;
            f32 gnd_offset = 0.0f;
            f32 gnd_up_h = 0.0f;
            run_frame_stages(room, f, cyls, Stages::GroundNoRoof, &frame_pos, &gnd_offset,
                             &gnd_up_h);
            cXyz staged_old = f.old_pos;
            int ground_branch = 0;
            cXyz staged = stage_by_hand(st_room, staged_old, f.pos, cyls, 3, 0.0f, true, nullptr,
                                        nullptr, &ground_branch);
            if (ground_branch > 0) {
                continue;
            }
            frames++;
            // The one change: `staged.y` instead of `f.pos.y`.
            apply_ground_check(st_room, &staged, staged.y, gnd_offset, gnd_up_h, nullptr);
            if (bits(frame_pos.x) != bits(staged.x) || bits(frame_pos.y) != bits(staged.y) ||
                bits(frame_pos.z) != bits(staged.z)) {
                differed++;
            }
        }
    }
    c.note(std::to_string(differed) + " of " + std::to_string(frames) +
           " staged frame(s) answer differently with the snap tested against the triple's y");
    REQUIRE_TRUE(c, differed == 0,
                 "testing the snap against the position the triple left answers what the frame "
                 "answers - which would mean field_0xb4 is a latch nothing depends on");
}

TWWE_RED_CONTROL(red_the_staged_triple_reproduces_the_frame_with_the_latch_dropped,
         "the same three stages with the wall pass not handed the latch. It must disagree with "
         "CrrPos, or the latch argument is a value nothing reads") {
    RoomDzb dzb = read_room_dzb(golden("kaisen_r0_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    stand_cyls(cyls);

    int differed = 0, frames = 0;
    const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
    for (size_t fi = 0; fi < derived.size(); fi++) {
        const DerivedFrame& f = derived[fi];
        frames++;
        cXyz frame_pos;
        run_frame(room, f, cyls, &frame_pos);
        const cXyz dropped = stage_by_hand(room, f, cyls, false, nullptr, nullptr);
        if (bits(frame_pos.x) != bits(dropped.x) || bits(frame_pos.y) != bits(dropped.y) ||
            bits(frame_pos.z) != bits(dropped.z)) {
            differed++;
        }
    }
    c.note(std::to_string(differed) + " of " + std::to_string(frames) +
           " frame(s) answer differently with the latch dropped");
    REQUIRE_TRUE(c, differed == 0,
                 "staging the frame with the latch dropped answers what CrrPos answers - which "
                 "would mean SetWallHDirect is a field nobody reads");
}

TWWE_RED_CONTROL(red_the_frame_runs_the_wall_pass_before_the_line_check,
         "the same three stages in the wrong order - wall, line, line - which is a difference "
         "only a frame can have, because each stage on its own is unchanged. It must disagree "
         "with CrrPos, or the case above is measuring that three calls are three calls") {
    RoomDzb dzb = read_room_dzb(golden("kaisen_r0_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    stand_cyls(cyls);

    int differed = 0, frames = 0;
    const std::vector<DerivedFrame> derived = derive_frames(room, dzb);
    for (size_t fi = 0; fi < derived.size(); fi++) {
        const DerivedFrame& f = derived[fi];
        frames++;

        cXyz frame_pos;
        run_frame(room, f, cyls, &frame_pos);

        cXyz swapped = f.pos;
        Room::WallResult w;
        room.WallCorrect(&swapped, f.old_pos, 0.0f, cyls, 3, &w);
        Room::LineResult l1;
        room.LineCheck(&swapped, f.old_pos, cyls, 3, &l1);
        if (l1.hit) {
            Room::LineResult l2;
            room.LineCheck(&swapped, f.old_pos, cyls, 3, &l2);
        }
        if (bits(frame_pos.x) != bits(swapped.x) || bits(frame_pos.y) != bits(swapped.y) ||
            bits(frame_pos.z) != bits(swapped.z)) {
            differed++;
        }
    }
    c.note(std::to_string(differed) + " of " + std::to_string(frames) +
           " frame(s) answer differently with the wall pass first");
    REQUIRE_TRUE(c, differed == 0,
                 "running the wall pass before the line check answers what CrrPos answers - "
                 "which would mean the order this file gates is not in the answer");
}

}  // namespace testing
}  // namespace tww_engine
