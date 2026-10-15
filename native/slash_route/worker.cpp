#include <algorithm>
#include <atomic>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>
#include "engine/session.h"
#include "engine/link_assets.h"
#include "engine/jma_console_table.h"
#include "boundary/game_boundary.h"
#include "SSystem/SComponent/c_API_controller_pad.h"
#include "tests/framework/json.h"

using namespace tww_engine;
using tww_engine::testing::Json;

extern thread_local interface_of_controller_pad g_mDoCPd_cpadInfo[4];
static cXyz xyz(const Json& j);

static void camera_seed(Session& s, const Json& j) {
    if (!j.has("camera_state")) throw std::runtime_error("recapture this route to import camera state");
    const auto& state=j["camera_state"];
    if (state["external_target"].boolean) throw std::runtime_error("camera tracks an unimported actor");
    const std::string arm=state["arm"].str;
    if (arm!="FOLLOW" && arm!="MANUAL" && arm!="SUBJECT")
        throw std::runtime_error("unported captured camera algorithm");
    s.seatCamera((s16)j["camera"].as_int());
    auto& cam=s.cameraBody(); const auto& f=state["fields"];
#define CAM_FIELD(name, offset, kind) if (!f.has(#name)) throw std::runtime_error("missing camera field " #name); cam.name=(kind)f[#name].number;
#define CAM_VEC(name, offset) cam.name=xyz(f[#name]);
#define CAM_GLOBE(name, offset) cam.name.Val(f[#name][0].as_f32(), (s16)f[#name][1].as_int(), (s16)f[#name][2].as_int());
#define CAMERA_COMMON
#include "camera_fields.inc"
#undef CAMERA_COMMON
    if (arm=="FOLLOW") {
#define CAMERA_FOLLOW
#include "camera_fields.inc"
#undef CAMERA_FOLLOW
    } else if (arm=="MANUAL") {
#define CAMERA_MANUAL
#include "camera_fields.inc"
#undef CAMERA_MANUAL
    } else {
#define CAMERA_SUBJECT
#include "camera_fields.inc"
#undef CAMERA_SUBJECT
    }
#undef CAM_FIELD
#undef CAM_VEC
#undef CAM_GLOBE
    if (cam.mCurStyle<0 || cam.mCurStyle>=dCamParam_c::style_num ||
        cam.mCurType<0 || cam.mCurType>=dCamera_c::type_num || cam.mPadId!=0)
        throw std::runtime_error("invalid captured camera style/type/controller");
    cam.mCamParam.Change(cam.mCurStyle);
    if (cam.mCamParam.Algorythmn()!=state["algorithm"].as_int())
        throw std::runtime_error("captured camera style differs from engine version");
    s.lk.stub_camera_attn=(u32)state["attention"].as_int();
    s.lk.stub_player_status0=(u32)state["status0"].as_int();
    s.lk.stub_player_status1=(u32)state["status1"].as_int();
    s.lk.attention_info.position=xyz(j["attention_pos"]);
    s.lk.eyePos=xyz(j["eye_pos"]);
    cam_stub_lockon=false; cam_stub_lockon_truth=false;
}

static controller_pad_buttons buttons(unsigned mask) {
    controller_pad_buttons b{};
    b.left=mask&0x8000; b.right=mask&0x4000; b.down=mask&0x2000; b.up=mask&0x1000;
    b.z=mask&0x800; b.r=mask&0x400; b.l=mask&0x200; b.a=mask&0x100;
    b.b=mask&0x80; b.x=mask&0x40; b.y=mask&0x20; b.start=mask&0x10;
    return b;
}

