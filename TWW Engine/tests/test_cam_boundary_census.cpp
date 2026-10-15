// test_cam_boundary_census.cpp - which camera boundary stubs one driven `dCamera_c::Run` frame
// reaches, read off the camera boundary counter. Coverage, not correctness: stubs return fixed
// values, so no camera value is asserted, only the set of names. The case fails when the set
// changes in either direction.
//
// Two frames are driven: mode 12 (manual camera, the land frame) and an L tap, which raises `m19B`
// and drops to mode 0 (style FN01, follow) for one frame. The seed is the courtyard's camera:
// `+0x510 == 57` on the live anchor, and `types[7].mStyles[12] == dCamStyle_MM01_e == 57` in the
// decomp table (type 7 `Field`, mode 12 manual).

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "player_rig.h"

#include "d/d_camera.h"
#include "d/d_cam_param.h"
#include "d/actor/d_a_player_main.h"
#include "boundary/game_boundary.h"
#include "m_Do/m_Do_controller_pad.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Rig;

/// The courtyard's camera, which is the finder's. Type 7 is `Field`, mode 12 the manual camera.
const int kFinderType = 7;
const int kFinderMode = 12;
/// `+0x510` off the live courtyard anchor, and `types[7].mStyles[12]` out of the decomp's table.
const int kFinderStyle = 57;

/// A dCamera_c whose POD members are zero. `dCamera_c cam{}` does not give that: the class has a
/// user-provided default constructor, so value-initialisation leaves unassigned members as stack
/// garbage (garbage `m530`/`m254` reach extra stubs). Zero the storage, then placement-new.
dCamera_c* zeroed_camera(void* storage) {
    std::memset(storage, 0, sizeof(dCamera_c));
    return new (storage) dCamera_c();
}

/// Seed a camera on the finder's land frame.
void seed(dCamera_c& cam, fopAc_ac_c* player, bool l_tap) {
    cam.mPadId = 0;
    cam.mpPlayerActor = player;
    cam.mCurType = kFinderType;
    cam.mCurMode = kFinderMode;
    cam.mCurStyle = kFinderStyle;
    cam.mCamParam.Change(cam.mCurStyle);

    // The resting camera the old sim seeds: radius 300, level, looking at the origin.
    cam.mDirection.R(300.0f);
    cam.mViewCache.mDirection.R(300.0f);

    // Driven through the pad, since `updatePad` overwrites the camera's stick fields. The C-stick
    // past m09C holds mode 12; L past `mCamSetup.m0A0` (0.2) with `m19A` down raises `m19B` once.
    std::memset(&g_mDoCPd_cpadInfo[0], 0, sizeof(g_mDoCPd_cpadInfo[0]));
    g_mDoCPd_cpadInfo[0].mCStickValue = 1.0f;
    g_mDoCPd_cpadInfo[0].mCStickPosY = 0.0f;
    g_mDoCPd_cpadInfo[0].mMainStickValue = 0.0f;
    g_mDoCPd_cpadInfo[0].mTriggerLeft = l_tap ? 1.0f : 0.0f;
    cam.m19A = 0;
    cam.m144 = 0;
    cam.m184 = 0;

    // No lock-on target and no force-lock actor: the land route's own shape.
    cam.mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    cam.mpLockonActor = 0;
    cam.mpLockonTarget = 0;
    cam_stub_lockon = false;
    cam_stub_lockon_truth = false;

    daPy_lk_c* lk = static_cast<daPy_lk_c*>(static_cast<void*>(player));
    lk->stub_player_status0 = 0;
    lk->stub_player_status1 = 0;
}

/// The stubs one driven frame reached, sorted by name. Hit counts are printed, not asserted.
std::vector<std::string> census(void* storage, fopAc_ac_c* player, bool l_tap,
                                std::string* counts) {
    dCamera_c& cam = *zeroed_camera(storage);
    seed(cam, player, l_tap);
    cam_boundary_reset();
    cam.Run();
    std::vector<std::string> out;
    *counts = "";
    for (int i = 0; i < cam_boundary_names(); i++) {
        out.push_back(cam_boundary_name(i));
        if (cam_boundary_name_hits(i) > 1) {
            *counts += (counts->empty() ? "" : ", ") + std::string(cam_boundary_name(i)) + " x" +
                       std::to_string(cam_boundary_name_hits(i));
        }
    }
    std::sort(out.begin(), out.end());
    return out;
}

/// `manualCamera` and `followCamera` are absent because they are copied and run for real.
/// Absences that are measurements: bumpCheck's `compWallMargin`, `radiusActorInSight`,
/// `cM3d_2PlaneLinePosNearPos` and the corner arm's `GetTriPla` reads are unreached, so the frame
/// takes bumpCheck's else-branch; `checkGroundInfo`'s `lineCollisionCheckBush` and
/// `dCcS::GetMassCamTopPos` sit behind `if (m360)`, which is 0 on an empty dBgS, so that body's
/// tail is unrun here. `daSea_ChkArea` and `daSea_calcWave` are reached but do not bump this
/// counter.
const char* const kMode12[] = {
    "dAttention_c::Lockon",
    "dCamForcusLine::Off",
    "dCamera_c::Att",
    "dCamera_c::checkForceLockTarget",
    "dCamera_c::checkSpecialArea",
    "dCamera_c::defaultTriming",
    "dCamera_c::nextType",
    "dCamera_c::shakeCamera",
    "dCamera_c::updateMonitor",
    "dComIfGp_demo_getCamera",
    "dComIfGp_evmng_cameraPlay",
    "dComIfGp_offCameraAttentionStatus",
    "dComIfGp_onCameraAttentionStatus",
    "daNpc_Cb1_c::isFlying",
    "daNpc_Md_c::isFlying",
    "daPy_lk_c::getGrabActorID",
};

