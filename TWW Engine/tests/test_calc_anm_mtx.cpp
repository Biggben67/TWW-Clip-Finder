// test_calc_anm_mtx.cpp - the 42-joint skeleton walk: `J3DModel::calcAnmMtx` ->
// `J3DMtxCalcBasic::recursiveCalc` -> `J3DJoint::calcIn` -> `mDoExt_MtxCalcAnmBlendTblOld::calc`
// -> `mDoMtx_quat` -> `mDoExt_setJ3DData`, whose anmMtx array feeds `posMoveFromFootPos`.
//
// The player installs mDoExt_MtxCalcAnmBlendTblOld (d_a_player_main.cpp:12023, 12026), the
// quaternion path, so J3DGetTranslateRotateMtx (test_tr_matrix.cpp) is never reached.
//
// Pinned beyond the arithmetic, each with a red control: the walk order (child, then younger
// sibling), the per-node restore of mCurrentMtx / mCurrentS / mParentS, and the start from the
// base transform (J3DMdlFlag_Unk00002 clear; an identity-space walk is 1-2 ULP off in the world).
//
// The 1/mParentS scale compensation in `mDoExt_setJ3DData` is live (`slip` scales RlegA_jnt, whose
// child is compensating); the old sim's foot_fk.py omits it, so the port is right where they differ.
//
// Expected rows are composed from the old sim's single-precision primitives arranged as the decomp
// spells the pass: a transcription gate.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "boundary/game_boundary.h"
#include "d/actor/d_a_player_main.h"
#include "engine/jma_console_table.h"
#include "engine/link_model.h"
#include "engine/ps_mtx.h"
#include "JSystem/J3DGraphAnimator/J3DJoint.h"
#include "JSystem/J3DGraphBase/J3DSys.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::bits;

const char* const kGolden = "anm_mtx_oracle.json";

/// `Mtx` is a raw array, which cannot be a container element.
struct MtxBox {
    Mtx m;
};

/// What a run may be broken with. `Correct` is the port as it stands.
enum Injection {
    Correct,
    YoungerFirst,        ///< recursiveCalc's child and younger-sibling recursions exchanged
    NoRestore,           ///< the per-node backup of mCurrentMtx / mCurrentS / mParentS not restored
    IdentityBase,        ///< J3DMdlFlag_Unk00002, which seeds the walk from the identity
    NoScaleCompensate,   ///< the old sim's foot_fk spelling: the 1/mParentS row divide dropped
};

const daPy_portAnmTrack* track_for(u16 bck_idx) {
    for (size_t i = 0; i < daPy_portAnmTrackTableSize(); i++) {
        if (daPy_portAnmTrackTableAt(i)->mBckIdx == bck_idx) {
            return daPy_portAnmTrackTableAt(i);
        }
    }
    return NULL;
}

/// The three base matrices the golden names: identity, a world position, and that position turned
/// about Y.
void base_named(const std::string& name, Mtx out) {
    const f32 px = 1731.0f, py = 300.0f, pz = 764.0f;
    for (int r = 0; r < 3; r++) {
        for (int c = 0; c < 4; c++) {
            out[r][c] = (r == c) ? 1.0f : 0.0f;
        }
    }
    if (name == "identity") {
        return;
    }
    out[0][3] = px;
    out[1][3] = py;
    out[2][3] = pz;
    if (name == "world_turned") {
        const f32 cs = static_cast<f32>(std::cos(0.7));
        const f32 sn = static_cast<f32>(std::sin(0.7));
        out[0][0] = cs;
        out[0][2] = sn;
        out[2][0] = -sn;
        out[2][2] = cs;
    }
}

