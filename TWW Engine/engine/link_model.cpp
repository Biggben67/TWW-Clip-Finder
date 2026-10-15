#include "engine/link_model.h"

#include <cstdio>
#include <cstdlib>

#include "JSystem/J3DGraphBase/J3DSys.h"
#include "JSystem/J3DGraphBase/J3DTransform.h"
#include "JSystem/J3DGraphLoader/J3DJointFactory.h"

// The J3DSys statics the calc chain threads through, and its instance. Defined here because this
// port's J3DSys is a trim (include/JSystem/J3DGraphBase/J3DSys.h), not a copy.
thread_local Mtx J3DSys::mCurrentMtx;
thread_local Vec J3DSys::mCurrentS;
thread_local Vec J3DSys::mParentS;
thread_local J3DSys j3dSys;

#include "engine/link_assets.h"

namespace tww_engine {

int linkJointNum() { return kLinkJointNum; }

u16 linkVisitOrder(int i) { return linkSkeleton().visit[static_cast<size_t>(i)]; }

namespace {

/// J3DJointTree::makeHierarchy (J3DModelData.cpp:32-95), cut to the joint arm. `i` is the node to
/// start at and `root` the node every joint at this level is appended to; returns the index just
/// past the bracket this level closes.
int makeHierarchy(int i, J3DJoint* root, J3DJoint** joints, J3DJoint** outRoot) {
    J3DJoint* cur = root;
    const std::vector<J3DModelHierarchy>& stream = linkSkeleton().hierarchy;
    while (i < (int)stream.size()) {
        const J3DModelHierarchy& inf = stream[static_cast<size_t>(i)];
        if (inf.mType == 0x01) {            // kTypeBeginChild
            i = makeHierarchy(i + 1, cur, joints, outRoot);
        } else if (inf.mType == 0x02) {     // kTypeEndChild
            return i + 1;
        } else if (inf.mType == 0x10) {     // kTypeJoint
            i += 1;
            J3DJoint* node = joints[inf.getValue()];
            cur = node;
            if (root == NULL) {
                *outRoot = node;
            } else {
                root->appendChild(node);
            }
        } else {                            // a material or a shape: pCurNode is untouched
            i += 1;
        }
    }
    return i;
}

}  // namespace

LinkModel::LinkModel(bool scaleCompensate) {
    if (!linkAssetsInstalled()) {
        std::fprintf(stderr, "tww_engine: a Session was built before installLinkAssets\n");
        std::abort();
    }
    const LinkSkeleton& skeleton = linkSkeleton();
    std::vector<J3DJointInitData> init(skeleton.joints);
    for (size_t i = 0; i < init.size(); i++) {
        if (!scaleCompensate) {
            init[i].mScaleCompensate = false;
        }
    }

    // The JNT1 block the loader would hand the factory. Its tables are pointers where the
    // console's are offsets (see the factory constructor in boundary/stubs.cpp).
    J3DJointBlock block;
    block.mMagic = 0;
    block.mSize = 0;
    block.mJointNum = kLinkJointNum;
    block._pad = 0;
    block.mpJointInitData = init.data();
    block.mpIndexTable = const_cast<u16*>(skeleton.index.data());
    block.mpNameTable = NULL;
    J3DJointFactory factory(block);

    for (int i = 0; i < kLinkJointNum; i++) {
        // create() news a J3DJoint; copy it into owned storage and free it.
        J3DJoint* made = factory.create(i);
        mJoints[i] = *made;
        delete made;
        mJointPtr[i] = &mJoints[i];
        mScaleFlag[i] = 0;
    }

    J3DJoint* root = NULL;
    makeHierarchy(0, NULL, mJointPtr, &root);

    mModelData.mJointNum = kLinkJointNum;
    mModelData.mJointNodePointer = mJointPtr;
    mModelData.mRootNode = root;
    mModelData.mBasicMtxCalc = &mBasic;

    mModel.mModelData = &mModelData;
    mModel.mFlags = 0;
    mModel.mBaseScale = j3dDefaultScale;
    MTXCopy(j3dDefaultMtx, mModel.mBaseTransformMtx);
    mModel.mpScaleFlagArr = mScaleFlag;
    mModel.mpNodeMtx = mAnmMtx;

    // Zeroed, so a never-posed model reads zero matrices rather than indeterminate ones. The
    // first calcAnmMtx overwrites all 42.
    for (int i = 0; i < kLinkJointNum; i++) {
        for (int r = 0; r < 3; r++) {
            for (int col = 0; col < 4; col++) {
                mAnmMtx[i][r][col] = 0.0f;
            }
        }
    }
}

void LinkModel::setBase(const Mtx base) { MTXCopy(base, mModel.mBaseTransformMtx); }

void LinkModel::setMtxCalcOnAllJoints(J3DMtxCalc* calc) {
    for (int i = 0; i < kLinkJointNum; i++) {
        mJoints[i].setMtxCalc(calc);
    }
}

LinkUnderCalc::LinkUnderCalc(int animNum)
    : mOldFrame(mOldInfo, mOldQuat), mCalc(&mOldFrame, animNum, mRatio) {
    for (int i = 0; i < kLinkJointNum; i++) {
        mOldInfo[i] = j3dDefaultTransformInfo;
        mOldQuat[i].x = mOldQuat[i].y = mOldQuat[i].z = 0.0f;
        mOldQuat[i].w = 1.0f;
    }
}

void LinkUnderCalc::setAnim(int i, J3DAnmTransform* anm, f32 ratio) {
    mRatio[i].setAnmTransform(anm);
    mRatio[i].setRatio(ratio);
}

}  // namespace tww_engine
