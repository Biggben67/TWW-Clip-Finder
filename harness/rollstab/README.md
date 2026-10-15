# harness/rollstab - the roll-stab seam-clip solver (kaze r11 sandbox)

Plan a roll-stab (FRONT_ROLL -> single-B-edge CUT_F) that clips through the 110-degree seam at
kaze room 11 S=(9069.9043, 259.1986), and deliver it as a clean DTM. Standing instructions:
`SESSION_PROMPT.md`; current state: `## Status` below; narrative history:
`_notes/seam-clip-live-validation-handoff-*.md` (sessions 7-10).

## The problem shape (read this before touching knobs)

- The acceptance set is f32 DUST, not a window: `genuine_clip` (CrrPos not blocked + old in
  front of both wall planes + new behind) flickers at ULP scale along the roll ray. Slivers are
  0.0005-0.01u wide in the perp/x direction, ~10-30% dense over a 0.5-3u along-band, and are
  STRIPED per f32 x-column. Never target a fitted ribbon; always test the exact candidate
  (`geometry.pred_genuine` == the real cut, verified bit-identical to the sim's `new`).
- The roll only carries the full 49.2202 lunge from a capped walk: speedF MUST be 17.0 at the A
  press (gated everywhere).
- old_z must sit in ~[302.6, 308.2]: below, the roll is wall-blocked short; above, the lunge
  cannot reach behind the planes.

## The model: bit-exact FROM REST -- pure sim, no calibration

`rest.rest_state(anchor)` seeds a sim that matches live 0-ULP from row 0 through walk entry,
cruise, bearing arcs, partial-magnitude dips, and the roll, taking ONLY the anchor's seed json
as input (the objective's no-calibration requirement; the old K0 live-calibration crutch is
deleted). The terms that made it exact (each decomp-grounded, found by per-frame live diffing):

1. **The WAIT(4) rest blend** (`foot_speedf.seed_rest_blend`): the anchor rests in
   setMoveAnime(WAITS, WALK, r29=2) with BOTH frame ctrls live; procWait RE-INITS the blend every
   idle frame (`setBlendMoveAnime(-1.0f)` -> the f31 frame ROUND-TRIP `frame/60*60`, not an f32
   identity, and fc1 re-derived `f31*32`). Seeded from the seed json's `rest_*` fields plus the
   STORED delayed foot poses (mFootData 018/00C) -- those carry the pre-mint position's rounding
   noise, which re-posing at a translated position cannot reproduce (this was session 9's
   mysterious ~1e-4 translated-anchor residual).
2. **2 alignment no-ops** (`REST_NOOPS`): a savestate-anchored run_dtm movie's first two rows
   exist only for row alignment -- the game has not run yet (live d_frame holds the rest value
   through them).
3. **The draw happens at frame END** (deferred-draw mode): setWorldMatrix builds the pose base at
   the POST-integration position (d_a_player_main.cpp:11551), not the pre-step one the sim used
   to pose at. Invisible at cruise (m3598=0 hides the toe stream) and at small coords (the
   flat-arena suite), fatal on dip frames at kaze magnitudes.
4. **Link's world Y is in the base** (y=-6534 here): the m37B4 inverse's cancellation rounding is
   magnitude-dependent in every axis.
5. **The MOVE turn lean** (`LandState._set_move_slant_angle`, setMoveSlantAngle 9499):
   shape_angle.z = m351C>>1 tilts the base via ZXYrotM's z concat; m351C chases
   1.6*(m34DE - shape.y)*speed-factor while walking near cap, decays 35%/frame otherwise. The
   draw uses the PREVIOUS frame's lean (setWorldMatrix runs before setMoveSlantAngle).
6. **dtm_make's stick calibration** (`rest.dtm_stick`): every authored DTM delivers 255 as 254
   and 0 as 1, so plans are built FROM the delivered bytes. The un-calibrated (73,255) arc stick
   decoded 60 treads off and cost a 0.3u live miss -- the stick DECODE itself (PADClamp octagon +
   JUT CStick) matches the decomp exactly.

## The pipeline

1. **Mint** (`mint.py`): PAUSE FIRST, load the base anchor, auto-capture the `rest_*` seed fields
   (frame ctrls, m359C/m35B4, stored foot poses t2 + t1-via-one-paused-advance), re-load, write
   link_x/z += delta, save. Letting the game run between load and save desyncs the anchor (cost
   the idle4..idle11 chain).
2. **Verify** (`rest.py` CLI, 1 live DTM run per NEW anchor -- verification only, never in the
   solve loop): play the verification stream, log the anim fields per frame, then the offline
   from-rest diff. Must print **REST BIT-EXACT** (pos + d/w frame ctrls + m359C, every row)
   before the anchor's hits are trusted.
3. **Solve** (`solver.py`, offline): knobs = bearing ARCS (gross lateral shift), 1-frame
   partial-magnitude FINES, A_proj (17u z grid), and the **START CRAWL** -- the 1D-approach
   micro-moves: K<=3 partial-magnitude sticks (msd 0.52..0.889, aimed at F) in the first rows
   while speed is LOW, each shifting the downstream trajectory along-track by a fine quantum.
   Exact acceptance per run. `search(anchor, do_drill=True)` runs catalog + start-crawl sweep +
   iterative-deepening drill; hits -> `_generated/rollstab_hits.json`.
4. **Gate + deliver** (`deliver.py`): 0-ULP literal-stream from-rest replay gate (+ a +-2e-4
   sliver z-margin robustness check), then the clean DTM with a 120-frame watch-tail, per-frame
   live confirmation. NEVER advancewith.

**One-shot for a NOVEL screened corner: `novel_deliver.py`** (session 61) chains the whole recipe
-- geo -> band_dense re-check -> park-floor probe -> cam-target screen -> `mint_online` -> the
REST gate (abort on DIFF; auto-writes the rest golden) -> dust2d prebuild -> `solve_focused`
(+ the documented knob-family retries on a 0-hit draw) -> `deliver ship` (auto-writes the ship
golden) -> the per-seam test scaffold -- aborting at the first RED stage, with per-seam resume
state in `_generated/novel_<name>.json` (`start=`/`stop=` re-enter at any stage):

    python -m harness.rollstab.novel_deliver wallA=<pid> wallB=<pid> name=seam<pid>

**The Tetra push-aside clip has its own shipped pipeline: `pushaside.py`** (`mint` / `deliver` / `diff`
/ `search`). Read its docstring before ANY Tetra-clip delivery work -- it encodes the four delivery
truths (walkable Tetra floor; NEUTRAL roll stick; B one step later in the DTM than in the sim; seed the
sim at the DTM's REAL roll entry) which are NOT re-derivable from the sim alone and which each cost a
live run in session 22. When live disagrees with the sim, run `pushaside diff` (per-frame, BOTH actors)
-- never guess inputs.


## Status (2026-08-20)

> SINGLE SOURCE OF TRUTH for current seam-clip state. A pre-commit gate blocks any commit that
> changes `harness/rollstab/*.py` without touching this file, so keep it current. `SESSION_PROMPT.md`
> points here for state rather than restating it. The session-by-session log that used to live in
> this section is in [README-archive.md](README-archive.md); the ruled-out ledger is
> [knowledge/history/seam-clip-dead-ends.md](../../knowledge/history/seam-clip-dead-ends.md).

**This is the active thread.** The repo was split on 2026-08-20: a one-off Courtyard Tetra-push
route planner had been the only thing worked on for ~170 sessions, and it now lives on branch
`dmiller/courtyard-tetra-push` (forked at `c516cc3`). Generalizing *this* solver is the work again.

### Shipped: clips delivered live, 0-ULP, and gated offline

Each row is a seam whose clip was planned entirely in the sim from a static anchor and then
reproduced through a clean DTM, bit-for-bit. The gate replays the shipped plan against a recorded
golden, so it needs no Dolphin.

| Room | Seam | Tier | Gate |
|------|------|------|------|
| kaze r11 | seam152, seam152m | roll-stab | `tests/test_seam152_clip.py`, `test_seam152m_clip.py` |
| kaze r11 | seam157 | roll-stab | `tests/test_seam157_clip.py` |
| kaze r11 | seam824 | roll-stab | `tests/test_seam824_clip.py` |
| kaze r11 | seam915 | roll-stab | `tests/test_seam915_clip.py` |
| kaze r11 | mirror | roll-stab, sheathed | `tests/test_mirror_roll_clip.py`, `test_sheathed_roll_clip.py` |
| kaze r11 | seam352 | **walk-stab** | `tests/test_seam352_walkstab.py` |
| kaze r11 | (walk-stab anchor) | walk-stab | `tests/test_walkstab_clip.py` |
| Hyrule (flooded) | Tetra corner | roll-stab + CC push | `tests/test_pushaside_clip.py`, `test_turnaround_clip.py`, `test_tetra_clip.py` |
| Hyroom r0 | cseam4002 | roll-stab | `tests/test_cseam4002_clip.py` |
| GanonA r0 | seam255 | roll-stab, sloped ground | `tests/test_ganona_rest.py` |

Four rooms, both cut tiers, and the two Tetra deliveries (push-aside and the follow-enabled
turnaround). `python -m pytest` runs all of it.

### Open

- **Three lotteries, all `xfail` and all the same shape: dust too thin, not a model gap.** seam97,
  seam97m and hseam2709 have REST-bit-exact anchors and verified-genuine dust; the per-draw hit
  expectation is just below 1 inside the 2-minute budget. They go green when a draw lands. Do not
  re-diagnose them as broken.
- **Mid-run stop then re-walk is not bit-exact.** A full stop to WAIT and a MOVE re-entry diverges on
  the re-walk entry `speedF` (the WAIT row itself matches). From-rest entries are exact, so avoid a
  full stop inside a plan until this is modelled.
- **The Phase-W wall pass has no AABB cull.** The stepper iterates all 765 ordered walls, ~33 ms/frame
  pure-Python; far polys already no-op, so a block-grid cull is pure speed and would bring a
  multi-wall corner inside the solver budget.
- **The native driver no longer computes the `setMoveSlantAngle` turn lean.** Its only caller was the
  Courtyard step that the split removed. `m351C` is public for a caller to set, and the Python path in
  `tww_sim/land/state.py` models it. Wiring it into the general native step is a behaviour change that
  wants live re-validation, not a port.
- The `idle2`/`idle12` seed jsons predate the `rest_*` schema; re-mint with `mint.capture_rest` before
  solving off them.

### Closed since the last status
- **The live rolling GUI no longer treats geometric dust as a prepared setup.** It density-ranks exact f32 facings near the physical approach corridor, mints a neutral 580-unit runway, measures and centers the actual full-speed slash onto an exact witness, and checks ranked candidates until three physical runways have been searched. A result is emitted only after a live-recaptured exact replay passes ordered walls and `wall_faithful`; an obstructed runway is skipped instead of consuming the solver budget.
- **The live GUI exports candidate movies without controlling playback.** For each simulation hit it writes one complete seed-0 DTM, a matching `.dtm.sav` prepared state, and the `.dtm.sav.dtm` companion. It neither restarts Dolphin nor plays the movie. The editable six-character DTM game ID defaults to `GZLJ01`; manual playback is the confirmation gate because a simulator hit is not reported as live-proved.
- **The exact-facing screen is persistent.** `_generated/live_slash_facing_cache.json` stores geometry-only f32 witness lists keyed by seam, camera, speed, and aim. Repeated or overlapping angle-range scans reuse those entries; prepared runways, trajectory searches, and wall gates remain fresh.
- **Critical-health anchors are modeled.** Life `<= 6` routes WAIT through the mode-0 WAITATOB single before settling into the mode-2 WAITB/WALK blend at rate 0.4. The live finder captures and seeds either phase, including its delayed toe stream, instead of assuming the healthy rest pose.
- **Exact collision screening is native in the portable bundle.** `_collc.cp312-win_amd64.pyd` accelerates the unchanged collision predicates. The Edaichi exact-facing screen dropped from roughly 51 seconds per facing to roughly 2 seconds per facing before parallelism.

- **The late-FRONT_ROLL drawn-pose gap is FIXED.** It was the standing RED gap -- 1-122 ULP against
  live on ship rows 32-36, carried as a strict xfail since 2026-07-10 and blamed on an unmodelled
  `jointBeforeCB` body lean. It was the quaternion sign extension plus the `FrameCtrl` frame being
  kept in double. `tests/test_rollstab_rest.py::test_rest_roll_pose_bitexact` is green, so the roll
  pose is 0-ULP end to end and a post-roll WALK can no longer consume a stale toe stream.
- **The CC push distance was wrong in a way that mattered.** `dist²` is not fused: the binary computes
  two `fmuls` and an `fadds`, and the root is `__frsqrte` plus three double Newton steps, not a
  correctly-rounded `sqrtf`. The fused form biased the push ~3e-6 u/frame and the plow amplifier
  turned that into a 113 u miss.

### Next

The standing queue, unchanged by the split: ROADMAP exp5(b) (the fast-move camera auto-flip
envelope) and exp5(c) (arbitrary starting csangle), then exp6 (arbitrary mid-walk entry states). Also
worth a pass now that the walk-stab tier generalizes: re-screen the seams the locator flagged
budget-capped "unknown", since a 25-corner obtuse sample at 15x resolved 10 of them as genuine clips.

Related: `knowledge/strategy/seam-clip-solver.md` (methodology), `ROADMAP.md` (the phase plan),
`tests/dolphin/spotcheck_rollstab.py` (cut 0-ULP), `tests/dolphin/spotcheck_swordwalk.py` (DASHS toe).
