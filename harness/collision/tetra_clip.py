"""Tetra-nudge → seam-clip pipeline: does a Tetra (NPC Zl1) body-cylinder push turn a roll/thrust
that falls just short of a wall-corner's f32 minimum into an actual clip?

Composes two decomp-faithful ports:
  * :func:`tww_sim.core.cc_push.co_push_link` — Link's ``m_cc_move`` from a Co overlap with Tetra.
  * :func:`tww_sim.core.collision.crr_pos_walls` — the wall LineCheck + WallCorrect (clip decider).

Frame model (``daPy_lk_c::posMove`` → ``dBgS_Acch::CrrPos``, d_a_player_main.cpp:11407/11411):
Link's ``current.pos`` for the clip frame is ``old + push + thrust`` — ``posMove`` adds the accumulated
``m_cc_move`` (the push, from the PREVIOUS frame's overlap) FIRST, then the frame's own roll/thrust
movement — and ``CrrPos`` then sweeps ``old → current.pos`` against the wall. ``old`` is the settled
end-of-last-frame position, unaffected by this frame's push. So a Tetra placed behind Link (away from
the corner) adds a small extra displacement toward the corner on top of the roll, extending ``new``
past the seam into the f32 clip window.

Live-confirmed (Hyrule, GZLJ01): the game uses ``dCcS::SetPosCorrect`` (rank-table split), so with
Link (weight 120, rank 5) vs Tetra (weight 140, rank 5) ``rank_tbl[5][5]=50`` → Link gets **0.50×**
the overlap depth (NOT the mass-proportional 0.538 the old cCcS port assumed). The push is horizontal
(``dy=0``) along ``unit(link − tetra)``. Positions are f32 throughout (Link's ``cXyz`` is f32).

Cylinder caveat: Link's body Co cylinder is **R=30** (walking / FRONT_ROLL; R=50 only when carrying)
and its center is the horizontal midpoint of the root & neck joints (animation-driven, offset from
``current.pos``), not the feet — so ``sumR`` is 80, not 100. During a FRONT_ROLL lunge that center
**leads the feet by 10–26 u**, so the feet are a poor proxy. Pass ``link_center`` (from
:func:`tww_sim.core.anim.body_cyl.roll_co_center`, live-validated bit-exact) to place the push on the
true animated cylinder center; omit it to fall back to the old feet proxy (``old``). The push
(``m_cc_move``) is still applied to ``current.pos`` (the feet) — only the overlap geometry uses the
cylinder center. See knowledge/mechanics/actor-push.md.
"""
import math

from tww_sim.core.fp import f32 as _f, fadds
from tww_sim.core.collision import crr_pos_walls
from tww_sim.core.cc_push import co_push_link, WEIGHT_LINK, WEIGHT_TETRA_V5
from harness.collision.gap_search import WALL_H, WALL_R, settle

# Body *Co* cylinders that feed cM3d_Cross_CylCyl (distinct from the radius-35 wall cylinder):
# Link R=30/H~81.25 (walking / FRONT_ROLL; d_a_player_main.cpp:9762/9780); Tetra R=50/H=140 (live).
LINK_CO_R, LINK_CO_H = 30.0, 81.25
TETRA_CO_R, TETRA_CO_H = 50.0, 140.0


