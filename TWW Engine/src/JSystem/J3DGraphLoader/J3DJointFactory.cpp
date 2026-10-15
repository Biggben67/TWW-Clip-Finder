// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DJointFactory.cpp - J3DJointFactory::create (J3DJointFactory.cpp:19-34).
// The constructor is not copied: JSUConvertOffsetToPtr truncates the pointer to 32 bits.
// boundary/stubs.cpp stands in for it.

#include "JSystem/J3DGraphLoader/J3DJointFactory.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"


J3DJoint* J3DJointFactory::create(int jntNo) {
    J3DJoint* joint = new J3DJoint();
    joint->mJntNo = jntNo;
    joint->mKind = getKind(jntNo);
    joint->mScaleCompensate = getScaleCompensate(jntNo);
    joint->mTransformInfo = getTransformInfo(jntNo);
    joint->mRadius = getRadius(jntNo);
    joint->mMin = getMin(jntNo);
    joint->mMax = getMax(jntNo);
    joint->mMtxCalc = NULL;
    joint->mOldMtxCalc = NULL;
    if (joint->mScaleCompensate == 0xFF) {
        joint->mScaleCompensate = false;
    }
    return joint;
}
