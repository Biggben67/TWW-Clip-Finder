#include "roll_replay.h"
#include "player_rig.h"

#include <cstdio>
#include <cstring>

#include "engine/ppc_fp.h"
#include "JSystem/JMath/JMath.h"
#include "d/actor/d_a_player_main.h"
#include "engine/jma_console_table.h"

namespace tww_engine {
namespace testing {
namespace {

// --------------------------------------------------------------- the deliberately wrong twins

// TWIN: the anim clock accumulated in double instead of f32. `mFrame += mRate` is one f32 add;
// the console capture shows its drift (11.000000953674316 at the tenth step of 1.1).
struct WrongAnimClock {
    double frame = 0.0;
    void reset(f32 start) { frame = start; }
    void update(f32 rate) { frame += rate; }
    f32 get() const { return (f32)frame; }
};

// TWIN: cLib_addCalc's minStep arm written as "snap to the target"; the real one moves by
// +-minStep and clamps only if that overshoots. One capture frame lands in the arm.
// Deliberately narrow: setNormalSpeedF's maxStep for a centred stick (target 0), applied only on
// frames that begin and end in MOVE.
f32 addcalc_snap_to_target(f32 value, f32 target, f32 scale, f32 maxStep, f32 minStep) {
    if (value == target) {
        return value;
    }
    f32 step = scale * (target - value);
    if (step >= minStep || step <= -minStep) {
        if (step > maxStep) {
            step = maxStep;
        }
        if (step < -maxStep) {
            step = -maxStep;
        }
        return value + step;
    }
    return target;  // the slip: c_lib.cpp:172-186 moves by +-minStep and clamps.
}

f32 wrong_decel_speed(const daPy_HIO_c& hio, f32 before) {
    f32 maxStep = before;                        // d_a_player_main.cpp:2325-2332, with
    if (maxStep > hio.mMove.m.field_0x1C) {      // dVar10 == 0 (mStickDistance 0.0)
        maxStep = hio.mMove.m.field_0x1C;
    }
    if (maxStep < hio.mMove.m.field_0x20) {
        maxStep = hio.mMove.m.field_0x20;
    }
    return addcalc_snap_to_target(before, 0.0f, hio.mMove.m.field_0x24, maxStep,
                                  hio.mMove.m.field_0x20);
}

// TWIN: MOVE1's frame accumulated instead of re-slaved to MOVE0's phase. setMoveAnime recomputes
// it every frame from f31 = anm0_frame/anm0_frameMax (d_a_player_main.cpp:12743-12745);
// accumulating is 1 ULP out by the fourth frame.
struct AccumulatedMove1 {
    f32 frame = 0.0f;
    bool armed = false;

