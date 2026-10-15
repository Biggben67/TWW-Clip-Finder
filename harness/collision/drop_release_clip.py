"""Source-ordered bomb/pot B-drop seam simulator.

This joins the two required proof layers:

1. Generate the last held prop position and release-frame Link Co body.
2. Resolve the released prop against room background.
3. Compute the Co overlap and rank-table correction.
4. Consume Link's pending move and run Link's background ``mAcch.CrrPos``.

The coupled collision path is authoritative when fed an exact pose. The current
single-BCK pose generator is not: B resets and blends Link's upper animation,
so it remains diagnostic until it reproduces all measured free-space rows.
The CLI therefore emits a proof only when explicit ``hand_mid`` and ``link_co``
inputs are supplied with ``validated_pose``. ``drop_push_clip`` is calibration
only and never proves a setup.

The preferred path is fully offline with generated animation data:

    python -m harness.anim.parse_bmd
    python -m harness.anim.parse_bck which=link_anim_grab
    python -m harness.collision.drop_release_clip object=pot_small seam=586.023132,-50,-1413.401733 cache=_generated_ganonm_r0_iso_region.json box=...

For a one-off live state, pass the absolute hand midpoint and Link Co body read
from Dolphin; then the harness does not need the generated grab animation bank:

    python -m harness.collision.drop_release_clip object=pot_small old=x,y,z facing=30701 frame=1.0 hand_mid=x,y,z link_co=x,y,z,30,100 seam=...
"""
from __future__ import annotations

import math
import sys

from tww_sim.core import drop_release as dr
from tww_sim.core.collision import bg_blocks_crrpos
from harness.collision.dzb_iso import load_room_region, load_room_region_from_iso
from harness.collision.drop_push_clip import (
    _candidate_dirs, _coupled_clip_flags, _floor_at, _is_step_riser,
    _nearest_seam, _seam_walls,
)
from harness.collision.gap_search import settle
from harness.collision.seam_clip_check import _valid_initial, DIST_OFFSETS
from harness.collision.seam_scan import load_region_tris, _gather as gather_near_walls


def _parse_csv_floats(s):
    return tuple(float(x) for x in s.split(","))


def _parse_frames(s):
    if "-" in s:
        a, b = (float(x) for x in s.split("-", 1))
        out = []
        cur = a
        step = 1.0
        while cur <= b + 1e-7:
            out.append(round(cur, 6))
            cur += step
        return out
    return [float(x) for x in s.split(",") if x != ""]


def _parse_facings(s):
    if s == "auto":
        return None
    if s == "all":
        return "all"
    if "-" in s:
        a, b = (int(x, 0) for x in s.split("-", 1))
        return [x & 0xFFFF for x in range(a, b + 1)]
    return [int(x, 0) & 0xFFFF for x in s.split(",") if x != ""]


def _parse(argv):
    opts = {
        "stage": "GanonM",
        "room": 0,
        "cache": None,
        "iso": None,
        "box": None,
        "object": "pot_small",
        "seam": None,
        "old": None,
        "frame": [dr.NORMAL_B_DROP_HELD_FRAME],
        "facing": None,
        "facing_step": 256,
        "hand_mid": None,
        "link_co": None,
        "motion": (0.0, 0.0),
        "end_dist": 80.0,
        "limit": 20,
        "carrying_radius": False,
        "validated_pose": False,
        "verbose": False,
    }
    for a in argv:
        if a.startswith("stage="):
            opts["stage"] = a[6:]
        elif a.startswith("room="):
            opts["room"] = int(a[5:])
        elif a.startswith("cache="):
            opts["cache"] = a[6:]
        elif a.startswith("iso="):
            opts["iso"] = a[4:]
        elif a.startswith("box="):
            opts["box"] = _parse_csv_floats(a[4:])
        elif a.startswith("object="):
            opts["object"] = a[7:]
        elif a.startswith("seam="):
            opts["seam"] = _parse_csv_floats(a[5:])
        elif a.startswith("old="):
            opts["old"] = _parse_csv_floats(a[4:])
        elif a.startswith("frame="):
            opts["frame"] = _parse_frames(a[6:])
        elif a.startswith("facing="):
            opts["facing"] = _parse_facings(a[7:])
        elif a.startswith("facing_step="):
            opts["facing_step"] = int(a[12:], 0)
        elif a.startswith("hand_mid="):
            opts["hand_mid"] = _parse_csv_floats(a[9:])
        elif a.startswith("link_co="):
            opts["link_co"] = _parse_csv_floats(a[8:])
        elif a.startswith("motion="):
            opts["motion"] = _parse_csv_floats(a[7:])
        elif a.startswith("end_dist="):
            opts["end_dist"] = float(a[9:])
        elif a.startswith("limit="):
            opts["limit"] = int(a[6:])
        elif a == "carrying_radius":
            opts["carrying_radius"] = True
        elif a == "validated_pose":
            opts["validated_pose"] = True
        elif a == "verbose":
            opts["verbose"] = True
        elif a in ("-h", "--help", "help"):
            opts["help"] = True
    return opts


