// test_foot_term.cpp - `daPy_lk_c::posMoveFromFootPos` (d_a_player_main.cpp:2353) as a sequence
// over a posed LinkModel, against the old sim's foot_fk.step_feet and
// foot_speedf._py_foot_compose (sim tier):
//
//     cMtx_concat(m37B4, mpCLModel->getAnmMtx(LFOOT/RFOOT), mDoMtx_stack_c::get())
//     mDoMtx_stack_c::multVec(&l_toe_pos / &l_heel_pos, ...)   -> the four foot positions
//     the lower toe/heel midpoint is the PLANTED foot          -> m34BC
//     f31_2 = absXZ(planted toe - LAST frame's planted toe)    -> m359C
//     speedF = mNormalSpeed * (1 - m3598) +/- f31_2 * m3598    -> speedF, speed.x, speed.z
//
// execute() runs posMove at :11298, setWorldMatrix (base, and its inverse in m37B4) at :11544 and
// the skeleton pass at :11591, so the proc reads the previous frame's pose. The first row of each
// track takes the getOldFrameFlg()==false arm, which writes the rest offsets into mFootData.
//
// Position and the other inputs are driven per row, not integrated. The corpus excludes `slip`,
// whose scale compensation reaches the foot chain and foot_fk does not model.
// m359C alone is also held to the console in test_roll_replay.cpp.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "boundary/game_boundary.h"
#include "d/actor/d_a_player_main.h"
#include "engine/jma_console_table.h"
#include "engine/link_model.h"
#include "player_rig.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::Rig;

const char* const kGolden = "foot_term_oracle.json";

/// Column indices into a golden row. The twelve foot floats start at kFeet and are in
/// posMoveFromFootPos's own order: Rtoe, Ltoe, Rheel, Lheel, each (x, y, z).
enum Col {
    kAnim0 = 0, kBckIdx0, kAnim1, kBckIdx1, kTrack, kFacing,
    kFrame0, kFrame1, kRatio, kMorf,
    kPosX, kPosY, kPosZ,
    kNormalSpeed, kStickDistance, kM3598, kM35B4,
    kPlant, kSpeedF, kM359C, kSpeedX, kSpeedZ,
    kFeet
};

/// A row with no second animation (`bck_idx1` -1): setSingleMoveAnime's slot-1-NULL shape.
bool is_single(const Json& row) { return row[kBckIdx1].as_int() < 0; }

/// What a run may be broken with. `Correct` is the driver as execute() spells it.
enum Injection {
    Correct,
    PoseFirst,       ///< the skeleton posed BEFORE the proc, which drops the one-frame lag
    NoCarry,         ///< mFootData reset to the rest offsets every frame, so nothing is carried
    StaleBase,       ///< setWorldMatrix never re-run, so the base and m37B4 stay the first frame's
    NoBlend,         ///< slot 1 left empty, so the MOVE1 animation never reaches the pose
    NoMorf,          ///< initOldFrameMorf never fired, so the old-frame rate stays at 0
};

const daPy_portAnmTrack* track_for(u16 bck_idx) {
    for (size_t i = 0; i < daPy_portAnmTrackTableSize(); i++) {
        if (daPy_portAnmTrackTableAt(i)->mBckIdx == bck_idx) {
            return daPy_portAnmTrackTableAt(i);
        }
    }
    return NULL;
}

/// The driven inputs of a frame. Applied before the proc and again before the tail, so the body's
/// `current.pos += speed` does not move the next pose's base.
void drive(daPy_lk_c& lk, const Json& row) {
    lk.current.pos.set(row[kPosX].as_f32(), row[kPosY].as_f32(), row[kPosZ].as_f32());
    const s16 facing = static_cast<s16>(row[kFacing].as_int());
    lk.current.angle.y = facing;
    lk.shape_angle.x = 0;
    lk.shape_angle.y = facing;
    lk.shape_angle.z = 0;
    lk.scale.set(1.0f, 1.0f, 1.0f);
    lk.speed.set(0.0f, 0.0f, 0.0f);
    lk.mNormalSpeed = row[kNormalSpeed].as_f32();
    lk.mStickDistance = row[kStickDistance].as_f32();
    lk.m3598 = row[kM3598].as_f32();
    lk.m35B4 = row[kM35B4].as_f32();
    // The foot-rotate angle in sp0C; the land walk runs it at 0, and the non-zero arm is ungated.
    lk.m34E0 = 0;
    // Not SWIM_MOVE or CUT_ROLL, whose arms replace the walk's
    // `speed = speedF * (ssin, scos)(current.angle.y)`.
    lk.mCurProc = daPy_lk_c::daPyProc_MOVE_e;
}

