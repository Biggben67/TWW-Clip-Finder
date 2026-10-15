// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d_g_lin.h - cM3dGLin, trimmed (c_m3d_g_lin.h:8-13, 14-21, 36-44).

#ifndef TWW_PORT_C_M3D_G_LIN_H
#define TWW_PORT_C_M3D_G_LIN_H

#include "global.h"
#include "dolphin/types.h"

class cM3dGLin {
private:
    /* 0x00 */ cXyz mStart;
    /* 0x0C */ cXyz mEnd;
    /* 0x18 vtable */


public:
    cM3dGLin() {}
    cM3dGLin(const cXyz& start, const cXyz& end) : mStart(start), mEnd(end) {}
    virtual ~cM3dGLin() {}
    void SetStartEnd(const cXyz& start, const cXyz& end) {
        mStart = start;
        mEnd = end;
    }

    void SetEnd(const cXyz& pos) { mEnd = pos; }
    const cXyz* GetStartP() const { return &mStart; }
    cXyz* GetStartP() { return &mStart; }
    const cXyz& GetStart() const { return mStart; }
    cXyz& GetStart() { return mStart; }
    const cXyz* GetEndP() const { return &mEnd; }
    cXyz* GetEndP() { return &mEnd; }
    const cXyz& GetEnd() const { return mEnd; }
    cXyz& GetEnd() { return mEnd; }
};

#endif
