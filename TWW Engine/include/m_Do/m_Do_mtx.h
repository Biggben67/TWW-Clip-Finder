// m_Do_mtx.h - the game's matrix layer, trimmed to what the player's closure reaches. The
// paired-single `#if __MWERKS__` fork is resolved in engine/ps_mtx.h.

#ifndef TWW_PORT_M_DO_MTX_H
#define TWW_PORT_M_DO_MTX_H

#include "dolphin/types.h"
#include "engine/ps_mtx.h"

/// m_Do_mtx.h:11-20, trimmed; bodies in src/m_Do/m_Do_mtx.cpp. ZXYrotM skips any axis whose
/// angle is exactly zero, so those axes add no rounding.
void mDoMtx_ZXYrotS(MtxP, s16, s16, s16);
void mDoMtx_ZXYrotM(MtxP, s16, s16, s16);
void mDoMtx_XrotS(MtxP, s16);
void mDoMtx_XrotM(MtxP, s16);
void mDoMtx_YrotS(MtxP, s16);
void mDoMtx_YrotM(MtxP, s16);
void mDoMtx_ZrotS(MtxP, s16);
void mDoMtx_ZrotM(MtxP, s16);
void mDoMtx_QuatConcat(const Quaternion* a, const Quaternion* b, Quaternion* c);

/// m_Do_mtx.h:29-135, the inline wrappers, verbatim.
inline void mDoMtx_multVecSR(const f32 (*m)[4], const Vec* src, Vec* dst) {
    MTXMultVecSR(m, src, dst);
}

inline void mDoMtx_multVec(const f32 (*m)[4], const Vec* src, Vec* dst) {
    MTXMultVec(m, src, dst);
}

inline void mDoMtx_copy(const f32 (*src)[4], MtxP dst) {
    MTXCopy(src, dst);
}

inline void mDoMtx_trans(MtxP m, f32 x, f32 y, f32 z) {
    MTXTrans(m, x, y, z);
}

inline void mDoMtx_concat(const f32 (*a)[4], const f32 (*b)[4], MtxP c) {
    MTXConcat(a, b, c);
}

/// m_Do_mtx.h:128-130, verbatim.
inline void mDoMtx_identity(Mtx m) {
    MTXIdentity(m);
}

/// m_Do_mtx.h:34-36, verbatim.
inline void cMtx_concat(const f32 (*a)[4], const f32 (*b)[4], MtxP ab) {
    mDoMtx_concat(a, b, ab);
}

/// m_Do_mtx.h:70-72, 74-76, 86-88, verbatim.
inline void cMtx_XrotS(Mtx mtx, s16 x) {
    mDoMtx_XrotS(mtx, x);
}

inline void cMtx_YrotS(Mtx mtx, s16 y) {
    mDoMtx_YrotS(mtx, y);
}

inline void cMtx_multVec(const Mtx mtx, const Vec* src, Vec* dst) {
    mDoMtx_multVec(mtx, src, dst);
}

inline void mDoMtx_inverse(const f32 (*a)[4], MtxP b) {
    MTXInverse(a, b);
}

/// m_Do_mtx.h:144-146. MTXQuat is PSMTXQuat in the retail DOL.
inline void mDoMtx_quat(Mtx m, const Quaternion* q) {
    MTXQuat(m, q);
}

/// m_Do_mtx.h:161-371, trimmed. `now` and `buffer` are defined in src/m_Do/m_Do_mtx.cpp.
/// setWorldMatrix runs at the end of execute() (d_a_player_main.cpp:11544), so crawlBgCheck on
/// frame N reads the matrix of frame N-1, as in the game.
class mDoMtx_stack_c {
public:
    static void transM(f32 x, f32 y, f32 z);

    static MtxP get() { return now; }

    static void transS(f32 x, f32 y, f32 z) { MTXTrans(now, x, y, z); }

    /// m_Do_mtx.h:265.
    static void multVec(const Vec* a, Vec* b) { MTXMultVec(now, a, b); }

    static void multVecSR(const Vec* a, Vec* b) { MTXMultVecSR(now, a, b); }

    /// m_Do_mtx.h:296.
    static void ZXYrotS(s16 x, s16 y, s16 z) { mDoMtx_ZXYrotS(now, x, y, z); }

    static void ZXYrotM(s16 x, s16 y, s16 z) { mDoMtx_ZXYrotM(now, x, y, z); }

    static void YrotM(s16 y) { mDoMtx_YrotM(now, y); }

    static void YrotS(s16 y) { mDoMtx_YrotS(now, y); }

    /// m_Do_mtx.h:334-352 and :234-236.
    static void ZrotM(s16 z) { mDoMtx_ZrotM(now, z); }

    static void ZrotS(s16 z) { mDoMtx_ZrotS(now, z); }

    static void revConcat(const f32 (*m)[4]) { MTXConcat(m, now, now); }

    static void quatM(const Quaternion*);

    static void quatS(const Quaternion* quat) { MTXQuat(now, quat); }

    static void inverse() { MTXInverse(now, now); }

    static void concat(const f32 (*m)[4]) { MTXConcat(now, m, now); }

    // Static in the decomp; per thread here, since the library runs one player per thread.
    static thread_local Mtx now;
    static thread_local Mtx buffer[16];
    static thread_local Mtx* next;
    static thread_local Mtx* end;
};

#endif