/// recursiveCalc re-implemented for the two walk-shape injections, over the port's own calcIn.
void broken_recursive_calc(J3DNode* node, Injection how) {
    if (!node) {
        return;
    }
    Mtx backup;
    MTXCopy(J3DSys::mCurrentMtx, backup);
    const Vec backupS = J3DSys::mCurrentS;
    const Vec backupParentS = J3DSys::mParentS;

    node->calcIn();
    broken_recursive_calc(how == YoungerFirst ? node->getYounger() : node->getChild(), how);
    if (how != NoRestore) {
        MTXCopy(backup, J3DSys::mCurrentMtx);
        J3DSys::mCurrentS = backupS;
        J3DSys::mParentS = backupParentS;
    }
    node->calcOut();
    broken_recursive_calc(how == YoungerFirst ? node->getChild() : node->getYounger(), how);
}

/// One walk, into `out` - the 42 anmMtx in joint order.
void run_walk(tww_engine::LinkModel& model, const Mtx base, Injection how, std::vector<MtxBox>& out) {
    model.setBase(base);
    if (how == IdentityBase) {
        model.model()->onFlag(J3DMdlFlag_Unk00002);
    } else {
        model.model()->offFlag(J3DMdlFlag_Unk00002);
    }

    if (how == YoungerFirst || how == NoRestore) {
        // calcAnmMtx's three preconditions, then the broken walk.
        j3dSys.setModel(model.model());
        j3dSys.setCurrentMtxCalc(model.modelData()->getBasicMtxCalc());
        model.mBasic.init(*model.model()->getBaseScale(), model.model()->getBaseTRMtx());
        broken_recursive_calc(model.modelData()->getRootNode(), how);
    } else {
        model.model()->calcAnmMtx();
    }

    out.resize(static_cast<size_t>(tww_engine::linkJointNum()));
    for (int j = 0; j < tww_engine::linkJointNum(); j++) {
        MTXCopy(model.model()->getAnmMtx(j), out[static_cast<size_t>(j)].m);
    }
}

struct Counts {
    int walks = 0;
    int joints = 0;
    int differing_joints = 0;
    int differing_walks = 0;
    std::string first_diff;
};

/// Run the corpus. `compare` asserts against the golden; `measure` counts the joints where the
/// injected walk differs from the correct one.
Counts walk_all(Case& c, Injection how, bool compare, bool measure) {
    // `jmaSinTable` has no static initialiser; without this a filtered run reads a null pointer.
    JMA_useConsoleSinTable();

    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["expected"];
    const int joint_num = g["_joint_num"].as_int();

    tww_engine::LinkModel model(how != NoScaleCompensate);
    tww_engine::LinkUnderCalc under(1);
    model.setMtxCalcOnAllJoints(under.calc());

    tww_engine::LinkModel reference(true);
    tww_engine::LinkUnderCalc ref_under(1);
    reference.setMtxCalcOnAllJoints(ref_under.calc());

    Counts n;
    std::vector<MtxBox> got;
    std::vector<MtxBox> other;
    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        const std::string name = row[0].str;
        const u16 bck_idx = static_cast<u16>(row[1].as_int());
        const s16 frame_max = static_cast<s16>(row[2].as_int());
        const f32 frame = row[3].as_f32();
        const std::string bname = row[4].str;

        const daPy_portAnmTrack* track = track_for(bck_idx);
        REQUIRE_TRUE(c, track != NULL,
                     name + ": the golden names .bck index " + std::to_string(bck_idx)
                         + " and anm_track.inc has no row for it");
        if (track == NULL) {
            continue;
        }
        // A .bck with fewer joints than the skeleton would read the next animation's words.
        REQUIRE_INT(c, track->mJointNum, joint_num,
                    name + ": the animation's joint count and the skeleton's");

        daPy_portAnm_c anm;
        anm.load(frame_max, J3DFrameCtrl::EMode_NONE, track);
        anm.setFrame(frame);
        under.setAnim(0, &anm, 1.0f);

        Mtx base;
        base_named(bname, base);
        run_walk(model, base, how, got);

        if (measure) {
            ref_under.setAnim(0, &anm, 1.0f);
            run_walk(reference, base, Correct, other);
            int diff = 0;
            for (int j = 0; j < joint_num; j++) {
                bool differs = false;
                for (int r = 0; r < 3 && !differs; r++) {
                    for (int col = 0; col < 4 && !differs; col++) {
                        differs = bits(got[static_cast<size_t>(j)].m[r][col])
                                  != bits(other[static_cast<size_t>(j)].m[r][col]);
                    }
                }
                if (differs) {
                    diff++;
                    if (n.first_diff.empty()) {
                        char buf[256];
                        std::snprintf(buf, sizeof(buf),
                                      "%s @ %f (%s) joint %d: got %.9g ref %.9g",
                                      name.c_str(), (double)frame, bname.c_str(), j,
                                      (double)got[(size_t)j].m[0][0],
                                      (double)other[(size_t)j].m[0][0]);
                        n.first_diff = buf;
                    }
                }
            }
            n.differing_joints += diff;
            if (diff) {
                n.differing_walks++;
            }
        }

        if (compare) {
            const std::string at = name + " @ " + std::to_string(frame) + " (" + bname + ") ";
            for (int j = 0; j < joint_num; j++) {
                for (int r = 0; r < 3; r++) {
                    for (int col = 0; col < 4; col++) {
                        REQUIRE_BITS(c, got[static_cast<size_t>(j)].m[r][col],
                                     row[6 + (j * 3 + r) * 4 + col].as_f32(),
                                     at + "joint " + std::to_string(j) + " m"
                                         + std::to_string(r) + std::to_string(col));
                    }
                }
                n.joints++;
            }
        }
        n.walks++;
    }
    return n;
}

}  // namespace

