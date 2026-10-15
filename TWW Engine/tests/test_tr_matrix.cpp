// test_tr_matrix.cpp - J3DGetTranslateRotateMtx, the joint-local matrix under every calcTransform.
//
// The DOL does not fuse either overload (JP 0x802D7CAC / 0x802D7D84): each off-diagonal is
// `fmuls` then `fsubs`, two roundings, as the decomp's `sxcz*sy - cxsz` reads. The old sim's
// fk.py:tr_matrix fuses them (one rounding); the two disagree on 14,653 of 30,225 rotations.
// The port follows the DOL, and the red control is the fused spelling.
//
// The expected rows are composed from the old sim's single-precision ops and console sin/cos
// tables, arranged as the disassembly reads: a transcription gate, which pins fusion, table index
// and operand order.

#include <cstdio>
#include <string>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "dolphin/types.h"
#include "engine/jma_console_table.h"
#include "engine/ppc_fp.h"
#include "JSystem/J3DGraphBase/J3DTransform.h"
#include "JSystem/JMath/JMATrigonometric.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::bits;

const char* const kGolden = "tr_matrix_oracle.json";

/// fk.py:tr_matrix's four fused off-diagonals over the ported body; nothing else differs.
void fused_off_diagonals(const J3DTransformInfo& tx, Mtx dst) {
    J3DGetTranslateRotateMtx(tx, dst);
    const f32 sx = JMASSin(tx.mRotation.x), cx = JMASCos(tx.mRotation.x);
    const f32 sy = JMASSin(tx.mRotation.y);
    const f32 sz = JMASSin(tx.mRotation.z), cz = JMASCos(tx.mRotation.z);
    const f32 cxsz = ppc::fmuls(cx, sz);
    const f32 sxcz = ppc::fmuls(sx, cz);
    const f32 sxsz = ppc::fmuls(sx, sz);
    const f32 cxcz = ppc::fmuls(cx, cz);
    dst[0][1] = ppc::fmsubs(sxcz, sy, cxsz);
    dst[1][2] = ppc::fmsubs(cxsz, sy, sxcz);
    dst[0][2] = ppc::fmadds(cxcz, sy, sxsz);
    dst[1][1] = ppc::fmadds(sxsz, sy, cxcz);
}

struct Counts {
    int rows = 0;
    int animated = 0;
    int axis_aligned = 0;
};

Counts compare_all(Case& c, bool inject_fused) {
    // `jmaSinTable` has no static initialiser; without this a filtered run reads a null pointer.
    JMA_useConsoleSinTable();

    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["expected"];
    const Json& tr = g["_translation"];

    J3DTransformInfo info;
    info.mScale.x = info.mScale.y = info.mScale.z = 1.0f;
    info.mTranslate.x = tr[0].as_f32();
    info.mTranslate.y = tr[1].as_f32();
    info.mTranslate.z = tr[2].as_f32();

    Counts n;
    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        info.mRotation.x = static_cast<s16>(row[0].as_int());
        info.mRotation.y = static_cast<s16>(row[1].as_int());
        info.mRotation.z = static_cast<s16>(row[2].as_int());
        const std::string src = row[12].str;
        const std::string at = "rot " + src + " (" + std::to_string(info.mRotation.x) + ","
                               + std::to_string(info.mRotation.y) + ","
                               + std::to_string(info.mRotation.z) + ") ";

        Mtx m;
        if (inject_fused) {
            fused_off_diagonals(info, m);
        } else {
            J3DGetTranslateRotateMtx(info, m);
        }

        for (int r = 0; r < 3; r++) {
            for (int col = 0; col < 3; col++) {
                REQUIRE_BITS(c, m[r][col], row[3 + r * 3 + col].as_f32(),
                             at + "m" + std::to_string(r) + std::to_string(col));
            }
        }
        // The translation column is constant, so it is checked against `_translation`.
        REQUIRE_BITS(c, m[0][3], info.mTranslate.x, at + "m03");
        REQUIRE_BITS(c, m[1][3], info.mTranslate.y, at + "m13");
        REQUIRE_BITS(c, m[2][3], info.mTranslate.z, at + "m23");

        n.rows++;
        if (src == "animated") {
            n.animated++;
        } else if (src == "axis_aligned") {
            n.axis_aligned++;
        }
    }
    return n;
}

}  // namespace

