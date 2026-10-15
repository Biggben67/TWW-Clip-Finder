// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_a_player_sword.inc - changeCutProc, the basic cuts and combo enders, the spin attack,
// the jump slash and their helpers (d_a_player_sword.inc:269-274, 284-295, 386-401,
// 403-467, 558-586, 588-658, 660-688, 690-760, 762-789, 791-861, 863-890, 892-960, 962-989,
// 991-1044, 1046-1073, 1075-1125, 1309-1447, 1449-1509, 1661-1674, 1676-1684, 1686-1722,
// 1724-1812, 1872-1913, 1916-1939, 1942-1992, 1995-2031).
// changeCutProc's procCutExA / ExB / ExMJ / Kesa arms (m34C4 >= 5) land on boundary stubs.


BOOL daPy_lk_c::checkChanceMode() {
    if (dComIfGp_getDoStatus() == dActStts_PARRY_e || checkModeFlg(ModeFlg_PARRY)) {
        return true;
    }
    return false;
}

/* 8015559C-801555FC       .text getSwordBlurColor__9daPy_lk_cFv */
int daPy_lk_c::getSwordBlurColor() {
    if (mEquipItem == daPyItem_SWORD_e) {
        if (checkChanceMode()) {
            return 2;
        }
        if (checkNoResetFlg1(daPyFlg1_SOUP_POWER_UP)) {
            return 1;
        }
    }
    return 0;
}

/* 80155970-801559F0       .text getCutDirection__9daPy_lk_cFv */
int daPy_lk_c::getCutDirection() {
    int direction;
    if (mStickDistance <= 0.05f) {
        direction = DIR_NONE;
    } else {
        s16 angle;
        if (mpAttnActorLockOn != NULL) {
            angle = m34E8 - fopAcM_searchActorAngleY(this, mpAttnActorLockOn);
        } else {
            angle = m34E8 - m34DE;
        }
        direction = getDirectionFromAngle(angle);
    }
    return direction + 1;
}

/* 801559F0-80155C3C       .text changeCutProc__9daPy_lk_cFv */
int daPy_lk_c::changeCutProc() {
    if (m34C5 == 5 && changeSpecialBattle()) {
        m34C4 = 0;
        return true;
    }
    m34C4++;
    int direction = getCutDirection() - 1;
    short sVar2;
    if (checkAttentionLock() || mStickDistance <= 0.05f) {
        sVar2 = shape_angle.y;
    } else {
        sVar2 = m34E8;
    }
    u32 bVar1 = m34C4;
    if (bVar1 > 4) {
        mCutCount = bVar1 - 2;
    } else {
        mCutCount = bVar1;
    }
    bVar1 = m34C4;

    if (bVar1 == 4) {
        if (direction == DIR_RIGHT || direction == DIR_FORWARD) {
            procCutEA_init();
        } else {
            procCutEB_init();
        }
    } else if (bVar1 < 4) {
        if (direction == DIR_FORWARD) {
            procCutF_init(sVar2);
        } else if (direction == DIR_RIGHT) {
            procCutR_init(sVar2);
        } else if (direction == DIR_NONE) {
            if (checkAttentionLock()) {
                procCutA_init(sVar2);
            } else {
                procCutL_init(sVar2);
            }
        } else {
            procCutL_init(sVar2);
        }
    } else if (bVar1 == 6) {
        if (direction == DIR_FORWARD) {
            procCutTurn_init(TRUE);
        } else if (direction == DIR_NONE) {
            procCutExB_init();
        } else if (direction == DIR_RIGHT) {
            procCutExMJ_init(1);
        } else {
            procCutExMJ_init(0);
        }
    } else if (bVar1 < 6) {
        if (direction == DIR_FORWARD) {
            procCutExMJ_init(1);
        } else if (direction == DIR_RIGHT) {
            procCutKesa_init();
        } else {
            procCutExA_init();
        }
    }

    m3578 = 0;
    return true;
}

/* 80156034-80156198       .text procCutA_init__9daPy_lk_cFs */
BOOL daPy_lk_c::procCutA_init(s16 param_0) {
    commonProcInit(daPyProc_CUT_A_e);
    setSingleMoveAnime(
        ANM_CUTA,
        m_HIO->mCut.mCutA.m.field_0x4,
        m_HIO->mCut.mCutA.m.field_0x8,
        m_HIO->mCut.mCutA.m.field_0x2,
        m_HIO->mCut.mCutA.m.field_0x24
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTAA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTAMS_e));
    }
    m35EC = m_HIO->mCut.mCutA.m.field_0x8;
    current.angle.y = shape_angle.y;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    voiceStart(0);
    mProcVar2.m34D4 = param_0;
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    m3522 = m_HIO->mCut.mCutA.m.field_0x0;
    m351E = m34DC;
    onNoResetFlg0(daPyFlg0_UNK4);
    setBlurPosResource(dRes_INDEX_LKANM__CUTA_POS_e);
    setNormalCutAtParam(CUT_TYPE_CUT_A);
    return true;
}

