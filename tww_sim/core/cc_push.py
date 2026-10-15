"""FP-faithful port of TWW's actor-vs-actor "Co" collision push (the cylinder-cylinder shove).

This is the mechanism behind a **Tetra (NPC Zl1) nudge**: when Link's body cylinder overlaps
another actor's Co cylinder, the weight/priority system accumulates a horizontal push into Link's
``mStts.m_cc_move``, which Link consumes on the *next* frame in ``daPy_lk_c::posMove`` (``current.pos
+= *mStts.GetCCMoveP()``) — **before** that frame's own movement (roll/thrust) and **before**
``dBgS_Acch::CrrPos`` (the wall check). So a well-placed Tetra adds a small extra displacement toward
a wall corner on the clip frame, on top of the roll/thrust, which is exactly the lever a seam clip
needs when the roll+thrust displacement alone falls just short of the corner's f32 minimum.

**The game uses ``dCcS::SetPosCorrect`` (the game-subclass override), NOT ``cCcS::SetPosCorrect``.**
``SetPosCorrect`` is virtual and the live collision system is ``dCcS``, so the call dispatches to the
override — confirmed live (breakpoint JP 0x800AB1E4 fires; the base cCcS 0x8024101C never does). The
two differ crucially in the **weight split**: the base cCcS is mass-proportional (``wᵢ/(w₁+w₂)``); the
game's dCcS uses a **rank table** (``dCcS::GetRank`` collapses the raw weight to a rank 0..10, then
``rank_tbl[rank1][rank2]`` gives the mover's share as a 0..100 percentage). Two actors of the *same*
rank split 50/50 regardless of their exact weights.

Chain (all decomp-grounded, GZLJ01):
  1. **Overlap depth** — ``cM3d_Cross_CylCyl`` (``c_m3d.cpp:1553``, the ``f32*`` variant):
     two vertical cylinders (center, radius, height). Gate on XZ distance (``dist² > Σr²``) and Y
     overlap (``c1.y+h1 < c2.y  ||  c1.y > c2.y+h2``); depth ``= Σr − √(dx²+dz²)``. Live 60/60.
  2. **Push split** — ``dCcS::SetPosCorrect`` (``d_cc_s.cpp:180``), fed each cylinder's Co center
     (``GetCoCP()``) and the depth. A deadzone ``cM3d_IsZero(cross_len)`` (|·| < 1e-5) skips it; a
     both-immovable pair (both weight 0, or both 0xFF) skips too. Otherwise each actor is moved by
     ``cross_len × (its share)`` along the horizontal center-to-center line, away from the partner —
     obj1's share = ``rank_tbl[GetRank(w1)][GetRank(w2)]/100``, obj2's = the complement.
  3. **Consumption** — ``cCcD_Stts::PlusCcMove`` (``c_cc_d.cpp``) accumulates it; Link applies it next
     frame in ``posMove`` (``d_a_player_main.cpp``), then clears it.

Weights & cylinders (GZLJ01, live-confirmed 2026-07-06 in flooded Hyrule):
  * **Link** ``mStts.SetWeight(120)`` → GetRank(120) = **5**. Body Co cylinder (``daPy_lk_c::setCollision``,
    d_a_player_main.cpp:9748): **R = 30** while walking (``SetR(50)`` *only* when ``checkGrabWear()``,
    i.e. carrying), H ≈ ``40.1 + (neck_jnt − toe_jnt)`` ≈ 107, and the **center is the horizontal
    midpoint of the root & neck joints** (not ``current.pos`` — it sways with the walk animation, live
    offset ~16–22 u). FRONT_ROLL uses R=30, H=81.25, center.y = ``current.pos.y``.
  * **Tetra** (NPC ``Zl1``) body Co cylinder **R = 50, H = 140, center = ``current.pos``**; weight
    ``0x8C`` = 140 (the ``field_0x84F == 5`` variant) → GetRank(140) = **5**.
  * ⇒ ``rank_tbl[5][5] = 50`` → **Link takes exactly 0.50 × the overlap depth and Tetra recoils 0.50 ×**
    (live-confirmed: ``|Link.cc| / |Tetra.cc| = 1.0000`` every frame, ``Link.cc + Tetra.cc = 0``). NOT
    the mass-proportional 140/260 ≈ 0.538 the old cCcS port assumed. Re-confirm ranks for other scenes.

FP note (CORRECTED session 55, read off the shipped JP binary -- the old note here claimed the
opposite and it cost 113 u on console): ``dist²`` is **NOT** fused. ``cM3d_Cross_CylCyl`` computes it
as two ``fmuls`` and an ``fadds`` (JP 0x8024C44C-0x8024C454: ``fmuls f1,f2,f2`` / ``fmuls f0,f0,f0`` /
``fadds f4,f1,f0``), and ``dCcS::SetPosCorrect``'s ``objDistLen`` does the same (JP 0x800AB430-38, and
0x800AB394-3A4 for the correctY branch) -- there is no ``fmadds`` anywhere in either. The earlier port
assumed ``fmadds(dz,dz, fmuls(dx,dx))`` "like ``PSVECMag``"; ``PSVECMag`` is a different (paired-single)
routine and its fusing does not carry over. The ``√`` is ``std::sqrtf`` = ``__frsqrte`` + 3 double
Newton steps (:func:`collision.sqrtf_msl`), inlined at JP 0x800AB444 / in CylCyl, not a
correctly-rounded sqrt.

This is a **0-ULP surface, not a rounding detail**: the fused form put ``cross_len`` ~2 ULP high, which
biased the push ~3e-6 u/frame; the ~1.4x/contact-frame plow amplifier turned that into a 113 u miss by
plan frame 241, measured on console. Pure stdlib + ``core.fp``.
"""
from .fp import f32 as _f, fadds, fsubs, fmuls, fdivs
from .collision import sqrtf_msl as fsqrt, is_zero