static void camera_pad(const Json& row, unsigned previous) {
    auto& p=g_mDoCPd_cpadInfo[0]; p={};
    p.mMainStickPosX=row["mx"].as_f32(); p.mMainStickPosY=row["my"].as_f32();
    p.mMainStickValue=row["distance"].as_f32();
    p.mMainStickAngle=(s16)(row["angle"].as_int()-0x8000);
    p.mCStickPosX=row["cx"].as_f32(); p.mCStickPosY=row["cy"].as_f32();
    p.mCStickValue=row["cvalue"].as_f32(); p.mCStickAngle=(s16)row["cangle"].as_int();
    p.mAnalogA=row["analog_a"].as_f32(); p.mAnalogB=row["analog_b"].as_f32();
    p.mTriggerLeft=row["tl"].as_f32(); p.mTriggerRight=row["tr"].as_f32();
    const unsigned hold=(unsigned)row["hold"].as_int();
    p.mButtonHold=buttons(hold); p.mButtonTrig=buttons(hold & ~previous);
    p.mHoldLockL=(u8)row["lock_l"].as_int(); p.mHoldLockR=(u8)row["lock_r"].as_int();
    p.mTrigLockL=(u8)row["trig_l"].as_int(); p.mTrigLockR=(u8)row["trig_r"].as_int();
    cam_stub_lockon=p.mHoldLockL!=0;
    cam_stub_lockon_truth=false;
}

static cXyz xyz(const Json& j) {
    if (j.size() != 3) throw std::runtime_error("invalid vector");
    return {j[0].as_f32(), j[1].as_f32(), j[2].as_f32()};
}
static std::vector<u8> bytes(const std::filesystem::path& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("missing asset: " + path.string());
    return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}
static void assets(const std::string& path) {
    LinkAssets a;
    a.model = bytes(std::filesystem::path(path) / "cl.bdl");
    for (const auto& name : linkAnimationFiles())
        a.animations[name] = bytes(std::filesystem::path(path) / name);
    std::string why;
    if (!installLinkAssets(a, &why)) throw std::runtime_error(why);
    JMA_useConsoleSinTable();
}

static void acyclic(const std::vector<std::vector<size_t>>& edges, const char* name) {
    std::vector<u8> mark(edges.size(),0);
    std::function<void(size_t,size_t)> visit = [&](size_t i,size_t depth) {
        if (i>=edges.size()) throw std::runtime_error(std::string("invalid ")+name+" index");
        if (mark[i]==1) throw std::runtime_error(std::string("cyclic ")+name);
        if (mark[i]==2) return;
        if (depth>256) throw std::runtime_error(std::string("excessive ")+name+" depth");
        mark[i]=1;
        for (size_t next:edges[i]) visit(next,depth+1);
        mark[i]=2;
    };
    for (size_t i=0;i<edges.size();++i) visit(i,0);
}

