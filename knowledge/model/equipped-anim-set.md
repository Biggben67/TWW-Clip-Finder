# The equipped-item anim set (`getAnmData`)

**Answers:** Does Link walk with a different animation when his sword is out? Which anims change and
which do not? Why can a sword-drawn walk change `speedF` at all if the upper body is the only visible
difference?
**Status:** validated live 0-ULP: posing the sword pair took a delivered plan's first anim-driven frame
from 12/58 ULP to exact, and the whole walk-down band with it.
**Source:** decomp `d_a_player_main.cpp` `getAnmData` (`:12950`) + `mSwordAnmIndexTable`
(`d_a_player_main_data.inc:698`); sim
[`tww_sim/core/anim/anim_state.py`](../../tww_sim/core/anim/anim_state.py) (`UnderAnimState._walk` /
`_dash`) + [`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) (`PoseEngine.set_sword`).

---

`setBlendMoveAnime` and friends name anims by `daPy_ANM` enum, never by resource index. `getAnmData`
does the lookup, and it switches TABLE on `mEquipItem`: SWORD, BOKO, HAMMER and the
boomerang/leaf/telescope trio each have their own, everything else falls back to `mAnmDataTable`.

With the sword equipped (`mEquipItem == daPyItem_SWORD_e`, `m3562 == 0x103`) exactly two of the
under-body movement anims are re-pointed:

| `daPy_ANM` | default | sword table |
|------------|---------|-------------|
| `ANM_WALK` (0x01) | WALK | **WALKS** |
| `ANM_DASH` (0x02) | DASH | **DASHS** |
| `ANM_WAITS` (0x00) | WAITS | WAITS |
| `ANM_ATNDRS`/`ATNWLS`/... (0x07-0x0F) | themselves | themselves |

`mSwordAnmIndexTable` runs to `ANM_CUTTURNPWLR` (0x1A) and `getAnmData` bounds-checks against its
length, so anything above it - `ANM_ROLLF` (0x32) included - falls through to the default table. **A
sword-drawn roll poses the same ROLLF as a sheathed one.**

## Why it reaches the position

WALKS/DASHS differ from WALK/DASH only in the FEET: joints 0-4 and 14 - the neck chain the
[Co centre](../mechanics/link-co-centre.md) is built from - are identical, which is measured and is why
the actor push is indifferent to this. But the feet are exactly what
[`posMoveFromFootPos`](anim-engine.md#toe--speedf) reads: on any frame where the walk anim owns the speed
(`m3598 != 0`) the plant-toe delta IS `speedF`.

So the swap is inert for as long as Link is in momentum procs - rolls, brakeslides, the DASH cruise
where `m3598 == 0` - and becomes the position on the first blended walk frame.

That is the trap: a sword-drawn window can look perfectly bit-exact for dozens of frames with the wrong
anim pair loaded.

## In the sim

`LandState(sword_drawn=True)` gives `FootSpeedF(sword=True)` gives `UnderAnimState._walk`/`_dash`
resolving to `walks`/`dashs`; the native engine carries the same flag (`PoseEngine.set_sword`, codes
`C_WALKS`/`C_DASHS`). Seed it from the anchor's `mEquipItem` -
[`harness/rollstab/mint.py`](../../harness/rollstab/mint.py) reads `seed['mEquipItem'] == 0x103`.

## See also

- [anim-engine](anim-engine.md) - the blend/pose pipeline these anims feed
- [draw-base](draw-base.md) - the other half of "which pose": the base it is posed from
- [wait-stop-pose](wait-stop-pose.md) - which clip a stopped Link is being posed with
