"""fk.py - forward kinematics for Link's cl skeleton, bit-faithful to the console, producing the
model-local foot toe position spB0 that drives the walk speedF foot term.

Chain of specs (all in tww/):
  - Per-joint TRS at frame f: j3d_eval.calc_transform (Hermite + calcTransform).
  - Local joint matrix: J3DMtxCalcMaya::calcTransform (J3DJoint.cpp:140) -- Link's cl.bdl is Maya
    (INF1 flags&0xF==2). For the WALK foot chain every joint has scale==1 (no animated scale),
    so the scale-branch and scaleCompensate 1/parentS are both no-ops (parentS stays 1) -> the
    local matrix is exactly J3DGetTranslateRotateMtx(info) (J3DTransform.cpp:166).
  - Concat down the tree: MTXConcat==PSMTXConcat (retail) -- fused accumulation, decoded from the
    paired-single asm (mtx.c:119): ab[i][j] = fmadds(a[i][2],b[2][j], fmadds(a[i][1],b[1][j],
    fmuls(a[i][0],b[0][j]))) for j<3; ab[i][3] adds +a[i][3].
  - Toe: PSMTXMultVec (mtxvec.c:21): dst = (m0.*.sx + m2.*.sz) + (m1.*.sy + m3), grouped as two
    fmadds partials joined by a ps_sum0 (fadds). l_toe_pos={6,3.25,0}, l_heel_pos={-6,3.25,0}
    (d_a_player_main_data.inc:18-19).

THE FK MUST RUN IN WORLD SPACE (identity-space FK is 1-2 ULP wrong -- superseded):
  posMoveFromFootPos (d_a_player_main.cpp:2372) does spB0 = (m37B4 * anmMtx(FOOT)) * l_toe_pos.
  anmMtx(FOOT) = worldBase * localChain(FOOT) (FK starts at setBaseTRMtx(worldBase), :9580);
  m37B4 = inverse(worldBase) (:9581-82) with only m37B4[1][3]-=m35B8 (:8796) tweaking the Y row.
  Although m37B4*worldBase cancels ALGEBRAICALLY, it does NOT cancel in f32: the FK accumulates each
  joint matrix at WORLD magnitude (translation ~= Link's pos.z, e.g. 764), so each is quantized to the
  f32 spacing there (~6e-5); m37B4 removes the base afterward but the quantization is already baked in.
  So the sim runs the chain from worldBase and applies m37B4 (fk.world_base + FootFK world mode), NOT
  from identity. For the straight walk worldBase is a pure translation (facing==0) and pos.x==0, so only
  the Z column is at world magnitude; turns add a Y rotation. With this + the PSMTXQuat 'newton'
  reciprocal the leg chain is bit-exact and the walk pos_z is float-perfect. (foot_toe_local below keeps
  the old identity-space path for reference only.) See knowledge/model/sim.md.

Reads gitignored _generated anim/skeleton data (dev-supplied).
"""
import os, sys, json

from .. import fp
from .. import mathlib as S

from . import j3d_eval
from . import quat as Q

# l_toe/l_heel in Lfoot-joint local space (mirror x for the right foot? posMoveFromFootPos uses
# the SAME l_toe_pos for both feet -- the mtx handles the side). d_a_player_main_data.inc:18-19.
L_TOE = (6.0, 3.25, 0.0)
L_HEEL = (-6.0, 3.25, 0.0)

# JMACos/JMASin on s16 BAM from SEPARATE baked console tables (see sim.py _SIN_TABLE). tr_matrix/euler
# path is unused for the foot chain but kept faithful.
def jma_cos(a):
    return S._COS_TABLE[(int(a) & 0xFFFF) >> 4]

def jma_sin(a):
    return S._SIN_TABLE[(int(a) & 0xFFFF) >> 4]


def tr_matrix(rot, trans):
    """J3DGetTranslateRotateMtx(info) -> 3x4 Mtx (list of 3 rows of 4). rot=(rx,ry,rz) s16 BAM,
    trans=(tx,ty,tz) f32. Element ops fused per MWCC FMA codegen."""
    rx, ry, rz = rot
    sx, cx = jma_sin(rx), jma_cos(rx)
    sy, cy = jma_sin(ry), jma_cos(ry)
    sz, cz = jma_sin(rz), jma_cos(rz)
    m = [[0.0]*4 for _ in range(3)]
    m[2][0] = fp.f32(-sy)
    m[0][0] = fp.fmuls(cz, cy)
    m[1][0] = fp.fmuls(sz, cy)
    m[2][1] = fp.fmuls(cy, sx)
    m[2][2] = fp.fmuls(cy, cx)
    cxsz = fp.fmuls(cx, sz)
    sxcz = fp.fmuls(sx, cz)
    m[0][1] = fp.fmsubs(sxcz, sy, cxsz)      # sxcz*sy - cxsz
    m[1][2] = fp.fmsubs(cxsz, sy, sxcz)      # cxsz*sy - sxcz
    sxsz = fp.fmuls(sx, sz)
    cxcz = fp.fmuls(cx, cz)
    m[0][2] = fp.fmadds(cxcz, sy, sxsz)      # cxcz*sy + sxsz
    m[1][1] = fp.fmadds(sxsz, sy, cxcz)      # sxsz*sy + cxcz
    m[0][3] = fp.f32(trans[0])
    m[1][3] = fp.f32(trans[1])
    m[2][3] = fp.f32(trans[2])
    return m


