// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DNode.cpp - the constructor, destructor and appendChild (J3DNode.cpp:11-16, 19-20,
// 23-33).

#include "JSystem/J3DGraphAnimator/J3DNode.h"


J3DNode::J3DNode() {
    mCallBackUserData = NULL;
    mCallBack = NULL;
    mChild = NULL;
    mYounger = NULL;
}

J3DNode::~J3DNode() {
}

void J3DNode::appendChild(J3DNode* pChild) {
    if (mChild == NULL) {
        mChild = pChild;
    } else {
        J3DNode* curChild = mChild;
        while (curChild->getYounger() != NULL) {
            curChild = curChild->getYounger();
        }
        curChild->setYounger(pChild);
    }
}
