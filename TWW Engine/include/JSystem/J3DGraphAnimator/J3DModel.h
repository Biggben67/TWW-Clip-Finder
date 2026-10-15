// J3DModel.h - J3DModel trimmed to what the calc chain reads and writes; the rest is draw-side.
// The layout is not the decomp's (0xD4 bytes); nothing casts or indexes a J3DModel. The scale-flag
// array is only written here (its readers are draw-side) but the copied bodies write it.
#ifndef TWW_PORT_J3DMODEL_H
#define TWW_PORT_J3DMODEL_H

#include "dolphin/types.h"
#include "engine/ps_mtx.h"

class J3DModelData;

// J3DModel.h:10-19, whole.
enum J3DMdlFlag {
    /* 0x00001 */ J3DMdlFlag_Unk00001 = 0x1,
    /* 0x00002 */ J3DMdlFlag_Unk00002 = 0x2,
    /* 0x00004 */ J3DMdlFlag_SkinPosCpu = 0x4,
    /* 0x00008 */ J3DMdlFlag_SkinNrmCpu = 0x8,
    /* 0x00010 */ J3DMdlFlag_Unk00010 = 0x10,
    /* 0x20000 */ J3DMdlFlag_Unk20000 = 0x20000,
    /* 0x40000 */ J3DMdlFlag_Unk40000 = 0x40000,
    /* 0x80000 */ J3DMdlFlag_Unk80000 = 0x80000,
};

class J3DModel {
public:
    void calcAnmMtx();

    /// J3DModel.h:75 and :113, defined in boundary/stubs.cpp: the decomp's read plus a record of
    /// which joint was asked for. Answers NULL when mpNodeMtx is null (no skeleton attached).
    MtxP getAnmMtx(int idx);
    void setAnmMtx(int idx, Mtx mtx) { MTXCopy(mtx, mpNodeMtx[idx]); }

    J3DModelData* getModelData() { return mModelData; }
    bool checkFlag(u32 flag) const { return (mFlags & flag) ? true : false; }
    void onFlag(u32 flag) { mFlags |= flag; }
    void offFlag(u32 flag) { mFlags &= ~flag; }

    Mtx& getBaseTRMtx();
    void setBaseTRMtx(Mtx m) { MTXCopy(m, mBaseTransformMtx); }
    Vec* getBaseScale() { return &mBaseScale; }
    void setBaseScale(const Vec& scale) { mBaseScale = scale; }

    u8 getScaleFlag(int idx) const { return mpScaleFlagArr[idx]; }
    void setScaleFlag(int idx, u8 param_1) { mpScaleFlagArr[idx] = param_1; }

    /// Value-initialised: a model with no skeleton has a null mpNodeMtx and a zero base transform.
    J3DModelData* mModelData{};
    u32 mFlags{};
    Vec mBaseScale{};
    Mtx mBaseTransformMtx{};
    u8* mpScaleFlagArr{};
    Mtx* mpNodeMtx{};
};

#endif
