"""Offline regression guard for the view-frustum cull test (tww_sim.core.camera.frustum),
a 1:1 port of J3DUClipper (tww/src/JSystem/J3DU/J3DUClipper.cpp).

These lock the geometry and the cull verdicts so a future edit can't silently regress the port.
Live bit-exactness (clip_box verdict == the game's fopAcCnd_NODRAW_e) is validated separately in
the Dolphin harness; here we assert structure + representative verdicts that are robust to the
VECNormalize reciprocal-sqrt approximation. Convention: clip_* returns True == CULLED (outside)."""
import pytest

from tww_sim.core.camera.frustum import build_frustum, calc_view_frustum

IDENT = ((1.0, 0.0, 0.0, 0.0),
         (0.0, 1.0, 0.0, 0.0),
         (0.0, 0.0, 1.0, 0.0))  # camera space == world space: eye at origin looking down -Z

# The gameplay follow camera: FOV-Y 55 deg, aspect (4/3)*0.96 = 1.28, near 1.0.
FOVY, ASPECT, NEAR = 55.0, 1.28, 1.0


def _translate(tx, ty, tz):
    return ((1.0, 0.0, 0.0, tx), (0.0, 1.0, 0.0, ty), (0.0, 0.0, 1.0, tz))


# --- frustum construction ---------------------------------------------------------------

def test_build_frustum_stores_f32_params():
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    assert fr.fovy == pytest.approx(55.0)
    assert fr.aspect == pytest.approx(1.28, abs=1e-6)
    assert fr.near == 1.0
    assert fr.far == 100000.0
    assert len(fr.planes) == 4


def test_side_plane_signs():
    """The 4 side-plane normals point OUTWARD (dot>0 => outside). Their sign pattern is fixed
    by the corner cross-product order: left/top/right/bottom."""
    left, top, right, bottom = calc_view_frustum(FOVY, ASPECT, NEAR)
    # LEFT: normal.x < 0, normal.z > 0
    assert left[0] < 0 and left[2] > 0 and abs(left[1]) < 1e-6
    # TOP: normal.y > 0, normal.z > 0
    assert top[1] > 0 and top[2] > 0 and abs(top[0]) < 1e-6
    # RIGHT: normal.x > 0, normal.z > 0
    assert right[0] > 0 and right[2] > 0 and abs(right[1]) < 1e-6
    # BOTTOM: normal.y < 0, normal.z > 0
    assert bottom[1] < 0 and bottom[2] > 0 and abs(bottom[0]) < 1e-6


def test_side_planes_are_unit_length():
    for plane in calc_view_frustum(FOVY, ASPECT, NEAR):
        mag = sum(c * c for c in plane) ** 0.5
        assert mag == pytest.approx(1.0, abs=1e-6)


# --- sphere clip verdicts ---------------------------------------------------------------

@pytest.mark.parametrize("pos,radius,culled", [
    ((0.0, 0.0, -100.0), 1.0, False),    # dead ahead -> visible
    ((0.0, 0.0, 100.0), 1.0, True),      # behind the camera -> culled (near)
    ((0.0, 0.0, -0.5), 1.0, False),      # in front of near but radius reaches past it -> visible
    ((-50.0, 0.0, -100.0), 1.0, False),  # left but inside the ~66.6 half-width at z=-100
    ((-90.0, 0.0, -100.0), 1.0, True),   # left of the left plane -> culled
    ((90.0, 0.0, -100.0), 1.0, True),    # right plane -> culled
    ((0.0, 80.0, -100.0), 1.0, True),    # above the top plane -> culled
    ((0.0, -80.0, -100.0), 1.0, True),   # below the bottom plane -> culled
])
def test_clip_sphere_identity(pos, radius, culled):
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    assert fr.clip_sphere(IDENT, pos, radius) is culled


def test_clip_sphere_far_plane():
    fr = build_frustum(FOVY, ASPECT, NEAR, 1000.0)
    assert fr.clip_sphere(IDENT, (0.0, 0.0, -900.0), 1.0) is False   # within far
    assert fr.clip_sphere(IDENT, (0.0, 0.0, -2000.0), 1.0) is True   # beyond far -> culled


def test_clip_sphere_respects_view_translation():
    """A world point culled from the origin becomes visible once the view matrix places it in
    front of the eye (the mtx is view*model, i.e. world->camera)."""
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    world = (0.0, 0.0, 500.0)                 # behind an origin eye
    assert fr.clip_sphere(IDENT, world, 1.0) is True
    view = _translate(0.0, 0.0, -1000.0)      # shift world -1000 in z -> lands at z=-500 (ahead)
    assert fr.clip_sphere(view, world, 1.0) is False


# --- box clip verdicts ------------------------------------------------------------------

def test_clip_box_visible_and_behind():
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    assert fr.clip_box(IDENT, (-5.0, -5.0, -105.0), (5.0, 5.0, -95.0)) is False  # small box ahead
    assert fr.clip_box(IDENT, (-5.0, -5.0, 95.0), (5.0, 5.0, 105.0)) is True     # box behind eye


def test_clip_box_off_to_the_side():
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    # a small box far to the left: all 8 corners outside the left plane -> culled
    assert fr.clip_box(IDENT, (-205.0, -5.0, -105.0), (-195.0, 5.0, -95.0)) is True


def test_clip_box_huge_enclosing_box_is_not_culled():
    """The conservative all-8-corners-on-ONE-plane rule: a box that swallows the whole frustum
    has every corner outside *some* plane, but no single plane holds all 8 -> NOT culled. This is
    the key property that separates the box test from a naive per-corner reject."""
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    assert fr.clip_box(IDENT, (-1000.0, -1000.0, -101.0), (1000.0, 1000.0, -100.0)) is False


def test_clip_box_arg_swap_invariant():
    """TWW's actor path calls clip(mtx, box.max, box.min); the corner set is symmetric so the
    verdict must not depend on which arg is min vs max."""
    fr = build_frustum(FOVY, ASPECT, NEAR, 100000.0)
    lo, hi = (-205.0, -5.0, -105.0), (-195.0, 5.0, -95.0)
    assert fr.clip_box(IDENT, lo, hi) == fr.clip_box(IDENT, hi, lo)


def test_clip_box_far_plane():
    fr = build_frustum(FOVY, ASPECT, NEAR, 1000.0)
    box = ((-5.0, -5.0, -2005.0), (5.0, 5.0, -1995.0))  # beyond far=1000
    assert fr.clip_box(IDENT, *box) is True


# --- with_far (per-actor cullSizeFar / changeFar) ---------------------------------------

def test_with_far_keeps_side_planes_moves_far():
    fr = build_frustum(FOVY, ASPECT, NEAR, 1000.0)
    fr2 = fr.with_far(5000.0)
    assert fr2.far == 5000.0
    assert fr2.planes is fr.planes                       # side planes unchanged (near-only)
    # a box beyond the old far but within the new far flips from culled to visible
    box = ((-5.0, -5.0, -3005.0), (5.0, 5.0, -2995.0))
    assert fr.clip_box(IDENT, *box) is True
    assert fr2.clip_box(IDENT, *box) is False
