#include "player_rig.h"

#include "framework/golden.h"
#include "room_dzb.h"

namespace tww_engine {
namespace testing {

namespace {

/// A `*_bgd.json` golden as `Session`'s tables, or null for no room. A `unique_ptr` parameter
/// outlives the constructor's base initialiser, which takes a `const RoomDzb*`.
std::unique_ptr<RoomDzb> load_room(const char* room_golden) {
    if (room_golden == NULL) {
        return NULL;
    }
    return std::unique_ptr<RoomDzb>(new RoomDzb(read_room_dzb(golden(room_golden))));
}

}  // namespace

// `Room` copies the tables, so they may die with the parameter.
Rig::Rig(std::unique_ptr<RoomDzb> dzb) : Session(dzb.get()) {}

Rig::Rig() : Rig(std::unique_ptr<RoomDzb>()) {}

Rig::Rig(const std::string& room_golden) : Rig(load_room(room_golden.c_str())) {}

Rig::Rig(const char* room_golden) : Rig(load_room(room_golden)) {}

}  // namespace testing
}  // namespace tww_engine
