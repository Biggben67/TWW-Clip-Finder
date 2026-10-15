// recorded_list.h - the ground check's candidates as a capture recorded them: the control for
// test_ground_walk.cpp's descent.
//
// Both sides run the same copied decision code (RwgGroundCheckGnd, RwgGroundCheckWall,
// RwgGroundCheckCommon, cM3d_CrossY_Tri_Front) over different candidate sources, so a difference
// in the answer is a difference in the candidate set. It is also the unmutated baseline for the
// walk's table-mutation controls. The recording is an input, not an oracle.
//
// The chains are split by cBgW_CheckBGround (ny >= 0.5f), as cBgW::ClassifyPlane splits them,
// each in capture order. The per-leaf interleaving is not recoverable from a flattened capture
// and reaches no answer: order is visible only through RwgGroundCheckCommon's strict
// `y > mNowY`, an exact-height tie.

#ifndef TWW_ENGINE_TESTS_RECORDED_LIST_H
#define TWW_ENGINE_TESTS_RECORDED_LIST_H

#include <vector>

#include "SSystem/SComponent/c_bg_s_gnd_chk.h"
#include "SSystem/SComponent/c_bg_w.h"

namespace tww_engine {
namespace testing {

/// One candidate polygon as a floors golden banks it: the game's poly index, its three
/// world-space vertices, and the plane the game stored.
struct RecordedPoly {
    int poly;
    Vec v[3];
    cXyz n;
    f32 d;
};

/// The recorded candidate list, in the layout cBgW's chain walk reads. Owns its tables; the
/// cBgW's pointers are into them.
class RecordedList {
  public:
    explicit RecordedList(const std::vector<RecordedPoly>& polys);

    /// cBgS::GroundCross minus the loop over collision objects and minus the descent. The
    /// prologue is the decomp's: mNowY = -G_CM3D_F_INF, poly info cleared, and the two precheck
    /// words from mFlag's low bits (3, from cBgS_GndChk's constructor).
    ///
    /// `probe` is already raised by dBgS_Acch::GroundCheck's `m_ground_check_offset -
    /// m_ground_up_h` (60.0f and 0.0f, d_bg_s_acch.cpp:59-60, :128).
    ///
    /// Returns the ground height and writes the poly index the game records in
    /// dBgS_LinkAcch+0x554 (0xFFFF when nothing was found).
    ///
    /// No pass-check is pushed: ChkPolyThrough and ChkGrpThrough are cBgW's `return false`, not
    /// dBgW's overrides. Exact on kaze r11 and GanonA r0, which carry neither bit; not on sea r41.
    f32 GroundCross(const cXyz& probe, int* out_poly);

    /// The candidate count, split the way ClassifyPlane splits it.
    int ground_count() const { return m_ground_count; }
    int wall_count() const { return m_wall_count; }

  private:
    std::vector<cBgD_Vtx_t> m_vtx;
    std::vector<cBgD_Tri_t> m_tri_tbl;
    std::vector<cBgW_TriElm> m_tri;
    std::vector<cBgW_RwgElm> m_rwg;
    cBgD_t m_bgd;
    cBgW m_bgw;
    u16 m_ground_head;
    u16 m_wall_head;
    int m_ground_count;
    int m_wall_count;
};

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_RECORDED_LIST_H
