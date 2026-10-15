// test_cam_mode_machine.cpp - the camera's mode machine, per camera type.
//
// Run's mode machine, d_camera.cpp:188-206:
//
//     mNextMode = nextMode(mCurMode);
//     next = mNextMode;
//     if (next != mCurMode)
//         if (types[mCurType].mStyles[next] >= 0 && onModeChange(mCurMode, next))
//             mCurMode = mNextMode;
//     if (types[mCurType].mStyles[mCurMode] < 0) mCurMode = 0;
//     curStyle = types[mCurType].mStyles[mCurMode];
//     if (curStyle >= 0)
//         if (mCurStyle != curStyle && onStyleChange(mCurStyle, curStyle))
//             mCurStyle = types[mCurType].mStyles[mCurMode], mCamParam.Change(mCurStyle);
//
// test_cam_next_mode.cpp drives only type 1 ("Plain"), where every style is legal; this drives 60
// of the JPN build's 62 types, whose illegal modes reach onModeChange, the mode-0 fallback and
// the style change. 18 types have `mStyles[0] != mStyles[1]`, the only input onModeChange's two
// `m110 = 0` arms read.
//
// Sim tier: the oracle is the old sim's land_cam.py (`_next_mode`, `_on_mode_change`, the
// `m11C = 0` reset in `.step`). No capture records a camera mode. The producer hands the oracle
// this port's own `dCamera_c::types[]`, so the table is shared input, not under test; its row
// names are checked against this build below.
//
// Not gated:
//   * `Empty` and `Keep`, whose `mStyles[0] < 0`: the old sim indexes unguarded, so the producer
//     excludes them.
//   * onModeChange's `m10C = 0`, its `i_curMode == 0xe` setView arm, `case 3` clrComStat and
//     `case 12` `m254 |= 2`: not modelled by the old sim.
//   * onStyleChange beyond `m11C = 0`, including its `m144 = 1` raise; hence m144 is compared
//     after the mode half.
//   * Run's own copy of the legality test: nextMode's tail already refuses, so it is true on
//     every row.
//   * the NPC_MD force-lock arm: the id is -1 on every row.
//
// Run cannot be called (it runs checkSpecialArea, Att, updatePad and a camera engine first), so
// the lines above are transcribed in ask(); the red control checks the transcription.

#include <cstdio>
#include <cstdlib>
#include <map>
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

const char* const kGolden = "cam_mode_machine_oracle.json";

/// Values neither body writes, so "did not run" and "wrote the default" differ. They must match
/// the producer's `seeds` block, asserted below.
const int kSeedM108 = 77;
const int kSeedM10x = 3;
const int kSeedM110 = 5;
const f32 kSeedM14C = 12.5f;
const int kSeedM11C = 9;

/// What the machine settled on, split at the boundary the oracle can follow.
struct Settled {
    int mode;        //: mCurMode after the mode half
    int m144;        //: m144 after the mode half
    int m184;
    u32 flags;
    u32 m108;
    int m100, m101, m102;
    int m110;
    f32 m14C;
    u32 m11C;        //: after the style half
    int style;
    int next_mode;   //: what the ladder answered, before Run looked at it
    bool style_changed;
    bool m144_raised_by_style;
};

