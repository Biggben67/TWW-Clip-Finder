# Roll (FRONT_ROLL) — the fast approach movement

**Answers:** How does the forward roll work / what speed does it carry / how long? What is the
frame-perfect roll-EBS exit? How do chained rolls cover ground, and how do you get intermediate roll
speeds? Why does a roll make the C-up freeze analytic?
**Status:** validated live — the roll is **fully bit-exact** entry-to-standstill AND the roll-EBS exit
(`tww_sim.land`, pos_z d≈0.0001, roll-EBS speed −23.109 bit-exact). Intermediate roll speeds are
live-gated (2026-07-05k).
**Source:** decomp `d_a_player_main.cpp` `procFrontRoll_init` / `checkNextMode` / `posMoveFromFootPos`;
live captures. Constants: [reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

Press **A** (the "do" button, `dActStts_ATTACK_e`) while moving on the ground → **`procFrontRoll_init`
(state 30)**, `ANM_ROLLF`. On entry, facing snaps to the stick target (`shape_angle.y = m34E8`).
- **Speed (set once at entry, from the PRE-roll `speedF`):** `mNormalSpeed = clamp(speedF·1.5 + 0.5,
  5.0, 26.0)`. Full-run (`speedF` 17) → the **26 cap**; barely-moving → the **5.0 floor**. A big boost
  — 26 vs the walk cap 17 — which is why rolling is the workhorse ground-cover tech. During the roll
  `speedF == mNormalSpeed` (constant momentum; **no foot-plant blend**, `m3598 = 0`), so position
  advances at the roll speed exactly.
- **Duration:** state 30 while the `ANM_ROLLF` frame ctrl runs ~0→17 (`mRoll.field_0x10`, rate 1.1,
  ≈18 frames), then `checkNextMode(1)` exits to MOVE carrying the speed, which decels to a stop (a
  full-run roll travels ≈ **760 units** — pos_z 764→1525 on the flat anchor).
- Rolling **into a wall** → `procFrontRollCrash` (needs `speedF ≥ 10` = `field_0x3C`); inert on flat
  wall-free ground.

## Frame-perfect EBS out of a roll (~−23)

HOLD **L + full-down through the roll**. Because the stick is pushed, the `getFrame()>17`
(`field_0x10`) early-turn `checkNextMode(1)` fires *one frame before* the anim-end exit — and since L
is held it routes to **ATN_MOVE at the full 26** (skipping both the `getRate<0.01` branch's `−5` and
the roll→MOVE walk decel). Then **release L into ESS-down** → the ATN backward-flip preserves it as
**≈ −23.1** speed (state 6 EBS). A one-frame window — release a frame late and the roll→MOVE decel
bleeds it to ~−18; a frame early and it dead-stops. This combo (huge negative speed from a roll) is a
prime seam-clip setup, and the first step of the [wiggle-EBS chain](brakeslide-ebs.md#wiggle-ebs--lup-cancel--chained-roll).

## Simulation

`tww_sim.land`, `step` with A = button `0x100`: the roll is **fully bit-exact, entry to standstill AND
the roll-EBS exit** (`roll_run`/`roll_slow`/`roll_settle`/`roll_ebs` are all sim-vs-live). Two exits:
with a **neutral** stick the `getFrame()>17` early-turn `checkNextMode(1)` is inert (false when
`msd≤0.05` and no action button), so the roll runs to the anim end (`getRate<0.01`), takes
`mNormalSpeed -= 5.0` (26→21), and MOVE decels to a stop; with a **pushed** stick that early exit fires
one frame sooner (no `−5`) and routes to ATN_MOVE (L held) or MOVE — the roll-EBS above.
- **The low-speed post-roll tail** (`nspeed < 17`, where the walk foot-plant `m3598 > 0` resumes) is
  bit-exact because `posMoveFromFootPos` runs *every* frame — including the roll — so the foot engine
  poses `ANM_ROLLF` (a `setSingleMoveAnime`, MOVE0=rollf, MOVE1=NULL, `m34C3=0`) throughout the roll
  and keeps the smoothed toe-delta stream (`m359C`) warm. On the roll→MOVE exit the walk blend re-inits
  its frame ctrl to **frame 0** *because* `m34C3 == 0`, and `procMove_init` re-triggers the oldframe-morf
  (`mBasic.field_0xC` = 2.4). Foot engine: `tww_sim/core/anim/foot_speedf.py` `enter_roll`/`step_roll`.

## Chained rolls (26 u/frame ground cover)

`mNormalSpeed = clamp(speedF·1.5 + 0.5, 5, 26)`, and the cap 26 = `0.5 + 17·1.5`, so **any pre-roll
`speedF ≥ 17` re-rolls to the full 26**. A re-roll only registers from **MOVE** (never mid-ROLL — the
`a_pressed and grounded` gate excludes FRONT_ROLL) and carries the 2-frame `INPUT_DELAY`, so a chained
cycle is **19 frames = +486.5u (25.6 u/frame)** — you can't re-press sooner. (Native path: `roll_frame`
is NOT synced — read the state tag, not the frame ctrl.) See [strategy/roll-launch.md](../strategy/roll-launch.md)
for the fastest standstill→roll-chain launch.

## Intermediate roll speeds — decay `speedF` below 17 first

The re-roll clamps `speedF·1.5+0.5`, and `speedF ≥ 17 → 26`. **Holding full up between rolls keeps
`speedF` floored at the walk cap 17, so every chained roll is 26** — the 26→23.5→21→18.6 values you see
while holding up are the post-roll `speedF` **decay readouts**, NOT the resulting roll speed (they
re-clamp to 26). To get a genuine sub-26 roll you must **reduce the stick** before re-pressing A so
`speedF` settles below 17. The clean recipe is a **partial FORWARD hold** `(128, Y)` (`Y ≤ 191`,
live-valid) for a frame or two, then A: `speedF` decays toward that stick's walk cap `17·msd²`, and the
re-roll clamps it — giving a **continuous, live-valid, forward-moving** ladder of ~40 distinct speeds
5→26 (e.g. `Y187` ×2 → 23.7, `Y171` ×2 → 25.36, `Y180` ×5 → 13.8). This is the **densifier knob** in
the freeze planner (`reach_freeze(roll=True, roll_speed_min<26)`) — see
[model/land-planner.md](../model/land-planner.md#fewest-frame-freeze-via-a-roll-approach--and-the-analytic-solve-2026-07-05j).

## The roll RESETS the walk anim → the C-up freeze is analytic

Because the roll's `setSingleMoveAnime` leaves `m34C3 == 0`, the roll→MOVE exit re-inits the walk frame
ctrl to **frame 0**: post-roll **`anim_fc0 == 0` for every approach** (start crawl / accel length /
roll count — bit-exact). This kills the walk anim's sub-frame **precession** (the thing that blocks the
walk freeze's sub-second solve). After the first roll everything is **history-independent** — each roll
adds a fixed +486.5u, the post-roll walk-tail freeze coast is a **fixed table**, and a start-crawl
position offset carries through the roll **exactly**. So the [C-up freeze](precise-stop.md) after a
roll approach is `freeze = freeze_ref(nr, r) + δ(start)`, a closed-form/analytic solve (~15–30 frames
below the walk floor). Model + frame savings: [model/land-planner.md](../model/land-planner.md#fewest-frame-freeze-via-a-roll-approach--and-the-analytic-solve-2026-07-05j).

## See also

- [Land movement overview](land-movement.md) · [walk-run](walk-run.md) · [brakeslide-ebs](brakeslide-ebs.md) ·
  [roll-stab](roll-stab.md) (sword thrust out of a roll — the seam-clip lunge) · [precise-stop](precise-stop.md).
- [strategy/roll-launch](../strategy/roll-launch.md) — fastest standstill→roll chain.