struct Counts {
    int rows = 0;
    int compared = 0;
    int seed_rows = 0;
    int blend_poses = 0;    ///< poses run with a second animation in the table
    int morfs_fired = 0;    ///< initOldFrameMorf calls
};

/// What `setMoveAnime` writes into the blend table from inside the proc (d_a_player_main.cpp:
/// 2278-2279, 2291-2292, 2312): the two ratios, the two frames and the morf.
void tail(Rig& rig, const Json& row, daPy_portAnm_c& anm0, daPy_portAnm_c& anm1,
          Injection how, Counts& n) {
    const bool single = is_single(row) || how == NoBlend;
    if (single) {
        rig.setSingleAnim(&anm0);
    } else {
        rig.setBlendAnim(&anm0, &anm1, row[kRatio].as_f32());
        n.blend_poses++;
    }
    anm0.setFrame(row[kFrame0].as_f32());
    if (!single) {
        anm1.setFrame(row[kFrame1].as_f32());
    }
    const f32 i_morf = row[kMorf].as_f32();
    if (i_morf >= 0.0f && how != NoMorf) {
        rig.lk.m_old_fdata->initOldFrameMorf(i_morf, 0, 0x2A);
        n.morfs_fired++;
    }
}

/// One whole corpus run. `compare` asserts against the golden.
Counts run_all(Case& c, Injection how, bool compare) {
    // `jmaSinTable` has no static initialiser; without this a filtered run reads a null pointer.
    JMA_useConsoleSinTable();

    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["expected"];

    Counts n;
    size_t i = 0;
    while (i < rows.size()) {
        // A track is a contiguous run of rows with the same animations and track name, played as
        // one sequence on a fresh player and skeleton.
        const std::string anim = rows[i][kAnim0].str;
        const std::string anim1 = rows[i][kAnim1].str;
        const std::string track = rows[i][kTrack].str;
        const int bck_idx = rows[i][kBckIdx0].as_int();
        const int bck_idx1 = rows[i][kBckIdx1].as_int();
        size_t end = i;
        while (end < rows.size() && rows[end][kAnim0].str == anim
               && rows[end][kAnim1].str == anim1 && rows[end][kTrack].str == track) {
            end++;
        }

        const daPy_portAnmTrack* trk = track_for(static_cast<u16>(bck_idx));
        const daPy_portAnmTrack* trk1 =
            bck_idx1 < 0 ? NULL : track_for(static_cast<u16>(bck_idx1));
        REQUIRE_TRUE(c, trk != NULL && (bck_idx1 < 0 || trk1 != NULL),
                     anim + "/" + anim1 + ": the golden names .bck index "
                         + std::to_string(bck_idx) + "/" + std::to_string(bck_idx1)
                         + " and anm_track.inc has no row for one of them");
        if (trk == NULL || (bck_idx1 >= 0 && trk1 == NULL)) {
            i = end;
            continue;
        }

        Rig rig;
        // mOldFrameFlg starts low, so the first frame takes the rest-offset arm.
        rig.attachSkeleton(false);
        daPy_lk_c& lk = rig.lk;
        // m_anm_heap_under[0] and [1]: separate buffers with independent frames.
        daPy_portAnm_c anm0;
        daPy_portAnm_c anm1;
        // frameMax is unread on this path; the golden sets the frame per row.
        anm0.load(1000, J3DFrameCtrl::EMode_NONE, trk);
        if (trk1 != NULL) {
            anm1.load(1000, J3DFrameCtrl::EMode_NONE, trk1);
        }

        for (size_t r = i; r < end; r++) {
            const Json& row = rows[r];
            const std::string at = anim + (anim1.empty() ? "" : "+" + anim1) + " " + track
                                   + " frame " + std::to_string(row[kFrame0].as_f32()) + ": ";

            if (how == PoseFirst) {
                // The tail run at the top of the frame instead.
                drive(lk, row);
                tail(rig, row, anm0, anm1, how, n);
                rig.poseSkeleton();
            }
            if (how == NoCarry) {
                // The flag-false arm's rest offsets, written every frame.
                static const Vec rtoe = {-14.05f, 0.0f, 5.02f};
                static const Vec rheel = {-10.85f, 0.0f, -6.52f};
                lk.mFootData[0].field_0x018 = rtoe;
                lk.mFootData[0].field_0x00C = rheel;
                lk.mFootData[1].field_0x018.set(-rtoe.x, rtoe.y, rtoe.z);
                lk.mFootData[1].field_0x00C.set(-rheel.x, rheel.y, rheel.z);
            }

            drive(lk, row);
            lk.posMoveFromFootPos();

            if (compare) {
                REQUIRE_INT(c, static_cast<int>(lk.m34BC), row[kPlant].as_int(), at + "m34BC");
                REQUIRE_BITS(c, lk.speedF, row[kSpeedF].as_f32(), at + "speedF");
                REQUIRE_BITS(c, lk.m359C, row[kM359C].as_f32(), at + "m359C (f31_2)");
                REQUIRE_BITS(c, lk.speed.x, row[kSpeedX].as_f32(), at + "speed.x");
                REQUIRE_BITS(c, lk.speed.z, row[kSpeedZ].as_f32(), at + "speed.z");
                // Index 0 is the right foot.
                const Vec* got[4] = {&lk.mFootData[0].field_0x018, &lk.mFootData[1].field_0x018,
                                     &lk.mFootData[0].field_0x00C, &lk.mFootData[1].field_0x00C};
                static const char* const name[4] = {"Rtoe", "Ltoe", "Rheel", "Lheel"};
                for (int f = 0; f < 4; f++) {
                    const f32* v = &got[f]->x;
                    for (int a = 0; a < 3; a++) {
                        REQUIRE_BITS(c, v[a], row[kFeet + f * 3 + a].as_f32(),
                                     at + name[f] + "." + "xyz"[a]);
                    }
                }
                n.compared++;
            }
            if (row[kPlant].as_int() == 2) {
                n.seed_rows++;
            }
            n.rows++;

            if (how != PoseFirst) {
                // The frame's tail, in execute()'s order, from the row's position.
                drive(lk, row);
                tail(rig, row, anm0, anm1, how, n);
                if (how == StaleBase) {
                    // setWorldMatrix skipped: the base and m37B4 stay the first frame's.
                    lk.mpCLModel->calcAnmMtx();
                } else {
                    rig.poseSkeleton();
                }
            }
        }
        i = end;
    }
    return n;
}

}  // namespace

