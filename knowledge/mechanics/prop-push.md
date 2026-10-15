# Bomb and pot B-drop pushes

**Question:** What creates the push, why does its direction depend on the
animation position, and what must an offline seam-clip proof simulate?

**Status:** The release animation, prop motion, Co overlap, rank split, deferred
Link correction, console trig, and both background-collision passes are ported.
The first-principles model matches two live free-space endpoints bit-for-bit:
animation position 51 at `(-157.694931, -739.113281)`, facing 4683, and
animation position 11 at `(-566.3359375, -1365.3570556640625)`, facing 33952.
The CSV is no longer used to generate or classify clips.

## B drop is not GRABTHROW

The decisive branch is `daPy_lk_c::checkNextActionGrab` in
`d_a_player_grab.inc`. For an ordinary carried bomb or small pot the action
status is `DROP`. Pressing B with the sword equipped calls `freeGrabItem()` and
then `setAnimeEquipSword(0)`. It calls `procGrabThrow_init(1)` only when the
action status is `THROW`.

Consequently a normal B drop does **not** use GRABTHROW's horizontal speed 19
or vertical speed 34:

- Bomb: `procCarry_init` set `speedF=0` and zeroed `speed`. Once carry clears,
  `procCarry` enables Co through `procWait_init`, then `procWait` moves the bomb
  with zero horizontal speed.
- Small pot: `mode_carry_init` also set `speedF=0`. Once carry clears,
  `mode_carry` sees that `speedF` is not positive and enters `mode_wait`, not
  `mode_drop_init`. The small pot's throw speeds 36/27 are not assigned.

This is why normal bomb and small-pot B drops have the same horizontal push
family. Their actor code and vertical collision shapes differ, but each exposes
a radius-30, weight-200 Co body at the X/Z position last written by
`setGrabItemPos`.

## Source-ordered push

The horizontal displacement is ordinary actor-vs-actor Co correction:

1. On the last held update, `setGrabItemPos` writes the prop actor to the
   midpoint of Link's animated hand joints.
2. B clears carry. The prop runs its own movement and its own background
   `mAcch.CrrPos` before registering Co.
3. A bomb registers a sphere of radius 30 centered at actor Y+30. A small pot
   registers a cylinder of radius 30 and height 60 at actor position.
4. Link registers his body Co cylinder. Its X/Z center is the midpoint of the
   root and neck joint translations. Its radius is 30 after carry is cleared;
   its height is derived from the neck and toe joints.
5. Scene Draw calls `dComIfG_Ccsp()->Move()`. If the vertical gate passes, the
   horizontal overlap depth is `60 - center_distance`.
6. Link's weight 120 is rank 5 and the prop's weight 200 is rank 7.
   `rank_tbl[5][7]` gives Link 90 percent of the overlap correction.
7. `dCcS::SetPosCorrect` stores that vector in Link's `mStts.m_cc_move`. It also
   adjusts the registered shape center for the rest of the Co pass; it does not
   immediately write Link's actor position.
8. On Link's next Execute, `posMove` adds `m_cc_move` to `current.pos`, clears
   it, and then Link's `mAcch.CrrPos` resolves the `old.pos -> current.pos` wall
   sweep. That resolved position is the seam verdict.

The measured magnitude follows from this geometry. With two radius-30 bodies
whose centers are about 1.4 units apart, `(60 - 1.4) * 0.90` is about 52.7.

## Why animation position changes direction

The held prop follows the hand midpoint while Link's Co center follows the
root/neck midpoint. Their relative X/Z offset changes during GRABWAIT. On the B
execute, `freeGrabItem` also resets the upper animation and starts the sword
equip transition. The prop remains at the position produced by the previous
held pose, while Link's body cylinder is subsequently built from the
release-transition pose.

`setAnimeEquipSword(0)` installs `REST` in upper slot 2 with the cut HIO values
(reverse rate `-1.8`, start 1, explicit end 14, morph 1). GRAB_WAIT carries
`ModeFlg_00000001`, so `jointCB0` suppresses the normal equip-animation ratio
toggles. The release draw is therefore GRABWAIT for PART_UNDER (root, center,
waist, and legs) and REST at frame `13.999` for PART_UPPER (body through neck).

For a displayed animation position `N`, the source-ordered pose is:

- held prop hand midpoint: GRABWAIT frame `N + 1`;
- collision root/center under pose: GRABWAIT frame `N + 2`;
- collision upper-body pose: REST frame `13.999`.

Frames wrap at GRABWAIT's 60-frame loop. This is implemented by
`decomp_b_drop_pose` and was recovered without fitting the CSV: the live paused
bomb actor at animation position 11 stored the frame-12 hand midpoint exactly,
and the mixed frame-13/REST Link center reproduced the resulting endpoint.

