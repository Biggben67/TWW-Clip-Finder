// test_free_wait.cpp - procFreeWait and procFreeWait_init against the decomp's own lines.
//
// No console capture holds a proc-5 frame, so nothing here is credited to the console: the cases
// check the writes, both f32 boundaries of the RNG fork, the attention fork, the hand-back to
// procWait_init, the voice cues, and the three rest animations' lengths from LkAnm.arc.

#include <string>
#include <vector>

#include "framework/manifest.h"
#include "framework/runner.h"

#include "d/d_bg_s.h"
#include "d/actor/d_a_player_main.h"
#include "engine/jma_console_table.h"

// The generated mProcInitTable flag column, the same table commonProcInit reads.
#include "d/actor/proc_flags.inc"

namespace {

using tww_engine::testing::Case;

//: The three animations procFreeWait_init draws between, and the m3570 each arm writes.
struct Arm {
    const char* name;
    daPy_lk_c::daPy_ANM anm;
    int m3570;
};

const Arm kFreeA = {"ANM_FREEA", daPy_lk_c::ANM_FREEA, 0};
const Arm kFreeB = {"ANM_FREEB", daPy_lk_c::ANM_FREEB, 1};
const Arm kFreeD = {"ANM_FREED", daPy_lk_c::ANM_FREED, 0};

/// A player with the boundary reset and the HIO table wired up, as roll_replay.cpp's Rig does.
/// `lk{}` is value-initialisation, not memset: J3DFrameCtrl is polymorphic, and a memset zeroes
/// its vtable pointers.
struct Rig {
    daPy_lk_c lk{};
    daPy_HIO_c hio;
    dBgS bgs;

    Rig() {
        JMA_useConsoleSinTable();
        bgs.Ct();
        lk.reset_boundary();
        lk.m_HIO = &hio;
        set_dComIfG_Bgsp(&bgs);
        set_dComIfG_player(&lk);
    }

    /// Link standing still, facing `facing`, stick centred, nothing held.
    void at_rest(s16 facing) {
        lk.speedF = 0.0f;
        lk.mStickDistance = 0.0f;
        lk.shape_angle.y = facing;
        lk.current.angle.y = facing;
        lk.m34E8 = facing;
        lk.m34DC = facing;
        lk.m34DE = facing;
        lk.m34EA = facing;
        lk.mItemButton = 0;
        lk.mItemTrigger = 0;
        lk.stub_attention_lock = FALSE;
    }
};

/// `stub_rnd` values for each arm, including both boundaries: the fork is `< 0.3333f` then
/// `< 0.6666f`, both strict, so a `<=` slip shows only at those two values.
struct Draw {
    f32 rnd;
    const Arm* arm;
    const char* why;
};

const Draw kDraws[] = {
    {0.0f,    &kFreeA, "the bottom of the range"},
    {0.3332f, &kFreeA, "one thousandth below the first boundary"},
    {0.3333f, &kFreeB, "at the first boundary - `< 0.3333f` is strict, so this is FREEB"},
    {0.5f,    &kFreeB, "the middle of the range"},
    {0.6665f, &kFreeB, "one thousandth below the second boundary"},
    {0.6666f, &kFreeD, "at the second boundary - `< 0.6666f` is strict, so this is FREED"},
    {0.9f,    &kFreeD, "the top of the range"},
};

/// The same fork with both comparisons written `<=`, for the red control.
const Arm& wrong_inclusive_fork(f32 rnd) {
    if (rnd <= 0.3333f) {
        return kFreeA;
    } else if (rnd <= 0.6666f) {
        return kFreeB;
    }
    return kFreeD;
}

/// Run procFreeWait_init with one draw, and hand back the player it left.
void draw_free_wait(Rig& rig, f32 rnd, s16 facing) {
    rig.at_rest(facing);
    rig.lk.stub_rnd = rnd;
    rig.lk.mProcVar6.m3570 = -1;   // so `= 0` and `= 1` are both writes
    rig.lk.mNormalSpeed = 12.5f;   // ditto for `mNormalSpeed = 0.0f`
    rig.lk.mDirection = daPy_lk_c::DIR_FORWARD;
    rig.lk.procFreeWait_init();
}

}  // namespace