/* 80156198-80156424       .text procCutA__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutA() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    m3522 = m_HIO->mCut.mCutA.m.field_0x0;
    if (frameCtrl.getRate() < 0.01f) {
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        checkNextMode(0);
        return true;
    }

    if (frameCtrl.getFrame() > m_HIO->mCut.mCutA.m.field_0xC) {
        f32 dVar4 = mNormalSpeed;
        u8 orig_direction = mDirection;
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        if (checkNextMode(1)) {
            return true;
        }
        mNormalSpeed = dVar4;
        mDirection = orig_direction;
    }
    if (changeCutReverseProc(ANM_CUTRER)) {
        return true;
    }

    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (swordTrigger() && m34C5 != 5) {
        m34C5 = 1;
    }
    m34C2 = 1;
    if (mpAttnActorLockOn != NULL) {
        setShapeAngleToAtnActor();
        mProcVar2.m34D4 = shape_angle.y;
    } else {
        cLib_addCalcAngleS(
            &shape_angle.y,
            mProcVar2.m34D4,
            m_HIO->mTurn.m.field_0x4,
            m_HIO->mTurn.m.field_0x0,
            m_HIO->mTurn.m.field_0x2
        );
    }
    current.angle.y = shape_angle.y;
    if (frameCtrl.checkPass(m_HIO->mCut.mCutA.m.field_0x28)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutA.m.field_0x10 + m_HIO->mCut.mCutA.m.field_0x14;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutA.m.field_0x2C && frameCtrl.getFrame() < m_HIO->mCut.mCutA.m.field_0x30)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    cLib_addCalc(
        &mNormalSpeed, 0.0f, m_HIO->mCut.mCutA.m.field_0x20, m_HIO->mCut.mCutA.m.field_0x18, m_HIO->mCut.mCutA.m.field_0x1C
    );

    return true;
}

/* 80156424-80156584       .text procCutF_init__9daPy_lk_cFs */
BOOL daPy_lk_c::procCutF_init(s16 param_0) {
    commonProcInit(daPyProc_CUT_F_e);
    setSingleMoveAnime(
        ANM_CUTF,
        m_HIO->mCut.mCutF.m.field_0x4,
        m_HIO->mCut.mCutF.m.field_0x8,
        m_HIO->mCut.mCutF.m.field_0x2,
        m_HIO->mCut.mCutF.m.field_0x24
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTFA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTFMS_e));
    }
    m35EC = m_HIO->mCut.mCutF.m.field_0x8;
    mpCutfBpk->setFrame(m_HIO->mCut.mCutF.m.field_0x8);
    mpCutfBtk->setFrame(m_HIO->mCut.mCutF.m.field_0x8);
    m3700 = cXyz::Zero;
    m34C2 = 1;
    voiceStart(0);
    mProcVar2.m34D4 = param_0;
    m351E = m34DC;
    m3522 = m_HIO->mCut.mCutF.m.field_0x0;
    onNoResetFlg0(daPyFlg0_UNK4);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    setNormalCutAtParam(CUT_TYPE_CUT_F);
    return true;
}

/* 80156584-80156828       .text procCutF__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutF() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    mpCutfBpk->setFrame(frameCtrl.getFrame());
    mpCutfBtk->setFrame(frameCtrl.getFrame());
    m3522 = m_HIO->mCut.mCutF.m.field_0x0;
    if (frameCtrl.getRate() < 0.01f) {
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        checkNextMode(0);
        return true;
    }

    if (frameCtrl.getFrame() > m_HIO->mCut.mCutF.m.field_0xC) {
        f32 dVar4 = mNormalSpeed;
        u8 orig_direction = mDirection;
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        if (checkNextMode(1)) {
            return true;
        }
        mNormalSpeed = dVar4;
        mDirection = orig_direction;
    }
    if (changeCutReverseProc(ANM_CUTRER)) {
        return true;
    }
    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (swordTrigger() && m34C5 != 5) {
        m34C5 = 2;
    }
    m34C2 = 1;
    if (mpAttnActorLockOn != NULL) {
        setShapeAngleToAtnActor();
        mProcVar2.m34D4 = shape_angle.y;
    } else {
        cLib_addCalcAngleS(
            &shape_angle.y,
            mProcVar2.m34D4,
            m_HIO->mTurn.m.field_0x4,
            m_HIO->mTurn.m.field_0x0,
            m_HIO->mTurn.m.field_0x2
        );
    }
    current.angle.y = shape_angle.y;
    if (frameCtrl.checkPass(m_HIO->mCut.mCutF.m.field_0x28)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutF.m.field_0x10 + m_HIO->mCut.mCutF.m.field_0x14;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutF.m.field_0x2C && frameCtrl.getFrame() < m_HIO->mCut.mCutF.m.field_0x30)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    cLib_addCalc(
        &mNormalSpeed, 0.0f, m_HIO->mCut.mCutF.m.field_0x20, m_HIO->mCut.mCutF.m.field_0x18, m_HIO->mCut.mCutF.m.field_0x1C
    );
    return true;
}

/* 80156828-80156984       .text procCutR_init__9daPy_lk_cFs */
BOOL daPy_lk_c::procCutR_init(s16 param_0) {
    commonProcInit(daPyProc_CUT_R_e);
    setSingleMoveAnime(
        ANM_CUTR,
        m_HIO->mCut.mCutR.m.field_0x4,
        m_HIO->mCut.mCutR.m.field_0x8,
        m_HIO->mCut.mCutR.m.field_0x2,
        m_HIO->mCut.mCutR.m.field_0x24
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTRA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTRMS_e));
    }
    m35EC = m_HIO->mCut.mCutR.m.field_0x8;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    voiceStart(0);
    mProcVar2.m34D4 = param_0;
    m351E = m34DC;
    m3522 = m_HIO->mCut.mCutR.m.field_0x0;
    onNoResetFlg0(daPyFlg0_UNK4);
    setBlurPosResource(dRes_INDEX_LKANM__CUTR_POS_e);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    setNormalCutAtParam(CUT_TYPE_CUT_R);
    return true;
}

