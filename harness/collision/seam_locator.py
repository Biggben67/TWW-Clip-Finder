"""Analytic seam-clip locator — the fast, COMPLETE rebuild of :mod:`seam_clip_check`.

Motivation (2026-07-08 research, handoff ``_notes/handoff-2026-07-08c-analytic-locator.md``): the
FIRST-EXPERIMENT finding is that the cheap prune ``{cone ∧ floor ∧ valid-old ∧ not-blocked}`` is a
SOUND SUPERSET of the real f32-clip set (it never drops a real clip) but is NOT tight — for
isolated / barrier-free corners it passes the WHOLE cone, so the final f32 verify is LOAD-BEARING,
not optional. The residual is genuine f32-razor loss (measured: FN0/FN1 have zero barriers and a
flat floor, yet f32 clips land only in a narrow sub-band), and it scales with coordinate magnitude
(local ULP vs the ~1e-3 fan gap).

The key STRUCTURE (KB ``mechanics/seam-clip.md``): a clip is a LINE property — for a fixed travel
direction the LineCheck-miss window is a thin interval in the line's PERPENDICULAR offset ρ from the
seam vertex S (fan-width, ~1e-3 u), but it extends broadly ALONG the travel direction. The old
square-ULP ring search failed exactly because it conflated the two axes (too thin perpendicular at
high coord when the box was small; wrong along-track centre per ``tf``). This locator searches
ANISOTROPICALLY instead:

  * per hot-spot-ordered cone direction (bisector + edges are the hot spots), settle one valid,
    standable **deep** old (oblique approaches settle far back — floor+~8..20 — which was the earlier
    miss root-cause);
  * VERIFY along-track ``s`` in coarse WORLD steps (wide, catches the right distance past S) × a THIN
    f32 box perpendicular (fine — the clip sits within a few ULPs of the through-S line), using the
    FULL trilist (barriers included, so barriers are handled by the verify, not a separate — and
    unsound — direction-level block prune); first ``crr_pos`` clip → done;
  * RE-VERIFY the winning exact ``old``->``new`` against the WHOLE room's walls (``locate``). The
    per-seam barrier is gathered by edge-distance ``GATHER_R`` around S at LINK'S floor Y, but it can
    still MISS a wall that blocks the swept clip — most sharply on a TALL corner where the standable
    floor sits hundreds of u above the seam-vertex Y (GanonK top-of-room), or a busy side corner
    (A_mori). A clip whose full-room sweep is stopped short (line/wall hit) is a phantom and dropped.
    Far walls can't touch the short cut segment, so this never false-NEGATIVES a real clip.

Both differing-normal corners AND single-normal COPLANAR flat-wall seams are searched (``enumerate_seams``
emits both; the line threads the f32 gap where two coplanar wall tris meet — A_mori (4077.6,-1708.8) is
a live-confirmed flat-wall clip). Nothing in the acceptance keys off the corner type.

Cheap rejection (fast, no f32 ring) comes from the standable-floor / valid-old gates: most genuinely
unclippable seams have no standable floor next to them and are dropped instantly. A per-seam f32
budget bounds the residual worst case (an isolated corner that cheap-passes the whole cone but whose
f32 gap is sub-ULP everywhere, e.g. the Hyrule 90° corners).

Result vs the committed :func:`seam_clip_check.scan_region` on Hyrule room 0 (190 seams): 106 s vs
680 s, and a strict SUPERSET — all 34 of the old scanner's clips PLUS 18 more (real, confirmed by
:func:`gap_search.min_f32_clip`; the old scanner missed them to its shallow-first, small-budget
search). KNOWN LIMITS: (1) the hardest unclippable corners (int≈90, cheap-pass-wide + sub-ULP gap)
still take ~2–5 s each to confirm — a native (Cython) port of the ``first_f32_clip`` ring is the
next lever for a hard per-seam <1 s; (2) ``disp`` is deep-first, so it is an UPPER bound, not the
minimum — use the analytic floor ``disp_floor(interior)`` for the reachability question (a clip is
roll-stab-reachable iff ``interior > 90.63°`` ⟺ ``floor ≤ 49.22``).

    python -m harness.collision.seam_locator stage=Hyrule room=0
    python -m harness.collision.seam_locator stage=Hyrule room=0 probe   # just the known-hard seams
"""
import json
import math
import os
import sys
import time

from tww_sim.core.collision import (line_check, crr_pos_walls,  # noqa: F401 (barriers in the verify)
                                     bg_blocks_crrpos)
from tww_sim.core.fp import f32 as _f
from harness.collision.seam_scan import (enumerate_seams, _gather, disp_floor, interior_angle_deg,
                                         GROUND_NY_MIN)
