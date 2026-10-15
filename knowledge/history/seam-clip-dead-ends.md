# Roll-stab seam-clip dead ends (sessions 4-9, 2026-07-09/10)

> **status: historical** - research log / dead ends, NOT current truth. The current pipeline and
> run protocol live in `harness/rollstab/README.md`; the methodology in
> [strategy/seam-clip-solver.md](../strategy/seam-clip-solver.md). This page consolidates the
> approaches that were TRIED and RULED OUT while planning a roll-stab clip through the kaze room-11
> 110-degree seam, so the next session does not repeat them. Append new dead ends here as they occur.

Context: the goal is a PURE-SIM one-shot (given a fixed anchor + a target seam, compute the input
sequence, no live round-trip in the loop), DTM-verified, under 2 minutes. Most of these failures come
from either fighting the razor with the wrong knob, or trusting a sim result that a live run then
contradicted. Read alongside the "Dead ends" list in the README (this is the fuller version).

## A. Delivery and validation (permanent rules)

1. **`advancewith` for off-axis sticks is wrong.** It mis-injects near-full OFF-AXIS sticks (~+-160
   s16). It caused the G1 facing confusion (advancewith read 33353 while the sim decoded 33295); a
   walk-only DTM confirmed the SIM was right and advancewith was the artifact. Validate AND deliver any
   aimed/off-axis sequence via clean DTM only, NEVER advancewith. Off-axis + advancewith is
   deterministic from a fixed savestate (fine for a one-off demo) but is NOT portable. See the
   `advancewith-offaxis-stick-artifact` memory.

2. **Teleport / position-feedback tuning as the delivery method: REJECTED (user).** The final product
   is one-shot from a fixed anchor, no teleport, no position feedback. Related placement gotcha: writing
   ONLY the debug pos globals leaves `pm_old_pos` behind, so the next CrrPos sweeps a long line and
   snaps Link ~100u away (spurious BLOCK). If you ever place for a check, write BOTH player class-pos
   triples AND the link globals (the `teleport` CLI does this) and feed FULL f32 precision (3-decimal
   rounding flips CLIP to BLOCK).

## B. Sim-artifact traps (looked like a clip, was not)

3. **Session-4's 42-frame `genuine_clip` was a SIM ARTIFACT.** The sim had no wall collision in the
   roll approach, so it rolled Link straight THROUGH the corner wall to an unreachable `old` (z~278);
   the live wall blocks the roll ~26u short at z~304. The plan targeted a position that cannot exist.
   Lesson (now enforced in the pipeline): every candidate must clear the walls on EVERY roll frame, and
   `old_z` must sit in the reachable band (kaze r11: ~[302.6, 308.2]).

4. **Session-6's collision-free clip was a SIM ARTIFACT of the naive stick decode.** It was found
   before the PADClamp octagon clamp landed; replaying the same sequence under the fixed decode shifts
   `old` ~1.06u (9072.04 to 9073.10) and it no longer clips. Lesson: the decode is the octagon-clamped
   one now (`core.mathlib.main_stick_decode`). Any pre-fix "hit" must be re-verified under the current
   decode before it is trusted.

5. **A scan "negative" from the wrong window proves nothing.** Session-5's `check_blocked_clip.py`
   reported "no clip" but was sweeping the wrong `old_x` window at the wrong facing; the real
   clip-capable `old` was elsewhere (session 6 found 93 collision-free clips at that corner). Do not
   certify a corner unclippable from a scan unless the window AND facing are correct.

## C. Search-strategy dead ends

6. **Naive constant-stick single-ray one-shot at the 110-degree corner: INFEASIBLE (hard table
   limit).** The position integrator's `>>4` cos/sin table has only 4096 directions, which quantizes the
   roll-line direction, so rho (perp offset to the corner) is quantized to ~1.15u steps here; the
   ~0.037u clip window falls in a 1.15u gap (nearest reachable rho misses by ~0.009u). This is a table
   limit, not stick-byte or sim precision: closing other sim gaps does not help. NOTE 14/88 room seams
   ARE single-ray hittable (wider windows). For a gap target you need a DENSER lattice (start-crawl
   low-speed frames or mid-walk knobs), not a single ray.

7. **Two-segment pursuit walk (fixed-F perp knob): does not cross the razor.** rho quantizes to a
   coarse global tread lattice with a dead band sitting exactly over the window; partial-msd endgame +
   neutral creeps + large (26k-run) sweeps never crossed it. Fixed-F pursuit knobs are the wrong tool
   for the perp match.

8. **Ribbon-fit / |g| minimization targeting: wrong model of the acceptance region.** The genuine set
   is f32 DUST (striped slivers per f32 x-column), not a ribbon or centerline, so being 1e-4 from a
   fitted line says nothing. Always test the EXACT f32 candidate (the real `enter_cut` lunge; `new` ==
   `f32(old + lunge)` bit-for-bit).

9. **Anchor-z transfer aiming / aiming `dz` at a sliver: lands chaotically.** The live m359C reseed
   flips the A-press frame, so trying to aim a minted anchor's `dz` at a known sliver does not land
   there. Pick a FRESH arbitrary `dz` per anchor (each is an independent lottery draw of the reachable
   manifold against the dust); do not try to aim it.

10. **Turnaround-clip coarse knobs (integer n_walk / discrete stick aim / integer thrust, Tetra
    fixed): 0 genuine even at the shipped Tetra spot (session 23-24).** The acceptance is f32 dust; the
    ONLY fine knob is Tetra's f32 placement, solved at the exact roll entry. Also **octagon-VERTEX
    turnaround aim** (stickY=255) reaches only facing 40758/40913 -- outside the ~40842 seam-gap window,
    so `new` is wall-pinned ~49u short at EVERY placement; a **DIAGONAL** stick (108,204)->40835 is
    REQUIRED to thread the corner gap (retry a vertex aim only if the camera csangle changes).

11. **Coarse-locate the genuine Tetra region via min(new-to-seam): FAILS -- no gradient (session 24).**
    The clamped `new` is ~49u (blocked) or ~0.5u (clipped) with nothing between, so there is no ridge to
    descend. BUT the engine's UNCLAMPED-endpoint plane distances DO give a smooth ridge: `sweep_par`
    out[8]/[9] = `behindA`/`behindB` (signed dist of the pre-CrrPos predicted endpoint behind each seam
    wall). Coarse-scan those to bound the behind-both region, then fine-scan (step ~0.008) only there --
    a blind fine-scan of the whole approach corridor blows the 2-minute budget. This is how the
    session-24 live clip's placement was located at the measured entry.

## D. Calibration / anim-state dead ends (relevant to killing the live calibration)

10. **Per-move-set bias correction: not transferable.** The anim-phase bias is arc-dependent (0.09u on
    one arc vs 2.6u on another), so a single correction does not carry across move classes; it would
    need one live run per class. This is the drift path that grew into the live calibration step. Do not
    extend it; model the anim state instead.

11. **A from-rest roll as an anim-reset canonicalizer: does not resync.** A roll out of the idle/yawn
    does NOT wash the cold-start anim mismatch back to a canonical phase; it diverges from frame 1. It
    cannot be used to sidestep seeding the true idle-entry anim state.

## E. Mechanic constraints (real, do not chase)

12. **Aiming the thrust more than +-0x2000 (+-45 deg) off the roll facing dispatches CUT_L / CUT_R** (a
    different, weaker move), not the forward lunge. Documented dead end; do not chase it for the big
    clip frame. To steer the 49.22 lunge you must AIM THE ROLL, not the thrust.

13. **The camera cannot be forced behind Link in kaze room 11.** `cam_yaw` writes are clobbered by the
    integrator each frame (forcing them diverges facing); C-down drifts csangle to an unpredictable rest
    (~13-27 deg off); a full-up "camera-behind" roll goes off-course and bonks. Aim the STICK
    (`stick_for_bearing` at the stable csangle), do not fight the camera.

14. **speedF must be 17.0 at the A press (hard gate).** A sub-cap walk gives a sub-26 roll and a shrunk
    lunge that never reaches behind the seam planes. Gate it everywhere; it is not tunable down.

## K0 mid-run calibration + the "anchor lottery" (sessions 8-9; superseded session 10)

Pinning the sim to one live run at a mid-cruise row K0 (position + fc phases + m359C/m35B4 + a
re-posed toe stream) verified bit-exact on the CRUISE -- but at cap m3598 == 0, so the cruise
exposes none of the pose-dependent state, and the calibration silently left it sim-derived. Dip
frames (m3598 > 0) then consumed wrong poses and shipped hits missed live by ~0.3u; each anchor
looked like an independent "lottery draw". Session 10 replaced it with the from-rest exact model
(rest-blend seeding + stored mFootData poses + end-of-frame draw pos + world Y + turn lean +
dtm_make's 255->254 delivered-byte calibration) and the "lottery" vanished: the first robust hit
shipped clipped live 0-ULP. Lesson: a calibration verified only on a regime that HIDES state is
not a calibration of that state.

## The FRONT_ROLL Co-centre residual is the BASE LEAN, not the oldframe-morf (session 16)

The session-15 push-frame drift was blamed on `body_cyl.roll_co_center` carrying the FRONT_ROLL
**oldframe-morf** transient (supposedly bit-exact only after roll frame ~11), with the fix being "model
the morf". **Ruled out by a live capture** (`harness/rollstab/capture_roll_lean.py`, logging mCyl centre
+ `mBodyAngle` + `m34F2/m34F4` per roll frame): the roll's `i_morf` is `mRoll.field_0x14 = 2.0`, so the
oldframe-morf blends **roll frame 0 only** -- it cannot be the frames-1..11 residual. That residual is
the missing `setWorldMatrix` base `ZXYrotM` z-tilt by `shape_angle.z` (the MOVE turn lean `m351C>>1`,
decaying ~35%/frame): a curved approach carries a nonzero lean into the roll (`mBodyAngle.x=y=0`,
`m34F2=m34F4=0` throughout; only `mBodyAngle.z==shape_angle.z`), and the clean lean-0 pose is off by it.
Feeding the previous frame's `shape_z` to the base is 0-ULP on every settled roll frame; the
`jointBeforeCB` body_chn rotation contributes nothing to the root/neck xz midpoint (adding it breaks
it). Lesson: capture the actual per-frame quantity before attributing a residual to a plausible
mechanism -- two mechanisms with different timescales were conflated. Do NOT build a morf driver for the
push frames; the morf still owns roll frame 0 only (out of push scope).

## Tetra push STAGING: corner-brace and colinear-behind are both WRONG (session 19)

