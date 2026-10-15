// test_ps_inverse.cpp - PSMTXInverse (mtx.c:404) and ppc::fres, the Gekko's 12-bit reciprocal
// estimate, at 0 ULP against the old sim's fk.py:psmtx_inverse / quat.py:_fres (sim tier).
//
// x86 and ARM64 have no `fres`, so `1.0f / det` is a different function of the same argument; the
// red controls swap in that and the other shortcuts. The 4,096 sine-table sectors cover facings
// where R is not exactly orthonormal.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "engine/ppc_fp.h"
#include "engine/ps_mtx.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;

const char* const kGolden = "ps_inverse_oracle.json";

struct Row {
    std::string name;
    f32 src[3][4];
    int ret;
    bool has_inv;
    f32 inv[3][4];
};

const std::vector<Row>& rows() {
    static std::vector<Row> cached;
    if (!cached.empty()) {
        return cached;
    }
    const Json& cases = tww_engine::testing::golden(kGolden)["cases"];
    for (size_t i = 0; i < cases.size(); i++) {
        const Json& j = cases[i];
        Row r;
        r.name = j["name"].str;
        const Json& s = j["src"];
        for (int k = 0; k < 12; k++) {
            r.src[k / 4][k % 4] = s[k].as_f32();
        }
        r.ret = static_cast<int>(j["ret"].as_int());
        const Json& v = j["inv"];
        r.has_inv = !v.is_null();
        if (r.has_inv) {
            for (int k = 0; k < 12; k++) {
                r.inv[k / 4][k % 4] = v[k].as_f32();
            }
        }
        cached.push_back(r);
    }
    return cached;
}

//: The one substitution each red control makes; `None` reproduces the port.
enum class Variant {
    None,
    CorrectDivide,   //: recip = 1.0f / det - what every x86 and ARM64 build reaches for
    NewtonDropped,   //: the raw estimate, unrefined - 12 bits instead of 24
    Transpose,       //: R^-1 as R^T, which is right only at an axis-aligned facing
    TranslateUnfused //: the translation column as three separate roundings
};

/// A local copy of PSMTXInverse with one piece swappable, so the ported routine carries no test
/// mode. `the_variant_harness_is_the_ported_routine` holds the copy to it.
u32 inverse_variant(const f32 (*src)[4], MtxP inv, Variant var) {
    const f32 m00 = src[0][0], m01 = src[0][1], m02 = src[0][2], m03 = src[0][3];
    const f32 m10 = src[1][0], m11 = src[1][1], m12 = src[1][2], m13 = src[1][3];
    const f32 m20 = src[2][0], m21 = src[2][1], m22 = src[2][2], m23 = src[2][3];

    const f32 A00 = ppc::fmsubs(m11, m22, ppc::fmuls(m21, m12));
    const f32 B10 = ppc::fmsubs(m12, m20, ppc::fmuls(m22, m10));
    const f32 A01 = ppc::fmsubs(m21, m02, ppc::fmuls(m01, m22));
    const f32 B11 = ppc::fmsubs(m22, m00, ppc::fmuls(m02, m20));
    const f32 A02 = ppc::fmsubs(m01, m12, ppc::fmuls(m11, m02));
    const f32 B12 = ppc::fmsubs(m02, m10, ppc::fmuls(m12, m00));
    const f32 A20 = ppc::fmsubs(m10, m21, ppc::fmuls(m11, m20));
    const f32 A21 = ppc::fmsubs(m01, m20, ppc::fmuls(m00, m21));
    const f32 A22 = ppc::fmsubs(m00, m11, ppc::fmuls(m01, m10));

    const f32 det = ppc::fmadds(m20, A02, ppc::fmadds(m10, A01, ppc::fmuls(m00, A00)));
    if (det == 0.0f) {
        return 0;
    }

    f32 recip;
    if (var == Variant::CorrectDivide) {
        recip = 1.0f / det;
    } else if (var == Variant::NewtonDropped) {
        recip = (f32)ppc::fres((double)det);
    } else {
        const f32 est = (f32)ppc::fres((double)det);
        recip = ppc::fnmsubs(det, ppc::fmuls(est, est), ppc::fadds(est, est));
    }

    if (var == Variant::Transpose) {
        // Exact only where R is exactly orthonormal: the axis-aligned facings.
        inv[0][0] = m00; inv[0][1] = m10; inv[0][2] = m20;
        inv[1][0] = m01; inv[1][1] = m11; inv[1][2] = m21;
        inv[2][0] = m02; inv[2][1] = m12; inv[2][2] = m22;
    } else {
        inv[0][0] = ppc::fmuls(A00, recip);
        inv[0][1] = ppc::fmuls(A01, recip);
        inv[0][2] = ppc::fmuls(A02, recip);
        inv[1][0] = ppc::fmuls(B10, recip);
        inv[1][1] = ppc::fmuls(B11, recip);
        inv[1][2] = ppc::fmuls(B12, recip);
        inv[2][0] = ppc::fmuls(A20, recip);
        inv[2][1] = ppc::fmuls(A21, recip);
        inv[2][2] = ppc::fmuls(A22, recip);
    }

    for (int i = 0; i < 3; i++) {
        if (var == Variant::TranslateUnfused) {
            inv[i][3] = -(inv[i][0] * m03 + inv[i][1] * m13 + inv[i][2] * m23);
        } else {
            inv[i][3] = ppc::fnmadds(inv[i][2], m23,
                                     ppc::fmadds(inv[i][1], m13, ppc::fmuls(inv[i][0], m03)));
        }
    }
    return 1;
}