/* 80156984-80156C10       .text procCutR__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutR() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    m3522 = m_HIO->mCut.mCutR.m.field_0x0;
    if (frameCtrl.getRate() < 0.01f) {
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        checkNextMode(0);
        return true;
    }

    if (frameCtrl.getFrame() > m_HIO->mCut.mCutR.m.field_0xC) {
        f32 dVar4 = mNormalSpeed;
        u8 orig_direction = mDirection;
        mNormalSpeed = 0.0f;
        mDirection = DIR_RIGHT;
        if (checkNextMode(1)) {
            return true;
        }
        mNormalSpeed = dVar4;
        mDirection = orig_direction;
    }

    if (changeCutReverseProc(ANM_CUTRER)) {
        return true;
    }

    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (swordTrigger() && m34C5 != 5) {
        m34C5 = 3;
    }
    m34C2 = 1;
    if (mpAttnActorLockOn != NULL) {
        setShapeAngleToAtnActor();
        mProcVar2.m34D4 = shape_angle.y;
    } else {
        cLib_addCalcAngleS(
            &shape_angle.y,
            mProcVar2.m34D4,
            m_HIO->mTurn.m.field_0x4,
            m_HIO->mTurn.m.field_0x0,
            m_HIO->mTurn.m.field_0x2
        );
    }
    current.angle.y = shape_angle.y;
    if (frameCtrl.checkPass(m_HIO->mCut.mCutR.m.field_0x28)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutR.m.field_0x10 + m_HIO->mCut.mCutR.m.field_0x14;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutR.m.field_0x2C && frameCtrl.getFrame() < m_HIO->mCut.mCutR.m.field_0x30)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    cLib_addCalc(
        &mNormalSpeed, 0.0f, m_HIO->mCut.mCutR.m.field_0x20, m_HIO->mCut.mCutR.m.field_0x18, m_HIO->mCut.mCutR.m.field_0x1C
    );
    return true;
}

/* 80156C10-80156D6C       .text procCutL_init__9daPy_lk_cFs */
BOOL daPy_lk_c::procCutL_init(s16 param_0) {
    commonProcInit(daPyProc_CUT_L_e);
    setSingleMoveAnime(
        ANM_CUTL,
        m_HIO->mCut.mCutL.m.field_0x4,
        m_HIO->mCut.mCutL.m.field_0x8,
        m_HIO->mCut.mCutL.m.field_0x2,
        m_HIO->mCut.mCutL.m.field_0x24
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTLA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTLMS_e));
    }
    m35EC = m_HIO->mCut.mCutL.m.field_0x8;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    voiceStart(0);
    mProcVar2.m34D4 = param_0;
    m351E = m34DC;
    m3522 = m_HIO->mCut.mCutL.m.field_0x0;
    onNoResetFlg0(daPyFlg0_UNK4);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    setBlurPosResource(dRes_INDEX_LKANM__CUTL_POS_e);
    setNormalCutAtParam(CUT_TYPE_CUT_L);
    return true;
}

