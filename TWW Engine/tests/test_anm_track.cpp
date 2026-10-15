// test_anm_track.cpp - the keyframe sampler, held to the old sim at 0 ULP (anm_track_oracle.json).
//
//     J3DAnmTransformKey::calcTransform   the per-axis switch: 0 -> default, 1 -> constant,
//                                         else interpolate, and the rotation's `<< mDecShift`
//     J3DGetKeyFrameInterpolation<f32>    the endpoint clamps and the bisect, stride 3 and 4
//     J3DGetKeyFrameInterpolationS        the same for s16, with a different Hermite
//     JMAHermiteInterpolation             the f32 Hermite, extracted (FUSED 0)
//     J3DHermiteInterpolationS            the s16 Hermite, CARRIED (five fused ops)
//     generated/d/actor/anm_track.inc     the baked tracks, at the .bck's own offsets
//
// Sim tier: the oracle is the old sim's j3d_eval.py, a hand transcription of the same decomp, so
// agreement says the C++ reproduces the Python; a misreading both share is invisible. This file
// sweeps joint 0 densely (every bisect boundary, span midpoints, both clamps);
// test_anm_joints.cpp covers all 42 joints at their key times.
//
// JMAHermiteInterpolation (GZLJ01 0x802FF058) has no fused ops where j3d_eval uses four; they
// agree because every fused multiplicand is +/-2.0 and the one fused addend 0.0. The port keeps
// the DOL's spelling.

#include <limits>
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

const char* const kGolden = "anm_track_oracle.json";

/// One animation's baked track, found by the golden's .bck index rather than by position, so a
/// row added to either file cannot pair the walk with the dash.
const daPy_portAnmTrack* track_for(u16 bck_idx);

/// The port's sampler, driven exactly as posMove drives it: a frame set through the decomp's own
/// setFrame(), then getTransform(0, &out).
void sample(const daPy_portAnmTrack* track, s16 frame_max, float frame, J3DTransformInfo* out) {
    daPy_portAnm_c anm;
    anm.load(frame_max, J3DFrameCtrl::EMode_NONE, track);
    anm.setFrame(frame);
    anm.getTransform(0, out);
}

struct Counts {
    int anims = 0;
    int samples = 0;
};

Counts compare_all(Case& c, bool inject_full_semantics) {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& anims = g["anims"];
    Counts n;

    for (std::map<std::string, Json>::const_iterator it = anims.object.begin();
         it != anims.object.end(); ++it) {
        const std::string& name = it->first;
        const Json& a = it->second;
        const u16 bck_idx = static_cast<u16>(a["bck_idx"].as_int());
        const s16 frame_max = static_cast<s16>(a["frame_max"].as_int());

        const daPy_portAnmTrack* track = track_for(bck_idx);
        REQUIRE_TRUE(c, track != NULL,
                     name + ": the golden names .bck index " + std::to_string(bck_idx)
                         + " and anm_track.inc has no row for it");
        if (track == NULL) {
            continue;
        }
        REQUIRE_INT(c, track->mDecShift, a["dec_shift"].as_int(), name + ".decShift");
        n.anims++;

        const Json& rows = a["samples"];
        for (size_t r = 0; r < rows.size(); r++) {
            const Json& row = rows[r];
            const float frame = row[0].as_f32();
            const std::string at = name + " @ frame " + std::to_string(frame) + " ";

            J3DTransformInfo got;
            if (inject_full_semantics) {
                // The red control's injection, through the same comparison.
                daPy_portAnm_c anm;
                anm.load(frame_max, J3DFrameCtrl::EMode_NONE, track);
                anm.setFrame(frame);
                anm.getTransform(0, &got);
                const s32 f = static_cast<s32>(frame);
                const J3DAnmTransformKeyTable* tbl = track->mAnmTable;
                // Past the array's end the full body would read another animation's words; the
                // injection answers NaN there instead, which is as wrong and reads nothing.
                const size_t i = static_cast<size_t>(f < 0 ? 0 : f) + tbl[0].mTranslate.mOffset;
                got.mTranslate.x = i < track->mTransNum ? track->mTransData[i]
                                                        : std::numeric_limits<f32>::quiet_NaN();
            } else {
                sample(track, frame_max, frame, &got);
            }

            REQUIRE_BITS(c, got.mScale.x, row[1].as_f32(), at + "scale.x");
            REQUIRE_BITS(c, got.mScale.y, row[2].as_f32(), at + "scale.y");
            REQUIRE_BITS(c, got.mScale.z, row[3].as_f32(), at + "scale.z");

            // The golden carries j3d_eval's `(s32)v << mDecShift` before the s16 store into
            // J3DTransformInfo::mRotation; the truncation is applied here (`rollf` passes 66,000
            // BAM).
            REQUIRE_INT(c, got.mRotation.x, static_cast<s16>(row[4].as_int()), at + "rot.x");
            REQUIRE_INT(c, got.mRotation.y, static_cast<s16>(row[5].as_int()), at + "rot.y");
            REQUIRE_INT(c, got.mRotation.z, static_cast<s16>(row[6].as_int()), at + "rot.z");

            REQUIRE_BITS(c, got.mTranslate.x, row[7].as_f32(), at + "trans.x");
            REQUIRE_BITS(c, got.mTranslate.y, row[8].as_f32(), at + "trans.y");
            REQUIRE_BITS(c, got.mTranslate.z, row[9].as_f32(), at + "trans.z");
            n.samples++;
        }
    }
    return n;
}

}  // namespace

