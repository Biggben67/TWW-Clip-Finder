"""Ground-truth labeling oracle for the analytic seam-clip window model.

For every differing-normal vertical seam in a room, measure (via a thorough f32-lattice sweep that
enforces the SAME validity gate as the scanner, ``seam_clip_check._valid_initial``) the set of
travel directions + settled-old distances that actually clip. Emit one JSONL record per seam:
geometry FEATURES (interior, wall normals, each wall's face tangent + XZ length from S, bisector,
floor, coord scale) and the measured WINDOW (clip rel list, per-rel dist-offset range, ULP radius).

This is the dataset the analytic direction/distance predictor is fitted/validated against — the
window is measured, not guessed (an earlier hand-derived 2D condition was wrong because TWW's
inclusion test runs in a Y-involving projection with a +-20 area tolerance). Streaming append so a
kill keeps partial results.

    python -m harness.collision.window_dataset stage=Hyrule room=0 out=_generated/window_ds.jsonl
"""
import json
import math
import os
import struct
import sys

from tww_sim.core.fp import f32 as _f
from harness.collision.dzb_iso import load_room_region
from harness.collision.seam_scan import enumerate_seams, _gather, floor_ys_at
from harness.collision.seam_clip_check import _seam_walls, _valid_initial, _floor_at
from harness.collision.gap_search import bisector_dir, first_f32_clip, settle, WALL_H

REL_STEP = 2.0
DIST_OFFSETS = (0.0, 4.0, 9.0, 14.0, 20.0)
TFS = (0.4, 0.8)
BOX_ULPS = 50
MAX_CALLS = 2500
SEAM_BUDGET = 400_000        # per-seam eval cap so a genuinely unclippable seam bails fast


def _ulp(center, val):
    return abs(struct.unpack("<I", struct.pack("<f", _f(val)))[0]
               - struct.unpack("<I", struct.pack("<f", _f(center)))[0])


def _tangent_and_len(T, S):
    """Wall face tangent (unit XZ toward the far extent from S) + XZ length of the face from S."""
    verts = [(T.v0[0], T.v0[2]), (T.v1[0], T.v1[2]), (T.v2[0], T.v2[2])]
    far = max(verts, key=lambda v: (v[0] - S[0]) ** 2 + (v[1] - S[1]) ** 2)
    tx, tz = far[0] - S[0], far[1] - S[1]
    L = math.hypot(tx, tz)
    return (tx / L, tz / L) if L > 1e-6 else (0.0, 0.0), L


def measure_seam(region, ground, seam):
    S = (seam["S"][0], seam["S"][2])
    walls = _seam_walls(region, seam)
    if walls is None:
        return None
    wA, wB = walls
    ps = set(seam["polys"])
    ys = [v[1] for t in region if t["poly"] in ps for v in t["v"]]
    if not ys:
        return None
    yspan = (min(ys), max(ys))
    base = bisector_dir([wA, wA, wB])
    floor = seam["floor"]
    if not math.isfinite(floor):
        return None
    trilist = [wA, wA, wB] + list(_gather(region, seam["S"], seam["S"][1]))
    half = seam["interior"] / 2.0
    uA, lenA = _tangent_and_len(wA, S)
    uB, lenB = _tangent_and_len(wB, S)

    def rel_of(u):                              # signed bisector-relative angle of a unit XZ dir
        a = math.degrees(math.atan2(u[0], u[1]) - base)
        return (a + 180.0) % 360.0 - 180.0

    window = {}          # rel -> [min_off, max_off, min_ulp]
    budget = SEAM_BUDGET
    lim = half + 6.0
    n = int(2 * lim / REL_STEP) + 1
    for i in range(n):
        rel = -lim + i * REL_STEP
        ang = base + math.radians(rel)
        dx, dz = math.sin(ang), math.cos(ang)
        for off in DIST_OFFSETS:
            if budget <= 0:
                break
            ox, oz = S[0] - (floor + off) * dx, S[1] - (floor + off) * dz
            oy = _floor_at(ground, ox, oz, yspan)
            if oy is None:
                continue
            old = settle(trilist, (ox, oz), oy)
            if not _valid_initial(trilist, ground, old, wA, wB, yspan, True):
                continue
            for tf in TFS:
                nc = (S[0] + tf * dx, S[1] + tf * dz)
                hit, used = first_f32_clip(trilist, old, nc, oy, box_ulps=BOX_ULPS,
                                           max_calls=min(budget, MAX_CALLS))
                budget -= used
                if hit is not None:
                    ru = max(_ulp(nc[0], hit["new"][0]), _ulp(nc[1], hit["new"][1]))
                    e = window.get(round(rel, 2))
                    if e is None:
                        window[round(rel, 2)] = [off, off, ru]
                    else:
                        e[0] = min(e[0], off); e[1] = max(e[1], off); e[2] = min(e[2], ru)
                    break
        if budget <= 0:
            break
    return dict(
        S=[round(S[0], 3), round(seam["S"][1], 3), round(S[1], 3)],
        interior=round(seam["interior"], 3), base_deg=round(math.degrees(base), 3),
        floor=round(floor, 3), coord_scale=round(max(abs(S[0]), abs(S[1])), 1),
        nA=[round(wA.pla.nx, 4), round(wA.pla.nz, 4)],
        nB=[round(wB.pla.nx, 4), round(wB.pla.nz, 4)],
        uA_rel=round(rel_of(uA), 2), lenA=round(lenA, 2),
        uB_rel=round(rel_of(uB), 2), lenB=round(lenB, 2),
        half_cone=round(half, 3),
        window={str(k): v for k, v in sorted(window.items())},
    )


def main(argv):
    stage, room = "Hyrule", 0
    out = os.path.join(os.path.dirname(__file__), "..", "..", "_generated", "window_ds.jsonl")
    for a in argv:
        if a.startswith("stage="):
            stage = a[6:]
        elif a.startswith("room="):
            room = int(a[5:])
        elif a.startswith("out="):
            out = a[4:]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    region, box, _ = load_room_region(stage, room)
    ground = [t for t in region if t["n"][1] >= 0.5]
    seams = enumerate_seams(region, box)
    print("stage=%s room=%d: %d seams -> %s" % (stage, room, len(seams), out), flush=True)
    n_win = 0
    with open(out, "a", encoding="utf-8") as f:
        for i, seam in enumerate(seams):
            rec = measure_seam(region, ground, seam)
            if rec is None:
                continue
            rec["stage"] = stage
            rec["room"] = room
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if rec["window"]:
                n_win += 1
            if (i + 1) % 20 == 0:
                print("  ...%d/%d seams, %d with a window" % (i + 1, len(seams), n_win), flush=True)
    print("done: %d seams with a measured window" % n_win, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