/// Seed a camera from a golden row and run Run's mode machine over it.
Settled ask(dCamera_c& cam, fopAc_ac_c* player, const Json& row) {
    const int type = static_cast<int>(row["cur_type"].as_int());
    const int mode = static_cast<int>(row["cur_mode"].as_int());

    cam.mPadId = 0;
    cam.mpPlayerActor = player;
    cam.mCurType = type;
    cam.mCurMode = mode;
    // A camera whose current mode is illegal carries style -1, as the table says. The old sim
    // gets a sentinel unequal to every real style.
    cam.mCurStyle = dCamera_c::types[type].mStyles[mode];
    if (cam.mCurStyle >= 0) {
        cam.mCamParam.Change(cam.mCurStyle);
    }

    cam.m144 = static_cast<int>(row["m144"].as_int());
    cam.m184 = static_cast<int>(row["m184"].as_int());
    cam.m19B = static_cast<u8>(row["m19B"].as_int());
    cam.mStickCValueLast = row["cval"].as_f32();
    cam.mStickCPosYLast = row["cy"].as_f32();
    cam.mStickMainValueLast = row["mval"].as_f32();
    cam.mDirection.R(row["dir_r"].as_f32());
    cam.mEventFlags = static_cast<u32>(row["flags"].as_int());

    cam.m108 = static_cast<u32>(kSeedM108);
    cam.m100 = static_cast<u8>(kSeedM10x);
    cam.m101 = static_cast<u8>(kSeedM10x);
    cam.m102 = static_cast<u8>(kSeedM10x);
    cam.m110 = static_cast<u8>(kSeedM110);
    cam.m14C = kSeedM14C;
    cam.m11C = static_cast<u32>(kSeedM11C);

    // The NPC_MD arm, skipped on both sides by the same condition.
    cam.mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    cam.mpLockonActor = 0;
    cam.mpLockonTarget = row["has_target"].boolean ? player : 0;

    // `mBG.m00.m58 > player_pos.y` lowers m1AE; pinned so the branch goes the same way on every
    // row.
    cam.mBG.m00.m58 = -1.0e9f;
    cam.m1AE = 0;

    daPy_lk_c* lk = static_cast<daPy_lk_c*>(static_cast<void*>(player));
    lk->stub_player_status0 = static_cast<u32>(row["status0"].as_int());
    lk->stub_player_status1 = static_cast<u32>(row["status1"].as_int());
    cam_stub_lockon = row["lockon"].boolean;
    cam_stub_lockon_truth = row["truth"].boolean;

    Settled s;

    // ---- Run's mode machine, d_camera.cpp:188-206, transcribed ----------------------------
    cam.mNextMode = cam.nextMode(cam.mCurMode);
    const long next = cam.mNextMode;
    s.next_mode = static_cast<int>(next);

    if (next != cam.mCurMode) {
        if (dCamera_c::types[cam.mCurType].mStyles[next] >= 0 &&
            cam.onModeChange(cam.mCurMode, next)) {
            cam.mCurMode = cam.mNextMode;
        }
    }
    if (dCamera_c::types[cam.mCurType].mStyles[cam.mCurMode] < 0) {
        cam.mCurMode = 0;
    }

    // The mode half's answer, read before onStyleChange can touch m144.
    s.mode = cam.mCurMode;
    s.m144 = cam.m144;
    s.m184 = cam.m184;
    s.flags = cam.mEventFlags;
    s.m108 = cam.m108;
    s.m100 = cam.m100;
    s.m101 = cam.m101;
    s.m102 = cam.m102;
    s.m110 = cam.m110;
    s.m14C = cam.m14C;

    const s16 curStyle = dCamera_c::types[cam.mCurType].mStyles[cam.mCurMode];
    const int m144_before_style = cam.m144;
    s.style_changed = false;
    if (curStyle >= 0) {
        if (cam.mCurStyle != curStyle && cam.onStyleChange(cam.mCurStyle, curStyle)) {
            cam.mCurStyle = dCamera_c::types[cam.mCurType].mStyles[cam.mCurMode];
            cam.mCamParam.Change(cam.mCurStyle);
            s.style_changed = true;
        }
    }
    // -------------------------------------------------------------------------------------

    s.m11C = cam.m11C;
    s.style = cam.mCurStyle;
    s.m144_raised_by_style = (cam.m144 != m144_before_style);
    return s;
}

std::string where(const Json& row, const char* col) {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
                  "type %lld (%s), mode %lld, m144 %lld, m19B %lld, s0 0x%08llX, s1 0x%08llX: %s",
                  row["cur_type"].as_int(),
                  dCamera_c::types[row["cur_type"].as_int()].name,
                  row["cur_mode"].as_int(), row["m144"].as_int(), row["m19B"].as_int(),
                  static_cast<unsigned long long>(row["status0"].as_int()),
                  static_cast<unsigned long long>(row["status1"].as_int()), col);
    return buf;
}