TWWE_TEST(the_foot_term_reads_the_posed_skeleton_and_turns_it_into_speedF,
          "posMoveFromFootPos disagrees with the old sim's foot_fk somewhere between the joint "
          "matrix and speedF - the m37B4 concat, the toe and heel multVec, the planted-foot "
          "select, the one-frame toe delta, the 0.3/0.7 smoothing or the speedF blend") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Counts n = run_all(c, Correct, true);

    c.note("rows compared:   " + std::to_string(n.compared)
           + " (" + std::to_string(g["_corpus"].size())
           + " animations x 4 single tracks + " + std::to_string(g["_pairs"].size())
           + " pairs x 2 blend tracks x 7 consecutive frames)");
    c.note("seed rows:       " + std::to_string(n.seed_rows)
           + " - the getOldFrameFlg()==false arm, one per track");
    c.note("plant right/left/unposed: " + std::to_string(g["_plant_right"].as_int()) + "/"
           + std::to_string(g["_plant_left"].as_int()) + "/"
           + std::to_string(g["_plant_unposed"].as_int()));
    c.note("rows the smoothing ran on: " + std::to_string(g["_rows_smoothed"].as_int())
           + ", rows snapped to zero by the 0.05 guard: "
           + std::to_string(g["_rows_snapped_to_zero"].as_int()));
    c.note("poses with a second animation in the table: " + std::to_string(n.blend_poses)
           + ", oldframe morfs fired: " + std::to_string(n.morfs_fired)
           + " - the golden banks " + std::to_string(g["_poses_morphed"].as_int())
           + " poses that ran at a non-zero morf rate");
    c.note("oracle tier:     " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM, and the old sim's own functions called - foot_fk.step_feet and "
                             "foot_speedf._py_foot_compose - rather than its primitives composed"));
    REQUIRE_INT(c, n.compared, static_cast<int>(g["expected"].size()),
                "every row of the corpus ran");
    REQUIRE_INT(c, n.seed_rows,
                static_cast<int>(g["_corpus"].size()) * 4 + static_cast<int>(g["_pairs"].size()) * 2,
                "one flag-false seed row per track, and no more - a second would mean the "
                "skeleton pass had stopped raising mOldFrameFlg");
    // The blend and morf arms, counted: the single-animation majority touches neither.
    REQUIRE_INT(c, n.blend_poses, static_cast<int>(g["_pairs"].size()) * 2 * 7,
                "every frame of every blend track poses with a second animation in the table - "
                "which is mDoExt_MtxCalcAnmBlendTblOld::calc's `for i = 1; i < mNum` arm");
    REQUIRE_INT(c, n.morfs_fired,
                (static_cast<int>(g["_corpus"].size()) + static_cast<int>(g["_pairs"].size()))
                    * static_cast<int>(g["_morf_values"].size()),
                "each morf track fires initOldFrameMorf once per banked morf value");
    REQUIRE_TRUE(c, g["_poses_morphed"].as_int() > 0,
                 "and the morf reached a pose - a schedule that fired and expired before the "
                 "next pass would leave every row above identical to a run with no morf at all");
}

