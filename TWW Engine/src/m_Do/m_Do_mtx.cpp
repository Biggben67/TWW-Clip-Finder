// Generated from the zeldaret/tww decomp. Do not hand-edit.
// m_Do_mtx.cpp - the rotation helpers, mDoMtx_QuatConcat and the matrix stack
// (m_Do_mtx.cpp:13-17, 49-66, 68-85, 87-169, 274-279, 321-326, 350-354).
// mDoMtx_ZXYrotM skips any axis whose angle is exactly 0, so it carries no rounding from
// that axis.

#include "m_Do/m_Do_mtx.h"

#include "global.h"
#include "JSystem/JMath/JMATrigonometric.h"

thread_local Mtx mDoMtx_stack_c::now;
thread_local Mtx mDoMtx_stack_c::buffer[16];

thread_local Mtx* mDoMtx_stack_c::next = mDoMtx_stack_c::buffer;
thread_local Mtx* mDoMtx_stack_c::end = mDoMtx_stack_c::buffer + ARRAY_SIZE(mDoMtx_stack_c::buffer);

void mDoMtx_ZXYrotS(Mtx mtx, s16 x, s16 y, s16 z) {
    Mtx tmp;
    if (y != 0) {
        mDoMtx_YrotS(mtx, y);
    } else {
        mDoMtx_identity(mtx);
    }

    if (x != 0) {
        mDoMtx_XrotS(tmp, x);
        mDoMtx_concat(mtx, tmp, mtx);
    }

    if (z != 0) {
        mDoMtx_ZrotS(tmp, z);
        mDoMtx_concat(mtx, tmp, mtx);
    }
}

/* 8000CC84-8000CD28       .text mDoMtx_ZXYrotM__FPA4_fsss */
void mDoMtx_ZXYrotM(Mtx mtx, s16 x, s16 y, s16 z) {
    Mtx tmp;
    if (y != 0) {
        mDoMtx_YrotS(tmp, y);
        mDoMtx_concat(mtx, tmp, mtx);
    }

    if (x != 0) {
        mDoMtx_XrotS(tmp, x);
        mDoMtx_concat(mtx, tmp, mtx);
    }

    if (z != 0) {
        mDoMtx_ZrotS(tmp, z);
        mDoMtx_concat(mtx, tmp, mtx);
    }
}

/* 8000CD28-8000CD88       .text mDoMtx_XrotS__FPA4_fs */
void mDoMtx_XrotS(Mtx mtx, s16 x) {
    f32 l_cos = JMASCos(x);
    f32 l_sin = JMASSin(x);

    mtx[0][0] = 1.0f;
    mtx[0][1] = 0.0f;
    mtx[0][2] = 0.0f;
    mtx[0][3] = 0.0f;

    mtx[1][0] = 0.0f;
    mtx[1][1] = l_cos;
    mtx[1][2] = -l_sin;
    mtx[1][3] = 0.0f;

    mtx[2][0] = 0.0f;
    mtx[2][1] = l_sin;
    mtx[2][2] = l_cos;
    mtx[2][3] = 0.0f;
}

/* 8000CD88-8000CDC8       .text mDoMtx_XrotM__FPA4_fs */
void mDoMtx_XrotM(Mtx mtx, s16 x) {
    Mtx tmp;
    mDoMtx_XrotS(tmp, x);
    mDoMtx_concat(mtx, tmp, mtx);
}

/* 8000CDC8-8000CE28       .text mDoMtx_YrotS__FPA4_fs */
void mDoMtx_YrotS(Mtx mtx, s16 y) {
    f32 l_cos = JMASCos(y);
    f32 l_sin = JMASSin(y);

    mtx[0][0] = l_cos;
    mtx[0][1] = 0.0f;
    mtx[0][2] = l_sin;
    mtx[0][3] = 0.0f;

    mtx[1][0] = 0.0f;
    mtx[1][1] = 1.0;
    mtx[1][2] = 0.0;
    mtx[1][3] = 0.0f;

    mtx[2][0] = -l_sin;
    mtx[2][1] = 0.0f;
    mtx[2][2] = l_cos;
    mtx[2][3] = 0.0f;
}

/* 8000CE28-8000CE68       .text mDoMtx_YrotM__FPA4_fs */
void mDoMtx_YrotM(Mtx mtx, s16 y) {
    Mtx tmp;
    mDoMtx_YrotS(tmp, y);
    mDoMtx_concat(mtx, tmp, mtx);
}

/* 8000CE68-8000CEC8       .text mDoMtx_ZrotS__FPA4_fs */
void mDoMtx_ZrotS(Mtx mtx, s16 z) {
    f32 l_cos = JMASCos(z);
    f32 l_sin = JMASSin(z);

    mtx[0][0] = l_cos;
    mtx[0][1] = -l_sin;
    mtx[0][2] = 0.0f;
    mtx[0][3] = 0.0f;

    mtx[1][0] = l_sin;
    mtx[1][1] = l_cos;
    mtx[1][2] = 0.0;
    mtx[1][3] = 0.0f;

    mtx[2][0] = 0.0f;
    mtx[2][1] = 0.0f;
    mtx[2][2] = 1.0f;
    mtx[2][3] = 0.0f;
}

/* 8000CEC8-8000CF08       .text mDoMtx_ZrotM__FPA4_fs */
void mDoMtx_ZrotM(Mtx mtx, s16 z) {
    Mtx tmp;
    mDoMtx_ZrotS(tmp, z);
    mDoMtx_concat(mtx, tmp, mtx);
}

void mDoMtx_QuatConcat(const Quaternion* a, const Quaternion* b, Quaternion* c) {
    c->w = (a->w * b->w) - (a->x * b->x) - (a->y * b->y) - (a->z * b->z);
    c->x = (a->w * b->x) + (a->x * b->w) + (a->y * b->z) - (a->z * b->y);
    c->y = (a->w * b->y) + (a->y * b->w) + (a->z * b->x) - (a->x * b->z);
    c->z = (a->w * b->z) + (a->z * b->w) + (a->x * b->y) - (a->y * b->x);
}

/* 8000D850-8000D888       .text transM__14mDoMtx_stack_cFfff */
void mDoMtx_stack_c::transM(f32 x, f32 y, f32 z) {
    Mtx tmp;
    mDoMtx_trans(tmp, x, y, z);
    mDoMtx_concat(now, tmp, now);
}

void mDoMtx_stack_c::quatM(const Quaternion* quat) {
    Mtx tmp;
    mDoMtx_quat(tmp, quat);
    mDoMtx_concat(now, tmp, now);
}
