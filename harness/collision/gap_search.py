"""Analytic seam-clip gap search — the reliable replacement for the brute-force
``start x aim x D`` grid in :mod:`angle_experiment`.

**Why a grid fails.** A seam clip is a razor event: the swept centre-line must pass within a
*fan-sized* perpendicular offset of the seam vertex ``S`` — the offset window is only
~1e-3 u wide (its width IS the per-triangle plane fan, the 1-ULP normal difference between the two
triangles of each wall; see ``knowledge/mechanics/seam-clip.md``). A blind grid over start position,
aim and displacement steps far coarser than that window and reports spurious ``False`` at razor
angles (the old grid missed exactly-90.0 and 120.0, which DO clip).

**The analytic reduction.** The clip is decided by two independent conditions:

  1. **LineCheck miss** — the line's crossing with plane A and its crossing with plane B must each
     land just *past* the seam vertex (outside their own triangle's ``incl_box2d``). This happens
     iff the line passes within the fan offset of ``S``. So we do NOT search start-position freely:
     we **pin the line through S** (offset ``rho`` ~ 0) and only micro-scan ``rho`` at fan
     resolution. The travel *direction* has a broad window and the *displacement* ``D`` an even
     broader one (~35 up to ~95), so those are swept coarsely.
  2. **WallCorrect miss + a settled old** — both ends must clear the radius-35 wall cylinder. The
     endpoint clears cheaply (once ``new`` is behind the wall face, WallCorrect's directional test
     lets it pass, so it needs only a hair past ``S``). The DOMINANT term is the *old* position:
     ``old_pos`` must be a settled WallCorrect fixed point (the game never carries an old_pos inside
     the cylinder), so it sits ``~wall_r / sin(halfangle)`` in front — e.g. 37.6 u for the GanonL
     137-deg corner (``35/sin(68.5)``), ~35 u for a right-angle corner approached off the bisector.
     That front clearance sets the **min-speed** (geometry-dependent, ~35-38 u, NOT a flat 35).

Feeding the exact bit-exact FP model (:func:`tww_sim.core.collision.crr_pos_walls`) at the pinned
offsets makes "gap found" reliable and cheap. "No gap found" is only trustworthy when the offset
step is finer than the fan (see :func:`fan_offset_scale` and ``off_step`` — the default is fine
enough for real corners; for near-flat seams pass a smaller ``off_step``).

**f32-HONESTY (do NOT remove).** Link's position is stored as f32 (``cXyz`` = three f32;
``pm_pos``/``pm_old_pos`` are ``cXyz*``, ``d_bg_s_acch.h``), and ``core.fp`` is only console-faithful
when fed f32 (see its docstring). So every candidate ``old``/``new`` is snapped to f32 (:func:`_p32`)
before the model runs. This is not cosmetic: a blind double-precision search reports **false-positive**
clips at sub-ULP offsets the game can never occupy. Measured at the live (-1727,-990) seam: a
rel=-14deg direction has 9 "clips" over a 0.04u rho span in double precision but **0** survive f32
rounding, whereas the genuine clip zone (rel~+45deg) survives f32 (2571 vs 2573 of 20001 samples).
The continuous/double "gap window" is therefore only an upper bound — practical viability is decided
by whether an f32-representable position lands in it (``knowledge/mechanics/seam-clip.md``).

Geometry-agnostic: pass the 4 wall triangles (``tris[1]`` = wall-A seam triangle, ``tris[2]`` =
wall-B seam triangle — the convention :func:`angle_experiment.build_angle` and the GanonL
``seam_model`` both use) plus the seam XZ point and Link's floor Y.
"""
import math
import struct

from tww_sim.core.collision import acch_crr_pos, crr_pos_walls, wall_correct
from tww_sim.core.fp import f32 as _f

WALL_H = (30.1, 89.9, 125.0)   # player wall-cylinder heights (setBgCheckParam)
WALL_R = 35.0                  # player wall-cylinder radius (standing/walking)