/// How many of `rows()` a variant gets wrong. `population` excludes the singular row, which has no
/// expected inverse.
int wrong_count(Variant var, int* population) {
    int bad = 0;
    *population = 0;
    for (const Row& r : rows()) {
        if (!r.has_inv) {
            continue;
        }
        (*population)++;
        Mtx got;
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                got[i][j] = 0.0f;
            }
        }
        inverse_variant(r.src, got, var);
        bool differs = false;
        for (int i = 0; i < 3 && !differs; i++) {
            for (int j = 0; j < 4 && !differs; j++) {
                differs = tww_engine::testing::bits(got[i][j]) !=
                          tww_engine::testing::bits(r.inv[i][j]);
            }
        }
        if (differs) {
            bad++;
        }
    }
    return bad;
}

void expect_variant_matches_the_oracle(Case& c, Variant var, const char* what) {
    int population = 0;
    const int bad = wrong_count(var, &population);
    c.note(std::string(what) + ": " + std::to_string(bad) + " wrong and " +
           std::to_string(population - bad) + " right, of " + std::to_string(population) +
           " compared");
    REQUIRE_TRUE(c, population == 4387,
                 "the control ran over the whole compared population - a variant scored on a "
                 "corpus that shrank would report a rate nobody could read");
    REQUIRE_INT(c, bad, 0, std::string("matrices ") + what + " gets wrong");
}

}  // namespace

