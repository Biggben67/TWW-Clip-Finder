// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_a_player_crawl.inc - getCrawlMoveVec, crawlBgCheck, setDoStatusCrawl, procCrawlStart
// and procCrawlEnd (d_a_player_crawl.inc:163-183, 185-208, 236-264, 266-284, 286-308,
// 674-716, 718-731).
// crawlBgCheck's rays go through getBaseTRMtx, which the boundary answers with an unwritten
// matrix, so the crawl does not move Link.


/* 80138D50-80138F28       .text getCrawlMoveVec__9daPy_lk_cFP4cXyzP4cXyzP4cXyz */
int daPy_lk_c::getCrawlMoveVec(cXyz* param_0, cXyz* param_1, cXyz* param_2) {
    mLinkLinChk.Set(param_0, param_1, this);
    if (dComIfG_Bgsp()->LineCross(&mLinkLinChk)) {
        cM3dGPla* triPla = dComIfG_Bgsp()->GetTriPla(mLinkLinChk);
        int iVar4 = dComIfG_Bgsp()->GetSpecialCode(mLinkLinChk);
        f32 temp = triPla->GetNP()->y;
        if (cBgW_CheckBWall(temp)) {
            cXyz local_3c = (*param_1 - mLinkLinChk.GetCross());
            f32 dVar7 = local_3c.absXZ();
            param_2->x = -dVar7 * triPla->GetNP()->x;
            param_2->y = local_3c.y;
            param_2->z = -dVar7 * triPla->GetNP()->z;
            return true;
        } else if (iVar4 == 1 || (temp < 0.643832f && iVar4 == 2)) {
            *param_2 = (*param_1 - mLinkLinChk.GetCross());
            return true;
        }
    }
    return false;
}

/* 80138F28-801390B8       .text crawlBgCheck__9daPy_lk_cFP4cXyzP4cXyz */
void daPy_lk_c::crawlBgCheck(cXyz* param_0, cXyz* param_1) {
    int iVar1;
    int iVar2;
    cXyz cStack_50;
    cXyz cStack_44;
    cXyz cStack_38;

    mDoMtx_multVec(mpCLModel->getBaseTRMtx(), &l_crawl_top_offset, &cStack_50);
    iVar1 = getCrawlMoveVec(&cStack_50, param_0, &cStack_44);
    mDoMtx_multVec(mpCLModel->getBaseTRMtx(), &l_crawl_top_up_offset, &cStack_50);
    iVar2 = getCrawlMoveVec(&cStack_50, param_1, &cStack_38);
    if (iVar1 != 0 && iVar2 != 0) {
        if (cStack_44.abs2() > cStack_38.abs()) {
            current.pos -= cStack_44;
        } else {
            current.pos -= cStack_38;
        }
    } else if (iVar1 != 0) {
        current.pos -= cStack_44;
    } else if (iVar2 != 0) {
        current.pos -= cStack_38;
    }
}

/* 801392BC-80139424       .text setDoStatusCrawl__9daPy_lk_cFv */
void daPy_lk_c::setDoStatusCrawl() {
    dComIfGp_setRStatus(dActStts_CROUCH_e);
    if (dComIfGp_checkCameraAttentionStatus(mCameraInfoIdx, dCamAttnStts_00000080_e)) {
        dComIfGp_setAStatus(dActStts_RETURN_e);
        if (checkSubjectEnd(TRUE) || mWaterY > current.pos.y) {
            dComIfGp_clearPlayerStatus0(0, daPyStts0_SUBJECT_e);
        } else {
            dComIfGp_setPlayerStatus0(0, daPyStts0_SUBJECT_e);
        }
    } else if (dCam_getBody()->ChangeModeOK(4)) {
        if (mWaterY <= current.pos.y) {
            onResetFlg0(daPyRFlg0_SUBJECT_ACCEPT);
            if (dComIfGp_checkCameraAttentionStatus(mCameraInfoIdx, dCamAttnStts_00001000_e) && !dComIfGp_event_runCheck()) {
                setSubjectMode();
            }
        }
    }
    if (dComIfGp_checkCameraAttentionStatus(mCameraInfoIdx, dCamAttnStts_00000080_e) &&
        (mCurProc != daPyProc_CRAWL_MOVE_e || mProcVar6.m3570 == 0))
    {
        setBodyAngleToCamera();
        if (mBodyAngle.x > 0) {
            mBodyAngle.x = 0;
        }
    } else {
        mBodyAngle.x = 0;
    }
}

