#include "wall_probes.h"

#include <set>

#include "SSystem/SComponent/c_m3d.h"
#include "engine/ppc_fp.h"
#include "framework/require_bits.h"

namespace tww_engine {
namespace testing {

const f32 kWallH[3] = {30.1f, 89.9f, 125.0f};
const f32 kWallR = 35.0f;
const f32 kWallSpeedY = -2.5f;

namespace {

//: How far inside the wall each class puts Link, as a fraction of kWallR. `outside` is past the
//: radius, a control the pass must leave alone.
struct Depth {
    const char* name;
    f32 k;
};
const Depth kFaceDepths[] = {
    {"face_deep", 0.25f}, {"face_mid", 0.60f}, {"face_shallow", 0.95f}, {"face_outside", 1.40f}};
const Depth kCornerDepths[] = {{"corner_deep", 0.25f}, {"corner_shallow", 0.95f}};

//: The differential's |n_xz| cut; see the header.
const f32 kPythonFlatCut = 1.0e-3f;

}  // namespace

std::vector<int> wall_and_roof_chain_polys(const Room& room) {
    std::vector<int> out;
    for (int b = 0; b < room.block_count(); b++) {
        const std::vector<int> w = room.wall_chain(b);
        out.insert(out.end(), w.begin(), w.end());
        const std::vector<int> r = room.roof_chain(b);
        out.insert(out.end(), r.begin(), r.end());
    }
    return out;
}

bool wall_face_probe(const Room& room, const RoomDzb& dzb, int poly, f32 mid_h, f32 depth,
                     cXyz* out, f32* out_ux, f32* out_uz) {
    const cXyz* n = room.bgw().pm_tri[poly].m_plane.GetNP();
    // `sp68` as RwgWallCorrect computes it, so the polygons kept are the ones it does not drop.
    const f32 nlen = ppc::sqrtf_msl(SQUARE(n->x) + SQUARE(n->z));
    if (cM3d_IsZero(nlen)) {
        return false;
    }
    const f32 ux = n->x / nlen, uz = n->z / nlen;
    const cBgD_Tri_t& t = dzb.t_tbl[poly];
    const cBgD_Vtx_t& a = dzb.v_tbl[t.vtx0];
    const cBgD_Vtx_t& b = dzb.v_tbl[t.vtx1];
    const cBgD_Vtx_t& d = dzb.v_tbl[t.vtx2];
    out->x = (a.x + b.x + d.x) / 3.0f + ux * depth;
    out->y = (a.y + b.y + d.y) / 3.0f - mid_h + kWallSpeedY;
    out->z = (a.z + b.z + d.z) / 3.0f + uz * depth;
    if (out_ux != nullptr) {
        *out_ux = ux;
    }
    if (out_uz != nullptr) {
        *out_uz = uz;
    }
    return true;
}

std::vector<WallProbe> wall_probe_set(const Room& room, const RoomDzb& dzb, int* extra_flat) {
    std::vector<WallProbe> out;
    std::set<std::vector<u32> > seen;
    int flat = 0;

    for (int poly : wall_and_roof_chain_polys(room)) {
        const cXyz* n = room.bgw().pm_tri[poly].m_plane.GetNP();
        const f32 nlen = ppc::sqrtf_msl(SQUARE(n->x) + SQUARE(n->z));
        if (cM3d_IsZero(nlen)) {
            continue;
        }
        if (nlen < kPythonFlatCut) {
            flat++;
        }
        const f32 ux = n->x / nlen, uz = n->z / nlen;
        const cBgD_Tri_t& t = dzb.t_tbl[poly];
        const cBgD_Vtx_t* v[3] = {&dzb.v_tbl[t.vtx0], &dzb.v_tbl[t.vtx1], &dzb.v_tbl[t.vtx2]};
        const f32 cy = (v[0]->y + v[1]->y + v[2]->y) / 3.0f;
        const f32 py = cy - kWallH[1] + kWallSpeedY;

        WallProbe p;
        p.of_poly = poly;
        p.pos.y = py;

        const f32 cx = (v[0]->x + v[1]->x + v[2]->x) / 3.0f;
        const f32 cz = (v[0]->z + v[1]->z + v[2]->z) / 3.0f;
        for (const Depth& d : kFaceDepths) {
            const f32 k = kWallR * d.k;
            p.cls = d.name;
            p.pos.x = cx + ux * k;
            p.pos.z = cz + uz * k;
            std::vector<u32> key;
            key.push_back(bits(p.pos.x));
            key.push_back(bits(p.pos.y));
            key.push_back(bits(p.pos.z));
            if (seen.insert(key).second) {
                out.push_back(p);
            }
        }
        for (int a = 0; a < 3; a++) {
            for (const Depth& d : kCornerDepths) {
                const f32 k = kWallR * d.k;
                p.cls = d.name;
                p.pos.x = v[a]->x + ux * k;
                p.pos.z = v[a]->z + uz * k;
                std::vector<u32> key;
                key.push_back(bits(p.pos.x));
                key.push_back(bits(p.pos.y));
                key.push_back(bits(p.pos.z));
                if (seen.insert(key).second) {
                    out.push_back(p);
                }
            }
        }
    }
    if (extra_flat != nullptr) {
        *extra_flat = flat;
    }
    return out;
}

}  // namespace testing
}  // namespace tww_engine
