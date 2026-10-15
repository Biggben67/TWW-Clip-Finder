// room.h - a room's collision as dBgW holds it, built from the .dzb the disc ships.
//
// dBgW rather than cBgW because dBgW's ChkPolyThrough / ChkGrpThrough overrides read the
// attribute tables (m_ti_tbl via m_t_tbl[poly].id, m_g_tbl[grp].m_info) and can refuse polygons
// and groups; cBgW's return false.
//
// What stands in for the game:
//
//   cBgW::Set      the five tables (pm_tri, pm_rwg, pm_blk, m_nt_tbl, pm_grp) come from
//                  std::vector instead of the game heap, and mMoveCounter is not seeded from
//                  cM_rndF. Set's tail - ClassifyPlane(), mbNeedsFullTransform = true,
//                  MakeNodeTree() - runs from the copied bodies.
//   cBgW::SetVtx   a room is GLOBAL_e and not a moving BG, so `pm_vtx_tbl = pm_bgd->m_v_tbl`
//                  (c_bg_w.cpp:97): disc vertices are world vertices, untransformed.
//   dBgS::Regist   d_bg_s.cpp:51-62. The ChkMoveBg() arm is false for a room and is skipped;
//                  `cBgS::Regist(bgw, fopAcM_GetID(ac), ac)` is called directly with the given pid.
//
// mIgnorePlaneType is 0: a room ignores no plane type.

#ifndef TWW_ENGINE_ROOM_H
#define TWW_ENGINE_ROOM_H

#include <vector>

#include "SSystem/SComponent/c_bg_s_gnd_chk.h"
#include "SSystem/SComponent/c_bg_w.h"
#include "d/d_bg_s.h"
#include "d/d_bg_s_acch.h"
#include "d/d_bg_w.h"

namespace tww_engine {

/// The .dzb tables a room ships, as data; names are cBgD_t's fields. Reading a .dzb is the
/// caller's job: the engine has no file format.
struct RoomDzb {
    std::vector<cBgD_Vtx_t> v_tbl;
    std::vector<cBgD_Tri_t> t_tbl;
    std::vector<cBgD_Blk_t> b_tbl;
    std::vector<cBgD_Tree_t> tree_tbl;
    std::vector<cBgD_Grp_t> g_tbl;
    /// cBgD_t::m_ti_tbl - the attribute rows cBgD_Tri_t::id indexes.
    std::vector<cBgD_Ti_t> ti_tbl;
};

/// A world that is only a flat floor at `floor_y`, spanning +/-524288 (2^19, so vertices are
/// exact f32) in x and z. Two triangles, one block, a one-node tree, one group; no walls or
/// ceiling. A run that leaves it falls.
///
/// A floor is data rather than a supplied height because the ground response also reads the
/// polygon's plane and room id (d_bg_s_acch.cpp:158-172). The height comes back bit-exact;
/// `mNormal.y` is 1.00000012, as for any real flat polygon, because `cM3d_CalcPla` normalises
/// through the Gekko's `frsqrte` estimate plus one Newton step (engine/ps_vec.cpp).
RoomDzb flat_floor_dzb(f32 floor_y);

/// Who is asking; decides the pass-checks both overrides apply.
///
///   Link  dBgS_LinkAcch's: mbLinkThrough alone (d_bg_s_acch.h:256, pushed by
///         dBgS_Acch::GroundCheckInit's SetExtChk) and NORMAL_GRP alone (dBgS_GrpPassChk).
///   None  no pass-check: the decomp's `if (chk == NULL) return false` arm in both overrides.
enum class PassChk { Link, None };

/// The most wall cylinders one query can carry (Link uses three). WallCorrect refuses more.
const int kMaxWallCyl = 8;

/// A dBgW that records which polygons a walk asked `ChkPolyThrough` about, then delegates to
/// `dBgW::ChkPolyThrough`. What the log holds depends on the walk:
///
///   WallCorrect   every polygon the octree offered, in order (`RwgWallCorrect`, d_bg_w.cpp:110).
///   GroundCross   only those that passed `cM3d_CrossY_Tri` (c_bg_w.cpp:232).
///   RoofChk       the same as ground (d_bg_w.cpp:391).
class VisitLogBgW : public dBgW {
  public:
    /// Append into `sink` (never cleared here), or stop recording when null.
    void LogTo(std::vector<int>* sink) { m_sink = sink; }

