"""Offline bomb/small-pot B-drop setup generator and setup verifier.

The supplied CSV is interpreted as Link's measured local Co-push displacement,
captured from ``pos=(0,0), facing=0`` where +Z is forward.  The user-facing
animation position is one-based relative to the CSV: animation position 5 uses
CSV row 4.  That offset is calibrated by the documented GanonM setup; it is not
claimed as a decomp-derived animation convention.

The seam-only solver searches the source-ordered coupled path: prop background,
Co center recomputation, deferred Link correction, and Link background. It
solves backward from the seam along the actual coupled push instead of trying
to sample the sub-ULP clip window in world space. Results remain
``authoritative=False`` until the separate layered release-pose transforms are
generated exactly; they are table-calibrated generated setups, not direct CSV
endpoint guesses.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import math
import struct
import sys

from tww_sim.core.collision import acch_crr_pos, bg_blocks_crrpos, crr_pos_walls
from tww_sim.core.fp import f32 as _f, fadds
from tww_sim.core import fp
from tww_sim.core import drop_release as dr
from tww_sim.core import mathlib as M
from tww_sim.land.plan_land import world_angle_s16
from harness.collision.dzb_iso import load_room_region, load_room_region_from_iso
from harness.collision.dae_region import load_dae_region
from harness.collision.gap_search import bisector_dir, _next_f32
from harness.collision.seam_clip_check import (
    _floor_at, _is_step_riser, _seam_walls, _valid_initial, _wall_yspan,
    CONE_MARGIN, CONE_STEP,
)
from harness.collision.seam_scan import enumerate_seams, load_region_tris, _gather as gather_near_walls


DROP_MODEL_FAMILIES = {
    "bomb": "bomb_measured_drop",
    # Small pot B drops use the same measured XZ displacement table as bomb drops
    # for this setup class. Keep large pots separate until they have their own
    # calibration table.
    "pot_small": "bomb_measured_drop",
    "pot_large": "pot_large_measured_drop",
}

# The supplied measurements number rows from zero, while the animation position
# used in the documented setup is one-based: press B at 5 -> measured row 4.
DEFAULT_ANIMATION_TO_TABLE_OFFSET = -1
# The documented in-game regression is B at animation position 5 -> row 4.
# Try that validated row first for seam-only requests, then retain full-table
# fallback when it cannot produce a setup for the requested geometry.
DEFAULT_PREFERRED_TABLE_FRAME = 4
OLD_LATTICE_RADIUS = 4
CALIBRATED_GENERATION_TRUSTED = False
DECOMP_GENERATION_TRUSTED = True


@dataclass(frozen=True)
class DropFrame:
    frame: int
    local_dx: float
    local_dz: float
    speed: float
    local_angle_deg: float | None = None
    local_angle_s16: float | None = None

    @property
    def local_angle(self) -> int:
        return world_angle_s16(self.local_dx, self.local_dz)


def load_drop_table(path):
    """Load a measured drop-displacement CSV.

    Header rows before ``Bomb drop frame,...`` are ignored. Required columns are
    frame, X, Z. ``True Speed`` and angle columns are consumed when present.
    """
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = None
        for row in reader:
            if row and row[0].strip().lower().endswith("drop frame"):
                header = [c.strip() for c in row]
                break
        if header is None:
            raise ValueError("no '* drop frame' header found in %s" % path)
        idx = {name: i for i, name in enumerate(header)}
        frame_key = header[0]
        for row in reader:
            if not row or not row[0].strip():
                continue
            def val(name, default=None):
                i = idx.get(name)
                if i is None or i >= len(row) or row[i] == "":
                    return default
                return float(row[i])
            rows.append(DropFrame(
                frame=int(val(frame_key)),
                local_dx=val("X"),
                local_dz=val("Z"),
                speed=val("True Speed", math.hypot(val("X"), val("Z"))),
                local_angle_deg=val("Angle (deg)", None),
                local_angle_s16=val("Angle (halfword)", None),
            ))
    return rows


def infer_table_object(path):
    """Best-effort object label from the first ``* drop frame`` header cell."""
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if row and row[0].strip().lower().endswith("drop frame"):
                label = row[0].strip()[:-len(" drop frame")].strip().lower()
                aliases = {
                    "bomb": "bomb",
                    "small pot": "pot_small",
                    "pot small": "pot_small",
                    "pot_small": "pot_small",
                    "large pot": "pot_large",
                    "pot large": "pot_large",
                    "pot_large": "pot_large",
                }
                return aliases.get(label, label.replace(" ", "_"))
    return None


def compatible_drop_model(requested, table_object):
    """Whether a measured table can back ``requested`` object's drop model."""
    return DROP_MODEL_FAMILIES.get(requested, requested) == DROP_MODEL_FAMILIES.get(table_object, table_object)


