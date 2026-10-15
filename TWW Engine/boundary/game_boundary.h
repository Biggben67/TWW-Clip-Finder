// game_boundary.h - free game functions the copied collision bodies call, declared here so no
// decomp-path header has to change. Defined in stubs.cpp.

#ifndef TWW_BOUNDARY_GAME_BOUNDARY_H
#define TWW_BOUNDARY_GAME_BOUNDARY_H

#include "dolphin/types.h"

class fopAc_ac_c;
class dBgW;

/// f_op_actor_mng.h. The actor's process id; dBgS_Acch::Set passes it to SetActorPid so a query
/// does not collide with its own actor.
fpc_ProcID fopAcM_GetID(fopAc_ac_c* actor);

/// d_com_inf_game.h. The dBgW of room `room_no`; asked by dBgS_Acch::CrrPos's water stage.
dBgW* dComIfGp_roomControl_getBgW(int room_no);

/// d_a_sea.h. Whether (x, z) is in the ocean actor's area, and the wave height there. Both sit
/// behind `ChkSeaCheckOn()` in CrrPos.
bool daSea_ChkArea(f32 x, f32 z);
f32 daSea_calcWave(f32 x, f32 z);

/// The skeleton's three draw-side virtuals need definitions but must not be reached. Each bumps
/// this counter and names itself; tests/test_calc_anm_mtx.cpp requires 0 after every walk.
/// Per thread.
extern thread_local int j3d_boundary_hits;
extern thread_local const char* j3d_boundary_last;
void j3d_boundary_reached(const char* who);

/// The port-wide census: every instrumented definition (the PARTIAL and STUB grades, plus the
/// J3D and camera stubs) under one reset and one walk. SCOPE stubs are not counted.
///
/// Each row carries its grade: a STUB hit means missing arithmetic was asked for; a PARTIAL hit
/// means a body that is real only for some inputs was entered, and some run every frame.
///
/// Not self-resetting: call `boundary_reset()` before a run. Per thread, so a run stepped on a
/// worker thread must be reported from that thread.
///
/// `who` and `grade` are string literals, compared by pointer.
void boundary_reached(const char* who, const char* grade);
void boundary_reset();
int boundary_hits_total();
int boundary_names();
const char* boundary_name(int i);
const char* boundary_name_grade(int i);
int boundary_name_hits(int i);

/// Calls that found no row and no room for one. Non-zero means the census is incomplete. Counts
/// calls, not names.
int boundary_dropped();

/// The camera's boundary counter. dCamera_c::Run is copied and its callees are not; every camera
/// stub bumps this and names itself. Not required to be 0. Per thread.
extern thread_local int cam_boundary_hits;
extern thread_local const char* cam_boundary_last;
void cam_boundary_reached(const char* who);

/// The camera census: reset before a frame, then walk the names. Read by
/// tests/test_cam_boundary_census.cpp.
void cam_boundary_reset();
int cam_boundary_names();
const char* cam_boundary_name(int i);
int cam_boundary_name_hits(int i);

/// Driven answers for dAttention_c::LockonTruth and ::Lockon. Two fields because the decomp's
/// Lockon is `LockonTruth() || chkFlag(AttnFlag_20000000)`: truth implies lockon, not the reverse.
/// Both default to false. Per thread: set them on the thread that steps the Session.
extern thread_local bool cam_stub_lockon;
extern thread_local bool cam_stub_lockon_truth;


// ---------------------------------------------------------------- bumpCheck's corner solver
//
// c_m3d.cpp. The point on two planes' intersection line nearest a given point. Declared here so
// c_m3d.h stays a copy. Stubbed and unreached.
class cM3dGPla;
bool cM3d_2PlaneLinePosNearPos(const cM3dGPla&, const cM3dGPla&, const Vec*, Vec*);

// ---------------------------------------------------------------- bumpCheck's grab-actor arm
//
// d_a_tsubo.h:40-41. The decomp's own values, typed one at a time: Prm_e lives in an actor class
// this port does not carry.
namespace daTsubo {
class Act_c {
public:
    enum Prm_e {
        PRM_TYPE_W = 4,
        PRM_TYPE_S = 24,
    };
};
}  // namespace daTsubo

/// PrmAbstract below is d_a_obj.h:11-15, a definition with the decomp's expression; it does not
/// bump the camera census. Its callee is stubbed in stubs.cpp.
u32 fopAcM_GetParam(fopAc_ac_c* actor);

namespace daObj {
template <typename T>
int PrmAbstract(const fopAc_ac_c* actor, T width, T shift) {
    u32 param = fopAcM_GetParam((fopAc_ac_c*)actor);
    return ((1 << width) - 1) & (param >> shift);
}
}  // namespace daObj

#endif  // TWW_BOUNDARY_GAME_BOUNDARY_H
