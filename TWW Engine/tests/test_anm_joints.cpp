// test_anm_joints.cpp - the baked keytables of all 42 joints, held to the old sim at 0 ULP
// (anm_joints_oracle.json).
//
// test_anm_track.cpp gates the sampler's arithmetic at joint 0. This gates the data in
// anm_track.inc, whose faults are invisible at joint 0: a keytable emitted against the wrong
// joint, a count or offset from the wrong field, an array that ends early. Each joint is sampled
// at its own key times and span midpoints (derived from its nine keytables), plus frame 0 and
// frameMax.
//
// Sim tier: the oracle is the old sim's j3d_eval.py reading the arc's arrays through its own
// parse_bck, independent of the generated file. It says the C++ reads the same words the Python
// does; no capture records a joint transform.
//
// The red controls mutate the keytable indexing, not code, and run the real sampler; both faults
// are right at joint 0.

#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "d/actor/d_a_player_main.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "JSystem/J3DGraphBase/J3DTransform.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;

const char* const kGolden = "anm_joints_oracle.json";

/// How the keytable array is indexed for a (joint, axis). `Correct` is the decomp's
/// `mAnmTable[idx*3 + axis]`; the other two are the controls.
enum Indexing { Correct, JointDropped, AxisDropped };

const daPy_portAnmTrack* track_for(u16 bck_idx) {
    for (size_t i = 0; i < daPy_portAnmTrackTableSize(); i++) {
        if (daPy_portAnmTrackTableAt(i)->mBckIdx == bck_idx) {
            return daPy_portAnmTrackTableAt(i);
        }
    }
    return NULL;
}

/// One animation's keytable array with `how` applied; only the index is mutated, the keyframe
/// words are the baked ones.
std::vector<J3DAnmTransformKeyTable> remap(const daPy_portAnmTrack* track, Indexing how) {
    std::vector<J3DAnmTransformKeyTable> out(static_cast<size_t>(track->mJointNum) * 3);
    for (int j = 0; j < track->mJointNum; j++) {
        for (int a = 0; a < 3; a++) {
            int from = j * 3 + a;
            if (how == JointDropped) {
                from = a;
            } else if (how == AxisDropped) {
                from = j * 3;
            }
            out[static_cast<size_t>(j) * 3 + a] = track->mAnmTable[from];
        }
    }
    return out;
}

struct Counts {
    int anims = 0;
    int joints = 0;
    int samples = 0;
};

Counts compare_all(Case& c, Indexing how) {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& anims = g["anims"];
    Counts n;

    for (std::map<std::string, Json>::const_iterator it = anims.object.begin();
         it != anims.object.end(); ++it) {
        const std::string& name = it->first;
        const Json& a = it->second;
        const u16 bck_idx = static_cast<u16>(a["bck_idx"].as_int());
        const s16 frame_max = static_cast<s16>(a["frame_max"].as_int());
        const int joint_num = a["joint_num"].as_int();

        const daPy_portAnmTrack* track = track_for(bck_idx);
        REQUIRE_TRUE(c, track != NULL,
                     name + ": the golden names .bck index " + std::to_string(bck_idx)
                         + " and anm_track.inc has no row for it");
        if (track == NULL) {
            continue;
        }
        // The .bck's joint count against the parser's: a mismatch would read the next
        // animation's words.
        REQUIRE_INT(c, track->mJointNum, joint_num, name + ".jointNum");
        REQUIRE_INT(c, track->mDecShift, a["dec_shift"].as_int(), name + ".decShift");
        n.anims++;

        // `how == Correct` feeds the baked table, the shipped path.
        const std::vector<J3DAnmTransformKeyTable> remapped =
            how == Correct ? std::vector<J3DAnmTransformKeyTable>() : remap(track, how);
        daPy_portAnmTrack use = *track;
        if (how != Correct) {
            use.mAnmTable = &remapped[0];
        }

        daPy_portAnm_c anm;
        anm.load(frame_max, J3DFrameCtrl::EMode_NONE, &use);

        int last_joint = -1;
        const Json& rows = a["samples"];
        for (size_t r = 0; r < rows.size(); r++) {
            const Json& row = rows[r];
            const int joint = row[0].as_int();
            const float frame = row[1].as_f32();
            if (joint != last_joint) {
                last_joint = joint;
                n.joints++;
            }
            const std::string at = name + " joint " + std::to_string(joint) + " @ frame "
                                   + std::to_string(frame) + " ";

            J3DTransformInfo got;
            anm.setFrame(frame);
            anm.getTransform(static_cast<u16>(joint), &got);

            REQUIRE_BITS(c, got.mScale.x, row[2].as_f32(), at + "scale.x");
            REQUIRE_BITS(c, got.mScale.y, row[3].as_f32(), at + "scale.y");
            REQUIRE_BITS(c, got.mScale.z, row[4].as_f32(), at + "scale.z");

            // The golden carries j3d_eval's `(s32)v << mDecShift` before the s16 store into
            // J3DTransformInfo::mRotation; the truncation is applied here.
            REQUIRE_INT(c, got.mRotation.x, static_cast<s16>(row[5].as_int()), at + "rot.x");
            REQUIRE_INT(c, got.mRotation.y, static_cast<s16>(row[6].as_int()), at + "rot.y");
            REQUIRE_INT(c, got.mRotation.z, static_cast<s16>(row[7].as_int()), at + "rot.z");

            REQUIRE_BITS(c, got.mTranslate.x, row[8].as_f32(), at + "trans.x");
            REQUIRE_BITS(c, got.mTranslate.y, row[9].as_f32(), at + "trans.y");
            REQUIRE_BITS(c, got.mTranslate.z, row[10].as_f32(), at + "trans.z");
            n.samples++;
        }
    }
    return n;
}

}  // namespace