def validate_calibrated_table(table, object_types=("bomb", "pot_small"), tolerance=1e-5):
    """Require every row to round-trip through center inversion and source Co math."""
    anims = dr.load_grab_anims()
    skeleton = dr.load_skeleton()
    report = {}
    for object_type in object_types:
        errors = []
        for row in table:
            pose = dr.calibrated_b_drop_pose(
                (0.0, 0.0, 0.0),
                0,
                row.frame,
                row.local_dx,
                row.local_dz,
                object_type=object_type,
                anims=anims,
                skeleton=skeleton,
            )
            step = dr.b_drop_collision_step(
                (0.0, 0.0, 0.0),
                pose.link_co_center,
                pose.link_co_height,
                pose.held_prop_pos,
                object_type,
                [],
                link_co_radius=pose.link_co_radius,
            )
            errors.append(math.hypot(
                step.link_push[0] - row.local_dx,
                step.link_push[2] - row.local_dz,
            ))
        max_error = max(errors, default=0.0)
        if max_error > tolerance:
            raise ValueError(
                "%s table fails calibrated Co round-trip: max error %.9g > %.9g"
                % (object_type, max_error, tolerance)
            )
        report[object_type] = {
            "rows": len(errors),
            "max_error": max_error,
            "mean_error": sum(errors) / len(errors) if errors else 0.0,
        }
    return report


def bam_to_deg(a):
    return (int(a) & 0xFFFF) * 360.0 / 65536.0


def rotate_local(dx, dz, facing):
    """Rotate a facing-0 vector with the game's quantized s16 trig table.

    ``cM_ssin``/``cM_scos`` have one value per 32 BAM values.  Using host
    ``sin``/``cos`` is observably wrong for seam work: the documented GanonM
    window 36256..36271 is one lookup-table bucket.
    """
    s = M.cM_ssin_s16(facing)
    c = M.cM_scos_s16(facing)
    return (
        fp.fadds(fp.fmuls(dx, c), fp.fmuls(dz, s)),
        fp.fadds(fp.fmuls(fp.f32(-dx), s), fp.fmuls(dz, c)),
    )


def f32_bits(value):
    """Return the stored binary32 bits for an exact setup coordinate."""
    return struct.unpack(">I", struct.pack(">f", _f(value)))[0]


def _old_lattice_offsets(radius=OLD_LATTICE_RADIUS):
    """Nearby X/Z f32 offsets, with the analytic point first."""
    offsets = [(dx, dz) for dx in range(-radius, radius + 1)
               for dz in range(-radius, radius + 1)]
    offsets.sort(key=lambda p: (max(abs(p[0]), abs(p[1])),
                                abs(p[0]) + abs(p[1]), p))
    return offsets


def _ordered_rels(interior, step=2.0):
    half = interior / 2.0
    lim = half + CONE_MARGIN
    rels = [0.0]
    g = max(step, CONE_STEP)
    while g <= lim:
        rels += [g, -g]
        g += max(step, CONE_STEP)
    rels.sort(key=lambda r: (round(min(abs(r), abs(half - abs(r))), 3), abs(r)))
    return rels


def _nearest_seam(region, box, target, tol=1.0):
    tx, ty, tz = target
    seams = enumerate_seams(region, box)
    if not seams:
        return None

    def distance_key(candidate):
        ylo, yhi = candidate.get("edge_yspan", (candidate["S"][1], candidate["S"][1]))
        y_distance = max(ylo - ty, 0.0, ty - yhi)
        xz_distance_sq = (
            (candidate["S"][0] - tx) ** 2
            + (candidate["S"][2] - tz) ** 2
        )
        return xz_distance_sq, y_distance

    seam = min(seams, key=distance_key)
    dist = math.hypot(seam["S"][0] - tx, seam["S"][2] - tz)
    if dist > tol:
        raise ValueError("nearest seam is %.3fu away: %s" % (dist, seam["S"]))
    return seam


def _candidate_dirs(wallA, wallB, interior):
    base = bisector_dir([wallA, wallA, wallB])
    for rel in _ordered_rels(interior):
        a = base + math.radians(rel)
        yield rel, math.sin(a), math.cos(a)


