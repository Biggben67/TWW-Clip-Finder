# History — land planner precision claims (overturned)

> **status: historical** — superseded claims about how close the land planner stops. Current truth:
> [model/land-planner](../model/land-planner.md) and
> [mechanics/land-movement](../mechanics/land-movement.md). Kept because the *reason* they were wrong
> (a physics constraint the early tuning hid) matters.

---

## The "0.10u smooth-walk floor" (reach_precise) — overturned 2026-07-05

**Old claim.** `reach_precise` rests **~0.10u** from any target — "the smooth-walk floor (min
sustainable crawl)"; `reach_straight` rests ~0.23u.

**Reality.** Both are **target-SENSITIVE**, resting anywhere from **0.1u to ~9u** depending on the
target. The ~0.10u figure held only near favourable targets (e.g. z≈500, z≈2000); z=1200 rests 4.2u,
z=1500 6.1u. The early tuning (`k`, `min_crawl`, `turnback`) was effectively overfit to z≈2000.

**Why.** Two physics facts the early measurements didn't stress:
- The full-speed walk step is **17u** and the neutral coast-to-rest is a quasi-fixed **~49u** arc, so
  `reach_straight` rest lands on a coarse ~17u lattice — up to ~8.5u from an arbitrary target.
- `reach_precise`'s proportional decel **lags**: on a short trip Link is still near cruise speed when
  it reaches the vicinity and overshoots at speed; on a long trip it comes to a full stop and the
  **movement gate can't restart a crawl from rest** (needs `msd > 0.5`), so it stalls (limit-cycles to
  4000 frames). Neither reliably establishes the slow fine-crawl tail that a precise stop needs.

## The freeze planner was float-perfect only at lucky targets — overturned 2026-07-05

**Old claim.** `reach_freeze` (glide → tail beam-drill over the msd lattice) rests **~0.003u** on the
+z corridor; a one-off live-feedback beam reached **1 ULP at z=2000**.

**Reality.** The glide-based drill was float-perfect only where the proportional glide *happened* to
arrive slow (z≈2000 → 0.003u). At other targets it was far worse: z=1200 → 0.068u, z=3000 → 0.067u,
and pushing its params could make it catastrophic (multi-unit). The headline "0.003u" was cherry-picked.

**Fix (current truth).** The freeze coast (`+3` neutral frames) scales with approach speed, so a fine
freeze straddle exists **only when Link arrives slow**. The rewrite replaces the glide with **cruise →
sustained msd-0.5 crawl (the min stable crawl, ~1u/frame) → dedup-by-freeze-position drill**, which
guarantees a uniform fine straddle for **any** target: now within **~1–4 ULP (< 0.001u)** everywhere.
See [model/land-planner](../model/land-planner.md#float-perfect-stop--the-c-up-speed-cancel).

**Lesson.** A precision claim measured at one target is not a floor — sweep the target range before
calling a number a "floor". The land planner's real constraint is the **msd-0.5 crawl bifurcation**:
you cannot sustain a crawl slower than ~1u/frame, and you cannot slow down without a long decel
transient, so exact stops must ride the *one-shot* slow tail of a deceleration, placed by the drill.