/// Differs from mode 12 by the dispatch: `followCamera` asks `forwardCheckAngle`, and only the
/// mode-12 frame raises the attention status.
const char* const kLTap[] = {
    "dAttention_c::Lockon",
    "dCamForcusLine::Off",
    "dCamera_c::Att",
    "dCamera_c::checkForceLockTarget",
    "dCamera_c::checkSpecialArea",
    "dCamera_c::defaultTriming",
    "dCamera_c::forwardCheckAngle",
    "dCamera_c::nextType",
    "dCamera_c::shakeCamera",
    "dCamera_c::updateMonitor",
    "dComIfGp_demo_getCamera",
    "dComIfGp_evmng_cameraPlay",
    "dComIfGp_offCameraAttentionStatus",
    "daNpc_Cb1_c::isFlying",
    "daNpc_Md_c::isFlying",
    "daPy_lk_c::getGrabActorID",
};

std::string joined(const std::vector<std::string>& v) {
    std::string s;
    for (size_t i = 0; i < v.size(); i++) {
        s += (i ? ", " : "") + v[i];
    }
    return s;
}

/// Compare a measured list against its banked one, naming each difference on its own side.
void check_list(Case& c, const std::string& what, const std::vector<std::string>& got,
                const char* const* want, size_t want_n) {
    std::vector<std::string> expected(want, want + want_n);
    std::sort(expected.begin(), expected.end());

    for (size_t i = 0; i < got.size(); i++) {
        REQUIRE_TRUE(c, std::find(expected.begin(), expected.end(), got[i]) != expected.end(),
                     what + " reached `" + got[i] +
                         "`, which is not in the banked list - the finder's camera frame has "
                         "grown a boundary dependency it did not have");
    }
    for (size_t i = 0; i < expected.size(); i++) {
        REQUIRE_TRUE(c, std::find(got.begin(), got.end(), expected[i]) != got.end(),
                     what + " no longer reaches `" + expected[i] +
                         "` - if it got a body, delete the line; if the frame stopped reaching "
                         "it, find out why before editing this list");
    }
}

TWWE_TEST(the_finders_camera_frame_needs_exactly_these_stubs,
          "the set of camera boundary stubs a driven finder frame reaches has changed - either a "
          "stub got a body, or the frame started needing one it did not before, and which of "
          "those it is decides whether the list shrinks or the port grew a dependency") {
    Rig rig;
    // Raw storage, zeroed and placement-constructed per frame - see `zeroed_camera`.
    alignas(dCamera_c) unsigned char storage[sizeof(dCamera_c)];
    dCamera_c& cam = *zeroed_camera(storage);

    // The live anchor's +0x510 and the decomp table agree on style 57.
    REQUIRE_INT(c, dCamera_c::types[kFinderType].mStyles[kFinderMode], kFinderStyle,
                "the decomp's table and the live courtyard anchor disagree about the finder's "
                "camera style - one of them is not describing the room the finder runs");
    REQUIRE_TRUE(c, std::string(dCamera_c::types[kFinderType].name) == "Field",
                 "camera type 7 is not `Field` in this build");
    REQUIRE_INT(c, cam.mCamParam.Algorythmn(kFinderStyle), dCamAlg_MANUAL_CAMERA_e,
                "style 57 is not the MANUAL algorithm, so a mode-12 frame does not reach "
                "manualCamera and this census is about a different body");

    std::string counts12, countsL;
    const std::vector<std::string> mode12 = census(storage, &rig.lk, false, &counts12);
    const std::vector<std::string> ltap = census(storage, &rig.lk, true, &countsL);

    check_list(c, "mode 12 (manualCamera)", mode12, kMode12,
               sizeof(kMode12) / sizeof(kMode12[0]));
    check_list(c, "L tap (mode 0, followCamera)", ltap, kLTap, sizeof(kLTap) / sizeof(kLTap[0]));

    std::vector<std::string> both = mode12;
    both.insert(both.end(), ltap.begin(), ltap.end());
    std::sort(both.begin(), both.end());
    both.erase(std::unique(both.begin(), both.end()), both.end());

    c.note("mode 12 reached " + std::to_string(mode12.size()) + " stub(s); L tap " +
           std::to_string(ltap.size()) + "; union " + std::to_string(both.size()));
    c.note("the union: " + joined(both));
    c.note("reached more than once, mode 12: " + (counts12.empty() ? "none" : counts12));
    c.note("reached more than once, L tap:   " + (countsL.empty() ? "none" : countsL));

    // The copied engine bodies ran, not a stub in their place.
    REQUIRE_TRUE(c, std::find(both.begin(), both.end(), "dCamera_c::manualCamera") == both.end(),
                 "manualCamera answered from the boundary, so this frame did not run the copied "
                 "body and the census is about Run's prologue rather than about the camera");
    REQUIRE_TRUE(c, std::find(both.begin(), both.end(), "dCamera_c::followCamera") == both.end(),
                 "followCamera answered from the boundary on the L-tap frame");
}

}  // namespace