def prove_drop_frame(region, box, target_seam, drop_frame: DropFrame, *, verbose=False,
                     object_type="bomb", anims=None, skeleton=None):
    """Return one coupled calibrated-center candidate, never an exact-pose proof."""
    seam = _nearest_seam(region, box, target_seam)
    walls = _seam_walls(region, seam)
    if walls is None:
        return None
    wallA, wallB = walls
    ground = [t for t in region if t["n"][1] >= 0.5]
    polyset = set(seam["polys"])
    ys = [v[1] for t in region if t["poly"] in polyset for v in t["v"]]
    yspan = (min(ys), max(ys)) if ys else _wall_yspan(wallA, wallB)
    S = seam["S"]
    Sxz = (S[0], S[2])
    near_walls = gather_near_walls(region, S, target_seam[1])
    trilist = [wallA, wallA, wallB] + near_walls
    mag = drop_frame.speed or math.hypot(drop_frame.local_dx, drop_frame.local_dz)
    if mag <= 0.0:
        return None

    room_walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
    if anims is None:
        anims = dr.load_grab_anims()
    if skeleton is None:
        skeleton = dr.load_skeleton()

    # A clip trajectory must pass through the seam to sub-ULP precision. A
    # world-space direction/distance grid cannot hit that reliably. For each
    # useful direction, first obtain the actual coupled push for its console
    # trig bucket, then solve old = seam - t*push and search only the f32 phase
    # along that line.
    for rel, ux, uz in _candidate_dirs(wallA, wallB, seam["interior"]):
        travel_angle = world_angle_s16(ux, uz)
        facing = ((travel_angle - drop_frame.local_angle) & 0xFFFF) & ~0xF
        approx_dx, approx_dz = rotate_local(
            drop_frame.local_dx, drop_frame.local_dz, facing
        )
        ref_old = (
            _f(S[0] - 0.8 * approx_dx),
            _f(target_seam[1]),
            _f(S[2] - 0.8 * approx_dz),
        )
        ref_y = _floor_at(ground, ref_old[0], ref_old[2], yspan)
        if ref_y is None:
            continue
        ref_old = (ref_old[0], _f(ref_y), ref_old[2])
        ref_pose = dr.calibrated_b_drop_pose(
            ref_old, facing, drop_frame.frame,
            drop_frame.local_dx, drop_frame.local_dz,
            object_type=object_type, anims=anims, skeleton=skeleton,
        )
        ref_step = dr.b_drop_collision_step(
            ref_old, ref_pose.link_co_center, ref_pose.link_co_height,
            ref_pose.held_prop_pos, object_type, room_walls,
            link_co_radius=ref_pose.link_co_radius,
        )
        push_x, push_z = ref_step.link_push[0], ref_step.link_push[2]
        push_mag = math.hypot(push_x, push_z)
        if push_mag <= 0.0 or ref_step.prop_bg_info["wall_hit"]:
            continue
        t_start = max(0.55, min(0.95, (seam["floor"] - 1.0) / push_mag))
        # Aim the raw endpoint a small distance behind the seam, as in a bare
        # no-LineCheck seam traversal. Starting almost exactly at the seam
        # over-ranks deep endpoints that happen to survive this collision
        # approximation but do not resemble the established clip geometry.
        phase_center = max(t_start, min(0.999, 1.0 - 0.2 / push_mag))
        phase_steps = int(max(phase_center - t_start, 0.999 - phase_center) / 0.001) + 1
        t_values = []
        for i in range(phase_steps):
            offsets = (0.0,) if i == 0 else (i * 0.001, -i * 0.001)
            for offset in offsets:
                phase = phase_center + offset
                if t_start <= phase <= 0.999:
                    t_values.append(phase)
        for phase in t_values:
            ox = _f(S[0] - phase * push_x)
            oz = _f(S[2] - phase * push_z)
            ly = _floor_at(ground, ox, oz, yspan)
            if ly is None:
                continue
            if _is_step_riser(ground, Sxz, yspan, ly):
                continue
            mdx, mdz = rotate_local(drop_frame.local_dx, drop_frame.local_dz, facing)
            analytic_old = (ox, _f(ly), oz)
            if not _valid_initial(
                trilist, ground, analytic_old, wallA, wallB, yspan, True
            ):
                continue
            analytic_pose = dr.calibrated_b_drop_pose(
                analytic_old,
                facing,
                drop_frame.frame,
                drop_frame.local_dx,
                drop_frame.local_dz,
                object_type=object_type,
                anims=anims,
                skeleton=skeleton,
            )
            analytic_step = dr.b_drop_collision_step(
                analytic_old,
                analytic_pose.link_co_center,
                analytic_pose.link_co_height,
                analytic_pose.held_prop_pos,
                object_type,
                room_walls,
                link_co_radius=analytic_pose.link_co_radius,
            )
            analytic_coupled = _coupled_clip_flags(
                region, box, target_seam, analytic_old, analytic_step
            )
            if not analytic_coupled["coupled_crosses"]:
                continue
            lattice = []
            for ulp_x, ulp_z in _old_lattice_offsets():
                old = (
                    _next_f32(ox, ulp_x),
                    _f(ly),
                    _next_f32(oz, ulp_z),
                )
                if not _valid_initial(
                    trilist, ground, old, wallA, wallB, yspan, True
                ):
                    continue
                raw_new = (fadds(old[0], mdx), old[1], fadds(old[2], mdz))
                resolved = _resolved_prop_clip_flags(
                    region, box, target_seam, old, raw_new
                )
                pose = dr.calibrated_b_drop_pose(
                    old,
                    facing,
                    drop_frame.frame,
                    drop_frame.local_dx,
                    drop_frame.local_dz,
                    object_type=object_type,
                    anims=anims,
                    skeleton=skeleton,
                )
                step = dr.b_drop_collision_step(
                    old,
                    pose.link_co_center,
                    pose.link_co_height,
                    pose.held_prop_pos,
                    object_type,
                    room_walls,
                    link_co_radius=pose.link_co_radius,
                )
                coupled = _coupled_clip_flags(region, box, target_seam, old, step)
                if not coupled["coupled_crosses"]:
                    continue
                endpoint_model_error = math.hypot(
                    step.link_raw[0] - raw_new[0],
                    step.link_raw[2] - raw_new[2],
                )
                seam_miss = math.hypot(
                    step.link_after_bg[0] - S[0],
                    step.link_after_bg[2] - S[2],
                )
                lattice.append(dict(
                    old=old,
                    raw_new=raw_new,
                    resolved=resolved,
                    pose=pose,
                    step=step,
                    coupled=coupled,
                    ulp_offset=(ulp_x, ulp_z),
                    seam_miss=seam_miss,
                    endpoint_model_error=endpoint_model_error,
                ))
            if not lattice:
                continue
            lattice.sort(key=lambda c: (
                c["seam_miss"],
                max(abs(c["ulp_offset"][0]), abs(c["ulp_offset"][1])),
                abs(c["ulp_offset"][0]) + abs(c["ulp_offset"][1]),
                c["ulp_offset"],
            ))
            chosen = lattice[0]
            old = chosen["old"]
            raw_new = chosen["raw_new"]
            resolved = chosen["resolved"]
            pose = chosen["pose"]
            step = chosen["step"]
            coupled = chosen["coupled"]
            coupled["source"] = "prop_bg_then_co_then_link_acch_crrpos"
            endpoint_crosses = resolved["clips"]
            d = math.hypot(old[0] - S[0], old[2] - S[2])
            if verbose:
                print("table_frame=%d rel=%.1f d=%.3f old=(%.9f,%.9f) ulp=(%+d,%+d) "
                      "raw=(%.9f,%.9f) endpoint_crosses=%s seam_miss=%.9g"
                      % (drop_frame.frame, rel, d, old[0], old[2],
                         chosen["ulp_offset"][0], chosen["ulp_offset"][1],
                         raw_new[0], raw_new[2], endpoint_crosses,
                         chosen["seam_miss"]), flush=True)
            return dict(
                authoritative=False,
                endpoint_crosses=endpoint_crosses,
                model="calibrated_center_prediction",
                rejection_reason=(
                    "separate layered release-pose world transforms are not yet exact"
                ),
                frame=drop_frame.frame + 1,
                table_frame=drop_frame.frame,
                seam=seam,
                old=old,
                raw_new=step.link_raw,
                new=step.link_after_bg,
                endpoint_raw_new=raw_new,
                endpoint_resolved=resolved["resolved"],
                link_y=ly,
                facing=facing,
                travel_angle=travel_angle,
                rel_deg=rel,
                phase=phase,
                old_lattice_offset=chosen["ulp_offset"],
                old_lattice_candidates=len(lattice),
                old_bits=(f32_bits(old[0]), f32_bits(old[2])),
                endpoint_seam_miss=chosen["seam_miss"],
                endpoint_model_error=chosen["endpoint_model_error"],
                drop_local=(drop_frame.local_dx, drop_frame.local_dz),
                drop_world=(step.link_push[0], step.link_push[2]),
                drop_mag=math.hypot(step.link_push[0], step.link_push[2]),
                old_dist=d,
                info=step.link_bg_info,
                resolved=resolved,
                calibrated_pose=pose,
                collision_step=step,
                coupled=coupled,
            )
    return None


