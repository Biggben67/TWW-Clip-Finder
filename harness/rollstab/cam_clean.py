"""cam_clean.py -- LIVE camera-cleanliness probe for the seam-clip pipeline.

WHY THIS EXISTS (session 69, ROADMAP Phase A exp.5 -- "camera-in-the-loop"):
Live RE this session PROVED there is NO free-space auto-camera follow that moves csangle.
Walking Link straight/turning/arcing in the open arena with a centered C-stick leaves
csangle (``mAngleY``) BIT-FROZEN across every configuration tested (90deg turn, big arc,
sustained main-stick-X deflection). Decomp confirms it: ``dCamera_c::Run`` writes
``mAngleY = mDirection.U().Inv()`` (:905) and csangle == the horizontal bearing(eye->center)
EXACTLY (verified live, diff 0). ``followCamera``'s behind-Link follow updates the VIEW
direction / center, not the controlled csangle the stick decode reads.

So the sim's ``CameraManual`` (C-stick pan azimuth) is already FREE-SPACE-COMPLETE. The only
thing that shifts csangle without a C-stick input is ``bumpCheck`` (:893, runs every frame
just before the mAngleY write): the camera-arm wall collision that pushes the eye laterally.
Per Dereck's steer we do NOT model that collision -- we DETECT it, so the pipeline can confirm
a candidate park + approach is camera-clean (the frozen-cam precondition holds and the from-rest
sim stays bit-exact) or flag exactly where it isn't.

SCOPE (manual cam, NO L): this covers the manual free-behind cam the roll-stab approach walks in.
The L-target / recenter AUTO cam (lockonCamera; the DMC recenter `mAngleY = getDMCAngle` :902) is a
DISTINCT mode that DOES move csangle -- do NOT press L during the probe, and do not read the CLEAN
verdict as applying to an L-target approach.

THE INVARIANT THIS CHECKS:
    With the C-stick centered (csx=128 -> omega_cmd 0) and no L, csangle is provably constant in
    clean space. Any csangle change during such an approach walk is ENVIRONMENTAL (bumpCheck
    pushing the arm off a wall). => walk the intended approach with a centered C-stick (no L) and
    assert csangle holds. First drift frame names where the corridor goes dirty.

DIAGNOSTIC SIGNALS (both read from the live dCamera_c struct, csangle pointer chain + offsets):
  * csangle drift    -- THE pass/fail (a lateral eye push changes bearing(eye->center)).
  * arm compression  -- |eye-center| horizontal shrinking below nominal = the arm is touching a
                        wall (early warning; a purely radial pull may not yet move csangle).

Usage (CLI):
    python -m harness.rollstab.cam_clean anchor=<name> [sx=128 sy=255 n=40 csx=128 csy=128]
    python -m harness.rollstab.cam_clean anchor=<name> tol=0 armdrop=0.15   # thresholds
"""
from __future__ import annotations
import os, sys, math, subprocess

# >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path:
    sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')  # locate tools/
if _tb not in sys.path:
    sys.path.append(_tb)
import dolphin_mem as dm

ANCHORS = os.path.join(_rb, "tww_sim", "tests", "dolphin", "anchors")

# dCamera_c off the csangle pointer chain (inst = chain[0x34]+0x244): mCenter@inst+0x10 -> +0x254,
# mEye@inst+0x1C -> +0x260. Verified live: csangle == bearing(eye->center), nominal horiz arm ~514u.
_CENTER = (0x254, 0x258, 0x25C)   # mCenter.x/y/z (f32)
_EYE = (0x260, 0x264, 0x268)      # mEye.x/y/z    (f32)


def _f32(h, mem1, off):
    a = dm.resolve_chain(h, mem1, 0x803AD380, [0x34, off])
    import struct
    return struct.unpack(">f", dm.read_bytes(h, mem1, a, 4))[0]


def cam_geom(h, mem1):
    """Return (csangle, center(x,y,z), eye(x,y,z), horiz_arm). csangle == bearing(eye->center)."""
    cs = dm.read_named(h, mem1, "csangle") & 0xFFFF
    c = tuple(_f32(h, mem1, o) for o in _CENTER)
    e = tuple(_f32(h, mem1, o) for o in _EYE)
    arm = math.hypot(e[0] - c[0], e[2] - c[2])
    return cs, c, e, arm


def _sdiff(a, b):
    return ((a - b + 0x8000) & 0xFFFF) - 0x8000


