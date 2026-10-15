# Air refills

**Answers:** How do you refill air mid-swim? Why is touching land catastrophic? Why are refill spots
fixed on flat water but moving on wavy water? What are corner refills? Where does a refill usually
happen? How do TASers actually plan around refills today?
**Status:** TASer/community knowledge (user-reported 2026-07-03). The *sim's* 1-D refill model is
separate and marked approximate — see [planner](../model/planner.md#air-refill--the-far-swim-regime-sim-model).
**Source:** live TAS practice (dmiller).

---

Air drains −1/frame (max [900](../reference/constants.md#air)); lower air → head deeper → more
[head-bob drag](animation.md) → slower ESS. A refill resets air to 900, so far swims depend on it
(non-refill swims drown around ~450–500k — see [planner](../model/planner.md#air-refill--the-far-swim-regime-sim-model)).

## The boundary-skim trick

You refill by getting **close to the land/water boundary** of a **loaded** island (see
[collision streaming](ocean-environment.md#only-one-islands-collision-is-loaded-at-a-time)). Being
near the boundary **tricks the game into refilling air while you keep swimming**.

**Touching land for even ONE frame loses ALL speed.** So the maneuver is a *precise* skim: close
enough to the boundary to refill, never close enough to touch. This precision — a hard "where you
**can't** be" constraint — is the whole reason refills are hard, and why they're handled by a human
frame-by-frame rather than by the frame-count search.

## Flat vs wavy quadrants

- **Flat quadrants:** the waterline is static, so the refill band is a **fixed, known region** you can
  mark beforehand. (The repo's test savestates are deliberately placed in **flat** water.)
- **Wavy quadrants:** wave height shifts the effective waterline, so the refill spots **move with the
  waves** — the safe band oscillates in time. Much harder; out of scope for the current flat-water work.

## Corner refills

Some refill spots sit in an island's **corner**. They're fairly easy to hit, but getting one involves
the player **bumping into the corner repeatedly** — a collision interaction. The sim does not (and
should not) model that bounce; if such a maneuver is ever costed, its **frame overhead is calibrated
empirically**, not simulated.

## Where a refill usually happens (the launch-island pattern)

The dominant pattern: **start on an island → roll into the water → charge the superswim → skim the
launch island's edge for a refill (you're right next to it anyway) → cruise to another island.** So
**~90% of swims refill at the very start**, at distance ≈ 0. Mid-swim refills exist but are rare,
because the target island won't load in time
([streaming](ocean-environment.md#only-one-islands-collision-is-loaded-at-a-time)).

## In practice — the template + manual-refill + rerun loop

Because the refill is precise and collision-sensitive, the established TAS workflow is:

1. Run the **1-D sim as a template** — it says *when* (what distance/frame) air becomes binding and a
   refill is due.
2. **Manually perform** the inputs, and at the suggested moment **intervene by hand** to skim the
   refill (the precise, touch-nothing maneuver).
3. The game state has now **diverged** from the sim → **rerun the 1-D sim from the new live state** to
   finish the cruise.

This decomposition — 1-D sim owns the cruise (frame-exact), the human owns the precise refill — is
sound: the two sub-problems have completely different structure. The proposed sim-side refinement is to
model a refill as a **calibrated boundary event** (air:=900 + a measured frame cost at a route point),
never as collision physics — see [planner § unmodeled world features](../model/planner.md#unmodeled-world-features--the-re-plan-loop).

## See also

- [Ocean environment](ocean-environment.md) — streaming, sploosh zones, the quadrant grid.
- [Planner air-refill model](../model/planner.md#air-refill--the-far-swim-regime-sim-model) — the sim's 1-D approximation.
- [Phase ordering](../strategy/phase-ordering.md) — where the refill sits in the swim sequence.
