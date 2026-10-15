// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_camera.cpp - dCamera_c's Run, engine_tbl, updatePad, mode sequencer, followCamera,
// manualCamera, subjectCamera and the queries they make (d_camera.cpp:35-43, 45-47, 49-51,
// 53-59, 65-72, 110-117, 120-141, 674-912, 2611-2614, 2616-3293, 1552-1574, 1577-1579,
// 1582-1584, 1587-1589, 3296-3298, 3301-3307, 1768-1789, 1792-1832, 1847-1850, 1860-1865,
// 1591-1602, 1645-1649, 1618-1642, 4398-4747, 3856-4205, 3719-3854, 1004-1205, 1208-1259,
// 445-545, 2426-2609, 2064-2362, 2366-2401, 1417-1468).
// `mAngleY = mDirection.U().Inv()` (:852) sets the camera yaw; U() is the yaw (see
// c_angle.h).

#include "d/d_camera.h"

#include "d/actor/d_a_player_main.h"
#include "d/d_bg_s.h"
#include "d/d_bg_s_gnd_chk.h"
#include "d/d_bg_s_roof_chk.h"
#include "m_Do/m_Do_controller_pad.h"
#include "SSystem/SComponent/c_math.h"
#include "boundary/game_boundary.h"
#include "global.h"

namespace {  
    static f32 limitf(f32 value, f32 min, f32 max) {
        if (value > max) {
            return max;
        } else if (value < min) {
            return min;
        }
        return value;
    }

    inline static bool is_player(fopAc_ac_c* actor) {
        return fopAcM_GetName(actor) == fpcNm_PLAYER_e;
    }

    inline static bool isPlayerGuarding(u32 param_0) {
        return dComIfGp_checkPlayerStatus1(param_0, daPyStts1_UNK80000_e) || daNpc_Md_c::isMirror();
    }

    inline static bool isSubPlayerFlying() {
        return daNpc_Cb1_c::isFlying() || daNpc_Md_c::isFlying();
    }

    inline static bool isPlayerFlying(u32 param_0) {
        return dComIfGp_checkPlayerStatus1(param_0, daPyStts1_DEKU_LEAF_FLY_e) || isSubPlayerFlying();
    }

    inline static fopAc_ac_c* get_boomerang_actor(fopAc_ac_c* actor) {
        if (is_player(actor)) {
            daPy_py_c* link = (daPy_py_c*)actor;
            return fopAcM_SearchByID(link->getThrowBoomerangID());
        } else {
            return NULL;
        }
    }

    inline static u32 check_owner_action(u32 param_0, u32 param_1) {
        return dComIfGp_checkPlayerStatus0(param_0, param_1);
    }
    
    inline static u32 check_owner_action1(u32 param_0, u32 param_1) {
        return dComIfGp_checkPlayerStatus1(param_0, param_1);
    }
}  // namespace

engine_fn dCamera_c::engine_tbl[] = {
    &dCamera_c::letCamera,
    &dCamera_c::followCamera,
    &dCamera_c::lockonCamera,
    &dCamera_c::talktoCamera,
    &dCamera_c::subjectCamera,
    &dCamera_c::fixedPositionCamera,
    &dCamera_c::fixedFrameCamera,
    &dCamera_c::towerCamera,
    &dCamera_c::rideCamera,
    &dCamera_c::hungCamera,
    &dCamera_c::manualCamera,
    &dCamera_c::eventCamera,
    &dCamera_c::crawlCamera,
    &dCamera_c::hookshotCamera,
    &dCamera_c::tornadoCamera,
    &dCamera_c::vomitCamera,
    &dCamera_c::shieldCamera,
    &dCamera_c::nonOwnerCamera,
    &dCamera_c::followCamera2,
    &dCamera_c::demoCamera,
};

/* 80163514-80163EF4       .text Run__9dCamera_cFv */
bool dCamera_c::Run() {
    /* Nonmatching */
    f32 fVar1;
    f32 fVar2;
    f32 fVar3;
    long next;
    dCamera_c* camera;

    bool res = FALSE;
    
    camera = NULL;

    mForcusLine.Off();

    clrFlag(0x10149C01);

    checkSpecialArea();

    checkGroundInfo();

    if (m530 && !chkFlag(0x200000)) {
        if (!(dComIfGp_evmng_cameraPlay() || chkFlag(0x20000000))) {
            fVar1 = daObjPirateship::getShipOffsetY(&m534, &m536, 130.0f);
            fVar2 = fVar1 * m540;
            fVar3 = fVar2 - m538;
            if (((m530 == 1) && (m53C < 0.0f)) && (fVar3 > 0.0f)) {
                m254 |= 4;
            }
            m53C = fVar3;
            m538 = fVar2;
            mViewCache.mCenter.y -= m53C * mCamSetup.mManualStartCThreshold;
        }
    }

    updateMonitor();

    Att();

    clrComStat(dCamAttnStts_00000400_e | dCamAttnStts_00001000_e | dCamAttnStts_00002000_e);

    if (!dComIfGp_evmng_cameraPlay() && !chkFlag(0x20000000)) {
        updatePad();
        mCamSetup.mCstick.Shift(mPadId);
    }
    
    if (dComIfGp_getMiniGameType() == 8) {
        updatePad();
        mCamSetup.mCstick.Shift(mPadId);
    }
    
    if (dComIfGp_getAttention().Lockon()) {
        setFlag(0x1000);
    }
    
    if (!checkForceLockTarget()) {
        mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    }
    else {
        mForceLockTimer++;
    }
    
    mNextType = nextType(mCurType);

    if (mNextType != mCurType && onTypeChange(mCurType, mNextType)) {
        mCurType = mNextType;
    }

    mNextMode = nextMode(mCurMode);
    next = mNextMode;

    if (next != mCurMode) {
        if (types[mCurType].mStyles[next] >= 0 && onModeChange(mCurMode, next)) {
            mCurMode = mNextMode;
        }
    }

    if (types[mCurType].mStyles[mCurMode] < 0) {
        mCurMode = 0;
    }

    const s16 curStyle = types[mCurType].mStyles[mCurMode];
    if (curStyle >= 0) {
        if (mCurStyle != curStyle && onStyleChange(mCurStyle, curStyle)) {
            mCurStyle = types[mCurType].mStyles[mCurMode];
            mCamParam.Change(mCurStyle);
        }
    }
    
    clrFlag(0x20);

    if (mCurMode == 0xc) {
        setFlag(0x20);
    }

    clrFlag(0x80000000);
    
    clrComStat(dCamAttnStts_00000080_e);

    if (mCamParam.CheckFlag(dCamPrmFlg_UNK004) && !check_owner_action(mPadId, daPyStts0_UNK4000000_e) && !check_owner_action1(mPadId, daPyStts1_UNK40000_e)) {
        m148 += (forwardCheckAngle() - m148) * mCamSetup.mBGChk.FwdCushion();
    }
    else {
        m148 = cSAngle::_0;
    }

    defaultTriming();

    mTrimTypeForce = -1;
    m068 = 9;
    
    if (chkFlag(0x200000) && mCamParam.Algorythmn(mCurStyle) != dCamAlg_EVENT_CAMERA_e) {
        if (push_any_key(mPadId) || mMonitor.field_0x0C.x > 10.0f || !m360 || m31C) {
            clrFlag(0x200000);
        }
    }
    else if (dComIfGp_demo_getCamera() && mCamParam.Algorythmn() != dCamAlg_EVENT_CAMERA_e) {
        res = demoCamera(0);
    }
    else {
        // Issues here
        res = (this->*engine_tbl[mCamParam.Algorythmn(mCurStyle)])(mCurStyle);
        m07C++;
        m080++;
        m118++;
        m108++;
        m11C++;
    }

    if (!res) {
        m514 = 0;
    }

    if (!chkFlag(0x400)) {
        mViewCache.mBank -= mViewCache.mBank * 0.05f;
    }

    shakeCamera();

    clrFlag(0x90080);

    if (mCamParam.CheckFlag(dCamPrmFlg_UNK001)) {
        m068 = 0x3F;
    }
    else if (mCamParam.CheckFlag(dCamPrmFlg_UNK002)) {
        m068 = 0xF;
    }

    if (mCamParam.CheckFlag(dCamPrmFlg_UNK400)) {
        m068 |= 0x40;
    }

    fVar1 = m354 + mCamSetup.mBGChk.FloorMargin();

    if (mViewCache.mCenter.y < fVar1) {
        mCenter.x = mViewCache.mCenter.x;
        mCenter.z = mViewCache.mCenter.z;
        
        if ((mCamParam.Algorythmn(mCurStyle) == dCamAlg_SUBJECT_CAMERA_e) && chkFlag(0x10000800)) {
            m068 &= ~8;
            mCenter.y = mViewCache.mCenter.y;
        }
        else {
            mCenter.y = fVar1;
        }
    }
    else {
        mCenter = mViewCache.mCenter;
    }
    
    mFovy = mViewCache.mFovy;

    mBank = mViewCache.mBank;

    bumpCheck(m068);

    cSAngle angle(cSAngle(CPad_GET_STICK_ANGLE(mPadId)) - mDMCSystem.field_0x4);

    if (mStickMainValueLast < mCamSetup.DMCValue() || angle > cSAngle(mCamSetup.DMCAngle()) || angle < cSAngle(-mCamSetup.DMCAngle())) {
        mDMCSystem.field_0x0 = 0;
    }

    if (mDMCSystem.field_0x0) {
        mAngleY = getDMCAngle(CPad_GET_STICK_ANGLE(mPadId));
    }
    else {
        mAngleY = mDirection.U().Inv();
    }

    if (mCenter.x == mEye.x && mCenter.z == mEye.z) {
        mUp.set(0.01f, 1.0f, 0.0f);
    }
    else if (mDirection.V() > cSAngle(-90.0f) && mDirection.V() < cSAngle(90.0f)) {
        mUp.set(0.0f, 1.0f, 0.0f);
    }
    else {
        mUp.set(0.0f, -1.0f, 0.0f);
    }

    for (u32 i = 0; i < 3; i++) {
        bool playSound = FALSE;
        if ((m254 & (1 << i)) != 0 && (m258 & (1 << i)) == 0) {
            playSound = TRUE;
        }
        if (playSound) {
            mDoAud_seStart(m248[i]);
        }
    }

    m258 = m254;
    bool r3 = FALSE;
    m254 = FALSE;    
    
    if (m100 && m101 && m102) { // Also Inline?
        r3 = TRUE;
    }

    if (r3) {
        setComStat(dCamAttnStts_00000010_e);
    }
    else {
        clrComStat(dCamAttnStts_00000010_e);
    }

    if (chkFlag(0x40000)) {
        setComStat(dCamAttnStts_SUBJECT_e);
    }
    else if (mDirection.R() < mCamSetup.m048) {
        if (chkFlag(0x800)) {
            setComStat(dCamAttnStts_SUBJECT_e);
        }
        
        if (chkFlag(0x10000000)) {
            setComStat(dCamAttnStts_00000020_e);
        }
    }

    return res;
}

/* 8016A0F0-8016A110       .text followCamera2__9dCamera_cFl */
bool dCamera_c::followCamera2(s32 param_0) {
    return followCamera(param_0);
}

