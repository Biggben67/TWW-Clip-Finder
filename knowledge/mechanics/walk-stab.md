# Walk stab (sword thrust out of a walk): the no-roll seam clip

**Answers:** What is the walk stab, and how does it differ from the [roll stab](roll-stab.md)? How far
does its lunge reach, and which seams can it clip without a roll? Why is the thrust delayed several
frames when Link is holding an item? How does the one-frame L-target speed it up?
**Status:** decomp-grounded + **live-delivered 0-ULP** (kaze r11, savestate anchor
`kaze_r11_walkstab@twwgz.sav`, 2026-07-13). The min-clip geometry is computed, the equip-change delay is
live-measured, the from-rest sim is **BIT-EXACT (0 ULP) in position AND facing**, and a pure-sim solver
hit (found entirely offline, no calibration) was delivered as a clean DTM and **clipped the seam live**:
the CUT_F fired at N=13 with `old`/`new` bit-for-bit the sim's prediction and Link went OOB through the
seam. A second, razor-acceptance corner (seam352, interior 155.4) delivered 2026-07-20 after the
dispatch-frame travel fix (below).
See Simulation. Regression: `tests/test_walkstab_clip.py` + golden `tests/golden/walkstab_deliver.json`.
**Source:** decomp `d_a_player_main.cpp:4087` (`checkNextActionFromButton`), `:3946`/`:3959`
(equip-anime completion), `:3436`/`:3499` (the take/rest anime setup), `d_a_player_sword.inc:404`
(`changeCutProc`); HIO `daPy_HIO_item` (`d_a_player_HIO_data.inc:293`); live captures + the
seam-clip scanner (`harness/collision`). Constants:
[reference/constants.md#land-sword-cut-roll-stab](../reference/constants.md#land-sword-cut-roll-stab).

---

The walk stab is the [roll stab](roll-stab.md) without the roll: run up to walking speed, then thrust
(forward stick + B) so the CUT_F fires out of a MOVE instead of a FRONT_ROLL. The single-frame lunge is
the same shape, only the carried speed differs.

## The lunge (same CUT_F, lower carried speed)

The cut's first-frame displacement is `speedF (carried in) + the CUT_F joint-0 root translate 23.220`
(the [roll-stab](roll-stab.md#where-the-4922-comes-from-posmove-m34c2--1) `posMove m34C2==1` stack;
`procCutF_init` zeroes `m3700` so frame 1 gets the full 23.220). A roll carries speedF 26 (lunge
**49.22**); a capped walk carries speedF 17, so the walk-stab lunge tops out at **17 + 23.220 = 40.22**.
Any sub-cap walk gives a shorter, tunable lunge down to a standstill stab's 23.22.

**The two terms aim at DIFFERENT angles on the dispatch frame** (live RAM-verified 0-ULP, 2026-07-20).
On the frame the buffered B fires the cut out of a walk, `procMove` (d_a_player_main.cpp:6221) runs
`setSpeedAndAngleNormal` -- the `current.angle.y` (travel) chase -- BEFORE `checkNextMode`'s
`checkNextActionFromButton` dispatches `procCutF_init`, and the init never writes `current.angle.y`
(only `procCutF` frame 2+ snaps it to shape). So `posMoveFromFootPos` fires the speedF foot term along
the **just-chased travel**, while the root-translate delta rotates by **shape/facing**. A walk whose
travel has not finished converging to facing (e.g. a start-crawl leaves a ~100-hw residue over ~16
frames) lunges measurably (~0.03u) off the facing line -- fatal on a razor-acceptance corner, invisible
on a dense one and on roll stabs (`_roll_init` sets travel = facing). Sim: `LandState.enter_cut_from_move`
(the dispatch-frame prefix + entry lunge); gate `tests/test_seam352_walkstab.py` (rawcut golden).

## Which seams a walk stab can clip (the displacement floor)

A convex-corner seam clip needs Link's settled `old` to sit `WALL_R / sin(interior/2)` in front of the
tip (the r=35 wall cylinder cannot settle closer), so the minimum one-frame displacement is a hard
geometric floor (`harness/collision/gap_search`, `seam_scan.disp_floor`):

    min_disp = 35 / sin(interior/2)      interior = 180 - acos(nA . nB)   (the two wall normals)

**Shallower (flatter) corners have a LOWER floor** (the cylinder tucks closer to a near-flat tip), so:

| corner interior | floor | reachable by |
|-----------------|-------|--------------|
| >= ~121 deg     | <= 40.22 | **WALK stab** (no roll) |
| ~91 - 121 deg   | 40.22 - 49.22 | [roll stab](roll-stab.md) |
| < ~91 deg       | > 49.22 | neither bare lunge; needs an [actor push](actor-push.md) |

Data points: the Tetra corner (interior 90.57 deg) needs a push; the kaze roll-stab seam (~110 deg)
needs the roll; a near-flat seam is walk-clippable. This is a NECESSARY floor (the exact clip also needs
the f32 acceptance dust and the `old` band, so a real seam can want a hair more), but it is the governing
lever for "roll or not."

**The centralized scanner** (`harness/rollstab/thrust_scan.py`) turns this table into a decision: given
an anchor + a seam it computes the floor, picks the technique tier, then FEASIBILITY-gates on run-up
space -- it simulates the straight approach from the anchor (`rest.rest_state`, C-down pin, per-frame
re-aim at S) and checks the required speedF (WALK: `floor - 23.220`; ROLL: the 17 cap) is built while
`old` is still `>= floor` from the tip. Fewest frames wins, so it prefers WALK when it fits the space,
else ROLL, else reports INFEASIBLE (`push` = floor too steep, or `space` = no run-up), then dispatches
the matching solver. Gate `tests/test_thrust_scan.py`.

**Worked case (kaze r11, the walkstab anchor).** The wall chain Link faces has a convex seam at
`S=(9030.955, 1385.858)` (poly 803 x 802, interior **168.97 deg**, near-flat). Exact minimum clip
displacement = **35.02 u** (f32-lattice `gap_search.min_f32_clip`, at Link's facing and the bisector
alike; floor 35.16 confirms it), so **min speedF ~= 11.8** (35.02 - 23.22), well under the 17 cap: it
clips from a plain walk, no roll, no aim change. The acceptance here is DENSE (hundreds of clipping f32
`new` in a small box), not the kaze roll-stab razor dust. All three seams in this chain clip near 35 u.

## The item put-away delay (why the thrust comes out later)

When Link holds a non-sword item (here the Wind Waker), the thrust is delayed because the game must
change the equip to the sword first. On the sword press `checkNextActionFromButton`
(`d_a_player_main.cpp:4087`) does NOT cut while `checkEquipAnime()` is true (`:4194`); the stow/draw
upper-body anime runs first (the WW stows via `LKANM_BCK_TAKEL`, `setAnimeUnequipItem` `:3499`), and only
when its frame ctrl passes the completion frame (`:3959`; single-item `mItem.field_0x20 = 4.0`, sword
`REST` 7.0) does the game run `deleteEquipItem` + `setSwordModel` and set `daPyRFlg0_UNK80`, so the NEXT
frame's `checkNextActionFromButton` fires the buffered `changeCutProc()` -> CUT_F. The delay is
**item-independent** (it is the stow-then-draw, common to every item).

**Live-measured delay = 4 frames**, constant (B edge at fN -> CUT_F at fN+4; verified at two press
frames). Crucially the equip anime is UPPER-body only, so **the lower body keeps walking through the
delay** (proc stays MOVE, speedF holds/builds). So the B-press TIMING sets where `old` lands: the cut
fires 4 walk-frames later at the then-current speedF. If Link reaches the wall before the cut, CrrPos
bleeds his speed, so the press must be timed to fire the cut at the target `old` before wall decel.

**Sword OUT vs sheathed (the DTM B-frame).** The put-away delay applies only when an item (or sheathed
sword) must be swapped to the drawn sword first. With the **sword already OUT** there is no equip anime,
so the cut fires with just the 1-frame DTM buffering: the DTM presses B at frame **N-1** (CUT_F at N).
Item held / sword sheathed: B at **N-5** (4-frame put-away + 1-frame buffer). `walkstab.deliver` derives
this from the anchor's captured equip state (`sword_drawn`), so both walk methods are supported.

## The one-frame L-target (faster accel) and the camera

A one-frame **L-target on frame 1** enters ATN_MOVE for that frame, injecting speedF at the side-branch
`ATN_SPD = 5.0` instead of the walk's `F14 = 3.5` (a permanent ~+5.7 position lead; full mechanism in
[roll-launch.md](../strategy/roll-launch.md#why-l-on-frame-1)). It reaches the needed speedF
sooner, shortening the run-up. **Hold C-down (`substickY = 0`) on that L frame** to keep the camera in
free-cam so the auto-cam does not swing (a swinging `csangle` rotates the stick->world mapping and drifts
Link's facing, observed ~33 u16/frame while walking; free-cam pins it).

## Simulation

**The from-rest sim is BIT-EXACT (0 ULP) in position + facing** (`rest.rest_state`, gated by
`tests/test_walkstab_rest.py`). The driver is walk-N-frames-then-`enter_cut(CUT_F)` from the seed; the
4-frame equip delay is **delivery-only** (the lower body keeps walking, so the DTM presses B at frame
N-5 -- 4-frame item put-away + 1-frame DTM buffering).

**Root cause of the (former) "walk-entry foot residual" -- the WRONG ANIM SET, not a foot-FK gap
(session 31, corrects session 30/dead-end #28).** The under-body walk/dash anim set is chosen by the
held item: `getAnmData` (`d_a_player_main.cpp:12950`) returns the sword table (WALKS/DASHS) only when
`mEquipItem == daPyItem_SWORD_e` (0x103). This anchor holds the Wind Waker (`mEquipItem` 0x22), so the
base WALK/DASH legs apply. WALK and WALKS share leg keyframes (a WAITS<->WALK entry is bit-identical
either way), but DASH and DASHS differ, so a sword-drawn assumption drifted the plant toe ~0.0024u the
instant DASH blends in (regime 2, the m3598<1 frame) -- exactly the session-30 "residual." Every
`jointBeforeCB`/`jointCB1` lean + foot-plant IK term (waist tilt `m34E0`, CLOTCH `field_0x030`, leg
bends `field_0x008/00A/002`, the MOMI face-joint sway) is **zero on this flat ground** (live-captured),
ruling them out. `rest.rest_state` now seeds `sword_drawn` from the anchor's captured equip state.

**The acceptance is a perpendicular RAZOR.** `harness/collision/gap_search`: the perp offset window
(`rho`, the cut ray's distance to `S`) is ~6e-4u at the corner bisector (sub-ULP at coord 9031, so
f32-striped dust like the [roll stab](../strategy/seam-clip-solver.md)); ~**2e-4u** at the walk facing;
the AIM window is wide (**+-40 deg**, bisector ~3537) and the displacement window wide (**35.5-40**). So
the razor is only the perpendicular offset. The walk-up bearing (~to S) differs from the bisector, so
walk and cut decouple by a turn.

**The razor is a GAP in the reachable-`old` byte lattice -- the search needs a K=3 crawl.** The
reachable `old` set (from octagon-clamped, byte-quantized deliverable sticks) is a coarse lattice; a
single-frame or K=2 crawl floors the perpendicular resolution at `min|perp|` **~1.3e-3u -- ~13x the
razor half-width**, so the razor falls between lattice points (dead-end #6 class) and a K<=2 enumerate-
and-test finds nothing. Each START-CRAWL frame (a partial-magnitude stick, octagon INTERIOR) densifies
the perp lattice ~20x (K=1 ~0.03u -> K=2 ~1.3e-3u -> **K=3 ~2e-5u**, below the razor), because an
interior byte is not clamped (every byte is a distinct decoded direction, unlike a FULL-mag arc/cruise
stick, which clamps and collapses). So the along variance is the crawl magnitudes and the fine perp
fill is the 3rd crawl frame's BYTE nudge. `solve_focused` (the freeze-solver pattern): bracket
`|perp_ray|` coarsely (cheap, no CrrPos), drill the byte-nudged 3rd crawl frame + test the EXACT
`genuine_clip`, then re-sim WITH walls and keep only `wall_hit==False` cuts (`old` is then the true
pre-brake position, speedF still 17). It finds wall-faithful genuine hits in < 2 min. Facing is
bit-exact from rest under the C-down camera pin (`substickY=0`; a centered stick lets the auto-cam
swing and drift facing).

**Delivery is LIVE, 0-ULP (no calibration).** Because the from-rest sim is bit-exact, a genuine offline
clip is a true one-shot -- the live `old` lands exactly on the sim's, on the razor. `deliver()` shipped
the top hit as a clean DTM (C-down every frame; B at frame N-5 = the 4-frame item put-away + 1-frame DTM
buffering, firing CUT_F at frame N; never advancewith): CUT_F fired at N=13, `old`/`new` were bit-for-bit
the sim's prediction, the clip is genuine, and Link went OOB through the seam (proc 0x24, `pos_y` below
the floor). Regression `tests/test_walkstab_clip.py`; live golden `tests/golden/walkstab_deliver.json`.

## See also

- [roll-stab.md](roll-stab.md) (the same CUT_F lunge fired out of a roll; 49.22 vs 40.22) ·
  [seam-clip.md](seam-clip.md) (why the corner clips, the f32 dust) ·
  [actor-push.md](actor-push.md) (the push tier for sub-91-deg corners).
- [roll-launch.md](../strategy/roll-launch.md) (the L-target ATN_MOVE boost) ·
  [land-movement.md](land-movement.md) (the walk/MOVE baseline).