def psmtx_inverse(m):
    """PSMTXInverse (dolphin/mtx/mtx.c:404, retail paired-single asm): the general 3x4 cofactor/
    determinant inverse, NOT a transpose. det = first-column cofactor expansion; the reciprocal is
    `fres` (12-bit estimate) + ONE Newton refine (recip = 2*est - det*est^2), NOT an exact fdivs.
    Each cofactor and the translation are fused (ps_msub/ps_madd/ps_nmadd) in the asm's exact order.

    For a matrix built from the JMASin/JMACos tables R is NOT exactly orthonormal (c^2+s^2 != 1.0 in
    f32 at a non-axis BAM), so this differs from R^T by a few ULP -- exact only when R's entries are
    0/+-1 (axis-aligned facings). Reproducing it is required for a bit-exact foot toe during a turn
    (the WaitTurn pivot poses the foot at intermediate facings). See knowledge/history/resolved-bugs.md."""
    m00, m01, m02, m03 = m[0]
    m10, m11, m12, m13 = m[1]
    m20, m21, m22, m23 = m[2]
    # cofactors -- fmsubs(a,b, fmuls(c,d)) = a*b - round(c*d), matching ps_mul then ps_msub.
    A00 = fp.fmsubs(m11, m22, fp.fmuls(m21, m12))   # f13.ps0
    A01 = fp.fmsubs(m21, m02, fp.fmuls(m01, m22))   # f12.ps0
    A02 = fp.fmsubs(m01, m12, fp.fmuls(m11, m02))   # f11.ps0
    A20 = fp.fmsubs(m10, m21, fp.fmuls(m11, m20))   # f10.ps0
    A21 = fp.fmsubs(m01, m20, fp.fmuls(m00, m21))   # f9.ps0
    A22 = fp.fmsubs(m00, m11, fp.fmuls(m01, m10))   # f8.ps0
    B10 = fp.fmsubs(m12, m20, fp.fmuls(m22, m10))   # f13.ps1 -> inv[1][0]
    B11 = fp.fmsubs(m22, m00, fp.fmuls(m02, m20))   # f12.ps1 -> inv[1][1]
    B12 = fp.fmsubs(m02, m10, fp.fmuls(m12, m00))   # f11.ps1 -> inv[1][2]
    det = fp.fmadds(m20, A02, fp.fmadds(m10, A01, fp.fmuls(m00, A00)))
    est = fp.f32(Q._fres(det))
    recip = fp.fnmsubs(det, fp.fmuls(est, est), fp.fadds(est, est))   # 2*est - det*est^2
    inv = [[0.0] * 4 for _ in range(3)]
    inv[0][0] = fp.fmuls(A00, recip); inv[0][1] = fp.fmuls(A01, recip); inv[0][2] = fp.fmuls(A02, recip)
    inv[1][0] = fp.fmuls(B10, recip); inv[1][1] = fp.fmuls(B11, recip); inv[1][2] = fp.fmuls(B12, recip)
    inv[2][0] = fp.fmuls(A20, recip); inv[2][1] = fp.fmuls(A21, recip); inv[2][2] = fp.fmuls(A22, recip)
    # translation inv_i3 = -(inv_i0*m03 + inv_i1*m13 + inv_i2*m23), fused nmadd(madd(mul)).
    for i in range(3):
        inv[i][3] = fp.fnmadds(inv[i][2], m23, fp.fmadds(inv[i][1], m13, fp.fmuls(inv[i][0], m03)))
    return inv