/* 8016A110-8016C4F8       .text followCamera__9dCamera_cFl */
bool dCamera_c::followCamera(s32 param_1) {
    /* Nonmatching */
    bool bVar2;
    bool bVar3;
    bool bVar4;
    f32 fVar37;
    
    f32 fVar40 = 0.9f;

    cSAngle acStack_490 = cSAngle(mCamSetup.m0A4);

    int iVar17 = mCamSetup.m0A8;
    f32 fVar38 = mCamSetup.mChargeLatitude;

    cSAngle local_494(80.0f);

    f32 dVar19 = mCamParam.Val(param_1, 1);
    f32 dVar20 = mCamParam.Val(param_1, 5);
    f32 dVar21 = mCamParam.Val(param_1, 0);
    f32 dVar22 = mCamParam.Val(param_1, 4);
    f32 dVar23 = mCamParam.Val(param_1, 3);
    f32 dVar24 = mCamParam.Val(param_1, 10);
    f32 dVar25 = mCamParam.Val(param_1, 0xb);
    f32 dVar26 = mCamParam.Val(param_1, 0xd);
    f32 dVar27 = mCamParam.Val(param_1, 0xe);
    f32 dVar28 = mCamParam.Val(param_1, 0xf);

    cSAngle local_498(mCamParam.Val(param_1, 0x10));
    cSAngle local_49c(mCamParam.Val(param_1, 0x11));

    f32 dVar29 = mCamParam.Val(param_1, 0x13);
    f32 dVar30 = mCamParam.Val(param_1, 0x12);
    f32 dVar31 = mCamParam.Val(param_1, 0x19);
    f32 dVar32 = mCamParam.Val(param_1, 0x1d);
    f32 dVar33 = mCamParam.Val(param_1, 0x17);
    f32 dVar34 = mCamParam.Val(param_1, 0x18);
    f32 dVar35 = mCamParam.Val(param_1, 0x14);
    
    f32 f14 = 3.8f;
    dAttention_c& attention = dComIfGp_getAttention();

    bVar2 = false;

#if VERSION > VERSION_DEMO
    if (m108 == 0) {
        mWork.follow.m3AC = 0;
        mWork.follow.m3B0 = 0.0f;
        mWork.follow.m3D9 = 0;
    }
#endif

    if (isSubPlayerFlying()) {
        fVar40 = 0.66f;

        static f32 SA_FLY = 35.0f;

        if (dVar28 < SA_FLY) {
            dVar28 = SA_FLY;
        }

        m148 *= 0.33f;

        if (dVar24 < 420.0f) {
            dVar24 = 420.0f;
        }

        if (dVar25 < 350.0f) {
            dVar25 = 350.0f;
        }

        local_49c.Val(80.0f);

        if (daNpc_Cb1_c::isFlying() && m788) {
            if (m787) {
                if (local_498 < cSAngle(30.0f)) {
                    local_498.Val(30.0f);
                }

                if (dVar28 < 50.0f) {
                    dVar28 = 50.0f;
                }

                dVar24 = 800.0f;
                dVar25 = 600.0f;
            }
            else {
                if (local_498 < cSAngle(10.0f)) {
                    local_498.Val(10.0f);
                }
            }
        }
    }

    if (check_owner_action(mPadId, daPyStts0_CRAWL_e | daPyStts0_SWIM_e)) {        
        if (local_498 < cSAngle(4.0f)) {
            local_498.Val(4.0f);
        }

        if (dVar20 < -10.0f) {
            dVar20 = -10.0f;
        }
    }

#if VERSION > VERSION_DEMO
    if (check_owner_action(mPadId, daPyStts0_UNK200_e | daPyStts0_HANG_e) && !check_owner_action(mPadId, daPyStts0_UNK2000000_e)) {
        if (dVar21 > -10.0f) {
            mWork.follow.m3B0 = -10.0f;
        }
    }
    else {
        mWork.follow.m3B0 += ((dVar21 - mWork.follow.m3B0) * 0.06f);
    }
#endif

    if (check_owner_action1(mPadId, daPyStts1_UNK40000_e)) {
        m148 = cSAngle::_0;
        dVar28 = -24.0f;
        dVar24 = dVar25 = 420.0f;
        dVar31 = 80.0f;
        dVar20 = 140.0f;
        bVar2 = true;
    }

    cSAngle acStack_4a0 = cSAngle::_0;

    if (check_owner_action(mPadId, daPyStts0_UNK40_e | daPyStts0_UNK20_e)) {
        acStack_4a0 = calcPeepAngle();
        if (check_owner_action(mPadId, daPyStts0_UNK20_e)) {
            dVar19 = -dVar19;
        }
    }
    
    if (mCamParam.Flag(param_1, dCamPrmFlg_UNK200)) {
        bVar2 = true;
    }

    if (!chkFlag(daPyStts0_SWIM_e) || !check_owner_action(mPadId, daPyStts0_BOOMERANG_AIM_e | daPyStts0_ROPE_AIM_e | daPyStts0_HOOKSHOT_AIM_e | daPyStts0_BOW_AIM_e)) {
        if (isSubPlayerFlying()) {
            if (mStickMainPosXLast < -0.2f) {
                mWork.follow.m3D9 = 1;
            }
    
            if (mStickMainPosXLast > 0.2f) {
                mWork.follow.m3D9 = 0;
            }
            
            f32 temp_004 = 0.04f;

            if (mWork.follow.m3D9) {
                fVar37 = -45.0f;
            }
            else {
                fVar37 = 45.0f;
            }

            mWork.follow.m3AC += (fVar37 - mWork.follow.m3AC) * temp_004;
        }
        else {
            mWork.follow.m3AC += (dVar19 - mWork.follow.m3AC) * 0.06f;
            
        }
    }
    

    cXyz local_314(mWork.follow.m3AC, dVar20, mWork.follow.m3B0);
    cXyz local_158;
    if (m108 == 0) {
        mViewCache.mDirection.Val(mViewCache.mEye - mViewCache.mCenter);
        mWork.follow.m378 = 'FLLW';
        mWork.follow.m394 = fVar40;
        mWork.follow.m388 = 0x50;
        mWork.follow.m398 = dVar25;
        mWork.follow.m39C = dVar24;
        mWork.follow.m38C = mWork.follow.m392 = mWork.follow.m390 = 0;
        mWork.follow.m3A0 = mWork.follow.m3BC = mDirection.V().Degree();
        mWork.follow.m3C0 = mViewCache.mCenter;
        mWork.follow.m3CC = mViewCache.mEye;
        mWork.follow.m3E8 = mWork.follow.m3E0 = mWork.follow.m3E4 = 0.01f;
        mWork.follow.m3DC = 0.75f;
        mWork.follow.m3EC = dVar23;
        mWork.follow.m3F0 = dVar22;
        mWork.follow.m3B4 = 0;
        mWork.follow.m3D8 = 1;
        mWork.follow.m3A8 = mViewCache.mFovy;
        mWork.follow.m3B8 = 0.0f;
        mWork.follow.m3DA = 0;

        mWork.follow.m3A4 = positionOf(mpPlayerActor).y;

        if (chkFlag(0x8000) || !m110) {
            m102 = 1;
            m101 = 1;
            m100 = 1;
            mWork.follow.m37C = 1;
        }
        else {
            cXyz cStack_248 = relationalPos(mpPlayerActor, &local_314);
            cSAngle acStack_4a4; 
            if (chkFlag(0x100000)) {
                acStack_4a4.Val(directionOf(mpPlayerActor).Inv());
            }
            else {
                acStack_4a4.Val(mViewCache.mDirection.V());
            }
            
            cSGlobe cStack_46c(dVar24, cSAngle(dVar28), acStack_4a4);
            cXyz cStack_2fc = cStack_248 + cStack_46c.Xyz();
            cXyz cStack_2e0 = mEye - cStack_2fc;
            dVar20 = cStack_2e0.abs();
            cXyz cStack_314 = mCenter - cStack_248;
            dVar19 = cStack_314.abs() * 4.0f;

            if (dVar20 < dVar19) {
                dVar20 = dVar19;
            }

            fVar37 = std::fabs(dVar20);
            f32 playerHeight = heightOf(mpPlayerActor);

            if (playerHeight < 10.0f) {
                playerHeight = 10.0f;
            }

            mWork.follow.m37C = (s32)(ppc::sqrtf_msl(fVar37 / playerHeight) * f14) + 1;
        }

        mWork.follow.m398 = mWork.follow.m39C = mDirection.R();
        mWork.follow.m3A8 = mFovy;
        mWork.follow.m380 = mWork.follow.m37C * (mWork.follow.m37C + 1) >> 1;
        mWork.follow.m384 = 0.0f;
    }

    cXyz cStack_260 = relationalPos(mpPlayerActor, &local_314);
    cSAngle acStack_4a8 = directionOf(mpPlayerActor);
    cSAngle local_4ac = acStack_4a8 - mViewCache.mDirection.V();
    cStack_260.y = getWaterSurfaceHeight(&cStack_260);
    cM3dGPla* plane;
    cXyz cross;
    if (m100 == 0) {
        if (m31D != 0) {
            dComIfG_Bgsp()->MoveBgMatrixCrrPos(mBG.m5C.m04, true, &mWork.follow.m3C0, NULL, NULL);
        }
        
        mWork.follow.m384 = mWork.follow.m37C - (int)m108;

        f32 temp = (mWork.follow.m384 / mWork.follow.m380);
        mWork.follow.m3C0 += (cStack_260 - mWork.follow.m3C0) * temp;

        mViewCache.mCenter += (mWork.follow.m3C0 - mViewCache.mCenter) * dVar23;

        f32 xyzDist = dCamMath::xyzHorizontalDistance(cStack_260, mWork.follow.m3C0);

        if (local_314.x > local_314.z) {
            local_314.z = local_314.x;
        }

        if (xyzDist < std::fabs(local_314.z) + 20.0f) {
            cXyz cStack_26c = attentionPos(mpPlayerActor);
            cStack_26c.y -= 15.0f;
            dBgS_CamLinChk_NorWtr lin_chk;
            if (lineBGCheck(&cStack_26c, &mViewCache.mCenter, &lin_chk, 0x7f)) {
                plane = dComIfG_Bgsp()->GetTriPla(lin_chk);
                mViewCache.mCenter = lin_chk.GetCross();
                mViewCache.mCenter += plane->mNormal;
            }
        }

        dVar29 = limitf(mViewCache.mDirection.R(), dVar25, dVar24);

        cSAngle local_4b0 = mViewCache.mDirection.V();

        if (local_4b0 < local_498) {
            local_4b0 = local_498;
        }

        if (local_4b0 > local_49c) {
            local_4b0 = local_49c;
        }
        
        cSGlobe local_474(dVar29, local_4b0, cSAngle(mAngleY.Inv()));
        mViewCache.mDirection.R(mViewCache.mDirection.R() + temp * (local_474.R() - mViewCache.mDirection.R()));
        mViewCache.mDirection.V(mViewCache.mDirection.V() + ((local_474.V() - mViewCache.mDirection.V()) * temp));

        if (chkFlag(0x100000)) {
            mViewCache.mDirection.U(mViewCache.mDirection.U() + ((acStack_4a8.Inv() - mViewCache.mDirection.U()) * temp));
        }

        mWork.follow.m3CC = mViewCache.mEye = mViewCache.mCenter + mViewCache.mDirection.Xyz();

        if (m108 >= mWork.follow.m37C - 1) {
            m102 = 1;
            m101 = 1;
            m100 = 1;
        }

        mWork.follow.m3A0 = mViewCache.mDirection.V().Degree();
        mWork.follow.m398 = mWork.follow.m39C = mViewCache.mDirection.R();
        mViewCache.mFovy += (temp * (dVar31 - mViewCache.mFovy));
        mWork.follow.m380 -= mWork.follow.m384;
        return true;
    }

    cXyz player_pos = positionOf(mpPlayerActor);
    player_pos.y += 10.0f;
    fVar37 = mpPlayerActor->current.pos.y;
    fVar37 -= groundHeight(&player_pos);

    if (m360 && (check_owner_action(mPadId, daPyStts0_SWIM_e) || daNpc_kam_c::m_hyoi_kamome == 0 || check_owner_action(mPadId, daPyStts0_UNK200_e))) {
        mWork.follow.m394 = 0.0f;
        mWork.follow.m388 = 0;
    }
    else if (mWork.follow.m388 < 0x50) {
        mWork.follow.m388++;
        mWork.follow.m394 += (fVar40 - mWork.follow.m394) * dCamMath::rationalBezierRatio(mWork.follow.m388 / 80.0f, 1.25f);
    }

    if (check_owner_action(mPadId, daPyStts0_UNK4000000_e | daPyStts0_UNK2000000_e | daPyStts0_UNK800000_e | daPyStts0_UNK40_e | daPyStts0_UNK20_e | daPyStts0_UNK1_e) || (check_owner_action1(mPadId, daPyStts1_UNK10000_e) && mDMCSystem.field_0x0 == 0)) {
        setDMCAngle();
    }

    if (!((check_owner_action(mPadId, daPyStts0_UNK2000000_e | daPyStts0_HANG_e | daPyStts0_UNK40_e | daPyStts0_UNK20_e | daPyStts0_UNK1_e) || check_owner_action1(mPadId, daPyStts1_UNK10000_e)) && !(cSAngle::_270 < local_4ac && local_4ac < cSAngle::_90))) {
        mWork.follow.m3EC = dVar23;
    }
    else {
        mWork.follow.m3EC = 0.1f;
    }

    if (mWork.follow.m388 == 0) {
        mWork.follow.m3F0 = dVar22;
    }
    else {
        mWork.follow.m3F0 = dVar22 * 0.1f + (1.0f - (dVar22 * 0.1f)) * mWork.follow.m394;
        if (
            (chkFlag(0x100000) && mWork.follow.m3EC > 0.25f) ||
            isSubPlayerFlying() ||
            check_owner_action1(mPadId, daPyStts1_UNK40000_e)
        ) {
            mWork.follow.m3EC = mWork.follow.m394 * 0.75f + 0.25f;
        }
    }

    LAB_8016b24c:
    cXyz cStack_284(mWork.follow.m3EC, mWork.follow.m3F0, mWork.follow.m3EC);
    bVar4 = true;
    bVar3 = false;

    if (chkFlag(0x80) && (mDirection.R() < dVar25)) {
        bVar3 = true;
    }

    if (chkFlag(0x100000) || check_owner_action(mPadId, daPyStts0_UNK4000000_e | daPyStts0_UNK2000000_e | daPyStts0_UNK800000_e | daPyStts0_TELESCOPE_LOOK_e | daPyStts0_UNK40_e | daPyStts0_UNK20_e | daPyStts0_UNK1_e) || check_owner_action1(mPadId, daPyStts1_UNK10000_e | daPyStts1_DEKU_LEAF_FAN_e) || mWork.follow.m388) {
        bVar4 = false;
    }

    if (mCurMode == 1) {
        if (cStack_260.y < attentionPos(mpPlayerActor).y + 50.0f) {
            cSGlobe cStack_47c(dVar25, 0, directionOf(mpPlayerActor).Inv());
            cXyz cStack_290 = attentionPos(mpPlayerActor);
            cXyz cStack_29c = cStack_290 + cStack_47c.Xyz();
            if (lineBGCheck(&cStack_290, &cStack_29c, 0x7f)) {
                cStack_260.y = cStack_290.y + 50.0f;
            }
        }
    }

    cXyz cStack_3c8 = cStack_260 - mViewCache.mCenter;
    mViewCache.mCenter += cStack_3c8 * cStack_284;
    
    if (m780) {
        cXyz attn_pos = attentionPos(mpPlayerActor);
        if (check_owner_action(mPadId, daPyStts0_CRAWL_e | daPyStts0_SWIM_e | daPyStts0_HANG_e)) {
            attn_pos.y = eyePos(mpPlayerActor).y + 30.0f;
        }
        else {
            attn_pos.y -= 15.0f;
        }

        dBgS_CamLinChk_NorWtr lin_chk;
        if (lineBGCheck(&attn_pos, &mViewCache.mCenter, &lin_chk, 0x7f)) {
            plane = dComIfG_Bgsp()->GetTriPla(lin_chk);
            mViewCache.mCenter = lin_chk.GetCross();
            mViewCache.mCenter += plane->mNormal;
        }
    }

    cSGlobe local_484(mViewCache.mEye - mViewCache.mCenter);
    
    if (mWork.follow.m392 > 0 && mWork.follow.m392 <= iVar17) {
        dVar20 = dCamMath::rationalBezierRatio((f32)mWork.follow.m392 / (f32)iVar17, fVar38);
        mWork.follow.m3D8 = 1;
        mWork.follow.m3B8 = (1.0f - mWork.follow.m3B8) * dVar20;
    }
    else if (chkFlag(0x100000) || daNpc_Cb1_c::isFlying()) {
        if (mWork.follow.m3D8) {
            mWork.follow.m3B8 = 0.05f;
        }

        mWork.follow.m3D8 = 0;
        mWork.follow.m3B8 += (1.0f - mWork.follow.m3B8) * 0.2f;
    }
    else if (daNpc_Md_c::isFlying() || daNpc_kam_c::m_hyoi_kamome) {
        mWork.follow.m3D8 = 1;
    }
    else if (check_owner_action1(mPadId, check_owner_action1(mPadId, daPyStts1_UNK40000_e | daPyStts1_DEKU_LEAF_FAN_e))) {
        if (mWork.follow.m3D8) {
            mWork.follow.m3B8 = 0.05f;
        }

        mWork.follow.m3D8 = 0;
        mWork.follow.m3B8 += (0.5f - mWork.follow.m3B8) * 0.05f;
    }
    else {
        mWork.follow.m3D8 = 1;

        if (mDMCSystem.field_0x0) {
            mWork.follow.m3B8 = 0.0f;
        }
        else if (mStickMainPosYLast >= 0.0f) {
            mWork.follow.m3B8 = 1.0f - ((cSAngle(dCamMath::rationalBezierRatio(mStickMainPosXLast, dVar33) * 180.0f).Cos() * 0.5f) + 0.5f);
        }
        else {
            mWork.follow.m3B8 = 1.0f - ((cSAngle(dCamMath::rationalBezierRatio(mStickMainPosXLast, dVar34) * 180.0f).Cos() * 0.25f) + 0.75f);
        }

        mWork.follow.m3B8 *= mStickMainValueLast;
        
        if (chkFlag(0x80000)) {
            mWork.follow.m3B8 *= 0.5f;
        }
        else {
            mWork.follow.m3B8 *= 0.1f;
        }

        if (
            check_owner_action(mPadId, daPyStts0_UNK2000000_e | daPyStts0_HANG_e) ||
            check_owner_action1(mPadId, check_owner_action1(mPadId, daPyStts1_UNK10000_e))
        ) {
            if (mWork.follow.m38C == 0) {
                if (local_4ac > cSAngle::_270 && local_4ac < cSAngle::_90) {
                    mWork.follow.m38C = 1;
                }
                else {
                    mWork.follow.m38C = -1;
                }
            }
            else if (mWork.follow.m38C < 0) {
                mWork.follow.m38C--;
                if (mWork.follow.m38C <= -0x20) {
                    mWork.follow.m38C = 0x10;
                }
            }
            else if (mWork.follow.m38C < 0xf) {
                mWork.follow.m3B8 = mWork.follow.m38C * 0.033333335f;
                mWork.follow.m38C++;
            }
            else if (!check_owner_action(mPadId, daPyStts0_UNK2000000_e)) {
                if (mStickMainValueLast < 0.1f) {
                    mWork.follow.m3B8 = 0.05f;
                }
                else {
                    mWork.follow.m3B8 = dCamMath::rationalBezierRatio(std::fabs(local_4ac.Sin()), 12.0f);
                }
            }
        }
        else if (isSubPlayerFlying()) {
            if (mWork.follow.m38C == 0 && (local_4ac <= cSAngle::_270 || local_4ac >= cSAngle::_90)) {
                mWork.follow.m38C = 1;
            }
            else if (mWork.follow.m38C < 0xf) {
                mWork.follow.m3B8 = mWork.follow.m38C * 0.033333335f;
                mWork.follow.m38C++;
            }
            else if (check_owner_action(mPadId, daPyStts0_UNK40_e | daPyStts0_UNK20_e)) {
                mWork.follow.m3B8 = 0.15f;
            }
            else if (mStickMainValueLast < 0.1f) {
                mWork.follow.m3B8 = 0.05f;
            }
            else {
                mWork.follow.m3B8 = dCamMath::rationalBezierRatio(std::fabs(local_4ac.Sin()), 12.0f);
            }
        }
        else {
            mWork.follow.m3B8 *= dVar35;
            mWork.follow.m38C = 0;
        }
    }

    cSAngle acStack_4b4;
    
    if (chkFlag(0x80) && !chkFlag(0x80000) && mCurMode == 0 && mWork.follow.m38C == 0) {
        acStack_4b4 = cSAngle(mDirection.U().Val()); 
    }
    else if (isSubPlayerFlying()) {
        acStack_4b4 = acStack_4a8;
        if (check_owner_action(mPadId, daPyStts0_UNK40_e | daPyStts0_UNK20_e)) {
            acStack_4b4 += acStack_4a0;
        }
    }
    else {
        acStack_4b4 = acStack_4a8.Inv();
    }

    cSAngle acStack_4b8 = cSAngle((s16)0);
    cSAngle acStack_51c = (acStack_4b4 - local_484.U()) * (mWork.follow.m3B8 * local_484.V().Cos());
    mViewCache.mDirection.U(local_484.U() + acStack_51c + acStack_4b8);
    cSAngle local_4bc;
    if (check_owner_action1(mPadId, daPyStts1_UNK20000_e)) {
        if (mWork.follow.m392 <= iVar17) {
            local_4bc = acStack_490;
            mWork.follow.m3E0 = dCamMath::rationalBezierRatio((f32)mWork.follow.m392 / (f32)iVar17, fVar38);
            setFlag(0x4000000);
            mWork.follow.m392++;
        }
        else {
            local_4bc = acStack_490;
            mWork.follow.m3E0 = 1.0f;
        }

        mWork.follow.m3BC = mWork.follow.m3A0 = local_4bc.Degree();
    }
    else {
        if (mWork.follow.m392 != 0) {
            mWork.follow.m3E0 = 0.0f;
        }

        mWork.follow.m392 = 0;

        if (mCurMode == 1) {
            mWork.follow.m3E0 = 0.5f;
            mWork.follow.m3BC = mWork.follow.m3A0 = mWork.follow.m3A0 + (mWork.follow.m3B8 * (dVar28 - mWork.follow.m3A0));
            local_4bc = cAngle::d2s(mWork.follow.m3A0);
            mWork.follow.m3E0 += (fVar40 - mWork.follow.m3E0) * 0.5f;
        }
        else if (mWork.follow.m388 == 0) {
            mWork.follow.m3BC += dVar27 * (dVar28 - mWork.follow.m3BC);
            dVar20 = 0.01f;

            if (mWork.follow.m3B4 != 0) {
                dVar20 = 0.25f;
                dVar29 = dVar20;
            }
            
            mWork.follow.m3A0 += dVar29 * ((mWork.follow.m3BC + m148.Degree()) - mWork.follow.m3A0);
            local_4bc = cAngle::d2s(mWork.follow.m3A0);

            if (chkFlag(0x80000)) {
                mWork.follow.m3E0 = 0.0f;
            }
            else if (mWork.follow.m3B4) {
                mWork.follow.m3E0 += dVar20 * (fVar40 - mWork.follow.m3E0);
            }
            else if (mMonitor.mPos.y < 0.01f && mCurMode == 0) {
                mWork.follow.m3E0 += (0.1f - mWork.follow.m3E0) * 0.05f;
            }
            else {
                mWork.follow.m3E0 += dVar20 * (fVar40 - mWork.follow.m3E0);
            }
        }
        else {
            if (check_owner_action(mPadId, daPyStts0_UNK2000000_e) || check_owner_action1(mPadId, daPyStts1_UNK10000_e)) {
                local_4bc = acStack_51c;
                mWork.follow.m3BC = mWork.follow.m3A0 = local_4bc.Degree();
                mWork.follow.m3E0 = 0.95f;
            }
            else if (isPlayerFlying(mPadId) || daNpc_kam_c::m_hyoi_kamome) {
                local_4bc = acStack_51c;
                if (mWork.follow.m3A4 < positionOf(mpPlayerActor).y) {
                    mWork.follow.m3E0 = dCamMath::rationalBezierRatio(mWork.follow.m394, dVar30);
                }
                else {
                    mWork.follow.m3E0 += (0.75f - mWork.follow.m3E0) * 0.15f;
                }

                mWork.follow.m3BC = mWork.follow.m3A0 = local_4bc.Degree();
            }
            else {
                local_4bc = acStack_51c;
                mWork.follow.m3BC = mWork.follow.m3A0 = local_4bc.Degree();
                mWork.follow.m3E0 = dCamMath::rationalBezierRatio(mWork.follow.m394, dVar30);
            }
        }
    }
    
    mWork.follow.m3A4 = positionOf(mpPlayerActor).y;
    
    if (check_owner_action(mPadId, daPyStts0_UNK2000000_e | daPyStts0_HANG_e | daPyStts0_UNK40_e | daPyStts0_UNK20_e | daPyStts0_UNK1_e || check_owner_action1(mPadId, daPyStts1_UNK10000_e))) {
        mWork.follow.m3B4 = 1;
    }
    else {
        mWork.follow.m3B4 = 0;
    }

    if (local_4bc < local_498) {
        local_4bc.Val(local_498);
    }
    else if (local_4bc > local_49c) {
        local_4bc.Val(local_49c);
    }
#if VERSION == VERSION_DEMO
    if (mMonitor.field_0x0C.x > 0.01f || !push_any_key(mPadId) || REG5_S(1) == 0) {
        mViewCache.mDirection.U(mViewCache.mDirection.U() + ((local_4bc - mViewCache.mDirection.U()) * mWork.follow.m3E0));
    }
#else
    mViewCache.mDirection.V(mViewCache.mDirection.V() + ((local_4bc - mViewCache.mDirection.V()) * mWork.follow.m3E0));
#endif

    if (mViewCache.mDirection.V() > local_494) {
        mViewCache.mDirection.V(local_494);
    }

    mWork.follow.m398 += dVar27 * (dVar25 - mWork.follow.m398);
    mWork.follow.m39C += dVar27 * (dVar24 - mWork.follow.m39C);

    if (local_484.R() < mWork.follow.m398) {
        mWork.follow.m3DC += (dVar26 - mWork.follow.m3DC) * 0.01f;
        local_484.R(mWork.follow.m398);
        
    }
    else if (local_484.R() > mWork.follow.m39C) {
        mWork.follow.m3DC += (dVar26 - mWork.follow.m3DC) * 0.01f;
        local_484.R(mWork.follow.m39C);
    }
    else {
        mWork.follow.m3DC = 1.0f;
    }

    mViewCache.mDirection.R(mViewCache.mDirection.R() + mWork.follow.m3DC * (local_484.R() - mViewCache.mDirection.R()));
    mWork.follow.m3CC = mViewCache.mCenter + mViewCache.mDirection.Xyz();

    if (bVar3 && bVar4 && mCamParam.Flag(param_1, dCamPrmFlg_UNK001)) {
        cSGlobe cStack_48c(mViewCache.mDirection);
        cStack_48c.V(cSAngle(dVar28));
        cXyz cStack_2b4 = mViewCache.mCenter + cStack_48c.Xyz();
        if (lineBGCheck(&mViewCache.mCenter, &cStack_2b4, 0x7f)) {
            setFlag(8);
        }
    }

    mViewCache.mEye += (mWork.follow.m3CC - mViewCache.mEye) * 0.75f;
    mViewCache.mDirection.Val(mViewCache.mEye - mViewCache.mCenter);
    
    if (chkFlag(8)) {
        mWork.follow.m3DA = 1;
    }

    mWork.follow.m3E8 += (dVar32 - mWork.follow.m3E8) * 0.01f;
    mViewCache.mFovy += mWork.follow.m3E8 * (dVar31 - mViewCache.mFovy);

    if (check_owner_action1(mPadId, daPyStts1_DEKU_LEAF_FAN_e)) {
        mViewCache.mFovy += cM_rndFX(mCamSetup.m078);
    }

    if (isPlayerFlying(mPadId) || daNpc_kam_c::m_hyoi_kamome) {
        if (fVar37 < 200.0f) {
            fVar37 = fVar37 / 200.0f;
            fVar40 = mStickMainPosXLast * fVar37;
            fVar38 = 1.0f - fVar37 * 0.96f;
        }
        else {
            fVar40 = mStickMainPosXLast;
            fVar38 = 0.04f;
        }
        
        mViewCache.mFovy += mCamSetup.m07C * cSAngle((s16)(m07C << 7)).Sin();
        mViewCache.mBank += (cSAngle(fVar40 * mCamSetup.FanBank()) - mViewCache.mBank) * fVar38;
        setFlag(0x400);
    }

    return true;
}