TWWE_TEST(the_inverse_reproduces_the_old_sim,
          "PSMTXInverse disagrees with the old sim's psmtx_inverse on some matrix - so either the "
          "cofactor spelling, the fused translation column, or the `fres` table and its single "
          "Newton step is not this hardware's") {
    REQUIRE_INT(c, (int)rows().size(), 4388,
                "the matrix corpus is not the 4,388 rows the producer emits - a corpus that "
                "shrank silently would report a rate over a population nobody checked");
    int compared = 0;
    int live = 0;
    int sector = 0;
    for (const Row& r : rows()) {
        Mtx got;
        // Sentinel fill, so the `ret == 0` case can show the routine wrote nothing.
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                got[i][j] = -777.0f;
            }
        }
        const u32 ret = PSMTXInverse(r.src, got);
        REQUIRE_INT(c, (int)ret, r.ret, r.name + ": return value");
        if (!r.has_inv) {
            // Singular: the asm's `bne skip_return` takes the early `blr` before writing anything.
            for (int i = 0; i < 3; i++) {
                for (int j = 0; j < 4; j++) {
                    REQUIRE_BITS(c, got[i][j], -777.0f,
                                 r.name + ": det == 0 leaves the output untouched");
                }
            }
            continue;
        }
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                REQUIRE_BITS(c, got[i][j], r.inv[i][j],
                             r.name + " m" + std::to_string(i) + std::to_string(j));
            }
        }
        compared++;
        if (r.name.compare(0, 5, "live/") == 0) { live++; }
        if (r.name.compare(0, 7, "sector/") == 0) { sector++; }
    }
    c.note("matrices compared:   " + std::to_string(compared) + " x 12 f32");
    c.note("  from live capture: " + std::to_string(live));
    c.note("  sine-table sector: " + std::to_string(sector));
    c.note("oracle tier:         " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM - the regression tier: this says the C++ reproduces the "
                             "Python, not that the inverse is right"));
    REQUIRE_INT(c, live, 282, "every frame of both live captures contributed a matrix");
    REQUIRE_INT(c, sector, 4096, "every sector of the sine table contributed a matrix");
}

TWWE_TEST(the_estimate_is_not_the_answer,
          "`fres` returns something within a ULP of 1/x, so the Newton step below it would be "
          "decoration and the red control that drops it would be green") {
    // Pins that the raw estimate differs from the refined one, so the Newton control discriminates.
    int seed_differs = 0;
    for (const Row& r : rows()) {
        if (!r.has_inv) {
            continue;
        }
        Mtx a, b;
        inverse_variant(r.src, a, Variant::None);
        inverse_variant(r.src, b, Variant::NewtonDropped);
        if (tww_engine::testing::bits(a[0][0]) != tww_engine::testing::bits(b[0][0])) {
            seed_differs++;
        }
    }
    c.note("matrices where the raw estimate differs from the refined one in m00: " +
           std::to_string(seed_differs) + " of 4387 compared");
    REQUIRE_TRUE(c, seed_differs > 4000,
                 "the unrefined estimate differs from the refined one almost everywhere - so the "
                 "Newton step is load-bearing and its red control discriminates");
}

TWWE_TEST(the_divide_and_the_estimate_agree_on_every_matrix_this_caller_produces,
          "a correctly-rounded divide is caught by more than one matrix of this corpus, or by "
          "none - either way the note below is stale and the reader is owed the new number") {
    // The divide control is caught only by `edge/aniso` (det 7.109375). Every world base has det
    // within a few ULP of 1.0, where fres + one Newton step and `1.0f / det` agree, so the port's
    // one caller, `mDoMtx_stack_c::inverse()`, cannot tell them apart.
    int divide_wrong = 0;
    int unit_det = 0;
    std::string first;
    for (const Row& r : rows()) {
        if (!r.has_inv) {
            continue;
        }
        Mtx a, b;
        inverse_variant(r.src, a, Variant::None);
        inverse_variant(r.src, b, Variant::CorrectDivide);
        bool same = true;
        for (int i = 0; i < 3 && same; i++) {
            for (int j = 0; j < 4 && same; j++) {
                same = tww_engine::testing::bits(a[i][j]) == tww_engine::testing::bits(b[i][j]);
            }
        }
        if (!same) {
            divide_wrong++;
            if (first.empty()) {
                first = r.name;
            }
        }
        // The determinant, recomputed the routine's way.
        const f32 A00 = ppc::fmsubs(r.src[1][1], r.src[2][2], ppc::fmuls(r.src[2][1], r.src[1][2]));
        const f32 A01 = ppc::fmsubs(r.src[2][1], r.src[0][2], ppc::fmuls(r.src[0][1], r.src[2][2]));
        const f32 A02 = ppc::fmsubs(r.src[0][1], r.src[1][2], ppc::fmuls(r.src[1][1], r.src[0][2]));
        const f32 det = ppc::fmadds(r.src[2][0], A02,
                                    ppc::fmadds(r.src[1][0], A01, ppc::fmuls(r.src[0][0], A00)));
        if (det == 1.0f) {
            unit_det++;
        }
    }
    // Only some world bases hit det exactly 1.0; the rest miss by a few ULP (`c*c + s*s` at a
    // non-axis facing), still one neighbourhood of the fres table.
    c.note("matrices with det exactly 1.0: " + std::to_string(unit_det) + " of 4387; the rest of "
           "the world bases sit a few ULP off it, and none of them separates the two");
    c.note("matrices the exact divide gets wrong: " + std::to_string(divide_wrong) +
           ", first " + first);
    REQUIRE_INT(c, divide_wrong, 1,
                "the exact divide is caught by exactly one matrix, and it is a hand-built edge");
    REQUIRE_TRUE(c, first == "edge/aniso",
                 "the one matrix that catches it is edge/aniso - if this moved, the corpus's "
                 "coverage of the fres table moved with it");
}

