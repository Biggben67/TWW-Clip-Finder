// line_walk.h - an editable copy of the line check, and the probe set every line gate asks about.
//
// `cBgW::LineCheckGrpRp` -> `LineCheckRp` -> `RwgLineCheck` are extracted bodies, so hypotheses
// are tried on this copy, held bit-identical to them by
// `the_line_variant_harness_is_the_ported_walk`.
//
// Every accepted crossing calls `chk->GetLinP()->SetEnd(pt)`, shortening the segment the rest of
// the walk tests against; that yields the nearest crossing without sorting, and tightens the
// octree's `cM3d_Cross_MinMaxBoxLine` prune as the walk proceeds.
//
// Whether a crossing is found is order-independent, so `Flat` is the prune's counterfactual.
// Where it lands is not: each acceptance re-anchors the next interpolation.
//
// A probe is a segment crossing a polygon's plane front-to-back: the acch runs
// `cM3d_Cross_LinPla` front-only (cBgS_LinChk::ct sets mFrontFlag, clears mBackFlag), so every
// probe starts on the +normal side, and `stops_short` ends before the plane.

#ifndef TWW_ENGINE_TESTS_LINE_WALK_H
#define TWW_ENGINE_TESTS_LINE_WALK_H

#include <string>
#include <vector>

#include "engine/room.h"

namespace tww_engine {
namespace testing {

enum class LineVariant {
    None,   //: the ported path, unchanged - the only value the bit-identity gate allows
    Flat,   //: the group's aab and the node's min/max box tests removed, nothing else, so the
            //  same DFS (and ChkGrpThrough) visits every leaf
    NoShrink,       //: an accepted crossing does not shorten the segment, so the last polygon
                    //  offered wins instead of the nearest
    TwoSided,       //: mBackFlag on, so a polygon crossed from behind is a hit too
    NoWallChain,    //: a leaf's wall chain not walked (c_bg_w.cpp:415)
    NoGroundChain,  //: a leaf's ground chain not walked (c_bg_w.cpp:417)
    NoRoofChain,    //: a leaf's roof chain not walked (c_bg_w.cpp:419)
    ChildrenReversed,  //: mChild[7..0] instead of [0..7]
    LegacyIsZero,   //: 1.0e-5f wherever this pass calls cM3d_IsZero - the old sim's threshold
    AxisIsZeroGate,  //: cM3d_Cross_LinTri's three 0.008f guards replaced by cM3d_IsZero, which
                     //  is 2,097 times smaller, so a nearly edge-on polygon takes that
                     //  projection's test instead of skipping it
};

/// One accepted crossing, in the order the walk accepted it.
struct LineStep {
    int poly;
    int cyl;
    u32 x_bits;
    u32 y_bits;
    u32 z_bits;
};

/// One polygon handed to the per-polygon test, in descent order. `Room::LogVisitedPolys` sits on
/// `dBgW::ChkPolyThrough`, reached only after `cM3d_Cross_LinTri` accepts, so it logs only
/// crossings.
struct LineOffer {
    int poly;
    int cyl;
    /// `cM3d_Cross_LinTri` accepted it.
    bool crossed;
    /// ...and then `dBgW::ChkPolyThrough` refused it (the second half of the same `&&`). The old
    /// sim has no dBgW and would take the crossing, so the list carries it.
    bool refused;
};

/// The editable line check. One instance per (room, variant).
class LineWalk {
  public:
    LineWalk(Room& room, LineVariant var) : m_room(room), m_w(room.bgw()), m_var(var) {}

    /// `Room::LineCheck`'s signature minus `who`; the gate compares against the Link arm.
    bool run(cXyz* pos, const cXyz& old_pos, const Room::WallCyl* cyls, int tbl_size,
             Room::LineResult* out);

    /// Record every accepted crossing into `sink` (cleared at the start of each `run`), or stop
    /// recording when it is null.
    void TraceTo(std::vector<LineStep>* sink) { m_trace = sink; }

    /// Record every offered polygon into `sink` (cleared per run, not per cylinder: a `LineOffer`
    /// names its cylinder), or stop when it is null.
    void OfferTo(std::vector<LineOffer>* sink) { m_offers = sink; }

    /// Polygons offered to the per-polygon test (all chains under `Flat`). Cumulative.
    long long offered() const { return m_offered; }
    /// How many of those crossed.
    long long crossed() const { return m_crossed; }
    /// Polygons accepted on the plane and refused by a projected triangle test.
    long long plane_only() const { return m_plane_only; }
    /// cM3d_Cross_LinPla calls whose two plane values were IsZero-apart (the refusing arm).
    long long lin_pla_degenerate() const { return m_lin_pla_degenerate; }
    void ResetCounts() {
        m_offered = m_crossed = m_plane_only = m_lin_pla_degenerate = 0;
    }

  private:
    bool line_cross(cBgS_LinChk* chk);
    bool grp_rp(cBgS_LinChk* chk, int grp_id, int depth);
    bool rp(cBgS_LinChk* chk, int i);
    bool rwg(u16 poly_index, cBgS_LinChk* chk);
    bool cross_lin_tri(const cM3dGLin* lin, const cM3dGTri* tri, Vec* dst, bool front, bool back);
    bool cross_lin_pla(const cM3dGLin* lin, const cM3dGPla* pla, Vec* dst, bool front, bool back);
    bool is_zero(f32 v) const;
    bool axis_gate(f32 n) const;
    void step(int poly, int cyl, const cXyz* pos);
    void offer(int poly, bool crossed, bool refused);

    Room& m_room;
    cBgW& m_w;
    LineVariant m_var;
    int m_cyl = 0;
    cXyz m_last_pt;
    bool m_last_pt_valid = false;
    std::vector<LineStep>* m_trace = nullptr;
    std::vector<LineOffer>* m_offers = nullptr;
    long long m_offered = 0;
    long long m_crossed = 0;
    long long m_plane_only = 0;
    long long m_lin_pla_degenerate = 0;
};

//: Link's three wall cylinders and radius (`daPy_lk_c::setBgCheckParam`), as in wall_probes.h.
extern const f32 kLineWallH[3];
extern const f32 kLineWallR;

/// One derived segment and what it was derived from.
struct LineProbe {
    cXyz old_pos;
    cXyz pos;
    int of_poly;
    /// "cross_mid", "cross_short", "graze", "stops_short", "corner_cross".
    const char* cls;
};

/// The probe set for one room: for every polygon on a wall, ground or roof chain, segments aimed
/// through it along its normal, deduplicated by (old, new) bits.
/// `flat_dropped` receives the count of polygons with no usable normal; unlike the wall pass
/// there is no |n_xz| guard, since a floor can be crossed.
std::vector<LineProbe> line_probe_set(const Room& room, const RoomDzb& dzb,
                                      int* flat_dropped = nullptr);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_LINE_WALK_H
