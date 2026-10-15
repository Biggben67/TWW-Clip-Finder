// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_a_player_main.cpp - the ported daPy_lk_c bodies (d_a_player_main.cpp:184-193, 605-624,
// 1036-1039, 2175-2227, 2229-2274, 2624-2630, 2276-2287, 2289-2297, 2299-2349, 2352-2484,
// 1368-1385, 2486-2622, 9546-9589, 262-382, 390-414, 487-544, 8598-8701, 8704-8848,
// 9523-9545, 11023-11050, 2749-2847, 2850-2878, 2881-2906, 2936-2949, 3216-3276, 2968-3213,
// 3279-3413, 3556-3574, 4007-4017, 4076-4326, 4412-4510, 4883-4906, 4908-4919, 6040-6077,
// 6079-6148, 6150-6171, 6173-6194, 6196-6205, 6207-6219, 6556-6568, 6571-6595, 6222-6230,
// 6233-6239, 6301-6319, 6322-6350, 6353-6371, 6374-6384, 6505-6512, 6514-6553, 5605-5614,
// 8585-8595, 6804-6836, 6838-6875, 6991-7011, 7014-7027, 7030-7058, 7061-7083, 9712-9738,
// 10220-10266, 10672-10713, 12717-12785, 12787-12839, 12881-12921, 12943-12962).
// d_a_player_sword.inc is included where the decomp includes it: it is not a translation
// unit.
// The `/* 801152D0-80115478 */` address comments are the decomp's own and are GZLE01
// addresses.

#include "d/actor/d_a_player_main.h"
#include "SSystem/SComponent/c_lib.h"

#include <cmath>
#include <cstdlib>
#include <stdexcept>

#include "d/actor/d_a_player_HIO_data.inc"
#include "d/actor/anm_tables.inc"
#include "d/actor/tex_anm_table.inc"
#include "d/actor/d_a_player_crawl.inc"
#include "d/actor/d_a_player_boomerang.inc"
#include "d/actor/d_a_player_sword.inc"

/* 801031DC-80103214       .text itemTrigger__9daPy_lk_cCFv */
BOOL daPy_lk_c::itemTrigger() const {
    if (mReadyItemBtn == dItemBtn_X_e) {
        return itemTriggerX();
    } else if (mReadyItemBtn == dItemBtn_Y_e) {
        return itemTriggerY();
    } else {
        return itemTriggerZ();
    }
}

void daPy_lk_c::getUnderUpperAnime(const daPy_anmIndex_c* anmIndex, J3DAnmTransform** pUnderBck, J3DAnmTransform** pUpperBck, int r7, u32 bufferSize) {
    if (m_anm_heap_under[r7].mIdx != anmIndex->mUnderBckIdx) {
        *pUnderBck = getAnimeResource(&m_anm_heap_under[r7], anmIndex->mUnderBckIdx, bufferSize);
    } else {
        *pUnderBck = getNowAnmPackUnder((daPy_UNDER)r7);
    }
    if (anmIndex->mUnderBckIdx != anmIndex->mUpperBckIdx) {
        if (bufferSize == 0xB400) {
            bufferSize = 0x4800;
        }
        if (m_anm_heap_upper[r7].mIdx != anmIndex->mUpperBckIdx) {
            *pUpperBck = getAnimeResource(&m_anm_heap_upper[r7], anmIndex->mUpperBckIdx, bufferSize);
        } else {
            *pUpperBck = getNowAnmPackUpper((daPy_UPPER)r7);
        }
    } else {
        *pUpperBck = NULL;
        m_anm_heap_upper[r7].mIdx = -1;
    }
}

/* 8010552C-8010558C       .text checkPlayerGuard__9daPy_lk_cCFv */
BOOL daPy_lk_c::checkPlayerGuard() const {
    return mCurProc == daPyProc_CROUCH_DEFENSE_e || checkUpperGuardAnime() || checkGuardSlip();
}

/* 801086C8-801088E8       .text setDoStatusBasic__9daPy_lk_cFv */
void daPy_lk_c::setDoStatusBasic() {
    f32 fVar1;

    if (dComIfGp_getDoStatus() == dActStts_BLANK_e) {
        int direction = getDirectionFromShapeAngle();
        if (checkHeavyStateOn()) {
            fVar1 = m_HIO->mBasic.m.field_0x1C * m_HIO->mMove.m.mHeavyStateScale;
        } else {
            fVar1 = m_HIO->mBasic.m.field_0x1C;
        }
        if (checkAttentionLock() ||
            (mActorKeepThrow.getActor() != NULL && mpAttnActorLockOn == mActorKeepThrow.getActor()))
        {
            if (mStickDistance > 0.05f && direction != DIR_FORWARD) {
                if (mEquipItem == daPyItem_BOKO_e && direction == DIR_BACKWARD) {
                    dComIfGp_setDoStatus(dActStts_THROW_e);
                } else {
                    dComIfGp_setDoStatus(dActStts_JUMP_e);
                }
            } else {
                if (!checkPlayerGuard() && (mEquipItem == daPyItem_BOKO_e ||
                                            mEquipItem == daPyItem_SWORD_e ||
                                            mEquipItem == dItemNo_SKULL_HAMMER_e))
                {
                    if (mEquipItem == daPyItem_BOKO_e) {
                        dComIfGp_setDoStatus(dActStts_THROW_e);
                    } else {
                        dComIfGp_setDoStatus(dActStts_UNK43);
                    }
                } else if (mEquipItem == daPyItem_BOKO_e) {
                    dComIfGp_setDoStatus(dActStts_THROW_e);
                } else {
                    dComIfGp_setDoStatus(dActStts_ATTACK_e);
                }
            }
        } else if (checkNoUpperAnime() && mEquipItem != daPyItem_NONE_e &&
                   checkModeFlg(ModeFlg_00000004) && mStickDistance <= fVar1)
        {
            if (mEquipItem == daPyItem_BOKO_e) {
                dComIfGp_setDoStatus(dActStts_THROW_e);
            } else {
                dComIfGp_setDoStatus(dActStts_PUT_AWAY_e);
            }
        } else if (mStickDistance > fVar1) {
            if (mEquipItem == daPyItem_BOKO_e) {
                dComIfGp_setDoStatus(dActStts_THROW_e);
            } else {
                dComIfGp_setDoStatus(dActStts_ATTACK_e);
            }
        }
    }
}

/* 801088E8-80108A9C       .text setDoStatus__9daPy_lk_cFv */
void daPy_lk_c::setDoStatus() {
    if (setHintActor()) {
        return;
    }
    
    if (mpAttnActorLockOn == NULL && mpAttnEntryA == NULL) {
        if (checkResetFlg0(daPyRFlg0_UNK8)) {
            dComIfGp_setRStatus(dActStts_GRAB_e);
            if (mFrontWallType == 7 || mFrontWallType == 8 || mFrontWallType == 9) {
                dComIfGp_setDoStatus(dActStts_CLIMB_e);
            } else if (mFrontWallType == 2) {
                dComIfGp_setDoStatus(dActStts_SIDLE_e);
            }
            return;
        } else if (mFrontWallType == 2) {
            dComIfGp_setDoStatus(dActStts_SIDLE_e);
            return;
        }
    }
    if (mpAttnEntryA != NULL) {
        // TODO: is there an inline for checkNoResetFlg0(daPy_FLG0(daPyFlg0_UNK20000000 | daPyFlg0_UNK80000000)) ?
        if ((!checkNoResetFlg0(daPy_FLG0(daPyFlg0_UNK20000000 | daPyFlg0_UNK80000000))) &&
            (mpAttnEntryA->mType == fopAc_Attn_TYPE_DOOR_e || (mpAttnEntryA->mType == fopAc_Attn_TYPE_TREASURE_e)))
        {
            dComIfGp_setDoStatus(dActStts_OPEN_e);
        } else if ((!checkNoResetFlg0(daPy_FLG0(daPyFlg0_UNK20000000 | daPyFlg0_UNK80000000))) &&
                   mpAttnEntryA->mType == fopAc_Attn_TYPE_SHIP_e)
        {
            if (!dComIfGp_checkPlayerStatus0(0, daPyStts0_SHIP_RIDE_e)) {
                dComIfGp_setDoStatus(dActStts_GET_IN_SHIP_e);
            }
        } else if (mpAttnEntryA->mType == fopAc_Attn_TYPE_CARRY_e) {
            if (!fopAcM_CheckStatus(mpAttnActorA, fopAcStts_CARRY_e)) {
                if (fopAcM_GetName(mpAttnActorA) == fpcNm_BOKO_e) {
                    dComIfGp_setDoStatus(dActStts_PICK_UP_e);
                } else {
                    dComIfGp_setDoStatus(dActStts_LIFT_e);
                }
            }
        } else if (!setTalkStatus()) {
            setSpecialBattle(0);
        }
    }
    setDoStatusBasic();
}

/* 80109E80-80109ED8       .text setShapeAngleToAtnActor__9daPy_lk_cFv */
void daPy_lk_c::setShapeAngleToAtnActor() {
    if (mpAttnActorLockOn != NULL) {
        s16 targetAngle = cLib_targetAngleY(&current.pos, &mpAttnActorLockOn->eyePos);
        cLib_addCalcAngleS(&shape_angle.y, targetAngle, 2, 0x2000, 0x800);
    }
}

/* 80108A9C-80108B08       .text getDirectionFromAngle__9daPy_lk_cFs */
int daPy_lk_c::getDirectionFromAngle(s16 angle) {
    if (abs(angle) > 0x6000) {
        return DIR_BACKWARD;
    } else if (angle >= 0x2000) {
        return DIR_LEFT;
    } else if (angle <= -0x2000) {
        return DIR_RIGHT;
    } else {
        return DIR_FORWARD;
    }
}

/* 80108B08-80108B38       .text getDirectionFromShapeAngle__9daPy_lk_cFv */
int daPy_lk_c::getDirectionFromShapeAngle() {
    return getDirectionFromAngle(m34E8 - shape_angle.y);
}

/* 80108B38-80108B68       .text getDirectionFromCurrentAngle__9daPy_lk_cFv */
int daPy_lk_c::getDirectionFromCurrentAngle() {
    return getDirectionFromAngle(m34E8 - current.angle.y);
}

/* 80108B68-80108D80       .text setNormalSpeedF__9daPy_lk_cFffff */
void daPy_lk_c::setNormalSpeedF(f32 param_1, f32 param_2, f32 param_3, f32 param_4) {
    f32 dVar10;
    if (dComIfGp_event_runCheck() || checkHeavyStateOn() || checkGrabWear()) {
        dVar10 = mMaxNormalSpeed * mStickDistance;
    } else {
        dVar10 = mStickDistance * (mMaxNormalSpeed * mStickDistance);
    }
    if (mDemo.getDemoMode() == daPy_demo_c::DEMO_KEEP_e || getSlidePolygon() != NULL) {
        return;
    }
    if (mAcch.ChkWallHit()) {
        s16 uVar2 = 0;
        dBgS_AcchCir* pdVar4 = &mAcchCir[0];
        for (int i = 0; i < 3; i++, pdVar4++) {
            if (pdVar4->ChkWallHit()) {
                uVar2 = (current.angle.y + 0x8000) - pdVar4->GetWallAngleY();
                break;
            }
        }
        if (abs(uVar2) < 0x4000) {
            dVar10 *= (1.0f - cM_scos(uVar2) * m_HIO->mBasic.m.field_0x14);
        }
    }
    f32 temp_f3;
    f32 dVar6;
    if (dVar10 < mNormalSpeed) {
        f32 temp_f0 = mNormalSpeed - dVar10;
        if (temp_f0 > param_3) {
            temp_f3 = param_3;
        } else {
            temp_f3 = temp_f0;
        }
        if (temp_f3 < param_4) {
            temp_f3 = param_4;
        }
        param_1 = 0.0f;
        dVar6 = dVar10;
    } else {
        temp_f3 = param_3;
        dVar6 = 0.0f;
    }
    if (!cM3d_IsZero(param_1)) {
        mNormalSpeed += param_1;
        if (mNormalSpeed > dVar10) {
            mNormalSpeed = dVar10;
        }
    } else {
        cLib_addCalc(&mNormalSpeed, dVar6, param_2, temp_f3, param_4);
    }
}

void daPy_lk_c::posMoveFromFootPos() {
    if (m_old_fdata->getOldFrameFlg() == false) {
        m34BC = 2;
        speedF = 0.0f;
        static const Vec rtoe_pos_offset = {-14.05f, 0.0f, 5.02f};
        static const Vec rheel_pos_offset = {-10.85f, 0.0f, -6.52f};
        mFootData[0].field_0x018 = rtoe_pos_offset;
        mFootData[0].field_0x00C = rheel_pos_offset;
        mFootData[1].field_0x018.x = -rtoe_pos_offset.x;
        mFootData[1].field_0x018.y = rtoe_pos_offset.y;
        mFootData[1].field_0x018.z = rtoe_pos_offset.z;
        mFootData[1].field_0x00C.x = -rheel_pos_offset.x;
        mFootData[1].field_0x00C.y = rheel_pos_offset.y;
        mFootData[1].field_0x00C.z = rheel_pos_offset.z;
        return;
    }

    cXyz spB0[2];
    cXyz sp98[2];
    cMtx_concat(m37B4, mpCLModel->getAnmMtx(CL_JNT_LFOOT_JNT_e), mDoMtx_stack_c::get());
    mDoMtx_stack_c::multVec(&l_toe_pos, &spB0[1]);
    mDoMtx_stack_c::multVec(&l_heel_pos, &sp98[1]);
    cMtx_concat(m37B4, mpCLModel->getAnmMtx(CL_JNT_RFOOT_JNT_e), mDoMtx_stack_c::get());
    mDoMtx_stack_c::multVec(&l_toe_pos, &spB0[0]);
    mDoMtx_stack_c::multVec(&l_heel_pos, &sp98[0]);
    cMtx_concat(m37B4, mpCLModel->getAnmMtx(CL_JNT_WAIST_JNT_e), mDoMtx_stack_c::get());
    MtxP r26 = mDoMtx_stack_c::get();
    f32 f31 = cM_ssin(m34E0);
    f32 f30 = cM_scos(m34E0);
    f32 sp0C[2];
    cXyz sp80[2];
    for (int i = 0; i < 2; i++) {
        sp80[i] = sp98[i] + spB0[i];
        sp80[i] *= 0.5f;
        f32 f2 = r26[1][3] + f30 * (sp80[i].y - r26[1][3]);
        sp0C[i] = f2 + f31 * (sp80[i].z - r26[2][3]);
    }
    if (sp0C[0] < sp0C[1]) {
        m34BC = 0;
    } else {
        m34BC = 1;
    }
    cXyz sp7C;
    cXyz sp68;
    sp68 = spB0[m34BC] - mFootData[m34BC].field_0x018;
    f32 f31_2 = sp68.absXZ();
    if (m3598 < 1.0f && std::abs(m35B4 - mStickDistance) < 0.2f) {
        f31_2 = ((f31_2 * 0.3f) + 0.7f * m359C);
    }
    sp7C.z = mNormalSpeed * (1.0f - m3598);
    if (mNormalSpeed < 0.0f) {
        sp7C.z -= (f31_2 * m3598);
    } else {
        sp7C.z += (f31_2 * m3598);
    }
    s16 r3;
    if (!mAcch.ChkGroundHit() || !dComIfG_Bgsp()->ChkPolySafe(mAcch.m_gnd) || m3580 == 8) {
        r3 = 0;
    } else {
        r3 = getGroundAngle(&mAcch.m_gnd, current.angle.y);
    }
    sp7C.z *= cM_scos(r3);
    if (r3 < 0) {
        sp7C.z *= 0.85f;
    }
    if (std::abs(sp7C.z) < 0.05f) {
        speedF = 0.0f;
        speed.x = 0.0f;
        speed.z = 0.0f;
    } else {
        speedF = sp7C.z;
        if (mCurProc == daPyProc_SWIM_MOVE_e) {
            f32 f1 = (
                (speedF * (1.0f - m_HIO->mSwim.m.field_0x60)) +
                m_HIO->mSwim.m.field_0x60 *
                (speedF * std::abs(cM_scos(cM_rad2s(M_PI * (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() / mFrameCtrlUnder[UNDER_MOVE0_e].getEnd())))))
            ) / (1.0f + (m_HIO->mSwim.m.field_0x7C * getSwimTimerRate()));
            speed.x = f1 * cM_ssin(current.angle.y);
            speed.z = f1 * cM_scos(current.angle.y);
        } else if (mCurProc != daPyProc_CUT_ROLL_e || !dComIfGp_event_runCheck() ||
                   checkPlayerDemoMode() || mDemo.getDemoMode() == daPy_demo_c::DEMO_CUT_ROLL_e)
        {
            speed.x = speedF * cM_ssin(current.angle.y);
            speed.z = speedF * cM_scos(current.angle.y);
        } else {
            speed.x = 0.0f;
            speed.z = 0.0f;
        }
    }
    m36AC = m36A0;
    if (!checkModeFlg(
            // Note: These flags combine into 0x11612832.
            ModeFlg_MIDAIR | ModeFlg_WHIDE | ModeFlg_HANG | ModeFlg_ROPE | ModeFlg_IN_SHIP | ModeFlg_CLIMB |
            ModeFlg_PUSHPULL | ModeFlg_LADDER | ModeFlg_CRAWL | ModeFlg_CAUGHT
        ) &&
        !dComIfGp_event_runCheck() && !checkPlayerDemoMode() && !checkHeavyStateOn() &&
        mCurrAttributeCode == dBgS_Attr_ICE_e &&
        !checkNoResetFlg0(daPy_FLG0(daPyFlg0_UNK20000000 | daPyFlg0_UNK80000000)) && !mAcch.ChkWallHit() &&
        mAcch.ChkGroundHit())
    {
        cLib_addCalc(&m36A0.x, 0.0f, 0.03f, 100.0f, 0.5f);
        cLib_addCalc(&m36A0.z, 0.0f, 0.03f, 100.0f, 0.5f);
        m36A0 += (mOldSpeed - speed) * 0.75f;
        speed += (mOldSpeed - speed) * 0.25f;
    } else {
        m36A0.x = 0.0f;
        m36A0.z = 0.0f;
    }
    m36A0.y = 0.0f;
    setBeltConveyerPower();
    setWindAtPower();
    f32 f1 = speed.y;
    if (checkHeavyStateOn()) {
        speed.y += gravity * 2.25f;
        if (speed.y < (maxFallSpeed * 1.5f)) {
            speed.y = maxFallSpeed * 1.5f;
        }
    } else {
        speed.y += gravity;
        if (speed.y < maxFallSpeed) {
            speed.y = maxFallSpeed;
        }
    }
    if (speed.y <= 0.0f && f1 > 0.0f) {
        m35F0 = current.pos.y;
    }
    current.pos += speed;
    for (int i = 0; i < 2; i++) {
        mFootData[i].field_0x018 = spB0[i];
        mFootData[i].field_0x00C = sp98[i];
    }
    m359C = f31_2;
}