// ------------------------------------------------------------------ 1. what the init writes

TWWE_TEST(free_wait_init_writes_the_decomps_own_words,
          "procFreeWait_init no longer leaves the player the way d_a_player_main.cpp:6151-6171 "
          "leaves him - the wrong rest animation for a draw, the wrong mProcVar6.m3570 beside "
          "it, or one of the four words after the fork not written at all") {
    const s16 facing = (s16)0x2000;

    for (const Draw& d : kDraws) {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, d.rnd, facing);
        const std::string at =
            std::string("rnd=") + std::to_string(d.rnd) + " (" + d.why + ")";

        // The fork: which animation, and the flag that arms the voice cues beside it.
        const u16 want_bck = lk.getAnmData(d.arm->anm)->mUnderBckIdx;
        REQUIRE_INT(c, lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx, want_bck,
                    at + ": the MOVE0 animation - expected " + d.arm->name);
        REQUIRE_INT(c, lk.mProcVar6.m3570, d.arm->m3570, at + ": mProcVar6.m3570");

        // The lines after the fork; draw_free_wait seeds each field with a non-answer.
        REQUIRE_INT(c, lk.mCurProc, daPy_lk_c::daPyProc_FREE_WAIT_e, at + ": mCurProc");
        REQUIRE_INT(c, (long long)(u32)lk.mModeFlg, (long long)(u32)daPy_procInitFlags[0x05],
                    at + ": mModeFlg, out of the decomp's own mProcInitTable column");
        REQUIRE_BITS(c, lk.mNormalSpeed, 0.0f, at + ": mNormalSpeed");
        REQUIRE_INT(c, lk.current.angle.y, facing, at + ": current.angle.y = shape_angle.y");
        REQUIRE_INT(c, lk.mDirection, daPy_lk_c::DIR_NONE, at + ": mDirection");

        // The RNG is a stub (boundary/stubs.cpp): its seeds are state a planner cannot know.
        // The decomp draws once per init.
        REQUIRE_INT(c, lk.rnd_draws, 1, at + ": cM_rnd draws");
    }

    c.note("procFreeWait_init's fork, at both f32 boundaries: 0.3333f picks FREEB and 0.6666f "
           "picks FREED, because both comparisons are strict");
}

TWWE_RED_CONTROL(red_free_wait_init_fork_is_inclusive,
                 "the transcription slip the boundary draws exist to catch: `< 0.3333f` and "
                 "`< 0.6666f` written `<=`. It changes the animation at exactly two arguments "
                 "out of the whole range, and at no other, so a draw set without them cannot "
                 "tell the two forks apart") {
    for (const Draw& d : kDraws) {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, d.rnd, (s16)0x2000);
        const Arm& twin = wrong_inclusive_fork(d.rnd);
        REQUIRE_INT(c, lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx,
                    lk.getAnmData(twin.anm)->mUnderBckIdx,
                    std::string("rnd=") + std::to_string(d.rnd) +
                        ": the inclusive fork's animation - " + twin.name);
    }
}

// ----------------------------------------------------- 2. the arm the finder actually rests in

TWWE_TEST(the_finders_rest_state_is_the_middle_arm_and_it_is_the_measured_one,
          "the FREEB arm's frame controller no longer matches the animation metadata the old sim "
          "measured and live-validated - which is the pose every anchor in the finder's catalog "
          "starts from") {
    Rig rig;
    daPy_lk_c& lk = rig.lk;
    draw_free_wait(rig, 0.5f, (s16)0x2000);

    // FREEB is 244 frames, EMode_NONE; `end < 0` in the decomp's call means the animation's own
    // length.
    const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
    REQUIRE_INT(c, (long long)c0.getEnd(), 244, "the FREEB frame controller's end");
    REQUIRE_INT(c, (long long)c0.getAttribute(), (long long)J3DFrameCtrl::EMode_NONE,
                "the FREEB frame controller's attribute");
    REQUIRE_BITS(c, c0.getRate(), 1.0f, "the FREEB frame controller's rate - the decomp's 1.0f");
    REQUIRE_BITS(c, c0.getFrame(), 0.0f, "the FREEB frame controller's frame - the decomp's 0.0f");
    REQUIRE_INT(c, lk.anm_meta_missing, 0,
                "UNDER animations loaded on the FREEB arm whose frameMax has never been measured");

    // Not credited to the `animation` subsystem row: the manifest allows one credit per row, and
    // test_roll_replay holds it to the console.

    c.note("the middle arm is the finder's: the old sim's IDLE_ANIM is 'freeb', and it is the "
           "only free* animation with a measured frameMax anywhere in this project");
}

