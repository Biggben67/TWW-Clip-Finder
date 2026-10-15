"""Out-of-the-box seam-clip checker: given a REGION (or a single seam), answer "is there a
clippable seam here, and what are the EXACT coordinates that perform the clip?" — accurately, with
NO parameters to get wrong, and fast (region scans complete in seconds, not minutes).

Scope (per the user's redirect): we do **not** compute the minimum-displacement clip for a seam
(that is :func:`gap_search.min_f32_clip`, an O(box²) lattice sweep). We only need to know a clip
**exists** and hand back one exact, physically valid ``(old, new)`` pair that performs it.

Hard requirements enforced here (all decided from the static DZB geometry — NOT from where Link
currently is, so the scan is Dolphin-free and its region is independent of Link):

  * **Existence, not minimum.** The reliable detector is the f32 lattice (:func:`first_f32_clip`):
    Link's position is f32, so only f32-representable ``new`` can clip. We ring-search out from a gap
    centre and return the FIRST clip (early-exit). A two-phase direction search finds it: a near-bisector
    sweep (symmetric corners) then, if empty, a screen-bracketed OBLIQUE band (asymmetric corners — the
    clip window skews fully off the bisector). The continuous screen only brackets where to look; it is
    anti-aligned with the exact f32 clip so it can't pinpoint it (see knowledge/mechanics/seam-clip.md).
  * **Standable, physically valid ``old``.** The returned initial position must be somewhere Link can
    actually stand: a DZB **ground** triangle under its XZ (:func:`seam_scan.floor_ys_at` — not Link's
    Y, not the wall base), the wall must reach that floor height, and ``old`` must be a WallCorrect
    fixed point against the FULL near-wall set (not embedded in / pushed out of any surrounding wall)
    and in front of both incident walls. ``require_standable=False`` (or ``override_link_y=``) skips
    the floor requirement for synthetic geometry (e.g. the self-test).

Self-test (reproduces the known GanonL grand-staircase clip, no hand params):
    python -m harness.collision.seam_clip_check --selftest
Region scan (live from a running Dolphin; needs the stage loaded):
    python -m harness.collision.seam_clip_check box=xmin,xmax,ymin,ymax,zmin,zmax
Offline replay of a captured region (no Dolphin):
    python -m harness.collision.seam_clip_check cache=region.json box=...
"""
import math
import sys

from tww_sim.core.collision import wall_correct, bg_is_wall
from harness.collision.gap_search import (first_f32_clip, settle,
                                          bisector_dir, WALL_H, WALL_R)
from harness.collision.seam_scan import (enumerate_seams, interior_angle_deg, disp_floor, _gather,
                                         floor_ys_at, read_region_tris, load_region_tris,
                                         GROUND_NY_MIN)

ROLL_STAB_MAX = 49.2202     # max single-frame roll-stab lunge (roll speedF 26 + CUT root 23.22)
STEP_EPS = 5.0              # tolerance (u) for floor-height matches in the step/ledge-riser test
GROUND_SNAP = 60.0          # m_ground_check_offset (d_bg_s_acch.cpp): per-frame ground snap-up range


def _wall_yspan(*walls):
    ys = [v[1] for w in walls for v in (w.v0, w.v1, w.v2)]
    return (min(ys), max(ys)) if ys else (None, None)


# f32-lattice search: ``new`` box half-width BOX_WORLD (world u -> ULPs, cap BOX_ULP_MAX); FWD_TFS
# forward centres. The direction/distance search + budget are below.
BOX_WORLD, BOX_ULP_MAX = 0.10, 300
FWD_TFS = (0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.05)

# Sweep the analytic cone |rel| <= interior/2 (+CONE_MARGIN), bisector-first. Cone bound + why the
# whole cone is swept (not sampled): knowledge/mechanics/seam-clip-scanner.md ("DETERMINISTIC model").
CONE_STEP, CONE_MARGIN = 1.0, 6.0
# DEEP distances: an oblique approach settles ``old`` at floor + ~6..18 (farther than the bisector
# clearance); probing only floor+0..2 was the miss root-cause. Shallow-first = near-minimal disp.
DIST_OFFSETS = (0.0, 1.0, 2.0, 4.0, 7.0, 10.0, 13.0, 16.0, 19.0)
CONE_BUDGET = 1_200_000          # per-seam CrrPos-eval cap (a real clip early-exits well under it)
PER_CALL_MAX = 8_000             # cap per first_f32_clip so one empty direction can't drain the budget