An exact animation-position generator therefore needs all of the following:

- the previous GRABWAIT hand midpoint;
- under/upper joint ownership and blend ratios;
- the upper-animation reset and old-frame morph caused by B;
- the release-frame root/neck/toe matrices;
- separate f32 world transforms at the requested actor position and facing.

Evaluating one GRABWAIT BCK for both centers is not equivalent. It does not
reproduce the 60 measured displacement directions.

## Why the CSV endpoint is not proof

The supplied CSV records Link's final free-space push at actor `(0,0)` and
facing 0. Computing `old + rotate(csv_vector)` near a wall omits two effects:

1. The released prop runs its own background `CrrPos` before Co. A wall may
   move its center, changing both the push direction and overlap depth.
2. The game transforms Link's and the prop's centers separately into large f32
   world coordinates, then subtracts them and recomputes Co. Rotating an
   already measured local vector skips that translation rounding. A difference
   near 0.001 unit can decide a seam result.

Facing must also use the console `cM_ssin`/`cM_scos` lookup table, not host
`sin`/`cos`. The documented GanonM facings 36256 through 36271 all select one
lookup bucket and therefore produce the same transform.

## Legacy calibrated reconstruction

The earlier implementation used an intermediate measured model:

1. Invert a measured free-space push using the radius sum and 90-percent split
   to recover the prop-to-Link Co center separation.
2. Generate the prop's local X/Z from the previous `setGrabItemPos` hand
   midpoint. Place Link's Co center relative to that prop using the measured
   center separation; the GRABWAIT root/neck/toe model still supplies Link's Y
   base and height.
3. Transform Link and the prop independently into f32 world coordinates with
   console matrix and trig rules.
4. Run the complete prop-BG, Co, deferred-Link-BG pipeline below.

This is implemented by `calibrated_b_drop_pose` plus
`b_drop_collision_step`. It does not inject the CSV displacement into Link.
The Co push is recomputed after any prop wall correction. On the documented
GanonM setup it changes the raw X/Z endpoint by roughly 0.001 unit relative to
the direct-vector calculation, which is enough to change full `mAcch.CrrPos`
from a wall rejection to a stable crossing.

That model remains only for historical regression diagnostics. It is not used
for generation: a world-position test differed from the game by about
`0.00464 X` and `-0.00183 Z`, enough to invalidate a seam result.

The two centers must be anchored before either world transform. Deriving a
world-space held prop first and subtracting a rotated separation afterward is
not equivalent: it couples independent f32 rounding paths. That older shortcut
produced reported false setups in GanonM. A later investigation found a second
acceptance bug: the generator computed the calibrated endpoint but classified
it with the simplified `crr_pos_walls` result. That path could call a deep
LineCheck projection a clip even when the already-computed player `Acch` result
reported a wall hit. The generator now accepts only
`b_drop_collision_step.link_after_bg`, with no Link wall hit and a stable full-
`Acch` follow-up.

The seam-only generator does not load the CSV. For each animation position and
console trig bucket it runs one first-principles reference step, solves
`old = seam - t * push`, and searches the binary32 phase along that trajectory.
Each result is checked for a floor, initial wall stability, prop BG, Co, Link
BG, follow-up stability, and adjacent angle-bucket rejection.

The backward solve lands near a binary32 boundary, so its rounded start is not
automatically the usable start. The generator first aims about `0.2` unit past
the seam, then searches the neighboring X/Z f32 lattice. The rotated measured
endpoint is retained only as a diagnostic; it can neither accept nor veto a
candidate. Acceptance requires the calibrated prop-BG/Co/Link-Acch path to
cross with no Link wall hit and remain stable on a follow-up full `Acch` pass.
It prints nine decimal places and the raw f32 bit patterns. On the
user-validated GanonM bisector setup, the usable boundary was one X ULP lower:

```text
rejected in-game: X = 572.7384033203125
works in-game:    X = 572.73834228515625
Z = -1378.59912109375, animation position 5, facing 29344..29359
```

`validate_calibrated_table` gates every loaded table by reconstructing and
rerunning Co in free space. The supplied 60-row table round-trips for both bomb
and small pot with a worst X/Z vector error below `8e-6` units.

Known GanonM room 0 regression:

```text
seam:        586.023132, -50.000000, -1413.401733
Link old:    596.77209472656, 0, -1378.4049072266
CSV row:     4
input label: press B at animation position 5
accepted:    facing 36256 through 36271
rejected:    facing 36255 and 36272
```

