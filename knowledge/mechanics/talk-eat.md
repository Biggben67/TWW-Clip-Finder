# The A-press talk-eat - when a roll's A becomes a conversation instead

**Answers:** Why did an A-press start a conversation (proc 170 DEMO_TALK) instead of dispatching the
FRONT_ROLL? Which state decides talk-vs-roll - the walk-end state or the dispatch frame's aim facing?
Is the action-button (A) region a different `dist_table` row or cone than the lock-on region? What
exact bearing does the attention system compare against the +-90 deg cone?
**Status:** decomp-derived predicate, validated against two live deliveries - one that talked (A
pressed 78.675 u from Tetra with the walk-end facing inside the cone, console proc 170) and one that
rolled (A at 174.794 u, INSIDE the 300 u region, because the walk-end facing was 22606 BAM outside the
cone). The geometry half runs offline as
[`npc_zl1.zl1_attention_active`](../../tww_sim/core/npc_zl1.py) (gated in
[`tests/test_tetra_follow.py`](../../tests/test_tetra_follow.py)); the CANTALK / priority-chain half is
specified here and not wired into any planner.
**Source:** decomp `setTalkStatus` / `setAtnList` / `setDoStatus` / `orderTalk` /
`checkNextActionFromButton` (`d_a_player_main.cpp:2039-2163, 4029-4323, 11322`),
`dAttention_c::Run` / `getActionBtnB` / `calcWeight` / `check_flontofplayer` / `check_distace`
(`d_attention.cpp`), `dist_table[0xAB]` (`d_att_dist.cpp:181`), `daNpc_Zl1_c::eventOrder`
(`d_a_npc_zl1.cpp:1053`), `cSGlobe` / `cM_atan2f` (`c_angle.cpp`, `c_math.cpp:162`).

---

The player's A dispatch is a PRIORITY CHAIN, and talking outranks rolling. In
`checkNextActionFromButton` (the walk proc's per-frame button dispatch) `setDoStatus` runs first: if
the attention system handed the player an A-action entry of type SPEAK (`mpAttnEntryA`, from
`getActionBtnB()` when there is no lock-on), `setTalkStatus` sets doStatus SPEAK and `orderTalk`
consumes the A (`fopAcM_orderTalkEvent`, then DEMO_TALK, proc 170). Only when no talk entry exists
does the A fall through to doStatus ATTACK and `procFrontRoll_init`. So "does the A roll?" reduces to
"is the NPC in the attention ACTION list this frame?" - and separately to
[whether the stick is deflected enough](roll-attack-threshold.md).

## The ACTION region is the SAME region as the lock-on region

Tetra's `createInit` sets `distances[TALK] = distances[SPEAK] = 0xAB`, so both lists read
`dist_table[0xAB]`: XZ <= 300 u (inclusive - the reject is strictly `300 < dist`), `|dy| < 300` between
attention points (exclusive bounds), and Link's facing within +-0x4000 of her bearing (inclusive - the
reject is strictly `> 0x4000`). Values live with the rest of her table in
[tetra-follow.md](tetra-follow.md).

Plus one non-geometric gate: her `eventInfo` must assert `dEvtCnd_CANTALK_e` that frame (`eventOrder`,
while her `field_0x84A` is 1 or 2) or `calcWeight` zero-weights her out of the list.

## The input is the WALK-END state, not the dispatch frame's aim facing

The two live deliveries prove this by themselves. The one that rolled had a roll facing 501 BAM off
her bearing - comfortably INSIDE the cone - so a predicate fed the aim facing calls a real roll a talk.
Its walk-end facing was 22606 BAM off, outside, and it rolled.

Mechanically: the attention lists are rebuilt each frame by the scene proc (`dScnPly_Execute`, then
`Run(-1)`, with no hysteresis in the absence of a lock-on) from positions and facings the player's
proc has not yet moved; and the roll's stick snap (`shape_angle.y = m34E8`) happens on the roll path
AFTER `orderTalk` has already taken the A. So the state to test is the last pre-dispatch frame's.

## The cone's bearing is NOT the raw table atan2s

`SelectAttention` computes it through `cSGlobe.U()`: `Radian_to_SAngle(cM_atan2f(dx, dz))` - the table
value round-tripped through f32 radians (`* 9.58738E-5f`, then `* 10430.378f`, s16 truncation toward
zero). That shifts about **18% of bearings by +-1 BAM**, which is enough to flip a verdict exactly on
the cone boundary. [`npc_zl1.attn_yaw_bam`](../../tww_sim/core/npc_zl1.py) is the exact chain and
`zl1_attention_active` uses it; a bare `cM_atan2s` does not reproduce the game here.

One decomp ambiguity, worth resolving conservatively: at a face error of exactly 0x8000 (dead behind),
`check_flontofplayer`'s s16 negation of -32768 overflows and the C source does not settle whether the
compiled game re-narrows. Treat it as a talk - the failure mode of guessing the other way is admitting
a plan that talks on console.

## Why it is a WRONG plan, not a refused one

A press that talks does not merely fail; it produces a *different, plausible* trajectory. Nothing in a
physics replay objects, because the replay was never asked which proc the button dispatched. So an
input stream that emits an A near a talkable NPC owes this check against the state at the press, in the
same place it owes the [deflection gate](roll-attack-threshold.md) - not after the fact.

## See also

- [tetra-follow.md](tetra-follow.md) - the `dist_table[0xAB]` geometry and her HIO values.
- [attention-lock-lifetime.md](attention-lock-lifetime.md) - the same lists read for a LOCK instead of
  an action entry, and how long a lock outlives L.
- [roll-attack-threshold.md](roll-attack-threshold.md) - the other gate between an A-press and a roll.
- [ebs-turnaround.md](ebs-turnaround.md) - clearing the cone in one frame so an L (or an A) acts with
  the NPC outside it.
