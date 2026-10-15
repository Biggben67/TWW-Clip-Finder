# Seam-clip north star: the TETRA seam clip, pure-sim (multi-session roadmap)

> **The Tetra north star is HIT (Phase T, session 22/24). The CURRENT north star is Phase A below:
> refine the screen->mint->solve->deliver pipeline until an ARBITRARY game state + a reasonably
> close target seam yields the clip inputs one-shot.** Adopted with Dereck, session 58.

## Phase A -- arbitrary-state seam clipping (CURRENT north star, adopted 2026-07-18 session 58)

The generalized pipeline delivers a screened corner per session (proven/sheathed/mirror/152/157
all live 0-ULP), but it still assumes: a mintable settled idle ~580u out, a freezable camera, a
straight ~1000u corridor, one room (kaze r11), and several manual steps per delivery. The end
state is: **feed an arbitrary game state + a nearby target seam, get the input sequence.** Steps
ordered so each strictly removes one assumption; do them IN ORDER -- 1-4 are refinement (no new
physics), 5-6 are the expansion and wait until 1-4 are boring:

1. **Make the recipe boring** -- deliver the queued screen picks verbatim (`seam_0465_0474` the
   152's z-mirror 0.458u band, likely cheapest; `seam_0467_0468`; `seam_0824_0826`), counting
   every manual touch per delivery. Exit: N-for-N with a written touch-list. (97m lottery keeps
   running in spare cycles; it is priced, not blocked.)
2. **One-shot the pipeline** -- fold the touch-list into a `novel_deliver` command: geo fixture ->
   corridor/cam screen -> `mint_online` (isokey-named) -> REST gate (abort on DIFF) -> dust2d
   prebuild OUTSIDE the draw budget -> `solve_focused` -> `deliver ship` -> golden + test
   scaffold. Exit: a novel screened corner delivers with one command + one review.
3. **Kill the ~580u rest envelope** -- `_derive_a_projs` implicitly assumes the proven rest
   distance (a 300u anchor never fires a capped baseline; ledger #42 corollary). Derive the
   A-proj scan center from the anchor's actual rest-to-seam distance. Exit: a ~300u-rest anchor
   solves; unblocks short-corridor corners (the 163, 5221 samples) without camera work.
4. **Prove it out-of-room** -- capture a second room's ordered wall mesh, screen it, deliver one
   corner there. Exit: no kaze-r11 assumption (flat floor Y, cam regime, mesh path) survives.
5. **Camera-in-the-loop (the old Phase R residual, promoted)** -- RE-SCOPED session 69 after live
   RE. The premise was a free-space behind-Link auto-cam FOLLOW that creeps csangle and needs a
   per-frame model. **Live RE DISPROVED it for the MANUAL / no-L cam the approach uses (dead-end
   #56):** with a centered C-stick and no L, csangle (`mAngleY`) is bit-frozen while Link
   walks/turns/arcs (5 experiments); `dCamera_c::Run` derives csangle from `bearing(eye->center)`
   and `followCamera`'s behind-follow moves the VIEW, not the controlled csangle. (The L-target /
   recenter AUTO cam -- `lockonCamera`, `getDMCAngle` -- IS a distinct mode that moves csangle; it
   is not used by the roll-stab approach and is not characterized here.) So the sim's `CameraManual`
   is already free-space-complete and the
   constant-csangle precondition ALREADY holds in open space. The only csangle contamination is
   `bumpCheck` camera-WALL collision (a lateral eye push in tight corridors), which per steer is
   DETECTED not modeled: `harness/rollstab/cam_clean.py` (csangle-invariance probe along the
   intended approach bearing). REMAINING under this step: (a) **DONE (session 70): `cam_clean` is
   folded into `mint`/`novel_deliver` as `mint.cam_clean_screen`** -- the invariant probe (fixed
   stick + centered horizontal C-stick down the seam bearing, scored by `cam_clean.evaluate`) is now
   `novel_deliver` stage 4, probing the DEFAULT aim target first and flagging a DIRTY corridor with
   its first-drift frame/pos; `cam_screen` is demoted to a legacy diagnostic. Live-verified CLEAN on
   the kaze 157 corridor; gate `tests/test_cam_clean.py::test_park_screen_kaze157_clean`. (b) the
   auto-flip envelope (the fast-move camera FLIP, still open, distinct from the follow); (c) whether
   an arbitrary state's starting csangle offset needs any handling beyond being a sim input (it does
   not, for a clean corridor). The "settle dance / pan mint / corridor constraint" exist to keep the
   arm OFF walls (avoid bumpCheck), not to fight a follow.
6. **Arbitrary entry states (mid-walk etc.)** -- a mid-walk mint/seed (in-flight frame ctrls,
   foot-pose delay buffer, m351C lean, travel/speedF), a mid-walk verification gate replacing
   REST BIT-EXACT, and the DTM row-alignment contract from a mid-anim savestate. Depends on 5
   (a mid-route state has a live camera). The sim half exists (bit-exact mid-walk clone).

The kaze r11 roll-stab clip (Phase 0, DONE) proved the method: a from-rest bit-exact sim +
exact-acceptance search one-shots a razor seam clip live, 0-ULP. The north star is the same
one-shot for the **Tetra Co-push seam clip** ([[tetra-push-model]] memory; corner at
(-1727,-990), ~1.23u Link/Tetra overlap steers the 49.22u roll-stab through). Everything below
is ordered so each phase lands as a standalone, live-gated sim capability.

**Standing rules for every phase** (same as SESSION_PROMPT.md): decomp-first; primitives already
live-proven are PROMOTED into the per-frame stepper, not rediscovered; each phase ends with a
live-data 0-ULP regression test (goldens like `tests/golden/rollstab_rest_*.json`) and a README
`## Status` update; dead ends go to `knowledge/history/seam-clip-dead-ends.md`. A phase is DONE
only on a confirmed live per-frame comparison, never on offline plausibility.

## Phase 0 -- from-rest exact walk + the kaze clip (DONE, 2026-07-10)

Live clip 0-ULP; pure sim, no calibration. See README `## Status` + the session-10 handoff.

## Phase W -- WALL collision in the stepper (DONE 2026-07-10: single-face + corner ordering)

**DONE (session 11):** `LandState(walls=)` runs the per-frame CrrPos wall pass
(`core.collision.acch_crr_pos`) + the proc wall feedback (wall-hold, m3570 bonk latch,
FRONT_ROLL_CRASH modeled, the sidle A-guard with the `sidle_blocked` planner signal). All four
live gates (head-on / oblique slide / roll crash / slow-roll grind) BIT-EXACT per frame on the
minted faceB anchor; goldens + `tests/test_rollstab_walls.py`; model page
`knowledge/mechanics/wall-response.md`. The original "done ==" bar is met for single-face walls.

**DONE (session 12): corner (multi-wall) correction ORDER.** When two non-coplanar walls correct
in one frame the poly order decides the result. The game's order is its DZB block-grid walk
(`WallCorrectGrpRp` -> `WallCorrectRp` octree DFS -> `RwgWallCorrect`); since `ClassifyPlane`
builds each block's wall list in ascending poly index it is reconstructable statically from the DZB
header tables. `capture_walls.py` reconstructs that walk and writes the room's ordered wall mesh;
the sim loads it via `load_ordered_mesh`. Corner gate (`cornergate.py`) on the minted
`kaze_r11_wallcorner` anchor: CORNER GATE BIT-EXACT 48/48 (24 two-wall frames), swapped order
diverges. Golden + `tests/test_rollstab_corner.py`. wallA(705) before wallB(713), block 137.

**Remainder (speed-only; pick up if a corner enters the solver budget):**
- Full-room block-grid AABB cull: the sim iterates all 765 ordered walls (~33 ms/frame
  pure-Python). Far polys already no-op, so the game's octree cull is a pure speed optimization.
- Walls for the ballistic hops + the freeze's early-return frames (no gate exercises them yet).
- NEW non-wall gap found by the grind gate: mid-run stop -> re-walk blend is not bit-exact
  (see README Status); becomes load-bearing for any plan that fully stops mid-run.

## Phase G -- GROUND collision (DONE 2026-07-10 as a flat-floor no-op -- **PROMOTED 2026-07-19**)

> **Session 65: the promotion is BUILT and live-validated through the incline walk.**
> `tww_sim/land/floors.py` + `LandState(floors=, gnd_seed=)`: per-frame gravity dip +
> GroundCross snap (pos_y follows the floor), the speedF slope scale (r3 < 0 uphill x0.85),
> and the m35B8 foot ground-lift -- decomp-first, flat paths byte-identical, offline gates
> `tests/test_floors_ground.py`. The micro-incline tier is EXACT by construction (cM_atan2s
> truncates ratio*1024: slopes < ~0.056 deg have getGroundAngle == 0, so only pos_y + m35B8
> are load-bearing); the ~10-deg ramp tier is UNPORTED and raises `SlopeNotModeled`. The
> GanonA REST gate ran BIT-EXACT rows 0-11 incl. pos_y on the incline; full-corridor
> BIT-EXACT is blocked only by the corridor STONE prop's CC push (ledger #52 -- mint-time
> setup, not a ground gap). Status + next steps: README ## Status (session 65).

