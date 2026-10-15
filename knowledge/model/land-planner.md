# The land input planner — target (x,z) → input sequence

**Answers:** What is the land planner's goal? How does `plan_land.py` reach a target (straight walk,
proportional glide, the C-up freeze)? What is the live-valid stick set? How close can it stop, and
what are the current gaps (curve residual, pillar collision)? What are the two use-case accuracy bars
(seam clips vs RTA setups)?
**Status:** milestone 1 — straight-walk reach bit-exact live; `reach_freeze` deterministic C-up-cancel
stop now **robustly float-perfect AND live-re-gated 0 ULP** (2026-07-05) — freezes byte-for-byte at the
sim's `freeze_pos.z` for every reachable on-axis target, and within a few float32 ULP (< 0.001u) of ANY
on-axis target offline (all-live-valid), not just lucky ones. Sweeps are O(n) via bit-exact mid-walk
clone. The C-up freeze + B-cancel + re-walk is now **input-driven in `step()`** (raw stream, 0 ULP live;
2026-07-05f) — a freeze plan is just an input sequence. The **fewest-frame bit-exact stop is the START
crawl** (2026-07-05h): fine-tune the from-rest accel frames (free low-speed fine grid), then cruise full
+ C-up — bit-exact ~+7 over the full-up floor, live-proven 0 ULP (supersedes chained/end-crawl for fewest
frames). **Productionised (2026-07-05i) as `reach_freeze(min_frames=True)`** with a δ-prediction filter
(~3× solve, NOT sub-second — floored by per-leaf pose sim; see below) + offline & live gates. The
**fewest-frame stop overall is the ROLL approach** (2026-07-05j): chained forward rolls (26 u/frame) rest
**~15–30 frames BELOW the walk floor**, and — because a roll RESETS the walk anim (fc0→0) — the freeze is
**analytically solvable** (`freeze = freeze_ref(nr,r) + δ`, sub-second lookup), unblocking the walk's
precession wall. Productionised as **`reach_freeze(roll=True)`**, live 0-ULP; see the ROLL section below. The **density fix
is done (2026-07-05k)**: the **`roll_speed_min` knob** admits partial-speed tuning rolls that let hard
exact-float targets hit at a **shallower start crawl** (k=5→k=3, ~57s→~2s, live 0-ULP) — trading a few
frames for solve speed; partial-speed rolls are now live-gated. Open: off-axis octagon clamp; collision;
A*. The chained-over-streams planner is done (modest ~1–3f). (Note:
`reach_straight`/`reach_precise` rest are target-SENSITIVE, 0.1–9u — use `reach_freeze` for exact stops.)
**Source:** `tww_sim/land/plan_land/`; live-validated via `advanceseq`. Forward model:
[land sim](land-sim.md) · [land movement](../mechanics/land-movement.md).

---

Where the [swim planner](planner.md) optimizes 1-D distance, the land planner's objective is a **2-D
position**: initial `LandState` + world target (x, z) → an input sequence that arrives there. Two use
cases set very different accuracy bars:

- **A. Seam clips (primary, knife-edge).** A clip is a boolean — the swept A→B segment threads a
  sub-ULP sliver between two triangle planes. You can't re-plan a mispredicted boolean, so **bit-exact
  position AND FMA-faithful collision are on the critical path**. Needs the approach movement
  (bit-exact) plus a collision predicate (`cM3d_CalcPla` + segment-vs-triangle, `fmadds`-faithful,
  seam triangles dumped from RAM) — the predicate is **unbuilt**; walking-position-exactness is the
  [FP proving ground](fp-faithfulness.md) for it.
- **B. RTA setup finder (robust/discrete).** Search discrete, human-executable action lattices for
  faster setups that *reliably* hit a position; score by **basin width** (timing slop tolerated),
  fastest-among-robust. Same forward model + predicate, evaluated over a perturbation neighborhood.

## Milestone 1 — straight-walk reach (`plan_land.py`)

- `world_angle_s16(dx, dz)` — travel bearing (s16, 0 = +z, 0x4000 = +x) matching
  `pos_x += d·sin(travel); pos_z += d·cos(travel)`.