static bool limited_range_addition(f32* param_1, f32 param_2, f32 param_3, f32 param_4) {
    f32 fVar1 = param_3;
    f32 fVar2 = param_4;

    if (param_3 > param_4) {
        param_2 = -param_2;
        fVar1 = param_4;
        fVar2 = param_3;
    }

    *param_1 += param_2;

    if (*param_1 < fVar1) {
        *param_1 = fVar1;
        return false;
    }

    if (*param_1 > fVar2) {
        *param_1 = fVar2;
        return false;
    }
    return true;
}

cSAngle dCamera_c::directionOf(fopAc_ac_c* i_this) {
    return cSAngle(i_this->shape_angle.y);
}

cXyz dCamera_c::positionOf(fopAc_ac_c* i_this) {
    return i_this->current.pos;
}

cXyz dCamera_c::attentionPos(fopAc_ac_c* i_this) {
    return i_this->attention_info.position;
}

cXyz dCamera_c::eyePos(fopAc_ac_c* i_actor) {
    return i_actor->eyePos;
}

f32 dCamera_c::heightOf(fopAc_ac_c* i_actor) {
    if (is_player(i_actor)) {
        return ((daPy_py_c*)i_actor)->getHeight();
    } else {
        return (i_actor->eyePos.y - i_actor->current.pos.y) * 1.1f;
    }
}