TWWE_TEST(the_camera_mode_machine_matches_the_old_sim,
          "dCamera_c's mode machine - nextMode, the types[] legality reads, onModeChange and "
          "onStyleChange's m11C reset - disagrees with the old sim's camera about which mode and "
          "style a camera settles into on a room whose type does not allow every mode") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["rows"];

    // A gate over zero rows reports success.
    REQUIRE_TRUE(c, rows.size() > 0, "the golden has no rows at all");
    c.note("rows: " + std::to_string(rows.size()));

    // Both sides seed onModeChange's fields with the same values it never writes.
    const Json& seeds = g["seeds"];
    REQUIRE_INT(c, kSeedM108, seeds["m108"].as_int(), "seed m108");
    REQUIRE_INT(c, kSeedM10x, seeds["m10x"].as_int(), "seed m100/m101/m102");
    REQUIRE_INT(c, kSeedM110, seeds["m110"].as_int(), "seed m110");
    REQUIRE_INT(c, kSeedM11C, seeds["m11C"].as_int(), "seed m11C");
    REQUIRE_BITS(c, kSeedM14C, seeds["m14C"].as_f32(), "seed m14C");

    // The producer parses `d_cam_type.cpp` as text, skipping `#if VERSION > VERSION_JPN` rows;
    // names are checked, not just the count, because a reordering keeps the count.
    const Json& types = g["types"];
    for (std::map<std::string, Json>::const_iterator it = types.object.begin();
         it != types.object.end(); ++it) {
        const int idx = std::atoi(it->first.c_str());
        REQUIRE_TRUE(c, idx >= 0 && idx < dCamera_c::type_num,
                     "the golden names camera type " + it->first +
                         ", which this build does not have");
        REQUIRE_TRUE(c, it->second.str == dCamera_c::types[idx].name,
                     "camera type " + it->first + " is '" +
                         std::string(dCamera_c::types[idx].name) + "' in this build and '" +
                         it->second.str + "' in the golden");
    }

    Rig rig;
    dCamera_c cam{};

    std::vector<int> mode_seen(32, 0);
    std::vector<int> type_seen(dCamera_c::type_num, 0);
    size_t ran_mode_change = 0, fell_back = 0, style_changed = 0, m144_by_style = 0;
    size_t m110_zero = 0, refused_by_run = 0, flag_gap_rows = 0;

    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        const Settled s = ask(cam, &rig.lk, row);

        REQUIRE_INT(c, s.next_mode, row["next_mode"].as_int(), where(row, "next_mode"));
        REQUIRE_INT(c, s.mode, row["mode_after"].as_int(), where(row, "mode_after"));
        REQUIRE_INT(c, s.m144, row["m144_after"].as_int(), where(row, "m144 (mode half)"));
        REQUIRE_INT(c, s.m184, row["m184_after"].as_int(), where(row, "m184"));

        // Known gap; the port is right. The two tails place the `next_mode == 1` flag
        // differently:
        //
        //   port        if (mStyles[next_mode] >= 0) { if (next_mode == 1) setFlag(0x100000);
        //                                              return next_mode; }
        //               return i_curMode;
        //   old sim     if nm not in self.types and nm != cur: return cur
        //               if nm == 1: self.flags |= 0x100000
        //
        // With n the ladder's answer after the mode-12 fixup, they differ only when n == cur == 1
        // and mode 1 is illegal: the old sim flags a change that did not happen. The oracle is
        // frozen, so the bit is an EXPECT_KNOWN_GAP. The golden banks the ladder's own answer
        // (`ladder_answer`, re-asked with every mode legal), since the tail returns cur.
        const dCamera__Type& t = dCamera_c::types[row["cur_type"].as_int()];
        const long long ladder = row["ladder_answer"].as_int();
        const long long n = (ladder == 12 && t.mStyles[12] < 0) ? row["cur_mode"].as_int()
                                                                : ladder;
        const bool flag_gap = n == 1 && row["cur_mode"].as_int() == 1 && t.mStyles[1] < 0;
        if (flag_gap) {
            flag_gap_rows++;
            REQUIRE_INT(c, static_cast<long long>(s.flags & ~0x100000u),
                        row["flags_after"].as_int() & ~0x100000LL,
                        where(row, "flags, less the 0x100000 known gap"));
            EXPECT_KNOWN_GAP(c, static_cast<long long>(s.flags) == row["flags_after"].as_int(),
                             "the old sim's camera raises 0x100000 when nextMode answers mode 1 "
                             "on a camera type where mode 1 is illegal; the decomp guards that "
                             "setFlag on the legality test and this port follows it");
        } else {
            REQUIRE_INT(c, static_cast<long long>(s.flags), row["flags_after"].as_int(),
                        where(row, "flags"));
        }
        REQUIRE_INT(c, static_cast<long long>(s.m108), row["m108_after"].as_int(),
                    where(row, "m108"));
        REQUIRE_INT(c, s.m100, row["m100_after"].as_int(), where(row, "m100"));
        REQUIRE_INT(c, s.m101, row["m101_after"].as_int(), where(row, "m101"));
        REQUIRE_INT(c, s.m102, row["m102_after"].as_int(), where(row, "m102"));
        REQUIRE_INT(c, s.m110, row["m110_after"].as_int(), where(row, "m110"));
        REQUIRE_BITS_RAW(c, tww_engine::testing::bits(s.m14C),
                         static_cast<u32>(row["m14C_after_bits"].as_int()), where(row, "m14C"));
        REQUIRE_INT(c, static_cast<long long>(s.m11C), row["m11C_after"].as_int(),
                    where(row, "m11C"));
        REQUIRE_INT(c, s.style, row["style_after"].as_int(), where(row, "style"));

        if (s.mode >= 0 && s.mode < 32) {
            mode_seen[s.mode]++;
        }
        type_seen[row["cur_type"].as_int()]++;
        if (s.m108 != static_cast<u32>(kSeedM108)) {
            ran_mode_change++;
        }
        if (s.m110 == 0) {
            m110_zero++;
        }
        if (s.mode == 0 && s.next_mode != 0) {
            fell_back++;
        }
        if (s.style_changed) {
            style_changed++;
        }
        if (s.m144_raised_by_style) {
            m144_by_style++;
        }
        if (s.next_mode != row["cur_mode"].as_int() &&
            dCamera_c::types[row["cur_type"].as_int()].mStyles[s.next_mode] < 0) {
            refused_by_run++;
        }
    }

    // Printed whether it passes or fails.
    int distinct_modes = 0, distinct_types = 0;
    for (size_t m = 0; m < mode_seen.size(); m++) {
        if (mode_seen[m]) {
            distinct_modes++;
        }
    }
    for (size_t t = 0; t < type_seen.size(); t++) {
        if (type_seen[t]) {
            distinct_types++;
        }
    }
    c.note("camera types driven: " + std::to_string(distinct_types) + " of " +
           std::to_string(dCamera_c::type_num));
    c.note("distinct settled modes: " + std::to_string(distinct_modes));
    c.note("onModeChange ran on " + std::to_string(ran_mode_change) + " row(s); its m110 = 0 arm "
           "on " + std::to_string(m110_zero));
    c.note("rows that fell back to mode 0 through Run's second types[] read: " +
           std::to_string(fell_back));
    c.note("rows where the style changed: " + std::to_string(style_changed) +
           "; of those, onStyleChange raised m144 on " + std::to_string(m144_by_style) +
           " (port-only - the old sim does not model it, so it is not asserted)");
    c.note("rows Run's own legality test refused: " + std::to_string(refused_by_run) +
           " (nextMode's tail already refuses, so Run's copy is true on every row here)");
    c.note("rows on the 0x100000 known gap (the port is right, the frozen oracle is not): " +
           std::to_string(flag_gap_rows));

    // The population is not degenerate on the axes this case adds.
    REQUIRE_TRUE(c, distinct_types >= 60,
                 "fewer than sixty camera types were driven, so the type axis this case exists "
                 "for is not in the corpus");
    REQUIRE_TRUE(c, ran_mode_change > 0 && ran_mode_change < rows.size(),
                 "onModeChange either ran on every row or on none, so the legality test that "
                 "decides whether it runs is asserted by nothing here");
    REQUIRE_TRUE(c, m110_zero > 0,
                 "onModeChange's m110 = 0 arm - the only thing in either body that reads "
                 "mStyles[0] == mStyles[1] - was never taken");
    REQUIRE_TRUE(c, fell_back > 0,
                 "no row fell back to mode 0 through Run's second types[] read, which is one of "
                 "the two reads this case exists to reach");
    REQUIRE_TRUE(c, style_changed > 0, "no row changed style, so onStyleChange never ran");
    // The known gap sits on a branch; a branch no row takes would never go stale visibly.
    REQUIRE_TRUE(c, flag_gap_rows > 0,
                 "no row reaches the 0x100000 flag gap, so the EXPECT_KNOWN_GAP marking it "
                 "cannot fire and would sit here unexamined - the corpus needs a camera type "
                 "whose mode 1 is illegal, entered in mode 1");

    // The tier, asserted, so this case cannot drift onto a console capture unnoticed.
    REQUIRE_TRUE(c, tww_engine::testing::golden_tier(kGolden) == tww_engine::testing::Tier::Sim,
                 "the camera mode-machine golden is no longer sim tier - re-read what this case "
                 "claims before believing it");
}

