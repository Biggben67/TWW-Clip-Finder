"""verify_stick_dump.py — certify a stick-grid dump WITHOUT trusting the raw-stick->clamp path.

The dump captures, per cell, the game's mMainStickAngle (`angle`) and mPosX/mPosY (`x`,`y`).
By construction (JUTGamePad::CStick::update) these satisfy
    angle == (s16) round-to-zero( 10430.3779296875f * atan2f(x, -y) )      [atan2f = (float)atan2(double)]
regardless of the deadzone/octagon clamp or Dolphin's analog quirks. So checking angle against
atan2f(x,-y) is an INTERNAL consistency proof: it catches exactly the failure the old table had
— angle captured from a different (latency-lagged) frame than x/y (e.g. (160,160) angle 24260 while
x==y demanded 24576). CSV stores x/y to 7 sig figs, so we allow |Δangle| <= TOL_S16 (a couple s16);
a real latency mismatch is off by hundreds.

Also: value == hypot(x,y) capped; stick_dist == value; and diff vs the shipped table (report the
angle cells that changed + confirm x==y cells resolve to exact-clean diagonals).

Usage:
    python verify_stick_dump.py new=superswim/tables/stick_angle_full.csv \
                                [old=superswim/tables/stick_angle_table.csv] [tol=2]
"""
import os, sys, csv, math

_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
if _rb not in sys.path: sys.path.insert(0, _rb)
from tww_sim.swim import sim as S            # S.f32 = ctypes-backed f32 rounding

RAD2S = 10430.3779296875                  # 0x8000/pi (the f32 constant 10430.379f rounds here)


def s16(v):
    return ((int(v) + 0x8000) & 0xFFFF) - 0x8000


def angle_from_xy(x, y):
    """Reproduce JUTGamePad::CStick::update's mAngle from mPosX=x, mPosY=y, in f32."""
    if y == 0.0:
        return 0x4000 if x > 0.0 else -0x4000
    # atan2f(x, -y) = (float)atan2((double)x, (double)-y); then * 10430.379f, cast to s16
    a = S.f32(math.atan2(x, -y))
    return s16(S.f32(RAD2S * a))           # C float->s16 truncates toward zero


def s16diff(a, b):
    d = ((a - b + 0x8000) & 0xFFFF) - 0x8000
    return abs(d)


def load(path):
    t = {}
    for r in csv.DictReader(open(path)):
        t[(int(r["sx"]), int(r["sy"]))] = r
    return t


def main():
    o = dict(t.split("=", 1) for t in sys.argv[1:] if "=" in t)
    new = load(o.get("new", os.path.join(_rb, "tww_sim", "core", "tables", "stick_angle_full.csv")))
    tol = int(o.get("tol", "2"))
    oldp = o.get("old", os.path.join(_rb, "tww_sim", "core", "tables", "stick_angle_table.csv"))
    old = load(oldp) if os.path.exists(oldp) else {}

    print("cells: %d" % len(new))
    if len(new) != 256 * 256:
        print("  !! expected 65536 cells, got %d (dump incomplete?)" % len(new))

    bad_angle = []      # angle inconsistent with its own x/y (latency mismatch)
    bad_value = []      # value != hypot(x,y) capped
    bad_sd = []         # stick_dist != value
    diag_bad = []       # x==y but angle not the exact-clean diagonal
    for (sx, sy), r in new.items():
        ang = int(r["angle"]); x = float(r["x"]); y = float(r["y"]); val = float(r["value"])
        sd = float(r["stick_dist"])
        if not (x == 0.0 and y == 0.0):
            pred = angle_from_xy(x, y)
            if s16diff(ang, pred) > tol:
                bad_angle.append((sx, sy, ang, pred))
        vpred = min(math.hypot(x, y), 1.0)
        if abs(val - vpred) > 5e-4:
            bad_value.append((sx, sy, val, vpred))
        if abs(sd - val) > 5e-4:
            bad_sd.append((sx, sy, sd, val))
        if x != 0.0 and y != 0.0 and abs(abs(x) - abs(y)) < 1e-6:   # exact diagonal
            # a perfect diagonal must land on an exact multiple of 0x2000 (45 deg)
            if (ang & 0x1FFF) not in (0, 0x1FFF) and s16diff(ang, round(ang / 0x2000) * 0x2000) > tol:
                diag_bad.append((sx, sy, ang))

    print("angle vs atan2f(x,-y) inconsistent (|d|>%d s16): %d" % (tol, len(bad_angle)))
    for c in bad_angle[:20]:
        print("   ", c)
    print("value != hypot(x,y) capped: %d" % len(bad_value))
    for c in bad_value[:10]:
        print("   ", c)
    print("stick_dist != value: %d" % len(bad_sd))
    for c in bad_sd[:10]:
        print("   ", c)
    print("exact-diagonal cells off the 45deg grid: %d" % len(diag_bad))
    for c in diag_bad[:10]:
        print("   ", c)

    if old:
        changed = [(sx, sy, int(old[(sx, sy)]["angle"]), int(r["angle"]))
                   for (sx, sy), r in new.items()
                   if (sx, sy) in old and int(old[(sx, sy)]["angle"]) != int(r["angle"])]
        print("\nangle cells changed vs shipped table: %d" % len(changed))
        big = [c for c in changed if s16diff(c[2], c[3]) > tol]
        print("  of which |d|>%d s16 (the real corruption fixed): %d" % (tol, len(big)))
        for c in big[:30]:
            print("    (%d,%d) %d -> %d  (d=%d)" % (c[0], c[1], c[2], c[3], s16diff(c[2], c[3])))

    ok = not (bad_angle or bad_value or bad_sd or diag_bad) and len(new) == 256 * 256
    print("\n%s" % ("ALL CHECKS PASS — dump is internally bit-consistent" if ok
                    else "ISSUES FOUND (see above)"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
