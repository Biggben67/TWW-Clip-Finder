# Ocean environment & collision streaming

**Answers:** How is the Great Sea laid out? Why is only one island "real" at a time? Why can't you
usually refill at an island mid-swim? What is a sploosh zone and why does it cap your speed? Why do
routes have to go *around* certain quadrants?
**Status:** TASer/community knowledge (user-reported 2026-07-03). Behavioral truth used to route
real swims; not yet decomp-grounded or modeled by the sim.
**Source:** live TAS practice (dmiller).

---

## The 7×7 quadrant grid

The Great Sea is a **7×7 grid of 49 quadrants**, one **island per quadrant**. Superswim routes are
planned across this grid, quadrant to quadrant.

## Only one island's collision is loaded at a time

At any moment **only a single island has its collision geometry loaded**. This is the streaming
constraint that shapes everything below, and **island load timing is very hard to predict**.

**Consequence — mid-swim refills are rare.** The common [air refill](air-refill.md) uses an island's
land/water boundary. But superswim is so fast that an island you'd want to skim *partway through* a
long swim **won't have finished loading its collision by the time you arrive** — so there's nothing to
skim. This is *why* refills cluster at the **start** of a swim (the launch island is already loaded),
not because mid-route refills are geometrically impossible. They occur, but they're the exception.

## Sploosh zones (ocean-collision load failure)

Some **flat-ocean quadrants** are **sploosh zones**: if you enter them **too fast**, the **ocean
surface collision itself hasn't loaded** in time, so Link **falls through to the bottom of the ocean**
(a "sploosh") and the swim is lost.

- **Sparse.** Most of the sea is safe to superswim freely; sploosh zones are the exception, not the rule.
- **Speed-capped entry.** A sploosh zone must be **approached below some maximum speed threshold** so
  the ocean collision can load before you're on top of it.
- **Routing constraint, not a physics one.** A direct straight-line route that would pass *through* a
  sploosh zone often has to be replaced with a **multi-step route that goes around** it (or slows to
  cross). This is a coarse, quadrant-level route decision — distinct from the per-frame cruise physics.

## Why this is a routing layer, not a search dimension

These constraints live at the **quadrant graph** level (which quadrants to cross, where to slow, which
island is loaded for a refill), *not* inside the per-frame cruise DP. Folding island/ocean collision
into the [planner](../model/planner.md)'s state would multiply an already-saturated
[frontier](../model/planner.md#frontier-size-vs-quality--mf2000-is-the-sweet-spot-non-monotone) by a
spatial dimension for no benefit. The natural decomposition is a **coarse quadrant-route layer** (avoid
sploosh zones, respect their speed caps, place refills at loaded islands) feeding **per-leg cruise
optimization** (the 1-D sim). See [planner § unmodeled world features](../model/planner.md#unmodeled-world-features--the-re-plan-loop).

## See also

- [Air refill](air-refill.md) — the boundary-skim mechanic that the loaded island enables.
- [Planner](../model/planner.md) — the 1-D cruise sim these constraints sit *around*, not inside.
- [Open questions](../history/open-questions.md) — what a world/route model would need.
