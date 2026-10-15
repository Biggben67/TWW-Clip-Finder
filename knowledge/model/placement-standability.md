# A seeded actor position the engine will never correct

**Answers:** My sweep found a placement that clips - can the actor actually STAND there? Why does a
seeded position inside a wall push Link perfectly happily instead of being ejected? What is the minimum
clearance a real approach can deliver an NPC to? Which of my search's axes needs a standability filter?
**Status:** measured on a flooded-Hyrule Tetra corner; the empirical check is 288 live-validated genuine
coords, which clear the bar by 7 u.
**Source:** [`tww_sim/core/_shovec.pyx`](../../tww_sim/core/_shovec.pyx) (`ShoveCtx._run`, the
`placed_step` seed), [`tww_sim/core/npc_zl1.py`](../../tww_sim/core/npc_zl1.py) (`WALL_R`),
[`tww_sim/core/collision.py`](../../tww_sim/core/collision.py) (`line_check` / `wall_correct`).

---

## The gap

`ShoveCtx._run` seeds the pushed actor by **writing her position** at `placed_step` and zeroing her
speed. Her own `CrrPos` then runs that same frame - and finds nothing to complain about:

- `line_check` sweeps `old -> new`, and a written position has `old == new`, so there is no segment to
  cross a wall triangle with;
- `wall_correct` tests the distance from a segment offset **outward** by her wall radius, so a point
  already *behind* the plane measures `radius + penetration` from it and is skipped as out of range.

So a placement inside a wall **stays inside the wall**, and the sweep reports its clip exactly as it
would a real one. Nothing in the engine is wrong here: `_run`'s seed is an initial condition, and the
game never produces one by teleporting an actor into geometry. The clause belongs to the caller.

## The bar

`CrrPos` never leaves her nearer a wall plane than her **BG wall radius, 50 u** (`npc_zl1.WALL_R`;
values in [../mechanics/tetra-follow.md](../mechanics/tetra-follow.md)), so that is the floor on a
deliverable placement. The empirical check agrees with room to spare: all **288** live-validated genuine
coords sit at **>= 56.98 u** from both planes.

    placeable(t)  <=>  planeA(t) >= 50  and  planeB(t) >= 50

## What it cost to not have it

A sweep with the filter off - 851,598 placement x entry pairs - found a cut endpoint going **through** a
wall plane at the earliest thrust step for the first time, which made both frames look live. That
placement was **3.54 u behind** one of the walls. From inside a wall she can graze Link's Co cylinder at
a bearing no reachable spot offers, which was the whole of the apparent margin. With the filter on, that
thrust step is refused at every aim cell with no hull anywhere in the search.

**The tell was in the sweep's own output, one column over.** Every one of those runs printed
`walkable True` - for LINK's entry. The filter existed and was applied to the wrong actor.

## The rule

**A search axis that positions an actor needs a standability clause, and it is not the same clause as
the one on the actor that moves.** Feasibility filters get written for a search's original axis and then
silently under-cover every axis added later: Link's entry had `is_walkable` from the first pass because
entries are where the planner walks, and her placement never got one because she arrived as a *parameter*
rather than as a plan. When a new axis joins a search, ask what makes a value of it **deliverable**, not
just evaluable.

## See also

- [../mechanics/wall-response.md](../mechanics/wall-response.md) - `line_check` / `wall_correct`, the two
  tests a written position slips between.
- [../mechanics/plow-ejection-equilibrium.md](../mechanics/plow-ejection-equilibrium.md) - where a real
  approach actually leaves her, which is the other half of "deliverable".
- [../mechanics/tetra-follow.md](../mechanics/tetra-follow.md) - what she does once she is somewhere she
  can stand.
- [required-cut-contact.md](required-cut-contact.md) - the requirement this filter guards, and how a
  push direction implies a placement.
