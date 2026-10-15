// Generated from the zeldaret/tww decomp. Do not hand-edit.
// c_m3d.cpp - the module constants and the triangle, cylinder, plane and line tests the
// collision walks use (c_m3d.cpp:22-25, 33-37, 40-44, 46-66, 105-123, 150-167, 249-268,
// 270-295, 297-336, 338-365, 368-532, 587-631, 706-775, 788-857, 859-929, 931-975,
// 1150-1219, 1232-1244).
// BEVEL3D_OUTCODE5 and OUTCODE6 test the same expression; so does the DOL.

#include "SSystem/SComponent/c_m3d.h"

#include "SSystem/SComponent/c_m3d_g_aab.h"
#include "SSystem/SComponent/c_m3d_g_cyl.h"
#include "SSystem/SComponent/c_m3d_g_lin.h"
#include "SSystem/SComponent/c_m3d_g_pla.h"
#include "SSystem/SComponent/c_m3d_g_tri.h"

const f32 G_CM3D_F_ABS_MIN = 3.8146973e-06f;
#if VERSION == VERSION_DEMO
const f32 G_CM3D_F_INF = 1.0e38f;
#endif

void cM3d_InDivPos1(const Vec* v0, const Vec* v1, f32 scale, Vec* pDst) {
    Vec tmp;
    VECScale(v1, &tmp, scale);
    VECAdd(&tmp, v0, pDst);
}

void cM3d_InDivPos2(const Vec* v0, const Vec* v1, f32 scale, Vec* pDst) {
    Vec tmp;
    VECSubtract(v1, v0, &tmp);
    cM3d_InDivPos1(v0, &tmp, scale, pDst);
}

/* 8024A4B4-8024A56C       .text cM3d_Len2dSqPntAndSegLine__FffffffPfPfPf */
bool cM3d_Len2dSqPntAndSegLine(f32 xp, f32 yp, f32 x0, f32 y0, f32 x1, f32 y1, f32* outx, f32* outy, f32* seg) {
    bool ret = false;
    f32 xd = x1 - x0;
    f32 yd = y1 - y0;
    f32 dot = (xd * xd + yd * yd);
    if (cM3d_IsZero(dot)) {
        *seg = 0.0f;
        return false;
    }

    f32 mag = (xd * (xp - x0) + yd * (yp - y0)) / dot;
    if (mag >= 0.0f && mag <= 1.0f) {
        ret = true;
    }

    *outx = x0 + xd * mag;
    *outy = y0 + yd * mag;
    *seg = cM3d_Len2dSq(*outx, *outy, xp, yp);
    return ret;
}

/* 8024A6F0-8024A7BC       .text cM3d_CalcPla__FPC3VecPC3VecPC3VecP3VecPf */
void cM3d_CalcPla(const Vec* p0, const Vec* p1, const Vec* p2, Vec* pDst, f32* pT) {
    cM3d_VectorProduct(p0, p1, p2, pDst);
    f32 t = VECMag(pDst);
#if VERSION == VERSION_DEMO
    if (!cM3d_IsZero(t))
#else
    if (std::fabs(t) >= 0.02f)
#endif
    {
        VECScale(pDst, pDst, 1.0f / t);
        *pT = -VECDotProduct(pDst, p0);
    } else {
        pDst->y = 0.0f;
        *pT = 0.0f;
        pDst->z = 0.0f;
        pDst->x = 0.0f;
    }
}

/* 8024A8E0-8024A988       .text cM3d_Cross_AabCyl__FPC8cM3dGAabPC8cM3dGCyl */
bool cM3d_Cross_AabCyl(const cM3dGAab* aab, const cM3dGCyl* cyl) {
    if (aab->GetMinP()->x > cyl->GetCP()->x + cyl->GetR()) {
        return false;
    } else if (aab->GetMaxP()->x < cyl->GetCP()->x - cyl->GetR()) {
        return false;
    } else if (aab->GetMinP()->z > cyl->GetCP()->z + cyl->GetR()) {
        return false;
    } else if (aab->GetMaxP()->z < cyl->GetCP()->z - cyl->GetR()) {
        return false;
    } else if (aab->GetMinP()->y > cyl->GetCP()->y + cyl->GetH()) {
        return false;
    } else if (aab->GetMaxP()->y < cyl->GetCP()->y) {
        return false;
    } else {
        return true;
    }
}

