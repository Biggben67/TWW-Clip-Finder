# The 1-frame turnaround out of an EBS - and why the camera cannot set it up

**Answers:** How does the instant 1-frame facing snap out of an extended brakeslide work? What decides
whether it fires? Can the camera (`csangle`) be steered to make it fire? Why does a probe that COMMANDS
a `csangle` find a snap window no real plan can reach?
**Status:** the snap itself is simulated bit-exact ([`tww_sim/land/procs/move.py`](../../tww_sim/land/procs/move.py),
the `temp * temp2 <= 0` branch); the camera-unreachability result is measured over 330 reachable camera
states drawn from 3 real arrivals.
**Source:** decomp `d_a_player_main.cpp` facing chase (`cLib_addCalcAngleS`) + the `temp * temp2 <= 0`
cross-travel branch; live captures.

---

## What it is

In the untarget [EBS](brakeslide-ebs.md) facing sits ~exactly `0x8000` from travel (Link slides
backwards). Holding [ESS](ess.md)-down `(128,110)` for ONE frame at the right `csangle` sets the stick
want-angle so the facing chase **steps across travel** in a single frame: `temp * temp2 <= 0` makes
`facing = travel`, a ~180 deg snap with the **speed preserved** (`cos(target - travel) ~ 1`, so a
-25.727 backslide is held). Off that window you get a `MOVE_TURN` reversal instead
([ground-turns.md](ground-turns.md)), which costs the speed.

This is the land counterpart of the swim charge snap ([turnaround.md](turnaround.md)) and a different
mechanism: the swim snap is `getDirectionFromAngle(stick vs FACING)`, this one is the facing chase
crossing **TRAVEL**.

## The quantity that decides it is `want - travel`, not `want - facing`

The stick is camera-relative, so its world want-angle is `m34E8 = stick_angle + 0x8000 + csangle`
([turnaround.md](turnaround.md#the-target-direction-term-m34e8)). The snap fires on where that lands
relative to **travel**, so the camera looks like a free knob: rotate `csangle`, rotate the want-angle,
walk it into the window.

Measured on one fixed EBS state, commanding `csangle` across the circle at 512 BAM: the ESS frame turns
**30778 BAM (169 deg)** and snaps for `want - travel` in roughly `-6986..-2890` (16-38 deg behind
travel), and turns **6000 BAM (33 deg)** with no snap one grid step outside it. A hard cliff, with a wide
(~78-82 deg of `csangle`) window on one side of it.

## But the camera cannot deliver it, because travel chases the camera

That window is real and unreachable, and the trap is worth stating plainly because a commanded-`csangle`
probe cannot see it: **the post-roll EBS travel chases `csangle`**. So slewing the camera moves the stick
want-angle and the travel TOGETHER, and `want - travel` - the only quantity that matters - barely moves.

Measured on 3 real arrivals, sweeping the previous roll's camera target over +-0x4000 at step 64 (513
targets, giving 110 distinct reachable `(csangle, travel)` states each):

| | reachable (the roll actually slewed there) | commanded (same csangles, travel frozen) |
|---|---|---|
| states that SNAP | **0 / 0 / 1** of 110 | **10 / 9 / 9** of 110 |
| `want - travel` covered | -21906..+6195 BAM, with a **15866 BAM (87 deg) HOLE** | continuous |

The hole is exactly where the snapping band sits. The travel chase pins `want - travel` near 0 across the
whole slew, then jumps it past the window when travel flips branch - so the window is skipped, not
approached. A camera bill priced at 29 deg inside a 56 deg slew span therefore reads payable and is not.

**The rule:** never price a facing-snap setup by commanding a `csangle` onto a state whose travel was
fixed by something else. Sweep the channel that would actually pay for it - here the previous roll's
C-stick - and read the states it delivers. Gate the CONTRAST, not either half: reachable-only looks like
a physics limit and commanded-only looks like a free lever, and only the pair is the finding.

## Why the snap is wanted, and what else can do its job

The usual reason to snap is to get an actor OUT of the +-90 deg talk/lock cone before an L input acts
([tetra-follow.md](tetra-follow.md), [talk-eat.md](talk-eat.md)) - an L that acts with the actor in the
cone targets it instead of doing its job. The snap is the cleanest way to clear the cone in one frame,
**not the only one**: measured, an ESS frame that turns only `0x1425` (28.3 deg), well under a snap,
still leaves a working escape, because the cone is cleared one frame later by the frame the L acts on.

So test the OUTCOME (did the L act with the actor out of cone) rather than the snap, or a sufficient
condition gets used as a necessary one and real states are discarded. The difference is not marginal:
over 26 real rolls the same camera sweep that snaps at 0-6 of ~110 reachable states CLEARS THE CONE at
1-68 of them, with a clearing target available for every one of the 26. The unreachability above is a
statement about the snap - not about what the camera can pay for.

## See also

- [brakeslide-ebs.md](brakeslide-ebs.md) - the EBS this snaps out of, and the facing/travel decoupling
  that makes facing steerable independently.
- [turnaround.md](turnaround.md) - the swim charge snap: the same 1-frame idea, a different branch.
- [ground-turns.md](ground-turns.md) - `MOVE_TURN` / `SLIP`, what you get instead when the snap misses.
- [land-camera.md](land-camera.md) - what a `csangle` slew actually costs and how fast it converges.
- [talk-eat.md](talk-eat.md) - the cone the snap is usually clearing.
