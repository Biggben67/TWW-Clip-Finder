// test_calc_pla.cpp - the PowerPC FP foundation, held to the console through cM3d_CalcPla.
//
// The game runs `frsqrte` inside PSVECMag inside cM3d_CalcPla, once per collision triangle at
// room load, and leaves the plane in `cBgW::pm_tri` where RAM can be read. So a stored plane
// normal is the smallest console oracle for the estimate path.
//
// Each row is three vertices fed to cM3d_CalcPla and the four f32 the game stored: 1,942 over six
// rooms, plus ten carried as bit patterns. Captured live.
//
// Five pieces of arithmetic a modern toolchain gets wrong by default, each a red control below:
//
//     cM3d_VectorProduct  ->  PSVECCrossProduct   asymmetric fusion: one product of each
//                                                 component is fused into the subtract, the
//                                                 other is rounded on its own
//     VECMag              ->  PSVECMag            frsqrte + one Newton step, not a square root
//     (inside PSVECMag)   ->  Force25Bit          Gekko rounds a single op's frC to 25 bits, and
//                                                 the estimate it squares has ~26
//     (inside PSVECMag)   ->  fnmsubs             the Newton step is fused
//     VECDotProduct       ->  PSVECDotProduct     x*x + y*y fused, + z*z not
//
// None is a contraction question, so `/fp:precise` and `-ffp-contract=off` do not catch them.
// `calc_pla_variant(..., Variant::None)` is held bit-identical to `cM3d_CalcPla` first, so the
// reds are about the port and not a local copy.

#include <cstdlib>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "SSystem/SComponent/c_m3d.h"
#include "engine/ppc_fp.h"
#include "engine/ps_vec.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;

//: The six room captures, in the order the manifest lists them.
const char* const kPlaneGoldens[] = {
    "kaze_r11_walls_ordered.json", "kaze_r11_floors.json",
    "ganona_r0_walls_ordered.json", "ganona_r0_floors.json",
    "ganonm_r0_walls_ordered.json", "ganonm_r0_floors.json",
};

struct Row {
    Vec v[3];
    Vec n;
    f32 d;
    std::string where;
};

/// Every poly of the six room captures, as (three verts in, plane out).
const std::vector<Row>& rows() {
    static std::vector<Row> all;
    if (!all.empty()) {
        return all;
    }
    for (const char* name : kPlaneGoldens) {
        const Json& g = tww_engine::testing::golden(name);
        const Json& polys = g["polys"];
        for (size_t i = 0; i < polys.size(); i++) {
            const Json& p = polys[i];
            Row r;
            for (int k = 0; k < 3; k++) {
                r.v[k].x = p["v"][k][0].as_f32();
                r.v[k].y = p["v"][k][1].as_f32();
                r.v[k].z = p["v"][k][2].as_f32();
            }
            r.n.x = p["n"][0].as_f32();
            r.n.y = p["n"][1].as_f32();
            r.n.z = p["n"][2].as_f32();
            r.d = p["d"].as_f32();
            r.where = std::string(name) + " poly " + std::to_string(p["poly"].as_int());
            all.push_back(r);
        }
    }
    return all;
}

/// `calc_pla_ram.json`, with hex f32 bit-pattern columns: ten polys with no decimal round-trip
/// between capture and comparison, separating a `strtod`/JSON fault from an arithmetic one.
float from_hex(const Json& j) {
    return tww_engine::testing::from_bits((uint32_t)std::strtoul(j.str.c_str(), nullptr, 16));
}

const std::vector<Row>& bit_rows() {
    static std::vector<Row> all;
    if (!all.empty()) {
        return all;
    }
    const Json& g = tww_engine::testing::golden("calc_pla_ram.json");
    static const char* const kV[3] = {"A", "B", "C"};
    for (size_t i = 0; i < g.size(); i++) {
        const Json& p = g[i];
        Row r;
        for (int k = 0; k < 3; k++) {
            r.v[k].x = from_hex(p[kV[k]][0]);
            r.v[k].y = from_hex(p[kV[k]][1]);
            r.v[k].z = from_hex(p[kV[k]][2]);
        }
        r.n.x = from_hex(p["n"][0]);
        r.n.y = from_hex(p["n"][1]);
        r.n.z = from_hex(p["n"][2]);
        r.d = from_hex(p["D"]);
        r.where = "calc_pla_ram.json poly " + std::to_string(p["poly"].as_int());
        all.push_back(r);
    }
    return all;
}

// ------------------------------------------------------------------- the variant harness

enum class Variant {
    None,            //: the ported pipeline, unchanged - the control
    NoForce25,       //: square the raw estimate without Gekko's 25-bit frC rounding
    NewtonUnfused,   //: `3.0f - esq*sq` as two roundings instead of one fnmsubs
    CorrectSqrt,     //: a correctly-rounded square root, which is what every x86 build gets
    CrossUnfused,    //: `(p*q) - (r*s)`, the symmetric spelling the decomp's C twin writes
    DotUnfused,      //: `((x*x) + (y*y)) + z*z`, three separate roundings
};