def evaluate(rows, tol=0, armdrop=0.15):
    """PURE verdict over recorded probe rows (each: f, cs, dcs, arm[, lx, lz]). Offline-testable.
    CLEAN iff max|csangle drift| <= tol (a nonzero drift is bumpCheck moving the arm off a wall)
    AND the horizontal arm never pulls in more than `armdrop` of its start value."""
    cs0 = rows[0]["cs"]
    arm0 = rows[0].get("arm")   # arm optional (CSV-sourced goldens are csangle-only)
    max_dcs = 0
    first_drift = None
    min_arm = arm0
    for r in rows:
        d = _sdiff(r["cs"], cs0)
        if abs(d) > abs(max_dcs):
            max_dcs = d
        if abs(d) > tol and first_drift is None and r["f"] > 0:
            first_drift = {"f": r["f"], "dcs": d, "lx": r.get("lx"), "lz": r.get("lz")}
        if r.get("arm") is not None and min_arm is not None:
            min_arm = min(min_arm, r["arm"])
    arm_ok = arm0 is None or arm0 <= 0 or (arm0 - min_arm) / arm0 <= armdrop
    clean = abs(max_dcs) <= tol and arm_ok
    return {"clean": clean, "max_dcs": max_dcs, "first_drift": first_drift,
            "arm0": arm0, "min_arm": min_arm}


def probe(anchor, sx=128, sy=255, n=40, csx=128, csy=128, tol=0, armdrop=0.15,
          verbose=True, out=None, settle=2):
    """Load `anchor`, walk n frames with a centered-C-stick (csx=128 => omega 0), and watch
    csangle. Returns dict(clean, max_dcs, first_drift, arm0, min_arm, rows). CLEAN iff
    max|csangle drift| <= tol (a nonzero drift is bumpCheck moving the arm off a wall).
    `out=<path>` dumps a golden JSON (meta + rows) for the offline regression.
    `settle` neutral frames run AFTER load before the baseline: a savestate load leaves the
    camera-pointer chain reading the PREVIOUS camera for a frame (the REST_NOOPS transient), so
    the baseline must be taken after the game has stepped once."""
    savpath = os.path.join(ANCHORS, anchor + ".sav")
    if not os.path.exists(savpath):
        savpath = os.path.join(ANCHORS, anchor)
    subprocess.run([sys.executable, os.path.join(_tb, "dolphin_mem.py"),
                    "savestate", "loadfile", savpath], check=True, capture_output=True)
    h, mem1 = dm.attach()
    for _ in range(settle):     # clear the post-load camera transient before the baseline
        dm.control_pipe_quiet("advancewith", {"stickX": 128, "stickY": 128,
                                              "substickX": 128, "substickY": 128, "frames": 1})

    cs0, _, _, arm0 = cam_geom(h, mem1)
    rows = [{"f": 0, "cs": cs0, "dcs": 0, "arm": round(arm0, 3)}]
    for i in range(1, n + 1):
        dm.control_pipe_quiet("advancewith", {"stickX": sx, "stickY": sy,
                                              "substickX": csx, "substickY": csy, "frames": 1})
        cs, c, e, arm = cam_geom(h, mem1)
        rows.append({"f": i, "cs": cs, "dcs": _sdiff(cs, cs0), "arm": round(arm, 3),
                     "lx": round(c[0], 2), "lz": round(c[2], 2)})

    res = evaluate(rows, tol=tol, armdrop=armdrop)
    res["rows"] = rows
    max_dcs, first_drift, min_arm = res["max_dcs"], res["first_drift"], res["min_arm"]
    clean = res["clean"]
    if out:
        import json
        with open(out, "w") as f:
            json.dump({"anchor": anchor, "sx": sx, "sy": sy, "csx": csx, "csy": csy,
                       "n": n, "rows": rows}, f, indent=1)
        if verbose:
            print(f"  wrote golden {out}")
    if verbose:
        arm_pct = 0.0 if arm0 <= 0 else 100.0 * (arm0 - min_arm) / arm0
        print(f"# cam_clean anchor={anchor} sx={sx} sy={sy} csx={csx} n={n} tol={tol}")
        print(f"  csangle0={cs0}  max|drift|={abs(max_dcs)} hw   "
              f"arm {arm0:.1f}->{min_arm:.1f} ({arm_pct:.1f}% pull-in)")
        if first_drift:
            print(f"  FIRST DRIFT at f{first_drift['f']} (dcs={first_drift['dcs']}) "
                  f"pos=({first_drift['lx']:.1f},{first_drift['lz']:.1f})")
        print(f"  VERDICT: {'CLEAN' if clean else 'DIRTY (camera-wall csangle contamination)'}")
    return res


def main():
    o = {}
    for tok in sys.argv[1:]:
        k, _, v = tok.partition("="); o[k] = v
    if "anchor" not in o:
        print(__doc__); sys.exit(1)
    probe(o["anchor"], sx=int(o.get("sx", 128)), sy=int(o.get("sy", 255)),
          n=int(o.get("n", 40)), csx=int(o.get("csx", 128)), csy=int(o.get("csy", 128)),
          tol=int(o.get("tol", 0)), armdrop=float(o.get("armdrop", 0.15)))


if __name__ == "__main__":
    main()