// ------------------------------------------------ 3. the attention fork and the hand-back

TWWE_TEST(free_wait_runs_the_attention_fork_both_ways,
          "procFreeWait's `checkAttentionLock() ? setSpeedAndAngleAtn() : setSpeedAndAngleNormal()` "
          "fork no longer forks - which would make the targeting arm's UNREACHED grade a claim "
          "about a branch that cannot be taken rather than about one that is not") {
    {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);
        lk.stub_attention_lock = FALSE;

        // Stick centred, so the call is `setNormalSpeedF(0.0f, field_0x24, field_0x1C,
        // field_0x20)` from the HIO table. From 4.25: 0.6 * -4.25 = -2.55 exceeds maxStep 2.5, so
        // the clamp lands on 1.75; then 0.6 * -1.75 = -1.05 is under minStep 1.8, so the minStep
        // step overshoots and the clamp pulls it back to 0.
        lk.mNormalSpeed = 4.25f;
        lk.procFreeWait();
        REQUIRE_BITS(c, lk.mNormalSpeed, 1.75f, "mNormalSpeed after one centred-stick FREE_WAIT "
                                                "frame - setNormalSpeedF's maxStep arm");
        lk.procFreeWait();
        REQUIRE_BITS(c, lk.mNormalSpeed, 0.0f, "mNormalSpeed after the second - the minStep snap "
                                               "with the overshoot clamp");
        REQUIRE_INT(c, lk.unreached_called, 0,
                    "boundary stubs graded UNREACHED that the no-lock arm called");
    }
    {
        // setSpeedAndAngleAtn's first line is `if (mDirection == DIR_FORWARD) return
        // setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0)`, the same call procFreeWait's else arm
        // makes, so on FORWARD both must write identical words.
        Rig a_rig;
        Rig b_rig;
        daPy_lk_c& a = a_rig.lk;
        daPy_lk_c& b = b_rig.lk;
        draw_free_wait(a_rig, 0.5f, (s16)0x2000);
        draw_free_wait(b_rig, 0.5f, (s16)0x2000);
        a.mDirection = b.mDirection = daPy_lk_c::DIR_FORWARD;
        a.mNormalSpeed = b.mNormalSpeed = 4.25f;
        a.setSpeedAndAngleAtn();
        b.setSpeedAndAngleNormal(daPy_HIO_move_c0::m.field_0x0);
        REQUIRE_BITS(c, a.mNormalSpeed, b.mNormalSpeed,
                     "mNormalSpeed: setSpeedAndAngleAtn on FORWARD against setSpeedAndAngleNormal "
                     "with the argument procFreeWait's else arm passes");
        REQUIRE_INT(c, a.shape_angle.y, b.shape_angle.y, "shape_angle.y, the same two calls");
        REQUIRE_INT(c, a.current.angle.y, b.current.angle.y, "current.angle.y, the same two calls");
        REQUIRE_BITS(c, a.mNormalSpeed, 1.75f,
                     "...and the value both land on is the unlocked arm's own: 0.6 * (0 - 4.25) "
                     "is -2.55, over mMove's maxStep 2.5, so this is setNormalSpeedF's clamped arm");
    }
    {
        // A side direction writes `shape_angle.y = m34E6`, which setSpeedAndAngleNormal has no
        // line for, and bleeds speed with mAtnMove's 0.5 / 7.5 / 4.0 instead of mMove's
        // 0.6 / 2.5 / 1.8: 0.5 * -4.25 = -2.125 is under minStep 4.0, so 4.25 - 4.0 = 0.25.
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);
        lk.mDirection = daPy_lk_c::DIR_RIGHT;
        lk.m34E6 = (s16)0x4000;           // the facing the targeting arm snaps to
        lk.mNormalSpeed = 4.25f;
        lk.setSpeedAndAngleAtn();
        REQUIRE_INT(c, lk.shape_angle.y, (s16)0x4000,
                    "shape_angle.y after one side-direction call - setSpeedAndAngleAtn's "
                    "`shape_angle.y = m34E6`, which the unlocked arm has no line for");
        REQUIRE_BITS(c, lk.mNormalSpeed, 0.25f,
                     "mNormalSpeed after it - setNormalSpeedF against mAtnMove's row, whose "
                     "minStep 4.0 the step -2.125 is under");
        REQUIRE_INT(c, lk.unreached_called, 0,
                    "UNREACHED boundary entries the side arm reached - setSpeedAndAngleAtn is a "
                    "copy");
    }
    {
        // With the lock held, checkNextMode's targeting branch runs `std::abs(mNormalSpeed) <=
        // 0.001f ? changeWaitProc() : procAtnMove_init()` (4467-4471). The init zeroes the speed,
        // so it is seeded here for the frame to leave for ATN_MOVE.
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);
        lk.stub_attention_lock = TRUE;
        lk.mNormalSpeed = 4.25f;          // 1.75 after the frame's own bleed, still over 0.001
        lk.procFreeWait();
        REQUIRE_INT(c, lk.mCurProc, daPy_lk_c::daPyProc_ATN_MOVE_e,
                    "mCurProc after one locked FREE_WAIT frame - checkNextMode's targeting "
                    "branch, into a proc that has a body");
        REQUIRE_INT(c, lk.mProcVar0.m34D0, 20,
                    "procAtnMove_init's own last line, which is how the copy is told from a "
                    "dispatch that only recorded the choice");
    }
    c.note("the targeting arm is a copy and its two reachable directions are both driven - "
           "the FORWARD one, where it is setSpeedAndAngleNormal verbatim, and a side one, where "
           "it writes a word that path cannot; the locked frame leaves FREE_WAIT for ATN_MOVE");
}

