// test_wall_correct.cpp - the wall pass. No console capture carries a corrected position, so this
// holds three weaker things:
//   the differential   the port's answers written out for a comparison against the old sim over
//                      the same positions (an oracle, not a gate: two ports of one decomp);
//   the preconditions  cM2d_CrossCirLin reads `t` uninitialised on two arms; which the rooms'
//                      geometry can reach is measured here, and whether a probe does is counted
//                      in test_wall_walk.cpp;
//   the primitive      the console's sqrt is not the decomp's `std::sqrtf`; the two are shown to
//                      be distinguishable, and their agreement rate is measured.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "SSystem/SComponent/c_m3d.h"
#include "SSystem/SComponent/c_m3d_g_cir.h"
#include "SSystem/SComponent/c_m2d.h"
#include "engine/ppc_fp.h"
#include "engine/room.h"
#include "framework/golden.h"
#include "framework/json.h"
#include "framework/runner.h"
#include "room_dzb.h"
#include "wall_probes.h"
#include "wall_walk.h"

using tww_engine::PassChk;
using tww_engine::Room;
using tww_engine::RoomDzb;
using tww_engine::kMaxWallCyl;
using tww_engine::testing::golden;
using tww_engine::testing::Json;
using tww_engine::testing::read_room_dzb;
using tww_engine::testing::wall_and_roof_chain_polys;
using tww_engine::testing::wall_face_probe;

namespace {

//: The rooms the differential runs on, so the preconditions are measured over the same geometry.
const char* kRooms[] = {"kaze_r11_bgd.json", "ganona_r0_bgd.json", "sea_r41_bgd.json",
                        "kaisen_r0_bgd.json"};


}  // namespace

// ===============================================================================================
// The square root
// ===============================================================================================

TWWE_TEST(the_console_sqrt_is_a_different_function,
          "the decomp writes std::sqrtf and the DOL inlines frsqrte plus three Newton steps; this "
          "holds both halves of the substitution - an argument that tells the two apart, and the "
          "rate at which they agree on everything the wall pass can actually hand them") {
    // Distinguishable: the console's `ble` leaves a negative argument alone, where sqrtss gives NaN.
    REQUIRE_BITS(c, ppc::sqrtf_msl(-1.0f), -1.0f,
                 "sqrtf(-1.0f) is -1.0f on the console: fcmpo/ble leaves f4 untouched");
    REQUIRE_BITS(c, ppc::sqrtf_msl(-1.0e-30f), -1.0e-30f, "sqrtf(-1e-30f) likewise");
    REQUIRE_TRUE(c, std::isnan(std::sqrt(-1.0f)),
                 "and the library's sqrt of a negative is NaN, which is what makes the pair a "
                 "discriminator rather than two spellings");
    REQUIRE_TRUE(c, std::isnan(ppc::sqrtf_msl(HUGE_VALF)) && std::isinf(std::sqrt(HUGE_VALF)),
                 "+inf is the second one: frsqrte(+inf) is 0, so the refinement produces NaN");

    // Agreement: each f32 root in [1,4) becomes its hardest argument (the midpoint above it,
    // squared, rounded to f32). sqrt(x * 4^k) is sqrt(x) * 2^k exactly and frsqrte's table index
    // depends only on the mantissa and the exponent's low bit, so two binades cover every normal
    // argument. The full sweep of 16,777,216 agrees bit for bit; the substitution follows the DOL.
    unsigned differ = 0, tested = 0;
    for (uint32_t base : {0x3F800000u, 0x40000000u}) {   // 1.0f, 2.0f
        for (uint32_t k = 0; k < (1u << 23); k += 97) {  // 1-in-97 stride, for suite time
            const float y = tww_engine::testing::from_bits(base + k);
            const float y2 = tww_engine::testing::from_bits(base + k + 1);
            const double m = ((double)y + (double)y2) * 0.5;
            const float x = (float)(m * m);
            tested++;
            if (tww_engine::testing::bits(ppc::sqrtf_msl(x)) !=
                tww_engine::testing::bits(std::sqrt(x))) {
                differ++;
            }
        }
    }
    REQUIRE_INT(c, (long long)differ, 0,
                "midpoint-targeted arguments where the console's sqrt and the library's differ");
    c.note(std::to_string(tested) + " midpoint-targeted argument(s) over [1,4), " +
           std::to_string(differ) + " disagreement(s) - the substitution changes no answer this "
           "repo can produce, and is made because the DOL says so");
}

