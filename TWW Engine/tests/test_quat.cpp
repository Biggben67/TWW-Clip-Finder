// test_quat.cpp - the three quaternion routines the skeleton is posed through, at 0 ULP.
//
//     JMAEulerToQuat    JMath.cpp:41. No fused ops: every term is a separate rounding.
//     JMAQuatLerp       JMath.cpp:59. Computes in double and does not renormalise.
//     PSMTXQuat         mtx.c:1016, carried asm; one of the DOL's three `fres` sites.
//
// mDoExt_MtxCalcAnmBlendTbl::calc chains them, ending in `MTXQuat(mtx, &quat3)` per joint.
//
// The golden (quat_oracle.json) comes from the old sim's quat.py, whose leg chain is bit-exact
// against the console's anmMtx. Because JMAQuatLerp does not renormalise, PSMTXQuat's denominator
// is often below 1.0, so an exact divide differs from `fres` + Newton on many rows here.
// The oracle's lerp dot is fused and the DOL's is not; the port follows the DOL, and a case
// counts the rows where that could change the sign.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "framework/runner.h"

#include "dolphin/types.h"
#include "engine/ppc_fp.h"
#include "engine/ps_mtx.h"
#include "JSystem/JMath/JMath.h"
#include "JSystem/JMath/JMATrigonometric.h"