from harness.collision.seam_clip_check import (_seam_walls, _valid_initial, _floor_at, _wall_yspan,
                                               _representative_link_y, _is_step_riser,
                                               _cyl_overlaps_edge)
from harness.collision.gap_search import bisector_dir, settle, first_f32_clip, WALL_H

CONE_MARGIN = 6.0            # search a little past the analytic cone |rel| <= interior/2
CONE_STEP = 1.0             # direction step (deg); 1° avoids skipping narrow valid-old regions
DIST_OFFSETS = (16.0, 12.0, 8.0, 20.0, 4.0, 0.0)   # settled-old distance past floor; DEEP first
S_LO, S_HI, S_STEP = 0.1, 2.2, 0.12                # along-track world scan just past S
BOX_ULP = 18               # thin perpendicular f32 box (clip sits near the through-S line)
PER_S_MAX = 1400           # cap f32 CrrPos calls per along-track centre
SEAM_BUDGET = 200_000      # per-seam f32 budget (bounds the sub-ULP cheap-pass-wide worst case)
ROLL_STAB_MAX = 49.2202    # max single-frame roll-stab lunge


def _ordered_rels(half):
    """Cone directions (bisector-relative deg) ordered by proximity to the nearer HOT SPOT — the
    bisector (0) or an edge (±interior/2) — so a clippable seam early-exits before the budget drains
    on empty mid-cone directions."""
    lim = half + CONE_MARGIN
    rels = [0.0]
    g = CONE_STEP
    while g <= lim:
        rels += [g, -g]
        g += CONE_STEP
    rels.sort(key=lambda r: (round(min(abs(r), abs(half - abs(r))), 3), abs(r)))
    return rels


def locate_geo(barrier_tris, ground_tris, S_xz, wA, wB, yspan=None, override_link_y=None,
               require_standable=True, stats=None):
    """Geometry-first core: decide whether the seam at ``S_xz`` (between walls ``wA``/``wB``) clips
    from a WallCorrect-STANDABLE old, and return one exact clip dict or ``None``. This is the reusable
    API the region wrapper :func:`locate` and any geometry-holder (e.g. ``SeamGeo.roll_reachable``)
    call directly -- no region/seam dicts, no re-enumeration.

      barrier_tris     : the gathered near-wall CrrPos barrier :class:`Tri` (WITHOUT the leading
                         [wA, wA, wB]; this prepends them, as the scanners do).
      ground_tris      : ground :class:`Tri`-dicts for the standable-floor gates; ``[]`` with an
                         ``override_link_y`` = a caller that already knows the seam stands on flat
                         ground (mirrors ``seam_clip_check.clip_check``'s override).
      override_link_y  : force a flat floor Y (skip the per-(x,z) ``_floor_at`` lookup).
      require_standable: as ``_valid_initial`` -- False when a flat ``override_link_y`` already
                         guarantees standability.

    ``disp`` is a deep-first UPPER bound (see the module docstring). Returns ``dict(S, interior, floor,
    disp, rel, s, reachable_rollstab, old, new)`` or ``None``."""
    if stats is None:
        stats = {}
    S = (S_xz[0], S_xz[-1])
    interior = interior_angle_deg((wA.pla.nx, 0.0, wA.pla.nz), (wB.pla.nx, 0.0, wB.pla.nz))
    floor = disp_floor(interior)
    if not math.isfinite(floor):
        return None
    base = bisector_dir([wA, wA, wB])
    half = interior / 2.0
    if yspan is None:
        yspan = _wall_yspan(wA, wB)
    tl = [wA, wA, wB] + list(barrier_tris)

    # SAME standable-floor + step/ledge-riser gates as seam_clip_check.clip_check (else the f32 verify
    # re-admits the OOB-skirt / step-riser phantoms). See knowledge/mechanics/seam-clip-scanner.md.
    rep_ly = _representative_link_y(ground_tris, S, base, half, floor, yspan, override_link_y)
    if rep_ly is None or _is_step_riser(ground_tris, S, yspan, rep_ly):
        return None

    budget = SEAM_BUDGET
    for rel in _ordered_rels(half):
        ang = base + math.radians(rel)
        dx, dz = math.sin(ang), math.cos(ang)
        old = None
        oy = None
        for off in DIST_OFFSETS:
            d = floor + off
            ox, oz = S[0] - d * dx, S[1] - d * dz
            oyt = override_link_y if override_link_y is not None else _floor_at(ground_tris, ox, oz, yspan)
            if oyt is None:
                continue
            cand = settle(tl, (ox, oz), oyt)
            if _valid_initial(tl, ground_tris, cand, wA, wB, yspan, require_standable):
                old, oy = cand, oyt
                break
        if old is None:
            continue
        # VERIFY anisotropic (barriers handled here — tl includes them; a direction-level line-block
        # prune is UNSOUND: a barrier can block the representative line while the true clip threads by).
        s = S_LO
        while s <= S_HI:
            hit, used = first_f32_clip(tl, old, (S[0] + s * dx, S[1] + s * dz), oy,
                                       box_ulps=BOX_ULP, max_calls=min(budget, PER_S_MAX))
            stats["verify_calls"] = stats.get("verify_calls", 0) + used
            budget -= used
            if hit is not None:
                disp = ((hit["new"][0] - old[0]) ** 2 + (hit["new"][1] - old[2]) ** 2) ** 0.5
                return dict(S=(S[0], oy, S[1]), interior=round(interior, 3), floor=round(floor, 3),
                            disp=round(disp, 4), rel=round(rel, 2), s=round(s, 2),
                            reachable_rollstab=floor <= ROLL_STAB_MAX,
                            old=old, new=(hit["new"][0], oy, hit["new"][1]))
            if budget <= 0:
                stats["capped"] = stats.get("capped", 0) + 1
                return None
            s += S_STEP
    return None