TWWE_TEST(every_joints_baked_track_reproduces_the_old_sim,
          "some joint's keytable in anm_track.inc is not the one the .bck holds for it - emitted "
          "against the wrong joint, or with a count, offset or type read out of the wrong field, "
          "or indexing an array that ends early") {
    const Counts n = compare_all(c, Correct);
    c.note("animations compared: " + std::to_string(n.anims));
    c.note("joints compared:     " + std::to_string(n.joints) + " (42 per animation)");
    c.note("samples compared:    " + std::to_string(n.samples) + " x 9 columns");
    c.note("oracle tier:         " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM - the regression tier: this says the C++ reads the same words "
                             "the Python does, not that the words are console RAM's"));
    REQUIRE_INT(c, n.anims, 27, "every animation anm_track.inc bakes was compared");
    REQUIRE_INT(c, n.joints, 27 * 42, "every joint of every animation was compared");
}

TWWE_TEST(the_skeletons_asks_are_counted_and_no_walk_runs_off_the_end,
          "a joint past the loaded .bck's own mJointNum was asked for and answered out of the "
          "next animation's keytables - or the skeleton's asks stopped being counted, which is "
          "what tells a replay apart from one that never walked the joints") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const daPy_portAnmTrack* track =
        track_for(static_cast<u16>(g["anims"]["walk"]["bck_idx"].as_int()));
    REQUIRE_TRUE(c, track != NULL, "the walk has a baked track");
    if (track == NULL) {
        return;
    }

    daPy_portAnm_c anm;
    anm.load(32, J3DFrameCtrl::EMode_NONE, track);
    anm.setFrame(4.0f);

    // One past the end: an unguarded read would find the next animation's first entry.
    J3DTransformInfo past;
    anm.getTransform(static_cast<u16>(track->mJointNum), &past);
    REQUIRE_BITS(c, past.mScale.x, 0.0f, "a joint past the end answers zero, not a neighbour");
    REQUIRE_BITS(c, past.mScale.y, 0.0f, "a joint past the end answers zero, not a neighbour");
    REQUIRE_BITS(c, past.mScale.z, 0.0f, "a joint past the end answers zero, not a neighbour");

    // ...and the last joint in range is answered, so the bound is not off by one.
    J3DTransformInfo last;
    anm.getTransform(static_cast<u16>(track->mJointNum - 1), &last);
    REQUIRE_TRUE(c, tww_engine::testing::bits(last.mScale.x) != tww_engine::testing::bits(0.0f),
                 "joint 41 of the walk is answered, so the bound rejects only what is past the end");
}

TWWE_RED_CONTROL(red_the_joint_index_was_never_added,
                 "every joint reads mAnmTable[axis] - joint 0's own three keytables - which is "
                 "the shape of a widening that baked 42 joints of data and left the reader at "
                 "the root. It is right on joint 0 and on every joint whose tracks happen to "
                 "match the root's, so the joint-0 gate is green on it") {
    compare_all(c, JointDropped);
}

TWWE_RED_CONTROL(red_the_axis_index_was_dropped,
                 "every axis reads mAnmTable[joint*3] - the joint's X entry - which is the shape "
                 "of a generator that emitted one keytable per joint instead of three. It is "
                 "right on the X column of every joint, and on any joint whose three axes carry "
                 "the same track") {
    compare_all(c, AxisDropped);
}
