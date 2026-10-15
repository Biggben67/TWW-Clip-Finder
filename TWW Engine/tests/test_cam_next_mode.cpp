// test_cam_next_mode.cpp - `dCamera_c::nextMode` (d_camera.cpp:1565), the fifteen-arm ladder that
// picks a frame's camera mode. An L tap goes through it: `m19B`, the trigger's rising edge, raises
// `m144`, which drops mode 12 to mode 0 for one frame.
//
// Sim tier: the oracle `cam_next_mode_oracle.json` is the old sim's `land_cam.py::_next_mode`, an
// independent model of the same body, not a console capture.
//
// Not gated: the NPC_MD force-lock arm (id held at -1, as the old sim assumes); `m254 |= 1` and the
// three `setComStat` calls (the old sim has none); `dComIfGp_evmng_cameraPlay()`'s true arm (stub
// answers 0); and the style-legality test in the tail on an illegal mode (both sides are driven to
// a no-op by camera type 1 and an all-modes types map).

#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "player_rig.h"

#include "d/d_camera.h"
#include "d/actor/d_a_player_main.h"
#include "boundary/game_boundary.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::Rig;

const char* const kGolden = "cam_next_mode_oracle.json";

/// One golden row, seeded onto a camera and asked.
struct Answer {
    int next_mode;
    int m144_after;
    int m184_after;
};

/// Seed `cam` from a golden row and call the body. Fields the row does not name are held at the
/// values it was produced with (no lock-on target).
Answer ask(dCamera_c& cam, fopAc_ac_c* player, const Json& row) {
    cam.mPadId = 0;
    cam.mpPlayerActor = player;
    // Type 1, "Plain": the tail discards any mode with `types[mCurType].mStyles[next_mode] < 0`,
    // and type 0 ("Empty") has every style at dCamStyle_NONE_e. Plain has a style for all twenty
    // modes, matching the oracle's all-modes types map.
    cam.mCurType = 1;
    cam.mCurMode = static_cast<int>(row["cur_mode"].as_int());
    cam.m144 = static_cast<int>(row["m144"].as_int());
    cam.m184 = static_cast<int>(row["m184"].as_int());
    cam.m19B = static_cast<u8>(row["m19B"].as_int());
    cam.mStickCValueLast = row["cval"].as_f32();
    cam.mStickCPosYLast = row["cy"].as_f32();
    cam.mStickMainValueLast = row["mval"].as_f32();
    cam.mDirection.R(row["dir_r"].as_f32());
    cam.mEventFlags = static_cast<u32>(row["flags"].as_int());

    // The NPC_MD arm, skipped on both sides by its own condition.
    cam.mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    cam.mpLockonActor = 0;
    // `mpLockonTarget` is the mode-8 arm's own test. The old sim spells it `lockon_target`.
    cam.mpLockonTarget = row["has_target"].boolean ? player : 0;

    // `mBG.m00.m58 > player_pos.y` lowers m1AE; both held so the branch is the same every row.
    cam.mBG.m00.m58 = -1.0e9f;
    cam.m1AE = 0;

    // The boundary the ladder asks: two masked status words and the attention pair.
    daPy_lk_c* lk = static_cast<daPy_lk_c*>(static_cast<void*>(player));
    lk->stub_player_status0 = static_cast<u32>(row["status0"].as_int());
    lk->stub_player_status1 = static_cast<u32>(row["status1"].as_int());
    cam_stub_lockon = row["lockon"].boolean;
    cam_stub_lockon_truth = row["truth"].boolean;

    Answer a;
    a.next_mode = cam.nextMode(cam.mCurMode);
    a.m144_after = cam.m144;
    a.m184_after = cam.m184;
    return a;
}