f32 mag(const Vec* v, Variant var) {
    const f32 xx = ppc::fmuls(v->x, v->x);
    const f32 yy = ppc::fmuls(v->y, v->y);
    const f32 sqmag = ppc::fadds(ppc::fmadds(v->z, v->z, xx), yy);
    if (sqmag == 0.0f) {
        return sqmag;
    }
    if (var == Variant::CorrectSqrt) {
        return (f32)std::sqrt((double)sqmag);
    }
    const double rmag = ppc::frsqrte(sqmag);
    const f32 nwork0 = var == Variant::NoForce25 ? (f32)(rmag * rmag)
                                                 : ppc::fmuls_fpr(rmag, rmag);
    const f32 nwork1 = ppc::fmuls_fpr(rmag, 0.5);
    const f32 refined = var == Variant::NewtonUnfused
                            ? ppc::fsubs(3.0f, ppc::fmuls(nwork0, sqmag))
                            : ppc::fnmsubs(nwork0, sqmag, 3.0f);
    return ppc::fmuls(sqmag, ppc::fmuls(refined, nwork1));
}

f32 dot(const Vec* a, const Vec* b, Variant var) {
    const f32 xx = ppc::fmuls(a->x, b->x);
    const f32 yy = ppc::fmuls(a->y, b->y);
    const f32 zz = ppc::fmuls(a->z, b->z);
    if (var == Variant::DotUnfused) {
        return ppc::fadds(ppc::fadds(xx, yy), zz);
    }
    return ppc::fadds(ppc::fmadds(a->x, b->x, yy), zz);
}

void cross(const Vec* a, const Vec* b, Vec* axb, Variant var) {
    f32 x, y, z;
    if (var == Variant::CrossUnfused) {
        x = ppc::fsubs(ppc::fmuls(a->y, b->z), ppc::fmuls(b->y, a->z));
        y = -ppc::fsubs(ppc::fmuls(a->x, b->z), ppc::fmuls(b->x, a->z));
        z = -ppc::fsubs(ppc::fmuls(a->y, b->x), ppc::fmuls(b->y, a->x));
    } else {
        x = ppc::fmsubs(a->y, b->z, ppc::fmuls(b->y, a->z));
        y = -ppc::fmsubs(a->x, b->z, ppc::fmuls(b->x, a->z));
        z = -ppc::fmsubs(a->y, b->x, ppc::fmuls(b->y, a->x));
    }
    axb->x = x;
    axb->y = y;
    axb->z = z;
}

/// `cM3d_CalcPla` with one piece swappable: the decomp's branch, its `1.0f / t`, its else-arm
/// zeroing.
void calc_pla_variant(const Vec* p0, const Vec* p1, const Vec* p2, Vec* pDst, f32* pT,
                      Variant var) {
    Vec v01, v02;
    PSVECSubtract(p1, p0, &v01);
    PSVECSubtract(p2, p0, &v02);
    cross(&v01, &v02, pDst, var);
    const f32 t = mag(pDst, var);
    if (std::fabs(t) >= 0.02f) {
        PSVECScale(pDst, pDst, 1.0f / t);
        *pT = -dot(pDst, p0, var);
    } else {
        pDst->y = 0.0f;
        *pT = 0.0f;
        pDst->z = 0.0f;
        pDst->x = 0.0f;
    }
}

/// How many of `rs` the variant gets wrong, reported by the red controls.
int wrong_count(const std::vector<Row>& rs, Variant var) {
    int bad = 0;
    for (const Row& r : rs) {
        Vec n;
        f32 d;
        calc_pla_variant(&r.v[0], &r.v[1], &r.v[2], &n, &d, var);
        if (tww_engine::testing::bits(n.x) != tww_engine::testing::bits(r.n.x) ||
            tww_engine::testing::bits(n.y) != tww_engine::testing::bits(r.n.y) ||
            tww_engine::testing::bits(n.z) != tww_engine::testing::bits(r.n.z) ||
            tww_engine::testing::bits(d) != tww_engine::testing::bits(r.d)) {
            bad++;
        }
    }
    return bad;
}

void check_rows(Case& c, const std::vector<Row>& rs) {
    for (const Row& r : rs) {
        Vec n;
        f32 d;
        cM3d_CalcPla(&r.v[0], &r.v[1], &r.v[2], &n, &d);
        REQUIRE_BITS(c, n.x, r.n.x, r.where + " nx");
        REQUIRE_BITS(c, n.y, r.n.y, r.where + " ny");
        REQUIRE_BITS(c, n.z, r.n.z, r.where + " nz");
        REQUIRE_BITS(c, d, r.d, r.where + " d");
    }
}