static RoomDzb room_data(const Json& j) {
    RoomDzb d;
    for (const auto& row : j["vertices"].array) {
        cBgD_Vtx_t v{}; const auto p = xyz(row);
        v.x=p.x; v.y=p.y; v.z=p.z; d.v_tbl.push_back(v);
    }
    for (const auto& r : j["triangles"].array) {
        cBgD_Tri_t t{};
        t.vtx0=(u16)r[0].as_int(); t.vtx1=(u16)r[1].as_int(); t.vtx2=(u16)r[2].as_int();
        t.id=(u16)r[3].as_int(); t.grp=(u16)r[4].as_int(); d.t_tbl.push_back(t);
    }
    for (const auto& r : j["blocks"].array) d.b_tbl.push_back({(u16)r.as_int()});
    for (const auto& r : j["trees"].array) {
        cBgD_Tree_t t{}; t.mFlag=(u16)r[0].as_int(); t.mParent=(u16)r[1].as_int();
        for (int i=0;i<8;++i) t.mChild[i]=(u16)r[i+2].as_int();
        d.tree_tbl.push_back(t);
    }
    for (const auto& r : j["groups"].array) {
        cBgD_Grp_t g{};
        g.m_scale=xyz(r["scale"]); g.m_translation=xyz(r["translation"]);
        g.m_rotation.x=(s16)r["rotation"][0].as_int();
        g.m_rotation.y=(s16)r["rotation"][1].as_int();
        g.m_rotation.z=(s16)r["rotation"][2].as_int();
        g.m_parent=(u16)r["links"][0].as_int();
        g.m_next_sibling=(u16)r["links"][1].as_int();
        g.m_first_child=(u16)r["links"][2].as_int();
        g.m_room_id=(u16)r["links"][3].as_int();
        g.m_first_vtx_idx=(u16)r["links"][4].as_int();
        g.m_tree_idx=(u16)r["links"][5].as_int();
        g.m_info=(u32)r["info"].as_int(); d.g_tbl.push_back(g);
    }
    for (const auto& r : j["attributes"].array) {
        cBgD_Ti_t t{}; t.mPolyInf0=(u32)r[0].as_int(); t.mPolyInf1=(u32)r[1].as_int();
        t.mPolyInf2=(u32)r[2].as_int(); t.mPolyInf3=(u32)r[3].as_int(); d.ti_tbl.push_back(t);
    }
    if (d.t_tbl.empty() || d.g_tbl.empty() || d.tree_tbl.empty() || d.b_tbl.empty())
        throw std::runtime_error("empty room collision tables");
    if (d.v_tbl.size()>65535 || d.t_tbl.size()>65535 || d.g_tbl.size()>65535 ||
        d.tree_tbl.size()>65535 || d.b_tbl.size()>65535 || d.ti_tbl.size()>65535)
        throw std::runtime_error("collision tables exceed u16 index capacity");
    for (const auto& v:d.v_tbl)
        if (!std::isfinite(v.x) || !std::isfinite(v.y) || !std::isfinite(v.z))
            throw std::runtime_error("nonfinite collision vertex");
    for (const auto& t : d.t_tbl)
        if (t.vtx0>=d.v_tbl.size() || t.vtx1>=d.v_tbl.size() || t.vtx2>=d.v_tbl.size() ||
            t.id>=d.ti_tbl.size() || t.grp>=d.g_tbl.size())
            throw std::runtime_error("invalid collision triangle index");
    for (size_t i=0;i<d.b_tbl.size();++i)
        if (d.b_tbl[i].startTri>=d.t_tbl.size() ||
            (i && d.b_tbl[i].startTri<d.b_tbl[i-1].startTri))
            throw std::runtime_error("invalid collision block range");
    std::vector<std::vector<size_t>> trees(d.tree_tbl.size()), groups(d.g_tbl.size());
    for (size_t i=0;i<trees.size();++i) {
        const auto& node=d.tree_tbl[i];
        if (node.mFlag&1) {
            if (node.mBlock!=0xFFFF && node.mBlock>=d.b_tbl.size())
                throw std::runtime_error("invalid collision leaf block");
        } else for (u16 child:node.mChild) if (child!=0xFFFF) trees[i].push_back(child);
    }
    for (size_t i=0;i<groups.size();++i) {
        const auto& group=d.g_tbl[i];
        if ((group.m_parent!=0xFFFF && group.m_parent>=groups.size()) ||
            (group.m_tree_idx!=0xFFFF && group.m_tree_idx>=trees.size()))
            throw std::runtime_error("invalid collision group reference");
        if (group.m_first_child!=0xFFFF) groups[i].push_back(group.m_first_child);
        if (group.m_next_sibling!=0xFFFF) groups[i].push_back(group.m_next_sibling);
    }
    acyclic(trees,"collision octree"); acyclic(groups,"collision group hierarchy");
    return d;
}