TWWE_RED_CONTROL(red_sqrt_is_the_library_one,
                 "the correctly-rounded library sqrt in place of the console's, asked the one "
                 "question that tells them apart - a negative argument, which the console returns "
                 "unchanged and sqrtss turns into NaN. This is the control for the substitution: "
                 "without it, 'we use the console's sqrt' is a sentence in a comment") {
    REQUIRE_BITS(c, std::sqrt(-1.0f), -1.0f, "the library's sqrt of -1.0f is not -1.0f");
}

// ===============================================================================================
// The uninitialised arms of cM2d_CrossCirLin
// ===============================================================================================

TWWE_TEST(the_uninitialised_arms_of_cross_cir_lin_are_one_shut_and_one_open,
          "cM2d_CrossCirLin reads `t` uninitialised on two arms and the port copies it that way. "
          "One is shut by algebra and gated here. The other is not: some of the four rooms' "
          "wall/roof polygons are flat enough in XZ to enter it, so this measures the population "
          "and marks the gap rather than asserting it away") {
    // Arm two, `dVar10 < 0.0f` where dVar10 = dVar14*dVar14 - (4.0f * dVar13) * c, is shut:
    // JUT_ASSERT(0x47) requires c < 0 (and aborts otherwise), so with dVar13 > 0 dVar10 > 0.
    //
    // Arm one, `cM3d_IsZero(dVar13) && cM3d_IsZero(dVar14)`, assigns no `t`. dVar13 == sp68 * sp68
    // with sp68 the polygon's xz normal length, which RwgWallCorrect only requires to pass
    // `!cM3d_IsZero(sp68)`; sp68 below 1.9531e-03 still squares to zero, so reachability depends
    // on how flat the room's wall/roof polygons are, measured below.
    const float kAbsMin = G_CM3D_F_ABS_MIN;
    const float kSafe = std::sqrt(kAbsMin);  // the sp68 above which sp68*sp68 is not IsZero

    int rooms = 0, polys = 0, asked = 0, too_flat = 0;
    float worst = 1.0f;
    std::string worst_where;
    for (const char* name : kRooms) {
        RoomDzb dzb = read_room_dzb(golden(name));
        Room room(dzb);
        rooms++;
        for (int poly : wall_and_roof_chain_polys(room)) {
            polys++;
            const cXyz* n = room.bgw().pm_tri[poly].m_plane.GetNP();
            const f32 sp68 = ppc::sqrtf_msl(SQUARE(n->x) + SQUARE(n->z));
            if (cM3d_IsZero(sp68)) {
                continue;  // RwgWallCorrect drops it before cM2d_CrossCirLin can be reached
            }
            asked++;
            if (sp68 < worst) {
                worst = sp68;
                worst_where = std::string(name) + " poly " + std::to_string(poly);
            }
            if (cM3d_IsZero(SQUARE(sp68))) {
                too_flat++;
            }
        }
    }
    REQUIRE_INT(c, (long long)rooms, 4, "rooms scanned");
    REQUIRE_TRUE(c, asked > 0,
                 "the population is not empty - a rate over zero polygons reports success");
    // Arm one is open: these rooms have polygons flat enough to enter it. No probe reaches it
    // (counted in test_wall_walk.cpp), but the polygons remain, so it stands as a known gap.
    EXPECT_KNOWN_GAP(c, too_flat == 0,
                     "cM2d_CrossCirLin's `cM3d_IsZero(dVar13) && cM3d_IsZero(dVar14)` arm "
                     "leaves `t` unassigned, and these rooms contain polygons flat enough to "
                     "enter it. No probe reaches it - test_wall_walk.cpp counts that at the "
                     "call site - so what stands is the population and not a defect. Unmark "
                     "when the count reaches 0");
    c.note(std::to_string(polys) + " wall/roof-chain polygon(s) in " + std::to_string(rooms) +
           " room(s); " + std::to_string(asked) + " survive cM3d_IsZero(sp68) and can reach the "
           "corner arm, of which " + std::to_string(too_flat) + " have sp68*sp68 below "
           "G_CM3D_F_ABS_MIN. The flattest is " + worst_where + " at |n_xz| " +
           std::to_string(worst) + ", against the " + std::to_string(kSafe) +
           " below which sp68*sp68 reads as zero");
}

