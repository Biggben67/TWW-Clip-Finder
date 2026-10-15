// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DModel.cpp - J3DModel::calcAnmMtx, the entry to the skeleton pass
// (J3DModel.cpp:487-497).

#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "JSystem/J3DGraphAnimator/J3DModelData.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"


void J3DModel::calcAnmMtx() {
    j3dSys.setModel(this);
    j3dSys.setCurrentMtxCalc(getModelData()->getBasicMtxCalc());

    if (checkFlag(J3DMdlFlag_Unk00002))
        j3dSys.getCurrentMtxCalc()->init(j3dDefaultScale, j3dDefaultMtx);
    else
        j3dSys.getCurrentMtxCalc()->init(mBaseScale, mBaseTransformMtx);

    getModelData()->getBasicMtxCalc()->recursiveCalc(getModelData()->getRootNode());
}