def _dist_sq(dx, dz):
    """``delta_x*delta_x + delta_z*delta_z`` the way both call sites compile it: two separate
    ``fmuls`` and an ``fadds``, each rounded to f32 -- NOT a fused ``fmadds`` (see the FP note)."""
    return fadds(fmuls(dx, dx), fmuls(dz, dz))

# Raw weights (cCcD_Stts::SetWeight). 0xFF is immovable, 0xFE is the near-immovable rank.
WEIGHT_LINK = 120           # daPy_lk_c setBgCheckParam SetWeight(120) -> GetRank 5
WEIGHT_TETRA_DEFAULT = 0xFF  # daNpc_Zl1_c::createInit default -> GetRank 10 (immovable)
WEIGHT_TETRA_V5 = 0x8C       # 140, field_0x84F==5 variant -> GetRank 5 (== Link's rank)

# dCcS::SetPosCorrect share table (d_cc_s.cpp:138). rank_tbl[obj1Rank][obj2Rank] = obj1's push % (0..100);
# obj2's % is the complement (100 − that). Rows/cols 0..10 index GetRank's output.
RANK_TBL = (
    (0, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100),
    (0,  50, 100, 100, 100, 100, 100, 100, 100, 100, 100),
    (0,   0,  50,  75,  90, 100, 100, 100, 100, 100, 100),
    (0,   0,  25,  50,  75,  90, 100, 100, 100, 100, 100),
    (0,   0,  10,  25,  50,  75,  90, 100, 100, 100, 100),
    (0,   0,   0,  10,  25,  50,  75,  90, 100, 100, 100),
    (0,   0,   0,   0,  10,  25,  50,  75,  90, 100, 100),
    (0,   0,   0,   0,   0,  10,  25,  50,  75, 100, 100),
    (0,   0,   0,   0,   0,   0,  10,  25,  50, 100, 100),
    (0,   0,   0,   0,   0,   0,   0,   0,   0,  50, 100),
    (0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0),
)


def get_rank(weight):
    """``dCcS::GetRank`` (d_cc_s.cpp:153): raw weight u8 -> rank 0..10."""
    w = weight & 0xFF
    if w == 0xFF:
        return 10
    if w == 0xFE:
        return 9
    if w >= 0xD9:
        return 8
    if w >= 0xB5:
        return 7
    if w >= 0x91:
        return 6
    if w >= 0x6D:
        return 5
    if w >= 0x49:
        return 4
    if w >= 0x25:
        return 3
    if w >= 0x02:
        return 2
    if w == 0x01:
        return 1
    return 0


