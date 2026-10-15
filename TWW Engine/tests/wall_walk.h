// wall_walk.h - an editable copy of the wall pass (dBgW::WallCorrectGrpRp -> WallCorrectRp ->
// RwgWallCorrect), so a hypothesis can be tried without editing the ported bodies.
//
// It drives a real dBgS_LinkAcch set up as Room::WallCorrect sets one up, because the pass
// writes: every accepted polygon moves Link and CalcMovePosWork rebuilds the circle, segment and
// bounding cylinder. `the_wall_variant_harness_is_the_ported_walk` holds WallVariant::None
// bit-identical to Room::WallCorrect over the probe set, which is what makes a variant's count a
// statement about the port.
//
// The trace records every accepted correction in order, so two engines' chains can be compared
// at the step they first differ rather than at the last polygon.
//
// Four variants are the old sim's spellings; the differential's oracle is its
// `acch_wall_correct`, not its `wall_correct`:
//   LegacyIsZero     `wall_correct`'s is_zero at 1.0e-5 (console: 2^-18) at every cM3d_IsZero;
//                    an upper bound on the threshold's reach, not an attribution.
//   LibrarySqrt      `wall_correct`'s correctly rounded sqrt (`acch_wall_correct` uses the
//                    console's sqrtf_c); likewise a bound.
//   SegIsZeroLegacy  the one 1.0e-5 test the oracle does use: its segment squared-length test.
//   SegAssignsStart  the old sim returns the segment start as the closest point; the decomp
//                    assigns nothing and RwgWallCorrect reads the locals anyway. The
//                    counterfactual for `degenerate_reads`.

#ifndef TWW_ENGINE_TESTS_WALL_WALK_H
#define TWW_ENGINE_TESTS_WALL_WALK_H

#include <vector>

#include "engine/room.h"

namespace tww_engine {
namespace testing {

enum class WallVariant {
    None,          //: the ported path, unchanged - the only value the gate allows
    LegacyIsZero,  //: 1.0e-5f wherever this pass calls cM3d_IsZero - the old sim's threshold
    LibrarySqrt,   //: std::sqrt in place of ppc::sqrtf_msl, in both arms - the old sim's root
    NoRebuild,     //: CalcMovePosWork not called after a correction, so the circle, the segment
                   //  and the octree's bounding cylinder stay where the frame began
    WallChainOnly,  //: a leaf's roof chain not walked (d_bg_w.cpp:272) - right everywhere except
                    //  under an overhang
    RoofFirst,      //: the roof chain walked before the wall chain; order changes answers here
    ChildrenReversed,  //: mChild[7..0] instead of [0..7]
    NearEndOnly,       //: the corner arm always takes the first endpoint, dropping the
                       //  `spE0 < spE4` choice of which corner is nearer
    SegIsZeroLegacy,   //: 1.0e-5f at cM3d_Len2dSqPntAndSegLine's `dot` test alone - the
                       //  differential oracle's spelling
    SegAssignsStart,   //: that arm assigns the closest point to (x0, y0) instead of leaving it -
                       //  the old sim's behaviour
};

/// One accepted correction, in the order the walk accepted it.
struct WallStep {
    int poly;
    int cyl;
    /// 's' the flat-wall arm (positionWallCorrect), '0' the nearer endpoint's corner arm,
    /// '1' the farther endpoint's. The three are different corrections, not three spellings.
    char arm;
    u32 x_bits;
    u32 z_bits;
};

/// The editable wall pass. One instance per (room, variant); `run` is re-entrant across calls.
class WallWalk {
  public:
    WallWalk(Room& room, WallVariant var) : m_w(room.bgw()), m_var(var) {}

    /// `Room::WallCorrect`'s signature minus `who` (the gate compares against the Link arm only);
    /// `latch` included, so degenerate reads are counted against this frame's own line check.
    bool run(cXyz* pos, const cXyz& old_pos, f32 speed_y, const Room::WallCyl* cyls, int tbl_size,
             Room::WallResult* out, const Room::LineResult* latch = nullptr);

    /// Record every accepted correction into `sink` (cleared at the start of each `run`), or stop
    /// recording when it is null.
    void TraceTo(std::vector<WallStep>* sink) { m_trace = sink; }

    /// cM2d_CrossCirLin's two arms that read `t` uninitialised, counted at the call site
    /// (counting inside the ported body would be an edit). Cumulative; `ResetCounts` clears them.
    long long cross_cir_lin_calls() const { return m_ccl_calls; }
    long long cross_cir_lin_unassigned() const { return m_ccl_unassigned; }
    /// Of the assigned calls, the two arms that do assign (the quadratic's roots and the
    /// degenerate-direction arm): the population beside `unassigned`.
    long long cross_cir_lin_quadratic() const { return m_ccl_quadratic; }
    /// JUT_ASSERTs the decomp makes that this run's variant broke. On the ported path the copied
    /// assert aborts as the game's does; a variant counts instead, since a control that ends the
    /// process reports nothing.
    long long broken_asserts() const { return m_asserts; }

    /// (polygon, cylinder) pairs of the last run that reached cM3d_Len2dSqPntAndSegLine's
    /// degenerate early return (closest point unassigned) and let those locals decide through
    /// RwgWallCorrect's facing test. Cleared per run.
    int degenerate_reads() const { return m_degenerate; }

    /// Square roots taken, and how many the correctly rounded root would answer differently, so
    /// `LibrarySqrt` changing nothing can be told apart from an unwired knob.
    long long root_calls() const { return m_root_calls; }
    long long root_differs() const { return m_root_differs; }
    void ResetCounts() {
        m_ccl_calls = m_ccl_unassigned = m_ccl_quadratic = m_asserts = 0;
        m_root_calls = m_root_differs = 0;
    }

  private:
    bool grp_rp(dBgS_Acch* acch, int grp_id, int depth);
    bool rp(dBgS_Acch* acch, int i);
    bool rwg(dBgS_Acch* acch, u16 poly_index);
    void position_wall_correct(dBgS_Acch* acch, f32 dist, cM3dGPla& plane, cXyz* upper_pos,
                               f32 speed);
    void cross_cir_lin(cM2dGCir& circle, f32 x0, f32 y0, f32 x1, f32 y1, f32* dst_x, f32* dst_y);
    bool len2dsq_pnt_seg(f32 xp, f32 yp, f32 x0, f32 y0, f32 x1, f32 y1, f32* outx, f32* outy,
                         f32* seg);

    bool is_zero(f32 v) const;
    bool seg_is_zero(f32 v) const;
    f32 root(f32 v);
    void step(int poly, int cyl, char arm, const cXyz* pos);

    cBgW& m_w;
    WallVariant m_var;
    std::vector<WallStep>* m_trace = nullptr;
    long long m_ccl_calls = 0;
    long long m_ccl_unassigned = 0;
    long long m_ccl_quadratic = 0;
    long long m_asserts = 0;
    int m_degenerate = 0;
    long long m_root_calls = 0;
    long long m_root_differs = 0;
};

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_WALL_WALK_H
