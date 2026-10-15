# Instant turnaround (charge snap)

**Answers:** How do turnaround frames work? What is the angle threshold for an instant
turnaround? When does Link snap 180° vs turn gradually? How do you reorient the charge axis?
**Status:** validated (decomp + live).
**Source:** decomp `getDirectionFromAngle` (d_a_player_main.cpp:2278); live 2026-06-26 (slot 9/10).

---

## What it is

While charging, Link's facing can **flip 180° in a single frame** ("instant turnaround" /
"charge snap") instead of turning gradually. This is what makes back-and-forth charging work:
each alternation snaps him to face the new stick direction. It is also the mechanism behind
[arrow swimming](arrow.md) — you steer by *where* the snap points.

## The angle threshold (the key number)

The snap is decided by `getDirectionFromAngle` from the angle between the **target stick
direction** (`m34E8`) and Link's **current facing**:

```
abs(m34E8 − facing) > 0x6000   → DIR_BACKWARD   (snap shape_angle instantly to the stick)
              >= 0x2000         → LEFT
              <= −0x2000        → RIGHT
              else              → FORWARD
```

Angle units: `0x10000 = 360°`, so **`0x6000` = 135°** and **`0x2000` = 45°**.

So the instant 180° snap (`DIR_BACKWARD`) fires only when the stick points **more than 135° away
from current facing** — equivalently, **within 45° of straight-back**. The backward snap cone is
**90° wide, centered on straight-back (180°)**. That **45°** is the entire angular budget for
[arrow swimming](arrow.md) while keeping full charge snaps; crossing it is the arrow "tip-over".

When it snaps, Link rotates **exactly (180° − β)**, where β is how far the stick sits off
straight-back. The snap appears **one frame after** the input changes (target-angle update lag).

### Live confirmation

Max 1-frame heading turn vs tilt β off straight-back (facing addr `0x803EA3D2`):

| β | 0 | 35 | 42 | 44 | 46 | 50 | 70 |
|---|---|----|----|----|----|----|----|
| turn (°) | 180 | 147.5 | 138.6 | 136.5 | 7.8 | 7.5 | 6.6 |

The snap fires for β ≤ 44° and dies between 44–46° → the boundary is **exactly 45°**.

## Beyond the budget: gradual turn

Once the stick exceeds 45° off straight-back, `getDirectionFromAngle` stops returning
`DIR_BACKWARD` and the facing instead chases the target gradually via `cLib_addCalcAngleS` at
**~7° / frame**. No instant snap; speed is lost (this is the arrow tip-over at Xbias ≈ 190–200).

## The target-direction term `m34E8`

The stick is camera-relative, so the target world direction is:

```
m34E8 = stick_angle + 0x8000 + csangle      (csangle = camera yaw)
```

With the camera fixed, only Link's facing changes between frames, so the stick→world mapping is
fixed and the snap is fully determined by the stick. See [glossary: csangle](../reference/glossary.md).

## Reorienting the charge axis (turnaround chains)

[Arrow](arrow.md) drift is **perpendicular** to the charge axis, so to arrow-swim a chosen world
direction you must first rotate Link's facing onto the axis perpendicular to it. Because a single
snap only fires for targets **> 135°** off current facing, a ~90° reorient **cannot be one snap** —
you **walk facing through intermediate diagonal snaps**, each Δ ≈ 145–165°, and **every snap
charges** (−2.3…−2.9/fr, so reorienting also builds speed).

Worked example (face east 90° → N–S axis), inputs and resulting facing:
`(35,255) → (255,80) → (0,128) → (0,128)` snaps facing `90° → 305° → 164° → 0°`.
Once on the N–S axis, alternating **Left `(0,128)` / Right `(255,128)`** charges cleanly
(facing snaps 0° ↔ 180°, −3.00/fr, pure N/S motion).

> **Do not hardcode the input chain.** Model it as a small BFS over facings (nodes = facings,
> edges = valid > 135° snaps to reachable `m34E8` gates) so it generalizes to any start/target
> axis. This is how `ArrowState.reorient_chain()` does it (15° gates, synthesized snap sticks).

## Constants used here

`0x6000` = 135°, `0x2000` = 45°, gradual turn ~7°/fr, arrow budget 45°. See
[reference/constants](../reference/constants.md#turnaround--arrow-angular-budget).

## See also

- [Arrow swimming](arrow.md) — steering toward a target using the snap, and the α tilt model.
- [Strobo bands](strobo.md) / [reboost](../strategy/reboost.md) — where charge snaps are used to
  re-aim the anim drift.
- History / provenance: [reboost-strobo-history](../history/reboost-strobo-history.md).
