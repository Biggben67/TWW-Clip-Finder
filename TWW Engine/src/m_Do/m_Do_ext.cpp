// Generated from the zeldaret/tww decomp. Do not hand-edit.
// m_Do_ext.cpp - mDoExt_setJ3DData, both blend-table calc bodies and the old-frame morf
// (m_Do_ext.cpp:23-66, 1128-1165, 1168-1228, 1231-1248, 1251-1268).
// The Old calc goes through the quaternion path even for one animation; the base takes the
// euler one when mNum == 1.

#include "m_Do/m_Do_ext.h"
#include "m_Do/m_Do_mtx.h"
#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "JSystem/J3DGraphAnimator/J3DModelData.h"
#include "JSystem/JMath/JMath.h"
#include "SSystem/SComponent/c_m3d.h"


void mDoExt_setJ3DData(Mtx mtx, const J3DTransformInfo* transformInfo, u16 jnt_no) {
    bool local_28;
    if (cM3d_IsZero(transformInfo->mScale.x - 1.0f) && cM3d_IsZero(transformInfo->mScale.y - 1.0f) && cM3d_IsZero(transformInfo->mScale.z - 1.0f)) {
        j3dSys.getModel()->setScaleFlag(jnt_no, 1);
        local_28 = true;
    } else {
        j3dSys.getModel()->setScaleFlag(jnt_no, 0);
        local_28 = false;
    }
    mtx[0][3] = transformInfo->mTranslate.x;
    mtx[1][3] = transformInfo->mTranslate.y;
    mtx[2][3] = transformInfo->mTranslate.z;

    if (!local_28) {
        mtx[0][0] *= transformInfo->mScale.x;
        mtx[0][1] *= transformInfo->mScale.y;
        mtx[0][2] *= transformInfo->mScale.z;
        mtx[1][0] *= transformInfo->mScale.x;
        mtx[1][1] *= transformInfo->mScale.y;
        mtx[1][2] *= transformInfo->mScale.z;
        mtx[2][0] *= transformInfo->mScale.x;
        mtx[2][1] *= transformInfo->mScale.y;
        mtx[2][2] *= transformInfo->mScale.z;
    }
    if (j3dSys.getModel()->getModelData()->getJointNodePointer(jnt_no)->getScaleCompensate() == 1) {
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
    mDoMtx_concat(J3DSys::mCurrentMtx, mtx, J3DSys::mCurrentMtx);
    j3dSys.getModel()->setAnmMtx(jnt_no, J3DSys::mCurrentMtx);
    J3DSys::mParentS.x = transformInfo->mScale.x;
    J3DSys::mParentS.y = transformInfo->mScale.y;
    J3DSys::mParentS.z = transformInfo->mScale.z;
}

void mDoExt_MtxCalcAnmBlendTbl::calc(u16 jnt_no) {
    j3dSys.setCurrentMtxCalc(this);
    if (mNum == 1) {
        J3DTransformInfo info1;
        mAnmRatio->getAnmTransform()->getTransform(jnt_no, &info1);
        calcTransform(jnt_no, info1);
        return;
    }
    J3DTransformInfo info2;
    Quaternion quat1;
    Quaternion quat2;
    Quaternion quat3;
    mAnmRatio->getAnmTransform()->getTransform(jnt_no, &info2);
    JMAEulerToQuat(info2.mRotation.x, info2.mRotation.y, info2.mRotation.z, &quat1);
    f32 f30 = mAnmRatio[0].getRatio();
    quat3 = quat1;
    for (int i = 1; i < mNum; i++) {
        J3DAnmTransform* transform = mAnmRatio[i].getAnmTransform();
        if (transform) {
            J3DTransformInfo info3;
            transform->getTransform(jnt_no, &info3);
            f32 ratio = mAnmRatio[i].getRatio();
            f30 = 1.0f - ratio;
            JMAEulerToQuat(info3.mRotation.x, info3.mRotation.y, info3.mRotation.z, &quat2);
            JMAQuatLerp(&quat1, &quat2, ratio, &quat3);
            quat1 = quat3;
            info2.mTranslate.x = info2.mTranslate.x * f30 + info3.mTranslate.x * ratio;
            info2.mTranslate.y = info2.mTranslate.y * f30 + info3.mTranslate.y * ratio;
            info2.mTranslate.z = info2.mTranslate.z * f30 + info3.mTranslate.z * ratio;
            info2.mScale.x = info2.mScale.x * f30 + info3.mScale.x * ratio;
            info2.mScale.y = info2.mScale.y * f30 + info3.mScale.y * ratio;
            info2.mScale.z = info2.mScale.z * f30 + info3.mScale.z * ratio;
        }
    }
    Mtx mtx;
    MTXQuat(mtx, &quat3);
    mDoExt_setJ3DData(mtx, &info2, jnt_no);
}

void mDoExt_MtxCalcAnmBlendTblOld::calc(u16 jnt_no) {
    j3dSys.setCurrentMtxCalc(this);
    J3DTransformInfo info1;
    Quaternion quat1;
    Quaternion quat2;
    Quaternion quat3;
    mAnmRatio->getAnmTransform()->getTransform(jnt_no, &info1);
    JMAEulerToQuat(info1.mRotation.x, info1.mRotation.y, info1.mRotation.z, &quat1);
    quat3 = quat1;
    for (int i = 1; i < mNum; i++) {
        if (mAnmRatio[i].getAnmTransform()) {
            J3DAnmTransform* transform = mAnmRatio[i].getAnmTransform();
            J3DTransformInfo info2;
            transform->getTransform(jnt_no, &info2);
            f32 ratio = mAnmRatio[i].getRatio();
            f32 f30 = 1.0f - ratio;
            JMAEulerToQuat(info2.mRotation.x, info2.mRotation.y, info2.mRotation.z, &quat2);
            JMAQuatLerp(&quat1, &quat2, ratio, &quat3);
            quat1 = quat3;
            info1.mTranslate.x = info1.mTranslate.x * f30 + info2.mTranslate.x * ratio;
            info1.mTranslate.y = info1.mTranslate.y * f30 + info2.mTranslate.y * ratio;
            info1.mTranslate.z = info1.mTranslate.z * f30 + info2.mTranslate.z * ratio;
            info1.mScale.x = info1.mScale.x * f30 + info2.mScale.x * ratio;
            info1.mScale.y = info1.mScale.y * f30 + info2.mScale.y * ratio;
            info1.mScale.z = info1.mScale.z * f30 + info2.mScale.z * ratio;
        }
    }

    J3DModel* model = j3dSys.getModel();
    J3DTransformInfo* oldTransInfo = mOldFrame->getOldFrameTransInfo(jnt_no);
    Quaternion* oldQuat = mOldFrame->getOldFrameQuaternion(jnt_no);
    if (mOldFrame->getOldFrameFlg()) {
        if (mOldFrame->getOldFrameRate() > 0.0f && mOldFrame->getOldFrameStartJoint() <= jnt_no && mOldFrame->getOldFrameEndJoint() > jnt_no) {
            f32 oldFrameRate = mOldFrame->getOldFrameRate();
            f32 f31 = 1.0f - oldFrameRate;
            JMAQuatLerp(oldQuat, &quat1, f31, &quat3);
            info1.mTranslate.x = info1.mTranslate.x * f31 + oldTransInfo->mTranslate.x * oldFrameRate;
            info1.mTranslate.y = info1.mTranslate.y * f31 + oldTransInfo->mTranslate.y * oldFrameRate;
            info1.mTranslate.z = info1.mTranslate.z * f31 + oldTransInfo->mTranslate.z * oldFrameRate;
            info1.mScale.x = info1.mScale.x * f31 + oldTransInfo->mScale.x * oldFrameRate;
            info1.mScale.y = info1.mScale.y * f31 + oldTransInfo->mScale.y * oldFrameRate;
            info1.mScale.z = info1.mScale.z * f31 + oldTransInfo->mScale.z * oldFrameRate;
        }
    } else if (jnt_no == model->getModelData()->getJointNum() - 1) {
        mOldFrame->onOldFrameFlg();
    }
    Mtx mtx;
    if (mBeforeCallback) {
        mBeforeCallback(mUserArea, jnt_no, &info1, &quat3);
    }
    mDoMtx_quat(mtx, &quat3);
    mDoExt_setJ3DData(mtx, &info1, jnt_no);
    if (mAfterCallback) {
        mAfterCallback(mUserArea, jnt_no, &info1, &quat3);
    }
    *oldQuat = quat3;
    *oldTransInfo = info1;
    if (jnt_no == model->getModelData()->getJointNum() - 1) {
        mOldFrame->decOldFrameMorfCounter();
    }
}

void mDoExt_MtxCalcOldFrame::initOldFrameMorf(f32 i_morf, u16 i_frameStartJoint, u16 i_frameEndJoint) {
    if (i_morf > 0.0f) {
        mOldFrameMorfCounter = i_morf;
        field_0x8 = 1.0f / i_morf;
        mOldFrameRate = 1.0f;
        field_0x10 = 1.0f;
        field_0x14 = 1.0f;
        decOldFrameMorfCounter();
    } else {
        mOldFrameMorfCounter = 0.0f;
        field_0x8 = 0.0f;
        mOldFrameRate = 0.0f;
        field_0x10 = 0.0f;
        field_0x14 = 0.0f;
    }
    mOldFrameStartJoint = i_frameStartJoint;
    mOldFrameEndJoint = i_frameEndJoint;
}

void mDoExt_MtxCalcOldFrame::decOldFrameMorfCounter() {
    if (!(mOldFrameMorfCounter > 0.0f)) {
        return;
    }
    mOldFrameMorfCounter -= 1.0f;
    if (mOldFrameMorfCounter <= 0.0f) {
        mOldFrameMorfCounter = 0.0f;
        field_0x8 = 0.0f;
        mOldFrameRate = 0.0f;
    }
    field_0x14 = field_0x10;
    field_0x10 = mOldFrameMorfCounter * field_0x8;
    if (field_0x14 > 0.0f) {
        mOldFrameRate = 1.0f - (field_0x14 - field_0x10) / field_0x14;
        return;
    }
    mOldFrameRate = 0.0f;
}
