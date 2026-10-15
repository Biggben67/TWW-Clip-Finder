# harness/rollstab - the session archive

The reverse-chronological session log that used to live in `README.md`'s `## Status` section: 41
`PRIOR THREAD` blocks plus the Phase 0/W/G/C/T records, sessions 10 to 75. It was 2270 of the
README's 2357 lines, which made the front door unreadable.

It is kept because it is the reasoning behind decisions the code no longer explains. It is NOT the
current state -- `README.md` `## Status` is, and where the two disagree the README is right. The
durable lessons are in `knowledge/history/seam-clip-dead-ends.md`.

---

## Status (2026-07-20, session 75)

> SINGLE SOURCE OF TRUTH for current seam-clip state. A pre-commit gate blocks any commit
> that changes `harness/rollstab/*.py` without touching this file, so keep it current.
> The session prompt (`SESSION_PROMPT.md`) points here for state rather than restating it.

> **CURRENT THREAD (2026-07-20, session 75): the seam352 walk-stab clip is DELIVERED LIVE 0-ULP --
> the ELEVENTH seam -- by root-causing and fixing the walk->cut DISPATCH-FRAME model. s74's "~1-ULP
> cut-endpoint gap" framing is OVERTURNED: the gap was ~0.026u, a model bug, found by capturing the
> live RAW CUT_F endpoint at posMove stage boundaries (movie-faithful playback + JP breakpoints, the
> s74 handoff's recipe).**
> - **The mechanic (RAM-verified, decomp-grounded):** the buffered-B cut dispatches INSIDE procMove
>   AFTER `setSpeedAndAngleNormal` runs that frame (6221 -> checkNextMode 4424 ->
>   checkNextActionFromButton), and `procCutF_init` never writes `current.angle.y` -- so the entry
>   foot term (speedF 17) fires along the JUST-CHASED travel (64961 here, one -100 step past the
>   old-frame 65061) while the m3700 delta rotates by shape/facing (64946). The sim's `_cut_init`
>   snapped travel=facing first, a 0.026u phantom on this razor corner. m3598 IS 0 on the cut frame
>   (commonProcInit force-zeroes it) -- the s74 foot-residual hypothesis was wrong; and dead-end #64's
>   "foot-term uses facing" was wrong too (s74 tested the STALE old-frame travel; ledger s75 entry).
> - **The fix (sim + solver, all decomp-grounded, no tuned constants):** `_cut_init` no longer snaps
>   travel; new `LandState.enter_cut_from_move(sx, sy, ...)` runs the dispatch-frame procMove prefix
>   (input-delay pop, stick decode, setSpeedAndAngleNormal, mMaxNormalSpeed) then the entry lunge;
>   `SeamGeo.cut_new`/`walkstab.fast_cut` take the dispatch `travel`; the solver's fast paths read it
>   off the walking state one frame later (zero extra cost), `_wall_faithful` runs the exact dispatch.
>   Roll paths are provably byte-identical (`_roll_init` sets travel=facing) and all four kaze
>   walk-stab goldens have converged travel==facing -- suite green unchanged, every shipped hit
>   recomposes.
> - **The delivery:** corrected-model `solve_focused` -> 1 wall-faithful hit (margin 24, N=16,
>   `old=(9346.9970703125,-410.4026184082031)` -> `new=(9344.6201171875,-370.25262451171875)`,
>   speedF 17.0), oracle-vetted (exact new CLIPS live, +0.001u BLOCKS), then `walkstab.deliver`:
>   **live CUT_F@f16, old/new bit-for-bit the sim, genuine, OOB** (proc 0x24, y through the floor).
> - **Locked live-data-backed:** golden `tests/golden/walkstab_seam352_deliver.json` (the ship) +
>   fixture `fixtures/seam352_rawcut_golden.json` (the raw dispatch-frame capture: sp8C=0, m3598=0,
>   travel'=64961, speed bits bf7035aa/4187caed, raw new 461202c4/c3b980f3). Gates
>   `tests/test_seam352_walkstab.py`: `test_seam352_rawcut_dispatch_frame_bitexact` NEW GREEN,
>   `test_seam352_clip_delivered` FLIPPED GREEN (xfail removed). Suite **427 passed, 1 skipped,
>   5 xfailed** (+2 / -1 xfail). KB: `mechanics/walk-stab.md` (the two-angle lunge) + the ledger s75
>   entry. Every other thread UNCHANGED (ten prior seams recompose, Tetra STANDALONE, lotteries).
>
> **NEXT (session 76): the standing queue -- ROADMAP exp5(b) (the fast-move camera auto-flip
> envelope) / exp5(c) (arbitrary starting csangle) + exp6 (arbitrary mid-walk entry states), the s64
> leftovers re-scope-or-drop, and the 97m/hseam2709 lotteries. Also worth a pass: re-screen the
> budget-capped "unknown" seams ([[seam-scanner-budget-optimization]]) now that the walk-stab tier
> is razor-correct -- corners the phantom model failed may now solve.**

> **PRIOR THREAD (2026-07-20, session 74): s73's "Wind-Waker-in-hand CUT" diagnosis is OVERTURNED --
> the WW cut fires FINE, the collision model is CORRECT, the 40.22 clip is REAL (live-verified), and the
> walk is 0-ULP. seam352's ONLY blocker is a ~1-ULP gap in the sim's `enter_cut` CUT_F endpoint, fatal
> because this sharp corner (interior 155) is a ~1-ULP ACCEPTANCE RAZOR (kaze walk-stab delivered only
> because its near-flat 169 corner has a DENSE acceptance that tolerates a sub-ULP gap). No code shipped;
> my travel-fix attempt was WRONG and is reverted.**
> - **What was live-verified (via a new clean-sweep collision oracle, see the handoff):**
>   (1) the live CUT_F fires at the bit-exact `old` (facing 64946, speedF 17.0 == sim 0-ULP); the
>   CUT_REVERSE (0x5A) is a DOWNSTREAM symptom (the forward lunge wall-blocks, then the sword strikes the
>   wall, `changeCutReverseProc`), NOT a weak WW cut. (2) A clean position-sweep `old -> sim_new` CLIPS
>   LIVE (y drops below the floor, state 39 OOB) -- the collision `genuine_clip` is faithful; the s72/mid-
>   s74 "collision false-positive" idea is WRONG. (3) The walk delivers `old` 0-ULP (live bits == sim every
>   frame). So the ~1-ULP error is entirely in the CUT endpoint.
> - **The game uses `travel == facing` for the cut foot-term** (confirmed live: the facing-based endpoint
>   reproduces the live block bit-for-bit; a travel-based endpoint was a clip cell the game never used).
>   `enter_cut`/`_cut_init` keeping `travel = facing` is CORRECT. The "foot-term uses the walk's travel"
>   fix is RULED OUT (dead-end #64).
> - **The likely gap (to confirm next):** the roll-stab `enter_cut` is 0-ULP because it dispatches from a
>   FRESH state; the walk-stab cut fires after a 16-frame walk, so the game carries a decaying foot-engine
>   residual (`m3598` / posMoveFromFootPos toe-stream) into the CUT init-frame position that `enter_cut`
>   zeroes ("no foot pose"). At x=9344 that residual is ~1 ULP.
> - **Locked live-data-backed (UNCHANGED, valid):** anchor `kaze_r11_walkstab_seam352@twwgz` + golden
>   `fixtures/seam352_rest_golden.json` (REST BIT-EXACT) + geo. Gate `tests/test_seam352_walkstab.py`:
>   `test_seam352_rest_bitexact` GREEN, `test_seam352_clip_delivered` strict-xfail. Suite unchanged
>   (only `harness/dtm/run_dtm.py` gained a `travel_angle` log field; sim/solver reverted pristine). Every
>   other thread UNCHANGED (ten delivered roll seams, kaze walk-stab DENSE, Tetra STANDALONE, lotteries).
> - KB dead-ends #63 (s73 WW-cut misdiagnosis) + #64 (the travel!=facing foot-term fix ruled out).
>
> **NEXT (session 75): make `enter_cut`'s CUT_F endpoint 0-ULP for the walk-stab case, then deliver.**
> Capture the LIVE RAW (pre-collision) cut endpoint via a MOVIE-faithful playback (advancewith desyncs the
> buffered-B walk) halted by `bp 0x800a39a8` (positionWallCorrect, JP), reading Link's pm_pos
> (deref 0x803AD860 + 0x120) before CrrPos corrects it; diff its bits vs `enter_cut`'s `new`. Model the
> missing transition-frame foot term in `enter_cut` (decomp-grounded, must keep the roll-stab spotcheck
> 0-ULP), re-solve, deliver. See the session-74 handoff for the exact recipe. HARD RULES: 0-ULP is
> mandatory (not a tolerance), ground in decomp, never sweep, never alter the anchor.

> **PRIOR THREAD (2026-07-20, session 73): the s72 seam352 "perp-resolution gap" was a SEARCH-
> STRUCTURE bug, not physics -- `solve_focused` now finds seam352 walk-stab clips OFFLINE (top perp
> margin 24, well inside the razor). The LIVE clip is still NOT delivered: it is blocked on the
> Wind-Waker-in-hand CUT (a mechanic already solved days ago that walk-stab's solve/deliver do not
> yet apply), and the next session must GROUND THAT IN DECOMP -- do NOT sweep, do NOT alter the
> anchor (Dereck's hard steers, [[decomp-first-not-brute-force]]/[[oneshot-no-manual-tweaking]]).**
> - **The fix (`solve_focused`, `walkstab.py`):** the s72 handoff blamed a physics "perp washout"
>   (auto-graze floored perp at 0.0016 ~= 16x the razor). WRONG. A dense exact-genuine sweep of the
>   SAME knobs on the deliverable seed=0 trajectory found genuine clips at |perp| 1.4e-4 (inside the
>   razor). The old solver missed them because Phase A kept only the top-16 brackets by a cheap
>   centered-perp key and Phase B **hill-descended a1/a2 to the perp-MINIMUM** -- which lands on the
>   `gen=False` perp-min f32 cell and steers OFF the genuine dust one lattice cell over (the dead-end
>   #41 greedy trap, now #61). Replaced the hill-descent with a **BREADTH exact-genuine c4-drill at
>   each bracket's OWN aims**, consuming brackets in cheap-perp order until `want`/budget; `_refine_aim`
>   deleted. Self-adaptive, no per-seam args. seam352 -> **4 wall-faithful clips, top margin 24,
>   speedF 17.0**; kaze -> margin 5 (unchanged); both in the 110s budget. Suite **425 passed, 1
>   skipped, 6 xfailed** (unchanged -- `test_seam352_clip_delivered` stays strict-xfail until the live
>   clip ships).
> - **The LIVE blocker (handed off, NOT the perp problem):** a clean-DTM delivery got the WALK
>   BIT-EXACT frame-by-frame (`old`, facing 64946, speedF 17 at the cut all match the sim 0-ULP), but
>   the live CUT_F lunged only ~6u to Link's RIGHT (then recovered, proc 0x5a) instead of the sim's
>   ~40u forward toward S (which would go OOB, proc 0x24). Same old/facing/speedF/aim (aim 0.2deg off
>   facing = CUT_F, not a side dispatch), and the drawn/undrawn foot set does NOT change `enter_cut`
>   (all sim paths give 40u). The anchor holds the **Wind Waker in hand (equip 0x22)**; the walk-stab's
>   single B puts it away then cuts, and that WW-in-hand cut is where the sim and live diverge. Dereck:
>   this was **solved days ago** -- find the existing decomp-grounded handling and apply it in
>   walkstab's solve+`fast_cut`/`enter_cut` so the modeled cut matches the real WW-in-hand cut. Do NOT
>   sweep b_frame; do NOT re-mint the anchor sword-drawn (that changes the given initial state, which
>   violates the objective). KB dead-ends #61 (greedy trap overturns the s72 "perp washout") + #62 (the
>   forbidden delivery-diagnosis anti-patterns).
> - **Locked live-data-backed:** anchor `kaze_r11_walkstab_seam352@twwgz` + golden
>   `fixtures/seam352_rest_golden.json` (REST BIT-EXACT, unchanged) + geo. Gate
>   `tests/test_seam352_walkstab.py`: `test_seam352_rest_bitexact` GREEN, `test_seam352_clip_delivered`
>   strict-xfail (flips when the clip ships). NO behavior change to `sim.py`/`land.py`/`deliver`/
>   `mint_online`/any shipped roll seam (only `solve_focused` search structure), so the live regression
>   and every shipped-hit recomposition are unaffected. Every other thread UNCHANGED (ten delivered roll
>   seams, kaze walk-stab, Tetra STANDALONE, 97m/hseam2709 lotteries, 467/163 blocked).
>
> **NEXT (session 74): deliver the seam352 walk-stab clip by GROUNDING THE WIND-WAKER-IN-HAND CUT IN
> DECOMP.** The offline solver already produces margin-24 hits; the walk is bit-exact; only the modeled
> CUT disagrees with the live WW-in-hand cut. Find the existing (days-ago) WW-in-hand cut handling, read
> `d_a_player_sword.inc` (procCutF / changeCutProc) + `d_a_player_main.cpp` (checkNextActionFromButton /
> equip-anime completion) for why the real cut lunges as it does from a WW-in-hand walk, model it in
> `fast_cut`/`enter_cut` so the solver searches the ACTUAL deliverable cut, re-solve, deliver. HARD
> RULES: ground in decomp (never sweep b_frame/inputs), never alter the given anchor. Then ROADMAP
> exp5(b)/(c)+exp6 and the lotteries.

> **PRIOR THREAD (2026-07-20, session 72): the WALK-stab tier is GENERALIZED to a novel anchor
> and made SELF-ADAPTIVE (Dereck's steer: one-shot from any viable corner, NO per-seam manual
> tweaking -- [[oneshot-no-manual-tweaking]]). The tooling ships regression-clean; the seam352 live
> clip is NOT yet delivered (a solver perp-resolution gap on the bit-exact trajectory, handed off).**
> - **`walkstab.configure(anchor, geo, name)` retargets the tier to ANY seam** (was hardcoded to the
>   one session-32 kaze anchor); the kaze default is byte-identical (23 offline gates green). New
>   novel-anchor machinery, all decomp/live-grounded: **`mint.mint_walkstab`** (a sub-580u pan mint,
>   parked directly, NO settle-walk -- a live probe showed the cam is behind Link after the pan, and
>   the long settle-walk OVERSHOT + curved off-line) with a **`check_runway` GUARD** (simulates the
>   from-rest walk and ABORTS if speedF does not cap before the cut zone -- a self-detect so a
>   too-close mint never wastes a live run); a **walls-aware REST gate** (`rest.main`/`verify_rest`
>   auto-thread the seam walls when a geo is given, byte-identical for far roll anchors -- a
>   short-corridor walk that SLIDES the seam wall no longer reads as a false DIVERGE); and a
>   **per-anchor `DTM_SEED`** (configure derives it: legacy kaze seed=1, a freshly-minted novel anchor
>   seed=0 -- the seed the anchor is REST-bit-exact at; a mismatch delivered the walk 1 frame off, the
>   old past the razor -- found by a per-frame delivery diff, not a guess).
> - **`solve_focused` is now self-adaptive (no per-seam args):** a FEASIBILITY pre-check via the
>   SHARED detector (`seam_feasibility.best_walk_aim`, the same `SeamGeo.pred_genuine` acceptance the
>   CSV dump uses -- enhanced with a `wall_clearance` filter + `SeamGeo.wall_clearance`, per Dereck's
>   DRY steer, NOT a re-implementation) confirms genuine walk-cap dust exists; then an AUTO-GRAZE
>   (1D-minimize the cut-ray |perp to S| over the walk aim -- replaces the hand-found `cruise_off`
>   sign/magnitude) + perp/along auto-decompose (crawl aim = perp, last-crawl byte nudge = along at
>   fixed facing) + auto k in {3,4}. It still delivers the kaze hit (margin 5, d2S 36).
> - **seam352 is minted (d2S 200, on-line, REST BIT-EXACT 28/28 with walls), feasibility-confirmed,
>   but NOT delivered.** The camera was a FALSE alarm (no collision; the arm converges to nominal and
>   csangle holds -- the earlier "dirty corridor" was a pan/settle transient). The real blocker: on
>   the bit-exact (seed=0) trajectory the auto-graze floors the cut-ray perp at ~0.0016 (~16x the
>   ~1e-4 razor) -- the start-crawl perp perturbation washes out over the ~16-frame walk, and the
>   along nudge does not touch perp. The seed=1 perp-0.000025 hits are on a 1-frame-off
>   (non-deliverable) trajectory. Needs a finer WALK-reachable perp knob on the true trajectory (a
>   mid-walk partial-mag dip near the cut, or the bearing-arc knob) -- the handoff's Next step.
> - **Locked live-data-backed:** anchor `kaze_r11_walkstab_seam352@twwgz` (minted, seed tracked) +
>   golden `fixtures/seam352_rest_golden.json` (REST BIT-EXACT, walls-aware) + geo
>   `fixtures/kaze_r11_seam352_geo.json` (regenerable). Gate `tests/test_seam352_walkstab.py`:
>   `test_seam352_rest_bitexact` GREEN, `test_seam352_clip_delivered` strict-xfail (flips when the
>   clip ships). Suite **425 passed, 1 skipped, 6 xfailed** (+1 pass +1 xfail). NO behavior change to
>   the kaze walk-stab delivery, `solver.py`, `deliver.py`, `mint_online`, or any shipped roll seam
>   (all recompose). KB: dead-ends #59 (camera false-alarm) / #60 (perp washout at range). Every
>   other thread UNCHANGED (ten delivered roll seams, kaze walk-stab, Tetra STANDALONE,
>   97m/hseam2709 lotteries, 467/163 blocked).
>
> **NEXT (session 73): deliver the seam352 walk-stab clip -- add a finer WALK-reachable perp knob to
> `solve_focused`'s steering (a mid-walk partial-magnitude dip near the cut frame, or the bearing-arc
> knob) that shifts perp WITHOUT the start-crawl washout, thread the ~1e-4 razor on the seed=0
> trajectory, and deliver via the (now seed-correct) `walkstab.deliver`. The anchor + REST golden +
> feasibility are ready. Then the standing ROADMAP exp5(b)/(c)+exp6 and the lotteries.**

> **PRIOR THREAD (2026-07-20, session 71): an in-situ shakeout ran the s70 `cam_clean` gate
> END-TO-END on a FRESH kaze corner for the first time -- and it exposed + fixed a REGRESSION the
> s70 rewrite introduced (ledger #57). The corner did not deliver (a corridor CC actor + the
> walk-stab tier boundary), but the cam-gate fix is the session's verified deliverable.**
> - **The regression (ledger #57):** s70 rewired `novel_deliver` stage 4 to "accept the DEFAULT aim
>   target if CLEAN, fall back to alternates only if DIRTY, take the first CLEAN one" -- which
>   DROPPED the session-61 / dead-end-#45 rule (pick the frozen target whose MEASURED settle parks
>   the mint ON the floor, smallest settle first). CLEAN/DIRTY (the `bumpCheck` invariant) is
>   ORTHOGONAL to settle magnitude: on `seam_0352_0353` (S=(9344.82,-373.61), interior 155.4) the
>   default target 65503 screened CLEAN (max|drift|=0) but its settle 607 parked the mint at d2S
>   1187, past the floor edge (~1050) -- stage aborted, never trying alternates -- while CLEAN
>   alternate 16351 (settle 253.6, park 833.6) fits. s70 was only verified on kaze-157 (default
>   both CLEAN and floored), so the gap hid.
> - **The fix (`novel_deliver` stage 4):** fast-path the default when CLEAN *and* floored; else
>   sweep the #44 alternates and take the SMALLEST-SETTLE clean+floored one (the floor re-probe is
>   folded into the selection loop). The abort now distinguishes "all CLEAN but off-floor"
>   (467/#43-class floor-block) from "all DIRTY" (bumpCheck). With it the cam gate auto-selected
>   16351 and the corner minted **ON-LINE (|old perp| 0.004)** -- the s70 gate is now shaken out
>   in situ.
> - **The corner did NOT deliver, for two reasons unrelated to the cam gate:** (a) the ROLL REST
>   gate went RED at a corridor CC actor (ledger #52 class -- a lateral bump-and-release ~35u at
>   d2S ~366, csangle/facing frozen, no wall in the mesh there); (b) the steer was to move Link PAST
>   the actor and WALK-stab from there. That is FEASIBLE (ledger #58) -- disp <= 40.2 clips this
>   corner (569 genuine `old`s; ~300 at d2S 36-40 with wall clearance > 35u, no touch), and a K=4
>   start-crawl + grazing cruise found a ROBUST wall-faithful hit (`old` d2S 38, speedF 17.0 full
>   cap, margin 24) offline. (My first-take "infeasible/wall-touch" call was WRONG -- Dereck
>   corrected it; the walk keeps ~40u clearance, and I had conflated the CUT-ray razor with a walk
>   wall-touch.) The LIVE clip missed only because the FRESHLY-MINTED novel anchor is not
>   REST-bit-exact: a per-frame diff showed a 1-frame walk-start delay (`rest_noops`) + ~300 s16
>   facing drift (the `settle_walk=0` mint never settled/screened the camera). Delivering a novel
>   walk-stab needs the machinery the ROLL pipeline has (`mint_online` cam-settle + `cam_clean`
>   screen + the REST-BIT-EXACT gate) and the walk-stab tier LACKS (`walkstab.py` is hardcoded to the
>   one session-32 anchor) -- that is the real open work. The K=4 solver + close-anchor mint were
>   done in scratch and reverted (proven-feasible, not yet a shippable tool).
> - **Locked deliverable:** the cam-gate #45 fix in `harness/rollstab/novel_deliver.py`, verified in
>   situ. NO `sim.py`/`land.py`/`solver.py`/`mint_online`/`deliver`/`walkstab.py` behavior change
>   (`walkstab.py` is PRISTINE), so the live regression and every shipped-hit recomposition are
>   unaffected. Suite **424 passed, 1 skipped, 5 xfailed** (unchanged). KB: dead-ends #57/#58. Every
>   seam thread UNCHANGED (ten delivered seams, walk-stab, Tetra STANDALONE, 97m/hseam2709
>   lotteries, 467/163 blocked). `seam_0352_0353` is a NEW OPEN target: deliverable as a WALK-stab
>   once the walk-stab tier gets a novel-anchor REST-bit-exact mint, or as a ROLL if the corridor CC
>   actor is removed (the #52 recipe).
>
> **NEXT (session 72): the remaining exp5 items -- (b) the auto-flip envelope (the fast-move camera
> FLIP, distinct from the follow) and (c) whether an arbitrary state's starting csangle offset needs
> handling beyond being a sim input -- then exp6 (arbitrary mid-walk entry states). A fresh
> `novel_deliver` run now exercises the FIXED cam gate (smallest-settle floored pick) end-to-end.
> The s64 leftovers re-scope-or-drop and the 97m/hseam2709 lotteries still stand.**

> **PRIOR THREAD (2026-07-20, session 70): the s69 `cam_clean` detector is FOLDED INTO the mint
> pipeline -- the camera is now screened by the csangle-INVARIANT probe (ROADMAP Phase A exp.5
> item (a) DONE), replacing the empirical `cam_screen` trial-pan hunt.**
> - **New `mint.cam_clean_screen(geo, target_csangle=None, ...)`:** at a candidate park it replicates
>   the mint's pre-mint teleport-park + C-stick pan to `target_csangle` (default = the aim F) + settle,
>   then walks `n=40` frames DOWN the seam bearing with a **FIXED stick** (computed ONCE from the
>   frozen csangle -- re-aiming each frame, `cam_screen`'s flaw, chases a drift and confounds the
>   signal) and a **centered horizontal C-stick**, and scores csangle drift + arm pull-in via
>   `cam_clean.evaluate`. CLEAN => the corridor keeps the camera arm off walls, so the park+csangle is
>   mintable and the from-rest constant-csangle model stays bit-exact; DIRTY => `first_drift` names the
>   frame/pos where `bumpCheck` first pushes the arm. Shares `_park_pan_settle`/`_aim_line` with
>   `cam_screen` (now demoted to a legacy diagnostic) so both park the cam identically.
> - **`novel_deliver` stage 4 rewired (ledger #56 replaces the #44 trial-pan gate):** probe the
>   DEFAULT aim target FIRST (not a 5-way sweep); accept it if CLEAN; fall back to the same #44
>   alternates (F +-8000/+-16384) only if the default corridor is DIRTY, taking the first CLEAN one;
>   abort with the default's first-drift frame/pos if every csangle is DIRTY. Measured settle
>   (park - rest_d2S) + the ledger-#43 floor re-probe are unchanged.
> - **Live-verified the invariant holds for the C-DOWN approach the delivery actually walks** (s69 used
>   a centered `csy=128`; the pipeline walks `csy=0`): a kaze walk creeps then recovers to the EXACT
>   start csangle -- C-down is azimuth-neutral, only `bumpCheck` moves csangle transiently. And the
>   screen ran LIVE on the delivered kaze-r11 157 corridor: **CLEAN, max|drift|=0 hw, arm 514.4->514.4
>   (0% pull-in), rest_d2S 703.8**.
> - **Locked live-data-backed:** golden `fixtures/cam_clean_kaze157_screen_golden.json` (the live
>   park-screen capture, arm-inclusive) + offline gate `tests/test_cam_clean.py::
>   test_park_screen_kaze157_clean`. Suite **424 passed, 1 skipped, 5 xfailed** (+1). NO
>   `sim.py`/`land.py`/`solver.py`/`mint_online`/`deliver` behavior change (camera SCREEN + a
>   mechanical `cam_screen` helper extraction only), so the live regression and every shipped-hit
>   recomposition are unaffected. Every seam thread UNCHANGED (ten delivered seams, walk-stab, Tetra
>   STANDALONE, 97m/hseam2709 lotteries, 467/163 blocked).
>
> **NEXT (session 71): the remaining exp5 items -- (b) the auto-flip envelope (the fast-move camera
> FLIP, distinct from the follow) and (c) whether an arbitrary state's starting csangle offset needs
> handling beyond being a sim input -- then exp6 (arbitrary mid-walk entry states). The s64 leftovers
> re-scope-or-drop and the 97m/hseam2709 lotteries still stand. A end-to-end `novel_deliver` run on a
> fresh corner would exercise the new cam gate in situ (the 157 was screened, not re-delivered).**

> **PRIOR THREAD (2026-07-20, session 69): ROADMAP Phase A expansion 5 ("camera-in-the-loop")
> is RE-SCOPED by live RE -- there is NO free-space auto-camera follow to model, and a live
> camera-wall-collision DETECTOR is delivered (Dereck's steer: detect collision, don't model it).**
> - **The premise was FALSE (dead-end #56), for the MANUAL / no-L cam the approach uses.** SCOPE:
>   this is the manual free-behind cam with no L pressed; the L-target / recenter AUTO cam
>   (`lockonCamera`, `getDMCAngle` :902) is a DISTINCT mode that DOES move csangle and is not used
>   by the roll-stab approach (L would lock a target and rotate the camera) -- not generalized here.
>   Walking Link in the open flat arena with a centered C-stick (`csx=128` -> `omega_cmd` 0, no L)
>   leaves csangle (`mAngleY`) BIT-FROZEN across every config
>   tried: straight walk, a full 90deg turn, a big continuous arc (facing swept 532->21854 while
>   csangle held), a sustained main-stick-X=160 walk -- 5 live experiments, ZERO csangle motion.
>   Decomp confirms it: `dCamera_c::Run` sets `mAngleY = mDirection.U().Inv()` (:905) and csangle
>   == the horizontal `bearing(eye->center)` EXACTLY (verified live, diff 0); `followCamera`'s
>   behind-follow (blend `m3B8` gated on `mStickMainPosXLast`, :3082) moves the VIEW direction, not
>   the controlled csangle the stick decode reads. **So the sim's `CameraManual` is already
>   free-space-complete; nothing is added to the sim camera model.**
> - **The only csangle contamination is `bumpCheck` camera-WALL collision (:893, every frame just
>   before the mAngleY write): a LATERAL eye push in tight corridors.** Live-demonstrated: a GanonA
>   straight-corridor walk creeps csangle +20 hw at f11 while the arm length is UNCHANGED (so the
>   push is lateral -> csangle-drift is the primary signal, arm-compression only secondary). This
>   is what the mint's pan/settle/corridor machinery has always been avoiding -- keeping the arm
>   off walls -- NOT fighting a follow.
> - **Detector delivered: `harness/rollstab/cam_clean.py`** (`probe`/`evaluate`, CLI). Invariant:
>   under a centered C-stick csangle is provably constant, so any drift during a probe walk along
>   the INTENDED approach bearing = bumpCheck contamination. Reads csangle + the eye/center arm off
>   the csangle pointer chain (mCenter@inst+0x10, mEye@inst+0x1C; csangle == bearing(eye->center)
>   verified live). Live-validated: open arena CLEAN (0 drift), GanonA straight DIRTY (+20@f11).
>   The next-step wiring is to fold it into `novel_deliver`/`mint` as the principled replacement for
>   the empirical `cam_screen` frozen-target hunt.
> - **Locked live-data-backed:** goldens `fixtures/cam_clean_open_golden.json` (csangle frozen every
>   frame = the invariant) + `fixtures/cam_clean_ganona_straight_golden.json` (+20@f11 = DIRTY),
>   both live captures; offline gate `tests/test_cam_clean.py` (3 tests) GREEN. Suite **423 passed,
>   1 skipped, 5 xfailed** (+3). KB: `knowledge/mechanics/camera.md` (the no-follow finding + the
>   detector), ROADMAP Phase A step 5 re-scoped, dead-end #56. NO `sim.py`/`land.py`/`solver.py`
>   change, so the live regression and all shipped-hit recompositions are unaffected. Every seam
>   thread UNCHANGED (ten delivered seams, walk-stab, Tetra STANDALONE, 97m/hseam2709 lotteries,
>   467/163 blocked).
> - **GOTCHA hit this session: `savestate loadfile <path>` (path load) can silently no-op on a
>   long-running Dolphin instance while `savestate load <slot>` still works** (loads ACK `ok:true`
>   but state is unchanged; deterministic, not a clearing race). It worked for ~6 loads then wedged.
>   The goldens were built from the live per-frame CSVs already captured before it wedged. Recover
>   with a slot load or a Dolphin relaunch; suspect the path-load code path, not physics.
>
> **NEXT (session 70): fold `cam_clean` into the mint/novel_deliver pipeline (replace the empirical
> `cam_screen` frozen-target hunt with the csangle-invariance probe along the aim bearing); then the
> remaining exp5 items (the auto-flip envelope, distinct from the follow) and exp6 (arbitrary
> mid-walk entry states). The s64 leftovers re-scope-or-drop and the 97m/hseam2709 lotteries still
> stand.**

> **PRIOR THREAD (2026-07-20, session 68): Dereck's standing post-s66 steer is DELIVERED -- the
> live land playback suite is PORTED to offline recorded-golden tests.** No seam-clip behavior
> changed (no `harness/rollstab` code touched); this closes handoff item (a):
> - **The standing land gate is OFFLINE now:** `tests/test_land_goldens.py` compares the sim PER
>   FRAME, 0-ULP (state/nspeed/facing/travel/pos_z, + pos_x where measured exact), against live
>   recordings in `fixtures/land_goldens/` -- all 14 cases, no Dolphin. Recordings minted once by
>   `tests/dolphin/record_land_goldens.py` (chunked capture cross-checked against the proven
>   one-shot advanceseq delivery; a golden is written only if the locked live checks pass).
>   `run_land_tests.py` remains the live diagnostic / re-record tool (14/14 live PASS).
> - **The flaky `wiggle_ebs_roll` DTM-playback case is RETIRED and root-caused** (resolved-bugs.md):
>   single-stepping a PLAYING movie slips 1-frame edges (bulk advance delivers the same movie
>   faithfully), and its mid-recording savestate carried unseedable in-flight attention state. The
>   chain's consumed inputs were read back per logic frame from `g_mDoCPd_cpadInfo[0]` and now run
>   as a clean-rest PIPE case -- bit-exact per frame incl. pos_x (a real coverage upgrade over the
>   old signature-only lock). Corollary re-measured: the pipe mis-injects near-full OFF-AXIS sticks
>   by +-1 raw byte; use dead-zone-axis byte pairs (the sim's octagon clamp matches the decomp).
> - Suite **420 passed, 1 skipped, 5 xfailed** (+16 = the 14 golden gates + presence + the wiggle
>   chain-signature guard).
>
> **NEXT (session 69): unchanged from s67 -- ROADMAP Phase A expansion 5 (camera-in-the-loop) as
> the biggest idealization left, the s64 leftovers re-scope-or-drop, or the standing lotteries
> (97m, hseam2709). Every seam thread (ten delivered seams, walk-stab, Tetra push-aside/turnaround
> STANDALONE, 467/163 blocked) UNCHANGED.**

> **CURRENT THREAD (2026-07-19, session 67): the GanonA seam255 clip is DELIVERED LIVE 0-ULP --
> Dereck's named TAS corner is HIT. Tenth delivered seam; fourth room; the FIRST clip on a
> SLOPED (micro-incline) corridor:**
> `old=(620.3892822265625, -2340.420166015625) -> new=(614.9080810546875, -2389.334228515625)`,
> CUT_F at f31, drift (0,0), threads=True. One default-family `solve_focused` draw (112s,
> 2201 exact dust pts in 4 perp columns), the hit via a B2 fine, margin 1.
> - **The blocker was the SHEATHED base (new ledger #55):** `ganona_r0_base@twwgz` rests with
>   the sword sheathed (equip 0x100), so the pure-sim baseline roll could never CUT and
>   `mint_online` reported old=None forever -- the true cause of s65's "perp never converged".
>   Fix = mint-time setup: `ganona_r0_base_drawn@twwgz` (one-time B-press draw + steady-WAITS
>   probe, live-verified 0x103), now first-class as `mint.draw_base` (CLI
>   `python -m harness.rollstab.mint drawbase=<base> name=<base>_drawn`). Check `sword_drawn`
>   in a novel base's seed BEFORE mint_online.
> - **The ON-LINE re-mint then accepted at iter 1:** baseline |old perp| 1.783 (tol 2.0), rest
>   d2S 584.5, facing == F == 33960, cam frozen at csangle 22577 (target 25951, #54 rule),
>   settle_walk=21 now a first-class `mint_online`/CLI knob. REST gate re-run on the new anchor:
>   **REST BIT-EXACT 30/30 rows 0-ULP incl. m359C + pos_y**, golden re-written.
> - **The flat-model solve is exact on this corridor by the zero-cell fact** (getGroundAngle==0
>   under ~0.056 deg): A/B-verified -- the shipped 38-row stream is byte-identical in x/z + procs
>   with and without floors mode. solve_focused needed NO floors threading for this tier.
> - **Locked live-data-backed:** anchor `ganona_r0_rollstab_seam255@twwgz` (re-minted drawn +
>   on-line, seed tracked) + base `ganona_r0_base_drawn@twwgz`; goldens
>   `fixtures/seam255_rest_golden.json` (re-captured) + `fixtures/seam255_roll_ship_golden.json`
>   (the clean-DTM ship). Gates `tests/test_ganona_rest.py::test_seam255_rest_bitexact` +
>   `test_seam255_clip_delivered` GREEN. Suite **404 passed, 1 skipped, 5 xfailed** (+1).
>   Original base `ganona_r0_base@twwgz` unchanged, stone INTACT (avoidance line held: the
>   solve + ship never touched it).
>
> **NEXT (session 68): the s64 leftovers now unblocked-or-moot -- the mint floor-ladder relax and
> the step-3/step-5 fork were for a >630u ramp park this delivery never needed; re-scope or drop
> them. Otherwise the ROADMAP Phase A expansions (camera-in-the-loop first) or the standing
> lotteries (97m, hseam2709). Dereck's post-s66 steer also stands: port the live land playback
> tests to offline recorded-golden tests. Every other thread (nine prior seams, walk-stab, Tetra
> push-aside/turnaround STANDALONE, 467/163 blocked) UNCHANGED.**

> **PRIOR THREAD (2026-07-19, session 66): the GanonA seam255 REST gate is GREEN, 28/28 rows
> 0-ULP incl. m359C + pos_y (`tests/test_ganona_rest.py` un-redded, golden
> `fixtures/seam255_rest_golden.json`), WITHOUT touching the corridor stone (Dereck's steer:
> avoid, don't break).** Three things delivered it:
> - **The stone is AVOIDED by aim geometry.** The geo fixture now declares `aim_deg=186.5` (the
>   hseam2709 grazing-aim mechanism): the PROC_STONE sits 16u off the interior-bisector line but
>   77.8u off the 186.5 line, the 949-plateau micro-incline holds to d2S~600 with 250u+ wall
>   clearance, and the minted rest's actual walk track clears it by 124.6u. A SECOND prop
>   (pid 459) sits ON the line down the ramp at along 918 - park at ~815 (settle_est=285) so
>   the settle never reaches it. Screen a corridor's ACTORS along the line (the ledger-#52
>   actor-list walk), not just walls/floor/cam, before parking.
> - **The cam-leash creep is beaten by `mint.cam_screen` (the #44 pattern generalizes):** on the
>   186.5 line the default aim-derived pan target CREEPS ~4 s16/row through the whole approach
>   (the row-5+ pure-bearing REST diff signature - stick decode is csangle-relative); two
>   alternates stay FROZEN and the smallest-settle one (target 25951, csangle 21121) minted the
>   REST-exact anchor at d2S 513.6, steady WAITS, plateau y 949.04.
> - **Two missing decomp ground terms found by the per-frame foot diff and modeled (the s66 sim
>   change, `knowledge/model/ground-model.md`):** (1) **setStepsOffset's m35C4 walk base-Y lift**
>   (:9524/:9561) - on a downhill walk the draw base (and footBgCheck's r30[1][3]) rides
>   ~0.7 x one frame's dy above pos.y (~4.9e-3 at cruise; exactly 0 on flat), plus the uphill
>   `pos.y = dVar5` snap-ahead branch; seeded `rest_m35C4` (mint captures JP +0x34EC, 0.0 at a
>   settled rest). (2) **footBgCheck's non-plant `field_0x030` CLOTCH leg lift** (:8816) -
>   `0.3f * ground clearance`, UNGATED (the 0.1 floor is only inside setLegAngle, which zeroes
>   the leg ANGLES), consumed by jointBeforeCB as `mTranslate.x -= field_0x030` at R/LCLOTCH
>   (:276/:282); it moves the drawn foot ~1e-3 on the incline and feeds m359C. Both were
>   invisible on flat (identically zero), which is why 9 flat seams gated clean without them.
> - **Locked live-data-backed:** anchor `ganona_r0_rollstab_seam255@twwgz` (re-minted on the
>   186.5 line, frozen cam, seed tracked incl. rest_m35C4) + golden
>   `fixtures/seam255_rest_golden.json` (REST BIT-EXACT). Gate `test_seam255_rest_bitexact`
>   GREEN. Suite **403 passed, 1 skipped, 5 xfailed** (the ganona xfail marker removed; the
>   uphill micro-incline offline gate updated to the setStepsOffset ahead-cross semantics).
>   Flat paths byte-identical (foot030=None / m35c4=0.0 fast paths; all shipped-hit goldens
>   recompose green). Base `ganona_r0_base@twwgz` unchanged, stone INTACT.
>
> **NEXT (session 67): the solve.** The REST anchor is off the nominal line (old perp +47.9,
> the cam-leash oscillation documented s65) and the solve needs an ON-LINE anchor with the
> ~580u envelope - re-run `mint_online` with `target_csangle=25951` iterating on the BASELINE
> old perp (the frozen cam should stop the oscillation), or accept the arc-bracket absorbing
> the offset. Then the s64 items (mint floor-ladder relax; step-3/step-5 fork for the >630u
> ramp park) and the 0.002u-dense dust lottery. Every other thread (nine delivered seams,
> walk-stab, Tetra push-aside/turnaround STANDALONE, 97m/hseam2709 lotteries, 467/163 blocked)
> UNCHANGED.**

> **PRIOR THREAD (2026-07-19, session 65): ROADMAP Phase G is PROMOTED into the stepper and
> live-validated THROUGH the GanonA incline walk.** Floors mode (`LandState(floors=, gnd_seed=)`,
> new `tww_sim/land/floors.py`) models ground per frame, decomp-first: the gravity dip +
> GroundCross snap (pos_y follows the floor plane; d_bg_s_acch.cpp:122, probe pos.y+60, MAX
> cross-y over ground-list polys + walls ny>=0.014), the posMoveFromFootPos speedF slope scale
> (r3 = getGroundAngle(prev CrrPos poly, travel) incl. the r3<0 UPHILL x0.85 branch, :2408-2417),
> and the m35B8 foot ground-lift (footBgCheck :8712: per-delayed-foot GroundCross + the 10u/5-frame
> probe-freeze hysteresis + the waist r31 term, chased addCalc(0.5, 7.5, 2.5), baked base y += /
> m37B4 y -= at the draw). Flat paths are byte-identical (floors=None untouched; suite **402
> passed, 1 skipped, 6 xfailed** incl. +5 floors gates `tests/test_floors_ground.py`: flat-mesh
> step-identical equivalence, micro-incline plane-cross following, ramp REFUSES).
> - **The tier fact that shaped the model: `cM_atan2s` truncates `ratio*1024`, so any slope under
>   ~1/1024 (~0.056 deg) has getGroundAngle EXACTLY 0.** The GanonA 0.022-deg micro-incline is a
>   zero cell -- every angle term (speedF cos, x0.85, m34E2 anim-rate cos, m34E0 waist tilt, leg
>   IK) is exactly zero there; only pos_y + m35B8 are load-bearing. The ~10-deg ramp is NOT ported:
>   floors mode raises `SlopeNotModeled` rather than approximating (refuse-don't-guess).
> - **The LIVE gate reached rows 0-11 BIT-EXACT -- pos, frame ctrls, m359C AND pos_y tracking the
>   incline (949.0138 -> 948.966) -- so the ground model is live-validated.** Rows 12+ diverge for
>   a NON-ground cause, root-caused live (ledger #52): a **PROC_STONE skull prop stands ON the
>   corridor at (569.72, 948.94, -2080.17)** and the live walk takes a CC push around it (measured:
>   live speed == 17*dir(travel) exactly while position gains a 4-frame decaying push; no wall/bg/
>   posMove term -- an actor CC cylinder). Fix = mint-time SETUP (the #47/#49 pattern): break the
>   stone in the base -> `ganona_r0_base2@twwgz` -> re-mint -> re-gate. Screen a novel corridor for
>   CC-capable PROPS (stones/pots line dungeon corridors), not just walls/floor/cam.
> - **New JP RAM truths (mint.py header): the decomp's US field-name offsets shift -0xD8 on JP** in
>   both daPy and fopAc space (m35B8 +0x34E0, mCurrAttributeCode +0x34AC, m34DC +0x3404, speed
>   +0x148, speedF +0x17C, mpCLModel +0x254 -> J3DModel +0x8C mpNodeMtx) -- each live-validated.
>   Mint now captures the Phase G rest seed (rest_m35B8 / rest_foot024 / rest_foot001 / rest_waist);
>   `rest.py` threads `floors=` (CLI too) and the verification compares pos_y per row.
> - **mint_online on this corridor:** the cam leashes to csangle 28401 (never reaches the aim
>   target -- fixed-cam-like) and the settle varies 217-330u across the ramp junction, so the along
>   loop oscillated (rest d2S 411/690/483) and the perp never converged (22.9u off-line; retry with
>   `settle_est=320` after the stone). An off-line anchor is FINE for the REST gate, not the solve.
>   The 226-tread mid-cruise aim turn this caused is what flushed the stone out (first big turn any
>   REST stream ever ran).
> - **Locked live-data-backed:** floors mesh `fixtures/ganona_r0_floors.json` (capture_walls
>   `floors=1`, GroundCross candidate set in visit order); anchors `ganona_r0_base@twwgz` (healed,
>   steady WAITS, A-probe CLEAN -- no armed event) + `ganona_r0_rollstab_seam255@twwgz` (seed
>   tracked, d2S 483 ON the incline); gate `tests/test_ganona_rest.py::test_seam255_rest_bitexact`
>   **strict-xfail RED** (flips by removing the marker once the golden ships). NO shipped-hit
>   behavior change (flat paths byte-identical; all nine seams' goldens recompose).
>
> **NEXT (session 66): run the stone-break recipe (s65 handoff), save `ganona_r0_base2@twwgz`,
> re-mint with `settle_est=320`, re-run `python -m harness.rollstab.rest anchor=... geo=fixtures/
> ganona_r0_seam255_geo.json seed=0 floors=fixtures/ganona_r0_floors.json golden=fixtures/
> seam255_rest_golden.json` -> expect REST BIT-EXACT end-to-end -> un-red the test. Then the mint
> floor-ladder relax + the step-3/step-5 fork for the >630u ramp park (s64 handoff items 4-5); the
> clip itself is a 0.002u-dense lottery after that. Every other thread (nine delivered seams,
> walk-stab, Tetra push-aside/turnaround STANDALONE, 97m/hseam2709 lotteries, 467/163 blocked)
> UNCHANGED.**

> **PRIOR THREAD (2026-07-18, session 63): ROADMAP Phase A step 4's "deliver one corner
> out-of-kaze" tail is CLOSED -- the THIRD room (Hyrule Castle interior `Hyroom` r0, picked by
> Dereck's option (b): man-made flat floors) delivered a novel corner LIVE 0-ULP via the one-shot:
> seam_4002_4004 ("cseam4002", S=(-1210.3112, 207.8036), polys 4002x4004, interior 93.03, basement
> level link_y -1958.3, band_dense 0.018u, corridor 1340u, ~9.2k exact dust points) went room
> pre-rank (the seam-locator CSVs: one-flat-Y rooms; Siren r0 ruled a boat/tidal non-room) ->
> `capture_walls` (3430 walls) -> screen (121 rows) -> floor/cam (5/5 frozen) -> `mint_online` ->
> **REST BIT-EXACT** -> `solve_focused` -> **LIVE 0-ULP clean-DTM clip at seed=0**:
> `old=(-1184.0915527,167.6703033) -> new=(-1211.0118408,208.8762207)`, CUT_F at f30, drift (0,0).
> Ninth delivered seam; third room; second stage outside kaze.**
> - **The session's real finding (ledger #49): rooms carry ARMED one-shot auto-events.** The first
>   ship died with `end proc=0xb5` (`daPyProc_DEMO_LOOK_AROUND2_e`, an evmng staff cut): ANY A press
>   across a broad corridor region fires the event instead of the roll -- deterministically, movie
>   AND pipe -- while buttonless walks (and therefore the REST gate) pass clean. The event is
>   ONE-SHOT: play it out in the mint BASE (A-mash ~270 frames) and mint from the consumed state
>   (`hyroom_r0_base2@twwgz`, the ledger-#47 heal pattern). Probe a new room's base with an A press
>   mid-corridor, not just steady WAITS.
> - **Two more general lessons (ledger #50/#51):** a re-mint over the same anchor name ORPHANS a
>   solved-but-unshipped hit (the first anchor's 2-clip draw was lost; `deliver.gate` honestly
>   fails dOLD!=0 -- ship before re-minting); and the mint is DETERMINISTIC from its base, so the
>   honest fresh-lattice re-roll is the NEXT frozen cam target from the measured screen set
>   (44608: 8 documented families 0-hit, best d_true 0.21; 48971: DEFAULT draw 1 clip, margin 0).
>   `novel_deliver` gained `max_iter=` (mint re-park budget, aborts cleanly at the cap).
> - **Locked live-data-backed:** anchors `hyroom_r0_base@twwgz` + `hyroom_r0_base2@twwgz`
>   (consumed-event base) + `hyroom_r0_rollstab_cseam4002@twwgz` (seed tracked); goldens
>   `fixtures/cseam4002_rest_golden.json` (REST BIT-EXACT) + `fixtures/cseam4002_roll_ship_golden.
>   json` (the clean-DTM ship); mesh `fixtures/hyroom_r0_walls_ordered.json`; geo
>   `fixtures/hyroom_r0_cseam4002_geo.json`. Gates `tests/test_cseam4002_clip.py::
>   test_cseam4002_rest_bitexact` + `test_cseam4002_clip_delivered` GREEN. Suite **397 passed,
>   1 skipped, 5 xfailed** (+2). KB: room generalization split to its own page
>   (`knowledge/strategy/seam-clip-rooms.md`, the solver page hit the 250-line cap). NO
>   `sim.py`/`land.py`/`solver.py` change (novel_deliver max_iter plumbing only), so the live
>   regression and all shipped-hit recompositions are unaffected.
>
> **NEXT (RE-STEERED 2026-07-19, session 64 -- Dereck named a TAS target): the GanonA r0 corner
> seam_0255_0256 (S=(615.5078, 948.859436035, -2383.9854), interior 159.2, dust thin 0.002u,
> fixtures captured) has the first LOAD-BEARING floor slope -- a 0.022-deg micro-incline across
> the whole rest envelope + a ~10-deg ramp at the mint park -- so the next work is the Phase G
> promotion (floor-following pos_y + getGroundAngle r3 + m35B8 lift in the stepper), gated by
> REST BIT-EXACT on that corridor. See ROADMAP Phase G + the session-64 handoff. The step 3
> re-scope / step 5 fork folds into it (the >630u ramp park needs one of them). The hseam2709
> lottery can still re-roll cheaply via the ledger-#51 frozen-cam-target trick. Every other
> thread (proven/mirror/sheathed/152/157/152m/824/915/cseam4002 clips DONE, walk-stab, Tetra
> push-aside/turnaround STANDALONE, 97m lottery, 467/163 blocked) UNCHANGED.**

> **PRIOR THREAD (2026-07-18, session 62): ROADMAP Phase A step 4 (second room) -- the pipeline
> is ROOM-AGNOSTIC and the from-rest model is BIT-EXACT OUTSIDE KAZE. Dereck picked step 4;
> flooded Hyrule is the second room (its ordered wall mesh already existed from Phase C). The
> `mesh=`/`prefix=`/`base=` knobs are threaded through `make_seam_geo`/`seam_screen`/
> `novel_deliver` (geo fixtures now carry their mesh path; kaze defaults byte-identical), the
> room screened 284 seams / 100 rows (`_generated/seam_screen_hyrule.json`), and the one
> all-gates-green corner (seam_2709_2919, S=(-1744.197, 752.903), interior 107.4, ON the proven
> Tetra plain, grazing `aim_deg=344` so the ~1200u corridor hugs wall 2919's 300u flat strip) went
> floor -> cam (3/5 frozen, smallest settle 310) -> `mint_online` (2 iters, |old perp| 0.000, d2S
> 580.0) -> **REST BIT-EXACT (first 0-ULP from-rest verification outside kaze r11)**. The CLIP is
> NOT yet delivered: the corner's dust is 97m-class thin (band_dense 0.011-0.014u) and 8 documented
> knob-family draws (4 one-shot + kbr=300 / c3m=0.84/0.90 / nudge=16, ~300k exact candidates,
> near-band yield 0-4/draw, best d_true 0.00875) found 0 genuine -- an honest lottery with the
> anchor + rest golden READY (`hyrule_rollstab_hseam2709@twwgz`, `fixtures/hseam2709_rest_golden.
> json` auto-written).**
> - **Three NEW mint-time blockers found + fixed/ruled live (ledger #46-#48):** (a) open terrain
>   is mostly SLOPED -- floor-LADDER the aim line and require constant y (top pick seam_0185_0193
>   n=70098 ramps -15..-135; the -1853 region likewise; castle-footing corners all open OFF their
>   flat slab into voids); (b) a LOW-HP base savestate idles in ANM_WAITB (`checkRestHPAnime`,
>   life=1 from the Tetra sessions' falls) which the rest blend does not model -- healed base
>   `hyrule_plain_base@twwgz` + `mint_novel` now PROBES for steady WAITS (w ctrl moves on a
>   1-frame advance; d_rate 1.1) before minting; (c) run_dtm's log DOUBLED a row inside the REST
>   gate on this slower-loading stage -- proven physics-clean by reading the RAW PAD per row, and
>   the shared gate now drops byte-identical consecutive rows (`rest._dedup_log`).
> - **Locked live-data-backed:** anchor `hyrule_rollstab_hseam2709@twwgz` (seed tracked, healed
>   base) + `fixtures/hseam2709_rest_golden.json` (REST BIT-EXACT, dedup 1 row). No per-seam clip
>   test yet (nothing shipped); the solve stage FAILs honestly at 0 hits.
> - **Step-4 exit judgment: the room-generalization is PROVEN through REST (mesh capture path,
>   screen, floor/cam/mint recipes, DTM contract, from-rest model -- every kaze assumption
>   removed); the "deliver one corner" tail is blocked on Hyrule's dust geometry, not on any
>   room assumption.** Options: keep the hseam2709 lottery running in spare cycles (97m
>   precedent), or capture a third room's mesh (a DUNGEON room with man-made flat floors screens
>   better than open terrain -- the actual lesson of this room).
>
> **NEXT: Dereck's call -- (a) spare-cycle lottery draws on hseam2709 (anchor ready, ~2 min/draw
> offline), (b) a third room with man-made floors (one `capture_walls.py` run + the same one-shot),
> or (c) back to ROADMAP step 3 re-scope / step 5 (camera-in-the-loop). Every other thread
> (proven/mirror/sheathed/152/157/152m/824/915 kaze clips DONE, walk-stab, Tetra push-aside/
> turnaround STANDALONE, 97m lottery, 467/163 blocked) UNCHANGED.**

> **CURRENT THREAD (2026-07-18, session 61): ROADMAP Phase A step 2 is DELIVERED -- the whole
> touch-list is folded into the ONE-SHOT `novel_deliver.py` (10 gated stages: geo -> recheck ->
> floor -> cam -> mint -> rest -> dust -> solve -> ship -> test scaffold; per-seam resume state in
> `_generated/novel_<name>.json`), and its first run delivered a fresh screened corner end-to-end:
> the NOVEL 151-corner seam_0915_0918 (S=(13049.7656, 1368.0778), polys 915x918, interior 151.08,
> n=658 / band_dense 0.027u / corridor 1080u -- the best remaining walkable pick) went one command ->
> LIVE 0-ULP clean-DTM clip at seed=0 (8th delivered seam; first shipped stream worked):
> `old=(13026.662109375, 1324.813720703125) -> new=(13049.8466796875, 1368.2310791015625)`, CUT_F
> then OOB, drift (0,0). Draw pricing behaved as documented: default draw 0 hits (near-band 0),
> the c3m=0.78 family (the built-in documented retry) delivered 1 clip (margin 6, via a B2 fine).
> `mint_online` converged in 2 iters (rest d2S 580.0, baseline |old perp| **0.001**), REST
> BIT-EXACT every row.**
> - **The one lesson the validation forced (ledger #45): the cam screen's settle travel is
>   TARGET-dependent (rest_d2S 332..688 from the same 1000u park across seam915's five frozen
>   targets), so preferring the default aim-derived target is WRONG** -- its 668u settle parked the
>   mint at d2S 1248, past the floor edge (the floor stage had probed 1000/1100 FLOOR), Link
>   teleport-slid and fell OOB before minting, and the baseline could never fire. Fix shipped in
>   `novel_deliver`: choose the frozen target with the SMALLEST measured settle (deepest park
>   inside the probed floor) and floor-probe the implied park when it lies beyond what the floor
>   stage checked. The gates did their job: every failure aborted cleanly at its stage.
> - **New first-class pieces (all folded from touch-list items / scratch scripts):**
>   `mint.floor_probe` (+ CLI `floorprobe=`, the ledger-#43 park-floor screen),
>   `seam_screen.recheck` (the step-0 honest band_dense re-check), `rest.write_golden` (+
>   `golden=` on the rest CLI -- the REST golden assembles itself on a BIT-EXACT pass), the
>   generated per-seam test scaffold (never overwrites an existing locked test), and the
>   documented knob-family retry (`DRAW_FAMILIES`: default, c3m 0.78/0.72/0.56) on a 0-hit draw.
>   `seam_screen.KNOWN` now also excludes 152m/824/467/163.
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam915@twwgz` (seed tracked); goldens
>   `fixtures/seam915_rest_golden.json` (REST BIT-EXACT, auto-written) +
>   `fixtures/seam915_roll_ship_golden.json` (the clean-DTM ship). Gates (scaffold-generated)
>   `tests/test_seam915_clip.py::test_seam915_rest_bitexact` + `test_seam915_clip_delivered`
>   GREEN. Suite **394 passed, 1 skipped, 4 xfailed** (+2). NO `sim.py`/`land.py`/`solver.py`
>   change (orchestration + mint/rest/screen tooling only), so the live regression and all
>   shipped-hit recompositions are unaffected.
>
> **NEXT: ROADMAP step 3 needs the RE-SCOPE decision from Dereck first (the ~580u rest envelope is
> roll PHYSICS -- s60 finding -- so short-corridor seams want the walk-stab tier or
> camera-in-the-loop, not a smaller A_proj). Then step 4 (second room): `novel_deliver` is ready
> except the kaze-specific mesh paths (`seam_screen.MESH`, `make_seam_geo.MESH`) -- capturing the
> second room's ordered mesh is the actual work. The 97m lottery keeps running in spare cycles.
> Every other thread (proven/mirror/sheathed/152/157/152m/824/915 clips DONE, walk-stab, Tetra
> push-aside/turnaround STANDALONE, 97+493 push-steer-only) UNCHANGED.**

> **PRIOR THREAD (2026-07-18, session 60): Phase A step 1's queue is CLOSED -- seam_0824_0826
> ("824", S=(9689.1406, 123.4604), polys 824x826, interior 157.33) is DELIVERED LIVE 0-ULP (7th
> seam; one default 112s draw, 2 wall-faithful clips, top margin 27; first shipped stream worked):
> `old=(9731.271484375, 138.69970703125) -> new=(9684.986328125, 121.95780944824219)`, CUT_F then
> OOB, drift (0,0). seam_0467_0468 is RULED unmintable (ledger #43: aim-line FLOOR ends d2S ~1050
> while its settle needs ~722u -- park space is floor, and `seam_screen.corridor` only measures
> wall clearance). Both picks were band_dense re-checked first (467: 0.031u honest; 824: 0.024u).**
> - **The 824 needed a NEW screen + mint knob (ledger #44): its corridor carries a fixed,
>   ROAD-triggered camera-trigger band (csangle dips ~-300 s16 over d2S 588..384 and recovers;
>   proven road-triggered by a shifted-start probe) that fires only on the DEFAULT pan target's
>   cam track.** Fix shipped first-class: `mint.cam_screen` (CLI `camscreen=<geo>`) probes
>   alternate `target_csangle`s at the park and reports frozen-vs-deviating corridors; all four
>   alternates (F+-8000/+-16384) stayed frozen. Minted with the screened 37512 (csangle 41530
>   frozen) -> `mint_online` converged in 2 iters (rest d2S 580.0, baseline |old perp| 0.114) ->
>   REST BIT-EXACT every row. `mint_online` CLI also gained `settle_est=`/`target_csangle=`
>   (touch-list item 2 closed) and the rest verification calib now logs per-frame `csangle` (the
>   diagnostic that found the band).
> - **ROADMAP step-3 correction (from the 467/824 measurements): the ~580u rest envelope is
>   mostly PHYSICS for the standard roll** -- the A press fires ~506u out (derived A_projs ~-507,
>   roll travel A->cut ~463u) + ~74u cap walk -- so step 3's exit "a ~300u-rest anchor solves"
>   cannot be met by the roll path. Short-corridor/short-floor seams (163, 467) need a different
>   technique (walk-stab tier? camera-in-the-loop?), not a smaller A_proj. Surfaced for re-scoping.
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam824@twwgz` (seed tracked); goldens
>   `fixtures/seam824_rest_golden.json` (REST BIT-EXACT) + `fixtures/seam824_roll_ship_golden.json`
>   (the clean-DTM ship). Gates `tests/test_seam824_clip.py::test_seam824_rest_bitexact` +
>   `test_seam824_clip_delivered` GREEN. Suite **392 passed, 1 skipped, 4 xfailed** (+2). NO
>   `sim.py`/`land.py`/`solver.py` change (mint/rest tooling only), so the live regression and all
>   shipped-hit recompositions are unaffected. seam467 geo kept (`fixtures/kaze_r11_seam467_geo.
>   json`); its non-REST anchor deleted (163 precedent).
>
> **NEXT (Phase A step 2, the queue being closed): fold the touch-list into a one-shot
> `novel_deliver`** -- now including the two session-60 screens (park-FLOOR probe; `cam_screen`
> when REST diverges with the csangle-wobble signature -- or run it up front). Step 3 needs
> RE-SCOPING with Dereck first (the envelope is physics; the honest unblockers for short seams
> are the walk-stab tier or camera-in-the-loop). Then step 4 (second room). The 97m lottery keeps
> running in spare cycles. Every other thread (proven/mirror/sheathed/152/157/152m/824 clips DONE,
> walk-stab, Tetra push-aside/turnaround STANDALONE, 97+493 push-steer-only) UNCHANGED.

> **PRIOR THREAD (2026-07-18, session 59): ROADMAP Phase A step 1, first queued pick DELIVERED --
> the 152m corner (the 152's z-mirror, S=(10555.1904, -190.6696), polys 465x474, interior 151.68)
> went make_seam_geo -> `mint_online` -> REST BIT-EXACT (28+ rows) -> `solve_focused` **6
> wall-faithful clips in one c3m=0.78 111s draw** (top margin 8) -> **LIVE 0-ULP clean-DTM clip at
> seed=0**: `old=(10519.09375,-223.71536254882812) -> new=(10555.3984375,-190.47947692871094)`,
> CUT_F then OOB, drift (0,0). Sixth delivered seam; first shipped stream worked live.**
> - **Screen caveat found (fixed in `seam_screen.py`): the `band` metric is outlier-inflatable.**
>   The 152m screened 0.458u but its DENSE cluster is 0.026u (mirror-class) + one stray column at
>   +0.322; the default c3m=0.66 draw found 0 (near-band 0) twice, then the documented c3m=0.78
>   family delivered 6 in one draw. The screen now also reports `band_dense` (largest contiguous
>   column cluster) -- price picks by that; strategy page updated.
> - **`mint_online` hardened (general, ledger-#42 corollary): never accept on the rest-perp
>   fallback while the pure-sim baseline roll does not fire.** The first 152m mint accepted
>   ON-LINE at rest d2S 460.9 where NO spF-17 baseline exists (old=None -- the short-rest
>   envelope symptom); the fix re-parks on the along error (and drops the secant history across
>   the fallback) until the baseline fires. Converged in 3 iters: rest d2S 576.8, |old perp|
>   0.547, facing==F==8685, csangle 3683 frozen.
> - **Phase-A step-1 TOUCH-LIST (the step's exit metric -- what `novel_deliver` must fold in):**
>   (1) seam naming + geo-fixture rename by hand (make_seam_geo names by polys); (2) mint_online
>   called via Python API (CLI lacks `settle_est=`); (3) anchor files renamed to `@twwgz` by hand;
>   (4) the rest golden assembled by hand from `_generated/rollstab_calib.json` (rest.py has no
>   `golden=` writer); (5) a knob-family retry decision when the default draw hit 0; (6) the
>   per-seam test file authored by hand (copy of the 157's). Plus the standing per-delivery runs
>   (screen numbers re-check, REST verify, 2-3 draws, ship).
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam152m@twwgz` (seed tracked); goldens
>   `fixtures/seam152m_rest_golden.json` (REST BIT-EXACT) + `fixtures/seam152m_roll_ship_golden.json`
>   (the clean-DTM ship). Gates `tests/test_seam152m_clip.py::test_seam152m_rest_bitexact` +
>   `test_seam152m_clip_delivered` GREEN. Suite **390 passed, 1 skipped, 4 xfailed** (+2). NO
>   `sim.py`/`land.py`/`solver.py` change (mint acceptance + screen metric only), so the live
>   regression and all shipped-hit recompositions are unaffected.
>
> **NEXT (Phase A step 1 continues): deliver the remaining queued screen picks verbatim, counting
> touches** -- `seam_0467_0468` (10762.53,-273.26; n=2285 but thin 0.031u band -- expect knob-family
> draws) and `seam_0824_0826` (9689.14,123.46; n=725; re-check its band_dense first). Then step 2
> (fold the touch-list above into a one-shot `novel_deliver`), step 3 (kill the ~580u rest envelope
> in `_derive_a_projs` -- also unblocks the 163-corner), step 4 (second room), then the expansions.
> The 97m lottery keeps running in spare cycles. Every other thread (proven/mirror/sheathed/152/157/
> 152m clips DONE, walk-stab, Tetra push-aside/turnaround STANDALONE, 97+493 push-steer-only)
> UNCHANGED.

> **PRIOR THREAD (2026-07-18, session 58): Dereck's pick (b) is DELIVERED -- the room-wide density
> SCREEN is now first-class tooling (`seam_screen.py`) and its first pick, the NOVEL 157-deg corner
> S=(9689.1406, -150.3137) (polys 456x459, walkable floor, corridor 1400u), went screen -> `mint_online`
> -> REST BIT-EXACT -> `solve_focused` **2 wall-faithful clips in one default 112s draw** (top margin
> 60, the fattest yet) -> **LIVE 0-ULP clean-DTM clip at seed=0**:
> `old=(9734.5458984,-166.6959534) -> new=(9688.2480469,-149.9900513)`, CUT_F then OOB, drift (0,0).
> The 97m background lottery ran 6 more knob-family draws (kbr=300, c3m 0.56/0.78/0.84 x nudge 10/16,
> ~880k exact candidates): still 0 -- ~15 cumulative draws now; it stays an honest lottery
> (`test_seam97m_clip_delivered` strict-xfail RED) while dense corners deliver in one draw.**
> - **The screen (`seam_screen.py`, ~10 min cold):** enumerate all 159 room seams -> corner filter ->
>   `roll_reachable` -> the s55 density scan (samples / along-row coverage / perp band width) + two
>   delivery constraints the metric alone misses: `link_y` on the WALKABLE floor (the two densest raw
>   candidates sit on the -4680 upper level, unproven) and approach CORRIDOR length (>= ~1000u; see
>   the mint fixes below). Benchmarks in-scan: 152 = 1408/70%/0.021u (delivered, now 3 clips/draw),
>   mirror = 360/17%/0.021u (delivered), 97m = 84/14%/0.018u (undelivered). The 157 pick screens
>   1480/50%/**0.33u band** -- a WIDE perp band is the strongest single predictor (near-band candidates
>   come cheap: Phase B put 3 in-band in 48s where the 97m's best draws manage ~4 in 110s).
> - **Two general `mint_online`/`mint_novel` fixes (both bit-measured live, ledger #42):** (1) the
>   walk-settle now runs UNTIL csangle freezes (chunked, stick re-derived per chunk; a FIXED 14-frame
>   settle under-settled the 163-corner by ~258 s16 and the cam crept through the verification's first
>   ~15 rows); (2) the re-park loop steps by a SECANT gain from the iteration history (the 1:1 step
>   oscillated at a ~25-deg settle misaim, measured response ~1.8x). RULED OUT live (ledger #42):
>   teleport-to-rest after the settle -- a teleport RESETS the cam-Link leash and the next from-rest
>   walk re-pulls the cam (~16 frames of csangle creep), so the settle must genuinely END at the rest;
>   that is WHY the corridor constraint exists. The 163-corner (S=(9709.58,-13.43), 5221 samples, the
>   densest walkable candidate) stays a candidate BLOCKED on its 720u corridor, not on dust (geo kept:
>   `fixtures/kaze_r11_seam163_geo.json`; its non-REST-exact anchor was deleted). Also learned:
>   `_derive_a_projs` implicitly assumes the ~580u rest envelope (a 300u-rest anchor never fires
>   spF-17 baselines) -- `mint_online` d2s stays 580.
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam157@twwgz` (seed tracked); goldens
>   `fixtures/seam157_rest_golden.json` (REST BIT-EXACT, 28/28 rows incl. frame ctrls + m359C) +
>   `fixtures/seam157_roll_ship_golden.json` (the clean-DTM ship). Gates `tests/test_seam157_clip.py::
>   test_seam157_rest_bitexact` + `test_seam157_clip_delivered` GREEN. Suite **388 passed, 1 skipped,
>   4 xfailed** (+2). NO `sim.py`/`land.py`/`solver.py` change (mint + screen tooling only), so the
>   live regression and all shipped-hit recompositions are unaffected.
>
> **NEXT (DECIDED with Dereck, end of s58): follow ROADMAP.md Phase A -- refine the current
> pipeline toward arbitrary-state seam clipping, steps IN ORDER.** Step 1 = deliver the queued
> screen picks verbatim, counting manual touches (next: seam_0465_0474, the 152's z-mirror, 835
> samples / WIDE 0.458u band -- likely cheapest; then seam_0467_0468 (2285, thin 0.031u band),
> seam_0824_0826 (725)); ranked list in `_generated/seam_screen.json` (regen: `python -m
> harness.rollstab.seam_screen`). Then step 2 (one-shot `novel_deliver`), step 3 (kill the ~580u
> rest envelope in `_derive_a_projs` -- also unblocks the 163-corner), step 4 (second room), and
> only then the expansions (camera-in-the-loop, mid-walk entry states) -- full rationale + exit
> criteria in `ROADMAP.md` Phase A. The 97m lottery keeps running in spare cycles (untried: crawl
> slot 0 as a solver param, c3m 0.90+, A_projs deeper than [:6], off_step 60 interleave). Every
> other thread (proven/mirror/sheathed/152/157 clips DONE, walk-stab, Tetra push-aside/turnaround
> STANDALONE, 97-corner +493 push-steer-only) UNCHANGED.

> **CURRENT THREAD (2026-07-17, session 57): `solve_focused` is RESTRUCTURED on two measured bugs
> (dead-end #41) -- Phase A' now ranks CRAWL-INCLUDED centers (arc x A_proj x the full derived m2
> family, pooled) by TRUE 2D distance to the exact dust cloud with ROUND-ROBIN consumption across
> arc families, and B2's rounded-column ranker is replaced by the same metric -- and the shipped
> seams re-solve BETTER than before (152: 3 wall-faithful clips in 111s, was 1 in 80s; mirror: 2 in
> 112s, was 1 in 85s). The 97m is STILL not delivered: near-band yield went 0 -> ~4.5 per 110s
> draw (best child d_true 0.00121) but 4 knob-varied draws (~474k exact candidates) found 0 genuine
> -- expected ~0.2-0.4 hits/draw at this sliver thinness. `test_seam97m_clip_delivered` stays
> strict-xfail RED (honest).**
> - **The session's measurements (Dereck's pick was (b), 2D-exact ranking, validate-before-commit;
>   the measurement half-failed and forced the deeper fix):** (1) the s56 B2 ranker `_dcol` (perp to
>   1e-3-ROUNDED columns, along-blind) put candidates 3-12u of along from any real dust at the top of
>   the drill order (dcol 1e-5 with true distance 3.0; top-40 overlap with the true ranking 8/40);
>   (2) a 1-frame FINE is NOT a local refiner -- children land median ~3.5u of along from the parent
>   (chaotic like the nudge), so drilling the 200 TRULY nearest keepers x all 150 fines (19,230 exact)
>   still gave 0 genuine: B2 can never close a last ~1e-3, it is only extra independent draws;
>   (3) the s56 "cloud sprays median 1.86u of perp around a razor-close center" is a RANKING artifact:
>   Phase A ranked the CRAWL-LESS trajectory while Phase B always added the K=3 crawl, which shifts
>   the center ~1.15u of perp (the m2 family steers centers SMOOTHLY, -1.15..-3.2 -- a knob, not chaos).
> - **The restructure (`solver.py`; `_dust2d` exact sliver cloud 0.005 along x 2e-5 perp over the
>   column band, disk-cached ~30s/seam under `_generated/`; `_dust_dist` perp-x200 nearest lookup):**
>   Phase A' sweeps arc(off,dur,lead) x A_projs x m2fam (m2s=None derives the full distinct-stick msd
>   family, 11 sticks on the 97m) with the crawl INCLUDED and ranks by d_true; brackets are consumed
>   ROUND-ROBIN across arc families (each off's best m2 first -- a center point is noise at the cloud's
>   ~1-2u chaotic scale, so pure ranked-greedy over-concentrates: the greedy first cut LOST the 152
>   re-solve, whose winning family's crawl-included center sits 0.28u of perp off-band at d_true 56;
>   breadth restored it and MORE); Phase B byte-nudges the kept (bracket, m2) pairs (center's cross
>   seeds the fixpoint); B2 unchanged but ranked by d_true -- all 5 regression clips arrived via B2
>   fines, so the drill EARNS its budget on dense seams even though it cannot "close" (finding 2).
>   The solver now PRINTS the near-band yield per draw (the deliverable metric). Legacy m2s tuples
>   still honored. Gates: suite **386 passed, 1 skipped, 4 xfailed** (+3 = `tests/test_solver_dust2d.py`:
>   exact-vs-bruteforce walker, cache round-trip, points-are-genuine); mirror + 152 re-solve in budget
>   under the new structure; NO `sim.py`/`land.py`/`run()` change (candidate evaluation is untouched --
>   only WHICH candidates a draw evaluates changed).
> - **Locked live-data-backed:** nothing new live (no Dolphin run -- anchors/goldens unchanged).
>
> **NEXT (pick one):** (a) **hunt the 97m hit with independent draw families** -- each 110s draw at a
> documented knob family (crawl slot 0 `(f2, full, c3)` [scratch-validated, fresh families], c3m
> 0.60/0.66/0.72/0.78, kbr depth, nudge width) yields ~4-6 near-band candidates and ~0.2-0.4 expected
> hits; a handful of draws is the honest price at this dust thinness -- then `deliver ship` -> live
> 0-ULP -> flip the xfail. (b) **screen the room scan's 74 clippable seams by near-band YIELD** (the
> solver's printed metric makes this cheap) and deliver a denser corner instead. Every other thread
> (proven/mirror/sheathed/152 clips DONE, walk-stab, Tetra push-aside/turnaround STANDALONE, 97-corner
> +493 push-steer-only) UNCHANGED.

> **PRIOR THREAD (2026-07-17, session 56): the s55 NEXT (run() THROUGHPUT) is DELIVERED and GATED --
> a 2-minute `solve_focused` draw now covers ~7x the candidates (~1.7k/s pooled vs s55's ~255/s) with
> every output bit identical -- and ~1.2M exact candidates were drawn on the 97m at the new density
> (7 draws: default grid, nudge=16, m2-dense, c3m=0.72/0.6, kbr=60, + the new Phase-B2 fine drill):
> STILL 0 hits. The session's diagnostic OVERTURNS the s55 pricing: the search cost is not the seam's
> dust density alone but the chaotic crawl CLOUD's PERP SPREAD -- a bracket's 441-nudge cloud lands
> median ~1.86u from the nearest genuine perp column (p10 0.33u), so ~99.8% of Phase-B candidates are
> never even in the razor band. Frontier = put candidates IN the band (Phase-A bracket diversity /
> 2D-exact dust ranking / a denser corner), not more of the same draws. Surfaced to Dereck.**
> - **Throughput, 3 mechanisms (all BIT-IDENTICAL, gated by the new `tests/test_solver_fastpose.py` +
>   all shipped-hit recomposition gates green + a full-grid pool-vs-serial mirror A/B finding the SAME
>   single hit):** (1) **lazy cruise-pose defer** -- `FootSpeedF.skip_cruise_pose` upgraded from
>   walkstab's drop-outright shortcut to a defer+replay backlog (`_drain_skipped`): at m3598==0 speedF
>   ==nspeed exactly, so cruise/roll poses defer and REPLAY IN ORDER on the first consumer (an
>   m3598!=0 compose or a stop) -- exact for EVERY stream incl. mid-cruise fines, ~1.9x; solver.run/
>   wall_faithful enable it via `solver.FAST_POSE` (walkstab callers inherit the safer semantics).
>   (2) **fixpoint `cross_hint`** -- run() seeds its placement fixpoint with a neighbour's cross frame
>   (the accept invariant want==placed on the SIMULATED trajectory is unchanged), ~1.3x. (3)
>   **`solve_focused(procs=)`** -- Phase B fans the nudge grid to worker processes (default cpu-2 cap
>   10) which evaluate the SAME exact run+wall_faithful gates; full default grid 35s (was over-budget).
> - **Phase B2 NEW (the freeze-solver drill in the focused path):** every fired near-miss is ranked by
>   perp distance to a genuine column; the nearest are extended with one documented 1-frame
>   partial-magnitude FINE (`fine_family`) and tested exactly, until the wall-clock budget. On the 97m
>   it drilled 1169 keepers (best dcol 1e-5) -- 0 genuine; NOTE `fine_family` octagon-collapses to 30
>   distinct sticks here (the known #29/#32 collapse), so the fine lattice is coarse.
> - **The overturning diagnostic (scratchpad `diag97m.py`, finding in the strategy page):** the s55
>   "dust density prices the search" model predicted ~1 hit per ~30-130k candidates at 97m density;
>   ~1.4M cumulative exact candidates (s55's 200k + s56's 1.2M) found 0. Measured on the top bracket
>   (score 5.4e-4): the Phase-B cloud's perp-to-column distances are median 1.86u / p10 0.33u / min
>   1.4e-3 over 2.6k fired candidates. The bracket CENTER is razor-close but the nudge cloud sprays
>   units-wide in perp; hits require the (rare) near-column tail AND the f32 z-sliver. Density screens
>   remain necessary but NOT sufficient -- the deliverable metric is near-band candidate yield.
> - **Locked live-data-backed:** nothing new live this session (no Dolphin run needed -- the anchor +
>   REST golden were ready and unchanged; no sim.py/land.py change, live regression unaffected;
>   `foot_speedf.py` changed only behind the default-OFF `skip_cruise_pose` flag). Suite **383 passed,
>   1 skipped, 4 xfailed** (+2 = the fast-path A/B gates). `test_seam97m_clip_delivered` stays
>   strict-xfail RED (honest).
>
> **NEXT (pick one, Dereck's call):** (a) **Phase-A bracket DIVERSITY** (the s55 deferred option b,
> now the evidence-backed frontier): today every draw hangs off the same deterministic ~40 bracket
> centers; a walkstab-style K=2 start-crawl inside Phase A (crawl frame BEFORE the ranking) mints
> fresh independent center families whose clouds populate different perp bands. (b) **2D-exact dust
> ranking for B2**: `_genuine_perps` rounds columns to 1e-3 -- scan the exact sliver point cloud once
> (0.005 along x 2e-5 perp over the band) and rank near-misses/drills by TRUE (along, perp) distance
> to real dust (the drill's x200 perp weighting), so the drill spends its 30-stick fine lattice only
> on candidates a fine can actually close. (c) **a denser corner** (the room scan lists 74 clippable
> seams; screen dust density AND expected near-band yield first). Every other thread (proven/mirror/
> sheathed/152 clips DONE, walk-stab, Tetra push-aside/turnaround STANDALONE, 97-corner +493
> push-steer-only) UNCHANGED.

> **PRIOR THREAD (2026-07-17, session 55): the z-mirror 97-corner S=(13539.2393,-493.3560) is
> PAN-MINTED + REST BIT-EXACT -- the s54 camera recipe GENERALIZES (the s53/s54 candidate's blocker is
> CLOSED) -- but the CLIP is NOT delivered: the corner's genuine dust is ~4x thinner than the mirror's
> and `solve_focused` at the 2-minute budget gives < 1 expected hit per draw (8 independent draws, 0
> hits). Surfaced to Dereck; scaling options below.**
> - **`mint.mint_online` NEW (first-class, the handoff's secondary ask): the on-line pan mint as one
>   call** -- park on the aim line, `mint_novel` C-stick pan, then re-park driving the **BASELINE ROLL
>   `old`'s perp** to ~0 (measured PURE-SIM from the minted seed via `solver.run(anchor, [])`; converges
>   in 1 step). The rest-perp-only re-park (s54's recipe) UNDER-measures wherever the settle misaim is
>   large: the ~23-deg misaim's MOVE turn added ~12u perp between rest and the roll here, leaving a
>   rest-on-line anchor rolling from perp +15 (outside the arc reach) -- dead-end #38. GOTCHA fixed
>   in-place: `solver._BASE`/`_BASE_WALLED` cache rest states by anchor NAME; the re-mint loop
>   invalidates them (else every iteration re-measures the first mint).
> - **REST BIT-EXACT at an AUTO-cam mid-room corner** (28/28 rows 0-ULP incl. the 23-deg MOVE turn,
>   seed=0, C-down; csangle 5131 frozen through the whole live approach). This was exactly what blocked
>   the corner in s54 (#36) -- the pan recipe is now proven at a second auto-cam region.
> - **The search gap, quantified (the session's finding): dust DENSITY prices the search.** Fine-scan
>   (0.02 along x 0.0002 perp over the reach band): 97m = **84** genuine samples (13% of along rows,
>   slivers <=0.0006u, perp band 0.02u) vs the delivered mirror **360** and 152-corner **1409** (70%
>   rows, 0.41u band). The focused search's chaotic clouds (local perp spacing ~0.008u) expect < 1 hit
>   per 110s draw at that density. Ruled out at this budget (#39): finer `off_step` (arcs
>   octagon-saturate -- Phase A brackets byte-identical at 60 vs 120), the NEW `solve_focused(m2s=,
>   c3m=)` knob families (frame-2 partial magnitude + c3 base -- correct generalizations of the
>   documented K=3 crawl, kaze byte-identical at defaults, but each cloud is too diffuse), a 2D
>   frame2 x frame3 byte grid. The full-aim mouth screen confirms the bisector aim is already optimal
>   (mouth-open dust peaks at F=8769/8936). Roll-reachability is NOT in question.
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam97m@twwgz` (seed tracked); golden
>   `fixtures/seam97m_rest_golden.json` (REST BIT-EXACT). Gates `tests/test_seam97m_clip.py::
>   test_seam97m_rest_bitexact` GREEN + `test_seam97m_clip_delivered` strict-xfail RED (the honest
>   flag). Suite **381 passed, 1 skipped, 4 xfailed** (+1 pass, +1 xfail). NO `sim.py`/`land.py`
>   change; `solver.py` changed ONLY additively (`m2s`/`c3m` params, m2=1.0-first order preserves the
>   original lattice per bracket), all seam-param/bands/mirror/152 gates green.
>
> **NEXT (DECIDED -- Dereck picked run() THROUGHPUT, end of s55):** make the from-rest candidate sim
> faster so a 2-minute `solve_focused` draw covers ~4x+ more candidates (~4ms/candidate caps a draw at
> ~28k today; the 97m needs ~4x the mirror's density). Profile run() first; any speedup must be
> BIT-IDENTICAL (the rest blend / turn lean / deferred draw live on the Python foot -- that is WHY
> `rest_state` is foot_native=False; gate = shipped kaze/mirror/152 hits recompose byte-identical + a
> fast-vs-slow A/B on candidate streams). Then re-run the 97m draws (anchor + REST golden are READY,
> nothing to re-mint) -> deliver -> flip `test_seam97m_clip_delivered` GREEN. Deferred alternatives:
> K=2-crawl Phase-A diversity; a denser corner (screen dust density first). Every other thread
> (proven/mirror/sheathed/152 clips DONE, walk-stab, Tetra push-aside/turnaround STANDALONE, 97-corner
> +493 push-steer-only) UNCHANGED.

> **PRIOR THREAD (2026-07-17, session 54): a SECOND novel corner is DELIVERED LIVE, 0-ULP, pure-sim --
> the 152-deg corner S=(10555.1904, 190.6696) (interior 151.68, walls 840x845), picked by the session-53
> screening tooling, minted fresh, solved by `solve_focused` in 80s, and shipped via a clean DTM at seed=0:
> `old=(10542.6318359, 232.2424469) -> new=(10556.8652344, 185.1252899)`, CUT_F then OOB (proc 0x24),
> live old/new drift (0,0). NO solver/sim code change -- the whole session was screening + mint recipe
> work; the generalized path delivered as-built.** Two firsts: the fixture DECLARES an off-bisector aim
> (`aim_deg=163.08`; the 132.3 bisector has no reachable dust -- found by the full-aim mouth screen), and
> the anchor is a PANNED-camera mint (`mint_novel` C-stick pan) at a region whose AUTO-cam tracks Link.
> - **The candidate z-MIRROR 97-corner S=(13539.24,-493.36) IS roll-reachable geometrically -- 11
>   mouth-open genuine points at its DEFAULT bisector F=8824 (dust 35.3-36.9u off BOTH walls, unlike its
>   +493 sibling whose dust hugs wallA at 2.8-5.4u) -- but was NOT deliverable this session: its bisector
>   approach crosses a region where the AUTO-camera pans continuously with Link's position (~5-20 s16 per
>   walk frame; the cam only moves while Link MOVES -- idle never relaxes it), so the constant-csangle
>   rest model cannot be bit-exact there. NOT a dead end: the C-stick-pan mint (discovered later at the
>   152-corner, below) was never RETRIED on it -- it is the natural next candidate. Geo fixture kept:
>   `fixtures/kaze_r11_seam97m_geo.json`.
> - **CAMERA lesson (the session's real finding): kaze r11 has TWO cam regimes.** The +493 seam sat in a
>   FIXED-cam region (csangle 29883 frozen; s52's pan "sprang back", hence the aligned-idle-only recipe).
>   Mid-room, the auto-cam TRACKS Link's position while he walks -- every unpanned mint attempt crept
>   (29883->29767->29351 near the corner). The fix is the SHIPPED `mint.mint_novel` C-stick pan (arms the
>   MANUAL cam, which then freezes for good once the walk-settle passes the leash pull) -- the s50 mirror
>   recipe, which s52 had set aside as fixed-cam-specific. After the pan, csangle 22603 held FROZEN
>   bit-exact through the whole live approach (REST gate). Screen a novel corner's cam BEFORE minting.
> - **ON-LINE mint constraint (new, gated by the Phase-A score): the anchor must rest within the arc
>   reach (~+-15u; aim |perp| < 8u) of the F-through-S line.** `mint_novel`'s settle walk drifts off the
>   park bearing (travel settles ~22 deg off F here -- advancewith stick injection + cam motion during the
>   walk), so the first mint sat 117.5u off-line and `solve_focused` found 0 hits with Phase-A best score
>   118.85 == exactly that offset (the tell). Fix: measure `seam.perp(rest)` from the minted seed and
>   re-park by -perp (converged in 1 iteration: perp -3.99u, d2S 584u). The anchor does NOT need to face
>   F: facing 25794 vs F=29729 (~22 deg) -- the arc bracket absorbed it (the hit's arc is off=+1800, dur 3).
> - **Locked live-data-backed:** anchor `kaze_r11_rollstab_seam152@twwgz` (seed tracked); goldens
>   `fixtures/seam152_rest_golden.json` (REST BIT-EXACT, straight-then-aim stream incl. the 22-deg MOVE
>   turn) + `fixtures/seam152_roll_ship_golden.json` (the clean-DTM ship). Gates
>   `tests/test_seam152_clip.py::test_seam152_rest_bitexact` + `test_seam152_clip_delivered` GREEN. Suite
>   **380 passed, 1 skipped, 3 xfailed** (was 378; +2). NO `sim.py`/`land.py`/`harness/rollstab/*.py`
>   change, so the live regression is unaffected.
>
> **NEXT:** (1) the z-mirror 97-corner with the PAN mint (its dust is bisector-reachable; the only blocker
> was the unpanned cam) -- would prove the pan recipe generalizes and close the s53 candidate; (2) fold the
> cam screen + on-line re-park into `mint.py` as a first-class `mint_online` (both are scratch scripts
> today); (3) the standing camera-in-the-loop frontier (Phase R) remains the honest fix for approaches
> that CANNOT be pan-frozen. Every other thread (proven/mirror/sheathed clips DONE, walk-stab, Tetra
> push-aside/turnaround STANDALONE, 97-corner +493 push-steer-only) UNCHANGED.

> **PRIOR THREAD (2026-07-15, session 53): the 97-deg corner's reachability puzzle is RESOLVED WITH LIVE
> DATA -- its genuine dust is NOT reachable by a standard from-rest ROLL, and that is REAL GEOMETRY, not a
> sim over-correction. NOT "impossible" (the clip EXISTS; it needs a non-roll technique). Awaiting Dereck's
> strategic pick for the next target.** The session-52 crux (is the sim's 35u WallCorrect hold faithful near
> this concave corner, or an over-correction?) was answered LIVE: a clean-DTM roll toward the corner (facing
> 16306, seed=0, per-frame RAM read; NEVER advancewith) is **BIT-EXACT with the walled sim through the whole
> roll + wall-slide** -- Link's center is held at wallA_d==35.00 exactly as it grazes wallA, never closer.
> So the 35u roll hold is decomp-and-live ground truth here.
> - **The dust is roll-unreachable, rigorously.** The corner's only genuine dust hugs wallA at wallA_d
>   **2.79..5.43u** (15 f32 points, ~90-deg grazing aim); the live-faithful roll hold is 35u; a **500k+-
>   candidate f32 scan of the reachable mouth** (old >=33u from BOTH walls) across grazing aims 84.6..94.5deg
>   found **0 reachable genuine**. The dust sits ~30u inside the hold. A free roll (or walk -- same 35u
>   cylinder) can never place `old` there. This is the STANDARD-ROLL technique ruled out for THIS corner,
>   NOT the clip's existence: a wall-hugging clip position is the kind reached by PUSH-STEERING (the
>   standalone Tetra Co-push, which STEERS the lunge past the free-roll hold) or another mechanic.
> - **Locked live-data-backed:** immutable `fixtures/seam97_roll_wallhold_golden.json` + gate
>   `tests/test_seam97_clip.py::test_seam97_roll_wallhold_bitexact` (walled from-rest roll BIT-EXACT vs live
>   on every FRONT_ROLL frame; live hold min == 35.0). `test_seam97_clip_delivered` stays xfail-RED: the ROLL
>   path cannot deliver this corner. Angle 1 (relax `solver.wall_faithful` to bonk-only) is a correct
>   concave-corner model tidy but does NOT unblock (the 35u-held sliders it admits are non-genuine) -- left
>   unchanged (no passing use-case). Suite **369 passed, 1 skipped, 3 xfailed** (was 368; +1 = the wall-hold
>   gate). NO `sim.py`/`land.py`/`harness/rollstab/*.py` change (only tests + a fixture + KB), so the live
>   regression is unaffected.
>
> **REACHABILITY SCREEN WIRED IN (session 53, Dereck's steer -- "pick a different novel roll corner" + add
> a reachable-mouth screen): the shipped analytic locator is now the ONE accurate reachability oracle,
> shared by the CSV dump, region scans, AND the seamgeo layer.** `seam_locator.locate` was refactored into a
> geometry-first core `locate_geo(barrier_tris, ground_tris, S, wA, wB, override_link_y=, require_standable=)`
> (it settles a real WallCorrect-standable `old` + f32-verifies the clip FROM it); `locate` is now a thin
> region adapter over it (byte-identical -- the slow `test_seam_locator` guard + the `scan_all_dzb` CSV dump
> are unaffected). `SeamGeo.roll_reachable()` calls `locate_geo` DIRECTLY on the seam's own walls + flat
> floor (no region reload, no dict plumbing). This REPLACES the two weaker screens: the deleted
> `seam_feasibility.wall_reach` nearest-wall heuristic (false-NEGATED the proven seam) and the disp-floor
> proxy (`floor<=49.22`, which the 97-corner PASSED). Validated (gate `test_seamgeo.py::
> test_roll_reachable_screen`): it REJECTS the 97-corner (matches the live wall-hold finding) and ACCEPTS the
> proven + mirror seams (both roll-delivered). A kaze-r11 room scan (74 clippable of 159 seams) confirms the
> 97-corner is the only interior-97 corner rejected; its z-mirror at S=(13539.24,-493.36) IS locator-clippable
> (a candidate). Suite **370 passed** (+1). `disp` stays a deep-first upper bound (a non-None result proves a
> standable clip EXISTS; the precise roll-stab reach = `pred_genuine` at a `search_band` old).
>
> **NEXT (Dereck's pick, tooling now in place): choose a novel roll-reachable corner + deliver it.** Use
> `SeamGeo.roll_reachable()` (or `seam_locator` room scan) to pick a corner whose dust sits in the OPEN mouth
> (roll-reachable), MINT an anchor (the fixed-camera aligned-idle recipe), solve via the generalized path,
> DELIVER a clean-DTM 0-ULP clip. Candidate surfaced: the 97-corner's z-mirror (13539.24,-493.36). The
> 97-corner (+493) itself needs a non-roll (push-steer) technique. Every other thread (mirror/sheathed clips
> DONE, walk-stab, Tetra push-aside/turnaround STANDALONE) UNCHANGED.
>
> **PRIOR THREAD (2026-07-15, session 52): the 97-deg corner has a WALLED-REST-BIT-EXACT anchor and a
> clean solver run, but 0 wall-faithful hits -- an OPEN search/model gap, NOT an impossibility (Dereck's
> rule: `pred_genuine` verifies the clip EXISTS, so the search must find the reachable path). Handoff for
> a new session.** Target = the DISTINCT 97-deg corner S=(13539.24,493.36), walls 871x899, clippable at a
> ~90-deg GRAZING aim (facing 16306 at csangle 29883; geo `fixtures/kaze_r11_seam97_geo.json`, which now
> DECLARES `aim_deg=90`). Done this session (offline + live mint/verify; never advancewith for delivery):
> - **Anchor `kaze_r11_rollstab_seam97@twwgz` MINTED + WALLED-REST BIT-EXACT** (golden
>   `fixtures/seam97_rest_golden.json`; gate `tests/test_seam97_clip.py::test_seam97_rest_bitexact_walled`
>   GREEN). The camera is a FIXED room cam at csangle 29883 (frozen through idle+walk -- NO camera modeling
>   needed; Dereck's steer to use the initial-savestate camera). The mint needed a real fix: a NOVEL anchor
>   at a fixed-camera seam must be a GENUINELY aligned idle (`travel_angle` == facing) -- a teleport-rotated
>   idle inherits the base idle's `travel_angle` (33328) and arcs off-course into the south wall. Recipe
>   (works, verified): align-walk toward F -> settle to idle -> teleport-to-rest (preserves the aligned
>   idle) -> `mint_current`. The straight +X approach grazes wallA near the corner, so REST is bit-exact
>   only WITH walls (wall-less diverges ~row 24); the WALLED sim (walls=`seam.TRIS`) is 0-ULP every row.
> - **Off-bisector aim threaded cleanly via the FIXTURE.** `SeamGeo` now reads an optional `"aim_deg"` key
>   from the geo dict (else bisector default), so `rest`/`solver`/`deliver`/`seam_feasibility` all use the
>   90-deg aim from the fixture with NO per-CLI plumbing. Byte-identical for every existing seam (bisector
>   default unchanged; walkstab still passes its explicit `aim_deg`). Gate: `test_seamgeo`/`_seam_bands`/
>   `_solver_seam_param`/`_walkstab_seam`/`_mirror_roll_clip` all green.
> - **`seam_feasibility.py` gained a REACHABILITY screen** (`wall_reach`): of the genuine dust at an aim,
>   how much sits >= the roll's ~35u wall hold from both walls. Validates the lesson -- 97-corner 0/15
>   reachable (dust 2.8-5.4u off wallA), shipped mirror 12/35 reachable -- so a future novel-seam pick sees
>   "clippable but dust hugs a wall" up front instead of discovering it mid-solve (this session's surprise).
> - **`solve_focused` ran clean but found 0 wall-faithful hits** (`test_seam97_clip_delivered` xfail-RED,
>   strict). The reachability tension (the puzzle to resolve, see the dead-end ledger 97-deg STATUS): the
>   verified-genuine dust is confined <=5.4u in front of wallA (the razor runs ~parallel to the aim the
>   roll grazes along), while the walled roll holds Link's center 35u off wallA (WallCorrect `wall_r=35`),
>   pushing the roll ~30u off the razor before the CUT. A 108-sample x all-aims scan of the REACHABLE
>   corner mouth (>=35u from BOTH walls -- where the proven/mirror clips sit ~38-40u out) found 0 genuine.
> - Suite **368 passed, 1 skipped, 3 xfailed** (was 367/2; +1 pass = seam97 walled REST, +1 xfail = seam97
>   clip). Only `harness/rollstab/seamgeo.py` behavior changed (the fixture `aim_deg` default; byte-identical
>   for existing seams); NO `sim.py`/`land.py` change, so the live regression is unaffected.
>
> **NEXT (deliver the 97-deg corner -- resolve the search/model gap; do NOT conclude impossible):** two
> angles, both from Dereck's steers. (1) CONCAVE corners (this is one, interior 97) may TOUCH/SLIDE walls --
> only a BONK (`FRONT_ROLL_CRASH`) disqualifies -- but `solver.wall_faithful` rejects on ANY `wall_hit`
> (`solver.py:84`); relax it to reject only bonks (the 97 roll slides without bonking) and re-run
> `solve_focused`. (2) VERIFY the roll-near-concave-corner wall behaviour LIVE (unverified: the walk
> verification only reached ~x13290, before the corner) -- is Link really held 35u off wallA here, or does
> the concave WallCorrect let him closer? If closer, the dust is reachable and the sim is over-correcting.
> Repro: `python -m harness.rollstab.solver anchor=kaze_r11_rollstab_seam97@twwgz
> geo=fixtures/kaze_r11_seam97_geo.json seed=0 focused`. Every other thread (mirror/sheathed clips DONE,
> walk-stab, Tetra push-aside/turnaround STANDALONE) UNCHANGED.

> **CURRENT THREAD (2026-07-15, session 51): PHASE 5 IS DONE -- the NOVEL mirror-roll seam clip is
> DELIVERED LIVE, 0-ULP, pure-sim, no calibration. The "generalization works" proof is HIT: a seam the
> solver was never hardcoded to, solved by a reproducible <2-min pure-sim search and delivered via a clean
> DTM at seed=0.**
> - **The blocker (session 50's density wall) is BEATEN by the walkstab-style focused search, ported into
>   the roll path (`solver.solve_focused`).** Root cause, refined: for a NOVEL seam the reachable roll
>   `old` sits GROSSLY off the razor in perp (the mirror approach line is ~2.7u off the F-through-S line;
>   the proven kaze seam was already near its razor, so `search`'s fine knobs sufficed there). Closing that
>   needs the ARC (full-mag off-aim; the gross perp knob, octagon-SATURATING); threading the exact f32
>   column needs a byte-NUDGE of a start-crawl frame acted at LOW speed (spF < `NUDGE_SPMAX`=14, the
>   octagon INTERIOR -- Dereck's steer). NOTE the nudge is NOT smooth in the roll form (a low-speed
>   perturbation propagates through the whole cruise+roll -> a CHAOTIC reachable lattice); a genuine hit is
>   an isolated lattice point, found by sweeping the nudge grid + testing EXACTLY.
> - **`solver.solve_focused(anchor, seam)` NEW** (the objective-compliant one-shot; the freeze-solver
>   pattern): Phase A brackets arc(off,dur,lead)xA_proj ranked by how near `old`'s perp sits to a genuine
>   dust COLUMN in the reach band (`_genuine_perps`, PURE GEOMETRY -- the corner razor's perp offset is
>   derived, not a typed target, [[no-overtuned-constants]]); Phase B byte-nudges the low-speed start-crawl
>   frame; Phase C `wall_faithful` gate. It found a **margin-24** wall-faithful hit on the mirror in **85s**
>   (< 2 min): `old=(9072.0332031,-313.3167725) -> new=(9069.8251953,-264.1460876)`, disp 49.2202, CUT_F,
>   spF@A=17, facing=seam.F. Every knob derived or a documented physical regime; no per-seam constants.
> - **LIVE CLIP CONFIRMED 0-ULP** (`deliver ship geo=... golden=...`, clean DTM seed=0, C-down every
>   frame). Live `old`/`new` bit-for-bit == the sim (drift d(old)=(0,0)); proc 0x42 (CUT_F) at the cut then
>   proc 0x24 (OOB) THROUGH the mirror seam -- threads=True, behindA=True, behindB=True. Delivered twice,
>   deterministic.
> - **Delivery path threaded for the C-down camera pin.** `deliver.ship` now authors substickY=0 (the
>   free-cam pin) for a novel/seed-0 anchor (same rule `rest.main` uses; byte-identical csy=128 for the
>   proven anchors) -- else the auto-cam swings csangle off the frozen sim value and the clip misses. Added
>   a live-golden save (`golden=<path>`) so novel deliveries auto-lock an immutable regression.
> - **Locked live-data-backed:** immutable `fixtures/mirror_roll_ship_golden.json` (the clean-DTM run).
>   Gate `tests/test_mirror_roll_clip.py::test_mirror_clip_delivered` xfail-RED -> **GREEN** (the from-rest
>   sim on the shipped stream reproduces the live CUT_F old/new 0-ULP + OOB fall). Suite **367 passed, 1
>   skipped, 2 xfailed** (was 366; +1, mirror clip flipped). Only `harness/rollstab/{solver,deliver}.py`
>   behavior changed (kaze byte-identical -- `test_solver_seam_param`/`_seamgeo`/`_seam_bands`/`_sheathed_
>   roll_clip`/`_walkstab_clip` all green); NO `sim.py`/`land.py` change, so the live regression is
>   unaffected.
>
> **NEXT (deliver the 97-deg corner -- Dereck's target): the DISTINCT 97-deg corner S=(13539.24,493.36)
> (walls 871x899) IS roll-clippable, OVERTURNING session 50's "infeasible" ruling.** New tool
> `seam_feasibility.py` (the full-aim-circle f32 `pred_genuine` probe -- session 50 swept aim only
> `dir+-15deg` of the into-corner bisector and MISSED the gap): the clip sits at a ~90-deg GRAZING aim
> (facing **16384**, ~41deg off the bisector 131.5), an 18-26-point f32 razor (along d2S 25..49, perp
> -0.048..-0.094, all in_front; precise, as Dereck expected from the 91-deg Tetra corner). Geo
> `fixtures/kaze_r11_seam97_geo.json` (regen `make_seam_geo wallA=871 wallB=899`). TO DELIVER: (1) build
> the SeamGeo with `aim_deg~=90` (NOT the default bisector -- the s48 per-seam-aim mechanism; the clippable
> aim is off-bisector like a near-flat seam's bear_to_S); (2) MINT an anchor aiming ~90deg at this corner
> (`mint.mint_novel`, camera+C-down recipe as the mirror), verify REST BIT-EXACT; (3) `solve_focused` (it
> threads exactly this precise razor) -- OPEN UNKNOWN: wall-faithful REACHABILITY of the ~90-deg-aim `old`
> (needs the anchor to check); (4) `deliver ship geo=... golden=...` -> live 0-ULP. Secondary Phase-5 tidy:
> wire `thrust_scan._matches`'s kaze guard drop -> SeamGeo-per-enumerated-seam. Every other thread
> (mirror/sheathed clips DONE, walk-stab, Tetra push-aside/turnaround STANDALONE) UNCHANGED.

> **PRIOR THREAD (2026-07-15, session 50): Phase 5 IN PROGRESS -- a NOVEL seam (the mirror-roll
> corner) has a fresh live-minted anchor that is REST BIT-EXACT, and two real generalization bugs are
> fixed; the LIVE CLIP is NOT yet delivered (blocked on the octagon-clamp dust-density wall). OFFLINE +
> live mint/verify; suite 366 green (+1).**
> - **Target = the MIRROR-ROLL corner** S=(9069.9043,-265.9138), interior 109.4, walls 355x357 (a
>   genuinely distinct seam from the proven roll seam at +259, mirrored across z). Dereck first picked the
>   distinct 97deg corner S=(13539.24,493.36); a **dedicated search proved it NOT roll-clippable** (no
>   CrrPos-missing gap at any disp -- `disp_floor<reach` is NECESSARY, not SUFFICIENT; wall 899 extends
>   away from the roll dir so the roll exits both finite wall segments). New dead-end ledger entry.
> - **`make_seam_geo.py` NEW** (generalized geo-fixture builder from the block-grid ordered mesh;
>   auto-gathers the CrrPos barrier by GATHER_R + band-overlap in game order). `fixtures/kaze_r11_seam_
>   mirror_geo.json`. The mirror seam is FEASIBLE: 74 f32 `pred_genuine` dust hits (~ the proven 95).
> - **Anchor `kaze_r11_rollstab_mirror@twwgz` MINTED + REST BIT-EXACT** (golden `fixtures/mirror_roll_
>   rest_golden.json`, 30 rows, pos+d/w+m359C 0-ULP). Live-mint procedure (camera behind Link WITHOUT
>   the L button -- not wired live -- via C-stick pan + a walk-settle past the free-cam leash pull;
>   deliver at seed=0). Gate `tests/test_mirror_roll_clip.py::test_mirror_rest_bitexact` GREEN.
> - **Two real Phase-5 solver bugs fixed (kaze byte-identical, gates green):** (a) `solver.run` aimed the
>   approach at the hardcoded `geometry.F` -> now aims `seam.F` (a novel seam was walked the WRONG way);
>   (b) the hardcoded A_projs are anchor-DISTANCE specific -> NEW `solver._derive_a_projs` brackets the
>   reach band per anchor (the mirror at 555u needs different thresholds than the proven at 748u).
> - **Delivery path HARDENED for novel seams (so the next session isn't re-blocked):** `rest.py`
>   (`sticks_of`/`main`/`verify_rest`) + `deliver.py` (`gate`/`ship`, new `_seam_for`) + `mint.py`
>   (new `mint_novel` = the camera-behind mint procedure as one call) now thread a `seam=`/`geo=`
>   (byte-identical for the kaze default). `rest`/`deliver` CLIs take `geo=<fixture>` (+ `rest` `seed=`);
>   `mint_novel` encodes teleport + C-stick camera pan + walk-settle. These were the traps this session
>   hit in scratch -- the proven anchors were unaffected (all gates green).
> - **BLOCKED (the clip): the cold search finds 0 genuine** -- the same octagon-clamp reachable-lattice
>   DENSITY WALL as the sheathed roll (dead-ends #29/#32): the fine perp knob collapses to ~27 distinct
>   bytes. `solver.py` lacks the walkstab K=3-byte densifier (session 32); the proven/sheathed roll clips
>   used FOCUSED WARM-START recipes, not a cold drill (over-budget). `test_mirror_clip_delivered` RED
>   (strict-xfail). Suite **366 passed, 1 skipped, 2 xfailed** (was 365; +1). NO `sim.py`/`land.py` change.
>
> **NEXT (deliver the mirror clip = the Phase-5 live proof):** get a genuine wall-faithful hit on the
> mirror seam, then DELIVER it via a clean DTM (seed=0) and confirm live 0-ULP. To beat the density wall
> either (1) PORT the walkstab `solve_focused` K=3-byte-nudge densifier into `solver.py`'s roll path (the
> principled fix -- `start_family`'s msd combos octagon-collapse), or (2) develop a mirror focused
> warm-start recipe as the proven/sheathed clips did. Then flip `test_mirror_clip_delivered` GREEN and
> add a ship golden. Remaining Phase-5 tidy: wire `thrust_scan` dispatch to build a SeamGeo per enumerated
> seam (the `_matches` guard drop) once delivery works. Every other thread UNCHANGED.

> **PRIOR THREAD (2026-07-15, session 49): the Phase-5 PREREQUISITE is DONE -- the solvers' last
> kaze-hardcoded numeric ranges are now DERIVED per-seam, with candidate REACHABILITY decided by a real
> walled physics re-sim rather than a typed-in `old_z` band (Dereck's call; OFFLINE, suite 365 green).**
> This clears the blocker Phases 3-4 deliberately left for a NOVEL seam to solve. Done this session
> (offline; 1 in-budget `solve_focused` + a short roll `search` smoke run, no live Dolphin run):
> - **Reachability is decided by PHYSICS, not a typed near-edge (Dereck chose this over a derived-span
>   or padded band).** The kaze `solver.py` `ZLO/ZHI = 302.6/308.2` old_z band was really a proxy for
>   the dead-end-#3 guard (reject an `old` the WALL-LESS roll overshot into). It is DELETED; the
>   recording gate is now `genuine and clear and wall_faithful(...)`, where new `solver.wall_faithful`
>   replays the candidate's exact stream through a WALLED `rest_state` and accepts only if the roll
>   reaches `old` bit-for-bit with no `wall_hit` before the CUT. This is the SAME walled re-sim
>   `walkstab._wall_faithful` (Phase C) already used -- the two solvers now share one physics guard, no
>   typed boundary. Verified: it ACCEPTS the shipped seed-0 roll hit (old bit-exact, no wall stop) and
>   REJECTS a fabricated unreachable `old`.
> - **The FAR edge + search windows are DERIVED from the lunge reach (`SeamGeo`).** New `SeamGeo.reach`
>   / `reach_at(speedf)` (the cut displacement, from `cut_new`, no pasted distance) and `search_band()`
>   (a general seam-INDEPENDENT relative bracket `[reach*0.80, reach*1.02]` -- the same rule for every
>   seam, not per-case constants). The reachable band's near edge is a reachability limit (the wall
>   braking the approach), NOT geometry -- confirmed by a fine scan (the geometric genuine region runs
>   all the way to the seam vertex for BOTH seams) -- so a generous relative window + the physics guard
>   is the honest split.
> - **`walkstab.solve_focused`'s `d2S`/N windows + perp gate are DERIVED (`bounds()`).** WIN_LO/HI =
>   `sg().search_band(speedf=17)`; the N window is the frame range where the baseline cruise walk's d2S
>   enters the reach band, widened for the crawl start-delay (derived from the baseline trajectory);
>   the perp pre-filter is a small general multiple of reach (~the f32 razor). The pasted `WIN_LO/HI
>   =34.5/40.35`, `NLO_F/NHI_F=10/15`, `34.0..40.5`, `PERP_GATE_F=0.006` are GONE.
> - **The `solver.py` drill `_dust_cache` box is DERIVED, not the kaze `x 9071.5..9072.7 / z
>   302.6..308.2`.** It now centers on the sim's baseline roll landing (`r0['old']`) with extents from
>   the seam's reach band, capped -- a region built from the search's own reachable samples + geometry.
> - **GATE PASSED (both halves).** The kaze roll + walk seams still reproduce their shipped hits
>   bit-exact (`test_solver_seam_param`/`test_walkstab_clip`/`_rest`/`_seam` all green), and the SEARCH
>   still finds them under the derived ranges: `solve_focused` found **4 wall-faithful genuine hits in
>   60.1s** (< 2 min; top margin 17, N=13), and the roll `search` runs the physics gate end-to-end
>   (baseline fires, 1261 runs/12s, no error). NEW `tests/test_seam_bands.py` (6 green) locks the
>   derivations (reach/band camera-and-`roll_speedf`-dependent, windows bracket the shipped hits,
>   `wall_faithful` accepts the shipped hit + rejects an unreachable `old`). Suite **365 passed, 1
>   skipped, 2 xfailed** (was 359; +6). NO `sim.py`/`land.py` change (live regression unaffected); the
>   roll/tetra solvers stay byte-identical at their defaults (the band change only affects which hits a
>   full `search` RECORDS, not stream recomposition, so all bit-exact gates hold).
>
> **NEXT (the live "generalization works" proof -- Phase 5 proper):** drop `thrust_scan._matches`'s
> kaze guard, dispatch a NEW enumerated seam to the generalized standard-roll path, MINT an anchor
> there (`mint.py`), solve via the generalized solver (now range-free per-seam), and DELIVER a
> clean-DTM 0-ULP clip -- the real proof. All the per-seam numeric prerequisites are now in place; the
> remaining work is the enumeration/dispatch + the mint + the live delivery. Every other thread
> (sheathed clip DONE, walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 48): generalization Phase 4 DONE -- `walkstab.py` is THREADED
> through `SeamGeo`; its private acceptance duplicates are ABSORBED, and its thrust facing + crawl-window
> center are DERIVED, not pasted (OFFLINE, GATE PASSED, suite 359 green).** Continues session-47 Phase 3.
> Done this session (offline; 1 in-budget `solve_focused` run, no live Dolphin run):
> - **`walkstab.py` acceptance is now the shared `SeamGeo`.** `in_front`/`genuine_clip`/`perp_ray`/
>   `fast_cut` DELEGATE to a walk-stab `SeamGeo` instance (`sg()`, built from the new geo fixture +
>   anchor csangle); the private `WALLA`/`WALLB`/`TRIS`/`_mk`/`_pfunc`/`cut_lunge_const` and the pasted
>   `LINK_Y`/`SEAM` literals are GONE. `SEAM`/`LINK_Y` are now sourced from the fixture at FULL f32
>   precision (was `z=1385.858`/`link_y=-6534.329`, rounded; verified the precise values give a
>   byte-identical `genuine_clip` verdict, since the seam faces are near-vertical). `genuine_clip` keeps
>   its `(ok, why)` signature with the boolean byte-identical to the pre-SeamGeo copy.
> - **NEW walk-stab geo fixture + reproducible builder.** `fixtures/kaze_r11_walkstab_geo.json`
>   (`make_walkstab_geo.py`, offline from the ordered DZB mesh): wallA/wallB = polys 803/802, the ordered
>   CrrPos barrier `tris = [801,803,802,804,798,800]` (the r=35 sweep chain the shipped solver used), S =
>   the precise shared floor vertex, interior 168.968, link_y precise.
> - **F is DERIVED from `bear_to_S`, NOT the corner bisector** (Dereck-confirmed the per-seam aim
>   source). This seam is nearly FLAT (interior 169 deg): it is clipped by GRAZING toward S, so its
>   thrust facing = `derive_F(bear_to_S)` == **5625 bit-exact** (the shipped threading facing). The corner
>   bisector (~19.4 deg) would give a different facing (3576) -- wrong for a flat seam. `SeamGeo` gained a
>   per-seam `aim_deg=` (default = the fixture bisector, so CORNER seams like the roll are unchanged;
>   walk-stab passes `aim_deg=bear_to_S`). `solve_focused`'s `cruise_beta` now defaults to `bear_to_S`
>   (was the pasted `CRUISE_BETA=5556`; deleted).
> - **`SeamGeo` generalized (roll path byte-identical).** `cut_new`/`pred_genuine` take optional
>   `facing=`/`speedf=` (default the roll F + `roll_speedf`; walk-stab passes the runtime walk facing +
>   per-frame nspeed, since its lunge speed is the walk speedF, not the roll cap) -- bit-identical to
>   `enter_cut`. New `perp_to_ray(old,new)` (the exact ray-vs-S razor, walk-stab's `perp_ray`). `TRIS`
>   now comes from the fixture's explicit `tris` when present, else the legacy `[wA,wA,wB]+barrier`
>   composition (the roll fixture has no `tris` -> unchanged).
> - **GATE PASSED + `solve_focused` still finds hits.** The shipped walk-stab clip reproduces bit-exact
>   (`test_walkstab_clip.py`/`test_walkstab_rest.py` 9 green). `solve_focused` with the DERIVED crawl
>   center (`bear_to_S=5584`) found **2 wall-faithful genuine hits in 79.9s** (< 2 min; top margin 17,
>   facing 5625, speedF 17). NEW `tests/test_walkstab_seam.py` (5 green): F-from-bear_to_S (== 5625, NOT
>   the bisector), F-camera-dependent, geometry-from-fixture (ordered tris + precise S/link_y), shipped
>   verdict via SeamGeo, `fast_cut`==`enter_cut` 0-ULP. Suite **359 passed, 1 skipped, 2 xfailed** (was
>   354; +5). NO `sim.py`/`land.py` change (live regression unaffected); the roll/tetra solvers
>   (`test_seamgeo`/`test_solver_seam_param`/`test_tetra_solver`) still byte-identical.
>
> **NEXT (per the session-45/46/47 handoffs, OFFLINE until the Phase-5 live close): Phase 5 --** drop
> `thrust_scan._matches`'s kaze guard, dispatch a NEW enumerated seam to the generalized standard-roll
> path, MINT an anchor there (`mint.py`), solve via the generalized solver, and DELIVER a clean-DTM 0-ULP
> clip (the real "generalization works" proof). **Phase-5 prerequisite (deliberately left by Phases 3-4):
> the solver still carries kaze-specific numeric ranges** -- `solver.py`'s `ZLO/ZHI = 302.6/308.2` (roll
> old_z clear band) and the drill `_dust_cache` bounds (`x 9071.5..9072.7`, `z 302.6..308.2`), and
> `walkstab.solve_focused`'s hardcoded `d2S`/N windows (`34.0..40.5`, `NLO_F/NHI_F=10/15`) + the perp
> gate. These must be DERIVED per-seam (from the seam's along/perp band) before a novel seam solves;
> threading them onto `SeamGeo` is the natural Phase-5 companion. Every other thread (sheathed clip DONE,
> Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 47): generalization Phase 3 DONE -- `SeamGeo` is THREADED
> through `solver.py`; the module-global `geometry as G` is GONE from the solver (OFFLINE, ZERO behavior
> change, suite 354 green).** Continues the session-46 Phases 1-2. Done this session (offline, no live run):
> - **`solver.py` takes a per-seam `seam=` param** on `run`/`base`... `search`/`start_family`/`fine_family`/
>   `arc_family` (default `None` = the kaze r11 seam `geometry.SEAM`, a `SeamGeo` instance). Every
>   `G.X` is now `seam.X`: `G.along`/`B_BTN`/`A_BTN`/`KROLL`/`genuine_clip`/`seg_blocked`/`perp` in `run`,
>   the `r['facing'] != G.F` accept gate -> `seam.F`, and the drill dust cache `G.pred_genuine` ->
>   `seam.pred_genuine`. The family aim `F` defaults from `seam.F` (was `G.F`). `import geometry as G` is
>   DELETED from the solver -- it now imports only `geometry.SEAM` (the kaze default instance) + the
>   `load_seed` anchor helper. **csangle stays anchor-sourced** (`load_seed(anchor)['csangle']`, unchanged):
>   it is the camera yaw for decoding sticks, genuinely per-anchor, and `solver_tetra`'s `F=GT.F` family
>   reuse depends on it -- so it is NOT bound to the seam (all kaze anchors share csangle 29883 anyway).
>   `geometry.py` gains a public `SEAM = _SEAM` handle; still a byte-identical shim.
> - **GATE (Phase 3) PASSED:** the shipped seed-0 kaze hit (`_generated/rollstab_hits.json[0]`,
>   `old=(9072.2089844,308.0280762)`) recomposes BIT-FOR-BIT via the parameterized path, both `seam=None`
>   (default) and `seam=geometry.SEAM` (explicit), down to identical stream bytes ->
>   `new=(9069.8886719,258.8625793)`, facing 33295, genuine+clear.
> - **Regression `tests/test_solver_seam_param.py` (3 green):** shipped-hit-bit-exact-via-explicit-seam
>   (== default byte-identical), seam-honored-by-families (a shifted-yaw `SeamGeo`'s different `F` moves
>   `start_family`'s aim -- guards against a reintroduced module-global hardcode), default-seam-is-kaze.
>   Suite **354 passed, 1 skipped, 2 xfailed** (was 351; +3). NO `sim.py`/`land.py` change, so the live
>   sim-vs-Dolphin regression is unaffected; `solver_tetra`/`thrust_scan`/`deliver` callers unchanged
>   (default seam = byte-identical; `test_tetra_solver`'s `F=`-family reuse still green).
>
> **NEXT (per the session-45/46 handoffs, OFFLINE until the Phase-5 live close):** Phase 4 -- generalize
> `walkstab` the same way (absorb its PRIVATE acceptance duplicates into `SeamGeo`; derive the settled
> thrust facing from the bisector like `F`; derive the crawl-window center from `bear_to_S`, not
> `CRUISE_BETA`) -- GATE: reproduce the shipped walk-stab clip bit-exact. Then Phase 5 -- drop
> `thrust_scan`'s `_matches` kaze guard, dispatch to a NEW enumerated seam, MINT an anchor there, solve
> via the generalized path, DELIVER a clean-DTM 0-ULP clip (the real "generalization works" proof). NOTE
> for Phase 5: the solver still carries kaze-specific numeric ranges that Phase 3 deliberately left alone
> (the `ZLO/ZHI = 302.6/308.2` old_z band and the drill `_dust_cache` x/z bounds `9071.5..9072.7` /
> `302.6..308.2`) -- these must be DERIVED per-seam (from the seam's along/perp band) before a novel seam
> solves. Every other thread (sheathed clip DONE, walk-stab clip, Tetra push-aside/turnaround, thrust
> scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 46): the SOLVER GENERALIZATION is BEGUN -- Phases 1-2 of the
> session-45 kickoff are DONE + green (OFFLINE, ZERO behavior change).** Dereck scoped this: the Tetra
> push clip (`geometry_tetra`/`solver_tetra`/`pushaside`/`turnaround`) is a STANDALONE, single-seam solver
> and stays separate; the generalization is for STANDARD roll/wall clips (`geometry.py` + `solver.py` +
> `walkstab.py`). Done this session:
> - **`SeamGeo` abstraction built (`harness/rollstab/seamgeo.py`).** A per-seam roll/wall-clip geometry +
>   exact-acceptance object, DERIVED from a geo fixture + the anchor camera yaw. `geometry.py` is now a
>   THIN instance-backed shim over it (loads the kaze r11 fixture, builds `SeamGeo`, re-exports the whole
>   `G` surface -- `F`/`LUNGE`/`TRIS`/`genuine_clip`/`pred_genuine`/`perp`/`along`/...). Both of SeamGeo's
>   inputs come from STATE, not pasted constants -- exactly what a live tww-python Dolphin feed will supply:
>   the seam geometry from the room's DZB collision (the fixture was built from live RAM by
>   `capture_walls.py`) and the camera yaw from Link's `csangle` (READ from the canonical kaze anchor's
>   rest snapshot, not hardcoded). The full suite is BYTE-IDENTICAL (346 pre-existing passed, unchanged;
>   the razor accept in `solver.run` already used the real sim cut, not `G.LUNGE`).
> - **F is DERIVED, not pasted (`seamgeo.derive_F`).** F = the walk want-target (m34E8) of the
>   closest-reachable full-deflection stick to the interior `bisector_deg` at csangle
>   (`stick_for_bearing(bisector, csangle, 1.0)` -> decode -> `+0x8000+csangle`). GATE: derived F == 33295
>   bit-exact at the kaze roll seam (csangle 29883); `test_F_is_camera_dependent` proves it moves with the
>   camera (no reintroduced literal). The pasted `F = 33295` is deleted.
> - **The cut LUNGE is DERIVED per-candidate, not a frozen delta.** `SeamGeo.cut_new(old)` computes the
>   CUT_F entry endpoint from the CUT anim's joint-0 root translate at F + the roll speedF (26) lunge term,
>   BIT-IDENTICAL to `LandState.enter_cut` (gated `test_cut_new_matches_enter_cut_bit_exact`, 4 olds
>   spanning the band, 0-ULP). This deletes the pasted `LUNGE = (-2.32.., -49.16..)`: the old literal was
>   an approximation extracted at ONE `old` (the shipped hit's ~9072), and (the audit found) the two
>   geometry modules' LUNGE literals were even extracted at DIFFERENT `old` conventions (kaze at the
>   shipped old, tetra at origin) -- computing per-`old` removes that drift entirely. Verified: the new
>   per-`old` `pred_genuine` gives IDENTICAL genuine verdicts to the old frozen add over the entire
>   337,200-point dust-cache region + the deliver sliver points (0 mismatches). `LUNGE` remains exposed as
>   an origin-referenced derived property (magnitude 49.2202, the roll-stab reach) for compatibility.
> - **Regression `tests/test_seamgeo.py` (5 green)** locks F-derived-bit-exact, F-camera-dependent,
>   cut_new==enter_cut 0-ULP, shim-is-instance-backed (verdicts identical over the dust band), and the
>   reach magnitude. Suite **351 passed, 1 skipped, 2 xfailed** (was 346; +5 new). NO `sim.py`/`land.py`
>   change, so the live sim-vs-Dolphin regression is unaffected.
>
> **NEXT (per the session-45 handoff, OFFLINE until the Phase-5 live close):** (3) thread `SeamGeo` through
> `solver.run`/`base`/`search`/families (replace the module-global `G`; `!= G.F` gate -> `seam.F`; the
> drill cache -> `seam.pred_genuine`) -- GATE: re-solve the kaze roll seam via the parameterized path,
> reproduce the shipped seed-0 hit bit-exact. (4) Generalize `walkstab` the same way (absorb its PRIVATE
> acceptance duplicates into SeamGeo; derive the settled thrust facing from the bisector like F; derive the
> crawl-window center from `bear_to_S`, not `CRUISE_BETA`) -- GATE: reproduce the shipped walk-stab clip.
> (5) Drop `thrust_scan`'s `_matches` kaze guard, dispatch to a NEW enumerated seam, MINT an anchor there,
> solve via the generalized path, DELIVER a clean-DTM 0-ULP clip -- that live clip on a novel seam is the
> real "generalization works" proof. Every other thread (sheathed clip DONE, walk-stab clip, Tetra
> push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 44): the SHEATHED ROLL-STAB CLIP IS DELIVERED LIVE, 0-ULP,
> pure-sim, no calibration.** The session-43 blocker (the session-39 hit "doesn't survive seed=0") was
> NOT a density wall to grind past -- it was a GENERAL seed-0 crawl-composition bug, fixed structurally
> (no tuned constants). Done this session (offline + 2 live clean-DTM runs -- 1 ship + 1 golden capture,
> never advancewith):
> - **ROOT CAUSE nailed + fixed GENERALLY (dead-end #35's "NEXT" step 1).** Under `dtm_seed=0` the game
>   delivers one FEWER leading neutral poll, so `rest_state` burns one MORE leading no-op
>   (`noops = rest_noops + (1 - dtm_seed)`, measured live s43). That extra no-op was silently EATING the
>   start-crawl's first frame `start[0]` (a dead no-op absorbs it), so every crawl-based search composed
>   one frame short under seed=0 -- exactly why the s43 re-solve "hit a density wall". The fix
>   (`solver.run`): prepend `(1 - dtm_seed)` neutral ABSORBER frames so `start[0]` always lands on the
>   first LIVE frame. The absorber is a FULL frame (a `polls` multiple), so seed-0's correct sub-frame
>   poll phase is PRESERVED (unlike a seed neutral = 1 poll). seed=1 => 0 absorbers => byte-identical.
> - **The session-39 recipe, RE-COMPOSED under `dtm_seed=0`, is genuine bit-for-bit AND ships.** This is
>   NOT the ruled-out "deliver the s39 BYTES via seed=0" (#35: replaying the seed=1 bytes with no
>   absorber lands +0.588u off-razor). Re-composing produces DIFFERENT bytes (absorber prepended) that
>   compose correctly for seed=0 delivery: `run(..., dtm_seed=0)` reproduces
>   `old=(9072.2089844,308.0280762) -> new=(9069.8886719,258.8625793)`, disp 49.2202, CUT_F, spF@A=17,
>   genuine+clear+sliver-robust -- bit-identical to the seed=1 sim. The general fix, applied to the
>   existing derived recipe, delivered it; no bespoke/tuned solver.
> - **LIVE CLIP CONFIRMED 0-ULP.** `deliver ship` (auto seed=0 from the hit's `dtm_seed`) played a clean
>   DTM: live `old`/`new` bit-for-bit == the sim (drift d(old)=(0,0)), proc 0x42 (CUT_F) at the cut then
>   proc 0x24 (OOB) -- threads=True, behindA=True, behindB=True. The scanner now routes a NOT-DRAWN
>   (sheathed) anchor's ROLL verdict end-to-end to a live clip (the milestone's "done").
> - **Locked live-data-backed:** immutable game_frame-tagged golden
>   `fixtures/sheathed_roll_ship_seed0_golden.json` (captured from the successful ship). Gate
>   `tests/test_sheathed_roll_clip.py`: `test_sheathed_ship_delivery` RED-xfail -> **GREEN** (sim bit-exact
>   vs the seed-0 golden on every game_frame-aligned row THROUGH the CUT_F entry; the post-cut OOB fall
>   proc 0x24 is the known-unmodeled CUT tail, moot for the clip); NEW `test_seed0_crawl_frame_acts`
>   locks the general fix (seed-0 stream carries one absorber, crawl composes seed-invariantly);
>   `test_seed1_delivery_drops_band` keeps the #34 seed=1 drop gated (xfail). `test_s39_hit_not_genuine_
>   under_seed0` (s43) still PASSES -- the raw seed=1 bytes are correctly still not seed-0-deliverable
>   (re-composing, not byte-replay, is the fix). Suite **346 passed, 1 skipped, 2 xfailed**. Only
>   `harness/rollstab/solver.py` behavior changed (the absorber; seed=1 byte-identical) -- NO
>   `sim.py`/`land.py` change, so the live sim-vs-Dolphin regression is unaffected.
>
> **NEXT (the clip is DONE; remaining is polish, not blocking):** (1) OPTIONAL -- fold the seed-0 solve
> into the harness as a reproducible <2-min search: the generic `solver.search`/drill under seed=0 is
> still over-budget and does NOT reach the f32 dust on its own (a real property of the seam -- the derived
> recipe came from session 39's focused warm-start, now made deliverable by the general fix). A reproducible
> focused solve (warm-started, no tuned constants) would close the objective's "found by the search"
> clause; the CLIP itself is delivered. (2) The generalize-off-hardcoded-kaze-seam work (thrust_scan
> dispatch to any enumerated seam) stands. Every other thread (walk-stab clip, Tetra push-aside/turnaround,
> thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 43): the make_dtm seed=0 delivery fix is PLUMBED end-to-end and
> its from-rest model is MEASURED LIVE + bit-exact -- but shipping is BLOCKED on a RE-SOLVE: the
> session-39 hit does NOT survive seed=0, and re-solving hits the sessions-39/40 f32-dust density wall.
> No sim/physics behavior changed; all `seed`/`dtm_seed` plumbing is byte-identical at the seed=1
> default (suite 342 passed, unchanged).** This was session-42 NEXT (ship the fix). Done this session
> (offline + 1 live jitter-immune capture_walkentry seed=0, never advancewith):
> - **`seed`/`dtm_seed` threaded end-to-end** (additive, default 1 = byte-identical): `rest.rest_state
>   (dtm_seed=, noops=)`, `capture_walkentry.capture(seed=)`, `solver.base/run/search(dtm_seed=)` +
>   `_record` tags each hit's `dtm_seed`, `deliver.gate/replay/ship` read the hit's `dtm_seed` and
>   author the DTM with it. The `run_dtm`/`make_dtm` `seed` param already existed.
> - **The seed-0 leading-poll layout is MEASURED, not guessed (handoff step 2 DONE).** Captured the
>   seed-0 walk-entry live (jitter-immune, game_frame-tagged) and diffed the sim d_frame-aligned vs the
>   seed-1 golden: seed=1 => noops=1 (28/0 bit-exact, byte-identical to before), **seed=0 => noops=2
>   (28/0 bit-exact, dz=0 every aligned row)**. So the coupling is `noops = rest_noops + (1 - dtm_seed)`
>   (fewer leading neutral polls => the game's rest blend advances one MORE frame before the plan, so
>   the sim needs one MORE leading no-op -- the OPPOSITE sign of the intuitive guess). Immutable golden
>   `fixtures/sheathed_walkentry_seed0_golden.json`; gate `tests/test_sheathed_roll_rest.py::
>   test_sheathed_rest_bitexact_seed0`.
> - **The `solver.fine_family` band-exclusion is REMOVED (handoff step 4a):** band fines (msd 0.889-1.0)
>   are usable again under seed=0 (delivery faithful). NOTE they are an ALONG knob (the speedF dip), not
>   perp, and near-cap ones octagon-clamp -- so they did NOT break the perp density wall below.
> - **LOAD-BEARING NEGATIVE RESULT: the session-39 hit does NOT clip under seed=0.** Replaying its exact
>   stream bytes through the (measured-correct) seed-0 model, `old` shifts **+0.588u in z (308.028 ->
>   308.616), off the f32 razor -> NOT genuine** (behind neither wall). So the handoff's hope that "the
>   s39 hit should clip" under seed=0 is DISPROVEN; a fresh seed-0 solve is REQUIRED (gate
>   `test_s39_hit_not_genuine_under_seed0`). [Mechanism: seed-0's extra leading no-op shifts the whole
>   from-rest approach; the dust is single f32 columns, so any along-shift lands off-razor.]
> - **The re-solve hits the sessions-39/40 f32-DUST DENSITY WALL (open).** ~several-thousand-run focused
>   sweeps under seed=0 (arc gross-perp -> |rho| 0.017 collapses because full-mag arcs octagon-clamp;
>   partial interior 3rd-crawl-byte fine-perp -> ~2e-4 steps but a DEAD-BAND GAP over rho=0; A_proj/sub-
>   band along fines -> coarse z, few distinct sticks at bearing F; partial-mag arc -> 0.033 worse)
>   reached **~0.0035u nearest, 0 genuine** -- mirroring session 40's 0.0013u wall. The lattices tried
>   don't align onto a genuine column. This is the SAME frontier that consumed sessions 39-40; the
>   generic `solver.search` drill is over-budget (>2min) and under-samples.
>
> **DEEPER ROOT CAUSE + anti-overtuning course-correction (session 43, later in the session):** the
> re-solve difficulty is NOT a constant-tuning problem -- it is a GENERAL seed-0 CRAWL bug. Under
> `dtm_seed=0` the leading no-op count is 2, so `rest_state`'s seed step eats noop #1 and **the FIRST
> start-crawl frame (`start[0]`) is eaten as a dead no-op** -- so any crawl-based search under seed=0
> silently loses its first crawl frame (this is almost certainly why the existing derived search
> under-performed under seed=0, NOT its constants). Verified knob roles (Dereck's hint): the ACTED crawl
> MAGNITUDE is the fine along/z fill (an acted crawl frame's magnitude walks `old` z across ~298.5..308.5
> in fine steps); partial-INTERIOR crawl BEARINGS give continuous perp (|rho|->0.0007); `A_proj` is COARSE
> (the fixpoint crossing pins the along-position -> A_proj only selects the ~16u walk-step, NOT the
> sub-step fill). A prototype `solve_focused` with hand-tuned bearing/magnitude/A_proj grids was built and
> DISCARDED as calibration-flavored drift (Dereck flagged the overtuning). dead-end #35 (expanded).
>
> **NEXT (the principled, least-tuning path -- delivery fix + live-measured model are DONE and locked;
> only the seed-0 solve remains):** (1) fix the seed-0 leading-dead-frame GENERALLY at
> `run()`/crawl-composition (so `start[0]` is not silently dropped) -> every DERIVED family
> (`start_family`/`arc_family`/`fine_family`, already parameterized off csangle + the movement-gate band,
> no magic constants) composes correctly under seed=0; (2) run the EXISTING `solver.search`/catalog under
> `dtm_seed=0` (do NOT hand-tune a bespoke per-seam solver); (3) if it still can't reach the f32 dust in
> <2 min, that is a real finding about the seam, not something to paper over with tuned constants. Then
> `deliver ship` (auto seed=0 from the hit's dtm_seed) -> live OOB clip -> flip `test_sheathed_ship_
> delivery` GREEN. Validate any hit with `capture_decode.delivery_sweep` (every fine received + roll-row
> unchanged + OOB). Every other thread (walk-stab clip, Tetra push-aside/turnaround, thrust scanner)
> UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 42): the sheathed-clip row-18 blocker is RAM-CONFIRMED as a
> `make_dtm` DELIVERY DROP -- NOT a physics/decode gap, and NOT the "band walk-speed" of #33 (overturned).
> The game never RECEIVES the row-18 band fine; make_dtm's default `seed=1` poll phase drops it. The fix
> is characterized live (`seed=0` + re-derive `rest_noops`) but NOT yet shipped. No sim/physics code
> changed.** Following Dereck's steer to READ THE PAD FROM RAM (not infer it), done this session
> (decomp trace + ~7 live DTM captures reading `g_mDoCPd_cpadInfo[0]`, never advancewith):
> - **Decomp EXONERATES the physics + decode (traced, not assumed).** Every row-18-path function matches
>   the sim line-for-line (`setStickData` 10569, `setNormalSpeedF` 2301 -- the `msd^2*max` decel is
>   UNCONDITIONAL once below nspeed, `setSpeedAndAngleNormal` 2751, `setBlendMoveAnime` m3598, the 0.3/0.7
>   toe recursion 2399-2484); `PADRead->PADClamp->CStick::update->mMainStickValue` is stateless. So IF the
>   game received `(96,192)` (msd 0.9605) it MUST decel -- there is nothing to "model" (kills #33).
> - **The decode is faithful even for Y>=192 when ISOLATED.** A 1-frame `(96,192)` after plain cruise
>   delivers `cpad_val=0.9605` == the sim and dips (`transient_probe`). So no band-walk-speed gap exists.
> - **In the SHIP the band fine is DROPPED (RAM-confirmed).** At fed-index 16 (acted row 18) the game polls
>   the FULL neighbour: `cpad_val=1.0, (px,py)=(-0.32,0.95)` = the `(77,249)` stick, not `(96,192)`. A
>   distinctive px=0 marker at fed-16 ALSO drops (positional, value-independent); an all-full ramp delivers
>   every frame; the ship's other fines (0.9313/0.7848/0.8784) DO deliver -- so a CLUSTER of preceding
>   partials induces a poll-phase slip that drops a later 1-frame partial. That one dropped dip is the
>   ENTIRE 1.9125u miss (offline: forcing row-18 to full shifts along-track by exactly -1.91248u).
> - **`make_dtm`'s poll cadence is the cause; `seed` controls it (live sweep, `delivery_sweep`):**
>   `(polls=4, seed=1)` [default] drops the band, roll row 22; `(4, seed=0)` DELIVERS it at the SAME roll
>   row 22 (timing preserved); `(4, seed>=2)` delivers but shifts timing to row 23; `(8, *)` delivers all
>   but at ~2x timing (breaks the plan's discrete B/A). The game reads ~4 SI polls / 30fps frame (polls=4
>   = correct 1:1); `seed=1`'s leading neutral poll is the phase that slips.
> - **THE FIX (characterized live, NOT shipped):** `make_dtm(seed=0)` alone delivers the band but leaves a
>   ~0.6u residual and no OOB clip -- because it shifts the leading-poll layout the from-rest prefix's
>   `rest_noops` (s38) is calibrated to. Clean fix = **`seed=0` PLUS re-derive `rest_noops` for the seed-0
>   layout**, re-verify REST BIT-EXACT, then the session-39 hit should clip. The `fine_family` band-exclusion
>   (s41/solver.py) is NOT the fix and should be REMOVED once delivery is faithful (it kills usable density).
> - **Artifacts:** the RAW pad read (`g_mDoCPd_cpadInfo[0]`) is PROMOTED into `capture_decode.py`
>   (`capture` logs cpad_val/px/py; `delivery_sweep(anchor, stream, combos)` = the (polls,seed) delivery
>   probe reporting fines-received/roll-row/OOB-clip; `python -m harness.rollstab.capture_decode sweep`).
>   RED gate renamed `test_sheathed_roll_clip.py::test_sheathed_ship_delivery` (reason corrected to the
>   delivery drop). dead-end #34 (+ #33 correction banner). Suite **342 passed, 1 skipped, 2 xfailed**
>   (unchanged count). NO sim/physics behavior changed; the interim `fine_family` exclusion is UNTOUCHED.
>
> **NEXT: ship the make_dtm fix.** (1) `make_dtm`/`run_dtm`/deliver default to `seed=0` (or thread it),
> keeping `polls=4`. (2) Re-derive the sheathed anchor's `rest_noops` for the seed-0 leading-poll layout
> (mint.capture_rest derives it; or bump/measure it) and re-verify REST BIT-EXACT via `capture_walkentry`.
> (3) `deliver ship` the session-39 hit -> confirm live 0-ULP CLIP (proc 0x24 OOB) -> flip
> `test_sheathed_ship_delivery` GREEN. (4) REMOVE `solver.fine_family` band-exclusion, re-solve if needed.
> GUARD: re-run the existing bit-exact goldens (walk-stab, tetra, rollstab_rest) under the new seed --
> if seed=0 changes their alignment, thread `seed` per-call rather than changing the global default.
> Every other thread (walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 41): the sheathed-clip row-18 blocker is RE-ROOT-CAUSED
> DETERMINISTICALLY and it OVERTURNS BOTH #31 AND #32 -- the live miss is a ONE-FRAME WALK-SPEED
> gap the sim isn't modeling (a band-magnitude stick at cap), NOT a decode or facing error. Per
> Dereck's directive, a RED gate is added for next session to resolve by MODELING it. No sim behavior
> shipped except the interim `fine_family` band-exclusion.** Done this session (offline + ~5 live
> DETERMINISTIC DTM measurements, never advancewith):
> - **The band DECODE is faithful even for a 1-frame transient (overturns #32).** A deterministic
>   stopped-position probe (`aim-cruise + [1-frame T] + neutral-to-DEAD-STOP`, read the constant
>   stopped pos -> ±1 log jitter cannot corrupt it): the culprit `(96,192)` live stopped pos == the
>   sim's RAW-decode prediction BIT-FOR-BIT (the "holds prior" prediction was off 20.9u); sub-band
>   control likewise. The decode formula is correct; the whole game stick path (PADRead->PADClamp->
>   CStick::update) is STATELESS (decomp), zero prior-frame state.
> - **The divergence is purely ALONG-TRACK (speedF), not facing (overturns #31).** gf-aligned to the
>   jitter-immune golden (emulator counter ticks 2x/game frame -> gf = 2*row + const, 0 conflicts):
>   rows 0-17 BIT-EXACT (incl. the arc + sub-band fines + a held-2 full stick), then row 18 the sim
>   dips speedF 17->15.091 while live holds 17.0 (perp x matches to 0.02u). `17-15.091 = 1.909` ==
>   the 1.9125u lag, frozen through the roll -> `old` off the razor -> no clip. Two independent live
>   runs agree (golden + a fresh `deliver ship`: live old z 306.116 vs sim 308.028).
> - **The gap = the console's BAND-magnitude WALK-SPEED (the thing to model).** decomp: target speed
>   `dVar10 = msd^2*max` (setNormalSpeedF 2306); `mStickDistance = mMainStickValue` (setStickData
>   10569). For a band magnitude (0.889,1.0) the console's effective walk-speed differs from the sim's
>   `min(hypot/54,1)`->msd^2 model -- the SAME caveat precise-stop.md documents (held `(128,196)`:
>   console 15.76 vs sim 16.38). Only band AT CAP dips (`start1 (98,191)` is band but was bit-exact --
>   it is in the low-speed start crawl, still accelerating). Sessions 39/40 misdiagnosed it (MOVE-turn
>   / band-decode) by reading run_dtm's ±1-ambiguous per-frame log instead of the robust z-trajectory.
> - **OPEN SUBTLETY (recorded, not over-claimed): the probe (band after plain cruise) matched the
>   sim's dip, yet the ship (band after the ARC) shows live NOT dipping** -- an arc-carried hidden
>   state changes the console's band-speed response; not isolated. Doesn't change the fix. (dead-end #33.)
> - **Artifacts:** RED gate `tests/test_sheathed_roll_clip.py::test_sheathed_band_speed_at_cap`
>   (strict-xfail, corrected reason: band walk-speed, gf-aligned to the immutable jitterproof golden);
>   interim `solver.fine_family` band-exclusion (`_in_band`, `BAND_LO/HI`); `capture_decode.band_sweep`
>   (per-frame sweep -- but per-frame band reads are ±1-unreliable, use the stopped-position probe).
>   Suite **342 passed, 1 skipped, 2 xfailed** (unchanged count).
>
> **NEXT (Dereck's directive: model what the sim isn't modeling): resolve the RED gate by modeling the
> console's band-magnitude walk speed to f32.** Decomp-first from `setStickData`/`mMainStickValue` /
> `JUTGamePad::CStick::update` value near the cap; characterize the arc-carried context dependence via
> the DETERMINISTIC stopped-position probe **`harness.rollstab.capture_decode.transient_probe`**
> (`... capture_decode probe`; PROMOTED this session out of scratch -- it is the band-walk-speed
> measurement tool: sweep `holds=(1,2,3,4)` on a band stick at cap, the incremental stopped distance
> per added frame is the console's per-frame band speed). NEVER per-frame run_dtm reads for 1-frame
> events (±1-ambiguous; the `band_sweep` per-frame decode is flagged unreliable). Then
> REMOVE the `fine_family` band-exclusion so the solver can USE band sticks again (restoring the
> near-full-mag fine-perp density the band-free search lacks -- session 40's 0.0013u wall), re-solve,
> deliver. Every other thread (walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-14, session 40): the session-39 live blocker is RE-ROOT-CAUSED
> (jitter-immune) and it OVERTURNS dead-end #31. No sim code changed. The tried approaches did not
> deliver; the frontier is open.** Path 1 (the session-39 handoff's "try first") was run, then the
> blocker was re-measured jitter-immune. Done this session (offline + 3 live jitter-immune DTM captures,
> never advancewith):
> - **Path 1 (re-search for a deliverable pure-sim hit) did NOT find one in the structures tried.** A
>   pure LIVE-VALID search (every stick msd<=0.889 or ==1.0, avoiding the (0.889,1.0) band) reached
>   **~0.0013u from the f32 dust with 0 genuine hits over ~60k runs** (dense 2-knob vernier: arc + clean
>   fine + K3-crawl-3rd byte). The genuine dust is single f32 columns (~0.001u spaced, most z empty); the
>   live-valid lattices tried did not align onto one. This bounds the recipe SHAPES tried, not the clip.
>   (The `clean_settle` speedF-dip filter I prototyped is the WRONG filter -- a dip on a fine-ACTED frame
>   is live-faithful; reverted.)
> - **The row-18 blocker RE-ROOT-CAUSED, jitter-immune -> dead-end #31 was WRONG.** Using deterministic
>   game_frame tags (`fixtures/sheathed_roll_ship_jitterproof.json`) instead of run_dtm's jittery poll:
>   the stick DECODE is bit-exact live (held 8 frames, `(96,192)`->0.9605 == sim). But a **1-FRAME
>   TRANSIENT band stick** `(96,192)` (msd 0.9605, in the (0.889,1.0) band) decodes live to ~aim
>   (33295, msd 1.0 -- it holds the prior value) and does NOT turn; the sim decodes it raw (33367,
>   0.9605) and turns -> the row-18 divergence. Non-band 1-frame fines register correctly. The
>   two-angle chase is FAITHFUL; it is a TRANSIENT input-layer effect ("input-layer != /54", the freeze
>   planner already excludes the band). The session-39 "shape overshoot / MOVE-turn settle" reads were
>   run_dtm poll-jitter (live-row-19 poll caught the neighboring aim frame). dead-end #32 (corrects #31).
> - **The session-39 winning offline hit relies on the sim's transient-band mis-model, so THAT hit does
>   not reproduce live.** Its genuine landing depends on the sim treating the transient band stick as a
>   ~0.9605/33367 perp nudge, which live reads as ~aim. So a FAITHFUL transient-band model is needed to
>   make the sim predictive here; it removes that artifact rather than delivering THIS hit -- a new,
>   band-faithful solve is what delivers.
> - **Artifacts:** jitter-immune golden `fixtures/sheathed_roll_ship_jitterproof.json` (game_frame-
>   tagged, IMMUTABLE). Gate `tests/test_sheathed_roll_clip.py`: offline clip test GREEN (the solve is
>   real, in the sim), `test_sheathed_ship_matches_live` strict-xfail RED with the CORRECTED reason
>   (transient-band decode, not MOVE-turn). Suite still **342 passed, 1 skipped, 2 xfailed**. NO
>   `harness/rollstab/*.py` behavior changed (the exploratory `clean_settle` field was reverted).
>
> **NEXT (open approaches -- the clip is not solved yet; keep pushing):** (1) **model the transient-band
> input-layer behavior to f32** -- characterize it with a live band-transient sweep via
> **`harness/rollstab/capture_decode.py`** (the jitter-immune decode + two-angle capture tool promoted
> this session; `capture()`/`hold_decode()`/`ship`, RAM offsets + the run_dtm poll-jitter trap in its
> docstring): is a 1-frame band stick == the prior frame's value? a 2-frame slew? -- then make
> `main_stick_decode`/the input buffer reproduce it, so the sim is FAITHFUL and the solver searches over
> what live ACTUALLY does; then solve band-faithfully and deliver. (2) **expand the search** far beyond
> the shapes tried -- more knobs, longer
> crawls, other draw/arc placements, other A_proj phases, a warm-start off the walk-stab solver -- to
> close the last ~0.0013u to the f32 dust; the 0.0013u floor is a property of the LATTICES tried, so a
> richer input alphabet is the lever. (3) reconsider the delivery mechanics themselves (draw timing, B
> timing, the roll-entry frame) for degrees of freedom not yet exploited. Every other thread (walk-stab
> clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **CURRENT THREAD (2026-07-13, session 39): the sheathed roll-stab clip is SOLVED offline
> (pure-sim, from-rest, 0-ULP ship-gate PASS) but LIVE delivery is BLOCKED by a newly root-caused
> sim MOVE-turn facing-settle residual. Diagnosed to a single frame; RED regression added; NO sim
> code changed (Dereck's call: diagnose first).** This is session-38 NEXT (solve + deliver).
> Done this session (offline, plus 4 live DTM runs -- 1 ship + 3 diagnostic, never advancewith):
> - **SOLVE done.** A from-rest SHEATHED roll-stab genuine clip found ENTIRELY in the sim:
>   `old=(9072.2089844,308.0280762)` -> `new=(9069.8886719,258.8625793)`, disp 49.2202, CUT_F,
>   facing 33295, spF@A=17.0, sliver-robust (+-2e-4). `deliver.py gate` PASSES 0-ULP (dOLD/dNEW=(0,0),
>   genuine, clear, behind BOTH walls). Recipe (pure sim, seed-only): `A_proj=-500`, `draw_at=3`, a
>   K=2 crawl `((77,249),(98,191))` + arc `(9,(73,254),2)` + fines `(10,(99,183))`,`(4,(96,192))`,
>   `(6,(98,188))`. Found in **91 s** by a focused sweep warm-started from the same-seam idle13 recipe.
> - **LIVE ship FAILED -- root-caused by per-frame sim-vs-live diff (do NOT guess inputs).** Rows 0-17
>   of the ship stream (crawl, the row-3 draw B-edge, arc, fines) are **BIT-EXACT live** -- so delivery
>   alignment and `rest_noops` are correct. At **row 18** (an aim frame after the row-16 fine settles)
>   the SIM's `shape_angle` OVERSHOOTS to 33367 while live holds the settled 33295; that phantom
>   one-frame turn dips speedF to 15.05 vs live's 17.0 cap -> a **~1.9u along-track lag that freezes**
>   for the rest of the roll -> `old` lands off the f32 razor -> the CUT fires from the wrong spot (no
>   clip; live `new` is not behind the walls). The **drawn idle13 cached hit has the IDENTICAL row-18
>   overshoot**, so this blocks the roll-stab clip for BOTH anchors -- the cached idle13 hit appears to
>   have never been live-shipped through the current turn model.
> - **DISCRIMINATOR (Dereck's directive): it is a two-angle/MOVE-turn SETTLE residual, NOT an input-
>   delay/buffering shift.** Live shape+travel per frame (`0x136`/`0x12E`) vs the sim: `live[row r] ==
>   sim[row r]` on EVERY row except 18 -- live does NOT lead the sim by a frame (rules out the
>   pushaside-#3 class). The sim inserts one spurious facing value (33367) at row 18 that live never
>   has. Root is the `shape_angle` chase / `setMoveSlantAngle` settle after an arc+fine (README model
>   term #5; the Phase-R MOVE-turn frontier). dead-end #31 (NEW).
> - **Artifacts:** offline hit recorded to `_generated/rollstab_hits.json[0]` (gitignored);
>   live-golden fixture `fixtures/sheathed_roll_ship_live.json` (jitter-immune: shape+travel+pos per
>   row, first divergence row 18, IMMUTABLE); gate `tests/test_sheathed_roll_clip.py` -- offline clip
>   test GREEN (the solve is real), ship-vs-live test strict-xfail RED (the turn residual). Full suite
>   **342 passed, 1 skipped, 2 xfailed** (was 341/1xf). NO `harness/rollstab/*.py` behavior changed.
> - **Side finding:** `solver.search` is over-budget for the roll-stab -- at 200s it had not finished
>   drill level 0 for EITHER idle13 or sheathed (the dust cache under-samples the 1-f32-col-per-z
>   genuine set, mis-guiding the drill). The 91s find used a focused warm-start, not `solver.search`.
>   The <2-min pure-sim search is met by the focused path, not the generic drill as it stands.
>
> **NEXT (Dereck decides the branch; diagnosis is DONE): make the sheathed clip deliver live.** Two
> objective-compliant paths, neither started this session:
> 1. **Re-search for a CLEAN-SETTLE hit (no sim change):** add an acceptance constraint that the
>    from-rest approach holds speedF==17 on every cruise frame from the last intended turn through the
>    A press (reject any stream with a phantom row-18-type dip), then search for a deliverable sheathed
>    hit. Fast to try; open whether such a hit reaches the f32 razor.
> 2. **Fix the sim MOVE-turn model (decomp-first, the general fix):** find why `shape_angle` overshoots
>    one frame after an arc+fine (`setMoveSlantAngle`/two-angle settle, `d_a_player_main.cpp`) and model
>    it to f32 so any arc approach delivers 0-ULP -- flips `test_sheathed_ship_matches_live` GREEN. Per
>    the sim-change protocol: decomp-first, then live-confirm. Also fixes the drawn idle13 clip.
> Separately, fold the 91s focused solve into the harness as a reproducible <2-min sheathed solve.
> Every other thread (walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-13, session 38): the sheathed anchor's `REST`-not-bit-exact blocker is
> RESOLVED offline -- and it was NEVER the walk-entry foot-FK (session 37 was wrong). The sole cause
> was a one-frame walk-entry DTM-ALIGNMENT noop, which is the anchor savestate's emulator SUB-FRAME
> CAPTURE PHASE (not in-game). Now derived per-anchor; sheathed from-rest is BIT-EXACT; RED test flipped
> GREEN; 341 passed, locked goldens untouched.**
> Diagnosis (offline vs the s37 goldens + 2 paused-RAM probes; Dolphin up for the derivation):
> - **The FK poses are bit-exact.** With the 1-frame `mFootData` lag, every idle13 golden row matches
>   the sim 12/12 and BOTH sheathed WAIT frames match 12/12 EXACT. Session 37's `f312` "razor" mismatch
>   was an ALIGNMENT artifact -- it compared a sim MOVE frame against a live WAIT frame at the same
>   d=55.0, because the sim was one d-advance ahead. No FK residual.
> - **Sole divergence = WAIT->MOVE alignment.** By the jitter-immune d_frame clock, live sheathed does
>   3 WAIT d-advances then MOVE; the sim (REST_NOOPS=2) did 2. With **noops=1** sheathed is 0-divergence
>   on pos + m3598 + m359C at every d-aligned frame. idle13 needs 2 (breaks at 1); the two anchors
>   genuinely differ by one leading no-op.
> - **Proven a savestate CAPTURE-PHASE artifact, not in-game.** Loading each anchor paused + single-
>   stepping: idle13's first frame HOLDS d then advances; sheathed's advances immediately. idle13's hold
>   frame mutates ZERO player-RAM bytes (a pure re-display of a frame captured mid-execution); survives
>   load->save; a single advance destroys it; no player-RAM field flips it. idle13 = legacy MID-FRAME
>   capture (+1 spurious re-display -> noops=2); sheathed = `mint_current` BOUNDARY capture -> noops=1.
>   **noops=1 is the canonical standard** (clean mints + the future live-RAM UI feed all land there);
>   idle13's 2 is an artifact pinned to its locked golden.
> - **FIX (no hardcode, no re-mint, no refactor -- Dereck's call to keep noops=2 for legacy alignment):**
>   `mint.capture_rest` DERIVES the phase from its existing t1-advance (advances-until-`d`-changes) into
>   `seed['rest_noops']`; `rest.rest_state` reads it (default `REST_NOOPS=2` for legacy seeds, so
>   idle13/walkstab locked goldens stay bit-exact). Sheathed seed `rest_noops=1` (derived live).
>   `tests/test_sheathed_roll_rest.py` flipped xfail->PASS (d_frame-aligned vs the jitter-proof
>   `sheathed_walkentry_golden.json`). Full suite **341 passed, 1 skipped, 1 xfailed** (was 340/2xf).
>   dead-end #30 corrected. The FK model of #25/#28 stays genuinely open (session-25 slot-7 residual) --
>   it was simply NOT the sheathed blocker.
>
> **NEXT (the remaining LIVE increment -- the sheathed-roll milestone's "done"): solve + deliver.** The
> offline from-rest sim is now bit-exact for the sheathed anchor, so: `solver.search(anchor, draw_at=~3)`
> offline (<2 min; `draw_at` plumbing done s36) -> a from-rest sheathed roll-stab hit -> `deliver.py`
> clean DTM + live 0-ULP clip -> "done" = the scanner routes a not-drawn anchor's ROLL verdict end-to-end
> to a live clip. Verify the anchor jitter-proof with `capture_walkentry` (d_frame-aligned), NOT the
> row-indexed `rest.py` gate (which the run_dtm poll jitter can trip -- it misled sessions 36-37). Every
> other thread (walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-13, session 37): the sheathed anchor's `REST`-not-bit-exact blocker is
> RE-ROOT-CAUSED -- the session-36 diagnosis was a POLL-JITTER artifact; the real cause is the
> walk-entry foot toe-stream FK residual (dead-end #25/#28). No solver behavior changed; the fix
> (model the walk-entry foot poses to f32) is HANDED OFF to a dedicated session (Dereck's call).**
> Done this session (2 live runs, otherwise offline):
> - **Refuted session-36 lead (a) + dead-end #30's "extra idle frame" story.** Two run-free RAM reads:
>   the loaded idle bck `m_anm_heap_under[0].mIdx` is `BCK_WAITS` (0x126) at BOTH idle13 (drawn) and the
>   sheathed anchor -- the idle ARM is identical (only `heap[1]` differs, WALKS vs WALK = the modelled
>   `sword_drawn` walk arm), and both seed.jsons match live RAM. So `idle_anim='waits'` is correct.
> - **Jitter-proof measurement (`harness/rollstab/capture_walkentry.py`, NEW):** tag every live row with
>   the deterministic emulator frame (game_frame = emu - F0). BOTH anchors reach proc-MOVE at the SAME
>   game-frame (gf6) and the big walk step at gf8 -- the session-36 "3 idle rows vs 2" was `run_dtm`'s
>   row-0 fast-poll catching the two captures at different start frames.
> - **Real root cause = the walk-entry toe-stream `f312`, amplified by the 0.05 speedF clamp.** At the
>   sheathed idle phase (d~52.8) the sim's first-walk-frame toe delta is ~0.034 vs live ~0.060; the
>   decomp-faithful `_py_foot_compose` clamp (`speedF=0 if |spz|<0.05`) zeros the sim but keeps live ->
>   opposite sides of the razor -> ~0.8u accumulated over the m3598>0 blend frames (freezes when m3598
>   hits 0, same class as #25). PHASE-driven, NOT equip (forcing `sword_drawn`/`model_draw` -> ~0.003u).
> - **Ground-truth artifacts for the fix:** `fixtures/sheathed_walkentry_golden.json` (RED) +
>   `fixtures/idle13_walkentry_golden.json` (bit-exact reference) -- game_frame-aligned, raw mFootData
>   toe/heel + plant per frame. RED test `tests/test_sheathed_roll_rest.py` reason corrected (still xfail).
>   dead-end #30 corrected. Full suite unchanged (340 passed, 2 xfailed).
>
> **NEXT (Dereck's decision -- the objective-compliant frontier fix, its own session): MODEL the
> walk-entry foot poses to f32** so `posMoveFromFootPos`/`f312` is bit-exact from rest at ANY idle
> phase (fixes the sheathed anchor AND the session-25 slot-7 residual). Diff the sim against
> `sheathed_walkentry_golden.json` on the raw foot poses (aligned by game_frame), find where the pose
> delta drifts on the m3598>0 blend frames (the `plant` foot flips 0->1 at gf6 for sheathed but stays 1
> for idle13 -- likely a lead), and model it. THEN the sheathed anchor goes `REST BIT-EXACT` ->
> `solver.search(anchor, draw_at=~3)` (draw_at plumbing DONE session 36) -> `deliver.py` clean DTM +
> live 0-ULP -> flip `test_sheathed_roll_rest.py` green. Cheap first check: try a clean-provenance
> re-mint (lead b) before the FK model -- low odds but fast. Everything else UNCHANGED.

> **PRIOR THREAD (2026-07-13, session 36): started the LIVE sheathed-roll increment -- the
> `draw_at` solver plumbing + a full-seed mint tool + a minted sheathed anchor are DONE, but the
> anchor is NOT YET `REST BIT-EXACT` (BLOCKED on a walk-entry alignment; root-caused, RED test
> added).** This is session-35 NEXT #1. Done this session:
> - **`solver.search`/`check` now thread `draw_at`** into every `run` call (was the trivial-but-missing
>   plumbing session 35 flagged; additive, default None = byte-identical). `run` already accepted it.
> - **`mint.py` gained `mint_current(name)` + `capture_full_seed`** -- mint the CURRENT live paused
>   state as a fresh FULL-seed anchor (every field read from RAM, no base-seed inheritance), so an
>   equip change is mintable (`mint.py`'s translate path only shifts pos within a room). CLI:
>   `python -m harness.rollstab.mint current=<name>`.
> - **Minted `kaze_r11_rollstab_sheathed@twwgz`** at idle13's spot (equip-only change: load idle13,
>   press A while idle to put the sword away -> `mEquipItem` 0x100, settle, mint). Pos/facing (33328)/
>   csangle (29883)/state (4) identical to idle13; blend rates match (`d_rate` 1.1, `w_rate` 0.5867 --
>   the same WAIT/WALK arm). `rest.rest_state` auto-enables `model_draw` for it (sheathed => not
>   sword_drawn).
> - **RED regression `tests/test_sheathed_roll_rest.py`** (strict xfail) + live calib fixture
>   `fixtures/sheathed_rest_calib.json`. Full suite **340 passed** (unchanged), now **2 xfailed**.
>
> **THE BLOCKER (root-caused, do NOT re-derive):** the sheathed from-rest walk is NOT bit-exact. The
> sword-DRAWN idle13 IS (its gates are green), so it is NOT the code, NOT `sword_drawn`, NOT
> `model_draw` (forcing either changes the ramp by ~0.003u -- ruled out offline). **The sheathed idle
> takes ONE EXTRA idle frame before the WAIT->MOVE walk transition** (live: 3 idle rows k=0..2, MOVE at
> k=3; idle13: 2 idle rows, MOVE at k=2), so the sim's walk starts one frame early and every downstream
> row is off by ~one walk step (both still hit the same 16.98 cap). A single `REST_NOOPS` shift CANNOT
> fix it: that constant holds the idle-anim `d_frame` and the position TOGETHER, but live advances
> `d_frame` at k=2 while position stays at rest until k=3 -- a WAIT->MOVE / stick-delivery latency the
> drawn idle lacks. Two things to chase (see the session-36 handoff): (a) **the sheathed idle likely
> rests in a non-`waits` anim arm** (`rest_state` hardcodes `idle_anim='waits'`; the Phase-R risk the
> session-35 handoff flagged) whose transition differs by a frame -- verify the live idle anim ID; OR
> (b) **mint a clean-provenance sheathed savestate** (the current one was made via `advancewith`
> frame-stepping; a real-time `resume`/`setinput` sheathe was attempted but the idle A-press needs an
> EDGE that held-A / post-`clearinput` timing missed -- get the clean sheathe working, then re-check).
> NOTE the live DTM row-0 alignment is also jittery +-1 idle frame (`run_dtm` fast-poll), which muddies
> single-run diffs -- diff the STABLE structure (idle-row count before MOVE), not row-0 `d`.
>
> **NEXT (unchanged goal): make the sheathed anchor `REST BIT-EXACT`, then solve + deliver live.** Fix
> the walk-entry alignment (a or b above) so `rest.py` prints `REST BIT-EXACT`; then thread `draw_at`
> through `solver.search` (done) to solve offline (<2 min); then `deliver.py` clean DTM + live-gate
> 0-ULP, flipping `test_sheathed_roll_rest.py` green and replacing the synthetic-seed wiring test with
> a live golden. Everything else (walk-stab clip, Tetra push-aside/turnaround, thrust scanner) UNCHANGED.

> **PRIOR THREAD (2026-07-13, session 35): the SHEATHED ROLL PATH is WIRED offline + gated; the
> live mint/deliver is the remaining increment (deliberate checkpoint).** This is session-34 NEXT #1
> -- routing a NOT-DRAWN (sheathed) anchor's ROLL verdict to a roll-stab clip. Decision (Dereck):
> REUSE the kaze roll seam (S=(9069.904,259.199), F=33295) with a sheathed anchor, so NO geometry
> generalization is needed for this milestone -- only the draw wiring is new. **Done this session
> (OFFLINE, no live runs):**
> - `rest.rest_state(anchor, model_draw=None)`: defaults to `not sword_drawn`, so a SHEATHED anchor
>   auto-enables `LandState(model_draw=True)` (a drawn anchor stays OFF = byte-identical).
> - `solver.run(anchor, ..., draw_at=None)`: feeds a single B rising edge on approach row `draw_at`
>   (the mid-walk sword pull-out). With model_draw ON the draw completes before the A press, so the
>   roll routes to a CUT (`land/procs/roll.py:79` needs `sword_drawn`).
> - **Offline-proven end to end** (synthetic sheathed seed = drawn idle13 + equip forced sheathed):
>   draw-B@row3 -> `sword_drawn` flips at row8 (5 frames after the raw feed, matching the live-pinned
>   `f_draw`) -> foot set base->sword (`walk`->`walks`) -> speedF holds the 17 cap across the
>   phase-preserved swap -> A@row19 -> FRONT_ROLL -> **CUT_F fires**. The draw is LOAD-BEARING:
>   `draw_at=None` leaves the roll->CUT gate unsatisfied and NO cut fires.
> - Gate `tests/test_sheathed_roll_wiring.py` (4 green, OFFLINE); full suite **340 passed** (was 336),
>   1 skipped, 1 xfailed. Additive/backward-compatible: the existing drawn-anchor solvers are
>   byte-identical (both new params default to the old behavior).
>
> **NEXT (the remaining LIVE increment for this milestone -- checkpointed, not started):**
> 1. **Mint a sheathed roll-clippable anchor at the kaze roll seam.** Every existing roll anchor
>    (`idle13`, `mEquipItem=0x103`) is sword-DRAWN, and `mint.py` only translates within a room (no
>    equip change), so this needs a fresh live capture: place Link with enough run-up (draw + build to
>    cap + roll before the seam), sheathe the sword (`mEquipItem` 0x100), let the idle settle, save +
>    auto-capture the `rest_*` seed. A sheathed idle may rest in a different arm than `waits`
>    (`rest_state` models the `waits` arm; Phase R residual) -- verify `REST BIT-EXACT` (`rest.py`).
> 2. **Solve** offline (`solver.search` with `draw_at` threaded through; <2 min) -> a from-rest sheathed
>    roll-stab hit.
> 3. **Deliver** as a clean DTM + live-gate 0-ULP; replace the synthetic-seed offline test with a live
>    golden. "Done" = the scanner routes a not-drawn anchor's ROLL verdict end-to-end to a live clip.
> NOTE: `solver.search` does not yet thread `draw_at` into its `run` calls -- that plumbing is part of
> step 2 (trivial: pass `draw_at` through `run`/`check`; the offline path already accepts it).

> **CURRENT THREAD (2026-07-13, session 34): the MID-WALK SWORD PULL-OUT is MODELLED + live-gated
> 0-ULP.** This was the session-33 NEXT #1 (Dereck's directive) and it UNBLOCKS the scanner's ROLL
> dispatch for a not-drawn anchor. The sim froze the foot anim set (base WALK/DASH vs sword
> WALKS/DASHS) at `FootSpeedF` construction, so it couldn't represent a draw. **Decomp settled the
> OPEN question (no live breakpoint needed -- priority A):** the anim-set swap is an INSTANTANEOUS,
> phase-preserved pose jump with NO oldframe-morf -- `getAnmData` reselects the sword table the instant
> `mEquipItem` flips at the equip-anime completion (`d_a_player_main.cpp:3976`), `setMoveAnime`
> re-fetches it every frame (12734), and `procMove`'s steady `setBlendMoveAnime(-1.0f)` (6229) passes
> `i_morf < 0`; WALK/WALKS + DASH/DASHS share `frameMax` so the preserved phase `f31` leaves the frame
> value unchanged, only the legs swap. **Model:** `FootSpeedF.draw_sword()` flips `_walk`/`_dash`
> base->sword; `LandState(model_draw=True)` (opt-in; forces the pure-Python foot path -- native `_anmc`
> has no DASHS; default OFF = byte-identical) auto-triggers it `DRAW_DELAY=3` acted-frames after a B
> rising edge while walking sheathed. **`f_draw` = 5 frames after the raw B feed** (= 3 after the
> `INPUT_DELAY`-acted swordTrigger edge), live-pinned. **Live-gated 0-ULP:** capture
> `harness/rollstab/capture_draw.py` (`land_flatwalk`, sheathed `mEquipItem 0x100`; straight UP walk
> drawn at start via UP+B, then decelerated through the WALK<->DASH blend so the DASHS legs show on
> VISIBLE `m3598>0` frames); offline replay `harness/rollstab/validate_draw.py`; fixture
> `fixtures/walk_draw.json`; gate `tests/test_draw_switch.py` (5 green). The from-rest walk with the
> switch is 0-ULP vs live, and BOTH naive baselines DRIFT (never-draw stays DASH -> 1028 ULP off on the
> post-draw decel frames; always-drawn poses DASHS pre-draw -> 57 ULP), so the switch TIMING is
> load-bearing for the roll `old`. Full suite 336 passed (was 331; +5 `test_draw_switch.py`). The scanner /
> roll-stab / Tetra threads are otherwise UNCHANGED; the roll solver is not wired to `model_draw=True`
> yet (deferred with the roll-path solve).
>
> **NEXT (deferred to dedicated sessions):**
> 1. **Wire the scanner's ROLL dispatch to use `model_draw=True`** so a sheathed anchor draws mid-walk,
>    rebuilds to cap in the sword set, then A-presses to roll (roll->cut requires `sword_drawn`, which
>    `draw_sword` now sets on completion). Needs the roll-path solver (generalize `walkstab`/`solver` off
>    the hardcoded kaze seam -- see below), then a from-rest sheathed roll-stab delivered + live-gated.
> 2. **sword-OUT walk-stab live validation** (unchanged from s33): mint a sword-OUT anchor at a
>    walk-clippable seam + deliver/confirm live (`deliver` b_frame is already sword-aware, N-1 vs N-5).
> 3. **(optional) generalize the two solvers off their hardcoded kaze seam** (parameterize the settled
>    facing + crawl count from the seam bearing) so `thrust_scan.scan` can dispatch any enumerated seam.

> **CURRENT THREAD (2026-07-13, session 33): the CENTRALIZED THRUST-CLIP SCANNER is built (offline
> decision layer + dispatch), gated, and validated end-to-end.** `harness/rollstab/thrust_scan.py` is
> the front-end that, given an anchor seed + a target seam, DECIDES WALK vs ROLL vs INFEASIBLE and
> dispatches the matching existing solver (it does NOT rewrite them). The decision: the displacement
> floor `35/sin(interior/2)` sets the geometric tier (WALK <= 40.22, ROLL <= 49.22, else PUSH = actor
> push, out of scope), then a RUN-UP-SPACE feasibility gate simulates the straight approach from the
> anchor (`rest.rest_state`, C-down pin, per-frame re-aim at S) and requires the needed speedF (WALK:
> `floor-23.220`; ROLL: the 17 cap) to be built while `old` is still `>= floor` from the tip. FEWEST
> FRAMES wins -> prefer WALK when it fits the space, else ROLL, else INFEASIBLE(`push`|`space`). Gate
> `tests/test_thrust_scan.py` (9 green, OFFLINE): the four handoff cases (kaze walk seam -> WALK; kaze
> roll seam -> ROLL; a synthetic 90-deg seam -> INFEASIBLE/push; a close-start anchor -> INFEASIBLE/
> space) + tier boundaries + fewest-frames + dispatch. End-to-end validated: `scan(solve=True)` routes
> the walk seam to `walkstab.solve_focused` and reproduces the shipped clip's `old` (offline, 72.6s).
> `walkstab.deliver` is now sword-aware (B at N-1 sword-OUT vs N-5 sheathed; backward-compatible with
> the shipped golden). The Tetra-push / roll-stab threads remain PAUSED.
>
> **NEXT (deferred by Dereck to dedicated LIVE sessions):**
> 1. **MODEL the mid-walk sword pull-out (Dereck's directive 2026-07-13, session 33).** For a
>    NOT-DRAWN anchor the sword must be pulled out mid-walk, and the sim can't represent it: the foot
>    anim set (`_walk`/`_dash` -> WALK/DASH vs WALKS/DASHS) is frozen once at `FootSpeedF` construction
>    (`anim_state.py:170-171`), a STATIC flag. The current walk-stab escapes this only by construction
>    (B at N-5 times the draw to complete AT the cut, so no walk frame is posed in the sword set --
>    decomp `d_a_player_main.cpp:3975-3976` flips `mEquipItem` -> sword at the equip-anime completion
>    frame, and `getAnmData` keys the leg set off `mEquipItem`). It BREAKS for the ROLL path from a
>    sheathed anchor: the roll->cut trigger REQUIRES `sword_drawn` (`land/procs/roll.py:79`), so Link
>    must draw BEFORE the A-press then rebuild to cap in the SWORD set (DASHS != DASH, session 31), and
>    those frames drift. Model = make the foot anim set SWITCHABLE at a draw-completion frame `f_draw`
>    (from the B-press + equip duration: item put-away `field_0x20`/`0x30` then take-sword at 7.0; an
>    on-back sword is just the take at 7.0). OPEN, needs a live breakpoint: does the `mEquipItem` swap
>    trigger an oldframe-morf, or is it an instantaneous leg-pose jump (DASH/DASHS share frameMax 32 ->
>    rates match, so likely instantaneous -- VERIFY, don't assume). Then live-capture a mid-walk draw
>    (sheathed -> draw -> keep walking), per-frame diff to pin `f_draw` + confirm 0-ULP after, add a
>    live regression. This BLOCKS the scanner's ROLL dispatch for any not-drawn anchor.
> 2. **sword-OUT walk-stab live validation.** The B-frame code is in (`deliver` derives N-1 vs N-5 from
>    the anchor equip); what remains is minting a sword-OUT anchor at a walk-clippable seam (an equip
>    change at capture -- `mint.py` only translates within a room) and delivering + confirming live,
>    same rigor as the sheathed one.
> 3. **(optional) generalize the two solvers off their hardcoded kaze seam** (the scanner dispatches by
>    seam match today; a new-seam solve needs the settled facing + crawl count parameterized).
>
> **PRIOR THREAD (2026-07-13, session 32): the pure-sim WALK-STAB seam clip is DELIVERED LIVE, 0-ULP,
> no calibration -- the objective is MET for the walk stab.** A `solve_focused` hit found ENTIRELY in the
> sim shipped as a clean DTM and clipped the kaze r11 slot-3 seam (S=(9030.955,1385.858), poly 803x802,
> interior 168.97deg): the CUT_F fired at N=13 with `old=(9011.2773438,1352.7379150)` and
> `new=(9031.8212891,1387.3160400)` -- **BIT-FOR-BIT the sim's from-rest prediction** -- the clip is
> genuine, and Link went OOB (proc 0x24, `pos_y` below the floor) THROUGH the seam (Dereck confirmed OOB
> on screen). Anchor `tests/dolphin/anchors/kaze_r11_walkstab@twwgz.sav`; live golden
> `tests/golden/walkstab_deliver.json`; gate `tests/test_walkstab_clip.py` (xfail flipped -> PASS).
> Mechanism + disp-floor in KB `knowledge/mechanics/walk-stab.md`. The roll-stab / Tetra-push state below
> is PAUSED (same solver shape).
>
> (Session 32's "NEXT PHASE = a centralized thrust-clip scanner" is DONE -- see the session-33 thread
> at the top of this Status.)
>
> **SESSION-32 FINDINGS (the load-bearing ones):**
> - **The blocker was NEVER throughput -- it was distinct-old DENSITY near the razor perp.** The
>   acceptance perp razor (~2e-4u) is a GAP in the reachable-`old` byte lattice at K<=2 crawls: an offline
>   sweep floored `min|perp|` at **~1.3e-3u (~13x the razor)**. So the legacy `solve()` (CRAWLS K<=2 +
>   collapsing knobs) finds **0 hits even given the full 110s budget** -- speeding it up cannot help. The
>   fine knobs it leaned on (bearing arc `off`, the arc-frame byte nudge) are FULL-MAG sticks that
>   octagon-CLAMP, so they collapse (52k streams -> ~14 distinct near-razor `old`).
> - **The fix = a K=3 START CRAWL.** Each crawl frame densifies the perp lattice ~20x (K=1 ~0.03u -> K=2
>   ~1.3e-3u -> **K=3 ~2e-5u**, reaching the razor). The fine perp knob is the 3rd crawl frame's BYTE
>   nudge -- a PARTIAL-mag stick sits in the octagon INTERIOR, so every byte is distinct (unlike the
>   clamped full-mag arc). `solve_focused` (session 32): Phase A brackets `|perp_ray|` coarsely (cheap, no
>   CrrPos), Phase B drills the byte-nudged 3rd frame + tests EXACT `genuine_clip`, Phase C re-sims WITH
>   walls and accepts only `wall_hit==False` (rejecting the dead-end #28 wall-overshoot artifacts). It
>   found **3 wall-faithful genuine hits in 67s** (< 2 min); the top clipped live 0-ULP.
> - **RIGOROUS MULTI-POSITION VALIDATION (Dereck's ask): 3/3 distinct `old` positions clip live 0-ULP.**
>   Delivered three different positions around the seam (d2S 37.80 / 38.52 / 38.91; `old_x`
>   9011.08..9011.65), each `old`/`new` bit-for-bit its sim prediction, each genuine + OOB (proc 0x24,
>   `pos_y` below the floor). The DELIVERABLE window is a narrow **~1u band at d2S~38**: closer to S the
>   walk brakes on the seam wall pre-cut (the wall-faithful gate bounds it), farther the lunge cannot
>   reach. Within it the pipeline is reliable. Fixture `tests/golden/walkstab_positions.json`, gate
>   `tests/test_walkstab_clip.py::test_walkstab_multiple_positions_clip`.
> - **Dead-end #28 RETIRED at the premise.** "The walk-entry foot residual eats the razor" was the
>   session-31 sword/anim-set bug (already fixed); with the from-rest sim 0-ULP, any genuine offline clip
>   is a TRUE one-shot and the search's `old` IS the live `old` bit-for-bit. The margin-5 hit delivered
>   cleanly (0-ULP leaves no residual for the margin to absorb).
> - **The search speedups (all bit-exact-validated, committed):** module-cached cut anim (killed a
>   per-clone pyproject root-walk; `enter_cut` ~8.5x), `fast_cut` (cached constant CUT_F lunge, ~20x vs
>   `enter_cut`, 0-ULP over 378 snapshots), `FootSpeedF.skip_cruise_pose` opt-in flag (skip the cruise
>   foot pose -- 0-ULP for walk-then-cut over 1944 streams), and **memoized `stick_for_bearing`** (the
>   dominant win: 20M redundant `main_stick_decode` calls eliminated). Search 105 -> ~1340 streams/sec;
>   `run_dtm` now logs `pos_y` (the OOB/fall detector).
> - **Shipped this session:** `solve_focused` + `fast_cut` + memoized sticks in `harness/rollstab/walkstab.py`
>   (legacy `solve` kept as `solve_legacy`); `deliver` rewritten (explicit-sticks replay, OOB detection,
>   golden save); `cut.py` module anim cache; `foot_speedf.py` `skip_cruise_pose`; `run_dtm.py` `pos_y`;
>   `tests/golden/walkstab_deliver.json` (NEW live golden); `tests/golden/walkstab_positions.json` (the
>   3 live-confirmed positions); `tests/test_walkstab_clip.py` (gate PASS + from-rest re-sim + the
>   3-position guard).

- **WALL-BRACED CLIP TRIED LIVE -> INFEASIBLE on slot 7 (session 27, dead-end #27); NEXT = simulate
  PUSHING Tetra onto a genuine coord.** Drove the full live braced pipeline (perp-shifted Link start ->
  measured entry -> solved braced Tetra at (-1652.293,-940.256), fB=50 ON wallB -> deliver -> per-frame
  diff). Link's roll was BIT-EXACT but Tetra DRIFTED off the wall before it: the deep-corner brace spot is
  ~220u from Link, so the speed-building away-walk crosses her 230u follow threshold (peak 249u) and she
  flees; the cut wall-pinned short (no clip). Full roll + seam-reach + follow-safe cannot coexist (#27) --
  bracing is incompatible with the FOLLOW clip because follow breaks it (might work on slot 6's glitched
  no-follow Tetra; untried). **The shipped free-floor clip is UNCHANGED / still live bit-exact.**
  - **Genuine-placement list shipped: `_generated/tetra_placements.tsv`** (288 float-exact Tetra (x,z) at
    the session-24 working entry, step 0.004, with new/dist_wallB/dist_wallA/on_target/against_wall).
    Any row clips; none are against the wall (closest 56.98u -- the working entry's thread doesn't reach
    wallB). Regenerate: `_notes/scratch-session27/gen_placements.py`.
  - **NEXT (real-TAS positioning): simulate PUSHING/HERDING Tetra onto a genuine coord** -- you can't
    memory-write her in a TAS. Link's levers (all modelled + live-gated 0-ULP): FOLLOW
    (`core.npc_zl1.Zl1FollowState`), CC contact push (`cc_push`/`cc_stepper.CcCoupledStepper`), BG
    WallCorrect. Build a herding driver (Link inputs -> Tetra final f32 (x,z)) + search maneuvers that
    land her on a genuine spot; genuine test = `turnaround.search`/`ShoveCtx.sweep_par`. Open question:
    the coords are f32 slivers -- is Tetra's arrival f32-controllable by physics? See the session-27 handoff.

- **TETRA-PLACEMENT PRECISION CHARACTERIZED (session 26, SIM-ONLY): the genuine set is a thin
  CONNECTED THREAD, not a lottery point and not a fat band.** At the FIXED live-measured slot-7 roll
  entry `(-1516.116455078125, -765.1473999023438)` facing 40835 m351C 0, an offline f32 sweep
  (`ShoveCtx.sweep_par`, region located via the smooth behindA/behindB pre-CrrPos ridge then
  column-chunked f32 scans -- streaming to dodge the wide-grid OOM; ~66k sims/s) maps the genuine
  Tetra START placements to a **~46u thread** along a ~59deg-from-+X diagonal (slope dz/dx~1.67,
  x[-1651.7,-1628.1] z[-933.3,-893.2]), **meandering +-~2u** (RMS 1.14u off a straight fit -- follow
  the thread, never fit a line). Perpendicular it is **~8 f32-ULP thick (median ~4.9e-4u, range
  1-16 ULP)**; ~**84%** of consecutive f32 x-columns carry a genuine sliver and adjacent slivers
  overlap/touch (a CONNECTED thread, unlike kaze's disjoint per-column stripes). The landing `new`
  drifts ~0.001u along the thread (12 f32 values); the shipped target `new` is bit-exact only on a
  ~1-2u sub-segment, but ANY thread point clips (Link falls). **Verdict for the TAS:** ~46u of
  along-slack, but ~f32-precise (~5e-4u) perpendicular -- a targetable line, not a point.
  Full numbers + method on the KB page [[seam-clip-solver]] ("Tetra-corner placement" section).
  - **Dereck's wall-brace question, FULLY answered: Tetra can be braced on wallB but there is NO slide
    RANGE -- bracing only removes ONE coordinate, and this is fundamental.** Shifting the ROLL ENTRY
    (perp- ~-1.3u) walks the thread's corner-ward tip exactly onto the wallB brace locus (fB=TET_R=50,
    z=-940.25562 -- verified: deeper placements CrrPos-eject there, so fB=50 IS the wall), and
    braced-genuine placements exist (`new` bit-exact). BUT the along-wall window = thread-thickness
    (~5e-4u) / sin(crossing angle), and: **wallB is crossed near-PERPENDICULARLY** (local thread angle
    75-82deg at the brace point; swept facing 40805-40880, never rotates parallel) -> window only
    **2-3 f32-ULP (~0.0002u)** -- a point, so x still needs f32 precision (2D-f32 -> 1D-f32). **wallA
    (near-PARALLEL, the wall that could give a range) is UNREACHABLE** -- the thread's tip pins at
    x~-1650 (fA~76) at every entry tried (9 directions), ~25u short of the wallA brace (fA=50), an
    acceptance-geometry limit. So no Link knob (position, facing) opens a range. Untried long-shots:
    curved walk-up (`m351C` lean) + thrust timing (tip pin looks geometric -> low expectations).
    Numbers + method on KB [[seam-clip-solver]] "Wall-brace"; session-26 handoff has the tooling.

- **THE CLIP IS UNCHANGED AND STILL LIVE + BIT-EXACT (session 24, below).** Session 25 attempted the
  optional pure-sim polish (compute the roll entry from the slot-7 rest seed instead of measuring it)
  and ROOT-CAUSED the residual but did not close it -- the clip's shipped status is untouched (it still
  seeds at the MEASURED live entry, exactly as the pushaside clip does).
  - **From-rest slot-7 DOWN-walk residual ROOT-CAUSED (session 25), left open by choice.** The
    computed-from-rest entry lands ~**2.54u** NE of the live entry. Diagnosed by per-frame diff of the
    seeded sim vs a rich live walk trace (`_generated/turnaround_walk_trace.json`), and it is NOT what
    the session-24 handoff guessed ("seed_rest_blend + deferred-draw class"):
    - **Proc/frame alignment is PERFECT with `noops=0`** (NOT the kaze `REST_NOOPS=2`): WAIT f0-f2 (no
      move), MOVE f3-f8, roll entry f9 -- bit-identical frame numbering to live. The slot-7 idle
      genuinely RUNS procWait each WAIT frame (the WAIT/WALK blend advances d 17.80->18.20->18.60,
      w +0.674/frame); it is NOT the "game hasn't run yet" alignment-noop regime kaze modelled.
    - **The WAIT<->WALK blend `m3598` matches live BIT-EXACT** (0,0,0,1.0,1.0,0.7647,0.3529,0,0) and
      **`nspeed` ramps cleanly** (+3.5/frame to the 17 cap). So the accel integrator and the blend
      weight are already right.
    - **The entire error is in the foot toe-stream `f312`** (`posMoveFromFootPos`, `_py_foot_compose`)
      on the THREE walk-entry frames where `m3598 > 0` (f3-f5): there `speedF = nspeed*(1-m3598) +
      f312*m3598`, and the sim's `f312` is low (f3 0.068 vs live 0.105; f4 1.42 vs 2.15; f5 2.42 vs
      4.62). Once `m3598` hits 0 (f7+) `speedF == nspeed` and the two agree exactly, so the 2.54u
      freezes and never grows. Live's RAM `m359C` column IS this `f312` (0.105, 2.146, 4.618, ...).
    - This is the **same foot-FK-precision residual class as the Phase-R late-roll-pose drift**
      (jointBeforeCB MOMI body-lean / the walk-entry oldframe-morf toe stream), NOT a proc or blend
      bug. Closing it means modelling the walk-entry foot poses to f32, not re-seeding. Deferred: the
      clip does not need it (measured entry is 0-ULP live), and it is orthogonal to the Tetra-precision
      question the next session answers. Regression captured as the live trace fixture above; no RED
      test added (the finding is recorded here + in the handoff instead).

- **KILL-THE-GLITCHED-TETRA DONE (session 24): the FOLLOW-ENABLED turnaround-roll seam clip is LIVE,
  BIT-EXACT, with a NORMAL following Tetra.** The whole `turnaround.py` live pipeline is wired
  (`entry`/`solve`/`deliver`/`diff`) and delivered the clip on slot 7. LIVE: DOWN-walk + A+diagonal
  turnaround roll plows the type-5 Tetra aside; her CC push steers the roll-stab `CUT_F` lunge through
  the seam; the cut fires at `old=(-1692.314697265625, -955.0416870117188)` and lands at
  **`new=(-1727.1728515625, -990.4632568359375)` -- BIT-FOR-BIT the sim's prediction** -- then Link
  drops to proc 39 (falling), THROUGH the seam. **Every frame entry->cut is 0-ULP for BOTH actors**
  (the plow AND the push-steered lunge). Delivered by a clean DTM (never advancewith). This retires
  the session-22 GLITCH dependency: same corner, same target `new`, but a normal following Tetra.
  - **Winning setup (slot 7):** Link MOVED +110u NE along his facing to start
    (-1531.94677734375, -787.6950073242188) -- Dereck OK'd moving Link; the as-is start's roll entry
    lands ~110u short (wall-pinned). Tetra placed at **(-1645.696044921875, -919.3839721679688)**
    (walkable, bit-confirmed genuine). Stream: DOWN x6 -> A+diagonal (108,204) turnaround -> NEUTRAL
    roll -> UP+B at roll-index **b_step=16**. Measured live roll entry
    (-1516.116455078125, -765.1473999023438) facing 40835 m351C 0 speedF 26.
  - **Two delivery calibrations this cost** (on top of the four pushaside truths, which all carried over):
    1. **The from-rest walk is NOT yet bit-exact** -- the live roll entry is ~2.6u from the sim's
       from-rest entry, and the genuine Tetra region is f32-DUST sensitive to the entry, so the
       placement is solved AT the MEASURED live entry (pushaside truth #4, generalized). facing (40835)
       and speedF (26) ARE exact -- only the walk DISTANCE differs.
    2. **`b_step=16`, not the sim thrust+1=15** (pushaside was +1). At 15 the CUT fires ONE FRAME
       EARLY -> no lunge -> proc 90 recoil; at 16 it fires on the sim-step-16 frame and lunges through.
       The turnaround PRESS consumes an input, shifting the buffer by one vs the pushaside walk.
  - **Method that cracked it (do not guess inputs):** `turnaround.diff` per-frame BOTH-actor DTM-vs-sim
    diff showed the roll bit-exact (k0-k14 dLink=dTetra=0.00000) with the cut one frame early -> the
    b_step fix was named by the divergence frame, not guessed. The genuine region was LOCATED cheaply
    via the engine's unclamped-endpoint plane distances (`sweep_par` out[8]/[9] = behindA/behindB, a
    smooth ridge) instead of a blind fine-scan of the whole corridor.
  - Fixture `fixtures/hyrule_turnaround_clip_live.json`; gate `tests/test_turnaround_clip.py` (6 green,
    offline). Open (pure-sim polish, not the clip): model the from-rest slot-7 walk so the roll entry
    is computed, not measured (then it is a true one-shot; today `entry` measures it via one DTM run).

- **KILL-THE-GLITCHED-TETRA (session 23): the FOLLOW-ENABLED turnaround-roll clip is VIABLE in the
  sim; the solver is built (`turnaround.py`); live delivery was the open next step (DONE session 24,
  above).** The session-22 clip needed a GLITCHED no-follow Tetra; this is the successor with a NORMAL
  following Tetra. Dereck's **slot 7**: type-5 following-enabled Tetra idle in the corner, Link behind
  her facing away, sword OUT.
  The mechanic (all sim-validated): hold **DOWN** ~6 frames (speedF caps at 17 by ~frame 5; Tetra stays
  in her 130/230 follow band so she never engages) -> one frame **A + a DIAGONAL stick** = the
  turnaround roll ([[turnaround-roll-tech]]) entering FRONT_ROLL at nspeed 26 (full ~49u lunge; the roll
  SPEED comes from the walk cap, NOT the stick magnitude, so the entry stick is free to AIM) -> NEUTRAL
  roll -> **UP+B** CUT_F.
  - **PROVEN feasibility:** at a turnaround entry, facing in the seam-gap window (~40842, 224.35 deg)
    yields ~14-35 genuine Tetra placements landing EXACTLY on the shipped target `new=(-1727.173,
    -990.464)`. The lunge must aim THROUGH the fixed corner gap: outside the window `new` stays
    wall-pinned ~49u short and NO push helps. The octagon stick VERTEX only reaches 40758/40913 (miss);
    a **DIAGONAL stick (108,204) -> 40835** (or (108,203) -> 40849) hits the window under the slot-7
    camera (csangle 39981), NO camera change. The walk is ~6 frames, follow-safe (peak ~224u < 230),
    no initial Co overlap. Solver machinery gated: `turnaround.extract_schedule_at` is BIT-EXACT vs
    `fast_shove.extract_schedule` at the fixture entry/facing.
  - **Delivery = the session-22 recipe** (`pushaside.py` truths; [[tetra-clip-solved-live]] #4): the
    genuine Tetra spot is f32-DUST sensitive to the roll ENTRY (a ~0.2u entry shift relocates the whole
    genuine region out of a 20u box) and the from-rest walk is not yet bit-exact, so **seed the
    placement search at the DTM's MEASURED real roll entry**, fine-scan Tetra there, place her, deliver +
    per-frame diff (never guess inputs). `turnaround.py` has the offline solver (`search`) + stick
    builder (`build_sticks`) ready; the live plumbing (`entry`/`deliver`/`diff`, reusing `pushaside.play`
    with SLOT=7 sharing Tetra base 0x80ACD20C) is the next increment. See the session-23 handoff.
  - Ruled out this session: the octagon-VERTEX turnaround aim (40758/40913) never threads (wall-pinned
    49u short) -- the diagonal-stick aim is REQUIRED; a coarse (integer n_walk / discrete stick / integer
    thrust) sweep finds 0 genuine (the acceptance is f32 dust -- fine Tetra-placement is the only knob).

- **PHASE T / NORTH STAR ACHIEVED (session 22): the TETRA PUSH-ASIDE SEAM CLIP IS LIVE, BIT-EXACT.**
  Tetra stands at her spot from the START (`placed_step=0` -- an initial setup var, **no mid-run
  write**); Link's roll PLOWS her aside; her CC push steers the roll-stab `CUT_F` lunge through the
  seam at the (-1727,-990) corner. Delivered by a **clean DTM** (never advancewith). LIVE:
  the cut fires at `old=(-1692.314697265625, -955.0418090820312)` and lands at
  **`new=(-1727.173095703125, -990.4635009765625)` -- BIT-FOR-BIT the sim's prediction** -- then Link
  drops to proc 39 (falling), i.e. he is THROUGH the seam behind the corner. Winning setup: Tetra
  start **(-1652.2239990234375, -939.447998046875)**, roll entry (-1513.3475341796875,
  -763.5128784179688), thrust at sim-step 15, cut at step 16. Fixture
  `fixtures/hyrule_pushaside_clip_live.json`; gate `tests/test_pushaside_clip.py` (6 green, offline).
  This retires dead-end #19: the push-aside was always viable, the earlier "empty" was SCOPE.
  - **Four delivery truths this cost, all now permanent (do not relearn them):**
    1. **Tetra's START must be on WALKABLE floor** (`in_front` of BOTH seam walls). The sim clamps her
       to flat ground everywhere and NEVER models her falling, so it happily "stands" her behind a
       wall; live she falls OOB and there is **no push at all** (this is exactly how the first live
       attempt failed: her spot had `fB = -6.8`). The search now hard-constrains this.
    2. **The roll phase must hold a NEUTRAL stick, not UP.** A pushed stick (`msd > 0.05`) force-exits
       `FRONT_ROLL` the instant `roll_frame > ROLL_EARLY` (`land/procs/roll.py:60`), so the CUT can
       never fire OUT of the roll -- the B degrades to a plain MOVE-slash (proc 90 recoil, no lunge).
       The sim's own schedule (`fast_shove.make_inputs`) is NEUTRAL + one UP+B; **the DTM must deliver
       THAT**, not the capture fixture's UP-held sticks.
    3. **The B goes one step LATER in the DTM than in the sim**: the sim buffers B with a 2-step
       INPUT_DELAY (B at step 14 -> CUT at step 16), the DTM delivers it with 1 (B at sim-step 15).
    4. **Seed the sim at the DTM's ACTUAL roll entry**, not the capture fixture's. The DTM's
       calibrated walk (`dtm_make` 255->254) enters the roll ~0.004u away from the advancewith
       capture; on f32 dust that is block-vs-clip. Seeded at the real entry the engine is **0-ULP vs
       live on every frame for BOTH actors, including the cut**.
  - Open (the remaining pure-sim gap): the walk-up is still the CAPTURED slot-6 walk, so the roll
    entry is taken from a live trace rather than modelled. Closing it = a from-rest slot-6 anchor
    (cf. kaze's `rest.rest_state`) simulated on the DELIVERED bytes (254, not 255). The clip itself
    needs no live round-trip once the entry is known.

- **Phase T (session 21b, Dereck's correction): the ACCEPTED mechanism is the PUSH-ASIDE -- Tetra
  stands in place from the start (an initial setup var) and Link's roll PLOWS her aside into the
  clip-delivering position. NO mid-run writes.** The session-21 live "clip" below placed Tetra by
  teleport ON the last pre-cut frame -- that is a mid-run hack, so it is a VALIDATION artifact (it
  live-proves the engine, the graze-push physics, and the acceptance 0-ULP end-to-end), NOT the
  solve. The push-aside is NOT impossible: manual testing produced a **50.6u displacement** even
  with a bad angle/position (the clip needs ~49.99), so the earlier "plow-mediated staging never
  clips" result only means the SEARCHED SLICE was too thin -- one Link approach line, one entry
  point, 3 thrust steps. The search must widen: **roll timing (= Link's roll-entry point along the
  approach line -- the biggest knob, now a per-run engine param `link_x0/z0`, gated 15/15 vs the
  Python engine), Link lateral placement, a much wider/finer Tetra initial-position space, thrust
  timing, and roll angle (a schedule re-extract with a facing override)**. Tetra-from-the-start =
  `placed_step=0` (an initial condition, not a hack). See the session-21 handoff for the search plan.
- **Phase T (session 21): the fast exact engine + a teleport-staged live validation.**
  The two session-20 blockers fell in one session:
  1. **The fast coupled sim (>=100k sims/sec, EXACT -- not a predictor).** `tww_sim/core/_shovec.pyx`
     (build: `python _build_native.py _shovec`) runs the full coupled Link-roll + Tetra dynamics in C:
     the acch `CrrPos` for both actors (frsqrte `sqrtf_c`, `is_zero_x`, WallHDirect), the `dCcS`
     rank-split push pair, the complete type-5 Zl1 idle/move port (console sin/cos/atan tables), and
     Link's roll/cut folded to per-frame constants -- valid because (a) FRONT_ROLL/CUT world moves are
     `pos += f32(speedF*sin/cos(travel))` with a schedule-fixed speedF/travel (bonk disabled per the
     live-validated `m3570=False` grind), and (b) the animated Co-centre decomposes EXACTLY into
     position-independent per-joint f32-add constants (`body_cyl.roll_co_chain_consts`). Speed comes
     from exact-no-op reductions only: the static room cull (`land.walls.cull_walls`), an in-CrrPos
     AABB candidate prefilter, hoisted per-tri constants, precomputed WallCorrect slice chords, and an
     OpenMP `sweep_par`. Gated BIT-IDENTICAL to the live-validated Python `couple_replay` engine per
     placement (`harness/rollstab/fast_shove.py::gate_vs_reference`; `tests/test_shove_fast.py`).
     1.3 s/sim -> ~10 us/sim: a ~130,000x speedup.
  2. **A teleport-staged staging that threads (found by `harness/rollstab/search_shove.py`), kept as
     validation only (see 21b -- it is a mid-run hack, not the accepted mechanism).** The coarse sweep
     (13M+ sims, ONE approach line / entry point x thrust 13-15 x all placement steps) found no
     plow-mediated clip in THAT slice; the **last-pre-cut-step graze** (Tetra teleported onto the
     pre-cut Co-centre's graze circle so `old` stays on the wall pin and one clean ~0.6-0.83u
     seam-ward push feeds the cut) found **10 genuine coupled clips across 3 thrust timings** via the
     polar micro-search (angle 0.05 deg x depth 0.002u; the push sliver is dust, a 0.25u grid finds
     nothing), all bit-confirmed vs the Python engine. NOTE: acceptance slivers are per-`old`-bits --
     the session-18 golden push does NOT thread from the pin (`pred_genuine(pin, golden_push)` is
     False); never transfer a push between olds.
  3. **LIVE (slot 6): the teleport-staged clip reproduced, proving the whole physics chain.**
     `capture_cc_push slot=6 ... thrust_at=14 place_after_roll=14 tcx=-1625.9922189608035
     tcz=-923.4329080655332`: Link rolls to the pin (-1692.3143311, -955.0761108), Tetra appears on
     the graze, the UP+B CUT_F fires, and Link lands at **(-1727.45263671875, -990.7470703125)** --
     bit-for-bit the sim's genuine `new`, BEHIND the seam past the (-1727,-990) corner. Replay: both
     actors 0-ULP on the placement + clip frames (the parked-Tetra free-fall rows and the post-clip
     CUT tail are the known out-of-scope gaps). Locked fixture `fixtures/hyrule_tetra_clip_live.json`,
     gate `tests/test_shove_fast.py` (also gates the cull, the chain-consts decomposition, and
     native==Python). This retires any doubt about the engine, the CC push, the cut lunge, or the
     acceptance -- the remaining problem is purely the SEARCH for a no-hack staging (21b).
  - Also new: `land.walls.cull_walls` (order-preserving exact AABB cull), `fixtures/hyrule_shove_roll6.json`
    (the session-20 live shove capture, promoted from scratchpad -- the engine's gate fixture).
  - Open next (see 21b): the WIDE push-aside search (roll timing / Link entry / Tetra initial
    position / thrust timing / roll angle); then from-rest planning (the slot-6 walk-up modeled from
    a rest anchor, cf. the kaze `rest.rest_state`); the descoped CUT-tail/post-clip recovery.
- **Phase T (session 20): un-braced Tetra shove + roll-stab CUT_F entry LIVE-VALIDATED 0-ULP; the
  placement search was BLOCKED on coupled-sim SPEED (now resolved, above).** On slot 6 (Dereck's ideal setup: Link facing/camera
  40842 on-axis, sword DRAWN, ~528u runway) a straight roll into a movable behind-placed Tetra plows +
  repositions her and thrusts; the coupled sim (`cc_stepper` via `capture_cc_push`, now `slot=`/`sword_drawn=`
  aware) matches live BIT-EXACT for BOTH actors through the roll AND the CUT_F entry frame (the CUT tail
  diverges, descoped as in session 17). So the un-braced shove the staging search leans on is proven. BUT a
  460-placement offline sweep (thrust-frame 14, via the `couple_replay` engine) found **0 genuine clips**:
  closest `new` pins at the golden `old` z (~35u short), because a seam-ward push needs Tetra BEHIND, whose
  plow (a) is razor-chaotic and (b) knocks Link OFF the golden `old` so the lunge is wall-blocked short
  (seam-ward push and full-lunge-from-golden-old are mutually exclusive here at this timing; strengthens
  dead-ends #15-17). The FAST-centre predictor is INVALID (the push perturbs Link's feet, so his Co-centre
  is NOT Tetra-independent). **Blocker for the real search: the coupled sim is ~1.3s/sim** (99% in
  `acch_crr_pos` iterating all 765 walls/3162 tris every frame; anim secondary). Fix (handed off): cull walls
  to the corner (the pending Phase-W AABB cull) + precompute the roll Co-centre-offset + CUT `m3700` tables so
  the per-placement inner loop is pure arithmetic; target >=100k/sec. Then search placement x roll/thrust
  timing x placement-frame, and if empty, vary Link's roll angle/approach. Immovable Tetra (rank-10, near-
  guaranteed) is CONFIRMED IMPOSSIBLE here (decomp: escort hardcoded type-5 movable). Details:
  session-20 handoff; memory `tetra-clip-targeted-oneshot`.
- **North star: the TETRA seam clip, pure-sim** -- the phased plan (wall collision -> ground ->
  CC Link<->Tetra -> the Tetra clip) lives in `ROADMAP.md`. Phases W + G + the load-bearing Phase-C
  items are DONE; **Phase T is OPEN** -- its acceptance FOUNDATION landed (session 18). The Phase-T
  STAGING is the current open question (session 19 REOPENED it, below): how to position Link + Tetra so
  a controlled, seam-ward push lands on the cut frame. Remaining Phase-C items are the CUT *tail* (Co
  centre during the cut + the post-cut recovery proc), `GetCCMoveP` from Tetra's own recoil buffer, and
  the read-lag; the Phase-W full-room cull is speed-only.
- **Phase T (session 19): STAGING REOPENED -- the behind-Link *stationary* Tetra is REFUTED; the
  correct staging is now the open question.** An earlier draft of this entry claimed staging was
  "resolved = behind-Link stationary idle Tetra"; the coupled DYNAMICS refute it. What holds:
  - **The corner needs a push** (bare roll-stab is wall-blocked at every REACHABLE start; the wall pins
    Link at `old` ~= the golden and the bare CUT_F is blocked), and **the push must point TOWARD the
    seam** (bearing ~235deg, ~0.75u), which requires Tetra BEHIND Link (a corner-braced Tetra pushes the
    wrong way). Collision-valid start = Link's r=35 wall cylinder clears both walls (signed plane dist
    >= 35). These are sound.
  - **REFUTED: a stationary behind-Link Tetra cannot deliver a controlled push.** The needed push is
    only ~11deg off the roll line, so the delivering Tetra sits ~15u from the line -- exactly where
    Link's rolling Co centre travels -- so the roll-in PLOWS her (large chaotic pushes) and flings an
    un-braced Tetra ~40u away before the cut frame; the CUT_F then fires with zero/wrong push. The
    ONLY dynamically-controlled push is Link plowing a BRACED Tetra (sessions 15-17), but braced-in-
    corner points the wrong way. See dead-ends #17 and the session-19 handoff.
  - `harness/rollstab/solver_tetra.py` + `tests/test_tetra_solver.py` (6 green) exist and the offline
    STATIC-`co_move_pair` acceptance core is bit-exact vs the golden, BUT it assumes the refuted
    stationary-behind mechanism, so DO NOT build the from-rest solver on it as-is. Acceptance must be
    the DYNAMIC coupled cut (run the plow through `cc_stepper.CcCoupledStepper`), not a static predictor.
  - `solver.py`'s knob families gained an optional `F=` param (backward-compatible; default kaze) -- that
    part stands.
  - **NEXT (open): the staging strategy** -- position Link + Tetra so a controlled seam-ward push lands
    on the cut frame. Candidates (session-19 handoff): brace Tetra on the behind side; or accept the big
    braced-plow push and search old+aim+placement via the full coupled dynamics. Then it feeds the
    from-rest solver (needs a minted slot-3 rest anchor; none exists -- `mint.py` only translates within
    a room).
- **Phase T OPENED (session 18): the Tetra-corner seam-clip ACCEPTANCE FOUNDATION, live-anchored.**
  Measure-first (Phase-G discipline), the flooded-Hyrule corner at (-1727,-990) is now in the rollstab
  pipeline's conventions: `fixtures/hyrule_tetra_geo.json` (built offline from the live RAM golden
  `tests/golden/hyrule_seam_1727_ram.json` by `make_tetra_geo.py`: the two incident wall tris --
  wallA +X poly 2915, wallB +Z poly 2904, a 90.57-deg corner -- the 4-tri CrrPos barrier, `link_y` =
  Phase-G's flat 0.16327, seam vertex S, and the authoritative live-confirmed clip target old/new) and
  the acceptance module `geometry_tetra.py` (the `geometry.py` sibling, PUSH-AWARE: `pred_genuine(old,
  push)` tests the COUPLED endpoint `new = f32(old + push + lunge)` in the decomp `posMove` order, not
  the bare kaze `old + LUNGE`). **Established facts (gate `tests/test_tetra_geo.py`, offline, 5 green):**
  the corner is a NEEDS-PUSH clip -- the 49.2202u lunge (facing F=40874) lands **~0.7507u short** of the
  seam; a **~0.7506u Link CC push** (the ~1.5u corner-braced-Tetra overlap x the 0.50 rank-table share)
  steers `new` behind the seam and reproduces the live golden endpoint **BIT-EXACT** (0-ULP). Measured
  dust structure (informs the coupled solver): with the push fixed, `old` clips over a **~0.86u
  along-band at ~8% f32 density** (kaze-like -- the approach razor is threadable by the from-rest knobs,
  not a single lottery point); the push is razor-thin as a continuous knob but that is a NON-issue --
  it is produced bit-exactly by the coupled sim from Tetra's f32 placement, so the solver places Tetra
  at f32 coords, lets the exact push fall out, and tests the exact candidate (the seam-clip-solver
  discipline, extended to placement). NOT yet done: the from-rest COUPLED solver (search a Tetra
  placement + approach that lands `old` on the sliver) and its clean-DTM live clip -- the next increment.
- **Phase C CLIP-FRAME ORDERING now BIT-EXACT (session 17): the roll-stab CUT_F entry, LIVE-GATED
  0-ULP.** The clip frame is the single frame Link fires a FORWARD `CUT_F` out of the roll into the
  corner-braced Tetra, so it stacks -- in the decomp's `posMove` order (`d_a_player_main.cpp:2556-2610`)
  -- `posMoveFromFootPos` (the roll speedF move) -> consume `mStts.m_cc_move` (the ~22u CC push from
  the prior frame's `dCcS` overlap) -> the `m34C2` cut root-translate lunge (~49u) -> `dBgS_Acch::CrrPos`
  (the wall pass). This ordering was already structurally in `step()`; this session live-VALIDATED it.
  The coupled stepper already dispatches the roll->CUT continuation (`roll._roll_exit` -> `_cut_init` on
  the B rising edge with the sword drawn); `cc_stepper.couple_replay` now replays the capture's per-frame
  controller inputs (not a neutral hold) and seeds `sword_drawn`, so the B thrust fires the CUT at the
  same frame it did live. **LIVE (slot 3, `capture_cc_push.py` with `draw_at=`/`thrust_at=`):** sword
  drawn early during the walk-up (so the drawn-sword walk still rebuilds to the speedF-17 cap for a
  full-26 roll), Link rolls into wall-braced Tetra, and a UP+B thrust (a *neutral* B is a side slash --
  dead-end #12) fires an in-line `CUT_F` at roll anim-frame >17. The coupled sim reproduces **every
  frame from Tetra's placement through the CUT_F entry 0-ULP for BOTH actors** (the roll-into-braced-
  Tetra approach AND the push x cut-lunge x wall-pass on the clip frame). Gate `tests/test_cc_rollstab.py`
  (fixture `fixtures/hyrule_cc_rollstab.json`, no Dolphin via `couple_replay`).
  - Scoped to the CUT_F ENTRY (the single-frame lunge that decides the clip). The CUT *tail* diverges
    and is NOT asserted (a separate, non-clip gap): the sim keeps posing Link's Co centre with the
    frozen roll anim (`body_cyl.roll_co_center`) rather than the CUT pose, and live enters a post-cut
    recovery proc (`0x5a`) the sim does not model. Both are moot for the clip (fully decided by the
    entry-frame lunge; the roll never re-walks after) -- like the descoped roll->MOVE exit gap.
  - This capture is wall-BLOCKED (Link rolled straight into the corner, so `CrrPos` eats the lunge's
    z): it validates the ORDERING, not a clip-through. Threading the lunge behind the seam is the
    solver's job (Phase T), not this ordering gate.
- **Phase C CC-PUSH STEPPER wired + live-validated to the push frame (session 15).** The Co push is
  now in the per-frame stepper in the decomp's order: `LandState._cc_move` (set via `set_cc_move`)
  is consumed in `posMove` AFTER `posMoveFromFootPos` (the speedF/foot move) and BEFORE the m34C2
  cut root-translate + the CrrPos wall pass (`d_a_player_main.cpp:2556-2610`; the overlap that feeds
  it is computed in the DRAW phase, `dScnPly_Draw -> dCcS::Move`, from the prior frame's settled
  positions). `cc_push.co_move_pair` returns BOTH actors' `SetPosCorrect` moves (Link's is bit-
  identical to the shipped `co_push_link`; same-rank 50/50 -> equal and opposite). The coupled driver
  `harness/rollstab/cc_stepper.CcCoupledStepper` runs Link (`LandState`) + Tetra (`Zl1FollowState`)
  together, computing the overlap each frame from Link's animated roll Co centre (`body_cyl.
  roll_co_center`) and Tetra's cylinder. **LIVE (slot 3, `capture_cc_push.py`):** Tetra teleported
  into the corner (WallCorrect braces her), Link rolls in from far out and CONVERGES into her while
  she is wall-braced. The coupled sim reproduces this **0-ULP**: Link's wall-approach roll AND
  Tetra's teleport-into-corner brace are bit-exact every frame, and Link stays bit-exact right up to
  the frame the push is first consumed (proving the push is applied at the right point). Offline gate
  `tests/test_cc_gate.py` (fixture `fixtures/hyrule_cc_push.json`, replayed with no Dolphin via
  `cc_stepper.couple_replay`); offline math/consumption gates `tests/test_cc_stepper.py`.
- **Phase C PUSH FRAMES now BIT-EXACT through the whole roll (session 16): the body lean, not the
  morf.** `test_coupled_push_frames_bitexact` was RED because once the push converged (roll frame ~6)
  Link drifted; the session-15 note blamed the `roll_co_center` oldframe-morf. Root-caused this session
  by capturing the live lean terms (`harness/rollstab/capture_roll_lean.py`, mCyl centre + `mBodyAngle`
  + `m34F2/m34F4` per frame): the early-frame residual is **NOT** the morf (`initOldFrameMorf(mRoll.
  field_0x14=2.0,...)` touches roll frame 0 only) -- it is the missing `setWorldMatrix` base `ZXYrotM`
  z-tilt by `shape_angle.z` (the MOVE turn lean `m351C>>1`). A curved approach carries a nonzero turn
  lean into the roll (`mBodyAngle.x=y=0`, `m34F2=m34F4=0` throughout -- only `mBodyAngle.z==shape_angle.z`
  is nonzero); it decays ~35%/frame, and the old clean (lean-0) centre made the push overlap -- hence
  Link -- drift. Fix: `body_cyl.roll_co_center(..., shape_z=)` feeds the **previous frame's** lean to the
  base (the setWorldMatrix/setMoveSlantAngle 1-frame lag; the `jointBeforeCB` body_chn rotation
  contributes nothing to the xz midpoint, verified live). `LandState` now exposes `_draw_lean` + evolves
  `m351C` every frame; `cc_stepper` passes it and seeds `m351C` at roll entry from the live value.
  **RESULT (live re-capture, slot 3): every FRONT_ROLL push frame 0-ULP for BOTH actors** (was bit-exact
  only to the pre-push f14; now through the entire roll to f26). Regression: `body_cyl` 0-ULP vs
  `fixtures/hyrule_roll_lean.json` (`tests/test_body_cyl.py`); `test_cc_gate.py::test_coupled_push_frames_bitexact`
  flipped xfail->pass (scoped to the roll frames). Offline land + live land 14/14 byte-identical (the
  `state.py` lean change is inert on position).
  - Still open for Phase C: the roll's EXIT to MOVE is not bit-exact (the neutral-hold capture's f27+;
    the separate "mid-run stop -> re-walk" gap -- irrelevant to the clip, which fires a CUT out of the
    roll); `GetCCMoveP` wired from Tetra's own recoil pending-buffer; the three-way CC -> WallCorrect ->
    net-overlap ordering on the actual clip frame; the Tetra read-lag (execute order Link-then-Tetra).
- **Phase C Tetra FOLLOW + attention DONE (session 14): the Tetra counterpart state, LIVE-GATED
  0-ULP.** The type-5 (following) Tetra's per-frame model is decomp-faithful and bit-exact vs live:
  `tww_sim/core/npc_zl1.Zl1FollowState.step(link_pos)` runs the `optn_1`/`optn_2` idle<->move state
  machine (`d_a_npc_zl1.cpp`) -- engage at 3D dist > 230, turn (`cLib_addCalcAngleS 4/0x800/0x80`),
  accelerate (`cLib_chaseF` 1 u/f) to a distance-capped target speed (`0.04*sqrt(dist^2-130^2)`, max
  10), decelerate, stop <=130 -- then `posMoveF`/`calcSpeed`/`posMove` + a flat-ground `CrrPos` Y
  clamp. Live gate: `harness/rollstab/capture_tetra_follow.py` teleports Tetra far on slot 3, logs
  her chase back to a stationary Link; the offline replay matches **0-ULP over 119 frames** (pos +
  facing + speedF + action-state), engage->cruise->stop (fixture `fixtures/hyrule_tetra_follow.json`,
  regression `tests/test_tetra_follow.py`; seed from frame 1 past the 1-frame post-teleport settle).
  Also `zl1_attention_active(link_pos, link_facing, tetra_pos)`: the decomp-exact L-target / talk /
  speak AVOID region (`dist_table[0xAB]`: XZ < 300, |dy| < 300, Link facing within +-90deg of Tetra)
  so a planner routes the setup so an A/L press near her doesn't talk/lock instead. Her **BG
  collision** is also modeled + LIVE-GATED 0-ULP: `mObjAcch.CrrPos` is the SAME `dBgS_Acch::CrrPos`
  pass as Phase W (`dBgS_ObjAcch` subclass, no override) with her single R=50/half-H=30 AcchCir;
  `Zl1FollowState.step(walls=)` runs it. She floats with speed.y==0 on the corner (live), so the
  pass uses speed_y=0 (a -4.5 dip is 1 ULP off). Validated by a corner-wall eject
  (`fixtures/hyrule_tetra_wallcorrect.json`) - this WallCorrect wall-brace (wedged Tetra's CC recoil is
  canceled so she holds) is a validated MECHANIC; whether it helps the clip is OPEN (a corner-braced
  Tetra pushes the WRONG way, a stationary behind-Link Tetra gets plowed -- clip staging unsolved, see
  the Phase-T status entry). Mechanic page `knowledge/mechanics/tetra-follow.md`. Open Phase-C items: the `GetCCMoveP` term at
  the decomp's frame point, the three-way CC-push -> WallCorrect -> net-overlap ordering, the
  attention live reticle confirmation, and the Tetra read-lag (the follow gate used a stationary Link).
- **Phase G DONE (session 13): the Tetra floor is FLAT -> ground collision is a no-op for this clip.**
  Measured before modeling (as ROADMAP prescribes): the walkable floor Link's roll crosses at the
  (-1727,-990) Tetra corner (flooded Hyrule, savestate slot 3) is a single flat tri (poly 2917),
  normal (0,1,0), plane Y=0.16327, spanning the entire roll footprint old->seam. Verified by an
  INDEPENDENT method (normal recomputed from raw vertices via cross-product == the game's stored
  plane == (0,1,8e-08); a dense grid over the whole roll region finds no other walkable-height tri).
  The 25-deg surface sharing the XZ footprint sits ~560u overhead (terrain) and is never touched. So
  `getGroundAngle` r3 = 0 (already hardcoded in the sim's speedF `cM_scos` scale; r3<0 x0.85 never
  fires) and m35B8 per-foot ground-lift is provably 0 -- the existing flat-floor model applies to the
  Tetra clip unchanged; NO GroundCross/getGroundAngle/m35B8 modeling needed. Self-contained capture
  `harness/rollstab/capture_ground.py` (`dolphin_mem` only, capture_walls.py pattern) -> fixture
  `fixtures/hyrule_tetra_ground.json`; regression `tests/test_tetra_ground.py` (flatness + footprint
  coverage + single-plane; goes RED if a future Tetra spot ever shows slope).
- **Phase W CORNER ORDERING DONE (session 12): multi-wall WallCorrect in game order, LIVE-GATED
  0-ULP.** When the cylinder wedges between two non-coplanar walls, WallCorrect corrects them
  sequentially, so the poly ORDER decides the result. The game's order is its DZB block-grid walk
  (`WallCorrectGrpRp` -> `WallCorrectRp` octree DFS -> `RwgWallCorrect`), and since `ClassifyPlane`
  builds each block's wall list in ascending poly index it is reconstructable STATICALLY from the
  DZB header tables. `capture_walls.py` reconstructs that walk and writes the room's walls in exact
  game order to `fixtures/kaze_r11_walls_ordered.json` (stored bit-exact planes) -> the sim loads it
  via `land.walls.load_ordered_mesh`. Corner gate (`cornergate.py`): walk into the
  110-deg seam vertex on the minted `kaze_r11_wallcorner` anchor; **CORNER GATE BIT-EXACT** per
  frame (48/48, incl. 24 two-wall frames), and the SWAPPED order diverges (24/48) so the ordering
  is load-bearing. Golden `tests/golden/rollstab_corner.json`, regression
  `tests/test_rollstab_corner.py` (incl. an order-load-bearing guard). At kaze the seam is wallA
  (poly 705) before wallB (poly 713): same block 137, ascending index.
- **Phase W CORE DONE (session 11): WALLS IN THE STEPPER, LIVE-GATED 0-ULP.** `LandState(walls=)`
  runs the player-faithful per-frame CrrPos wall pass (`core.collision.acch_crr_pos`: every-frame
  LineCheck with the full normal-add/WallHDirect response, WallCorrect with the mid-frame gravity
  dip, console `sqrtf_c`, exact 2^-18 IsZero) + the proc feedback (setNormalSpeedF wall-hold, the
  m3570 roll-bonk latch, FRONT_ROLL_CRASH fully modeled, the sidle A-guard). Four clean-DTM gates
  on the minted `kaze_r11_wallgate_faceB` anchor (head-on hold / oblique slide / roll crash /
  slow-roll grind) verified **WALL GATE BIT-EXACT** per frame (pos bits + proc + facing), via
  `wallgate.py` (mint/plan/run/verify/golden). Goldens `tests/golden/rollstab_wall_*.json` +
  regression `tests/test_rollstab_walls.py`; mechanics page `knowledge/mechanics/wall-response.md`.
  - Planner-rejection contract: a bonk = FRONT_ROLL_CRASH in `visited`; a sidle-suppressed roll
    sets the sticky `sidle_blocked` (the sidle proc itself is intentionally unmodeled).
  - Phase-W open edge (speed-only): a full-room block-grid AABB cull so a corner could enter the
    2-minute solver budget (the sim iterates all 765 ordered walls today, ~33 ms/frame pure-Python;
    far polys already no-op, so a cull is pure speed). Walls for the ballistic hops + freeze frames.
  - **NEW flagged gap (non-wall, found by the grind gate): mid-run stop -> re-walk.** A full stop
    to WAIT and MOVE re-entry is NOT bit-exact (the WAIT row matched; the re-walk entry speedF
    diverged). From-rest entries are exact; avoid full stops inside plans until modeled.
- **Phase 0 / kaze OBJECTIVE MET (session 10): LIVE CLIP CONFIRMED, 0-ULP.** A solver hit planned entirely
  offline from the idle13 anchor's rest state shipped as a clean DTM and clipped through the
  seam live: the cut fired on the predicted frame at the bit-identical position
  (`d(old) = (0.000000, 0.000000)`, old=(9071.9804688,303.1956787),
  new=(9069.6601562,254.0301819)).
- **PURE SIM / NO CALIBRATION: satisfied.** The K0 live-calibration crutch is DELETED
  (`base_state`/`apply_calibration`/`calibrated_state` are gone); `rest.rest_state` models the
  from-rest idle->walk entry from the anchor seed alone (model terms above). The only remaining
  live run is the OPTIONAL per-new-anchor verification gate (`rest.py` CLI) -- outside the loop.
- Search cost: singles + start-crawl sweep ~15s; full drill found 4 hits in ~4 min on idle13
  (first hits well inside the 2-minute budget; the drill tail is depth-2 combos).
- Regression: `tests/test_rollstab_rest.py` + live goldens
  `tests/golden/rollstab_rest_{cruise,ship}.json` (2 green, 1 strict-xfail).
- **Known open gap (flagged RED)**: late FRONT_ROLL drawn poses drift 1-122 ULP vs live (ship
  trace rows 32-36; sub-1e-5 on near-zero coords). NO effect on any current plan element --
  m3598 is frozen during the roll, positions/facing/cut stay 0-ULP -- but a post-roll WALK
  resuming on blend frames would consume the stale toe stream. Prime suspect: the
  daPy_lk_c::jointBeforeCB body-lean on the MOMI/thigh joints (m3516/m3518/m351A quat concat --
  in the foot FK chain, currently unmodeled; listed as future work in SESSION_PROMPT.md), then
  m35C4 / foot-lift m35B8 / recovery shape angle. Decomp-first: jointBeforeCB + procFrontRoll +
  setFootPos (8780) + setWorldMatrix (9554).
- idle2/idle12 seed jsons predate the `rest_*` schema -- run `mint.capture_rest` (or re-mint)
  before solving off them.
- Dead ends (do not repeat; full ledger
  [knowledge/history/seam-clip-dead-ends.md](../../knowledge/history/seam-clip-dead-ends.md)):
  two-seg pursuit walks, ribbon-fit |g| minimization, per-move-set live bias correction,
  roll-as-anim-reset canonicalization, anchor-z transfer aiming, and K0 mid-run calibration
  (patched only the state the cruise could see; m3598=0 hid the rest).

Related: `knowledge/strategy/seam-clip-solver.md` (methodology page),
[[rollstab-clip-solver-mvp]] memory, `tests/dolphin/spotcheck_rollstab.py` (cut 0-ULP),
`tests/dolphin/spotcheck_swordwalk.py` (DASHS toe).