/* 80156D6C-80156FF8       .text procCutL__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutL() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    m3522 = m_HIO->mCut.mCutL.m.field_0x0;
    if (frameCtrl.getRate() < 0.01f) {
        mNormalSpeed = 0.0f;
        mDirection = DIR_LEFT;
        checkNextMode(0);
        return true;
    }

    if (frameCtrl.getFrame() > m_HIO->mCut.mCutL.m.field_0xC) {
        f32 dVar4 = mNormalSpeed;
        u8 orig_direction = mDirection;
        mNormalSpeed = 0.0f;
        mDirection = DIR_LEFT;
        if (checkNextMode(1)) {
            return true;
        }
        mNormalSpeed = dVar4;
        mDirection = orig_direction;
    }
    if (changeCutReverseProc(ANM_CUTREL)) {
        return true;
    }

    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }
    if (swordTrigger() && m34C5 != 5) {
        m34C5 = 4;
    }
    m34C2 = 1;
    if (mpAttnActorLockOn != NULL) {
        setShapeAngleToAtnActor();
        mProcVar2.m34D4 = shape_angle.y;
    } else {
        cLib_addCalcAngleS(
            &shape_angle.y,
            mProcVar2.m34D4,
            m_HIO->mTurn.m.field_0x4,
            m_HIO->mTurn.m.field_0x0,
            m_HIO->mTurn.m.field_0x2
        );
    }
    current.angle.y = shape_angle.y;
    if (frameCtrl.checkPass(m_HIO->mCut.mCutL.m.field_0x28)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutL.m.field_0x10 + m_HIO->mCut.mCutL.m.field_0x14;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutL.m.field_0x2C && frameCtrl.getFrame() < m_HIO->mCut.mCutL.m.field_0x30)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    cLib_addCalc(
        &mNormalSpeed, 0.0f, m_HIO->mCut.mCutL.m.field_0x20, m_HIO->mCut.mCutL.m.field_0x18, m_HIO->mCut.mCutL.m.field_0x1C
    );
    return true;
}

/* 80156FF8-80157154       .text procCutEA_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutEA_init() {
    commonProcInit(daPyProc_CUT_EA_e);
    setSingleMoveAnime(
        ANM_CUTEA,
        m_HIO->mCut.mCutEA.m.field_0x4,
        m_HIO->mCut.mCutEA.m.field_0x8,
        m_HIO->mCut.mCutEA.m.field_0x0,
        m_HIO->mCut.mCutEA.m.field_0x20
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTEAA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTEAMS_e));
    }
    m35EC = m_HIO->mCut.mCutEA.m.field_0x8;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    mProcVar0.m34D0 = m_HIO->mCut.mCutEA.m.field_0x2;
    onNoResetFlg0(daPyFlg0_UNK4);
    voiceStart(1);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    setBlurPosResource(dRes_INDEX_LKANM__CUTEA_POS_e);
    setFinishCutAtParam(CUT_TYPE_CUT_EA);
    m34C4 = 0;
    m3522 = 0;
    return true;
}

/* 80157154-80157348       .text procCutEA__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutEA() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    if (frameCtrl.getRate() < 0.01f) {
        if (mProcVar0.m34D0 > 0) {
            mProcVar0.m34D0--;
        } else {
            mNormalSpeed = 0.0f;
            mDirection = DIR_RIGHT;
            checkNextMode(0);
            return true;
        }
    }
    if (changeCutReverseProc(ANM_CUTREL)) {
        return true;
    }

    if (mpAttnActorLockOn != NULL) {
        setShapeAngleToAtnActor();
        current.angle.y = shape_angle.y;
    }
    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (frameCtrl.checkPass(m_HIO->mCut.mCutEA.m.field_0x24)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutEA.m.field_0xC + m_HIO->mCut.mCutEA.m.field_0x10;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutEA.m.field_0x28 &&
        frameCtrl.getFrame() < m_HIO->mCut.mCutEA.m.field_0x2C)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    m34C2 = 1;
    cLib_addCalc(
        &mNormalSpeed,
        0.0f,
        m_HIO->mCut.mCutEA.m.field_0x1C,
        m_HIO->mCut.mCutEA.m.field_0x14,
        m_HIO->mCut.mCutEA.m.field_0x18
    );
    return true;
}

/* 80157348-801574A4       .text procCutEB_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutEB_init() {
    commonProcInit(daPyProc_CUT_EB_e);
    setSingleMoveAnime(
        ANM_CUTEB,
        m_HIO->mCut.mCutEB.m.field_0x4,
        m_HIO->mCut.mCutEB.m.field_0x8,
        m_HIO->mCut.mCutEB.m.field_0x0,
        m_HIO->mCut.mCutEB.m.field_0x20
    );
    if (checkNormalSwordEquip()) {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTEBA_e));
    } else {
        mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTEBMS_e));
    }
    m35EC = m_HIO->mCut.mCutEB.m.field_0x8;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    mProcVar0.m34D0 = m_HIO->mCut.mCutEB.m.field_0x2;
    onNoResetFlg0(daPyFlg0_UNK4);
    voiceStart(1);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    setBlurPosResource(dRes_INDEX_LKANM__CUTEB_POS_e);
    setFinishCutAtParam(CUT_TYPE_CUT_EB);
    m34C4 = 0;
    m3522 = 0;
    return true;
}

/* 801574A4-8015768C       .text procCutEB__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutEB() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if (swordButton() && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }
    if (frameCtrl.getRate() < 0.01f) {
        if (mProcVar0.m34D0 > 0) {
            mProcVar0.m34D0--;
        } else {
            mNormalSpeed = 0.0f;
            mDirection = DIR_LEFT;
            checkNextMode(0);
            return true;
        }
    }
    if (changeCutReverseProc(ANM_CUTRER)) {
        return true;
    }
    setShapeAngleToAtnActor();
    current.angle.y = shape_angle.y;
    setSpecialBattle(TRUE);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (frameCtrl.checkPass(m_HIO->mCut.mCutEB.m.field_0x24)) {
        mNormalSpeed = std::fabs(speedF) * m_HIO->mCut.mCutEB.m.field_0xC + m_HIO->mCut.mCutEB.m.field_0x10;
    }
    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutEB.m.field_0x28 &&
        frameCtrl.getFrame() < m_HIO->mCut.mCutEB.m.field_0x2C)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
        }
        onResetFlg0(daPyRFlg0_UNK2);
    }
    m34C2 = 1;
    cLib_addCalc(
        &mNormalSpeed,
        0.0f,
        m_HIO->mCut.mCutEB.m.field_0x1C,
        m_HIO->mCut.mCutEB.m.field_0x14,
        m_HIO->mCut.mCutEB.m.field_0x18
    );
    return true;
}

/* 80157D3C-80158220       .text procCutTurn_init__9daPy_lk_cFi */
BOOL daPy_lk_c::procCutTurn_init(BOOL param_0) {
    float fVar1;

    commonProcInit(daPyProc_CUT_TURN_e);
    if (param_0) {
        fVar1 = m_HIO->mCut.mCutTurn.m.field_0xC;
    } else {
        fVar1 = m_HIO->mCut.mCutTurn.m.field_0x8;
    }
    if (mEquipItem == daPyItem_SWORD_e) {
        setSingleMoveAnime(
            ANM_CUTTURN,
            m_HIO->mCut.mCutTurn.m.field_0x4,
            fVar1,
            m_HIO->mCut.mCutTurn.m.field_0x0,
            m_HIO->mCut.mCutTurn.m.field_0x28
        );
    } else {
        setSingleMoveAnime(
            ANM_CUTTURNC,
            m_HIO->mCut.mCutTurn.m.field_0x4,
            fVar1,
            m_HIO->mCut.mCutTurn.m.field_0x0,
            m_HIO->mCut.mCutTurn.m.field_0x28
        );
    }
    if (mEquipItem == daPyItem_SWORD_e) {
        if (checkNormalSwordEquip()) {
            mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTTURNA_e));
        } else {
            mSwordAnim.changeBckOnly(getItemAnimeResource(dRes_INDEX_LKANM_BCK_CUTTURNMS_e));
        }
        if (checkNormalSwordEquip()) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x40;