TWWE_RED_CONTROL(red_the_flatness_bound_is_cM3d_IsZero_of_sp68,
                 "the precondition above read off RwgWallCorrect's own guard - `!cM3d_IsZero(sp68)` "
                 "- instead of `!cM3d_IsZero(sp68*sp68)`, which is what cM2d_CrossCirLin tests. The "
                 "two spellings are one square apart and the gap between them is three orders of "
                 "magnitude wide; a polygon inside it passes the walk's guard and still reaches the "
                 "uninitialised arm, so a case that checked the walk's spelling would report every "
                 "room clean and prove nothing") {
    // A wall-chain polygon a twentieth of a degree from flat.
    const f32 sp68 = 1.0e-3f;
    REQUIRE_TRUE(c, !cM3d_IsZero(sp68),
                 "RwgWallCorrect's own guard lets this polygon through - which is the premise, "
                 "and it holds");
    REQUIRE_TRUE(c, !cM3d_IsZero(SQUARE(sp68)),
                 "...and this is the claim the case above makes. It is false here: sp68*sp68 is "
                 "1e-06, below G_CM3D_F_ABS_MIN, so `t` would be read uninitialised. The gap is "
                 "real and the case measures that no room falls in it");
}

// ===============================================================================================
// The differential
// ===============================================================================================
//
// `Room::WallCorrect` over positions supplied by the run, for comparison against the old sim's
// `core.collision.wall_correct`. Written out: corrected X and Z as bits and decimals, the wall-hit
// flag, and the per-cylinder polygon and angle (the old sim has no counterpart for the last).
// With TWWE_DIFF_WALL_VISITS, also the polygons the descent offered, in order: the old sim walks
// the whole list, so re-asking it over this list separates the octree prune from a real
// disagreement.