/* 80139424-801394F0       .text procCrawlStart_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCrawlStart_init() {
    commonProcInit(daPyProc_CRAWL_START_e);
    m3700 = cXyz::Zero;
    m34C2 = 1;
    setSingleMoveAnime(
        ANM_LIE,
        m_HIO->mCrouch.m.field_0x20,
        m_HIO->mCrouch.m.field_0x24,
        m_HIO->mCrouch.m.field_0x6,
        m_HIO->mCrouch.m.field_0x2C
    );
    mNormalSpeed = 0.0f;
    current.angle.y = shape_angle.y;
    m35A0 = 1.0f / (m_HIO->mCrouch.m.field_0x28 - m_HIO->mCrouch.m.field_0x24);
    m35E4 = 0.0f;
    dComIfGp_setPlayerStatus0(0, daPyStts0_CRAWL_e);
    return true;
}

/* 801394F0-80139640       .text procCrawlStart__9daPy_lk_cFv */
BOOL daPy_lk_c::procCrawlStart() {
    setDoStatusCrawl();
    m35E4 = 1.0f - m35A0 * ((m_HIO->mCrouch.m.field_0x28) - mFrameCtrlUnder[UNDER_MOVE0_e].getFrame());
    cXyz local_20(l_crawl_front_offset.x, l_crawl_front_offset.y, l_crawl_front_offset.z * m35E4);
    cXyz afStack_2c;
    cXyz cStack_38;
    mDoMtx_multVec(mpCLModel->getBaseTRMtx(), &local_20, &afStack_2c);
    local_20.y = 50.0f;
    mDoMtx_multVec(mpCLModel->getBaseTRMtx(), &local_20, &cStack_38);
    crawlBgCheck(&cStack_38, &cStack_38);
    if (!spActionButton() || checkCrawlWaterIn()) {
        procCrawlEnd_init(0, shape_angle.x, shape_angle.z);
    } else if (mStickDistance > 0.05f &&
               ((mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) ||
                (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mCrouch.m.field_0x28)))
    {
        procCrawlMove_init(shape_angle.x, shape_angle.z);
    } else {
        m34C2 = 1;
    }
    return true;
}

/* 8013A630-8013A7C4       .text procCrawlEnd_init__9daPy_lk_cFiss */
BOOL daPy_lk_c::procCrawlEnd_init(int param_1, s16 param_2, s16 param_3) {
    f32 fVar1;
    J3DAnmTransform* pJVar2;
    f32 dVar4;
    J3DTransformInfo auStack_58;

    dVar4 = mFrameCtrlUnder[UNDER_MOVE0_e].getFrame();
    commonProcInit(daPyProc_CRAWL_END_e);
    current.angle.y = shape_angle.y;
    m34C2 = 1;
    if (param_1 != 0) {
        fVar1 = m_HIO->mCrouch.m.field_0x4C;
    } else {
        fVar1 = -1.0f;
    }
    setSingleMoveAnime(
        ANM_LIE,
        m_HIO->mCrouch.m.field_0x40,
        m_HIO->mCrouch.m.field_0x44,
        m_HIO->mCrouch.m.field_0xE,
        fVar1
    );
    if (param_1 == 0) {
        if (m_HIO->mCrouch.m.field_0x44 > dVar4) {
            dVar4 = m_HIO->mCrouch.m.field_0x44;
        } else if (m_HIO->mCrouch.m.field_0xE <= dVar4) {
            dVar4 = m_HIO->mCrouch.m.field_0xE - 0.001f;
        }
        mFrameCtrlUnder[UNDER_MOVE0_e].setFrame(dVar4);
        mAnmRatioUnder[UNDER_MOVE0_e].getAnmTransform()->setFrame(dVar4);
    }
    pJVar2 = mAnmRatioUnder[UNDER_MOVE0_e].getAnmTransform();
    pJVar2->getTransform(0, &auStack_58);
    m3700.x = auStack_58.mTranslate.x;
    m3700.y = auStack_58.mTranslate.y;
    m3700.z = auStack_58.mTranslate.z;
    mNormalSpeed = 0.0f;
    shape_angle.x = param_2;
    shape_angle.z = param_3;
    m35A0 = 1.0f / (m_HIO->mCrouch.m.field_0xE - m_HIO->mCrouch.m.field_0x48);
    return true;
}

/* 8013A7C4-8013A85C       .text procCrawlEnd__9daPy_lk_cFv */
BOOL daPy_lk_c::procCrawlEnd() {
    m35E4 = m35A0 * (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() - m_HIO->mCrouch.m.field_0x48);
    if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() > -0.01f) {
        checkNextMode(0);
    } else if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() < m_HIO->mCrouch.m.field_0x48) {
        if (!checkNextMode(1)) {
            m34C2 = 1;
        }
    } else {
        m34C2 = 1;
    }
    return true;
}