> **Session 66: the full-corridor REST gate is GREEN (28/28 rows 0-ULP incl. m359C + pos_y,
> `tests/test_ganona_rest.py`).** The stone is AVOIDED by geometry (geo `aim_deg=186.5` + a
> cam-screened frozen pan target), never consumed; and rows 12+ exposed the last two ground
> terms, now modeled: setStepsOffset's m35C4 walk base-Y lift (:9524/:9561) and footBgCheck's
> non-plant field_0x030 CLOTCH leg lift (:8816) -- both exactly 0 on flat. Model doc:
> `knowledge/model/ground-model.md`. Ramp tier still UNPORTED (SlopeNotModeled).

Measured first, as planned: the walkable floor Link's roll crosses at the (-1727,-990) Tetra corner
is PERFECTLY FLAT. `harness/rollstab/capture_ground.py` (self-contained, `dolphin_mem` only) samples
the DZB ground along the whole roll footprint old->seam (flooded Hyrule, savestate slot 3): a single
tri (poly 2917), normal (0,1,0), plane Y=0.16327, covers the entire footprint; the normal recomputed
from raw vertices == the game's stored plane == (0, 1, 8e-08). (The ~25-deg surface that shares the
XZ footprint sits ~560u OVERHEAD -- Hyrule terrain -- and the roll at Y~0.16 never touches it; that
was the only thing that could have made "flat" wrong, and it is ruled out.) So `getGroundAngle`'s
slope term r3 = 0 (the sim already hardcodes r3=0 in the speedF `cM_scos` scale; the r3<0 x0.85
branch never fires) and the m35B8 per-foot ground-lift is provably 0 -- the existing flat-floor model
(exact at kaze, also flat) applies to the Tetra clip UNCHANGED. No GroundCross / getGroundAngle /
m35B8 modeling is needed. Fixture `fixtures/hyrule_tetra_ground.json`; regression
`tests/test_tetra_ground.py` (flatness + full-footprint coverage + single-plane; goes RED if a future
Tetra spot ever shows slope -- the signal Phase G modeling has become load-bearing).