def prove_drop(region, box, target_seam, table, frame=None, limit=0, object_type=None,
               frame_offset=DEFAULT_ANIMATION_TO_TABLE_OFFSET):
    """Find calibrated-center candidates after the full coupled collision path.

    Candidate acceptance uses the source-ordered prop BG -> Co -> Link Acch
    result. The rotated origin endpoint is diagnostic only because f32 Co math
    is not translation-invariant.
    """
    table_frame = None if frame is None else frame + frame_offset
    frames = [r for r in table if table_frame is None or r.frame == table_frame]
    anims = dr.load_grab_anims()
    skeleton = dr.load_skeleton()
    if table_frame is None:
        seam = _nearest_seam(region, box, target_seam)
        walls_pair = _seam_walls(region, seam) if seam is not None else None
        room_walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
        ground = [t for t in region if t["n"][1] >= 0.5]

        def agreement(row):
            if walls_pair is None:
                return (float("inf"), row.frame)
            wall_a, wall_b = walls_pair
            rel, ux, uz = next(_candidate_dirs(wall_a, wall_b, seam["interior"]))
            travel = world_angle_s16(ux, uz)
            facing = ((travel - row.local_angle) & 0xFFFF) & ~0xF
            direct = rotate_local(row.local_dx, row.local_dz, facing)
            old = (_f(seam["S"][0] - 0.95 * direct[0]),
                   _f(target_seam[1]),
                   _f(seam["S"][2] - 0.95 * direct[1]))
            floor_y = _floor_at(ground, old[0], old[2], _wall_yspan(wall_a, wall_b))
            if floor_y is None:
                return (float("inf"), row.frame)
            old = (old[0], _f(floor_y), old[2])
            pose = dr.calibrated_b_drop_pose(
                old, facing, row.frame, row.local_dx, row.local_dz,
                object_type=object_type or "bomb", anims=anims, skeleton=skeleton,
            )
            step = dr.b_drop_collision_step(
                old, pose.link_co_center, pose.link_co_height,
                pose.held_prop_pos, object_type or "bomb", room_walls,
                link_co_radius=pose.link_co_radius,
            )
            error = math.hypot(
                step.link_push[0] - direct[0], step.link_push[2] - direct[1]
            )
            return (error, row.frame)

        frames.sort(key=agreement)
    hits = []
    for r in frames:
        hit = prove_drop_frame(
            region,
            box,
            target_seam,
            r,
            object_type=object_type or "bomb",
            anims=anims,
            skeleton=skeleton,
        )
        if hit is not None:
            if object_type is not None:
                hit["object"] = object_type
            bucket = hit["facing"] & ~0xF
            window = [((bucket - 1 + i) & 0xFFFF) for i in range(18)]
            checked = verify_setup(
                region, box, target_seam, [r], frame=hit["frame"],
                old=hit["old"], facings=window, calibrated=True,
                object_type=object_type or "bomb",
            )
            checked_by_facing = {row["facing"]: row for row in checked}

            def accepted_at(value):
                normalized = value & 0xFFFF
                if normalized not in checked_by_facing:
                    row = verify_setup(
                        region, box, target_seam, [r], frame=hit["frame"],
                        old=hit["old"], facings=[normalized], calibrated=True,
                        object_type=object_type or "bomb",
                    )[0]
                    checked_by_facing[normalized] = row
                return checked_by_facing[normalized]["calibrated"].get(
                    "calibrated_conditions_pass", False
                )

            left = hit["facing"]
            right = hit["facing"]
            while left > 0 and accepted_at(left - 1):
                left -= 1
            while right < 0xFFFF and accepted_at(right + 1):
                right += 1
            accepted = list(range(left, right + 1))
            hit["accepted_facings"] = accepted
            hit["facing_range"] = (left, right) if accepted_at(hit["facing"]) else None
            hits.append(hit)
            if limit and len(hits) >= limit:
                break
    hits.sort(key=lambda h: (h["frame"], h["old_dist"]))
    return hits


