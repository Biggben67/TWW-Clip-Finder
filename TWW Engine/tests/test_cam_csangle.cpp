// test_cam_csangle.cpp - `csangle`, the camera number the setup finder reads, per frame.
//
// `dCam_getControledAngleY` is `mAngleY`, written at the end of `dCamera_c::Run`:
//
//     bumpCheck(m068);                                       d_camera.cpp:302
//     ...
//     mAngleY = mDirection.U().Inv();                        d_camera.cpp:315
//
// This calls `Run` itself (prologue, `checkGroundInfo`, `updatePad`, the mode machine, the
// `engine_tbl` algorithm, the tail and `bumpCheck`), so it gates the composition. `bumpCheck` is
// the only body that promotes `mViewCache.mDirection` onto `mDirection`.
//
// The tier is regression: the oracle is the old sim's `LandCamera.step`, an independent model of
// the same decomp bodies.
//
// The tape holds the C-stick off centre on both signs, inside the rational-Bezier band and past
// the 0.75 saturation (a centred stick makes the chase an identity). The producer refuses a tape
// that moves `csangle` on fewer than half its frames.
//
// `manualCamera` only: the oracle's `_follow` stops after the `m108 == 0` entry and the
// `m100 == 0` approach blend, while the port runs 370 more lines that assign
// `mViewCache.mDirection` (d_camera.cpp:879) and chase it (:975, :978, :1001). The producer
// refuses a tape that leaves mode 12. `followCamera`'s `m37C` was corrected against GZLJ01
// 0x8016743C-0x8016751C (the body is `/* Nonmatching */`), but is read only under `m100 == 0`
// (d_camera.cpp:617, :663), and both sides seed `m100 = 1`.
//
// `LandCamera.__init__` starts m100/m101/m102 and m110 at 1, a zeroed `dCamera_c` at 0, so the
// counters come from the golden's seed.
//
// Not gated:
//   * `bumpCheck`'s hit branch: the Rig's dBgS is empty, so it takes the else-branch every frame.
//   * `getDMCAngle` and the DMC path: the main stick is at rest.
//   * `m360`: the old sim writes 1, the port's `checkGroundInfo` 0 on an empty world; every read
//     is behind the demo flag `chkFlag(0x200000)`.
//   * `followCamera`, as above.
//   * the lock-on arms: `mpLockonTarget` is null and `LockonTruth` false.
//   * the camera boundary stubs a finder frame reaches (`test_cam_boundary_census.cpp`).

#include <cstdio>
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
using tww_engine::testing::Json;
using tww_engine::testing::Rig;

const char* const kGolden = "cam_csangle_oracle.json";

uint32_t bits_of(const Json& v) {
    return static_cast<uint32_t>(v.as_int());
}

f32 f32_of(const Json& v) {
    const uint32_t b = bits_of(v);
    f32 out;
    std::memcpy(&out, &b, sizeof(out));
    return out;
}

cXyz vec_of(const Json& v) {
    return cXyz(f32_of(v[0]), f32_of(v[1]), f32_of(v[2]));
}

/// A `dCamera_c` whose POD members are zero: its default constructor is user-provided, so
/// value-initialisation zeroes nothing else, and `Run` reads dozens of fields.
dCamera_c* zeroed_camera(void* storage) {
    std::memset(storage, 0, sizeof(dCamera_c));
    return new (storage) dCamera_c();
}

/// Seed the camera and Link from the golden's `seed` block.
void seed(dCamera_c& cam, daPy_lk_c& lk, const Json& s) {
    cam.mPadId = 0;
    cam.mpPlayerActor = static_cast<fopAc_ac_c*>(static_cast<void*>(&lk));
    cam.mCurType = static_cast<int>(s["cur_type"].as_int());
    cam.mCurMode = static_cast<int>(s["cur_mode"].as_int());
    cam.mCurStyle = static_cast<s16>(s["cur_style"].as_int());
    cam.mCamParam.Change(cam.mCurStyle);

    const f32 radius = f32_of(s["radius_bits"]);
    cam.mDirection.Val(radius, (s16)0, (s16)0);
    cam.mViewCache.mDirection.Val(radius, (s16)0, (s16)0);

    cam.mViewCache.mCenter = vec_of(s["center_bits"]);
    cam.mViewCache.mEye = cam.mViewCache.mCenter + cam.mViewCache.mDirection.Xyz();
    cam.mCenter = cam.mViewCache.mCenter;
    cam.mEye = cam.mViewCache.mEye;
    cam.mFovy = f32_of(s["fovy_bits"]);
    cam.mViewCache.mFovy = cam.mFovy;

    const Json& counters = s["counters"];
    cam.m100 = static_cast<u8>(counters["m100"].as_int());
    cam.m101 = static_cast<u8>(counters["m101"].as_int());
    cam.m102 = static_cast<u8>(counters["m102"].as_int());
    cam.m110 = static_cast<u8>(counters["m110"].as_int());
    cam.m108 = static_cast<u32>(counters["m108"].as_int());
    cam.m11C = static_cast<u32>(counters["m11c"].as_int());
    cam.m068 = static_cast<int>(counters["m068"].as_int());
    cam.mEventFlags = static_cast<u32>(counters["flags"].as_int());

    cam.m144 = 0;
    cam.m184 = 0;
    cam.m19A = 0;
    cam.m19B = 0;

    // No lock-on target and no force-lock actor, as the boundary census drives.
    cam.mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    cam.mpLockonActor = 0;
    cam.mpLockonTarget = 0;
    cam_stub_lockon = false;
    cam_stub_lockon_truth = false;

    lk.current.pos = vec_of(s["link_pos_bits"]);
    lk.attention_info.position = vec_of(s["link_attn_bits"]);
    lk.eyePos = vec_of(s["link_eye_bits"]);
    lk.shape_angle.y = static_cast<s16>(s["link_facing"].as_int());
    lk.stub_player_status0 = 0;
    lk.stub_player_status1 = 0;
}

