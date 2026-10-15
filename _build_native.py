"""Build the native (Cython) accelerators in-place:
  tww_sim/core/_fpc.pyx        -- single-precision (f32) fused ops
  tww_sim/core/anim/_anmc.pyx  -- land-walk anim hot loop (matrix/quat/Hermite)
  tww_sim/core/_collc.pyx      -- wall-collision hot loop (crr_pos_walls/line_check/wall_correct)

All are OPTIONAL: when a .pyd is absent the pure-Python fallbacks run (same result). Run:
    python _build_native.py            # build all
    python _build_native.py _anmc      # build only the anim accelerator
    python _build_native.py _collc     # build only the collision accelerator
"""
import sys
from setuptools import setup, Extension
from Cython.Build import cythonize

_SOURCES = {
    "_fpc": "tww_sim/core/_fpc.pyx",
    "_anmc": "tww_sim/core/anim/_anmc.pyx",
    "_collc": "tww_sim/core/_collc.pyx",
    "_shovec": "tww_sim/core/_shovec.pyx",
}
# _shovec's sweep_par uses OpenMP (prange); MSVC flag. Exactness
# is untouched: /openmp does not change FP codegen, and every op is an explicit <float> cast.
_OMP = {"_shovec": ["/openmp"]}          # only _shovec fans out with prange

sel = [a for a in sys.argv[1:] if a in _SOURCES]
exts = [Extension(_SOURCES[k].replace("/", ".").rsplit(".pyx", 1)[0].replace(".pyx", ""),
                  [_SOURCES[k]], extra_compile_args=_OMP.get(k, []))
        for k in (sel or _SOURCES)]
# strip our own args so setuptools only sees build_ext
sys.argv = [sys.argv[0], "build_ext", "--inplace"]
setup(name="tww_sim_native", ext_modules=cythonize(exts, language_level=3))
