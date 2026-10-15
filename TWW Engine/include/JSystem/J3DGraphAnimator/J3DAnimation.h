// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DAnimation.h - the key-table structs, J3DAnmBase, J3DAnmTransform, J3DAnmTransformKey
// and J3DFrameCtrl (J3DAnimation.h:8-12, 40-44, 308-329, 331-352, 353-371, 824-872).

#ifndef TWW_PORT_J3DANIMATION_H
#define TWW_PORT_J3DANIMATION_H

#include "dolphin/types.h"
#include "JSystem/J3DGraphBase/J3DTransform.h"

struct J3DAnmKeyTableBase {
    /* 0x00 */ u16 mMaxFrame;
    /* 0x02 */ u16 mOffset;
    /* 0x04 */ u16 mType;
};  // Size = 0x6

struct J3DAnmTransformKeyTable {
    /* 0x00 */ J3DAnmKeyTableBase mScale;
    /* 0x06 */ J3DAnmKeyTableBase mRotation;
    /* 0x0C */ J3DAnmKeyTableBase mTranslate;
};  // Size = 0x12

class J3DAnmBase {
public:
    J3DAnmBase(s16 i_frameMax) {
        mFrame = 0.0f;
        mFrameMax = i_frameMax;
    }

    virtual ~J3DAnmBase() {}

    u8 getAttribute() const { return mAttribute; }
    s16 getFrameMax() const { return mFrameMax; }
    f32 getFrame() const { return mFrame; }
    void setFrame(f32 frame) { mFrame = frame; }
    s32 getKind() const { return mKind; }

protected:
    /* 0x4 */ u8 mAttribute;
    /* 0x5 */ u8 field_0x5;
    /* 0x6 */ s16 mFrameMax;
    /* 0x8 */ f32 mFrame;
    /* 0xC */ s32 mKind;
};  // Size: 0x10

class J3DAnmTransform : public J3DAnmBase {
public:
    J3DAnmTransform(s16 i_frameMax, f32* scaleData, s16* rotData, f32* transData) : J3DAnmBase(i_frameMax) {
        mScaleData = scaleData;
        mRotData = rotData;
        mTransData = transData;
        mKind = 0;
    }

    virtual ~J3DAnmTransform() {}
    virtual void getTransform(u16, J3DTransformInfo*) const {}

protected:
    /* 0x10 */ f32* mScaleData;
    /* 0x14 */ s16* mRotData;
    /* 0x18 */ f32* mTransData;
    /* 0x1C */ s16 field_0x1c;
    /* 0x1E */ s16 field_0x1e;
    /* 0x20 */ u16 field_0x20;
    /* 0x22 */ u16 field_0x22;
};  // Size: 0x24


// BCK
class J3DAnmTransformKey : public J3DAnmTransform {
public:
    friend class J3DAnmKeyLoader_v15;

    J3DAnmTransformKey() : J3DAnmTransform(0, NULL, NULL, NULL) {
        mDecShift = 0;
        mAnmTable = NULL;
    }

    virtual void calcTransform(f32, u16, J3DTransformInfo*) const;

    virtual ~J3DAnmTransformKey() {}
    virtual void getTransform(u16 idx, J3DTransformInfo* dst) const { calcTransform(getFrame(), idx, dst); }

private:
    /* 0x24 */ int mDecShift;
    /* 0x28 */ J3DAnmTransformKeyTable* mAnmTable;
};  // Size: 0x2C

class J3DFrameCtrl {
public:
    enum Attribute_e {
        /*  -1 */ EMode_NULL = -1,
        /* 0x0 */ EMode_NONE,
        /* 0x1 */ EMode_RESET,
        /* 0x2 */ EMode_LOOP,
        /* 0x3 */ EMode_REVERSE,
        /* 0x4 */ EMode_LOOP_REVERSE,
    };

    enum State_e {
        /* 0x1 */ STATE_STOP_E = 0x1,
        /* 0x2 */ STATE_LOOP_E = 0x2,
    };

    J3DFrameCtrl() { this->init(0); }
    void init(s16 end);
    BOOL checkPass(f32);
    void update();
    virtual ~J3DFrameCtrl() {}

    u8 getAttribute() const { return mAttribute; }
    void setAttribute(u8 attr) { mAttribute = attr; }
    u8 getState() const { return mState; }
    void restoreState(u8 state) { mState = state; }
    bool checkState(u8 state) const { return mState & state ? true : false; }
    s16 getStart() const { return mStart; }
    void setStart(s16 start) {
        mStart = start;
        mFrame = start;
    }
    s16 getEnd() const { return mEnd; }
    void setEnd(s16 end) { mEnd = end; }
    s32 getLoop() const { return mLoop; }
    void setLoop(s16 loop) { mLoop = loop; }
    f32 getRate() const { return mRate; }
    void setRate(f32 rate) { mRate = rate; }
    f32 getFrame() const { return mFrame; }
    void setFrame(f32 frame) { mFrame = frame; }

private:
    /* 0x04 */ u8 mAttribute;
    /* 0x05 */ u8 mState;
    /* 0x06 */ s16 mStart;
    /* 0x08 */ s16 mEnd;
    /* 0x0A */ s16 mLoop;
    /* 0x0C */ f32 mRate;
    /* 0x10 */ f32 mFrame;
};  // Size: 0x14

#endif
