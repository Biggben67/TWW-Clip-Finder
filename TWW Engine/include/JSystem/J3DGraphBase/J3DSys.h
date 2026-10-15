// J3DSys.h - j3dSys trimmed to the calc chain's state; the rest is render state. The layout is
// not the decomp's (0x128 bytes); nothing casts or indexes a J3DSys. setModel's J3D_ASSERT is
// dropped.
#ifndef TWW_PORT_J3DSYS_H
#define TWW_PORT_J3DSYS_H

#include "dolphin/types.h"

class J3DMtxCalc;
class J3DModel;

struct J3DSys {
public:
    void setModel(J3DModel* pModel) { mModel = pModel; }
    J3DModel* getModel() { return mModel; }

    void setCurrentMtxCalc(J3DMtxCalc* pCalc) { mCurrentMtxCalc = pCalc; }
    J3DMtxCalc* getCurrentMtxCalc() { return mCurrentMtxCalc; }

    // Static in the decomp; per thread here, since the library runs one player per thread.
    static thread_local Mtx mCurrentMtx;
    static thread_local Vec mCurrentS;
    static thread_local Vec mParentS;

    J3DMtxCalc* mCurrentMtxCalc;
    J3DModel* mModel;
};

extern thread_local J3DSys j3dSys;

#endif