def cyl_cyl_cross_len(c1, r1, h1, c2, r2, h2):
    """``cM3d_Cross_CylCyl`` (c_m3d.cpp:1553, the ``f32*`` overlap-depth variant).

    ``c1``/``c2`` = (x, y, z) cylinder centers; ``r*``/``h*`` = radius/height. Returns
    ``(hit: bool, cross_len: f32)`` where ``cross_len`` is the overlap depth (``Σr − dist``), or
    ``(False, 0.0)`` if the XZ circles miss or the height ranges don't overlap. Live 60/60 on GZLJ01.
    """
    dx = fsubs(c1[0], c2[0])
    dz = fsubs(c1[2], c2[2])
    dist_sq = _dist_sq(dx, dz)                       # (dx*dx) + (dz*dz), UNFUSED (see the FP note)
    radius_sum = fadds(r1, r2)
    if dist_sq > fmuls(radius_sum, radius_sum):
        return False, _f(0.0)
    # Y-overlap gate: c1.y + h1 < c2.y  ||  c1.y > c2.y + h2
    if fadds(c1[1], h1) < c2[1] or c1[1] > fadds(c2[1], h2):
        return False, _f(0.0)
    return True, fsubs(radius_sum, fsqrt(dist_sq))


def push_shares(w1, w2):
    """``dCcS::SetPosCorrect`` weight branch (d_cc_s.cpp:201-211). Returns ``(obj1Weight, obj2Weight)``
    as f32 shares in [0,1], or ``None`` for a both-immovable pair (no correction). ``obj_i`` is moved
    by ``cross_len × obj_iWeight``. NOTE: obj1's share uses ``rank_tbl[rank1][rank2]`` — the table is
    asymmetric, so obj1/obj2 order matters (the lighter/lower-rank actor moves more)."""
    a, b = w1 & 0xFF, w2 & 0xFF
    if (a == 0 and b == 0) or (a == 0xFF and b == 0xFF):
        return None
    rank = RANK_TBL[get_rank(a)][get_rank(b)]        # obj1's push %, 0..100
    obj1_weight = fmuls(_f(rank), _f(0.01))
    obj2_weight = fmuls(_f(100 - rank), _f(0.01))
    return obj1_weight, obj2_weight


def co_push_link(link_c, link_r, link_h, other_c, other_r, other_h,
                 link_w=WEIGHT_LINK, other_w=WEIGHT_TETRA_V5):
    """Link's accumulated ``m_cc_move`` from one Co overlap with ``other`` (e.g. Tetra).

    Ports ``cM3d_Cross_CylCyl`` (overlap depth) + ``dCcS::SetPosCorrect`` (rank-table split, horizontal
    push away from the partner). ``*_c`` = (x, y, z) Co cylinder centers; ``*_r/*_h`` = radius/height;
    ``*_w`` = raw weight value. Returns the ``(dx, dy, dz)`` push that Link's next ``posMove`` adds to
    ``current.pos`` (``dy = 0`` — the cylinder path is horizontal, ``correctY`` is false for two
    cylinders). ``(0, 0, 0)`` if no overlap, inside the deadzone, or both immovable.

    Link is treated as **obj1** (matching the live capture: r4 = Link's cCcD_Obj), so Link's push uses
    ``rank_tbl[GetRank(link_w)][GetRank(other_w)]``. ``dist`` is recomputed from the Co centers exactly
    as ``SetPosCorrect`` does.
    """
    hit, cross_len = cyl_cyl_cross_len(link_c, link_r, link_h, other_c, other_r, other_h)
    if not hit:
        return _f(0.0), _f(0.0), _f(0.0)
    if is_zero(cross_len):                       # dCcS: cM3d_IsZero(cross_len) -> skip (|.| < 1e-5)
        return _f(0.0), _f(0.0), _f(0.0)

    shares = push_shares(link_w, other_w)
    if shares is None:
        return _f(0.0), _f(0.0), _f(0.0)
    obj1_weight, _obj2_weight = shares           # Link = obj1; Link moves by cross_len * obj1_weight

    # SetPosCorrect (!correctY): objsDist = ppos2 - ppos1 = other - link (XZ); scale to cross_len;
    # vec1 (Link) = -objsDist * (cross_len/dist) * obj1_weight  ==  (link - other) dir, mag cl*share.
    dx = fsubs(other_c[0], link_c[0])
    dz = fsubs(other_c[2], link_c[2])
    dist = fsqrt(_dist_sq(dx, dz))
    if not is_zero(dist):
        f = fdivs(cross_len, dist)               # pushFactor = cross_len / objDistLen
        return (fmuls(fmuls(dx, f), fsubs(_f(0.0), obj1_weight)), _f(0.0),
                fmuls(fmuls(dz, f), fsubs(_f(0.0), obj1_weight)))
    # degenerate: centers coincident -> push along +x by cross_len*share (SetPosCorrect else-branch)
    mag = cross_len if not is_zero(cross_len) else _f(1.0)
    return fmuls(fsubs(_f(0.0), mag), obj1_weight), _f(0.0), _f(0.0)


