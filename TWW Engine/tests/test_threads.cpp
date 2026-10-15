// test_threads.cpp - the port's game globals are per thread.
//
// Shared globals do not crash; they silently answer about another thread's run. So the check is
// an equality: N distinct scenarios run sequentially, then all N on their own threads at once,
// and every frame must be bit-identical. Contention comes from a registered floor
// (`cBgS::Regist`/`l_SetCounter`), the camera (pad block, `followCamera`'s memory), the pose
// (`mDoMtx_stack_c`, `J3DSys` statics) and many frames with the workers released together.
// The scenarios differ so that a value crossing between workers is visibly wrong.
//
// Not covered: two threads stepping the same Session, which the library does not offer.

#include "framework/runner.h"

#include "engine/session.h"

#include "boundary/game_boundary.h"
#include "d/actor/d_a_player_main.h"
#include "m_Do/m_Do_controller_pad.h"

#include <atomic>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

using tww_engine::testing::Case;

/// How many run at once; enough to make interleaving inside a frame likely.
const int kWorkers = 8;

/// Frames per worker: long enough for the acceleration ramp, proc dispatch and camera chase.
const int kFrames = 40;

/// What one frame is compared on. Not a memcmp of `daPy_lk_c`: it holds pointers into itself,
/// which differ between sessions describing the same player.
struct Frame {
    uint32_t pos_x, pos_y, pos_z;
    uint32_t old_x;
    uint32_t speed_f;
    uint32_t normal_speed;
    int shape_y;
    int travel_y;
    int proc;
    int camera_yaw;
};

/// One scenario; every field depends on `w` so no two workers run the same thing.
struct Scenario {
    int facing;
    float floor_y;
    int camera_yaw;
    int stick;
    float speed;
};

Scenario scenario(int w) {
    Scenario s;
    s.facing = (w * 0x1FE7) & 0xFFFF;
    s.floor_y = static_cast<float>(w) * 37.5f;
    s.camera_yaw = (0x4000 + w * 0x0911) & 0xFFFF;
    s.stick = (s.facing + w * 0x0400) & 0xFFFF;
    s.speed = 1.0f + static_cast<float>(w) * 0.75f;
    return s;
}

tww_engine::RunOptions options_for(const Scenario& s) {
    tww_engine::RunOptions opts;
    // A floor so something registers and the slot counter is exercised; no room fixture needed.
    opts.ground = tww_engine::RunOptions::Ground::Supplied;
    opts.floor_y = s.floor_y;
    // The camera is what reaches the pad block and followCamera's three words of memory.
    opts.camera = true;
    opts.camera_yaw = static_cast<s16>(s.camera_yaw);
    return opts;
}

tww_engine::Init init_for(const Scenario& s) {
    tww_engine::Init init;
    init.pos.set(209.62948608398438f, s.floor_y, 549.9795532226562f);
    init.shape_angle_y = static_cast<s16>(s.facing);
    init.travel_angle_y = static_cast<s16>(s.facing);
    init.pad.stick_angle_raw = static_cast<s16>(s.stick);
    init.pad.target_angle = static_cast<s16>(s.stick);
    init.pad.stick_distance = 1.0f;
    // Start in procMove (so `procMove_init` has run) rather than transitioning from wait.
    init.proc = daPy_lk_c::daPyProc_MOVE_e;
    init.normal_speed = s.speed;
    init.speed_f = s.speed;
    return init;
}

/// Run one scenario and record every frame. The pad block is per thread, so it is zeroed here,
/// on the running thread.
std::vector<Frame> run(const Scenario& s) {
    std::memset(&g_mDoCPd_cpadInfo[0], 0, sizeof(g_mDoCPd_cpadInfo));

    tww_engine::Session session(init_for(s), NULL, options_for(s));

    tww_engine::Pad pad;
    pad.stick_angle_raw = static_cast<s16>(s.stick);
    pad.target_angle = static_cast<s16>(s.stick);
    pad.stick_distance = 1.0f;

    std::vector<Frame> out;
    out.reserve(kFrames);
    for (int f = 0; f < kFrames; f++) {
        session.step(pad);
        const daPy_lk_c& lk = session.state();
        Frame fr;
        fr.pos_x = tww_engine::f32_bits(lk.current.pos.x);
        fr.pos_y = tww_engine::f32_bits(lk.current.pos.y);
        fr.pos_z = tww_engine::f32_bits(lk.current.pos.z);
        fr.old_x = tww_engine::f32_bits(lk.old.pos.x);
        fr.speed_f = tww_engine::f32_bits(lk.speedF);
        fr.normal_speed = tww_engine::f32_bits(lk.mNormalSpeed);
        fr.shape_y = lk.shape_angle.y;
        fr.travel_y = lk.current.angle.y;
        fr.proc = lk.mCurProc;
        fr.camera_yaw = session.cameraYaw() & 0xFFFF;
        out.push_back(fr);
    }
    return out;
}