TWWE_TEST(free_wait_hands_back_to_wait_only_under_an_event,
          "procFreeWait's `!checkNextMode(0) && dComIfGp_event_runCheck()` hand-back no longer "
          "behaves as the decomp writes it - and this is the branch a fixed-FALSE "
          "dComIfGp_event_runCheck leaves UNGATED") {
    {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);
        lk.stub_event_run = FALSE;
        lk.procFreeWait();
        REQUIRE_INT(c, lk.mCurProc, daPy_lk_c::daPyProc_FREE_WAIT_e,
                    "the proc after an idle FREE_WAIT frame with no event running");
        REQUIRE_BITS(c, lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].getRate(), 1.0f,
                    "the MOVE0 rate - the hand-back's setRate(0.0f) must not have run");
    }
    {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);
        lk.stub_event_run = TRUE;      // a cutscene has taken Link over
        lk.procFreeWait();
        // procWait_init's FREE_WAIT early-out (6049) needs `!dComIfGp_event_runCheck()`, so the
        // full init runs and its new animation hides the hand-back's setRate(0.0f).
        REQUIRE_INT(c, lk.mCurProc, daPy_lk_c::daPyProc_WAIT_e,
                    "the proc after the hand-back ran procWait_init");
        REQUIRE_TRUE(c, lk.m_anm_heap_under[daPy_lk_c::UNDER_MOVE0_e].mIdx !=
                            lk.getAnmData(daPy_lk_c::ANM_FREEB)->mUnderBckIdx,
                     "the MOVE0 animation is still FREEB, so procWait_init did not re-pose Link");
    }
    c.note("the hand-back is a branch no gate can enter while dComIfGp_event_runCheck is a "
           "fixed FALSE: `!checkNextMode(0) && FALSE` is dead");
}