    void arm(f32 f) {
        if (!armed) {
            frame = f;
            armed = true;
        }
    }
    void step(f32 rate) {
        if (armed) {
            frame += rate;
        }
    }
};

// TWIN (`wrong_order`): the proc run before the anim clocks. execute() calls animeUpdate at 11346
// and dispatches the proc at 11394. Visible at capture frame 63, where procCrouch_init resets
// MOVE0 after animeUpdate has advanced it.

// TWIN (`wrong_blend`): blend_move read as the MOVE1 blend ratio instead of m3598 (the
// WALK<->DASH speedF blend); 1.0 against 0.588 on every compared frame.

//: cPadInfo +0x30/+0x32 (the capture's `btn_hold`/`btn_trig`) are `controller_pad_buttons`, a
//: 12-bit bitfield (c_API_controller_pad.h:7-20), not the PAD_BUTTON_* word: here 0x0400 is R.
enum : int {
    kCpadL = 0x0200,
    kCpadR = 0x0400,
    kCpadA = 0x0100,
    kCpadB = 0x0080,
    kCpadX = 0x0040,
    kCpadY = 0x0020,
    kCpadZ = 0x0800,
};

//: The five setStickData gates behind `dComIfGp_getButtonActionMode()` (and, for X/Y/Z, behind
//: mTinkleHoverTimer). The capture has no column for either.
struct Gated {
    const char* name;
    int bit;
};
const Gated kActionModeGated[] = {
    {"a", kCpadA}, {"b", kCpadB}, {"x", kCpadX}, {"y", kCpadY}, {"z", kCpadZ},
};

}  // namespace

uint8_t item_trigger_for(const Json& golden, int i) {
    int t = 0;
    if (golden[size_t(i)]["lock_r"].as_int() && !golden[size_t(i - 1)]["lock_r"].as_int()) {
        t |= daPy_lk_c::BTN_R;  // mDoCPd_R_LOCK_TRIGGER(0) -> BTN_R
    }
    if (golden[size_t(i)]["btn_trig"].as_int() & kCpadL) {
        t |= daPy_lk_c::BTN_L;  // CPad_CHECK_TRIG_L(0) -> BTN_L, ungated
    }
    return uint8_t(t);
}

std::vector<std::string> untranslatable_presses(const Json& golden, int first, int last) {
    std::vector<std::string> out;
    for (int f = first; f <= last; f++) {
        for (const Gated& g : kActionModeGated) {
            if (golden[size_t(f)]["btn_trig"].as_int() & g.bit) {
                char buf[32];
                std::snprintf(buf, sizeof buf, "%d:%s", f, g.name);
                out.push_back(buf);
            }
        }
    }
    return out;
}

ReplayResult run_roll_replay(const Json& golden, const RollReplayOptions& opt) {
    // In place of JMANewSinTable(12) (m_Do_machine.cpp:614): the console's table, which the
    // decomp's builder does not reproduce.
    JMA_useConsoleSinTable();

    // Kaisen r0, the capture's room: its `floor_tri` column names a kaisen_r0_bgd.json triangle
    // containing the row's position on all 120 rows, and is compared per frame.
    Rig rig("kaisen_r0_bgd.json");
    daPy_lk_c& lk = rig.lk;
    ReplayResult res;

    // The seed: the capture's frame-42 state (the frame before the roll), as bits.
    const Json& seed = golden[size_t(kSeedFrame)];
    lk.speedF = seed["true_speed"].as_f32();
    lk.mStickDistance = seed["msd"].as_f32();
    lk.shape_angle.y = (s16)seed["shape_angle_y"].as_int();
    lk.current.angle.y = lk.shape_angle.y;
    // Position seeded once, then computed; `old.pos` matches, as the actor manager's
    // `old = current` would have left it.
    lk.current.pos.x = seed["pos_x"].as_f32();
    lk.current.pos.y = seed["pos_y"].as_f32();
    lk.current.pos.z = seed["pos_z"].as_f32();
    lk.old.pos = lk.current.pos;
    // The one posMoveFromFootPos input the capture has no column for (see foot_seed).
    lk.m359C = opt.foot_seed;

    // The A press is acted on at capture frame 43; that row is the state after procFrontRoll_init.
    lk.procFrontRoll_init(lk.m_HIO->mRoll.m.mAnmStartFrame);  // d_a_player_main.cpp 4311

    WrongAnimClock wrong;
    wrong.reset(lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].getFrame());
    AccumulatedMove1 acc1;

    // execute():11400-11406 - posMove, `mOldSpeed = speed`, then the collision pass. Also runs on
    // the entry frame, after the init.
    Room::FrameResult last_frame{};
    auto integrate = [&]() {
        if (!opt.no_pos_move) {
            pos_move(lk);
        }
        if (!opt.no_crr_pos) {
            last_frame = crr_pos(rig);
            if (last_frame.wall_hit) {
                res.wall_hit_frames++;
            }
            if (last_frame.ran_line_check) {
                res.line_check_frames++;
            }
        }
        // execute()'s tail (:11544, :11591), after the collision pass. The next frame's
        // posMoveFromFootPos reads the joint matrices this writes.
        if (!opt.no_pose) {
            rig.poseSkeleton();
        }
    };
    integrate();