TWWE_TEST(the_variant_harness_is_the_ported_routine,
          "the red controls below swap one piece of a local copy of PSMTXInverse, and that copy "
          "has drifted from the ported routine - so what they are evidence about is the copy, "
          "not the port") {
    int differ = 0;
    for (const Row& r : rows()) {
        Mtx a, b;
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                a[i][j] = b[i][j] = -777.0f;
            }
        }
        const u32 ra = PSMTXInverse(r.src, a);
        const u32 rb = inverse_variant(r.src, b, Variant::None);
        bool same = (ra == rb);
        for (int i = 0; i < 3 && same; i++) {
            for (int j = 0; j < 4 && same; j++) {
                same = tww_engine::testing::bits(a[i][j]) == tww_engine::testing::bits(b[i][j]);
            }
        }
        if (!same) {
            differ++;
        }
    }
    REQUIRE_INT(c, differ, 0, "matrices where the variant harness and PSMTXInverse disagree");
    c.note("the harness reproduces PSMTXInverse on all " + std::to_string(rows().size()) +
           " matrices, so the four red controls below are about the port");
}

TWWE_RED_CONTROL(red_a_correctly_rounded_divide_instead_of_the_estimate,
                 "`1.0f / det` in place of fres + one Newton step - which is what every x86 and "
                 "ARM64 build gets from the decomp's own C twin, silently, and what no build flag "
                 "in this project's CMakeLists has anything to say about") {
    expect_variant_matches_the_oracle(c, Variant::CorrectDivide, "a correctly-rounded divide");
}

TWWE_RED_CONTROL(red_the_newton_step_dropped,
                 "the raw `fres` estimate used as the reciprocal. It is ~12 bits where the result "
                 "is 24, so this is the control that says the refinement is arithmetic and not a "
                 "flourish") {
    expect_variant_matches_the_oracle(c, Variant::NewtonDropped, "the Newton step dropped");
}

TWWE_RED_CONTROL(red_the_inverse_as_a_transpose,
                 "R^-1 written as R^T, which is the shortcut a reader reaches for and is right at "
                 "every axis-aligned facing. `c*c + s*s` is not exactly 1.0 in f32 at any other "
                 "BAM, so this is also the control that says the 4,096-sector sweep earns its "
                 "place: a gate built on a straight walk would be green here") {
    expect_variant_matches_the_oracle(c, Variant::Transpose, "the inverse as a transpose");
}

TWWE_RED_CONTROL(red_the_translation_column_unfused,
                 "the translation column as `-(a*m03 + b*m13 + c*m23)`, three separate roundings, "
                 "instead of the `ps_nmadd(ps_madd(ps_mul))` chain the asm block spells") {
    expect_variant_matches_the_oracle(c, Variant::TranslateUnfused, "the translation un-fused");
}
