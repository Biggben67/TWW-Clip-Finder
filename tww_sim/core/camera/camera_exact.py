"""camera_exact.py — BIT-EXACT camera yaw (csangle) predictor for TWW superswim steering.

Recovered by LIVE reverse-engineering of GZLJ01 (2026-06-28), NOT by decompiling: the
C-stick X -> camera-rate curve flows through dCamMath::rationalBezierRatio, which is
Nonmatching in the decomp. The exact model was read out of live RAM via two fields of the
dCamera_c instance (base resolved from the csangle writer PC 0x80160a0c, r28 = 0x80acffa4
after slot 10):

    yaw    s16 @ instance+0x0E   (0x80acffb2)   -- the integrated camera yaw
    target s16 @ instance+0x3AE  (0x80ad0352)   -- the angle accumulator the yaw chases
    csangle (the u16 we read via [[0x803AD380]+0x34]+0x2B0) = (yaw + 0x8000) & 0xFFFF
                                                  (mAngleY/+0x6C path; +0x8000 offset, verified live)

EXACT PER-FRAME RECURRENCE (all s16, integer arithmetic; verified bit-exact incl. sign flips):

    # 1-frame input lag: the C-stick supplied on frame f is consumed by the camera on f+1.
    target = (target + omega_cmd(csx_prev, csy_prev)) & 0xFFFF        # accumulate the rate command
    diff   = s16(target - yaw)
    yaw    = (yaw + int(diff / 2)) & 0xFFFF                           # C integer divide, trunc toward 0
    csangle = (yaw + 0x8000) & 0xFFFF

  * omega_cmd(csx) is an INTEGER (the per-frame target increment), measured live (tables below).
    It is the C-stick X -> camera-rate curve. Deadzone, steep S-curve, saturation:
      - deadzone:    csx in 113..148  -> 0   (asymmetric: +d<=20 i.e. csx<=148 give 0, but the
                     low side's last zero is csx=112, so -d<=15; csx 109..112 already give -1)
      - saturation:  csx >= 175  -> +546 ;  csx <= 81  -> -547   (= +/-3.0 deg/frame, |d|>=47)
      - between:     the measured _OMEGA_POS / _OMEGA_NEG tables (NOT perfectly symmetric:
                     e.g. csx=160 (d=+32)->+18 but csx=96 (d=-32)->-19).
    C-stick full DOWN (csy <= 64) is the free-cam FREEZE used by straight superswims -> 0.

  * The chase yaw += int(diff/2) is exactly cLib_addCalcAngleS-style proportional convergence
    with scale 2 and no min/max clamp in this regime (the C `/2` truncates toward zero, so a
    rising yaw truncs down and a settling/decaying yaw truncs toward target — this reproduces
    BOTH the build ramp and the release tail, which a per-frame "round(omega)" model cannot).

  * REST STATE: with neutral C-stick, target == yaw - 1 (a fixed -1 offset that holds yaw still,
    since int(-1/2) == 0). The predictor seeds target = yaw_init - 1.

This is fully integer and deterministic. No floats, no curve-fitting: omega_cmd is read directly
from the live target field (target_delta == omega_cmd exactly), and the chase is verified
int(diff/2) every frame including through reversals.
"""
from __future__ import annotations

# omega_cmd integer table, indexed by raw substickX (0..255), measured live on GZLJ01 (slot 10).
# Positive deflection (csx > 128):
_OMEGA_POS = {
    149: 1, 150: 2, 151: 2, 152: 3, 153: 4, 154: 6, 155: 7, 156: 9, 157: 11, 158: 13,
    159: 15, 160: 18, 161: 22, 162: 26, 163: 31, 164: 36, 165: 43, 166: 51, 167: 60,
    168: 72, 169: 86, 170: 105, 171: 130, 172: 164, 173: 218, 174: 325,
}
# Negative deflection (csx < 128):
_OMEGA_NEG = {
    112: -1, 111: -1, 110: -1, 109: -1,
    108: -1, 107: -2, 106: -3, 105: -3, 104: -4, 103: -5, 102: -6, 101: -8, 100: -10,
    99: -12, 98: -14, 97: -16, 96: -19, 95: -23, 94: -27, 93: -32, 92: -37, 91: -44,
    90: -52, 89: -61, 88: -73, 87: -87, 86: -106, 85: -131, 84: -165, 83: -219, 82: -326,
}
SAT_POS = 546     # csx >= 175  (|d| >= 47)
SAT_NEG = -547    # csx <= 81