THREE Tetra stagings for the (-1727,-990) corner clip are ruled out (#15 corner-brace, #16 colinear-
behind, #17 stationary behind-Link). The correct staging is STILL OPEN (session-19 handoff): the push
must point toward the seam (so Tetra behind Link), but a stationary behind-Link Tetra gets plowed, so
some form of BRACING or timed placement is needed. NOTE `co_move_pair`/`cc_stepper._cc_check` reproduces
the golden push STATICALLY, but that is not the dynamically-reachable push (see #17).

15. **Corner-BRACED Tetra pushes the WRONG WAY.** The sessions-15..17 captures teleport Tetra INTO the
    corner and roll Link in; her push then points AWAY from the seam (she shoves Link out of the corner),
    so it cannot close a clip that needs ~0.75u ADDED toward the seam. Those captures were wall-BLOCKED
    and only ever validated the CC frame ORDERING (push consume -> m34C2 lunge -> CrrPos), never a
    clip-through. The corner-brace is stable (WallCorrect holds her) but geometrically wrong. The clip
    needs Tetra BEHIND Link (push toward the seam) -- but a *stationary* behind-Link Tetra is itself
    ruled out, see #17.

16. **Colinear-behind Tetra (push along the roll facing F) does NOT clip -- the STEER matters.** Placing
    Tetra exactly opposite the lunge (along -F) gives a push along +F (224.53deg), but the needed push
    bearing is ~235deg (~11deg off F): the ~0.75u must STEER `new` sideways onto the seam vertex, not
    just extend the lunge. So the Tetra placement is a 2D f32 knob, not a 1D distance
    (`tetra_clip.solve_min_overlap`'s colinear-behind placement fails for the real thrust; [[tetra-push-model]]).

17. **Stationary behind-Link Tetra CANNOT deliver the push -- she gets PLOWED (session 19).** An earlier
    draft claimed a stationary idle Tetra behind Link (within the follow radius) would deliver the push as
    her anim Co centre sweeps the overlap. The DYNAMICS refute it (`scratchpad/proto_dynamics.py`,
    `confirm_plow.py`): because the needed push is only ~11deg off the roll line (#16), the delivering
    Tetra sits ~15u from the line -- exactly where Link's rolling Co centre travels -- so the roll-in
    PLOWS her over ~8 frames with large (3-12u) chaotic pushes and flings an un-braced Tetra ~40u away
    before the cut frame; the CUT_F then fires with zero/wrong push. Link's FRONT_ROLL Co centre LEADS the
    feet toward the corner (away from a behind Tetra), and its wall-pinned sweep never gives a clean single
    ~1.5u graze; a tangential (side) graze gives a ~90deg-wrong (pure-lateral) push. "Forward push" and
    "off the roll path" are mutually exclusive here. The only dynamically-controlled push is Link plowing a
    BRACED Tetra -- so the open staging must BRACE her (on the behind side, if geometry allows) or use a
    timed placement, and acceptance must be the DYNAMIC coupled cut, not the static `co_move_pair`
    predictor `solver_tetra`/`test_tetra_solver.py` uses.

18. **Fast bare-centre push predictor is INVALID for the coupled Tetra clip (session 20).** A cheap solver
    that precomputes Link's roll Co-centre trajectory ONCE (Tetra-free) and then rolls only Tetra's shove per
    candidate placement (the freeze-solver pattern) does NOT work here: the CC push perturbs Link's FEET
    substantially (live: his roll z lagged -910 vs the bare -955), so his Co-centre is NOT Tetra-independent.
    Only the FULL coupled sim (`cc_stepper.CcCoupledStepper`) is faithful. Corollary confirmed live 0-ULP on
    slot 6: the un-braced shove + roll-stab CUT_F entry are bit-exact, so the substrate is trustworthy -- but
    a 460-placement sweep at a FIXED roll timing found 0 genuine (closest `new` pins ~35u short of the seam;
    the seam-ward push and a full lunge from the golden `old` are mutually exclusive under a movable Tetra's
    plow, restating #15-17 with coupled data). NOT proven across all roll timings / roll angles -- the search
    is blocked on coupled-sim SPEED (~1.3s/sim, 99% in `acch_crr_pos` over all 765 walls; needs the Phase-W
    wall cull + precomputed roll/cut tables before a timing x placement sweep is feasible).

19. **[RESOLVED session 22 -- the push-aside CLIPS LIVE, bit-exact. Kept only as the record of why the
    session-21 slice was empty.]** A THIN plow-staging slice came up empty (session 21) -- the push-aside
    itself was never ruled out.
    With the exact >=100k sims/sec engine (`tww_sim/core/_shovec`), 13M+ coupled sims over placement
    x[-1725,-1600] z[-1000,-860] x thrust steps 13/14/15 x placement steps found 0 genuine -- but ALL of
    it at ONE Link approach line, ONE roll-entry point, ONE roll angle. ~98% of un-walled cut endpoints
    are already BEHIND the seam plane, so the razor is the CrrPos block, and in THAT slice no
    plow-perturbed `old` landed on a threading sliver. Dereck's correction (21b): the push-aside is the
    REQUIRED mechanism (a mid-run Tetra placement is a hack) and manual testing has produced a 50.6u
    displacement with a bad angle/position (>= the ~49.99 the clip needs) -- so the lesson is scope, not
    impossibility. Retry WITH the wide knobs: roll timing / Link entry point (`link_x0/z0`), lateral
    placement, finer + wider Tetra initial positions (`placed_step=0`), thrust timing, roll angle.

20. **Transferring a threading push between different `old`s (session 21).** The session-18 golden push
    (-0.618,-0.427) does NOT thread from the straight-roll wall pin (`pred_genuine(pin, golden)` False):
    the acceptance slivers are a function of `old`'s exact bits. Search pushes per-old (the polar graze
    sweep over the FULL angular range, 0.05 deg x 0.002u depth); never re-aim a known-good push at a new old.

## The four things that made the push-aside miss LIVE (session 22 -- all fixed; do not relearn)

The push-aside clip is SOLVED and live-confirmed bit-exact (README `## Status`). Getting there burned a
lot of live runs on four traps, each of which LOOKED like "the sim is wrong" and was not:

21. **A Tetra spot that is not on WALKABLE FLOOR.** The coupled sim clamps Tetra to the flat ground plane
    everywhere and never models her FALLING, so it will happily "stand" her behind a wall and report a
    genuine clip. Live she drops OOB, delivers **no push at all**, and the bare cut is wall-blocked. The
    first live attempt died exactly here (her spot had `fB = -6.8`, behind wall B). **Constrain her start
    to `in_front` of BOTH seam walls** (and keep her plow path there too). A sim "hit" on non-floor is an
    artifact, in the same family as dead-ends #3/#4.

22. **Holding UP through the roll in the delivered DTM.** A pushed stick (`msd > 0.05`) force-exits
    `FRONT_ROLL` the moment `roll_frame > ROLL_EARLY` (`land/procs/roll.py:60`), so the roll ends into
    MOVE and the B can only ever fire a plain MOVE-slash (proc 90, backward recoil, no lunge) -- the
    roll-stab CUT_F never happens. The capture fixture holds UP (it was driven by `capture_cc_push`), but
    the SIM's schedule (`fast_shove.make_inputs`) holds **NEUTRAL** + one UP+B. **Deliver the sim's
    sticks, not the capture's.** Symptom: proc goes 30 -> 6 (MOVE) instead of 30 -> 66 (CUT_F).

23. **Assuming the sim's B step is the DTM's B step.** The sim buffers B with a 2-step INPUT_DELAY (B at
    step 14 -> CUT at step 16); the clean DTM delivers it with **1**. So the B goes one step LATER in the
    DTM (sim-step 15). Off by one either way and you get: too early -> the edge is consumed mid-roll and
    ignored; too late -> the roll has already exited and you get the MOVE-slash of #22.

24. **Seeding the sim at the CAPTURE's roll entry instead of the DTM's.** `dtm_make` calibrates sticks
    (255->254), so the delivered walk enters the roll ~0.004u away from the advancewith capture's entry.
    The acceptance is f32 DUST, so a placement solved at the capture's entry lands `old` on a sliver the
    real run MISSES -- block, not clip. **Seed `link_x0/z0` at the entry the DTM actually produces**;
    there the engine is 0-ULP vs live on every frame for both actors. (Generalises README model term #6:
    *always* sim the DELIVERED bytes, not the authored ones.)

**Method lesson (Dereck, session 22):** when a live delivery disagrees with the sim, do NOT tweak inputs
by guesswork -- **log the DTM per-frame and diff it against the sim** (both actors), and the divergence
frame names the bug. Four live runs were wasted guessing the B frame before the per-frame diff instantly
exposed #22/#23/#24. `run_dtm` has a `log_frames` param for exactly this.

## The from-rest slot-7 walk residual is a FOOT-POSE precision gap, not a seeding gap (session 25)

25. **"Seed the slot-7 DOWN-walk via `seed_rest_blend` + REST_NOOPS=2 + deferred-draw" (the session-24
    handoff's guess for computing the roll entry): WRONG lever.** Diagnosed by per-frame diff of the seeded
    sim vs a rich live walk trace. `noops=2` (kaze's value) FREEZES the WAIT/WALK blend advance and
    mis-aligns the walk start (residual worsens to ~4.2u); the slot-7 idle genuinely runs procWait every
    WAIT frame (blend advances d 17.80->18.20->18.60), so the right value is **`noops=0`**. At `noops=0`
    the proc/frame alignment is PERFECT (WAIT f0-2 / MOVE f3-8 / roll f9), the WAIT<->WALK blend `m3598`
    matches live BIT-EXACT (0,0,0,1.0,1.0,0.7647,0.3529,0,0), and `nspeed` ramps cleanly (+3.5/frame to
    cap) -- yet the entry is still ~**2.54u** off. The ENTIRE residual is the foot toe-stream `f312`
    (`posMoveFromFootPos` / `_py_foot_compose`) on the 3 walk-entry frames where `m3598>0` (f3-f5:
    speedF `nspeed*(1-m3598)+f312*m3598`, sim f312 low -- 0.068 vs live 0.105, 1.42 vs 2.15, 2.42 vs 4.62);
    it FREEZES at 2.54u once m3598 hits 0 (speedF==nspeed thereafter) and never grows. So this is the
    **same foot-FK-precision class as the Phase-R late-roll-pose drift** (jointBeforeCB MOMI body-lean /
    the walk-entry oldframe-morf toe stream), NOT a proc/blend/seed bug. Retry a computed entry only WITH
    a walk-entry foot-pose model, not more seeding knobs. The clip does not need it (measured entry is
    0-ULP live). Live trace: `_generated/turnaround_walk_trace.json`.

## Wall-brace for a Tetra-placement RANGE: no usable slide range exists (session 26)

26. **Bracing Tetra on a wall to get a targetable placement RANGE: RULED OUT (does not yield a range;
    bracing removes only one coordinate).** The genuine Tetra-placement set is a ~5e-4u-thin THREAD (KB
    [[strategy/seam-clip-solver]] "Tetra-corner placement"), so the along-wall braced window = thickness
    / sin(crossing angle) -- a useful range (~0.1u) needs the thread within ~0.3deg of PARALLEL to the
    wall at the brace distance. It never is. **wallB** (+Z) IS reachable -- a perp- roll-entry shift
    (~-1.3u) walks the thread's tip exactly onto the fB=TET_R=50 brace locus (z=-940.25562; verified the
    engine CrrPos-ejects deeper placements there, so fB=50 is the wall) -- but the thread crosses it
    near-PERPENDICULARLY (local angle 75-82deg; swept facing 40805-40880, never rotates toward 0), so the
    braced-genuine window is only 2-3 f32-ULP (~0.0002u): a POINT, x still f32-precise. **wallA** (+X) is
    the near-PARALLEL wall (thread local angle ~78-82deg ~ wallA's 90deg) that COULD give a range, but it
    is UNREACHABLE: the thread's corner-ward tip pins at x~-1650 (fA~76) at every Link entry tried (9
    directions, +-1.5-3u perp/roll/axis), ~25u short of the wallA brace (fA=50, x~-1677.66) -- an
    acceptance-geometry limit, not an unturned knob. Net: Tetra CAN be placed against wallB (z pinned
    free) but the along-wall x still needs f32 precision, and no Link position/facing knob opens a slide
    range. Untried long-shots (low expectations, the pin looks geometric): curved walk-up (nonzero
    `m351C` turn-lean) + thrust/roll timing. Tooling: `scratchpad/entry_brace.py`, `wall_range.py`,
    `walla_probe.py` (perp sweep + f32 thread-track + braced-z-line scan + wallA reachability).

## Wall-braced clip on the FOLLOW-enabled turnaround (slot 7): infeasible, Tetra flees (session 27, LIVE)

27. **A wall-braced Tetra clip is INFEASIBLE on slot 7 (follow-enabled turnaround) -- the deep-corner
    brace spot is not follow-safe.** Ran the full live pipeline: perp-shifted Link's start ~-1.3u so the
    roll entry reaches the wallB brace locus, measured the live entry (-1515.11,-766.13; the
    start-perp-shift translates to the entry RIGIDLY, matching the sim-predicted perp entry ~bit-for-bit),
    solved the braced-genuine placement (Tetra (-1652.293,-940.256), fB=50 ON wallB, bit-confirmed genuine
    at that entry), placed her, delivered, and per-frame-diffed. **Link's roll was BIT-EXACT (dLink=0), but
    Tetra DRIFTED off the wall before the roll reached her:** the brace spot sits ~220u from Link, and the
    speed-building DOWN away-walk pushes him PAST her 230u follow threshold (peak 249u at the walk end), so
    she ENGAGES follow and flees toward him; the cut wall-pinned short (live new=(-1692.3,-954.9), no clip).
    Offline-confirmed the bind: full roll (nspeed 26 needs walk>=5 frames) + seam-reach (Link far NE -- the
    +110 move exists because closer entries wall-pin) + follow-safe (walk peak<230) CANNOT coexist -- every
    follow-safe entry (backshift>=+24u toward the corner) has ZERO genuine (roll wall-pins). So bracing is
    incompatible with the FOLLOW-enabled clip *because follow is what breaks it*. Might work with the
    glitched no-follow Tetra (slot 6 pushaside, she stays put) -- UNTRIED. Tooling:
    `_notes/scratch-session27/{braced_live,entry_brace,wall_range,walla_probe}.py`.

## The pure-sim WALK-stab one-shot is blocked by the walk-entry foot residual (session 30, LIVE)

28. **A found walk-stab clip clips OFFLINE (0-ULP) but the clean-DTM live delivery does NOT -- the
    walk-entry foot toe-stream residual eats the razor.** The kaze r11 slot-3 walk-stab seam
    (S=(9030.955,1385.858), poly 803x802, interior 168.97deg) clips genuinely in the sim:
    `harness/rollstab/walkstab.solve()` finds it 0-ULP in < 2 min (the acceptance is f32 DUST, so it
    ENUMERATES distinct C-down walk streams -- beta spiral / start-crawl / bearing arc / per-byte fine
    nudge / N -- and tests the exact `genuine_clip`; the dust is SPARSE, ~ONE reachable `old` in the
    ~2e-4u perp sliver). Delivered as a clean DTM (C-down every frame, never advancewith), the walk is
    FACING-bit-exact every frame, but the CUT does NOT clip (`old_live` -> `genuine_clip` blocked;
    nearest clip ~1.2e-4u further in perp).
    - **Root cause:** to thread the perp razor the walk must TURN (aim the crawl+arc so the cut ray
      hits S); the turn overlaps the speedF-BLEND walk-entry frame (f6 here), which freezes a foot
      toe-stream (`m359C`/`f312`) position error of ~0.00037u. That error is a speedF-magnitude error
      (ALONG travel), but because the walk was TURNING when it froze, its component perpendicular to
      the FINAL cut facing is ~**1.9e-4u** (live-measured) -- and the clip's perp margin is only
      ~**1e-4u**. So `old_live` falls off the razor.
    - **This CORRECTS the session-29 feasibility read.** Session 29 measured the residual on a
      STRAIGHT walk (facing constant) and got perp ~3.7e-5u ("16x inside the razor, harmless"). But a
      real clip walk CANNOT be straight -- the 17u/frame along-granularity forces a start-crawl + arc
      (a turn) to place `old` in-window AND thread rho -- and the turning walk's perp residual is ~5x
      worse and comparable to the whole clip window (~2e-4u). No reliable margin exists. (The crawl
      entry actually SHRANK the residual, 0.00037u vs the straight walk's 0.0024u, and delayed it to
      the ramp frame -- but not enough.)
    - **Objective-compliant fix = MODEL the walk-entry foot toe-stream** (the Phase-R / session-25
      gap: `posMoveFromFootPos` / `_py_foot_compose` f312 is low on the m3598>0 blend frames;
      jointBeforeCB MOMI body-lean / oldframe-morf). NOT calibrate: choosing a window-EDGE hit so
      `old_sim + measured_residual` lands inside the sliver is position feedback (forbidden), and the
      residual is walk-dependent so it doesn't transfer. Once the toe-stream is bit-exact from rest,
      any centered hit delivers.
    - **B-timing (live-diffed, do not guess):** a B edge at DTM frame N-5 fires CUT_F at frame N (the
      4-frame item put-away delay + 1-frame DTM buffering); the lower body walks through the delay so
      `old` = the position after N walk steps. Symptom of +1: the CUT fires one frame late, `old`
      ~17u further along.
    - Tooling: `harness/rollstab/walkstab.py` (`solve`/`deliver`/`perp_margin`); live golden
      `tests/golden/walkstab_deliver.json`; regression `tests/test_walkstab_clip.py` (offline clip
      GREEN, live-clips xfail). Never re-ship a dust hit for delivery without the residual modelled
      (or a fat-band, residual-robust acceptance -- which this near-flat seam does not offer).
    - **CORRECTED (session 31): the "walk-entry foot residual" was the WRONG ANIM SET, not a
      foot-FK/lean/IK gap. `rest.rest_state` hardcoded `sword_drawn=True`, but this anchor holds the
      Wind Waker (`mEquipItem` 0x22, not `daPyItem_SWORD_e` 0x103), so `getAnmData` selects the base
      WALK/DASH legs, not the sword-drawn WALKS/DASHS.** WALK and WALKS share leg keyframes (a
      WAITS<->WALK entry is bit-identical either way, which is why f0-f3 matched), but DASH and DASHS
      differ, so the sword-drawn assumption drifted the plant toe ~0.0024u the instant DASH blends in
      (regime 2). Live-captured `mFootData` proved EVERY `jointBeforeCB`/`jointCB1` lean + foot-plant
      IK term is ZERO on this flat ground (waist tilt `m34E0`, CLOTCH `field_0x030`, leg bends
      `field_0x008/00A/002`; the SESSION_PROMPT note's "MOMI thigh lean from lateral accel" was wrong
      twice over -- MOMI 0x10/0x11 are FACE joints, not in the foot chain, and the lean is wind-driven).
      Fix: `rest.rest_state` seeds `sword_drawn` from the anchor's captured equip (`seed.json`
      `sword_drawn`/`equip_item`; default True for the sword-drawn roll-stab idle anchors). The
      from-rest walk is now BIT-EXACT 0-ULP in position + facing (`tests/test_walkstab_rest.py`), so
      any genuine OFFLINE clip is a true one-shot -- there is no residual to eat the razor. The
      session-30 hit no longer clips (fixing the ~0.0024u along-track error shifts `old` ~2-3 f32
      x-columns off its sliver; the dust is striped per column), so a deliverable hit is re-found in
      the corrected sim. **Lesson: verify the anim SET (equip state) before attributing a foot-pose
      residual to FK precision -- and capture the actual per-frame RAM quantity (mFootData, mEquipItem)
      before believing a plausible mechanism (cf. the session-16 morf-vs-lean lesson).**
    - **RESOLVED (session 32): the WALK-STAB clip is DELIVERED LIVE, 0-ULP, pure sim -- #28's premise
      is fully retired.** With the sim 0-ULP from rest (the session-31 sword fix), the live `old` lands
      exactly on the sim's; the only remaining problem was FINDING a deliverable hit, and that was
      NEVER throughput (see #29) -- it was distinct-`old` DENSITY near the razor perp. A K=3 crawl
      search (`solve_focused`) found wall-faithful genuine hits in 67s and the top clipped the seam live
      (CUT_F@N=13, `old`/`new` bit-for-bit the sim, Link OOB proc 0x24). Golden
      `tests/golden/walkstab_deliver.json`.

29. **The reachable-`old` byte lattice is a GAP over the perp razor at K<=2 crawls; the fine knobs the
    legacy `solve()` leaned on COLLAPSE under octagon clamping (session 32).** The acceptance perp razor
    is ~2e-4u; an offline sweep floored the reachable `min|perp|` at **~1.3e-3u (~13x)** with K<=2
    crawls, so `solve()` finds 0 even given the full 2-min budget -- MORE SPEED CANNOT HELP (the extra
    streams are octagon-clamped DUPLICATES: 52k streams -> ~14 distinct near-razor `old`). Root cause:
    the bearing arc `off` and the arc-frame per-byte fine nudge are FULL-magnitude sticks (octagon
    VERTEX), and PADClamp clamps them to the same delivered byte, so they do not move `old`. **The fine
    perp knob must be a PARTIAL-magnitude (octagon INTERIOR) stick, where every byte is a distinct
    decoded direction.** The fix (`solve_focused`): a K=3 START CRAWL -- each partial-mag crawl frame
    densifies the perp lattice ~20x (K=1 ~0.03u -> K=2 ~1.3e-3u -> K=3 ~2e-5u, below the razor), with
    the 3rd frame's BYTE nudge as the fine fill; bracket `|perp_ray|` cheap (no CrrPos), exact-test near
    the razor, and gate on a WITH-walls re-sim (`wall_hit==False`) to drop the #3/#28 wall-overshoot
    artifacts (an N=13 cut whose walk touched the seam wall has an `old` the wall-less sim overshot).
    **Lesson: when a byte-quantized reachable set won't hit an f32 razor, the lever is lattice DENSITY
    (more interior-stick DOF), not search speed -- measure `distinct near-razor old`, not `streams/sec`.**

## The SHEATHED roll anchor is not REST BIT-EXACT: an extra walk-entry idle frame (session 36)

30. **Equip-only sheathed mint off idle13 + default `rest_state`: NOT REST BIT-EXACT (a genuine
    walk-entry transition gap, not a fixable knob).** For the sheathed-roll milestone (session 35) a
    sheathed anchor was minted at idle13's spot (`kaze_r11_rollstab_sheathed@twwgz`; press A while idle
    to sheathe -> `mEquipItem` 0x100; pos/facing/csangle/state + blend rates all match idle13). The
    sword-DRAWN idle13 verifies `REST BIT-EXACT`, but the sheathed one does NOT, and the following were
    RULED OUT as the cause:
    - **NOT the code / `model_draw` / `sword_drawn`.** `model_draw`'s only effect without a B edge is
      forcing `native/foot_native=False` (already the case) -- all three of `model_draw` None/False/True
      give an identical sim walk. Forcing `sword_drawn` True vs False changes the entry ramp by ~0.003u
      (the base-vs-sword leg set is NOT the divergence). idle13 (drawn, same code path) is bit-exact.
    - **NOT a single `REST_NOOPS` / prepended-idle shift.** The real divergence: the sheathed idle takes
      **3 idle rows before the WAIT->MOVE transition** (live proc 4 at k=0..2, proc 6 at k=3) vs idle13's
      **2** -- the sim's walk starts one frame early and every downstream row is off by ~one 16.98u walk
      step (both reach the same cap). `REST_NOOPS` holds the idle-anim `d_frame` AND position TOGETHER,
      but live advances `d_frame` at k=2 while position stays at rest until k=3 -- so no dead-no-op count
      (0..4 swept) and no prepended blend/neutral step makes it bit-exact. The extra frame is a
      WAIT->MOVE / stick-delivery latency the drawn idle does not have.
    - **`run_dtm`'s row-0 alignment is JITTERY +-1 idle frame** (the `_log_playback` fast-poll lands "a
      couple frames in"): one sheathed verify showed row0 `d` = seed+1.1, another (same savestate) showed
      row0 `d` = seed. So diff the STABLE structure (idle-row count before MOVE), NOT row-0 `d`; a single
      run's +1 pre-advance is a red herring.
    Likely cause (untested, the session-35 Phase-R warning): the **sheathed idle rests in a non-`waits`
    anim arm** (`rest.rest_state` hardcodes `idle_anim='waits'`) whose WAIT->MOVE transition differs by a
    frame -- VERIFY the live idle anim ID before modelling. Or mint a clean-provenance sheathed savestate
    (the current one was made via `advancewith` frame-stepping; a real-time `resume`/`setinput` sheathe
    needs the idle A-press as a clean EDGE, which held-A / post-`clearinput` timing missed). RED test:
    `tests/test_sheathed_roll_rest.py` (strict xfail); live calib `fixtures/sheathed_rest_calib.json`.
    - **CORRECTED (session 37): the "one extra idle frame before WAIT->MOVE" was a `run_dtm` row-0
      POLL-JITTER artifact, and the "non-`waits` arm" lead is REFUTED.** Two run-free RAM reads + a
      jitter-proof measurement settled it:
      - **Idle arm is IDENTICAL** -- `m_anm_heap_under[0].mIdx` (loaded lower-body bck) reads `BCK_WAITS`
        (0x126) at BOTH the drawn idle13 and the sheathed anchor; only `heap[1]` differs (WALKS 0x135 vs
        WALK 0x12E = the already-modelled `sword_drawn` walk arm). So `idle_anim='waits'` is correct for
        the sheathed anchor. Both seeds are faithful (seed.json == live RAM). (Decomp: `getAnmData`
        d_a_player_main.cpp:12951 remaps the anim resource by `mEquipItem`; sheathed 0x100 -> base table,
        but `mAnmDataTable[ANM_WAITS]`'s under-bck IS WAITS 0x126, confirmed by the read.)
      - **Both anchors reach proc-MOVE at the SAME game-frame.** Tagging every live row with the
        deterministic emulator frame counter (game_frame = emu - F0; F0 = the savestate's stored frame,
        read by loading it paused) and aligning by that, BOTH transition proc 4->6 at gf6 and take the big
        walk step at gf8. The session-36 "3 idle rows vs 2" was the fast-poll catching the two captures at
        different start frames. `harness.rollstab.capture_walkentry` is the jitter-proof capture (plays the
        clean-DTM verification stream, tags emu, logs raw mFootData toe/heel + plant + m3598 + m359C).
      - **The REAL residual = the walk-entry foot TOE-STREAM (`posMoveFromFootPos`/`f312`), amplified by
        the 0.05 speedF clamp.** At the sheathed idle phase (d~52.8) the sim's first-walk-frame toe delta
        is ~0.034; live's is ~0.060 (`m359C`). The decomp-faithful `_py_foot_compose` clamp
        (`speedF = 0 if |spz| < 0.05`) then zeros the sim's step while live keeps it -- opposite sides of
        the razor -- and the error accumulates to ~0.8u over the m3598>0 blend frames (freezing once
        m3598 hits 0, same class as #25's 2.54u freeze). It is PHASE-driven, NOT equip (forcing
        `sword_drawn`/`model_draw` moves it ~0.003u; re-seeding at idle13's phase d=30.8 moves gf6 from
        0.0->0.056). `plant` also differs at entry (idle13 stays 1; sheathed flips 0->1 at gf6). So this
        is the **walk-entry foot-FK frontier of #25/#28**, exposed at a phase idle13 does not hit -- NOT a
        proc-timing, idle-arm, `REST_NOOPS` (swept 0..4, s36), or equip bug. Fix = model the walk-entry
        foot poses to f32 (session 37 handoff). Ground truth: `fixtures/sheathed_walkentry_golden.json`
        (RED) + `fixtures/idle13_walkentry_golden.json` (bit-exact reference), game_frame-aligned.
    - **CORRECTED + RESOLVED (session 38): the session-37 `f312`-FK story is REFUTED; the walk-entry
      foot-FK is BIT-EXACT. The real (and only) cause was a one-frame walk-entry DTM-ALIGNMENT noop --
      the anchor savestate's emulator SUB-FRAME CAPTURE PHASE, NOT in-game.** Diagnosis, all offline
      against the s37 goldens except two paused-RAM probes:
      - **The FK poses are bit-exact.** With the known 1-frame `mFootData` lag (sim pose N == live
        mFootData N+1) EVERY idle13 golden row matches the sim 12/12, and BOTH sheathed WAIT frames
        (gf2 d=53.9, gf4 d=55.0) match 12/12 EXACT. The s37 `m359C` "razor" mismatch was an ALIGNMENT
        artifact: the sim was one d-advance AHEAD (already MOVE at d=55.0 while live is still WAIT at
        d=55.0), so s37 compared a sim MOVE frame against a live WAIT frame -- not an FK residual.
      - **The sole divergence is the WAIT->MOVE alignment.** By the jitter-immune d_frame clock, live
        sheathed does 3 WAIT d-advances (52.8->53.9->55.0->MOVE@56.1) but the sim (REST_NOOPS=2) did 2
        (->MOVE@55.0). With **`noops=1`** the sheathed from-rest sim is **0-divergence on pos, m3598, and
        m359C at every d-aligned WAIT+MOVE frame**. idle13 needs 2, breaks at 1 (converse confirmed).
      - **It is a savestate CAPTURE PHASE, proven not in-game.** Loading each anchor paused and
        single-stepping neutral (no DTM, no jitter): idle13's first frame HOLDS d (30.8->30.8) then
        advances; sheathed's ADVANCES immediately. idle13's hold frame mutates **zero** player-RAM bytes
        (a pure emulator re-display of a frame captured mid-execution). It survives `load->save`, a single
        advance destroys it, VI-frame parity doesn't predict it, and none of 6 candidate player-RAM fields
        flip it (causal write-test). idle13 was minted MID-FRAME (legacy translate lineage) -> +1 spurious
        re-display -> noops=2; sheathed via `mint_current` (boundary capture, the canonical phase, same as
        the future live-RAM UI feed) -> noops=1. So `noops=1` is the STANDARD; idle13's 2 is a capture
        artifact pinned to its locked golden.
      - **FIX (no hardcode, no re-mint, locked goldens intact):** `mint.capture_rest` now DERIVES the
        phase from its existing t1-advance (advances-until-`d`-changes) into `seed['rest_noops']`;
        `rest.rest_state` reads it (legacy seeds default `REST_NOOPS=2`). Sheathed seed `rest_noops=1`
        (derived live). `tests/test_sheathed_roll_rest.py` FLIPPED to a plain assert (d_frame-aligned vs
        `sheathed_walkentry_golden.json`, GREEN); full suite 341 passed, locked idle13/walkstab untouched.
        The FK model of #25/#28 remains genuinely open (session-25 slot-7 residual, curved MOVE-turn
        overlap) -- it was just NOT the sheathed blocker.

## The sheathed roll-stab clip: SOLVED offline, LIVE-blocked by a sim MOVE-turn facing overshoot (session 39, LIVE)

31. **[CORRECTED session 40 -> #32: the "two-angle/MOVE-turn SETTLE residual" diagnosis below is WRONG.
    A jitter-immune measurement proved the row-18 divergence is a TRANSIENT (0.889,1.0)-BAND STICK
    input-layer decode divergence; the two-angle chase is faithful. The session-39 "shape overshoot"
    reads were run_dtm poll-jitter. Read #32.]**
    **The row-18 facing overshoot is a two-angle/MOVE-turn SETTLE residual, NOT input buffering, and it
    blocks the live roll-stab clip for BOTH the sheathed and drawn anchors.** Session 39 SOLVED a
    from-rest sheathed roll-stab clip (pure sim, seed-only; `old=(9072.209,308.028)`, offline `deliver
    gate` PASS 0-ULP genuine, sliver-robust) but the LIVE ship did not clip. Per-frame sim-vs-live diff
    (fixture `fixtures/sheathed_roll_ship_live.json`):
    - **Rows 0-17 are BIT-EXACT live** -- the K=2 crawl, the row-3 draw B-edge, the arc, and the fines
      all deliver 0-ULP, so delivery alignment / `rest_noops` (#30) are correct and the draw is not it.
    - **Row 18 diverges by a single frame:** on an aim-stick frame (after the row-16 fine settles) the
      SIM's `shape_angle` OVERSHOOTS to 33367 while live holds the settled 33295; the phantom turn dips
      speedF to 15.05 vs live's 17.0 cap -> a **~1.9u along-track lag that FREEZES** for the whole roll
      -> `old` lands off the f32 razor -> the CUT fires from the wrong spot (live `new` not behind the
      walls; the lunge misdirects). Same class as the #25 speedF-freeze, but the trigger is the TURN.
    - **DISCRIMINATOR (ruled out the buffering hypothesis): live shape+travel (`0x136`/`0x12E`) per
      frame == the sim on EVERY row except 18** -- live does NOT lead the sim by a frame, so it is NOT a
      stick INPUT_DELAY/buffering shift (the pushaside-#3 class). The sim inserts one spurious facing
      value at row 18 that live never has -> a genuine `shape_angle` chase / `setMoveSlantAngle` settle
      overshoot after an arc+fine (README model term #5; the Phase-R MOVE-turn frontier). NOT fixed this
      session (Dereck: diagnose first). Two open paths: (a) re-search for a CLEAN-SETTLE hit (constrain
      speedF==17 on every cruise frame from the last turn through A -- no sim change); (b) model the turn
      overshoot to f32 (decomp-first, the general fix, also unblocks the drawn idle13 hit). RED gate
      `tests/test_sheathed_roll_clip.py::test_sheathed_ship_matches_live` (strict-xfail).
    - **Side note (search speed):** `solver.search` is over-budget for the roll-stab -- at 200s it had
      not finished drill level 0 for idle13 OR sheathed; its `_dust_cache` under-samples the
      1-f32-col-per-z genuine set (step 0.001 >> f32) and mis-guides the drill. The 91s find used a
      focused warm-start from the same-seam idle13 recipe (objective-compliant: seed-only). Fold that
      into a reproducible <2-min sheathed solve; do NOT trust the generic drill for the roll-stab.

## The sheathed roll-stab clip: row-18 blocker RE-ROOT-CAUSED as a transient band-stick decode divergence (session 40, LIVE, jitter-immune)

32. **[CORRECTED session 41 -> #33: the "1-frame band stick decodes to ~aim / holds prior" claim below
    is WRONG. A deterministic stopped-position probe proved the band DECODE registers its raw value
    bit-for-bit (target + msd), even as a 1-frame transient. The row-18 divergence is a WALK-SPEED gap
    (the sim dips speedF on the band magnitude at cap; the console does not), NOT a decode gap. The
    session-40 single-frame decode read was itself a ±1-frame misread of run_dtm's log (the same trap
    it claimed to have designed out -- the log's stream->frame offset is ±1 ambiguous, and a 1-frame
    event lives entirely inside that window). Read #33.]**
    **The row-18 blocker is a TRANSIENT (0.889,1.0)-magnitude-band stick input-layer decode divergence
    -- NOT the two-angle/MOVE-turn settle of #31.** Session 40, all measured jitter-immune (deterministic
    game_frame tags, `fixtures/sheathed_roll_ship_jitterproof.json`), the run_dtm poll-jitter that misled
    #31 designed out:
    - **The stick DECODE is bit-exact live.** Holding each band stick CONSTANT for 8 frames, live
      `mStickDistance`/`m34DC` == the sim's closed-form `main_stick_decode` exactly (`(96,192)`->0.9605,
      `(98,191)`->0.9313, ...). So there is nothing wrong with the decode formula, and the two-angle
      chase is faithful (it follows `target`, which is correct for held sticks).
    - **But a 1-FRAME TRANSIENT band stick decodes DIFFERENTLY live.** At ship row 18 the acted stick is
      the fine `(96,192)` (msd 0.9605, in the band). The sim decodes it raw (target 33367, msd 0.9605)
      and turns; LIVE decodes the 1-frame transient to ~aim (target 33295, msd 1.0 -- it HOLDS the prior
      value) and does not turn. Non-band 1-frame fines (`(98,188)` 0.878, `(99,183)` 0.785) register
      correctly. So the band divergence is a TRANSIENT/input-layer effect (input smoothing/latency near
      the magnitude cap), the same "input-layer != /54" family precise-stop.md/land-planner.md warn about
      and the freeze planner already excludes from its crawl.
    - **This means the session-39 winning hit is not predictive live (it depends on the sim's mis-model),
      and the SEARCH SHAPES tried this session did not find a band-faithful hit.** The winning hit's
      genuine landing depends on the sim treating that transient band stick as a real ~0.9605/33367 perp
      nudge, which live reads as ~aim -- so the sim must be made band-FAITHFUL before its hits are
      trustworthy. And the pure LIVE-VALID lattices tried (every stick msd<=0.889 or ==1.0, avoiding the
      band; dense 2-knob vernier arc + clean fine + K3-crawl-3rd-byte) reached only ~0.0013u from the f32
      dust with 0 genuine over ~60k runs. The dust is single f32 columns (~0.001u spaced); those
      lattices did not align onto one. NOTE: 0.0013u bounds the recipe SHAPES tried, NOT the clip -- a
      richer input alphabet / faithful band model is the untried lever.
    - **RULED OUT this session (approaches, not the clip):** (a) path-1 "clean-settle" re-search -- a
      speedF dip on a fine-ACTED frame is live-faithful (live turns there too), so a clean_settle filter
      wrongly rejects real dips; only transient BAND sticks are sim-only. (b) "fix the decode as a
      closed-form" -- the held decode is already bit-exact; only the 1-frame transient diverges (needs an
      input-layer/buffer model, not a decode-formula change). (c) the #31 "two-angle settle" story --
      refuted (chase faithful).
    - **Open approaches to PURSUE (the clip is not solved -- keep pushing):** (1) MODEL the transient-band
      input-layer behavior to f32 -- characterize it with a live band-transient sweep (is a 1-frame band
      stick == prior-frame value? a 2-frame slew?) and make `main_stick_decode`/the input buffer
      reproduce it, so the solver searches over what live ACTUALLY does, then solve band-faithfully; (2)
      EXPAND the search well beyond the shapes tried (more knobs, longer crawls, other draw/arc/A_proj
      placements, a walk-stab-solver warm-start) to close the last ~0.0013u -- the 0.0013u floor is a
      property of the tried lattices, so a richer alphabet is the lever; (3) exploit delivery-mechanics
      DOF not yet used (draw timing, B timing, roll-entry frame). Ground truth:
      `fixtures/sheathed_roll_ship_jitterproof.json`.

## The sheathed roll-stab clip: row-18 blocker is a BAND WALK-SPEED gap, not decode (session 41, LIVE, deterministic)

33. **[CORRECTED session 42 -> #34: the "console's BAND WALK-SPEED is unmodeled" mechanism below is
    WRONG. Reading the RAW SI-delivered pad (`g_mDoCPd_cpadInfo[0]`) from RAM proved the sim/decomp
    physics are FAITHFUL and the stick decode is faithful even for Y>=192 when ISOLATED -- there is no
    band-walk-speed gap to model. The row-18 miss is a make_dtm DELIVERY DROP: the game never receives
    the band fine (it polls the full neighbour). The "OPEN SUBTLETY" below (probe dips, ship doesn't)
    was the tell -- a walk-speed formula cannot be context-dependent; a delivery cadence can. The z/speed
    observations below are all correct; only the mechanism (walk-speed formula) is wrong. Read #34.]**
    **The row-18 live miss is a ONE-FRAME along-track (walk-SPEED) deficit from a band-magnitude stick
    at the speed cap -- the sim is NOT modeling the console's band walk-speed. NOT a decode gap (#32
    wrong) and NOT a facing/MOVE-turn overshoot (#31 wrong).** Both prior diagnoses were ±1-frame
    misreads of run_dtm's per-frame log; reading the ROBUST z-trajectory (immune to ±1 -- a
    misalignment shows as a ~17u step, not 1.9u) settled it. Established this session:
    - **The band DECODE is faithful, even for a 1-frame transient.** A DETERMINISTIC probe -- deliver
      `aim*cruise + [1-frame T] + neutral*16 (decel to a DEAD STOP)` and read the STOPPED position
      (constant -> ±1 read cannot corrupt it) -- gives, for the culprit `(96,192)`, live stopped pos ==
      the sim's raw-decode prediction BIT-FOR-BIT (0 ULP; sim's no-op "holds prior" prediction was off
      by 20.9u). A sub-band control `(98,188)` likewise. So the sim's `main_stick_decode` (target + msd)
      is correct for band 1-frame transients -- overturns #32. Tool: `harness.rollstab.capture_decode.
      transient_probe` (stopped-position, deterministic; `python -m harness.rollstab.capture_decode
      probe`); the per-frame `capture_decode.band_sweep` is NOT
      reliable for 1-frame reads (its stream->row offset is ±1 ambiguous; O=2 and O=3 both give 0
      disagreement on settled runs).
    - **The divergence is purely SPEED (z), not facing (x).** gf-aligned to the jitter-immune golden
      (`fixtures/sheathed_roll_ship_jitterproof.json`, gf = 2*row + const; the emulator counter ticks
      twice per game frame -- 0 gf conflicts, clean +2 cadence): rows 0-17 are BIT-EXACT (incl. the
      whole arc at rows 12-16, and sub-band 1-frame fines, and a held-2 full stick). At row 18 the sim
      dips speedF 17->15.091 while live holds 17.0; perp x matches to 0.02u. The one-frame deficit
      `17 - 15.091 = 1.909` == the observed 1.9125u lag, which FREEZES through the roll -> `old` off the
      f32 razor -> no clip. Confirmed by two independent live runs (the golden + a fresh `deliver ship`:
      live old z 306.116 vs sim 308.028, d = -1.912).
    - **The mechanism (decomp): `mStickDistance` walk-speed.** `setNormalSpeedF` (d_a_player_main.cpp:2306)
      sets the target speed `dVar10 = mStickDistance * (mMaxNormalSpeed * mStickDistance)` = msd^2*max;
      for `(96,192)` msd 0.9605 that is 15.68 < 17 -> the sim decelerates. `setStickData` (10569) sets
      `mStickDistance = g_mDoCPd_cpadInfo[0].mMainStickValue` (JUTGamePad::CStick::update value =
      `min(hypot(clamped)/54, 1)`). The whole game path (PADRead->PADClamp->CStick::update) is STATELESS
      (decode faithful), so the gap is the console's EFFECTIVE walk-speed for a band magnitude, which
      differs from msd^2*max. This is the SAME band-speed caveat precise-stop.md already documents
      (held `(128,196)`: console 15.76 vs sim 16.38 -- sim HIGHER when held; but for a 1-frame band at
      cap the console holds full and the sim dips -- sim LOWER). Only band magnitudes (0.889,1.0)
      diverge; sub-band and full are bit-exact live (rows 0-17 prove it). `start1 (98,191)` is band too
      but was bit-exact -- because it is in the start crawl at LOW speed (target above current -> still
      accelerating -> no dip); only band AT CAP dips.
    - **OPEN SUBTLETY (do not over-claim a mechanism -- the #31/#32 lesson): the probe (band after plain
      cruise) MATCHED the sim's dip bit-for-bit, yet the ship (band after the arc) shows live NOT
      dipping.** Same stick, same cap speed, same bit-exact entering state -- so an arc-carried hidden
      state (travel/anim/turn-lean) changes the console's band-speed response, and the sim does not model
      it. Not isolated this session; it does not change the fix.
    - **INTERIM WORKAROUND (session 41): `solver.fine_family` now EXCLUDES the (0.889,1.0) band**
      (`_in_band`), so the solver cannot emit a divergent 1-frame band fine. But this lands on session
      40's wall -- the band-free search does not reach the f32 dust (band fines were the near-full-mag
      fine-perp density). Deliverable hit is NOT found band-free.
    - **NEXT (Dereck's directive: model what the sim isn't modeling): resolve the RED gate
      `tests/test_sheathed_roll_clip.py::test_sheathed_band_speed_at_cap` by modeling the console's
      band-magnitude walk speed to f32** -- decomp-first from `setStickData`/`mMainStickValue` /
      `JUTGamePad::CStick::update` value near the cap (and characterize the arc-carried context
      dependence via the deterministic stopped-position probe, NOT per-frame run_dtm reads). Once
      faithful, REMOVE the `fine_family` band-exclusion so the solver can USE band sticks again
      (restoring density), re-solve, deliver.

## The sheathed roll-stab clip: row-18 miss is a make_dtm DELIVERY DROP, not physics (session 42, LIVE, RAM-confirmed)

34. **The row-18 live miss is a `make_dtm` poll-cadence DELIVERY DROP -- the game never receives the
    band fine -- NOT a Link-physics gap and NOT the "band walk-speed" of #33 (WRONG).** Found by reading
    the RAW SI-delivered pad from RAM (`g_mDoCPd_cpadInfo[0].mMainStickValue` @ JP 0x80398310, and PosX/
    PosY/Angle @ 0x80398308/+4/+0xC), i.e. what the game ACTUALLY polls, instead of inferring it from
    downstream speed/position. Tool: the cpad read is now in `harness.rollstab.capture_decode` (`capture`
    logs cpad_val/px/py; `delivery_sweep` = the (polls,seed) delivery probe; `sweep` CLI). Established:
    - **The decomp physics + decode are FAITHFUL (traced, not assumed).** Every function in the row-18
      path matches the sim line-for-line: `setStickData` (10569), `setNormalSpeedF` (2301: the
      `dVar10 = msd^2*max` decel is unconditional once `msd^2*max < mNormalSpeed`), `setSpeedAndAngleNormal`
      (2751), `setBlendMoveAnime`'s `m3598` (pure function of nspeed, 2976/3163/3180), the 0.3/0.7 toe
      recursion (2399-2484). `PADRead->PADClamp->CStick::update->mMainStickValue` is stateless. So per the
      decomp, IF the game received `(96,192)` msd 0.9605, it MUST decel -- there is nothing to "model".
    - **The stick decode is faithful even for Y>=192 when ISOLATED.** A 1-frame `(96,192)` (and `(96,193)`,
      `(98,192)`) after plain cruise delivers `cpad_val` == the sim's `main_stick_decode` bit-for-bit and
      dips. So #33's "band walk-speed" premise is void -- there is no band-magnitude walk-speed gap.
    - **In the SHIP the band fine is DROPPED in delivery.** At fed-index 16 (acted row 18) the game polls
      the FULL neighbour: `cpad_val=1.0, (px,py)=(-0.32,0.95)` == the `(77,249)` stick, NOT `(96,192)`'s
      `(-0.3148,0.9074)`. A distinctive px=0 marker at fed-16 ALSO drops (positional, value-independent);
      an all-full ramp delivers every frame; the ship's OTHER fines (0.9313 START, 0.7848 arc, 0.8784)
      DO deliver -- so a CLUSTER of preceding partials induces a sub-frame poll-phase slip that drops a
      later 1-frame partial. This single dropped dip is the ENTIRE 1.9125u miss (offline: forcing row-18
      to full shifts along-track by exactly -1.91248u; live old_z 306.116 == sim 308.028 - 1.912).
    - **The cause is `make_dtm`'s poll cadence, and `seed` controls it (live sweep):** with the pipeline
      default `(polls=4, seed=1)` the band drops (roll row 22); `(4, seed=0)` DELIVERS the band at the
      SAME roll row 22 (timing preserved); `(4, seed>=2)` delivers but shifts timing (roll row 23);
      `(8, *)` delivers every frame but at ~2x timing (each authored frame spans 2 game frames -> the
      plan's discrete B/A land wrong; no clip). So the game reads ~4 SI polls per 30fps logic frame
      (polls=4 = correct 1:1); `seed=1`'s leading neutral poll sets the phase that slips.
    - **THE FIX (characterized, NOT yet shipped):** `make_dtm(seed=0)` restores delivery at correct
      timing, BUT seed=0 alone still leaves a ~0.6u residual and no OOB clip -- because changing the
      leading-poll layout desyncs the from-rest prefix the sim's `rest_noops` (session 38) is calibrated
      to. So the clean fix is **`seed=0` PLUS re-derive `rest_noops` for the seed-0 layout** (mint.capture_rest
      derives it from the t1-advance), re-verify REST BIT-EXACT, then the session-39 hit should clip.
      **[UPDATED session 43 -> #35: the delivery fix + its live-measured seed-0 model are RIGHT and DONE,
      but "then the session-39 hit should clip" is WRONG -- the s39 hit was solved on the seed=1 model
      and is NOT genuine under seed=0. A fresh seed-0 solve is required. Read #35.]**
      Validate with `capture_decode.delivery_sweep`: VALID == every authored fine received + roll row
      unchanged + OOB `proc 0x24`. The `fine_family` band-exclusion (#33/solver.py) is NOT the fix and
      should be REMOVED once make_dtm delivers faithfully (it removes usable fine-perp density -- s40's
      0.0013u wall). OPEN: whether this drop is Dolphin-DTM-specific or real-hardware (a real TAS would
      hit the same SI cadence) -- the fix makes the sim+DTM self-consistent regardless.

## The sheathed roll-stab clip: seed=0 delivery fix is DONE, but the seed-1 hit doesn't survive it (session 43, LIVE-measured)

35. **The make_dtm seed=0 delivery fix and its from-rest model are correct + shipped, but the session-39
    hit does NOT clip under seed=0 -- a fresh seed-0 solve is required, and it re-hits the sessions-39/40
    f32-dust density wall.** Refines #34's over-optimistic "then the session-39 hit should clip".
    - **The seed-0 leading-poll layout was MEASURED, not guessed.** Captured the seed-0 walk-entry live
      (`capture_walkentry seed=0`, jitter-immune, game_frame-tagged) and diffed the sim d_frame-aligned:
      seed=1 => noops=1 (bit-exact, byte-identical to the shipped model), **seed=0 => noops=2 (28/0
      bit-exact, dz=0)**. Coupling: `noops = rest_noops + (1 - dtm_seed)` -- fewer leading neutral polls
      => the game's rest blend advances one MORE frame before the plan, so the sim needs one MORE leading
      no-op (OPPOSITE sign to the intuitive "seed=0 => fewer" guess; #34's "re-derive rest_noops" framing
      was right in spirit -- it is +1, not via mint's savestate-phase advance which is seed-independent).
      Golden `fixtures/sheathed_walkentry_seed0_golden.json`; gate `test_sheathed_rest_bitexact_seed0`.
    - **RULED OUT: delivering the session-39 hit via seed=0.** Its exact stream bytes, replayed through
      the measured-correct seed-0 model, land `old` at z=308.616 (=308.028 + 0.588), OFF the f32 razor,
      genuine=False (behind neither wall). seed-0's extra leading no-op shifts the whole from-rest
      approach ~0.59u along-track; the dust is single f32 columns, so any such shift lands off-razor.
      The hit does not survive; gate `test_s39_hit_not_genuine_under_seed0`.
    - **RULED OUT (this session's re-solve sweeps, ~several-thousand runs, seed-0, band fines re-enabled):
      the ad-hoc focused sweeps do NOT break the density wall.** Full-mag arcs octagon-clamp (perp
      collapses to discrete values, |rho| floor ~0.017); the partial interior 3rd-crawl-byte gives fine
      perp (~2e-4 steps) but a DEAD-BAND GAP straddling rho=0; A_proj barely moves z (the fixpoint snaps);
      sub-band along fines at bearing F yield only ~6 distinct sticks (coarse z); a partial-mag arc was
      worse (0.033). Nearest ~0.0035u, 0 genuine -- the same wall session 40 hit at 0.0013u. Band fines
      (msd 0.889-1.0), now deliverable under seed=0, are an ALONG knob (the speedF dip), NOT perp, and
      near-cap ones clamp -- so re-enabling them did not add perp density. The generic `solver.search`
      drill is over-budget (>2 min) and under-samples the 1-f32-col-per-z dust.
    - **DEEPER ROOT CAUSE (session 43, later): a general seed-0 CRAWL bug, not a constant-tuning problem.**
      Under `dtm_seed=0` the leading no-op count is 2 (measured), so `rest_state`'s seed step eats noop #1
      and **the FIRST start-crawl frame (`start[0]`) is eaten as a dead no-op** -- any crawl-based search
      under seed=0 SILENTLY LOSES its first crawl frame. This is almost certainly why the existing derived
      search (`solver.search` via `start_family`) under-performed under seed=0: its crawls compose one frame
      short, NOT because its (already-derived, non-magic) constants are wrong. The objective-compliant fix
      is GENERAL -- handle the seed-0 leading-dead-frame at `run()`/crawl-composition (e.g. prepend one
      absorber frame) so every derived family (`start_family`/`arc_family`/`fine_family`) composes correctly
      under seed=0 -- then run the EXISTING search. Do NOT hand-tune a bespoke per-seam solver.
    - **KNOB ROLES VERIFIED (Dereck's hint; the along fill works once the frame ACTS):** the ACTED crawl
      MAGNITUDE is the fine along/z fill (sweeping an acted crawl frame's magnitude walks `old` z across
      298.5..308.5 in fine ~0.02-0.5u steps); partial-INTERIOR crawl BEARINGS give continuous perp
      (|rho| -> 0.0007, no dead-band -- the full-mag arc's dead-band gap was because a clamped edge stick
      is discrete). `A_proj` is COARSE: the fixpoint crossing pins `old`'s along-position, so A_proj only
      SELECTS the ~16u walk-step (z jumps {272,293,307.9,324,343}; one in-band step); the sub-step z fill
      is the acted-crawl magnitude, NOT A_proj.
    - **LESSON (Dereck flagged mid-session): do NOT overtune constants to one anchor/seam.** A prototype
      `solve_focused` with hand-picked bearing ranges / magnitude sets / magic A_proj values / nbrackets was
      built and then DISCARDED -- it is calibration-flavored drift, not a pure-sim solver. Keep the derived
      families; fix the general seed-0 crawl composition; let the existing search run. Infrastructure in
      place (committed 15cf4d3): `dtm_seed` threaded through rest/solver/deliver/capture_walkentry (default
      1 = byte-identical); a hit records its `dtm_seed`; `deliver` ships with it; `fine_family` band-
      exclusion removed. **NEXT-SESSION TASK: the general seed-0 crawl-composition fix, then run the
      existing derived search under seed=0.**
    - **RESOLVED (session 44): the general seed-0 crawl-composition fix WORKED and the clip DELIVERED
      LIVE 0-ULP.** The "density wall" was a symptom, not the disease: under `dtm_seed=0` the extra
      leading no-op silently absorbed the start-crawl's FIRST frame `start[0]`, so every crawl composed
      one frame short (that is why the s43 seed-0 sweeps under-performed -- not the constants). Fix
      (`solver.run`, no tuned constants): prepend `(1 - dtm_seed)` neutral ABSORBER frames so `start[0]`
      always lands on the first LIVE frame; the absorber is a FULL frame (a `polls` multiple) so seed-0's
      correct sub-frame poll phase is preserved. With it, the SAME session-39 recipe RE-COMPOSED under
      `dtm_seed=0` reproduces the genuine clip bit-for-bit and DELIVERS live (proc 0x42 CUT -> 0x24 OOB,
      old/new drift 0-ULP; golden `fixtures/sheathed_roll_ship_seed0_golden.json`, gate
      `tests/test_sheathed_roll_clip.py::test_sheathed_ship_delivery` GREEN). NOTE the distinction the
      fix rests on (`test_s39_hit_not_genuine_under_seed0` still PASSES): replaying the s39 BYTES via
      seed=0 stays off-razor (#35 above) -- you must RE-COMPOSE the recipe (which prepends the absorber),
      not byte-replay. STILL OPEN (non-blocking): the GENERIC `solver.search`/drill under seed=0 remains
      over-budget and does not reach the dust unaided (the recipe came from a session-39 focused
      warm-start); a reproducible <2-min focused solve is optional polish, the CLIP is done.

## A near-flat seam's thrust facing does NOT derive from the interior bisector (session 48, offline)

Generalizing `walkstab.py` through `SeamGeo` (Phase 4), the session-47 handoff said to "derive the
settled thrust facing from the bisector like `F`" -- the rule that works for the ROLL seam. **It is
wrong for a NEARLY-FLAT seam and was ruled out before building on it.**
- Measured (kaze r11 walk-stab seam, interior 168.97 deg, csangle 4522): the shipped threading facing
  is **5625**, and `bear_to_S` (the bearing from the anchor start to S) is 5584 -- they match. The
  geometric interior bisector (the `-(nA+nB)` into-corner convention, ~19.4 deg) decodes to **3576**,
  ~11 deg / ~2000 s16 off. So `derive_F(bisector)` gives the WRONG facing here.
- Root cause: a 110-deg corner (the roll seam) is clipped by aiming INTO the corner along the bisector;
  a near-flat seam is clipped by GRAZING toward the seam vertex S, i.e. `bear_to_S` -- which is
  anchor-start-dependent, not pure seam geometry. The two aims coincide only for a sharp corner.
- Resolution (Dereck-confirmed): per-seam AIM SOURCE. `SeamGeo(aim_deg=)` defaults to the fixture
  bisector (corner seams like the roll unchanged, byte-identical); the flat-seam driver passes
  `aim_deg=bear_to_S`. Same `derive_F` stick-settle mechanism, different source direction. Verified:
  `derive_F(bear_to_S)==5625` bit-exact; the shipped walk-stab clip still reproduces 0-ULP.
- **Do NOT** re-bind a flat seam's F to the bisector when minting a novel near-flat seam in Phase 5.
  Check the interior angle: sharp corner -> bisector aim; near-flat -> bear_to_S aim.

## The reachable band's NEAR edge is NOT geometric -- it is a reachability limit (session 49, offline)

Deriving the solvers' per-seam ranges (the Phase-5 prerequisite: `solver.py` ZLO/ZHI + dust-cache box,
`walkstab.solve_focused`'s d2S/N windows), the tempting move is to derive the search box's NEAR edge
from the seam's genuine geometry (a `pred_genuine` scan). **That is wrong -- ruled out before building
on it.**
- Measured (fine `pred_genuine` scan outward from S along the aim, at cap speed): the geometric genuine
  region runs ALL THE WAY from the seam vertex (d2S ~ 0) to the lunge reach (d2S ~ `reach`) for BOTH
  the roll and the walk seam. There is NO geometric near bound at the shipped windows' lower edge
  (roll `ZLO`->d2S~43.5, walk `WIN_LO`=34.5). With infinite wall planes a close `old` + a full lunge
  still lands `new` far behind the plane, so it reads "genuine".
- The shipped windows' near edge is therefore a REACHABILITY limit: the wall braking the roll/walk
  approach short (dead-end #3 -- the wall-LESS sim overshoots to an `old` live cannot reach). It is a
  DYNAMICS quantity, not seam geometry, so no geometric scan recovers it.
- Resolution (Dereck-chosen, over a derived-span or padded band): decide reachability by a real WALLED
  PHYSICS re-sim -- `solver.wall_faithful` (new) / `walkstab._wall_faithful` (existing) -- and keep only
  the FAR edge + a generous general RELATIVE search bracket `SeamGeo.search_band()=[reach*0.80,
  reach*1.02]` (seam-independent fractions, not per-case constants) to FOCUS the search. The far edge
  `reach` is derived from the cut model (`SeamGeo.reach_at`). Gate: kaze roll + walk still reproduce
  their shipped hits and `solve_focused` still finds wall-faithful hits < 2 min. See the
  `no-overtuned-constants` memory + README `## Status` (session 49).
- **Do NOT** reintroduce a typed-in `old_z`/d2S near-edge, and do NOT try to derive one from a
  genuine-geometry scan -- the near edge is only knowable by simulating the approach WITH the wall.

## A sharp corner's clippable aim can be FAR off the bisector -- feasibility must sweep ALL aims (session 50 CLAIM, OVERTURNED session 51)

Picking the first Phase-5 novel target, the distinct 97-deg corner S=(13539.24, 493.36) (kaze r11, walls
871 x 899) was chosen because its `disp_floor = wall_r/sin(interior/2) = 46.73 < 49.22` (roll reach), so
the scanner tiers it ROLL.

**Session 50 ruled it "NOT roll-clippable at ANY displacement" -- that ruling is WRONG (overturned session
51). The seam IS roll-clippable; the s50 search just never aimed where the gap is.** At aim ~90 deg (facing
16384) it has a coherent genuine f32 razor: **26 `SeamGeo.pred_genuine` points**, all in_front, along-band
d2S 29.6..49.1, perp -0.094..-0.057 (perp grows linearly with along -> a real threadable gap, not an f32
fluke). Confirmed by an ALL-FACING f32 scan (`pred_genuine` at true f32 perp resolution ~0.0005u; a coarse
perp step reads 0 even for the PROVEN/mirror seams, so resolution is load-bearing).
- WHY s50 missed it: its "6 methods" swept aim only `dir +-15deg` around the INTO-CORNER bisector (131.5
  deg). The clippable aim here is ~90 deg -- ~41 deg OFF the bisector -- so it fell outside every sweep.
  The into-corner aim genuinely gives 0 (wall 899 extends +z, away from the +x,-z into-corner roll dir, so
  an into-corner lunge exits both finite wall segments); but a GRAZING aim (~90 deg, roughly along wall
  899) threads the vertex. Same phenomenon as the near-flat walk seam clipping at `bear_to_S`, not the
  bisector (dead-end above): the clippable aim is NOT always the bisector, even for a SHARP corner.
- `disp_floor` is still only a NECESSARY lower bound (assumes symmetric walls), and `characterize`'s
  continuous screen still over-promises vs the finite-extent f32 CrrPos truth -- both true. What was wrong
  was concluding "infeasible" from an aim-BOUNDED f32 sweep.
- LESSON (corrected): a feasibility scan MUST sweep the FULL aim circle (all facings) at TRUE f32 perp
  resolution, not just +-15 deg around the bisector. The right feasibility probe is
  `SeamGeo.pred_genuine` over (along, perp) at each facing (the exact sim acceptance). `derive_F` from the
  bisector is only the DEFAULT aim; a corner whose gap is off-bisector needs its clippable aim passed as
  `aim_deg=` (the s48 per-seam-aim mechanism), same as a near-flat seam.
- STATUS (session 53): the reachability puzzle is RESOLVED with LIVE DATA -- the 97-deg corner's genuine
  dust is NOT reachable by a standard from-rest ROLL, and this is REAL GEOMETRY, not a sim over-correction.
  The crux (session-52 angle 2) was whether the sim's 35u WallCorrect hold is faithful near this concave
  corner. Answer, LIVE (clean DTM, facing 16306, seed=0, per-frame RAM read; NEVER advancewith): the walled
  from-rest roll is **BIT-EXACT with live through the entire roll + wall-slide** -- Link's center is held at
  wallA_d==35.00 exactly as it grazes wallA, never closer (gate `test_seam97_roll_wallhold_bitexact`,
  immutable golden `fixtures/seam97_roll_wallhold_golden.json`). So:
  * The corner's only genuine dust hugs wallA at wallA_d **2.79..5.43u** (15 f32 razor points at the ~90-deg
    grazing aim). The live-faithful roll hold is 35u. A **500k+-candidate f32 scan of the reachable mouth**
    (old >=33u from BOTH walls) across grazing aims 84.6..94.5 deg found **0 reachable genuine** -- the s52
    108-sample result, now rigorous. The dust sits ~30u inside the hold: roll-unreachable.
  * NOT "impossible" (Dereck's rule stands): a clip position hugging a wall is exactly the kind reached by
    PUSH-STEERING (the standalone Tetra Co-push STEERS the lunge and overrides the free-roll hold) or another
    mechanic -- not by a free roll. What is ruled out is the STANDARD ROLL technique for THIS corner, not the
    clip's existence. Next-target choice (push-steer this corner vs. a different novel roll target for the
    generalization proof) is a STRATEGIC pick, surfaced to Dereck.
  * Angle 1 (relax `solver.wall_faithful` to reject only bonks, not any `wall_hit`) is a correct
    concave-corner model tidy but does NOT unblock: the sliders it would admit are held at 35u = non-genuine.
    Left unchanged (no passing use-case; would be speculative churn).
  Tooling used: `seam_feasibility.py` (all-facing f32 scan), the reachable-mouth f32 scan, and the live
  roll-vs-sim wallA_d diff. The anchor + walled-REST-bit-exact model + mint recipe (align-walk -> settle ->
  teleport-to-rest -> mint_current for a fixed-camera novel anchor) all stand from session 52.

## Unpanned mints at an auto-cam region + off-line anchors (session 54, LIVE)

36. **Minting a novel-seam anchor WITHOUT the C-stick pan, anywhere the auto-cam tracks Link: RULED
    OUT.** Mid-room kaze r11 (unlike the +493 seam's FIXED-cam region, where s52's pan "sprang back"),
    the auto-camera's yaw chases Link's POSITION while he walks (~5-20 s16/frame; it NEVER moves while
    Link is idle, so a post-teleport transient does not relax by waiting) -- every unpanned mint's
    delivery walk creeps csangle and the constant-cs rest model can never be bit-exact. This is what
    actually blocked the z-mirror 97-corner S=(13539.24,-493.36) (whose dust IS bisector-roll-reachable,
    11 mouth-open points -- the seam is NOT ruled out; retry it WITH the pan). The fix is the SHIPPED
    `mint.mint_novel` C-stick pan (arms the MANUAL cam, frozen for good after the walk-settle leash
    pull) -- proven at the 152-corner: csangle 22603 frozen bit-exact through the whole live approach.
    Screen a candidate's cam regime BEFORE minting (walk its approach live and diff csangle); do NOT
    conclude "needs camera-in-the-loop" until the pan has been tried.

37. **An anchor minted OFF the F-through-S line (|perp| beyond the arc reach ~15u): 0 hits, always.**
    `mint_novel`'s settle walk drifts off the park bearing (advancewith stick injection + the cam moving
    during the walk), so the rest can land far off-line (117.5u at the first 152-corner mint). The
    solver's gross perp knob is the arc (~+-15u); nothing else closes tens of units, so `solve_focused`
    returns 0 wall-faithful with Phase-A best score == the line offset (the diagnostic tell: score >> 1
    means MINT problem, not search problem). Fix at mint time: measure `seam.perp(rest)` from the seed
    and re-park by -perp (1 iteration sufficed). Do NOT widen the arc family to chase an off-line anchor.
    Corollary (positive): the anchor need NOT face F -- facing 25794 vs F=29729 (~22 deg) delivered fine;
    the arc bracket absorbs initial misaim, and REST bit-exactness is the only hard precondition.

## Rest-perp-only re-parks + thin-dust knob-family re-draws (session 55, z-mirror 97-corner)

38. **Re-parking an on-line mint by the REST's perp alone: insufficient wherever the settle misaim
    is large.** #37's fix ("re-park by `-seam.perp(rest)`") under-measures: the settle walk's misaim
    (~23 deg at the 97m corner, facing 4630 vs F=8769) makes the approach's MOVE turn to F add more
    perp BETWEEN rest and the roll (~12u here), so a rest-on-line anchor still rolls from perp +15
    -- outside the arc family's ~+-9u reach, 0 hits with Phase-A best score == the residual (the #37
    tell, at a smaller magnitude). The fix (shipped, `mint.mint_online`): measure the PURE-SIM
    baseline roll `old`'s perp from the minted seed (`solver.run(anchor, [])` -- offline, no live
    round-trip) and re-park by THAT; converges in 1 step (the park shift translates the trajectory
    ~1:1). s54's 152-corner never saw this because its settle misaim's drift happened to be small.
    GOTCHA (harness): `solver._BASE`/`_BASE_WALLED` cache rest states by ANCHOR NAME -- a re-park
    loop that re-mints the same name in one process must invalidate them (mint_online does), else
    every iteration measures the FIRST mint's trajectory.

39. **A THIN-DUST seam vs. the chaotic-crawl focused search at the 2-minute budget: knob-family
    re-draws do NOT scale -- 8 independent full draws found 0 hits.** The z-mirror 97-corner is
    roll-REACHABLE (mouth-open dust 35-37u off both walls; `roll_reachable` accepts; anchor REST
    BIT-EXACT via the pan mint -- #36's retry is CLOSED, the camera was never the residual blocker),
    but its genuine dust is an order thinner than the delivered seams': fine-scan (0.02 along x
    0.0002 perp, reach band) counts **84** samples (13% of along rows, slivers <=0.0006u, perp band
    0.02u) vs the mirror's **360** and the 152-corner's **1409** (70% rows, 0.41u band -- why those
    delivered in one ~80s draw). Ruled out at this budget: finer arc `off_step` (60 == 120
    byte-identical brackets -- arcs octagon-saturate at Phase-A level too); the frame-2 partial-mag
    m2 sweep + c3 base-magnitude families (shipped as `solve_focused(m2s=, c3m=)` -- correct
    generalizations of the documented K=3 crawl, kaze byte-identical at defaults, but each draw's
    chaotic cloud has local perp spacing ~0.008u vs sliver width ~0.0002-0.0006u => < 1 expected hit
    per draw); a 2D frame2 x frame3 byte grid (6.5k runs, closest approach 7.6e-5, still 0). NOT
    ruled out (the scaling paths, Dereck's pick): (a) run() THROUGHPUT -- ~4ms/run caps a draw at
    ~28k candidates; a faster from-rest walk (native core under the rest-exact foot) multiplies
    density directly; (b) a walkstab-style K=2-crawl Phase A (bracket DIVERSITY -- today's Phase A
    is deterministic, every draw hangs off the same 40 bracket centers); (c) another roll-reachable
    corner (the room scan lists 74 clippable seams; screen dust DENSITY first -- see the strategy
    page). LESSON: before minting a novel corner, fine-scan its dust and compare to the delivered
    seams' counts; reachability alone does not price the search.

## Throughput-scaled same-family draws on a thin-dust seam (session 56, z-mirror 97-corner)

40. **Scaling the SAME knob-family draws ~7x (run() throughput: lazy cruise-pose defer + fixpoint
    cross-hint + Phase-B worker pool, all bit-identical and gated) does NOT close the 97m: ~1.2M
    exact candidates across 7 draws (default grid, nudge=16, m2-dense 6-value sweep, c3m=0.72/0.6,
    kbr=60, and the new Phase-B2 fine drill on the 1169 nearest-to-column near-misses) found 0
    genuine.** Root cause, measured (the diagnostic that OVERTURNS the s55 "dust density prices the
    search" model, which predicted ~1 hit per ~30-130k candidates here): a bracket's byte-nudge
    cloud is NOT concentrated near its razor-close center -- over 2.6k fired candidates on the top
    bracket (center score 5.4e-4) the perp distance to the nearest genuine column is median
    **1.86u**, p10 0.33u, min 1.4e-3. ~99.8% of Phase-B candidates are never in the razor band, so
    the effective near-band sample count per draw is ~hundreds, not tens of thousands, and each
    near-band sample still needs the f32 z-sliver. Also re-confirmed: `fine_family` octagon-collapses
    to ~30 distinct sticks (#29/#32), so the B2 fine drill's perp lattice is coarse. Do NOT buy more
    of the same draws; the frontier is putting candidates IN the band: fresh Phase-A bracket
    families (a K=2 start-crawl inside Phase A), a 2D-exact dust ranking for the drill
    (`_genuine_perps` rounds to 1e-3 -- rank against the real sliver point cloud), or a denser
    corner screened for near-band YIELD, not raw dust count. The throughput work itself is KEPT
    (bit-identical, `tests/test_solver_fastpose.py` + a full-grid pool-vs-serial mirror A/B finding
    the same single hit); it is necessary, just not sufficient here.

## The B2 fine drill as a last-mile closer; rounded-column ranking; crawl-less Phase-A ranking (session 57)

41. **The Phase-B2 fine drill can NEVER "close a last ~1e-3" on a chaotic-lattice seam -- a fine is
    a fresh cloud resample, not a local refiner.** Measured (scratch mini-B2: the 200 near-misses
    TRULY nearest to real dust x all 150 fines = 19,230 exact candidates, 0 genuine): a 1-frame
    partial-magnitude fine displaces `old` by median ~3.5u ALONG / ~0.33u perp -- the same chaotic
    propagation as the c3 byte-nudge. So ranking B2 better cannot make it a closer; it is only more
    independent draws around good families. Two REAL bugs the same measurement exposed, both FIXED
    (session 57, `solve_focused` restructure -- this is the overturn of how s55/s56 read the search):
    - **`_dcol` ranked against a 1e-3-ROUNDED perp-column set with no along term**: the s56 drill's
      top keepers sat 3-12u of along from ANY real dust (dcol=1e-5 with true distance 3.0; top-40
      overlap with the true ranking 8/40) -- the drill budget was spent on phantoms. Fixed by the
      EXACT sliver point cloud (`_dust2d`, 0.005 along x 2e-5 perp over the column band, disk-cached
      ~30s/seam) + `_dust_dist` (perp x200, the legacy drill weighting).
    - **Phase A ranked the CRAWL-LESS arc trajectory while Phase B always added the K=3 crawl**,
      which displaces the center ~1.15u of perp on the 97m (the m2 magnitude family spans centers
      -1.15..-3.2 smoothly -- a usable steering knob, not chaos). The s56 "cloud sprays median 1.86u
      around a razor-close center" mystery was THIS: the razor-close score belonged to a family
      Phase B never evaluated. Fixed: Phase A' ranks crawl-INCLUDED centers (arc x A_proj x the full
      derived m2 family, pooled) by true 2D dust distance; Phase B nudges the kept (bracket, m2).
    Result on the 97m: near-band yield (fired candidates with d_true < 0.02) went 0 -> ~4.5 per
    110s draw, best child d_true 0.00121 -- but 4 knob-varied draws (crawl slot 0/1 x c3m 0.66/0.72,
    kbr=300; ~474k exact candidates) still found 0 genuine. At this sliver thinness (~0.026-weighted
    x ~0.001u rectangles) the expected hit rate is ~0.2-0.4 per draw: the restructure closes the
    structural waste, and delivery needs a handful more independent draw families -- or the denser
    corner -- not a different mechanism. Do NOT re-add an along-blind or rounded ranking, and do not
    expect B2 to refine.
    THIRD lesson (same session): pure ranked-GREEDY bracket consumption is ALSO wrong -- it lost the
    152 re-solve (its winning family's crawl-included center sits 0.28u of perp off-band, d_true 56,
    buried below the top-40 cutoff; the old crawl-less ranking had reached it by accident). A center
    point is noise at the cloud's ~1-2u chaotic scale, so a DENSE seam is priced by family BREADTH,
    a THIN seam by nearest-band-first order. The shipped consumption is ROUND-ROBIN across arc
    families (families ordered by best center, each off's best m2 first), which serves both: 152
    re-solves with 3 clips in 111s (old structure: 1 in 80s), mirror 2 in 112s (was 1 in 85s), all
    5 via B2 fines -- the drill earns its budget on dense seams as extra draws around good families
    even though it cannot refine.

## Teleport-to-rest after the cam settle; fixed-frame settle walks (session 58)

42. **Teleporting Link to the anchor rest spot AFTER the camera settle does NOT preserve the frozen
    manual cam -- a teleport resets the cam-Link leash geometry, so the next from-rest walk RE-PULLS
    the camera from scratch.** Measured live (163-corner, polys 458x827): after settle-until-frozen
    (csangle stable at 53178) + teleport back ~120-400u along the aim line, the verification walk's
    csangle crept 53590 -> 53178 over its first ~16 frames before re-freezing -- REST can never be
    bit-exact. The motivation was corridor length: the 163-corner's 720u corridor cannot fit
    park = d2s(580) + settle travel (~300-450u). The honest consequence: a mint needs the settle to
    genuinely END at the rest spot, so a novel corner needs ~1000u+ of clear approach line --
    `seam_screen.py` now measures `corridor` per seam so the pick sees it up front. The 163-corner
    (S=(9709.58,-13.43), the screen's densest walkable candidate, 5221 samples) stays a CANDIDATE
    blocked on the corridor, not on dust (geo kept: `fixtures/kaze_r11_seam163_geo.json`); the
    session-58 delivery took the 157-corner (1480 samples, 0.33u band, corridor 1400u) instead.
    Two REAL mint bugs the same session fixed (both general, in `mint.py`):
    - **A fixed-frame settle walk under-settles at some seams**: 14 frames left ~258 s16 of leash
      pull, which then played out during the verification approach (the same creep signature).
      Fixed: the walk-settle runs in chunks UNTIL csangle stops changing (cap `settle_walk`).
    - **The 1:1 re-park step oscillates when the settle misaim is large**: the measured baseline-old
      perp response per unit park shift was ~1.8 at the 163-corner (the MOVE turn amplifies), so
      -35.98 -> -11.83 -> +9.30. Fixed: a SECANT gain estimated from the iteration history
      (clamped; 1:1 on the first step) -- `mint_online` then converged in 1-2 iterations at both
      corners tried.

## Park space is FLOOR, not wall clearance; the default pan target can be the one bad cam track (session 60)

43. **seam_0467_0468 (kaze r11, S=(10762.53,-273.26), n=2285): NOT mintable by the current
    pipeline -- the aim-line FLOOR ends at d2S ~1050-1100 while this seam's settle needs the full
    42-frame cap (~722u, csangle never froze), so park = d2s(580) + settle(~720) ~ 1300u has no
    floor.** Parks beyond d2S~1050 teleport-slide off the edge and Link falls OOB (live-probed:
    FLOOR at d=1050, OFF-FLOOR at 1100+); reachable parks give rest d2S <= ~340, under the roll's
    rest envelope, so the baseline never fires (the s59 mint_online guard correctly refuses). Two
    lessons: (a) `seam_screen.py`'s `corridor` measures WALL clearance along the aim line, NOT
    floor coverage -- it read 1020 "clear" over a pit edge; screen the park FLOOR (live teleport
    probe, or the ground mesh) before minting. (b) The settle travel is per-seam (~324u at the
    824 corner vs ~722+ here, cam never frozen at the cap) -- park space must budget the MEASURED
    settle, not a constant. Geo kept: `fixtures/kaze_r11_seam467_geo.json` (the seam itself is
    dense, n=2285/0.031u band, and stays a candidate for a shorter-envelope solver -- but note the
    roll's ~580u rest floor is mostly PHYSICS: A-press runway ~506u + cap walk ~74u, see #44).

44. **Minting seam_0824_0826 at the DEFAULT aim-derived pan target: REST diverges at the first
    aim row -- the approach corridor carries a FIXED, ROAD-triggered camera-trigger band, and
    whether it fires depends on which cam track the pan leaves.** At the default target (aim
    45542 -> frozen csangle 50266) the verification walk's csangle dips ~-300 s16 over d2S
    ~588..384 and RECOVERS to exactly 50266 (facing tracks it one frame behind; same stick bytes
    all stream) -- not the monotone #42 leash creep, and not a per-walk pull (the five delivered
    anchors' verifications never wobble). Road-trigger proven by a shifted-start probe: a walk
    started 150u further along wobbles at the SAME WORLD band and re-freezes at the same x~10050.
    **Fix (shipped, `mint.cam_screen`): screen alternate `target_csangle` pan targets at the park
    -- all four probed alternates (F +-8000, +-16384) stayed FROZEN through the whole corridor --
    and mint with a frozen one (`mint_online(target_csangle=)`; here 37512 -> csangle 41530).**
    The value is measured per seam (a mint-time live screen, like the mint itself), never tuned.
    With it the 824 anchor minted at rest d2S 580.0, REST BIT-EXACT, and the clip DELIVERED live
    0-ULP in one default draw. Corollary noted for ROADMAP step 3: the ~580u rest envelope is
    mostly irreducible for the STANDARD roll -- the A press fires ~506u out (derived A_projs
    ~-507; roll travel A->cut ~463u) plus ~74u of cap walk -- so "a ~300u-rest anchor solves"
    cannot be met by the roll path; short-corridor seams need a different technique (walk-stab
    tier) or camera-in-the-loop, not a smaller A_proj.

## Preferring the default pan target in the cam screen; assuming settle travel is per-seam (session 61)

45. **Choosing the DEFAULT aim-derived pan target from the cam screen's frozen set (the
    novel_deliver first cut): the settle travel is TARGET-dependent, and a large-settle target
    parks the mint past the floor.** Measured at seam_0915_0918 (kaze r11, S=(13049.77, 1368.08)):
    from the SAME 1000u park, the five frozen targets' settle-until-frozen walks ended at rest_d2S
    332 / 332 / 526 / 382 / 688 -- a 356u spread, so "settle travel is per-seam" (ledger #43's
    lesson) under-states it: it is per-(seam, target) leash geometry. The default target's 668u
    settle implied a mint park at d2S 1248 -- past the floor edge (the probe had passed at
    1000/1100) -- so Link teleport-slid (dy -2.5) and fell OOB (state 39) before minting; the
    "minted" rest fields were falling-state garbage and the baseline roll could never fire
    (mint_online refused, correctly, 3 iters). Fix (shipped in `novel_deliver`): among FROZEN
    targets choose the one with the SMALLEST measured settle (deepest park inside the probed
    floor), and floor-probe the implied park whenever it lies beyond what the floor stage checked.
    With it the same seam minted at rest d2S 580.0, baseline |old perp| 0.001, REST BIT-EXACT,
    and delivered live 0-ULP.

## Open-terrain rooms: the screen's link_y is not proof of a mintable corridor (session 62, second room)

46. **Picking a second-room (flooded Hyrule) corner by density + corridor alone: three NEW floor
    failure classes the kaze screen never saw, each ruled out live by `mint.floor_probe` ladders.**
    Kaze r11's walls all stand on one flat floor, so `link_y` + wall-clearance `corridor` implied a
    mintable approach; open terrain breaks that three ways. (a) **SLOPED approach**: the top screen
    pick seam_0185_0193 (n=70098, band 0.059u, corridor 1400) has walkable floor the whole way --
    but it RAMPS (y -15 -> -135 over d2S 580..1100; likewise the -1853 region: -1782 -> -1872),
    and the rest model is flat-floor; REST can never hold. (b) **PHANTOM LEDGE**: seam_0202_0203's
    walls' bottom verts sit at y 199.12 with NO ground at that height (Link probes fall to the 0.16
    plain 199u below; walls based above Link's collision band are not even a barrier there) -- the
    geo's `link_y` = the wall-bottom vertex, which proves nothing about standable ground. (c)
    **OUTWARD MOUTHS on man-made floors**: all 8 castle-footing corners share a perfectly flat
    link_y -1267.71, but every mouth opens OFF the structure (bisector parks land in voids at
    y -2800..-5300); no aim keeps the ~1000u approach on the floor. Consequence: on a novel room,
    floor-ladder the pick's aim line (`floor_probe` at 200..1100) BEFORE the cam screen, and treat
    "FLOOR at every d" as necessary but not sufficient -- the ladder must also be FLAT (constant y
    == link_y), since fall_tol accepts +-60u of slope. The one Hyrule corner that passes everything
    (seam_2709_2919, ON the proven Tetra plain, grazing aim_deg=344 hugging the 300u flat strip
    along wall 2919) is dust-THIN (band_dense 0.011-0.014u, near-band yield 0-4/draw): an honest
    97m-class lottery, REST BIT-EXACT anchor ready.

47. **Minting from a savestate where Link is at LOW HEALTH: the idle is ANM_WAITB ("breathing
    heavily", `checkRestHPAnime`, d_a_player_main.cpp:3148 -- fires at life <= threshold), and the
    WAIT(4) rest-blend model (steady WAITS + procWait per-frame re-init) does not cover it: REST
    diverges at row 1 (live w ctrl frozen, then a 0-reset a few rows in).** The Tetra-session base
    savestate had life=1 (all the OOB falls). Fix is mint-time SETUP, not modeling: heal Link
    (write life @0x803B810B) in the base anchor (`hyrule_plain_base@twwgz` = healed
    tetra_pushaside). Two mint hardenings shipped with it (both general, `mint.py`): (a)
    `mint_novel` now PROBES for steady WAITS before minting (in the stop-transition tail the w
    ctrl holds frozen across a 1-frame advance; idle in chunks until it moves -- the first Hyrule
    mint's 20-frame settle_idle ended inside the stop anim: d_rate 0.6/0.4 vs steady 1.1); (b) a
    healthy-WAITS anchor reads d_rate 1.1 -- if a fresh mint's seed shows a different idle rate,
    suspect the idle arm before anything else.

48. **Trusting run_dtm's per-frame log INSIDE the REST gate on a slower-loading stage: the log can
    DOUBLE a row (the known [[run-dtm 1-frame jitter]]), and the index-aligned diff then fails
    every row after the duplicate while live physics is bit-exact.** On Hyrule the verification
    calib carried one byte-identical duplicate row (d frozen at 26.296 twice); logging the RAW PAD
    per row (g_mDoCPd_cpadInfo[0]@0x80398308, the jitter-immune probe) proved the walk entry
    structure matched kaze exactly. Fix shipped in the shared gate (`rest._dedup_log`): once
    d_frame leaves the rest value every real frame advances d/w/pos (procWait re-inits the blend
    each idle frame), so a byte-identical consecutive row is necessarily a log duplicate and is
    dropped before the diff. Kaze captures (no duplicates) are unaffected.

## Room events, deterministic mints, and the anchor-overwrite trap (session 63, third room)

49. **Delivering in a room with an ARMED one-shot auto-event (Hyrule Castle interior `Hyroom` r0,
    basement level): ANY A press across a broad region of the corridor fires the event instead of
    the roll** -- Link enters `daPyProc_DEMO_LOOK_AROUND2_e` (0xB5, evmng staff cut, ANM_WHO), the
    event camera takes over, and the ship movie ends with no CUT frame (deterministic: movie AND
    pipe; warm AND fresh-boot). Position-only walks NEVER trigger it (a stickless probe walked the
    whole corridor and wall-held clean), so the REST gate (no buttons) passes while the ship (A at
    ~row 12) dies -- the tell is `end proc=0xb5` + an event csangle in the failed watch log. The
    A-hijack region covered rest through d2S ~307 but not ~155; the roll physics pins A at ~460-510u
    from S, inside it. **Fix is mint-time SETUP (the #47 pattern): the event is ONE-SHOT -- play it
    out once (A-mash ~270 frames) in the mint BASE and save the consumed-event base
    (`hyroom_r0_base2@twwgz`); every later A rolls clean.** Validate a new room's base with an
    A-press probe mid-corridor, not just steady WAITS.

50. **Re-minting over the SAME anchor name while a solved hit is still unshipped ORPHANS the hit**
    -- `_generated/rollstab_hits.json` / the ship plan reference the anchor by name, and the new
    seed makes `deliver.gate` honestly fail (`dOLD != 0`), so the solution is lost with no way to
    reload the old rest state (the first cseam4002 anchor's 2-clip draw died this way). Ship (or
    at least gate-and-archive the winning stream + seed json) BEFORE any re-mint of the same name.

51. **Re-running an identical mint as a "fresh lottery draw": the mint is DETERMINISTIC from the
    base** (same teleport/pan/settle -> byte-identical anchor, byte-identical 0-hit lattice). Per
    #9 the ANCHOR is the lottery ticket; the honest re-roll knob is another FROZEN target from the
    cam screen's measured set (different csangle -> different F/dust slice/lattice), never a tuned
    offset. cseam4002: 8 documented families at csangle 44608 drew 0 (best d_true 0.21); the next
    frozen target (51544 -> cs 48971) delivered on the DEFAULT draw (margin 0).

Room-pick notes (same session): Tower of the Gods `Siren` r0 screens spectacularly (132 locator
clips on one flat Y) but is UNDELIVERABLE as a hunting ground -- the spawn is a boat spawn (Link
rides KoRL, state 137) and the big flat floor is the tidal pool bottom. The Hyroom basement's six
hexagonal Master-Sword-chamber corners screen at n~2.6M / band ~1u (a visibly open gap, not razor
dust) but their corridors are 460-700u, under the ~900u+ (rest 580 + settle) the standard roll
mint needs -- a non-roll technique's target, not a roll pick.

## Corridor props and the JP offset shift (session 65, GanonA / Phase G)

52. **Assuming a wall/floor/cam-screened corridor is CLEAR: dungeon corridors carry CC-capable
    PROPS (d_a_stone skulls, tsubo pots) that WallCorrect/GroundCross screening cannot see.**
    The GanonA r0 REST gate was BIT-EXACT rows 0-11 (the Phase G ground model validated live,
    pos_y tracking the incline) then diverged on a 4-frame decaying position push -- measured
    live: `speed` stayed exactly 17*dir(travel) while the position gained (+6.4, +7.3)u/frame
    rotating 41->85 deg, with NO wall hit, NO bg registration near the path, and every posMove
    additive term (cc/m3644/m36A0/m36B8/m3730) zero in the log -- the pusher was a **PROC_STONE
    (460) skull prop standing ON the corridor** at (569.72, 948.94, -2080.17), found by walking
    the live actor list. The sim runs no actor there. Fix is mint-time SETUP (the #47/#49
    consumed-base pattern): break the prop in the BASE savestate and mint from the consumed
    state. Screen a novel corridor by ACTOR SCAN (props within ~70u of the aim line), not
    geometry alone. Corollary: the divergence only fired because the anchor was 22.9u off-line
    (mint_online never converged here) and the aim stick ran a 226-tread mid-cruise turn --
    the first big turn any REST stream ever exercised; near-zero-turn streams on the other nine
    seams could never have flushed this out.
    RESOLVED s66 by AVOIDANCE, not the break recipe (Dereck's steer): declare `aim_deg` in the
    geo fixture so the whole approach line misses the prop (186.5 clears it by 77.8u where the
    bisector passed 16u), and actor-scan the NEW line before parking (a second prop sat ON it
    at along 918 - parked short of it). The base keeps the stone INTACT.

53. **Parking the rest PAST an on-line obstacle (d2S < ~440) fails the REST gate on stream
    length, not physics.** The verification stream is NPREF 10 + NCRUISE 18 = 28 walk rows
    (~430u of travel), so a rest minted past the GanonA stone (the stone sits ~300u from S,
    forcing rest d2S <= ~240u) walks into the corner walls mid-stream, and walls are outside
    the REST model. A REST anchor needs d2S >= ~450 regardless of how clean the line is; below
    that, fix the LINE (aim_deg) or the obstacle, not the park.

54. **Trusting the default aim-derived pan target off the bisector line: the GanonA cam leash
    CREEPS position-dependently on the 186.5 line** (~+4 s16 per row through the WHOLE
    approach, +125 near the corner; the s65 28401 "freeze" was a bisector-line property, not a
    corridor property). Signature: REST rows go pure-bearing-off (~0.08 deg) from the first
    cruise row while d/w frame ctrls stay exact. Fix is the ledger-#44 tool, generalized:
    `mint.cam_screen` at the actual park found two FROZEN alternates (25951/17567); mint with
    the smallest-settle one (#45 rule). A settle that hits the `settle_walk` frame cap without
    the csangle-freeze break is the tell that the default target never froze.

Also learned (same session, documented in `harness/rollstab/mint.py`): the decomp's US
field-name offsets shift **-0xD8 on JP** in BOTH daPy and fopAc space (m35B8 -> +0x34E0,
mCurrAttributeCode -> +0x34AC, speed -> +0x148, mpCLModel -> +0x254); reading the US-name
offset raw returns plausible-looking garbage, so validate any new field live before trusting a
probe built on it.

## The SHEATHED mint base silently blocks mint_online's baseline (session 67, GanonA)

55. **Minting from a base whose rest is sword-SHEATHED (equip 0x100, `sword_drawn` false):
    the pure-sim baseline roll can never fire a CUT** -- `solver.run(anchor, [])` presses B
    mid-roll with no `draw_at`, and the roll->CUT gate needs the sword out -- so `mint_online`
    reports `old=None` on EVERY iteration and can never accept ON-LINE (it correctly refuses
    the rest-perp fallback, ledger #42). This was the real cause of s65's "perp never
    converged" on GanonA (misread then as cam/settle trouble): spF_at_A hits 17.0, the roll
    runs (proc 0x1e), then exits to MOVE with no cut. Every previously delivered seam's base
    happened to rest DRAWN (0x103), so nine mints never exercised the path. The tell: baseline
    `old=None` while `spF_at_A == 17.0`. Fix is mint-time SETUP, not solver surgery (the
    sheathed `draw_at` path exists in `run`/`search` but is NOT threaded through
    `solve_focused`): one-time B-press draw in the base + steady-WAITS re-probe, saved as
    `ganona_r0_base_drawn@twwgz`; the re-mint accepted at iter 1 (|old perp| 1.783).
    First-class: `python -m harness.rollstab.mint drawbase=<sheathed_base> name=<base>_drawn`.
    Check `sword_drawn` in the base's minted seed BEFORE any mint_online loop.

## The "free-space auto-cam follow needs modeling" premise was FALSE (session 69, Phase A exp.5)

56. **Expansion 5 ("camera-in-the-loop") assumed a free-space behind-Link auto-camera FOLLOW
    that creeps csangle as Link walks, needing a per-frame model. Live RE DISPROVED it (for the
    MANUAL / no-L cam the approach uses).** SCOPE: this is the manual free-behind cam with no L
    pressed; the L-target / recenter AUTO cam (`lockonCamera` :3348, `getDMCAngle` :902) is a
    distinct mode that DOES move csangle and is not used by the roll-stab approach (pressing L
    would lock a target and rotate the camera) - do not generalize the frozen result to it.
    Walking Link from a settled idle in the OPEN flat arena (`land_flatwalk@twwgz`) with a centered
    C-stick (csx=128 -> `omega_cmd`=0, no L) left csangle (`mAngleY`) BIT-FROZEN across every config
    tried: straight walk 764->2027z, a full 90deg perpendicular turn, a big continuous arc
    (facing swept 532->21854 while csangle held), and a sustained main-stick-X=160 walk -- 5
    experiments, ZERO csangle motion. Decomp-grounded: `dCamera_c::Run` writes
    `mAngleY = mDirection.U().Inv()` (:905) and csangle == the horizontal `bearing(eye->center)`
    EXACTLY (verified live, diff 0); `followCamera`'s behind-follow (blend `m3B8` gated on
    `mStickMainPosXLast`, :3082-3089) updates the VIEW direction / center, not the controlled
    csangle the stick decode reads. So the sim's `CameraManual` (C-stick pan azimuth) is already
    FREE-SPACE-COMPLETE; there is nothing to add to the sim camera model. The ONLY thing that
    shifts csangle without a C-stick input is `bumpCheck` (:893, runs every frame just before the
    mAngleY write): the camera-arm WALL collision that pushes the eye LATERALLY. Per Dereck's
    steer that collision is NOT modeled -- it is DETECTED (`harness/rollstab/cam_clean.py`, the
    csangle-invariance probe: a centered-C-stick approach walk must hold csangle; any drift =
    bumpCheck contamination). Live-validated: open arena CLEAN (0 drift), GanonA straight-corridor
    DIRTY (+20 hw at f11, arm UNCHANGED at 483.2 -> the push is lateral, so arm-compression alone
    misses it and csangle-drift is the correct primary signal). The shipped GanonA clip's real
    approach walks the aim=186.5 line (not straight down-corridor), which the mint's cam screen
    kept clean (REST BIT-EXACT 30/30) -- so probe the INTENDED approach bearing, not just forward.
    Corollary: DMC mode (`mAngleY = getDMCAngle(mMainStickAngle)`, :902) drives csangle off the
    main stick, but it disengages for a normal walking approach (:897), so it does not affect the
    from-rest model.

## The s70 cam-clean gate dropped the smallest-settle-floored pick; a novel walk-stab needs the roll pipeline's from-rest machinery (session 71, in-situ shakeout)

57. **The session-70 `cam_clean` fold-in regressed dead-end #45 (fixed session 71).** s70 rewired
    `novel_deliver` stage 4 to "probe the DEFAULT aim target first, accept it if CLEAN, fall back to
    the alternates only if DIRTY, take the first CLEAN one." But the invariant CLEAN/DIRTY signal
    (`bumpCheck` arm-wall contamination) is ORTHOGONAL to the target's MEASURED SETTLE, and #45's
    rule is that the settle is per-(seam,target) leash geometry -- you must pick the frozen target
    whose settle-implied mint park (`d2s + settle`) stays ON the floor, smallest settle first. An
    in-situ shakeout on a FRESH kaze corner (seam_0352_0353, S=(9344.82,-373.61), interior 155.4)
    exposed it: the DEFAULT target 65503 screened CLEAN (max|drift|=0) but its settle 607 parked the
    mint at d2S 1187, past the floor edge (~1050) -> stage aborted, never trying alternates -- while
    CLEAN alternate 16351 (settle 253.6, park 833.6) fits the floor. s70 was only verified on
    kaze-157, where the default was BOTH clean and floored, so the gap hid. Fix (session 71): stage 4
    fast-paths the default when CLEAN *and* floored, else sweeps the #44 alternates and takes the
    SMALLEST-SETTLE clean+floored one (folds the floor re-probe into the selection); distinguishes
    "all CLEAN but off-floor" (467/#43-class floor-block) from "all DIRTY" (bumpCheck) in the abort.
    With it seam_0352_0353 minted ON-LINE (|old perp| 0.004) at 16351. Lesson: an invariant screen
    (CLEAN) is necessary but not sufficient -- a mint target must also FIT the floored corridor, and
    the #45 selection survives the s69/s70 invariant re-scope.

58. **A NOVEL walk-stab corner IS deliverable in principle but is blocked by INFRASTRUCTURE the
    walk-stab tier lacks -- a from-rest REST-bit-exact mint (cam-settle + rest_noops). NOT the seam,
    NOT wall-touch (my first-take "infeasible" was WRONG; Dereck corrected it, session 71).**
    seam_0352_0353's ROLL REST gate went RED at a corridor CC actor (ledger #52 class: a lateral
    bump-and-release ~35u at d2S ~366, csangle/facing frozen, no wall in the mesh); the steer was to
    move Link PAST the actor (rest d2S 210) and WALK-stab. I first concluded infeasible on a
    wall-touch argument -- WRONG on two counts:
    - **The corner clips at disp <= 40.2 (the walk cap lunge = speedF 17 + the 23.22 CUT_F root
      translate), so it is FEASIBLE.** 569 genuine `old`s exist; ~300 sit at d2S 36-40 with wall
      CLEARANCE > 35u (Link's ~35u WallCorrect radius) -- clearance is ~40u at d2S 41 and only drops
      below 35 at d2S < 36. A K=4 start-crawl + a grazing cruise (~3deg off bisector, cruise_off +540)
      found a ROBUST wall-faithful hit: `old` d2S 38, speedF **17.0 (full cap, NO wall brake)**, margin
      **24** (the session-32 delivered walk-stab was margin 5), genuine bit-confirmed offline.
    - **The wall-touch claim conflated two things:** "the cut RAY is CrrPos-blocked at most rho" (the
      razor -- true, it is dust) vs "the WALK touches the wall" (false -- the approach keeps ~40u
      clearance). A walk-stab does NOT need `old` at d2S ~35; d2S 36-41 clips with safe clearance.
    The real block to the LIVE clip: the FRESHLY-MINTED novel anchor is not REST-bit-exact. A
    per-frame sim-vs-live diff showed (a) a 1-frame walk-START delay (a `rest_noops` alignment
    offset) and (b) facing drifting ~300 s16 and growing (the mint used `settle_walk=0`, so the
    camera was never pre-settled/screened -- the sim holds csangle frozen but live's decode drifts),
    so `old` landed ~20u off and missed. This is exactly the machinery the ROLL pipeline has
    (`mint_online` cam-settle + `cam_clean` screen + the REST-BIT-EXACT gate) and the WALK-stab tier
    LACKS: `walkstab.py` is hardcoded to the one hand-crafted session-32 anchor with no novel-anchor
    mint/REST path. Delivering a novel walk-stab = build that (and a re-mint changes csangle, so the
    found hit must be re-solved on the settled anchor). The K=4 solver + close-anchor mint were done
    in scratch and reverted (proven-feasible, not yet a shippable tool). **LESSON: never call a seam
    infeasible from a search/mint failure -- if disp <= the technique's max lunge clips it (dust
    exists), it is feasible; the blocker is the SEARCH (lattice density) or the MINT (from-rest
    bit-exactness), both fixable.** Corridor-actor removal for a ROLL delivery (the #52 recipe) also
    remains open.

## The seam352 corridor is camera-CLEAN, and the walk-stab perp knob washes out at range (session 72)

59. **"seam352's corridor is bumpCheck-DIRTY for the walk-stab approach": FALSE -- a false alarm
    from a pan/settle transient, not a real collision.** The `cam_clean_screen` SETTLE walk drifted
    csangle ~2600-2900 hw, which I wrongly read as `bumpCheck` camera-wall contamination over the
    approach and escalated to "model the camera collision" (a ~1500-line dCamera_c + dBgS port,
    ruled out-of-scope by Dereck). A real from-rest approach probe settled it: teleport to d2S 200,
    camera behind Link, walk toward S with C-down -- **csangle moved a total of 11 hw over the whole
    approach and the arm CONVERGED monotonically 672 -> 514 (nominal) with ZERO pull-in.** A wall
    collision spikes/pushes the arm BELOW nominal; a clean convergence to nominal is the idle->walk
    arm settle, radial, csangle-neutral. The ~2900 settle drift was the pan/settle transient inside
    the screen tool, NOT the corridor. **The from-rest walk-stab walk is BIT-EXACT 28/28 (0-ULP) with
    the seam walls in the gate.** LESSON: confirm a "camera collision" from a REAL from-rest approach
    playback (arm length + csangle per frame), not from a pan/settle probe's transient -- and read the
    arm signature (converge-to-nominal = settle, spike/below-nominal = collision). The `cam_clean.py`
    arm-compression signal exists precisely to tell these apart; use it before concluding.

60. **The start-crawl perp knob WASHES OUT over a long walk, so a walk-stab rest that is far enough
    for runway can be too far to thread the razor with the crawl alone (session 72).** seam352's
    walk-stab from a d2S-200 rest (cut at N~16) is feasibility-confirmed (the shared
    `seam_feasibility` detector finds genuine walk-cap dust), and its from-rest model is bit-exact,
    but `solve_focused` finds 0 clips: on the bit-exact (seed=0, noops=2) trajectory the auto-graze
    floors the cut-ray |perp to S| at ~0.0016 (~16x the ~1e-4 f32 razor). Root cause, found by
    instrumenting the drill: the start-crawl (early partial-mag frames) perp perturbation DAMPS OUT
    over the ~16-frame walk, and the last-crawl byte NUDGE shifts `old` ALONG its own facing (same
    ray -> same perp), so it is an ALONG knob, not perp. Perp is set by the crawl AIM (a1/a2), which
    floors at 0.0016 here. The perp-0.000025 hits found at seed=1 are on a 1-frame-off
    (non-deliverable) trajectory -- a per-frame delivery diff proved live leads the seed=1 sim by 1
    frame; the anchor is bit-exact only at seed=0. Corollary (ledger seed rule): a freshly-minted
    (mint_walkstab/mint_current) anchor is REST-bit-exact at the seed giving noops=2 (rest_noops 1 ->
    seed=0); solve AND deliver must both use it. FIX (open, session-73 handoff): a finer
    WALK-reachable perp knob that does NOT wash out -- a mid-walk partial-magnitude dip near the cut
    frame, or the bearing-arc knob (a full-mag off-aim hold for a few frames near the cut) -- to
    thread the razor on the true trajectory. NOT a per-seam constant: the same knob family, searched.

## The session-72 "perp washout is physics" was a SEARCH-STRUCTURE bug (session 73, OVERTURNS the entry above)

The session-72 entry called the seam352 perp floor (~0.0016, ~16x the razor) a physics limit of the
start-crawl and proposed a "finer WALK-reachable perp knob" as the fix. That was WRONG. A dense
exact-genuine sweep of the SAME existing knobs (crawl aims a1/a2 x mags x the c4 byte) on the
deliverable seed=0 trajectory found genuine clips at |perp| 1.4e-4, INSIDE the razor. So the razor was
always reachable on the bit-exact trajectory; the solver just never tested those candidates.

Root cause (the dead-end #41 greedy trap, restated for walk-stab): `solve_focused` Phase A kept only the
top-16 brackets by a cheap CENTERED-c4 perp key, and Phase B `_refine_aim`-hill-descended a1/a2 to
MINIMIZE that cheap perp. The perp-minimum f32 cell is `gen=False` (CrrPos/in-front gating), and the
genuine dust sits one lattice cell over at slightly larger perp; minimizing the predictor steers you
straight off it. No new knob was needed. FIX: delete the hill-descent, drill c4 (breadth) at each
bracket's OWN aims, test the EXACT genuine_clip, consume brackets in cheap-perp order until want/budget.
seam352 -> 4 wall-faithful clips (margin 24); kaze -> margin 5 (unchanged); < 2 min. LESSON: a cheap
predictor is a PRE-FILTER, never an objective to minimize; the accept is always the exact test, and
greedy-on-the-predictor is the recurring trap (see #41). The perp-knob search proposed at s72 is moot.

## Forbidden delivery-diagnosis anti-patterns + the real seam352 live blocker is the WW-in-hand CUT (session 73)

The seam352 walk-stab delivers the WALK bit-exact (live `old`/facing/speedF match the sim 0-ULP through
the cut entry) but the live CUT_F lunges only ~6u to Link's RIGHT (then recovers, proc 0x5a) instead of
the sim's ~40u forward toward S (OOB, proc 0x24). The anchor holds the **Wind Waker in hand (equip
0x22)**; the single B puts it away then cuts, and the sim's `enter_cut` (which models a clean sword cut,
foot term = speedF, always 40u) does not match that WW-in-hand cut. This WW-in-hand cut was already
solved days ago; the fix is to find and apply that decomp-grounded handling, NOT to re-derive it.

RULED-OUT (Dereck's hard steers, [[decomp-first-not-brute-force]]/[[oneshot-no-manual-tweaking]]):
- **Sweeping b_frame (or any input) live to find what clips is FORBIDDEN.** "NEVER sweep. always ground
  in decomp." The cut behavior is in `d_a_player_sword.inc` (procCutF/changeCutProc) + `d_a_player_main.
  cpp` (checkNextActionFromButton / equip-anime completion); read it.
- **Re-minting the anchor sword-drawn (the ganona `mint.draw_base` trick) to dodge the WW is FORBIDDEN.**
  It changes the GIVEN initial state, which is the opposite of the objective ("you MUST use the initial
  state given to you"). The draw-base tier is for the ROLL pipeline's own bases, not a delivery fix here.
- Not the drawn/undrawn foot set: `enter_cut` ignores it (all sim paths give 40u). Not the aim (0.2deg
  off facing = CUT_F, not a side dispatch). Not b_frame timing per se (the cut fired at N from the
  bit-exact `old`). The divergence is intrinsic to the WW-in-hand cut, still to be modeled from decomp.

## The s73 "WW-in-hand CUT" diagnosis was WRONG; seam352 is blocked by a ~1-ULP cut-endpoint gap (session 74, LIVE, OVERTURNS #62)

s73 concluded the seam352 live blocker was "the Wind-Waker-in-hand CUT lunging weakly / firing CUT_REVERSE,
a mechanic to model in fast_cut/enter_cut." Session 74 live-refuted every part of that:

- **The CUT_F fires FINE at the bit-exact `old`** (facing 64946, speedF 17.0, all == sim 0-ULP). The
  CUT_REVERSE (proc 0x5A, `changeCutReverseProc` d_a_player_sword.inc:469) is a DOWNSTREAM symptom: the
  forward lunge gets CrrPos-wall-blocked, then the sword tip strikes the wall and bounces. There is no
  "weak WW cut" to model. Do not chase a WW-specific cut lunge.
- **The collision model is CORRECT and the 40.22 clip is REAL.** A clean position-sweep from the exact
  `old` to the sim's `new` CLIPS LIVE (Link reaches `new`, world Y drops below the floor, state -> 39
  fall/OOB). `genuine_clip`/`crr_pos_walls` is faithful here (a mid-s74 "collision false-positive" idea
  was also wrong). Oracle: teleport to `old` (settle), writename link_x/link_z = `new`, advance, read
  link_y/link_state (clip = y drops + state 39; block = y holds + state 4, slid along the wall). It is
  razor-discriminating (exact clips, +0.001u blocks).
- **The walk is 0-ULP** (movie-playback bit-diff: live `old` bits == sim bits every frame, N=11..16).
- **So the ONLY error is a ~1-ULP gap in `enter_cut`'s CUT_F endpoint.** It is fatal only because
  seam352's sharp corner (interior 155) has a ~1-ULP ACCEPTANCE RAZOR: the sim's `new` sits on a clip
  cell, the live cut lands ~1 ULP over (at x=9344 one f32 ULP is ~0.00098u), so it blocks. kaze walk-stab
  delivered because its near-flat 169 corner has a DENSE acceptance (walk-stab.md: "hundreds of clipping
  f32 `new` in a small box") that swallows any sub-ULP gap. **Lesson: 0-ULP is not optional; a razor seam
  makes a latent sub-ULP model gap fatal, and the gap was invisible on every dense-acceptance seam before.**
- **Likely source (unconfirmed):** the roll-stab `enter_cut` is 0-ULP because it dispatches from a FRESH
  state (the spotcheck seeds `state=FRONT_ROLL` directly). The walk-stab cut fires after a 16-frame walk,
  so the game carries a decaying foot-engine residual (`m3598` / posMoveFromFootPos toe-stream) into the
  CUT init-frame position that `enter_cut` zeroes ("no foot pose, m3598==0"). Confirm by capturing the
  live RAW pre-collision cut endpoint (movie-faithful playback + `bp 0x800a39a8`, read pm_pos
  deref(0x803AD860)+0x120 before CrrPos) and diffing bits vs `enter_cut`.

## The walk-stab cut foot-term uses `travel`, not `facing`: WRONG (session 74, LIVE-refuted, REVERTED)

Tempting fix for the above: since `procCutF_init` (d_a_player_sword.inc:660) does not reset
`current.angle.y` (only `procCutF` frame 2+, :744, does `current.angle.y = shape_angle.y`), the init-frame
FOOT-TERM should lunge along the CARRIED walk `travel`, not `facing` -- and at seam352 the walk left
travel != facing by 115 s16. It was decomp-plausible and offline-safe (425 green; roll/kaze byte-identical
since their travel==facing). **But LIVE-REFUTED:** the game snaps travel to facing on the cut frame and the
foot-term uses FACING. Proof: the facing-based endpoint clean-sweeps to the block basin (9351.86,-407.895)
BYTE-IDENTICAL to the live delivery block, while the travel-based endpoint was a clip cell the game never
reached. `enter_cut`/`_cut_init` keeping `travel = facing` is CORRECT; the change was reverted. Do not
re-open the travel/facing split. (Also ruled out this session: driving the delivery with `advancewith` to
reach the cut frame with a breakpoint armed -- it DESYNCS the buffered-B walk, ~4.6u off; the faithful
walk is only reproducible via the DTM MOVIE.)

## The s74 "~1-ULP cut-endpoint gap" and the #64 travel refutation: BOTH overturned by direct RAM capture (session 75, DELIVERED)

Session 75 captured the live RAW (pre-collision) CUT_F endpoint at posMove stage boundaries (JP bps:
posMove entry/blr, posMoveFromFootPos entry/blr, positionWallCorrect) on a movie-faithful playback.
The direct measurement overturned both of s74's inferences and delivered the seam352 clip:

- **The gap was NOT ~1 ULP -- it was ~0.026u**, and it is a MODEL bug, not a sub-ULP foot residual:
  the buffered-B walk-stab cut dispatches AFTER procMove's `setSpeedAndAngleNormal` runs that frame
  (procMove 6221 -> checkNextMode 4424 -> checkNextActionFromButton), so the entry foot term fires
  along the JUST-CHASED `current.angle.y` (travel), while the m3700 delta rotates by shape/facing.
  RAM proof: at the cut-frame positionWallCorrect, `speed == 17*dir(travel')` exactly (travel'=64961,
  one more -100 chase step past the old-frame 65061; facing 64946). The m3598 residual hypothesis was
  wrong (m3598 is force-zeroed by commonProcInit; the BP read 0), and sp8C was genuinely Zero.
- **Dead-end #64's "the foot-term uses facing" refutation was itself wrong**: s74's travel fix used
  the OLD-frame travel (65061, no chase step), whose endpoint indeed never matched -- the CONCEPT
  (foot term along carried travel) was right, the VALUE was one chase step stale. The block-basin
  endpoint match that "proved" facing was a coincidence of the basin swallowing the difference.
  `procCutF_init` does NOT write current.angle.y (only procCutF frame 2+ snaps it) -- as #64's decomp
  reading already said.
- **Why every earlier delivery hid it:** the roll-stab dispatch has travel==facing (`_roll_init`
  6837), and the kaze walk-stab cruise had converged travel==facing by its cut frame (verified for
  all four kaze goldens) -- byte-identical under both models. seam352's start-crawl left a 115-hw
  residue that ~16 frames of chase had not converged, and its razor acceptance made the resulting
  0.026u phantom fatal. **Lesson: a "verified 0-ULP" sub-model is only verified FOR THE DISPATCH
  CONTEXTS exercised; a new context (walk-dispatched cut with unconverged travel) needs its own raw
  capture, and endpoint basin-matching is NOT a substitute for reading the mid-frame RAM.**
- Also useful: between posMove's output and positionWallCorrect, CrrPos's line-clip already pulls a
  blocked lunge back (~3.57u here) -- the "raw" pos read at the wallCorrect BP is NOT posMove's
  output. Capture at the posMove blr (JP 0x80106DF4) for the true unblocked endpoint.

Fix shipped: `_cut_init` no longer snaps travel; `LandState.enter_cut_from_move` runs the dispatch
prefix; the solver/fast paths thread the dispatch-frame travel. Locked by
`tests/test_seam352_walkstab.py::test_seam352_rawcut_dispatch_frame_bitexact` (fixture
`fixtures/seam352_rawcut_golden.json`) + the delivered-clip gate (the 11th seam, margin-24 hit,
oracle-vetted CLIP/BLOCK at exact/+0.001u).

## Pointers

- Current pipeline + run protocol + verification: `harness/rollstab/README.md`.
- Methodology (why the region is dust, why calibration was added): [strategy/seam-clip-solver.md](../strategy/seam-clip-solver.md).
- Collision / clip mechanism: [mechanics/collision.md](../mechanics/collision.md).
- The SOLVED fast-exact sim-search pattern to reuse: `tww_sim/land/plan_land/_freeze/roll.py`
  (cheap monotone predictor + prune + bit-confirm, no table, no calibration).