/* 80106750-801067D8       .text checkNoCollisionCorret__9daPy_lk_cFv */
BOOL daPy_lk_c::checkNoCollisionCorret() {
    if (checkModeFlg(ModeFlg_HANG | ModeFlg_ROPE | ModeFlg_IN_SHIP | ModeFlg_LADDER | ModeFlg_CAUGHT) ||
        mDemo.getDemoType() == daPy_demo_c::TYPE_TOOL_e ||
        mDemo.getDemoMode() == daPy_demo_c::DEMO_OPEN_TREASURE_e ||
        mDemo.getDemoMode() == daPy_demo_c::DEMO_UNK_030_e ||
        checkResetFlg0(daPyRFlg0_CRAWL_AUTO_MOVE) ||
        eventInfo.checkCommandDoor() ||
        mCurProc == daPyProc_VERTICAL_JUMP_e ||
        mCurProc == daPyProc_CRAWL_END_e ||
        mCurProc == daPyProc_VOMIT_WAIT_e ||
        mCurProc == daPyProc_DEMO_DOOR_OPEN_e ||
        mCurProc == daPyProc_HOOKSHOT_FLY_e)
    {
        return true;
    }
    return false;
}

/* 8010959C-80109E80       .text posMove__9daPy_lk_cFv */
void daPy_lk_c::posMove() {
    mDoExt_MtxCalcAnmBlendTblOld* pmVar10 = m_pbCalc[PART_UNDER_e];
    cXyz sp8C = m3700;
    J3DAnmTransform* pJVar5 = pmVar10->getAnmTransform(0);
    J3DTransformInfo spB8;
    pJVar5->getTransform(0, &spB8);
    pJVar5 = pmVar10->getAnmTransform(1);
    if (pJVar5 != NULL) {
        J3DTransformInfo sp98;
        pJVar5->getTransform(0, &sp98);
        f32 fVar2 = pmVar10->getRatio(1);
        f32 fVar4 = 1.0f - fVar2;
        spB8.mTranslate.x = spB8.mTranslate.x * fVar4 + sp98.mTranslate.x * fVar2;
        spB8.mTranslate.y = spB8.mTranslate.y * fVar4 + sp98.mTranslate.y * fVar2;
        spB8.mTranslate.z = spB8.mTranslate.z * fVar4 + sp98.mTranslate.z * fVar2;
    }
    J3DTransformInfo* pJVar11 = m_old_fdata->getOldFrameTransInfo(0);
    f32 dVar15 = cM_ssin(shape_angle.y);
    f32 dVar14 = cM_scos(shape_angle.y);
    cXyz sp80;
    cXyz sp74;
    if (m34C2 == 11) {
        sp80 = current.pos - old.pos;
        pJVar11->mTranslate.x -= (-dVar15 * sp80.z) + (dVar14 * sp80.x);
        pJVar11->mTranslate.y -= sp80.y;
        pJVar11->mTranslate.z -= (dVar14 * sp80.z) + (dVar15 * sp80.x);
    } else if (m34C2 == 10) {
        sp80.set(
            spB8.mTranslate.x - pJVar11->mTranslate.x,
            spB8.mTranslate.y - pJVar11->mTranslate.y,
            spB8.mTranslate.z - pJVar11->mTranslate.z
        );
        sp74.x = (dVar15 * sp80.z) + (dVar14 * sp80.x);
        sp74.y = sp80.y;
        sp74.z = (dVar14 * sp80.z) - (dVar15 * sp80.x);
        current.pos -= sp74;
        old.pos -= sp74;
        pJVar11->mTranslate.x = spB8.mTranslate.x;
        pJVar11->mTranslate.y = spB8.mTranslate.y;
        pJVar11->mTranslate.z = spB8.mTranslate.z;
    } else if (m34C2 == 2 || m34C2 == 6) {
        pJVar11->mTranslate.x = spB8.mTranslate.x;
        pJVar11->mTranslate.z = spB8.mTranslate.z;
        if (m34C2 == 6) {
            pJVar11->mTranslate.y = spB8.mTranslate.y;
        }
    } else if (m34C2 == 4) {
        m3700.x = 0.0f;
        m3700.z = 0.0f;
        sp8C.x = 0.0f;
        sp8C.z = 0.0f;
        sp8C.y = spB8.mTranslate.y;
        pJVar11->mTranslate.x = 0.0f;
        pJVar11->mTranslate.z = 0.0f;
        pJVar11->mTranslate.y = spB8.mTranslate.y;
        m35E0 = spB8.mTranslate.y;
        m34C2 = 5;
    } else if (m34C2 == 7 || m34C2 == 3) {
        sp8C.x = spB8.mTranslate.x;
        sp8C.y = spB8.mTranslate.y;
        sp8C.z = spB8.mTranslate.z;
        if (m34C2 == 7) {
            m34C2 = 5;
        } else {
            m34C2 = 1;
        }
    }
    m3700 = spB8.mTranslate;
    posMoveFromFootPos();
    if (!checkNoCollisionCorret()) {
        current.pos += *mStts.GetCCMoveP();
        if (!dComIfGp_event_runCheck() && !checkPlayerDemoMode()) {
            if (!checkNoResetFlg1(daPyFlg1_UNK10000000) || !checkHeavyStateOn()) {
                current.pos.x += m3644 * cM_ssin(m3640);
                current.pos.z += m3644 * cM_scos(m3640);
            }
            if (mWhirlId != fpcM_ERROR_PROCESS_ID_e) {
                fopAc_ac_c* local_110 = fopAcM_SearchByID(mWhirlId);
                if (local_110 != NULL) {
                    cXyz sp68 = current.pos - local_110->current.pos;
                    s16 iVar7 = cM_atan2s(sp68.x, sp68.z) + 0x5000;
                    cLib_chaseF(&m3610, 40.0f, 5.0f);
                    current.pos.x += m3610 * cM_ssin(iVar7);
                    current.pos.z += m3610 * cM_scos(iVar7);
                    f32 dVar13 = sp68.absXZ();
                    if (dVar13 < 500.0f) {
                        startRestartRoom(5, 0xC9, -1.0f, 0);
                    }
                } else {
                    m3610 = 0.0f;
                }
            } else {
                m3610 = 0.0f;
            }
            if (mAcch.ChkGroundHit() && dComIfG_Bgsp()->ChkPolySafe(mAcch.m_gnd)) {
                s16 uVar8 = getGroundAngle(&mAcch.m_gnd, 0);
                current.pos.z += m36A0.z * cM_scos(uVar8);
                uVar8 = getGroundAngle(&mAcch.m_gnd, 0x4000);
                current.pos.x += m36A0.x * cM_scos(uVar8);
            }
            current.pos += m36B8;
            if (mCurProc != daPyProc_FAN_GLIDE_e) {
                current.pos.x += m3730.x;
                current.pos.z += m3730.z;
            }
        }
    } else if (!dComIfGp_event_runCheck() && !checkPlayerDemoMode() && daPy_getPlayerActorClass() == this &&
               mCurProc == daPyProc_HANG_MOVE_e)
    {
        f32 dVar13 = mStts.GetCCMoveP()->absXZ();
        if (dVar13 > 1.0f) {
            if ((s16)(cM_atan2s(mStts.GetCCMoveP()->x, mStts.GetCCMoveP()->z) - shape_angle.y) >= 0) {
                current.pos.x += dVar13 * cM_scos(shape_angle.y);
                current.pos.z -= dVar13 * cM_ssin(shape_angle.y);
            } else {
                current.pos.x -= dVar13 * cM_scos(shape_angle.y);
                current.pos.z += dVar13 * cM_ssin(shape_angle.y);
            }
        }
    }
    m3644 = 0.0f;
    mStts.GetCCMoveP()->x = mStts.GetCCMoveP()->y = mStts.GetCCMoveP()->z = 0.0f;
    if (m34C2 == 1 || m34C2 == 8 || m34C2 == 9 || m34C2 == 5) {
        cXyz sp5C;
        if (m34C2 == 1 || m34C2 == 5) {
            sp5C = m3700 - sp8C;
        } else {
            sp5C = sp8C - m3700;
        }
        current.pos.x += (sp5C.z * dVar15) + (sp5C.x * dVar14);
        current.pos.z += (sp5C.z * dVar14) - (sp5C.x * dVar15);
        if (m34C2 == 5) {
            current.pos.y += sp5C.y;
        }
    }
}

/* 8011CDB4-8011D070       .text setWorldMatrix__9daPy_lk_cFv */
void daPy_lk_c::setWorldMatrix() {
    BOOL bVar1;
    daShip_c* ship;
    f32 dVar6;
    cXyz local_44;
    Mtx afStack_38;

    mDoMtx_stack_c::transS(current.pos.x, current.pos.y + m35C4 + m3608, current.pos.z);
    ship = dComIfGp_getShipActor();
    if (dComIfGp_checkPlayerStatus0(0, daPyStts0_SHIP_RIDE_e) && ship != NULL) {
        mDoMtx_stack_c::ZXYrotM(m353C, ship->shape_angle.y, m353E);
        mDoMtx_stack_c::YrotM(shape_angle.y - ship->shape_angle.y);
        mDoMtx_copy(mDoMtx_stack_c::get(), afStack_38);
        bVar1 = true;
    } else if (checkModeFlg(ModeFlg_CLIMB)) {
        mDoMtx_stack_c::ZXYrotM(shape_angle.x, shape_angle.y, shape_angle.z);
        mDoMtx_stack_c::transM(0.0f, 0.0f, 20.5f);
        mDoMtx_stack_c::YrotM(m34EC);
        mDoMtx_stack_c::transM(0.0f, 0.0f, -20.5f);
        bVar1 = false;
    } else {
        mDoMtx_stack_c::ZXYrotM(shape_angle.x, shape_angle.y + m34EC, shape_angle.z);
        bVar1 = false;
    }

    mpCLModel->setBaseScale(scale);
    mpCLModel->setBaseTRMtx(mDoMtx_stack_c::get());
    mDoMtx_stack_c::inverse();
    mDoMtx_copy(mDoMtx_stack_c::get(), m37B4);
    if (bVar1) {
        mDoMtx_stack_c::YrotS(-shape_angle.y);
        mDoMtx_stack_c::concat(afStack_38);
        mDoMtx_stack_c::multVecSR(&cXyz::BaseZ, &local_44);
        shape_angle.x = cM_atan2s(-local_44.y, local_44.z);
        mDoMtx_stack_c::multVecSR(&cXyz::BaseX, &local_44);
        dVar6 = ppc::sqrtf_msl(local_44.y * local_44.y + local_44.z * local_44.z);
        if (local_44.y >= 0.0f) {
            shape_angle.z = cM_atan2s(dVar6, local_44.x);
        } else {
            shape_angle.z = cM_atan2s(-dVar6, local_44.x);
        }
    }
}

BOOL daPy_lk_c::jointBeforeCB(int jnt_no, J3DTransformInfo* param_2, Quaternion* param_3) {
    thread_local Mtx root_mtx;
    static Quaternion norm_quat = {0.0f, 0.0f, 0.0f, 1.0f};
    Quaternion local_20;
    Quaternion afStack_30;

    csXyz local_38(0, 0, 0);
    if (jnt_no == CL_JNT_HEAD_JNT_e) {
        local_38.set(m3564.y, m3564.z, m3564.x);
    } else if (jnt_no == CL_JNT_LCLOTCH_JNT_e) {
        m34C6 = 2;
        m3668.mScale = param_2->mScale;
        m3668.mRotation = param_2->mRotation;
        m3668.mTranslate = param_2->mTranslate;
        param_2->mTranslate.x = param_2->mTranslate.x - mFootData[1].field_0x030;
    } else if (jnt_no == CL_JNT_RCLOTCH_JNT_e) {
        m34C6 = 2;
        m3668.mScale = param_2->mScale;
        m3668.mRotation = param_2->mRotation;
        m3668.mTranslate = param_2->mTranslate;
        param_2->mTranslate.x = param_2->mTranslate.x - mFootData[0].field_0x030;
    } else if (jnt_no == CL_JNT_LMOMI_JNT_e) {
        local_38.y = m3516;
        local_38.z = m351A;
    } else if (jnt_no == CL_JNT_RMOMI_JNT_e) {
        local_38.y = m3518;
        local_38.z = m351A;
    } else if (jnt_no == CL_JNT_BODY_CHN_e) {
        local_38.set(-mBodyAngle.z, mBodyAngle.y, mBodyAngle.x);
        m34C6 = 2;
        m3668.mScale = param_2->mScale;
        m3668.mRotation = param_2->mRotation;
        m3668.mTranslate = param_2->mTranslate;
        param_2->mTranslate.y = param_2->mTranslate.y + m35D8;
    } else if (jnt_no == 0) {
        local_38.x = m34F2;
        local_38.z = m34F4;
    } else if (
        (jnt_no == CL_JNT_RARMA_JNT_e || jnt_no == CL_JNT_RARMB_JNT_e) &&
        dComIfGp_checkPlayerStatus0(0, daPyStts0_SHIP_RIDE_e) &&
        m_old_fdata->getOldFrameFlg() != false
    ) {
        if (dComIfGp_getShipActor() != NULL) {
            if (!fpcM_IsCreating(fopAcM_GetID(dComIfGp_getShipActor()))) {
                if (!checkShipNotNormalMode()) {
                    setShipRideArmAngle(jnt_no, param_2);
                    param_2->mTranslate.x = 0.0f;
                    param_2->mTranslate.y = 0.0f;
                    param_2->mTranslate.z = 0.0f;
                    JMAQuatLerp(m_old_fdata->getOldFrameQuaternion(jnt_no), &norm_quat,
                                (1.0f - m_old_fdata->getOldFrameRate()), param_3);
                }
            }
        }
    }

#if VERSION == VERSION_DEMO
    if (
        !checkModeFlg(ModeFlg_WHIDE | ModeFlg_SWIM | ModeFlg_CRAWL) &&
        mCurProc != daPyProc_VOMIT_WAIT_e && mCurProc != daPyProc_ELEC_DAMAGE_e && mCurProc != daPyProc_DEMO_DOOR_OPEN_e
    )
#else
    if (!checkResetFlg0(daPyRFlg0_ORIGINAL_HAT_ANIM))
#endif
    {
        if (jnt_no == CL_JNT_HATA_JNT_e) {
            JMAEulerToQuat(0, m34F8, m3528 + (m34F6 + -0x8000) + m350E, param_3);
        } else if (jnt_no == CL_JNT_HATB_JNT_e) {
            JMAEulerToQuat(0, m34FC, m34FA + m3510, param_3);
        } else if (jnt_no == CL_JNT_HATC_JNT_e) {
            JMAEulerToQuat(0, m3500, m34FE + m3512, param_3);
        }
    }

    if (jnt_no == CL_JNT_LINK_ROOT_e) {
        if (m34C2 == 1) {
            param_2->mTranslate.x = 0.0f;
            param_2->mTranslate.z = 0.0f;
        } else if (m34C2 == 5) {
            param_2->mTranslate.x = 0.0f;
            param_2->mTranslate.y = m35E0;
            param_2->mTranslate.z = 0.0f;
        }
    }
    if (jnt_no == CL_JNT_WAIST_JNT_e && (m34E0 != 0 || m34E4 != 0)) {
        local_38.y = m34E4;
        local_38.z = m34E0;
    }
    if (local_38.x != 0 || local_38.y != 0 || local_38.z != 0) {
        m34C6 = m34C6 | 1;
        m3658 = *param_3;
        if (local_38.x != 0 || local_38.y != 0) {
            local_20 = *param_3;
            JMAEulerToQuat(local_38.x, local_38.y, 0, &afStack_30);
            mDoMtx_QuatConcat(&local_20, &afStack_30, param_3);
        }
        if (local_38.z != 0) {
            local_20 = *param_3;
            JMAEulerToQuat(0, 0, local_38.z, &afStack_30);
            mDoMtx_QuatConcat(&local_20, &afStack_30, param_3);
        }
    }
    if ((checkUpperGuardAnime() && mCurProc != daPyProc_BACK_JUMP_e) ||
        checkGrabAnime() ||
        m_anm_heap_upper[UPPER_MOVE0_e].mIdx == dRes_INDEX_LKANM_BCK_ATNBOKO_e ||
        m_anm_heap_upper[UPPER_MOVE0_e].mIdx == dRes_INDEX_LKANM_BCK_ATNHAM_e ||
        checkUpperReadyThrowAnime())
    {
        if (jnt_no == CL_JNT_LINK_ROOT_e) {
            m3648 = *param_3;
        } else if (jnt_no == CL_JNT_CENTER_e) {
            mDoMtx_copy(J3DSys::mCurrentMtx, root_mtx);
            mDoMtx_stack_c::quatS(&m3648);
            mDoMtx_stack_c::inverse();
            cMtx_concat(J3DSys::mCurrentMtx, mDoMtx_stack_c::get(), J3DSys::mCurrentMtx);
        } else if (jnt_no == CL_JNT_WAIST_CHN_e) {
            mDoMtx_copy(root_mtx, J3DSys::mCurrentMtx);
        }
    }
    return true;
}