def clip_with_push(old_xz, link_y, thrust, tetra_xz, tris,
                   tetra_w=WEIGHT_TETRA_V5, link_w=WEIGHT_LINK,
                   link_co_h=LINK_CO_H, tetra_h=TETRA_CO_H, link_center=None):
    """Run one clip frame with a Tetra push. ``old_xz`` = settled Link XZ (the feet, = current.pos);
    ``thrust`` = (dx, dz) the roll/sword move would add this frame (no Tetra); ``tetra_xz`` = Tetra's
    body-cyl center XZ. ``link_center`` = Link's body Co cyl center XZ for this frame (from
    :func:`tww_sim.core.anim.body_cyl.roll_co_center`); when ``None`` it falls back to the feet
    (``old_xz``) as a first-order proxy. Returns a dict with ``clipped``, the resulting ``new`` XZ,
    the ``push`` vector, ``disp`` (|new−old|), and the ``crr_pos_walls`` ``info``. The overlap /
    push DIRECTION use the cylinder center; the push is applied to the feet (``current.pos``)."""
    old = (_f(old_xz[0]), _f(link_y), _f(old_xz[1]))
    ctr_xz = old_xz if link_center is None else link_center
    center = (_f(ctr_xz[0]), _f(link_y), _f(ctr_xz[1]))
    tetra_c = (_f(tetra_xz[0]), _f(link_y), _f(tetra_xz[1]))
    px, _py, pz = co_push_link(center, LINK_CO_R, link_co_h, tetra_c, TETRA_CO_R, tetra_h,
                               link_w=link_w, other_w=tetra_w)
    # posMove order: current.pos += m_cc_move (push), then += thrust  (componentwise f32 adds)
    nx = fadds(fadds(old[0], px), _f(thrust[0]))
    nz = fadds(fadds(old[2], pz), _f(thrust[1]))
    new = (nx, _f(link_y), nz)
    _, info = crr_pos_walls(old, new, tris)
    clipped = (not info["line_hit"]) and (not info["wall_hit"])
    disp = math.hypot(nx - old[0], nz - old[2])
    return dict(clipped=clipped, new=(nx, nz), push=(px, pz), disp=disp,
                overlap=math.hypot(center[0] - tetra_c[0], center[2] - tetra_c[2]), info=info)


def solve_min_overlap(old_xz, link_y, thrust, tris, tetra_w=WEIGHT_TETRA_V5,
                      max_overlap=6.0, step=0.02, link_co_h=LINK_CO_H, tetra_h=TETRA_CO_H,
                      link_center=None):
    """Find the smallest Tetra→Link overlap that makes the roll/thrust clip, with Tetra placed
    directly behind Link's cylinder center (opposite the thrust) so the whole push points toward the
    corner.

    ``thrust`` = (dx, dz). ``link_center`` = Link's body Co cyl center XZ (from
    :func:`tww_sim.core.anim.body_cyl.roll_co_center`); when ``None`` the feet (``old_xz``) are used.
    Tetra is placed behind that center at center-distance ``sumR − overlap``, so ``overlap`` IS the
    true cylinder overlap depth. Sweeps overlap 0 → ``max_overlap`` u. Returns the first clipping
    case (dict from :func:`clip_with_push` plus ``overlap``), or ``None`` if none clip within
    ``max_overlap``. Reports the baseline (overlap 0 == no Tetra) clip state in ``baseline_clips``."""
    tmag = math.hypot(thrust[0], thrust[1])
    if tmag == 0.0:
        raise ValueError("thrust must be nonzero")
    thx, thz = thrust[0] / tmag, thrust[1] / tmag          # unit thrust (toward corner)
    ctr = old_xz if link_center is None else link_center   # place Tetra relative to the cyl center
    baseline = clip_with_push(old_xz, link_y, thrust, (ctr[0] - 1e6, ctr[1]), tris,
                              tetra_w=tetra_w, link_co_h=link_co_h, tetra_h=tetra_h,
                              link_center=link_center)
    sum_r = LINK_CO_R + TETRA_CO_R                          # 80 (Link R=30 + Tetra R=50)
    n = int(max_overlap / step) + 1
    for k in range(1, n):
        ov = k * step
        d = sum_r - ov                                     # center distance for this overlap
        tx, tz = ctr[0] - thx * d, ctr[1] - thz * d        # Tetra behind Link's cyl center
        r = clip_with_push(old_xz, link_y, thrust, (tx, tz), tris,
                           tetra_w=tetra_w, link_co_h=link_co_h, tetra_h=tetra_h,
                           link_center=link_center)
        if r["clipped"]:
            r["overlap"] = ov
            r["tetra_xz"] = (tx, tz)
            r["baseline_clips"] = baseline["clipped"]
            r["baseline_disp"] = baseline["disp"]
            return r
    return None