bool cM3d_Cross_LinPla(const cM3dGLin* lin, const cM3dGPla* pla, Vec* dst, bool a, bool b) {
    f32 startVal = pla->getPlaneFunc(lin->GetStartP());
    f32 endVal = pla->getPlaneFunc(lin->GetEndP());
    if (startVal * endVal > 0.0f) {
        *dst = lin->GetEnd();
        return false;
    } else {
        if (startVal >= 0.0f && endVal <= 0.0f) {
            if (a) {
                return cM3d_CrossInfLineVsInfPlane_proc(startVal, endVal, lin->GetStartP(), lin->GetEndP(), dst);
            }
        } else {
            if (b) {
                return cM3d_CrossInfLineVsInfPlane_proc(startVal, endVal, lin->GetStartP(), lin->GetEndP(), dst);
            }
        }
        *dst = lin->GetEnd();
        return false;
    }
}

const u32 BPCP_OUTCODE0 = 0x00000001;
const u32 BPCP_OUTCODE1 = 0x00000002;
const u32 BPCP_OUTCODE4 = 0x00000010;
const u32 BPCP_OUTCODE5 = 0x00000020;
const u32 BPCP_OUTCODE2 = 0x00000004;
const u32 BPCP_OUTCODE3 = 0x00000008;
const u32 BEVEL2D_OUTCODE0 = 0x00000001;
const u32 BEVEL2D_OUTCODE1 = 0x00000002;
const u32 BEVEL2D_OUTCODE2 = 0x00000004;
const u32 BEVEL2D_OUTCODE3 = 0x00000008;
const u32 BEVEL2D_OUTCODE4 = 0x00000010;
const u32 BEVEL2D_OUTCODE5 = 0x00000020;
const u32 BEVEL2D_OUTCODE6 = 0x00000040;
const u32 BEVEL2D_OUTCODE7 = 0x00000080;
const u32 BEVEL2D_OUTCODE8 = 0x00000100;
const u32 BEVEL2D_OUTCODE9 = 0x00000200;
const u32 BEVEL2D_OUTCODE10 = 0x00000400;
const u32 BEVEL2D_OUTCODE11 = 0x00000800;
const u32 BEVEL3D_OUTCODE0 = 0x00000001;
const u32 BEVEL3D_OUTCODE1 = 0x00000002;
const u32 BEVEL3D_OUTCODE2 = 0x00000004;
const u32 BEVEL3D_OUTCODE3 = 0x00000008;
const u32 BEVEL3D_OUTCODE4 = 0x00000010;
const u32 BEVEL3D_OUTCODE5 = 0x00000020;
const u32 BEVEL3D_OUTCODE6 = 0x00000040;
const u32 BEVEL3D_OUTCODE7 = 0x00000080;

inline u32 cM3d_CheckBoxEdgePlane_Bevel2DCheck(const Vec* param_0, const Vec* param_1, const Vec* param_2) {
    u32 ret = 0;
    if (-param_0->x + param_0->y > -param_1->x + param_2->y) {
        ret |= BEVEL2D_OUTCODE0;
    }
    if (-param_0->x + param_0->y < -param_2->x + param_1->y) {
        ret |= BEVEL2D_OUTCODE1;
    }
    if (param_0->x + param_0->y > param_2->x + param_2->y) {
        ret |= BEVEL2D_OUTCODE2;
    }
    if (param_0->x + param_0->y < param_1->x + param_1->y) {
        ret |= BEVEL2D_OUTCODE3;
    }
    if (-param_0->z + param_0->y > -param_1->z + param_2->y) {
        ret |= BEVEL2D_OUTCODE4;
    }
    if (-param_0->z + param_0->y < -param_2->z + param_1->y) {
        ret |= BEVEL2D_OUTCODE5;
    }
    if (param_0->z + param_0->y > param_2->z + param_2->y) {
        ret |= BEVEL2D_OUTCODE6;
    }
    if (param_0->z + param_0->y < param_1->z + param_1->y) {
        ret |= BEVEL2D_OUTCODE7;
    }
    if (-param_0->z + param_0->x > -param_1->z + param_2->x) {
        ret |= BEVEL2D_OUTCODE8;
    }
    if (-param_0->z + param_0->x < -param_2->z + param_1->x) {
        ret |= BEVEL2D_OUTCODE9;
    }
    if (param_0->z + param_0->x > param_2->z + param_2->x) {
        ret |= BEVEL2D_OUTCODE10;
    }
    if (param_0->z + param_0->x < param_1->z + param_1->x) {
        ret |= BEVEL2D_OUTCODE11;
    }
    return ret;
}