namespace {

using tww_engine::testing::Case;
using tww_engine::testing::Json;
using tww_engine::testing::bits;

const char* const kGolden = "quat_oracle.json";

// Local copies of the three routines, each control one changed line; a red control below checks
// the copies match the shipped bodies.

enum Variant {
    Shipped,
    EulerXYFused,        //: JMAEulerToQuat's x term fused
    LerpInSingle,        //: JMAQuatLerp in f32 instead of double
    LerpNeverNegates,    //: JMAQuatLerp's `dot < 0.0` branch dropped
    QuatExactDivide,     //: PSMTXQuat with 2.0f/denom instead of fres + one Newton step
    QuatNewtonDropped,   //: PSMTXQuat with the estimate used raw
    QuatTwoFolded,       //: the multiply by 2.0 folded into the Newton step instead of after it
};

void euler_to_quat(s16 x, s16 y, s16 z, Quaternion* out, Variant v) {
    f32 cos_0 = JMASCos(x / 2);
    f32 cos_1 = JMASCos(y / 2);
    f32 cos_2 = JMASCos(z / 2);
    f32 sin_0 = JMASSin(x / 2);
    f32 sin_1 = JMASSin(y / 2);
    f32 sin_2 = JMASSin(z / 2);

    f32 c1_c2 = cos_1 * cos_2;
    f32 s1_s2 = sin_1 * sin_2;

    out->w = (cos_0 * c1_c2) + (sin_0 * s1_s2);
    if (v == EulerXYFused) {
        // sin_0*c1_c2 - cos_0*s1_s2 as one rounding.
        out->x = ppc::fmsubs(sin_0, c1_c2, ppc::fmuls(cos_0, s1_s2));
    } else {
        out->x = (sin_0 * c1_c2) - (cos_0 * s1_s2);
    }
    out->y = (cos_2 * (cos_0 * sin_1)) + (sin_2 * (sin_0 * cos_1));
    out->z = (sin_2 * (cos_0 * cos_1)) - (cos_2 * (sin_0 * sin_1));
}

void quat_lerp(Quaternion* a, Quaternion* b, f32 t, Quaternion* out, Variant v) {
    Quaternion temp;

    f32 dot = (a->x * b->x) + (a->y * b->y) + (a->z * b->z) + (a->w * b->w);
    if (dot < 0.0 && v != LerpNeverNegates) {
        temp.x = -b->x;
        temp.y = -b->y;
        temp.z = -b->z;
        temp.w = -b->w;
    } else {
        temp.x = b->x;
        temp.y = b->y;
        temp.z = b->z;
        temp.w = b->w;
    }

    if (v == LerpInSingle) {
        const f32 om = 1.0f - t;
        out->x = om * a->x + t * temp.x;
        out->y = om * a->y + t * temp.y;
        out->z = om * a->z + t * temp.z;
        out->w = om * a->w + t * temp.w;
        return;
    }
    out->x = (1.0 - t) * a->x + (f64)t * temp.x;
    out->y = (1.0 - t) * a->y + (f64)t * temp.y;
    out->z = (1.0 - t) * a->z + (f64)t * temp.z;
    out->w = (1.0 - t) * a->w + (f64)t * temp.w;
}

void psmtx_quat(MtxP m, const Quaternion* q, Variant v) {
    const f32 x = q->x, y = q->y, z = q->z, w = q->w;
    const f32 c_one = 1.0f;
    const f32 c_zero = ppc::fsubs(c_one, c_one);
    const f32 c_two = ppc::fadds(c_one, c_one);

    const f32 xx = ppc::fmuls(x, x);
    const f32 yy = ppc::fmuls(y, y);
    const f32 zz = ppc::fmuls(z, z);
    const f32 ww = ppc::fmuls(w, w);

    const f32 zz_xx = ppc::fmadds(z, z, xx);
    const f32 ww_yy = ppc::fmadds(w, w, yy);
    const f32 denom = ppc::fadds(zz_xx, ww_yy);

    const f32 yw = ppc::fmuls(y, w);
    const f32 xw = ppc::fmuls(x, w);

    f32 s;
    if (v == QuatExactDivide) {
        s = ppc::fdivs(c_two, denom);
    } else if (v == QuatNewtonDropped) {
        s = ppc::fmuls((f32)ppc::fres((double)denom), c_two);
    } else if (v == QuatTwoFolded) {
        const f32 est = (f32)ppc::fres((double)denom);
        s = ppc::fmuls(ppc::fmuls(est, c_two), ppc::fnmsubs(denom, est, c_two));
    } else {
        const f32 est = (f32)ppc::fres((double)denom);
        s = ppc::fmuls(ppc::fmuls(est, ppc::fnmsubs(denom, est, c_two)), c_two);
    }

    const f32 zz_yy = ppc::fadds(zz, yy);
    const f32 zw = ppc::fmuls(z, w);
    const f32 xx_yy = ppc::fadds(xx, yy);

    const f32 xy_plus_zw = ppc::fmadds(x, y, zw);
    const f32 xy_minus_zw = ppc::fmsubs(x, y, zw);

    const f32 xz_plus_yw = ppc::fmadds(x, z, yw);
    const f32 yz_plus_xw = ppc::fmadds(y, z, xw);
    const f32 xz_minus_yw = ppc::fnmsubs(yw, c_two, xz_plus_yw);
    const f32 yz_minus_xw = ppc::fnmsubs(xw, c_two, yz_plus_xw);

    m[0][0] = ppc::fnmsubs(zz_yy, s, c_one);
    m[0][1] = ppc::fmuls(xy_minus_zw, s);
    m[0][2] = ppc::fmuls(xz_plus_yw, s);
    m[0][3] = c_zero;
    m[1][0] = ppc::fmuls(xy_plus_zw, s);
    m[1][1] = ppc::fnmsubs(zz_xx, s, c_one);
    m[1][2] = ppc::fmuls(yz_minus_xw, s);
    m[1][3] = c_zero;
    m[2][0] = ppc::fmuls(xz_minus_yw, s);
    m[2][1] = ppc::fmuls(yz_plus_xw, s);
    m[2][2] = ppc::fnmsubs(xx_yy, s, c_one);
    m[2][3] = c_zero;
}

// ---------------------------------------------------------------------------------------------

struct Counts {
    int euler = 0;
    int lerp = 0;
    int mtx = 0;
};

Quaternion quat_of(const Json& row, int base) {
    Quaternion q;
    q.x = row[base + 0].as_f32();
    q.y = row[base + 1].as_f32();
    q.z = row[base + 2].as_f32();
    q.w = row[base + 3].as_f32();
    return q;
}

/// Every comparison this file makes, at one `Variant`. `Shipped` calls the real bodies; anything
/// else calls the local copies, so a control is the same traversal with one line changed.
Counts compare_all(Case& c, Variant v) {
    const Json& g = tww_engine::testing::golden(kGolden);
    Counts n;

    const Json& eu = g["euler"];
    for (size_t i = 0; i < eu.size(); i++) {
        const Json& row = eu[i];
        const s16 rx = static_cast<s16>(row[0].as_int());
        const s16 ry = static_cast<s16>(row[1].as_int());
        const s16 rz = static_cast<s16>(row[2].as_int());
        const std::string at = "euler " + row[7].str + " ("
                               + std::to_string(rx) + "," + std::to_string(ry) + ","
                               + std::to_string(rz) + ") ";
        Quaternion q;
        if (v == Shipped) {
            JMAEulerToQuat(rx, ry, rz, &q);
        } else {
            euler_to_quat(rx, ry, rz, &q, v);
        }
        REQUIRE_BITS(c, q.w, row[3].as_f32(), at + "w");
        REQUIRE_BITS(c, q.x, row[4].as_f32(), at + "x");
        REQUIRE_BITS(c, q.y, row[5].as_f32(), at + "y");
        REQUIRE_BITS(c, q.z, row[6].as_f32(), at + "z");
        n.euler++;
    }

    const Json& lp = g["lerp"];
    for (size_t i = 0; i < lp.size(); i++) {
        const Json& row = lp[i];
        Quaternion a = quat_of(row, 0);
        Quaternion b = quat_of(row, 4);
        const f32 t = row[8].as_f32();
        const std::string at = "lerp " + row[13].str + " @ t "
                               + std::to_string(t) + " ";
        Quaternion out;
        if (v == Shipped) {
            JMAQuatLerp(&a, &b, t, &out);
        } else {
            quat_lerp(&a, &b, t, &out, v);
        }
        REQUIRE_BITS(c, out.x, row[9].as_f32(), at + "x");
        REQUIRE_BITS(c, out.y, row[10].as_f32(), at + "y");
        REQUIRE_BITS(c, out.z, row[11].as_f32(), at + "z");
        REQUIRE_BITS(c, out.w, row[12].as_f32(), at + "w");
        n.lerp++;
    }

    const Json& mt = g["mtx"];
    for (size_t i = 0; i < mt.size(); i++) {
        const Json& row = mt[i];
        const Quaternion q = quat_of(row, 0);
        const std::string at = "mtx " + row[17].str + " ";
        Mtx m;
        if (v == Shipped) {
            PSMTXQuat(m, &q);
        } else {
            psmtx_quat(m, &q, v);
        }
        for (int r = 0; r < 3; r++) {
            for (int col = 0; col < 4; col++) {
                REQUIRE_BITS(c, m[r][col], row[4 + r * 4 + col].as_f32(),
                             at + "m" + std::to_string(r) + std::to_string(col));
            }
        }
        n.mtx++;
    }
    return n;
}

}  // namespace

