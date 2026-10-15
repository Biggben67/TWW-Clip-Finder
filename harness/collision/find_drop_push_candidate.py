"""First-principles bomb/small-pot B-drop candidate scan for one seam.

This is a thin scanner over the existing drop-push collision model. It keeps the
animation data loaded once, sweeps facing trig buckets and start-position phase,
then prints candidates whose decomp-derived center path crosses the target seam.
"""
from __future__ import annotations

import sys
import math
from dataclasses import dataclass

from harness.collision.drop_push_clip import (
    _floor_at,
    _load_region,
    _nearest_seam,
    _parse,
    _seam_walls,
    _valid_initial,
    _wall_yspan,
    bam_to_deg,
)
from tww_sim.core import drop_release as dr
from tww_sim.core.collision import acch_crr_pos, bg_blocks_crrpos
from tww_sim.core.fp import f32 as _f


@dataclass(frozen=True)
class DropPushSearchContext:
    region: list
    box: tuple
    seam_target: tuple
    seam: object
    wall_a: object
    wall_b: object
    yspan: tuple
    ground: list
    floors: list
    barriers: list
    walls: list
    anims: object
    skeleton: object


@dataclass(frozen=True)
class DropPushCandidate:
    frame: int
    object_type: str
    facing: int
    facing_range: tuple
    phase: float
    old: tuple
    push: tuple
    raw: tuple
    resolved: tuple
    stable_delta: float
    prop_wall: bool
    link_line: bool
    link_wall: bool
    oob_landing: bool
    seam_distance: float
    landing_floor: object
    wall_depths: tuple
    score: tuple


def prepare_search(region, box, seam_target):
    """Build geometry and animation state shared by a multi-frame search."""
    if box is None:
        raise ValueError("a search box is required")
    seam = _nearest_seam(region, box, seam_target)
    if seam is None:
        raise ValueError("no seam was found near the supplied coordinates")
    seam_target = (
        seam_target[0],
        seam.get("test_y", seam["S"][1]),
        seam_target[2],
    )
    wall_pair = _seam_walls(region, seam)
    if wall_pair is None:
        raise ValueError("target seam does not have two incident wall planes")
    wall_a, wall_b = wall_pair
    # A B-drop moves each actor by less than 60 units. Restrict repeated floor
    # and Acch passes to triangles whose AABB reaches the local search volume;
    # the room cache can otherwise contain hundreds of distant triangles.
    margin = 80.0
    xmin, xmax, ymin, ymax, zmin, zmax = box
    local_region = []
    for tri in region:
        vertices = tri["v"]
        if (
            max(v[0] for v in vertices) >= xmin - margin
            and min(v[0] for v in vertices) <= xmax + margin
            and max(v[1] for v in vertices) >= ymin - margin
            and min(v[1] for v in vertices) <= ymax + margin
            and max(v[2] for v in vertices) >= zmin - margin
            and min(v[2] for v in vertices) <= zmax + margin
        ):
            local_region.append(tri)
    ground = [t for t in local_region if t["n"][1] >= 0.5]
    floors = [t for t in local_region if t["n"][1] >= 0.014]
    barriers = [t["T"] for t in local_region]
    walls = [t["T"] for t in local_region if bg_blocks_crrpos(t["n"][1])]
    return DropPushSearchContext(
        region=local_region,
        box=box,
        seam_target=seam_target,
        seam=seam,
        wall_a=wall_a,
        wall_b=wall_b,
        yspan=_wall_yspan(wall_a, wall_b),
        ground=ground,
        floors=floors,
        barriers=barriers,
        walls=walls,
        anims=dr.load_grab_anims(),
        skeleton=dr.load_skeleton(),
    )


def _front_phase_interval(context, mdx, mdz, lo, hi, padding):
    """Return the phase interval that can place Link in front of both walls."""
    sx, sy, sz = context.seam_target
    valid_lo, valid_hi = lo, hi
    for wall in (context.wall_a, context.wall_b):
        at_lo = wall.pla.func((sx - valid_lo * mdx, sy, sz - valid_lo * mdz))
        at_hi = wall.pla.func((sx - valid_hi * mdx, sy, sz - valid_hi * mdz))
        if at_lo <= 0.0 and at_hi <= 0.0:
            return None
        if (at_lo > 0.0) != (at_hi > 0.0):
            fraction = -at_lo / (at_hi - at_lo)
            crossing = valid_lo + fraction * (valid_hi - valid_lo)
            if at_lo > 0.0:
                valid_hi = min(valid_hi, crossing + padding)
            else:
                valid_lo = max(valid_lo, crossing - padding)
        if valid_lo > valid_hi:
            return None
    return valid_lo, valid_hi


