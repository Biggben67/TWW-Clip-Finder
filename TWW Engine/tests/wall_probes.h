// wall_probes.h - the positions every wall gate asks about, derived from the room's own tables.
// Shared by test_wall_correct.cpp and test_wall_walk.cpp.
//
// A wall probe is a position where Link's cylinder overlaps the polygon:
//
//   height   `sp7C` is `pos.y + wall_h - speed_y`, so `pos.y` puts the middle cylinder's cut at
//            the polygon's centroid height.
//   side     the pass skips a Link the normal does not point at
//            (`spD4 * sp50.x + spD8 * sp50.z < 0.0f -> continue`), so probes are on the +normal
//            side.
//   depth    inside the radius; three depths and one control past it.
//
// Polygons are kept down to RwgWallCorrect's own `cM3d_IsZero(sp68)` guard rather than the
// differential's |n_xz| < 1.0e-3 cut, so this set is a superset (`extra_flat` counts the extra).
// That band is exactly what reaches cM2d_CrossCirLin's unassigned arm. |n_xz| is the f32 sum
// through the console's sqrt, as `sp68` is computed.

#ifndef TWW_ENGINE_TESTS_WALL_PROBES_H
#define TWW_ENGINE_TESTS_WALL_PROBES_H

#include <string>
#include <vector>

#include "engine/room.h"

namespace tww_engine {
namespace testing {

//: `daPy_lk_c::setBgCheckParam` (d_a_player_main.cpp:10680) + `create` (:12204) - Link's three
//: wall cylinders in the normal ground state.
extern const f32 kWallH[3];
extern const f32 kWallR;
//: `mAutoJump.field_0xC` - the grounded per-frame speed.y at CrrPos time, which RwgWallCorrect
//: subtracts from each cylinder's cut height.
extern const f32 kWallSpeedY;

/// One derived position and what it was derived from.
struct WallProbe {
    cXyz pos;
    int of_poly;
    /// "face_deep" ... "face_outside", "corner_deep", "corner_shallow".
    const char* cls;
};

/// Every polygon on a block's wall or roof chain, which dBgW::WallCorrectRp visits at a leaf
/// (d_bg_w.cpp:270, 272). Walks no tree.
std::vector<int> wall_and_roof_chain_polys(const Room& room);

/// The probe set for one room, deduplicated by (x, y, z) bits; the first class to name a point
/// keeps it.
/// `extra_flat` receives the count of polygons with |n_xz| between G_CM3D_F_ABS_MIN and 1.0e-3.
std::vector<WallProbe> wall_probe_set(const Room& room, const RoomDzb& dzb,
                                      int* extra_flat = nullptr);

/// The face probe for one polygon at one depth. False for a polygon with no XZ direction (a floor
/// or ceiling), which RwgWallCorrect drops on `cM3d_IsZero(sp68)`.
bool wall_face_probe(const Room& room, const RoomDzb& dzb, int poly, f32 mid_h, f32 depth,
                     cXyz* out, f32* out_ux = nullptr, f32* out_uz = nullptr);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_WALL_PROBES_H