def co_move_pair(c1, r1, h1, c2, r2, h2, w1=WEIGHT_LINK, w2=WEIGHT_TETRA_V5):
    """Both actors' ``m_cc_move`` from ONE Co overlap -- the full ``dCcS::SetPosCorrect`` output
    (``d_cc_s.cpp:180``), for the CC-push STEPPER (Link *and* Tetra recoil each on their next frame).

    ``c1``/``c2`` = (x, y, z) Co cylinder centers, ``r*``/``h*`` = radius/height, ``w*`` = raw weight.
    Returns ``((dx1,dy1,dz1), (dx2,dy2,dz2))`` -- obj1's and obj2's accumulated moves (``dy = 0``: two
    cylinders, ``correctY`` false). Both ``(0,0,0)`` on no overlap / deadzone / both-immovable.

    obj1 is moved by ``vec1 = -objsDist * obj2Weight`` and obj2 by ``vec2 = +objsDist * obj1Weight``
    where ``objsDist = (c2 - c1)`` scaled to ``cross_len`` (decomp lines 234/247): obj1's move factor
    is ``rank_tbl[GetRank(w1)][GetRank(w2)]/100`` and obj2's is the complement. So obj1's move here is
    IDENTICAL to :func:`co_push_link` (guarded in tests/test_cc_stepper.py); this adds the obj2 recoil
    that a stepper must feed back into the partner. For a same-rank pair (Link 5 vs Tetra-v5 5) the
    two moves are equal-and-opposite (``sum == 0``, live-confirmed)."""
    hit, cross_len = cyl_cyl_cross_len(c1, r1, h1, c2, r2, h2)
    zero = (_f(0.0), _f(0.0), _f(0.0))
    if not hit or is_zero(cross_len):            # cM3d_IsZero(cross_len) skips SetPosCorrect
        return zero, zero
    shares = push_shares(w1, w2)                 # None => both immovable
    if shares is None:
        return zero, zero
    # push_shares returns (obj1_move_factor, obj2_move_factor) == (rank*0.01, (100-rank)*0.01).
    # In SetPosCorrect naming these are (obj2Weight, obj1Weight): vec1 uses the FIRST, vec2 the SECOND.
    obj2_weight, obj1_weight = shares
    dx = fsubs(c2[0], c1[0])                     # objsDist = ppos2 - ppos1 (obj2 - obj1)
    dz = fsubs(c2[2], c1[2])
    dist = fsqrt(_dist_sq(dx, dz))
    if not is_zero(dist):
        f = fdivs(cross_len, dist)               # pushFactor = cross_len / objDistLen
        sx = fmuls(dx, f)                         # objsDist.x *= pushFactor (scaled in place)
        sz = fmuls(dz, f)
        vec1 = (fmuls(sx, fsubs(_f(0.0), obj2_weight)), _f(0.0),
                fmuls(sz, fsubs(_f(0.0), obj2_weight)))
        vec2 = (fmuls(sx, obj1_weight), _f(0.0), fmuls(sz, obj1_weight))
        return vec1, vec2
    # degenerate: centers coincident -> along +x (SetPosCorrect else-branch)
    mag = cross_len if not is_zero(cross_len) else _f(1.0)
    return ((fmuls(fsubs(_f(0.0), mag), obj2_weight), _f(0.0), _f(0.0)),
            (fmuls(mag, obj1_weight), _f(0.0), _f(0.0)))