    bool ChkPolyThrough(int poly_index, cBgS_PolyPassChk* chk) override {
        if (m_sink != nullptr) {
            m_sink->push_back(poly_index);
        }
        return dBgW::ChkPolyThrough(poly_index, chk);
    }

  private:
    std::vector<int>* m_sink = nullptr;
};

/// The pids a Room and Link register under. They must differ, or ChkSameActorPid would reject
/// the room as Link's own collision.
const fpc_ProcID kRoomPid = 0x1001;
const fpc_ProcID kLinkPid = 0x1002;

/// One room's dBgW, built and registered in its own dBgS. Owns its tables.
class Room {
  public:
    /// `owner_pid` is stored by cBgS::Regist and tested against each query's pid.
    explicit Room(const RoomDzb& dzb, fpc_ProcID owner_pid = kRoomPid);

    /// cBgS::GroundCross for a one-object world. `probe` is already raised: dBgS_Acch::GroundCheck
    /// adds `m_ground_check_offset - m_ground_up_h` (60.0f, 0.0f; d_bg_s_acch.cpp:59-60, :128)
    /// first. Returns the height and writes the poly index (dBgS_LinkAcch+0x554; 0xFFFF for none).
    f32 GroundCross(const cXyz& probe, int* out_poly, PassChk who = PassChk::Link);

    /// dBgS::RoofChk for a one-object world (d_bg_s.cpp:356-363). `probe` is Link's position,
    /// unraised (d_bg_s_acch.cpp:253). Returns the ceiling height, G_CM3D_F_INF for none, and
    /// writes the poly index (dBgS_RoofChk+0x00).
    f32 RoofChk(const cXyz& probe, int* out_poly, PassChk who = PassChk::Link);

    /// One wall cylinder as `dBgS_AcchCir` holds it: height above the position and radius. Link
    /// standing uses 30.1 / 89.9 / 125.0 at r 35; `daPy_lk_c::setBgCheckParam` picks them per proc.
    struct WallCyl {
        f32 h;
        f32 r;
    };

    /// What the wall pass left, per cylinder; procs read `mAcchCir[0]`, not the aggregate.
    struct WallResult {
        /// dBgS_Acch's WALL_HIT: any correction, including the corner arms.
        bool wall_hit;
        int tbl_size;
        bool cir_hit[kMaxWallCyl];
        /// cBgS_PolyInfo::mPolyIndex per cylinder; 0xFFFF where nothing corrected it.
        int cir_poly[kMaxWallCyl];
        /// cM_atan2s(n.x, n.z) of the correcting polygon - the s16 angle procWait snaps to.
        s16 cir_angle[kMaxWallCyl];
    };

    struct LineResult;

    /// dBgS::WallCorrect for a one-object world (d_bg_s.cpp:332-350). Moves `pos` in place;
    /// returns whether anything moved it.
    ///
    /// `old_pos` feeds SetLin. `speed_y` is the frame's vertical speed, subtracted from each
    /// cylinder's cut height (RwgWallCorrect's `sp7C`). `latch` is a line check run earlier in
    /// the same frame, whose SetWallHDirect heights replace the derived cut height; null means
    /// none ran. The surrounding line checks are not run - see CrrPos.
    bool WallCorrect(cXyz* pos, const cXyz& old_pos, f32 speed_y, const WallCyl* cyls,
                     int tbl_size, WallResult* out, PassChk who = PassChk::Link,
                     const LineResult* latch = nullptr);

    /// What the line check left, per cylinder.
    struct LineResult {
        /// dBgS_Acch's LINE_CHECK_HIT; CrrPos tests it to decide on a second pass.
        bool hit;
        int tbl_size;
        bool cir_hit[kMaxWallCyl];
        /// cBgS_LinChk::mPolyIndex of the nearest crossing; 0xFFFF where nothing crossed.
        int cir_poly[kMaxWallCyl];
        /// SetWallHDirect's latch: set when the crossing polygon's normal has an XZ part, and the
        /// height the wall pass then cuts at.
        bool whd_set[kMaxWallCyl];
        f32 whd[kMaxWallCyl];
        /// Cylinders that crossed a ground-classed polygon (ny >= 0.5f). Their `GroundCheck`
        /// re-run is not ported, so a non-zero count means the position is incomplete.
        int ground_branch;
    };

