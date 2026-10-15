// Generated from the zeldaret/tww decomp. Do not hand-edit.
// J3DAnimation.cpp - J3DFrameCtrl::init / checkPass / update and the keyframe sampler
// (J3DAnimation.cpp:12-21, 24-140, 142-210, 368-411, 413-456, 458-516).
// `mFrame += mRate` accumulates f32 rounding; a frame computed as n * rate differs.
// J3DHermiteInterpolationS (322-366) is an asm block in the decomp; engine/j3d_hermite.cpp
// carries it, transcribed from the DOL.

#include "JSystem/J3DGraphAnimator/J3DAnimation.h"
#include "JSystem/JMath/JMath.h"

// The decomp declares this through its include web; the body is engine/j3d_hermite.cpp.
f32 J3DHermiteInterpolationS(f32 t, s16* time0, s16* value0, s16* tangent0,
                             s16* time1, s16* value1, s16* tangent1);

/* 802EF5D8-802EF608       .text init__12J3DFrameCtrlFs */
void J3DFrameCtrl::init(s16 end) {
    mAttribute = EMode_LOOP;
    mState = 0;
    mStart = 0;
    mEnd = end;
    mLoop = 0;
    mRate = 1.0f;
    mFrame = 0.0f;
}

BOOL J3DFrameCtrl::checkPass(f32 pass_frame) {
    f32 cur_frame = mFrame;
    f32 next_frame = cur_frame + mRate;

    switch (mAttribute) {
    case EMode_NONE:
    case EMode_RESET:
        if (next_frame < mStart) {
            next_frame = mStart;
        }

        if (next_frame >= mEnd) {
            next_frame = mEnd - 0.001f;
        }

        if (cur_frame <= next_frame) {
            if (cur_frame <= pass_frame && pass_frame < next_frame) {
                return true;
            } else {
                return false;
            }
        }

        if (next_frame <= pass_frame && pass_frame < cur_frame) {
            return true;
        }
        return false;
    case EMode_LOOP:
        if (cur_frame < mStart) {
            while (next_frame < mStart) {
                if (mLoop - mStart <= 0.0f) {
                    break;
                }
                next_frame += mLoop - mStart;
            }

            if (next_frame <= pass_frame && pass_frame < mLoop) {
                return true;
            } else {
                return false;
            }
        } else if (mEnd <= cur_frame) {
            while (next_frame >= mEnd) {
                if (mEnd - mLoop <= 0.0f) {
                    break;
                }
                next_frame -= mEnd - mLoop;
            }

            if (mLoop <= pass_frame && pass_frame < next_frame) {
                return true;
            } else {
                return false;
            }
        } else if (next_frame < mStart) {
            while (next_frame < mStart) {
                if (mLoop - mStart <= 0.0f) {
                    break;
                }
                next_frame += mLoop - mStart;
            }

            if ((mStart <= pass_frame && pass_frame < cur_frame) || (next_frame <= pass_frame && pass_frame < mLoop)) {
                return true;
            } else {
                return false;
            }
        } else if (mEnd <= next_frame) {
            while (next_frame >= mEnd) {
                if (mEnd - mLoop <= 0.0f) {
                    break;
                }

                next_frame -= mEnd - mLoop;
            }

            if ((cur_frame <= pass_frame && pass_frame < mEnd) || (mLoop <= pass_frame && pass_frame < next_frame)) {
                return true;
            } else {
                return false;
            }
        } else if (cur_frame <= next_frame) {
            if (cur_frame <= pass_frame && pass_frame < next_frame) {
                return true;
            } else {
                return false;
            }
        } else if (next_frame <= pass_frame && pass_frame < cur_frame) {
            return true;
        }
        return false;
    case EMode_REVERSE:
    case EMode_LOOP_REVERSE:
        if (next_frame >= mEnd) {
            next_frame = mEnd - 0.001f;
        }

        if (next_frame < mStart) {
            next_frame = mStart;
        }

        if (cur_frame <= next_frame) {
            if (cur_frame <= pass_frame && pass_frame < next_frame) {
                return true;
            } else {
                return false;
            }
        }

        if (next_frame <= pass_frame && pass_frame < cur_frame) {
            return true;
        }
        return false;
    default:
        return false;
    }
}

