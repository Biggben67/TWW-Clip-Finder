# Tetra (NPC `Zl1`) - the look-at head: eyePos + attention position

**Answers:** Where does Tetra's **eyePos** (the point Link's ATN_ACTOR `setShapeAngleToAtnActor`
re-aim chases) come from, frame by frame? Where is her **attention position** (the camera's lock
target)? How do her head and backbone turn to look at Link, which animation plays while she is
plowed, and what hidden state does a from-seed replay need?
**Status:** LIVE-VALIDATED 0-ULP. The model
([`tww_sim/core/npc_zl1_look.Zl1Look`](../../tww_sim/core/npc_zl1_look.py)) reproduced every live
eyePos, attention position, chased joint angle, clamped target and half-angle twist bit-exactly over a
44-frame window given the live per-frame inputs. **No offline gate ships in this repo:** her skeleton
and animation banks are disc-extracted to the gitignored `_generated/anim/zl1_{skeleton,anims}.json`
by [`harness/anim/extract_zl1.py`](../../harness/anim/extract_zl1.py), so the model cannot even load
on a clean clone, and the live fixture went with the route search that produced it. Re-extract and
re-capture before trusting a change.
**Source:** decomp GZLJ01 `daNpc_Zl1_c` (`lookBack`, `setAttention`, `setMtx`, `_nodeCB_Head` /
`_nodeCB_BackBone`, `optn_1`, `setAnm`/`setAnm_NUM`, `play_animation`; `d_a_npc_zl1.cpp`),
`dNpc_JntCtrl_c` (`lookAtTarget_2` + turn/clamp helpers, `d_npc.cpp:775-915`), `dNpc_playerEyePos`
(`d_npc.cpp:609`), `mDoExt_McaMorf` (`m_Do_ext.cpp:1267-1560`), `J3DFrameCtrl::update`
(`J3DAnimation.cpp:143`), `mDoMtx_*rot*` (`m_Do_mtx.cpp`). Values:
[reference/constants-npc.md#zl1-look](../reference/constants-npc.md#zl1-look).

---

## The two outputs

- **`attention_info.position`** - `setAttention` (`:1277`), every execute frame:
  `(pos.x, f32(pos.y + 140.0), pos.z)` at her **post-move** position (140.0 = HIO `field_1C`). That
  is all: feet plus a constant. The camera consumes it during lock windows
  ([land-camera.md](land-camera.md)).
- **`eyePos`** - her **animated head-joint world position** pushed through the look-at twists plus a
  constant offset (`_nodeCB_Head`, `:167-182`):

      eye = anmMtx(head) . RotY(-head_y/2) . RotZ(-head_x/2) . (20, -16, 0)

  where `anmMtx(head)` is the head joint's world matrix from the model calc in `setMtx` (execute pass,
  post-move position) and `head_x/2`, `head_y/2` are the stored half-angles (`field_0x83C`/`E` - the
  other half of the look goes to her pupils via `eye_ctrl`). Link's re-aim reads the value Tetra wrote
  LAST frame, because Link executes before `Zl1` in the actor list.

## The head FK chain

`setMtx`: base = `transS(current.pos) . ZXYrotM(current.angle)` (angle x/z are 0 in the plowed
regime, so the base is translate x RotY(travel)); then the `zl.bdl` chain
`world_root(0) -> stomach(1) -> chest(2) -> neck(5) -> head(6)` posed by the playing BCK via
`mDoExt_McaMorf` - a single anim plus an 8-frame quat-lerp morf on anim switches, the same old-pose
blend machinery as Link's engine. All chain scale tracks are static 1.0, so the Maya scale / SSC
branches are no-ops. Two node callbacks apply the look-at:

- **chest** (`_nodeCB_BackBone`): `M . RotX(backbone_y) . RotZ(-backbone_x)`, which propagates to neck
  and head;
- **head** (`_nodeCB_Head`): records the head world origin, then the negative HALF angles as above
  (mDoMtx JMAS-table rotations, post-multiplied).

## The look-at chase (`dNpc_JntCtrl_c::lookAtTarget_2`)

Every execute frame `lookBack` runs the chase with source `(pos.x, eyePos.y, pos.z)` - her PRE-move
position at her own previous eye height - and target `dNpc_playerEyePos(-20)` =
`(link.pos.x, mHeadTopPos.y - 20, link.pos.z)`, Link's exec-pass head-top Y over his feet
(`FootFK.head_top`: `anmMtx(head_jnt 15) . (40,0,0)`, written right after the same
`mpCLModel->calc()` that `setCollision` reads). Note the asymmetry: the source is pre-move, the
FK base is post-move.

The yaw delta splits between head and backbone through the `chkLim` clamp cascade (head first or
backbone first, keyed on the old backbone target's sign); elevation splits head-clamp-first. All four
angles chase their clamped targets with `cLib_addCalcAngleL(angle, target, 4, step, 4)`. The body-turn
branch (`mbTrn`) is blocked in the plowed regime (`optn_1` sets `field_0x7D8`), so her
`current.angle.y` never moves.

## The plowed-idle anim machine

`setStt(3)` selects **wait03.bck** (40f, LOOP, rate 1.0, morf 8) and seeds the look-around countdown
`field_0x7B8 = rnd(90, 180)`. Each `optn_1` frame in plow range with no talk decrements it; at 0 she
switches to **look.bck** (80f, LOOP, morf 8) with `field_0x84D = 0` (target released, so the chase
decays home) for `(g_Counter & 1) + 1` anim wraps, then returns to wait03 and **reseeds `7B8` from the
global RNG stream**.

That reseed is unmodelable offline, so the model flags a `rng_horizon` there rather than inventing a
value - the same guard class as the follow model's distance warning. A window shorter than the seeded
timer never reaches it; a window longer than timer + one look cycle crosses it and its later frames
are not predictions.

## Hidden seed state

`Zl1Look.seed_from_row` consumes: the four chased `mAngles` plus the clamped targets
(`f2C`/`f2E`/`f30`/`f32`), `mbTrn`, the McaMorf frame ctrl plus cur/prev morf and step, the current
anim number (`f849`), the timers `f7B8`/`f7BA`/`f7BC`, the wrap flag `f7C3` plus `mFrame`, the
half-angles `f83C`/`f83E`, her `eyePos`, and `travel`. A morf ACTIVE at the seed would also need the
per-joint old-pose store.

## Open

- Her `pos.y` is tracked static in replays (live `CrrPos` wiggles it ~1e-5 u) - a last-bit echo in eye
  and attention Y only.
- The morf (anim-switch) pose path is decomp-faithful but has **no live ground truth**: no switch
  occurred inside the validated window, because the look timer was seeded past its end. A look-anim
  window capture would gate it.

## See also

- [link-head-look.md](link-head-look.md) - Link's own `m3564` twist, which moves the head-top Y this
  chase targets.
- [tetra-follow.md](tetra-follow.md) - her movement, follow regime and attention region.
- [../model/porting-the-look-pair.md](../model/porting-the-look-pair.md) - running this model and
  Link's inside a native frame, and what a gate for a long-memory model has to compare.