def _cyl_overlaps_edge(link_y, edge_yspan):
    """Is the SHARED vertical seam edge within Link's cylinder at stance ``link_y``? A corner clip
    needs BOTH walls present at Link's height; the shared edge (the seam ``enumerate_seams`` clustered)
    is exactly the y-band where both walls coexist. A stance whose cylinder (feet + ``WALL_H``) sits
    entirely ABOVE or BELOW that edge faces only one wall (or none) -- the two-plane fan cannot produce
    a clip, so it is a phantom regardless of what the f32 verify finds.

    Two real cases this culls (both user-flagged): Omori (2249.6,1772.6) -- edge y905..1227 but the
    standable floor is y358, ~420u BELOW the corner; GanonK top (+-250,-2902.6) -- edge y6997..7504 but
    the settled floor is y7770, ~260u ABOVE the corner (poly 1319 rises to y9917 ALONE, no corner there).
    Same collidability convention as :func:`_floor_at`. ``None`` edge span (synthetic geometry) = pass."""
    if edge_yspan is None:
        return True
    elo, ehi = edge_yspan
    return any(elo - 2.0 <= link_y + h <= ehi + 2.0 for h in WALL_H)


def _floor_at(ground_tris, x, z, yspan):
    """Top-most ground height under (x,z) where the seam wall (vertical span ``yspan``) is actually
    COLLIDABLE at Link's stance — i.e. at least one LineCheck cylinder sample (feet + ``WALL_H``) lies
    inside the wall span. None if no such floor.

    Without the cylinder-height test a floor is accepted whenever the wall merely reaches its Y, which
    admits OOB floors sitting just below a wall that tops out under Link's cylinder (a low skirt lip he
    steps over and never collides with). Live example: Hyrule's stage underside — floor Y≈-100, wall
    span (-1945, -99.6); the lowest sample -100+30.1=-70.2 is above the wall top, so the game never
    touches the wall and cannot clip it, yet the plane-only model reported a clip (user-flagged)."""
    ylo, yhi = yspan
    cands = []
    for y in floor_ys_at(ground_tris, x, z):
        if ylo is None or any(ylo - 2.0 <= y + h <= yhi + 2.0 for h in WALL_H):
            cands.append(y)
    return max(cands) if cands else None