BOOL daPy_lk_c::jointAfterCB(int jnt_no, J3DTransformInfo* param_2, Quaternion* param_3) {
    if (m34C6 != 0) {
        if ((m34C6 & 1) != 0) {
            *param_3 = m3658;
        }
        if ((m34C6 & 2) != 0) {
            *param_2 = m3668;
        }
        m34C6 = 0;
    }
    if (jnt_no == CL_JNT_LFOOT_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_LFOOT_JNT_e), mFootData[1].field_0x088[2]);
    } else if (jnt_no == CL_JNT_RFOOT_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_RFOOT_JNT_e), mFootData[0].field_0x088[2]);
    } else if (jnt_no == CL_JNT_LLEGA_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_LLEGA_JNT_e), mFootData[1].field_0x088[0]);
    } else if (jnt_no == CL_JNT_LLEGB_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_LLEGB_JNT_e), mFootData[1].field_0x088[1]);
    } else if (jnt_no == CL_JNT_RLEGA_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_RLEGA_JNT_e), mFootData[0].field_0x088[0]);
    } else if (jnt_no == CL_JNT_RLEGB_JNT_e) {
        mDoMtx_copy(mpCLModel->getAnmMtx(CL_JNT_RLEGB_JNT_e), mFootData[0].field_0x088[1]);
    }
    return true;
}

BOOL daPy_lk_c::jointCB1() {
    if (m_old_fdata->getOldFrameFlg() == false) {
        return false;
    }

    J3DTransformInfo* trans_info;
    Quaternion* quaternion;
    trans_info = m_old_fdata->getOldFrameTransInfo(CL_JNT_LLEGB_JNT_e);
    quaternion = m_old_fdata->getOldFrameQuaternion(CL_JNT_LLEGB_JNT_e);
    
    mDoMtx_stack_c::ZrotS(mFootData[1].field_0x008);
    mDoMtx_stack_c::revConcat(mpCLModel->getAnmMtx(CL_JNT_LLEGA_JNT_e));
    mpCLModel->setAnmMtx(CL_JNT_LLEGA_JNT_e, mDoMtx_stack_c::get());
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mDoMtx_stack_c::ZrotM(mFootData[1].field_0x00A);
    mpCLModel->setAnmMtx(CL_JNT_LLEGB_JNT_e, mDoMtx_stack_c::get());
    trans_info++;
    quaternion++;
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mDoMtx_stack_c::ZrotM(mFootData[1].field_0x002);
    mpCLModel->setAnmMtx(CL_JNT_LFOOT_JNT_e, mDoMtx_stack_c::get());
    trans_info++;
    quaternion++;
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mpCLModel->setAnmMtx(CL_JNT_LTOE_JNT_e, mDoMtx_stack_c::get());

    trans_info = m_old_fdata->getOldFrameTransInfo(CL_JNT_RLEGB_JNT_e);
    quaternion = m_old_fdata->getOldFrameQuaternion(CL_JNT_RLEGB_JNT_e);
    mDoMtx_stack_c::ZrotS(mFootData[0].field_0x008);
    mDoMtx_stack_c::revConcat(mpCLModel->getAnmMtx(CL_JNT_RLEGA_JNT_e));
    mpCLModel->setAnmMtx(CL_JNT_RLEGA_JNT_e, mDoMtx_stack_c::get());
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mDoMtx_stack_c::ZrotM(mFootData[0].field_0x00A);
    mpCLModel->setAnmMtx(CL_JNT_RLEGB_JNT_e, mDoMtx_stack_c::get());
    trans_info++;
    quaternion++;
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mDoMtx_stack_c::ZrotM(mFootData[0].field_0x002);
    mpCLModel->setAnmMtx(CL_JNT_RFOOT_JNT_e, mDoMtx_stack_c::get());
    trans_info++;
    quaternion++;
    
    mDoMtx_stack_c::transM(trans_info->mTranslate.x, trans_info->mTranslate.y, trans_info->mTranslate.z);
    mDoMtx_stack_c::quatM(quaternion);
    mpCLModel->setAnmMtx(CL_JNT_RTOE_JNT_e, mDoMtx_stack_c::get());

    return TRUE;
}

int daPy_lk_c::setLegAngle(f32 param_1, int param_2, s16* param_3, s16* param_4) {
    cXyz spE8;
    cXyz spDC;
    cXyz spD0;
    cXyz spC4;
    cXyz spB8;
    cXyz spAC;
    cXyz spA0;
    cXyz sp94;
    cXyz sp88;
    cXyz sp7C;
    cXyz sp70;
    cXyz sp64;
    cXyz sp58;

    if (std::abs(param_1) < 0.1f) {
        return false;
    }
    f32 f31;
    f32 f30;
    f30 = 0.5f * param_1;
    if (f30 > 10.0f) {
        f30 = 10.0f;
    }

    MtxP mtx;
    cMtx_concat(m37B4, mFootData[param_2].field_0x088[0], mDoMtx_stack_c::get());
    mtx = mDoMtx_stack_c::get();
    spE8.set(0.0f, mtx[1][3], mtx[2][3]);

    cMtx_concat(m37B4, mFootData[param_2].field_0x088[1], mDoMtx_stack_c::get());
    mtx = mDoMtx_stack_c::get();
    spDC.set(0.0f, mtx[1][3], mtx[2][3]);

    cMtx_concat(m37B4, mFootData[param_2].field_0x088[2], mDoMtx_stack_c::get());
    mtx = mDoMtx_stack_c::get();
    spD0.set(0.0f, mtx[1][3] + 3.25f, mtx[2][3]);

    spAC = spDC - spE8;
    spA0 = spD0 - spDC;
    spB8.x = spD0.x;
    spB8.y = spD0.y;
    spB8.z = spD0.z;
    spB8.y += param_1;
    spB8.z += f30;
    if (spB8.y >= spE8.y) {
        return false;
    }
    sp7C = spB8 - spE8;
    f31 = sp7C.abs2();
    if (cM3d_IsZero(f31)) {
        return false;
    }
    f30 = spAC.abs2();
    f32 f1 = spA0.abs2();
    if (ppc::sqrtf_msl(f30) + ppc::sqrtf_msl(f1) <= ppc::sqrtf_msl(f31)) {
        return false;
    }
    f32 f3 = (((f31 + f30) - f1) / (2.0f * f31));
    sp58.x = 0.0f;
    sp58.y = spE8.y + (f3 * sp7C.y);
    sp58.z = spE8.z + (f3 * sp7C.z);
    f32 f4 = f30 - (f3 * (f31 * f3));
    if (f4 < 0.0f) {
        f4 = 0.0f;
    }
    f31 = ppc::sqrtf_msl(f4);
    sp70.x = 0.0f;
    sp70.y = sp7C.z;
    sp70.z = -sp7C.y;
    f32 f1_2 = sp70.abs();
    if (cM3d_IsZero(f1_2)) {
        return false;
    }
    f32 f2 = f31 / f1_2;
    spC4.x = 0.0f;
    spC4.y = sp58.y + f2 * sp70.y;
    spC4.z = sp58.z + f2 * sp70.z;
    sp94 = spC4 - spE8;
    sp88 = spB8 - spC4;

    cMtx_concat(m37B4, mpCLModel->getAnmMtx(CL_JNT_LINK_ROOT_e), mDoMtx_stack_c::get());
    mtx = mDoMtx_stack_c::get();
    sp64.set(0.0f, mtx[1][3], mtx[2][3]);

    s16 r29 = cM_atan2s(-sp64.y, -sp64.z);
    s16 r27 = cM_atan2s(sp94.y, sp94.z);
    s16 r26 = cM_atan2s(sp88.y, sp88.z);
    s16 r3 = r27 - r29;
    if (r3 > 0x6000) {
        r27 = r29 + 0x6000;
    } else if (r3 < -0x4000) {
        r27 = r29 + -0x4000;
    }
    s16 r0 = r26 - r27;
    if (r0 > 0) {
        r26 = r27;
    } else if (r0 < -0x7000) {
        r26 = r27 + -0x7000;
    }
    *param_3 = cM_atan2s(spAC.y, spAC.z) - r27;
    *param_4 = cM_atan2s(spA0.y, spA0.z) - r26;
    return true;
}

void daPy_lk_c::footBgCheck() {
    u32 r28;
    f32 sp18[2];
    int sp10[2];
    int i;
    f32* r26;
    daPy_footData_c* r25_r26;

    MtxP r30 = mpCLModel->getBaseTRMtx();
    u32 r29 = checkModeFlg(ModeFlg_00000001);
    cMtx_concat(m37B4, mpCLModel->getAnmMtx(CL_JNT_WAIST_JNT_e), mDoMtx_stack_c::get());
    MtxP r31 = mDoMtx_stack_c::get();

    f32 f28 = cM_ssin(m34E0);
    f32 f27 = cM_scos(m34E0);
    r25_r26 = mFootData;
    r26 = sp18;
    for (i = 0; i < 2; i++, r25_r26++, r26++) {
        cXyz sp74;
        cXyz sp68;
        cXyz sp5C;
        cXyz sp50;
        sp74 = (r25_r26->field_0x018 + r25_r26->field_0x00C) * 0.5f;
        sp50 = sp74 - r25_r26->field_0x024;
        if (sp50.abs2XZ() < SQUARE(10.0f) && r29 != 0) {
            if (r25_r26->field_0x001 != 0) {
                r25_r26->field_0x001--;
            } else {
                sp74 = r25_r26->field_0x024;
            }
        } else {
            r25_r26->field_0x001 = 5;
        }
        r25_r26->field_0x024 = sp74;
        f32 f26 = r31[1][3] + (f27 * (sp74.y - r31[1][3])) + (f28 * (sp74.z - r31[2][3]));
        mDoMtx_multVec(r30, &sp74, &sp68);
        sp5C.set(sp68.x, current.pos.y + 30.1f, sp68.z);
        r25_r26->field_0x034.SetPos(&sp5C);
        f32 f1 = dComIfG_Bgsp()->GroundCross(&r25_r26->field_0x034);
        if (checkNoResetFlg0(daPyFlg0_UNK80000000) && current.pos.y > f1) {
            f1 = current.pos.y;
            sp10[i] = 1;
        } else {
            sp10[i] = 0;
        }
        if (f1 != -G_CM3D_F_INF && sp5C.y - f1 < 60.2f) {
            *r26 = f1;
            r25_r26->field_0x000 = 1;
        } else {
            *r26 = current.pos.y;
            r25_r26->field_0x000 = 0;
        }
        if (checkNoResetFlg0(daPy_FLG0(daPyFlg0_UNK20000000 | daPyFlg0_UNK80000000)) && *r26 <= current.pos.y) {
            *r26 = current.pos.y;
        }
        *r26 -= (sp74.y - f26);
    }

    int r23;
    if (!mAcch.ChkGroundHit() || checkModeFlg(
                                     // Note: These flags combine into 0x1045A822.
                                     ModeFlg_MIDAIR | ModeFlg_HANG | ModeFlg_ROPE | ModeFlg_IN_SHIP | ModeFlg_00008000 |
                                     ModeFlg_CLIMB | ModeFlg_SWIM | ModeFlg_LADDER | ModeFlg_CAUGHT
                                 ))
    {
        r23 = 2;
    } else if (sp18[0] > sp18[1]) {
        r23 = 1;
    } else {
        r23 = 0;
    }
    f32 f1;
    if (r23 == 2 || mCurProc == daPyProc_DEMO_TOOL_e || std::abs(m35C4) > 1.0f) {
        f1 = 0.0f;
    } else {
        if (sp18[0] > sp18[1]) {
            f1 = sp18[1];
        } else {
            f1 = sp18[0];
        }
        f1 -= current.pos.y;
    }
    cLib_addCalc(&m35B8, f1, 0.5f, 7.5f, 2.5f);
    r30[1][3] += m35B8;
    m37B4[1][3] = m37B4[1][3] - m35B8;
    s16 sp0C[2];
    s16 sp08[2];
    if (r23 == 2) {
        for (int i = 0; i < 2; i++) {
            sp0C[i] = 0;
            sp08[i] = 0;
            mFootData[i].field_0x030 = 0.0f;
        }
    } else {
        r28 = r23 + 1 & 1;
        daPy_footData_c* r4;
        r4 = &mFootData[r23];
        r25_r26 = &mFootData[r28];
        r4->field_0x030 = 0.0f;
        if (!setLegAngle(sp18[r23] - r30[1][3], r23, &sp0C[r23], &sp08[r23])) {
            sp0C[r23] = 0;
            sp08[r23] = 0;
        }
        f32 f1 = sp18[r28] - r30[1][3];
        if (f1 > 0.0f || r29 != 0) {
            r25_r26->field_0x030 = 0.3f * f1;
            if (!setLegAngle(0.7f * f1, r28, &sp0C[r28], &sp08[r28])) {
                sp0C[r28] = 0;
                sp08[r28] = 0;
            }
        } else {
            r25_r26->field_0x030 = 0.0f;
            sp0C[r28] = 0;
            sp08[r28] = 0;
        }
    }

    for (i = 0; i < 2; i++) {
        r25_r26 = &mFootData[i];
        if (r25_r26->field_0x008 * sp0C[i] < 0 && abs(sp0C[i] - r25_r26->field_0x008) >= 0x8000) {
            if (sp0C[i] >= 0) {
                sp0C[i] -= 0x4000;
            } else {
                sp0C[i] += 0x4000;
            }
        }
        cLib_addCalcAngleS(&r25_r26->field_0x008, sp0C[i], 2, 0x1800, 0x10);
        cLib_addCalcAngleS(&r25_r26->field_0x006, sp08[i], 2, 0x1800, 0x10);
        r25_r26->field_0x00A = r25_r26->field_0x006 - r25_r26->field_0x008;
        r25_r26->field_0x002 = -(m34E0 + r25_r26->field_0x006);
    }

    r25_r26 = mFootData;
    for (i = 0; i < 2; i++, r25_r26++) {
        s16 r4;
        if (sp10[i] == 0 && r25_r26->field_0x000 != 0 && r29 != 0) {
            r4 = getGroundAngle(&r25_r26->field_0x034, shape_angle.y);
            r25_r26->field_0x002 = r25_r26->field_0x002 + r4;
            r4 = getGroundAngle(&r25_r26->field_0x034, shape_angle.y + -0x4000);
        } else {
            r4 = 0;
        }
        cLib_addCalcAngleS(&r25_r26->field_0x004, r4, 2, 0x1800, 0x10);
    }
}

void daPy_lk_c::setWaistAngle() {
    f32 fVar1;
    s16 sVar2;

    if (checkModeFlg(ModeFlg_00000001 | ModeFlg_MIDAIR | ModeFlg_HANG | ModeFlg_ROPE |
                     ModeFlg_IN_SHIP | ModeFlg_00008000 | ModeFlg_CLIMB | ModeFlg_SWIM |
                     ModeFlg_LADDER | ModeFlg_CAUGHT))
    {
        sVar2 = 0;
    } else {
        fVar1 = std::abs(mNormalSpeed / (mMaxNormalSpeed));
        if (fVar1 > 1.0f) {
            fVar1 = 1.0f;
        }
        if (m3580 == 8) {
            sVar2 = 0;
        } else {
            sVar2 = 0.7f * m34E2 * fVar1;
        }
    }
    cLib_addCalcAngleS(&m34E0, sVar2, 2, 0x800, 0x200);
}


void daPy_lk_c::setStepsOffset() {
    f32 fVar1;
    f32 dVar5;
    f32 dVar6;
    cXyz local_2c;

    cLib_addCalc(&m35C4, 0.0f, 0.5f, 25.0f, 5.0f);
    dVar6 = (cM_ssin(m34E2) / cM_scos(m34E2));
    local_2c.x = current.pos.x + speedF * cM_ssin(current.angle.y);
    local_2c.y = 30.1f + current.pos.y;
    local_2c.z = current.pos.z + speedF * cM_scos(current.angle.y);
    mGndChk.SetPos(&local_2c);
    dVar5 = dComIfG_Bgsp()->GroundCross(&mGndChk);
    if (checkNoResetFlg0(daPyFlg0_UNK80000000) && current.pos.y > dVar5) {
        dVar5 = current.pos.y;
    }
    fVar1 = (dVar5 - current.pos.y) - (-speedF * dVar6);
    if (fVar1 > 0.0f) {
        current.pos.y = dVar5;
        m35C4 -= fVar1 * 0.7f;
    } else if (!checkNoResetFlg0(daPyFlg0_UNK80000000)) {
        local_2c = old.pos - current.pos;
        fVar1 = local_2c.y - (dVar6 * local_2c.absXZ());
        if (fVar1 >= 0.0f) {
            m35C4 += fVar1 * 0.7f;
        }
    }
}

