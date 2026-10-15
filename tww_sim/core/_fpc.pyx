# cython: language_level=3
# Native single-precision (f32) ops. (float)(double expr) rounds once, round-half-to-even -- bit-
# identical to ctypes c_float(...) and to fp.py's f64-arith-then-f32. MSVC /fp:precise does not
# contract a*b+c into a hardware FMA, so the double intermediates match fp.py exactly.
cpdef inline double f32(double x):
    return <double><float>x
cpdef inline double fmuls(double a, double b):
    return <double><float>(a * b)
cpdef inline double fadds(double a, double b):
    return <double><float>(a + b)
cpdef inline double fsubs(double a, double b):
    return <double><float>(a - b)
cpdef inline double fdivs(double a, double b):
    return <double><float>(a / b)
cpdef inline double fmadds(double a, double b, double c):
    return <double><float>(a * b + c)
cpdef inline double fmsubs(double a, double b, double c):
    return <double><float>(a * b - c)
cpdef inline double fnmadds(double a, double b, double c):
    return <double><float>(-(a * b + c))
cpdef inline double fnmsubs(double a, double b, double c):
    return <double><float>(-(a * b - c))