def _load_region(opts):
    if opts["cache"]:
        if opts["box"] is None:
            raise ValueError("cache= requires box=xmin,xmax,ymin,ymax,zmin,zmax")
        region, stage = load_region_tris(opts["cache"])
        return region, opts["box"], stage
    if opts["iso"]:
        return load_room_region_from_iso(opts["iso"], opts["stage"], opts["room"])
    return load_room_region(opts["stage"], opts["room"])


def _link_body_for_pose(pose, link_co, anims, skeleton):
    if link_co is not None:
        if len(link_co) == 5:
            x, y, z, r, h = link_co
        elif len(link_co) == 3:
            x, y, z = link_co
            r, h = 30.0, 100.0
        else:
            raise ValueError("link_co must be x,y,z or x,y,z,r,h")
        return {"center": (x, y, z), "radius": r, "height": h}
    return dr.link_body_co(pose, anims=anims, skeleton=skeleton)


def _candidate_olds(region, box, target_seam, explicit_old=None):
    if explicit_old is not None:
        yield {
            "old": explicit_old,
            "travel_angle": None,
            "rel_deg": None,
            "old_dist": None,
            "near_walls": [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])],
        }
        return

    seam = _nearest_seam(region, box, target_seam)
    if seam is None:
        raise ValueError("no seam was enumerated in box=%r" % (box,))
    walls = _seam_walls(region, seam)
    if walls is None:
        return
    wallA, wallB = walls
    ground = [t for t in region if t["n"][1] >= 0.5]
    polyset = set(seam["polys"])
    ys = [v[1] for t in region if t["poly"] in polyset for v in t["v"]]
    yspan = (min(ys), max(ys))
    S = seam["S"]
    Sxz = (S[0], S[2])
    near_walls = gather_near_walls(region, S, target_seam[1])
    trilist = [wallA, wallA, wallB] + near_walls
    for rel, ux, uz in _candidate_dirs(wallA, wallB, seam["interior"]):
        travel_angle = _world_angle_s16(ux, uz)
        for d in DIST_OFFSETS + (24.0, 30.0, 38.0, 45.0, 55.0):
            ox, oz = S[0] - d * ux, S[2] - d * uz
            ly = _floor_at(ground, ox, oz, yspan)
            if ly is None or _is_step_riser(ground, Sxz, yspan, ly):
                continue
            old = settle(trilist, (ox, oz), ly)
            if not _valid_initial(trilist, ground, old, wallA, wallB, yspan, True):
                continue
            yield {
                "old": old,
                "travel_angle": travel_angle,
                "rel_deg": rel,
                "old_dist": d,
                "near_walls": near_walls,
            }


def _world_angle_s16(dx, dz):
    return int(round(math.atan2(dx, dz) * 65536.0 / (2.0 * math.pi))) & 0xFFFF


def _facings_for(candidate, explicit, step):
    if explicit == "all":
        for a in range(0, 65536, step):
            yield a
        return
    if explicit is not None:
        yield from explicit
        return
    if candidate["travel_angle"] is not None:
        yield candidate["travel_angle"]
        return
    for a in range(0, 65536, step):
        yield a


def prove_pose(region, box, target_seam, object_type, old, frame, facing, *,
               hand_mid=None, link_co=None, motion=(0.0, 0.0), anims=None, skeleton=None,
               near_walls=None, end_dist=5.0, carrying_radius=False,
               pose_validated=False):
    pose = dr.CarryPose(tuple(old), facing, float(frame), hand_mid=hand_mid)
    held_prop = dr.carried_actor_pos(pose, anims=anims, skeleton=skeleton)
    if link_co is not None:
        body = _link_body_for_pose(pose, link_co, anims, skeleton)
    else:
        body = dr.link_body_co(pose, anims=anims, skeleton=skeleton, carrying=carrying_radius)
    room_walls = [t["T"] for t in region if bg_blocks_crrpos(t["n"][1])]
    step = dr.b_drop_collision_step(
        old,
        body["center"],
        body["height"],
        held_prop,
        object_type,
        room_walls,
        link_co_radius=body["radius"],
        link_motion=(motion[0], 0.0, motion[1]),
    )
    move_mag = math.hypot(step.link_raw[0] - old[0], step.link_raw[2] - old[2])
    if move_mag < 1e-5:
        return None
    resolved = _coupled_clip_flags(region, box, target_seam, old, step)
    if not resolved["coupled_crosses"]:
        return None
    exact_explicit_pose = hand_mid is not None and link_co is not None and pose_validated
    return {
        "object": object_type,
        "frame": frame,
        "facing": facing,
        "old": old,
        "raw_new": step.link_raw,
        "new": step.link_after_bg,
        "push": (step.link_push[0], step.link_push[2]),
        "push_mag": math.hypot(step.link_push[0], step.link_push[2]),
        "held_prop": held_prop,
        "prop_after_bg": step.prop_after_bg,
        "prop_bg_info": step.prop_bg_info,
        "co_center": step.prop_co_center,
        "link_co": body,
        "carrying_radius": carrying_radius,
        "authoritative": exact_explicit_pose,
        "proved_clip": bool(exact_explicit_pose and resolved["coupled_crosses"]),
        "pose_source": "validated_explicit" if exact_explicit_pose else "uncalibrated_single_bck",
        "info": step.link_bg_info,
        "resolved": resolved,
    }