# f32-HONESTY: snap every candidate to f32 before the model — Link's pos is f32 (cXyz), and a
# double-precision search FALSE-POSITIVES on sub-ULP gaps (see the module docstring + seam-clip.md).
def _p32(x, y, z):
    return (_f(x), _f(y), _f(z))


def _is_clip(tris, ix, iz, ex, ez, link_y):
    _, info = crr_pos_walls(_p32(ix, link_y, iz), _p32(ex, link_y, ez), tris)
    return (not info["line_hit"]) and (not info["wall_hit"])


def _is_settled(tris, p, wall_h=WALL_H, wall_r=WALL_R):
    """True if ``p`` is a physical ``old_pos`` — a WallCorrect fixed point (Link not overlapping any
    wall). CrrPos always leaves ``pm_old_pos`` settled, so a clip's old_pos must clear the radius-35
    cylinder; a raw point deep inside it is not a position the game would ever carry. ``p`` is
    snapped to f32 first (Link's stored position is f32)."""
    p = _p32(p[0], p[1], p[2])
    q, hit = wall_correct(p, 0.0, tris, wall_h, wall_r)
    return (not hit) and ((q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2) ** 0.5 < 1e-4


def bisector_dir(tris):
    """Front->back travel direction along the corner bisector: ``-(nA + nB)`` normalised, from the
    two seam triangles' planes. Returned as ``atan2(dx, dz)`` so ``d = (sin, cos)``."""
    pA, pB = tris[1].pla, tris[2].pla
    bx, bz = -(pA.nx + pB.nx), -(pA.nz + pB.nz)
    return math.atan2(bx, bz)


def _line(seam, ang, rho, D, t_back):
    """A swept line pinned to pass through ``S + rho*perp`` travelling at ``ang``. ``old`` sits
    ``t_back`` u before that point (in front of the walls), ``new`` ``D - t_back`` u past it."""
    dx, dz = math.sin(ang), math.cos(ang)
    px, pz = -dz, dx
    cx, cz = seam[0] + rho * px, seam[1] + rho * pz
    return (cx - t_back * dx, cz - t_back * dz,        # old x,z
            cx + (D - t_back) * dx, cz + (D - t_back) * dz)  # new x,z


def offset_window(tris, seam, link_y, ang, D=40.0, t_back=3.0,
                  off_half=0.006, off_step=2e-5):
    """All perpendicular offsets ``rho`` (line pinned through ``S``, travelling at ``ang``) that
    clip, at this displacement. The clipping ``rho`` form a single contiguous fan-width interval;
    returns the sorted list (empty if none)."""
    hits = []
    n = int(2 * off_half / off_step) + 1
    for j in range(n):
        rho = -off_half + j * off_step
        ix, iz, ex, ez = _line(seam, ang, rho, D, t_back)
        if _is_clip(tris, ix, iz, ex, ez, link_y):
            hits.append(rho)
    return hits


def screen_gaps(tris, seam, link_y, D=40.0, t_back=3.0,
                dir_half_deg=80.0, dir_step_deg=1.0, off_half=0.0005, off_step=2e-5,
                merge_deg=4.0):
    """Every bisector-relative travel direction within ``+/- dir_half_deg`` where the swept line
    MISSES LineCheck (a gap exists), clustered into contiguous windows and returned as those windows'
    centre rels, ORDERED by proximity to the bisector. Empty == no gap anywhere == unclippable.

    Unlike :func:`find_clip` (which returns only the FIRST gap it hits, an oblique grazing edge on a
    symmetric corner), this reports ALL gap windows so the caller can f32-search each: an asymmetric
    corner's clip window is fully oblique (the head-on approach is covered by a long diagonal wall),
    while a symmetric corner clips near the bisector — both must be found."""
    base = bisector_dir(tris)
    n = int(2 * dir_half_deg / dir_step_deg) + 1
    gap_rels = []
    for i in range(n):
        rel = -dir_half_deg + i * dir_step_deg
        ang = base + math.radians(rel)
        if offset_window(tris, seam, link_y, ang, D, t_back, off_half, off_step):
            gap_rels.append(rel)
    if not gap_rels:
        return []
    centers, lo, prev = [], gap_rels[0], gap_rels[0]
    for r in gap_rels[1:]:
        if r - prev > merge_deg:
            centers.append((lo + prev) / 2.0)
            lo = r
        prev = r
    centers.append((lo + prev) / 2.0)
    centers.sort(key=abs)
    return centers


def find_clip(tris, seam, link_y, D=40.0, t_back=3.0,
              dir_half_deg=50.0, dir_step_deg=0.5,
              off_half=0.006, off_step=2e-5, physical=True):
    """Search for ANY clipping line for this corner. Sweeps travel direction over
    ``bisector +/- dir_half_deg`` and micro-scans the offset at each. Returns ``(clipped, rec)``
    for the first clip found, else ``(False, None)``.

    With ``physical=True`` (default) the returned ``old`` is a genuine **standable** position — a
    settled WallCorrect fixed point in front of the walls (via :func:`min_displacement_for_line`),
    and ``new`` is the minimal step past the seam; ``rec`` = ``dict(rel_deg, rho, old, new, D,
    t_back, t_fwd)``. With ``physical=False`` it returns the raw pinned line at the fixed ``t_back``
    (``old`` may sit inside the wall cylinder — useful only for detection, not for a real setup)."""
    base = bisector_dir(tris)
    nd = int(2 * dir_half_deg / dir_step_deg) + 1
    for i in range(nd):
        rel = -dir_half_deg + i * dir_step_deg
        ang = base + math.radians(rel)
        hits = offset_window(tris, seam, link_y, ang, D, t_back, off_half, off_step)
        if hits:
            rho = hits[len(hits) // 2]
            if physical:
                r = min_displacement_for_line(tris, seam, link_y, ang, rho)
                if r is None:
                    continue          # this direction has no physical (settled-old) clip; keep looking
                Dp, tb, tf = r
                dx, dz = math.sin(ang), math.cos(ang)
                px, pz = -dz, dx
                cx, cz = seam[0] + rho * px, seam[1] + rho * pz
                # return the actual f32-representable positions (what the game would hold)
                old = (_f(cx - tb * dx), _f(cz - tb * dz))
                new = (_f(cx + tf * dx), _f(cz + tf * dz))
                return True, dict(rel_deg=round(rel, 3), rho=rho, old=old, new=new,
                                  D=Dp, t_back=tb, t_fwd=tf)
            ix, iz, ex, ez = _line(seam, ang, rho, D, t_back)
            return True, dict(rel_deg=round(rel, 3), rho=rho,
                              old=(_f(ix), _f(iz)), new=(_f(ex), _f(ez)), D=D)
    return False, None


def min_displacement_for_line(tris, seam, link_y, ang, rho, step=0.05, reach=90.0):
    """Smallest one-frame displacement ``|new - old|`` that yields a genuine seam clip on the pinned
    line ``(ang, rho)``, using a PHYSICAL ``old_pos`` (a settled WallCorrect fixed point in front).
    ``line_check`` depends only on the line (not where ``old`` sits, verified), so we minimise the
    two ends independently: ``t_fwd`` = least distance past ``S`` where the endpoint clears
    WallCorrect (``new`` is already behind the wall face, so this is small), ``t_back`` = least
    distance in front where ``old`` is settled AND still on the front side (this is the dominant
    term — ~``wall_r / sin(halfangle)`` to clear the wall faces). Returns ``(D, t_back, t_fwd)`` or
    ``None``."""
    dx, dz = math.sin(ang), math.cos(ang)
    px, pz = -dz, dx
    cx, cz = seam[0] + rho * px, seam[1] + rho * pz
    old_far = (cx - reach * dx, link_y, cz - reach * dz)   # deeply-settled reference old
    pA, pB = tris[1].pla, tris[2].pla
    # min t_fwd: endpoint clears WallCorrect (full clip against a settled old)
    t_fwd = None
    t = step
    while t <= reach:
        new = (cx + t * dx, link_y, cz + t * dz)
        if _is_clip(tris, old_far[0], old_far[2], new[0], new[2], link_y):
            t_fwd = t
            break
        t += step
    # min t_back: old settled AND in front of both walls (fA, fB > 0)
    t_back = None
    t = step
    while t <= reach:
        ox, oz = cx - t * dx, cz - t * dz
        fA = pA.d + pA.nx * ox + pA.ny * link_y + pA.nz * oz
        fB = pB.d + pB.nx * ox + pB.ny * link_y + pB.nz * oz
        if fA > 0 and fB > 0 and _is_settled(tris, (ox, link_y, oz)):
            t_back = t
            break
        t += step
    if t_fwd is None or t_back is None:
        return None
    old = (cx - t_back * dx, link_y, cz - t_back * dz)
    new = (cx + t_fwd * dx, link_y, cz + t_fwd * dz)
    if not _is_clip(tris, old[0], old[2], new[0], new[2], link_y):
        return None
    D = ((new[0] - old[0]) ** 2 + (new[2] - old[2]) ** 2) ** 0.5
    return round(D, 3), round(t_back, 3), round(t_fwd, 3)


def characterize(tris, seam, link_y, D=40.0, t_back=3.0,
                 dir_half_deg=50.0, dir_step_deg=0.5,
                 off_half=0.006, off_step=2e-5):
    """Full analytic characterisation of a corner's gap: the clippable direction window, the offset
    window (at the central clipping direction), and the min displacement. Returns a dict, or
    ``dict(clippable=False)`` if no gap survives the scan.

    NOTE: ``min_displacement`` here is an **over-estimate** — this continuous machinery pins the line
    through S and requires a settled old at a swept t_back, missing lower-displacement approaches.
    For the authoritative clippable/min-displacement answer use :func:`min_f32_clip` (direct
    f32-lattice search). At the live (-1727,-990) seam this reports ~63 u where ``min_f32_clip``
    finds the true 49.9 u."""
    base = bisector_dir(tris)
    clip_dirs = []
    nd = int(2 * dir_half_deg / dir_step_deg) + 1
    for i in range(nd):
        rel = -dir_half_deg + i * dir_step_deg
        ang = base + math.radians(rel)
        hits = offset_window(tris, seam, link_y, ang, D, t_back, off_half, off_step)
        if hits:
            clip_dirs.append((rel, hits))
    if not clip_dirs:
        return dict(clippable=False)
    # True min displacement (physical settled old) over ALL clipping directions.
    best = None
    for rel, off in clip_dirs:
        ang = base + math.radians(rel)
        rho = off[len(off) // 2]
        r = min_displacement_for_line(tris, seam, link_y, ang, rho)
        if r is not None and (best is None or r[0] < best[0]):
            best = (r[0], rel, rho, r[1], r[2])
    # central clipping direction (for the offset-window report)
    rel_c, off_c = clip_dirs[len(clip_dirs) // 2]
    return dict(
        clippable=True,
        dir_window_deg=(clip_dirs[0][0], clip_dirs[-1][0]),
        dir_window_width_deg=round(clip_dirs[-1][0] - clip_dirs[0][0], 3),
        offset_window=(round(min(off_c), 6), round(max(off_c), 6)),
        offset_window_width=round(max(off_c) - min(off_c), 6),
        min_displacement=(best[0] if best else None),
        min_disp_at=(dict(rel_deg=best[1], rho=best[2], t_back=best[3], t_fwd=best[4])
                     if best else None),
    )


def _next_f32(x, d):
    """The f32 that is ``d`` ULPs away from f32 ``x`` (magnitude-directed: +d moves away from 0)."""
    b = struct.unpack("<I", struct.pack("<f", _f(x)))[0]
    b = (b + d) if x >= 0 else (b - d)
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


def settle(tris, xz, link_y, wall_h=WALL_H, wall_r=WALL_R, iters=8):
    """Iterate WallCorrect to a settled f32 fixed point (what the game carries as ``pm_old_pos``).
    Returns the settled ``(x, y, z)`` as f32."""
    pos = _p32(xz[0], link_y, xz[1])
    for _ in range(iters):
        pos, _ = wall_correct(pos, 0.0, tris, wall_h, wall_r)
        pos = _p32(pos[0], pos[1], pos[2])
    return pos


def min_f32_clip(tris, old, new_center, link_y, box_ulps=400, wall_h=WALL_H, wall_r=WALL_R):
    """RELIABLE f32-lattice clip search — no false positives, no aliasing. Given a **settled f32**
    ``old`` (x,y,z) and a guess ``new_center`` (x,z) just behind the wall, enumerate every
    f32-representable ``new`` in a ``+/-box_ulps``-ULP box (in x and z) around ``new_center`` and
    return the minimum-displacement one that genuinely clips, or ``None``.

    This is the honest primitive the continuous ``find_clip``/``characterize`` machinery only
    approximates: because Link's position is f32 (``cXyz``), the ONLY reachable clips are on this
    lattice. It is O(box_ulps^2) model calls, so keep the box tight (a few hundred ULPs ~ a few
    hundredths of a unit near coord 1700). Returns ``dict(disp, new, old, n_clips)``."""
    cx, cz = _f(new_center[0]), _f(new_center[1])
    best = None
    n = 0
    for i in range(-box_ulps, box_ulps + 1):
        nx = _next_f32(cx, i)
        for j in range(-box_ulps, box_ulps + 1):
            nz = _next_f32(cz, j)
            _, info = crr_pos_walls(old, (nx, link_y, nz), tris, wall_h, wall_r)
            if (not info["line_hit"]) and (not info["wall_hit"]):
                n += 1
                disp = ((nx - old[0]) ** 2 + (nz - old[2]) ** 2) ** 0.5
                if best is None or disp < best[0]:
                    best = (disp, (nx, nz))
    if best is None:
        return None
    return dict(disp=best[0], new=best[1], old=(old[0], old[2]), n_clips=n)


def first_f32_clip(tris, old, new_center, link_y, box_ulps=120, wall_h=WALL_H, wall_r=WALL_R,
                   max_calls=None):
    """EXISTENCE variant of :func:`min_f32_clip` — return the FIRST clipping f32 ``new`` found,
    searched nearest-to-``new_center`` first (Chebyshev rings of growing ULP radius), then stop.

    We do not need the minimum-displacement clip (that is :func:`min_f32_clip`), only proof that a
    clip exists here plus one exact f32 ``new`` that performs it. ``new_center`` (a continuous point
    just past the seam, inside the gap) is where a clip is most likely, so ring-search out from it and
    early-exit. ``max_calls`` caps the CrrPos evaluations (a bounded search that finds nothing is an
    honest 'unclippable-in-practice', since the position is f32). Returns ``(hit, n_calls)`` where
    ``hit`` = ``dict(disp, new, old)`` or None."""
    cx, cz = _f(new_center[0]), _f(new_center[1])
    n = 0
    for r in range(0, box_ulps + 1):
        for i in range(-r, r + 1):
            js = range(-r, r + 1) if abs(i) == r else (-r, r)
            for j in js:
                if max_calls is not None and n >= max_calls:
                    return None, n
                nx, nz = _next_f32(cx, i), _next_f32(cz, j)
                _, info = crr_pos_walls(old, (nx, link_y, nz), tris, wall_h, wall_r)
                n += 1
                if (not info["line_hit"]) and (not info["wall_hit"]):
                    disp = ((nx - old[0]) ** 2 + (nz - old[2]) ** 2) ** 0.5
                    return dict(disp=disp, new=(nx, nz), old=(old[0], old[2])), n
    return None, n


# FAST PATH: native (Cython) ring (_collc.first_f32_clip), 0-ULP vs the pure def above (absent .pyd ->
# pure). Wrapper keeps the pure call signature. See knowledge/mechanics/seam-clip-scanner.md.
_first_f32_clip_py = first_f32_clip
try:
    from tww_sim.core._collc import first_f32_clip as _first_f32_clip_native

    def first_f32_clip(tris, old, new_center, link_y, box_ulps=120, wall_h=WALL_H, wall_r=WALL_R,
                       max_calls=None):
        return _first_f32_clip_native(old, new_center, link_y, tris, wall_h=wall_h, wall_r=wall_r,
                                      box_ulps=box_ulps, max_calls=max_calls)

    first_f32_clip.__doc__ = _first_f32_clip_py.__doc__
except ImportError:
    pass


def first_f32_acch_clip(tris, old, new_center, link_y, box_ulps=120,
                        wall_h=WALL_H, wall_r=WALL_R, max_calls=None,
                        stable_tolerance=1e-3):
    """Return the nearest f32 endpoint accepted by Link's full CrrPos path.

    Unlike :func:`first_f32_clip`, this uses the player-faithful ``acch_crr_pos``
    implementation, including unconditional Link LineCheck, WallCorrect's exact
    sqrt behavior, and a second fixed-point pass. Moving-drop refinement must use
    this oracle because its final verifier uses the same path; targeting a point
    accepted only by the older ``crr_pos_walls`` model creates false near hits.
    """
    old = _p32(old[0], old[1], old[2])
    cx, cz = _f(new_center[0]), _f(new_center[1])
    n = 0
    for r in range(0, box_ulps + 1):
        for i in range(-r, r + 1):
            js = range(-r, r + 1) if abs(i) == r else (-r, r)
            for j in js:
                if max_calls is not None and n >= max_calls:
                    return None, n
                new = (_next_f32(cx, i), _f(link_y), _next_f32(cz, j))
                resolved, info = acch_crr_pos(
                    old, new, tris, wall_h=wall_h, wall_r=wall_r,
                )
                n += 1
                if info["line_hit"] or info["wall_hit"]:
                    continue
                stable, stable_info = acch_crr_pos(
                    resolved, resolved, tris, wall_h=wall_h, wall_r=wall_r,
                )
                if stable_info["line_hit"] or stable_info["wall_hit"]:
                    continue
                if math.hypot(
                    stable[0] - resolved[0], stable[2] - resolved[2]
                ) > stable_tolerance:
                    continue
                disp = math.hypot(new[0] - old[0], new[2] - old[2])
                return dict(
                    disp=disp,
                    new=(new[0], new[2]),
                    old=(old[0], old[2]),
                    resolved=(resolved[0], resolved[2]),
                ), n
    return None, n


def fan_offset_scale(tris, seam):
    """Estimate the perpendicular-offset scale of the seam gap = how far the two triangles of a
    wall disagree on where the seam-crossing lands, driven by their 1-ULP plane-normal difference.
    A trustworthy "unclippable" verdict needs ``off_step`` a few times smaller than this."""
    def sep(p, q):
        # angular difference between the two normals -> lateral crossing separation over ~unit reach
        return math.hypot(p.nx - q.nx, p.nz - q.nz)
    # within-wall fans (A_up vs A_lo, B1 vs B2) AND the cross-wall seam-pair fan (A_seam vs B_seam,
    # the one that matters for a near-flat seam where the two walls are nearly coplanar).
    return max(sep(tris[0].pla, tris[1].pla),
               sep(tris[2].pla, tris[3].pla),
               sep(tris[1].pla, tris[2].pla))