inline u32 cM3d_CheckBoxEdgePlane_Bevel3DCheck(const Vec* param_0, const Vec* param_1, const Vec* param_2) {
    u32 ret = 0;
    if (param_0->x + param_0->y + param_0->z > param_2->x + param_2->y + param_2->z) {
        ret |= BEVEL3D_OUTCODE0;
    }
    if (-param_0->x + param_0->y + param_0->z > -param_1->x + param_2->y + param_2->z) {
        ret |= BEVEL3D_OUTCODE1;
    }
    if (-param_0->x + param_0->y - param_0->z > -param_1->x + param_2->y - param_1->z) {
        ret |= BEVEL3D_OUTCODE2;
    }
    if (param_0->x + param_0->y - param_0->z > param_2->x + param_2->y - param_1->z) {
        ret |= BEVEL3D_OUTCODE3;
    }
    if (param_0->x - param_0->y + param_0->z > param_2->x - param_1->y + param_2->z) {
        ret |= BEVEL3D_OUTCODE4;
    }
    if (-param_0->x - param_0->y + param_0->z > -param_1->x - param_1->y + param_2->z) {
        ret |= BEVEL3D_OUTCODE5;
    }
    if (-param_0->x - param_0->y + param_0->z > -param_1->x - param_1->y + param_2->z) {
        ret |= BEVEL3D_OUTCODE6;
    }
    if (-param_0->x - param_0->y - param_0->z > -param_1->x - param_1->y - param_1->z) {
        ret |= BEVEL3D_OUTCODE7;
    }
    return ret;
}

