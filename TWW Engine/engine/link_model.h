// link_model.h - Link's skeleton, built without the game's loader.
//
// The calc chain (J3DModel::calcAnmMtx, J3DMtxCalcBasic::recursiveCalc, J3DJoint::calcIn/calcOut,
// mDoExt_MtxCalcAnmBlendTblOld::calc, mDoExt_setJ3DData, J3DJointFactory::create) is copied. The
// load - parsing cl.bdl, allocating joints, J3DJointTree::makeHierarchy - is written here.
//
// `makeHierarchy` in link_model.cpp is J3DJointTree::makeHierarchy (J3DModelData.cpp:32-95) cut
// to the joint arm. Material and shape nodes are skipped rather than removed, since the brackets
// around them give joints their parents. The tree and order come from the installed INF1 stream
// (engine/link_assets.h); nothing here chooses them.
#ifndef TWW_ENGINE_LINK_MODEL_H
#define TWW_ENGINE_LINK_MODEL_H

#include "dolphin/types.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"
#include "JSystem/J3DGraphAnimator/J3DModel.h"
#include "JSystem/J3DGraphAnimator/J3DModelData.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "m_Do/m_Do_ext.h"

namespace tww_engine {

/// Link's joint count.
int linkJointNum();

/// Joint `i` in the order the installed INF1 stream lists joints.
u16 linkVisitOrder(int i);

/// Link's model: 42 joints, the tree, the model data and the anmMtx array. `mBasic` is the
/// J3DMtxCalcMaya the .bmd asks for (INF1 mFlags & 0xF == 2). Aborts if assets are not installed.
struct LinkModel {
    /// `scaleCompensate` false clears every joint's mScaleCompensate before the factory reads it
    /// (a data mutation for tests: the 1/mParentS divide is then skipped).
    explicit LinkModel(bool scaleCompensate = true);

    J3DModel* model() { return &mModel; }
    J3DModelData* modelData() { return &mModelData; }
    J3DJoint* joint(int i) { return mJointPtr[i]; }

    /// The model's base transform, where the FK starts.
    void setBase(const Mtx base);

    /// Install one mtx calc on every joint, as the player installs its PART_UNDER calc.
    void setMtxCalcOnAllJoints(J3DMtxCalc* calc);

    J3DMtxCalcMaya mBasic;

private:
    J3DJoint mJoints[42];
    J3DJoint* mJointPtr[42];
    Mtx mAnmMtx[42];
    u8 mScaleFlag[42];
    J3DModelData mModelData;
    J3DModel mModel;
};

/// A standalone PART_UNDER blend calc with its old-frame storage (one J3DTransformInfo and one
/// Quaternion per joint), for tests without a player.
struct LinkUnderCalc {
    LinkUnderCalc(int animNum);

    mDoExt_MtxCalcAnmBlendTblOld* calc() { return &mCalc; }
    mDoExt_MtxCalcOldFrame* oldFrame() { return &mOldFrame; }
    void setAnim(int i, J3DAnmTransform* anm, f32 ratio);

private:
    J3DTransformInfo mOldInfo[42];
    Quaternion mOldQuat[42];
    mDoExt_AnmRatioPack mRatio[4];
    mDoExt_MtxCalcOldFrame mOldFrame;
    mDoExt_MtxCalcAnmBlendTblOld mCalc;
};

}  // namespace tww_engine

#endif
