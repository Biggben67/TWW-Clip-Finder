"""frustum.py — faithful port of J3DUClipper: the TWW view-frustum cull test.

This is the *culling truth*. TWW decides whether an actor is drawn by testing its
per-actor cull volume (a bounding box or sphere) against a view frustum built from the
camera's FOV-Y / aspect / near, with the far plane set to the stage **cull point**
(`dStage_stagInfo_GetCullPoint` — the effective draw distance, NOT the render far plane).
Ported 1:1 from ``tww/src/JSystem/J3DU/J3DUClipper.cpp`` (US decomp; logic is version-agnostic).

CONVENTION (matches the C ``BOOL``): every ``clip_*`` returns ``True`` when the volume is
**outside** the frustum, i.e. it would be CULLED / not drawn. ``False`` means visible.

The frustum is 4 side planes + 2 scalar depth bounds:

  * ``calc_view_frustum`` builds the 4 side-plane normals (left/top/right/bottom) as the
    cross products of the near-face corners, each passing through the camera origin, then
    normalizes them. The near-face corners come from ``tan(fovY/2)`` and aspect; note the
    side planes depend only on ``near`` (via the corners' shared scale) — they are invariant
    to ``far`` (see ``with_far``).
  * near / far are kept as scalars and tested against camera-space ``-z``.

Fidelity notes:
  * All arithmetic uses the console-faithful f32 ops from :mod:`tww_sim.core.fp`.
  * The **box** test's per-corner threshold is ``dot > 0`` (and near/far are ``< near`` /
    ``> far``), so plane-normal *scale* cannot change a box verdict — the box path is exact
    regardless of the ``VECNormalize`` reciprocal-sqrt approximation below. TWW's
    ``fopAc_ac_c`` actors of interest are box-culled, so this is the path that matters most.
  * The **sphere** test compares ``dot > radius`` against the *normalized* plane, so its
    verdict does depend on the normalize precision. We use a correctly-rounded double
    ``1/sqrt`` (``math.sqrt``) rounded to f32; TWW's ``VECNormalize`` uses an frsqrte+Newton
    reciprocal-sqrt which agrees to <=1 ULP. If live validation ever shows a boundary flip on
    the sphere path we swap in the frsqrte version (as ``foot_speedf._sqrtf`` already does).

Matrices are camera-space transforms (view * model), row-major 3x4: ``m[row][col]`` with
``m[i][3]`` the translation. Vectors are plain ``(x, y, z)`` float tuples.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from ..fp import f32, fmuls, fadds, fsubs, fdivs

Vec3 = Tuple[float, float, float]
Mtx = Sequence[Sequence[float]]  # 3 rows x 4 cols, row-major

DEG2RAD = f32(0.017453292)  # J3DUClipper.cpp: static const f32 Deg2Rad


# --- primitives (faithful to the decomp's math) -----------------------------------------

def _cross(a: Vec3, b: Vec3) -> Vec3:
    """J3DVecCrossProduct(a, b) -> a x b, componentwise f32 (two products then subtract)."""
    return (
        fsubs(fmuls(a[1], b[2]), fmuls(a[2], b[1])),
        fsubs(fmuls(a[2], b[0]), fmuls(a[0], b[2])),
        fsubs(fmuls(a[0], b[1]), fmuls(a[1], b[0])),
    )


def _normalize(v: Vec3) -> Vec3:
    """VECNormalize: mag = x^2+y^2+z^2; scale by 1/sqrt(mag). See fidelity note in the module
    docstring — scale is irrelevant to the box verdict (threshold 0)."""
    mag = fadds(fadds(fmuls(v[0], v[0]), fmuls(v[1], v[1])), fmuls(v[2], v[2]))
    if mag <= 0.0:
        return (0.0, 0.0, 0.0)
    inv = f32(1.0 / math.sqrt(mag))  # 1.0f / sqrtf(mag)
    return (fmuls(v[0], inv), fmuls(v[1], inv), fmuls(v[2], inv))


def _mtx_mult_vec(m: Mtx, v: Vec3) -> Vec3:
    """MTXMultVec: affine transform of a point by a 3x4 matrix, left-to-right f32."""
    x = fadds(fadds(fadds(fmuls(m[0][0], v[0]), fmuls(m[0][1], v[1])), fmuls(m[0][2], v[2])), m[0][3])
    y = fadds(fadds(fadds(fmuls(m[1][0], v[0]), fmuls(m[1][1], v[1])), fmuls(m[1][2], v[2])), m[1][3])
    z = fadds(fadds(fadds(fmuls(m[2][0], v[0]), fmuls(m[2][1], v[1])), fmuls(m[2][2], v[2])), m[2][3])
    return (x, y, z)


def _dot(p: Vec3, plane: Vec3) -> float:
    """p . plane_normal, left-to-right f32 (the side-plane half-space test)."""
    return fadds(fadds(fmuls(p[0], plane[0]), fmuls(p[1], plane[1])), fmuls(p[2], plane[2]))


def transform_point(m: Mtx, v: Vec3) -> Vec3:
    """Affine transform of a point by a 3x4 matrix (public MTXMultVec). Used to map a local
    cull-box corner to world space via the actor's cullMtx for drawing."""
    return _mtx_mult_vec(m, v)


