// ppc_fp.h - Gekko/Broadway (PPC 750CL) single-precision arithmetic, on x86-64 and ARM64.
//
// Every op is a named function so a call site states which instruction the DOL runs. That states
// intent; it does not enforce it, because inlining lets the compiler fuse two calls together.
//
// `(float)((double)a*(double)b + (double)c)` is exactly `fmadds`: an f32*f32 product is exact in
// f64, and one f64 rounding then one f32 rounding equals a single f32 rounding when the
// intermediate has >= 2p+2 = 50 bits (Boldo/Melquiond). Contracting the double expression into a
// double FMA cannot change it either, since the product is already exact.
//
// Build contract (not self-enforcing):
//
//   gcc / clang : -ffp-contract=off          and never -ffast-math / -Ofast
//   MSVC        : /fp:precise (the default)  and never /fp:fast
//
// Fused ops across the port with -mfma forced:
//
//                            g++ 13.3.0   clang 18.1.3
//   -ffp-contract=off             0            0        <- what CMakeLists sets
//   no flag at all               23            0
//   -ffp-contract=fast           23           21
//
// gcc's default contracts across inlined calls; clang's `on` contracts only within one
// expression. FMA is baseline on ARM64, so an ARM64 build always has it available.

#ifndef TWW_PPC_FP_H
#define TWW_PPC_FP_H

#include <cstdint>
#include <cstring>
#include <limits>

#if defined(__FAST_MATH__)
#error "ppc_fp.h: -ffast-math/-Ofast reassociates and contracts float arithmetic. 0 ULP is impossible under it."
#endif
#if defined(_M_FP_FAST)
#error "ppc_fp.h: /fp:fast contracts and reassociates. Build with /fp:precise."
#endif
// Standard C pragma; clang honours it. GCC ignores it and MSVC warns C4068 on it (hence the flag).
#if defined(__clang__)
#pragma STDC FP_CONTRACT OFF
#endif

