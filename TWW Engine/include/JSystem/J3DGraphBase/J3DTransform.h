// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DTransform.h - J3DTransformInfo, the j3dDefault* constants and both
// J3DGetTranslateRotateMtx overloads (J3DTransform.h:9-20, 22-24, 32-33). Both are declared
// so a caller cannot reach the wrong one by implicit conversion.

#ifndef TWW_PORT_J3DTRANSFORM_H
#define TWW_PORT_J3DTRANSFORM_H

#include "dolphin/types.h"

struct J3DTransformInfo {
    /* 0x00 */ Vec mScale;
    /* 0x0C */ SVec mRotation;
    /* 0x14 */ Vec mTranslate;

    inline J3DTransformInfo& operator=(const J3DTransformInfo& b) {
        mScale = b.mScale;
        mRotation = b.mRotation;
        mTranslate = b.mTranslate;
        return *this;
    }
};  // Size: 0x20

extern J3DTransformInfo const j3dDefaultTransformInfo;
extern Vec const j3dDefaultScale;
extern Mtx const j3dDefaultMtx;

void J3DGetTranslateRotateMtx(J3DTransformInfo const&, Mtx);
void J3DGetTranslateRotateMtx(s16, s16, s16, f32, f32, f32, Mtx);

#endif