TWWE_TEST(the_skeleton_walk_poses_every_joint_the_way_the_game_does,
          "the 42-joint pass disagrees with the old sim's primitives on some joint - the walk "
          "order, the parent a joint accumulates against, the concat's operand order, which "
          "joint's scale mParentS holds, or the per-joint quaternion arithmetic underneath") {
    const int before = j3d_boundary_hits;
    const Counts n = walk_all(c, Correct, true, false);

    c.note("walks compared:        " + std::to_string(n.walks)
           + " (27 animations x 4 frames x 3 base matrices)");
    c.note("joint matrices:        " + std::to_string(n.joints) + " x 12 elements");
    c.note("oracle tier:           " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM, and a transcription gate rather than an independent one - the "
                             "expected rows are composed from the old sim's primitives, arranged "
                             "the way the decomp spells the pass"));
    REQUIRE_INT(c, n.walks, 324, "every walk in the corpus ran");
    REQUIRE_INT(c, n.joints, 324 * 42, "every joint of every walk was compared");

    // The draw-side virtuals kept for the vtable (J3DJoint::entryIn, J3DJoint::recursiveCalc,
    // J3DMtxCalcSoftimage::calcTransform) must be unreachable from the pass.
    REQUIRE_INT(c, j3d_boundary_hits - before, 0,
                "the walk reached no draw-side boundary function; last was "
                    + std::string(j3d_boundary_last));
}

TWWE_TEST(the_walk_visits_the_joints_in_the_order_the_hierarchy_puts_them,
          "the tree engine/link_model.cpp builds visits the joints in a different order from the "
          "one the generator measured off the .bmd's own INF1 stream - so the appendChild "
          "replay and the generator's replay have parted company") {
    // The visit order alone, no arithmetic. Expected is the generator's replay of
    // J3DJointTree::makeHierarchy; got is the tree J3DNode::appendChild built, walked as
    // recursiveCalc walks it.
    tww_engine::LinkModel model;

    std::vector<int> order;
    std::vector<J3DNode*> stack;
    stack.push_back(model.modelData()->getRootNode());
    while (!stack.empty()) {
        J3DNode* node = stack.back();
        stack.pop_back();
        if (!node) {
            continue;
        }
        order.push_back(static_cast<J3DJoint*>(node)->getJntNo());
        // Sibling pushed first so the child pops first.
        stack.push_back(node->getYounger());
        stack.push_back(node->getChild());
    }

    REQUIRE_INT(c, static_cast<int>(order.size()), tww_engine::linkJointNum(),
                "the walk reaches every joint exactly once - a tree with a joint appended twice "
                "would pose it twice, and one with a joint unreached would leave its anmMtx "
                "whatever the previous frame left there");
    for (int i = 0; i < tww_engine::linkJointNum() && i < static_cast<int>(order.size()); i++) {
        REQUIRE_INT(c, order[static_cast<size_t>(i)], tww_engine::linkVisitOrder(i),
                    "visit " + std::to_string(i));
    }
    REQUIRE_INT(c, model.modelData()->getJointNum(), tww_engine::linkJointNum(),
                "the model data's joint count is the skeleton's - which is what "
                "mDoExt_MtxCalcAnmBlendTblOld::calc's last-joint test reads");
    c.note("joints visited: " + std::to_string(order.size())
           + ", in the order the .bmd's INF1 stream puts them");
}