bool cM3d_Cross_MinMaxBoxLine(const Vec* param_0, const Vec* param_1, const Vec* param_2, const Vec* param_3) {
    u32 uVar3 = 0;
    u32 uVar4 = 0;

    if (param_2->x > param_1->x) {
        if (param_3->x > param_1->x) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE0;
    } else if (param_3->x > param_1->x) {
        uVar4 |= BPCP_OUTCODE0;
    }

    if ((uVar3 & BPCP_OUTCODE0) == 0 && param_2->x < param_0->x) {
        if ((uVar4 & BPCP_OUTCODE0) == 0 && param_3->x < param_0->x) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE1;
    } else if ((uVar4 & BPCP_OUTCODE0) == 0 && param_3->x < param_0->x) {
        uVar4 |= BPCP_OUTCODE1;
    }

    if (param_2->z > param_1->z) {
        if (param_3->z > param_1->z) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE4;
    } else if (param_3->z > param_1->z) {
        uVar4 |= BPCP_OUTCODE4;
    }

    if ((uVar3 & BPCP_OUTCODE4) == 0 && param_2->z < param_0->z) {
        if ((uVar4 & BPCP_OUTCODE4) == 0 && param_3->z < param_0->z) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE5;
    } else if ((uVar4 & BPCP_OUTCODE4) == 0 && param_3->z < param_0->z) {
        uVar4 |= BPCP_OUTCODE5;
    }

    if (param_2->y > param_1->y) {
        if (param_3->y > param_1->y) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE2;
    } else if (param_3->y > param_1->y) {
        uVar4 |= BPCP_OUTCODE2;
    }

    if ((uVar3 & BPCP_OUTCODE2) == 0 && param_2->y < param_0->y) {
        if ((uVar4 & BPCP_OUTCODE2) == 0 && param_3->y < param_0->y) {
            return false;
        }
        uVar3 |= BPCP_OUTCODE3;
    } else if ((uVar4 & BPCP_OUTCODE2) == 0 && param_3->y < param_0->y) {
        uVar4 |= BPCP_OUTCODE3;
    }

    if (uVar3 == 0) {
        return true;
    }
    if (uVar4 == 0) {
        return true;
    }

    uVar3 |= cM3d_CheckBoxEdgePlane_Bevel2DCheck(param_2, param_0, param_1) << 8;
    uVar4 |= cM3d_CheckBoxEdgePlane_Bevel2DCheck(param_3, param_0, param_1) << 8;
    if ((uVar3 & uVar4) != 0) {
        return false;
    }

    uVar3 |= cM3d_CheckBoxEdgePlane_Bevel3DCheck(param_2, param_0, param_1) << 0x18;
    uVar4 |= cM3d_CheckBoxEdgePlane_Bevel3DCheck(param_3, param_0, param_1) << 0x18;
    if ((uVar3 & uVar4) != 0) {
        return false;
    }

    cM3dGLin line(*param_2, *param_3);

    if ((uVar3 ^ uVar4) & BPCP_OUTCODE0) {
        cM3dGPla plane;
        plane.mNormal.x = 1.0f;
        plane.mNormal.y = 0.0f;
        plane.mNormal.z = 0.0f;
        plane.mD = -param_1->x;
        Vec cross;
        if (plane.cross(line, cross) && param_0->y <= cross.y && cross.y <= param_1->y
            && param_0->z <= cross.z && cross.z <= param_1->z)
        {
            return true;
        }
    }

    if ((uVar3 ^ uVar4) & BPCP_OUTCODE1) {
        cM3dGPla plane;
        plane.mNormal.x = -1.0f;
        plane.mNormal.y = 0.0f;
        plane.mNormal.z = 0.0f;
        plane.mD = param_0->x;
        Vec cross;
        if (plane.cross(line, cross) && param_0->y <= cross.y && cross.y <= param_1->y
            && param_0->z <= cross.z && cross.z <= param_1->z)
        {
            return true;
        }
    }

    if ((uVar3 ^ uVar4) & BPCP_OUTCODE2) {
        cM3dGPla plane;
        plane.mNormal.x = 0.0f;
        plane.mNormal.y = 1.0f;
        plane.mNormal.z = 0.0f;
        plane.mD = -param_1->y;
        Vec cross;
        if (plane.cross(line, cross) && param_0->x <= cross.x && cross.x <= param_1->x
            && param_0->z <= cross.z && cross.z <= param_1->z)
        {
            return true;
        }
    }

    if ((uVar3 ^ uVar4) & BPCP_OUTCODE3) {
        cM3dGPla plane;
        plane.mNormal.x = 0.0f;
        plane.mNormal.y = -1.0f;
        plane.mNormal.z = 0.0f;
        plane.mD = param_0->y;
        Vec cross;
        if (plane.cross(line, cross) && param_0->x <= cross.x && cross.x <= param_1->x
            && param_0->z <= cross.z && cross.z <= param_1->z)
        {
            return true;
        }
    }
    
    if ((uVar3 ^ uVar4) & BPCP_OUTCODE4) {
        cM3dGPla plane;
        plane.mNormal.x = 0.0f;
        plane.mNormal.y = 0.0f;
        plane.mNormal.z = 1.0f;
        plane.mD = -param_1->z;
        Vec cross;
        if (plane.cross(line, cross) && param_0->x <= cross.x && cross.x <= param_1->x
            && param_0->y <= cross.y && cross.y <= param_1->y)
        {
            return true;
        }
    }

    if ((uVar3 ^ uVar4) & BPCP_OUTCODE5) {
        cM3dGPla plane;
        plane.mNormal.x = 0.0f;
        plane.mNormal.y = 0.0f;
        plane.mNormal.z = -1.0f;
        plane.mD = param_0->z;
        Vec cross;
        if (plane.cross(line, cross) && param_0->x <= cross.x && cross.x <= param_1->x
            && param_0->y <= cross.y && cross.y <= param_1->y)
        {
            return true;
        }
    }

    return false;
}