/// One red control's body: assert the variant matches the console, which it must not.
void expect_variant_matches_console(Case& c, Variant var, const char* what) {
    const int bad = wrong_count(rows(), var);
    c.note(std::string(what) + ": " + std::to_string(bad) + " of " +
           std::to_string(rows().size()) + " planes wrong");
    REQUIRE_INT(c, bad, 0, std::string("planes ") + what + " gets wrong");
}

}  // namespace

TWWE_TEST(calc_pla_is_bit_exact_on_console_planes,
          "the ported cM3d_CalcPla no longer reproduces the plane normals the game computed and "
          "stored, so the estimate class - frsqrte, Force25Bit, the fused Newton step - is not "
          "this hardware's") {
    REQUIRE_TRUE(c, rows().size() == 1942,
                 "the plane corpus is not the 1,942 rows the manifest copies - a corpus that "
                 "shrank silently would report a rate over a population nobody checked");
    check_rows(c, rows());
    c.note("1942 console planes over 6 rooms, 4 f32 each");
    // Credit the FP row here; the proc ledger cannot see a gate no replayed frame enters. Armed
    // only for green cases.
    tww_engine::testing::ledger_record_subsystem(
        "PowerPC FP", tww_engine::testing::Tier::Console,
        std::to_string(rows().size() + bit_rows().size()) +
            " plane(s), in 6 room(s), via cM3d_CalcPla");
}

TWWE_TEST(calc_pla_is_bit_exact_on_the_bit_pattern_capture,
          "cM3d_CalcPla disagrees with the capture whose columns are raw f32 bit patterns - so "
          "the disagreement is arithmetic and not a decimal round-trip through the JSON") {
    REQUIRE_TRUE(c, bit_rows().size() == 10, "calc_pla_ram.json no longer carries its ten polys");
    check_rows(c, bit_rows());
}

TWWE_TEST(the_variant_harness_is_the_ported_function,
          "the red controls below swap one piece of a local copy of the pipeline, and that copy "
          "has drifted from the ported cM3d_CalcPla - so what they are evidence about is the "
          "copy, not the port") {
    int differ = 0;
    for (const Row& r : rows()) {
        Vec a, b;
        f32 da, db;
        cM3d_CalcPla(&r.v[0], &r.v[1], &r.v[2], &a, &da);
        calc_pla_variant(&r.v[0], &r.v[1], &r.v[2], &b, &db, Variant::None);
        if (tww_engine::testing::bits(a.x) != tww_engine::testing::bits(b.x) ||
            tww_engine::testing::bits(a.y) != tww_engine::testing::bits(b.y) ||
            tww_engine::testing::bits(a.z) != tww_engine::testing::bits(b.z) ||
            tww_engine::testing::bits(da) != tww_engine::testing::bits(db)) {
            differ++;
        }
    }
    REQUIRE_INT(c, differ, 0, "rows where the variant harness and cM3d_CalcPla disagree");
    c.note("the harness reproduces cM3d_CalcPla on all " + std::to_string(rows().size()) +
           " rows, so the five red controls below are about the port");
}

TWWE_RED_CONTROL(red_force25_dropped_from_the_estimate_square,
                 "Gekko's 25-bit rounding of a single-precision op's frC operand, dropped. A "
                 "no-op for f32 operands, which is why it is easy to leave out - and not a no-op "
                 "for the ~26-bit frsqrte estimate that PSVECMag squares") {
    expect_variant_matches_console(c, Variant::NoForce25, "force25 dropped");
}

TWWE_RED_CONTROL(red_newton_step_unfused,
                 "PSVECMag's Newton refinement written as `3.0f - esq*sq`, two roundings, instead "
                 "of the one `fnmsubs` the asm block spells") {
    expect_variant_matches_console(c, Variant::NewtonUnfused, "Newton un-fused");
}

TWWE_RED_CONTROL(red_correctly_rounded_sqrt_instead_of_the_estimate,
                 "std::sqrt in place of frsqrte + Newton - which is what every x86 and ARM64 "
                 "build gets from the decomp's own C twin, silently, and what no build flag in "
                 "this project's CMakeLists has anything to say about") {
    expect_variant_matches_console(c, Variant::CorrectSqrt, "a correctly-rounded sqrt");
}

TWWE_RED_CONTROL(red_cross_product_lanes_unfused,
                 "the cross product as a symmetric `(p*q) - (r*s)`. PSVECCrossProduct fuses the "
                 "first product into the subtract and rounds the second on its own; the decomp's "
                 "C_VECCrossProduct - the arm a modern compiler picks - does not") {
    expect_variant_matches_console(c, Variant::CrossUnfused, "the cross lanes un-fused");
}

TWWE_RED_CONTROL(red_dot_product_unfused,
                 "the plane offset's dot product as three separate roundings. PSVECDotProduct "
                 "fuses x*x + y*y and leaves + z*z separate") {
    expect_variant_matches_console(c, Variant::DotUnfused, "the dot un-fused");
}