def _parse_facing_spec(spec):
    vals = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (int(x, 0) for x in part.split("-", 1))
            step = 1 if b >= a else -1
            vals.extend(range(a, b + step, step))
        else:
            vals.append(int(part, 0))
    return vals


def _resolved_prop_clip_flags(region, box, seam_target, old, raw_new):
    """Verify the next-frame Link move produced by a pending prop Co push.

    ``SetPosCorrect`` receives pointers to the two collision-shape centers.  It
    adjusts those temporary centers for the remainder of ``Ccsp()->Move()`` and
    stores the same correction in each actor status.  Link's actor position only
    receives that stored correction in the following ``posMove``.  The player
    then runs ``mAcch.CrrPos(old, raw_new)``; that resolved actor position is the
    seam-clip result.

    A corner clip may legitimately report ``line_hit=True``: LineCheck can snap
    Link onto one incident wall after the movement has crossed behind the other.
    The useful verdict is therefore that the settled old position is in front of
    both walls, the resolved position is behind both, and a zero-motion
    follow-up CrrPos leaves that resolved position stable.
    """
    if seam_target is None or box is None:
        raise ValueError("a target seam and ordered box are required for a clip proof")
    seam = _nearest_seam(region, box, seam_target)
    if seam is None:
        raise ValueError("no seam was enumerated in box=%r" % (box,))
    walls_pair = _seam_walls(region, seam)
    if walls_pair is None:
        raise ValueError("target seam does not have two incident wall planes")
    room_walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
    resolved, crr_info = crr_pos_walls(old, raw_new, room_walls)
    stable, stable_info = crr_pos_walls(resolved, resolved, room_walls)
    stable_delta = math.hypot(stable[0] - resolved[0], stable[2] - resolved[2])
    wallA, wallB = walls_pair
    old_front = wallA.pla.func(old) > 0.0 and wallB.pla.func(old) > 0.0
    raw_behind = wallA.pla.func(raw_new) < 0.0 and wallB.pla.func(raw_new) < 0.0
    resolved_plane_values = (wallA.pla.func(resolved), wallB.pla.func(resolved))
    resolved_behind = resolved_plane_values[0] < 0.0 and resolved_plane_values[1] < 0.0
    clips = (
        old_front
        and raw_behind
        and resolved_behind
        and not crr_info["wall_hit"]
        and not stable_info["wall_hit"]
        and stable_delta <= 1e-3
    )
    return dict(
        clips=clips,
        raw_new=raw_new,
        resolved=resolved,
        crr_info=crr_info,
        stable=stable,
        stable_info=stable_info,
        stable_delta=stable_delta,
        old_front=old_front,
        raw_behind=raw_behind,
        resolved_behind=resolved_behind,
        resolved_plane_values=resolved_plane_values,
        seam=seam,
    )


