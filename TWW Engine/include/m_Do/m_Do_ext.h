// Generated from the zeldaret/tww decomp. Do not hand-edit.
// m_Do_ext.h - mDoExt_AnmRatioPack, mDoExt_MtxCalcOldFrame and the two blend-table mtx
// calcs (m_Do_ext.h:187-203, 216-258, 260-280, 282-301). mDoExt_MtxCalcAnmBlendTblOld is
// Link's (d_a_player_main.cpp:12023, 12026).

#ifndef TWW_PORT_M_DO_EXT_H
#define TWW_PORT_M_DO_EXT_H

#include "dolphin/types.h"
#include "global.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"
#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "JSystem/J3DGraphBase/J3DTransform.h"

void mDoExt_setJ3DData(Mtx mtx, const J3DTransformInfo* transformInfo, u16 jnt_no);

class mDoExt_AnmRatioPack {
public:
    ~mDoExt_AnmRatioPack() {}
    mDoExt_AnmRatioPack() {
        mRatio = 0.0f;
        mAnmTransform = NULL;
    }

    f32 getRatio() { return mRatio; }
    void setRatio(f32 ratio) { mRatio = ratio; }
    J3DAnmTransform* getAnmTransform() { return mAnmTransform; }
    void setAnmTransform(J3DAnmTransform* anm) { mAnmTransform = anm; }

private:
    /* 0x0 */ f32 mRatio;
    /* 0x4 */ J3DAnmTransform* mAnmTransform;
};  // Size: 0x8

class mDoExt_MtxCalcOldFrame {
public:
    mDoExt_MtxCalcOldFrame(J3DTransformInfo* param_1, Quaternion* param_2) {
        mOldFrameTransInfo = param_1;
        mOldFrameQuaternion = param_2;
        mOldFrameRate = 0.0f;
        mOldFrameFlg = false;
        field_0x1 = true;
        mOldFrameStartJoint = 0;
        mOldFrameEndJoint = 0;
        mOldFrameMorfCounter = 0.0f;
        field_0x8 = 0.0f;
#if VERSION > VERSION_DEMO
        field_0x10 = 0.0f;
        field_0x14 = 0.0f;
#endif
    }
    
    void initOldFrameMorf(f32 i_morf, u16 i_frameStartJoint, u16 i_frameEndJoint);
    void decOldFrameMorfCounter();

    bool getOldFrameFlg() { return mOldFrameFlg; }
    void onOldFrameFlg() { mOldFrameFlg = true; }
    f32 getOldFrameRate() { return mOldFrameRate; }
    J3DTransformInfo* getOldFrameTransInfo(int i) { return &mOldFrameTransInfo[i]; }
    u16 getOldFrameStartJoint() { return mOldFrameStartJoint; }
    u16 getOldFrameEndJoint() { return mOldFrameEndJoint; }
    Quaternion* getOldFrameQuaternion(int i_no) { return &mOldFrameQuaternion[i_no]; }
    f32 getOldFrameMorfCounter() { return mOldFrameMorfCounter; }
    void restoreClock(bool flag, bool active, f32 counter, f32 previous, f32 rate,
                      f32 value10, f32 value14, u16 start, u16 end) {
        mOldFrameFlg = flag;
        field_0x1 = active;
        mOldFrameMorfCounter = counter;
        field_0x8 = previous;
        mOldFrameRate = rate;
        field_0x10 = value10;
        field_0x14 = value14;
        mOldFrameStartJoint = start;
        mOldFrameEndJoint = end;
    }

private:
    /* 0x00 */ bool mOldFrameFlg;
    /* 0x01 */ bool field_0x1;
    /* 0x04 */ f32 mOldFrameMorfCounter;
    /* 0x08 */ f32 field_0x8;
    /* 0x0C */ f32 mOldFrameRate;
    /* 0x10 */ f32 field_0x10;
    /* 0x14 */ f32 field_0x14;
    /* 0x18 */ u16 mOldFrameStartJoint;
    /* 0x1A */ u16 mOldFrameEndJoint;
    /* 0x1C */ J3DTransformInfo* mOldFrameTransInfo;
    /* 0x20 */ Quaternion* mOldFrameQuaternion;
};  // Size: 0x24

struct mDoExt_MtxCalcAnmBlendTbl : public J3DMtxCalcMaya {
    mDoExt_MtxCalcAnmBlendTbl(int num, mDoExt_AnmRatioPack* anmRatio) {
        mNum = num;
        mAnmRatio = anmRatio;
        for (int i = 0; i < mNum; i++) {
            if (!mAnmRatio[i].getAnmTransform()) {
                mAnmRatio[i].setRatio(0.0f);
            }
        }
    }

    virtual ~mDoExt_MtxCalcAnmBlendTbl() {};
    virtual void calc(u16);

    f32 getRatio(int i) { return mAnmRatio[i].getRatio(); }
    void setRatio(int i, f32 ratio) { mAnmRatio[i].setRatio(ratio); }
    J3DAnmTransform* getAnmTransform(int i) { return mAnmRatio[i].getAnmTransform(); }

    /* 0x50 */ int mNum;
    /* 0x54 */ mDoExt_AnmRatioPack* mAnmRatio;
};

struct mDoExt_MtxCalcAnmBlendTblOld : public mDoExt_MtxCalcAnmBlendTbl {
    typedef int (*CalcCallback)(u32, u16, J3DTransformInfo*, Quaternion*);

    mDoExt_MtxCalcAnmBlendTblOld(mDoExt_MtxCalcOldFrame* oldFrame, int num, mDoExt_AnmRatioPack* anmRatio) : mDoExt_MtxCalcAnmBlendTbl(num, anmRatio) {
        mOldFrame = oldFrame;
        mBeforeCallback = NULL;
        mAfterCallback = NULL;
        mUserArea = 0;
    }
    virtual void calc(u16);

    void setUserArea(u32 area)  { mUserArea = area; }
    void setBeforeCalc(CalcCallback callback) { mBeforeCallback = callback; }
    void setAfterCalc(CalcCallback callback) { mAfterCallback = callback; }

    /* 0x58 */ u32 mUserArea;
    /* 0x5C */ mDoExt_MtxCalcOldFrame* mOldFrame;
    /* 0x60 */ CalcCallback mBeforeCallback;
    /* 0x64 */ CalcCallback mAfterCallback;
};  // Size: 0x90

#endif