## Phase C -- CC collision Link<->Tetra in the stepper

The push model is live-confirmed but lives in standalone probes (`cc_push.py`/`tetra_clip.py`,
[[tetra-push-model]]): dCcS rank-table 50/50 split, Link Co R=30, joint-midpoint center, push
STEERS.

**Tetra counterpart state DONE (session 14).** Decided with Dereck: a PARTIAL `daNpc_Zl1_c` model,
not a full NPC port and not a captured schedule -- her FOLLOW behaviour (she chases Link when he
gets too far) plus the LOCK-ON/TALK region (so a planner avoids accidentally talking/locking her).
`tww_sim/core/npc_zl1.Zl1FollowState` (the `optn_1`/`optn_2` idle<->move follow: engage > 230, turn,
accelerate to `0.04*sqrt(dist^2-130^2)` capped 10, stop <= 130) is **live-gated 0-ULP** on slot 3
(`capture_tetra_follow.py`, `tests/test_tetra_follow.py`), and `zl1_attention_active` is the
decomp-exact avoid predicate (`dist_table[0xAB]`: XZ < 300, ±90deg cone). Her **BG collision** is
modelled too (`mObjAcch.CrrPos` = the same Phase-W `dBgS_Acch::CrrPos`, `dBgS_ObjAcch` subclass, her
single R=50/half-H=30 AcchCir; `step(walls=)`), LIVE-GATED 0-ULP by a corner-wall eject. This
WallCorrect **wall-brace** (wedged Tetra's CC recoil is canceled so she holds) is a validated MECHANIC.
Whether it helps the clip is OPEN (session-19 correction): a corner-braced Tetra pushes the WRONG way
and a stationary behind-Link Tetra gets plowed, so the clip STAGING is unsolved (see Phase T).
Mechanic page `knowledge/mechanics/tetra-follow.md`.

**CC push WIRED into the stepper + live-validated to the push frame (session 15).** The Co push now
runs in the per-frame stepper in the decomp's order: `LandState._cc_move` is consumed in `posMove`
AFTER `posMoveFromFootPos` and BEFORE the m34C2 cut lunge + `CrrPos` (`d_a_player_main.cpp:2556-2610`;
the overlap feeding it is computed in the DRAW phase, `dScnPly_Draw -> dCcS::Move`). `cc_push.
co_move_pair` gives both actors' `SetPosCorrect` moves; `cc_stepper.CcCoupledStepper` couples Link
(`LandState`) + Tetra (`Zl1FollowState`) each frame via Link's animated roll Co centre. LIVE (slot 3,
`capture_cc_push.py`): Tetra teleported into the corner (WallCorrect braces her), Link rolls in and
CONVERGES into her; the coupled sim is **0-ULP** on Link's wall-approach roll AND Tetra's brace, and
Link stays bit-exact through the frame the push is first consumed. Offline gate `tests/test_cc_gate.py`
(no Dolphin, fixture `fixtures/hyrule_cc_push.json`) + math/consumption `tests/test_cc_stepper.py`.

