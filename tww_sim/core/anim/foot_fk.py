"""foot_fk.py - STATEFUL foot forward-kinematics driver with the oldframe-morf blend.

fk.foot_toe_blend poses one frame in isolation. But at a walk-proc ENTRY the game morphs the new
pose toward the PREVIOUS frame's stored pose over a couple of frames (mDoExt_MtxCalcOldFrame, the
oldframe-morf), so the transient foot toe is only bit-exact if we carry per-joint old pose + the morf
counter across frames. This driver does that: feed it the per-frame anim-blend state
(from anim_state.UnderAnimState.step) and it returns the model-local toe for both feet, applying morf.

Timeline of the morf rate the FOOT joints (34/39, before the last joint 41) see, verified vs live:
  trigger frame: initOldFrameMorf(2.4) does dec#1 -> rate 0.583 (foot uses this); the per-frame
  last-joint dec then -> 0.286. next frame: foot uses 0.286; last-joint dec -> 0. So exactly 2 foot
  draw frames are morphed. Per joint (m_Do_ext.cpp:1195): quat3 = JMAQuatLerp(oldQuat, blendedQuat,
  1-rate); trans = blendedTrans*(1-rate) + oldTrans*rate; then oldQuat/oldTrans <- the posed result.

Seed the old pose with the FREEB (rest) pose at the entry frame before the first walk step, matching
the game (which stores old every frame, standing included).
Reads gitignored _generated anim/skeleton data (dev-supplied).
"""
from .. import fp
from .. import mathlib as S
from . import j3d_eval
from . import quat as Q
from . import fk

# Optional native anim accelerator (anim/_anmc.pyx): a C-resident PoseEngine does the whole per-frame
# pose+chain+toe in one call on the world-space FK path; else pure-Python. See fp-faithfulness.md.
try:
    from . import _anmc as _N
    _N.init_tables(S._COS_TABLE, S._SIN_TABLE)
    # The Courtyard native step needs the table atan2 (cone gate / re-aim) + the CC-push rank table.
    if hasattr(_N, 'init_atan_table'):
        from ..cc_push import RANK_TBL as _RANK_TBL
        _N.init_atan_table(S._ATN_TABLE)
        _N.init_rank_table(_RANK_TBL)
except ImportError:
    _N = None

# Cache the immutable native AnimData (registered keyframe data + chains) per parsed anim set, so every
# clone shares it instead of re-copying ~90k keyframe values into C. See fp-faithfulness.md.
_ANIMDATA_CACHE = {}


def _shared_anim_data(anms, chains):
    key = id(anms)
    hit = _ANIMDATA_CACHE.get(key)
    if hit is not None:
        return hit[0], hit[1]
    data = _N.AnimData()
    anim_idx = {}
    for i, (name, a) in enumerate(anms.items()):
        data.add_anim(i, a); anim_idx[name] = i
    data.set_chains(chains[34], chains[39])
    _ANIMDATA_CACHE[key] = (data, anim_idx, anms)   # keep anms alive so id(anms) can't be reused
    return data, anim_idx

# union of both foot chains, in joint-index (calc) order; each processed once per frame.
CHAIN_JOINTS = [0, 1, 29, 30, 31, 32, 33, 34, 36, 37, 38, 39]
MORF_START, MORF_END = 0, 0x2A          # initOldFrameMorf(2.4, 0, 0x2A) joint range
# body-Co mode (setCollision root/neck midpoint): the neck-chain joints past the foot set plus the
# head (15, mHeadTopPos); all < MORF_END, so the oldframe-morf covers them like the feet.
BODY_CO_EXTRA = [2, 3, 4, 14, 15]
NECK_CHAIN = [0, 1, 2, 3, 4, 14]
HEAD_CHAIN = [0, 1, 2, 3, 4, 14, 15]
HEAD_TOP_OFF = (40.0, 0.0, 0.0)     # head_offset (d_a_player_main.cpp:11589)
# J3D segment-scale-compensation joints on the neck chain (scale_compensate=1): mDoExt_setJ3DData
# (m_Do_ext.cpp:47) row-scales their local 3x3 by 1/parentS. KB: mechanics/link-co-centre.md.
BODY_CO_SSC = (3, 4, 14)