// Checks the transcription: drop the second `types[]` read (the mode-0 fallback) and the suite
// must reject it. `fell_back > 0` above is what makes that possible.
TWWE_RED_CONTROL(the_corpus_can_tell_the_mode_0_fallback_is_there,
                 "Run's `if (types[mCurType].mStyles[mCurMode] < 0) mCurMode = 0` is dropped "
                 "from the transcription, so a camera whose settled mode is illegal for its type "
                 "keeps that mode instead of falling back") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["rows"];

    Rig rig;
    dCamera_c cam{};

    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        const Settled s = ask(cam, &rig.lk, row);
        (void)s;

        // Re-run the mode half with the fallback removed.
        const int type = static_cast<int>(row["cur_type"].as_int());
        cam.mCurType = type;
        cam.mCurMode = static_cast<int>(row["cur_mode"].as_int());
        cam.m144 = static_cast<int>(row["m144"].as_int());
        cam.m184 = static_cast<int>(row["m184"].as_int());
        cam.mEventFlags = static_cast<u32>(row["flags"].as_int());
        const long next = cam.nextMode(cam.mCurMode);
        if (next != cam.mCurMode) {
            if (dCamera_c::types[type].mStyles[next] >= 0 &&
                cam.onModeChange(cam.mCurMode, next)) {
                cam.mCurMode = static_cast<int>(next);
            }
        }
        REQUIRE_INT(c, cam.mCurMode, row["mode_after"].as_int(),
                    where(row, "mode_after (fallback dropped)"));
    }
}

}  // namespace
