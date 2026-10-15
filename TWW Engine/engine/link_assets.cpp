// link_assets.cpp - see link_assets.h.
//
// The two parsers read exactly what the game's own loaders read: J3DAnmKeyLoader_v15::
// setAnmTransform for an ANK1 block (J3DAnmLoader.cpp:455), and J3DModelLoader::readInformation
// and readJoint for INF1 and JNT1 (J3DModelLoader.cpp:250). The arrays are kept verbatim, as the
// loader leaves them for J3DAnmTransformKey and J3DJointFactory to index.

#include "engine/link_assets.h"

#include <cstring>

#include "d/actor/d_a_player_main.h"

namespace tww_engine {

const char* const kLinkModelArchive = "res/Object/Link.arc";
const char* const kLinkModelFile = "cl.bdl";
const char* const kLinkAnimationArchive = "res/Object/LkAnm.arc";

namespace {

struct Wanted {
    u16 bckIdx;
    const char* file;
};

// The animations the ported bodies are validated against. An index not here is answered by the
// counters in boundary/stubs.cpp rather than by a default.
const Wanted kWanted[] = {
    { dRes_INDEX_LKANM_BCK_ATNDB_e, "atndb.bck" },
    { dRes_INDEX_LKANM_BCK_ATNDLS_e, "atndls.bck" },
    { dRes_INDEX_LKANM_BCK_ATNDL_e, "atndl.bck" },
    { dRes_INDEX_LKANM_BCK_ATNDRS_e, "atndrs.bck" },
    { dRes_INDEX_LKANM_BCK_ATNDR_e, "atndr.bck" },
    { dRes_INDEX_LKANM_BCK_ATNJL_e, "atnjl.bck" },
    { dRes_INDEX_LKANM_BCK_ATNJLLAND_e, "atnjlland.bck" },
    { dRes_INDEX_LKANM_BCK_ATNJR_e, "atnjr.bck" },
    { dRes_INDEX_LKANM_BCK_ATNJRLAND_e, "atnjrland.bck" },
    { dRes_INDEX_LKANM_BCK_ATNLS_e, "atnls.bck" },
    { dRes_INDEX_LKANM_BCK_ATNL_e, "atnl.bck" },
    { dRes_INDEX_LKANM_BCK_ATNRS_e, "atnrs.bck" },
    { dRes_INDEX_LKANM_BCK_ATNR_e, "atnr.bck" },
    { dRes_INDEX_LKANM_BCK_ATNWB_e, "atnwb.bck" },
    { dRes_INDEX_LKANM_BCK_ATNWLS_e, "atnwls.bck" },
    { dRes_INDEX_LKANM_BCK_ATNWL_e, "atnwl.bck" },
    { dRes_INDEX_LKANM_BCK_ATNWRS_e, "atnwrs.bck" },
    { dRes_INDEX_LKANM_BCK_ATNWR_e, "atnwr.bck" },
    { dRes_INDEX_LKANM_BCK_CROUCH_e, "crouch.bck" },
    { dRes_INDEX_LKANM_BCK_CUTA_e, "cuta.bck" },
    { dRes_INDEX_LKANM_BCK_CUTEA_e, "cutea.bck" },
    { dRes_INDEX_LKANM_BCK_CUTEB_e, "cuteb.bck" },
    { dRes_INDEX_LKANM_BCK_CUTF_e, "cutf.bck" },
    { dRes_INDEX_LKANM_BCK_CUTL_e, "cutl.bck" },
    { dRes_INDEX_LKANM_BCK_CUTR_e, "cutr.bck" },
    { dRes_INDEX_LKANM_BCK_CUTTURN_e, "cutturn.bck" },
    { dRes_INDEX_LKANM_BCK_CUTTURNP_e, "cutturnp.bck" },
    { dRes_INDEX_LKANM_BCK_CUTTURNPWFB_e, "cutturnpwfb.bck" },
    { dRes_INDEX_LKANM_BCK_DASH_e, "dash.bck" },
    { dRes_INDEX_LKANM_BCK_DASHS_e, "dashs.bck" },
    { dRes_INDEX_LKANM_BCK_FREEA_e, "freea.bck" },
    { dRes_INDEX_LKANM_BCK_GRABWAIT_e, "grabwait.bck" },
    { dRes_INDEX_LKANM_BCK_FREEB_e, "freeb.bck" },
    { dRes_INDEX_LKANM_BCK_FREED_e, "freed.bck" },
    { dRes_INDEX_LKANM_BCK_JATTACK_e, "jattack.bck" },
    { dRes_INDEX_LKANM_BCK_JATTACKLAND_e, "jattackland.bck" },
    { dRes_INDEX_LKANM_BCK_LIE_e, "lie.bck" },
    { dRes_INDEX_LKANM_BCK_ROLLB_e, "rollb.bck" },
    { dRes_INDEX_LKANM_BCK_ROLLBLAND_e, "rollbland.bck" },
    { dRes_INDEX_LKANM_BCK_ROLLF_e, "rollf.bck" },
    { dRes_INDEX_LKANM_BCK_REST_e, "rest.bck" },
    { dRes_INDEX_LKANM_BCK_ROT_e, "rot.bck" },
    { dRes_INDEX_LKANM_BCK_SLIP_e, "slip.bck" },
    { dRes_INDEX_LKANM_BCK_WAITATOB_e, "waitatob.bck" },
    { dRes_INDEX_LKANM_BCK_WAITB_e, "waitb.bck" },
    { dRes_INDEX_LKANM_BCK_WAITS_e, "waits.bck" },
    { dRes_INDEX_LKANM_BCK_WALK_e, "walk.bck" },
    { dRes_INDEX_LKANM_BCK_WALKS_e, "walks.bck" },
    { dRes_INDEX_LKANM_BCK_WALKSLOPE_e, "walkslope.bck" },
};

const size_t kWantedCount = sizeof(kWanted) / sizeof(kWanted[0]);

u16 be16(const u8* p) { return static_cast<u16>((p[0] << 8) | p[1]); }

u32 be32(const u8* p) {
    return (static_cast<u32>(p[0]) << 24) | (static_cast<u32>(p[1]) << 16) |
           (static_cast<u32>(p[2]) << 8) | static_cast<u32>(p[3]);
}

f32 bef32(const u8* p) {
    const u32 w = be32(p);
    f32 f;
    std::memcpy(&f, &w, sizeof f);
    return f;
}

struct Animation {
    daPy_portAnmMeta meta;
    daPy_portAnmTrack track;
    std::vector<J3DAnmTransformKeyTable> table;
    std::vector<f32> scale;
    std::vector<s16> rot;
    std::vector<f32> trans;
};

// `track` points into its own Animation's vectors. The outer vector is sized once, before any
// pointer is taken, and swapped - never copied - so no element moves after its pointers are set.
struct Installed {
    bool ok = false;
    LinkSkeleton skeleton;
    std::vector<Animation> animations;
};

Installed& installed() {
    static Installed s;
    return s;
}

/// The block of a J3D file whose four-character type is `type`, or NULL. Bounds-checked.
const u8* block_of(const std::vector<u8>& f, const char* type, size_t* size) {
    if (f.size() < 0x20) return NULL;
    const u32 count = be32(&f[0x0C]);
    size_t at = 0x20;
    for (u32 i = 0; i < count; i++) {
        if (at + 8 > f.size()) return NULL;
        const u32 n = be32(&f[at + 4]);
        if (n < 8 || n > f.size() - at) return NULL;
        if (std::memcmp(&f[at], type, 4) == 0) {
            *size = n;
            return &f[at];
        }
        at += n;
    }
    return NULL;
}

bool parse_bck(const std::vector<u8>& f, u16 bckIdx, Animation* a, std::string* why) {
    size_t n = 0;
    const u8* b = block_of(f, "ANK1", &n);
    if (b == NULL || n < 0x24) {
        *why = "no ANK1 block";
        return false;
    }
    const u16 joints = be16(b + 0x0C);
    const u16 scales = be16(b + 0x0E);
    const u16 rots = be16(b + 0x10);
    const u16 transes = be16(b + 0x12);
    const size_t tableAt = be32(b + 0x14);
    const size_t scaleAt = be32(b + 0x18);
    const size_t rotAt = be32(b + 0x1C);
    const size_t transAt = be32(b + 0x20);
    const size_t tableCount = static_cast<size_t>(joints) * 3;
    if (tableAt + tableCount * 18 > n || scaleAt + scales * 4u > n || rotAt + rots * 2u > n ||
        transAt + transes * 4u > n) {
        *why = "ANK1 runs past its block";
        return false;
    }

    a->table.resize(tableCount);
    for (size_t i = 0; i < tableCount; i++) {
        const u8* e = b + tableAt + i * 18;
        J3DAnmKeyTableBase* k[3] = {&a->table[i].mScale, &a->table[i].mRotation,
                                    &a->table[i].mTranslate};
        for (int j = 0; j < 3; j++) {
            k[j]->mMaxFrame = be16(e + j * 6 + 0);
            k[j]->mOffset = be16(e + j * 6 + 2);
            k[j]->mType = be16(e + j * 6 + 4);
        }
    }
    a->scale.resize(scales);
    for (u16 i = 0; i < scales; i++) a->scale[i] = bef32(b + scaleAt + i * 4u);
    a->rot.resize(rots);
    for (u16 i = 0; i < rots; i++) a->rot[i] = static_cast<s16>(be16(b + rotAt + i * 2u));
    a->trans.resize(transes);
    for (u16 i = 0; i < transes; i++) a->trans[i] = bef32(b + transAt + i * 4u);

    a->meta.mBckIdx = bckIdx;
    a->meta.mFrameMax = static_cast<s16>(be16(b + 0x0A));
    a->meta.mAttribute = b[0x08];
    a->track.mBckIdx = bckIdx;
    a->track.mDecShift = b[0x09];
    a->track.mJointNum = joints;
    a->track.mAnmTable = a->table.data();
    a->track.mScaleData = a->scale.data();
    a->track.mRotData = a->rot.data();
    a->track.mTransData = a->trans.data();
    a->track.mScaleNum = scales;
    a->track.mRotNum = rots;
    a->track.mTransNum = transes;
    return true;
}

bool parse_bdl(const std::vector<u8>& f, LinkSkeleton* s, std::string* why) {
    size_t n = 0;
    const u8* inf = block_of(f, "INF1", &n);
    if (inf == NULL || n < 0x18) {
        *why = "no INF1 block";
        return false;
    }
    // J3DMtxCalcMaya is the calc engine/link_model.h builds; readInformation picks it on 2.
    if ((be16(inf + 0x08) & 0xF) != 2) {
        *why = "the model's matrix calc is not Maya";
        return false;
    }
    s->hierarchy.clear();
    s->visit.clear();
    for (size_t at = be32(inf + 0x14);; at += 4) {
        if (at + 4 > n) {
            *why = "INF1 has no terminator";
            return false;
        }
        J3DModelHierarchy h;
        h.mType = be16(inf + at);
        h.mValue = be16(inf + at + 2);
        if (h.mType == 0) break;
        s->hierarchy.push_back(h);
        // makeHierarchy appends each joint as the last child of the open bracket, and
        // recursiveCalc visits child before younger sibling, so the walk is the stream's order.
        if (h.mType == 0x10) s->visit.push_back(h.mValue);
    }

    const u8* jnt = block_of(f, "JNT1", &n);
    if (jnt == NULL || n < 0x18) {
        *why = "no JNT1 block";
        return false;
    }
    const u16 joints = be16(jnt + 0x08);
    if (joints != kLinkJointNum || s->visit.size() != joints) {
        *why = "the model does not have Link's joint count";
        return false;
    }
    const size_t initAt = be32(jnt + 0x0C);
    const size_t indexAt = be32(jnt + 0x10);
    if (indexAt + joints * 2u > n) {
        *why = "JNT1 runs past its block";
        return false;
    }
    s->index.resize(joints);
    size_t rows = 0;
    for (u16 i = 0; i < joints; i++) {
        s->index[i] = be16(jnt + indexAt + i * 2u);
        if (s->index[i] + 1u > rows) rows = s->index[i] + 1u;
    }
    if (initAt + rows * 0x40u > n) {
        *why = "JNT1 runs past its block";
        return false;
    }
    s->joints.resize(rows);
    for (size_t i = 0; i < rows; i++) {
        const u8* r = jnt + initAt + i * 0x40u;
        J3DJointInitData& d = s->joints[i];
        d.mKind = be16(r + 0x00);
        d.mScaleCompensate = r[0x02] != 0;
        d.mTransformInfo.mScale.x = bef32(r + 0x04);
        d.mTransformInfo.mScale.y = bef32(r + 0x08);
        d.mTransformInfo.mScale.z = bef32(r + 0x0C);
        d.mTransformInfo.mRotation.x = static_cast<s16>(be16(r + 0x10));
        d.mTransformInfo.mRotation.y = static_cast<s16>(be16(r + 0x12));
        d.mTransformInfo.mRotation.z = static_cast<s16>(be16(r + 0x14));
        d.mTransformInfo.mTranslate.x = bef32(r + 0x18);
        d.mTransformInfo.mTranslate.y = bef32(r + 0x1C);
        d.mTransformInfo.mTranslate.z = bef32(r + 0x20);
        d.mRadius = bef32(r + 0x24);
        d.mMin.x = bef32(r + 0x28);
        d.mMin.y = bef32(r + 0x2C);
        d.mMin.z = bef32(r + 0x30);
        d.mMax.x = bef32(r + 0x34);
        d.mMax.y = bef32(r + 0x38);
        d.mMax.z = bef32(r + 0x3C);
    }
    return true;
}

}  // namespace

std::vector<std::string> linkAnimationFiles() {
    std::vector<std::string> files;
    for (size_t i = 0; i < kWantedCount; i++) files.push_back(kWanted[i].file);
    return files;
}

bool installLinkAssets(const LinkAssets& assets, std::string* why) {
    std::string local;
    std::string& w = why ? *why : local;
    Installed next;
    if (!parse_bdl(assets.model, &next.skeleton, &w)) {
        w = std::string(kLinkModelFile) + ": " + w;
        return false;
    }
    next.animations.resize(kWantedCount);
    for (size_t i = 0; i < kWantedCount; i++) {
        const std::map<std::string, std::vector<u8> >::const_iterator f =
            assets.animations.find(kWanted[i].file);
        if (f == assets.animations.end()) {
            w = std::string(kWanted[i].file) + ": missing";
            return false;
        }
        if (!parse_bck(f->second, kWanted[i].bckIdx, &next.animations[i], &w)) {
            w = std::string(kWanted[i].file) + ": " + w;
            return false;
        }
    }
    Installed& s = installed();
    s.skeleton.hierarchy.swap(next.skeleton.hierarchy);
    s.skeleton.joints.swap(next.skeleton.joints);
    s.skeleton.index.swap(next.skeleton.index);
    s.skeleton.visit.swap(next.skeleton.visit);
    s.animations.swap(next.animations);
    s.ok = true;
    return true;
}

bool linkAssetsInstalled() { return installed().ok; }

const char* linkAnimationName(u16 bckIdx) {
    for (size_t i = 0; i < kWantedCount; ++i)
        if (kWanted[i].bckIdx == bckIdx) return kWanted[i].file;
    return "";
}

const LinkSkeleton& linkSkeleton() { return installed().skeleton; }

const daPy_portAnmMeta* linkAnimationMeta(u16 bckIdx) {
    const std::vector<Animation>& a = installed().animations;
    for (size_t i = 0; i < a.size(); i++) {
        if (a[i].meta.mBckIdx == bckIdx) return &a[i].meta;
    }
    return NULL;
}

const daPy_portAnmTrack* linkAnimationTrack(u16 bckIdx) {
    const std::vector<Animation>& a = installed().animations;
    for (size_t i = 0; i < a.size(); i++) {
        if (a[i].track.mBckIdx == bckIdx) return &a[i].track;
    }
    return NULL;
}

size_t linkAnimationCount() { return installed().animations.size(); }

const daPy_portAnmTrack* linkAnimationTrackAt(size_t i) {
    const std::vector<Animation>& a = installed().animations;
    return i < a.size() ? &a[i].track : NULL;
}

}  // namespace tww_engine
