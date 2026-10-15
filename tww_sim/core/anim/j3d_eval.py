"""j3d_eval.py - port of the J3D animation keyframe eval: sample a BCK's per-joint TRS at
an arbitrary (fractional) frame, bit-faithful to the console.

Spec (tww/src/JSystem/J3DGraphAnimator/J3DAnimation.cpp):
  - J3DHermiteInterpolationS (L323): s16 rotation Hermite. The C comment is readable-but-not-
    identical; the authoritative version is the inline PPC asm (L342-363). Ported instruction-by-
    instruction below with the fused ops from tww_sim.core.fp. s16 keyframe data is loaded via
    `psq_l ...,5` = GQR5 = S16 quant, scale 0 (OSInitFastCast) -> pure (float)s16.
  - JMAHermiteInterpolation (JMath.cpp:82): f32 scale/translate Hermite (plain C; ported with
    fused ops in source order -- validated empirically, see NOTE).
  - J3DGetKeyFrameInterpolation[S] (L369/L414): endpoint clamp (frame<data[0] -> first value;
    frame>=last time -> last value) + binary-search bisect. stride 3 (type0: time,val,tan) or
    4 (type1: time,val,tanIn,tanOut; interp uses left tanOut=data[3], right tanIn=data[6]).
  - J3DAnmTransformKey::calcTransform (L459): per joint idx, per axis: mMaxFrame 0 -> default
    (S=1,R=0,T=0); 1 -> constant data[mOffset]; else Hermite. Rotation result: (s32)f << mDecShift
    (the constant case also shifts).

Data source = parse_bck.py output (_generated/anim/link_anim_walk_dash.json): per joint j, axes
dict 's'/'r'/'t' each a list of 3 [count, offset, ttype] KeyTables (x/y/z), plus scale_data (f32),
rot_data (s16), trans_data (f32) arrays, and dec_shift.

NOTE the f32 Hermite's exact op fusion is MWCC codegen; if a downstream toe position is off by
ULPs and traces to an animated translate/scale track, pull the real disassembly. The s16 path
(all leg/foot rotations -- the dominant term) is the exact asm and needs no such caveat.

Reads gitignored _generated anim data (dev-supplied). Rotations are returned as s16 BAM (already
<<decShift), matching J3DTransformInfo.mRotation.
"""
import os, sys, json, struct

from .. import fp


# --- s16 Hermite: exact port of the inline asm (J3DAnimation.cpp:342-363) ---------------------
def hermite_s16(t, time0, value0, tan0, time1, value1, tan1):
    """t is f32 frame; the other 6 are raw s16 keyframe ints (loaded as (float)s16). Returns f32.
    Register trace of the asm: fout aliases the entry arg t (used before its psq_l reload)."""
    f0 = float(time0)                       # psq_l f0, time0
    f3 = float(time1)                       # psq_l f3, time1
    f2 = float(value0)                      # psq_l f2, value0
    f4 = fp.fsubs(f3, f0)                   # fsubs f4,f3,f0     ; timeRange
    f3 = float(value1)                      # psq_l f3, value1
    f6 = fp.fsubs(t, f0)                    # fsubs f6,fout,f0   ; fout==t here
    fout = float(tan1)                      # psq_l fout, tan1
    f5 = fp.fsubs(f3, f2)                   # fsubs f5,f3,f2     ; value1-value0
    f6 = fp.fdivs(f6, f4)                   # fdivs f6,f6,f4     ; kt
    f0 = float(tan0)                        # psq_l f0, tan0
    fout = fp.fmadds(fout, f4, f2)          # fmadds fout,fout,f4,f2   ; tan1*tr+value0
    f7 = fp.fmuls(f6, f6)                   # fmuls f7,f6,f6     ; kt*kt
    f5 = fp.fnmsubs(f4, f0, f5)             # fnmsubs f5,f4,f0,f5      ; (v1-v0)-tr*tan0
    fout = fp.fsubs(fout, f3)               # fsubs fout,fout,f3
    fout = fp.fsubs(fout, f5)               # fsubs fout,fout,f5
    f3 = fp.fmuls(f7, fout)                 # fmuls f3,f7,fout   ; t2
    fout = fp.fmadds(f4, f0, f3)            # fmadds fout,f4,f0,f3     ; tr*tan0+t2
    fout = fp.fmadds(fout, f6, f2)          # fmadds fout,fout,f6,f2   ; *kt+value0
    fout = fp.fmadds(f5, f7, fout)          # fmadds fout,f5,f7,fout
    fout = fp.fsubs(fout, f3)               # fsubs fout,fout,f3       ; -t2
    return fout


# --- f32 Hermite: JMAHermiteInterpolation (JMath.cpp:82), fused ops in source order -----------
def hermite_f32(frame, time0, value0, tan0, time1, value1, tan1):
    length = fp.fsubs(time1, time0)
    f9 = fp.fsubs(frame, time0)
    f1 = fp.fdivs(1.0, length)
    f2 = fp.fmuls(fp.fmuls(f9, f9), f1)
    f10 = fp.fmuls(f2, f1)
    f11 = fp.fmuls(f9, f10)
    f12 = fp.fmuls(f11, f1)
    # value0 * (1 + (2*f12 - 3*f10))
    a = fp.fmadds(value0, fp.fadds(1.0, fp.fmsubs(2.0, f12, fp.fmuls(3.0, f10))), 0.0)
    # value1 * (-2*f12 + 3*f10)
    b = fp.fmuls(value1, fp.fmadds(-2.0, f12, fp.fmuls(3.0, f10)))
    # tangent0 * (f9 + (f11 - 2*f2))
    c = fp.fmuls(tan0, fp.fadds(f9, fp.fnmsubs(2.0, f2, f11)))   # f11 - 2*f2
    # tangent1 * (f11 - f2)
    d = fp.fmuls(tan1, fp.fsubs(f11, f2))
    return fp.fadds(fp.fadds(fp.fadds(a, b), c), d)


