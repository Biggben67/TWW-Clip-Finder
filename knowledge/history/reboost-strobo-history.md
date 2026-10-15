# History — strobo / reboost / arrow research

> **status: historical** — provenance and superseded conclusions, NOT current truth. For what is
> true now, see [strobo](../mechanics/strobo.md), [reboost](../strategy/reboost.md),
> [turnaround](../mechanics/turnaround.md), [arrow](../mechanics/arrow.md). This page exists so the
> *journey* (and the dead ends) is recoverable without polluting the truth pages.

This page is excluded from "current truth" retrieval. Date stamps are the original session dates.

---

## Reversal: reboost cadence (2026-06-26)

- **Earlier conclusion (superseded):** "Reboost is net-negative — charge frames move Link almost
  nothing, so a blind 20-ESS + 2-charge cadence loses (−2% band-2, −8% band-1). Never reboost."
- **What was actually wrong:** only *blind fixed cadences* were tested. Those fire at arbitrary anim
  phases and pay the turnaround tax without aiming the drift.
- **Corrected truth:** reboost **saves time when phase-triggered** (fire as anim drifts off the
  peak), up to **+15%**, beam-search-confirmed and live-verified (+15.7%). See
  [reboost](../strategy/reboost.md).

The raw in-band measurement that seeded the wrong conclusion (pure ESS 30 fr = 15677 disp vs
(8 ESS + 2 up/dn)×3 = 13673 disp) is real — it just only proves *fixed cadence* loses.

## Reversal: bug#2 — physics vs pipe artifact (pt19–pt21)

- **Earlier framing (superseded):** dense back-to-back pump plans reached only ~127k live vs sim's
  ~300k → "bug#2 is a real game-physics divergence; dense plans are invalid."
- **Corrected truth:** it is an **input-delivery artifact**. The external `advanceseq` pipe's
  FrameAdvance listener jitters SI polls on dense transitions. A **cleanly authored DTM** (8
  ControllerState rows per 30 fps game-frame, 254/1 calibration) played via the movie system is
  **bit-exact to sim** (cruise_pump300k: net 300,816). Dense plans are **valid**. See glossary:
  [DTM](../reference/glossary.md), [bug#2](../reference/glossary.md).
- A DTM *recorded* from the pipe inherits the jitter — only an *independently authored* DTM is the
  unbiased delivery path. (This was the critical insight, pt19.)

## Open / partially-resolved (as of pt27, 2026-06-27)

- **Arrow swimming may not pay off.** `ArrowState` is live-validated **charged only** (v ≈ −300,
  state 55): facing to ≤ 0.6°, drift bearing sim 224° vs live 223°. But the offline planner verdict
  is that arrow **likely loses 2–4 frames** at 200k — early `sin α` drift doesn't cover the prefix
  overhead — and it is **not yet validated from a cold start**, because `ArrowState` does not model
  the state-54→55 entry release + [x598 scramble](../reference/glossary.md#x598). A cold-built arrow
  plan diverges live at the prefix. Next: capture charged-arrow anchors, compare via DTM.
- **Strobo band exact derivation** is open — the bands are empirical (emerge from the increment
  formula); the exact decomp source (likely a Nonmatching `J3DFrameCtrl::update` term) and whether
  the bands are sharp or fuzzy are not pinned.
- **Multi-pump precision** degrades after ~1.5 cycles (single/double pumps bit-exact); the x598
  scramble amplifies a ~1e-4 per-entry anim oscillation past the cos-table boundary (~0.07 v per
  pump). Escape hatch: a per-entry anim search dimension in the planner.

## Pointers

These threads were reconstructed from the `_notes/` session handoffs (pt4, pt8, pt18–pt27) and the
dated findings formerly inline in `SUPERSWIM_KNOWLEDGE.md`.