TWWE_TEST(the_three_quaternion_routines_reproduce_the_old_sim,
          "JMAEulerToQuat, JMAQuatLerp or PSMTXQuat disagrees with the old sim on some "
          "angle, blend or quaternion - or the `fres` table under the matrix routine is not the "
          "Gekko's") {
    const Counts n = compare_all(c, Shipped);
    c.note("euler triples:  " + std::to_string(n.euler) + " x 4 columns");
    c.note("lerps:          " + std::to_string(n.lerp) + " x 4 columns");
    c.note("matrices:       " + std::to_string(n.mtx) + " x 12 columns");
    c.note("oracle tier:    " +
           std::string(tww_engine::testing::golden_tier(kGolden) ==
                               tww_engine::testing::Tier::Console
                           ? "CONSOLE"
                           : "SIM - the regression tier, though this oracle is validated "
                             "downstream against the live anmMtx"));
    REQUIRE_INT(c, n.euler, 20589, "every euler row was compared");
    REQUIRE_INT(c, n.mtx, 5664, "every quaternion row was compared");
}

TWWE_TEST(the_exact_divide_is_wrong_on_this_call_sites_own_population,
          "the `fres` carry has become unfalsifiable again - a correctly-rounded divide agrees "
          "with the estimate on this whole corpus, which would mean either that the table is not "
          "being read or that the population lost the denominators that are not 1.0") {
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& mt = g["mtx"];
    int wrong_all = 0, wrong_single = 0, single = 0, blended = 0, below_one = 0;

    for (size_t i = 0; i < mt.size(); i++) {
        const Json& row = mt[i];
        const Quaternion q = quat_of(row, 0);
        const std::string src = row[17].str;
        const bool is_single = src.rfind("single", 0) == 0;
        if (is_single) {
            single++;
        } else if (src.rfind("blend", 0) == 0) {
            blended++;
        }
        if (row[16].as_f32() < 1.0f) {
            below_one++;
        }

        Mtx shipped, divided;
        psmtx_quat(shipped, &q, Shipped);
        psmtx_quat(divided, &q, QuatExactDivide);
        bool differs = false;
        for (int r = 0; r < 3 && !differs; r++) {
            for (int col = 0; col < 4 && !differs; col++) {
                differs = bits(shipped[r][col]) != bits(divided[r][col]);
            }
        }
        if (differs) {
            wrong_all++;
            if (is_single) {
                wrong_single++;
            }
        }
    }

    c.note("quaternions:                       " + std::to_string(mt.size()));
    c.note("  single-animation:                " + std::to_string(single));
    c.note("  blended (JMAQuatLerp, no renorm):" + std::to_string(blended));
    c.note("  denominator below 1.0:           " + std::to_string(below_one));
    c.note("an exact 2.0f/denom is wrong on:   " + std::to_string(wrong_all));
    c.note("  ...of which single-animation:    " + std::to_string(wrong_single));

    // At a denominator of exactly 1.0 (mDoMtx_stack_c::inverse(), test_ps_inverse.cpp) the
    // estimate and a divide agree. Here even single-animation norms are a few ULP off 1.0, so
    // both blended and single rows must catch the divide.
    REQUIRE_TRUE(c, blended > 1000,
                 "the corpus still holds the blended quaternions - the population whose "
                 "denominator is furthest from 1.0, and the one that reads the table's high "
                 "indices at all");
    REQUIRE_TRUE(c, wrong_all > 100,
                 "a correctly-rounded divide is wrong on more than a handful of these, so the "
                 "`fres` carry is doing work a compiler's own divide would get wrong");
    REQUIRE_TRUE(c, wrong_single > 0 && wrong_all - wrong_single > 0,
                 "both populations catch it - so this call site's lift over "
                 "test_ps_inverse.cpp's limit does not depend on the blend, and a future corpus "
                 "that lost the blended rows would still be able to see the table");
}

