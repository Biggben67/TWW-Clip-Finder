# Link's head-look twist `m3564` (setNeckAngle)

**Answers:** Why does Link's head visibly turn toward a lock-on/attention target, what state drives
it, when does it engage and disengage, and what does `mHeadTopPos` (the point an NPC's look-at chases)
actually depend on?
**Status:** LIVE-VALIDATED 0-tolerance. The model
([`tww_sim/land/neck_look.NeckLook`](../../tww_sim/land/neck_look.py)) reproduced every live `m3564`
AND every live facing bit-exactly over a 44-frame two-actor window. **No offline gate ships in this
repo** - the fixture and its harness went with the route search that produced them, so treat the page
as the specification and re-capture before trusting a change.
**Source:** decomp `daPy_lk_c::setNeckAngle` (`d_a_player_main.cpp:8938-9169`, called at `:11571`),
`jointBeforeCB` (`:269-270`, `:350-362`), `checkAttentionPosAngle` (`:8923`), the proc mode-flag table
(`d_a_player_main_data.inc:223-302`), `dAttention_c` list stocking (`d_attention.cpp:518-560`,
`judgementStatus*` 764-844). Values:
[reference/constants.md#link-head-look](../reference/constants.md#link-head-look).

---

## What it is

`m3564` (csXyz, s16) is Link's **head-look twist**: `jointBeforeCB` rotates the HEAD joint
(`CL_JNT_HEAD_JNT_e`, 15) by `local_38 = (m3564.y, m3564.z, m3564.x)`, applied as two quat concats
onto the animated pose - `Q(x=m3564.y, y=m3564.z, 0)` then `Q(0, 0, z=m3564.x)` (`:353-362`). So
`m3564.x` is pitch, `.y` is yaw, and `.z` (roll) is never driven on land.

The twist changes only the head joint's ROTATION - root and neck translates (the
[body Co centre](link-co-centre.md)) are untouched. `mHeadTopPos = anmMtx(head) * (40, 0, 0)` moves
with it, by up to ~1 u of Y at full deflection, which is what makes this reach an NPC's elevation
chase and come back as a facing difference.

## The per-frame update (setNeckAngle, in the execute pass)

Runs at `:11571` - **after** `posMove`/`setMoveSlantAngle`, **before** this frame's
`mpCLModel->calc()` - so it measures the **previous** frame's head anm matrix and twists **this**
frame's pose. Two timing traps, both live-pinned:

- **`m34DE` here is the frame-START facing** (the previous frame's end value): it is written in the
  execute PROLOGUE (`:11287`), before the proc dispatch (`:11402`) updates `shape_angle.y`. Feeding
  the post-step facing lands every yaw target one re-aim ahead, which shows up as a sign flip on the
  first frame after a re-aim.
- **The mode flags are the pause-boundary dispatch proc's** (`mModeFlg`, set from the proc table at
  `commonProcInit` `:5806`, which runs on the new proc's first dispatch frame).

The law, all s16 arithmetic:

1. **Gate**: a look target is chased only when `mModeFlg` carries `0x80 | 0x8000000` AND a look pos
   was selected. MOVE / WAIT / ATN* / SIDESTEP / CUT* carry `0x80`; **FRONT_ROLL, MOVE_TURN,
   WAIT_TURN and SLIP do not** - so `m3564` chases 0 through every roll, even while an actor lock is
   held mid-roll. Gate off means the targets are 0 (every reachable else-branch: the `m34C3 == 1` arm
   reads `m34E2 >> 1`, which is 0 in ordinary land regimes).
2. **Look pos** = the locked actor's `eyePos` (`mpAttnActorLockOn`, `:9014`) or, unlocked, the
   attention's stocked lock-on-list head's (`GetLockonList(0)` via `checkAttentionPosAngle`,
   `:9019-9029`) - both through the **+-0x6000 cone of `m34DE`** on the feet-to-eye bearing. The list
   is restocked every NONE-state attention Run (`stockAttention`) and kept through LOCK/RELEASE, but
   the Run that transitions to NONE has just `freeAttention()`d it and does NOT restock - a
   **one-frame empty hole on the lock-drop frame**, so the chase reads 0 for exactly one frame
   between two chase frames. `AttentionLock.list_present` models that timing; which frame the drop
   lands on is [attention-lock-lifetime.md](attention-lock-lifetime.md).
3. **Measure** (off the previous head matrix M): `spC4 = M*(11.25, 0, 0)` (head centre),
   `spAC = M*(11.25, 18.75, 0) - spC4` (eye direction); the anim's own pitch/yaw with the current
   twist subtracted: `r24_4 = atan2s(-spAC.y, absXZ(spAC)) - m3564.x`,
   `r25_3 = atan2s(spAC.x, spAC.z) - m34DE - m3564.y`.
4. **Targets**: `spB8 = look_pos - spC4`; pitch `r27 = atan2s(-spB8.y, absXZ(spB8))` clamped
   `[-10000, 8000]`; yaw `r23_3 = atan2s(spB8.x, spB8.z) - m34DE`, **except `absXZ(spB8) < 30`
   freezes it at the current `m3564.y`** - a razor branch that fires when Link is nearly on top of
   the target, and the reason a close-quarters yaw sequence can read as an implausible dance
   (`60 / -3 / 0` on consecutive frames) rather than a chase - then clamped +-14336.
5. **Chase**: `cLib_addCalcAngleS(&m3564.{x,y}, (target >> 1) - measured, 3, 0x1000, 0x100)` (the
   `>> 1` half-angle variant runs for `0x80` procs whose upper anim is not DASHKAZE), then the yaw
   overflow clamp keeps `r25_3 + m3564.y` inside +-14336 (this applies on every `0x80` frame, whether
   or not a target was selected); `.z` chases 0.

## The echo chain it sits in

`m3564` sets this frame's head pose, which sets `mHeadTopPos.y`, which is the target an NPC's look-at
ELEVATION chase reads ([tetra-look.md](tetra-look.md)), which sets her head pose, which sets her
**eyePos x/z**, which is what Link's ATN_ACTOR re-aim bearing reads, which is his **facing**.

Unmodelled, the close-quarters head-top Y sits up to ~1 u high and facing echoes up to ~16 BAM on
the frames after a lock drop. That is small and it is not noise: a facing feeds a stick decode and a
travel angle, so it survives into position.

## Sim wiring

`NeckLook` consumes the cached previous-frame head matrix (`FootFK.head_mtx`, twist included), the
pre-step `m34de`, the post-step dispatch proc, `AttentionLock.locked`/`list_present`, and the
end-of-previous-frame NPC eye. Seed `m3564` from the live capture - at a mid-conversation entry it is
part-way through decaying from a prior look, so a zero seed is a real error. The native `LandCore`
carries the same update (`seed_look`, `_zl1c.pxi`) on its coupled-actor surface.

## See also

- [tetra-look.md](tetra-look.md) - the NPC half of the chain, and the eye this one chases.
- [attention-lock-lifetime.md](attention-lock-lifetime.md) - which frame the lock (and the list) drops.
- [../model/anim-engine.md](../model/anim-engine.md) - where `jointBeforeCB` sits in the pose pipeline.
- [../model/porting-the-look-pair.md](../model/porting-the-look-pair.md) - what it took to run this
  and the NPC model inside a native frame.
