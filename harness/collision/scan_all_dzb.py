"""Scan EVERY room/collision DZB in the extracted game for clippable seams and write one CSV per DZB
into ``_generated/seam_clips/`` (override with ``out=``), mirroring the disc's ``Stage/<stage>/``
folder layout. Streams as it goes (writes each DZB's CSV the moment it finishes and prints a progress
line) so the viewer can live-update, and is resumable (skips DZBs whose CSV already exists), so a
long full-game run can be interrupted and continued.

The scanner is :mod:`seam_locator` (the fast analytic locator — a superset of the older
``seam_clip_check`` at ~8x). For each ``Room<N>.arc`` the DZB is world-transformed by the stage
``MULT`` room placement (validated identity for dungeons: GanonL via ISO reproduces its 40 live
clips; Earth Temple room 18 = 0). Planes are the bit-exact ``calc_pla`` (the DZB stores none).
Non-room DZBs (e.g. ``Stage.arc`` door collision) have no MULT room, so they are scanned in local
coords; their world placement is unresolved.

Each clippable DZB becomes ``<stage>/<Arc>__<dzb>.csv`` with one row per clippable seam:
    seam_x, seam_y, seam_z, init_x, init_y, init_z, dest_x, dest_y, dest_z, angle_deg
(seam vertex at the standable floor Y, the standable initial/old position, the clip destination/new
position, and the interior angle between the two walls). Coordinates are written at FULL f32
precision — a seam clip is a sub-ULP razor, so rounding a coord turns a CLIP into a BLOCK. DZBs with
no clippable seam write no file.

UNDECIDED seams (the search hit the per-seam ``SEAM_BUDGET`` mid cone-sweep without resolving
clip-or-not — a cheap-pass-wide corner, most often a COPLANAR flat-wall seam, whose f32 gap is
sub-ULP) are NOT proven unclippable, so they are written SEPARATELY to
``<stage>/<Arc>__<dzb>__unknown.csv`` (``seam_x, seam_y, seam_z, interior, floor``; no init/dest — the
clip is undetermined). This keeps the clip CSV schema untouched (existing consumers ignore the
sibling) while flagging what the scan could not decide, instead of silently lumping it with no-clip.

    python -m harness.collision.scan_all_dzb                 # all stages -> _generated/seam_clips
    python -m harness.collision.scan_all_dzb stage=M_Dai     # one stage
    python -m harness.collision.scan_all_dzb out=/some/dir   # override the output dir
"""
import csv
import json
import os
import re
import struct
import sys
import time

from harness.collision.dzb_iso import read_rarc, region_from_dzb
from harness.collision.seam_locator import scan_region     # the shipped scanner (fast analytic superset)

_ROOM_RE = re.compile(r"^Room(\d+)$", re.I)
CSV_HEADER = ["seam_x", "seam_y", "seam_z", "init_x", "init_y", "init_z",
              "dest_x", "dest_y", "dest_z", "angle_deg"]


def _extract_dir():
    cfg = os.path.join(os.path.dirname(__file__), "..", "..", "dolphin.local.json")
    return json.load(open(cfg))["tww_extract_dir"]


def _stage_mult(stage_dir):
    """{room_no: (tx, tz, angY_deg)} from the stage's Stage.arc MULT chunk (empty if none)."""
    sa = os.path.join(stage_dir, "Stage.arc")
    if not os.path.exists(sa):
        return {}
    try:
        st = read_rarc(sa)
    except Exception:
        return {}
    dzs = next((st[k] for k in st if k.lower().endswith(".dzs")), None)
    if dzs is None:
        return {}
    out = {}
    nch = struct.unpack_from(">I", dzs, 0)[0]
    for i in range(nch):
        tag, cnt, off = struct.unpack_from(">4sII", dzs, 4 + i * 12)
        if tag == b"MULT":
            for j in range(cnt):
                tx, tz, ang, rm, _ = struct.unpack_from(">ffhBB", dzs, off + j * 0xC)
                out[rm] = (tx, tz, ang * 360.0 / 65536.0)
    return out


def _g(x):
    """Lossless float -> str (round-trips f32; a rounded seam coord flips CLIP to BLOCK)."""
    return repr(float(x))


UNKNOWN_HEADER = ["seam_x", "seam_y", "seam_z", "interior", "floor"]