/* 8010A4D4-8010A96C       .text setSpeedAndAngleNormal__9daPy_lk_cFs */
void daPy_lk_c::setSpeedAndAngleNormal(s16 param_1) {
    f32 dVar11;
    f32 dVar9;
    if (mStickDistance > 0.05f) {
        BOOL bVar2 = false;
        dVar11 = mStickDistance * mStickDistance;
        if (checkHeavyStateOn()) {
            dVar11 *= 1.0f / (m_HIO->mMove.m.mHeavyStateScale * m_HIO->mMove.m.mHeavyStateScale);
        }
        if (checkGrabWear()) {
            dVar11 *= 1.0f / (m_HIO->mMove.m.field_0x74 * m_HIO->mMove.m.field_0x74);
        }
        if ((!checkAttentionLock() && cLib_distanceAngleS(m34E8, current.angle.y) > 0x7800) &&
            mCurProc != daPyProc_MOVE_TURN_e)
        {
            if (checkModeFlg(ModeFlg_00000001)) {
                return;
            }
            if (mCurProc == daPyProc_MOVE_e) {
                if ((speedF / mMaxNormalSpeed > m_HIO->mSlip.m.mSpeedRatioMin) &&
                    getDirectionFromAngle(m34EA - m34DC) == DIR_BACKWARD)
                {
                    return;
                }
                if (speedF / mMaxNormalSpeed <= m_HIO->mSlip.m.mSpeedRatioMin) {
                    cLib_addCalcAngleS(&current.angle.y, m34E8, m_HIO->mMove.m.field_0x6,
                                       param_1, m_HIO->mMove.m.field_0x4);
                    return;
                }
                bVar2 = true;
            } else {
                cLib_addCalcAngleS(&current.angle.y, m34E8, m_HIO->mMove.m.field_0x6, param_1,
                                   m_HIO->mMove.m.field_0x4);
            }
        } else {
            s16 sVar6;
            s16 sVar7;
            if (dComIfGp_event_runCheck()) {
                sVar6 = param_1;
                sVar7 = m_HIO->mMove.m.field_0x4;
            } else {
                sVar6 = param_1 * dVar11;
                if (sVar6 < 10) {
                    sVar6 = 10;
                }
                sVar7 = m_HIO->mMove.m.field_0x4 * dVar11;
                if (sVar7 < 1) {
                    sVar7 = 1;
                }
            }
            cLib_addCalcAngleS(&current.angle.y, m34E8, m_HIO->mMove.m.field_0x6, sVar6, sVar7);
        }
        if (!bVar2) {
            dVar9 = cM_scos(m34E8 - current.angle.y);
            if (mNormalSpeed > 0.5f * mMaxNormalSpeed) {
                if (dVar9 < 0.7f) {
                    dVar9 = 0.7f;
                }
            } else if (dVar9 < 0.0f) {
                dVar9 = 0.0f;
            }
            if (dComIfGp_event_runCheck()) {
                dVar9 *= m_HIO->mMove.m.field_0x14 * mStickDistance;
            } else {
                f32 dVar10 = 0.5f - (0.5f * std::abs(mNormalSpeed / mMaxNormalSpeed));
                if (checkHeavyStateOn()) {
                    dVar10 *= m_HIO->mMove.m.mHeavyStateScale;
                }
                if (checkGrabWear()) {
                    dVar10 *= m_HIO->mMove.m.field_0x74;
                }
                if (mStickDistance > dVar10) {
                    dVar9 *= m_HIO->mMove.m.field_0x14 * dVar11;
                } else {
                    dVar9 = 0.0f;
                }
            }
        } else {
            dVar9 = 0.0f;
        }
    } else {
        dVar9 = 0.0f;
    }
    if ((!checkAttentionLock() && mCurProc != daPyProc_MOVE_TURN_e) &&
        mStickDistance > 0.05f)
    {
        s16 sVar6 = shape_angle.y;
        cLib_addCalcAngleS(&shape_angle.y, m34E8, m_HIO->mMove.m.field_0x6,
                           (s16)(param_1 << 1), (s16)(m_HIO->mMove.m.field_0x4 << 1));
        s16 temp = (s16)(sVar6 - current.angle.y);
        s16 temp2 = (s16)(shape_angle.y - current.angle.y);
        if (temp * temp2 <= 0) {
            shape_angle.y = current.angle.y;
        }
    }
    setNormalSpeedF(dVar9, m_HIO->mMove.m.field_0x24, m_HIO->mMove.m.field_0x1C,
                    m_HIO->mMove.m.field_0x20);
}

void daPy_lk_c::setSpeedAndAngleAtn() {
    s16 sVar1;
    f32 fVar2;

    if (mDirection == DIR_FORWARD) {
        return setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0);
    }
    if (mDirection == DIR_BACKWARD) {
        return setSpeedAndAngleAtnBack();
    }
    
    if (mStickDistance > 0.05f) {
        if (getDirectionFromCurrentAngle() == DIR_BACKWARD) {
            current.angle.y += 0x8000;
            mNormalSpeed *= -1.0f;
        }
        sVar1 = current.angle.y;
        cLib_addCalcAngleS(&current.angle.y, m34E8, m_HIO->mAtnMove.m.field_0x4,
                            m_HIO->mAtnMove.m.field_0x0, m_HIO->mAtnMove.m.field_0x2);
        fVar2 = m_HIO->mAtnMove.m.field_0x8 * mStickDistance *
                cM_scos(current.angle.y - sVar1);
    } else {
        fVar2 = 0.0f;
    }
    
    shape_angle.y = m34E6;
    return setNormalSpeedF(fVar2, m_HIO->mAtnMove.m.field_0x18,
                           m_HIO->mAtnMove.m.field_0x10, m_HIO->mAtnMove.m.field_0x14);
}

void daPy_lk_c::setSpeedAndAngleAtnBack() {
    f32 f1;
    if (mStickDistance > 0.05f) {
        if (getDirectionFromCurrentAngle() == DIR_BACKWARD) {
            current.angle.y += 0x8000;
            mNormalSpeed *= -1.0f;
        }
        s16 origAngleY = current.angle.y;
        cLib_addCalcAngleS(
            &current.angle.y, m34E8,
            m_HIO->mAtnMoveB.m.field_0x4,
            m_HIO->mAtnMoveB.m.field_0x0,
            m_HIO->mAtnMoveB.m.field_0x2
        );
        f1 = (m_HIO->mAtnMoveB.m.field_0x8 * mStickDistance) * cM_scos(current.angle.y - origAngleY);
    } else {
        f1 = 0.0f;
    }
    shape_angle.y = m34E6;
    setNormalSpeedF(
        f1,
        m_HIO->mAtnMoveB.m.field_0x18,
        m_HIO->mAtnMoveB.m.field_0x10,
        m_HIO->mAtnMoveB.m.field_0x14
    );
}

/* 8010AC8C-8010ACEC       .text setFrameCtrl__9daPy_lk_cFP12J3DFrameCtrlUcssff */
void daPy_lk_c::setFrameCtrl(J3DFrameCtrl* frameCtrl, u8 attribute, s16 start, s16 end, f32 rate, f32 frame) {
    frameCtrl->setAttribute(attribute);
    frameCtrl->setEnd(end);
    frameCtrl->setRate(rate);
    frameCtrl->setStart(start);
    frameCtrl->setFrame(frame);
    if (rate >= 0.0f) {
        frameCtrl->setLoop(start);
    } else {
        frameCtrl->setLoop(end);
    }
}


void daPy_lk_c::setBlendAtnBackMoveAnime(f32 param_1) {
    f32 fVar1;
    if (m3580 == 8) {
        fVar1 = 1.0f;
    } else {
        fVar1 = cM_scos(m34E2);
    }
    f32 dVar7 = (std::abs(mNormalSpeed * fVar1) / mMaxNormalSpeed);
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE1_e];
    if (dVar7 < m_HIO->mAtnMoveB.m.field_0x1C) {
        f32 fVar1 = dVar7 / m_HIO->mAtnMoveB.m.field_0x1C;
        int iVar4;
        if (checkModeFlg(ModeFlg_00000001)) {
            iVar4 = 2;
            m3598 = 0.0f;
        } else {
            iVar4 = 4;
            m3598 = 1.0f;
        }
        setMoveAnime(fVar1, m_HIO->mMove.m.field_0x38, m_HIO->mAtnMoveB.m.field_0x24, ANM_WAITS, ANM_ATNWB, iVar4, param_1);
        if (!checkModeFlg(ModeFlg_00000001)) {
            if (frameCtrl.checkPass(2.0f)) {
                onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
            } else if (frameCtrl.checkPass(12.0f)) {
                onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
            }
        }
    } else if (dVar7 < m_HIO->mAtnMoveB.m.field_0x20) {
        f32 fVar1 = (dVar7 - m_HIO->mAtnMoveB.m.field_0x1C) /
                    (m_HIO->mAtnMoveB.m.field_0x20 - m_HIO->mAtnMoveB.m.field_0x1C);
        setMoveAnime(fVar1, m_HIO->mAtnMoveB.m.field_0x24, m_HIO->mAtnMoveB.m.field_0x28, ANM_ATNWB, ANM_ATNDB, 4, param_1);
        m3598 = 1.0f - fVar1;
        if (frameCtrl.checkPass(5.0f) || frameCtrl.checkPass(15.0f)) {
            onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
        } else if (frameCtrl.checkPass(3.0f) || frameCtrl.checkPass(13.0f)) {
            onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
        }
    } else {
        f32 fVar1;
        if (m36A0.abs2XZ() >= SQUARE(7.0f)) {
            fVar1 = 1.9f * m_HIO->mAtnMoveB.m.field_0x28;
            onResetFlg0(daPyRFlg0_UNK40000);
        } else {
            fVar1 = m_HIO->mAtnMoveB.m.field_0x28;
        }
        setMoveAnime(1.0f, fVar1, fVar1, ANM_ATNDB, ANM_ATNDB, 4, param_1);
        m3598 = 0.0f;
        if (frameCtrl.checkPass(5.0f) || frameCtrl.checkPass(15.0f)) {
            onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
        } else if (frameCtrl.checkPass(3.0f) || frameCtrl.checkPass(13.0f)) {
            onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
        }
    }
    if (dVar7 >= 0.9f) {
        onResetFlg0(daPyRFlg0_UNK10);
    }
    if (!getFootOnGround()) {
        resetFootEffect();
    }
    setHandModel(ANM_ATNDB);
}

void daPy_lk_c::setBlendMoveAnime(f32 param_1) {
    f32 f1_1;
    if (m3580 == 8) {
        f1_1 = 1.0f;
    } else {
        f1_1 = cM_scos(m34E2);
    }
    f32 f30 = (std::abs(mNormalSpeed * f1_1) / mMaxNormalSpeed);
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE1_e];
    f32 f29;
    f32 f28;
    if (dComIfGp_event_runCheck() || checkPlayerDemoMode()) {
        f29 = m_HIO->mMove.m.field_0x44;
        f28 = m_HIO->mMove.m.field_0x64;
    } else if (checkHeavyStateOn()) {
        f29 = m_HIO->mMove.m.field_0x78;
        f28 = m_HIO->mMove.m.field_0x7C;
    } else {
        f29 = m_HIO->mMove.m.field_0x40;
        f28 = m_HIO->mMove.m.field_0x60;
    }
    daPy_ANM r28 = ANM_WAITS;
    daPy_ANM r27;
    daPy_ANM r26;
    if (checkGrabWear()) {
        r27 = ANM_WALKBARREL;
        r26 = ANM_WALKBARREL;
    } else if (checkHeavyStateOn()) {
        if ((m373C.abs2XZ() > SQUARE(5.0f) &&
                (cLib_distanceAngleS(cM_atan2s(m373C.x, m373C.z), shape_angle.y) >= 0x4000)) ||
            ((checkNoResetFlg1(daPyFlg1_UNK10000000) && m3644 > 5.0f) &&
                cLib_distanceAngleS(m3640, shape_angle.y) >= 0x4000))
        {
            r27 = ANM_WALKHBOOTSKAZE;
            r26 = ANM_WALKHBOOTSKAZE;
            if (!checkNoResetFlg1(daPyFlg1_UNK1000000)) {
                param_1 = m_HIO->mBasic.m.mAnmMorf;
                onNoResetFlg1(daPyFlg1_UNK1000000);
            }
        } else {
            r27 = ANM_WALKHBOOTS;
            r26 = ANM_WALKHBOOTS;
            if (checkNoResetFlg1(daPyFlg1_UNK1000000)) {
                param_1 = m_HIO->mBasic.m.mAnmMorf;
                offNoResetFlg1(daPyFlg1_UNK1000000);
            }
        }
    } else if (m3580 != 8 && m34E2 <= -0x11C7) {
        r27 = ANM_WALKSLOPE;
        r26 = ANM_WALKSLOPE;
        if (!checkNoResetFlg1(daPyFlg1_UNK80)) {
            param_1 = m_HIO->mBasic.m.mAnmMorf;
            onNoResetFlg1(daPyFlg1_UNK80);
        }
    } else {
        r27 = ANM_WALK;
        if ((m3730.abs2XZ() > SQUARE(5.0f) &&
                (cLib_distanceAngleS(cM_atan2s(m3730.x, m3730.z), shape_angle.y) >= 0x4000)) ||
            ((checkNoResetFlg1(daPyFlg1_UNK10000000) && m3644 > 5.0f) &&
                cLib_distanceAngleS(m3640, shape_angle.y) >= 0x4000))
        {
            r26 = ANM_DASHKAZE;
            if (!checkNoResetFlg1(daPyFlg1_UNK1000000)) {
                param_1 = m_HIO->mBasic.m.mAnmMorf;
                onNoResetFlg1(daPyFlg1_UNK1000000);
            }
        } else {
            r26 = ANM_DASH;
            if (checkNoResetFlg1(daPyFlg1_UNK1000000)) {
                param_1 = m_HIO->mBasic.m.mAnmMorf;
                offNoResetFlg1(daPyFlg1_UNK1000000);
            }
        }
        if (checkNoResetFlg1(daPyFlg1_UNK80)) {
            param_1 = m_HIO->mBasic.m.mAnmMorf;
            offNoResetFlg1(daPyFlg1_UNK80);
        }
    }
    BOOL r25 = false;
    f32 f1;
    f32 f31 = m36A0.abs2XZ();
    f32 f25 = m3730.abs2XZ();
    f32 f1_2 = m36B8.abs2XZ();
    BOOL bVar3;
    if (f31 > f25) {
        if (f31 > f1_2) {
            f1_2 = f31;
        }
        bVar3 = true;
    } else if (f25 > f1_2) {
        f1_2 = f25;
        bVar3 = false;
    } else {
        bVar3 = false;
    }
    if (mStickDistance < 0.05f &&
        ((f1_2 >= 25.0f || ((f1_2 >= 0.09f && ((m34C3 == 9 || m34C3 == 10)))))))
    {
        seStartMapInfo(JA_SE_LK_SLIP_SUS);
        if ((m34C3 != 9 && (bVar3)) || ((m34C3 != 10 && (!bVar3)))) {
            if (bVar3) {
                setSingleMoveAnime(
                    ANM_SLIPICE,
                    m_HIO->mIceSlip.m.field_0x10,
                    m_HIO->mIceSlip.m.field_0x14,
                    m_HIO->mIceSlip.m.field_0x0,
                    m_HIO->mIceSlip.m.field_0x18
                );
                m34C3 = 9;
            } else {
                setSingleMoveAnime(ANM_WAITQ, m_HIO->mMove.m.field_0x84, 0.0f, -1, m_HIO->mBasic.m.mAnmMorf);
                setTextureAnime(0x68, 0);
                m34C3 = 10;
            }
            voiceStart(35);
        }
        if (checkGrabAnime()) {
            resetActAnimeUpper(UPPER_MOVE2_e, -1.0f);
        }
        freeGrabItem();
        if (mEquipItem == daPyItem_BOKO_e) {
            deleteEquipItem(FALSE);
        }
        m3598 = 0.0f;
    } else {
        if (m34C3 == 9) {
            param_1 = m_HIO->mBasic.m.mAnmMorf;
        }
        if (f30 < m_HIO->mMove.m.field_0x2C || checkHeavyStateOn()) {
            f32 f25_2;
            if (checkHeavyStateOn()) {
                f25_2 = f30 / m_HIO->mMove.m.mHeavyStateScale;
                if (f25_2 > 0.55f) {
                    r25 = true;
                }
            } else {
                f25_2 = f30 / m_HIO->mMove.m.field_0x2C;
            }
            r28 = ANM_WAITS;
            int r24;
            // JP 0x801084C0 inherits f27: OSInit clears it and the main01 ->
            // actor execute -> proc caller chain never writes this saved register.
            f32 in_f27 = 0.0f;
            if (checkModeFlg(ModeFlg_00000001)) {
                if (checkAttentionLock()) {
                    if (checkUpperGuardAnime()) {
                        setMoveAnime(0.0f, m_HIO->mAtnMove.m.field_0x24, m_HIO->mAtnMove.m.field_0x28, ANM_ATNRS, ANM_ATNWRS, 2, m_HIO->mBasic.m.mAnmMorf);
                        return;
                    }
                }
                f32 f1 = m3598 = 0.0f;
                r24 = 2;
                if ((checkNoResetFlg1(daPyFlg1_CONFUSE) && !checkPlayerDemoMode()) &&
                    !dComIfGp_event_runCheck())
                {
                    if (m_anm_heap_under[UNDER_MOVE0_e].mIdx != dRes_INDEX_LKANM_BCK_WAITQ_e) {
                        setSingleMoveAnime(ANM_WAITQ, m_HIO->mMove.m.field_0x84, f1, -1, m_HIO->mBasic.m.mAnmMorf);
                        m34C3 = 2;
                    }
                    return;
                }
                if (shape_angle.y != m34DE && !checkAttentionLock()) {
                    s16 r3 = (s16)(shape_angle.y - m34DE);
                    if (r3 > 0) {
                        r27 = ANM_ATNWLS;
                    } else {
                        r27 = ANM_ATNWRS;
                    }
                    f25_2 = (0.5f + 0.001f * abs(r3));
                    if (f25_2 > 1.0f) {
                        f25_2 = 1.0f;
                    }
                    if (!checkNoResetFlg1(daPyFlg1_UNK800000)) {
                        param_1 = m_HIO->mBasic.m.mAnmMorf;
                    }
                    onNoResetFlg1(daPyFlg1_UNK800000);
                    f29 = m_HIO->mAtnMove.m.field_0x28;
                } else if (checkRestHPAnime()) {
                    r28 = ANM_WAITB;
                    in_f27 = m_HIO->mMove.m.field_0x3C;
                    if (checkNoResetFlg1(daPyFlg1_UNK800000)) {
                        param_1 = m_HIO->mBasic.m.mAnmMorf;
                    }
                    offNoResetFlg1(daPyFlg1_UNK800000);
                } else {
                    in_f27 = m_HIO->mMove.m.field_0x38;
                    if (checkNoResetFlg1(daPyFlg1_UNK800000)) {
                        param_1 = m_HIO->mBasic.m.mAnmMorf;
                    }
                    offNoResetFlg1(daPyFlg1_UNK800000);
                }
            } else {
                m3598 = (1.0f - ((1.0f - f28) * f25_2));
                r24 = 1;
                in_f27 = m_HIO->mMove.m.field_0x38;
            }
            setMoveAnime(f25_2, in_f27, f29, r28, r27, r24, param_1);
            if (r28 == ANM_WAITB && (!dComIfGp_event_runCheck() || mDemo.getDemoType() != daPy_demo_c::TYPE_ORIGINAL_e) &&
                mFrameCtrlUnder[UNDER_MOVE0_e].checkPass(15.0f))
            {
                if (dComIfGs_getLife() <= 2) {
                    voiceStart(21);
                } else {
                    voiceStart(20);
                }
            }
        } else if (f30 < m_HIO->mMove.m.field_0x30) {
            f1 = (f30 - m_HIO->mMove.m.field_0x2C) / (m_HIO->mMove.m.field_0x30 - m_HIO->mMove.m.field_0x2C);
            setMoveAnime(f1, f29, m_HIO->mMove.m.field_0x48, r27, r26, 1, param_1);
            m3598 = (f28 * (1.0f - f1));
        } else {
            f32 f1;
            if (f31 >= 169.0f) {
                f1 = 1.7f * m_HIO->mMove.m.field_0x48;
                onResetFlg0(daPyRFlg0_UNK40000);
            } else {
                f1 = m_HIO->mMove.m.field_0x48;
            }
            setMoveAnime(1.0f, f1, f1, r26, r26, 1, param_1);
            m3598 = 0.0f;
        }
    }
    if (f30 >= 0.9f || (r25)) {
        onResetFlg0(daPyRFlg0_UNK10);
    }
    if (!checkModeFlg(ModeFlg_00000001)) {
        if (frameCtrl.checkPass(4.0f)) {
            onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
        } else if (frameCtrl.checkPass(20.0f)) {
            onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
        } else {
            resetFootEffect();
        }
    }
    if (m34C3 != 9 && m34C3 != 10) {
        if (f30 > m_HIO->mMove.m.field_0x34) {
            setHandModel(r26);
        } else if (f30 > 0.0f) {
            setHandModel(r27);
        } else {
            setHandModel(r28);
        }
    }
}