class MorfState:
    """mDoExt_MtxCalcOldFrame morf counter (m_Do_ext.cpp:1226,1246). rate is what joints read."""
    __slots__ = ('counter', 'f8', 'rate', 'f10', 'f14')

    def __init__(self):
        self.counter = self.f8 = self.rate = self.f10 = self.f14 = 0.0

    def clone(self):
        """Memberwise copy (mid-walk clone support). See land.LandState.clone."""
        c = MorfState()
        c.counter = self.counter; c.f8 = self.f8; c.rate = self.rate
        c.f10 = self.f10; c.f14 = self.f14
        return c

    def init_morf(self, i_morf):
        # mOldFrameMorfCounter/i_morf are f32 in-game; f64 2.4 rounds the morf rate 1 ULP low ->
        # jnt0.z entry-morf +5 ULP. Quantize to f32. See knowledge/history/resolved-bugs.md.
        i_morf = fp.f32(i_morf)
        if i_morf > 0.0:
            self.counter = i_morf
            self.f8 = fp.fdivs(1.0, i_morf)
            self.rate = 1.0
            self.f10 = 1.0
            self.f14 = 1.0
            self.dec()
        else:
            self.counter = self.f8 = self.rate = self.f10 = self.f14 = 0.0

    def dec(self):
        if not (self.counter > 0.0):
            return
        self.counter = fp.fsubs(self.counter, 1.0)
        if self.counter <= 0.0:
            self.counter = 0.0; self.f8 = 0.0; self.rate = 0.0
        self.f14 = self.f10
        self.f10 = fp.fmuls(self.counter, self.f8)
        if self.f14 > 0.0:
            self.rate = fp.fsubs(1.0, fp.fdivs(fp.fsubs(self.f14, self.f10), self.f14))
        else:
            self.rate = 0.0