def _write_csv(path, clips):
    """One row per clippable seam; FULL precision. ``clips`` = seam_locator result dicts."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in clips:
            S, old, new = r["S"], r["old"], r["new"]
            w.writerow([_g(S[0]), _g(S[1]), _g(S[2]),
                        _g(old[0]), _g(old[1]), _g(old[2]),
                        _g(new[0]), _g(new[1]), _g(new[2]),
                        _g(r["interior"])])


def _write_unknown_csv(path, unknown):
    """One row per UNDECIDED seam (search hit the per-seam budget without resolving clip/no-clip) --
    NOT proven unclippable, so flagged separately from the clip CSV. ``unknown`` = the seam_locator
    ``dict(S, interior, floor)`` entries. Sibling file ``<Arc>__<dzb>__unknown.csv`` (the clip CSV
    schema is left untouched, so existing consumers ignore these)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(UNKNOWN_HEADER)
        for u in unknown:
            S = u["S"]
            w.writerow([_g(S[0]), _g(S[1]), _g(S[2]), _g(u["interior"]), _g(u["floor"])])


def main(argv):
    only_stage = None
    # Regenerable artifact -> the gitignored _generated/ tree (override with out=). No sibling-repo
    # write target: this repo depends only on ../tools/, never ../tww-python-scripts/.
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                       "_generated", "seam_clips"))
    for a in argv:
        if a.startswith("stage="):
            only_stage = a[6:]
        elif a.startswith("out="):
            out = os.path.abspath(a[4:])
    root = os.path.join(_extract_dir(), "files", "res", "Stage")
    stages = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    if only_stage:
        stages = [s for s in stages if s == only_stage]
    # enumerate (stage, arc) work items
    work = []
    for stage in stages:
        sdir = os.path.join(root, stage)
        for arc in sorted(f for f in os.listdir(sdir) if f.lower().endswith(".arc")):
            work.append((stage, sdir, arc))
    print("=== scanning %d arcs across %d stages -> %s ===" % (len(work), len(stages), out),
          flush=True)
    total_clips = total_unknown = total_dzb = errors = 0
    t0 = time.time()
    for wi, (stage, sdir, arc) in enumerate(work):
        outdir = os.path.join(out, stage)
        try:
            files = read_rarc(os.path.join(sdir, arc))
        except Exception as e:
            print("  [%d/%d] %s/%s ARC-ERR %s" % (wi + 1, len(work), stage, arc, e), flush=True)
            errors += 1
            continue
        mult = None
        for dzbname, data in files.items():
            if not dzbname.lower().endswith(".dzb"):
                continue
            csvpath = os.path.join(outdir, "%s__%s.csv" % (os.path.splitext(arc)[0],
                                                           os.path.splitext(dzbname)[0]))
            unkpath = os.path.splitext(csvpath)[0] + "__unknown.csv"
            if os.path.exists(csvpath) or os.path.exists(unkpath):   # resume: clip OR unknown written
                total_dzb += 1
                continue                                    # resume: already done
            m = _ROOM_RE.match(os.path.splitext(arc)[0])
            if m is not None:
                if mult is None:
                    mult = _stage_mult(sdir)
                xform = mult.get(int(m.group(1)), (0.0, 0.0, 0.0))
            else:
                xform = (0.0, 0.0, 0.0)
            try:
                region, box = region_from_dzb(data, *xform)
                clips, unknown = (scan_region(region, box, verbose=False, return_unknown=True)
                                  if region else ([], []))
                if clips or unknown:
                    os.makedirs(outdir, exist_ok=True)
                if clips:
                    _write_csv(csvpath, clips)
                if unknown:
                    _write_unknown_csv(unkpath, unknown)
                total_dzb += 1
                total_clips += len(clips)
                total_unknown += len(unknown)
                tag = "CLIPS=%d" % len(clips) if clips else "clips=0"
                if unknown:
                    tag += " UNKNOWN=%d" % len(unknown)
                print("  [%d/%d] %s/%s::%s tris=%d %s"
                      % (wi + 1, len(work), stage, arc, dzbname, len(region), tag), flush=True)
            except Exception as e:
                print("  [%d/%d] %s/%s::%s DZB-ERR %s"
                      % (wi + 1, len(work), stage, arc, dzbname, e), flush=True)
                errors += 1
    print("=== done: %d DZBs, %d clippable seams, %d unknown (budget-capped) seams, %d errors, %.0fs ==="
          % (total_dzb, total_clips, total_unknown, errors, time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