def locate(region, ground, seam, stats=None):
    """Decide whether ``seam`` clips and return one exact clip dict or ``None``. Thin REGION adapter
    over :func:`locate_geo`: extracts the two incident walls, the gathered CrrPos barrier, the local
    ground subset, and the wall Y-span from ``region``/``seam``, then defers to the shared core.

    ``region`` = list of tri dicts (``poly``/``v``/``n``/``T``); ``ground`` = its ground-tri subset;
    ``seam`` = an :func:`seam_scan.enumerate_seams` entry. Pure geometry, no Dolphin."""
    walls = _seam_walls(region, seam)
    if walls is None:
        return None
    wA, wB = walls
    polyset = set(seam["polys"])
    ys = [v[1] for t in region if t["poly"] in polyset for v in t["v"]]
    yspan = (min(ys), max(ys)) if ys else _wall_yspan(wA, wB)
    # local ground: only tris whose XZ AABB is within reach of S — floor_ys_at over the whole region
    # per cell was the entire cheap-pass cost. reach = deepest settled-old distance + a margin.
    interior = interior_angle_deg((wA.pla.nx, 0.0, wA.pla.nz), (wB.pla.nx, 0.0, wB.pla.nz))
    floor = disp_floor(interior)
    S = (seam["S"][0], seam["S"][2])
    R = (floor if math.isfinite(floor) else 60.0) + DIST_OFFSETS[3] + 45.0
    lg = [t for t in ground
          if not (max(v[0] for v in t["v"]) < S[0] - R or min(v[0] for v in t["v"]) > S[0] + R
                  or max(v[2] for v in t["v"]) < S[1] - R or min(v[2] for v in t["v"]) > S[1] + R)]
    # Gather the barrier at LINK'S floor Y, not the seam-vertex Y (the wall cylinder is at his feet; a
    # tall corner's floor sits far above the base, so a base gather drops the blocker). KB: seam-clip-scanner.md.
    rep_ly = _representative_link_y(lg, S, bisector_dir([wA, wA, wB]), interior / 2.0, floor, yspan)
    barrier = list(_gather(region, seam["S"], rep_ly if rep_ly is not None else seam["S"][1]))
    r = locate_geo(barrier, lg, seam["S"], wA, wB, yspan=yspan, stats=stats)
    if r is None:
        return None
    # Cull a phantom whose settled stance faces only one wall: the shared corner edge must be within
    # Link's cylinder at his floor (_cyl_overlaps_edge; the Omori/GanonK-top floating-seam FPs). KB.
    if not _cyl_overlaps_edge(r["old"][1], seam.get("edge_yspan")):
        if stats is not None:
            stats["edge_rejected"] = stats.get("edge_rejected", 0) + 1
        return None
    # FINAL soundness re-verify vs the FULL room walls: the edge-dist gather can miss a blocker, so drop
    # any clip whose full-room sweep is stopped short. Far walls can't touch the short segment (no FN). KB.
    old, new = r["old"], r["new"]
    po, pn = (_f(old[0]), _f(old[1]), _f(old[2])), (_f(new[0]), _f(old[1]), _f(new[2]))
    res, info = crr_pos_walls(po, pn, [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])])
    if info["line_hit"] or info["wall_hit"] or abs(res[0] - pn[0]) > 1e-2 or abs(res[2] - pn[2]) > 1e-2:
        if stats is not None:
            stats["fullroom_rejected"] = stats.get("fullroom_rejected", 0) + 1
        return None
    return r