def _candidate_crosses(context, old, step):
    """Require a genuine corner crossing behind both incident seam walls."""
    stable, stable_info = acch_crr_pos(step.link_after_bg, step.link_after_bg, context.walls)
    stable_delta = math.hypot(
        stable[0] - step.link_after_bg[0], stable[2] - step.link_after_bg[2]
    )
    old_front = (
        context.wall_a.pla.func(old) > 0.0
        and context.wall_b.pla.func(old) > 0.0
    )
    raw_behind = (
        context.wall_a.pla.func(step.link_raw) < 0.0
        and context.wall_b.pla.func(step.link_raw) < 0.0
    )
    resolved_behind = (
        context.wall_a.pla.func(step.link_after_bg) < 0.0
        and context.wall_b.pla.func(step.link_after_bg) < 0.0
    )
    crosses = (
        old_front
        and raw_behind
        and resolved_behind
        and not step.link_bg_info["wall_hit"]
        and not stable_info["wall_hit"]
        and stable_delta <= 1e-3
    )
    return crosses, stable_delta


def find_candidates(context, frame, object_type="bomb",
                    facing_ranges=((25000, 39000, 16),),
                    phases=(0.45, 0.98, 0.002), limit=20,
                    progress=None, cancelled=None,
                    require_oob_landing=False, oob_tolerance=0.005):
    """Search one displayed animation position using the decomp pose model."""
    sx, sy, sz = context.seam_target
    total_facings = sum(((hi - lo) // step) + 1 for lo, hi, step in facing_ranges)
    completed_facings = 0
    hits = []
    plo, phi, pstep = phases

    for flo, fhi, fstep in facing_ranges:
        for facing in range(flo, fhi + 1, fstep):
            if cancelled is not None and cancelled():
                return []
            # The free-space step seeds candidate old positions only. Every
            # candidate is transformed and collision-tested again at its exact
            # binary32 world position.
            ref_old = (_f(sx), _f(sy), _f(sz))
            ref_pose = dr.decomp_b_drop_pose(
                ref_old,
                facing,
                frame,
                object_type=object_type,
                anims=context.anims,
                skeleton=context.skeleton,
            )
            ref_step = dr.b_drop_collision_step(
                ref_old,
                ref_pose.link_co_center,
                ref_pose.link_co_height,
                ref_pose.held_prop_pos,
                object_type,
                [],
                link_co_radius=ref_pose.link_co_radius,
            )
            mdx, mdz = ref_step.link_push[0], ref_step.link_push[2]
            if abs(mdx) >= 1e-6 or abs(mdz) >= 1e-6:
                front_interval = _front_phase_interval(
                    context, mdx, mdz, plo, phi, 2.0 * pstep
                )
                p = front_interval[0] if front_interval is not None else phi + pstep
                phase_hi = front_interval[1] if front_interval is not None else phi
                # Preserve the caller's phase lattice after clipping the range.
                p = plo + max(0, int(math.ceil((p - plo) / pstep))) * pstep
                while p <= phase_hi + 1e-9:
                    if cancelled is not None and cancelled():
                        return []
                    ox = _f(sx - p * mdx)
                    oz = _f(sz - p * mdz)
                    oy = _floor_at(context.ground, ox, oz, context.yspan)
                    if oy is not None:
                        old = (ox, _f(oy), oz)
                        if _valid_initial(
                            context.barriers,
                            context.ground,
                            old,
                            context.wall_a,
                            context.wall_b,
                            context.yspan,
                            True,
                        ):
                            pose = dr.decomp_b_drop_pose(
                                old,
                                facing,
                                frame,
                                object_type=object_type,
                                anims=context.anims,
                                skeleton=context.skeleton,
                            )
                            step = dr.b_drop_collision_step(
                                old,
                                pose.link_co_center,
                                pose.link_co_height,
                                pose.held_prop_pos,
                                object_type,
                                context.walls,
                                link_co_radius=pose.link_co_radius,
                            )
                            crosses, stable_delta = _candidate_crosses(context, old, step)
                            if crosses and not step.prop_bg_info["wall_hit"]:
                                resolved = step.link_after_bg
                                seam_distance = math.hypot(
                                    resolved[0] - sx, resolved[2] - sz
                                )
                                landing_floor = _floor_at(
                                    context.ground,
                                    resolved[0],
                                    resolved[2],
                                    context.yspan,
                                )
                                wall_depths = (
                                    -context.wall_a.pla.func(resolved),
                                    -context.wall_b.pla.func(resolved),
                                )
                                oob_landing = (
                                    wall_depths[0] > 0.0
                                    and wall_depths[1] > 0.0
                                    and seam_distance <= oob_tolerance
                                    and landing_floor is not None
                                    and abs(landing_floor - old[1]) <= 1e-3
                                )
                                if require_oob_landing and not oob_landing:
                                    p += pstep
                                    continue
                                if require_oob_landing:
                                    score = (
                                        abs(stable_delta),
                                        seam_distance,
                                        abs(p - 1.0),
                                    )
                                else:
                                    score = (
                                        abs(stable_delta),
                                        abs(p - 0.74),
                                        abs(resolved[0] - sx) + abs(resolved[2] - sz),
                                    )
                                hits.append(DropPushCandidate(
                                    frame=frame,
                                    object_type=object_type,
                                    facing=facing,
                                    facing_range=(facing & ~0xF, (facing & ~0xF) + 15),
                                    phase=p,
                                    old=old,
                                    push=(step.link_push[0], step.link_push[2]),
                                    raw=(step.link_raw[0], step.link_raw[2]),
                                    resolved=(resolved[0], resolved[2]),
                                    stable_delta=stable_delta,
                                    prop_wall=step.prop_bg_info["wall_hit"],
                                    link_line=step.link_bg_info["line_hit"],
                                    link_wall=step.link_bg_info["wall_hit"],
                                    oob_landing=oob_landing,
                                    seam_distance=seam_distance,
                                    landing_floor=landing_floor,
                                    wall_depths=wall_depths,
                                    score=score,
                                ))
                    p += pstep
            completed_facings += 1
            if progress is not None and (
                    completed_facings == total_facings or completed_facings % 16 == 0):
                progress(completed_facings, total_facings)

    hits.sort(key=lambda hit: hit.score)
    return hits[:limit] if limit else hits


def _arg(argv, name, default=None):
    prefix = name + "="
    for arg in argv:
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return default


def _float_range(spec, default):
    if spec is None:
        return default
    parts = [float(p) for p in spec.split(":")]
    if len(parts) == 2:
        return parts[0], parts[1], default[2]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    raise ValueError("range must be lo:hi[:step]")


def _int_ranges(spec, default):
    if spec is None:
        return default
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        bits = [int(x, 0) for x in part.split(":")]
        if len(bits) == 2:
            bits.append(16)
        if len(bits) != 3:
            raise ValueError("facing ranges must be lo:hi[:step]")
        out.append(tuple(bits))
    return out


def main(argv):
    opts = _parse(argv)
    if opts["seam"] is None:
        print(
            "usage: python -m harness.collision.find_drop_push_candidate "
            "seam=x,y,z [cache=region.json box=...] "
            "[frame=5] [object=bomb] [facings=28000:32000:16] "
            "[phase=0.45:0.95:0.002] [limit=20]"
        )
        return 2

    frame = opts["frame"] or 5
    region, box, stage = _load_region(opts)
    sx, sy, sz = opts["seam"]
    landing_mode = _arg(argv, "landing", "clip").lower()
    if landing_mode not in ("clip", "oob"):
        raise ValueError("landing must be clip or oob")
    require_oob_landing = landing_mode == "oob"
    oob_tolerance = float(_arg(argv, "tolerance", "0.005"))
    default_phases = (0.9995, 1.0, 0.00005) if require_oob_landing else (0.45, 0.98, 0.002)
    phases = _float_range(_arg(argv, "phase"), default_phases)
    facing_ranges = _int_ranges(
        _arg(argv, "facings"),
        [(25000, 39000, 16)],
    )
    limit = int(_arg(argv, "limit", opts["limit"] or 20))

    context = prepare_search(region, box, opts["seam"])
    hits = find_candidates(
        context,
        frame,
        object_type=opts["object"],
        facing_ranges=facing_ranges,
        phases=phases,
        limit=limit,
        require_oob_landing=require_oob_landing,
        oob_tolerance=oob_tolerance,
    )
    print(
        "stage=%s room=%d object=%s seam=(%.6f,%.6f,%.6f) frame=%d "
        "model=decomp landing=%s hits=%d"
        % (stage, opts["room"], opts["object"], sx, sy, sz, frame,
           landing_mode, len(hits))
    )
    for hit in hits:
        print(
            "facing=%d facing_range=%d-%d facing_deg=%.6f phase=%.6f "
            "old=(%.9f,%.9f,%.9f) push=(%.9f,%.9f) raw=(%.9f,%.9f) "
            "resolved=(%.9f,%.9f) prop_wall=%s link_line=%s link_wall=%s "
            "stable_delta=%.9g oob_landing=%s seam_distance=%.9g "
            "landing_floor=%r wall_depths=%r score=%r"
            % (
                hit.facing,
                hit.facing_range[0],
                hit.facing_range[1],
                bam_to_deg(hit.facing),
                hit.phase,
                hit.old[0],
                hit.old[1],
                hit.old[2],
                hit.push[0],
                hit.push[1],
                hit.raw[0],
                hit.raw[1],
                hit.resolved[0],
                hit.resolved[1],
                hit.prop_wall,
                hit.link_line,
                hit.link_wall,
                hit.stable_delta,
                hit.oob_landing,
                hit.seam_distance,
                hit.landing_floor,
                hit.wall_depths,
                hit.score,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