def omega_cmd(csx: int, csy: int = 128) -> int:
    """Integer per-frame target increment commanded by the C-stick (the camera-rate curve)."""
    if csy <= 64:                 # free-cam freeze (C-stick held down)
        return 0
    csx = int(csx)
    if csx >= 175:
        return SAT_POS
    if csx <= 81:
        return SAT_NEG
    if csx > 128:
        return _OMEGA_POS.get(csx, 0)
    if csx < 128:
        return _OMEGA_NEG.get(csx, 0)
    return 0


def _s16(x: int) -> int:
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


class CameraExact:
    """Bit-exact per-frame csangle predictor. csangle in halfword (0..65535)."""

    def __init__(self, csangle: int = 49152, target: int | None = None, pending_cmd: int = 0):
        self.yaw = (int(csangle) - 0x8000) & 0xFFFF          # internal s16 yaw (+0x0E)
        # rest offset: target = yaw - 1 (holds yaw still since int(-1/2)==0)
        self.target = (self.yaw - 1) & 0xFFFF if target is None else int(target) & 0xFFFF
        self._pending = int(pending_cmd)                     # 1-frame input lag

    @property
    def csangle(self) -> int:
        return (self.yaw + 0x8000) & 0xFFFF

    def clone(self) -> "CameraExact":
        c = CameraExact.__new__(CameraExact)
        c.yaw = self.yaw
        c.target = self.target
        c._pending = self._pending
        return c

    def step(self, csx: int, csy: int = 128) -> int:
        """Advance one frame; the C-stick (csx,csy) takes effect with a 1-frame lag.
        Returns the new csangle (halfword)."""
        self.target = (self.target + self._pending) & 0xFFFF
        diff = _s16(self.target - self.yaw)
        self.yaw = (self.yaw + int(diff / 2)) & 0xFFFF       # C integer divide (trunc toward 0)
        self._pending = omega_cmd(csx, csy)
        return self.csangle


# ----------------------------------------------------------------------------------
# Validation against a camera_capture.py CSV (bit-exact: predicted csangle == live)
# ----------------------------------------------------------------------------------
def validate(csv_path, verbose=False):
    import csv
    rows = list(csv.DictReader(open(csv_path)))
    cs = CameraExact(csangle=int(rows[0]["csangle"]))
    worst = nbad = 0
    for r in rows[1:]:
        csx = int(r["csx"]) if r["csx"] != "" else 128
        csy = int(r["csy"]) if r["csy"] != "" else 128
        pred = cs.step(csx, csy)
        live = int(r["csangle"])
        err = ((pred - live + 0x8000) & 0xFFFF) - 0x8000
        if err:
            nbad += 1
            if verbose:
                print(f"  f{r['f']} csx={csx} live={live} pred={pred} err={err}")
        worst = max(worst, abs(err))
    print(f"{csv_path}: WORST |err| = {worst} hw, {nbad}/{len(rows)-1} frames off")
    return worst


if __name__ == "__main__":
    import sys
    paths = sys.argv[1:] or ["capA.csv", "capB.csv", "capC.csv",
                             "cap_hold160.csv", "cap_hold170.csv", "cap_hold175.csv",
                             "cap_tap.csv", "cap_reversal.csv"]
    tot = 0
    for p in paths:
        try:
            tot = max(tot, validate(p, verbose=True))
        except FileNotFoundError:
            print(f"{p}: (missing)")
    print(f"\nOVERALL WORST |err| = {tot} hw")