void daPy_lk_c::setBlendAtnMoveAnime(f32 f30) {
    s16 r3;
    if (mAcch.ChkGroundHit() || !dComIfG_Bgsp()->ChkPolySafe(mAcch.m_gnd)) {
        r3 = 0;
    } else {
        r3 = getGroundAngle(&mAcch.m_gnd, current.angle.y);
    }
    f32 f31 = std::abs((mNormalSpeed * cM_scos(r3)) / mMaxNormalSpeed);
    int iVar6 = current.angle.y - shape_angle.y;
    f32 f2 = cM_ssin(iVar6);
    f32 fVar4 = cM_scos(iVar6);
    u8 uVar1 = mDirection;
    if (mDemo.getDemoMode() == daPy_demo_c::DEMO_A_WAIT_e) {
        if (mDemo.getParam0() == 1) {
            mDirection = DIR_LEFT;
        } else {
            mDirection = DIR_RIGHT;
        }
    } else if (mStickDistance > 0.05f) {
        if (mpAttnActorLockOn == NULL &&
            (fVar4 <= m_HIO->mAtnMoveB.m.field_0x30 || (fVar4 >= m_HIO->mAtnMoveB.m.field_0x2C)))
        {
            if (fVar4 <= m_HIO->mAtnMoveB.m.field_0x30) {
                mDirection = DIR_BACKWARD;
            } else {
                mDirection = DIR_FORWARD;
            }
        } else {
            if (uVar1 == DIR_BACKWARD || uVar1 == DIR_FORWARD) {
                mDirection = DIR_RIGHT;
                mMaxNormalSpeed = m_HIO->mAtnMove.m.mMaxNormalSpeed;
            }
            if (f2 > 0.0f) {
                mDirection = DIR_LEFT;
            } else if (f2 < 0.0f) {
                mDirection = DIR_RIGHT;
            }
        }
    }
    u8 uVar2 = mDirection;
    if (uVar1 != uVar2) {
        f30 = m_HIO->mBasic.m.mAnmMorf;
    }
    if (uVar2 == DIR_BACKWARD) {
        mMaxNormalSpeed = m_HIO->mAtnMoveB.m.field_0xC;
        setBlendAtnBackMoveAnime(f30);
    } else if (uVar2 == DIR_FORWARD) {
        mMaxNormalSpeed = m_HIO->mMove.m.mMaxNormalSpeed;
        setBlendMoveAnime(f30);
    } else {
        daPy_ANM dVar8;
        daPy_ANM dVar9;
        if (uVar2 != DIR_RIGHT && uVar2 != DIR_LEFT) {
            mDirection = DIR_RIGHT;
            f30 = m_HIO->mBasic.m.mAnmMorf;
        }
        J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE1_e];
        f32 f29;
        if (checkHeavyStateOn()) {
            f29 = 0.6f;
        } else {
            f29 = 1.0f;
        }
        if (f31 < m_HIO->mAtnMove.m.field_0x1C) {
            f32 f1 = f31 / m_HIO->mAtnMove.m.field_0x1C;
            if (mDirection == DIR_LEFT) {
                dVar8 = ANM_ATNLS;
                dVar9 = ANM_ATNWLS;
            } else {
                dVar8 = ANM_ATNRS;
                dVar9 = ANM_ATNWRS;
            }
            if (checkModeFlg(ModeFlg_00000001)) {
                iVar6 = 2;
                m3598 = 0.0f;
            } else {
                iVar6 = 4;
                m3598 = 1.0f;
            }
            setMoveAnime(f1, m_HIO->mAtnMove.m.field_0x24, m_HIO->mAtnMove.m.field_0x28 * f29, dVar8, dVar9, iVar6, f30);
        } else {
            if (f31 < m_HIO->mAtnMove.m.field_0x20) {
                f32 f28 = (f31 - m_HIO->mAtnMove.m.field_0x1C) /
                          (m_HIO->mAtnMove.m.field_0x20 - m_HIO->mAtnMove.m.field_0x1C);
                if (mDirection == DIR_LEFT) {
                    dVar8 = ANM_ATNWLS;
                    dVar9 = ANM_ATNDLS;
                } else {
                    dVar8 = ANM_ATNWRS;
                    dVar9 = ANM_ATNDRS;
                }
                setMoveAnime(f28, m_HIO->mAtnMove.m.field_0x28 * f29, m_HIO->mAtnMove.m.field_0x2C * f29, dVar8, dVar9, 4, f30);
                m3598 = 1.0f - (f28 * m3598);
            } else {
                if (mDirection == DIR_LEFT) {
                    dVar9 = ANM_ATNDLS;
                } else {
                    dVar9 = ANM_ATNDRS;
                }
                f32 f2;
                if (m36A0.abs2XZ() >= SQUARE(7.0f)) {
                    f2 = 1.9f * m_HIO->mAtnMove.m.field_0x2C;
                    onResetFlg0(daPyRFlg0_UNK40000);
                } else {
                    f2 = m_HIO->mAtnMove.m.field_0x2C * f29;
                }
                setMoveAnime(1.0f, f2, f2, dVar9, dVar9, 4, f30);
                m3598 = 0.0f;
            }
        }
        if (f31 >= 0.9f) {
            onResetFlg0(daPyRFlg0_UNK10);
        }
        if (!checkModeFlg(ModeFlg_00000001)) {
            if (mDirection == DIR_LEFT) {
                if (frameCtrl.checkPass(2.0f)) {
                    onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
                } else if (frameCtrl.checkPass(10.0f)) {
                    onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
                } else {
                    resetFootEffect();
                }
            } else {
                if (frameCtrl.checkPass(10.0f)) {
                    onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
                } else if (frameCtrl.checkPass(2.0f)) {
                    onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
                } else {
                    resetFootEffect();
                }
            }
        }
        setHandModel(dVar9);
    }
}


/* 8010C4A4-8010C4C8       .text checkSingleItemEquipAnime__9daPy_lk_cCFv */
BOOL daPy_lk_c::checkSingleItemEquipAnime() const {
    return checkUpperAnime(dRes_INDEX_LKANM_BCK_TAKEL_e) ||
        checkUpperAnime(dRes_INDEX_LKANM_BCK_TAKER_e);
}

/* 8010C4C8-8010C528       .text checkItemEquipAnime__9daPy_lk_cCFv */
BOOL daPy_lk_c::checkItemEquipAnime() const {
    return checkUpperAnime(dRes_INDEX_LKANM_BCK_TAKE_e) ||
        checkSingleItemEquipAnime() ||
        checkUpperAnime(dRes_INDEX_LKANM_BCK_TAKEBOTH_e);
}

/* 8010C528-8010C570       .text checkEquipAnime__9daPy_lk_cCFv */
BOOL daPy_lk_c::checkEquipAnime() const {
    return checkUpperAnime(dRes_INDEX_LKANM_BCK_REST_e) ||
        checkItemEquipAnime();
}

BOOL daPy_lk_c::checkJumpCutFromButton() {
    if (((mEquipItem == daPyItem_SWORD_e &&
          ((checkResetFlg0(daPyRFlg0_UNK80) || swordTrigger()))) ||
         ((mEquipItem == daPyItem_BOKO_e && swordTrigger()))) ||
        (((mEquipItem == dItemNo_SKULL_HAMMER_e && itemTrigger()) &&
          mEquipItem == getReadyItem())))
    {
        return procJumpCut_init(1);
    }
    return false;
}

/* 8010DB58-8010E448       .text checkNextActionFromButton__9daPy_lk_cFv */
BOOL daPy_lk_c::checkNextActionFromButton() {
    int direction;

    if (checkResetFlg0(daPyRFlg0_UNK80)) {
        if (mEquipItem == daPyItem_SWORD_e) {
            resetActAnimeUpper(UPPER_MOVE2_e, -1.0f);
            return changeCutProc();
        }
        if (checkPhotoBoxItem(mEquipItem) || mEquipItem == dItemNo_TELESCOPE_e) {
            return procScope_init(mEquipItem);
        }
        if (mEquipItem == dItemNo_DEKU_LEAF_e) {
            return procFanSwing_init();
        }
        if (checkBowItem(mEquipItem)) {
            return checkNextBowMode();
        }
        if (mEquipItem == dItemNo_HOOKSHOT_e) {
            return checkNextHookshotMode();
        }
        if (mEquipItem == dItemNo_BOOMERANG_e) {
            return checkNextBoomerangMode();
        }
        if (mEquipItem == dItemNo_GRAPPLING_HOOK_e) {
            return checkNextRopeMode();
        }
        if (mEquipItem == dItemNo_WIND_WAKER_e) {
            return procTactWait_init(-1);
        }
    }
    if (checkGrabAnime()) {
        if (checkNextActionGrab()) {
            return true;
        }
        setDoStatusBasic();
    } else if (checkHookshotReadyAnime()) {
        if (checkNextActionHookshotReady()) {
            return true;
        }
        setDoStatusBasic();
    } else if (checkBowAnime()) {
        if (checkNextActionBowReady()) {
            return true;
        }
        setDoStatusBasic();
    } else {
        if (checkBoomerangThrowAnime()) {
            return true;
        }
        if (checkBoomerangReadyAnime()) {
            if (checkNextActionBoomerangReady()) {
                return true;
            }
            setDoStatusBasic();
        } else if (checkRopeAnime()) {
            if (checkNextActionRopeReady()) {
                return true;
            }
            setDoStatusBasic();
        } else {
            setDoStatus();
            if (spActionTrigger() && dComIfGp_getRStatus() == dActStts_GRAB_e) {
                return procPushPullWait_init(1);
            }
            if (orderTalk()) {
                return true;
            }
            if (doTrigger()) {
                if (dComIfGp_getDoStatus() == dActStts_ba_sake__dupe_31) {
                    fopAcM_orderZHintEvent(this, dComIfGp_att_getZHint());
                    return true;
                }
                if (dComIfGp_getDoStatus() == dActStts_GET_IN_SHIP_e) {
                    return procShipReady_init();
                }
                if (dComIfGp_getDoStatus() == dActStts_CLIMB_e) {
                    if (mFrontWallType == 7) {
                        return procHangWallCatch_init();
                    } else {
                        return procVerticalJump_init();
                    }
                }
                if (dComIfGp_getDoStatus() == dActStts_OPEN_e) {
                    if (mpAttnEntryA->mType == 5) {
                        fopAcM_orderDoorEvent(this, mpAttnActorA);
#if VERSION > VERSION_DEMO
                        changeWaitProc();
#endif
                    } else {
                        fopAcM_orderTreasureEvent(this, mpAttnActorA);
                    }
                    return true;
                }
                if (dComIfGp_getDoStatus() == dActStts_LIFT_e ||
                    dComIfGp_getDoStatus() == dActStts_PICK_UP_e)
                {
                    return procGrabReady_init();
                }
                if (dComIfGp_getDoStatus() == dActStts_UNK43) {
                    return procJumpCut_init(0);
                }
                if (dComIfGp_getDoStatus() == dActStts_SIDLE_e) {
                    return procWHideReady_init(NULL, &m3724);
                }
            }
        }
    }
    if (!checkEquipAnime() && !checkPlayerGuard()) {
        if (!daPy_dmEcallBack_c::checkCurse()) {
            if (mEquipItem == daPyItem_SWORD_e) {
                if (checkNoResetFlg0(daPyFlg0_UNK4)) {
                    return procCutTurnCharge_init();
                }
                if (swordTrigger() && abs(m3578) > 0xF800) {
                    return procCutTurn_init(TRUE);
                }
                if (swordTrigger() || m34C5 != 0) {
                    return changeCutProc();
                }
            } else if (mEquipItem == daPyItem_BOKO_e) {
                if (checkNoResetFlg0(daPyFlg0_UNK4)) {
                    return procCutTurnCharge_init();
                }
                if (swordTrigger() && mActorKeepEquip.getActor() != NULL) {
                    if (abs(m3578) > 0xF800) {
                        return procCutTurn_init(TRUE);
                    } else if ((fopAcM_GetParam(mActorKeepEquip.getActor()) == 0) ||
                               (fopAcM_GetParam(mActorKeepEquip.getActor()) == 1))
                    {
                        return procWeaponNormalSwing_init();
                    } else if (fopAcM_GetParam(mActorKeepEquip.getActor()) == 4) {
                        return procWeaponSideSwing_init();
                    } else {
                        return procWeaponFrontSwingReady_init();
                    }
                }
                if (doTrigger() && dComIfGp_getDoStatus() == dActStts_THROW_e) {
                    return procWeaponThrow_init();
                }
            }
            if (itemTrigger() && mEquipItem == getReadyItem()) {
                if (mEquipItem == dItemNo_HOOKSHOT_e) {
                    if (!checkHookshotReadyAnime()) {
                        return checkNextHookshotMode();
                    }
                } else if (mEquipItem == dItemNo_GRAPPLING_HOOK_e) {
                    if (!checkRopeAnime()) {
                        return checkNextRopeMode();
                    }
                } else {
                    if (mEquipItem == dItemNo_BOOMERANG_e) {
                        return checkNextBoomerangMode();
                    }
                    if (checkBowItem(mEquipItem)) {
                        return checkNextBowMode();
                    }
                    if (mEquipItem == dItemNo_DEKU_LEAF_e) {
                        return procFanSwing_init();
                    }
                    if (mEquipItem == dItemNo_EMPTY_BOTTLE_e) {
                        return procBottleSwing_init(0);
                    }
                    if (mEquipItem == dItemNo_SKULL_HAMMER_e) {
                        direction = getDirectionFromShapeAngle();
                        if (mStickDistance > 0.05f && (direction == DIR_LEFT || direction == DIR_RIGHT)) {
                            return procHammerSideSwing_init();
                        } else {
                            return procHammerFrontSwingReady_init();
                        }
                    }
                    if (checkPhotoBoxItem(mEquipItem) || mEquipItem == dItemNo_TELESCOPE_e) {
                        return procScope_init(mEquipItem);
                    }
                    if (mEquipItem == dItemNo_WIND_WAKER_e) {
                        return procTactWait_init(-1);
                    }
                }
            }
        }
        if (changeSpecialBattle())
            return true;
    }
    if (
        dComIfGp_getRStatus() == dActStts_BLANK_e &&
#if VERSION > VERSION_DEMO
        !checkUpperReadyThrowAnime() &&
#endif
        !checkEquipAnime()
    ) {
        if (!checkGrabAnime()) {
            if (checkNoResetFlg1(daPyFlg1_NPC_CALL_COMMAND)) {
                dComIfGp_setRStatus(dActStts_CALL_e);
                if (spActionTrigger()) {
                    return procCall_init();
                }
            } else if (mEquipItem == daPyItem_BOKO_e) {
                dComIfGp_setRStatus(dActStts_DROP_e);
                if (spActionTrigger()) {
                    deleteEquipItem(FALSE);
                    m_old_fdata->initOldFrameMorf(5.0f, 0, 0x2A);
                    return true;
                }
            } else if (dComIfGs_getSelectEquip(1) == dItemNo_NONE_e ||
                       mEquipItem == daPyItem_NONE_e)
            {
                if (checkModeFlg(ModeFlg_00000001)) {
                    dComIfGp_setRStatus(dActStts_CROUCH_e);
                    if (spActionButton()) {
                        return procCrouch_init();
                    }
                }
            } else {
                if (checkGuardAccept()) {
                    dComIfGp_setRStatus(dActStts_DEFEND_e);
                    if (spActionButton()) {
                        return procCrouchDefense_init();
                    }
                }
            }
        }
    }
    if (doTrigger()) {
        if (dComIfGp_getDoStatus() == dActStts_JUMP_e) {
            direction = getDirectionFromShapeAngle();
            if (direction == DIR_LEFT || direction == DIR_RIGHT) {
                return procSideStep_init(direction);
            }
            if (direction == DIR_BACKWARD) {
                return procBackJump_init();
            }
        } else if (dComIfGp_getDoStatus() == dActStts_ATTACK_e) {
            if (!checkAttentionLock() && mStickDistance > 0.05f) {
                shape_angle.y = m34E8;
            }
            return procFrontRoll_init(m_HIO->mRoll.m.mAnmStartFrame);
        }
    }
    if (
        (daPy_getPlayerActorClass() == this && !dComIfGp_event_runCheck())
#if VERSION > VERSION_DEMO
        && !checkGrabWear()
#endif
    ) {
        onResetFlg0(daPyRFlg0_SUBJECT_ACCEPT);
        if (dComIfGp_checkCameraAttentionStatus(mCameraInfoIdx, dCamAttnStts_00001000_e)) {
            return procSubjectivity_init(0);
        }
    }
    return checkItemChangeFromButton();
}