def scan_region(region, box, require_standable=True, override_link_y=None, verbose=True,
                return_unknown=False):
    """Every clippable differing-normal vertical seam in ``box`` (sorted by displacement).

    ``require_standable`` / ``override_link_y`` are accepted for drop-in signature parity with
    :func:`seam_clip_check.scan_region` (so this is the shipped full-game scanner). The locator is
    intrinsically standable-only — it settles a real WallCorrect old on the local ground, so a seam
    with no standable floor is dropped regardless; ``require_standable=False`` (the old
    ``no-standable`` mode) therefore has no effect here, and ``override_link_y`` is unused (the floor
    Y is resolved per approach direction).

    ``return_unknown=True`` -> return ``(clips, unknown)`` where ``unknown`` is the list of seams the
    search could NOT resolve because it exhausted the per-seam ``SEAM_BUDGET`` mid cone-sweep (a
    cheap-passed corner whose f32 verify drained the cap without a hit AND without finishing). Those
    are genuinely UNDECIDED -- NOT proven unclippable -- so a caller (the batch scanner) can flag them
    rather than silently lump them with the no-clip seams. Each unknown entry is ``dict(S, interior,
    floor)`` (the enumerated seam vertex + interior angle + displacement lower bound). Default
    (``False``) returns just ``clips`` for signature parity with the old callers/tests."""
    ground = [t for t in region if t["n"][1] >= GROUND_NY_MIN]
    seams = enumerate_seams(region, box)
    clips = []
    unknown = []
    stats = {}
    for i, seam in enumerate(seams):
        capped_before = stats.get("capped", 0)
        r = locate(region, ground, seam, stats)
        if r is not None:
            clips.append(r)
        elif stats.get("capped", 0) > capped_before:
            # budget-exhausted, no hit found -> UNDECIDED (the ONLY None cause that bumps `capped`; a
            # phantom-rejected or genuinely no-clip seam returns None without incrementing it).
            unknown.append(dict(S=seam["S"], interior=seam["interior"], floor=seam["floor"]))
        if verbose and (i + 1) % 25 == 0:
            print("  ...%d/%d seams, %d clippable, %d unknown"
                  % (i + 1, len(seams), len(clips), len(unknown)), flush=True)
    clips.sort(key=lambda r: r["disp"])
    if verbose:
        print("=== %d clippable, %d unknown of %d seams (verify_calls=%d, capped=%d) ==="
              % (len(clips), len(unknown), len(seams), stats.get("verify_calls", 0),
                 stats.get("capped", 0)), flush=True)
    return (clips, unknown) if return_unknown else clips


# hard seams (Hyrule room 0) that the old scanner or earlier prototypes got wrong — a quick probe.
_PROBE = [((1127, 1621), "FN0"), ((919, -7986), "FN1"), ((0, 586), "m0_586"),
          ((1769, 745), "m1769"), ((-477, -15832), "m477"), ((280, -997), "cap90-unclippable")]


def main(argv):
    from harness.collision.dzb_iso import load_room_region
    stage, room, probe = "Hyrule", 0, False
    for a in argv:
        if a.startswith("stage="):
            stage = a[6:]
        elif a.startswith("room="):
            room = int(a[5:])
        elif a == "probe":
            probe = True
    region, box, _ = load_room_region(stage, room)
    ground = [t for t in region if t["n"][1] >= GROUND_NY_MIN]
    seams = enumerate_seams(region, box)
    print("stage=%s room=%d: %d seams" % (stage, room, len(seams)), flush=True)
    if probe:
        for xz, lab in _PROBE:
            seam = min(seams, key=lambda s: (s["S"][0] - xz[0]) ** 2 + (s["S"][2] - xz[1]) ** 2)
            st = {}
            t = time.time()
            r = locate(region, ground, seam, st)
            print("  %-18s int=%.1f: %s (%.2fs, vcalls=%d)"
                  % (lab, seam["interior"],
                     ("CLIP disp=%.2f rel=%s s=%s reachable=%s"
                      % (r["disp"], r["rel"], r["s"], r["reachable_rollstab"])) if r else "NO CLIP",
                     time.time() - t, st.get("verify_calls", 0)), flush=True)
        return 0
    t = time.time()
    clips = scan_region(region, box)
    print("scanned in %.1fs" % (time.time() - t), flush=True)
    for c in clips[:20]:
        print("  CLIP S=(%.1f,%.1f,%.1f) int=%.1f disp<=%.2f %s"
              % (c["S"][0], c["S"][1], c["S"][2], c["interior"], c["disp"],
                 "roll-stab reachable" if c["reachable_rollstab"] else "needs push"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