f32 dCamera_c::groundHeight(cXyz* param_0) {
    dBgS_GndChk gndchk;
    gndchk.SetPos(param_0);
    f32 gnd_y = dComIfG_Bgsp()->GroundCross(&gndchk);

    dBgS_CamGndChk_Wtr gndchk_wtr;
    gndchk_wtr.SetPos(param_0);
    f32 wtr_y = dComIfG_Bgsp()->GroundCross(&gndchk_wtr);

    if (gnd_y >= wtr_y) {
        wtr_y = gnd_y;
    }

    if (wtr_y == -G_CM3D_F_INF) {
        gnd_y = param_0->y;
    }
    else {
        gnd_y = wtr_y;
    }
    
    return gnd_y;
}

bool dCamera_c::lineBGCheck(cXyz* i_start, cXyz* i_end, dBgS_LinChk* i_linChk, u32 i_flags) {
    if (i_flags & 0x80) {
        i_linChk->ClrCam();
        i_linChk->SetObj();
    } else {
        i_linChk->ClrObj();
        i_linChk->SetCam();
    }

    i_linChk->Set(i_start, i_end, NULL);

    if (i_flags & 4) {
        i_linChk->ClrSttsRoofOff();
    } else {
        i_linChk->SetSttsRoofOff();
    }

    if (i_flags & 2) {
        i_linChk->ClrSttsWallOff();
    } else {
        i_linChk->SetSttsWallOff();
    }

    if (i_flags & 1) {
        i_linChk->ClrSttsGroundOff();
    } else {
        i_linChk->SetSttsGroundOff();
    }

    if (i_flags & 8) {
        i_linChk->OnWaterGrp();
    } else {
        i_linChk->OffWaterGrp();
    }

    if (dComIfG_Bgsp()->LineCross(i_linChk)) {
        return true;
    } else {
        return false;
    }
}

bool dCamera_c::lineBGCheck(cXyz* i_start, cXyz* i_end, u32 i_flags) {
    dBgS_CamLinChk_NorWtr lin_chk;
    return lineBGCheck(i_start, i_end, &lin_chk, i_flags);
}

/* 80166CD4-80166D00       .text lineBGCheckBoth__9dCamera_cFP4cXyzP4cXyzP11dBgS_LinChkUl */
bool dCamera_c::lineBGCheckBoth(cXyz* i_start, cXyz* i_end, dBgS_LinChk* i_linChk, u32 i_flags) {
    i_linChk->OnBackFlag();
    i_linChk->OnFrontFlag();
    return lineBGCheck(i_start, i_end, i_linChk, i_flags);
}

/* 801652E8-801653B0       .text relationalPos__9dCamera_cFP10fopAc_ac_cP4cXyz */
cXyz dCamera_c::relationalPos(fopAc_ac_c* i_actor, cXyz* i_offset) {
    if (i_actor == NULL) {
        return cXyz::Zero;
    }

    cSGlobe offset_globe(*i_offset);

    offset_globe.U(directionOf(i_actor) + offset_globe.U());

    return attentionPos(i_actor) + offset_globe.Xyz();
}

void dCamera_c::setDMCAngle() {
    mDMCSystem.field_0x0 = 1;
    mDMCSystem.field_0x2 = mDirection.U().Inv();
    mDMCSystem.field_0x4 = cSAngle(CPad_GET_STICK_ANGLE(mPadId));
}

cXyz dCamera_c::relationalPos(fopAc_ac_c* i_actor1, fopAc_ac_c* i_actor2, cXyz* i_offset, f32 param_3) {
    if (i_actor1 == NULL) {
        return cXyz::Zero;
    }

    if (i_actor2 == NULL) {
        return relationalPos(i_actor1, i_offset);
    }

    cXyz pos1 = attentionPos(i_actor1);
    cXyz pos2 = attentionPos(i_actor2);
    
    cXyz mid = pos1 + (pos2 - pos1) * 0.5f;
    
    cSGlobe delta_globe(pos2 - pos1);
    cSGlobe offset_globe(*i_offset);

    offset_globe.U(directionOf(i_actor1) + offset_globe.U());
    
    cSAngle acStack_104 = mViewCache.mDirection.U() - delta_globe.U();
    delta_globe.R(0.5f * delta_globe.R() * acStack_104.Cos() * param_3);

    cXyz ret = mid + delta_globe.Xyz() + offset_globe.Xyz();
    return ret;
}

bool dCamera_c::manualCamera(s32 param_1) {
    /* Nonmatching */
    f32 offset_x = mCamParam.Val(param_1, 1);
    f32 offset_z = mCamParam.Val(param_1, 0);
    f32 center_cushion_xz = mCamParam.Val(param_1, 3);
    f32 center_cushion_y = mCamParam.Val(param_1, 4);
    f32 cushion = mCamParam.Val(param_1, 0x15);
    f32 cushion_limited = mCamParam.Val(param_1, 0x14);
    f32 height_rate = mCamParam.Val(param_1, 9);
    f32 height_lower = mCamParam.Val(param_1, 6);
    f32 height_upper = mCamParam.Val(param_1, 7);
    f32 radius_rate = mCamParam.Val(param_1, 0xe);
    f32 radius_lower = mCamParam.Val(param_1, 0xb);
    f32 radius_upper = mCamParam.Val(param_1, 0xc);
    f32 latitude_rate = mCamParam.Val(param_1, 0x13);
    f32 latitude_lower = mCamParam.Val(param_1, 0x10);
    f32 latitude_upper = mCamParam.Val(param_1, 0x11);
    f32 longitude_rate = mCamParam.Val(param_1, 0x18);
    f32 fovy_rate = mCamParam.Val(param_1, 0x1d);
    f32 fovy_lower = mCamParam.Val(param_1, 0x1a);
    f32 fovy_upper = mCamParam.Val(param_1, 0x1b);

    if (m11C == 0) {
        m100 = 1;
        m101 = 1;
        m102 = 1;

        if ((mEventFlags & dCamAttnStts_00001000_e) && mpLockonTarget != NULL) {
            mWork.manual.m394 = 1.0f;
        }
        else {
            mWork.manual.m394 = 0.0f;
        }

        cXyz attn_pos = attentionPos(mpPlayerActor);

        mWork.manual.m398 = mViewCache.mCenter.y - attn_pos.y;
        mWork.manual.m3A4 = radius_lower;
        mViewCache.mDirection.Val(mViewCache.mEye - mViewCache.mCenter);

        if (dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_UNK20000_e)) {
            mWork.manual.m3A0 = 1;
        }
        else {
            mWork.manual.m3A0 = 0;
        }

        mWork.manual.m3A8 = mViewCache.mDirection;
        mWork.manual.m37C = cXyz::Zero;
        mWork.manual.m3B8 = 0;
    }

    if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_CRAWL_e)) {
        if (latitude_lower < 4.0f) {
            latitude_lower = 4.0f;
        }

        if (height_lower < -10.0f) {
            height_lower = -10.0f;
        }
    }
    else if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_UNK2000000_e | daPyStts0_UNK800000_e |
                                                 daPyStts0_HANG_e) ||
             dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_UNK10000_e | daPyStts1_DEKU_LEAF_FLY_e) ||
             isSubPlayerFlying()) {
        if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_UNK2000000_e)) {
            latitude_lower = -58.0f;
        }
        else {
            latitude_lower = -70.0f;
        }

        latitude_upper = 70.0f;
        latitude_rate = 4.0f;
        center_cushion_xz = 0.45f;

        if (radius_upper > 500.0f) {
            radius_upper = 500.0f;
        }
    }
    else if (dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_UNK40000_e)) {
        latitude_lower = -10.0f;
        latitude_upper = 10.0f;
    }

    if (!mWork.manual.m3A0 && dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_UNK20000_e)) {
        m144 = 1;
        mEventFlags |= 0x4000000;
    }

    if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_UNK800000_e) && m784) {
        offset_x = 0.0f;
        offset_z = 1.0f;
        center_cushion_xz = 0.75f;
        center_cushion_y = 0.25f;
        cushion = 0.2f;
        cushion_limited = 0.33f;
        height_rate = 0.0f;
        height_lower = 0.0f;
        height_upper = 0.0f;
        radius_rate = 1.0f;
        radius_lower = 300.0f;
        radius_upper = 300.0f;
        longitude_rate = 6.0f;
        latitude_rate = 6.0f;
        latitude_lower = 60.0f;
        latitude_upper = -60.0f;
        fovy_rate = 1.0f;
        fovy_lower = 55.0f;
        fovy_upper = 55.0f;
    }

    f32 stick_x_ratio;
    if (mStickCPosXLast >= 0.75f) {
        stick_x_ratio = 1.0f;
    }
    else if (mStickCPosXLast <= -0.75f) {
        stick_x_ratio = -1.0f;
    }
    else {
        stick_x_ratio = dCamMath::rationalBezierRatio(1.333333f * mStickCPosXLast, 2.0f);
    }

    f32 stick_y_ratio;
    if (mStickCPosYLast >= 0.75f) {
        stick_y_ratio = 1.0f;
    }
    else if (mStickCPosYLast <= -0.75f) {
        stick_y_ratio = -1.0f;
    }
    else {
        stick_y_ratio = dCamMath::rationalBezierRatio(1.333333f * mStickCPosYLast, 2.0f);
    }

    // One cushion register serves the center height first and the fovy afterwards; the fovy
    // branch re-reads styleParam[0x14] rather than reusing cushion_limited.
    f32 cur_cushion = cushion;
    f32 latitude_cushion = cushion;
    f32 radius_cushion = cushion;

    if ((dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_UNK4000000_e | daPyStts0_UNK2000000_e |
                                             daPyStts0_UNK800000_e | daPyStts0_UNK40_e |
                                             daPyStts0_UNK20_e | daPyStts0_UNK1_e) ||
         dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_UNK10000_e)) &&
        mDMCSystem.field_0x0 == 0) {
        setDMCAngle();
    }

    stick_y_ratio = -stick_y_ratio;

    f32 height = mWork.manual.m398;

    if (!limited_range_addition(&height, stick_y_ratio * height_rate, height_lower, height_upper)) {
        cur_cushion = cushion_limited;
    }

    if ((mEventFlags & dCamAttnStts_00001000_e) && mpLockonTarget != NULL && (m784 || m785)) {
        height = -50.0f;
    }

    mWork.manual.m398 += cur_cushion * (height - mWork.manual.m398);

    if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_HANG_e)) {
        if (offset_z > -10.0f) {
            offset_z = -10.0f;
        }

        if (mWork.manual.m398 < 30.0f) {
            mWork.manual.m398 = 30.0f;
        }
    }

    cXyz offset(offset_x, mWork.manual.m398, offset_z);
    bool no_lockon = false;

    if ((mEventFlags & dCamAttnStts_00001000_e) && mpLockonTarget != NULL) {
        mWork.manual.m388 = relationalPos(mpPlayerActor, mpLockonTarget, &offset, 0.5f);

        cXyz normal_pos = relationalPos(mpPlayerActor, &offset);

        dBgS_CamLinChk_NorWtr lin_chk;
        dBgS_CamLinChk_NorWtr lin_chk_both;

        if (lineBGCheck(&normal_pos, &mWork.manual.m388, &lin_chk, 0x7f) &&
            lineBGCheckBoth(&mEye, &normal_pos, &lin_chk_both, 0x7f)) {
            cM3dGPla* plane = dComIfG_Bgsp()->GetTriPla(lin_chk_both);

            if (plane->getPlaneFunc(&mEye) < 0.0f) {
                mEventFlags |= 0x80000000;
            }
        }
        else {
            f32 water_height = getWaterSurfaceHeight(&mWork.manual.m388);

            if (water_height > mWork.manual.m388.y) {
                mWork.manual.m388.y = water_height;
            }

            mWork.manual.m37C = mWork.manual.m388 - normal_pos;

            if (mWork.manual.m394 < 1.0f) {
                mWork.manual.m394 += 0.05f;
                mWork.manual.m388 = normal_pos + mWork.manual.m37C * mWork.manual.m394;
            }
            else if (mWork.manual.m394 > 1.0f) {
                mWork.manual.m394 = 1.0f;
            }
        }
    }
    else {
        no_lockon = true;
    }

    if (no_lockon) {
        mWork.manual.m388 = relationalPos(mpPlayerActor, &offset);

        f32 water_height = getWaterSurfaceHeight(&mWork.manual.m388);

        if (water_height > mWork.manual.m388.y) {
            mWork.manual.m388.y = water_height;
        }

        if (mWork.manual.m394 > 0.0f) {
            mWork.manual.m394 -= 0.05f;
            mWork.manual.m388 = mWork.manual.m388 + mWork.manual.m37C * mWork.manual.m394;
        }
        else if (mWork.manual.m394 < 0.0f) {
            mWork.manual.m394 = 0.0f;
        }
    }

    if (m11C == 0) {
        cXyz center_diff = mWork.manual.m388 - mViewCache.mCenter;
        f32 center_dist = center_diff.abs();
        f32 near_ratio;

        if (center_dist > 100.0f) {
            near_ratio = 0.0f;
        }
        else {
            near_ratio = 1.0f - center_dist / 100.0f;
        }

        mWork.manual.m3B0 = center_cushion_xz * near_ratio;
        mWork.manual.m3B4 = center_cushion_y * near_ratio;
    }
    else {
        mWork.manual.m3B0 += (center_cushion_xz - mWork.manual.m3B0) * 0.05f;
        mWork.manual.m3B4 += (center_cushion_y - mWork.manual.m3B4) * 0.05f;
    }

    cXyz center_cushion(mWork.manual.m3B0, mWork.manual.m3B4, mWork.manual.m3B0);

    mViewCache.mCenter += (mWork.manual.m388 - mViewCache.mCenter) * center_cushion;

    if (mpLockonTarget == NULL && !m780) {
        cXyz check_pos = attentionPos(mpPlayerActor);

        if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_CRAWL_e | daPyStts0_SWIM_e |
                                                daPyStts0_HANG_e)) {
            check_pos.y = 30.0f + eyePos(mpPlayerActor).y;
        }
        else {
            check_pos.y = check_pos.y - 15.0f;
        }

        dBgS_CamLinChk_NorWtr lin_chk;

        if (lineBGCheck(&check_pos, &mViewCache.mCenter, &lin_chk, 0x7f)) {
            cM3dGPla* plane = dComIfG_Bgsp()->GetTriPla(lin_chk);

            mViewCache.mCenter = lin_chk.GetCross();
            mViewCache.mCenter += plane->mNormal;
        }
    }

    f32 radius = mWork.manual.m3A8.R();

    if (!limited_range_addition(&radius, stick_y_ratio * radius_rate, radius_lower, radius_upper)) {
        radius_cushion = cushion_limited;
    }

    f32 latitude = mWork.manual.m3A8.V().Degree();

    if (!limited_range_addition(&latitude, stick_y_ratio * latitude_rate, latitude_lower,
                                latitude_upper)) {
        latitude_cushion = cushion_limited;
    }

    f32 longitude = mWork.manual.m3A8.U().Degree() + stick_x_ratio * longitude_rate;

    mWork.manual.m3A8.Val(radius, cAngle::d2s(latitude), cAngle::d2s(longitude));

    if ((mEventFlags & dCamAttnStts_00001000_e) && mpLockonTarget != NULL) {
        mEventFlags |= dCamAttnStts_00002000_e;
    }

    // Per-member writes rather than Val(): Val() ends in Formal(), which flips the globe when
    // the radius turns negative or the azimuth leaves +-90 degrees, and the console stores
    // these three members straight. The setter named U writes the member the getter named V
    // reads, and vice versa, so each line below chases the member its own getter names.
    mViewCache.mDirection.R(mViewCache.mDirection.R() +
                            radius_cushion * (mWork.manual.m3A8.R() - mViewCache.mDirection.R()));
    mViewCache.mDirection.V(mViewCache.mDirection.V() +
                            (mWork.manual.m3A8.V() - mViewCache.mDirection.V()) * latitude_cushion);
    mViewCache.mDirection.U(mViewCache.mDirection.U() +
                            (mWork.manual.m3A8.U() - mViewCache.mDirection.U()) * cushion);
    mViewCache.mEye = mViewCache.mCenter + mViewCache.mDirection.Xyz();

    f32 fovy = mViewCache.mFovy;

    if (!limited_range_addition(&fovy, stick_y_ratio * fovy_rate, fovy_lower, fovy_upper)) {
        cur_cushion = mCamParam.Val(param_1, 0x14);
    }

    mViewCache.mFovy += cur_cushion * (fovy - mViewCache.mFovy);

    f32 fly_ratio = 1.0f - (radius - radius_lower) / (radius_upper - radius_lower);

    if (dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_DEKU_LEAF_FAN_e)) {
        mViewCache.mFovy += cM_rndFX(fly_ratio * mCamSetup.m078);
    }

    if (dComIfGp_checkPlayerStatus1(mPadId, daPyStts1_DEKU_LEAF_FLY_e)) {
        cXyz ground_check_pos = positionOf(mpPlayerActor);

        ground_check_pos.y += 10.0f;

        f32 fly_height = mpPlayerActor->current.pos.y - groundHeight(&ground_check_pos);
        f32 bank_scale;
        f32 bank_cushion;

        if (fly_height < 200.0f) {
            bank_scale = mStickMainPosXLast * (fly_height / 200.0f);
            bank_cushion = 1.0f - 0.95f * (fly_height / 200.0f);
        }
        else {
            bank_scale = mStickMainPosXLast;
            bank_cushion = 0.05f;
        }

        mViewCache.mFovy += fly_ratio * (mCamSetup.m07C * cSAngle((s16)(m07C << 7)).Sin());
        mViewCache.mBank +=
            (cSAngle(fly_ratio * (bank_scale * mCamSetup.FanBank())) - mViewCache.mBank) * bank_cushion;
        mEventFlags |= dCamAttnStts_00000400_e;
    }

    return true;
}