/* 8010E828-8010EC78       .text checkNextMode__9daPy_lk_cFi */
BOOL daPy_lk_c::checkNextMode(int r29) {
    f32 f31 = mMaxNormalSpeed;
    setFrontWallType();
    
    if (checkNoResetFlg1(daPyFlg1_FORCE_VOMIT_JUMP)) {
        return procVomitJump_init(2);
    }
    if (checkNoResetFlg1(daPyFlg1_FORCE_VOMIT_JUMP_SHORT)) {
        return procVomitJump_init(3);
    }
    
    BOOL r24 = checkAttentionLock() ||
        (mActorKeepThrow.getActor() != NULL && mpAttnActorLockOn == mActorKeepThrow.getActor()) ||
        checkUpperReadyThrowAnime() ||
        mDemo.getDemoMode() == daPy_demo_c::DEMO_A_WAIT_e;
    
    if (r24) {
        mMaxNormalSpeed = m_HIO->mAtnMove.m.mMaxNormalSpeed;
    } else {
        mMaxNormalSpeed = m_HIO->mMove.m.mMaxNormalSpeed;
    }
    
    if (changeSlideProc()) {
        return true;
    }
    if (checkNextActionFromButton()) {
        return true;
    }
#if VERSION == VERSION_DEMO
    if (checkResetFlg0(daPyRFlg0_UNK10000000)) {
        return procCutReverse_init(ANM_CUTRER);
    }
#endif
    if (r29 != 0 && !(mStickDistance > 0.05f) && !spActionButton()) {
        mMaxNormalSpeed = f31;
        return false;
    }

    BOOL r3;
    if (r24) {
        if (checkBoomerangAnime()) {
            r3 = checkNextBoomerangMode();
        } else if (checkBowAnime()) {
            r3 = checkNextBowMode();
        } else if (checkHookshotReadyAnime()) {
            r3 = checkNextHookshotMode();
        } else if (checkRopeAnime()) {
            r3 = checkNextRopeMode();
        } else if (mpAttnActorLockOn != NULL || (mDemo.getDemoMode() == daPy_demo_c::DEMO_A_WAIT_e)) {
            if (std::abs(mNormalSpeed) <= 0.001f) {
                r3 = procAtnActorWait_init();
            } else {
                r3 = procAtnActorMove_init();
            }
        } else if (std::abs(mNormalSpeed) <= 0.001f) {
            r3 = changeWaitProc();
        } else {
            r3 = procAtnMove_init();
        }
    } else {
        mDirection = DIR_NONE;
        int direction = getDirectionFromCurrentAngle();
        if (std::abs(mNormalSpeed) <= 0.001f) {
            if (cLib_distanceAngleS(m34E8, current.angle.y) > 0x7800 && mStickDistance > 0.05f)
            {
                r3 = procWaitTurn_init();
                if (!r3 && !dComIfGp_event_runCheck() && !checkPlayerDemoMode())
                {
                    r3 = changeWaitProc();
                }
            } else {
                r3 = changeWaitProc();
            }
        } else if (mCurProc == daPyProc_MOVE_TURN_e && current.angle.y != shape_angle.y) {
            r3 = procMoveTurn_init(0);
        } else if (cLib_distanceAngleS(m34E8, current.angle.y) > 0x7800 &&
                   mStickDistance > 0.05f)
        {
            if ((speedF / mMaxNormalSpeed > m_HIO->mSlip.m.mSpeedRatioMin) &&
                mCurrAttributeCode != dBgS_Attr_ICE_e &&
                (!checkGrabAnime() && getDirectionFromAngle(m34EA - m34DC) == DIR_BACKWARD))
            {
                r3 = procSlip_init();
            } else {
                r3 = procMoveTurn_init(1);
            }
        } else if (direction == DIR_BACKWARD && mStickDistance > 0.05f) {
            r3 = procMoveTurn_init(1);
        } else {
            r3 = procMove_init();
        }
    }
    
    if (!r3) {
        r3 = checkJumpFlower();
    }
    return r3;
}

/* 8010FEC4-8010FFB0       .text changeSlideProc__9daPy_lk_cFv */
int daPy_lk_c::changeSlideProc() {
    s16 sVar4;

    cM3dGPla* pfVar1 = getSlidePolygon();
    if (pfVar1 != NULL) {
        sVar4 = cM_atan2s(pfVar1->GetNP()->x, pfVar1->GetNP()->z);
        if (m34C3 != 0) {
            cLib_addCalc(&mNormalSpeed, 0.0f, 0.4f, 5.0f, 1.0f);
            m3526--;
            if (mNormalSpeed > 5.0f || m3526 > 0) {
                return false;
            }
        }
        if (cLib_distanceAngleS(sVar4, shape_angle.y) < m_HIO->mSlide.m.mFrontAngleRange) {
            return procSlideFront_init(sVar4);
        } else {
            return procSlideBack_init(sVar4);
        }
    } else {
        m3526 = 8;
        return false;
    }
}

/* 8010FFB0-80110028       .text changeWaitProc__9daPy_lk_cFv */
BOOL daPy_lk_c::changeWaitProc() {
    if (checkGrabAnime()) {
        return procGrabWait_init();
    } else if (checkUpperAnime(dRes_INDEX_LKANM_BCK_BOOMCATCH_e)) {
        return procBoomerangCatch_init();
    } else if (daPy_getPlayerActorClass() != this) {
        return procControllWait_init();
    } else {
        return procWait_init();
    }
}

BOOL daPy_lk_c::procWait_init() {
    if (mDemo.getDemoMode() == daPy_demo_c::DEMO_KM_WAIT_e && m_tex_scroll_heap.field_0x6 == 0xFFFF) {
        changeTextureAnime(dRes_INDEX_LKANM_BTP_TMABACC_e, dRes_INDEX_LKANM_BTK_TEUR_e, -1);
        voiceStart(38);
        mProcVar0.m34D0 = 20;
    }
    if (mCurProc == daPyProc_WAIT_e) {
        return false;
    }
    if (!dComIfGp_event_runCheck() && mCurProc == daPyProc_FREE_WAIT_e &&
        mFrameCtrlUnder[UNDER_MOVE0_e].getRate() > 0.01f && checkNoUpperAnime())
    {
        return false;
    }
    int iVar3 = checkPlayerGuard();
    commonProcInit(daPyProc_WAIT_e);
    mNormalSpeed = 0.0f;
    int iVar4 = checkRestHPAnime();
    if (iVar4 != 0 && iVar3 == 0) {
        s32 uVar2 = m_tex_anm_heap.mIdx == mTexAnmIndexTable[daPyFace_TMABAF].mBtpIdx;
        u16 uVar1 = m3530;
        setSingleMoveAnime(ANM_WAITATOB, m_HIO->mMove.m.field_0x68, m_HIO->mMove.m.field_0x6C, m_HIO->mMove.m.field_0x10, m_HIO->mMove.m.field_0x70);
        if (uVar2 == 0) {
            onModeFlg(ModeFlg_00000400);
            offModeFlg(ModeFlg_00000100);
        } else {
            setTextureAnime(0xe, uVar1);
        }
    } else {
        setBlendMoveAnime(m_HIO->mBasic.m.mAnmMorf);
    }
    current.angle.y = shape_angle.y;
    mDirection = DIR_NONE;
    m35A0 = 0.0f;
    f32 dVar5 = cM_rndF(150.0f);
    mProcVar1.m34D2 = (s16)(300.0f + dVar5);
    return true;
}

/* 80113044-801133FC       .text procWait__9daPy_lk_cFv */
BOOL daPy_lk_c::procWait() {
    if (m36A0.abs2XZ() <= SQUARE(1.0f / 1000.0f) && m36AC.abs2XZ() >= SQUARE(5.0f)) {
        return procIceSlipAlmostFall_init();
    }
    if (!dComIfGp_event_runCheck() && !checkPlayerDemoMode() && spLTrigger() && mAcch.ChkWallHit()) {
        dBgS_AcchCir* pdVar5 = &mAcchCir[0];
        for (int i = 0; i < 3; i++, pdVar5++) {
            if (pdVar5->ChkWallHit()) {
                s16 sVar4 = pdVar5->GetWallAngleY() + 0x8000;
                if (cLib_distanceAngleS(shape_angle.y, sVar4) <= 0x2000) {
                    shape_angle.y = sVar4;
                    current.angle.y = shape_angle.y;
                    m34E6 = shape_angle.y;
                }
                break;
            }
        }
    }
    s16 sVar2 = shape_angle.y;
    if (checkAttentionLock()) {
        setSpeedAndAngleAtn();
    } else {
        setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0);
    }
    m35A0 = 0.0f;
    if (!checkNextMode(0)) {
        if (m34C3 == 0) {
            if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f || !checkRestHPAnime()) {
                setBlendMoveAnime(m_HIO->mBasic.m.mAnmMorf);
                offModeFlg(ModeFlg_00000400);
                onModeFlg(ModeFlg_00000100);
            }
        } else if (checkRestHPAnime() &&
                   m_anm_heap_under[UNDER_MOVE0_e].mIdx != dRes_INDEX_LKANM_BCK_WAITB_e)
        {
            s32 uVar3 = m_tex_anm_heap.mIdx == mTexAnmIndexTable[daPyFace_TMABAF].mBtpIdx;
            u16 uVar1 = m3530;
            setSingleMoveAnime(ANM_WAITATOB, m_HIO->mMove.m.field_0x68, m_HIO->mMove.m.field_0x6C, m_HIO->mMove.m.field_0x10, m_HIO->mMove.m.field_0x70);
            if (uVar3 == 0) {
                onModeFlg(ModeFlg_00000400);
                offModeFlg(ModeFlg_00000100);
            } else {
                setTextureAnime(0xe, uVar1);
            }
        } else {
            m35A0 = 0.005f * (s16)(shape_angle.y - sVar2);
            setBlendMoveAnime(-1.0f);
        }
        if (mDemo.getDemoMode() == daPy_demo_c::DEMO_KM_WAIT_e) {
            if (mProcVar0.m34D0 != 0) {
                mProcVar0.m34D0--;
            } else if (cM_rnd() < 0.05f) {
                voiceStart(38);
                mProcVar0.m34D0 = 20;
            }
        }
        if (!dComIfGp_event_runCheck() && m_anm_heap_under[UNDER_MOVE0_e].mIdx == dRes_INDEX_LKANM_BCK_WAITS_e &&
            checkNoUpperAnime() && daPy_matAnm_c::getEyeMoveFlg() == 0 && m3564.y == 0 && m3564.z == 0 && m3564.x == 0)
        {
            mProcVar1.m34D2--;
            if (mProcVar1.m34D2 == 0) {
                procFreeWait_init();
            }
        } else {
            mProcVar1.m34D2 = (s16)(300.0f + cM_rndF(150.0f));
        }
    }
    return true;
}

/* 801133FC-801134A0       .text procFreeWait_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procFreeWait_init() {
    daPy_ANM dVar1;
    f32 dVar2;

    commonProcInit(daPyProc_FREE_WAIT_e);
    mNormalSpeed = 0.0f;
    dVar2 = cM_rnd();
    mProcVar6.m3570 = 0;
    if (dVar2 < 0.3333f) {
        dVar1 = ANM_FREEA;
    } else if (dVar2 < 0.6666f) {
        dVar1 = ANM_FREEB;
        mProcVar6.m3570 = 1;
    } else {
        dVar1 = ANM_FREED;
    }
    setSingleMoveAnime(dVar1, 1.0f, 0.0f, -1, 5.0f);
    current.angle.y = shape_angle.y;
    mDirection = DIR_NONE;
    return true;
}

/* 801134A0-801135C4       .text procFreeWait__9daPy_lk_cFv */
BOOL daPy_lk_c::procFreeWait() {
    if (checkAttentionLock()) {
        setSpeedAndAngleAtn();
    } else {
        setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0);
    }
    if (mProcVar6.m3570 != 0) {
        if (mFrameCtrlUnder[UNDER_MOVE0_e].checkPass(168.0f)) {
            voiceStart(48);
        } else {
            if (mFrameCtrlUnder[UNDER_MOVE0_e].checkPass(105.0f)) {
                voiceStart(47);
            }
        }
    }
    if (!checkNextMode(0) && dComIfGp_event_runCheck()) {
        mFrameCtrlUnder[UNDER_MOVE0_e].setRate(0.0f);
        procWait_init();
    }
    return true;
}

/* 801135C4-80113628       .text procMove_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procMove_init() {
    if (mCurProc == daPyProc_MOVE_e) {
        return false;
    }
    commonProcInit(daPyProc_MOVE_e);
    setBlendMoveAnime(m_HIO->mBasic.m.mAnmMorf);
    mProcVar0.m34D0 = 20;
    return true;
}

/* 80113628-801136D4       .text procMove__9daPy_lk_cFv */
BOOL daPy_lk_c::procMove() {
    setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0);
    if (!checkNextMode(0) && !changeFrontWallTypeProc() && !checkIceSlipFall()) {
        if (mDemo.getDemoMode() == daPy_demo_c::DEMO_N_WALK_e) {
            if (mNormalSpeed > mMaxNormalSpeed * m_HIO->mMove.m.field_0x2C) {
                mNormalSpeed = m_HIO->mMove.m.field_0x2C * mMaxNormalSpeed;
            }
        }
        setBlendMoveAnime(-1.0f);
    }
    return true;
}

BOOL daPy_lk_c::procMoveTurn_init(int param) {
    if (mCurProc == daPyProc_MOVE_TURN_e) {
        return false;
    }
    commonProcInit(daPyProc_MOVE_TURN_e);
    setBlendMoveAnime(m_HIO->mBasic.m.mAnmMorf);
    dComIfGp_setPlayerStatus0(0, daPyStts0_UNK800_e);
    if (param != 0) {
        mProcVar2.m34D4 = (m_HIO->mMove.m.field_0x0 * 4) + 0x4A56;
        mProcVar3.m34D6 = m_HIO->mMove.m.field_0x0 * 2;
        mProcVar0.m34D0 = 2;
        current.angle.y = m34E8;
        mNormalSpeed *= 0.5f;
    } else {
        mProcVar2.m34D4 = m_HIO->mMove.m.field_0x0 * 2;
        mProcVar3.m34D6 = m_HIO->mMove.m.field_0x0;
        mProcVar0.m34D0 = 3;
    }
    return true;
}

BOOL daPy_lk_c::procMoveTurn() {
    setSpeedAndAngleNormal(m_HIO->mMove.m.field_0x0);
    cLib_addCalcAngleS(&shape_angle.y, current.angle.y,
                      mProcVar0.m34D0, mProcVar2.m34D4, mProcVar3.m34D6);
    if (!checkNextMode(0)) {
        setBlendMoveAnime(-1.0f);
    }
    return true;
}