static void restore_collision(Room& room, const Json& j) {
    if (!j.has("runtime")) return; // Offline DZB fixtures intentionally build their own tables.
    const auto& r=j["runtime"]; auto& bg=room.bgw();
    if (r["planes"].size()!=room.tri_count() || r["links"].size()!=room.tri_count() ||
        r["blocks"].size()!=room.block_count() || r["nodes"].size()!=room.node_count() ||
        r["groups"].size()!=room.group_count())
        throw std::runtime_error("live collision table lengths differ");
    const int root=(int)r["root"].as_int();
    if (root<0 || root>=room.group_count()) throw std::runtime_error("invalid collision root group");
    // A corrupt list must not trap one CPU lane in a native collision walk.
    std::vector<u8> visited(room.tri_count(),0);
    for (int i=0;i<room.tri_count();++i) {
        int n=i; std::vector<int> path;
        while (n!=0xFFFF && !visited[n]) {
            visited[n]=1; path.push_back(n);
            const int next=(int)r["links"][(size_t)n].as_int();
            if (next!=0xFFFF && (next<0 || next>=room.tri_count()))
                throw std::runtime_error("invalid runtime collision chain");
            n=next;
        }
        if (n!=0xFFFF && visited[n]==1)
            throw std::runtime_error("cyclic runtime collision chain");
        for (int index:path) visited[index]=2;
    }
    for (int i=0;i<room.tri_count();++i) {
        const auto& p=r["planes"][(size_t)i];
        bg.pm_tri[i].m_plane.mNormal=cXyz{p[0].as_f32(),p[1].as_f32(),p[2].as_f32()};
        bg.pm_tri[i].m_plane.mD=p[3].as_f32();
        const int next=(int)r["links"][(size_t)i].as_int();
        if (next!=0xFFFF && (next<0 || next>=room.tri_count()))
            throw std::runtime_error("invalid runtime collision chain");
        bg.pm_rwg[i].next=(u16)next;
    }
    for (int i=0;i<room.block_count();++i) {
        const auto& b=r["blocks"][(size_t)i];
        for (int k=0;k<3;++k)
            if (b[k].as_int()!=0xFFFF && (b[k].as_int()<0 || b[k].as_int()>=room.tri_count()))
                throw std::runtime_error("invalid runtime collision block");
        bg.pm_blk[i].roof=(u16)b[0].as_int();
        bg.pm_blk[i].wall=(u16)b[1].as_int();
        bg.pm_blk[i].ground=(u16)b[2].as_int();
    }
    for (int i=0;i<room.node_count()+room.group_count();++i) {
        const bool node=i<room.node_count();
        const auto& a=r[node?"nodes":"groups"][(size_t)(node?i:i-room.node_count())];
        cXyz lo{a[0].as_f32(),a[1].as_f32(),a[2].as_f32()};
        cXyz hi{a[3].as_f32(),a[4].as_f32(),a[5].as_f32()};
        if (node) bg.m_nt_tbl[i].Set(&lo,&hi);
        else bg.pm_grp[i-room.node_count()].aab.Set(&lo,&hi);
    }
    bg.m_rootGrpIdx=root; bg.mFlags=(u8)r["flags"].as_int();
    bg.mMoveCounter=(u8)r["move_counter"].as_int();
    bg.mWallCorrectPriority=(u8)r["priority"].as_int();
    bg.mIgnorePlaneType=(int)r["ignore_plane"].as_int();
}