#if VERSION == VERSION_DEMO
            mAtCyl.SetAtAtp(2);
#else
            if (checkNoResetFlg1(daPyFlg1_SOUP_POWER_UP)) {
                mAtCyl.SetAtAtp(4);
            } else {
                mAtCyl.SetAtAtp(2);
            }
#endif
        } else {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x44;
#if VERSION == VERSION_DEMO
            mAtCyl.SetAtAtp(4);
#else
            if (checkNoResetFlg1(daPyFlg1_SOUP_POWER_UP)) {
                mAtCyl.SetAtAtp(8);
            } else {
                mAtCyl.SetAtAtp(4);
            }
#endif
        }
        setBlurPosResource(dRes_INDEX_LKANM__CUTTURN_POS_e);
    } else {
        daBoko_c* boko = (daBoko_c*)mActorKeepEquip.getActor();
        u32 boko_type;
        if (boko == NULL) {
            boko_type = daBoko_c::Type_BOKO_STICK_e;
#if VERSION > VERSION_DEMO
            mAtCyl.SetAtAtp(1);
#endif
        } else {
            boko_type = fopAcM_GetParam(boko);
#if VERSION > VERSION_DEMO
            mAtCyl.SetAtAtp(boko->getAtPoint());
#endif
        }
        if (boko_type == daBoko_c::Type_BOKO_STICK_e) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x60;
        } else if (boko_type == daBoko_c::Type_MACHETE_e) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x64;
        } else if (boko_type == daBoko_c::Type_STALFOS_MACE_e) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x68;
        } else if (boko_type == daBoko_c::Type_DARKNUT_SWORD_e) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x6C;
        } else if (boko_type == daBoko_c::Type_MOBLIN_SPEAR_e) {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x70;
        } else {
            m35A4 = m_HIO->mCut.mCutTurn.m.field_0x74;
        }
        setBlurPosResource(dRes_INDEX_LKANM__WEAPONTURN_POS_e);
    }
    mAtCyl.SetR(m35A4 * 0.5f);
    m35EC = fVar1;
    m3700 = cXyz::Zero;
    m34C2 = 1;
    mProcVar0.m34D0 = m_HIO->mCut.mCutTurn.m.field_0x2;
    current.angle.y = shape_angle.y;
    m3578 = 0;
    voiceStart(1);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    mCutType = CUT_TYPE_CUT_TURN;
    offResetFlg0(daPyRFlg0_NOT_ATTACKING);
    mAtCyl.SetR(m35A4 * 0.5f);
    if (!checkNoResetFlg0(daPyFlg0_UNK80000000)) {
        m32E4.makeEmitter(dPa_name::ID_AK_JN_ROUNDATTACKTOE, mpCLModel->getAnmMtx(CL_JNT_RTOE_JNT_e), &current.pos, NULL);
        if (mCurrAttributeCode == dBgS_Attr_GRASS_e) {
            GXColor color = {tevStr.mColorC0.r, tevStr.mColorC0.g, tevStr.mColorC0.b, tevStr.mColorC0.a};
            m32F0.makeEmitterColor(
                dPa_name::ID_AK_JN_ROUNDATTACKKUSA, mpCLModel->getAnmMtx(CL_JNT_LTOE_JNT_e), &current.pos, &color, &tevStr.mColorK0
            );
            m35A0 = 18.0f;
        } else if (mCurrAttributeCode == dBgS_Attr_WATER_e) {
            GXColor amb, dif;
            dKy_get_seacolor(&amb, &dif);
            m32F0.makeEmitterColor(dPa_name::ID_AK_JN_ROUNDATTACKSHIBUKI, mpCLModel->getAnmMtx(CL_JNT_LTOE_JNT_e), &current.pos, &amb, NULL);
            m35A0 = 17.0f;
        } else {
            dComIfGp_particle_setToonP1(
                dPa_name::ID_AK_JT_ROUNDATTACKSMOKE,
                &current.pos,
                NULL,
                NULL,
                m_HIO->mBasic.m.field_0x2,
                &mSmokeEcallBack,
                -1,
                NULL,
                NULL,
                NULL
            );
            m35A0 = 21.0f;
        }
    }
    mProcVar6.m3570 = 0;
    if (m34C4 == 6) {
        onNoResetFlg0(daPyFlg0_UNK4);
        mProcVar6.m3570 = 1;
    } else {
        mCutCount = 0;
    }
    mNormalSpeed = 0.0f;
    m34C4 = 0;
    endFlameDamageEmitter();
    return true;
}