TWWE_TEST(the_skeleton_is_what_makes_the_foot_term_a_number,
          "the foot term has stopped moving speedF - which would mean either that the corpus lost "
          "its m3598, or that the toe delta has gone back to the zero the boundary answered") {
    // Counts the oracle rows where the foot term moves speedF off `mNormalSpeed * (1 - m3598)`.
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["expected"];
    int moved = 0;
    int posed = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        if (rows[i][kPlant].as_int() == 2) {
            continue;
        }
        posed++;
        const f32 without = rows[i][kNormalSpeed].as_f32() * (1.0f - rows[i][kM3598].as_f32());
        if (tww_engine::testing::f32_bits(rows[i][kSpeedF].as_f32())
            != tww_engine::testing::f32_bits(without)) {
            moved++;
        }
    }
    c.note("rows where the foot term moves speedF: " + std::to_string(moved) + " of "
           + std::to_string(posed) + " posed rows");
    c.note("what it is worth is measured on the oracle's rows, so this is a claim about the "
           "corpus rather than about the port - the case above is what holds the port");
    REQUIRE_TRUE(c, moved > posed / 2,
                 "the foot term changes speedF on most of the corpus, so a port that answered "
                 "zero for it could not pass the case above by accident");
}

TWWE_TEST(the_player_is_not_where_the_skeleton_lives,
          "sizeof(daPy_lk_c) has grown by the size of a skeleton - which would mean a LinkModel "
          "had been embedded in the player rather than pointed at from it") {
    // `mpCLModel` is a pointer on daPy_py_c; the game allocates its target from the model heap
    // (as d_a_player_main.cpp:12020 does m_old_fdata's arrays), so the skeleton lives in the rig.
    c.note("sizeof(daPy_lk_c):   " + std::to_string(sizeof(daPy_lk_c)) + " bytes");
    c.note("sizeof(LinkModel):   " + std::to_string(sizeof(tww_engine::LinkModel)) + " bytes, "
           "owned beside the player by the rig");
    c.note("sizeof(Rig::FreshOldFrame): " + std::to_string(sizeof(Rig::FreshOldFrame))
           + " bytes, allocated only by attachSkeleton(false)");
    REQUIRE_TRUE(c, sizeof(tww_engine::LinkModel) > 4096,
                 "the skeleton is big enough that where it lives is a decision rather than a "
                 "detail - if this ever stops being true the note above is what to re-read");
    // The skeleton pass needs the sine table and a slot-0 animation, or it dereferences null.
    JMA_useConsoleSinTable();
    Rig rig;
    REQUIRE_TRUE(c, rig.skeleton && rig.lk.mpCLModel == rig.skeleton->model(),
                 "every rig gets a skeleton and the player points at it - reset_boundary's own "
                 "claim is that Link's skeleton has been calculated, and posMoveFromFootPos's "
                 "foot-term arm concatenates m37B4 onto a joint matrix out of it");
    REQUIRE_TRUE(c, rig.lk.mpCLModel != &rig.lk.port_cl_model,
                 "and the player's own no-skeleton J3DModel is left behind rather than filled "
                 "in - it is still what getAnmMtx answers NULL for");
    REQUIRE_TRUE(c, rig.lk.m_old_fdata == &rig.lk.port_old_fdata
                        && rig.lk.m_pbCalc[daPy_lk_c::PART_UNDER_e]->mOldFrame
                               == rig.lk.m_old_fdata,
                 "the player's m_old_fdata and the mtx calc's are the same object, which is what "
                 "makes the flag the skeleton pass raises the flag posMoveFromFootPos reads "
                 "(d_a_player_main.cpp:12020-12023)");
    REQUIRE_TRUE(c, rig.lk.m_old_fdata->getOldFrameFlg() == true,
                 "raised by default, because that is the state every banked capture's frames are "
                 "in - hundreds of frames into a loaded room");

    // The flag-low state, once per actor. mDoExt_MtxCalcOldFrame has no `off`, so it takes a fresh
    // object.
    Rig fresh;
    fresh.attachSkeleton(false);
    REQUIRE_TRUE(c, fresh.lk.m_old_fdata->getOldFrameFlg() == false,
                 "a freshly built old-frame object starts low");
    daPy_portAnm_c anm;
    anm.load(1000, J3DFrameCtrl::EMode_NONE, daPy_portAnmTrackTableAt(0));
    anm.setFrame(0.0f);
    fresh.setSingleAnim(&anm);
    fresh.poseSkeleton();
    REQUIRE_TRUE(c, fresh.lk.m_old_fdata->getOldFrameFlg() == true,
                 "and one skeleton pass raises it, from the last joint (m_Do_ext.cpp:1212)");
}