BOOL daPy_lk_c::procSlip_init() {
    commonProcInit(daPyProc_SLIP_e);
    daPy_matAnm_c::offMabaFlg();
    setSingleMoveAnime(ANM_SLIP, m_HIO->mSlip.m.field_0xC, 0.0f, -1,
                       m_HIO->mSlip.m.field_0x1C);
    mNormalSpeed = speedF * m_HIO->mSlip.m.field_0x8;
    if (m_HIO->mSlip.m.field_0x0 == 1) {
        mNormalSpeed = mMaxNormalSpeed;
    } else if (m_HIO->mSlip.m.field_0x0 == 2 && mNormalSpeed > mMaxNormalSpeed) {
        mNormalSpeed = mMaxNormalSpeed;
    }
    setFootEffectPosType(2);
    seStartMapInfo(JA_SE_LK_RUN_SLIP);
    return true;
}

BOOL daPy_lk_c::procSlip() {
    f32 remaining = cLib_addCalc(&mNormalSpeed, 0.0f, m_HIO->mSlip.m.field_0x18,
                                m_HIO->mSlip.m.field_0x10, m_HIO->mSlip.m.field_0x14);
    if (remaining <= 0.001f) {
        if (mStickDistance > 0.05f) {
            current.angle.y = shape_angle.y + 0x8000;
            shape_angle.y = shape_angle.y + 0x100;
            mNormalSpeed = mMaxNormalSpeed * 0.5f;
            procMoveTurn_init(0);
        } else {
            checkNextMode(0);
        }
    } else if (mAcch.ChkWallHit()) {
        mNormalSpeed = 0.0f;
        checkNextMode(0);
        return true;
    } else {
        if (mNormalSpeed < m_HIO->mSlip.m.field_0x20) {
            resetFootEffect();
        }
        cXyz start = current.pos;
        start.y += 2.5f;
        cXyz end(start.x + 50.0f * cM_ssin(current.angle.y), start.y,
                 start.z + 50.0f * cM_scos(current.angle.y));
        mLinkLinChk.Set(&start, &end, this);
        if (dComIfG_Bgsp()->LineCross(&mLinkLinChk)) {
            cM3dGPla* plane = dComIfG_Bgsp()->GetTriPla(mLinkLinChk);
            if (cBgW_CheckBWall(plane->GetNP()->y)) {
                mNormalSpeed = 0.0f;
                checkNextMode(0);
            }
        }
    }
    return true;
}

BOOL daPy_lk_c::procWaitTurn_init() {
    if (mCurProc == daPyProc_WAIT_TURN_e) {
        return false;
    }
    commonProcInit(daPyProc_WAIT_TURN_e);
    setSingleMoveAnime(ANM_ROT, m_HIO->mBasic.m.field_0x4, 0.0f, -1, m_HIO->mBasic.m.mAnmMorf);
    if (dComIfGp_event_runCheck()) {
        mNormalSpeed = 0.0f;
    }
    mProcVar2.m34D4 = m34E8;
    current.angle.y = shape_angle.y;
    return true;
}

BOOL daPy_lk_c::procWaitTurn() {
    cLib_addCalc(&mNormalSpeed, 0.0f, m_HIO->mMove.m.field_0x24, m_HIO->mMove.m.field_0x1C,
                 m_HIO->mMove.m.field_0x20);
    if (changeSlideProc()) {
        return true;
    }
    s16 sVar1 = cLib_addCalcAngleS(&shape_angle.y, mProcVar2.m34D4, m_HIO->mTurn.m.field_0x4,
                                   m_HIO->mTurn.m.field_0x0, m_HIO->mTurn.m.field_0x2);
    current.angle.y = shape_angle.y;
    if (checkNextActionFromButton()) {
        return true;
    }
    if (sVar1 == 0) {
        if (dComIfGp_event_runCheck()) {
            if (mDemo.getDemoMode() == daPy_demo_c::DEMO_WAIT_TURN_e) {
                dComIfGp_evmng_cutEnd(mStaffIdx);
            } else {
                checkNextMode(0);
            }
        } else {
            checkNextMode(0);
        }
    }
    return true;
}

BOOL daPy_lk_c::procAtnMove_init() {
    if (mCurProc == daPyProc_ATN_MOVE_e) {
        return false;
    }
    commonProcInit(daPyProc_ATN_MOVE_e);
    setBlendAtnMoveAnime(m_HIO->mBasic.m.mAnmMorf);
    mProcVar0.m34D0 = 20;
    return true;
}

BOOL daPy_lk_c::procAtnMove() {
    setSpeedAndAngleAtn();
    if (!checkNextMode(0) && (mDirection != DIR_FORWARD || !changeFrontWallTypeProc()) && !checkIceSlipFall()) {
        setBlendAtnMoveAnime(-1.0f);
    }
    return true;
}

BOOL daPy_lk_c::procSideStep_init(int param_1) {
    commonProcInit(daPyProc_SIDE_STEP_e);
    mDirection = param_1;
    daPy_ANM anm;
    if (param_1 == DIR_LEFT) {
        anm = ANM_ATNJL;
        current.angle.y = shape_angle.y + 0x4000;
    } else {
        anm = ANM_ATNJR;
        current.angle.y = shape_angle.y + -0x4000;
    }
    setSingleMoveAnime(anm, m_HIO->mSideStep.m.field_0xC, m_HIO->mSideStep.m.field_0x10, m_HIO->mSideStep.m.field_0x4, m_HIO->mSideStep.m.field_0x14);
    mNormalSpeed = cM_scos(m_HIO->mSideStep.m.field_0x2) * m_HIO->mSideStep.m.field_0x8;
    speed.y = cM_ssin(m_HIO->mSideStep.m.field_0x2) * m_HIO->mSideStep.m.field_0x8;
    gravity = m_HIO->mSideStep.m.field_0x18;
    mProcVar6.m3570 = 0;
    voiceStart(5);
    return true;
}

BOOL daPy_lk_c::procSideStep() {
    if (m_HIO->mSideStep.m.field_0x0 != 0) {
        if (mpAttnActorLockOn != NULL) {
            s16 sVar2 = fopAcM_searchActorAngleY(this, mpAttnActorLockOn);
            cLib_addCalcAngleS(&shape_angle.y, sVar2, 5, 0x5e8, 0x13c);
        }
        if (mDirection == DIR_LEFT) {
            current.angle.y = shape_angle.y + 0x4000;
        } else {
            current.angle.y = shape_angle.y + -0x4000;
        }
    }
    checkNextActionItemFly();
    if (mAcch.ChkGroundHit()) {
        procSideStepLand_init();
    } else {
        if (checkJumpCutFromButton()) {
            return true;
        }
        if (checkFanGlideProc(0)) {
            return true;
        }
        if (current.pos.y < m3688.y - m_HIO->mSideStep.m.field_0x30) {
            procFall_init(2, m_HIO->mSideStep.m.field_0x2C);
        }
    }
    checkItemChangeFromButton();
    return true;
}

BOOL daPy_lk_c::procSideStepLand_init() {
    commonProcInit(daPyProc_SIDE_STEP_LAND_e);
    mNormalSpeed = 0.0f;
    daPy_ANM anm;
    if (mDirection == DIR_LEFT) {
        anm = ANM_ATNJLLAND;
    } else {
        anm = ANM_ATNJRLAND;
    }
    setSingleMoveAnime(anm, m_HIO->mSideStep.m.field_0x1C, m_HIO->mSideStep.m.field_0x20, m_HIO->mSideStep.m.field_0x6, m_HIO->mSideStep.m.field_0x24);
    setFootEffectPosType(3);
    onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
    onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
    current.angle.y += 0x8000;
    if (checkHeavyStateOn()) {
        dComIfGp_getVibration().StartShock(5, -0x31, cXyz(0.0f, 1.0f, 0.0f));
    }
    return true;
}

BOOL daPy_lk_c::procSideStepLand() {
    resetFootEffect();
    if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        checkNextMode(0);
    } else {
        if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mSideStep.m.field_0x28) {
            checkNextMode(1);
        }
    }
    return true;
}

/* 801143D4-80114440       .text procCrouch_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCrouch_init() {
    commonProcInit(daPyProc_CROUCH_e);
    setSingleMoveAnime(ANM_CROUCH, m_HIO->mCrouch.m.field_0x18, 0.0f, -1, m_HIO->mCrouch.m.field_0x1C);
    deleteEquipItem(FALSE);
    current.angle.y = shape_angle.y;
    return true;
}

/* 80114440-8011476C       .text procCrouch__9daPy_lk_cFv */
BOOL daPy_lk_c::procCrouch() {
    cXyz acStack_20;
    cXyz cStack_2c;
    cXyz cStack_38;
    cXyz local_5c;
    cXyz local_68;

    dComIfGp_setRStatus(dActStts_CROUCH_e);
    if (dCam_getBody()->ChangeModeOK(4) && current.pos.y >= mWaterY) {
        onResetFlg0(daPyRFlg0_SUBJECT_ACCEPT);
        if (dComIfGp_checkCameraAttentionStatus(mCameraInfoIdx, dCamAttnStts_00001000_e) && !dComIfGp_event_runCheck()) {
            return procSubjectivity_init(1);
        }
    }
    cLib_addCalc(&mNormalSpeed, 0.0f, m_HIO->mMove.m.field_0x24, m_HIO->mMove.m.field_0x1C,
                 m_HIO->mMove.m.field_0x20);
    if (!spActionButton() ||
        (checkAttentionLock() && checkShieldEquip() && checkGuardAccept()))
    {
        checkNextMode(0);
    } else if (m_old_fdata->getOldFrameRate() < 0.01f && mStickDistance > 0.05f && !checkCrawlWaterIn()) {
        mDoMtx_stack_c::transS(current.pos.x, current.pos.y, current.pos.z);
        mDoMtx_stack_c::ZXYrotM(m34E2, shape_angle.y, 0);
        mDoMtx_stack_c::multVec(&l_crawl_start_front_offset, &acStack_20);
        mDoMtx_stack_c::multVec(&l_crawl_top_offset, &cStack_2c);
        if (getCrawlMoveVec(&cStack_2c, &acStack_20, &cStack_38)) {
            local_5c = current.pos - cStack_38;
            local_5c.y += 5.0f;
            mGndChk.SetPos(&local_5c);
            local_5c.y = dComIfG_Bgsp()->GroundCross(&mGndChk);
            local_68 = current.pos - local_5c;
            if (cLib_distanceAngleS(cM_atan2s(-local_68.y, local_68.absXZ()), m34E2) > 0x100) {
                return true;
            }
        }
        procCrawlStart_init();
    }
    return true;
}

BOOL daPy_lk_c::checkRestHPAnime() {
    if (!checkPlayerGuard() && checkNoUpperAnime() && mpAttnActorLockOn == NULL &&
        ((!checkPlayerDemoMode() && !checkModeFlg(ModeFlg_IN_SHIP) &&
          dComIfGs_getLife() <= m_HIO->mMove.m.field_0xE) ||
         mDemo.getDemoMode() == daPy_demo_c::DEMO_UNK_018_e))
    {
        return true;
    }
    return false;
}

s16 daPy_lk_c::getGroundAngle(cBgS_PolyInfo* param_1, s16 param_2) {
    cM3dGPla* plane = dComIfG_Bgsp()->GetTriPla(*param_1);
    if (plane == NULL || !cBgW_CheckBGround(plane->GetNP()->y)) {
        return 0;
    }
    cXyz* norm = plane->GetNP();
    f32 cos = cM_scos((cM_atan2s(norm->x, norm->z) - param_2));
    f32 xz = (ppc::sqrtf_msl(norm->x * norm->x + norm->z * norm->z));
    xz *= cos;
    return cM_atan2s(xz, norm->y);
}

/* 801152D0-80115478       .text procFrontRoll_init__9daPy_lk_cFf */
BOOL daPy_lk_c::procFrontRoll_init(f32 param_1) {
    commonProcInit(daPyProc_FRONT_ROLL_e);
    setSingleMoveAnime(ANM_ROLLF, m_HIO->mRoll.m.mAnmRate, param_1, m_HIO->mRoll.m.mAnmEndFrame, m_HIO->mRoll.m.mAnmMorf);
    mNormalSpeed = speedF * m_HIO->mRoll.m.mSpeedMul + m_HIO->mRoll.m.mSpeedAdd;
    if (checkHeavyStateOn()) {
        mNormalSpeed *= m_HIO->mMove.m.mHeavyStateScale;
    }
    if (mNormalSpeed < m_HIO->mRoll.m.mSpeedMin) {
        mNormalSpeed = m_HIO->mRoll.m.mSpeedMin;
    } else {
        param_1 = m_HIO->mRoll.m.mSpeedAdd +
                  m_HIO->mMove.m.mMaxNormalSpeed * m_HIO->mRoll.m.mSpeedMul;
        if (checkHeavyStateOn()) {
            param_1 *= m_HIO->mMove.m.mHeavyStateScale;
        }
        if (mNormalSpeed > param_1) {
            mNormalSpeed = param_1;
        }
    }
    current.angle.y = shape_angle.y;
    if (mAcchCir[0].ChkWallHit() &&
        cLib_distanceAngleS(current.angle.y + 0x8000, mAcchCir[0].GetWallAngleY()) <= m_HIO->mRoll.m.mWallHitAngleRange)
    {
        mProcVar6.m3570 = 0;
    } else {
        mProcVar6.m3570 = 1;
    }
    offNoResetFlg0(daPyFlg0_UNK8);
    mProcVar2.m34D4 = 0;
    voiceStart(7);
    return true;
}

/* 80115478-80115628       .text procFrontRoll__9daPy_lk_cFv */
BOOL daPy_lk_c::procFrontRoll() {
    if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > 6.0f) {
        setFootEffectPosType(4);
        endFlameDamageEmitter();
    }
    if (getSlidePolygon() != NULL) {
        cLib_addCalc(&mNormalSpeed, 0.0f, 0.5f, 2.5f, 0.1f);
    }
    if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        if (mStickDistance <= 0.05f) {
            mNormalSpeed -= m_HIO->mRoll.m.mSpeedMin;
        }
        checkNextMode(0);
    } else {
        if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mRoll.m.mEarlyEndFrame) {
            checkNextMode(1);
        } else {
            if (speedF >= m_HIO->mRoll.m.mWallHitSpeedMin &&
                !checkNoResetFlg1(daPyFlg1_UNK100000))
            {
                if (checkNoResetFlg0(daPyFlg0_UNK8) ||
                    (mProcVar6.m3570 != 0 && mAcch.ChkWallHit() && mAcchCir[0].ChkWallHit() &&
                     cLib_distanceAngleS(current.angle.y + 0x8000, mAcchCir[0].GetWallAngleY()) <=
                         m_HIO->mRoll.m.mWallHitAngleRange &&
                     mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() >= m_HIO->mRoll.m.mWallHitFrameMin &&
                     mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() <= m_HIO->mRoll.m.mWallHitFrameMax))
                {
                    if (!checkNoResetFlg0(daPyFlg0_UNK8)) {
                        m3620 = dComIfG_Bgsp()->GetMtrlSndId(mAcchCir[0]);
                    }
                    procFrontRollCrash_init();
                }
            }
        }
    }
    return true;
}

BOOL daPy_lk_c::procBackJump_init() {
    f32 fVar1;

    if (mCurProc == daPyProc_BACK_JUMP_e) {
        return false;
    }
    commonProcInit(daPyProc_BACK_JUMP_e);
    if (checkHeavyStateOn()) {
        mNormalSpeed = 0.5f * m_HIO->mBackJump.m.field_0x10;
        fVar1 = 1.5f * m_HIO->mBackJump.m.field_0x4;
    } else {
        mNormalSpeed = m_HIO->mBackJump.m.field_0x10;
        fVar1 = m_HIO->mBackJump.m.field_0x4;
    }
    setSingleMoveAnime(ANM_ROLLB, fVar1, m_HIO->mBackJump.m.field_0x8, m_HIO->mBackJump.m.field_0x0, m_HIO->mBackJump.m.field_0xC);
    speed.y = m_HIO->mBackJump.m.field_0x14;
    gravity = m_HIO->mBackJump.m.field_0x18;
    current.angle.y = shape_angle.y + 0x8000;
    voiceStart(7);
    return true;
}

BOOL daPy_lk_c::procBackJump() {
    if (mAcch.ChkGroundHit() && mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        procBackJumpLand_init();
    } else {
        if (checkFanGlideProc(0)) {
            return true;
        }
        if (current.pos.y < m3688.y - m_HIO->mBackJump.m.field_0x1C) {
            procFall_init(2, m_HIO->mBackJump.m.field_0x20);
        }
    }
    checkItemChangeFromButton();
    return true;
}

BOOL daPy_lk_c::procBackJumpLand_init() {
    commonProcInit(daPyProc_BACK_JUMP_LAND_e);
    mNormalSpeed = 0.0f;
    setSingleMoveAnime(
        ANM_ROLLBLAND,
        m_HIO->mBackJump.m.field_0x24,
        m_HIO->mBackJump.m.field_0x28,
        m_HIO->mBackJump.m.field_0x2,
        m_HIO->mBackJump.m.field_0x2C
    );
    setFootEffectPosType(3);
    onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
    onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
    current.angle.y = shape_angle.y;
    if (checkHeavyStateOn()) {
        dComIfGp_getVibration().StartShock(5, -0x31, cXyz(0.0f, 1.0f, 0.0f));
    }
    if ((mEquipItem == daPyItem_SWORD_e || mEquipItem == daPyItem_BOKO_e) &&
        !daPy_dmEcallBack_c::checkCurse() && checkNoUpperAnime())
    {
        mProcVar6.m3570 = 1;
    }
#if VERSION > VERSION_DEMO
    else {
        mProcVar6.m3570 = 0;
    }
#endif
    return true;
}