TWWE_TEST(the_port_corrects_the_wall_positions_a_wall_differential_run_asks_for,
          "with TWWE_DIFF_WALL_POINTS set, the port's corrected position at every position the "
          "old sim will also be asked about - written out to diff against the old sim, so the "
          "console is only ever spent where two engines disagree") {
    const char* in_path = std::getenv("TWWE_DIFF_WALL_POINTS");
    const char* out_path = std::getenv("TWWE_DIFF_WALL_OUT");
    if (in_path == nullptr || out_path == nullptr) {
        c.note("set TWWE_DIFF_WALL_POINTS=<points.json> and TWWE_DIFF_WALL_OUT=<answers.json> to "
               "run the wall differential (TWWE_DIFF_WALL_VISITS to carry the visit list too). "
               "Unset, this case answers nothing and asserts nothing");
        REQUIRE_TRUE(c, true, "");
        return;
    }
    Json pts;
    std::string err;
    REQUIRE_TRUE(c, Json::load(in_path, &pts, &err),
                 std::string("TWWE_DIFF_WALL_POINTS could not be read: ") + err);
    const Json& rows = pts["points"];
    const std::string room_name = pts["bgd"].str;

    // Cylinders come from the run: setBgCheckParam chooses them per proc.
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
    const f32 speed_y = pts["speed_y"].as_f32();

    // Opt-in: the visit list is ~20x the row it sits beside.
    const bool want_visits = std::getenv("TWWE_DIFF_WALL_VISITS") != nullptr;
    std::vector<int> visited;

    // The room is the golden the run names; an unknown name fails in the golden store.
    RoomDzb dzb = read_room_dzb(golden(room_name));
    Room fx_room(dzb);

    // `undef`: cM3d_Len2dSqPntAndSegLine's `cM3d_IsZero(dot)` arm leaves the closest point
    // unassigned and RwgWallCorrect's facing test reads it, so there the answer is stack-dependent.
    // Counted on the `SegAssignsStart` variant (which assigns the segment start, as the old sim
    // does), because an unmutated walk can diverge and trip cM2d_CrossCirLin's JUT_ASSERT. The
    // first degenerate read precedes any divergence, so `undef > 0` means the ported pass read an
    // unassigned local; the count itself is the variant's.
    tww_engine::testing::WallWalk undef_walk(fx_room,
                                             tww_engine::testing::WallVariant::SegAssignsStart);

    //: Rows carrying a wall height latched by an earlier line check, reported in the note.
    int latched_rows = 0;

    std::string body;
    for (size_t i = 0; i < rows.size(); i++) {
        cXyz pos;
        pos.x = rows[i]["x"].as_f32();
        pos.y = rows[i]["y"].as_f32();
        pos.z = rows[i]["z"].as_f32();
        // old_pos == pos: the wall pass alone, with SetLin's segment degenerate. A real frame
        // passes the pre-movement position.
        const cXyz old_pos = pos;

        // A wall height latched by the frame's first line check, when the row carries one;
        // without it the pass cuts at a derived height.
        const Json& ws = rows[i]["whd_set"];
        Room::LineResult latch;
        for (int k = 0; k < kMaxWallCyl; k++) {
            latch.whd_set[k] = false;
            latch.whd[k] = 0.0f;
        }
        const bool has_latch = ws.size() > 0;
        if (has_latch) {
            REQUIRE_TRUE(c, (int)ws.size() == tbl_size && (int)rows[i]["whd"].size() == tbl_size,
                         "row " + std::to_string(i) +
                             ": whd_set and whd name one value per cylinder");
            bool any = false;
            for (int k = 0; k < tbl_size && k < (int)ws.size(); k++) {
                latch.whd_set[k] = ws[(size_t)k].boolean;
                latch.whd[k] = rows[i]["whd"][(size_t)k].as_f32();
                any = any || latch.whd_set[k];
            }
            if (any) {
                latched_rows++;
            }
        }

        Room::WallResult res;
        visited.clear();
        fx_room.LogVisitedPolys(want_visits ? &visited : nullptr);
        fx_room.WallCorrect(&pos, old_pos, speed_y, cyls, tbl_size, &res, PassChk::Link,
                            has_latch ? &latch : nullptr);
        fx_room.LogVisitedPolys(nullptr);
        cXyz undef_pos = old_pos;
        Room::WallResult undef_res;
        undef_walk.run(&undef_pos, old_pos, speed_y, cyls, tbl_size, &undef_res,
                       has_latch ? &latch : nullptr);
        const int undef = undef_walk.degenerate_reads();
        char buf[512];
        std::snprintf(buf, sizeof(buf),
                      "%s{\"i\": %zu, \"x\": %.9g, \"z\": %.9g, \"x_bits\": %u, \"z_bits\": %u, "
                      "\"hit\": %s, \"undef\": %d, \"cir_poly\": [%d, %d, %d], "
                      "\"cir_angle\": [%d, %d, %d]",
                      i ? ",\n" : "", i, (double)pos.x, (double)pos.z,
                      (unsigned)tww_engine::testing::bits(pos.x),
                      (unsigned)tww_engine::testing::bits(pos.z),
                      res.wall_hit ? "true" : "false", undef,
                      res.cir_poly[0], res.cir_poly[1], res.cir_poly[2],
                      (int)res.cir_angle[0], (int)res.cir_angle[1], (int)res.cir_angle[2]);
        body += buf;
        if (want_visits) {
            body += ", \"visited\": [";
            for (size_t v = 0; v < visited.size(); v++) {
                body += (v ? "," : "") + std::to_string(visited[v]);
            }
            body += "]";
        }
        body += "}";
    }
    // The room's planes, when asked: a normal that is noise in x (Kaisen r0 has n.x of 2e-09)
    // decides `sp50` and the sign of RwgWallCorrect's facing test, so one ulp here flips a hit.
    const char* pla_path = std::getenv("TWWE_DIFF_WALL_PLANES");
    if (pla_path != nullptr) {
        std::FILE* pf = std::fopen(pla_path, "wb");
        REQUIRE_TRUE(c, pf != nullptr,
                     std::string("TWWE_DIFF_WALL_PLANES could not be opened: ") + pla_path);
        if (pf != nullptr) {
            std::fprintf(pf, "{\"bgd\": \"%s\", \"planes\": [\n", room_name.c_str());
            for (int t = 0; t < fx_room.tri_count(); t++) {
                const cM3dGPla& pla = fx_room.bgw().pm_tri[t].m_plane;
                std::fprintf(pf, "%s[%u, %u, %u, %u]", t ? ",\n" : "",
                             (unsigned)tww_engine::testing::bits(pla.GetNP()->x),
                             (unsigned)tww_engine::testing::bits(pla.GetNP()->y),
                             (unsigned)tww_engine::testing::bits(pla.GetNP()->z),
                             (unsigned)tww_engine::testing::bits(pla.mD));
            }
            std::fprintf(pf, "\n]}\n");
            std::fclose(pf);
        }
    }

    std::FILE* f = std::fopen(out_path, "wb");
    REQUIRE_TRUE(c, f != nullptr,
                 std::string("TWWE_DIFF_WALL_OUT could not be opened: ") + out_path);
    if (f != nullptr) {
        std::fprintf(f, "{\"bgd\": \"%s\", \"answers\": [\n%s\n]}\n", room_name.c_str(),
                     body.c_str());
        std::fclose(f);
    }
    c.note(std::to_string(rows.size()) + " position(s) corrected from " + room_name + ", " +
           std::to_string(latched_rows) + " of them with a wall height latched by a line check" +
           " -> " + out_path);
}