/* 802EFBA8-802EFFE4       .text update__12J3DFrameCtrlFv */
void J3DFrameCtrl::update() {
    mState = 0;
    mFrame += mRate;
    switch (mAttribute) {
    case EMode_NONE:
        if (mFrame < mStart) {
            mFrame = mStart;
            mRate = 0.0f;
            mState |= 1;
        }
        if (mFrame >= mEnd) {
            mFrame = mEnd - 0.001f;
            mRate = 0.0f;
            mState |= 1;
        }
        break;
    case EMode_RESET:
        if (mFrame < mStart) {
            mFrame = mStart;
            mRate = 0.0f;
            mState |= 1;
        }
        if (mFrame >= mEnd) {
            mFrame = mStart;
            mRate = 0.0f;
            mState |= 1;
        }
        break;
    case EMode_LOOP:
        while (mFrame < mStart) {
            mState |= 2;
            if (mLoop - mStart <= 0.0f) {
                break;
            }
            mFrame += mLoop - mStart;
        }
        while (mFrame >= mEnd) {
            mState |= 2;
            if (mEnd - mLoop <= 0.0f) {
                break;
            }
            mFrame -= mEnd - mLoop;
        }
        break;
    case EMode_REVERSE:
        if (mFrame >= mEnd) {
            mFrame = mEnd - 0.001f;
            mRate = -mRate;
        }
        if (mFrame < mStart) {
            mFrame = mStart;
            mRate = 0.0f;
            mState |= 1;
        }
        break;
    case EMode_LOOP_REVERSE:
        if (mFrame >= mEnd) {
            mFrame = mEnd - 0.001f;
            mRate = -mRate;
        }
        if (mFrame < mStart) {
            mFrame = mStart;
            mRate = -mRate;
            mState |= 2;
        }
        break;
    }
}

/* 802F072C-802F0954       .text J3DGetKeyFrameInterpolationS__FfP18J3DAnmKeyTableBasePs */
f32 J3DGetKeyFrameInterpolationS(f32 frame, J3DAnmKeyTableBase* table, s16* data) {
    if (table->mType == 0) {
        if (frame < data[0]) {
            return data[1];
        } else if (data[3 * (table->mMaxFrame - 1)] <= frame) {
            return data[3 * (table->mMaxFrame - 1) + 1];
        } else {
            // bisect
            int num = table->mMaxFrame;
            while (num > 1) {
                int mid = num / 2;
                if (frame >= data[3 * mid]) {
                    data += 3 * mid;
                    num -= mid;
                } else {
                    num = mid;
                }
            }

            return J3DHermiteInterpolationS(frame, &data[0], &data[1], &data[2], &data[3], &data[4], &data[5]);
        }
    } else {
        if (frame < data[0]) {
            return data[1];
        } else if (data[4 * (table->mMaxFrame - 1)] <= frame) {
            return data[4 * (table->mMaxFrame - 1) + 1];
        } else {
            // bisect
            int num = table->mMaxFrame;
            while (num > 1) {
                int mid = num / 2;
                if (frame >= data[4 * mid]) {
                    data += 4 * mid;
                    num -= mid;
                } else {
                    num = mid;
                }
            }

            return J3DHermiteInterpolationS(frame, &data[0], &data[1], &data[3], &data[4], &data[5], &data[6]);
        }
    }
}

template <typename T>
f32 J3DGetKeyFrameInterpolation(f32 frame, J3DAnmKeyTableBase* table, T* data) {
    if (table->mType == 0) {
        if (frame < data[0]) {
            return data[1];
        } else if (data[3 * (table->mMaxFrame - 1)] <= frame) {
            return data[3 * (table->mMaxFrame - 1) + 1];
        } else {
            // bisect
            int num = table->mMaxFrame;
            while (num > 1) {
                int mid = num / 2;
                if (frame >= data[3 * mid]) {
                    data += 3 * mid;
                    num -= mid;
                } else {
                    num = mid;
                }
            }

            return JMAHermiteInterpolation(frame, data[0], data[1], data[2], data[3], data[4], data[5]);
        }
    } else {
        if (frame < data[0]) {
            return data[1];
        } else if (data[4 * (table->mMaxFrame - 1)] <= frame) {
            return data[4 * (table->mMaxFrame - 1) + 1];
        } else {
            // bisect
            int num = table->mMaxFrame;
            while (num > 1) {
                int mid = num / 2;
                if (frame >= data[4 * mid]) {
                    data += 4 * mid;
                    num -= mid;
                } else {
                    num = mid;
                }
            }

            return JMAHermiteInterpolation(frame, data[0], data[1], data[3], data[4], data[5], data[6]);
        }
    }
}