/// One frame's pad, written where the game writes it: `updatePad` overwrites the camera's own
/// stick fields.
void drive_pad(const Json& row) {
    std::memset(&g_mDoCPd_cpadInfo[0], 0, sizeof(g_mDoCPd_cpadInfo[0]));
    g_mDoCPd_cpadInfo[0].mCStickPosX = f32_of(row["cx_bits"]);
    g_mDoCPd_cpadInfo[0].mCStickPosY = f32_of(row["cy_bits"]);
    g_mDoCPd_cpadInfo[0].mCStickValue = f32_of(row["cval_bits"]);
    g_mDoCPd_cpadInfo[0].mTriggerLeft = f32_of(row["trig_bits"]);
    // The main stick stays at rest, which pins the DMC flag down.
    g_mDoCPd_cpadInfo[0].mMainStickPosX = 0.0f;
    g_mDoCPd_cpadInfo[0].mMainStickPosY = 0.0f;
    g_mDoCPd_cpadInfo[0].mMainStickValue = 0.0f;
    g_mDoCPd_cpadInfo[0].mMainStickAngle = 0;
}

std::string at(size_t frame, const char* col) {
    char buf[128];
    std::snprintf(buf, sizeof(buf), "frame %u: %s", static_cast<unsigned>(frame), col);
    return buf;
}

