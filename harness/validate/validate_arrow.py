"""Offline regression check: superswim_sim arrow-charge model vs the live capture
(capture_arrow.py, current slot-10 slate, v=-300, air~898). Charge-rate is anim-
independent (-3cos2a); the cross-drift fraction dz/|move| = sin(alpha) is read straight
off the position deltas, so neither check needs the (unrecorded) live anim.

Run: python validate_arrow.py
"""
import math, os, csv
import os, sys  # >>> repo bootstrap: locate tww_sim/ package + ../tools/ (dolphin_mem)
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
_tb = os.path.join(os.path.dirname(_rb), 'tools')
if _tb not in sys.path: sys.path.append(_tb)

from tww_sim.swim import sim as S

# (xbias, alpha_deg_from_facing_geometry, measured_charge_rate, measured dx, dz)
# alpha from the facing snap: Delta-facing = 180-2*alpha -> alpha = (180-|dface|)/2.
# rows lifted from capture_arrow.py xbias=128/160/180 (steady frames).
ROWS = [
    # xbias, dface_deg, rate_meas, dx_meas, dz_meas
    (128, 180.0, -3.00, 295.0,  0.0),
    (160, 164.0, -2.88, 291.0, 41.0),
    (180, 144.0, -2.44, 278.0, 89.0),
]

# --- FULL slot-9 capture (2026-06-27, v=-300, cam=270 west, face0=90 east) -----------
# Reorient east->N-S axis then arrow-swim WEST: (35,255)(255,80)(0,128)(0,128) then
# alternate (0,96)/(255,96). Validates the 2-D stepper end-to-end (rotation chain +
# tilted drift bearing), not just the per-frame charge/drift formulas.
# Captured with: python capture_arrow.py seq="..." slot=9 v=-300
SLOT9_STICKS = ([(35, 255), (255, 80), (0, 128), (0, 128)] +
                [(0, 96) if i % 2 == 0 else (255, 96) for i in range(16)])
# live facing (deg) per frame, and the final cumulative net-drift bearing
SLOT9_FACING = [90, 305, 164, 0, 0, 7, 172, 8, 172, 8, 172, 8, 172, 8,
                172, 8, 172, 8, 172, 8]
SLOT9_NET_BRG = 223.0     # live final net bearing (WSW: westward drift confirmed)

def check_slot9():
    rows = S.run_arrow(SLOT9_STICKS, v=-300.0, anim=0.0, air=898,
                       facing_deg=90.0, cam_deg=270.0)
    print("\nFULL slot-9 capture (rotation chain + arrow drift):")
    print(f"{'f':>3} {'stick':>9} {'face_live':>9} {'face_sim':>8} {'err':>5} {'tag':>5}")
    ok = True
    for r, fl in zip(rows, SLOT9_FACING):
        e = abs(S.angdiff_deg(r['facing'], fl))
        ok = ok and e <= 8.0
        print(f"{r['f']:>3} {str(r['stick']):>9} {fl:>9} {r['facing']:>8.0f} "
              f"{e:>5.1f} {r['tag']:>5}")
    nb = rows[-1]['net_brg']
    be = abs(S.angdiff_deg(nb, SLOT9_NET_BRG))
    ok = ok and be <= 8.0
    print(f"net drift bearing: live {SLOT9_NET_BRG:.0f}  sim {nb:.0f}  err {be:.1f}  "
          f"(westward={'YES' if 135 < nb < 270 else 'NO'})")
    print("SLOT9 RESULT:", "OK (facing chain + drift bearing match live)"
          if ok else "MISMATCH")
    return ok

# Game-exact stick->angle dump validating stick_angle_deg gate-wide. Optional, untracked (copyrighted
# game RAM): supply at _generated/INPUT_DUMP_MAIN.csv or via TWW_STICK_DUMP (harness/capture/stick_grid_redump.py).
STICK_DUMP = os.environ.get("TWW_STICK_DUMP") or os.path.join(
    _rb, "_generated", "INPUT_DUMP_MAIN.csv")

def check_stick_table():
    if not os.path.exists(STICK_DUMP):
        print("\nstick-angle table: SKIP (INPUT_DUMP_MAIN.csv not found)")
        return True
    errs = []
    with open(STICK_DUMP) as f:
        for r in csv.reader(f):
            try:
                x, y, ang = int(r[0]), int(r[1]), int(r[5])
            except (ValueError, IndexError):
                continue                                   # header / short row
            mine = S.stick_angle_deg(x, y)
            if mine is None:
                continue
            errs.append(abs(S.angdiff_deg(mine, ang * 360.0 / 65536.0)))
    errs.sort()
    n = len(errs)
    mx, mean, p95 = errs[-1], sum(errs) / n, errs[int(n * 0.95)]
    ok = mx < 1.5 and mean < 0.1
    print(f"\nstick-angle table ({n} game-exact pts): mean={mean:.3f} p95={p95:.3f} "
          f"max={mx:.3f} deg")
    print("STICK-TABLE RESULT:", "OK (model = game stick fn)" if ok else "MISMATCH")
    return ok

def main():
    print(f"{'xb':>4} {'alpha':>6} {'rate_model':>10} {'rate_meas':>9} {'drr_err':>7}"
          f"   {'sin(a)_model':>11} {'dz/|mv|_meas':>11} {'err':>6}")
    ok = True
    for xb, dface, rate_meas, dx, dz in ROWS:
        alpha = (180.0 - dface) / 2.0
        rate_model = S.arrow_charge_rate(alpha)               # dist=1 (full Y)
        sin_model = math.sin(math.radians(alpha))
        frac_meas = dz / math.hypot(dx, dz)                   # = sin(alpha) live
        re = abs(rate_model - rate_meas)
        fe = abs(sin_model - frac_meas)
        ok = ok and re < 0.02 and fe < 0.03
        print(f"{xb:>4} {alpha:>6.1f} {rate_model:>10.3f} {rate_meas:>9.2f} {re:>7.3f}"
              f"   {sin_model:>11.3f} {frac_meas:>11.3f} {fe:>6.3f}")
    print("per-frame RESULT:", "OK (model matches live)" if ok else "MISMATCH")
    ok = check_stick_table() and ok
    ok = check_slot9() and ok
    print("\nOVERALL:", "OK" if ok else "MISMATCH")

if __name__ == "__main__":
    main()