/* 802F0954-802F0E20       .text calcTransform__18J3DAnmTransformKeyCFfUsP16J3DTransformInfo */
void J3DAnmTransformKey::calcTransform(f32 frame, u16 idx, J3DTransformInfo* dst) const {
    /* Scale */
    switch (mAnmTable[idx*3 + 0].mScale.mMaxFrame) {
    case 0:  dst->mScale.x = 1.0f; break;
    case 1:  dst->mScale.x = mScaleData[mAnmTable[idx*3 + 0].mScale.mOffset]; break;
    default: dst->mScale.x = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 0].mScale, &mScaleData[mAnmTable[idx*3 + 0].mScale.mOffset]); break;
    }

    switch (mAnmTable[idx*3 + 1].mScale.mMaxFrame) {
    case 0:  dst->mScale.y = 1.0f; break;
    case 1:  dst->mScale.y = mScaleData[mAnmTable[idx*3 + 1].mScale.mOffset]; break;
    default: dst->mScale.y = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 1].mScale, &mScaleData[mAnmTable[idx*3 + 1].mScale.mOffset]); break;
    }

    switch (mAnmTable[idx*3 + 2].mScale.mMaxFrame) {
    case 0:  dst->mScale.z = 1.0f; break;
    case 1:  dst->mScale.z = mScaleData[mAnmTable[idx*3 + 2].mScale.mOffset]; break;
    default: dst->mScale.z = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 2].mScale, &mScaleData[mAnmTable[idx*3 + 2].mScale.mOffset]); break;
    }

    /* Rotation */
    switch (mAnmTable[idx*3 + 0].mRotation.mMaxFrame) {
    case 0:  dst->mRotation.x = 0; break;
    case 1:  dst->mRotation.x = mRotData[mAnmTable[idx*3 + 0].mRotation.mOffset] << mDecShift; break;
    default: dst->mRotation.x = (s32)(J3DGetKeyFrameInterpolationS(frame, &mAnmTable[idx*3 + 0].mRotation, &mRotData[mAnmTable[idx*3 + 0].mRotation.mOffset])) << mDecShift; break;
    }

    switch (mAnmTable[idx*3 + 1].mRotation.mMaxFrame) {
    case 0:  dst->mRotation.y = 0; break;
    case 1:  dst->mRotation.y = mRotData[mAnmTable[idx*3 + 1].mRotation.mOffset] << mDecShift; break;
    default: dst->mRotation.y = (s32)(J3DGetKeyFrameInterpolationS(frame, &mAnmTable[idx*3 + 1].mRotation, &mRotData[mAnmTable[idx*3 + 1].mRotation.mOffset])) << mDecShift; break;
    }

    switch (mAnmTable[idx*3 + 2].mRotation.mMaxFrame) {
    case 0:  dst->mRotation.z = 0; break;
    case 1:  dst->mRotation.z = mRotData[mAnmTable[idx*3 + 2].mRotation.mOffset] << mDecShift; break;
    default: dst->mRotation.z = (s32)(J3DGetKeyFrameInterpolationS(frame, &mAnmTable[idx*3 + 2].mRotation, &mRotData[mAnmTable[idx*3 + 2].mRotation.mOffset])) << mDecShift; break;
    }

    /* Translation */
    switch (mAnmTable[idx*3 + 0].mTranslate.mMaxFrame) {
    case 0:  dst->mTranslate.x = 0.0f; break;
    case 1:  dst->mTranslate.x = mTransData[mAnmTable[idx*3 + 0].mTranslate.mOffset]; break;
    default: dst->mTranslate.x = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 0].mTranslate, &mTransData[mAnmTable[idx*3 + 0].mTranslate.mOffset]); break;
    }

    switch (mAnmTable[idx*3 + 1].mTranslate.mMaxFrame) {
    case 0:  dst->mTranslate.y = 0.0f; break;
    case 1:  dst->mTranslate.y = mTransData[mAnmTable[idx*3 + 1].mTranslate.mOffset]; break;
    default: dst->mTranslate.y = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 1].mTranslate, &mTransData[mAnmTable[idx*3 + 1].mTranslate.mOffset]); break;
    }

    switch (mAnmTable[idx*3 + 2].mTranslate.mMaxFrame) {
    case 0:  dst->mTranslate.z = 0.0f; break;
    case 1:  dst->mTranslate.z = mTransData[mAnmTable[idx*3 + 2].mTranslate.mOffset]; break;
    default: dst->mTranslate.z = J3DGetKeyFrameInterpolation<f32>(frame, &mAnmTable[idx*3 + 2].mTranslate, &mTransData[mAnmTable[idx*3 + 2].mTranslate.mOffset]); break;
    }
}
