# Constants - NPC / actor (canonical values)

**Answers:** What are the actor-vs-actor Co-push values (radii, weights, the rank split)? Tetra's
(`Zl1`) look-at clamps, chase steps, and attention offset?
**Status:** validated (decomp + live) unless a row says otherwise.
**Source:** per-row. Split from [constants.md](constants.md) (that page hit its size cap); same
contract - this table is the single source of truth, other pages link here instead of restating.

---

<a id="collision-actor-co-push"></a>
## Collision (actor Co push)

The actor-vs-actor "Co" push (a [Tetra nudge](../mechanics/actor-push.md)). Distinct from the
player wall cylinders ([constants.md#collision-player-wall-cylinders](constants.md#collision-player-wall-cylinders)).
All live-confirmed on GZLJ01.

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Link Co radius | **30.0** (walking/rolling); 50.0 only if `checkGrabWear()` | Link body Co cylinder radius | decomp `daPy_lk_c::setCollision` (d_a_player_main.cpp:9762/9760) |
| Link Co height | **≈107** walking (`40.1 + neck−toe`); 81.25 in FRONT_ROLL | Link body Co cylinder height | decomp same fn (:9794/9780) |
| Link Co center | midpoint(root_jnt, neck_jnt) XZ; toe_jnt Y (feet in FRONT_ROLL) | animation-driven, **not** `current.pos` | decomp same fn (:9753/9792); [link-co-centre.md](../mechanics/link-co-centre.md) |
| Tetra Co radius / height | **50.0 / 140.0**, center = `current.pos` | Tetra (`Zl1`) body Co cylinder | live read |
| Link weight / rank | **120** → rank **5** | `mStts.SetWeight(120)`; `dCcS::GetRank` | decomp `:11233`, `d_cc_s.cpp:153` |
| Tetra weight / rank | **0x8C=140** → rank **5** (the `field_0x84F==5` variant; else 0xFF→10) | live read | decomp `d_a_npc_zl1.cpp:428` |
| Push share (rank 5 vs 5) | **0.50 / 0.50** | `rank_tbl[5][5]=50` → Link takes 0.50× depth, Tetra recoils 0.50× | decomp `d_cc_s.cpp:138`, live |
| Co deadzone | **1e-5** (`cM3d_IsZero(cross_len)`) | `dCcS::SetPosCorrect` skip threshold (base `cCcS` uses 1/125) | decomp `d_cc_s.cpp:190` |

The **game uses `dCcS::SetPosCorrect`** (virtual override, JP 0x800AB1E4), whose weight split is
the `rank_tbl` above - NOT the base `cCcS` mass-proportional split (JP 0x8024101C, never fires
live).

<a id="zl1-look"></a>
## Zl1 (Tetra) look-at head

The look-at chase + eye/attention offsets ([mechanics/tetra-look.md](../mechanics/tetra-look.md)).
Decomp `daNpc_Zl1_c` HIO `a_prm_tbl` (d_a_npc_zl1.cpp:85-118) + `dNpc_JntCtrl_c::setParam`;
live-confirmed against a flooded-Hyrule capture.

| Constant | Value | Meaning | Source |
|----------|-------|---------|--------|
| Attention Y offset | **140.0** | `attention_info.position.y = pos.y + this` (`setAttention`) | HIO `field_1C` |
| Eye offset | **(20, -16, 0)** | `_nodeCB_Head` head-local eye position | `a_eye_pos_off` (:169) |
| Head clamps (x, y) | **±0x18E2 / ±0x2328** (mins mirror: 0xE71E/0xDCD8) | look elevation / yaw head share | HIO `mMaxHeadX/Y`, `mMinHeadX/Y` |
| Backbone clamp x | **max 0x0BB8, min −0x071C (0xF8E4)** | elevation backbone share | HIO `mMaxBackboneX/mMinBackboneX` |
| Backbone clamp y | **±0x03E8** (min 0xFC18) | yaw backbone share | HIO `mMaxBackboneY/mMinBackboneY` |
| Chase step | **0x1000** while `field_0x7BC < 0`, else **0x0180** | `cLib_addCalcAngleL(angle, tgt, 4, step, 4)`, all four angles | HIO `mMaxTurnStep` / `field_5C` |
| Player eye target | `(link.x, mHeadTopPos.y − 20, link.z)` | `dNpc_playerEyePos(-20)`; Link head-top = `anmMtx(15)·(40,0,0)` | d_npc.cpp:609, d_a_player_main.cpp:11592 |
| stt-3 anims | **wait03.bck** (40f) / **look.bck** (80f), both LOOP, rate 1.0, **morf 8** | the plowed idle + the random look-around | `setAnm`/`setAnm_NUM` prm tables |
| Look timer | **rnd(0x5A, 0xB4)** at `setStt(3)` + each look return | `field_0x7B8` countdown to the look anim | `setStt`/`optn_1` |
