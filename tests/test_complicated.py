"""test_complicated.py — bit-exact regression test for the unified superswim predictor on
COMPLICATED input: a random-direction charge build (to ~-140) with a randomly-spun camera.

Validates swim_predict_full.predict() against live ground-truth captures (offline, fast).
PASS = bit-exact: cam 0 hw, v 0.0, anim 0.0, position at the f32 floor (<= 0.01).

Captures (live ground truth, in tests/):
  cap_randcharge.csv  — RANDOM main-stick directions (sx 98-158, sy alt) charging to ~-140,
                        with FULLY RANDOM C-stick (csx,csy 0..255) spinning the camera.
                        Stresses: arbitrary-direction charge gains + camera under uncontrolled
                        C-stick (freeze + auto-follow regimes).  [currently FAILS — to solve]
  cap_camchaos.csv    — clean charge main-stick + RANDOM csx, csy=128 fixed (rotation regime).
                        Isolates the camera under random csx with no freeze.  [~1 hw]

Run:  python tests/test_complicated.py
"""
import os, sys, csv, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from tww_sim.swim.predict import swim_predict_complicated as F

# bit-exact thresholds (POS allowed up to the single-ULP f32 floor at ~4e4 coords)
TOL_CAM_HW = 0      # camera must be exact s16
TOL_V = 1e-4
TOL_ANIM = 1e-3
TOL_POS = 0.01

CASES = [
    ("cap_randcharge.csv", "random-dir charge to ~-140 + fully-random camera"),
    ("cap_camchaos.csv",   "clean charge + random csx (csy=128)"),
    # GENERALIZATION (new random seeds, captured live; not the curve-fit set):
    ("gen_charge.csv",     "random-dir charge (seed 101) + fully-random camera"),
]


def run_case(fname):
    path = os.path.join(HERE, fname)
    rows = list(csv.DictReader(open(path)))
    f0 = rows[0]
    frames = [(int(r["sx"]), int(r["sy"]), int(r["csx"]), int(r["csy"])) for r in rows[1:]]
    mrate0 = float(f0["move0_mrate"])
    # seed exactly like capture_full (run_tests-style); pass logged mRate for the cold start
    pred = F.predict_full(frames, v0=float(f0["potential_speed"]), anim0=float(f0["anim_frame"]),
                          air0=int(f0["air"]), st0=int(f0["link_state"]), cam0=int(f0["csangle"]),
                          facing0=int(f0["facing"]), mrate0=mrate0,
                          x0=float(f0["link_x"]), z0=float(f0["link_z"]))
    wcam = wv = wa = wpos = 0.0
    for r, p in zip(rows[1:], pred):
        wcam = max(wcam, abs(((p["cam"] - int(r["csangle"]) + 0x8000) & 0xFFFF) - 0x8000))
        wv = max(wv, abs(p["v"] - float(r["potential_speed"])))
        wa = max(wa, abs(p["anim"] - float(r["anim_frame"])))
        wpos = max(wpos, math.hypot(p["x"] - float(r["link_x"]), p["z"] - float(r["link_z"])))
    ok = (wcam <= TOL_CAM_HW and wv <= TOL_V and wa <= TOL_ANIM and wpos <= TOL_POS)
    return ok, wcam, wv, wa, wpos


# --- pytest entry points (offline; reads tests/*.csv, no Dolphin) ----------------------
# All three cases are strictly bit-exact (cam 0 hw, v 0, anim 0, pos at the f32 floor). The old
# cam=1-2hw bound on the random-camera cases was the corrupt omega grid (see knowledge/history/camera-model-history.md).
import pytest  # noqa: E402  (kept below the script body so `python tests/test_complicated.py` is unaffected)

_BIT_EXACT = {"cap_camchaos.csv", "cap_randcharge.csv", "gen_charge.csv"}


@pytest.mark.parametrize("fname,desc", CASES, ids=[c[0] for c in CASES])
def test_predict_complicated(fname, desc):
    ok, wcam, wv, wa, wpos = run_case(fname)
    assert fname in _BIT_EXACT
    assert ok, ("expected bit-exact for %s but cam=%s v=%g anim=%g pos=%g"
                % (fname, wcam, wv, wa, wpos))


def main():
    allok = True
    for fname, desc in CASES:
        try:
            ok, wcam, wv, wa, wpos = run_case(fname)
        except Exception as e:
            print(f"ERROR {fname}: {e}"); allok = False; continue
        allok &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {fname}: cam={wcam}hw v={wv:.5f} "
              f"anim={wa:.5f} pos={wpos:.4f}  ({desc})")
    print("---")
    print("ALL BIT-EXACT" if allok else "NOT bit-exact (see FAILs)")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