/* 80158220-80158460       .text procCutTurn__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutTurn() {
    J3DFrameCtrl& frameCtrl = mFrameCtrlUnder[UNDER_MOVE0_e];
    m35EC = frameCtrl.getFrame();
    if ((mProcVar6.m3570 != 0 && swordButton()) && m34C5 == 0) {
        onNoResetFlg0(daPyFlg0_UNK4);
    } else {
        offNoResetFlg0(daPyFlg0_UNK4);
    }

    if (frameCtrl.getRate() < 0.01f) {
        if (mProcVar0.m34D0 > 0) {
            mProcVar0.m34D0--;
        } else {
            mDirection = DIR_RIGHT;
            checkNextMode(0);
            return true;
        }
    } else if (frameCtrl.getFrame() > m_HIO->mCut.mCutTurn.m.field_0x10) {
        u8 orig_direction = mDirection;
        mDirection = DIR_RIGHT;
        if (checkNextMode(1)) {
            return true;
        }
        mDirection = orig_direction;
    } else if (frameCtrl.getFrame() > 17.0f) {
        m32E4.end();
    }

    if (frameCtrl.getFrame() > m35A0) {
        m32F0.end();
        mSmokeEcallBack.remove();
    }
    setSpecialBattle(1);
    if (doTrigger() && dComIfGp_getDoStatus() == dActStts_PARRY_e) {
        return changeSpecialBattle();
    }

    if (frameCtrl.getFrame() >= m_HIO->mCut.mCutTurn.m.field_0x30 &&
        frameCtrl.getFrame() < m_HIO->mCut.mCutTurn.m.field_0x34)
    {
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            onResetFlg0(daPyRFlg0_UNK1);
            seStartSwordCut(JA_SE_LK_KAITENGIRI);
        }
        onResetFlg0(daPyRFlg0_UNK2);
        cLib_chaseF(mAtCyl.GetRP(), m35A4, 18.0f);
    }

    if (frameCtrl.checkPass(m_HIO->mCut.mCutTurn.m.field_0x34)) {
        m331C.setAlpha(0x80);
        m332C.setAlpha(0x80);
        m333C.setAlpha(0x80);
    } else if (m331C.getAlpha() == 0x80) {
        m331C.setAlpha(0x00);
        m332C.setAlpha(0x00);
        m333C.setAlpha(0x00);
    }
    m34C2 = 1;
    return true;
}

/* 80158A98-80158B00       .text procCutTurnCharge_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutTurnCharge_init() {
    commonProcInit(daPyProc_CUT_TURN_CHARGE_e);
    setSingleMoveAnime(
        ANM_CUTTURNP,
        m_HIO->mCut.mCutTurnR.m.field_0xC,
        m_HIO->mCut.mCutTurnR.m.field_0x10,
        m_HIO->mCut.mCutTurnR.m.field_0x4,
        m_HIO->mCut.mCutTurnR.m.field_0x14
    );
    mNormalSpeed = 0.0f;
    current.angle.y = shape_angle.y;
    return true;
}

/* 80158B00-80158B58       .text procCutTurnCharge__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutTurnCharge() {
    if (!swordButton() || daPy_dmEcallBack_c::checkCurse()) {
        checkNextMode(0);
    } else if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        procCutTurnMove_init();
    }
    return true;
}

/* 80158B58-80158D40       .text procCutTurnMove_init__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutTurnMove_init() {
    static Vec eff_scale = {1.5f, 1.5f, 1.5f};
    BOOL bVar1;
    cXyz* pcVar4;

    commonProcInit(daPyProc_CUT_TURN_MOVE_e);
    setSingleMoveAnime(ANM_CUTTURNPWFB, 0.0f, 0.0f, -1, m_HIO->mCut.mCutTurnR.m.field_0x1C);
    if (mEquipItem == daPyItem_BOKO_e && (mAnmRatioUpper[UPPER_MOVE0_e].getAnmTransform() != NULL)) {
        mFrameCtrlUpper[UPPER_MOVE0_e].setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getEnd() - 0.001f);
        mAnmRatioUpper[UPPER_MOVE0_e].getAnmTransform()->setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getFrame());
    }
    m3598 = 1.0f;
    mDirection = DIR_FORWARD;

    if (dComIfGs_isEventBit(dSv_event_flag_c::UNK_0B20)) {
        bVar1 = true;
    } else if (dComIfGs_isTmpBit(dSv_event_tmp_flag_c::UNK_0402)) {
        bVar1 = true;
    } else {
        bVar1 = false;
    }

    if (bVar1 && mEquipItem == daPyItem_SWORD_e && dComIfGs_getMagic() >= 2 && !checkSwordMiniGame() &&
        dComIfGp_getMiniGameType() != 6)
    {
        pcVar4 = checkNormalSwordEquip() ? NULL : (cXyz*)&eff_scale;
        m32E4.makeEmitter(dPa_name::ID_AK_JN_CHARGEPOWER00, mpCLModel->getAnmMtx(CL_JNT_CL_LHANDA_e), &current.pos, pcVar4);
        m32F0.makeEmitter(dPa_name::ID_AK_JN_CHARGEPOWER01, mpCLModel->getAnmMtx(CL_JNT_CL_LHANDA_e), &current.pos, pcVar4);
        mProcVar0.m34D0 = 47;
    } else {
        mProcVar0.m34D0 = -1;
    }

    dComIfGp_setPlayerStatus0(0, daPyStts0_SPIN_ATTACK_e);
    return true;
}

/* 80158D40-80159130       .text procCutTurnMove__9daPy_lk_cFv */
BOOL daPy_lk_c::procCutTurnMove() {
    setShapeAngleToAtnActor();
    m34E6 = shape_angle.y;
    if (0 < mProcVar0.m34D0) {
        mProcVar0.m34D0--;
        if (mProcVar0.m34D0 == 0) {
            dComIfGp_setPlayerStatus1(0, daPyStts1_UNK20000_e);
        }
    }
    if (mProcVar0.m34D0 != -1) {
        seStartSystem(JA_SE_LK_SWORD_CHARGE);
    }
    if (changeSlideProc()) {
        return true;
    }

    if (daPy_dmEcallBack_c::checkCurse()) {
        checkNextMode(0);
    } else if (swordButton()) {
        f32 dVar8 = 0.0f;
        if (mStickDistance > 0.05f) {
            int direction = getDirectionFromAngle(m34E8 - m34E6);
            daPy_ANM dVar6 = (daPy_ANM)0xffff;
            cLib_addCalcAngleS(&current.angle.y, m34E8, 4, 12000, 0x2000);
            f32 in_f30;
            if (mDirection == DIR_FORWARD || mDirection == DIR_BACKWARD) {
                if (direction == DIR_LEFT || direction == DIR_RIGHT) {
                    dVar6 = ANM_CUTTURNPWLR;
                    in_f30 = m_HIO->mCut.mCutTurnR.m.field_0x24;
                    mNormalSpeed *= 0.5f;
                } else if (mDirection != direction) {
                    mNormalSpeed *= 0.5f;
                }
            } else if (direction == DIR_FORWARD || direction == DIR_BACKWARD) {
                dVar6 = ANM_CUTTURNPWFB;
                in_f30 = m_HIO->mCut.mCutTurnR.m.field_0x1C;
                mNormalSpeed *= 0.5f;
            } else if (mDirection != direction) {
                mNormalSpeed *= 0.5f;
            }
            if (mDirection == direction) {
                dVar8 = m_HIO->mMove.m.field_0x14 * mStickDistance;
            } else {
                mDirection = direction;
            }
            if (dVar6 != (daPy_ANM)0xffff) {
                setSingleMoveAnime(dVar6, 0.0f, 0.0f, -1, in_f30);
            }
        }
        setNormalSpeedF(dVar8, 0.5f, 2.0f, 0.25f);
        if (mDirection == DIR_FORWARD) {
            dVar8 = m_HIO->mCut.mCutTurnR.m.field_0x18;
        } else if (mDirection == DIR_BACKWARD) {
            dVar8 = -m_HIO->mCut.mCutTurnR.m.field_0x18;
        } else if (mDirection == DIR_RIGHT) {
            dVar8 = -m_HIO->mCut.mCutTurnR.m.field_0x20;
        } else { // DIR_LEFT
            dVar8 = m_HIO->mCut.mCutTurnR.m.field_0x20;
        }
        f32 dVar7 = mNormalSpeed / mMaxNormalSpeed;
        mFrameCtrlUnder[UNDER_MOVE0_e].setRate(dVar7 * dVar8);
        if (dVar8 >= 0.0f) {
            mFrameCtrlUnder[UNDER_MOVE0_e].setLoop(mFrameCtrlUnder[UNDER_MOVE0_e].getStart());
        } else {
            mFrameCtrlUnder[UNDER_MOVE0_e].setLoop(mFrameCtrlUnder[UNDER_MOVE0_e].getEnd());
        }
        initSeAnime();
        m3598 = 1.0f - ((1.0f - m_HIO->mCut.mCutTurnR.m.field_0x28) * dVar7);
        if (mNormalSpeed <= 0.001f) {
            onModeFlg(ModeFlg_00000001);
            m3598 = 0.0f;
        } else {
            offModeFlg(ModeFlg_00000001);
            m3598 = 1.0f;
        }
        if (mEquipItem == daPyItem_BOKO_e && (mAnmRatioUpper[UPPER_MOVE0_e].getAnmTransform() != NULL)) {
            mFrameCtrlUpper[UPPER_MOVE0_e].setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getEnd() - 0.001f);
            mAnmRatioUpper[UPPER_MOVE0_e].getAnmTransform()->setFrame(mFrameCtrlUpper[UPPER_MOVE0_e].getFrame());
        }
    } else if (mProcVar0.m34D0 == 0) {
        procCutRoll_init();
    } else {
        mNormalSpeed = speedF;
        procCutTurn_init(FALSE);
    }

    return true;
}