inline static bool cM3d_InclusionCheckPosIn3PosBox2d(
    f32 param_1, f32 param_2,
    f32 param_3, f32 param_4,
    f32 param_5, f32 param_6,
    f32 param_7, f32 param_8
) {
    f32 f31;
    f32 f30;
    if (param_1 < param_3) {
        f31 = param_1;
        f30 = param_3;
    } else {
        f31 = param_3;
        f30 = param_1;
    }

    if (f31 > param_5) {
        f31 = param_5;   
    } else if (f30 < param_5) {
        f30 = param_5;
    }

    if (f31 > param_7 || f30 < param_7) {
        return false;
    } 

    if (param_2 < param_4) {
        f31 = param_2;
        f30 = param_4;
    } else {
        f31 = param_4;
        f30 = param_2;
    }

    if (f31 > param_6) {
        f31 = param_6;
    } else if (f30 < param_6) {
        f30 = param_6;
    }
    
    if (f31 > param_8 || f30 < param_8) {
        return false;
    }
    return true;
}

bool cM3d_CrossX_Tri(const cM3dGTri* tri, const Vec* pos) {
    if (cM3d_IsZero(tri->GetNP()->x)) {
        return false;
    }
    if (!cM3d_InclusionCheckPosIn3PosBox2d(
        tri->mA.y,
        tri->mA.z,
        tri->mB.y,
        tri->mB.z,
        tri->mC.y,
        tri->mC.z,
        pos->y,
        pos->z
    )) {
        return false;
    }
    f32 f12 = cM3d_VectorProduct2d(
        tri->mA.y,
        tri->mA.z,
        tri->mB.y,
        tri->mB.z,
        pos->y,
        pos->z
    );
    if (f12 <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.y,
            tri->mB.z,
            tri->mC.y,
            tri->mC.z,
            pos->y,
            pos->z
        ) <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.y,
            tri->mC.z,
            tri->mA.y,
            tri->mA.z,
            pos->y,
            pos->z
        ) <= 20.0f
    ) {
        return true;
    }
    if (f12 >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.y,
            tri->mB.z,
            tri->mC.y,
            tri->mC.z,
            pos->y,
            pos->z
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.y,
            tri->mC.z,
            tri->mA.y,
            tri->mA.z,
            pos->y,
            pos->z
        ) >= -20.0f
    ) {
        return true;
    }
    return false;
}

bool cM3d_CrossY_Tri(const cM3dGTri* tri, const Vec* pos) {
    if (cM3d_IsZero(tri->GetNP()->y)) {
        return false;
    }
    if (!cM3d_InclusionCheckPosIn3PosBox2d(
        tri->mA.z,
        tri->mA.x,
        tri->mB.z,
        tri->mB.x,
        tri->mC.z,
        tri->mC.x,
        pos->z,
        pos->x
    )) {
        return false;
    }
    f32 f12 = cM3d_VectorProduct2d(
        tri->mA.z,
        tri->mA.x,
        tri->mB.z,
        tri->mB.x,
        pos->z,
        pos->x
    );
    if (f12 <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.z,
            tri->mB.x,
            tri->mC.z,
            tri->mC.x,
            pos->z,
            pos->x
        ) <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.z,
            tri->mC.x,
            tri->mA.z,
            tri->mA.x,
            pos->z,
            pos->x
        ) <= 20.0f
    ) {
        return true;
    }
    if (f12 >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.z,
            tri->mB.x,
            tri->mC.z,
            tri->mC.x,
            pos->z,
            pos->x
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.z,
            tri->mC.x,
            tri->mA.z,
            tri->mA.x,
            pos->z,
            pos->x
        ) >= -20.0f
    ) {
        return true;
    }
    return false;
}