TWWE_TEST(the_lerps_dot_is_spelled_the_DOLs_way_and_the_corpus_says_what_that_costs,
          "the fused and unfused dot products disagree about the sign on some row - in which "
          "case the port and its oracle answer different quaternions there, and the count below "
          "stops being 0") {
    // The oracle's dot is fused and the DOL's is not; it only feeds `dot < 0.0`, so only a sign
    // flip could change an answer.
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& lp = g["lerp"];
    int sign_differs = 0;
    for (size_t i = 0; i < lp.size(); i++) {
        const Json& row = lp[i];
        const Quaternion a = quat_of(row, 0);
        const Quaternion b = quat_of(row, 4);
        const f32 plain = (a.x * b.x) + (a.y * b.y) + (a.z * b.z) + (a.w * b.w);
        const f32 fused = ppc::fmadds(a.w, b.w,
                              ppc::fmadds(a.z, b.z,
                                  ppc::fmadds(a.y, b.y, ppc::fmuls(a.x, b.x))));
        if ((plain < 0.0f) != (fused < 0.0f)) {
            sign_differs++;
        }
    }
    c.note("rows where the fused and unfused dot disagree about the sign: "
           + std::to_string(sign_differs) + " of " + std::to_string(lp.size()));
    REQUIRE_INT(c, sign_differs, 0,
                "no row in this corpus can tell the port's dot from its oracle's. If this ever "
                "fires, the port is right - the DOL's body is FUSED 0 - and the golden's affected "
                "rows are the oracle's, not a regression");
}

TWWE_RED_CONTROL(red_the_variant_harness_is_not_the_ported_routines,
                 "claims the local copies the controls mutate differ from the shipped bodies. It "
                 "must fail: if it passed, every control below would be evidence about a "
                 "different function than the one this port ships") {
    // Inverted: it asserts a difference, so the copies matching makes it red.
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& mt = g["mtx"];
    int same = 0;
    for (size_t i = 0; i < mt.size(); i++) {
        const Quaternion q = quat_of(mt[i], 0);
        Mtx shipped, local;
        PSMTXQuat(shipped, &q);
        psmtx_quat(local, &q, Shipped);
        bool identical = true;
        for (int r = 0; r < 3; r++) {
            for (int col = 0; col < 4; col++) {
                identical = identical && bits(shipped[r][col]) == bits(local[r][col]);
            }
        }
        if (identical) {
            same++;
        }
    }
    const Json& eu = g["euler"];
    for (size_t i = 0; i < eu.size(); i++) {
        const s16 rx = static_cast<s16>(eu[i][0].as_int());
        const s16 ry = static_cast<s16>(eu[i][1].as_int());
        const s16 rz = static_cast<s16>(eu[i][2].as_int());
        Quaternion a, b;
        JMAEulerToQuat(rx, ry, rz, &a);
        euler_to_quat(rx, ry, rz, &b, Shipped);
        if (bits(a.w) == bits(b.w) && bits(a.x) == bits(b.x) &&
            bits(a.y) == bits(b.y) && bits(a.z) == bits(b.z)) {
            same++;
        }
    }
    REQUIRE_INT(c, same, 0,
                "the local copies reproduce the shipped bodies on every row, which is what has "
                "to be true and what makes this control red");
}