def mtx_concat(a: Mtx, b: Mtx) -> Mtx:
    """3x4 * 3x4 matrix concat (Dolphin MTXConcat / cMtx_concat): out = a . b, treating each as
    a 4x4 with last row (0,0,0,1). Used to form pMtx = view . cullMtx for the cull test."""
    out = [[0.0, 0.0, 0.0, 0.0] for _ in range(3)]
    for i in range(3):
        for j in range(4):
            s = fadds(fadds(fmuls(a[i][0], b[0][j]), fmuls(a[i][1], b[1][j])), fmuls(a[i][2], b[2][j]))
            if j == 3:
                s = fadds(s, a[i][3])
            out[i][j] = s
    return out


# --- the clipper -------------------------------------------------------------------------

@dataclass
class Frustum:
    """A built view frustum: FOV-Y (deg) / aspect / near / far and the 4 side-plane normals.
    Returned by :func:`build_frustum`. ``clip_*`` return True == culled (outside)."""
    fovy: float
    aspect: float
    near: float
    far: float
    planes: List[Vec3]  # [left, top, right, bottom], normals point OUTWARD (dot > 0 => outside)

    def with_far(self, far: float) -> "Frustum":
        """A copy with a new far plane. Mirrors ``mDoLib_clipper::changeFar`` /
        per-actor ``cullSizeFar`` scaling: the side planes are unchanged (they depend only on
        near), so only the ``far`` scalar moves."""
        return Frustum(self.fovy, self.aspect, self.near, f32(far), self.planes)

    def clip_sphere(self, mtx: Mtx, pos: Vec3, radius: float) -> bool:
        """J3DUClipper::clip(mtx, pos, radius). True => sphere is fully outside (culled)."""
        p = _mtx_mult_vec(mtx, pos)
        neg_z = -p[2]
        if neg_z < fsubs(self.near, radius):
            return True
        if neg_z > fadds(self.far, radius):
            return True
        for plane in self.planes:
            if _dot(p, plane) > radius:
                return True
        return False

    def clip_box(self, mtx: Mtx, pmin: Vec3, pmax: Vec3) -> bool:
        """J3DUClipper::clip(mtx, pMin, pMax). True => AABB is fully outside (culled).

        Note: the corner set is all 8 combinations of {pmin,pmax} per axis, so swapping the
        two args (TWW's actor path calls it as ``clip(mtx, box.max, box.min)``) yields the
        identical verdict. An AABB is culled only if all 8 corners fall outside one plane."""
        corners = (
            (pmax[0], pmax[1], pmin[2]),
            (pmax[0], pmax[1], pmax[2]),
            (pmin[0], pmax[1], pmax[2]),
            (pmin[0], pmax[1], pmin[2]),
            (pmax[0], pmin[1], pmin[2]),
            (pmax[0], pmin[1], pmax[2]),
            (pmin[0], pmin[1], pmax[2]),
            (pmin[0], pmin[1], pmin[2]),
        )
        clip = [0, 0, 0, 0, 0, 0]  # [left, top, right, bottom, near, far]
        for corner in corners:
            p = _mtx_mult_vec(mtx, corner)
            any_out = False
            neg_z = -p[2]
            if neg_z < self.near:
                clip[4] += 1; any_out = True
            if neg_z > self.far:
                clip[5] += 1; any_out = True
            if _dot(p, self.planes[0]) > 0.0:
                clip[0] += 1; any_out = True
            if _dot(p, self.planes[1]) > 0.0:
                clip[1] += 1; any_out = True
            if _dot(p, self.planes[2]) > 0.0:
                clip[2] += 1; any_out = True
            if _dot(p, self.planes[3]) > 0.0:
                clip[3] += 1; any_out = True
            if not any_out:
                return False  # this corner is inside every plane => visible
        # all 8 corners outside on some single shared plane => culled
        return any(c == 8 for c in clip)


def calc_view_frustum(fovy: float, aspect: float, near: float) -> List[Vec3]:
    """J3DUClipper::calcViewFrustum — the 4 normalized side-plane normals (left/top/right/
    bottom) for the given FOV-Y (deg), aspect, near. Independent of far."""
    fovy = f32(fovy); aspect = f32(aspect); near = f32(near)
    tan_fovy = f32(math.tan(fmuls(fmuls(fovy, 0.5), DEG2RAD)))
    near_y = fmuls(near, tan_fovy)
    near_x = fmuls(aspect, near_y)
    c0 = (-near_x, -near_y, -near)
    c1 = (-near_x,  near_y, -near)
    c2 = ( near_x,  near_y, -near)
    c3 = ( near_x, -near_y, -near)
    return [
        _normalize(_cross(c1, c0)),
        _normalize(_cross(c2, c1)),
        _normalize(_cross(c3, c2)),
        _normalize(_cross(c0, c3)),
    ]


def build_frustum(fovy: float, aspect: float, near: float, far: float) -> Frustum:
    """Build a :class:`Frustum` from the camera's FOV-Y (deg), aspect, near, and the culling
    far (the stage cull point). This is exactly what ``mDoLib_clipper::setup`` feeds the game's
    clipper each frame (``d_camera.cpp`` view_setup)."""
    fovy = f32(fovy); aspect = f32(aspect); near = f32(near); far = f32(far)
    return Frustum(fovy, aspect, near, far, calc_view_frustum(fovy, aspect, near))