// Each CPU thread owns its entire collision registry. BG indices, priorities,
// planes and linked lists stay separate even where actor and stage vertices coincide.
struct CapturedWorld {
    std::vector<std::unique_ptr<Room>> rooms;
    CapturedWorld(const std::vector<RoomDzb>& data, const Json& snapshot) {
        for (const auto& dzb:data) rooms.emplace_back(new Room(dzb));
        if (!snapshot.has("backgrounds")) {
            restore_collision(*rooms.front(),snapshot);
            return;
        }
        auto& registry=rooms.front()->bgs(); registry.Ct();
        for (size_t i=0;i<rooms.size();++i) {
            const auto& entry=snapshot["backgrounds"][i];
            const int slot=(int)entry["bg"].as_int();
            if (slot<0 || slot>=256 || registry.m_chk_element[slot].ChkUsed())
                throw std::runtime_error("invalid or duplicate captured BG slot");
            restore_collision(*rooms[i],entry);
            auto& bg=rooms[i]->bgw(); bg.SetId(slot);
            registry.m_chk_element[slot].Regist2(&bg,kRoomPid+(fpc_ProcID)i*2,NULL);
        }
    }
    Room& primary() { return *rooms.front(); }
};
static void clock(J3DFrameCtrl& c, const Json& j) {
    c.setAttribute((u8)j["attribute"].as_int());
    c.setStart((s16)j["start"].as_int()); c.setEnd((s16)j["end"].as_int());
    c.setLoop((s16)j["loop"].as_int()); c.setRate(j["rate"].as_f32());
    c.setFrame(j["frame"].as_f32()); c.restoreState((u8)j["state"].as_int());
}
static void anim(daPy_portAnm_c& a, mDoExt_AnmRatioPack& ratio,
                 J3DFrameCtrl& c, const Json& j) {
    const u16 idx=(u16)j["index"].as_int();
    if (j["active"].boolean) {
        const auto* meta=linkAnimationMeta(idx); const auto* track=linkAnimationTrack(idx);
        if (!meta || !track) throw std::runtime_error("unavailable animation index " + std::to_string(idx));
        a.load(meta->mFrameMax,meta->mAttribute,track);
        a.setFrame(j["pose_frame"].as_f32()); ratio.setAnmTransform(&a);
    } else ratio.setAnmTransform(nullptr);
    ratio.setRatio(j["ratio"].as_f32()); clock(c,j);
}
static void seed(Session& s, const Json& j) {
    auto& lk=s.lk; const auto& f=j["fields"];
#define FIELD(name, offset, kind) if (!f.has(#name)) throw std::runtime_error("missing seed field " #name); lk.name=(kind)f[#name].number;
#include "seed_fields.inc"
    if (f.has("mProcVar3.m34D6")) {
        lk.mProcVar3.m34D6 = (s16)f["mProcVar3.m34D6"].number;
    } else if ((int)j["proc"].as_int() == daPy_lk_c::daPyProc_MOVE_TURN_e) {
        throw std::runtime_error("recapture MOVE_TURN seed: missing mProcVar3.m34D6");
    } else {
        lk.mProcVar3.m34D6 = 0; // Other procs initialize it before reading it.
    }
#undef FIELD
    lk.current.pos=xyz(j["pos"]); lk.old.pos=xyz(j["old_pos"]);
    lk.shape_angle.x=(s16)j["shape"][0].as_int();
    lk.shape_angle.y=(s16)j["shape"][1].as_int();
    lk.shape_angle.z=(s16)j["shape"][2].as_int();
    lk.current.angle.y=(s16)j["travel"].as_int(); lk.speed=xyz(j["speed"]);
    lk.mCurProc=(int)j["proc"].as_int(); lk.stub_life=(int)j["life"].as_int();
    lk.stub_select_equip[0]=dItemNo_SWORD_e;
    for (int i=0;i<2;++i) {
        const auto& a=j["under"][(size_t)i];
        lk.m_anm_heap_under[i].mIdx=(u16)a["index"].as_int();
        anim(lk.port_anm_under[i],lk.mAnmRatioUnder[i],lk.mFrameCtrlUnder[i],a);
    }
    for (int i=0;i<3;++i) {
        const auto& a=j["upper"][(size_t)i];
        lk.m_anm_heap_upper[i].mIdx=(u16)a["index"].as_int();
        if (a.has("under_alias")) {
            const int alias=(int)a["under_alias"].as_int();
            if(alias<0 || alias>1) throw std::runtime_error("invalid animation alias");
            lk.mAnmRatioUpper[i].setAnmTransform(&lk.port_anm_under[alias]);
            lk.mAnmRatioUpper[i].setRatio(a["ratio"].as_f32());
            clock(lk.mFrameCtrlUpper[i],a);
        } else anim(lk.port_anm_upper[i],lk.mAnmRatioUpper[i],lk.mFrameCtrlUpper[i],a);
    }
    const auto& old=j["old_frame"];
    lk.m_old_fdata->restoreClock(old["flag"].boolean,old["active"].boolean,
        old["counter"].as_f32(),old["previous"].as_f32(),old["rate"].as_f32(),
        old["value10"].as_f32(),old["value14"].as_f32(),
        (u16)old["start"].as_int(),(u16)old["end"].as_int());
    for (int i=0;i<42;++i) {
        const auto& t=old["transforms"][(size_t)i]; auto* dst=lk.m_old_fdata->getOldFrameTransInfo(i);
        dst->mScale=xyz(t["scale"]); dst->mTranslate=xyz(t["translation"]);
        dst->mRotation.x=(s16)t["rotation"][0].as_int();
        dst->mRotation.y=(s16)t["rotation"][1].as_int();
        dst->mRotation.z=(s16)t["rotation"][2].as_int();
        auto* q=lk.m_old_fdata->getOldFrameQuaternion(i);
        q->x=t["quat"][0].as_f32(); q->y=t["quat"][1].as_f32();
        q->z=t["quat"][2].as_f32(); q->w=t["quat"][3].as_f32();
        MtxP m=lk.mpCLModel->getAnmMtx(i);
        for (int k=0;k<12;++k) m[k/4][k%4]=j["joint_matrices"][(size_t)i][(size_t)k].as_f32();
    }
    for (int k=0;k<12;++k) lk.m37B4[k/4][k%4]=j["inverse"][(size_t)k].as_f32();
    for (int i=0;i<2;++i) {
        const auto& f=j["feet"][(size_t)i]; auto& d=lk.mFootData[i];
        d.field_0x000=(u8)f["flag0"].as_int(); d.field_0x001=(u8)f["flag1"].as_int();
        d.field_0x002=(s16)f["angle2"].as_int(); d.field_0x004=(s16)f["angle4"].as_int();
        d.field_0x006=(s16)f["angle6"].as_int(); d.field_0x008=(s16)f["angle8"].as_int();
        d.field_0x00A=(s16)f["angleA"].as_int(); d.field_0x00C=xyz(f["toe"]);
        d.field_0x018=xyz(f["heel"]); d.field_0x024=xyz(f["ground"]);
        d.field_0x030=f["height"].as_f32();
    }
    const auto& v=j["vectors"];
    lk.mOldSpeed=xyz(v["mOldSpeed"]); lk.m3688=xyz(v["m3688"]);
    lk.m36A0=xyz(v["m36A0"]); lk.m36AC=xyz(v["m36AC"]); lk.m36B8=xyz(v["m36B8"]);
    lk.m3700=xyz(v["m3700"]); lk.m3724=xyz(v["m3724"]); lk.m3730=xyz(v["m3730"]);
    lk.m373C=xyz(v["m373C"]);
}
static void vec(std::ostream& out, const cXyz& p) {
    out << '[' << p.x << ',' << p.y << ',' << p.z << ']';
}
static std::string replay(const Json& req, const Json& rows, Room& room) {
    const bool benchmark=req["benchmark"].boolean;
    Init init;
    if (!benchmark) init.pos=xyz(req["seed"]["pos"]);
    init.equip_item=daPyItem_SWORD_e; init.select_equip_0=dItemNo_SWORD_e;
    Session s(init,room);
    if (!benchmark) seed(s,req["seed"]);
    if (!benchmark) camera_seed(s,req["seed"]);
    Session::boundary_reset();
    std::ostringstream out; out << std::setprecision(9) << "{\"frames\":[";
    bool first=true; unsigned previous=(unsigned)s.lk.mItemButton;
    unsigned previous_pad=benchmark ? 0 : (unsigned)req["seed"]["pad"]["hold"].as_int();
    for (const auto& row: rows.array) {
        if (!benchmark) camera_pad(row,previous_pad);
        previous_pad=(unsigned)row["hold"].as_int();
        Pad p; p.stick_distance=row["distance"].as_f32();
        p.stick_angle_raw=p.stick_distance>0.05f ? (s16)row["angle"].as_int() : s.lk.m34DC;
        const int camera=benchmark ? (int)req["camera"].as_int() : s.cameraYaw();
        p.target_angle=p.stick_distance>0.05f ? (s16)(p.stick_angle_raw+camera) : s.lk.current.angle.y;
        p.item_button=(u8)row["item_button"].as_int();
        p.item_trigger=(u8)(p.item_button & ~previous); previous=p.item_button;
        p.attention_lock=row["target"].boolean;
        const cXyz old=s.lk.current.pos; const int before=s.lk.mCurProc;
        const auto ok=s.step(p);
        if (ok!=StepResult::Ok) throw std::runtime_error("unported proc or missing animation at " + std::to_string(s.lk.mCurProc));
        if (s.lk.next_init_calls) throw std::runtime_error("unported proc transition " + std::to_string(s.lk.next_init));
        if (!std::isfinite(s.lk.current.pos.x)||!std::isfinite(s.lk.current.pos.y)||!std::isfinite(s.lk.current.pos.z))
            throw std::runtime_error("nonfinite native position");
        if (!first) out << ','; first=false;
        out << "{\"before\":" << before << ",\"state\":" << s.lk.mCurProc
            << ",\"facing\":" << (u16)s.lk.shape_angle.y << ",\"travel\":" << (u16)s.lk.current.angle.y
            << ",\"speed\":" << s.lk.speedF << ",\"old\":"; vec(out,old);
        out << ",\"flags\":" << s.lk.mAcch.m_flags;
        if (!benchmark) {
            const auto& cam=s.cameraBody();
            out << ",\"camera\":" << (u16)s.cameraYaw() << ",\"camera_mode\":" << cam.mCurMode;
            out << ",\"camera_eye\":"; vec(out,cam.mEye);
            out << ",\"camera_center\":"; vec(out,cam.mCenter);
        }
        out << ",\"raw\":"; vec(out,s.last_raw_position);
        out << ",\"pos\":"; vec(out,s.lk.current.pos);
        if (req["diagnostics"].boolean) {
            out << ",\"under\":[";
            for (int i=0;i<2;++i) {
                if (i) out << ',';
                auto& clock=s.lk.mFrameCtrlUnder[i];
                auto& blend=s.lk.mAnmRatioUnder[i];
                auto* animation=blend.getAnmTransform();
                out << "{\"index\":" << s.lk.m_anm_heap_under[i].mIdx
                    << ",\"active\":" << (animation ? "true" : "false")
                    << ",\"ratio\":" << blend.getRatio()
                    << ",\"frame\":" << clock.getFrame()
                    << ",\"rate\":" << clock.getRate()
                    << ",\"pose_frame\":" << (animation ? animation->getFrame() : 0.0f) << '}';
            }
            out << ']';
        }
        out << '}';
    }
    out << "],\"boundary\":["; first=true;
    for (const auto& h:s.boundary_report()) {
        if (!first) out << ','; first=false;
        out << "{\"name\":\"" << h.name << "\",\"grade\":\"" << h.grade << "\",\"hits\":" << h.hits << '}';
    }
    out << "]}"; return out.str();
}
static std::string error(const std::string& why) {
    std::string escaped;
    for(char c:why) { if(c=='"'||c=='\\') escaped+='\\'; if(c=='\n'||c=='\r') escaped+=' '; else escaped+=c; }
    return "{\"error\":\"" + escaped + "\"}";
}
int main() {
    std::vector<RoomDzb> data; Json snapshot; bool ready=false;
    std::vector<std::unique_ptr<CapturedWorld>> worlds;
    std::string line;
    while(std::getline(std::cin,line)) {
        try {
            Json req; std::string why;
            if(!Json::parse(line,&req,&why)) throw std::runtime_error(why);
            if(req.has("assets")) {
                ready=false; worlds.clear();
                assets(req["assets"].str);
                data.clear(); snapshot=req["room"];
                if (req.has("benchmark_floor_y")) data.push_back(flat_floor_dzb(req["benchmark_floor_y"].as_f32()));
                else if (snapshot.has("backgrounds")) {
                    if (snapshot["backgrounds"].size()==0 || snapshot["backgrounds"].size()>256)
                        throw std::runtime_error("invalid captured collision registry size");
                    for (const auto& bg:snapshot["backgrounds"].array) data.push_back(room_data(bg));
                } else data.push_back(room_data(snapshot));
                worlds.emplace_back(new CapturedWorld(data,snapshot));
                ready=true;
                std::cout << "{\"ready\":true,\"protocol\":1}" << std::endl; continue;
            }
            if(!ready) throw std::runtime_error("worker not initialized");
            const auto& routes=req["routes"].array; std::vector<std::string> outputs(routes.size());
            std::atomic<size_t> next{0};
            const size_t count=std::min<size_t>(std::max<long long>(1,req["workers"].as_int()),std::min<size_t>(16,routes.size()));
            while(worlds.size()<count) worlds.emplace_back(new CapturedWorld(data,snapshot));
            std::vector<std::thread> threads;
            for(size_t i=0;i<count;++i) threads.emplace_back([&,i] {
                for(size_t n;(n=next.fetch_add(1))<routes.size();) {
                    try { outputs[n]=replay(req,routes[n],worlds[i]->primary()); }
                    catch(const std::exception& e) { outputs[n]=error(e.what()); }
                }
            });
            for(auto& t:threads) t.join();
            std::cout << "{\"results\":[";
            for(size_t i=0;i<outputs.size();++i) { if(i) std::cout << ','; std::cout << outputs[i]; }
            std::cout << "]}" << std::endl;
        } catch(const std::exception& e) { std::cout << error(e.what()) << std::endl; }
    }
}
