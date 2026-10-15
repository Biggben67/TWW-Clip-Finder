// test_crawl_pos.cpp - the crawl's position: root motion (posMove's m34C2 == 1 arm),
// crawlBgCheck's wall push and dBgS_Acch::CrrPos, one frame at a time against Kaisen r0, compared
// with the console's next row.
//
// A crawl has no speed (potential_speed and true_speed are 0.0 on every console crawl row, asserted
// in test_crawl.cpp), so its travel is the animation's joint-0 translate plus the wall pushes. The
// room is Kaisen r0: the capture header names it, and the first body rows sit at z = 770.0001,
// Link's collision radius off the z = 800 wall.
//
// Not gated here:
//   * the demo capture: nothing in it settles which room it was recorded in;
//   * joints 1-41: baked, but no ported body reads them (test_crawl.cpp holds anm_track_nonroot
//     at 0);
//   * the other m34C2 arms (11, 10, 2/6, 4): each writes the old-frame joint-0 transform, which is
//     asserted still zero after the run.
// checkNoCollisionCorret names daPyProc_CRAWL_END_e, so the crawl-up skips posMove's collision
// push, wind, ground slip and conveyor; the GetCCMoveP ask count pins that.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "crawl_replay.h"
#include "framework/golden.h"
#include "framework/json.h"
#include "framework/require_bits.h"
#include "framework/runner.h"
#include "player_rig.h"
#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::CrawlCapture;
using tww_engine::testing::CrawlFrame;
using tww_engine::testing::CrawlReplayOptions;
using tww_engine::testing::CrawlRun;
using tww_engine::testing::Json;

/// The only capture this file can speak about - the one whose room the data settles.
const CrawlCapture& cap() {
    return tww_engine::testing::crawl_capture(tww_engine::testing::kCrawlWall);
}

const Json& rows() {
    return tww_engine::testing::crawl_rows(tww_engine::testing::golden(cap().golden), cap());
}

std::vector<CrawlRun> replay(const CrawlReplayOptions& opt) {
    return tww_engine::testing::run_crawl_replay(rows(), cap(), opt);
}

/// Every compared column of one frame, in one place, so a red control cannot compare less than
/// the gate it is a control on.
void compare_frame(Case& c, const CrawlFrame& r) {
    const Json& want = rows()[size_t(r.frame)];
    char where[128];
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X, m34C2 %d) pos.x",
                  r.frame, r.proc, r.m34c2);
    c.check_bits(r.pos_x_bits, tww_engine::testing::bits(want["pos_x"].as_f32()), where);
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X, m34C2 %d) pos.y",
                  r.frame, r.proc, r.m34c2);
    c.check_bits(r.pos_y_bits, tww_engine::testing::bits(want["pos_y"].as_f32()), where);
    std::snprintf(where, sizeof(where), "frame %d (proc 0x%02X, m34C2 %d) pos.z",
                  r.frame, r.proc, r.m34c2);
    c.check_bits(r.pos_z_bits, tww_engine::testing::bits(want["pos_z"].as_f32()), where);
}

void compare_all(Case& c, const std::vector<CrawlRun>& runs) {
    for (size_t i = 0; i < runs.size(); i++) {
        for (size_t j = 0; j < runs[i].rows.size(); j++) {
            compare_frame(c, runs[i].rows[j]);
        }
    }
}

/// The port's sampler driven as posMove drives it: setFrame(), then getTransform(0). frameMax is
/// procCrawlStart_init's; the .bck's attribute is EMode_NONE.
void sample_lie(const daPy_portAnmTrack* track, float frame, J3DTransformInfo* out) {
    daPy_portAnm_c anm;
    anm.load(9, J3DFrameCtrl::EMode_NONE, track);
    anm.setFrame(frame);
    anm.getTransform(0, out);
}

/// The first row whose console pos_z differs from the entry row's; before it Link is pinned at
/// the wall's clamp distance. Read off the capture.
int first_unpinned_row(int entry) {
    const uint32_t pinned = tww_engine::testing::bits(rows()[size_t(entry)]["pos_z"].as_f32());
    for (int f = entry + 1; f < int(rows().size()); f++) {
        if (tww_engine::testing::bits(rows()[size_t(f)]["pos_z"].as_f32()) != pinned) {
            return f;
        }
    }
    return int(rows().size());
}

}  // namespace