// ===============================================================================================
// The visit log
// ===============================================================================================
//
// `Room::LogVisitedPolys` overrides a virtual the decomp's walk dispatches through. It must not
// change the answer, and the list must be the descent's rather than the room's.

TWWE_TEST(the_visit_log_does_not_change_the_answer,
          "every wall probe in kaze r11 run twice, once with the log off and once with it on: "
          "position, hit flag, per-cylinder polygon and per-cylinder angle have to be bit for "
          "bit the same. An observer that moves Link would make every prune attribution a "
          "statement about the instrumented engine") {
    RoomDzb dzb = read_room_dzb(golden("kaze_r11_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    const f32 hs[3] = {30.1f, 89.9f, 125.0f};
    for (int i = 0; i < 3; i++) {
        cyls[i].h = hs[i];
        cyls[i].r = 35.0f;
    }

    std::vector<int> visited;
    int tried = 0, corrected = 0, logged = 0;
    for (int poly : wall_and_roof_chain_polys(room)) {
        cXyz start;
        if (!wall_face_probe(room, dzb, poly, hs[1], 0.5f * 35.0f, &start)) {
            continue;
        }
        tried++;

        cXyz off_pos = start;
        Room::WallResult off;
        room.LogVisitedPolys(nullptr);
        room.WallCorrect(&off_pos, start, -2.5f, cyls, 3, &off);

        cXyz on_pos = start;
        Room::WallResult on;
        visited.clear();
        room.LogVisitedPolys(&visited);
        room.WallCorrect(&on_pos, start, -2.5f, cyls, 3, &on);
        room.LogVisitedPolys(nullptr);

        const std::string at = "poly " + std::to_string(poly);
        REQUIRE_BITS(c, on_pos.x, off_pos.x, at + " x");
        REQUIRE_BITS(c, on_pos.z, off_pos.z, at + " z");
        REQUIRE_INT(c, on.wall_hit ? 1 : 0, off.wall_hit ? 1 : 0, at + " wall_hit");
        for (int i = 0; i < 3; i++) {
            const std::string col = at + " cyl " + std::to_string(i);
            REQUIRE_INT(c, on.cir_hit[i] ? 1 : 0, off.cir_hit[i] ? 1 : 0, col + " hit");
            REQUIRE_INT(c, on.cir_poly[i], off.cir_poly[i], col + " poly");
            REQUIRE_INT(c, (long long)on.cir_angle[i], (long long)off.cir_angle[i], col + " angle");
        }
        if (off.wall_hit) {
            corrected++;
        }
        logged += (int)visited.size();
    }
    REQUIRE_TRUE(c, tried > 0, "the population is not empty");
    REQUIRE_TRUE(c, corrected > 0, "and the pass fired on some of it");
    REQUIRE_TRUE(c, logged > 0, "and the log recorded something to be wrong about");
    c.note(std::to_string(tried) + " probe(s), " + std::to_string(corrected) +
           " corrected, " + std::to_string(logged) +
           " polygon(s) logged - the logged run bit-identical to the unlogged one throughout");
}

TWWE_TEST(the_visit_log_is_the_descents_and_not_the_rooms,
          "what comes back is a subset of the room's wall and roof chains, without repeats, and "
          "it contains every polygon a cylinder recorded as the one that corrected it. Those "
          "three together are what make the list usable as a counterfactual mesh: a log that "
          "missed the correcting polygon would attribute by removing the cause") {
    RoomDzb dzb = read_room_dzb(golden("kaze_r11_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    const f32 hs[3] = {30.1f, 89.9f, 125.0f};
    for (int i = 0; i < 3; i++) {
        cyls[i].h = hs[i];
        cyls[i].r = 35.0f;
    }

    const std::vector<int> chain = wall_and_roof_chain_polys(room);
    std::vector<bool> on_chain((size_t)room.tri_count(), false);
    for (int poly : chain) {
        on_chain[(size_t)poly] = true;
    }

    std::vector<int> visited;
    int tried = 0, off_chain = 0, repeats = 0, unlogged_corrector = 0, pruned_probes = 0;
    long long total_logged = 0;
    for (int poly : chain) {
        cXyz start;
        if (!wall_face_probe(room, dzb, poly, hs[1], 0.5f * 35.0f, &start)) {
            continue;
        }
        tried++;
        cXyz pos = start;
        Room::WallResult res;
        visited.clear();
        room.LogVisitedPolys(&visited);
        room.WallCorrect(&pos, start, -2.5f, cyls, 3, &res);
        room.LogVisitedPolys(nullptr);

        std::vector<bool> seen((size_t)room.tri_count(), false);
        for (size_t v = 0; v < visited.size(); v++) {
            const int p = visited[v];
            if (p < 0 || p >= room.tri_count() || !on_chain[(size_t)p]) {
                off_chain++;
                continue;
            }
            if (seen[(size_t)p]) {
                repeats++;
            }
            seen[(size_t)p] = true;
        }
        for (int i = 0; i < 3; i++) {
            if (res.cir_hit[i] && res.cir_poly[i] != 0xFFFF &&
                (res.cir_poly[i] >= room.tri_count() || !seen[(size_t)res.cir_poly[i]])) {
                unlogged_corrector++;
            }
        }
        total_logged += (long long)visited.size();
        if (visited.size() < chain.size()) {
            pruned_probes++;
        }
    }
    REQUIRE_TRUE(c, tried > 0, "the population is not empty");
    REQUIRE_INT(c, (long long)off_chain, 0,
                "logged polygons that are on no wall or roof chain at all");
    REQUIRE_INT(c, (long long)repeats, 0, "polygons the descent offered twice in one query");
    REQUIRE_INT(c, (long long)unlogged_corrector, 0,
                "polygons a cylinder recorded as its corrector that the log does not carry");
    // The prune bites: a log of the whole chain list would satisfy the three checks above.
    REQUIRE_INT(c, (long long)pruned_probes, (long long)tried,
                "probes whose descent reached fewer polygons than the room has");
    c.note(std::to_string(tried) + " probe(s) over " + std::to_string(chain.size()) +
           " wall/roof polygon(s); the descent offered " + std::to_string(total_logged) +
           " in total, " + std::to_string(total_logged / (tried ? tried : 1)) + " per probe");
}

TWWE_RED_CONTROL(red_the_walk_visits_every_wall_polygon,
                 "claims the descent offers the room's whole wall and roof chain list at every "
                 "position - which is what the old sim walks. It must fail: if it ever passed, "
                 "the visit list would be attributing the prune with the prune switched off") {
    RoomDzb dzb = read_room_dzb(golden("kaze_r11_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    const f32 hs[3] = {30.1f, 89.9f, 125.0f};
    for (int i = 0; i < 3; i++) {
        cyls[i].h = hs[i];
        cyls[i].r = 35.0f;
    }

    const std::vector<int> chain = wall_and_roof_chain_polys(room);
    std::vector<int> visited;
    for (size_t k = 0; k < chain.size(); k++) {
        cXyz start;
        if (!wall_face_probe(room, dzb, chain[k], hs[1], 0.5f * 35.0f, &start)) {
            continue;
        }
        cXyz pos = start;
        Room::WallResult res;
        visited.clear();
        room.LogVisitedPolys(&visited);
        room.WallCorrect(&pos, start, -2.5f, cyls, 3, &res);
        room.LogVisitedPolys(nullptr);
        REQUIRE_INT(c, (long long)visited.size(), (long long)chain.size(),
                    "poly " + std::to_string(chain[k]) + ": polygons offered by the descent");
    }
}

// ===============================================================================================
// The pass fires, in the direction the geometry says
// ===============================================================================================
//
// Not an oracle: the walk reaches a polygon, the correction has the right sign and magnitude
// class, and the per-cylinder polygon and angle the procs read are filled in.

TWWE_TEST(the_wall_pass_pushes_him_out_along_the_polygons_own_normal,
          "a position placed inside a known wall polygon comes back outside it, moved along that "
          "polygon's XZ normal and by about the distance that was missing - and the cylinder "
          "records which polygon did it. Without this the differential could be comparing two "
          "engines that both do nothing") {
    RoomDzb dzb = read_room_dzb(golden("kaze_r11_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    const f32 wall_r = 35.0f;
    const f32 hs[3] = {30.1f, 89.9f, 125.0f};
    for (int i = 0; i < 3; i++) {
        cyls[i].h = hs[i];
        cyls[i].r = wall_r;
    }

    int tried = 0, corrected = 0, wrong_side = 0, over_radius = 0, no_poly = 0;
    for (int poly : wall_and_roof_chain_polys(room)) {
        // Half a radius inside, through the probe derivation the differential shares.
        cXyz pos;
        f32 ux, uz;
        if (!wall_face_probe(room, dzb, poly, hs[1], 0.5f * wall_r, &pos, &ux, &uz)) {
            continue;
        }
        const cXyz start = pos;
        const cXyz old_pos = pos;

        Room::WallResult res;
        tried++;
        if (!room.WallCorrect(&pos, old_pos, -2.5f, cyls, 3, &res)) {
            continue;
        }
        corrected++;
        // Outward, along +n.
        const f32 dx = pos.x - start.x, dz = pos.z - start.z;
        if (dx * ux + dz * uz < 0.0f) {
            wrong_side++;
        }
        // Bounded: longer than 2r would be a sign error in the segment maths.
        const f32 moved = ppc::sqrtf_msl(dx * dx + dz * dz);
        if (moved > 2.0f * wall_r) {
            over_radius++;
        }
        // Attributed: some cylinder names the polygon, which procWait's wall snap reads.
        bool named = false;
        for (int i = 0; i < 3; i++) {
            if (res.cir_hit[i] && res.cir_poly[i] != 0xFFFF) {
                named = true;
            }
        }
        if (!named) {
            no_poly++;
        }
    }
    REQUIRE_TRUE(c, tried > 0, "the population is not empty");
    REQUIRE_TRUE(c, corrected > 0,
                 "at least one probe was corrected - a wall pass that never fires would pass "
                 "every other assertion in this case");
    REQUIRE_INT(c, (long long)wrong_side, 0, "corrections that moved him into the wall");
    REQUIRE_INT(c, (long long)over_radius, 0, "corrections longer than two wall radii");
    REQUIRE_INT(c, (long long)no_poly, 0, "corrections no cylinder recorded a polygon for");
    c.note(std::to_string(corrected) + " of " + std::to_string(tried) +
           " half-radius probes corrected in kaze r11, every one outward, bounded, and recorded "
           "against the polygon that did it");
}

TWWE_TEST(a_position_outside_the_radius_is_left_alone,
          "the other end of the population: past the radius the pass must be an exact no-op, "
          "bit for bit. This is what says the corrections above came from the geometry and not "
          "from the pass moving everything it is handed") {
    RoomDzb dzb = read_room_dzb(golden("kaze_r11_bgd.json"));
    Room room(dzb);

    Room::WallCyl cyls[3];
    const f32 hs[3] = {30.1f, 89.9f, 125.0f};
    for (int i = 0; i < 3; i++) {
        cyls[i].h = hs[i];
        cyls[i].r = 35.0f;
    }

    int tried = 0, moved = 0, reached = 0;
    for (int poly : wall_and_roof_chain_polys(room)) {
        // Ten radii out along this polygon's normal. Some land inside a different wall, so what
        // is counted is whether this polygon corrected him.
        cXyz pos;
        if (!wall_face_probe(room, dzb, poly, hs[1], 10.0f * 35.0f, &pos)) {
            continue;
        }
        const cXyz start = pos;
        Room::WallResult res;
        tried++;
        room.WallCorrect(&pos, start, -2.5f, cyls, 3, &res);
        bool by_this_poly = false;
        for (int i = 0; i < 3; i++) {
            if (res.cir_hit[i] && res.cir_poly[i] == poly) {
                by_this_poly = true;
            }
        }
        if (by_this_poly) {
            reached++;
        }
        if (tww_engine::testing::bits(pos.x) != tww_engine::testing::bits(start.x) ||
            tww_engine::testing::bits(pos.z) != tww_engine::testing::bits(start.z)) {
            moved++;
        }
    }
    REQUIRE_TRUE(c, tried > 0, "the population is not empty");
    REQUIRE_INT(c, (long long)reached, 0,
                "probes ten radii out that their own polygon corrected anyway");
    REQUIRE_TRUE(c, moved < tried,
                 "and not every probe was moved by something else either - if every one were, "
                 "this would be measuring a room with no empty space rather than a pass with a "
                 "radius");
    c.note(std::to_string(tried) + " probe(s) ten radii outside their own polygon: 0 corrected by "
           "it, " + std::to_string(moved) + " moved by a different wall the position landed in. "
           "So the corrections the case above counts are the geometry's, and not the pass moving "
           "everything it is handed");
}
