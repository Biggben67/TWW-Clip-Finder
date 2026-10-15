# Roll launch (fastest standstill → roll-chain)

**Answers:** From a standstill, what is the fastest input sequence to get into a high-speed roll
chain? Why hold L on the first frame? Why does a slight up-left/up-right (off-axis) stick beat
straight-up? Why does the frame-6 roll cap at ~25.9 instead of the full 26? Can the camera help?
**Status:** DECOMP-GROUNDED / SIM-CALCULATED (**DTM/live validation pending**). The potential-speed
ceiling is exact; the final roll speed is animation-seed-dependent and must be calculated from a
captured rest seed. Calculator: `python -m harness.rollstab.roll_launch`.
**Source:** decomp HIO `mAtnMove`/`mMove` constants + `_update_atn_direction` (`setBlendAtnMoveAnime`
@3280) + `procFrontRoll`; sim exploration 2026-07-06 (native `LandCore`, seeded from savestate 6 =
the resting-anchor defaults). Constants live in [`constants.md#land-movement`](../reference/constants.md#land-movement).

---

## The sequence (from a forward standstill)

1. **Frame 1: L-target + the exact side-gate stick.** The potential-speed optimum is clean-DTM
   `(151,199)`, which decodes to offset `-1481`. L is held only here.
2. **Keep that same full-magnitude stick for three more acted frames.** Frame 2 receives the SIDE
   acceleration; frames 3-4 receive normal MOVE acceleration without a cosine loss.
3. **Press A on the next acted frame.** This is the one-frame-early roll family commonly called the
   frame-6 launch. The two-frame controller pipeline shifts when inputs are authored, but does not
   change this acted-frame sequence.

## Why L on frame 1

From a standstill, holding L enters `ATN_MOVE`. The **first ATN frame** takes the side branch
(`mDirection` is still `NONE` at entry), whose maximum is **`ATN_SPD = 5.0`** rather than the walk's
**`F14 = 3.5`**. The required side-gate angle applies a cosine, so the exact first injection is
`5*cos_s16(-1481) = 4.949206829`. This head start is a *permanent position lead* because
the roll chain equalizes speed afterward (a higher `speedF` earlier is never repaid). This is the
[ATN_MOVE tier](../mechanics/brakeslide-ebs.md#brakeslide-l-held) engaged for one frame from rest.

## Why the slight diagonal beats straight-up (the +2.4)

`_update_atn_direction` picks the next frame's `mDirection` from `cos(travel − facing)`:

- `cos ≥ ATNB_COS_FWD (0.99)` → **`DIR_FORWARD`** → next ATN frame uses the walk path (**+3.5**).
- otherwise → a **SIDE** direction → next ATN frame uses the side branch (**+5.0**).

Straight-up keeps travel = facing → `cos = 1` → FORWARD, so the next frame gets only normal MOVE
acceleration. The exact off-axis input makes `cos(travel-facing) < 0.99`, selecting **SIDE** for the
second ATN frame. Keeping the same target makes that frame's travel delta zero, so it injects the
full 5.0. The two following MOVE frames add the maximum 3.5 each.

The threshold is `arccos(0.99) ≈ 8.11°`, but only the game's decoded s16 angle and cosine table
matter. An exhaustive scan of every DTM-deliverable byte pair finds `(151,199)` at offset `-1481`,
cosine `0.989841342`, as the closest full-magnitude target below the gate. The older top-edge
`(94,254)` input is valid but weaker. The cosine table is not perfectly sign-symmetric.

## Why the frame-6 roll caps at ~25.9, not 26

Roll speed = `clamp(speedF·1.5 + 0.5, 5, 26)`; the 26 cap needs `speedF ≥ 17` at entry. After four
acceleration frames, the exact potential-speed sequence is:

`4.949206829 -> 9.949207306 -> 13.449207306 -> 16.949207306`

Treating `speedF == mNormalSpeed` gives the strict HIO ceiling **25.923810959**, but the early walk
still has a small foot-plant blend. The actual pre-roll `speedF` therefore depends on the captured
WAIT frame controllers and delayed toe stream. Sampled exact sim phases produced roughly
`25.75-25.81`; `25.9` is the rounded technique name/upper bound, not one universal bit pattern.

- Getting the *second* SIDE frame requires the setup frame to be off-axis, so its own injection is
  forced below 5.0: exactly `5*cos_s16(-1481) = 4.949206829` for the best clean-DTM input.
- You can't have both a clean +5.0 setup frame *and* a SIDE next frame: straight is +5.0 but snaps
  FORWARD (no bonus); off-axis earns the bonus but costs the setup-frame cosine. Net
  `mNormalSpeed = 16.949207306` before the early roll.

So the normal rest-start choice is **early roll below 26** or **one more acceleration frame at 26**.
An absolute early-roll value cannot be named from health and stick bytes alone; it requires the exact
rest animation seed. `trace_fast_launch` calculates one input, while
`optimize_constant_gate_launch` scans all 907 clean-DTM SIDE targets through the exact animation
model. The latter may select a nearby angle with slightly lower potential speed but higher actual
`speedF` for that specific WAIT phase.

## Critical health

Critical health does **not** change the 5.0 / 3.5 acceleration constants. It changes WAIT:
`procWait_init` plays the mode-0 `ANM_WAITATOB` single at rate 0.6. If Link remains stopped, it then
settles into the mode-2 `ANM_WAITB`/WALK blend at rate 0.4. Both phases change the delayed foot-toe
stream and therefore the roll speed; neither is equivalent to the healthy WAITS idle.

The simulator now seeds both low-health phases: `FootSpeedF.seed_rest_single` handles an in-progress
WAITATOB capture, while the rest-blend seed handles a settled WAITB critical-health WAIT. The live
slash finder accepts both and records `low_life` in its anchor.

**Camera doesn't improve the ceiling.** It only rotates the stick's world target. The stick already
supplies the closest decoded target outside the SIDE gate, and any larger first-frame travel change
lowers the `5*cos(delta)` injection. A pre-set camera can reproduce the same target with different
raw bytes, but cannot exceed it.

**The one escape (untested):** the potential-speed ceiling is specific to an aligned standstill. If
`travel` were already off-axis from `facing`, the first frame could inject the full 5.0 while already
selecting SIDE, allowing `mNormalSpeed` to reach 17 one frame earlier. A full-26 roll would still
require the animation-derived `speedF` to reach 17, so this needs a realistic non-rest seed rather
than only the HIO equation.

## See also

- [land-movement.md](../mechanics/land-movement.md) — the ATN_MOVE tier, roll mechanics, and the
  `Values` table (ATN_SPD, F14, ATNB_COS_FWD, ATN_MAX, roll `clamp`).
- [turnaround.md](../mechanics/turnaround.md) — the analogous instant-snap threshold (charge/swim).