namespace ppc {

// -- separately-rounded singles: `fmuls`, `fadds`, ... one rounding each --------------------
inline float fmuls(float a, float b) { return a * b; }
inline float fadds(float a, float b) { return a + b; }
inline float fsubs(float a, float b) { return a - b; }
inline float fdivs(float a, float b) { return a / b; }

// -- fused singles: one rounding of the exact product-sum ----------------------------------
inline float fmadds(float a, float b, float c) {
    return (float)((double)a * (double)b + (double)c);
}
inline float fmsubs(float a, float b, float c) {
    return (float)((double)a * (double)b - (double)c);
}
// Negation is exact, so these are exactly the negations of the two above.
inline float fnmadds(float a, float b, float c) {
    return (float)(-((double)a * (double)b + (double)c));
}
inline float fnmsubs(float a, float b, float c) {
    return (float)(-((double)a * (double)b - (double)c));
}

// =============================================================================================
// Estimate instructions. Gekko has no usable square root or divide seed: the JP DOL has
// frsqrte x505, fres x3, ps_res x1 and fsqrt/fsqrts x0. Every root is a table estimate plus
// Newton refinement, which differs from x86 `sqrtss` / ARM64 `fsqrt` in the last bits, and no
// build flag changes that. Replacing frsqrte+Newton with a correctly-rounded sqrt gets 627 of
// 1,942 console plane normals wrong (tests/test_calc_pla.cpp).
// =============================================================================================

//: `int.bit_length()`; C++17 has no std::bit_width.
inline int bit_length64(uint64_t v) {
    int n = 0;
    while (v) { v >>= 1; n++; }
    return n;
}

inline double bits_to_f64(uint64_t u) { double d; std::memcpy(&d, &u, 8); return d; }
inline uint64_t f64_to_bits(double d) { uint64_t u; std::memcpy(&u, &d, 8); return u; }

/// Gekko rounds a single-precision op's `frC` operand to 25 mantissa bits before multiplying
/// (Dolphin `Force25Bit`, Interpreter_FPUtils.h). A no-op for f32 operands; it matters for the
/// raw ~26-bit `frsqrte` estimate, which `PSVECMag` squares (75 of 1,942 console planes differ
/// without it).
inline double force25(double d) {
    const uint64_t EXP = 0x7FFull << 52;
    const uint64_t FRAC = (1ull << 52) - 1;
    uint64_t i = f64_to_bits(d);
    if ((i & EXP) == 0 && (i & FRAC) != 0) {
        // Subnormal: shift the keep-mask and the round bit right until the fraction is "normal".
        const int shift = (64 - bit_length64(i & FRAC)) - 11;
        const uint64_t keep = (uint64_t)((int64_t)0xFFFFFFFFF8000000ll >> shift);  // arithmetic
        const uint64_t rnd = 0x8000000ull >> shift;
        i = (i & keep) + (i & rnd);
    } else {
        i = (i & 0xFFFFFFFFF8000000ull) + (i & 0x8000000ull);
    }
    return bits_to_f64(i);
}

//: The 32 (base, decrement) pairs of the Gekko's reciprocal-square-root lookup table.
struct FrsqrteEntry { int32_t base; int32_t dec; };
inline const FrsqrteEntry* frsqrte_table() {
    static const FrsqrteEntry t[32] = {
        {0x1a7e800, -0x568}, {0x17cb800, -0x4f3}, {0x1552800, -0x48d}, {0x130c000, -0x435},
        {0x10f2000, -0x3e7}, {0x0eff000, -0x3a2}, {0x0d2e000, -0x365}, {0x0b7c000, -0x32e},
        {0x09e5000, -0x2fc}, {0x0867000, -0x2d0}, {0x06ff000, -0x2a8}, {0x05ab800, -0x283},
        {0x046a000, -0x261}, {0x0339800, -0x243}, {0x0218800, -0x226}, {0x0105800, -0x20b},
        {0x3ffa000, -0x7a4}, {0x3c29000, -0x700}, {0x38aa000, -0x670}, {0x3572000, -0x5f2},
        {0x3279000, -0x584}, {0x2fb7000, -0x524}, {0x2d26000, -0x4cc}, {0x2ac0000, -0x47e},
        {0x2881000, -0x43a}, {0x2665000, -0x3fa}, {0x2468000, -0x3c2}, {0x2287000, -0x38e},
        {0x20c1000, -0x35e}, {0x1f12000, -0x332}, {0x1d79000, -0x30a}, {0x1bf4000, -0x2e6},
    };
    return t;
}

/// `frsqrte` - the reciprocal square-root estimate, as the hardware computes it: halve the
/// exponent, index the table with the top bits of (exponent lsb | mantissa), interpolate.
/// Returned as `double` because it carries ~26 bits the Newton step needs.
inline double frsqrte(double val) {
    const uint64_t SIGN = 1ull << 63;
    const uint64_t EXP = 0x7FFull << 52;
    const uint64_t FRAC = (1ull << 52) - 1;
    uint64_t integral = f64_to_bits(val);
    uint64_t mantissa = integral & FRAC;
    const uint64_t sign = integral & SIGN;
    uint64_t exponent = integral & EXP;

    if (mantissa == 0 && exponent == 0) {
        return sign ? -std::numeric_limits<double>::infinity() : std::numeric_limits<double>::infinity();
    }
    if (exponent == EXP) {
        if (mantissa == 0) { return sign ? std::numeric_limits<double>::quiet_NaN() : 0.0; }
        return val;
    }
    if (sign) { return std::numeric_limits<double>::quiet_NaN(); }
    if (exponent == 0) {
        while (!(mantissa & (1ull << 52))) {
            exponent -= 1ull << 52;
            mantissa <<= 1;
        }
        mantissa &= FRAC;
        exponent += 1ull << 52;
    }
    const uint64_t exponent_lsb = exponent & (1ull << 52);
    // Signed division truncating toward zero.
    const int64_t half = (int64_t)(exponent - (0x3FEull << 52)) / 2;
    exponent = (uint64_t)((int64_t)(0x3FFull << 52) - half) & EXP;
    integral = sign | exponent;
    const uint64_t i = (exponent_lsb | mantissa) >> 37;
    const FrsqrteEntry& e = frsqrte_table()[i / 2048];
    integral |= (uint64_t)((int64_t)(e.base + e.dec * (int32_t)(i % 2048)) << 26);
    return bits_to_f64(integral);
}

/// `fmuls frD, frA, frC` on raw FPR values: `frC` is rounded to 25 bits, then the product once to
/// single. Argument order matters once an operand is wider than f32. The double product is exact
/// (~26 + 25 bits <= 53).
inline float fmuls_fpr(double frA, double frC) {
    return (float)(frA * force25(frC));
}

//: The 32 (base, decrement) pairs of the Gekko's reciprocal lookup table (`fres`).
struct FresEntry { int32_t base; int32_t dec; };
inline const FresEntry* fres_table() {
    static const FresEntry t[32] = {
        {0x7ff800, 0x3e1}, {0x783800, 0x3a7}, {0x70ea00, 0x371}, {0x6a0800, 0x340},
        {0x638800, 0x313}, {0x5d6200, 0x2ea}, {0x579000, 0x2c4}, {0x520800, 0x2a0},
        {0x4cc800, 0x27f}, {0x47ca00, 0x261}, {0x430800, 0x245}, {0x3e8000, 0x22a},
        {0x3a2c00, 0x212}, {0x360800, 0x1fb}, {0x321400, 0x1e5}, {0x2e4a00, 0x1d1},
        {0x2aa800, 0x1be}, {0x272c00, 0x1ac}, {0x23d600, 0x19b}, {0x209e00, 0x18b},
        {0x1d8800, 0x17c}, {0x1a9000, 0x16e}, {0x17ae00, 0x15b}, {0x14f800, 0x15b},
        {0x124400, 0x143}, {0x0fbe00, 0x143}, {0x0d3800, 0x12d}, {0x0ade00, 0x12d},
        {0x088400, 0x11a}, {0x065000, 0x11a}, {0x041c00, 0x108}, {0x020c00, 0x106},
    };
    return t;
}

/// `fres` - the reciprocal estimate, used by PSMTXInverse, PSMTXQuat and PSQUATInverse (the only
/// three in the DOL). One Newton step from its 12-bit seed reaches ~24 bits, so the result's last
/// bits are the seed's, not a divide's. Blend poses reach table indices single-animation poses do
/// not, because `JMAQuatLerp` does not renormalise.
///
/// Returned as `double` for the caller's refinement; the value is always exact in f32 (low 29
/// mantissa bits are zero).
inline double fres(double val) {
    const uint64_t SIGN = 1ull << 63;
    const uint64_t EXP = 0x7FFull << 52;
    const uint64_t FRAC = (1ull << 52) - 1;
    const uint64_t integral = f64_to_bits(val);
    const uint64_t mantissa = integral & FRAC;
    const uint64_t sign = integral & SIGN;
    const uint64_t exponent = integral & EXP;

    if (mantissa == 0 && exponent == 0) { return bits_to_f64(sign | EXP); }          // 1/0   -> +-inf
    if (exponent == EXP) {
        if (mantissa == 0) { return bits_to_f64(sign); }                             // 1/inf -> +-0
        return val;                                                                  // nan   -> nan
    }
    if (exponent < (895ull << 52)) { return bits_to_f64(sign | EXP); }                // tiny  -> +-inf
    if (exponent >= (1149ull << 52)) { return bits_to_f64(sign); }                    // huge  -> +-0

    // The top 15 mantissa bits: the high 5 index the table, the low 10 interpolate inside it.
    const uint64_t i = mantissa >> 37;
    const FresEntry& e = fres_table()[i >> 10];
    uint64_t out = sign;
    out |= (0x7FDull - (exponent >> 52)) << 52;
    out |= (uint64_t)(e.base - (e.dec * (int32_t)(i % 1024) + 1) / 2) << 29;
    return bits_to_f64(out);
}

/// `std::sqrtf` as MWCC inlines it (`sqrtf__3stdFf`): `frsqrte`, three Newton refinements in
/// double, one final round to single. Read off the DOL at RwgWallCorrect's first root
/// (0x800A3BE8..0x800A3C60):
///
///     fcmpo  f4, 0.0        ; r2-0x6d88
///     ble    skip           ; x <= 0 returns x unchanged, not NaN and not 0
///     frsqrte f0, f4
///     3x { fmul f1, 0.5, f0 ; fmul f0, f0, f0 ; fmul f0, f4, f0 ; fsub f0, 3.0, f0 ;
///          fmul f0, f1, f0 }                             ; all op-63 double, no fused fmadd
///     fmul   f0, f4, f0 ; frsp f0, f0 ; stfs/lfs         ; one round to single at the end
///
/// r2 = 0x803F31A0 (from `lfs f0, -0x4068(r2)` = G_CM3D_F_ABS_MIN at 0x803EF138), so the
/// constants at r2-0x6d80 / -0x6d78 are 0.5 and 3.0. Force25 does not apply: every step is a
/// double-precision op.
inline float sqrtf_msl(float x) {
    const double d = (double)x;
    // `ble` is not taken on unordered, so NaN runs the refinement: `!(d <= 0.0)`, not `d > 0.0`.
    if (!(d <= 0.0)) {
        double g = frsqrte(d);
        for (int i = 0; i < 3; i++) {
            g = (0.5 * g) * (3.0 - d * (g * g));
        }
        return (float)(d * g);
    }
    return x;
}

inline uint32_t bits(float f) { uint32_t u; std::memcpy(&u, &f, 4); return u; }

} // namespace ppc
#endif