- `stick_for_bearing(theta_s16, csangle, msd)` — inverse stick for the walk want-target
  `m34E8 = m34DC + csangle` (`m34DC = stickAngle + 0x8000`), adding the 15-unit dead zone back per
  axis. **Live-faithfulness rule:** for `msd ≥ 1` emit the TRUE full corner (r = 112 → 255/1); for a
  partial use the dead-zoned magnitude `msd·54`; **never** the ambiguous near-cap band (see the
  live-valid set below).
- `reach_straight(seed, tx, tz)` — aim full stick at the LIVE bearing each frame; sweep the release
  frame for minimum **resting** distance and stop at the FIRST local min (past it the re-aim orbits
  back through turn procs). Bit-exact live, but the rest is **target-SENSITIVE** (0.1–9u): the 17u
  full-speed step + fixed ~49u neutral coast lands rest on a coarse lattice.
- `reach_precise(seed, tx, tz, k=0.5)` — proportional-speed glide (target speed = `k·remaining`)
  staying IN MOTION, then truncation-search the tail cut. Also **target-sensitive** (0.1–9u): the
  proportional decel LAGS, so it overshoots-at-speed on short trips and stalls to a dead stop on long
  ones. For an exact stop use `reach_freeze`. (Older docs claimed a uniform "0.10u smooth-walk floor";
  overturned — [history](../history/land-planner-precision.md).)
- `reach_freeze(seed, tx, tz)` — the **robustly float-perfect** approach via the C-up speed cancel
  (below): within a few ULP of any on-axis target.