BOOL daPy_lk_c::procJumpCut_init(int param_0) {
    fopAc_ac_c* equip_actor = mActorKeepEquip.getActor();
    if (daPy_dmEcallBack_c::checkCurse() || (mEquipItem == daPyItem_BOKO_e && equip_actor == NULL)) {
        return false;
    }

    commonProcInit(daPyProc_JUMP_CUT_e);
    if (param_0 != 0) {
        setSingleMoveAnime(
            ANM_JATTACK,
            m_HIO->mCut.mCutJump.m.field_0x20,
            m_HIO->mCut.mCutJump.m.field_0x24,
            m_HIO->mCut.mCutJump.m.field_0x6,
            m_HIO->mCut.mCutJump.m.field_0x28
        );
        mNormalSpeed = m_HIO->mCut.mCutJump.m.field_0x2C;
        speed.y = m_HIO->mCut.mCutJump.m.field_0x30;
        gravity = m_HIO->mCut.mCutJump.m.field_0x34;
    } else {
        setSingleMoveAnime(
            ANM_JATTACK,
            m_HIO->mCut.mCutJump.m.field_0x8,
            m_HIO->mCut.mCutJump.m.field_0xC,
            m_HIO->mCut.mCutJump.m.field_0x0,
            m_HIO->mCut.mCutJump.m.field_0x10
        );
        mNormalSpeed = m_HIO->mCut.mCutJump.m.field_0x14;
        speed.y = m_HIO->mCut.mCutJump.m.field_0x18;
        gravity = m_HIO->mCut.mCutJump.m.field_0x1C;
    }
    current.angle.y = shape_angle.y;
    mProcVar6.m3570 = 0;
    voiceStart(1);
    dComIfGp_setPlayerStatus0(0, daPyStts0_SWORD_SWING_e);
    if (mEquipItem == daPyItem_BOKO_e) {
        setBlurPosResource(dRes_INDEX_LKANM__WEAPONJUMP_POS_e);
    } else {
        setBlurPosResource(dRes_INDEX_LKANM__CUTJUMP_POS_e);
    }
    setJumpCutAtParam();
    return true;
}

