#include <cstring>
#include <iostream>
#include <stdexcept>
#include "engine/room.h"
#include "d/d_bg_s_sph_chk.h"
#include "d/d_camera.h"
#include "d/actor/d_a_player_main.h"
#include "SSystem/SComponent/c_m3d_g_tri.h"

using namespace tww_engine;

static void check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

static cM3dGTri triangle(cXyz a, cXyz b, cXyz c, cXyz normal) {
    cM3dGTri tri;
    tri.mA=a; tri.mB=b; tri.mC=c;
    tri.mNormal=normal; tri.mD=-VECDotProduct(&normal,&a);
    return tri;
}

int main() {
    try {
        dBgS_CamSphChk query;
        auto tri=triangle(cXyz(0,0,0),cXyz(10,0,0),cXyz(0,10,0),cXyz(0,0,1));
        query.Set(cXyz(2,2,1),1.001f);
        check(query.cross(&tri),"sphere near radius limit of triangle face");
        query.Set(cXyz(2,2,1.01f),1);
        check(!query.cross(&tri),"sphere beyond plane radius");
        query.Set(cXyz(5,-0.5f,0),1);
        check(query.cross(&tri),"sphere crossing triangle edge");
        query.Set(cXyz(-0.5f,-0.5f,0),1);
        check(query.cross(&tri),"sphere crossing triangle vertex");
        query.Set(cXyz(9,9,0),1);
        check(!query.cross(&tri),"outside triangle inside its bounding box");
        query.Set(cXyz(5,5,0),0);
        check(query.cross(&tri),"point on triangle edge");
        auto xtri=triangle(cXyz(0,0,0),cXyz(0,10,0),cXyz(0,0,10),cXyz(1,0,0));
        query.Set(cXyz(1,2,2),1.001f);
        check(query.cross(&xtri),"X-dominant triangle projection");
        auto ytri=triangle(cXyz(0,0,0),cXyz(0,0,10),cXyz(10,0,0),cXyz(0,1,0));
        query.Set(cXyz(2,1,2),1.001f);
        check(query.cross(&ytri),"Y-dominant triangle projection");

        auto data=flat_floor_dzb(0);
        // Group pass checks apply at depth two, as in real room collision.
        const auto floor_group=data.g_tbl[0];
        data.g_tbl.push_back(floor_group);
        data.g_tbl[0].m_tree_idx=0xffff;
        data.g_tbl[0].m_first_child=1;
        data.g_tbl[1].m_parent=0;
        for (auto& face : data.t_tbl) face.grp=1;
        Room room(data);
        set_dComIfG_Bgsp(&room.bgs());
        dCamera_c cam;
        check(!cam.mBG.m00.m04.MaskNormalGrp() && cam.mBG.m00.m04.MaskWaterGrp(),
              "camera water query must not accept normal floor groups");
        cXyz above_floor(0,100,0);
        cam.mBG.m00.m04.SetPos(&above_floor);
        check(room.bgs().GroundCross(&cam.mBG.m00.m04)==-G_CM3D_F_INF,
              "normal floor must not be reported as a camera water surface");
        cam.mBG.m5C.m04.SetPos(&above_floor);
        check(room.bgs().GroundCross(&cam.mBG.m5C.m04)==0,
              "camera ordinary ground query must still find the floor");
        auto water_data=data;
        water_data.g_tbl[1].m_info=0x100;
        Room water(water_data);
        check(water.bgs().GroundCross(&cam.mBG.m00.m04)==0,
              "camera water query must still find water groups");
        cam.mViewCache.mCenter=cXyz(0,100,0);
        cXyz contact(0,0,0);
        const auto corrected=cam.compWallMargin(&contact,10.5f);
        check(corrected.x==0 && corrected.z==0 && corrected.y>10.49f && corrected.y<10.51f,
              "camera sphere corrects floor contact");
        cam.mViewCache.mCenter=cXyz(0,-100,0);
        const auto back=cam.compWallMargin(&contact,10.5f);
        check(back.y==0,"back-facing plane must not push camera");
        cXyz clear(0,100,0);
        check(cam.compWallMargin(&clear,10.5f).y==100,"clear camera point must not move");
        data.ti_tbl[0].mPolyInf3|=1;
        Room camera_pass(data);
        set_dComIfG_Bgsp(&camera_pass.bgs());
        cam.mViewCache.mCenter=cXyz(0,100,0);
        check(cam.compWallMargin(&contact,10.5f).y==0,"camera-through polygon must be skipped");
        set_dComIfG_Bgsp(nullptr);
        std::cout << "Camera collision: 16 checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