class FootFK:
    """Stateful driver. `anms` = {name: parsed bck}, `sk` = skeleton. Carries per-joint old pose."""

    def __init__(self, anms, sk, world=True):
        self.anms = anms
        self.sk = sk
        self.parent = {j['index']: j['parent'] for j in sk['joints']}
        # Static root->foot FK chains (jnt 39 = right, 34 = left), accumulated once per foot per frame
        # and shared by that foot's toe AND heel vectors (see _chain_mtx).
        self._chains = {}
        for fj in (34, 39):
            ch = []
            j = fj
            while j != -1:
                ch.append(j); j = self.parent[j]
            ch.reverse()
            self._chains[fj] = ch
        self.morf = MorfState()
        self.old_quat = {}          # jnt -> (w,x,y,z) posed quat last frame
        self.old_trans = {}         # jnt -> (x,y,z) posed translate last frame
        self.old_scale = {}         # jnt -> (x,y,z) posed scale last frame (morf blends it too)
        # World-space FK (the game's real path): FK from worldBase (world-magnitude quantization) then
        # remove the base with m37B4. world=False = legacy identity FK. See knowledge/model/sim.md.
        self.world = world
        self.quatfn = Q.psmtx_quat if world else Q.mtx_quat   # foot chain uses PSMTXQuat (=mDoMtx_quat)
        # C-resident pose engine (world path only): registers the anims + chains once; owns old-pose +
        # morf state internally, so seed()/step_feet() become a single native call. Bit-exact fallback.
        self._engine = None
        # `_pose_engine` = the pose_chain PoseEngine handle (shared AnimData sampler); stays live even
        # when FootSpeedF nulls `_engine` for the Python foot STATE path (pose_chain reads AnimData only).
        self._pose_engine = None
        if _N is not None and world and len(anms) <= 20:
            data, self._anim_idx = _shared_anim_data(anms, self._chains)
            # AnimData (keyframe data) is shared + cached across instances; only the per-instance
            # mutable engine (old pose / morf / worldBase) is built here -> clone() stays cheap.
            self._engine = _N.PoseEngine(data)
            self._pose_engine = self._engine
        self.base = None            # worldBase 3x4 (set each frame by set_pos)
        self.m37b4 = None           # PSMTXInverse(worldBase)
        # Phase G: record the WAIST (30) world translate per drawn pose (footBgCheck's r31
        # consumes LAST frame's value). Off by default -- zero cost on the flat paths.
        self.track_waist = False
        # Phase G: mFootData[i].field_0x030, the CLOTCH leg lift consumed at jnt 36 (i=0)
        # / 31 (i=1) (jointBeforeCB :276/:282). None = off (flat paths).
        self.foot030 = None
        self.last_waist = None
        # body-Co mode: also pose the neck-chain extras each frame for body_co_center (the
        # setCollision midpoint). Off by default -- the pose loop is byte-identical without it.
        self.body_co = False
        # (slot, jnt) pose order for the native pose_chain fold; slots align with AnimData's _CJALL
        # (foot chain 0-11 then BODY_CO_EXTRA 12-16). Built once (immutable list, shared by clones).
        self._body_co_slots = list(enumerate(CHAIN_JOINTS + BODY_CO_EXTRA))

    def clone(self):
        """State-copy clone (mid-walk-safe): shares the immutable anims/skeleton/chains (+ the shared
        AnimData inside the engine) and deep-copies the mutable pose state -- the fused C PoseEngine
        (via clone_state) OR, in the pure-Python fallback, the oldframe-morf + old-pose dicts. The
        worldBase (base/m37b4) is reset by set_pos before every pose, so its reference is shared, not
        copied. See land.LandState.clone."""
        c = FootFK.__new__(FootFK)
        c.anms = self.anms; c.sk = self.sk
        c.parent = self.parent; c._chains = self._chains
        c.world = self.world; c.quatfn = self.quatfn
        if self._engine is not None:
            c._engine = self._engine.clone_state()   # shares immutable AnimData, copies mutable state
            c._pose_engine = c._engine
            c._anim_idx = self._anim_idx
        else:
            c._engine = None
            # pose_chain uses no per-instance engine state (reads immutable AnimData only) -> share.
            c._pose_engine = self._pose_engine
            c._anim_idx = getattr(self, '_anim_idx', None)
        c.morf = self.morf.clone()
        c.old_quat = dict(self.old_quat)             # jnt -> immutable (w,x,y,z): shallow dict copy
        c.old_trans = dict(self.old_trans)
        c.old_scale = dict(self.old_scale)
        c.base = self.base                           # replaced (not mutated) each set_pos -> share ok
        c.m37b4 = self.m37b4
        c.track_waist = self.track_waist
        c.last_waist = self.last_waist
        c.foot030 = self.foot030                     # immutable tuple (or None): assign ok
        c.body_co = self.body_co
        c._body_co_slots = self._body_co_slots        # immutable list: share
        return c

    def set_pos(self, px, pz, py=0.0, facing=0, lean=0, m35b8=0.0):
        """Set Link's world pose for the frame about to be posed. X, Z, facing AND Y all matter:
        the base is removed by the f32 inverse m37B4, and the cancellation rounding is magnitude-
        dependent in every axis (a y=-6534 floor perturbs pose Y coords by ULPs vs py=0 -- found
        live on kaze r11, 2026-07-10). Pass Link's real world Y. `lean` = shape_angle.z (the MOVE
        turn lean m351C>>1, setMoveSlantAngle) -- Python path only. No-op when world FK is
        disabled. With the engine, worldBase + m37B4 are built + kept in C (no per-frame Python
        list round-trip). `m35b8` = footBgCheck's ground foot-lift (Phase G, d_a_player_main.cpp
        :8794-8796): applied the game's way -- base[1][3] += m35B8 and m37B4[1][3] -= m35B8 on
        the ALREADY-BUILT matrices (never re-derived) -- Python path only; 0.0 skips (byte-
        identical flat)."""
        if self._engine is not None:
            if m35b8:
                raise NotImplementedError("m35B8 needs the pure-Python foot path (native=False)")
            self._engine.set_pos(px, py, pz, facing, int(lean) & 0xFFFF)
        elif self.world:
            self.base, self.m37b4 = fk.world_base(px, py, pz, facing, lean)
            if m35b8:
                self.base = [row[:] for row in self.base]
                self.m37b4 = [row[:] for row in self.m37b4]
                self.base[1][3] = fp.fadds(self.base[1][3], m35b8)
                self.m37b4[1][3] = fp.fsubs(self.m37b4[1][3], m35b8)

    def _blend_joint(self, move0, move1, f0, f1, ratio, jnt, rate):
        """Blended (quat, trans, scale) for one joint, then oldframe-morf toward the stored old pose.
        Scale is blended linearly like translate; almost every foot-chain joint is identity-scale (so
        this is a no-op vs the old R-only path), but ANM_SLIP scales jnt37.x by 1.2 -> it moves the
        right-foot toe, so scale must be carried into the matrix (see _pose_frame)."""
        i0 = j3d_eval.calc_transform(self.anms[move0], jnt, f0)
        i1 = j3d_eval.calc_transform(self.anms[move1], jnt, f1)
        q0 = Q.euler_to_quat(*i0['rotation'])
        q1 = Q.euler_to_quat(*i1['rotation'])
        q3 = Q.quat_lerp(q0, q1, ratio)
        r30 = fp.fsubs(1.0, ratio)
        # translate/scale blend is NON-fused (m_Do_ext.cpp:1183, like JMAEulerToQuat) -- both products
        # separately f32-rounded then added; a fused fmadds is 1 ULP off on blend frames. See sim.md.
        trans = tuple(fp.fadds(fp.fmuls(i0['translate'][k], r30), fp.fmuls(i1['translate'][k], ratio))
                      for k in range(3))
        scale = tuple(fp.fadds(fp.fmuls(i0['scale'][k], r30), fp.fmuls(i1['scale'][k], ratio))
                      for k in range(3))
        if rate > 0.0 and MORF_START <= jnt < MORF_END and jnt in self.old_quat:
            f31 = fp.fsubs(1.0, rate)
            q3 = Q.quat_lerp(self.old_quat[jnt], q3, f31)
            ot = self.old_trans[jnt]
            trans = tuple(fp.fadds(fp.fmuls(trans[k], f31), fp.fmuls(ot[k], rate)) for k in range(3))
            os_ = self.old_scale[jnt]
            scale = tuple(fp.fadds(fp.fmuls(scale[k], f31), fp.fmuls(os_[k], rate)) for k in range(3))
        self.old_quat[jnt] = q3
        self.old_trans[jnt] = trans
        self.old_scale[jnt] = scale
        return q3, trans, scale

    def _pose_frame(self, move0, move1, f0, f1, ratio, rate, _force_slow=False):
        """Pose all chain joints once, return {jnt: local 3x4 matrix}. In body_co mode this is one
        native pose_chain call (C sampling + blend + old-pose update); `_force_slow` keeps the
        per-joint blend_joint reference path (the differential-gate oracle)."""
        local = {}
        joints = CHAIN_JOINTS + BODY_CO_EXTRA if self.body_co else CHAIN_JOINTS
        if (self.body_co and self._pose_engine is not None and self.world and not _force_slow):
            # Fused body_co pose: the whole 17-joint sample+blend+store loop in one C call.
            f30 = self.foot030
            return self._pose_engine.pose_chain(
                self._anim_idx[move0], self._anim_idx[move1], f0, f1, ratio, rate,
                self._body_co_slots, self.old_quat, self.old_trans, self.old_scale,
                float(f30[0]) if f30 else 0.0, float(f30[1]) if f30 else 0.0)
        if _N is not None and self.world:
            # Fused native path: one C call per joint does the whole blend + PSMTXQuat + scale/trans,
            # returning the local matrix and the (quat, trans, scale) to store as the new old pose.
            anm0 = self.anms[move0]; anm1 = self.anms[move1]
            ct = j3d_eval.calc_transform
            oq = self.old_quat; ot = self.old_trans; os_ = self.old_scale
            morf_on = rate > 0.0
            for jnt in joints:
                i0 = ct(anm0, jnt, f0)
                i1 = ct(anm1, jnt, f1)
                apply_morf = morf_on and MORF_START <= jnt < MORF_END and jnt in oq
                m, q3, trans, scale = _N.blend_joint(
                    i0, i1, ratio, rate, apply_morf,
                    oq.get(jnt), ot.get(jnt), os_.get(jnt))
                oq[jnt] = q3; ot[jnt] = trans; os_[jnt] = scale
                local[jnt] = m
            self._apply_foot030(local)
            return local
        for jnt in joints:
            q3, trans, scale = self._blend_joint(move0, move1, f0, f1, ratio, jnt, rate)
            m = self.quatfn(q3)                      # 3x3 rotation, trans column 0 (PSMTXQuat in world mode)
            for i in range(3):                       # M = R * diag(scale): scale column j by scale[j]
                m[i][0] = fp.fmuls(m[i][0], scale[0])
                m[i][1] = fp.fmuls(m[i][1], scale[1])
                m[i][2] = fp.fmuls(m[i][2], scale[2])
            m[0][3] = fp.f32(trans[0]); m[1][3] = fp.f32(trans[1]); m[2][3] = fp.f32(trans[2])
            local[jnt] = m
        self._apply_foot030(local)
        return local

    def _apply_foot030(self, local):
        """jointBeforeCB's per-leg CLOTCH lift (d_a_player_main.cpp:276/:282): the local
        translate.x -= mFootData[i].field_0x030, applied to the built joint matrix (rotation and
        scale never touch column 3, so the post-adjust is bit-identical to the game's pre-build
        TransformInfo edit). The stored old pose (morf source) keeps the UN-adjusted translate --
        the game saves the original into m3668 and the anim history never sees the callback."""
        f30 = self.foot030
        if f30 is None:
            return
        if f30[0]:
            local[36][0][3] = fp.fsubs(local[36][0][3], f30[0])   # RCLOTCH <- mFootData[0]
        if f30[1]:
            local[31][0][3] = fp.fsubs(local[31][0][3], f30[1])   # LCLOTCH <- mFootData[1]

    def _chain_mtx(self, local, foot_jnt):
        """The accumulated FK matrix for one foot's chain (shared by that foot's toe AND heel).
        World mode: m37B4 * (worldBase * localChain(FOOT)); identity mode: localChain only."""
        chain = self._chains[foot_jnt]
        if self.world and self.base is not None:
            # World-space FK: start at worldBase, accumulate local chain (world-magnitude quantization),
            # then anmMtx-to-model via m37B4 (posMoveFromFootPos: spB0 = m37B4 * anmMtx(FOOT) * toe).
            if _N is not None:
                return _N.chain_concat(self.base, self.m37b4, [local[j] for j in chain])
            cur = [row[:] for row in self.base]
            for jnt in chain:
                cur = fk.mtx_concat(cur, local[jnt])
            return fk.mtx_concat(self.m37b4, cur)
        cur = None
        for jnt in chain:
            cur = local[jnt] if cur is None else fk.mtx_concat(cur, local[jnt])
        return cur

    def _toe(self, local, foot_jnt, toe):
        return fk.mtx_mult_vec(self._chain_mtx(local, foot_jnt), toe)

    def waist_from_old(self):
        """Rebuild the WAIST world translate from the stored old pose (the per-joint quat/trans/
        scale of the LAST posed frame) -- the cold-start seed when track_waist was enabled after
        the constructor's rest pose. A minted (translated) anchor should seed the captured RAM
        value instead (the stored pose carries the pre-mint position's rounding noise)."""
        local = {}
        for jnt in self._chains[34]:
            m = self.quatfn(self.old_quat[jnt])
            s = self.old_scale[jnt]
            t = self.old_trans[jnt]
            for i in range(3):
                m[i][0] = fp.fmuls(m[i][0], s[0])
                m[i][1] = fp.fmuls(m[i][1], s[1])
                m[i][2] = fp.fmuls(m[i][2], s[2])
            m[0][3] = fp.f32(t[0]); m[1][3] = fp.f32(t[1]); m[2][3] = fp.f32(t[2])
            local[jnt] = m
            if jnt == 30:
                break
        return self._waist_world(local)

    @staticmethod
    def _quat_concat(a, b):
        """mDoMtx_QuatConcat(a, b) -- the quaternion product the jointBeforeCB adjust uses.
        Canonical in `quat.quat_concat` (`body_cyl`'s baked chain runs the same twist)."""
        return Q.quat_concat(a, b)

    @staticmethod
    def _sx(v):
        v = int(v) & 0xFFFF
        return v - 0x10000 if v >= 0x8000 else v

    def _local_from_old(self, jnt, body_x=0, cb_xyz=None):
        """Rebuild one joint's local 3x4 matrix from the STORED old pose (the quat/trans/scale of
        the LAST posed frame) -- the same reconstruction waist_from_old uses, factored per joint.
        ``body_x`` (s16) = jointBeforeCB's body_chn extra rotation x term (-mBodyAngle.z; the y/x
        attention twists are separate and 0 in the courtyard window) -- the callback post-multiplies
        the animated quat (d_a_player_main.cpp:350-357) and the stored old pose keeps the UN-adjusted
        quat (m3658), so the adjust is applied here at rebuild time, only at CL_JNT_BODY_CHN.
        ``cb_xyz`` = a full ``local_38`` (x, y, z) callback adjust (the HEAD joint's
        ``(m3564.y, m3564.z, m3564.x)`` twist, :270): the decomp applies it as TWO quat concats --
        ``Q(x, y, 0)`` then ``Q(0, 0, z)`` -- each skipped when its components are 0 (:353-362)."""
        q = self.old_quat[jnt]
        if body_x:
            # JMAEulerToQuat halves the angle as a SIGNED s16; an unsigned-masked -1 mis-rounds
            # to a ~-32-BAM ghost twist where the game gets identity (session 16).
            q = self._quat_concat(q, Q.euler_to_quat(self._sx(body_x), 0, 0))
        if cb_xyz is not None:
            lx, ly, lz = (self._sx(v) for v in cb_xyz)
            if lx or ly:
                q = self._quat_concat(q, Q.euler_to_quat(lx, ly, 0))
            if lz:
                q = self._quat_concat(q, Q.euler_to_quat(0, 0, lz))
        m = self.quatfn(q)
        s = self.old_scale[jnt]
        t = self.old_trans[jnt]
        for i in range(3):
            m[i][0] = fp.fmuls(m[i][0], s[0])
            m[i][1] = fp.fmuls(m[i][1], s[1])
            m[i][2] = fp.fmuls(m[i][2], s[2])
        m[0][3] = fp.f32(t[0]); m[1][3] = fp.f32(t[1]); m[2][3] = fp.f32(t[2])
        return m

    def body_co_center(self, px, py, pz, facing, lean=0, body_lean=None, _force_py=False):
        """Link's body **Co** cylinder centre (x, z) for the pose LAST posed (drawn) by this driver --
        ``daPy_lk_c::setCollision``'s root/neck world midpoint (d_a_player_main.cpp:9748-9754), the
        centre ``cM3d_Cross_CylCyl`` pushes other actors from. The generalization of
        ``body_cyl.roll_co_center`` to EVERY pose this driver produces (walk/dash blends, ATN strafes,
        rolls INCLUDING the entry oldframe-morf): the stored old pose (position-independent local
        quat/trans/scale) is re-accumulated from ``worldBase(px, py, pz, facing, lean)`` WITHOUT the
        ``m37B4`` removal -- ``getAnmMtx(joint)`` column 3 is world.

        Call it AFTER the frame's pose with the frame's SETTLED (post-integration) position, facing,
        and the draw-time lean (``LandState._draw_lean``) -- the setCollision timing the coupled
        stepper is gated on. Requires ``body_co`` mode (the neck-chain extras must have been posed);
        Python world path only.

        ``body_lean`` = the lean the BODY_CHN counter-twist uses -- this frame's POST-update
        ``shape_angle.z`` (``m351C >> 1``), NOT the draw lean. In the execute pass, ``setWorldMatrix``
        (:11551, the base -- OLD lean) runs BEFORE ``setMoveSlantAngle`` (:11561, updates ``m351C``
        and sets ``mBodyAngle.z = shape_angle.z``), and ``mpCLModel->calc()`` (:11591, where
        ``jointBeforeCB`` reads ``mBodyAngle.z``) runs after BOTH -- so the twist is one lean-update
        ahead of the base (session-16 chain probe: anim x Rx(-new_lean) reproduces the live joint-2
        matrix to 0.000000 on every probed frame; the old-lean twist erred only where the two leans
        cross a sin-table quantization bucket, which is why the gap toggled per frame). Defaults to
        ``lean`` (the old behavior) for callers without a post-update value."""
        if not (self.body_co and self.world):
            raise RuntimeError("body_co_center needs body_co=True on the Python world FK path")
        lv = int(lean if body_lean is None else body_lean) & 0xFFFF
        body_x = -(lv - 0x10000 if lv >= 0x8000 else lv)   # -mBodyAngle.z; .z==shape_angle.z (:9526)
        if _N is not None and self.world and not _force_py:
            # Native one-call fold of the Python loop below (gated bit-exact by test_from_f0.py +
            # tests/test_body_co_native.py); marshal the stored old pose in chain order.
            oq = self.old_quat; ot = self.old_trans; os_ = self.old_scale
            return _N.co_center(fp.f32(px), fp.f32(py), fp.f32(pz), int(facing) & 0xFFFF,
                                int(lean) & 0xFFFF, body_x,
                                [oq[j] for j in NECK_CHAIN], [ot[j] for j in NECK_CHAIN],
                                [os_[j] for j in NECK_CHAIN])
        base, _ = fk.world_base(fp.f32(px), fp.f32(py), fp.f32(pz), int(facing) & 0xFFFF,
                                int(lean) & 0xFFFF)
        cur = base
        root_t = None
        for jnt in NECK_CHAIN:
            m = self._local_from_old(jnt, body_x=body_x if jnt == 2 else 0)
            if jnt in BODY_CO_SSC:
                # SSC: row r of the local 3x3 scaled by 1/parentS[r] (the parent's post-morf local
                # scale this frame = the old-scale store; mDoExt_setJ3DData:47).
                ps = self.old_scale.get(self.parent[jnt])
                if ps is not None and (ps[0] != 1.0 or ps[1] != 1.0 or ps[2] != 1.0):
                    for r in range(3):
                        inv = fp.fdivs(1.0, ps[r])
                        m[r][0] = fp.fmuls(m[r][0], inv)
                        m[r][1] = fp.fmuls(m[r][1], inv)
                        m[r][2] = fp.fmuls(m[r][2], inv)
            cur = fk.mtx_concat(cur, m)
            if jnt == 0:
                root_t = (cur[0][3], cur[2][3])
        cx = fp.fmuls(0.5, fp.fadds(root_t[0], cur[0][3]))
        cz = fp.fmuls(0.5, fp.fadds(root_t[1], cur[2][3]))
        return cx, cz

    def head_mtx(self, px, py, pz, facing, lean=0, body_lean=None, neck=None):
        """The WORLD head anm matrix (``getAnmMtx(CL_JNT_HEAD_JNT_e)``, 3x4) for the pose LAST
        posed by this driver -- the exec-pass matrix :meth:`head_top` multiplies and the one the
        NEXT frame's ``setNeckAngle`` (:11571, before that frame's calc) measures its current head
        angles from. Same base/lean conventions as :meth:`body_co_center`. ``neck`` = the head
        jointBeforeCB ``local_38`` twist ``(m3564.y, m3564.z, m3564.x)`` (d_a_player_main.cpp:270;
        `land.neck_look.NeckLook.local_38`); None/zeros = untwisted (the pre-model behavior)."""
        if not (self.body_co and self.world):
            raise RuntimeError("head_mtx needs body_co=True on the Python world FK path")
        base, _ = fk.world_base(fp.f32(px), fp.f32(py), fp.f32(pz), int(facing) & 0xFFFF,
                                int(lean) & 0xFFFF)
        lv = int(lean if body_lean is None else body_lean) & 0xFFFF
        body_x = -(lv - 0x10000 if lv >= 0x8000 else lv)
        cur = base
        for jnt in HEAD_CHAIN:
            m = self._local_from_old(jnt, body_x=body_x if jnt == 2 else 0,
                                     cb_xyz=neck if jnt == 15 else None)
            if jnt in BODY_CO_SSC:
                ps = self.old_scale.get(self.parent[jnt])
                if ps is not None and (ps[0] != 1.0 or ps[1] != 1.0 or ps[2] != 1.0):
                    for r in range(3):
                        inv = fp.fdivs(1.0, ps[r])
                        m[r][0] = fp.fmuls(m[r][0], inv)
                        m[r][1] = fp.fmuls(m[r][1], inv)
                        m[r][2] = fp.fmuls(m[r][2], inv)
            cur = fk.mtx_concat(cur, m)
        return cur

    def head_top(self, px, py, pz, facing, lean=0, body_lean=None, neck=None):
        """Link's ``mHeadTopPos`` for the pose LAST posed by this driver -- ``cMtx_multVec(
        anmMtx(CL_JNT_HEAD_JNT_e), head_offset)`` at d_a_player_main.cpp:11592, written right
        after the SAME exec-pass ``mpCLModel->calc()`` (:11591) ``setCollision`` reads, so the
        base/lean call convention is identical to :meth:`body_co_center` (same worldBase, same
        new-lean BODY_CHN twist, same proc-init zero-lean handling by the caller). Consumed by
        Tetra's look-at as ``dNpc_playerEyePos``'s Y (x/z are overwritten with Link's
        ``current.pos``). Returns the full (x, y, z); pass the REAL ``py`` (the Y is the
        payload). Requires ``body_co`` mode (joint 15 is posed with the neck-chain extras).
        ``neck`` = the head-look twist, as in :meth:`head_mtx`."""
        return tuple(fk.mtx_mult_vec(
            self.head_mtx(px, py, pz, facing, lean=lean, body_lean=body_lean, neck=neck),
            HEAD_TOP_OFF))

    def _waist_world(self, local):
        """WORLD translate of the WAIST joint (30) for the pose being drawn: the base->waist
        prefix of the foot chain accumulation (bit-identical to the game's getAnmMtx(WAIST)
        column 3). Phase G / floors mode only (Python world path)."""
        cur = self.base
        for jnt in self._chains[34]:
            cur = fk.mtx_concat(cur, local[jnt])
            if jnt == 30:
                return (cur[0][3], cur[1][3], cur[2][3])
        raise AssertionError("WAIST joint 30 is not on the foot chain")

    def seed(self, move0, f0):
        """Populate old pose from a single anim (e.g. FREEB rest) before the first walk step."""
        if self._engine is not None:
            i = self._anim_idx[move0]
            self._engine.pose_toe(i, i, f0, f0, 0.0, -1.0)
            return
        self._pose_frame(move0, move0, f0, f0, 0.0, 0.0)

    def step(self, move0, move1, f0, f1, ratio, i_morf=-1.0, toe=fk.L_TOE):
        """Advance one frame; return (Ltoe, Rtoe) model-local. i_morf>=0 triggers oldframe-morf."""
        if i_morf >= 0.0:
            self.morf.init_morf(i_morf)
        rate = self.morf.rate                        # rate the foot joints see this frame
        local = self._pose_frame(move0, move1, f0, f1, ratio, rate)
        lt = self._toe(local, 34, toe)
        rt = self._toe(local, 39, toe)
        self.morf.dec()                              # the per-frame "last joint" decrement
        return lt, rt

    def step_feet(self, move0, move1, f0, f1, ratio, i_morf=-1.0):
        """Advance one frame; return dict with model-local toe+heel (x,y,z) for both feet, keyed as
        spB0/sp98 in posMoveFromFootPos: index 0 = RIGHT foot (jnt 39), index 1 = LEFT foot (jnt 34).
        posMoveFromFootPos uses the SAME l_toe_pos/l_heel_pos for both feet (the joint mtx mirrors)."""
        if self._engine is not None:
            m1 = move1 if move1 is not None else move0
            return self._engine.pose_toe(self._anim_idx[move0], self._anim_idx[m1],
                                         f0, f1, ratio, i_morf)
        if i_morf >= 0.0:
            self.morf.init_morf(i_morf)
        rate = self.morf.rate
        local = self._pose_frame(move0, move1, f0, f1, ratio, rate)
        if self.track_waist:
            self.last_waist = self._waist_world(local)
        # Accumulate each foot's chain matrix ONCE, then read both the toe and heel off it.
        cur39 = self._chain_mtx(local, 39)
        cur34 = self._chain_mtx(local, 34)
        mv = fk.mtx_mult_vec
        rt = mv(cur39, fk.L_TOE); lt = mv(cur34, fk.L_TOE)
        rh = mv(cur39, fk.L_HEEL); lh = mv(cur34, fk.L_HEEL)
        self.morf.dec()
        # Flat 12-tuple [Rtoe, Ltoe, Rheel, Lheel] x (x,y,z) -- matches PoseEngine.pose_toe.
        return (rt[0], rt[1], rt[2], lt[0], lt[1], lt[2],
                rh[0], rh[1], rh[2], lh[0], lh[1], lh[2])