/* 801708E0-801719C4       .text subjectCamera__9dCamera_cFl */
bool dCamera_c::subjectCamera(s32 param_1) {
    // Non-matching
    f32 p1  = mCamParam.Val(param_1, 1);
    f32 p5  = mCamParam.Val(param_1, 5);
    f32 p0  = mCamParam.Val(param_1, 0);
    f32 p10 = mCamParam.Val(param_1, 10);
    f32 p25 = mCamParam.Val(param_1, 25);
    f32 p20 = mCamParam.Val(param_1, 20);
    f32 p19 = mCamParam.Val(param_1, 19);
    f32 p24 = mCamParam.Val(param_1, 24);
    f32 p26 = mCamParam.Val(param_1, 26);

    cSAngle baseYaw = directionOf(mpPlayerActor).Inv();
    cSAngle angX, angY;
    s16 tmpX, tmpY;

    cXyz camRel;

    cSGlobe desired;

    int end;

    if (m108 == 0) {
        mWork.subject.m378 = 'SUBJ';
        mWork.subject.m37C = 0;
        mWork.subject.m37D = 1;
        mWork.subject.m380 = param_1;

        mWork.subject.m384 = 0.0f;
        mWork.subject.m388 = 0.0f;
        mWork.subject.m38C = 0.0f;

        mWork.subject.m3A8 = 100;
        mWork.subject.m3C0 = 0;
        mWork.subject.m3BC = 0;

        if (dComIfGp_getMiniGameType() == 3) {
            mWork.subject.m3C0 = 2;
        } else if (dComIfGp_checkPlayerStatus0(mPadId, daPyStts0_SUBJECT_e) == 0 && (mCamParam.Flag(param_1, dCamPrmFlg_UNK010) == 0)) {
            mWork.subject.m3C0 = 1;
        }

        if (attentionPos(mpPlayerActor).y < m354 + 20.0f) {
            mWork.subject.m3BD = 1;
        } else {
            mWork.subject.m3BD = 0;
        }

        if (mStickCPosYLast < -0.74f) {
            mWork.subject.m3C4 = 2;
        } else {
            mWork.subject.m3C4 = 0;
        }
    }

    if (mWork.subject.m3BD) {
        p5 = 60.0f;
        p0 = -5.0f;
    }

    camRel.set(p1, p5, p0);

    if (mCamParam.Flag(param_1, dCamPrmFlg_UNK080)) {
        setFlag(0x800);
    }
    if (mCamParam.Flag(param_1, dCamPrmFlg_UNK100)) {
        setFlag(0x10000000);
    }

    if (!m100) {
        if (check_owner_action(mPadId, daPyStts0_SUBJECT_e)) {
            end = 7;
        }
        else {
            end = 10;
        }

        const int framesLeft = end - m108;
        const f32 t = 1.0f / (f32)framesLeft;

        cXyz targetPos;

        switch (mWork.subject.m3C0) {
            case 1: {
                cSGlobe g(camRel);
                g.U(directionOf(mpPlayerActor) + g.U());
                targetPos = eyePos(mpPlayerActor) + g.Xyz();
                break;
            }
            case 2: {
                targetPos = mExtendedPos;
                cSAngle ang = m0FA;
                baseYaw.Val(ang.Inv());
                break;
            }
            default: {
                targetPos = relationalPos(mpPlayerActor, &camRel);
                break;
            }
        }

        cXyz delta = targetPos - mViewCache.mCenter;
        mViewCache.mCenter += delta * t;

        desired.Val(p10, cSAngle::_0, baseYaw);

        mViewCache.mDirection.R(mViewCache.mDirection.R() + (desired.R() - mViewCache.mDirection.R()) * t);
        mViewCache.mDirection.U(mViewCache.mDirection.U() + (desired.U() - mViewCache.mDirection.U()) * t);
        mViewCache.mDirection.V(mViewCache.mDirection.V() + (desired.V() - mViewCache.mDirection.V()) * t);

        mViewCache.mEye = mViewCache.mCenter + mViewCache.mDirection.Xyz();

        if (!mCamParam.CheckFlag(dCamPrmFlg_UNK010)) {
            mViewCache.mFovy += t * (p25 - mViewCache.mFovy);
        } else {
            if (m108 >= (u32)(end - 6)) {
                if (check_owner_action(mPadId, daPyStts0_TELESCOPE_LOOK_e)) {
                    setComStat(dCamAttnStts_TELESCOPE_LOOK_e);
                }
                if (check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
                    setComStat(dCamAttnStts_PICTO_BOX_AIM_e);
                }

                setComZoomScale(1.0f);

                f32 x = (dComIfGp_getItemScopeWipeScale() - 1.0f) * 0.5f * 640.0f + 320.0f;
                if (x < 640.0f &&
                    dComIfGp_getItemScopeWipeScale() >= 1.0f &&
                    dComIfGp_getItemScopeWipeScale() <= 3.0f) {

                    f32 s = (640.0f - x) / 320.0f;

                    if (dComIfGp_demo_getCamera() || check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
                        setView(s * 160.0f, s * 35.0f, x, (s * -160.0f) + 480.0f);
                    }

                    mViewCache.mFovy = mWork.subject.m39C + s * (mWork.subject.m3A0 - mWork.subject.m39C);
                }
            } else {
                if (m108 < (u32)(end - 7)) {
                    if (check_owner_action(mPadId, daPyStts0_TELESCOPE_LOOK_e)) {
                        setComStat(dCamAttnStts_TELESCOPE_LOOK_e);
                    }
                    if (check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
                        setComStat(dCamAttnStts_PICTO_BOX_AIM_e);
                    }
                    
                    setComZoomScale(1.0f);
                } else {
                    if (m108 == 0) {
                        mWork.subject.m3A0 = mViewCache.mFovy;
                        mWork.subject.m39C = mViewCache.mFovy * 0.666667f;
                    }
                }
            }
        }

        if (m108 == end - 1) {
            m100 = 1;
            m101 = 1;
            m102 = 1;

            mWork.subject.m384 = 0.0f;
            mWork.subject.m388 = 0.0f;
            mWork.subject.m38C = 0.0f;

            mWork.subject.m39C = mViewCache.mFovy;
            mWork.subject.m398 = 0;
            mWork.subject.m390 = 0.0f;
        }

        return TRUE;
    }

    if (check_owner_action(mPadId, daPyStts0_CRAWL_e)) {
        setComStat(dCamAttnStts_00000080_e);
    }

    if (dComIfGp_getScopeType() || check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
        setView(160.0f, 35.0f, 320.0f, 320.0f);
        mWork.subject.m3BC = 1;
    } else if (mWork.subject.m3BC) {
        setView(0.0f, 0.0f, 640.0f, 480.0f);
    }

    if (mWork.subject.m37D) {
        mWork.subject.m37C = 1;
        CalcSubjectAngle(&tmpX, &tmpY);
        angX = tmpX;
        angY = tmpY - mWork.subject.m3BA;
    } else {
        // actor-angle path
        if (is_player(mpPlayerActor)) {
            angX = (cSAngle)((daPy_py_c*)mpPlayerActor)->getBodyAngleX();
        } else {
            angX = mpPlayerActor->shape_angle.x;
        }
        angY = (cSAngle)mpPlayerActor->shape_angle.y - mWork.subject.m3BA;

        mWork.subject.m388 = angX.Degree() / p19;
        mWork.subject.m384 = angY.Degree() / p24;
    }

    // rotate camera-relative vector
    cXyz v1 = dCamMath::xyzRotateX(camRel, angX);
    cXyz v2 = dCamMath::xyzRotateY(v1, angY);

    switch (mWork.subject.m3C0) {
        case 1: {
            cSGlobe g(v2);
            g.U(directionOf(mpPlayerActor) + g.U());
            mViewCache.mCenter = eyePos(mpPlayerActor) + g.Xyz();
            break;
        }
        case 2: {
            mViewCache.mCenter = mExtendedPos;
            cSAngle ang(m0FA);
            baseYaw = ang.Inv();
            break;
        }
        default: {
            mViewCache.mCenter = relationalPos(mpPlayerActor, &v2);
            break;
        }
    }

    // lock-on / attention smoothing blocks
    if ((((mEventFlags >> 0x19) & 1) != 0 || (mLockOnActorId != -1)) && mpLockonTarget != NULL) {
        cXyz at = attentionPos(mpLockonTarget);
        at.y -= 25.0f;

        desired.Val(mViewCache.mCenter - at);

        mViewCache.mDirection.R(mViewCache.mDirection.R() + (p10 - mViewCache.mDirection.R()) * 0.04f);
        desired.R(p10);

        mViewCache.mDirection.U(mViewCache.mDirection.U() + (desired.U() - mViewCache.mDirection.U()) * 0.04f);
        mViewCache.mDirection.V(mViewCache.mDirection.V() + (desired.V() - mViewCache.mDirection.V()) * 0.04f);

        cSAngle dy = mViewCache.mDirection.U() - baseYaw;
        cSAngle ax = mViewCache.mDirection.V();

        mWork.subject.m384 = dy.Degree() / p24;
        mWork.subject.m388 = ax.Degree() / p19;
        mWork.subject.m3A8 = 0;
        mWork.subject.m37C = 0;
    } else if (mWork.subject.m3BC && ((mEventFlags & 0x2000000) != 0)) {
        cSGlobe g;
        g.Val(mViewCache.mCenter - mExtendedPos);

        mViewCache.mDirection.R(mViewCache.mDirection.R() + (p10 - mViewCache.mDirection.R()) * 0.05f);
        g.R(p10);

        mViewCache.mDirection.U(mViewCache.mDirection.U() + (g.U() - mViewCache.mDirection.U()) * 0.05f);
        mViewCache.mDirection.V(mViewCache.mDirection.V() + (g.V() - mViewCache.mDirection.V()) * 0.05f);

        cSAngle dy;
        cSAngle ax;
        dy = mViewCache.mDirection.U() - baseYaw;
        ax = mViewCache.mDirection.V();

        mWork.subject.m384 = dy.Degree() / p24;
        mWork.subject.m388 = ax.Degree() / p19;

        mWork.subject.m3A8 = 0;
        mWork.subject.m37C = 0;
    } else {
        cSGlobe g;
        g.Val(p10, angX, baseYaw + angY);

        mViewCache.mDirection.R(mViewCache.mDirection.R() + (g.R() - mViewCache.mDirection.R()) * p20);
        mViewCache.mDirection.U(mViewCache.mDirection.U() + (g.U() - mViewCache.mDirection.U()) * p20);
        mViewCache.mDirection.V(mViewCache.mDirection.V() + (g.V() - mViewCache.mDirection.V()) * p20);

        if (mWork.subject.m3A8 < 10) {
            mWork.subject.m3A8++;
        }
        mWork.subject.m37C = 1;
    }

    mViewCache.mEye = mViewCache.mCenter + mViewCache.mDirection.Xyz();

    if (mCamParam.CheckFlag(dCamPrmFlg_UNK010)) {
        // zoom control block
        f32 a = 0.0f;
        f32 stick = mStickCPosYLast;

        f32 b = dCamMath::rationalBezierRatio(-stick, mCamSetup.mCurveWeight);

        f32 next = mWork.subject.m38C + p26 * (a - b) * 0.1f;
        if (next < 0.0f) {
            mWork.subject.m38C = 0.0f;
        }
        else if (next > 1.0f) {
            mWork.subject.m38C = 1.0f;
        }
        else {
            mWork.subject.m38C = next;
        }

        f32 z = mWork.subject.m38C;
        if (z == 0.0f || z == 0.5f || z == 1.0f) {
            a = 0.0f;
            b = 0.0f;
        }

        f32 scale = z * 8.0f + 1.0f;
        mViewCache.mFovy += p20 * ((dCamMath::zoomFovy(mWork.subject.m39C * 0.5f, scale) * 2.0f) - mViewCache.mFovy);

        setComZoomScale(scale);

        if (check_owner_action(mPadId, daPyStts0_TELESCOPE_LOOK_e)) {
            setComStat(dCamAttnStts_TELESCOPE_LOOK_e);
        }
        if (check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
            setComStat(dCamAttnStts_PICTO_BOX_AIM_e);
        }

        f32 focus = 1.0f - (std::fabs(a - b) * 511.0f);
        setComZoomForcus(focus);

        mDoGph_gInf_c::offAutoForcus();
    } else {
        mViewCache.mFovy += p20 * (p25 - mViewCache.mFovy);
    }

    mWork.subject.m37D = 1;

    // "C-stick down" behavior block
    if (check_owner_action(mPadId, daPyStts0_SUBJECT_e)) {
        if (mWork.subject.m3C4 == 2 && mStickCPosYLast >= -0.001f) {
            mWork.subject.m3C4 = 0;
        }
        else if (mWork.subject.m3C4 == 1 && mStickCPosYLast < -0.74f) {
            mWork.subject.m3C4 = 2;
            setComStat(dCamAttnStts_00002000_e);
        }
        else if (mStickCPosYLast < -0.001f) {
            mWork.subject.m3C4 = 1;
        }
        else {
            mWork.subject.m3C4 = 0;
        }
    }

    return TRUE;
}

