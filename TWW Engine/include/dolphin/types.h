// types.h - the subset of the decomp's scalar and SDK types that the ported bodies name, spelled
// as the decomp spells them so copied bodies compile unedited.

#ifndef TWW_PORT_TYPES_H
#define TWW_PORT_TYPES_H

#include <cstddef>   // NULL
#include <cstdint>
#include <cstdlib>

#include "engine/ppc_fp.h"

typedef int8_t s8;
typedef uint8_t u8;
typedef int16_t s16;
typedef uint16_t u16;
typedef int32_t s32;
typedef uint32_t u32;
typedef float f32;
typedef double f64;

/// MSL's <math.h> defines these unconditionally; MSVC's <cmath> does not. Same decimals as MSL,
/// so a redefinition is token-identical. M_PI: posMoveFromFootPos. M_SQRT2 / M_SQRT1_2:
/// dCamMath::customRBRatio (d_cam_param.cpp:50,58), where M_SQRT2 is in live double arithmetic.
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#ifndef M_SQRT2
#define M_SQRT2 1.41421356237309504880
#endif
#ifndef M_SQRT1_2
#define M_SQRT1_2 0.70710678118654752440
#endif

typedef int BOOL;
#ifndef TRUE
#define TRUE 1
#define FALSE 0
#endif

/// f_pc_base.h:11 and f_pc_manager.h:10-12, written rather than included. An opaque token here:
/// nothing in the port compares two (engine/room.h stands in for the registered-object loop).
typedef unsigned int fpc_ProcID;
enum {
    fpcM_ERROR_PROCESS_ID_e = -1,
};

/// dolphin/mtx/mtx.h:14-15. Only ever passed along; the port has no matrix stack here.
typedef f32 Mtx[3][4];
typedef f32 (*MtxP)[4];

/// dolphin/gx/GXStruct.h:10-16 and :18-24, verbatim. Nothing reads a channel back.
struct GXColor {
    u8 r, g, b, a;
};

struct GXColorS10 {
    s16 r, g, b, a;
};

/// c_sxyz.h:8-21. The default constructor is defaulted rather than the decomp's `{}` so a
/// value-initialised csXyz is zero, which the port's resets rely on.
struct csXyz {
    csXyz() = default;
    csXyz(s16 oX, s16 oY, s16 oZ) : x(oX), y(oY), z(oZ) {}
    void set(s16 oX, s16 oY, s16 oZ) {
        x = oX;
        y = oY;
        z = oZ;
    }
    s16 x, y, z;
};

/// dolphin/mtx/vec.h.
struct Vec {
    f32 x, y, z;
};

/// dolphin/mtx/vec.h:18-20.
struct SVec {
    s16 x, y, z;
};

/// Stands in for the decomp's `(Vec){x, y, z}` compound literal, which MSVC refuses (C4576).
inline Vec J3D_VEC(f32 x, f32 y, f32 z) {
    Vec v;
    v.x = x;
    v.y = y;
    v.z = z;
    return v;
}

/// dolphin/mtx/quat.h:10-12, verbatim. The member order is load-bearing: PSMTXQuat reads it as
/// two paired loads, (x, y) then (z, w).
typedef struct Quaternion {
    f32 x, y, z, w;
} Quaternion;

/// engine/ps_vec.h, declared here because that header includes this one.
f32 PSVECSquareDistance(const Vec* a, const Vec* b);
f32 PSVECSquareMag(const Vec* v);
void PSVECSubtract(const Vec* a, const Vec* b, Vec* a_b);
void PSVECAdd(const Vec* a, const Vec* b, Vec* ab);
void PSVECScale(const Vec* src, Vec* dst, f32 scale);