TWWE_TEST(the_crawls_position_is_the_consoles,
          "a frame of the crawl - the proc, posMove's root motion and dBgS_Acch::CrrPos against "
          "Kaisen r0 - leaves current.pos where the console left it") {
    const std::vector<CrawlRun> runs = replay(CrawlReplayOptions{});
    c.require(!runs.empty(), "the replay produced no runs");

    int compared = 0;
    int wall = 0;
    int ground = 0;
    for (size_t i = 0; i < runs.size(); i++) {
        const CrawlRun& run = runs[i];
        c.require(run.stopped_on_proc < 0,
                  "the replay stopped on a proc this port has no body for");
        for (size_t j = 0; j < run.rows.size(); j++) {
            const CrawlFrame& r = run.rows[j];
            c.require(r.pos_recorded, "a frame of the wall capture recorded no position");
            compare_frame(c, r);
            // The crawl's bodies write m34C2 = 1 every frame; anything else means another arm ran.
            char where[96];
            std::snprintf(where, sizeof(where), "frame %d m34C2 - the root-motion arm", r.frame);
            c.check_int(r.m34c2, 1, where);
            wall += r.wall_hit ? 1 : 0;
            ground += r.ground_hit ? 1 : 0;
            compared++;
        }

        // first_unpinned_row is row 15 of 23 here; crawlBgCheck's probe fires on six of the rows
        // after it.
        c.require(first_unpinned_row(run.entry) < run.entry + int(run.rows.size()),
                  "the console never leaves the wall's clamp distance on this run - the rows the "
                  "crawl probe decides would then not be in it at all");

        // crawlBgCheck's push, measured across the proc dispatch, where nothing else writes
        // current.pos.
        c.require(run.push_frames > 0,
                  "crawlBgCheck moved current.pos on no frame - the probe found no geometry, and "
                  "the positions above would then be root motion and the acch alone");

        // One setWorldMatrix per integrated frame, so the probe endpoints are the frame's own.
        c.check_int(run.world_matrix_calls, run.integrated_frames,
                    "setWorldMatrix calls against integrated frames");
        // Each left m37B4 a real transform (a zero m37B4 is a setWorldMatrix whose last line did
        // nothing). Not a claim the inverse is right: m37B4 reaches no compared column here, and
        // tests/test_ps_inverse.cpp is its gate.
        c.check_int(run.world_inverse_frames, run.world_matrix_calls,
                    "frames where setWorldMatrix left m37B4 a real transform");
        // The ship arm is asked every frame and answers NULL: there is no ship actor.
        c.check_int(run.ship_actor_calls, run.world_matrix_calls,
                    "dComIfGp_getShipActor asks - the ship arm is evaluated before the status "
                    "bit, so it is asked once per frame and answers NULL every time");
        c.check_bits(run.old_frame_trans_bits[0], tww_engine::testing::bits(0.0f),
                     "the old-frame joint-0 translate x - non-zero means an m34C2 arm this port "
                     "has no skeleton to feed wrote it");
        c.check_bits(run.old_frame_trans_bits[1], tww_engine::testing::bits(0.0f),
                     "the old-frame joint-0 translate y");
        c.check_bits(run.old_frame_trans_bits[2], tww_engine::testing::bits(0.0f),
                     "the old-frame joint-0 translate z");
        // posMove asks GetCCMoveP four times on its main path and three on the
        // checkNoCollisionCorret fork. CRAWL_END is in that function's list and in the block
        // catalog, so the fork is taken on exactly the crawl-up's frames.
        c.check_int(run.integrated_frames, int(run.rows.size()) + 1,
                    "frames posMove ran on - the emitted rows plus the entry frame's own");
        c.check_int(run.cc_move_asks,
                    4 * run.integrated_frames - run.no_collision_corret_frames,
                    "GetCCMoveP asks - 4 per integrated frame, 3 on a frame that took the fork");
        c.check_int(run.no_collision_corret_frames, run.crawl_end_integrated,
                    "frames that took checkNoCollisionCorret's TRUE fork against the frames in "
                    "CRAWL_END - the crawl-up is the one term of that function this catalog can "
                    "reach, so any other count means a second term fired");
    }
    c.require(compared > 0, "no frame was compared");

    char note[240];
    std::snprintf(note, sizeof(note),
                  "%d frame(s) compared over %d run(s); the wall stage corrected %d of them and "
                  "the ground stage %d",
                  compared, (int)runs.size(), wall, ground);
    c.note(note);
}