def _coupled_clip_flags(region, box, seam_target, old, step):
    """Classify a B-drop step that already ran both prop and Link BG passes."""
    if seam_target is None or box is None:
        raise ValueError("a target seam and ordered box are required")
    seam = _nearest_seam(region, box, seam_target)
    if seam is None:
        raise ValueError("no seam was enumerated in box=%r" % (box,))
    walls_pair = _seam_walls(region, seam)
    if walls_pair is None:
        raise ValueError("target seam does not have two incident wall planes")
    room_walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
    stable, stable_info = acch_crr_pos(step.link_after_bg, step.link_after_bg, room_walls)
    stable_delta = math.hypot(
        stable[0] - step.link_after_bg[0], stable[2] - step.link_after_bg[2]
    )
    wall_a, wall_b = walls_pair
    old_front = wall_a.pla.func(old) > 0.0 and wall_b.pla.func(old) > 0.0
    raw_behind = wall_a.pla.func(step.link_raw) < 0.0 and wall_b.pla.func(step.link_raw) < 0.0
    resolved_behind = (
        wall_a.pla.func(step.link_after_bg) < 0.0
        and wall_b.pla.func(step.link_after_bg) < 0.0
    )
    crosses = (
        old_front
        and raw_behind
        and resolved_behind
        and not step.link_bg_info["wall_hit"]
        and not stable_info["wall_hit"]
        and stable_delta <= 1e-3
    )
    return {
        "coupled_crosses": crosses,
        "old_front": old_front,
        "raw_behind": raw_behind,
        "resolved_behind": resolved_behind,
        "stable": stable,
        "stable_info": stable_info,
        "stable_delta": stable_delta,
        "resolved": step.link_after_bg,
        "link_bg_info": step.link_bg_info,
        "seam": seam,
    }


def verify_setup(region, box, seam_target, table, *, frame, old, facings,
                 frame_offset=DEFAULT_ANIMATION_TO_TABLE_OFFSET, calibrated=False,
                 object_type="bomb"):
    """Diagnose a known setup using only a rotated free-space endpoint."""
    table_frame = frame + frame_offset
    rows = [r for r in table if r.frame == table_frame]
    if not rows:
        raise ValueError("animation frame %d maps to missing table frame %d" % (frame, table_frame))
    drop_frame = rows[0]
    walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
    anims = dr.load_grab_anims() if calibrated else None
    skeleton = dr.load_skeleton() if calibrated else None
    out = []
    for facing in facings:
        mdx, mdz = rotate_local(drop_frame.local_dx, drop_frame.local_dz, facing)
        new = (fadds(old[0], mdx), _f(old[1]), fadds(old[2], mdz))
        corr, crr_info = crr_pos_walls(old, new, walls)
        acorr, acch_info = acch_crr_pos(old, new, walls)
        resolved = _resolved_prop_clip_flags(region, box, seam_target, old, new)
        calibrated_result = None
        if calibrated:
            pose = dr.calibrated_b_drop_pose(
                old,
                facing,
                table_frame,
                drop_frame.local_dx,
                drop_frame.local_dz,
                object_type=object_type,
                anims=anims,
                skeleton=skeleton,
            )
            step = dr.b_drop_collision_step(
                old,
                pose.link_co_center,
                pose.link_co_height,
                pose.held_prop_pos,
                object_type,
                walls,
                link_co_radius=pose.link_co_radius,
            )
            calibrated_resolved = _resolved_prop_clip_flags(
                region, box, seam_target, old, step.link_raw
            )
            calibrated_coupled = _coupled_clip_flags(
                region, box, seam_target, old, step
            )
            calibrated_result = {
                "authoritative": False,
                "status": "calibrated_center_prediction",
                "pose": pose,
                "step": step,
                "coupled_crosses": calibrated_coupled["coupled_crosses"],
                "resolved": calibrated_resolved,
                "coupled": calibrated_coupled,
            }
            endpoint_model_error = math.hypot(
                step.link_raw[0] - new[0],
                step.link_raw[2] - new[2],
            )
            calibrated_result["endpoint_model_error"] = endpoint_model_error
            calibrated_conditions_pass = (
                calibrated_coupled["coupled_crosses"]
                and not step.prop_bg_info["wall_hit"]
            )
            calibrated_result["calibrated_conditions_pass"] = calibrated_conditions_pass
            calibrated_result["generator_grade"] = (
                CALIBRATED_GENERATION_TRUSTED and calibrated_conditions_pass
            )
        out.append(dict(
            authoritative=False,
            endpoint_crosses=resolved["clips"],
            model="rotated_free_space_endpoint",
            rejection_reason=(
                "released prop background correction and world-space Co recomputation "
                "were not simulated"
            ),
            frame=frame,
            table_frame=table_frame,
            facing=facing & 0xFFFF,
            old=old,
            new=new,
            drop_local=(drop_frame.local_dx, drop_frame.local_dz),
            drop_world=(mdx, mdz),
            crr_corr=corr,
            acch_corr=acorr,
            acch_info=acch_info,
            acch_clips=(not acch_info.get("line_hit", False)) and (not acch_info.get("wall_hit", False)),
            calibrated=calibrated_result,
            **resolved,
        ))
    return out