TWWE_RED_CONTROL(red_free_wait_hands_back_without_an_event,
                 "claims the hand-back runs with no event - which is what a port that dropped "
                 "the `&& dComIfGp_event_runCheck()` term would do, and what a FALSE-only "
                 "boundary could never tell apart from the correct body") {
    Rig rig;
    daPy_lk_c& lk = rig.lk;
    draw_free_wait(rig, 0.5f, (s16)0x2000);
    lk.stub_event_run = FALSE;
    lk.procFreeWait();
    REQUIRE_INT(c, lk.mCurProc, daPy_lk_c::daPyProc_WAIT_e,
                "the proc after an idle FREE_WAIT frame with no event running");
}

// ------------------------------------------------------------------------ 4. the voice cues

TWWE_TEST(free_wait_voice_cues_fire_where_the_anim_clock_passes_them,
          "procFreeWait's two voiceStart arms no longer fire where d_a_player_main.cpp:6180-6188 "
          "fires them - the 168 test before the 105 test, both inside `mProcVar6.m3570 != 0`, "
          "and neither reached when the flag is clear") {
    // Two checkPass tests, the 105 one in the else of the 168 one, behind a flag only the FREEB
    // arm sets.
    struct Probe { f32 frame; int want; const char* why; };
    const Probe probes[] = {
        {0.0f,   -1, "frame 0 - the clock has passed neither cue"},
        {104.5f, 47, "the step 104.5 -> 105.5 passes 105 and not 168"},
        {167.5f, 48, "the step 167.5 -> 168.5 passes 168, and the 105 test is the else"},
        {200.0f, -1, "past both - checkPass is an edge, not a threshold"},
    };
    for (const Probe& p : probes) {
        Rig rig;
        daPy_lk_c& lk = rig.lk;
        draw_free_wait(rig, 0.5f, (s16)0x2000);   // the FREEB arm, so m3570 is 1
        REQUIRE_INT(c, lk.mProcVar6.m3570, 1, "the FREEB arm arms the cues");
        lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setFrame(p.frame);
        lk.voice_id = -1;
        lk.procFreeWait();
        REQUIRE_INT(c, lk.voice_id, p.want, std::string("voiceStart id at ") + p.why);
    }

    // The FREEA arm leaves m3570 at 0, and the same clock position plays nothing.
    Rig rig;
    daPy_lk_c& lk = rig.lk;
    draw_free_wait(rig, 0.0f, (s16)0x2000);       // the FREEA arm
    REQUIRE_INT(c, lk.mProcVar6.m3570, 0, "the FREEA arm leaves the cues disarmed");
    lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setFrame(104.5f);
    lk.voice_id = -1;
    lk.procFreeWait();
    REQUIRE_INT(c, lk.voice_id, -1, "voiceStart id with mProcVar6.m3570 clear");
}

// ---------------------------------------------------------------- 5. the rest animations' lengths

TWWE_TEST(all_three_rest_animations_have_a_measured_length,
          "a rest animation with no measured frameMax loads at length 0, and since a missing "
          "under length stops the run (StepResult::NoAnimation) every idle past the fidget "
          "countdown would end the move there") {
    // A missing frameMax is not defaulted: getAnimeResource bumps `anm_meta_missing` and loads 0.
    // The lengths are LkAnm.arc's; FREEA and FREED are not console-verified.
    struct Want {
        const Arm* arm;
        f32 draw;
        int end;
    };
    const Want wants[] = {{&kFreeA, 0.0f, 199}, {&kFreeB, 0.5f, 244}, {&kFreeD, 0.9f, 139}};
    int measured = 0;
    for (const Want& w : wants) {
        Rig rig;
        draw_free_wait(rig, w.draw, (s16)0x2000);
        REQUIRE_INT(c, rig.lk.anm_meta_missing, 0, std::string(w.arm->name) + " has no length");
        REQUIRE_INT(c, rig.lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].getEnd(), w.end,
                    std::string(w.arm->name) + "'s clock does not end at its .bck's frameMax");
        if (rig.lk.anm_meta_missing == 0) ++measured;
    }
    REQUIRE_INT(c, measured, 3, "rest animations procFreeWait_init can draw with a known length");
    c.note("FREEA 199, FREEB 244, FREED 139 frames");
}