**PUSH FRAMES now bit-exact through the whole roll (session 16): the body lean, not the morf.** The
push overlap uses `body_cyl.roll_co_center`, which drifted on early roll frames -- root-caused (live
capture `capture_roll_lean.py`) to the missing `setWorldMatrix` base z-tilt by `shape_angle.z` (the
MOVE turn lean `m351C>>1`), NOT the oldframe-morf (that touches roll frame 0 only). A curved approach
carries a nonzero turn lean into the roll; `body_cyl.roll_co_center(..., shape_z=)` now feeds the
previous frame's lean, `LandState` exposes `_draw_lean` + evolves `m351C`, `cc_stepper` seeds `m351C`
at roll entry. Live re-capture (slot 3): **every FRONT_ROLL push frame 0-ULP for Link AND Tetra**
(`test_cc_gate::test_coupled_push_frames_bitexact`, xfail->pass; scoped to the roll frames). Live land
14/14 byte-identical.

**CLIP-FRAME ORDERING now bit-exact through the CUT_F entry (session 17).** The clip frame -- Link
fires a FORWARD `CUT_F` out of the roll into the corner-braced Tetra -- stacks, in the decomp's
`posMove` order (`d_a_player_main.cpp:2556-2610`), the roll speedF move -> the ~22u CC push consume ->
the `m34C2` cut lunge (~49u) -> `dBgS_Acch::CrrPos`. Already structural in `step()`; this session
live-VALIDATED it. `cc_stepper.couple_replay` now replays the capture's per-frame controller inputs +
seeds `sword_drawn` so the B thrust fires the roll->CUT at the same frame it did live. LIVE (slot 3,
`capture_cc_push.py draw_at=/thrust_at=`): sword drawn early during the walk-up (drawn-sword walk still
reaches the speedF-17 cap -> full-26 roll), Link rolls into wall-braced Tetra, a UP+B thrust (a neutral
B is a side slash -- dead-end #12) fires an in-line `CUT_F` at roll anim-frame >17. **Every frame from
Tetra's placement through the CUT_F entry is 0-ULP for BOTH actors.** Gate `tests/test_cc_rollstab.py`
(fixture `fixtures/hyrule_cc_rollstab.json`). Scoped to the entry (the single-frame lunge that decides
the clip); wall-BLOCKED here, so it validates the ORDERING, not a clip-through (Phase T threads the
lunge behind the seam).

Still missing to close Phase C:
- The CUT *tail* (the frames after the CUT_F entry): the sim keeps posing Link's Co centre with the
  frozen roll anim (`body_cyl.roll_co_center`) rather than the CUT pose, and live enters a post-cut
  recovery proc (`0x5a`) the sim does not model. Both moot for the clip (decided by the entry lunge;
  the roll never re-walks), like the descoped roll->MOVE exit gap -- model them to extend the window.
- The roll's EXIT to MOVE is not bit-exact (the neutral-hold capture's f27+, the separate "mid-run
  stop -> re-walk" gap). Irrelevant to the clip, which fires a CUT out of the roll, not a MOVE exit.
- Live reticle confirmation of the attention region; the Tetra read-lag (execute order Link-then-
  Tetra in the driver); `GetCCMoveP` from Tetra's own recoil buffer; the `move_jmp` gap hop
  (unmodelled, no gate needs it yet).

## Phase R -- residuals (parallel, pick up when they block)

- Late FRONT_ROLL drawn poses (strict-xfail `test_rest_roll_pose_bitexact`): jointBeforeCB MOMI
  body-lean prime suspect. Becomes load-bearing when a plan WALKS AGAIN after a roll on blend
  frames -- likely in Tetra setups (roll, reposition, roll again).
- `rest_state` models only the sword-drawn `waits` idle arm; a Tetra-area anchor may rest in
  wait00/fidget arms (mint's capture generalizes; the re-init modeling doesn't yet).
- Camera-in-the-loop: kaze's csangle sat frozen; a panning camera feeds the stick decode
  per-frame (CameraManual is bit-exact but unexercised by this pipeline).
- Re-verify the DTM contract (2 alignment rows; 255->254) per new stage via the rest.py gate.

## Phase T -- the Tetra seam clip end-to-end (**DONE 2026-07-11, session 22: LIVE, BIT-EXACT**)

**SUCCESSOR DONE (session 24): the FOLLOW-ENABLED turnaround-roll clip, LIVE + BIT-EXACT.** The
session-22 clip needed a GLITCHED no-follow Tetra; session 24 delivered the same corner clip with a
NORMAL following (type-5) Tetra via the A+diagonal-stick TURNAROUND roll ([[turnaround-roll-tech]]) on
slot 7: Link (moved +110u NE) DOWN-walks then turnaround-rolls to plow her aside, her CC push steers
the `CUT_F` lunge through the seam, landing `new=(-1727.1728515625, -990.4632568359375)` bit-for-bit
and Link falls (proc 39). Every frame entry->cut is 0-ULP for BOTH actors. Module `turnaround.py`
(full live pipeline `entry`/`solve`/`deliver`/`diff`); fixture `fixtures/hyrule_turnaround_clip_live.json`;
gate `tests/test_turnaround_clip.py`. Two delivery calibrations beyond the four pushaside truths: the
from-rest walk is not yet bit-exact so the placement is solved at the MEASURED live roll entry (facing +
speedF ARE exact, only the walk distance differs); and `b_step=16` (turnaround press shifts the buffer
one vs pushaside's +1). See README `## Status` (session 24).

**THE NORTH STAR IS HIT.** The Tetra push-aside seam clip is live-confirmed bit-for-bit: Tetra stands
at her spot from the START (`placed_step=0`, an initial setup var, NO mid-run write), Link's roll PLOWS
her aside, and her CC push steers the roll-stab `CUT_F` lunge through the seam at (-1727,-990).
Delivered by a clean DTM (never advancewith). Live: the cut fires at `old=(-1692.3147, -955.0418)` and
lands at **`new=(-1727.173095703125, -990.4635009765625)`, bit-for-bit the sim's prediction**, then Link
falls (proc 39) -- through the seam. Setup: Tetra (-1652.2239990234375, -939.447998046875); roll entry
(-1513.3475341796875, -763.5128784179688); thrust sim-step 15, cut step 16. Fixture
`fixtures/hyrule_pushaside_clip_live.json`, gate `tests/test_pushaside_clip.py`. Details + the four
delivery truths (walkable Tetra floor; NEUTRAL roll stick; B one step later in the DTM; seed at the
DTM's real entry) are in README `## Status` and dead-ends #21-24.

Remaining (pure-sim polish, not the clip): the walk-up is still the CAPTURED slot-6 walk, so the roll
entry comes from a live trace rather than a model. Closing it = a from-rest slot-6 anchor (cf. kaze's
`rest.rest_state`) simulated on the DELIVERED bytes (254, not 255).

Original plan (for the record): same solver shape as Phase 0 -- from-rest exact approach -> steer via
push overlap -> roll+cut acceptance through exact geometry at the Tetra corner -> deliver clean DTM ->
live 0-ULP clip. No new physics needed discovering; none did.

**Acceptance FOUNDATION DONE (session 18), measure-first.** The Tetra corner (-1727,-990) is now in
the rollstab conventions: `fixtures/hyrule_tetra_geo.json` (built offline from the live RAM golden
`tests/golden/hyrule_seam_1727_ram.json` by `make_tetra_geo.py`; wallA +X poly 2915, wallB +Z poly
2904, 90.57-deg corner, the 4-tri CrrPos barrier, `link_y`=0.16327, seam vertex S, authoritative
old/new) + the PUSH-AWARE acceptance module `geometry_tetra.py` (`pred_genuine(old, push)` tests the
coupled `new = f32(old + push + lunge)`). Live-anchored facts (gate `tests/test_tetra_geo.py`, 5
green): NEEDS-PUSH -- the 49.2202u lunge (F=40874) is ~0.7507u short; a ~0.7506u Link push (~1.5u
corner-braced-Tetra overlap x 0.50 share) reproduces the live golden endpoint BIT-EXACT. The approach
razor is threadable (with push fixed, `old` clips over a ~0.86u along-band at ~8% f32 density, kaze-
like); the push is not a free continuous knob -- the coupled sim produces it bit-exactly from Tetra's
f32 placement, so the solver tests the exact candidate.

**Coupled solver core built, but STAGING REOPENED (session 19).** `harness/rollstab/solver_tetra.py` (the
Tetra counterpart of `solver.py`) is wired and its offline STATIC-`co_move_pair` acceptance is gated vs
the live golden (`tests/test_tetra_solver.py`, 6 green) -- but it assumes a staging the DYNAMICS refute.
- **REFUTED: BEHIND-LINK, stationary idle Tetra.** The needed push (~235deg, ~0.75u) is only ~11deg off
  the roll line, so the delivering Tetra sits ~15u from the line -- exactly where Link's rolling Co centre
  travels -- so the roll-in PLOWS her (large chaotic pushes) and flings an un-braced Tetra ~40u away
  before the cut; the CUT_F fires with zero/wrong push (`scratchpad/proto_dynamics.py`, `confirm_plow.py`;
  dead-ends #17). Still sound: the corner NEEDS a push toward the seam (bare is wall-blocked at every
  reachable start), so Tetra must be behind (corner-brace pushes the wrong way); collision-valid start =
  r=35 cylinder clears both walls. The only controlled push is Link plowing a BRACED Tetra.
- Acceptance must be the DYNAMIC coupled cut (run the plow through `cc_stepper.CcCoupledStepper`), NOT the
  static per-position predictor `solver_tetra` uses. `solver.py`'s families' new `F=` param stands.

**Next: the STAGING STRATEGY (open).** Position Link + Tetra so a controlled seam-ward push lands on the
cut frame. Candidates (session-19 handoff): (1) brace Tetra on the behind side (hunt DZB geometry for a
brace); (2) accept the big braced-plow push and search old+aim+placement via the full coupled dynamics.
Then it feeds the from-rest solver (needs a minted slot-3 rest anchor; none exists -- `mint.py` only
translates within a room), verify REST BIT-EXACT (`rest.py`), deliver via `deliver.py`; live 0-ULP clip.