TWWE_TEST(csangle_matches_the_old_sim_over_a_cstick_tape,
          "dCamera_c::Run - updatePad, the mode machine, manualCamera/followCamera and bumpCheck "
          "composed - disagrees with the old sim's camera about the camera yaw the setup finder "
          "reads, on a tape that moves the C-stick instead of holding it centred") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["rows"];
    const Json& s = g["seed"];

    // The population: a gate over zero rows reports success.
    REQUIRE_TRUE(c, rows.size() > 0, "the golden has no rows at all");
    c.note("frames: " + std::to_string(rows.size()));

    // The seed style is the one this build's types[] table gives (as in
    // `test_cam_boundary_census.cpp`).
    const int type = static_cast<int>(s["cur_type"].as_int());
    const int mode = static_cast<int>(s["cur_mode"].as_int());
    const int style = static_cast<int>(s["cur_style"].as_int());
    REQUIRE_INT(c, dCamera_c::types[type].mStyles[mode], style,
                "the golden's camera style is not the one this build's types[] table gives that "
                "type and mode - the tape describes a different camera");

    Rig rig;
    alignas(dCamera_c) unsigned char storage[sizeof(dCamera_c)];
    dCamera_c& cam = *zeroed_camera(storage);
    seed(cam, rig.lk, s);

    // And the first frame dispatches to manualCamera.
    REQUIRE_INT(c, cam.mCamParam.Algorythmn(cam.mCurStyle), dCamAlg_MANUAL_CAMERA_e,
                "the seed style is not the MANUAL algorithm, so frame 0 does not reach "
                "manualCamera and this tape is about a different body");

    size_t manual_frames = 0, follow_frames = 0;
    int angle_min = 0x10000, angle_max = -1;

    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        drive_pad(row);
        cam.Run();

        // csangle first; the rest localises a disagreement (promotion vs. upstream chase).
        REQUIRE_INT(c, cam.mAngleY.Val() & 0xFFFF, row["angle_y"].as_int(), at(i, "csangle"));

        REQUIRE_INT(c, cam.mCurMode, row["mode"].as_int(), at(i, "mCurMode"));
        REQUIRE_INT(c, cam.mCurStyle, row["style"].as_int(), at(i, "mCurStyle"));
        REQUIRE_INT(c, cam.m19B, row["m19b"].as_int(), at(i, "m19B (the L tap)"));

        // The committed globe, which `bumpCheck` promotes.
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mDirection.R()),
                         bits_of(row["dir_r_bits"]), at(i, "mDirection.R"));
        REQUIRE_INT(c, cam.mDirection.U().Val(), row["dir_u"].as_int(), at(i, "mDirection.U"));
        REQUIRE_INT(c, cam.mDirection.V().Val(), row["dir_v"].as_int(), at(i, "mDirection.V"));

        // The view cache the algorithm wrote, which is where a chase disagreement shows first.
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mDirection.R()),
                         bits_of(row["vc_dir_r_bits"]), at(i, "mViewCache.mDirection.R"));
        REQUIRE_INT(c, cam.mViewCache.mDirection.U().Val(), row["vc_dir_u"].as_int(),
                    at(i, "mViewCache.mDirection.U"));
        REQUIRE_INT(c, cam.mViewCache.mDirection.V().Val(), row["vc_dir_v"].as_int(),
                    at(i, "mViewCache.mDirection.V"));

        const Json& vc_center = row["vc_center_bits"];
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mCenter.x),
                         bits_of(vc_center[0]), at(i, "mViewCache.mCenter.x"));
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mCenter.y),
                         bits_of(vc_center[1]), at(i, "mViewCache.mCenter.y"));
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mCenter.z),
                         bits_of(vc_center[2]), at(i, "mViewCache.mCenter.z"));

        const Json& vc_eye = row["vc_eye_bits"];
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mEye.x),
                         bits_of(vc_eye[0]), at(i, "mViewCache.mEye.x"));
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mEye.y),
                         bits_of(vc_eye[1]), at(i, "mViewCache.mEye.y"));
        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mEye.z),
                         bits_of(vc_eye[2]), at(i, "mViewCache.mEye.z"));

        REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mViewCache.mFovy),
                         bits_of(row["vc_fovy_bits"]), at(i, "mViewCache.mFovy"));

        // `mWork` is a union on the port and two field sets in the old sim, so only manual frames
        // are compared; `follow_frames` is asserted against the producer's count.
        if (cam.mCurMode == mode) {
            manual_frames++;
            REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mWork.manual.m3A8.R()),
                             bits_of(row["target_globe_r_bits"]),
                             at(i, "mWork.manual.m3A8.R (the target globe)"));
            REQUIRE_INT(c, cam.mWork.manual.m3A8.U().Val(), row["target_globe_u"].as_int(),
                        at(i, "mWork.manual.m3A8.U (the yaw target)"));
            REQUIRE_INT(c, cam.mWork.manual.m3A8.V().Val(), row["target_globe_v"].as_int(),
                        at(i, "mWork.manual.m3A8.V"));
            REQUIRE_BITS_RAW(c, tww_engine::testing::f32_bits(cam.mWork.manual.m398),
                             bits_of(row["m398_bits"]),
                             at(i, "mWork.manual.m398 (the centre height)"));
        } else {
            follow_frames++;
        }

        const int angle = static_cast<int>(row["angle_y"].as_int());
        if (angle < angle_min) {
            angle_min = angle;
        }
        if (angle > angle_max) {
            angle_max = angle;
        }
    }

    // The population the producer measured is the one this run drove.
    const Json& pop = g["population"];
    REQUIRE_INT(c, static_cast<long long>(rows.size()), pop["frames"].as_int(),
                "the golden's row count and its own population block disagree");
    REQUIRE_INT(c, static_cast<long long>(follow_frames), pop["follow_blips"].as_int(),
                "the run took a different number of followCamera frames than the producer did");
    REQUIRE_TRUE(c, manual_frames > 0, "no frame ran manualCamera");
    REQUIRE_TRUE(c, angle_max - angle_min > 1000,
                 "csangle spans fewer than 1000 BAM across the whole tape, so this is a gate "
                 "over a camera that barely moved");

    c.note("manualCamera frames: " + std::to_string(manual_frames) + ", followCamera frames: " +
           std::to_string(follow_frames));
    c.note("csangle span over the tape: " + std::to_string(angle_max - angle_min) + " BAM (" +
           std::to_string(pop["distinct_csangle"].as_int()) + " distinct values)");

    // The camera row's `0 ULP vs` column: no player proc reaches `Run`, so the proc ledger cannot
    // see the camera. Recorded at the sim tier.
    tww_engine::testing::ledger_record_subsystem(
        "camera", tww_engine::testing::Tier::Sim,
        std::to_string(manual_frames) + " frame(s) of dCamera_c::Run on the finder's camera, "
        "csangle and the view-cache state bit-exact per frame over a C-stick tape - "
        "manualCamera only; followCamera is UNGATED because the oracle models its approach entry "
        "and not the 370-line tail, and its m37C - corrected against DOL "
        "0x8016743C-0x8016751C - is read only under m100 == 0, which this seed never reaches");
}

}  // namespace