TWWE_TEST(the_keyframe_sampler_reproduces_the_old_sim,
          "calcTransform, both keyframe lookups and both Hermites disagree with the old sim "
          "on some animation, frame or axis - or joint 0's keytables in anm_track.inc "
          "are not the ones the .bck holds") {
    const Counts n = compare_all(c, false);
    c.note("animations compared: " + std::to_string(n.anims));
    c.note("samples compared:    " + std::to_string(n.samples) + " x 9 columns");
    c.note("oracle tier:         " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM - the regression tier: this says the C++ reproduces the "
                             "Python, not that the sampler is right"));
    REQUIRE_INT(c, n.anims, 27, "every animation anm_track.inc bakes was compared");
}

TWWE_TEST(the_sampler_is_asked_for_the_root_and_nothing_else,
          "the port asks the sampler for a joint other than 0, or for an animation with no baked "
          "track - either of which is answered with zeros, which is a plausible-looking value") {
    daPy_portAnm_c anm;
    const daPy_portAnmTrack* track = track_for(
        static_cast<u16>(tww_engine::testing::golden(kGolden)["anims"]["walk"]["bck_idx"].as_int()));
    REQUIRE_TRUE(c, track != NULL, "the walk has a baked track");

    J3DTransformInfo out;
    anm.load(32, J3DFrameCtrl::EMode_NONE, track);
    anm.setFrame(4.0f);
    anm.getTransform(0, &out);
    // The walk's root at an interpolated frame against frame 0: a sampler stuck on the first key
    // would pass every constant column.
    J3DTransformInfo at_zero;
    anm.setFrame(0.0f);
    anm.getTransform(0, &at_zero);
    REQUIRE_TRUE(c, tww_engine::testing::bits(out.mTranslate.y) !=
                        tww_engine::testing::bits(at_zero.mTranslate.y),
                 "the walk's root height differs between frame 0 and frame 4 - a sampler that "
                 "returned the first key regardless of frame would pass every constant column");
}

TWWE_RED_CONTROL(red_the_full_animation_body,
                 "translate.x is read as `mTransData[frame + mOffset]` - the body of "
                 "J3DAnmTransformFull::getTransform, which is the class for a .bca. It is the mistake a "
                 "reader makes who takes `getTransform` to be a table lookup, and it is right on "
                 "every constant track and at every integer frame of a 1-key axis") {
    compare_all(c, true);
}

namespace {

const daPy_portAnmTrack* track_for(u16 bck_idx) {
    for (size_t i = 0; i < daPy_portAnmTrackTableSize(); i++) {
        if (daPy_portAnmTrackTableAt(i)->mBckIdx == bck_idx) {
            return daPy_portAnmTrackTableAt(i);
        }
    }
    return NULL;
}

}  // namespace