    /// dBgS_Acch::LineCheck for a one-object world (d_bg_s_acch.cpp:175-206). Moves `pos`: per
    /// cylinder in order, sweeps `old_pos` -> `pos` at that height, snaps to the nearest front
    /// crossing and pushes one unit along its normal. The ground arm's `GroundCheck(i_bgs)` is
    /// not run; see `LineResult::ground_branch`.
    bool LineCheck(cXyz* pos, const cXyz& old_pos, const WallCyl* cyls, int tbl_size,
                   LineResult* out, PassChk who = PassChk::Link);

    /// One frame of collision, read off the acch after CrrPos.
    struct FrameResult {
        /// LINE_CHECK_HIT, WALL_HIT, GROUND_HIT, GROUND_LANDING, GROUND_AWAY, ROOF_HIT,
        /// WATER_HIT, WATER_IN - each the acch's own bit, in the order CrrPos raises them.
        bool line_hit;
        bool wall_hit;
        bool ground_hit;
        bool ground_find;
        bool ground_landing;
        bool ground_away;
        bool roof_hit;
        bool water_hit;
        bool water_in;
        /// CrrPos's `ranLineCheck` local (d_bg_s_acch.cpp:227); not derivable from line_hit.
        bool ran_line_check;
        /// m_ground_h, m_roof_height, m_sea_height as CrrPos left them.
        f32 ground_h;
        /// The polygon m_gnd names after the ground stage, or 0xFFFF.
        int ground_poly;
        f32 roof_height;
        f32 sea_height;
        /// The per-cylinder wall answer, as WallCorrect reports it.
        WallResult wall;
    };

    /// A standalone Link acch, configured as d_a_player_main.cpp:12189-12193 does. Held across
    /// frames because CrrPos reads last frame's `m_gnd` and `field_0xb0` (GROUND_LANDING/AWAY).
    /// Cylinders are an argument, as `setBgCheckParam` picks them per proc.
    class PlayerAcch {
      public:
        /// The acch keeps pointers to `pos`, `old_pos` and `speed`, as the game does.
        PlayerAcch(cXyz* pos, cXyz* old_pos, cXyz* speed, const WallCyl* cyls, int tbl_size,
                   fpc_ProcID pid = kLinkPid);

        dBgS_Acch& acch() { return m_acch; }
        dBgS_AcchCir& cir(int i) { return m_cir[i]; }
        int tbl_size() const { return m_tbl_size; }

      private:
        dBgS_AcchCir m_cir[kMaxWallCyl];
        dBgS_LinkAcch m_acch;
        int m_tbl_size;
    };

    /// dBgS_Acch::CrrPos (d_bg_s_acch.cpp:209): the whole frame in the game's order - conditional
    /// line check, wall pass, second line check if a wall corrected, roof, ground, GroundRoofProc.
    /// Moves the position the acch points at.
    FrameResult CrrPos(PlayerAcch& player);

    /// The same, on a caller-owned acch and cylinders (the player's own `mAcch`/`mAcchCir`).
    FrameResult CrrPos(dBgS_Acch& acch, dBgS_AcchCir* cirs, int tbl_size);

    /// The dBgS this room is registered in, for `dComIfG_Bgsp()`.
    dBgS& bgs() { return m_bgs; }

    /// Record polygons the following walks visit (see VisitLogBgW). Appends; null stops.
    void LogVisitedPolys(std::vector<int>* sink) { m_bgw.LogTo(sink); }

    /// The built tables.
    const cBgW& bgw() const { return m_bgw; }
    cBgW& bgw() { return m_bgw; }
    int tri_count() const { return m_bgd.m_t_num; }
    int block_count() const { return m_bgd.m_b_num; }
    int node_count() const { return m_bgd.m_tree_num; }
    int group_count() const { return m_bgd.m_g_num; }

    /// One block's ground, wall and roof chains in chain order, as cBgW::BlckConnect threaded
    /// them through pm_rwg.
    std::vector<int> ground_chain(int block) const;
    std::vector<int> wall_chain(int block) const;
    std::vector<int> roof_chain(int block) const;

  private:
    std::vector<int> chain_from(u16 head) const;

    /// One registered object and 255 empty slots; a member so two Rooms are two worlds.
    dBgS m_bgs;

    RoomDzb m_dzb;
    cBgD_t m_bgd;
    std::vector<cBgW_TriElm> m_tri;
    std::vector<cBgW_RwgElm> m_rwg;
    std::vector<cBgW_BlkElm> m_blk;
    std::vector<cBgW_NodeTree> m_nt;
    std::vector<cBgW_GrpElm> m_grp;
    VisitLogBgW m_bgw;
};

}  // namespace tww_engine

#endif  // TWW_ENGINE_ROOM_H
