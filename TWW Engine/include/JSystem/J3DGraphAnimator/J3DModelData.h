// J3DModelData.h - J3DModelData trimmed to the four accessors the calc chain uses, with the
// J3DJointTree forwarding hop removed (not carried). Filled from a generated table rather than a
// parsed .bmd; the layout is not the decomp's (0xE4 bytes).
#ifndef TWW_PORT_J3DMODELDATA_H
#define TWW_PORT_J3DMODELDATA_H

#include "dolphin/types.h"

class J3DJoint;
class J3DMtxCalc;

// J3DJointTree.h:10-15, whole.
struct J3DModelHierarchy {
    /* 0x0 */ u16 mType; // TODO enum
    /* 0x2 */ u16 mValue;

    inline u16 getValue() const { return mValue; }
};

class J3DModelData {
public:
    u16 getJointNum() const { return mJointNum; }
    J3DJoint* getJointNodePointer(u16 idx) const { return mJointNodePointer[idx]; }
    J3DJoint* getRootNode() { return mRootNode; }
    J3DMtxCalc* getBasicMtxCalc() { return mBasicMtxCalc; }
    void setBasicMtxCalc(J3DMtxCalc* calc) { mBasicMtxCalc = calc; }

    u16 mJointNum;
    J3DJoint** mJointNodePointer;
    J3DJoint* mRootNode;
    J3DMtxCalc* mBasicMtxCalc;
};

#endif