# --- keyframe lookup: endpoint clamp + bisect (J3DGetKeyFrameInterpolation[S]) -----------------
def _keyframe_interp(frame, count, ttype, data, base, hermite):
    """data = flat list, base = mOffset into it. stride 3 (type0) or 4 (type1). hermite is the
    s16 or f32 hermite fn. Returns f32."""
    stride = 3 if ttype == 0 else 4
    d0 = data[base + 0]
    if frame < d0:
        return float(data[base + 1])
    last = base + stride * (count - 1)
    if data[last] <= frame:
        return float(data[last + 1])
    # bisect: p is index into data (in stride units offset from base)
    p = base
    num = count
    while num > 1:
        mid = num // 2
        if frame >= data[p + stride * mid]:
            p += stride * mid
            num -= mid
        else:
            num = mid
    if stride == 3:
        return hermite(frame, data[p+0], data[p+1], data[p+2], data[p+3], data[p+4], data[p+5])
    else:
        return hermite(frame, data[p+0], data[p+1], data[p+3], data[p+4], data[p+5], data[p+6])


# --- calcTransform: per-joint TRS at a frame (J3DAnmTransformKey::calcTransform) ---------------
# calc_transform is PURE in (anm, joint, frame) -> memoize (walk frames recur; shared across a search).
# Cache lives ON the anm dict (per-anm, NOT id()-keyed: id-reuse-after-GC corrupts it); result read-only.
def calc_transform(anm, joint_idx, frame):
    """Return dict scale=[x,y,z] (f32), rotation=[x,y,z] (s16 BAM, <<decShift applied),
    translate=[x,y,z] (f32) for the joint at fractional `frame`. Memoized per-anm (pure)."""
    _cache = anm.get('_ct_cache')
    if _cache is None:
        _cache = anm['_ct_cache'] = {}
    _ck = (joint_idx, frame)
    _cv = _cache.get(_ck)
    if _cv is not None:
        return _cv
    j = anm['joints'][joint_idx]
    dec = anm['dec_shift']
    sdata, rdata, tdata = anm['scale_data'], anm['rot_data'], anm['trans_data']
    out = {'scale': [1.0, 1.0, 1.0], 'rotation': [0, 0, 0], 'translate': [0.0, 0.0, 0.0]}
    for axis in range(3):
        # scale
        cnt, off, tt = j['s'][axis]
        if cnt == 0:
            out['scale'][axis] = 1.0
        elif cnt == 1:
            out['scale'][axis] = fp.f32(sdata[off])
        else:
            out['scale'][axis] = _keyframe_interp(frame, cnt, tt, sdata, off, hermite_f32)
        # rotation (s16 BAM -> (s32) << decShift)
        cnt, off, tt = j['r'][axis]
        if cnt == 0:
            out['rotation'][axis] = 0
        elif cnt == 1:
            out['rotation'][axis] = _as_s32(rdata[off] << dec)
        else:
            v = _keyframe_interp(frame, cnt, tt, rdata, off, hermite_s16)
            out['rotation'][axis] = _as_s32(int(v) << dec)   # (s32)v truncates toward zero
        # translate
        cnt, off, tt = j['t'][axis]
        if cnt == 0:
            out['translate'][axis] = 0.0
        elif cnt == 1:
            out['translate'][axis] = fp.f32(tdata[off])
        else:
            out['translate'][axis] = _keyframe_interp(frame, cnt, tt, tdata, off, hermite_f32)
    _cache[_ck] = out
    return out


def _as_s32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


# Optional native (bit-exact) Hermite kernels (anim/_anmc.pyx); _keyframe_interp picks them up by name.
# Absent -> the Python defs above run unchanged. See fp-faithfulness.md.
try:
    from . import _anmc as _N
    hermite_s16 = _N.hermite_s16
    hermite_f32 = _N.hermite_f32
except ImportError:
    pass


_ANIM_CACHE = {}

def load_anim(path=None):
    """Parse the walk/dash BCK JSON. CACHED per path: the parsed anim is read-only truth (the only
    mutation is the pure `_ct_cache` calc_transform memoize, which is safe -- and beneficial -- to
    share across FootSpeedF instances). Re-parsing this ~300KB file on every LandState/clone was
    ~7ms each and dominated the A* land planner's clone cost."""
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        rb = here
        while rb != os.path.dirname(rb) and not os.path.exists(os.path.join(rb, 'pyproject.toml')):
            rb = os.path.dirname(rb)
        path = os.path.join(rb, '_generated', 'anim', 'link_anim_walk_dash.json')
    anm = _ANIM_CACHE.get(path)
    if anm is None:
        with open(path) as f:
            anm = _ANIM_CACHE[path] = json.load(f)
    return anm


if __name__ == '__main__':
    anm = load_anim()['walk']
    # smoke: sample the L-foot joint rotation at a few frames
    for f in (0.0, 8.0, 8.5, 16.0, 31.0):
        tr = calc_transform(anm, 34, f)   # Lfoot_jnt
        print("f=%5.1f  Lfoot R=%s T=%s" % (f, tr['rotation'], ['%.4f' % v for v in tr['translate']]))