/* 80170490-801708E0       .text CalcSubjectAngle__9dCamera_cFPsPs */
bool dCamera_c::CalcSubjectAngle(s16* param_1, s16* param_2) {
    f32 fVar1;
    f32 fVar2;
    f32 fVar3;
    f32 fVar4;
    f32 fVar5;
    f32 fVar6;
    f32 dVar11;
    f32 dVar12;

    bool bVar9 = true;
    
    if (dComIfGp_evmng_cameraPlay() && dComIfGp_getMiniGameType() != 8) {
        return false;
    }

    if (mWork.subject.m378 != 'SUBJ') {
        return false;
    }

    if (!m100) {
        return false;
    }

    if (!mWork.subject.m37C) {
        bVar9 = false;
    }

    fVar1 = mCamParam.Val(mWork.subject.m380, 19);
    fVar2 = mCamParam.Val(mWork.subject.m380, 24);
    fVar3 = mCamParam.Val(mWork.subject.m380, 21);
    fVar4 = mCamSetup.m030;
    
    if (!bVar9) {
        cSAngle local_88(fVar2 * mWork.subject.m384);
        cSAngle local_8c(fVar1 * mWork.subject.m388);
        s16 local_98 = local_88.Val() + mWork.subject.m3BA;
        *param_2 = local_98;
        *param_1 = local_8c.Val();
    }
    
    fVar6 = CPad_GET_STICK_POS_X(mPadId);
    fVar5 = CPad_GET_STICK_POS_Y(mPadId);

    if (is_player(mpPlayerActor)) {
        mWork.subject.m3B8 = ((daPy_py_c*)mpPlayerActor)->getBodyAngleX();
    }
    else {
        mWork.subject.m3B8 = mpPlayerActor->shape_angle.x;
    }

    mWork.subject.m3BA = mpPlayerActor->shape_angle.y;

    f32 f1;
    if (fVar6 > 0.7f) {
        f1 = 1.0f;
    } 
    else if (fVar6 < -0.7f) {
        f1 = -1.0f;
    }
    else {
        f1 = fVar6 / 0.7f;
    }

    f32 f3;
    if (fVar5 > 0.7f) {
        f3 = 1.0f;
    } 
    else if (fVar5 < -0.7f) {
        f3 = -1.0f;
    }
    else {
        f3 = fVar5 / 0.7f;
    }
    fVar5 = f3;

    f32 f2 = 5.0f;
    if ((mEye.y <= m354 + f2 || mEye.y <= mBG.m5C.m58 + f2) && ((mWork.subject.m388 >= 0.0f && f3 > 0.0f) || (mWork.subject.m388 < 0.0f && f3 <= 0.0f))) {
        fVar5 = 0.0f;
    }
    
    if (check_owner_action(mPadId, daPyStts0_CRAWL_e)) {
        fVar5 = 0.0f;
    }

    if (!check_owner_action(mPadId, daPyStts0_UNK40000_e)) {
        if (mCamParam.Flag(mWork.subject.m380, dCamPrmFlg_UNK020)) {
            mWork.subject.m384 = -f1;
            mWork.subject.m388 = fVar5;
        }
        else {
            dVar11 = dCamMath::rationalBezierRatio(f1, mCamSetup.CurveWeight());
            dVar12 = dCamMath::rationalBezierRatio(fVar5, mCamSetup.CurveWeight());
            if (check_owner_action(mPadId, daPyStts0_SUBJECT_e)) {
                mWork.subject.m384 = -dVar11 * fVar3;
                mWork.subject.m388 += dVar12 * fVar3;
            }
            else {
                if (mCamParam.Flag(mWork.subject.m380, dCamPrmFlg_UNK010)) {
                    f32 temp = fVar3 - (mWork.subject.m38C * (fVar3 * fVar4));
                    mWork.subject.m384 = -dVar11 * temp;
                    mWork.subject.m388 += dVar12 * temp;
                }
                else {
                    mWork.subject.m384 = -dVar11 * fVar3;
                    mWork.subject.m388 += dVar12 * fVar3;
                }
            }
            if (mWork.subject.m384 > 1.0f) {
                mWork.subject.m384 = 1.0f;
            }
            if (mWork.subject.m384 < -1.0f) {
                mWork.subject.m384 = -1.0f;
            }
            if (mWork.subject.m388 > 1.0f) {
                mWork.subject.m388 = 1.0f;
            }
            if (mWork.subject.m388 < -1.0f) {
                mWork.subject.m388 = -1.0f;
            }
        }
    }
    else {
        mWork.subject.m384 = 0.0f;
    }

    cSAngle local_90(fVar2 * mWork.subject.m384);
    cSAngle local_94(fVar1 * mWork.subject.m388);
    
    s16 local_a8 = local_90.Val() + mWork.subject.m3BA;
    *param_2 = local_a8;
    *param_1 = local_94.Val();
    mWork.subject.m37D = 0;
    return bVar9;
}

int dCamera_c::nextMode(s32 i_curMode) {
    /* Nonmatching - regswap related to check_owner_action/check_owner_action1 */
    dAttention_c& attn = dComIfGp_getAttention();
    s32 next_mode = i_curMode;
    cXyz player_pos = positionOf(mpPlayerActor);

    if (!dComIfGp_evmng_cameraPlay()) {
        if (mBG.m00.m58 > player_pos.y) {
            m1AE = 0;
        }
        switch(i_curMode) {
            case 4:
            case 10:
            case 11:
            case 13:
            case 14:
                m144 = 1;
                m184 = 0;
                break;
            case 5:
            case 6:
                m144 = 1;
                m184 = 0;
            case 1:
                mpLockonTarget = NULL;
            default:
                if (m19B) {
                    m144 = 1;
                    m184 = 0;
                }
                else if (mStickCPosYLast <= 0.0f && mStickCValueLast > mCamSetup.m09C) {
                    m144 = 0;
                }
                else if (i_curMode == 0 || i_curMode == 0x13) {
                    positionOf(mpPlayerActor);
                    if (
                        !(
                            mStickMainValueLast >= 0.5f ||
                            attn.LockonTruth() ||
                            check_owner_action(mPadId, daPyStts0_SWIM_e)
                        )
                    ) {
                        if (m184 == 1) {
                            if (mStickCPosYLast < mCamSetup.mCstick.m00) {
                                m184 = 0;
                            }
                        }
                        else if (mStickCPosYLast > mCamSetup.mCstick.m04) {
                            // C-stick up.
                            setComStat(dCamAttnStts_00001000_e);
                            m184 = 1;
                            setComStat(dCamAttnStts_00000400_e);
                        }
                        else {
                            setComStat(dCamAttnStts_00000400_e);
                        }
                    }
                }
                break;
            case 12:
                if ((mStickCValueLast < 0.01f && mDirection.R() < mCamSetup.m098) || chkFlag(0x80000000)) {
                    m144 = 1;
                    m184 = 0;
                }
                else if (m19B != 0) {
                    m144 = 1;
                    m184 = 0;
                }
                break;
        }
        if (chkFlag(0x4000000)) {
            if (m144 == 0) {
                m254 |= 1;
            }

            if (check_owner_action(mPadId, daPyStts0_UNK80000000_e)) {
                setFlag(0x8000);
            }

            m144 = 1;

            clrFlag(0x4000000);
        }

        if (mLockOnActorId != fpcM_ERROR_PROCESS_ID_e && mpLockonActor && fopAcM_GetName(mpLockonActor) == fpcNm_NPC_MD_e) {
            m144 = 1;
            i_curMode = 0;
        }

        if (i_curMode == 12 && m144 != 0) {
            next_mode = 0;
        }
        else if (check_owner_action(mPadId, daPyStts0_TELESCOPE_LOOK_e) || check_owner_action1(mPadId, daPyStts1_PICTO_BOX_AIM_e)) {
            next_mode = 0xe;
        }
        else if (check_owner_action(mPadId, daPyStts0_UNK80000000_e | daPyStts0_UNK80_e)) {
            next_mode = 0x11;
        }
        else if (check_owner_action(mPadId, daPyStts0_UNK800000_e)) {
            if (m144 == 0) {
                next_mode = 0xc;
            }
            else {
                next_mode = 0x12;
            }
        }
        else if (check_owner_action1(mPadId, daPyStts1_UNK10_e)) {
            next_mode = 0xf;
        }
        else if (check_owner_action(mPadId, daPyStts0_SUBJECT_e)) {
            next_mode = 4;
        }
        else if (check_owner_action(mPadId, daPyStts0_ROPE_AIM_e | daPyStts0_HOOKSHOT_AIM_e | daPyStts0_BOW_AIM_e) && !attn.Lockon()) {
            next_mode = 10;
        } else if (check_owner_action(mPadId, daPyStts0_BOOMERANG_AIM_e) && !attn.Lockon()) {
            next_mode = 11;
        } else if (m144 == 0) {
            next_mode = 12;
        }
        else if (check_owner_action1(mPadId, daPyStts1_UNK2_e)) {
            next_mode = 5;
        }
        else if (check_owner_action1(mPadId, daPyStts1_UNK4_e)) {
            next_mode = 6;
        }
        else if (check_owner_action(mPadId, daPyStts0_UNK40_e | daPyStts0_UNK20_e)) {
            next_mode = 6;
        }
        else if (check_owner_action(mPadId, daPyStts0_UNK40_e | daPyStts0_UNK20_e | daPyStts0_UNK1_e)) {
            next_mode = 5;
        }
        else if (check_owner_action(mPadId, daPyStts0_UNK400_e | daPyStts0_UNK4_e | daPyStts0_UNK2_e) && i_curMode != 12) {
            if (mpLockonTarget) {
                next_mode = 8;
            }
        }
        else if (attn.LockonTruth() && !check_owner_action(mPadId, daPyStts0_CRAWL_e | daPyStts0_UNK4000000_e)) {
            next_mode = 2;
        }
        else if (attn.Lockon()) {
            next_mode = 1;
        }
        else if (check_owner_action(mPadId, daPyStts0_BOOMERANG_WAIT_e) && !check_owner_action(mPadId, daPyStts0_UNK37a02371_e & ~daPyStts0_UNK1000000_e) && !check_owner_action1(mPadId, daPyStts1_UNK10_e | daPyStts1_WIND_WAKER_CONDUCT_e)) {
            mpLockonTarget = get_boomerang_actor(mpPlayerActor);
            next_mode = 2;
            mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
        }
        else if (isPlayerGuarding(mPadId)) {
            next_mode = 19;
        }
        else if (mLockOnActorId != fpcM_ERROR_PROCESS_ID_e) {
            if (mpLockonActor) {
                next_mode = 2;
                mpLockonTarget = mpLockonActor;
            }
            else {
                next_mode = 0;
                mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
            }
        }
        else {
            switch (i_curMode) {
            case 12:
                if (m144 != 0) {
                    next_mode = 0;
                }
                break;
            default:
                next_mode = 0;
            }
        }
    }

    if (next_mode != 2) {
        mLockOnActorId = fpcM_ERROR_PROCESS_ID_e;
    }

    if (next_mode == 12 && types[mCurType].mStyles[next_mode] < 0) {
        next_mode = i_curMode;
        if (
            mCurType != mCamTypeEvent && mCurType != mCamTypeBoat &&
#if VERSION == VERSION_DEMO
            mCurType != GetCameraTypeFromCameraName("BoatBattle")
#else
            mCurType != mCamTypeBoatBattle && mCurType != mCamTypeRestrict
#endif
        )
        {
            m254 |= 1;
        }
        m144 = 1;
    }

    if (types[mCurType].mStyles[next_mode] >= 0) {
        if (next_mode == 1) {
            setFlag(0x100000);
        }
        return next_mode;
    }

    return i_curMode;
}