All three sweep by **cloning a snapshot** at each candidate release/cut/cancel frame rather than
re-simulating the walk prefix — bit-exact because `LandState.clone()` is faithful **mid-walk** (it
state-copies the anim engine's toe stream + oldframe-morf, not a fresh rest rebuild). That turns the
O(n²) release sweeps O(n) (`reach_precise` to a far target: 246k → 4k `step` calls). See
[FP faithfulness](fp-faithfulness.md#cython-fast-path).

**Straight walk (0, 2000): bit-exact** (sim-vs-live Δ = 0.0003u). The milestone-1 core is real.

## Live-valid stick magnitudes

`_set_stick_data` uses `msd = min(hypot(deadzone)/54, 1)`, which **caps**; live PADClamp saturates
differently near the cap. So `Y ≤ 191` (msd ≤ 0.889) is bit-exact and `(128,255)` (true full) is
exact, but **`Y ∈ [192,254]` diverges live** (a walk at `(128,196)` gives sim v=16.38 vs live 15.76).
**Any land search over partials must restrict to `Y ≤ 191 ∪ {255}`; never emit 192–254.** From a
standstill the walk needs `msd > 0.5` to move (`(128,171)` is the smallest that cruises); the L-target
`ATN_MOVE` unlocks lower speeds (`Y=168` → 3.64). Detail: [land movement](../reference/constants.md#land-movement).

## Float-perfect stop — the C-up speed cancel

Natural walk-stop coasts a quasi-fixed decel arc and floors at ~0.019u; float-exact resting is
unreachable that way. The **C-up speed cancel** freezes mid-motion instead: while walking, half-press
L for one frame (ends manual cam), then neutral stick + C-stick full up → after 2 latency frames + 1
decel frame the speed snaps to 0 and position locks. The sim reproduces the freeze with **zero new
code** — `frozen_pos = walk-sim pos 3 frames after the neutral+C-up input` (`plan_land._freeze_pos`).

`reach_freeze` is the **deterministic offline planner** for this, in **three phases** (each
O(1)-per-candidate on the bit-exact mid-walk clone):

1. **Cruise** full-speed until the freeze lands within `coarse_gap` (60u) of the target.
2. **Sustained msd-0.5 crawl** (stick `(128,170)`, the min STABLE crawl — nspeed≈4.25 → ~1u/frame),
   snapshotting each frame until the freeze crosses the target. This is the key to robustness: it
   guarantees a **uniform ~1u fine straddle for ANY target**. The freeze coast scales with approach
   speed, so you must **arrive SLOW to arrive fine** — a proportional glide overshoots-at-speed on
   short trips and stalls on long ones, which is why the old glide-based drill was float-perfect only
   at lucky targets.
3. **Dedup-by-freeze-position beam drill** from a few crawl frames before the crossing: branch over
   `NEUTRAL ∪ {live-valid integer walk sticks}` (`msd ≤ 0.889 ∪ {1.0}`, aimed at the live bearing),
   keeping a frontier deduped by quantized freeze position and capped to those nearest the target.
   This fills the ~1u crawl step down to the float floor.

On the open **+z corridor** the production beam rests within **~1–4 float32 ULP (< 0.001u)** with an
**all-live-valid** seq. That residual is **NOT sim error** — the sim reproduces live `pos_z` at **0 ULP**
([land-sim](land-sim.md), gated no-tolerance by `run_land_tests`), so an offline *exact* freeze lands
exactly live (**confirmed 2026-07-05** by driving whole plans in Dolphin: `pos_z` froze byte-for-byte at
the sim's `freeze_pos.z` for z = 1500 / 2000 / 2500, `pos_x` = 0).

**Exact-float (0-ULP) freeze IS reachable, live-proven** (the production robust beam's ~1–4 ULP was the
beam under-exploring the tail, not a lattice floor). The exact solvers are now productionised — the
fewest-frame **START crawl** (`min_frames=True`) and the **ROLL** approach (`roll=True`, below) — and
since the sim is 0-ULP vs live, an offline-exact solve lands exact on console (verified: `2000.0` /
`1800.0`, `pos_x`=0). **Off-axis freeze plans are not yet live-valid** — an off-axis crawl emits diagonal
sticks needing the octagon clamp (a separate open decode issue). Mechanics of the cancel:
[land movement](../mechanics/precise-stop.md).

## Fewest-frame bit-exact stop — the START crawl (2026-07-05h)

The **cheapest** bit-exact freeze is not a slow approach (reach_freeze rests ~+19..32 over the full-up
floor) nor a chained coarse+fine (below, ~+12): it is to do the ULP fine-tuning at the **START**, then
run full speed to the target. Bit-exact needs a few LOW-SPEED frames (the freeze grid is only ULP-dense
below the 17u speed cap — see next paragraph); at the *start* the from-rest acceleration frames are
low-speed **for free**, so you spend nothing extra:

1. **k fine start frames from rest** — the natural accel ramp, magnitudes slightly reduced (live-valid
   Y∈[171,191]∪{255}). At low speed each frame's freeze step is fine; k=3–4 of them fill to the ULP (the
   same momentum-diversity that fills the drill's last ULP, but at zero frame cost).
2. **full-forward cruise** (exactly +17.000/frame), half-L on the last frame;
3. **C-up cancel** → the freeze locks on the **exact** float — the start offset shifted the whole
   full-speed lattice onto the target.

**Bit-exact at a consistent ~+7 over the full-up floor** (z=2000 → 80f/+7.3; z=1500 → 50f/+6.7;
z=2810.99 → 128f/+7.6), and **live-proven 0-ULP** (z=2000/1500/2500 froze byte-for-byte at the sim's
`freeze_pos.z` in Dolphin — `spotcheck_freeze.py --min`). The plan is a raw stream (the freeze is
input-driven in `step()`).

**Productionised (2026-07-05i): `reach_freeze(seed, tx, tz, min_frames=True)`** — requires the seed AT
REST, on-axis/+z corridor; returns the same plan dict (0-ULP freeze, all sticks live-valid) and falls
back to the robust phases if no exact hit up to `kmax`. Offline gate
`test_reach_freeze_min_frames_bit_exact_and_fewer`; live gate `spotcheck_freeze.py --min`.

**Solve speed — δ-prediction filter (~3×, NOT sub-second for WALK).** Once nspeed hits the 17u cap every
start seq cruises **+17.000 pos/frame and +2.300 `anim_fc0`/frame** (exposed on `LandState.anim_fc0`), and
the freeze coast is a function of `anim_fc0` (±0.3u, from one reference cruise) — so a candidate's freeze is
predictable from (pos, fc0) at the cap frame; predictions outside ±0.5u skip the exact cruise (z=2000
4.7→1.7s, identical start seqs). But it's a **filter, not O(1)**: an arbitrary-ULP target needs ~10⁵
distinct start seqs to cover δ, each needing a pose sim. **Walk sub-second is blocked** because the ~7-frame
walk anim **precesses** (never bit-exactly repeats), so the coast can't be memoised on a low-dim key. **The
ROLL approach RESOLVES this** — a roll resets the anim (fc0→0), making the coast a reusable table → analytic
solve (ROLL section below). Prototypes: `_notes/chained-freeze-probes/`.

**Why full-speed windows can't hit bit-exact (settled, measured):** at the 17u cap momentum is pinned
(1 slid frame → 0.0177u; exhaustive 3-frame window 274,625 combos → 0 hits; smallest live-valid stick step
drops speed ≥3.5u). Bit-exact **requires sub-cap momentum** — the start crawl / drill provide it.

## Fewest-frame freeze via a ROLL approach — AND the analytic solve (2026-07-05j)

`reach_freeze(seed, tx, tz, roll=True)` (`_reach_freeze_roll`): from-rest start crawl (free fine grid) →
full cruise → **chained forward rolls** (26 u/frame) → short walk tail → C-up. Two wins:

- **~15–30 fewer frames.** Rolls cover **~25.6 vs 17 u/frame**, so the freeze rests **13–23 frames BELOW
  the full-up walk floor** `(z−764.08)/17`: z=2000 → 60f (walk 79), z=2500 → 79f (109), z=2810.98 → 97f
  (~127). A chained roll = **+486.5u / 19 frames** (first roll off cruise 476.0); the freeze fires only
  from a post-roll MOVE frame (A/C-up don't arm mid-roll). Roll mechanics + the retain-26 window +
  intermediate speeds: [land movement](../mechanics/roll.md).
- **ANALYTIC solve — unblocks the walk's precession wall (above).** A roll **resets the walk anim** (the
  roll→MOVE exit re-inits the walk frame ctrl to 0, since `setSingleMoveAnime` left `m34C3==0`) → post-roll
  `anim_fc0==0`, so everything downstream is **history-independent**: fixed +486.5u/roll, a FIXED walk-tail
  coast table, and the start-crawl offset **δ carries through the roll EXACTLY**. Hence
  **freeze(nr, r, start) = freeze_ref(nr, r) + δ(start)** — a closed-form lookup with a REUSABLE δ memo
  (impossible for the walk: its coast rode the *precessing* fc0). Prototype table k=4 → 111k δ (~75s once)
  then ~5–12 ms/target; productionised as a **per-call guided DFS** (no table): exact per-leaf δ → predict
  → bit-confirm the matching (nr, r). Solve k=3 ~1s, k=4 ~16–21s (≈ walk `min_frames`); unlucky exact
  targets need k=5 (slow).

**LIVE 0-ULP (2026-07-05j):** plans freeze byte-for-byte at the sim's `freeze_pos` (`spotcheck_roll_freeze.py`:
z=2000/2222.2/2345.678, all 0 ULP, held stable). **Seed from the LIVE anchor** — the default `LandState`
rounds pos_z to 764.079 vs the anchor's 764.0791015625 (2 ULP); a seed mismatch shifts the freeze 1 ULP
(root-caused: the sim is 0-ULP vs live when seeded right — a seed bug, not sim error). Gates:
`test_reach_freeze_roll_bit_exact_and_beats_floor` + `spotcheck_roll_freeze.py`. `seq` frames are
`(sx, sy, buttons)` 3-tuples (A=0x100 on roll press frames). On-axis / +z only.

### The partial-tuning-roll densifier — `roll_speed_min` (2026-07-05k)

The full-only grid (all 26-rolls + tail) is **sparse** (~17u tail steps), so a hard exact-float target
needs a **deep (k=5) start crawl** to bridge the residual — a slow (~57s) DFS. The
**`reach_freeze(roll=True, roll_speed_min=<float>)`** knob (default 26.0 = full-only) fixes this: lower it
to admit **partial-speed tuning rolls** (mNormalSpeed in `[roll_speed_min, 26]`, via a pre-roll partial
FORWARD hold — [land movement](../mechanics/roll.md))
as the last roll. Each covers a distinct distance → extra coarse-grid points → the target hits at a
**shallower k** (fast solve). Every roll resets the walk anim (`anim_fc0 == 0`), so the tuning roll is just
extra `freeze_ref` rows and the prediction stays exact.

**It trades frames for solve-speed** (the user's dial): a partial roll is slower than 26, so the
fewest-frame stop is **always all-full-rolls** (settled) — the densifier doesn't cut frames, it makes a
**lower-k** solution *exist* at a few extra frames. Search per k: fewest-frame **full** config first
(first-hit, fast); only if none, fewest-frame **tuning** config (config-first over enumerated leaves);
return the first k with a hit. Use a **small `kmax`** (≈3). Live-proven 0 ULP: the k=5-hard **z=2000 → k=3
in ~2s, 72f** (vs ~60f k=5 full-only), z=1900/2345.678 too — **partial-speed rolls are now live-gated**.
Gate: `test_reach_freeze_roll_densifier_lowers_k` + `spotcheck_roll_freeze.py rmin=…`. **Open:** off-axis.
Prototypes: `_notes/roll-freeze-probes/`.

## Roadmap: chained coarse+fine freeze (B-cancel) — fewest frames (TAS)

The **B-cancel chained freeze** (coarse-freeze from full speed → B-cancel → re-walk from rest → fine-freeze
on the exact float) is fully **MODELED, input-driven, and live-proven 0 ULP** (2026-07-05f): the former
blocker (post-B-cancel re-walk inheriting the freeze foot-anim phase) is the `m34C3 = 2`
phase-preservation of the subjectivity/WAIT blend, and `LandState.step()` now consumes the raw controller
stream so a plan plays 1:1 on sim + Dolphin (gate `spotcheck_subj_inputdriven.py`; details in
[land movement](../mechanics/precise-stop.md)).
**But the measured savings are modest — only ~1–3 frames** vs a good single freeze (z=2000 → 86f vs 89;
prototype `chained_solve`), since the exact-float stop is intrinsically ~12–17 frames over the full-up
floor either way. **Remaining (low priority):** redo the chained PLANNER search over real input streams
(cruise × B-cancel timing × re-walk × fine-cancel; objective = frames over floor excluding lock frames);
if the win stays ~1–3 frames it may not be worth productionising into `plan_land.py`.

## Open gaps

- **Curved-walk chase residual (sub-2u).** A sustained gentle-curve walk (~15° heading over ~1900u)
  drifts 0.5–1.6u — the walk facing/travel chase (`cLib_addCalcAngleS`) in a continuously-turning
  MOVE, a regime the [land tests](land-sim.md#enforced-to-the-byte-by-three-gates) don't stress (walk is
  dead-straight; turn tests are big reversals). NOT the camera (csangle stays 0). Fine for flavor B
  (unit-scale basins); must be closed before flavor-A clip planning.
- **Wall/pillar collision (unported).** A diagonal target that crosses a pillar mispredicts by ~36u.
  v1 targets OPEN GROUND only. Because the sim has NO collision, a plan can silently target past a
  wall: on the `land_flatwalk` anchor the +z corridor ends at a **wall at `pos_z ≈ 2932.4294`
  (`0x453746df`)** — a plan for z ≥ 3000 freezes AT the wall, not the requested z (live-observed
  2026-07-05). Keep on-axis targets in `(764.08, 2932.43)` on this anchor. Collision is the flavor-A
  centerpiece (see above).

## Roadmap

Land A* mirroring the [swim planner](planner.md) machinery (sig/dominance/`_hcost`) over a 2-D target
+ steerable facing (reusing `plan.py`/`optimize.py`); flavor B (basin-scored reach) first, flavor A
(clip predicate) after the collision core and the curve residual are closed.

## See also

- [Land sim](land-sim.md) · [Land movement](../mechanics/land-movement.md) ·
  [Swim planner](planner.md) · [FP faithfulness](fp-faithfulness.md) (collision on-ramp).