def scan(region, box, seam, object_type="pot_small", frames=(2,), facings=None,
         facing_step=256, old=None, hand_mid=None, link_co=None, motion=(0.0, 0.0),
         end_dist=5.0, limit=20, carrying_radius=False, verbose=False,
         pose_validated=False):
    anims = skeleton = None
    if hand_mid is None or link_co is None:
        anims = dr.load_grab_anims()
        skeleton = dr.load_skeleton()

    hits = []
    for cand in _candidate_olds(region, box, seam, explicit_old=old):
        for facing in _facings_for(cand, facings, facing_step):
            for frame in frames:
                hit = prove_pose(
                    region, box, seam, object_type, cand["old"], frame, facing,
                    hand_mid=hand_mid, link_co=link_co, motion=motion,
                    anims=anims, skeleton=skeleton, near_walls=cand["near_walls"],
                    end_dist=end_dist, carrying_radius=carrying_radius,
                    pose_validated=pose_validated,
                )
                if verbose:
                    print("old=(%.3f,%.3f) frame=%s facing=%d hit=%s" % (
                        cand["old"][0], cand["old"][2], frame, facing, hit is not None),
                        flush=True)
                if hit is None:
                    continue
                hit.update({
                    "rel_deg": cand["rel_deg"],
                    "old_dist": cand["old_dist"],
                    "travel_angle": cand["travel_angle"],
                })
                hits.append(hit)
                if limit and len(hits) >= limit:
                    return hits
    return hits


def _fmt(hit):
    old = hit["old"]
    new = hit["new"]
    co = hit["co_center"]
    return (
        "%-9s frame=%s facing=%d old=(%.6f,%.6f,%.6f) new=(%.6f,%.6f,%.6f) "
        "push=(%.6f,%.6f) mag=%.6f co=(%.6f,%.6f,%.6f) "
        "coupled_crosses=%s proved_clip=%s authoritative=%s "
        "prop_bg_wall=%s link_line=%s link_wall=%s"
        % (
            hit["object"], hit["frame"], hit["facing"],
            old[0], old[1], old[2], new[0], new[1], new[2],
            hit["push"][0], hit["push"][1], hit["push_mag"],
            co[0], co[1], co[2],
            hit["resolved"]["coupled_crosses"], hit["proved_clip"], hit["authoritative"],
            hit["prop_bg_info"]["wall_hit"], hit["info"]["line_hit"],
            hit["info"]["wall_hit"],
        )
    )


def main(argv):
    opts = _parse(argv)
    if opts.get("help"):
        print(__doc__.strip())
        return 0
    if opts["object"] not in dr.DROP_OBJECTS:
        print("unknown object=%s; known: %s" % (
            opts["object"], ", ".join(sorted(dr.DROP_OBJECTS))), file=sys.stderr)
        return 2
    if opts["seam"] is None:
        print("missing seam=x,y,z", file=sys.stderr)
        return 2
    if opts["validated_pose"] and (opts["hand_mid"] is None or opts["link_co"] is None):
        print("validated_pose requires both hand_mid=x,y,z and link_co=x,y,z,r,h",
              file=sys.stderr)
        return 2
    try:
        region, box, stage = _load_region(opts)
        hits = scan(
            region, box, opts["seam"], object_type=opts["object"], frames=opts["frame"],
            facings=opts["facing"], facing_step=opts["facing_step"], old=opts["old"],
            hand_mid=opts["hand_mid"], link_co=opts["link_co"], motion=opts["motion"],
            end_dist=opts["end_dist"], limit=opts["limit"],
            carrying_radius=opts["carrying_radius"], verbose=opts["verbose"],
            pose_validated=opts["validated_pose"],
        )
    except FileNotFoundError as exc:
        print("missing generated animation data: %s" % exc, file=sys.stderr)
        print("Either generate it with:", file=sys.stderr)
        print("  python -m harness.anim.parse_bmd", file=sys.stderr)
        print("  python -m harness.anim.parse_bck which=link_anim_grab", file=sys.stderr)
        print("or pass both hand_mid=x,y,z and link_co=x,y,z,r,h from a live probe.", file=sys.stderr)
        return 2
    proofs = sum(1 for hit in hits if hit["proved_clip"])
    print("stage=%s room=%d object=%s seam=(%.6f,%.6f,%.6f) "
          "coupled_candidates=%d proofs=%d" % (
        stage, opts["room"], opts["object"], opts["seam"][0], opts["seam"][1], opts["seam"][2],
        len(hits), proofs), flush=True)
    if hits and not proofs:
        print("NO PROOF: pose source is not calibrated across the B-release animation transition",
              flush=True)
    for h in hits:
        print(_fmt(h), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
