# Actor-vs-actor "Co" push - how Tetra (or any actor) shoves Link

**Answers:** How does another actor push Link (the "Tetra nudge")? What's the cyl-cyl overlap math
and the weight/rank split? Which way does Link get pushed, and on which frame? Can a Tetra push
supply the extra displacement a seam clip needs when the roll/thrust falls just short? (How FAR a
push moves an actor is [push-magnitude.md](push-magnitude.md).)
**Status:** validated live - decomp-faithful port ([`tww_sim/core/cc_push.py`](../../tww_sim/core/cc_push.py))
reproduces the game on GZLJ01. The overlap math (`cM3d_Cross_CylCyl`) matches 60/60; the weight split
is the **`dCcS::SetPosCorrect` rank table** (NOT the base `cCcS` mass-proportional split), confirmed
by a live `m_cc_move` capture (`|Link.cc| / |Tetra.cc| = 1.0000` every frame → exact 50/50). Tetra's
cylinder+weight and Link's cylinder are read live (Hyrule, GZLJ01, 2026-07-06). Link's **animated
cylinder center** (root+neck joint midpoint) is a decomp-faithful anim-engine port
([`body_cyl.roll_co_center`](../../tww_sim/core/anim/body_cyl.py)), **live-validated bit-exact** vs the
game's `mCyl` centre during a FRONT_ROLL (2026-07-06). The seam-clip pipeline is now driven by the
model-derived thrust (`LandState.enter_cut`; reproduces the live (−1727,−990) clip endpoint bit-for-bit),
and the roll-stab was live-reproduced at the corner - aim/wall-hold/bonk confirmed (2026-07-06, below).
**Source:** decomp `dCcS::SetPosCorrect` / `dCcS::GetRank` / `rank_tbl` (`d_cc_s.cpp:138/153/180`),
`cM3d_Cross_CylCyl` (`c_m3d.cpp:1553`), `cCcD_Stts::PlusCcMove` (`c_cc_d.cpp`), `daPy_lk_c::posMove`
+ `daPy_lk_c::setCollision` (`d_a_player_main.cpp:9748`) + player/Tetra weights (`:11233`,
`d_a_npc_zl1.cpp`); the push's FP shape is read off the shipped JP binary (see
[The FP shape](#the-fp-shape-load-bearing---read-this-before-touching-the-push)). Constants:
[reference/constants-npc.md](../reference/constants-npc.md#collision-actor-co-push).

---

## The chain

Every frame the collision system (`cCcS::ChkCo`) tests all registered **Co** cylinders pairwise.
When two overlap it computes an overlap depth and shares a corrective move between them. Link consumes
his share on the **next** frame, before his own movement and before the wall check.

1. **Overlap depth** - `cM3d_Cross_CylCyl` (the `f32*` variant). Two vertical cylinders (center,
 radius, height). Gate on XZ distance (`dist² > (r₁+r₂)²` → miss) and on Y overlap
 (`c₁.y+h₁ < c₂.y || c₁.y > c₂.y+h₂` → miss); otherwise depth `= (r₁+r₂) − √(dx²+dz²)`.
2. **Weight split** - **`dCcS::SetPosCorrect`** (the game subclass's virtual override - a live
 breakpoint on the base `cCcS::SetPosCorrect` JP 0x8024101C **never fires**; the game calls the
 override at JP 0x800AB1E4). A deadzone `cM3d_IsZero(cross_len)` (|·| < 1e-5) skips it, and a
 both-immovable pair (both weight 0, or both 0xFF) skips too. Otherwise the split is a **rank-table
 lookup**, not mass-proportional:
 - `dCcS::GetRank(weight)` collapses the raw weight to a rank 0..10 (0xFF→10, 0xFE→9, then
 `≥0xD9→8, ≥0xB5→7, ≥0x91→6, ≥0x6D→5, ≥0x49→4, ≥0x25→3, ≥0x02→2, ==1→1, else 0`).
 - `obj1`'s share = `rank_tbl[GetRank(w₁)][GetRank(w₂)] / 100`; `obj2`'s share is the complement.
 The table is **asymmetric** (lower rank ⇒ larger share ⇒ moves more). Same-rank pairs split
 **50/50** regardless of the exact weights.
 - Each actor moves `depth × its share` along the horizontal center-to-center line, **away** from
 the partner.
3. **Consumption** - the move is accumulated into `mStts.m_cc_move` (`PlusCcMove`, in `dCcS::Move()`,
 called from `dScnPly_Draw` - the **Draw** phase, *after* every actor's Execute) and applied on
 Link's next `posMove` (`d_a_player_main.cpp:2556-2610`). The exact order inside `posMove` is:
 `posMoveFromFootPos()` (the foot/roll **speedF** move) **first**, THEN `current.pos +=
 *mStts.GetCCMoveP()` (`:2558`), THEN the m34C2 **cut root-translate lunge** (`:2610`, the roll-stab
 thrust), THEN `dBgS_Acch::CrrPos` (the wall LineCheck + WallCorrect). So on the roll-stab clip
 frame the push stacks **between** the roll's speedF displacement and the sword-thrust lunge (not
 before both), then the wall sweeps `old → new`. Because f32 adds don't associate, that ordering is
 load-bearing at the seam's ULP scale - the sim reproduces it exactly (`LandState._cc_move`,
 consumed at the same point; `harness/rollstab/cc_stepper.py`). The push from frame *N*'s Draw-phase
 overlap (computed from *N*'s settled + drawn positions) lands on frame *N+1*, **before** the wall
 is tested.

## The FP shape (load-bearing - read this before touching the push)

Both distance computations in the chain are **UNFUSED**, and the square root is the game's
`std::sqrtf`, not a correctly-rounded one. Read off the shipped JP binary:

| Site | JP address | Instructions |
|------|-----------|--------------|
| `cM3d_Cross_CylCyl` `dist_sq` | `0x8024C44C` | `fmuls f1,f2,f2` · `fmuls f0,f0,f0` · `fadds f4,f1,f0` |
| `dCcS::SetPosCorrect` `objDistLen` | `0x800AB430` (correctY: `0x800AB394`) | the same three ops |
| `std::sqrtf` (both) | inlined, e.g. `0x800AB444` | `frsqrte` + **3** double Newton steps, then one f32 round of `x*guess` (MSL `math.h`) |

There is **no `fmadds` in either routine**. Do not assume the fused form because `PSVECMag` fuses -
`PSVECMag` is a separate paired-single routine and its shape does not carry over. This is not
rounding pedantry: fusing puts `cross_len` ~2 ULP high, which biases the push ~3e-6 u per frame, and
a two-actor plow AMPLIFIES that ~1.4x per contact frame - over a few hundred contact frames it grows
into a divergence of tens of units against the console. The port
([`tww_sim/core/cc_push.py`](../../tww_sim/core/cc_push.py)) carries the unfused shape and its
native twin is gated bit-for-bit against it
([`tests/test_cc_push_native.py`](../../tests/test_cc_push_native.py)).

## Link & Tetra parameters (GZLJ01, live-confirmed)

- **Link** weight **120** → `GetRank(120) = 5`. Body Co cylinder (`daPy_lk_c::setCollision`):
 **R = 30** while walking/rolling (`SetR(50)` *only* when `checkGrabWear()`, i.e. carrying/wearing
 an item); H ≈ `40.1 + (neck_jnt − toe_jnt)` ≈ 107 walking (81.25 in FRONT_ROLL). Its **center is
 the horizontal midpoint of the root & neck joints** (`0.5·(root+neck)` of the *world* anim matrices
 `getAnmMtx(joint)[0/2][3]`, d_a_player_main.cpp:9753-9754), vertical = the lower toe joint
 (FRONT_ROLL: `= current.pos.y`). So Link's Co cylinder is **animation-driven**, not feet-centered:
 it sways ~16–22 u from `current.pos` while walking and, during a **FRONT_ROLL lunge, leads the feet
 by 10–31 u** (peaks ~frame 5–6 of the roll). The offline port
 [`tww_sim/core/anim/body_cyl.roll_co_center(pos, facing, frame, shape_z)`](../../tww_sim/core/anim/body_cyl.py)
 runs the same world-space FK the walk foot chain uses and is **live-validated bit-exact** once
 **both** body-lean terms are fed in - the turn lean reaches the midpoint TWICE, one frame apart, and
 the twist is a no-op below ~30 BAM and worth ~0.35 u at a real one. That, the two ports, and the
 regime trap in gating them are [link-co-centre.md](link-co-centre.md)
 (`tests/test_body_cyl.py`, `fixtures/hyrule_roll_lean.json`).
- **Tetra** (NPC `Zl1`) body Co cylinder **R = 50, H = 140, center = `current.pos`** (feet). Weight
 is `0xFF` (immovable, GetRank 10) by default in `createInit`, but **`0x8C` = 140 (GetRank 5)** for
 the `field_0x84F == 5` variant - and the **flooded-Hyrule Tetra is live-confirmed as that variant**
 (`mStts.m_weight` = 0x8C, 2026-07-06).
- ⇒ Link (rank 5) vs Tetra (rank 5): `rank_tbl[5][5] = 50` → **Link takes exactly 0.50 × the overlap
 depth and Tetra recoils 0.50 ×** (live: `|Link.cc| = |Tetra.cc|`, `Link.cc + Tetra.cc = 0` every
 frame). To nudge Link by *d* toward a corner you need overlap `2d`, with Tetra placed on the far
 side of Link from the corner (push = `unit(link − tetra)`). An **immovable** (0xFF) Tetra instead
 gives Link the full depth (`rank_tbl[5][10] = 100`). **Re-confirm the live weight/rank for any other
 scene.**

> **Only actionable, *moving* Link pushes.** Live: an **idle** Link (state 4) sitting inside a 6.4 u
> overlap produced **no** `m_cc_move` and no separation - his body Co cylinder is set/checked while he
> is actively moving (walking/rolling, e.g. state 6). Validate the push with Link *walking into* the
> partner, not standing in overlap. (This is why the earlier debug-pos-hack attempts saw nothing.)

## Using it for a seam clip

A [seam clip](seam-clip.md) needs `old` settled in front of the corner and `new` far enough past the
seam vertex S that WallCorrect no longer overlaps **and** the swept LineCheck misses all four
triangle planes. When the roll/thrust displacement alone lands `new` just short, a Tetra push extends
it: `new = old + push + thrust` (the `posMove` order). [`tetra_clip.py`](../../harness/collision/README.md)
composes `co_push_link` + `crr_pos_walls`: `clip_with_push(old, link_y, thrust, tetra_xz, tris)` runs
one clip frame; `solve_min_overlap` places Tetra directly behind Link and returns the smallest overlap
that clips (with `sumR = 30 + 50 = 80`).

**Worked result (live −1727,−990 anchor, `tests/test_tetra_clip.py`) - now model-derived end to end:**
the thrust is `LandState.enter_cut(CUT_F)` out of a 26 u roll at the anchor's clip facing (**40874 BAM /
224.5°**), giving `(dx,dz) = (−34.415, −35.189)`, disp **49.220 u**, direction **40844 BAM**. Aimed there
the roll+thrust **does not clip alone** (live-confirmed: a bare roll-stab into the corner **bonks off the
wall**, proc `0x5A` - [see below](#live-corner-reproduction-2026-07-06)). The push the live clip needed is
`NEW − OLD − thrust = (−0.618, −0.427)`, **|push| ≈ 0.75 u**, at the **0.50 share** so an overlap of
**≈1.50 u**. Placing Tetra behind Link's roll-cyl center along −push at that overlap, `clip_with_push`
reproduces the live clip endpoint **NEW = (−1727.3423, −990.6356) bit-for-bit**.

> **The push STEERS `new` into the seam - its direction is NOT the thrust direction.** The modeled thrust
> aims at **40844 BAM**, but the observed `old→new` is **40874 BAM** (≈30 BAM / 0.16° off), and the seam
> clip window is razor-thin at that scale. The ≈0.75 u push points along **42848 BAM** - well off the
> thrust - and that lateral component is exactly what walks `new` from the thrust ray onto the seam
> vertex. So `solve_min_overlap` (which places Tetra *colinear behind the thrust* and sweeps depth) does
> **NOT** find a clip for the true model thrust: with the push forced along 40844 it never reaches the
> 40874 window. The overlap depth is placement-invariant only when the thrust already aims at the seam;
> for the real roll-stab (whose achievable facing doesn't perfectly hit S) the **Tetra position, not just
> the depth, decides the clip**.

> **The 49.22 u is a roll + sword thrust - now modeled bit-exact.** The displacement that reaches the
> corner is a **stacked land move** - a FRONT_ROLL into a **sword thrust** (the
> [roll stab](roll-stab.md)). The land sim
> ([`tww_sim/land/land.py`](../../tww_sim/land/land.py)) now models BOTH halves **bit-exact** (`CUT_F`
> forward thrust / `CUT_A` L+B vertical slash; live 0 ULP, GZLJ01 2026-07-06). The roll caps at 26.0 u,
> and the cut's FIRST frame adds the animation joint-0 root-translate lunge (`m3700`, reset to 0 in
> `procCut*_init`, +23.220 u at anim frame 4.0) on top of the carried roll `speedF`: `26 + 23.220 =
> 49.220 u` (`posMove` `m34C2 == 1`, `d_a_player_main.cpp:2488`; cut procs `d_a_player_sword.inc:690`, HIO
> `d_a_player_HIO_data.inc:31/27`; root motion via [`core.anim.j3d_eval`](../../tww_sim/core/anim/j3d_eval.py)
> on `cutf.bck`/`cuta.bck`). `test_tetra_clip.py` now derives the displacement from
> `LandState.enter_cut(CUT_F)` (model-derived, not a literal). The Tetra-push pipeline that closes the
> remaining sub-unit gap is unchanged. Full mechanic + constants:
> [land-movement.md](roll-stab.md),
> [reference/constants.md](../reference/constants.md#land-sword-cut-roll-stab).

> **Where the animated center matters.** For the *colinear-behind* solver, the **overlap depth** is
> placement-invariant (Tetra sits along `−thrust`, so `unit(center − tetra)` is the thrust direction and
> the depth is the swept overlap regardless of where the center sits) - but as the steering note above
> shows, that arrangement doesn't reproduce the real clip; the actual Tetra sits **off** the thrust ray so
> its position sets both the depth (≈1.50 u) and the push direction (≈42848 BAM). Either way the animated
> center changes the **physical world position Tetra must occupy** - she stands behind the *cylinder
> center*, not the feet, so at the lunge peak (frame ~5–6, center 31 u ahead of the feet) the required
> Tetra position shifts **~31 u** further along the roll from the feet-proxy spot. Pass
> `link_center=body_cyl.roll_co_center(pos, facing, frame)` to `clip_with_push` / `solve_min_overlap`
> to place her correctly (the returned `tetra_xz`); omit it for the feet proxy. It also matters for a
> **fixed** Tetra (spawned at a set world point, not placed optimally), where the true center changes
> both the depth and the push direction. The **sword-thrust half is now modeled** (`CUT_F`/`CUT_A`,
> live 0 ULP) so the land sim produces the real per-frame roll+thrust displacement and the clip frame - 
> the 49.22 u is model-derived (`LandState.enter_cut`), not a literal.

## Live corner reproduction (2026-07-06)

Driving the roll-stab at the real (−1727,−990) corner (savestate 3) live-confirmed the pieces the
pipeline assumes:

- **Aim decides the clip, and it must be ≈224.5° (40874 BAM), ~7.5° off camera-forward.** At the corner
 the camera faces 39507 (217°); a straight-up run/roll thrusts at 217°, whose displacement is mostly
 **into** the +Z wall (z ≈ −955) → WallCorrect blocks it → no clip. The clip direction must bisect the
 corner toward the seam vertex. Tilt the stick **left** (`stickX ≈ 96`) to raise the roll/cut facing to
 ≈40965 (right-tilt *lowers* it). The seam window is razor-thin (~30 BAM), so this is a fine-aim trick.
- **The wall holds the roll speed.** A 26 u roll into the corner reaches `old` and, pressed against the
 wall, **keeps `speedF = 26` for 10+ frames** (position frozen by WallCorrect, speed un-decayed) - so
 the roll doesn't need a 390 u runway to still carry 26 into the cut; it can arrive and hold at `old`.
 `kroll = 15` (roll frames before the thrust is accepted) still applies.
- **Roll + thrust ALONE bonks - no clip without the push.** Even with the right facing and `old` at the
 corner, a Tetra-free roll-stab moves ≈0.03 u then transitions to the **bonk/recoil proc `0x5A`**
 (facing flips, knocked back NE). This is the direct live confirmation that 49.22 u is short of the f32
 clip floor at this corner and the **Tetra push is required** - exactly what `test_tetra_clip.py` asserts.
- **The model predicts the exact Tetra position for a live clip.** With Link's roll-cyl center at
 `roll_co_center(old, 40874, 12) = (−1688.31, −948.46)` and push dir `unit(center − tetra)`, the ≈1.50 u
 overlap that closes it puts Tetra's **body-cyl center at ≈(−1623.7, −903.8)** (center distance
 `80 − 1.50 = 78.5`). (Tetra found live via the DMC walk - [[find-rel-actor-live]]; instance
 `0x80acd20c`, body cyl @ `+0x68C`, `current.pos` @ `+0x1F8`.) A live clip re-demonstration is still
 open - Link's roll passes through that spot, so Tetra must arrive there only on the pre-clip frame (a
 following-NPC timing, or a late position-hack); see the handoff.

## How FAR the push can move an actor per frame

The magnitude half has its own page: [push-magnitude.md](push-magnitude.md). In one line, a single
frame's push is exactly the overlap halved - `(R_link + R_actor - centre_distance) / 2`, measured to
the animated centre above - so the SUSTAINED rate is set by the mean contact depth and settles at
`|speedF| / 2` (13.0 u/frame at the roll cap). That is an average and not a per-frame bound: the pose
swing lets one frame reach 18.84 u, and a shallow contact pushes proportionally less.

## Frame-lag caveat for setups

The push consumed on the clip frame comes from the overlap **one frame earlier**. The model assumes a
single clean overlap frame just before the roll (Link settled at `old`, Tetra positioned to overlap).
Because Tetra (rank 5, same as Link) also recoils each overlap frame, a multi-frame hold drifts her - 
hold the overlap for exactly the frame before the clip.

## See also
- [mechanics/link-co-centre.md](link-co-centre.md) - where Link's pushing cylinder actually is, and the two turn-lean terms that tilt it.
- [mechanics/push-magnitude.md](push-magnitude.md) - how far one frame of push moves an actor.
- [mechanics/prop-push.md](prop-push.md) - bomb/small-pot B-drop branch, frame order,
  coupled collision model, and proof gates.
- [mechanics/seam-clip.md](seam-clip.md) - the wall-corner clip this push feeds; `min_f32_clip` reachability.
- [mechanics/collision.md](collision.md) - the DZB wall mesh and the `CrrPos` wall barriers.
- [reference/constants-npc.md](../reference/constants-npc.md#collision-actor-co-push) - cylinder radii/heights, ranks.
- [history/tetra-push-massprop-superseded.md](../history/tetra-push-massprop-superseded.md) - the
 superseded mass-proportional (cCcS, 0.538, R=50) model and why it was wrong.