For facing 36256, the invalid direct endpoint is approximately
`(581.288818, -1428.810913)` and full Link `mAcch.CrrPos` wall-corrects it. The
calibrated-center Co recomputation produces approximately
`(581.290161, -1428.811279)`; full `mAcch.CrrPos` reports no line or wall hit and
the follow-up is stable. That 0.001-scale difference is why the old finder
looked plausible but did not reproduce in game.

```powershell
python -m harness.collision.drop_push_clip `
  object=pot_small `
  seam=-584.995605,16.695562,-1413.985596 `
  cache=_generated_ganonm_r0_iso_region.json `
  box=-650,-500,-50,100,-1500,-1300 `
  frame=11
```

## Offline proof pipeline

A trustworthy setup prover must run this complete sequence for every
`(object, animation position, facing, old position)` candidate:

1. Generate the exact previous-pose held-prop center and release-pose Link Co
   center/height.
2. Transform those centers separately with console f32 matrix and trig rules.
3. Run the released prop's movement and background `CrrPos` against the room.
4. Build the bomb sphere or pot cylinder at the corrected prop position.
5. Run the vertical gate, X/Z overlap, and rank-table split to obtain Link's
   pending `m_cc_move`.
6. On the following Link update, add that pending move and run Link's full
   background `mAcch.CrrPos` against the ordered room walls.
7. Require an established standable old position in front of both seam walls,
   a resolved position behind both incident walls, and a stable follow-up
   correction.
8. For generated setups, accept only the independently transformed Co endpoint
   after full Link `Acch`; keep the rotated measured endpoint diagnostic-only.
9. Reject missing seams, unreachable old positions, collision-flag shortcuts,
   and any result based only on a direct CSV endpoint.

`decomp_b_drop_pose` implements steps 1-2 and
`b_drop_collision_step` implements steps 3-7.
`center_separation_from_measured_push` only inverts a free-space row for
legacy calibration diagnostics.

## Thin OOB seam landing

An ordinary clip verdict does not imply that Link can stand at the destination;
it only proves the wall traversal and follow-up wall stability. The GUI's OOB
landing mode adds four destination requirements:

1. The resolved X/Z lies behind both incident wall planes.
2. Its X/Z distance from the target vertical seam is at most the requested
   tolerance (default `0.005` unit).
3. The ground mesh supports the resolved X/Z at exactly the starting floor Y.
4. A full zero-motion follow-up `Acch` pass leaves the destination stable.

This mode searches release phases immediately around `1.0`, where almost the
entire prop push is spent reaching the seam. Its phase grids are much finer
than the ordinary clip search because a `0.002` phase step moves a roughly
53-unit push by about `0.1` unit and skips the OOB strip.

Known offline proof for GanonM room 0, target seam
`(-584.995605, 16.695562, -1413.985596)`:

```text
object: bomb or small pot
animation position: 11
facing: 41472 through 41487
old: (-538.1468505859375, 0.0, -1389.37939453125)
resolved: (-584.9979248046875, 0.0, -1413.98681640625)
XZ distance from seam: 0.002621237342063287
wall depths: 0.0023193359375, 0.001220703125
landing floor Y: 0.0
follow-up stability delta: 0.0
```

The same first-principles pose, prop BG, Co, and Link BG pipeline is used; the
CSV is not loaded. As with every newly generated setup, the offline result
should receive one in-game confirmation before being treated as live-validated.

## Required validation gates

The remaining validation gates are:

- Optionally compare all 60 historical CSV rows as validation only; never feed
  those rows into candidate generation.
- Reproduce the documented GanonM room 0 setup at
  `(596.77209472656, 0, -1378.4049072266)`, animation position 5, and facings
  36256 through 36271 without disabling wall or line collision.
- Reject adjacent facing buckets and deliberately shifted old positions.
- Always run `center -> prop BG -> Co -> Link BG`; never use a direct measured
  endpoint as the proof result.
- Confirm a newly generated setup in game. Free-space endpoint generation is
  already bit-exact in the two independent live cases above.

## Decomp sources

- `src/d/actor/d_a_player_grab.inc`: `setGrabItemPos`, `freeGrabItem`,
  `checkNextActionGrab`, `procGrabThrow_init`.
- `src/d/actor/d_a_bomb3.inc`: `procCarry_init`, `procCarry`, `procWait_init`,
  `procWait`, bomb sphere setup.
- `src/d/actor/d_a_tsubo.cpp`: `create_init_cc`, `mode_carry_init`,
  `mode_carry`, `mode_wait_init`, `mode_drop_init`.
- `src/d/actor/d_a_player_main.cpp`: `posMove`, `setCollision`, player Execute
  ordering.
- `src/d/d_cc_s.cpp`: `rank_tbl`, `GetRank`, `SetPosCorrect`.
- `src/d/d_s_play.cpp`: scene Draw call to `dComIfG_Ccsp()->Move()`.