void compare(Case& c, int w, const std::vector<Frame>& want, const std::vector<Frame>& got) {
    const std::string who = "worker " + std::to_string(w) + " ";
    REQUIRE_INT(c, static_cast<long long>(got.size()), static_cast<long long>(want.size()),
                who + "frame count");
    const size_t n = want.size() < got.size() ? want.size() : got.size();
    for (size_t f = 0; f < n; f++) {
        const std::string at = who + "frame " + std::to_string(f) + ": ";
        REQUIRE_BITS_RAW(c, got[f].pos_x, want[f].pos_x, at + "current.pos.x");
        REQUIRE_BITS_RAW(c, got[f].pos_y, want[f].pos_y, at + "current.pos.y");
        REQUIRE_BITS_RAW(c, got[f].pos_z, want[f].pos_z, at + "current.pos.z");
        REQUIRE_BITS_RAW(c, got[f].old_x, want[f].old_x, at + "old.pos.x");
        REQUIRE_BITS_RAW(c, got[f].speed_f, want[f].speed_f, at + "speedF");
        REQUIRE_BITS_RAW(c, got[f].normal_speed, want[f].normal_speed, at + "mNormalSpeed");
        REQUIRE_INT(c, got[f].shape_y, want[f].shape_y, at + "shape_angle.y");
        REQUIRE_INT(c, got[f].travel_y, want[f].travel_y, at + "current.angle.y");
        REQUIRE_INT(c, got[f].proc, want[f].proc, at + "mCurProc");
        REQUIRE_INT(c, got[f].camera_yaw, want[f].camera_yaw, at + "cameraYaw");
    }
}

}  // namespace

TWWE_TEST(eight_sessions_stepped_at_once_answer_what_they_answer_one_at_a_time,
          "every piece of state the port holds in a global because the game has one player - the "
          "live player pointer, the collision world, the registry's slot counter, followCamera's "
          "memory of its last frame, the pad block - is per thread. Shared, a threaded run still "
          "answers, off somebody else's player, with no fault and nothing in the process able to "
          "say so, and this equality is the only thing that can") {
    std::vector<std::vector<Frame> > want(kWorkers);
    for (int w = 0; w < kWorkers; w++) {
        want[w] = run(scenario(w));
    }

    // Released together by a spin, so the workers' frames overlap rather than run in start order.
    std::vector<std::vector<Frame> > got(kWorkers);
    std::atomic<int> ready(0);
    std::atomic<bool> go(false);
    std::vector<std::thread> pool;
    pool.reserve(kWorkers);
    for (int w = 0; w < kWorkers; w++) {
        pool.push_back(std::thread([w, &got, &ready, &go]() {
            ready.fetch_add(1);
            while (!go.load()) {
            }
            got[w] = run(scenario(w));
        }));
    }
    while (ready.load() < kWorkers) {
    }
    go.store(true);
    for (int w = 0; w < kWorkers; w++) {
        pool[w].join();
    }

    for (int w = 0; w < kWorkers; w++) {
        compare(c, w, want[w], got[w]);
    }
    c.note("workers: " + std::to_string(kWorkers) + ", frames each: " + std::to_string(kFrames));
}

TWWE_TEST(a_worker_binds_its_own_player_and_cannot_unbind_anybody_elses,
          "`Session::bind` writes the two globals a copied body reads by name, and its destructor "
          "clears them. Shared, a Session going out of scope on one thread leaves every other "
          "thread's stubs reading a null - which answers, quietly, with the stub's own default. "
          "This drives that exact shape: short-lived sessions churning beside a long-lived one") {
    const Scenario s = scenario(3);
    const std::vector<Frame> want = run(s);

    std::atomic<bool> stop(false);
    std::vector<std::thread> churn;
    churn.reserve(4);
    for (int w = 0; w < 4; w++) {
        churn.push_back(std::thread([w, &stop]() {
            while (!stop.load()) {
                // Continuous bind/unbind churn while the long run below steps.
                tww_engine::Session t(init_for(scenario(w + 4)), NULL, options_for(scenario(w + 4)));
                t.step(tww_engine::Pad());
            }
        }));
    }

    const std::vector<Frame> got = run(s);
    stop.store(true);
    for (size_t w = 0; w < churn.size(); w++) {
        churn[w].join();
    }

    compare(c, 3, want, got);
}

TWWE_TEST(the_session_count_is_the_whole_process_and_survives_being_counted_from_eight_threads,
          "`Session::built` is the one counter here that stays process-wide, because what it is "
          "for is a claim about the process - the finder's walk saying nothing in it touches this "
          "library. Per thread it would pass for free the day that walk moved onto workers, and a "
          "plain ++ from eight threads loses increments without saying it did") {
    const unsigned long long before = tww_engine::Session::built();

    const int per_worker = 50;
    std::vector<std::thread> pool;
    pool.reserve(kWorkers);
    for (int w = 0; w < kWorkers; w++) {
        pool.push_back(std::thread([w, per_worker]() {
            for (int i = 0; i < per_worker; i++) {
                tww_engine::Session t(NULL, tww_engine::RunOptions());
                (void)t;
            }
        }));
    }
    for (int w = 0; w < kWorkers; w++) {
        pool[w].join();
    }

    const unsigned long long after = tww_engine::Session::built();
    REQUIRE_INT(c, static_cast<long long>(after - before),
                static_cast<long long>(kWorkers * per_worker),
                "sessions built across eight threads");
}