bool dCamera_c::onModeChange(s32 i_curMode, s32 i_nextMode) {
    if (i_curMode == 0xe && mCamParam.CheckFlag(dCamPrmFlg_UNK010)) {
        setView(0.0f, 0.0f, 640.0f, 480.0f);
    }
    
    m108 = 0;
    m100 = 0;
    m101 = 0;
    m102 = 0;
    m10C = 0;
    m110 = 1;
    m14C = 0.0f;
    
    clrFlag(0x11E);
    clrFlag(0x2000);
    
    switch (i_curMode) {
    case 3:
        clrComStat(dCamAttnStts_00000004_e);
        break;
    case 4:
    case 10:
    case 11:
    case 13:
    case 14:
        break;
    }
    
    switch(i_nextMode) {
    case 7:
        setFlag(0x10);
        break;
    case 0:
        if (i_curMode == 1 && types[mCurType].mStyles[0] == types[mCurType].mStyles[1]) {
            m110 = 0;
        }
        break;
    case 1:
        if (i_curMode == 0 && types[mCurType].mStyles[0] == types[mCurType].mStyles[1]) {
            m110 = 0;
        }
        break;
    case 12:
        if (i_curMode != i_nextMode) {
            m254 |= 2;
        }
        break;
    case 4:
        break;
    }
    return TRUE;
}

void dCamera_c::updatePad() {
    f32 fVar1;
    f32 fVar2;
    f32 fVar3;
    
    if (chkFlag(0x1000000)) {
        fVar1 = 0.0f;
        fVar2 = 0.0f;
        fVar3 = 0.0f;
    }
    else {
        fVar1 = CPad_GET_STICK_POS_X(mPadId);
        fVar2 = CPad_GET_STICK_POS_Y(mPadId);
        fVar3 = CPad_GET_STICK_VALUE(mPadId);
    }

    cSAngle unused(CPad_GET_STICK_ANGLE(mPadId)); // Unused object? Code matches so perhaps a developer oversight

    mStickMainPosXDelta = fVar1 - mStickMainPosXLast;
    mStickMainPosYDelta = fVar2 - mStickMainPosYLast;
    mStickMainValueDelta = fVar3 - mStickMainValueLast;

    mStickMainPosXLast = fVar1;
    mStickMainPosYLast = fVar2;
    mStickMainValueLast = fVar3;

    if (chkFlag(0x800000)) {
        fVar1 = 0.0f;
        fVar2 = 0.0f;
        fVar3 = 0.0f;
    }
    else {
        fVar1 = CPad_GET_SUBSTICK_POS_X(mPadId);
        fVar2 = CPad_GET_SUBSTICK_POS_Y(mPadId);
        fVar3 = CPad_GET_SUBSTICK_VALUE(mPadId);
    }

    mStickCPosXDelta = fVar1 - mStickCPosXLast;
    mStickCPosYDelta = fVar2 - mStickCPosYLast;
    mStickCValueDelta = fVar3 - mStickCValueLast;

    mStickCPosXLast = fVar1;
    mStickCPosYLast = fVar2;
    mStickCValueLast = fVar3;

    fVar1 = CPad_GET_ANALOG_L(mPadId);
    mTriggerLeftDelta = mTriggerLeftLast - fVar1;
    mTriggerLeftLast = fVar1;

    mHoldLockL = mDoCPd_L_LOCK_BUTTON(mPadId);
    mTrigLockL = mDoCPd_L_LOCK_TRIGGER(mPadId);

    if (mTriggerLeftLast > mCamSetup.m0A0) {
        if (m19A == 0) {
            m19B = 1;
        }
        else {
            m19B = 0;
        }
        
        m19A = 1;
    }
    else {
        m19B = 0;
        m19A = 0;
    }

    fVar1 = CPad_GET_ANALOG_R(mPadId);
    mTriggerRightDelta = mTriggerRightLast - fVar1;
    mTriggerRightLast = fVar1;

    mHoldLockR = mDoCPd_R_LOCK_BUTTON(mPadId);
    mTrigLockR = mDoCPd_R_LOCK_TRIGGER(mPadId);

    if (mTriggerRightLast > mCamSetup.m0A0) {
        if (m1A6 == 0) {
            m1A7 = 1;
        }
        else {
            m1A7 = 0;
        }
        
        m1A6 = 1;
    }
    else {
        m1A7 = 0;
        m1A6 = 0;
    }


    mHoldX = (bool)CPad_CHECK_HOLD_X(mPadId);
    mTrigX = (bool)CPad_CHECK_TRIG_X(mPadId);

    mHoldY = (bool)CPad_CHECK_HOLD_Y(mPadId);
    mTrigY = (bool)CPad_CHECK_TRIG_Y(mPadId);

    mHoldZ = (bool)CPad_CHECK_HOLD_B(mPadId); // mHoldZ might not be the appropriate name for this?
    mTrigZ = (bool)CPad_CHECK_TRIG_B(mPadId); // likewise for mTrigZ

    m1AE = 0;
}

/* 80169528-8016A0F0       .text checkGroundInfo__9dCamera_cFv */
void dCamera_c::checkGroundInfo() {
    cXyz player_pos = positionOf(mpPlayerActor);
    cXyz gnd_chk_pos = player_pos;

    f32 player_height; // suprisingly the `heightOf` function wasn't used here
    if (is_player(mpPlayerActor)) {
        player_height = ((daPy_py_c*)mpPlayerActor)->getHeight();
    } else {
        player_height = (mpPlayerActor->eyePos.y - mpPlayerActor->current.pos.y) * 1.1f;
    }

    player_pos.y += player_height;

    dBgS_RoofChk roof_chk;
    roof_chk.SetPos(gnd_chk_pos);

    f32 roof_y = dComIfG_Bgsp()->RoofChk(&roof_chk);

    if (gnd_chk_pos.y < roof_y) {
        gnd_chk_pos.y = roof_y;
    }

#if VERSION > VERSION_JPN
    dBgS_CamGndChk gnd_chk;
    gnd_chk.ClrCam();
    gnd_chk.SetObj();
    gnd_chk.SetPos(&player_pos);
    f32 ground_y = dComIfG_Bgsp()->GroundCross(&gnd_chk);
#endif

#if VERSION <= VERSION_JPN
    if (m787 != 0) {
        mBG.m5C.m04.ClrCam();
        mBG.m5C.m04.SetObj();
    } else {
        mBG.m5C.m04.SetCam();
        mBG.m5C.m04.ClrObj();
    }
#else
    mBG.m5C.m04.SetCam();
    mBG.m5C.m04.ClrObj();
#endif

    mBG.m5C.m04.SetPos(&player_pos);
    
    mBG.m5C.m58 = dComIfG_Bgsp()->GroundCross(&mBG.m5C.m04);

#if VERSION > VERSION_JPN
    if (mBG.m5C.m58 < ground_y) {
        mBG.m5C.m58 = ground_y;
        mBG.m5C.m04 = gnd_chk;
    }
#endif

    mBG.m5C.m00 = mBG.m5C.m58 != -G_CM3D_F_INF;
    
    mBG.m00.m04.SetPos(&gnd_chk_pos);

    mBG.m00.m58 = dComIfG_Bgsp()->GroundCross(&mBG.m00.m04);

    mBG.m00.m00 = mBG.m00.m58 != -G_CM3D_F_INF;

    m354 = mBG.m00.m58;
    if (footHeightOf(mpPlayerActor) - mBG.m5C.m58 > mCamSetup.mBGChk.FloorMargin()) {
        m360 = 0;
    }
    else {
        m360 = 1;
    }

    m31D = 0;
    m33C = 0;
    
    if (dComIfG_Bgsp()->ChkMoveBG(mBG.m5C.m04)) {
        m33C = dComIfG_Bgsp()->GetActorPointer(mBG.m5C.m04);
        if (m33C) {
            cXyz pos = positionOf(m33C);
            cSAngle angle = directionOf(m33C);

            if (m31C) {
                m320 = m32C - pos;
                m338 = m33A - angle;

                if (fopAcM_GetName(m33C) == fpcNm_Obj_Pirateship_e) {
                    mViewCache.mCenter.y += m320.y * mCamSetup.mManualStartCThreshold;
                }
            }

            m31C = 1;

            if (!dComIfGp_evmng_cameraPlay() && !chkFlag(0x20000000) && m360) { 
                m31D = 1;
            }

            if (m31D) {
                dComIfG_Bgsp()->MoveBgMatrixCrrPos(mBG.m5C.m04, true, &mViewCache.mCenter, NULL, NULL);
                dComIfG_Bgsp()->MoveBgMatrixCrrPos(mBG.m5C.m04, true, &mViewCache.mEye, NULL, NULL);
                mViewCache.mDirection.Val(mViewCache.mEye - mViewCache.mCenter);
            }

            m32C = pos;
            m33A = angle;
        }
    } 
    else {
        m31C = 0;
    }
    
    if (mBG.m5C.m00) {
        m350 = dComIfG_Bgsp()->GetCamMoveBG(mBG.m5C.m04);
    }
    else {
        m350 = 0;
    }

    mRoomNo = -1;

    if (mBG.m00.m00 && check_owner_action(mPadId, daPyStts0_SWIM_e)) {
        mRoomMapToolCameraIdx = dComIfG_Bgsp()->GetPolyCamId(mBG.m00.m04.GetBgIndex(), mBG.m00.m04.GetPolyIndex());
    }
    else if (m360 == 0) {
        mRoomMapToolCameraIdx = 0x1ff;
    }
    else if (mBG.m5C.m00) {
        mRoomMapToolCameraIdx = dComIfG_Bgsp()->GetRoomCamId(mBG.m5C.m04);
        if (mRoomMapToolCameraIdx == 0xff) {
            mRoomMapToolCameraIdx = dComIfG_Bgsp()->GetPolyCamId(mBG.m5C.m04.GetBgIndex(), mBG.m5C.m04.GetPolyIndex());
        }
        else {
            mRoomNo = dComIfG_Bgsp()->GetRoomId(mBG.m5C.m04);;
        }
    }
    else {
        mRoomMapToolCameraIdx = 0xff;
    }

    if (daSea_ChkArea(player_pos.x, player_pos.z)) {
        m318 = daSea_calcWave(player_pos.x, player_pos.z);
        m314 = 1;
    }
    else {
        m318 = -G_CM3D_F_INF;
        m314 = 0;
    }
    
    if (m354 < m318) {
        m354 = m318;
    }

    dBgS_GndChk gnd_chk_2;

    gnd_chk_2.SetPos(&mEye);

    cXyz pos1;
    cXyz pos2;
    if (dComIfG_Bgsp()->GroundCross(&gnd_chk_2) < mBG.m5C.m58 + 40.0f) {
        pos1 = mEye;
        pos2 = attentionPos(mpPlayerActor);
        pos2 += (pos1 - pos2) * 0.5f;
    }
    else {
        pos2 = mEye;
        pos1 = attentionPos(mpPlayerActor);
        pos1 += (pos2 - pos1) * 0.5f;
    }

    if (m360) {
        m364 = lineCollisionCheckBush(&pos1, &pos2) & 5;
        if (m364 & 4) {
            m368 = mCamSetup.m0C0;
        }
        if (m364 & 1) {
            m368 = mCamSetup.LockonChangeCushion();
        }
        if (m364) {
            dComIfG_Ccsp()->GetMassCamTopPos(&m36C);
        }
    }
    else {
        m364 = 0;
        m368 = 0.0f;
    }
}