def _valid_initial(trilist, ground_tris, p, wallA, wallB, yspan, require_standable):
    """Is ``p=(x,y,z)`` a physically valid initial position? Not embedded in any wall (a WallCorrect
    fixed point against the full near-wall set), in front of both incident walls, and — when
    ``require_standable`` — standing on a DZB ground triangle at its feet (not in the air)."""
    q, hit = wall_correct(p, 0.0, trilist, WALL_H, WALL_R)
    if hit or ((q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2) ** 0.5 > 1e-3:
        return False                                   # inside / pushed out of a wall
    if wallA.pla.func(p) <= 0 or wallB.pla.func(p) <= 0:
        return False                                   # behind a wall, not on the approach side
    if not require_standable:
        return True
    return _floor_at(ground_tris, p[0], p[2], yspan) is not None


def _representative_link_y(ground_tris, S, base, half_cone, floor, yspan, override_link_y=None):
    """A representative standable floor Y next to the seam (for the step-riser test / seam Y). Probes
    several cone directions — not just the bisector, since an oblique-only floor still clips — at a
    few settled-old distances. Returns the first floor found, ``override_link_y`` if given, or None
    when there is no standable floor at the wall's height."""
    if override_link_y is not None:
        return override_link_y
    for rel in (0.0, half_cone * 0.5, -half_cone * 0.5, half_cone, -half_cone):
        a = base + math.radians(rel)
        for dd in (floor, floor + 9.0, floor + 18.0):
            ly = _floor_at(ground_tris, S[0] - dd * math.sin(a), S[1] - dd * math.cos(a), yspan)
            if ly is not None:
                return ly
    return None


def _is_step_riser(ground_tris, S, yspan, link_y):
    """STEP / LEDGE RISER (not a clip): a floor staircase at the seam XZ that climbs to the wall CROWN
    in <= GROUND_SNAP hops means Link ascends onto the top floor instead of clipping. See
    seam-clip-scanner.md "Standability". False without a ground mesh or a floor."""
    if not (ground_tris and link_y is not None):
        return False
    yhi = yspan[1]
    reach = link_y
    for fy in sorted(f for f in floor_ys_at(ground_tris, S[0], S[1]) if f >= link_y - STEP_EPS):
        if fy - reach <= GROUND_SNAP + STEP_EPS:
            reach = max(reach, fy)
    return reach >= yhi - STEP_EPS


def clip_check(barrier_tris, ground_tris, S, wallA, wallB,
               require_standable=True, override_link_y=None, roll_stab=ROLL_STAB_MAX, yspan=None):
    """Decide whether a single seam clips and, if so, return the exact coords that perform it.

    ``barrier_tris`` = ALL near wall :class:`Tri` (the CrrPos barrier set); ``ground_tris`` = the
    region's ground-triangle dicts (for the standable-floor lookup); ``S`` = seam vertex (x,z);
    ``wallA``/``wallB`` = the two incident wall Tri (their planes give the bisector).

    Returns ``dict(clips, old, new, link_y, interior, floor, disp, standable, reachable_rollstab,
    needs_push, reason)``. ``old``/``new`` are full (x,y,z) world coords; ``reachable_rollstab`` =
    the found clip's displacement ``<= roll_stab`` (a bare roll-stab reaches it; else a Tetra push
    is needed). We sweep the settled-old distance from the cylinder floor upward and stop at the
    first standable f32 clip, so ``disp`` is near-minimal (existence + performable coords, NOT the
    exact minimum)."""
    interior = interior_angle_deg((wallA.pla.nx, 0.0, wallA.pla.nz),
                                  (wallB.pla.nx, 0.0, wallB.pla.nz))
    floor = disp_floor(interior)
    # yspan = the wall's FULL vertical extent (union of all incident tris; scan_region passes it). A lone
    # representative Tri can be the UPPER half only, so the floor check would reject the real floor.
    if yspan is None:
        yspan = _wall_yspan(wallA, wallB)

    def nore(reason):
        return dict(clips=False, old=None, new=None, link_y=override_link_y,
                    interior=round(interior, 3), floor=round(floor, 3), disp=None,
                    standable=None, needs_push=None, reachable_rollstab=False, reason=reason)

    if not math.isfinite(floor):
        return nore("flat corner (interior ~180) — unclippable")

    base = bisector_dir([wallA, wallA, wallB])          # front->back travel dir (into the wall)
    half_cone = interior / 2.0

    # link_y = a representative standable floor for the step-riser check (several cone directions).
    link_y = _representative_link_y(ground_tris, S, base, half_cone, floor, yspan, override_link_y)
    if link_y is None:
        return nore("no standable floor next to the seam at the wall's height")
    if _is_step_riser(ground_tris, S, yspan, link_y):
        return nore("wall crown reachable by a ground-snap staircase (step/ledge riser) — "
                    "Link ascends, not clippable")

    trilist = [wallA, wallA, wallB] + list(barrier_tris)

    # f32 ``new`` box = fixed world window (±BOX_WORLD u) -> ULPs (grows near origin). Positives
    # early-exit in the first rings; detection must NOT be ULP-coarsened (see seam-clip.md).
    ulp = max(abs(S[0]), abs(S[1]), 1.0) * 2 ** -23
    box_ulps = max(24, min(BOX_ULP_MAX, int(BOX_WORLD / ulp)))

    def search(rels, budget, dists):
        """f32-search the given travel directions (bisector-relative rels, already ordered) for the
        first standable clip, trying each settled-old distance in ``dists``. Returns
        (clip_dict|None, remaining_budget). Fewer ``dists`` == a lighter probe per direction, so a wide
        grid can reach an oblique window without the empty directions draining the budget first."""
        for rel in rels:
            ang = base + math.radians(rel)
            dx, dz = math.sin(ang), math.cos(ang)
            for d in dists:
                ox, oz = S[0] - d * dx, S[1] - d * dz
                ly = override_link_y if override_link_y is not None else \
                    _floor_at(ground_tris, ox, oz, yspan)
                if ly is not None:
                    old = settle(trilist, (ox, oz), ly)
                    if _valid_initial(trilist, ground_tris, old, wallA, wallB, yspan,
                                      require_standable):
                        for tf in FWD_TFS:
                            hit, used = first_f32_clip(trilist, old,
                                                       (S[0] + tf * dx, S[1] + tf * dz), ly,
                                                       box_ulps=box_ulps,
                                                       max_calls=min(budget, PER_CALL_MAX))
                            budget -= used
                            if hit is not None:
                                new = (hit["new"][0], ly, hit["new"][1])
                                disp = ((new[0] - old[0]) ** 2 + (new[2] - old[2]) ** 2) ** 0.5
                                return dict(clips=True, old=old, new=new, link_y=ly,
                                            interior=round(interior, 3), floor=round(floor, 3),
                                            disp=round(disp, 4),
                                            standable=(require_standable or None),
                                            needs_push=disp > roll_stab,
                                            reachable_rollstab=disp <= roll_stab,
                                            reason="clip"), budget
                            if budget <= 0:
                                return None, 0
        return None, budget

    dists = [floor + o for o in DIST_OFFSETS]

    # Cone directions, ordered by proximity to a hot spot (bisector / either edge +-interior/2) so
    # early-exit fires before the budget drains on empty mid-cone directions. Rationale: scanner KB page.
    lim = half_cone + CONE_MARGIN
    rels = [0.0]
    g = CONE_STEP
    while g <= lim:
        rels += [g, -g]
        g += CONE_STEP
    rels.sort(key=lambda r: (round(min(abs(r), abs(half_cone - abs(r))), 3), abs(r)))
    hit, _ = search(rels, CONE_BUDGET, dists)
    if hit is not None:
        return hit
    return nore("no standable f32-representable clip (sub-ULP gap or unclippable geometry)")


def _seam_walls(region_tris, seam):
    """The two incident wall Tri meeting at the seam. For a differing-normal corner, one representative
    per distinct wall normal. For a COPLANAR seam (``seam['coplanar']`` -- a flat wall's own
    tessellation edge), two coplanar tris from the single normal group (or the same tri twice): their
    planes are identical, so ``in_front``/behind reduce to the one wall plane -- exactly the flat-wall
    genuine-clip test. Prefer the pairing :func:`seam_scan.enumerate_seams` already computed
    (``seam['polys']`` -- robust when the two walls' seam vertices are slightly offset); fall back to
    XZ vertex-incidence. None only if NO wall tri is incident here."""
    polyset = set(seam.get("polys") or ())
    if polyset:
        inc = [t for t in region_tris if t["poly"] in polyset and bg_is_wall(t["n"][1])]
    else:
        sx, sz = seam["S"][0], seam["S"][2]
        inc = [t for t in region_tris if bg_is_wall(t["n"][1])
               and any(abs(v[0] - sx) < 0.1 and abs(v[2] - sz) < 0.1 for v in t["v"])]
    groups = {}
    for t in inc:
        groups.setdefault((round(t["n"][0], 4), round(t["n"][2], 4)), []).append(t)
    gk = sorted(groups, key=lambda k: -len(groups[k]))
    if not gk:
        return None
    if len(gk) < 2:
        # coplanar seam: two tris from the single normal group (identical planes), so the flat-wall
        # clip is still testable. Same tri twice if only one is incident (a lone free edge).
        g = groups[gk[0]]
        return g[0]["T"], (g[1]["T"] if len(g) > 1 else g[0]["T"])
    return groups[gk[0]][0]["T"], groups[gk[1]][0]["T"]


def scan_region(region_tris, box, require_standable=True, override_link_y=None, verbose=True):
    """Answer "are there clippable seams in this region?" Enumerate every differing-normal vertical
    seam in ``box`` and run :func:`clip_check` on each. Returns the clippable-seam result dicts (each
    with the seam ``S``), sorted by displacement. Pure geometry — no Dolphin (``region_tris`` may be
    live from :func:`seam_scan.read_region_tris` or offline from :func:`seam_scan.load_region_tris`).
    ``require_standable`` (default) drops seams with no standable floor next to them; set it False (or
    pass ``override_link_y``) to include them anyway."""
    ground = [t for t in region_tris if t["n"][1] >= GROUND_NY_MIN]
    seams = enumerate_seams(region_tris, box)
    if verbose:
        print("%d differing-normal vertical seams in region (%d ground tris)"
              % (len(seams), len(ground)), flush=True)
    clippable = []
    for i, seam in enumerate(seams):
        walls = _seam_walls(region_tris, seam)
        if walls is None:
            continue
        wallA, wallB = walls
        S = (seam["S"][0], seam["S"][2])
        # yspan = FULL vertical extent over ALL incident tris (a wall split lower+upper still registers);
        # gather barriers at the seam base so the cylinder band covers floor-level walls.
        polyset = set(seam["polys"])
        ys = [v[1] for t in region_tris if t["poly"] in polyset for v in t["v"]]
        yspan = (min(ys), max(ys)) if ys else _wall_yspan(wallA, wallB)
        barrier = _gather(region_tris, seam["S"], seam["S"][1])
        res = clip_check(barrier, ground, S, wallA, wallB, require_standable=require_standable,
                         override_link_y=override_link_y, yspan=yspan)
        # Cull a phantom whose settled stance faces only one wall: the shared corner edge must be within
        # Link's cylinder (see _cyl_overlaps_edge -- Omori/GanonK-top floating-seam false positives).
        if res["clips"] and not _cyl_overlaps_edge(res["old"][1], seam.get("edge_yspan")):
            res["clips"] = False
        if res["clips"]:
            # report the seam at the STANDABLE floor Y (clip is height-invariant), not the wall base
            # (which can sit far below reachable ground). See seam-clip-scanner.md "Reported seam Y".
            res["S"] = (seam["S"][0], res["link_y"], seam["S"][2])
            clippable.append(res)
            if verbose:
                print("  CLIP S=(%.1f,%.1f,%.1f) interior=%.2f disp=%.4f %s"
                      % (res["S"][0], res["S"][1], res["S"][2], res["interior"], res["disp"],
                         "ROLL-STAB reachable" if res["reachable_rollstab"] else "needs push"),
                      flush=True)
        if verbose and (i + 1) % 25 == 0:
            print("  ...%d/%d seams scanned, %d clippable" % (i + 1, len(seams), len(clippable)),
                  flush=True)
    clippable.sort(key=lambda r: r["disp"])
    if verbose:
        print("=== %d clippable of %d seams ===" % (len(clippable), len(seams)), flush=True)
    return clippable


def _selftest():
    """Reproduce the known GanonL grand-staircase clip with ZERO hand-set params (synthetic geometry
    from seam_model — no ground mesh, so override the floor Y and skip the standable requirement)."""
    from harness.collision.seam_model import SEAM_TRIS, LINK_Y
    S = (-847.632, -37336.613)
    print("GanonL self-test: seam S=%s (known clip)" % (S,), flush=True)
    res = clip_check(SEAM_TRIS, [], S, SEAM_TRIS[1], SEAM_TRIS[2],
                     require_standable=False, override_link_y=LINK_Y)
    print("  RESULT clips=%s disp=%s reachable_rollstab=%s needs_push=%s (interior %.2f, floor %.2f)"
          % (res["clips"], None if res["disp"] is None else round(res["disp"], 4),
             res["reachable_rollstab"], res["needs_push"], res["interior"], res["floor"]), flush=True)
    if res["clips"]:
        print("  old=%s\n  new=%s" % (tuple(round(c, 4) for c in res["old"]),
                                      tuple(round(c, 4) for c in res["new"])), flush=True)
    assert res["clips"], "SELF-TEST FAILED: scanner did not find the known GanonL clip"
    print("  SELF-TEST PASSED", flush=True)


def main(argv):
    if "--selftest" in argv:
        _selftest()
        return 0
    box = cache = None
    require_standable = "no-standable" not in argv
    for a in argv:
        if a.startswith("box="):
            box = tuple(float(x) for x in a[4:].split(","))
        elif a.startswith("cache="):
            cache = a[6:]
    if box is None:
        print("usage: python -m harness.collision.seam_clip_check --selftest"
              " | box=xmin,xmax,ymin,ymax,zmin,zmax [cache=region.json] [no-standable]")
        return 2
    if cache:
        region, stage = load_region_tris(cache)
    else:
        region, stage = read_region_tris(box)
    print("stage=%s region tris=%d" % (stage, len(region)), flush=True)
    scan_region(region, box, require_standable=require_standable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
