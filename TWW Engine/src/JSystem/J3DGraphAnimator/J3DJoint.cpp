// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DJoint.cpp - recursiveCalc, the Basic and Maya calcTransform, and J3DJoint's initialize
// / calcIn / calcOut (J3DJoint.cpp:17-27, 30, 33-54, 57-85, 88-91, 140-184, 187-198,
// 211-218, 221-227).
// Link uses mDoExt_MtxCalcAnmBlendTblOld (m_Do_ext.cpp), so the two calcTransform bodies
// are not on his path.

#include "JSystem/J3DGraphAnimator/J3DJoint.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "JSystem/J3DGraphAnimator/J3DModelData.h"


void J3DMtxCalcAnm::calc(u16 jnt_no) {
    j3dSys.setCurrentMtxCalc(this);
    J3DTransformInfo info;
    J3DAnmTransform* transform = mOne[0];
    if (transform) {
        transform->getTransform(jnt_no, &info);
    } else {
        info = j3dSys.getModel()->getModelData()->getJointNodePointer(jnt_no)->getTransformInfo();
    }
    calcTransform(jnt_no, info);
}

J3DMtxCalcBasic::J3DMtxCalcBasic() {}

void J3DMtxCalcBasic::recursiveCalc(J3DNode* node) {
    if (!node) {
        return;
    }
    J3DMtxCalcBasic mtxCalc;
    MTXCopy(J3DSys::mCurrentMtx, mtxCalc.getBackupMtx());
    mtxCalc.setBackupS(J3DSys::mCurrentS);
    mtxCalc.setBackupParentS(J3DSys::mParentS);
    node->calcIn();
    if (node->getCallBack()) {
        node->getCallBack()(node, J3DNodeCBCalcTiming_In);
    }
    recursiveCalc(node->getChild());
    MTXCopy(mtxCalc.getBackupMtx(), J3DSys::mCurrentMtx);
    J3DSys::mCurrentS = mtxCalc.getBackupS();
    J3DSys::mParentS = mtxCalc.getBackupParentS();
    node->calcOut();
    if (node->getCallBack()) {
        node->getCallBack()(node, J3DNodeCBCalcTiming_Out);
    }
    recursiveCalc(node->getYounger());
}

void J3DMtxCalcBasic::calcTransform(u16 jnt_no, const J3DTransformInfo& info) {
    J3DSys::mCurrentS.x *= info.mScale.x;
    J3DSys::mCurrentS.y *= info.mScale.y;
    J3DSys::mCurrentS.z *= info.mScale.z;
    s32 r29;
    if (checkScaleOne(J3DSys::mCurrentS)) {
        j3dSys.getModel()->setScaleFlag(jnt_no, 1);
        r29 = 1;
    } else {
        j3dSys.getModel()->setScaleFlag(jnt_no, 0);
        r29 = 0;
    }
    Mtx mtx;
    J3DGetTranslateRotateMtx(info, mtx);
    if (r29 == 0) {
        mtx[0][0] *= info.mScale.x;
        mtx[0][1] *= info.mScale.y;
        mtx[0][2] *= info.mScale.z;
        mtx[1][0] *= info.mScale.x;
        mtx[1][1] *= info.mScale.y;
        mtx[1][2] *= info.mScale.z;
        mtx[2][0] *= info.mScale.x;
        mtx[2][1] *= info.mScale.y;
        mtx[2][2] *= info.mScale.z;
    }
    MTXConcat(J3DSys::mCurrentMtx, mtx, J3DSys::mCurrentMtx);
    J3DModel* model = j3dSys.getModel();
    model->setAnmMtx(jnt_no, J3DSys::mCurrentMtx);
}

void J3DMtxCalcBasic::calc(u16 jnt_no) {
    j3dSys.setCurrentMtxCalc(this);
    calcTransform(jnt_no, j3dSys.getModel()->getModelData()->getJointNodePointer(jnt_no)->getTransformInfo());
}

void J3DMtxCalcMaya::calcTransform(u16 jnt_no, const J3DTransformInfo& param_2) {
    J3DModel* model = j3dSys.getModel();
    u8 scaleCompensate = model->getModelData()->getJointNodePointer(jnt_no)->getScaleCompensate();
    s32 tmp;
    if (param_2.mScale.x == 1.0f && param_2.mScale.y == 1.0f && param_2.mScale.z == 1.0f) {
        model->setScaleFlag(jnt_no, 1);
        tmp = true;
    } else {
        model->setScaleFlag(jnt_no, 0);
        tmp = false;
    }
    Mtx mtx;
    J3DGetTranslateRotateMtx(param_2, mtx);
    if (tmp == 0) {
        mtx[0][0] *= param_2.mScale.x;
        mtx[0][1] *= param_2.mScale.y;
        mtx[0][2] *= param_2.mScale.z;
        mtx[1][0] *= param_2.mScale.x;
        mtx[1][1] *= param_2.mScale.y;
        mtx[1][2] *= param_2.mScale.z;
        mtx[2][0] *= param_2.mScale.x;
        mtx[2][1] *= param_2.mScale.y;
        mtx[2][2] *= param_2.mScale.z;
    }
    if (scaleCompensate == 1) {
        f32 x = 1.0f / J3DSys::mParentS.x;
        f32 y = 1.0f / J3DSys::mParentS.y;
        f32 z = 1.0f / J3DSys::mParentS.z;
        mtx[0][0] *= x;
        mtx[0][1] *= x;
        mtx[0][2] *= x;
        mtx[1][0] *= y;
        mtx[1][1] *= y;
        mtx[1][2] *= y;
        mtx[2][0] *= z;
        mtx[2][1] *= z;
        mtx[2][2] *= z;
    }
    MTXConcat(J3DSys::mCurrentMtx, mtx, J3DSys::mCurrentMtx);
    model = j3dSys.getModel();
    model->setAnmMtx(jnt_no, J3DSys::mCurrentMtx);
    J3DSys::mParentS.x = param_2.mScale.x;
    J3DSys::mParentS.y = param_2.mScale.y;
    J3DSys::mParentS.z = param_2.mScale.z;
}

void J3DJoint::initialize() {
    mJntNo = 0;
    mKind = 1;
    mScaleCompensate = 0;
    mTransformInfo = j3dDefaultTransformInfo;
    mRadius = 0.0f;
    mMin = J3D_VEC(0.0f, 0.0f, 0.0f);
    mMax = J3D_VEC(0.0f, 0.0f, 0.0f);
    mMtxCalc = NULL;
    mOldMtxCalc = NULL;
    mMesh = NULL;
}

void J3DJoint::calcIn() {
    if (mMtxCalc) {
        mOldMtxCalc = j3dSys.getCurrentMtxCalc();
        mMtxCalc->calc(mJntNo);
    } else if (j3dSys.getCurrentMtxCalc()) {
        j3dSys.getCurrentMtxCalc()->calc(mJntNo);
    }
}

void J3DJoint::calcOut() {
    if (!mOldMtxCalc) {
        return;
    }
    j3dSys.setCurrentMtxCalc(mOldMtxCalc);
    mOldMtxCalc = NULL;
}