BOOL daPy_lk_c::procBackJumpLand() {
    resetFootEffect();
    if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        if (dComIfGp_event_runCheck()) {
            dComIfGp_evmng_cutEnd(mStaffIdx);
        } else {
            checkNextMode(0);
        }
    } else if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mBackJump.m.field_0x30) {
        checkNextMode(1);
    } else if (mProcVar6.m3570 != 0) {
        mProcVar6.m3570 = 0;
        if (
            abs(m3578) > 0xF800
#if VERSION > VERSION_DEMO
            && mEquipItem == daPyItem_SWORD_e
#endif
        ) {
            procCutTurn_init(TRUE);
        }
    }
    return true;
}

f32 daPy_lk_c::getBlurTopRate() {
    if (mCurProc == daPyProc_DEMO_LAST_COMBO_e) {
        return 0.0f;
    }
    
    if (mEquipItem == daPyItem_SWORD_e) {
        if (checkNormalSwordEquip()) {
            return 0.5f;
        } else {
            return 1.0f;
        }
    }
    
    if (mEquipItem == daPyItem_BOKO_e) {
        if (mActorKeepEquip.getActor() == NULL) {
            return 0.0f;
        }
        daBoko_c* boko = (daBoko_c*)mActorKeepEquip.getActor();
        if (mCurProc == daPyProc_JUMP_CUT_e || mCurProc == daPyProc_JUMP_CUT_LAND_e) {
            return boko->getJumpBlurRate();
        } else {
            return boko->getBlurRate();
        }
    }
    
    return 0.0f;
}

void daPy_lk_c::setAttentionPos() {
    cXyz* pcVar3;
    cXyz afStack_18;

    attention_info.position.x = current.pos.x;
    attention_info.position.z = current.pos.z;
    daShip_c* ship = (daShip_c*)dComIfGp_getShipActor();
    if (checkModeFlg(ModeFlg_CRAWL)) {
        {
            static const Vec offset = {0.0f, 30.0f, 20.0f};
            mDoMtx_multVec(mpCLModel->getBaseTRMtx(), &offset, &attention_info.position);
        }
    } else if (dComIfGp_checkPlayerStatus0(0, daPyStts0_SUBJECT_e)) {
        {
            static const Vec offset = {0.0f, 70.0f, 0.0f};
            mDoMtx_stack_c::ZXYrotS(mBodyAngle.x, shape_angle.y, 0);
            mDoMtx_stack_c::multVec(&offset, &afStack_18);
            attention_info.position.y = 26.3f + current.pos.y;
            pcVar3 = &attention_info.position;
            *pcVar3 += afStack_18;
        }
    } else if (checkModeFlg(ModeFlg_CROUCH)) {
        attention_info.position.x += 20.0f * cM_ssin(shape_angle.y);
        attention_info.position.y = 46.25f + current.pos.y;
        attention_info.position.z += 20.0f * cM_scos(shape_angle.y);
    } else if (checkModeFlg(ModeFlg_ROPE)) {
        attention_info.position = current.pos;
    } else if (checkModeFlg(ModeFlg_HANG)) {
        attention_info.position.y = 92.5f + mCyl.GetCP()->y;
    } else if (checkModeFlg(ModeFlg_SWIM)) {
        attention_info.position.y = 20.05f + current.pos.y;
    } else if (checkModeFlg(ModeFlg_WHIDE) && checkNoResetFlg0(daPyFlg0_UNK10000)) {
        attention_info.position.y = (92.5f + mpCLModel->getBaseTRMtx()[1][3]) - 30.0f;
    } else if (checkModeFlg(ModeFlg_IN_SHIP) && ship != NULL && !ship->getFlyFlg()) {
        // !@bug(?): l_ship_offset is probably supposed to be x, not z.
        attention_info.position.x = ship->current.pos.x + cM_ssin(ship->shape_angle.y) * l_ship_offset.z;
        if (checkNoResetFlg0(daPyFlg0_UNK80)) {
            attention_info.position.y = 92.5f + (mWaterY + l_ship_offset.y);
        } else {
            attention_info.position.y = 92.5f + mpCLModel->getBaseTRMtx()[1][3];
        }
        attention_info.position.z = ship->current.pos.z + cM_scos(ship->shape_angle.y) * l_ship_offset.z;
        return;
    } else {
        attention_info.position.y = 92.5f + mpCLModel->getBaseTRMtx()[1][3];
    }
}

void daPy_lk_c::setBgCheckParam() {
    mAcchCir[0].SetWallH(30.1f);
    mAcchCir[1].SetWallH(89.9f);
    mAcchCir[2].SetWallH(125.0f);
    
    if (mCurProc == daPyProc_ROPE_SWING_START_e) {
        mAcchCir[0].SetWallH(-125.0f);
        mAcchCir[1].SetWallH(-89.9f);
        mAcchCir[2].SetWallH(0.0f);
    } else if (mCurProc == daPyProc_LARGE_DAMAGE_WALL_e || checkModeFlg(ModeFlg_CLIMB | ModeFlg_LADDER)) {
        mAcchCir[0].SetWallR(5.0f);
    } else if (checkModeFlg(ModeFlg_PUSHPULL)) {
        mAcchCir[0].SetWallR(40.0f);
    } else if (checkModeFlg(ModeFlg_WHIDE)) {
        mAcchCir[0].SetWallR(m_HIO->mWall.m.field_0x50);
        if (checkNoResetFlg0(daPyFlg0_UNK10000)) {
            mAcchCir[2].SetWallH(89.9f);
        }
    } else if (checkModeFlg(ModeFlg_SWIM)) {
        mAcchCir[0].SetWallR(67.5f);
        mAcchCir[0].SetWallH(-5.0f);
        mAcchCir[1].SetWallH(0.0f);
        mAcchCir[2].SetWallH(20.0f);
    } else if (checkModeFlg(ModeFlg_CRAWL) && mCurProc != daPyProc_CRAWL_END_e) {
        mAcchCir[0].SetWallR(30.0f);
        mAcchCir[0].SetWallH(10.0f);
        mAcchCir[1].SetWallH(50.0f);
        mAcchCir[2].SetWallH(50.0f);
    } else if (checkModeFlg(ModeFlg_HANG)) {
        mAcchCir[0].SetWallR(12.5f);
        mAcchCir[0].SetWallH(25.0f);
        mAcchCir[1].SetWallH(25.0f);
        mAcchCir[2].SetWallH(25.0f);
    } else if (checkGrabWear()) {
        mAcchCir[0].SetWallR(50.0f);
    } else {
        mAcchCir[0].SetWallR(35.0f);
    }
    
    mAcchCir[1].SetWallR(mAcchCir[0].GetWallR());
    mAcchCir[2].SetWallR(mAcchCir[0].GetWallR());
}

int daPy_lk_c::setMoveAnime(f32 f27, f32 f28, f32 f25, daPy_ANM r27, daPy_ANM r28, int r29, f32 i_morf) {
    J3DAnmTransform* r3 = mAnmRatioUnder[UNDER_MOVE0_e].getAnmTransform();
    J3DFrameCtrl& frameCtrl0 = mFrameCtrlUnder[UNDER_MOVE0_e];
    J3DFrameCtrl& frameCtrl1 = mFrameCtrlUnder[UNDER_MOVE1_e];
    f32 f31;
    if ((m34C3 == 0 || m34C3 == 9) || m34C3 == 10) {
        f31 = 0.0f;
    } else {
        f31 = r3->getFrame() / r3->getFrameMax();
    }
    const daPy_anmIndex_c* r25 = getAnmData(r27);
    const daPy_anmIndex_c* r24 = getAnmData(r28);
    J3DAnmTransform* sp14;
    J3DAnmTransform* sp10;
    getUnderUpperAnime(r25, &sp14, &sp10, 0, 0x2400);
    J3DAnmTransform* sp0C;
    J3DAnmTransform* sp08;
    getUnderUpperAnime(r24, &sp0C, &sp08, 1, 0x2400);
    mAnmRatioUnder[UNDER_MOVE0_e].setRatio(1.0f - f27);
    mAnmRatioUnder[UNDER_MOVE1_e].setRatio(f27);
    mAnmRatioUpper[UPPER_MOVE0_e].setRatio(1.0f - f27);
    mAnmRatioUpper[UPPER_MOVE1_e].setRatio(f27);
    f32 f3 = sp14->getFrameMax();
    f32 f26 = sp0C->getFrameMax();
    f32 f30 = 1.0f / f3;
    f27 = (f28 + (f27 * (((f25 * f3) / f26) - f28)));
    setFrameCtrl(&frameCtrl0, sp14->getAttribute(), 0, f3, f27, (f31 * f3));
    sp14->setFrame(frameCtrl0.getFrame());
    setFrameCtrl(&frameCtrl1, sp0C->getAttribute(), 0, f26, (f30 * (f27 * f26)),
                 (f31 * f26));
    sp0C->setFrame(frameCtrl1.getFrame());
    mAnmRatioUnder[UNDER_MOVE0_e].setAnmTransform(sp14);
    mAnmRatioUnder[UNDER_MOVE1_e].setAnmTransform(sp0C);
    if (sp10 != NULL) {
        f32 f2 = sp10->getFrameMax();
        mAnmRatioUpper[UPPER_MOVE0_e].setAnmTransform(sp10);
        setFrameCtrl(&mFrameCtrlUpper[UPPER_MOVE0_e], sp10->getAttribute(), 0, f2,
                     (f30 * (f27 * f2)), (f31 * f2));
        sp10->setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getFrame());
    } else {
        mAnmRatioUpper[UPPER_MOVE0_e].setAnmTransform(sp14);
    }
    if (sp08 != NULL) {
        f32 f2 = sp08->getFrameMax();
        mAnmRatioUpper[UPPER_MOVE1_e].setAnmTransform(sp08);
        setFrameCtrl(&mFrameCtrlUpper[UPPER_MOVE1_e], sp08->getAttribute(), 0, f2,
                     (f30 * (f27 * f2)), (f31 * f2));
        sp08->setFrame(mFrameCtrlUpper[UPPER_MOVE1_e].getFrame());
    } else {
        mAnmRatioUpper[UPPER_MOVE1_e].setAnmTransform(sp0C);
    }
    if (i_morf >= 0.0f) {
        m_old_fdata->initOldFrameMorf(i_morf, 0, 0x2A);
    }
    if (mDirection == DIR_BACKWARD ||
        (mCurProc == daPyProc_ROPE_SWING_e && !checkModeFlg(ModeFlg_00000400)))
    {
        setTextureAnime(mAnmDataTable[r28].mTexAnmIdx, 0);
    } else {
        setTextureAnime(mAnmDataTable[r27].mTexAnmIdx, 0);
    }
    if (r29 == 5 || r29 == 2) {
        setSeAnime(&m_anm_heap_under[UNDER_MOVE0_e], &frameCtrl0);
    } else {
        setSeAnime(&m_anm_heap_under[UNDER_MOVE1_e], &frameCtrl1);
    }
    m34C3 = r29;
    return true;
}

/* 8012821C-80128494       .text setSingleMoveAnime__9daPy_lk_cFQ29daPy_lk_c8daPy_ANMffsf */
BOOL daPy_lk_c::setSingleMoveAnime(daPy_ANM anm, f32 rate, f32 start, s16 end, f32 i_morf) {
    const daPy_anmIndex_c* anmData = getAnmData(anm);
    J3DAnmTransform* under_bck;
    J3DAnmTransform* upper_bck;
    getUnderUpperAnime(anmData, &under_bck, &upper_bck, 0, 0xB400);
    m_anm_heap_under[UNDER_MOVE1_e].mIdx = -1;
    m_anm_heap_upper[UPPER_MOVE1_e].mIdx = -1;
    mAnmRatioUpper[UPPER_MOVE0_e].setRatio(1.0f);
    mAnmRatioUpper[UPPER_MOVE1_e].setRatio(0.0f);
    mAnmRatioUnder[UNDER_MOVE0_e].setRatio(1.0f);
    mAnmRatioUnder[UNDER_MOVE1_e].setRatio(0.0f);
    mAnmRatioUnder[UNDER_MOVE0_e].setAnmTransform(under_bck);
    mAnmRatioUnder[UNDER_MOVE1_e].setAnmTransform(NULL);
    
    s16 endUnder;
    if (end < 0) {
        endUnder = under_bck->getFrameMax();
    } else {
        endUnder = end;
    }
    f32 frame = rate < 0.0f ? endUnder-0.001f : start;
    setFrameCtrl(&mFrameCtrlUnder[UNDER_MOVE0_e], under_bck->getAttribute(), start, endUnder, rate, frame);
    under_bck->setFrame(frame);
    
    if (upper_bck) {
        mAnmRatioUpper[UPPER_MOVE0_e].setAnmTransform(upper_bck);
        s16 endUpper;
        if (end < 0) {
            endUpper = upper_bck->getFrameMax();
        } else {
            endUpper = end;
        }
        frame = rate < 0.0f ? endUpper-0.001f : start;
        // Note: It uses under_bck->getAttribute() again here instead of using upper_bck->getAttribute().
        setFrameCtrl(&mFrameCtrlUpper[UPPER_MOVE0_e], under_bck->getAttribute(), start, endUpper, rate, frame);
        upper_bck->setFrame(frame);
    } else {
        mAnmRatioUpper[UPPER_MOVE0_e].setAnmTransform(under_bck);
    }
    mAnmRatioUpper[UPPER_MOVE1_e].setAnmTransform(NULL);
    
    if (i_morf >= 0.0f) {
        m_old_fdata->initOldFrameMorf(i_morf, 0, 0x2A);
    }
    
    setTextureAnime(mAnmDataTable[anm].mTexAnmIdx, 0);
    setHandModel(anm);
    setSeAnime(&m_anm_heap_under[UNDER_MOVE0_e], &mFrameCtrlUnder[UNDER_MOVE0_e]);
    m34C3 = 0;
    
    return TRUE;
}

/* 801286C0-801287E8       .text animeUpdate__9daPy_lk_cFv */
void daPy_lk_c::animeUpdate() {
    J3DAnmTransform* underPack0 = getNowAnmPackUnder(UNDER_MOVE0_e);
    J3DAnmTransform* underPack1 = getNowAnmPackUnder(UNDER_MOVE1_e);
    J3DAnmTransform* upperPack0 = getNowAnmPackUpper(UPPER_MOVE0_e);
    J3DAnmTransform* upperPack1 = getNowAnmPackUpper(UPPER_MOVE1_e);
    mFrameCtrlUnder[UNDER_MOVE0_e].update();
    underPack0->setFrame(mFrameCtrlUnder[UNDER_MOVE0_e].getFrame());
    if (underPack1) {
        mFrameCtrlUnder[UNDER_MOVE1_e].update();
        underPack1->setFrame(mFrameCtrlUnder[UNDER_MOVE1_e].getFrame());
    }
    if (upperPack0 && upperPack0 != underPack0) {
        mFrameCtrlUpper[UPPER_MOVE0_e].update();
        upperPack0->setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getFrame());
    }
    if (upperPack1 && upperPack1 != underPack1) {
        mFrameCtrlUpper[UPPER_MOVE1_e].update();
        upperPack1->setFrame(mFrameCtrlUpper[UPPER_MOVE1_e].getFrame());
    }
    
    // Bug? This loop starts past the end of the array and immediately stops, without running a single iteration.
    // Maybe the array used to be more than 2 elements long but was shrank later.
    for (int i = 2; i < 2; i++) {
        J3DAnmTransform* underPack2 = getNowAnmPackUnder((daPy_UNDER)i);
        if (underPack2) {
            mFrameCtrlUnder[i].update();
            underPack2->setFrame(mFrameCtrlUnder[i].getFrame());
        }
    }
    
    J3DAnmTransform* upperPack2 = getNowAnmPackUpper(UPPER_MOVE2_e);
    if (upperPack2) {
        mFrameCtrlUpper[UPPER_MOVE2_e].update();
        upperPack2->setFrame(mFrameCtrlUpper[UPPER_MOVE2_e].getFrame());
    }
    
    if (mpParachuteFanMorf) {
        mpParachuteFanMorf->play(NULL, 0, 0);
    }
}

const daPy_anmIndex_c* daPy_lk_c::getAnmData(daPy_ANM anm) const {
    if (mEquipItem == daPyItem_SWORD_e) {
        if (anm < (s32)ARRAY_SIZE(mSwordAnmIndexTable)) {
            return &mSwordAnmIndexTable[anm];
        }
    } else if (mEquipItem == daPyItem_BOKO_e) {
        if (anm < (s32)ARRAY_SIZE(mBokoAnmIndexTable)) {
            return &mBokoAnmIndexTable[anm];
        }
    } else if (mEquipItem == dItemNo_SKULL_HAMMER_e) {
        if (anm < (s32)ARRAY_SIZE(mHammerAnmIndexTable)) {
            return &mHammerAnmIndexTable[anm];
        }
    } else if (mEquipItem == dItemNo_BOOMERANG_e || mEquipItem == dItemNo_DEKU_LEAF_e || mEquipItem == dItemNo_TELESCOPE_e) {
        if (anm == ANM_DASH) {
            return &mSwordAnmIndexTable[anm];
        }
    }
    return &mAnmDataTable[anm].mAnmIdx;
}
