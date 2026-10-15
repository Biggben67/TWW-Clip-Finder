# How long the entry lean survives a roll

**Answers:** Is the entry lean `m351C` a knob on what happens late in a roll? Which roll frames does
the lean actually shape? Should a search carry the lean as an axis at every roll frame? Which engine
computes the decay?
**Status:** validated - the decay law is decomp-exact and the schedule below is the delivered draw
sequence off a real curved-approach roll. **Only the Python path computes it:** `SLANT_DECAY` and
`_set_move_slant_angle` live in [`tww_sim/land/state.py`](../../tww_sim/land/state.py); the native
`LandCore` tracks `m351C` and `_draw_lean_c` and consumes them in the pose chain, but no longer
computes `setMoveSlantAngle` itself (its only caller was removed), so a native-only run needs the lean
seeded or stepped from the Python side.
**Source:** decomp `daPy_lk_c::setMoveSlantAngle` (`d_a_player_main.cpp:11561`),
`d_a_player_HIO_data.inc` (`field_0x54`); sim
[`tww_sim/land/state.py`](../../tww_sim/land/state.py) (`SLANT_DECAY`, `_set_move_slant_angle`,
`_draw_lean`). Canonical value:
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

The MOVE turn lean `m351C` is what tilts Link's body, and through the body it tilts the draw base and
the Co-cylinder centre ([link-co-centre.md](link-co-centre.md), [../model/draw-base.md](../model/draw-base.md)).
A roll is not a MOVE, so `_set_move_slant_angle` takes its **decay branch** every roll frame:

    m351C <- m351C - int(f32(m351C * SLANT_DECAY))          # SLANT_DECAY = 0.35

which is a 35%-per-frame geometric decay with an integer truncation under it. The pose reads
`m351C >> 1`, so from an entry lean of 64761 (-775 signed) the draw goes:

| roll frame | 0 | 1 | 2 | 4 | 6 | 8 | 11 | **15** | 16 |
|---|---|---|---|---|---|---|---|---|---|
| draw | -388 | -252 | -164 | -70 | -30 | -13 | -4 | **-1** | 0 |

**So the entry lean is spent within about ten frames, whatever it was.** A +-3000 s16 entry lean - four
times the one above - is down to -2 by frame 15 as well: the decay is geometric, so a bigger lean buys
two or three more frames, not a different regime.

## Where it is a lever and where it is not

A [cut that dispatches at roll step 15..17](roll-cut-thrust-floor.md) is posed from a body with **no
lean left**, so the lean cannot move anything that frame reads - the Co centre, the push it generates,
or the endpoint. Measured with the geometry re-solved at each value, +-3000 s16 of entry lean moves the
late-roll penetration depth by **0.0003 u**.

That is not the same as "the lean does not matter". It shapes the **early** roll frames, where the Co
centre is displaced by tenths of a unit and a push on a nearby actor is real - which is why the two-lean
Co model was needed to make a clip roll bit-exact in the first place. The rule is about WHERE in the
roll:

> **The lean is an early-roll lever. Past ~10 roll frames it has decayed out, and a sweep of it at a
> late roll frame is measuring nothing.**

And "the value at one solved configuration" is not "the set of configurations that solve": re-scanning
a family at a non-zero entry lean can keep the late depth and still move the family, through the early
frames that decide where a plowed actor is left standing.

**Which lean to scan AT is the roll's own, not the walk's.** Input latency makes the A act a frame
late, so the roll's first frame is still a MOVE and its turn WRITES `m351C` before any decay begins. The
value to seed from is the one after the ENTRY frame, which one simulated roll reads out - not the walk's
last lean.

## The methodology trap

Sweeping the lean **at a frozen configuration** reads a spurious sensitivity - about 0.03 u where the
true figure is 0.0003. Changing the lean moves the geometry, so a frozen configuration is compared
off-curve and what the sweep reports is the residual's own gradient wearing the lean's name. Re-solve
onto the curve at every lean value, then compare.

## See also

- [link-co-centre.md](link-co-centre.md) - the two lean terms and which frame each one reads.
- [../model/draw-base.md](../model/draw-base.md) - the other place the lean lands: the base the whole
  pose is built from, and the proc-init frame that draws upright.
- [ground-turns.md](ground-turns.md) - where `m351C` is written in the first place.
- [roll.md](roll.md) - the roll's constant momentum and facing snap.