TWWE_TEST(the_travel_after_the_wall_probe_is_not_the_animations,
          "the console's travel after the crawl probe fires is small enough that the animation "
          "could be supplying it, which would make the excluded rows a root-motion gap instead") {
    // ANM_LIE's joint-0 z track (generated/d/actor/anm_track.inc) is nearly flat from frame 5
    // (30.06, 31.64 at 6, 31.93 at 9), where the console's travel is largest; crawlBgCheck's
    // `current.pos -= push` is the only other term in the crawl that moves Link. The track is
    // read through the port's own sampler, as posMove reads it.
    const daPy_portAnmTrack* track = NULL;
    for (size_t i = 0; i < daPy_portAnmTrackTableSize(); i++) {
        if (daPy_portAnmTrackTableAt(i)->mBckIdx == dRes_INDEX_LKANM_BCK_LIE_e) {
            track = daPy_portAnmTrackTableAt(i);
        }
    }
    c.require(track != NULL, "ANM_LIE has no baked joint-0 track");

    const int first = 17;
    const int last = 20;
    c.require(last < int(rows().size()), "the capture is shorter than the rows this case names");

    J3DTransformInfo a;
    J3DTransformInfo b;
    sample_lie(track, rows()[size_t(first - 1)]["anim_frame"].as_f32(), &a);
    sample_lie(track, rows()[size_t(last)]["anim_frame"].as_f32(), &b);
    const f32 anim_dx = b.mTranslate.x - a.mTranslate.x;
    const f32 anim_dz = b.mTranslate.z - a.mTranslate.z;
    const double anim = std::sqrt(double(anim_dx) * anim_dx + double(anim_dz) * anim_dz);

    const f32 cx = rows()[size_t(last)]["pos_x"].as_f32() - rows()[size_t(first - 1)]["pos_x"].as_f32();
    const f32 cz = rows()[size_t(last)]["pos_z"].as_f32() - rows()[size_t(first - 1)]["pos_z"].as_f32();
    const double console = std::sqrt(double(cx) * cx + double(cz) * cz);

    // The root transform is a rigid translation rotated into world XZ, so its length bounds what
    // the animation can move Link whatever the facing.
    c.check_int(console > anim * 10.0 ? 1 : 0, 1,
                "the console's travel over rows 17-20 against what ANM_LIE's joint-0 track can "
                "supply - within 10x and the excluded rows would be a root-motion question");

    char note[240];
    std::snprintf(note, sizeof(note),
                  "rows %d-%d: the console travels %.3f units in XZ and ANM_LIE's joint-0 track "
                  "supplies %.3f of it - %.1f%% has a source outside the animation, and "
                  "crawlBgCheck's push is the only one the crawl's closure has",
                  first, last, console, anim, 100.0 * (1.0 - anim / console));
    c.note(note);
}

// ------------------------------------------------------------------- the red controls
//
// Statements of execute():11400-11406, removed one at a time; each reaches the positions by a
// different line.

TWWE_RED_CONTROL(red_the_root_motion_not_run,
                 "posMove skipped: the position holds the seed row on every frame while the "
                 "console's travels") {
    CrawlReplayOptions opt;
    opt.no_pos_move = true;
    compare_all(c, replay(opt));
}

TWWE_RED_CONTROL(red_the_collision_pass_not_run,
                 "dBgS_Acch::CrrPos skipped: the root motion alone, so nothing pushes Link back "
                 "out of the z = 800 wall he crawls into and nothing clamps him to the floor") {
    CrawlReplayOptions opt;
    opt.no_crr_pos = true;
    compare_all(c, replay(opt));
}