TWWE_TEST(the_joint_local_matrix_is_the_DOLs_unfused_spelling,
          "J3DGetTranslateRotateMtx disagrees with the DOL's arrangement on some rotation - a "
          "fused off-diagonal, a swapped operand, or a sin where the disassembly reads cos") {
    const Counts n = compare_all(c, false);
    c.note("rotations compared:  " + std::to_string(n.rows) + " x 12 columns");
    c.note("  from an animation: " + std::to_string(n.animated));
    c.note("  axis-aligned:      " + std::to_string(n.axis_aligned)
           + " (where the off-diagonals collapse and no fusion difference can appear)");
    c.note("oracle tier:         " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM, and a transcription gate rather than an independent one - the "
                             "expected rows are composed from the old sim's primitives, arranged "
                             "the way the disassembly reads"));
    REQUIRE_INT(c, n.rows, 30225, "every rotation in the corpus was compared");
}

TWWE_TEST(the_old_sims_fusion_really_does_change_the_answer_and_here_is_how_often,
          "the fused and unfused spellings have stopped disagreeing - which would mean either "
          "that the corpus lost the non-degenerate rotations, or that the ported body has been "
          "quietly reconciled with the old sim's inference") {
    // Counts how often the red control's injection is reachable.
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& rows = g["expected"];
    const Json& tr = g["_translation"];

    J3DTransformInfo info;
    info.mScale.x = info.mScale.y = info.mScale.z = 1.0f;
    info.mTranslate.x = tr[0].as_f32();
    info.mTranslate.y = tr[1].as_f32();
    info.mTranslate.z = tr[2].as_f32();

    int differing = 0, differing_animated = 0, differing_axis = 0, animated = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];
        info.mRotation.x = static_cast<s16>(row[0].as_int());
        info.mRotation.y = static_cast<s16>(row[1].as_int());
        info.mRotation.z = static_cast<s16>(row[2].as_int());
        const std::string src = row[12].str;
        if (src == "animated") {
            animated++;
        }

        Mtx plain, fused;
        J3DGetTranslateRotateMtx(info, plain);
        fused_off_diagonals(info, fused);
        bool differs = false;
        for (int r = 0; r < 3 && !differs; r++) {
            for (int col = 0; col < 3 && !differs; col++) {
                differs = bits(plain[r][col]) != bits(fused[r][col]);
            }
        }
        if (differs) {
            differing++;
            if (src == "animated") {
                differing_animated++;
            }
            if (src == "axis_aligned") {
                differing_axis++;
            }
        }
    }

    c.note("rotations where the old sim's fusion changes the matrix: "
           + std::to_string(differing) + " of " + std::to_string(rows.size()));
    c.note("  ...of those, ones an animation actually produces:      "
           + std::to_string(differing_animated) + " of " + std::to_string(animated));
    c.note("  ...of those, axis-aligned:                             "
           + std::to_string(differing_axis) + " (expected 0 - the off-diagonals collapse there)");

    REQUIRE_TRUE(c, differing_animated > 1000,
                 "the fusion changes the answer on rotations this game's own animations produce, "
                 "so the disagreement is not a corner case and the port's spelling matters");
    REQUIRE_INT(c, differing_axis, 0,
                "no axis-aligned rotation can tell the two spellings apart, which is what says "
                "the count above comes from real angles rather than from the degenerate rows");
}

TWWE_RED_CONTROL(red_the_old_sims_fused_off_diagonals,
                 "the four off-diagonals written as fmsubs/fmadds - one rounding - which is what "
                 "the old sim does, on a comment inferring MWCC's "
                 "codegen rather than disassembling it. The DOL is FUSED 0 on both overloads and "
                 "the port follows the DOL. This control is the old sim being wrong, kept red by "
                 "name so the two cannot be reconciled in the wrong direction") {
    compare_all(c, true);
}
