# Big-reversal ground-turn procs (WAIT_TURN / MOVE_TURN / SLIP)

**Answers:** How do the three ground-turn procs work — the standstill pivot (WAIT_TURN), the slow-move
turn-around (MOVE_TURN), and the fast skid (SLIP)? When does each fire? Are they simulated bit-exact?
**Status:** validated live — fully simulated in `tww_sim.land`, **bit-exact** `mNormalSpeed` / state /
facing / travel / **position** (d=0.0000) vs live.
**Source:** decomp `d_a_player_main.cpp` `checkNextMode` (4424) + `procWaitTurn` / `procMoveTurn` /
`procSlip`; live captures. Constants:
[reference/constants.md#land-turn-procs](../reference/constants.md#land-turn-procs).

---

When the stick target is a hard reversal — `cLib_distanceAngleS(m34E8, current.angle.y) > 0x7800`
(≈ >168°) with `msd > 0.05`, no attention lock — `checkNextMode` routes *away* from the plain
[MOVE](walk-run.md) proc into one of three turn procs (no reversal ⇒ the aligned walk keeps
facing≈travel, so these never fire on-axis):

- **`procWaitTurn` (`WAIT_TURN`, 23)** — reversal from a **standstill** (`|mNormalSpeed| ≤ 0.001`). Link
  **pivots in place**: `mNormalSpeed` stays 0 while facing+travel rotate ~180° over ~5 frames, then it
  drops to WAIT and walks off in the new direction. (Flick down from the idle anchor → face-about.)
- **`procMoveTurn` (`MOVE_TURN`, 24)** — reversal while **moving below the slip threshold**
  (`speedF/mMaxNormalSpeed ≤ mSlip.field_0x4 = 0.6`), or as SLIP's hand-off. Travel flips to the new
  heading immediately (`current.angle.y += 0x8000`), `mNormalSpeed` is halved, then facing sweeps around
  to the new travel (`cLib_addCalcAngleS`) while it re-accelerates to the cap — a quick turn-around. It
  stays MOVE_TURN until facing == travel, then routes to MOVE.
- **`procSlip` (`SLIP`, 25)** — reversal while **moving fast** (`speedF/mMaxNormalSpeed > 0.6`, non-ice,
  and `getDirectionFromAngle(m34EA − m34DC) == BACKWARD` — i.e. the stick genuinely *flipped* between
  frames). Entry speed `mNormalSpeed = speedF · mSlip.field_0x8 (1.1)` (uncapped, e.g. 17 → 18.7). Link
  **keeps sliding FORWARD** (travel held at the old heading) while `mNormalSpeed` decelerates ~−1.25/frame
  through the skid; once it bleeds to ~0 it flips travel by 0x8000, re-seeds `mNormalSpeed = cap·0.5`,
  and hands to `MOVE_TURN`. So a full-speed reverse is **SLIP → MOVE_TURN → MOVE**.

## The idle-vs-moving reversal gate

The reversal early-return in `setSpeedAndAngleNormal` (2766) hinges on `ModeFlg_00000001` (set for the
idle procs WAIT / FREE_WAIT / WAIT_TURN, *not* MOVE / MOVE_TURN / SLIP): while idle a reversal is inert
(angles untouched), so `checkNextMode` sees the full >0x7800 gap and picks `procWaitTurn`; from MOVE the
reversal branch first chases/holds travel (dropping a slow reversal below 0x7800) so `checkNextMode`
routes via the SLIP / MOVE_TURN(1) / DIR_BACKWARD arms instead.

## Position bit-exactness (the toe-stream warming)

Locked by `run_land_tests` `waitturn`/`moveturn`/`slip` (sim-vs-live): the transient proc is proven
entered by the sim's `visited` set; the reversed-walk end state is bit-exact; the locked live distances
(690/546/982 on the flat anchor) guard the anchor. `test_moveturn_position_bit_exact` /
`test_waitturn_position_bit_exact` assert d=0.0000.

- **MOVE_TURN** uses the WALK blend (no new anim data): (1) `procMoveTurn_init` calls
  `setBlendMoveAnime(mBasic.field_0xC=2.4)` at 6616 **before** `mNormalSpeed *= 0.5` at 6623 — so the
  walk anim is posed at the *pre-halving* speed while `posMoveFromFootPos` integrates with the halved
  speed (the anim engine takes an `anim_nspeed` split for that one frame); (2) both the MOVE→MOVE_TURN
  entry *and* the MOVE_TURN→MOVE exit re-trigger the morf, re-warming the walk blend.
- **WAIT_TURN** poses `ANM_ROT` through the pivot (`setSingleMoveAnime`, warms the toe stream); when the
  pivot completes `checkNextMode` drops to WAIT and `procWait_init` runs the idle-proc `setBlendMoveAnime`
  (`ModeFlg_00000001` branch): because `shape_angle.y != m34DE` (the facing just pivoted) it poses the
  turn-in-place walk-step **MOVE0=`ANM_WAITS`, MOVE1=`ANM_ATNWLS`/`ANM_ATNWRS`** at ratio
  `clamp(0.5 + 0.001·|Δfacing|, 0, 1)` (`m3598=0`, morf 2.4). That `ATNW` pose (not `WAITS`) is what
  makes the walk-off entry drift `f31_2 = |ATNW@0 − ROT@last|` bit-exact (≈3.06 on the first moving
  frame) — a plain `WAITS@0` undershoots by 0.7u over the arc.
- **SLIP → MOVE_TURN** is bit-exact too. The skid is pure momentum (position exact on its own), but the
  `ANM_SLIP` pose feeds the MOVE_TURN walk tail's toe stream. The last unported detail: **`ANM_SLIP`
  scales foot-chain joint 37's X by 1.2**; the FK now builds the joint matrix as **M = R·diag(scale)**
  (a no-op for the identity-scale walk/dash/rollf anims) and carries `old_scale` through the
  oldframe-morf. `slip` pos_z now d=0.005 (advancewith/advanceseq pipe noise, not sim error). **No land
  tech is on the position fallback.**

## See also

- [Land movement overview](land-movement.md) · [walk-run](walk-run.md) · [brakeslide-ebs](brakeslide-ebs.md).
- [model/land-sim](../model/land-sim.md) (the `speedF < 0.05` slip-skid snap + position precision).