/// c_xyz.h:11. dolphin/mtx/vec.h picks C_VEC* unless `__MWERKS__`; the game ran the PSVEC*
/// paired-single versions (the DOL has no C_VEC* symbols), so these call PSVEC* as the console did.
struct cXyz : Vec {
    /// c_xyz.h:13-16 and c_xyz.cpp:9-12, defined in boundary/stubs.cpp. BaseX and BaseZ are
    /// named only by setWorldMatrix's dead ship arm.
    static const cXyz Zero;
    static const cXyz BaseX;
    static const cXyz BaseZ;

    cXyz() = default;
    ~cXyz() = default;
    cXyz(const cXyz& vec) = default;
    cXyz(f32 pX, f32 pY, f32 pZ) {
        x = pX;
        y = pY;
        z = pZ;
    }
    cXyz(const Vec& vec) {
        x = vec.x;
        y = vec.y;
        z = vec.z;
    }
    void operator=(const Vec& vec) {
        x = vec.x;
        y = vec.y;
        z = vec.z;
    }
    cXyz& operator=(const cXyz& vec) = default;

    /// c_xyz.h:94-98.
    void set(f32 pX, f32 pY, f32 pZ) {
        x = pX;
        y = pY;
        z = pZ;
    }

    /// c_xyz.h:115 - `cXyz tmp(x, 0, z); return tmp.abs2();`, as PSVECSquareMag (0x8030BB98)
    /// computes it: z*z + x*x fused, then + y*y.
    f32 abs2XZ() const {
        return ppc::fadds(ppc::fmadds(z, z, ppc::fmuls(x, x)), ppc::fmuls(0.0f, 0.0f));
    }

    /// c_xyz.h:113.
    f32 abs2() const { return PSVECSquareMag(this); }

    /// c_xyz.h:124 - `std::sqrtf`, which on the console is `sqrtf__3stdFf` (0x800EDF4C), not a
    /// correctly rounded sqrt.
    f32 abs() const { return ppc::sqrtf_msl(abs2()); }

    /// c_xyz.h:126.
    f32 absXZ() const { return ppc::sqrtf_msl(abs2XZ()); }

    /// c_xyz.cpp:19.
    cXyz operator+(const Vec& vec) const {
        Vec ret;
        PSVECAdd(this, &vec, &ret);
        return cXyz(ret);
    }

    /// c_xyz.cpp:33.
    cXyz operator*(f32 scale) const {
        Vec ret;
        PSVECScale(this, &ret, scale);
        return cXyz(ret);
    }

    /// c_xyz.cpp:40-46, verbatim: a componentwise multiply with no SDK call.
    cXyz operator*(const Vec& vec) const {
        cXyz ret;
        ret.x = this->x * vec.x;
        ret.y = this->y * vec.y;
        ret.z = this->z * vec.z;
        return cXyz(ret);
    }

    /// c_xyz.h:56-59.
    cXyz* operator*=(f32 scale) {
        PSVECScale(this, this, scale);
        return this;
    }

    /// c_xyz.h:65-68.
    cXyz* operator+=(const Vec& other) {
        PSVECAdd(this, &other, this);
        return this;
    }

    /// c_xyz.h:68-71.
    cXyz* operator-=(const Vec& other) {
        PSVECSubtract(this, &other, this);
        return this;
    }

    /// c_xyz.h:119-123.
    f32 abs2XZ(const Vec& other) const {
        const cXyz tmp(x, 0, z);
        const cXyz tmp2(other.x, 0, other.z);
        return PSVECSquareDistance(&tmp, &tmp2);
    }

    /// c_xyz.cpp:26. PSVECSubtract (0x8030BA4C) is two `ps_sub`s, which round each lane exactly
    /// as these scalar subtractions do.
    cXyz operator-(const Vec& vec) const {
        cXyz ret;
        ret.x = x - vec.x;
        ret.y = y - vec.y;
        ret.z = z - vec.z;
        return ret;
    }

};

/// f_op_actor.h `actor_place`. `current.angle.y` is +0x206 of the actor
/// (`lha r0, 0x206(r31)` in procFrontRoll_init).
struct actor_place {
    cXyz pos;
    csXyz angle;
    s16 roomNo;
};

#endif