TWWE_RED_CONTROL(red_the_euler_x_term_fused,
                 "JMAEulerToQuat's x written as one fused `sin0*c1c2 - cos0*s1s2` instead of two "
                 "separately-rounded products. The DOL's body is FUSED 0 over 50 instructions. "
                 "This is not hypothetical - the old sim shipped exactly this and it left joint "
                 "34 a ULP off, which leaked out to the planted foot toe") {
    compare_all(c, EulerXYFused);
}

TWWE_RED_CONTROL(red_the_lerp_in_single_precision,
                 "JMAQuatLerp's four components computed in f32. The decomp writes `(1.0 - t)` "
                 "as a double literal and `(f64)t` as an explicit widening, so each component is "
                 "a double expression rounded once on the store - tidying it to f32 rounds twice "
                 "and is a different number") {
    compare_all(c, LerpInSingle);
}

TWWE_RED_CONTROL(red_the_lerp_never_negates_b,
                 "JMAQuatLerp's `dot < 0.0` branch dropped, so b is interpolated toward as given "
                 "instead of along the short arc. It is right on every pair whose dot is already "
                 "positive, which at small blend steps between adjacent frames is most of them") {
    compare_all(c, LerpNeverNegates);
}

TWWE_RED_CONTROL(red_a_correctly_rounded_divide_instead_of_the_estimate,
                 "PSMTXQuat's scale as `2.0f / denom` instead of `fres` plus one Newton step - "
                 "which is what an x86 build gives you by default. It is right wherever the "
                 "denominator is close enough to 1.0, which is every single-animation pose, and "
                 "the blended ones are what catch it") {
    compare_all(c, QuatExactDivide);
}

TWWE_RED_CONTROL(red_the_newton_step_dropped,
                 "PSMTXQuat using the raw `fres` estimate, which carries about 12 bits where the "
                 "result is 24 wide") {
    compare_all(c, QuatNewtonDropped);
}

TWWE_TEST(the_scale_two_is_exact_so_where_it_multiplies_is_copied_and_not_gated,
          "multiplying by 2.0 has stopped being exact somewhere in this corpus - which would mean "
          "a quaternion whose scale overflows or falls into the denormals, and the placement of "
          "`fmuls scale, scale, c_two` would then be a real arithmetic choice rather than a "
          "spelling") {
    // Multiplying by 2.0 is exact short of overflow or denormals, so where the asm's
    // `fmuls scale, scale, c_two` sits cannot change a result; with denominators 0.0625 to 86 no
    // row here can tell. The port keeps the asm's order.
    const Json& g = tww_engine::testing::golden(kGolden);
    const Json& mt = g["mtx"];
    int identical = 0;
    f32 lo = 0.0f, hi = 0.0f;
    for (size_t i = 0; i < mt.size(); i++) {
        const Quaternion q = quat_of(mt[i], 0);
        const f32 denom = mt[i][16].as_f32();
        if (i == 0 || denom < lo) { lo = denom; }
        if (i == 0 || denom > hi) { hi = denom; }
        Mtx shipped, folded;
        psmtx_quat(shipped, &q, Shipped);
        psmtx_quat(folded, &q, QuatTwoFolded);
        bool same = true;
        for (int r = 0; r < 3; r++) {
            for (int col = 0; col < 4; col++) {
                same = same && bits(shipped[r][col]) == bits(folded[r][col]);
            }
        }
        if (same) {
            identical++;
        }
    }
    c.note("denominators in this corpus: " + std::to_string(lo) + " to " + std::to_string(hi));
    c.note("rows where folding the x2 into the Newton step changes nothing: "
           + std::to_string(identical) + " of " + std::to_string(mt.size()));
    REQUIRE_INT(c, identical, static_cast<int>(mt.size()),
                "every row agrees, so the x2's placement is copied rather than gated - inherited "
                "as a limit, not read as a green bar");
}