std::string where(const Json& row, const char* col) {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
                  "mode %lld, m144 %lld, m184 %lld, m19B %lld, s0 0x%08llX, s1 0x%08llX: %s",
                  row["cur_mode"].as_int(), row["m144"].as_int(), row["m184"].as_int(),
                  row["m19B"].as_int(),
                  static_cast<unsigned long long>(row["status0"].as_int()),
                  static_cast<unsigned long long>(row["status1"].as_int()), col);
    return buf;
}

TWWE_TEST(the_camera_mode_sequencer_matches_the_old_sim,
          "dCamera_c::nextMode disagrees with the old sim's camera about which camera "
          "algorithm a frame runs - so manualCamera is reached on a different set of frames "
          "than every land golden in the old repo was measured through") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["rows"];

    REQUIRE_TRUE(c, rows.size() > 0, "the golden has no rows at all");
    c.note("rows: " + std::to_string(rows.size()));

    Rig rig;
    dCamera_c cam{};

    std::vector<int> seen(32, 0);
    size_t m144_raised = 0, m184_raised = 0, changed_mode = 0;

    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        const Answer a = ask(cam, &rig.lk, row);

        REQUIRE_INT(c, a.next_mode, row["next_mode"].as_int(), where(row, "next_mode"));
        REQUIRE_INT(c, a.m144_after, row["m144_after"].as_int(), where(row, "m144"));
        REQUIRE_INT(c, a.m184_after, row["m184_after"].as_int(), where(row, "m184"));

        if (a.next_mode >= 0 && a.next_mode < 32) {
            seen[a.next_mode]++;
        }
        if (a.m144_after && !row["m144"].as_int()) {
            m144_raised++;
        }
        if (a.m184_after && !row["m184"].as_int()) {
            m184_raised++;
        }
        if (a.next_mode != row["cur_mode"].as_int()) {
            changed_mode++;
        }
    }

    // Coverage: a ladder answering one value on every row would pass the comparisons above.
    int distinct = 0;
    std::string spread;
    for (size_t m = 0; m < seen.size(); m++) {
        if (seen[m]) {
            distinct++;
            spread += " " + std::to_string(m) + "->" + std::to_string(seen[m]);
        }
    }
    c.note("distinct next_mode answers: " + std::to_string(distinct) + ";" + spread);
    c.note("rows where the mode changed: " + std::to_string(changed_mode));
    c.note("rows that raised m144: " + std::to_string(m144_raised) +
           "; that raised m184: " + std::to_string(m184_raised));

    REQUIRE_TRUE(c, distinct >= 6,
                 "the ladder answered fewer than six distinct modes over the whole grid, so most "
                 "of its arms were not reached and this case is not gating them");
    REQUIRE_TRUE(c, m184_raised > 0,
                 "no row raised m184 - the C-stick-up latch, the one piece of state nextMode "
                 "carries between frames, was never exercised");

    REQUIRE_TRUE(c, tww_engine::testing::golden_tier(kGolden) == tww_engine::testing::Tier::Sim,
                 "the camera sequencer golden is no longer sim tier - re-read what this case "
                 "claims before believing it");
}

// Red control: the status word answering yes to every mask must fail the grid.
TWWE_RED_CONTROL(the_grid_can_tell_two_status_masks_apart,
                 "the status0 word is driven to all bits set on every row instead of the row's "
                 "own mask - the shape of a boundary that discards its argument, where "
                 "every check_owner_action answers yes") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["rows"];

    Rig rig;
    dCamera_c cam{};

    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        Answer a = ask(cam, &rig.lk, row);
        (void)a;
        // Re-ask with every status bit set.
        rig.lk.stub_player_status0 = 0xFFFFFFFFu;
        cam.mCurMode = static_cast<int>(row["cur_mode"].as_int());
        cam.m144 = static_cast<int>(row["m144"].as_int());
        cam.m184 = static_cast<int>(row["m184"].as_int());
        const int got = cam.nextMode(cam.mCurMode);
        REQUIRE_INT(c, got, row["next_mode"].as_int(), where(row, "next_mode (mask discarded)"));
    }
}

}  // namespace