TWWE_RED_CONTROL(red_the_skeleton_is_posed_before_the_proc,
                 "setWorldMatrix and the skeleton pass run at the top of the frame instead of its "
                 "tail, so the proc reads joint matrices posed from its own frame's position and "
                 "animation frame rather than the previous one's. execute() runs posMove at "
                 ":11298 and both of these at :11544 and :11591; this is that order reversed, and "
                 "it is exactly right on the first compared frame of every track, where the two "
                 "poses are the same one") {
    run_all(c, PoseFirst, true);
}

TWWE_RED_CONTROL(red_the_previous_frames_feet_are_never_carried,
                 "mFootData written back to posMoveFromFootPos's own rest offsets before every "
                 "frame, so the toe delta is always measured against the standing pose instead of "
                 "against the last frame's. It is exactly right on the first compared row of "
                 "every track, which is the row whose previous frame really was the flag-false "
                 "arm - which is what makes it a claim about the carry rather than about the "
                 "offsets") {
    run_all(c, NoCarry, true);
}

TWWE_RED_CONTROL(red_the_world_matrix_is_never_rebuilt,
                 "setWorldMatrix skipped after the first frame, so the model's base transform and "
                 "m37B4 stay where Link started while the skeleton keeps posing. The joint "
                 "matrices are still built and still concatenated - what is wrong is the frame "
                 "they are built in, which is the half of the foot term the animation cannot "
                 "show. Right on every track's first compared row and on any row where the "
                 "position did not move") {
    run_all(c, StaleBase, true);
}

TWWE_RED_CONTROL(red_the_second_animation_never_reaches_the_pose,
                 "the blend table's slot 1 left empty on every frame, so MOVE1 never reaches the "
                 "pose and every joint is MOVE0 alone - which is setSingleMoveAnime's shape run "
                 "where setMoveAnime's belongs. It is exactly right on all 728 single-animation "
                 "rows and on the first compared row of every blend track, which is the row "
                 "posed by a frame whose own predecessor was the flag-false seed; what it is "
                 "wrong about is the blend, and nothing else") {
    run_all(c, NoBlend, true);
}

TWWE_RED_CONTROL(red_the_oldframe_morf_never_fires,
                 "initOldFrameMorf never called, so mOldFrameRate stays at the 0.0 its own "
                 "constructor sets and the arm that lerps a joint toward last frame's stored "
                 "pose is never entered. Right on every row of every track that fires no morf, "
                 "and right on the morf tracks up to the frame after the first fire - the morf "
                 "is state across frames, so what it is wrong about starts one frame late and "
                 "then stays wrong, because the pose it corrupted is what the next frame's toe "
                 "delta is measured against") {
    run_all(c, NoMorf, true);
}