TWWE_RED_CONTROL(red_the_world_matrix_not_run,
                 "setWorldMatrix skipped: getBaseTRMtx answers with the never-written matrix, so "
                 "both crawl probes are cast from the origin and the crawl's own wall push "
                 "disappears") {
    CrawlReplayOptions opt;
    opt.no_world_matrix = true;
    compare_all(c, replay(opt));
}

TWWE_TEST(the_rooms_own_codes_are_why_the_probes_second_arm_is_dead,
          "Kaisen r0's polygons do carry special codes - 204 of 886 - and not one of them is a "
          "value getCrawlMoveVec forks on, which is a different reason from an empty field") {
    // getCrawlMoveVec forks three ways on the polygon crossed: cBgW_CheckBWall(n.y)
    // (-0.8 <= ny < 0.5) pushes back along the normal; `code == 1 || (n.y < 0.643832f &&
    // code == 2)` pushes back along the segment; otherwise nothing moves. Kaisen r0 has coded
    // polygons but none with code 1 or 2, so every push above is the BWall arm's.
    tww_engine::testing::Rig rig("kaisen_r0_bgd.json");
    c.require(rig.room != NULL, "the room fixture did not load");

    const int tris = rig.room->tri_count();
    c.require(tris > 0, "the room has no polygons - a sweep over nothing reports success");

    int coded = 0;
    int code1 = 0;
    int code2 = 0;
    int bwall = 0;
    int second_arm = 0;
    int hist[16] = {0};
    for (int i = 0; i < tris; i++) {
        cBgS_PolyInfo info;
        info.SetActorInfo(0, &rig.room->bgw(), tww_engine::kRoomPid);
        info.SetPolyIndex(i);
        const int code = rig.room->bgs().GetSpecialCode(info);
        const f32 ny = rig.room->bgw().GetTriPla(i)->GetNP()->y;
        if (code != 0) {
            coded++;
        }
        code1 += (code == 1) ? 1 : 0;
        code2 += (code == 2) ? 1 : 0;
        if (code >= 0 && code < 16) {
            hist[code]++;
        }
        if (cBgW_CheckBWall(ny)) {
            bwall++;
        } else if (code == 1 || (ny < 0.643832f && code == 2)) {
            // getCrawlMoveVec's second condition, evaluated only where BWall said no.
            second_arm++;
        }
    }
    // The BWall arm: present, and not the whole room.
    c.require(bwall > 0,
              "no polygon in this room classifies as a BWall - the arm the six pushes above took "
              "would then have had nothing to take it on");
    c.require(bwall < tris,
              "every polygon in this room is a BWall, so cBgW_CheckBWall decides nothing here");
    // The second arm: dead on the values, with the coded population asserted so an empty
    // attribute table cannot pass the same way.
    c.require(coded > 0,
              "no polygon in this room carries any special code at all - the two zeroes below "
              "would then say nothing about which values the fork misses");
    c.check_int(code1, 0,
                "polygons of special code 1 - getCrawlMoveVec's second arm takes those "
                "unconditionally, and one of them would put a second rule behind the six pushes");
    c.check_int(code2, 0,
                "polygons of special code 2 - the second arm takes those under a steep normal");
    c.check_int(second_arm, 0,
                "polygons reaching the second arm - not a BWall and coded for it");

    char note[300];
    std::snprintf(note, sizeof(note),
                  "%d polygon(s) swept: %d classify as BWall (the arm the pushes took), %d carry "
                  "a non-zero special code, and %d of those are code 1 and %d code 2 - the only "
                  "two values the second arm forks on, so %d polygon(s) reach it",
                  tris, bwall, coded, code1, code2, second_arm);
    c.note(note);
    char codes[220];
    int written = std::snprintf(codes, sizeof(codes), "special codes present:");
    for (int v = 0; v < 16 && written > 0 && written < int(sizeof(codes)); v++) {
        if (hist[v] > 0) {
            written += std::snprintf(codes + written, sizeof(codes) - size_t(written),
                                     " %d x%d", v, hist[v]);
        }
    }
    c.note(codes);
}