BOOL daPy_lk_c::procJumpCut() {
    if (mAcch.ChkGroundHit()) {
        return procJumpCutLand_init();
    }

    if (current.angle.y == shape_angle.y && changeCutReverseProc(ANM_JATTACK)) {
        current.angle.y = current.angle.y + 0x8000;
        mNormalSpeed = 27.0f;
    } else if (current.angle.y != shape_angle.y) {
        cLib_addCalc(&mNormalSpeed, 5.0f, 0.2f, 1.0f, 0.1f);
    }
    if ((mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() >= m_HIO->mCut.mCutJump.m.field_0x48) &&
        (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() < m_HIO->mCut.mCutJump.m.field_0x4C))
    {
        if (mEquipItem != daPyItem_NONE_e) {
            if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
                onResetFlg0(daPyRFlg0_UNK1);
                seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
            }
            onResetFlg0(daPyRFlg0_UNK2);
        }
    }
    return true;
}

BOOL daPy_lk_c::procJumpCutLand_init() {
    f32 dVar3 = m35F0 - current.pos.y;
    commonProcInit(daPyProc_JUMP_CUT_LAND_e);
    if (!dComIfGp_event_runCheck()) {
        if (dVar3 >= (100.0f * m_HIO->mFall.m.field_0x10)) {
            setDamagePoint(-2.0f);
        } else if (dVar3 >= (100.0f * m_HIO->mFall.m.field_0x14)) {
            setDamagePoint(-1.0f);
        }
        if (dVar3 >= (100.0f * m_HIO->mFall.m.field_0x14)) {
            mDamageWaitTimer = m_HIO->mDam.m.field_0x0;
            onModeFlg(ModeFlg_DAMAGE);
        }
    }
    mNormalSpeed = 0.0f;
    setSingleMoveAnime(
        ANM_JATTACKLAND,
        m_HIO->mCut.mCutJump.m.field_0x38,
        m_HIO->mCut.mCutJump.m.field_0x3C,
        m_HIO->mCut.mCutJump.m.field_0x2,
        m_HIO->mCut.mCutJump.m.field_0x40
    );
    if (mEquipItem == daPyItem_NONE_e) {
        mProcVar6.m3570 = 0;
    } else {
        onResetFlg0(daPyRFlg0_UNK2);
        if (!checkNoResetFlg0(daPyFlg0_CUT_AT_FLG)) {
            seStartSwordCut(JA_SE_LK_SW_KAZEKIRI_S);
            mSwBlur.initSwBlur(
                mpCLModel->getBaseTRMtx(),
                (10.0f * m_HIO->mCut.mCutJump.m.field_0x48),
                getBlurTopRate(),
                getSwordBlurColor()
            );
            onNoResetFlg0(daPyFlg0_CUT_AT_FLG);
        }
        setJumpCutAtParam();
        mProcVar6.m3570 = 1;
    }
    mProcVar0.m34D0 = m_HIO->mCut.mCutJump.m.field_0x4;
    current.angle.y = shape_angle.y + 0x8000;
    setFootEffectPosType(3);
    onResetFlg0(daPyRFlg0_RIGHT_FOOT_ON_GROUND);
    onResetFlg0(daPyRFlg0_LEFT_FOOT_ON_GROUND);
    if (mEquipItem == dItemNo_SKULL_HAMMER_e) {
        setHammerQuake(NULL, NULL, -1);
    } else if (checkHeavyStateOn()) {
        dComIfGp_getVibration().StartShock(5, -0x31, cXyz(0.0f, 1.0f, 0.0f));
    }
    return true;
}

BOOL daPy_lk_c::procJumpCutLand() {
    current.angle.y = shape_angle.y;
    resetFootEffect();
    if (mProcVar6.m3570 != 0 && changeCutReverseProc(ANM_CUTRER)) {
        return true;
    }

    if (mFrameCtrlUnder[UNDER_MOVE0_e].getRate() < 0.01f) {
        if (mProcVar0.m34D0 > 0) {
            mProcVar0.m34D0--;
            checkNextMode(1);
        } else {
            checkNextMode(0);
        }
    } else if (mFrameCtrlUnder[UNDER_MOVE0_e].getFrame() > m_HIO->mCut.mCutJump.m.field_0x44) {
        checkNextMode(1);
    } else if (mProcVar6.m3570 != 0) {
        mProcVar6.m3570 = 0;
        if (
            abs(m3578) > 0xf800 &&
#if VERSION > VERSION_DEMO
            !daPy_dmEcallBack_c::checkCurse() &&
#endif
            (
                mEquipItem == daPyItem_SWORD_e
#if VERSION > VERSION_DEMO
                || mEquipItem == daPyItem_BOKO_e
#endif
            )
        ) {
            procCutTurn_init(TRUE);
        } else {
            onResetFlg0(daPyRFlg0_UNK2);
        }
    }
    return true;
}
