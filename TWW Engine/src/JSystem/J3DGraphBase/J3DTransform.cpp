// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DTransform.cpp - the j3dDefault* constants and both J3DGetTranslateRotateMtx overloads
// (J3DTransform.cpp:17-29, 166-190, 193-217).
// The off-diagonals are not fused: the DOL rounds the product, then subtracts (JP
// 0x802D7CAC, 0x802D7D84).

#include "JSystem/J3DGraphBase/J3DTransform.h"
#include "JSystem/JMath/JMATrigonometric.h"


const J3DTransformInfo j3dDefaultTransformInfo = {
    { 1.0f, 1.0f, 1.0f },
    { 0, 0, 0 },
    { 0.0f, 0.0f, 0.0f },
};

const Vec j3dDefaultScale = { 1.0f, 1.0f, 1.0f };

const Mtx j3dDefaultMtx = {
    { 1.0f, 0.0f, 0.0f, 0.0f },
    { 0.0f, 1.0f, 0.0f, 0.0f },
    { 0.0f, 0.0f, 1.0f, 0.0f },
};

void J3DGetTranslateRotateMtx(const J3DTransformInfo& tx, Mtx dst) {
    f32 sx = JMASSin(tx.mRotation.x), cx = JMASCos(tx.mRotation.x);
    f32 sy = JMASSin(tx.mRotation.y), cy = JMASCos(tx.mRotation.y);
    f32 sz = JMASSin(tx.mRotation.z), cz = JMASCos(tx.mRotation.z);

    dst[2][0] = -sy;
    dst[0][0] = cz * cy;
    dst[1][0] = sz * cy;
    dst[2][1] = cy * sx;
    dst[2][2] = cy * cx;

    f32 cxsz = cx * sz;
    f32 sxcz = sx * cz;
    dst[0][1] = sxcz * sy - cxsz;
    dst[1][2] = cxsz * sy - sxcz;

    f32 sxsz = sx * sz;
    f32 cxcz = cx * cz;
    dst[0][2] = cxcz * sy + sxsz;
    dst[1][1] = sxsz * sy + cxcz;

    dst[0][3] = tx.mTranslate.x;
    dst[1][3] = tx.mTranslate.y;
    dst[2][3] = tx.mTranslate.z;
}

void J3DGetTranslateRotateMtx(s16 rx, s16 ry, s16 rz, f32 tx, f32 ty, f32 tz, Mtx dst) {
    f32 sx = JMASSin(rx), cx = JMASCos(rx);
    f32 sy = JMASSin(ry), cy = JMASCos(ry);
    f32 sz = JMASSin(rz), cz = JMASCos(rz);

    dst[2][0] = -sy;
    dst[0][0] = cz * cy;
    dst[1][0] = sz * cy;
    dst[2][1] = cy * sx;
    dst[2][2] = cy * cx;

    f32 cxsz = cx * sz;
    f32 sxcz = sx * cz;
    dst[0][1] = sxcz * sy - cxsz;
    dst[1][2] = cxsz * sy - sxcz;

    f32 sxsz = sx * sz;
    f32 cxcz = cx * cz;
    dst[0][2] = cxcz * sy + sxsz;
    dst[1][1] = sxsz * sy + cxcz;

    dst[0][3] = tx;
    dst[1][3] = ty;
    dst[2][3] = tz;
}