bool dCamera_c::bumpCheck(u32 i_flags) {
    thread_local int prev_hit_type = 0;
    thread_local int prev_plat1 = 0;
    thread_local int prev_plat2 = 0;

    int curr_hit_type;
    int res = 0;

    f32 gaze_back_margin = mCamSetup.mBGChk.GazeBackMargin();
    f32 corner_cushion = mCamSetup.mBGChk.CornerCushion();
    f32 corner_angle_max_cos = cDegree(mCamSetup.mBGChk.CornerAngleMax()).Cos();
    f32 wall_up_distance = mCamSetup.mBGChk.WallUpDistance();

    if (is_player(mpPlayerActor)) {
        u32 grab_actor_id = static_cast<daPy_py_c*>(mpPlayerActor)->getGrabActorID();
        if (grab_actor_id != -1) {
            fopAc_ac_c* grab_actor = fopAcM_SearchByID(grab_actor_id);
            if (grab_actor != NULL) {
                s16 proc_name = fopAcM_GetName(grab_actor);
                if (proc_name == fpcNm_TSUBO_e) {
                    switch (daObj::PrmAbstract(grab_actor, daTsubo::Act_c::PRM_TYPE_W, daTsubo::Act_c::PRM_TYPE_S)) {
                        case 1:
                        case 2:
                        case 3:
                        case 4:
                        case 7:
                        case 8:
                        case 13:
                        case 14:
                        case 15:
                            wall_up_distance = 150.0f;
                            break;
                      
                        default:
                            wall_up_distance = 110.0f;
                            break;
                      }
                }
                else if (proc_name == fpcNm_NPC_MD_e) {
                    wall_up_distance = 130.0f;
                }
                else if (proc_name == fpcNm_Obj_Try_e) {
                    wall_up_distance = 200.0f;
                }
                else {
                    wall_up_distance = 110.0f;
                }
            }
        }
    }

    cXyz eye = mViewCache.mEye;
    cSGlobe direction = mViewCache.mDirection;

    if (chkFlag(0x2000) && mpLockonTarget) {
        f32 sight_radius = radiusActorInSight(mpPlayerActor, mpLockonTarget);
        if (sight_radius > 0.0f) {
            if (sight_radius >= 3500.0f) {
                sight_radius = 3500.0f;
            }
            m14C += (sight_radius - m14C) * 0.33f;
            res |= 0x40;
        }
        else {
            m14C -= m14C * 0.08f;
        }

        f32 fVar15 = 1.0f;
        if (m108 < 10) {
            fVar15 = m108 / 10.0f;
        }
        
        direction.R(m14C * fVar15 + direction.R());
        eye = mViewCache.mCenter + direction.Xyz();
    }

    if ((i_flags & 0x40) && m364 != 0) {
        cSGlobe cStack_3e4 = m36C - mViewCache.mCenter;
        if (direction.V() < cStack_3e4.V()) {
            cSAngle local_408 = mDirection.V();
            local_408 += (cStack_3e4.V() - local_408) * 0.05f;
            direction.V(local_408);
            eye = mViewCache.mCenter + direction.Xyz();
            res |= 0x20;
        }
    }

    dBgS_CamLinChk_NorWtr lin_chk1;
    dBgS_CamLinChk_NorWtr lin_chk2;

    f32 fVar2;

    cXyz local_2fc; /* 0x2FC */
    cXyz mid; /* 0x2F0 */
    cXyz local_2e4; /* 0x2E4 */
    cXyz cross_prod; /* 0x2D8 */
    cXyz cross1; /* 0x2CC */
    cXyz cross2; /* 0x2C0 */
    cXyz local_2b4; /* 0x2B4 */
    cXyz local_2a8; /* 0x2A8 */
    cXyz local_29c; /* 0x29C */
    cXyz local_290; /* 0x290 */
    cXyz local_284; /* 0x284 */
    cXyz local_278; /* 0x278 */

    if (lineBGCheck(&mCenter, &eye, &lin_chk1, i_flags)) {
        cM3dGPla* plane1 = dComIfG_Bgsp()->GetTriPla(lin_chk1);
        cM3dGPla* plane2 = NULL;
        if ((i_flags & 0x20) == 0) {
            curr_hit_type = 2;
        }
        else {
            if (lineBGCheck(&eye, &mCenter, &lin_chk2, i_flags)) {
                plane2 = dComIfG_Bgsp()->GetTriPla(lin_chk2);
                f32 dot_prod = VECDotProduct(plane1->GetNP(), plane2->GetNP());
                VECCrossProduct(plane1->GetNP(), plane2->GetNP(), &cross_prod);
                if (dot_prod > corner_angle_max_cos && std::fabs(cross_prod.y) > 0.5f) {
                    curr_hit_type = 3;
                }
                else if (prev_hit_type != 3) {
                    curr_hit_type = 4;
                }
                else {
                    curr_hit_type = 5;
                }
            }
            else if (prev_hit_type == 3 || prev_hit_type == 5) {
                curr_hit_type = 5;
            }
            else {
                curr_hit_type = 2;
            }
        }
        switch (curr_hit_type) {
            case 3: {
                res |= 2;
                cross1 = lin_chk1.GetCross(); 
                cross2 = lin_chk2.GetCross();
                mid = cross1 + (cross2 - cross1) * 0.5f;
                if (cM3d_2PlaneLinePosNearPos(*plane1, *plane2, &mid, &local_2fc)) {
                    local_2e4 = *plane1->GetNP() + *plane2->GetNP();
                    m070 = local_2fc + local_2e4 * 2.0f;
                    
                    cSGlobe globe;
                    globe.Val(m070 - mCenter);

                    mDirection.R(direction.R());
                    mDirection.V(mDirection.V() + (globe.V() - mDirection.V()) * 0.05f);
                    mDirection.U(mDirection.U() + (globe.U() - mDirection.U()) * corner_cushion);

                    local_2b4 = mCenter + mDirection.Xyz();
                    globe.R(globe.R() + 50.0f);
                    local_2a8 = mCenter + globe.Xyz();
                    if (!lineBGCheck(&mCenter, &local_2a8, 0x7f)) {
                        if (lineBGCheck(&m070, &local_2b4, &lin_chk1, 0x7f)) {
                            local_29c = lin_chk1.GetCross();
                            local_2b4 = compWallMargin(&local_29c, gaze_back_margin);
                        }
                        lineBGCheck(&mCenter, &local_2b4, &lin_chk1, i_flags);
                        mEye = local_2b4;
                        setFlag(0x80000);
                        break;
                    }
                    curr_hit_type = 2;
                }
                // Fall-through
            }
            case 2:
            case 4:
            case 5: {
                setFlag(0x80);
                setFlag(0x80);

                local_290 = lin_chk1.GetCross();

                local_284 = compWallMargin(&local_290, 0.5f + gaze_back_margin);

                local_278 = local_284;

                if (chkFlag(8) && (i_flags & 0x10) && curr_hit_type != 4) {
                    f32 xyzDist = dCamMath::xyzHorizontalDistance(local_290, mCenter);
                    f32 dVar14 =  wall_up_distance - (mCenter.y - attentionPos(mpPlayerActor).y);

                    if (!(xyzDist < 20.0f)) {
                        if (xyzDist > 320.0f) {
                            dVar14 = 0.0f;
                        }
                        else {
                            dVar14 *= 1.0f - (xyzDist - 20.0f) / 300.0f;
                        }
                    }

                    if (local_284.y - mCenter.y < dVar14) {
                        local_2e4 = *plane1->GetNP();

                        cSGlobe globe(local_2e4);
                        globe.V(globe.V() + cSAngle::_90);
                        globe.R(dVar14 * globe.V().Sin());

                        local_284 += globe.Xyz();

                        if (lineBGCheck(&local_278, &local_284, &lin_chk1, i_flags)) {
                            cXyz cross = lin_chk1.GetCross();
                            local_284 = compWallMargin(&cross, gaze_back_margin);
                            mEye += (local_284 - mEye) * mCamSetup.mBGChk.WallCushion();
                        }
                        else {
                            mEye += (local_284 - mEye) * mCamSetup.mBGChk.WallCushion();
                        }

                        setFlag(0x4000);
                    }
                    else {
                        if (lineBGCheck(&local_278, &local_284, &lin_chk1, i_flags)) {
                            cXyz cross = lin_chk1.GetCross();
                            local_284 = compWallMargin(&cross, gaze_back_margin);
                        }

                        mEye += (local_284 - mEye) * mCamSetup.mBGChk.WallBackCushion();
                    }
                }
                else {
                    mEye = local_284;
                }

                int engine_idx = mCamParam.Algorythmn();

                if (engine_idx == dCamAlg_FOLLOW_CAMERA_e || engine_idx == dCamAlg_MANUAL_CAMERA_e) {
                    cXyz attn_pos = attentionPos(mpPlayerActor);
                    cSGlobe globe(mEye - attn_pos);

                    if (globe.R() < 40.0f) {
                        globe.R(40.0f);
                        mEye = attn_pos + globe.Xyz();
                    }
                }

                mDirection.Val(mEye - mCenter);
                res |= 1;
                break;
            }
            default:
                mEye = eye;
                mDirection = direction;
                break;
        }
    } 
    else {
        curr_hit_type = 0;

        if (chkFlag(0x4000)) {
            if (i_flags & 0x10) {
                fVar2 = mCamSetup.mBGChk.WallBackCushion();
            }
            else {
                fVar2 = 0.2f;
            }

            mDirection.R(mDirection.R() + (mViewCache.mDirection.R() - mDirection.R()) * fVar2);
            mDirection.V(mDirection.V() + (mViewCache.mDirection.V() - mDirection.V()) * fVar2);
            mDirection.U(mViewCache.mDirection.U());

            mEye = mCenter + mDirection.Xyz();

            if (lineBGCheck(&mCenter, &mEye, &lin_chk1, i_flags)) {
                cXyz cross = lin_chk1.GetCross();
                mEye = compWallMargin(&cross, 0.5f + gaze_back_margin);
            }

            cSAngle acStack_440 = mDirection.V() - mViewCache.mDirection.V();
            corner_angle_max_cos = acStack_440.Degree();

            if (std::fabs(corner_angle_max_cos) < 0.2f) {
                clrFlag(0x4000);
            }
        } 
        else {
            mEye = eye;
            mDirection = direction;
        }
    }

    if ((i_flags & 8) != 0) {
        f32 water_surface_height = getWaterSurfaceHeight(&mEye);
        if (water_surface_height > mEye.y) {
            mEye.y = water_surface_height;
            mDirection.Val(mEye - mCenter);
            res |= 8;
        }
    }

    prev_hit_type = curr_hit_type;

    if (m78B && (mCamParam.Algorythmn(mCurStyle) != 4 || !chkFlag(0x10000800))) {
        mEye.y += 25.0f;
    }

    return res != 0;
}

f32 dCamera_c::getWaterSurfaceHeight(cXyz* param_0) {
    f32 var_f31 = -G_CM3D_F_INF;

    cXyz spF8(*param_0);
    dBgS_RoofChk roofchk;

    roofchk.SetPos(spF8);

    f32 roof_y = dComIfG_Bgsp()->RoofChk(&roofchk);
    if (spF8.y < roof_y) {
        spF8.y = roof_y;
    }
    
    dBgS_CamGndChk_Wtr gndchk;
    gndchk.SetPos(&spF8);

    f32 gnd_y = dComIfG_Bgsp()->GroundCross(&gndchk);

    if (gnd_y + 5.0f > param_0->y) {
        var_f31 = gnd_y + 5.0f;
    }
    
    
    if (daSea_ChkArea(param_0->x, param_0->z)) {
        f32 waveHeight = daSea_calcWave(param_0->x, param_0->z) + 20.0f;
        if (waveHeight > param_0->y  && waveHeight > var_f31) {
            var_f31 = waveHeight;
        }
    }

    if (var_f31 == -G_CM3D_F_INF) {
        var_f31 = param_0->y;
    }

    return var_f31;
}

bool dCamera_c::onStyleChange(s32 i_style1, s32 i_style2) {
    m11C = 0;

#if VERSION > VERSION_JPN
    bool bVar1 = false;
#endif

    switch (mCamParam.Algorythmn(i_style1)) {
    case dCamAlg_FIXED_POSITION_CAMERA_e:
    case dCamAlg_FIXED_FRAME_CAMERA_e:
        if (mDMCSystem.field_0x0 == 0) {
            setDMCAngle();
        }
#if VERSION > VERSION_JPN
        bVar1 = true;
#endif
        break;
    case dCamAlg_SUBJECT_CAMERA_e:
        setComZoomScale(1.0f);
        clrComStat(dCamAttnStts_TELESCOPE_LOOK_e | dCamAttnStts_PICTO_BOX_AIM_e);
        break;
    }

    switch(mCamParam.Algorythmn(i_style2)) {
    case dCamAlg_FOLLOW_CAMERA_e:
    case dCamAlg_RIDE_CAMERA_e:
        if (mCamParam.Algorythmn(i_style1) == mCamParam.Algorythmn(i_style2)) {
            setFlag(0x8000);
        }
        break;
    case dCamAlg_FIXED_POSITION_CAMERA_e:
    case dCamAlg_FIXED_FRAME_CAMERA_e:
        if (
            mDMCSystem.field_0x0 == 0
#if VERSION > VERSION_JPN
            || bVar1
#endif
        ) {
            setDMCAngle();
        }
        // Fall-through
    case dCamAlg_SUBJECT_CAMERA_e:
    case dCamAlg_CRAWL_CAMERA_e:
    case dCamAlg_HOOKSHOT_CAMERA_e:
        if (m144 == 0) {
            m144 = 1;
        }
        break;
    }

    return TRUE;
}
