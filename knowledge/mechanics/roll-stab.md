# Roll stab (sword thrust out of a roll): the seam-clip lunge

**Answers:** What is the roll stab / the 49.22 single-frame lunge? Where does the 49.22 come from
(CUT_F vs CUT_A)? Can the thrust be aimed (diagonal thrust), and over what range? How is it modeled?
**Status:** validated live **bit-exact (0 ULP)** on GZLJ01 (savestate 7): the in-line cut 2026-07-06,
the **diagonal (aimed) thrust** 2026-07-07. Modeled on the Python path
(`LandState(native=False, sword_drawn=True)`); the native `LandCore` carries the same arm
(`CutAnimData`, `_cut_init`, `_proc_cut`, `seed_cut`) on its coupled-actor surface, which no public
`step` currently dispatches - so a native-only run does not cut.
**Source:** decomp `d_a_player_main.cpp:2488` (`posMove` `m34C2==1`) + `d_a_player_sword.inc:690`
(`procCutF`/`procCutA`) + `:404` (`changeCutProc`/`getCutDirection`); live captures. Constants:
[reference/constants.md#land-sword-cut-roll-stab](../reference/constants.md#land-sword-cut-roll-stab).

---

The **fastest single-frame ground displacement** and the mechanic that reaches a wall-corner
[seam clip](seam-clip.md): fire a **sword cut out of a [FRONT_ROLL](roll.md)**. A roll alone caps at
26 u/frame (below the 35 u seam-clip floor); the cut stacks a root-motion lunge on top. Two variants,
both live-validated bit-exact:

- **CUT_F** (`daPyProc_CUT_F_e`, forward thrust): draw the sword (B while walking; the first B is the
  unsheathe, no slash, the sword is then out), run up to roll speed, roll (A), then **hold up + B on the
  first frame the roll accepts it**, giving a single-frame **49.22 u** lunge.
- **CUT_A** (`daPyProc_CUT_A_e`, vertical/overhead slash): same setup but the thrust is **L + B with a
  neutral stick** (L = targeting via the ATN path, so it does NOT need the digital-L button the pipe/DTM
  can't inject; analog-L targeting suffices). Same first-frame **49.22 u** (identical root motion).

## Where the 49.22 comes from (`posMove` `m34C2 == 1`)

A cut's per-frame displacement is **`speedF` (the `mNormalSpeed` foot term, along `current.angle.y`)
PLUS the animation's joint-0 (root) translate DELTA** (`sp5C = m3700(t) - m3700(t-1)`, rotated by
`shape_angle.y`). `procCut*_init` sets **`m3700 = 0`**, so on the cut's FIRST frame the delta is the
*full* root translate at the anim's start frame (`ANM_CUTF/CUTA` frame 4.0 → `m3700.z = 23.220`), and
it **stacks onto the carried roll `speedF` (26)**: `26 + 23.220 = 49.220`. That is why only a roll (26,
below the 35 u floor) can't clip but the roll+thrust can. The "first possible frame" (the earliest B
that produces the cut) carries the full **26**; one frame later carries `26 - 2.5` (the roll's decel),
giving 46.72, 44.22, … .

## `mNormalSpeed` during the cut (`procCutF/A`)

The `ANM_CUT` frame ctrl starts at 4.0, advances `+1.2/frame` (`EMode_NONE`, end 19); on
`checkPass(field_0x28=6.0)` `mNormalSpeed = |speedF|·0.2 + add` (CUT_F add 8.0, CUT_A add 10.0), then
`cLib_addCalc` decel each frame (CUT_F maxStep 0.95, CUT_A 2.6). `getFrame() > field_0xC` (CUT_F 17.0,
CUT_A 16.0) → `checkNextMode(1)` → **WAIT** (Link returns to idle). The root-motion `m3700` is the
`cutf.bck`/`cuta.bck` joint-0 translate, evaluated by the J3D keyframe engine
([`core.anim.j3d_eval`](../../tww_sim/core/anim/j3d_eval.py)), **0 ULP** vs the live `m3700` (no blend:
a cut is `setSingleMoveAnime`, MOVE1 NULL).

## Steering the thrust: a diagonal aim, and its range

The thrust direction has **two independently-steered parts**, because the lunge frame and the tail
read *different* angles (see [`posMove` `m34C2==1`](#where-the-4922-comes-from-posmove-m34c2--1): the
foot term is along `current.angle.y`, the root-translate delta along `shape_angle.y`):

- **The 49.22 lunge fires along the ROLL facing and CANNOT be steered on a forward roll.** The lunge
  is the cut's *init* frame; `procCutF/A` (the proc that turns `shape_angle.y`) does not run until the
  *next* frame (the main loop runs the proc once per frame, and `procCut*_init` only swaps in the proc
  pointer). So on the lunge frame `shape_angle.y` is still the roll's facing. To get a **diagonal
  49.22**, aim the *roll itself* diagonally (the whole roll-stab rotates); the lunge then points along
  that facing. Live 0-ULP for any facing (the root/foot rotation is `_cM_ssin_s16(facing)`).
- **The tail (frames 2+) snaps to the thrust aim.** A DIAGONAL thrust (roll **straight forward**, then
  push the stick up/left or up/right + B) latches `m34D4` = the stick target `m34E8` sampled at the
  thrust. On the first cut proc frame `procCutF/A` runs `cLib_addCalcAngleS(shape, m34D4, mTurn.f4=30,
  mTurn.f0=0x3CDF, mTurn.f2=0x1F40)`; the `0x1F40` min-step dwarfs any in-range diff, so `shape=travel`
  **snaps to the aim in one frame** and holds. The entry lunge stayed in-line (straight 49.22); the
  whole ~40u decel tail rotates by the aim. Live: X=96 up-left → tail rotated +8.01°, X=64 → +23.46°,
  bit-exact (the tail is the straight tail rotated by exactly the aim).

**Range:** the stab dispatches `CUT_F` only while `|aim - roll_facing| < 0x2000` (±45°;
`getDirectionFromAngle` FORWARD). A larger aim dispatches `CUT_L`/`CUT_R` (`getCutDirection`): a
different move, not this cut. So the diagonal-tail aim range is **±0x2000 (±45°)** off the roll
direction (constant [`CUT_DIR_FWD`](../reference/constants.md#land-sword-cut-roll-stab)).

**Dead end (do NOT re-chase): the side cuts `CUT_L`/`CUT_R` do NOT redirect the big lunge.** Same
init-frame rule (`procCutL/R_init` sets `m34C2=1`, `m3700=0`, but not `current.angle.y`; the turning
proc runs frame 2+), so their first frame is the **identical 49.22 STRAIGHT lunge** along the roll
facing (live X=0 hard-left thrust → CUT_L proc 0x44, first frame 49.2202 at ang 0). And their tail is
*weaker* than CUT_F (`checkPass` add 1.0 vs 8.0 → `mNormalSpeed` collapses to ~5, ~10u tail frames),
so switching to them past 45° redirects *less*, not more. **No cut variant redirects the 49.22; the
only way to aim the big frame is to aim the ROLL** (an aimed roll, above). `cutl/cutr.bck` are
deliberately NOT parsed into the sim (no benefit; would be dead weight).

## Simulation

[`tww_sim.land`](../../tww_sim/land/land.py) `CUT_F`/`CUT_A`,
`LandState(native=False, sword_drawn=True)`. The roll→cut trigger lives in `_roll_exit`: a buffered
sword button (B) + `sword_drawn` at the roll's early-exit (`getFrame() > 17`) routes to the cut (L held
→ CUT_A) instead of MOVE, carrying the roll's full `speedF`. The whole trajectory (the 49.22 lunge
through the decel tail to the WAIT idle frame) is **bit-exact end to end** (`tests/test_land.py::
test_rollstab_cut_bit_exact`, golden `tests/golden/land_rollstab_cuts.json`; `LandState.enter_cut(cut,
aim=None)` runs the entry frame programmatically for the seam-clip pipeline). Pass `aim=<s16 world
angle>` for a diagonal thrust; it must be within `±0x2000` of the roll facing or `enter_cut` raises
(it would be CUT_L/R). The steered trajectory is live 0-ULP across the range
(`tests/dolphin/spotcheck_rollstab_diag.py`, GZLJ01 flat arena, 2026-07-07) and locked offline by
`test_rollstab_diag_model_invariants`. Cut keyframe data (dev-supplied, gitignored
`_generated/anim/link_anim_cuts.json`) is regenerated by `harness/anim/parse_bck.py which=cuts`.

**Open:** the native (Cython) `LandCore` holds the cut arm but never advances it - `_proc_cut` has
no call site and `step` never raises the B trigger - so wiring the dispatch is the remaining work.
Separately the toe stream isn't warmed during a cut, so a *post-cut walk* isn't bit-exact (the cut
itself, ending in idle, is); model the cut's foot-chain pose to close that.

## See also
- [roll-cut-thrust-floor.md](roll-cut-thrust-floor.md) - which roll steps a B press can dispatch this cut on.
- [cut-frame-co-swing.md](cut-frame-co-swing.md) - where Link's Co centre is on the frame the cut consumes.
- [Land movement overview](land-movement.md) · [roll](roll.md) (the FRONT_ROLL it fires from).
- [seam-clip](seam-clip.md): how the 49.22 lunge clips a wall corner ·
  [actor-push](actor-push.md): the Tetra Co-push that supplies the extra overlap.
- Live gates `tests/dolphin/spotcheck_rollstab.py` (in-line) + `spotcheck_rollstab_diag.py` (diagonal).