def world_base(px, py, pz, facing=0, lean=0):
    """Build (worldBase, m37B4) for the CL model's setBaseTRMtx (d_a_player_main.cpp:9559-9575).
    worldBase = transS(px,py,pz) . ZXYrotM(0, facing, 0)  (flat ground: shape_angle.x/z == 0), and
    m37B4 = PSMTXInverse(worldBase). For the FOOT toe f31_2 only rows 0 and 2 (X,Z) matter, so the
    Y translation (py + the m35B8 tweak) is immaterial; pass py=0.

    WHY this exists: the game runs the foot FK from worldBase, so every accumulated joint matrix
    carries a WORLD-magnitude translation (~pz, e.g. 764) and is quantized to the f32 spacing there
    (~6e-5). m37B4 removes the base afterward, but the quantization is already baked into the toe.
    FK-from-identity (foot_toe_local) misses this. facing == 0 => worldBase is a pure translation and
    only the Z column is at world magnitude (px stays 0 for the straight walk). m37B4 must be the exact
    PSMTXInverse (cofactor/fres), not R^T -- they diverge at a non-axis facing (the WaitTurn pivot)."""
    facing = int(facing) & 0xFFFF
    c = jma_cos(facing); s = jma_sin(facing)
    ns = fp.f32(-s)
    # ZXYrotM with only the Y angle: column-vector Y rotation R = [[c,0,s],[0,1,0],[-s,0,c]].
    R = [[c, 0.0, s], [0.0, 1.0, 0.0], [ns, 0.0, c]]
    T = (fp.f32(px), fp.f32(py), fp.f32(pz))
    base = [[R[i][0], R[i][1], R[i][2], T[i]] for i in range(3)]
    lean = int(lean) & 0xFFFF
    if lean:
        # shape_angle.z != 0 (the MOVE turn lean, m351C >> 1): mDoMtx_ZXYrotM concats ZrotS onto
        # the Y-rotated base -- skipped entirely when z == 0, so the lean-free path is untouched.
        cz = jma_cos(lean); sz = jma_sin(lean)
        Rz = [[cz, fp.f32(-sz), 0.0, 0.0], [sz, cz, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
        base = mtx_concat(base, Rz)
    return base, psmtx_inverse(base)


def mtx_concat(a, b):
    """PSMTXConcat: ab = a * b (3x4 affine). Fused accumulation, order [0]->+[1]->+[2](->+trans)."""
    ab = [[0.0]*4 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            ab[i][j] = fp.fmadds(a[i][2], b[2][j], fp.fmadds(a[i][1], b[1][j], fp.fmuls(a[i][0], b[0][j])))
        ab[i][3] = fp.fadds(
            fp.fmadds(a[i][2], b[2][3], fp.fmadds(a[i][1], b[1][3], fp.fmuls(a[i][0], b[0][3]))),
            a[i][3])
    return ab


def mtx_mult_vec(m, v):
    """PSMTXMultVec: dst = (m0.col0*sx + m0.col2*sz) + (m0.col1*sy + m0.col3), per-row, with the
    ps_sum0 grouping (two fmadds partials joined by fadds)."""
    sx, sy, sz = v
    out = [0.0, 0.0, 0.0]
    for i in range(3):
        pa = fp.fmadds(m[i][2], sz, fp.fmuls(m[i][0], sx))   # m_i0*sx + m_i2*sz
        pb = fp.fadds(fp.fmuls(m[i][1], sy), m[i][3])        # m_i1*sy + m_i3
        out[i] = fp.fadds(pa, pb)
    return tuple(out)


# --- quaternion local-matrix path: the CL foot chain uses mDoExt_MtxCalcAnmBlendTblOld::calc ----
# euler->quat (both anims) -> QuatLerp blend -> mDoMtx_quat; translate = blended mTranslate (scale 1).
def local_mtx_quat_single(rot, trans):
    """Single-anim local matrix via the quat path (no blend)."""
    m = Q.mtx_quat(Q.euler_to_quat(*rot))
    m[0][3] = fp.f32(trans[0]); m[1][3] = fp.f32(trans[1]); m[2][3] = fp.f32(trans[2])
    return m

def local_mtx_quat_blend(info0, info1, ratio):
    """Two-anim local matrix: info0=dash(MOVE0), info1=walk(MOVE1), blend toward walk by ratio.
    Rotation via QuatLerp(q_dash,q_walk,ratio); translation linear a*(1-r)+b*r (fmadds)."""
    q0 = Q.euler_to_quat(*info0['rotation'])
    q1 = Q.euler_to_quat(*info1['rotation'])
    q3 = Q.quat_lerp(q0, q1, ratio)
    f30 = fp.fsubs(1.0, ratio)
    m = Q.mtx_quat(q3)
    for k in range(3):
        m[k][3] = fp.fmadds(info1['translate'][k], ratio, fp.fmuls(info0['translate'][k], f30))
    return m


def foot_toe_quat(anm, skeleton, frame, foot_jnt=34, toe=L_TOE):
    """Model-local toe via the QUAT path, single anim at `frame` (the correct path for the foot
    chain; use this, not foot_toe_local, once validated)."""
    chain = build_foot_chains(skeleton)[foot_jnt]
    cur = None
    for jidx in chain:
        tr = j3d_eval.calc_transform(anm, jidx, frame)
        local = local_mtx_quat_single(tr['rotation'], tr['translate'])
        cur = local if cur is None else mtx_concat(cur, local)
    return mtx_mult_vec(cur, toe)


def foot_toe_blend(anm_dash, anm_walk, skeleton, f_dash, f_walk, ratio, foot_jnt=34, toe=L_TOE):
    """Model-local toe of the BLENDED (dash+walk) pose -- the game's actual foot pose.
    f_dash/f_walk = the two frame-controller frames; ratio = getRatio(1) (walk weight)."""
    chain = build_foot_chains(skeleton)[foot_jnt]
    cur = None
    for jidx in chain:
        i0 = j3d_eval.calc_transform(anm_dash, jidx, f_dash)
        i1 = j3d_eval.calc_transform(anm_walk, jidx, f_walk)
        local = local_mtx_quat_blend(i0, i1, ratio)
        cur = local if cur is None else mtx_concat(cur, local)
    return mtx_mult_vec(cur, toe)


def build_foot_chains(skeleton):
    """Return {joint_idx: [ancestor..., joint_idx]} FK paths for LFOOT(34) and RFOOT(39)."""
    parent = {j['index']: j['parent'] for j in skeleton['joints']}
    def path(idx):
        p = []
        while idx != -1:
            p.append(idx)
            idx = parent[idx]
        return list(reversed(p))
    return {34: path(34), 39: path(39)}


def foot_toe_local(anm, skeleton, frame, foot_jnt=34, toe=L_TOE):
    """Model-local toe position of foot_jnt at `frame`, FK from identity through its chain."""
    chains = build_foot_chains(skeleton)
    chain = chains[foot_jnt]
    cur = None   # mCurrentMtx; starts as identity -> first joint's local mtx
    for jidx in chain:
        tr = j3d_eval.calc_transform(anm, jidx, frame)
        local = tr_matrix(tr['rotation'], tr['translate'])
        # NOTE: assumes scale==1 (Maya scale-branch/scaleCompensate no-op) for the foot chain.
        cur = local if cur is None else mtx_concat(cur, local)
    return mtx_mult_vec(cur, toe)


# Optional native (bit-exact) 3x4 matrix concat / mult-vec (anim/_anmc.pyx); mtx_concat is the single
# hottest walk-path function. Absent -> the Python defs above run unchanged. See fp-faithfulness.md.
try:
    from . import _anmc as _N
    _N.init_tables(S._COS_TABLE, S._SIN_TABLE)
    mtx_concat = _N.mtx_concat
    mtx_mult_vec = _N.mtx_mult_vec
    _world_base_py = world_base

    def world_base(px, py, pz, facing=0, lean=0):
        # Native fast path (no lean arg); the Python def carries the shape_angle.z lean concat.
        if lean:
            return _world_base_py(px, py, pz, facing, lean)
        return _N.world_base(px, py, pz, facing)
except ImportError:
    pass


_LOAD_CACHE = None

def load():
    """(anim, skeleton), CACHED. Both are read-only parsed data shared across every FootSpeedF /
    FootFK instance (and thus every A* clone) -- see load_anim. Eliminates the ~7ms/clone JSON
    re-parse that dominated the land planner. Call j3d_eval._ANIM_CACHE.clear() / reset here only if
    the dev-supplied data on disk changes mid-process (it never does in a run)."""
    global _LOAD_CACHE
    if _LOAD_CACHE is None:
        anm = j3d_eval.load_anim()
        here = os.path.dirname(os.path.abspath(__file__))
        rb = here
        while rb != os.path.dirname(rb) and not os.path.exists(os.path.join(rb, 'pyproject.toml')):
            rb = os.path.dirname(rb)
        with open(os.path.join(rb, '_generated', 'anim', 'link_skeleton.json')) as f:
            sk = json.load(f)
        _LOAD_CACHE = (anm, sk)
    return _LOAD_CACHE


if __name__ == '__main__':
    anm_all, sk = load()
    anm = anm_all['walk']
    print("model-local Lfoot/Rfoot toe over walk frames (FK from identity):")
    for f in (0.0, 4.0, 8.0, 8.5, 16.0, 24.0, 31.0):
        lt = foot_toe_local(anm, sk, f, 34, L_TOE)
        rt = foot_toe_local(anm, sk, f, 39, L_TOE)
        print("  f=%5.1f  Ltoe=(%.4f, %.4f, %.4f)  Rtoe=(%.4f, %.4f, %.4f)" % (f, *lt, *rt))