def _load_region(opts):
    if opts.get("dae"):
        region, box, stage = load_dae_region(opts["dae"])
        return region, opts["box"] or box, stage
    if opts.get("cache"):
        region, stage = load_region_tris(opts["cache"])
        return region, opts["box"], stage
    if opts.get("iso"):
        region, box, stage = load_room_region_from_iso(opts["iso"], opts["stage"], opts["room"])
        return region, box, stage
    region, box, stage = load_room_region(opts["stage"], opts["room"])
    return region, box, stage


def _parse(argv):
    opts = dict(stage="GanonM", room=0, box=None, cache=None, iso=None, object="bomb",
                dae=None, csv=None, seam=None, frame=None, table_frame=None, limit=1,
                old=None, facing=None, experimental=False)
    for a in argv:
        if a.startswith("stage="):
            opts["stage"] = a[6:]
        elif a.startswith("room="):
            opts["room"] = int(a[5:])
        elif a.startswith("box="):
            opts["box"] = tuple(float(x) for x in a[4:].split(","))
        elif a.startswith("cache="):
            opts["cache"] = a[6:]
        elif a.startswith("iso="):
            opts["iso"] = a[4:]
        elif a.startswith("dae="):
            opts["dae"] = a[4:]
        elif a.startswith("csv="):
            opts["csv"] = a[4:]
        elif a.startswith("object="):
            opts["object"] = a[7:]
        elif a.startswith("seam="):
            opts["seam"] = tuple(float(x) for x in a[5:].split(","))
        elif a.startswith("frame="):
            opts["frame"] = int(a[6:])
        elif a.startswith("table_frame="):
            opts["table_frame"] = int(a[12:])
        elif a.startswith("limit="):
            opts["limit"] = int(a[6:])
        elif a.startswith("old="):
            vals = tuple(float(x) for x in a[4:].split(","))
            if len(vals) == 3:
                opts["old"] = vals
            else:
                raise ValueError("old= needs x,y,z; seam Y is not Link's floor Y")
        elif a.startswith("facing="):
            opts["facing"] = _parse_facing_spec(a[7:])
        elif a in ("experimental=1", "experimental=true", "--experimental"):
            opts["experimental"] = True
    return opts


