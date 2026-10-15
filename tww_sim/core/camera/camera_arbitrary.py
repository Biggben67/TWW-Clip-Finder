"""camera_arbitrary.py - BIT-EXACT camera yaw (csangle) for ARBITRARY C-stick (csx,csy).

GAP 1 fix. camera_exact.CameraExact models the C-stick -> camera-rate command omega_cmd as a
function of csx ONLY, with a csy<=64 'freeze' (return 0). That is bit-exact only when csy stays
in the rotation regime (csy=128). For arbitrary csy it is wrong: live RE (omega_capture.py)
shows omega_cmd is a function of the WHOLE C-stick vector -- csy modulates the horizontal rate,
and there is NO csy<=64 freeze (e.g. csx=255,csy=0 gives omega 173, not 0).

This subclass keeps the EXACT integer recurrence (verified bit-exact incl. sign flips):

    cam_target += omega_cmd(csx_prev, csy_prev)         # 1-frame input lag
    cam_yaw    += int((s16)(cam_target - cam_yaw) / 2)  # C integer divide, trunc toward 0
    csangle     = (cam_yaw + 0x8000) & 0xFFFF

and only replaces omega_cmd with the live-captured 2-D table omega_table.csv (omega_capture.py).
For (csx,csy) NOT in the table it falls back to camera_exact.omega_cmd (the csx-only model) so
the 13 clean csy=128 captures still validate without re-capturing -- but a csy NOT in {128} that
is uncached raises so it is never silently approximated. NOTE one csy=128 cell the old table got
wrong (omega_cmd(109,128): old 0, live -1) -- that was the cap_camchaos 1-hw residual; the
captured table fixes it.

The auto-camera-FOLLOW the GAP-1 brief hypothesized was DISPROVEN by live RE: with a neutral or
frozen C-stick the camera does NOT move while Link charges/turns (d_cam_target == 0). All camera
motion comes from the C-stick via omega_cmd(csx,csy); there is no facing-follow term to model.
"""
from __future__ import annotations
import os, csv
from . import camera_exact as CE

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables")
# Two live omega sources (both raw-byte advancewith path, agree bit-exact on overlap): the csx 0..15
# x csy 0..255 grid omega_table_full.csv + fine per-capture cells omega_table.csv. NOT a 65536 grid.
_FULL_PATH = os.path.join(_HERE, "omega_table_full.csv")
_TABLE_PATH = os.path.join(_HERE, "omega_table.csv")

_OMEGA: dict[tuple[int, int], int] = {}
for _p in (_FULL_PATH, _TABLE_PATH):     # fine table loaded LAST so it wins on any overlap
    if os.path.exists(_p):
        for _r in csv.DictReader(open(_p)):
            _OMEGA[(int(_r["csx"]), int(_r["csy"]))] = int(_r["omega"])

_COMPLETE = len(_OMEGA) >= 256 * 256     # not a dense 256x256 grid; csx 0..15 band + captured cells


def omega_cmd(csx: int, csy: int) -> int:
    """Per-frame camera-rate command for the C-stick (csx,csy): exact lookup from the live grid +
    captures, the csx-only closed model when csy==128, else raise (off-grid is never approximated;
    capture the needed cells via harness/capture/omega_capture.py if off-grid accuracy matters)."""
    csx, csy = int(csx), int(csy)
    if (csx, csy) in _OMEGA:
        return _OMEGA[(csx, csy)]
    if csy == 128:                       # csx-only regime: the closed model is exact here
        return CE.omega_cmd(csx, csy)
    raise KeyError(f"omega for C-stick ({csx},{csy}) missing (table complete={_COMPLETE}); "
                   f"capture it via harness/capture/omega_capture.py --sticks {csx},{csy}")


def has(csx: int, csy: int) -> bool:
    return (int(csx), int(csy)) in _OMEGA or int(csy) == 128


class CameraArbitrary(CE.CameraExact):
    """CameraExact whose omega_cmd is the live-captured 2-D table (arbitrary csy)."""

    def step(self, csx: int, csy: int = 128) -> int:
        self.target = (self.target + self._pending) & 0xFFFF
        diff = CE._s16(self.target - self.yaw)
        self.yaw = (self.yaw + int(diff / 2)) & 0xFFFF
        self._pending = omega_cmd(csx, csy)
        return self.csangle

    def clone(self) -> "CameraArbitrary":
        c = CameraArbitrary.__new__(CameraArbitrary)
        c.yaw = self.yaw
        c.target = self.target
        c._pending = self._pending
        return c
