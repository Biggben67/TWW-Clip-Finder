// room_dzb.h - a banked `*_bgd.json` fixture becomes the cBgD_t tables cBgW::Set is handed.
// The engine has no file format; this is the one place in the suite that reads one.

#ifndef TWW_ENGINE_TESTS_ROOM_DZB_H
#define TWW_ENGINE_TESTS_ROOM_DZB_H

#include "engine/room.h"
#include "framework/json.h"

namespace tww_engine {
namespace testing {

/// The disc fixture's tables, as cBgD_t holds them.
RoomDzb read_room_dzb(const Json& g);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_ROOM_DZB_H
