# Tetra (NPC `Zl1`) - follow behaviour + lock-on/talk region

**Answers:** When and how does Tetra follow Link around (follow radius, turn, speed)? Where does she
stop? When can Link **lock onto / talk to / speak to** her (the region a planner must AVOID so an
A- or L-press doesn't trigger a conversation instead of the intended action)? Which Tetra variant is
this, and where do the numbers come from?
**Status:** LIVE-VALIDATED 0-ULP (2026-07-10). The follow integrator
([`tww_sim/core/npc_zl1.Zl1FollowState`](../../tww_sim/core/npc_zl1.py)) reproduces the live
type-5 Tetra frame-for-frame across engage → turn → accelerate → distance-capped cruise →
decelerate → stop (`tests/test_tetra_follow.py`, fixture `fixtures/hyrule_tetra_follow.json` from
`harness/rollstab/capture_tetra_follow.py`, flooded Hyrule savestate slot 3). Her BG collision
(`mObjAcch.CrrPos` WallCorrect, R=50/half-H=30) is also live-validated 0-ULP (corner-wall eject,
`fixtures/hyrule_tetra_wallcorrect.json`) - the wall-brace mechanic (a wedged Tetra's CC recoil is
canceled so she holds in place); whether corner-bracing helps the clip is OPEN (it pushes the wrong
way -- see below). The lock-on/talk region (`zl1_attention_active`) is
decomp-exact; its live reticle confirmation is still open (see Open below). Partial model on purpose
- event/demo/cutscene, message flow, eye/joint control, and water FX are out of scope.
**Source:** decomp GZLJ01 `daNpc_Zl1_c` (`optn_1`/`optn_2`/`optn_action1`, `createInit`,
`init_ZL1_5`, `chk_areaIN`, `setAttention`; `d_a_npc_zl1.cpp`), `dAttention_c::calcWeight` +
`check_distace` + `check_flontofplayer` (`d_attention.cpp`) + `dist_table` (`d_att_dist.cpp`),
`fopAcM_posMoveF`/`calcSpeed`/`posMove` (`f_op_actor_mng.cpp`), `cLib_addCalcAngleS`/`cLib_chaseF`/
`cLib_targetAngleY` (`c_lib.cpp`). Shared Co-push cylinder/weight constants:
[reference/constants-npc.md#collision-actor-co-push](../reference/constants-npc.md#collision-actor-co-push).

---

## Which Tetra this is

The flooded-Hyrule following Tetra is the **type-5** variant (`fopAcM_GetParam & 0xFF == 5` →
`field_0x84F == 5`, live-confirmed `actor+0x84F == 5`). `init_ZL1_5` installs the `optn_action1`
action and gives her weight `0x8C = 140` (rank 5, == Link) - the same variant [[tetra-push-model]]
uses. Other types (ship Zelda, cutscene Tetra) run different action funcs and are not modelled here.

## Follow: the idle ↔ move state machine

`optn_action1` dispatches on the action state `field_0x84B` (`actor+0x84B`): **3 = idle** (`optn_1`),
**4 = move** (`optn_2`). Distances are **3D** (`fopAcM_searchActorDistance2` = `delta.abs2()`), so the
gates compare `dist²` to the squared thresholds.

- **Idle (`optn_1`, stt 3):** if `dist² ≥ 230²` (`field_34 + 100`), turn toward Link
  (`cLib_addCalcAngleS(angle.y, angleToLink, 4, 0x800, 0x80)`); once the facing error `< 0x1800`
  (~33.75°), `setStt(4)`. speedF stays 0 (idle zeroed it). The `setStt` takes effect **next** frame
  (the `field_0x84B` switch is read once per frame), so the first move frame still moves 0.
- **Move (`optn_2`, stt 4):** target speed `vT = dist² > 130² ? min(0.04·√(dist² − 130²), 10.0) : 0`
  (`field_38 = 0.04`, `field_3C = 10`); turn toward Link (same params); `cLib_chaseF(speedF, vT, 1.0)`
  (accelerate/decelerate 1 u/f). When `(int)vT == 0 && (int)speedF == 0`, `setStt(3)` → idle.
- **Move integration:** `posMoveF` → `calcSpeed` (`xSpeed = speedF·cM_ssin(angle.y)`,
  `zSpeed = speedF·cM_scos(angle.y)`, `y += gravity −4.5`) → `posMove` (`pos += speed`, then `+=` the
  consumed CC recoil) → `CrrPos`. On the flat corner floor/water surface `CrrPos` holds Y, so the
  follow is an XZ + facing + speedF system.

**Net follow radius (hysteresis):** she **engages when Link is > 230 u away**, chases at up to
**10 u/f** (accel 1 u/f, speed scaled by `0.04·√(dist² − 130²)`), and **decelerates to a full stop
once he is back within 130 u**. Live: peak speedF 9.23 at ~250 u, settling to a stop at ~132 u.

## BG collision (her `mObjAcch.CrrPos` wall pass)

Every frame `_execute` runs `mObjAcch.CrrPos` after `posMove`. `mObjAcch` is a `dBgS_ObjAcch :
public dBgS_Acch` that does **not** override `CrrPos`, so her wall/ground pass is the *same*
player-faithful pass ported for Phase W (`core.collision.acch_crr_pos`); she differs from Link only
in (a) her wall-check cylinder, a **single** `dBgS_AcchCir` at **R=50, half-H=30**
(`mAcchCir.SetWall(30,50)`, `mObjAcch.Set(..., tbl_size=1, ...)`; Link has a 3-band R=35 cylinder),
and (b) the poly pass-through flag (`SetObj` → `mbObjThrough`, matters only for polys carrying that
attribute bit). `Zl1FollowState.step(walls=...)` runs it with her cylinder. On the flat corner
floor/water she floats with **speed.y == 0 every frame** (live-confirmed), so the pass runs
`speed_y = 0` (at 1-ULP scale `speed_y = -4.5` mis-ejects a wall-corrected XZ by 1 ULP).

The follow's 130 u keep-distance means she never touches a wall in a *normal* chase (the wall pass
no-ops, live 0-ULP over 119 frames). The wall pass is a validated MECHANIC for a wedged Tetra: her
`CrrPos` WallCorrect **cancels her CC recoil** (she would otherwise recoil away each overlap frame, the
[[tetra-push-model]] frame-lag caveat), so a wall holds her in place. Whether that helps the **clip** is
a separate, OPEN question (session-19 correction): a corner-braced Tetra pushes the WRONG way (out of
the seam) and a stationary behind-Link Tetra gets plowed by Link's roll, so the clip STAGING is unsolved
(see the rollstab `README.md` ## Status / [[seam-clip-solver]]). Live-validated 0-ULP: overlapping the
corner `+x` wall (x = −1727, normal +x) she ejects to the exact live XZ (`capture_tetra_wallcorrect.py` →
`fixtures/hyrule_tetra_wallcorrect.json`, `tests/test_tetra_follow.py`). The `move_jmp` gap hop
(over a ledge) is still unmodelled (no gate exercises it; the corner floor is flat).

## Lock-on / talk / speak region (planner AVOID)

Tetra's `attention_info` (`createInit`) sets `flags = LOCKON_TALK | ACTION_SPEAK` and
`distances[TALK] = distances[SPEAK] = 0xAB`, at `position = current.pos + (0, 140, 0)`. The player
attention system (`dAttention_c::calcWeight` → `check_distace` + `check_flontofplayer`) uses
`dist_table[0xAB]` to decide whether she is a valid **L-target / talk / speak** target. She is
eligible when **all** hold:

- **XZ distance < 300 u** (`mDistXZMax = 300`, `mDistXZAngleAdjust = 0` → constant, no angle widening);
- **|Δy| < 300** between the attention points (Tetra's is `pos.y + 140`);
- **Link's facing is within ±90° (`0x4000`) of the direction toward Tetra** - front-cone bits
  `0x0004` reject only `angle1 > 0x4000`, where `angle1 = (dir Link→Tetra) − Link.shape_angle.y`.
  Tetra's own facing does not matter.

`zl1_attention_active(link_pos, link_facing, tetra_pos)` returns exactly this predicate. It is
**necessary-not-sufficient** for an actual lock/talk (the real thing also needs her to be the
best-weighted target and the button pressed), so as a keep-out region it is conservative: **outside
it she cannot be locked/talked; inside it a live A/L can engage her.** A planner must keep Link out
of it on any frame where an A- or L-press is live for another purpose (or accept that Link talks /
locks Tetra instead). The lock-on release distance is also 300 (`mDistXZMaxRelease`).

> During the roll-stab clip itself Link is in FRONT_ROLL/CUT (A = cut, not talk), so the talk risk is
> in the **setup walk-up**, where an idle Link facing Tetra within 300 u shows the prompt.

The A-press DECISION chain built on this region - how a roll's A gets eaten by a conversation, why
the walk-END state is the input rather than the dispatch frame's aim, and the exact `cSGlobe.U()`
bearing the cone compares - is its own page: [talk-eat.md](talk-eat.md).

## Values (canonical here; shared Co-push cylinder/weight in constants-npc.md)

`daNpc_Zl1_HIO_c` `a_prm_tbl` (`d_a_npc_zl1.cpp:85`) + `dist_table[0xAB]` (`d_att_dist.cpp`).
These are un-versioned source literals → the GZLJ01 (JP) values equal the decomp (see
[[jp-vs-us-decomp-addresses]]).

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Follow keep distance | **130.0** (`field_34`) | target speed 0 at/below; decel target | `d_a_npc_zl1.cpp:107` |
| Follow engage distance | **230.0** (`field_34 + 100`) | idle→move: 3D `dist >` this | `optn_1` :2269 |
| Follow speed gain | **0.04** (`field_38`) | `vT = gain·√(dist² − 130²)` | `optn_2` :2341 |
| Follow speed cap | **10.0** (`field_3C`) | `cLib_maxLimit` on `vT` | `optn_2` :2342 |
| Follow accel | **1.0** (`field_44`) | `cLib_chaseF` step (u/frame) | `optn_2` :2347 |
| Follow turn | scale **4**, max **0x800**, min **0x80** | `cLib_addCalcAngleS` toward Link | `optn_1`/`optn_2` |
| Engage facing gate | **0x1800** (~33.75°) | idle must face within this before moving | `optn_1` :2287 |
| Gravity | **−4.5** | `init_ZL1_5`; applied in `calcSpeed` | `d_a_npc_zl1.cpp:364` |
| Attention height | **140.0** (`field_1C`) | `attention_info.position.y = pos.y + this` | `setAttention` :1278 |
| Talk/speak dist index | **0xAB** | `distances[TALK]=[SPEAK]` → `dist_table[0xAB]` | `createInit` :403 |
| Lock-on/talk XZ range | **300.0** (`mDistXZMax`, adjust 0) | eligibility + release radius | `d_att_dist.cpp` 0xAB |
| Lock-on/talk ΔY band | **(−300, 300)** | `mDeltaYMin/Max` | `d_att_dist.cpp` 0xAB |
| Front cone | **±0x4000 (90°)** | bits `0x0004` → reject `|angle1| > 0x4000` | `check_flontofplayer` |
| BG wall cylinder | **R=50, half-H=30** (single AcchCir) | `mObjAcch.CrrPos` WallCorrect | `d_a_npc_zl1.cpp:3022` |
| Grounded speed.y | **0** (floats on corner water) | wall-pass `speed_y` (1-ULP sensitive) | live |

## Open / follow-ups

- **Live reticle confirmation** of the lock-on/talk region (drive Link toward Tetra, read the
  attention lock state, confirm the 300 u / ±90° boundary). The predicate is decomp-exact but
  unverified against the on-screen reticle.
- **Read-lag** (which frame's Link pos Tetra reads) is unpinned - the follow gate used a stationary
  Link. A moving-Link capture would fix it (cf. the foot 1-frame lag in [[land-bitperfect-frontier]]).
- **`move_jmp` gap hop** (over a ledge) is unmodelled - no gate exercises it and the corner floor is
  flat. The wall half of `CrrPos` IS modelled (validated above).

## See also
- [mechanics/actor-push.md](actor-push.md) - the CC "Co" push this Tetra feeds into a seam clip
  (cylinder/weight/rank; [[tetra-push-model]]).
- [strategy/seam-clip-solver.md](../strategy/seam-clip-solver.md) - the seam-clip pipeline (Phase C
  needs this Tetra counterpart state).
- [reference/constants-npc.md#collision-actor-co-push](../reference/constants-npc.md#collision-actor-co-push)
  - shared Co-push cylinder/weight/rank constants.
