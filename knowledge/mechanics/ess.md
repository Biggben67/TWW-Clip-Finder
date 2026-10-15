# ESS (extended superslide)

**Answers:** What does ESS stand for? What is ESS physically? What stick values? Why is diagonal ESS
more efficient? Why is raw=110 optimal?
**Status:** validated (decomp + live).
**Source:** decomp stick pipeline (`PADClamp`, `JUTGamePad::CStick::update`, `setSpeedAndAngleSwim`); live.

---

**"ESS" = extended superslide** — a legacy term carried in from older Zelda-series movement tech; the
name is historical, not descriptive of what it does in TWW (the "Extra Slow Swim" backronym seen
elsewhere is wrong). It is used for both the swim tech below and the low-magnitude land aim-stick.

## What ESS is

Stick range is 0..255 per axis; **neutral = (128,128)** with a dead zone around it. ESS = the
*minimum* input just outside the dead zone that the game still registers — the smallest non-neutral
`mStickDistance`. So it has the smallest head-bob/anim drag while still on the swimming-input path,
decaying potential speed only **−1/6** (vs neutral's −2 and full charge's −3).

The tradeoff: ESS **preserves potential speed** (decay ~1/6) but, because the stick is non-neutral,
pays the [head-bob + air drag](animation.md) on true speed. [Neutral](neutral.md) loses potential
speed fast (−2) but moves drag-free. The planner finds where to switch.

## Stick values

**Cardinal ESS** (potential decay −1/6 ≈ −0.1667), 18 units off one axis:
- Down `(128,110)`, Up `(128,146)`, Left `(110,128)`, Right `(146,128)`.

**Diagonal ESS** (decay −0.1571, ~5% more efficient), 17 units off each axis:
- DL `(111,111)`, DR `(145,111)`, UR `(145,145)`, UL `(111,145)`.

Diagonal is more efficient because the octagonal dead-zone geometry removes slightly more, giving
effective magnitude 0.0524 vs cardinal 0.0556 → decay 0.0524·3 = 0.1571 < 1/6. So the −1/6 vs
−0.1571 constants are **grounded in stick geometry**, not arbitrary fits.

## raw=110 is provably optimal

`raw=110` (off 18) is the minimal deflection that still clears the swim-move gate
`mStickDistance > 0.05`: `(18−15)/54 = 0.0556 > 0.05`. Values like 111/112 that appear "better" in
the offline sim are artifacts — probe any new stick value against the decomp gate first. (See memory
`superswim-ess-stick-optimal`.)

## First-frame transient

The FIRST frame after switching from charge to a steady ESS hold shows a **−3.0 transient** as
Link's facing flips; decay settles to −1/6 from frame 2 on. The model prices this as `entry_tax`.

## See also

- [Decay curve](decay-curve.md) — ESS and charge are two points on one continuous law.
- [Animation / head-bob](animation.md) — the drag ESS pays on true speed.
- [Constants](../reference/constants.md#speed-deltas).