def main(argv):
    opts = _parse(argv)
    if opts["seam"] is None:
        print("usage: python -m harness.collision.drop_push_clip object=bomb "
              "seam=x,y,z [frame=animation_position] "
              "[landing=clip|oob tolerance=0.005] "
              "[old=x,y,z facing=A-B] [cache=region.json box=...] [dae=file.dae] "
              "[iso=game.iso stage=GanonM room=0] [limit=N] "
              "[csv=drop.csv  # legacy measured diagnostic only]")
        return 2
    if opts["csv"] is None:
        # Keep the established entry point while routing generation through
        # the first-principles pose. The fast scanner imports helpers from this
        # module, so defer the import until this module is fully initialized.
        from harness.collision.find_drop_push_candidate import main as decomp_main
        return decomp_main(argv)
    table_object = infer_table_object(opts["csv"])
    if table_object is not None and not compatible_drop_model(opts["object"], table_object):
        print("refusing object=%s with a %s displacement table (%s)" % (
            opts["object"], table_object, opts["csv"]))
        return 2
    table = load_drop_table(opts["csv"])
    try:
        calibration = validate_calibrated_table(table, object_types=(opts["object"],))
    except FileNotFoundError as exc:
        print("missing generated animation data: %s" % exc, file=sys.stderr)
        print("generate link_skeleton.json and link_anim_grab.json from the game ISO first",
              file=sys.stderr)
        return 2
    calibration_row = calibration[opts["object"]]
    print("calibration object=%s rows=%d max_error=%.9g mean_error=%.9g" % (
        opts["object"], calibration_row["rows"], calibration_row["max_error"],
        calibration_row["mean_error"]), flush=True)
    region, box, stage = _load_region(opts)
    if opts["table_frame"] is not None:
        mapped_animation_frame = opts["table_frame"] - DEFAULT_ANIMATION_TO_TABLE_OFFSET
        if opts["frame"] is not None and opts["frame"] != mapped_animation_frame:
            print("frame=%d conflicts with table_frame=%d (expected frame=%d)" % (
                opts["frame"], opts["table_frame"], mapped_animation_frame))
            return 2
        opts["frame"] = mapped_animation_frame
    if opts["old"] is not None or opts["facing"] is not None:
        if opts["old"] is None or opts["facing"] is None or opts["frame"] is None:
            print("setup verification needs old=, facing=, and frame=", flush=True)
            return 2
        rows = verify_setup(region, box, opts["seam"], table, frame=opts["frame"], old=opts["old"],
                            facings=opts["facing"], calibrated=True,
                            object_type=opts["object"])
        print("DIRECT ENDPOINT (diagnostic only); calibrated coupled result follows")
        print("stage=%s room=%d object=%s tris=%d setup_rows=%d animation_frame=%d "
              "table_frame=%d old=(%.9f,%.9f,%.9f)"
              % (stage, opts["room"], opts["object"], len(region), len(rows), opts["frame"],
                 rows[0]["table_frame"],
                 opts["old"][0], opts["old"][1], opts["old"][2]), flush=True)
        for r in rows:
            print("facing=%d facing_deg=%.6f raw_new=(%.9f,%.9f,%.9f) drop=(%.9f,%.9f) "
                  "endpoint_crosses=%s authoritative=%s old_front=%s raw_behind=%s resolved_behind=%s "
                  "stable_delta=%.9f crr_line=%s crr_wall=%s resolved=(%.9f,%.9f,%.9f) "
                  "acch_clip=%s acch_line=%s acch_wall=%s acch_corr=(%.9f,%.9f,%.9f)"
                  % (r["facing"], bam_to_deg(r["facing"]),
                     r["new"][0], r["new"][1], r["new"][2],
                     r["drop_world"][0], r["drop_world"][1],
                     r["endpoint_crosses"], r["authoritative"], r["old_front"],
                     r["raw_behind"], r["resolved_behind"],
                     r["stable_delta"], r["crr_info"]["line_hit"], r["crr_info"]["wall_hit"],
                     r["resolved"][0], r["resolved"][1], r["resolved"][2],
                     r["acch_clips"], r["acch_info"].get("line_hit", False),
                     r["acch_info"].get("wall_hit", False),
                     r["acch_corr"][0], r["acch_corr"][1], r["acch_corr"][2]),
                  flush=True)
            calibrated = r["calibrated"]
            step = calibrated["step"]
            print("  calibrated_center_model coupled_crosses=%s calibrated_conditions=%s "
                  "generator_grade=%s "
                  "endpoint_error=%.9g prop_bg_wall=%s link_line=%s link_wall=%s "
                  "push=(%.9f,%.9f) raw=(%.9f,%.9f) resolved=(%.9f,%.9f)"
                  % (calibrated["coupled_crosses"],
                     calibrated.get("calibrated_conditions_pass", False),
                     calibrated["generator_grade"],
                     calibrated["endpoint_model_error"], step.prop_bg_info["wall_hit"],
                     step.link_bg_info["line_hit"], step.link_bg_info["wall_hit"],
                     step.link_push[0], step.link_push[2],
                     step.link_raw[0], step.link_raw[2],
                     step.link_after_bg[0], step.link_after_bg[2]),
                  flush=True)
        return 0
    if not opts["experimental"]:
        print("refusing to generate a new setup from the calibrated-center model by default")
        print("reason: user-tested generated candidates failed in-game; use old=... facing=... "
              "for diagnostics, or pass experimental=1 for non-proof candidates")
        return 2
    hits = prove_drop(region, box, opts["seam"], table, frame=opts["frame"], limit=opts["limit"],
                      object_type=opts["object"])
    print("CALIBRATED CENTER MODEL: coupled candidates, not exact-pose proofs")
    print("stage=%s room=%d object=%s seam=(%.6f,%.6f,%.6f) rows=%d candidates=%d%s" % (
        stage, opts["room"], opts["object"], opts["seam"][0], opts["seam"][1], opts["seam"][2],
        len(table), len(hits), "" if opts["frame"] is None else " animation_frame=%d" % opts["frame"]),
        flush=True)
    for h in hits:
        facing_text = (
            "%d-%d" % h["facing_range"]
            if h.get("facing_range") is not None else "none"
        )
        print("animation_frame=%02d table_frame=%02d facing=%d facing_range=%s facing_deg=%.3f "
              "travel=%d travel_deg=%.3f rel=%+.1f "
              "old=(%.9f,%.9f,%.9f) old_bits=(0x%08X,0x%08X) old_ulp=(%+d,%+d) "
              "raw_new=(%.6f,%.6f,%.6f) resolved=(%.6f,%.6f,%.6f) "
              "push=(%.6f,%.6f) mag=%.6f endpoint_error=%.9g "
              "coupled_crosses=%s authoritative=%s "
              "old_front=%s resolved_behind=%s "
              "stable_delta=%.6f "
              "crr_line=%s crr_wall=%s"
              % (h["frame"], h["table_frame"], h["facing"], facing_text,
                 bam_to_deg(h["facing"]),
                 h["travel_angle"], bam_to_deg(h["travel_angle"]), h["rel_deg"],
                 h["old"][0], h["old"][1], h["old"][2],
                 h["old_bits"][0], h["old_bits"][1],
                 h["old_lattice_offset"][0], h["old_lattice_offset"][1],
                 h["raw_new"][0], h["raw_new"][1], h["raw_new"][2],
                 h["new"][0], h["new"][1], h["new"][2],
                 h["drop_world"][0], h["drop_world"][1], h["drop_mag"],
                 h["endpoint_model_error"],
                 h["coupled"]["coupled_crosses"], h["authoritative"],
                 h["coupled"]["old_front"], h["coupled"]["resolved_behind"],
                 h["coupled"]["stable_delta"],
                 h["info"]["line_hit"], h["info"]["wall_hit"]),
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