/* 8024C188-8024C370       .text cM3d_CrossY_Tri__FRC3VecRC3VecRC3VecRC8cM3dGPlaPC3Vec */
bool cM3d_CrossY_Tri(const Vec& r3, const Vec& r4, const Vec& r5, const cM3dGPla& pla, const Vec* pos) {
    if (cM3d_IsZero(pla.GetNP()->y)) {
        return false;
    }
    if (!cM3d_InclusionCheckPosIn3PosBox2d(
        r3.z,
        r3.x,
        r4.z,
        r4.x,
        r5.z,
        r5.x,
        pos->z,
        pos->x
    )) {
        return false;
    }
    f32 f12 = cM3d_VectorProduct2d(
        r3.z,
        r3.x,
        r4.z,
        r4.x,
        pos->z,
        pos->x
    );
    if (f12 <= 20.0f
        &&
        cM3d_VectorProduct2d(
            r4.z,
            r4.x,
            r5.z,
            r5.x,
            pos->z,
            pos->x
        ) <= 20.0f
        &&
        cM3d_VectorProduct2d(
            r5.z,
            r5.x,
            r3.z,
            r3.x,
            pos->z,
            pos->x
        ) <= 20.0f
    ) {
        return true;
    }
    if (f12 >= -20.0f
        &&
        cM3d_VectorProduct2d(
            r4.z,
            r4.x,
            r5.z,
            r5.x,
            pos->z,
            pos->x
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            r5.z,
            r5.x,
            r3.z,
            r3.x,
            pos->z,
            pos->x
        ) >= -20.0f
    ) {
        return true;
    }
    return false;
}

/* 8024C370-8024C4D0       .text cM3d_CrossY_Tri_Front__FRC3VecRC3VecRC3VecPC3Vec */
bool cM3d_CrossY_Tri_Front(const Vec& r3, const Vec& r4, const Vec& r5, const Vec* pos) {
    if (!cM3d_InclusionCheckPosIn3PosBox2d(
        r3.z,
        r3.x,
        r4.z,
        r4.x,
        r5.z,
        r5.x,
        pos->z,
        pos->x
    )) {
        return false;
    }
    if (cM3d_VectorProduct2d(
            r3.z,
            r3.x,
            r4.z,
            r4.x,
            pos->z,
            pos->x
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            r4.z,
            r4.x,
            r5.z,
            r5.x,
            pos->z,
            pos->x
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            r5.z,
            r5.x,
            r3.z,
            r3.x,
            pos->z,
            pos->x
        ) >= -20.0f
    ) {
        return true;
    }
    return false;
}

bool cM3d_CrossZ_Tri(const cM3dGTri* tri, const Vec* pos) {
    if (cM3d_IsZero(tri->GetNP()->z)) {
        return false;
    }
    if (!cM3d_InclusionCheckPosIn3PosBox2d(
        tri->mA.x,
        tri->mA.y,
        tri->mB.x,
        tri->mB.y,
        tri->mC.x,
        tri->mC.y,
        pos->x,
        pos->y
    )) {
        return false;
    }
    f32 f12 = cM3d_VectorProduct2d(
        tri->mA.x,
        tri->mA.y,
        tri->mB.x,
        tri->mB.y,
        pos->x,
        pos->y
    );
    if (f12 <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.x,
            tri->mB.y,
            tri->mC.x,
            tri->mC.y,
            pos->x,
            pos->y
        ) <= 20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.x,
            tri->mC.y,
            tri->mA.x,
            tri->mA.y,
            pos->x,
            pos->y
        ) <= 20.0f
    ) {
        return true;
    }
    if (f12 >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mB.x,
            tri->mB.y,
            tri->mC.x,
            tri->mC.y,
            pos->x,
            pos->y
        ) >= -20.0f
        &&
        cM3d_VectorProduct2d(
            tri->mC.x,
            tri->mC.y,
            tri->mA.x,
            tri->mA.y,
            pos->x,
            pos->y
        ) >= -20.0f
    ) {
        return true;
    }
    return false;
}

bool cM3d_Cross_LinTri(const cM3dGLin* lin, const cM3dGTri* tri, Vec* dst, bool a, bool b) {
    if (!cM3d_Cross_LinPla(lin, tri, dst, a, b)) {
        return false;
    }
    if ((std::fabs(tri->GetNP()->x) < 0.008f || cM3d_CrossX_Tri(tri, dst)) &&
        (std::fabs(tri->GetNP()->y) < 0.008f || cM3d_CrossY_Tri(tri, dst)) &&
        (std::fabs(tri->GetNP()->z) < 0.008f || cM3d_CrossZ_Tri(tri, dst))
    ) {
        return true;
    } else {
        return false;
    }
}
