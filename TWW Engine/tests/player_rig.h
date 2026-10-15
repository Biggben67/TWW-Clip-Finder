// player_rig.h - the test suite's front to `engine/session.h`.
//
// The player, world, frame stages and the one switch on `mCurProc` live in `engine/session.h`.
// What stays here is reading a room by golden name (a `*_bgd.json` in the manifest): the engine
// has no file format (`engine/room.h`). The captures' `floor_tri` column indexes the disc's
// triangle table, so a rig pointed at the wrong room disagrees on the first frame.
//
// The names below are re-exported into `tww_engine::testing` so the cases keep calling them as
// before.

#ifndef TWW_ENGINE_TESTS_PLAYER_RIG_H
#define TWW_ENGINE_TESTS_PLAYER_RIG_H

#include <string>

#include "engine/session.h"

namespace tww_engine {
namespace testing {

using tww_engine::f32_bits;

// The frame's stages, from the library; not second copies.
using tww_engine::actor_old_set;
using tww_engine::frame_top;
using tww_engine::pos_move;
using tww_engine::run_proc;
using tww_engine::stick_accumulate;

/// A `Session` that can be pointed at a room by the golden's name.
struct Rig : public Session {
    /// No room: the empty world.
    Rig();
    /// With one, read out of the manifest's `*_bgd.json`.
    explicit Rig(const std::string& room_golden);
    /// Either, from one expression: NULL is the room-less shape. A Rig must never be built as a
    /// temporary and moved, because the base constructor registers `&lk` in a global.
    explicit Rig(const char* room_golden);

  private:
    /// What all three delegate to. The tables arrive as a parameter, alive for the whole
    /// constructor (see player_rig.cpp).
    explicit Rig(std::unique_ptr<RoomDzb> dzb);
};

/// `Session::crr_pos()` at the name and the shape the cases call it by.
inline Room::FrameResult crr_pos(Rig& rig) {
    return rig.crr_pos();
}

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_PLAYER_RIG_H