TWWE_TEST(the_scale_compensation_is_live_and_here_is_what_it_is_worth,
          "the 1/mParentS row divide has stopped changing any joint matrix - which would mean "
          "either that the corpus lost the animations that scale a joint, or that the port has "
          "been quietly reconciled with the old sim, which does not apply it") {
    // Counts how often the red control's removal is reachable.
    const Counts n = walk_all(c, NoScaleCompensate, false, true);
    c.note("joint matrices the scale compensation moves: " + std::to_string(n.differing_joints)
           + " of " + std::to_string(n.walks * 42));
    c.note("walks it moves at least one in:              " + std::to_string(n.differing_walks)
           + " of " + std::to_string(n.walks));
    c.note("first difference: " + n.first_diff);
    c.note("the old sim applies the joint's own scale and not this - so a "
           "gate written against it would be red here, and the port is the side that is right");
    REQUIRE_TRUE(c, n.differing_joints > 1000,
                 "the scale compensation changes the answer on joints the game's own animations "
                 "produce, so it is not a corner case");
    REQUIRE_TRUE(c, n.differing_walks < n.walks,
                 "and it does not change every walk - `walk` and `dash` scale only arm and hair "
                 "joints, which is how the old sim's foot chain was validated without it");
}

TWWE_RED_CONTROL(red_the_walk_takes_the_younger_sibling_before_the_child,
                 "recursiveCalc's two recursions exchanged: each node's younger sibling walked "
                 "before its child. Every joint is still visited exactly once and every matrix is "
                 "still a matrix - what moves is which mCurrentMtx each joint's subtree inherits, "
                 "because the backup is taken before calcIn and restored after the first "
                 "recursion returns") {
    walk_all(c, YoungerFirst, true, false);
}

TWWE_RED_CONTROL(red_the_walk_never_restores_the_parent_state,
                 "the per-node backup of mCurrentMtx, mCurrentS and mParentS taken and never put "
                 "back, so each joint accumulates onto whatever the previous joint left rather "
                 "than onto its own parent - and a scale-compensating joint divides by the "
                 "previous joint's scale. It is right for every joint whose parent is the joint "
                 "before it, which on Link's leftmost spine is most of them") {
    walk_all(c, NoRestore, true, false);
}

TWWE_RED_CONTROL(red_the_walk_starts_from_the_identity_instead_of_the_base,
                 "J3DMdlFlag_Unk00002 set, which is calcAnmMtx's own arm for seeding mCurrentMtx "
                 "from j3dDefaultMtx rather than the model's base transform. It is exactly right "
                 "on the identity-base third of the corpus, and wrong on the other two thirds by "
                 "more than a translation: the FK quantizes each joint at the base's magnitude, "
                 "which is why the old sim runs it in world space") {
    walk_all(c, IdentityBase, true, false);
}

TWWE_RED_CONTROL(red_the_scale_compensation_is_dropped,
                 "every joint's mScaleCompensate zeroed - the old sim's "
                 "spelling, which applies the joint's own scale and not mDoExt_setJ3DData's "
                 "1/mParentS row divide. It is right on every joint whose parent is unscaled, "
                 "which is all of them in `walk` and `dash`; the case above counts where it is "
                 "not") {
    walk_all(c, NoScaleCompensate, true, false);
}