    auto emit = [&](int frame) {
        const J3DFrameCtrl& c0 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e];
        const J3DFrameCtrl& c1 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE1_e];
        ReplayFrame r;
        r.pos_x_bits = f32_bits(lk.current.pos.x);
        r.pos_y_bits = f32_bits(lk.current.pos.y);
        r.pos_z_bits = f32_bits(lk.current.pos.z);
        r.ground_poly = last_frame.ground_poly;
        r.ground_hit = last_frame.ground_hit;
        r.wall_hit = last_frame.wall_hit;
        r.line_hit = last_frame.line_hit;
        r.frame = frame;
        r.proc = lk.mCurProc;
        r.nspeed_bits = f32_bits(lk.mNormalSpeed);
        r.anim_bits = f32_bits(c0.getFrame());
        r.rate_bits = f32_bits(c0.getRate());
        r.end = (int)c0.getEnd();
        r.m1frame_bits = f32_bits(c1.getFrame());
        r.m1rate_bits = f32_bits(c1.getRate());
        r.m1end = (int)c1.getEnd();
        r.blend_bits = f32_bits(lk.m3598);
        r.foot_delta_bits = f32_bits(lk.m359C);
        r.plant = (int)lk.m34BC;
        r.crashed = lk.crash_called != 0;
        r.anm_meta_missing = lk.anm_meta_missing;
        res.rows.push_back(r);
    };
    emit(kFirstFrame);

    const int last = opt.through < int(golden.size()) - 1 ? opt.through : int(golden.size()) - 1;
    for (int i = kFirstFrame + 1; i <= last; i++) {
        const Json& r = golden[size_t(i)];
        // The pad row frame i consumed: the capture's pad columns lead by `pad_lead` (kPadLead).
        const int pi = i - opt.pad_lead;
        const Json& p = golden[size_t(pi)];

        // f_op_actor.cpp:196, before frame_top.
        if (!opt.stale_old_pos) {
            actor_old_set(lk);
        }
        frame_top(lk);  // before the inputs: it carries m34DC forward into m34EA
        lk.speedF = r["true_speed"].as_f32();
        lk.mStickDistance = r["msd"].as_f32();
        lk.m34E8 = (s16)r["target_angle"].as_int();
        lk.m34DC = (s16)r["stick_angle_raw"].as_int();
        // lock_r / lock_l are the game's latches (cPadInfo +0x37 / +0x35), which mItemButton is
        // built from, not the digital button word.
        lk.mItemButton = (u8)(p["lock_r"].as_int() ? daPy_lk_c::BTN_R : 0);
        lk.mItemTrigger = item_trigger_for(golden, pi);
        lk.stub_attention_lock = p["lock_l"].as_int() ? TRUE : FALSE;

        // animeUpdate() (d_a_player_main.cpp:11346, 12881), before the proc. It skips MOVE1 when
        // mAnmRatioUnder[1] is NULL (a single anim); the capture's move1_frame is frozen at
        // 28.693286895751953 through the roll.
        if (!opt.wrong_order) {
            lk.animeUpdate();
        }
        if (opt.wrong_anim && lk.mCurProc == daPy_lk_c::daPyProc_FRONT_ROLL_e) {
            wrong.update(lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].getRate());
            lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE0_e].setFrame(wrong.get());
        }

        const int proc_before = lk.mCurProc;
        const f32 nspeed_before = lk.mNormalSpeed;
        const bool had_body = run_proc(lk);
        // The ordering twin's clocks advance after the proc, and only if it had a body.
        if (opt.wrong_order && had_body) {
            lk.animeUpdate();
        }
        if (!had_body) {
            // The console is in a proc the port does not have: stop and record which.
            res.stopped_on_proc = lk.mCurProc;
            break;
        }

        if (opt.wrong_decel && proc_before == daPy_lk_c::daPyProc_MOVE_e &&
            lk.mCurProc == daPy_lk_c::daPyProc_MOVE_e) {
            lk.mNormalSpeed = wrong_decel_speed(*lk.m_HIO, nspeed_before);
        }
        if (opt.wrong_move1 && lk.mCurProc != daPy_lk_c::daPyProc_FRONT_ROLL_e) {
            J3DFrameCtrl& c1 = lk.mFrameCtrlUnder[daPy_lk_c::UNDER_MOVE1_e];
            acc1.arm(c1.getFrame());
            c1.setFrame(acc1.frame);
            acc1.step(c1.getRate());
        }
        if (opt.wrong_blend) {
            lk.m3598 = lk.mAnmRatioUnder[daPy_lk_c::UNDER_MOVE1_e].getRatio();
        }
        integrate();
        emit(i);
    }

    res.unreached_called = lk.unreached_called;
    res.precondition_broken = lk.precondition_broken;
    res.next_init_calls = lk.next_init_calls;
    res.button_dispatch_fellthrough = lk.button_dispatch_fellthrough;
    res.anm_resource_loads = lk.anm_resource_loads;
    return res;
}

}  // namespace testing
}  // namespace tww_engine
