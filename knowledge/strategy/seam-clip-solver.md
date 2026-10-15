# Seam-clip solver (roll-stab through a wall seam)

**Answers:** How do we plan a roll-stab that clips through a razor-thin wall seam, and validate it
live? What does the acceptance region actually look like? Why must every candidate be tested with
exact geometry instead of a fitted window? What made the sim bit-exact from rest?
**Status:** LIVE-DELIVERED (2026-07-10): a solver hit shipped as a clean DTM landed 0-ULP on the
sim's predicted cut (kaze r11, idle13 anchor) and threaded the seam. Regression:
`tests/test_rollstab_rest.py` (live goldens).
**Source:** sessions 7-10 (2026-07-09/10), the session-56/57 throughput/cloud-spread/ranking
findings (2026-07-17), and the session-58 room-wide density screen + 157-corner delivery
(2026-07-18), `_notes/seam-clip-live-validation-handoff-*.md`;
the session-59 152m delivery + band_dense screen caveat (2026-07-18);
the session-60 824 delivery + floor/cam-track screen gaps (2026-07-18, dead-ends #43/#44);
the session-61 one-shot `novel_deliver` + cam-target settle lesson (2026-07-18, dead-end #45);
the session-62 second-room (Hyrule) mesh knob + floor/idle/log-jitter lessons (2026-07-18,
dead-ends #46-#48);
the session-63 third-room (Hyroom) delivery + armed-event/anchor-lottery lessons (2026-07-18,
dead-ends #49-#51);
run protocol + model term list in `harness/rollstab/README.md`;
collision model [`mechanics/collision.md`](../mechanics/collision.md) (CrrPos, Force25Bit);
cut mechanics in [`mechanics/land-movement.md`](../mechanics/land-movement.md) (roll stab);
constants in [`reference/constants.md#land-movement`](../reference/constants.md#land-movement).

## The acceptance region is f32 dust

A cut segment `old -> new` clips iff CrrPos does not block it, `old` is in front of both incident
wall planes, and `new` is behind one. Along the roll ray this predicate flickers at ULP scale:
the genuine set is a scatter of slivers 0.0005-0.01u wide (perp), striped per f32 x-column
(adjacent columns' slivers do not overlap in z), at ~10-30% linear density over a 0.5-3u
along-band. Consequences:

- Never target a fitted ribbon/centerline: being 1e-4 from the fit says nothing. Test the exact
  f32 candidate. The real `enter_cut` lunge is constant at fixed facing and `new` equals
  `f32(old + lunge)` bit-for-bit, so the pure-geometry test (`harness/rollstab/geometry.
  pred_genuine`) is exact and cheap.
- `old_z` must sit in a clear band (kaze r11: ~[302.6, 308.2]): lower and the roll is
  wall-blocked short of the cut; higher and the lunge cannot reach behind the planes.
- The roll carries the full 49.2202 lunge only from a capped walk: speedF == 17.0 at the A press
  is a hard gate (a sub-cap walk shrinks the lunge below the seam's displacement floor).

## Tetra-corner placement: a thin thread, ~f32-precise perpendicular (2026-07-12)

For the Tetra push-aside / turnaround clip the free knob is not `old` but Tetra's f32 START
placement `(x, z)` (`placed_step=0`): her plow feeds the CC push that steers the lunge. The TAS
question -- must we hit her position float-perfect, or is there a targetable range? -- was answered
by an offline sweep at the FIXED, live-measured slot-7 roll entry
`(-1516.116455078125, -765.1473999023438)`, facing 40835, m351C 0 (native `ShoveCtx.sweep_par`, the
bit-confirmed genuine test; ~66k sims/s; region located via the smooth pre-CrrPos behindA/behindB
ridge then column-chunked f32 sweeps to dodge the wide-grid OOM).

The genuine placement set is a **thin connected THREAD**, not a point and not a fat band:
- It runs ~**46u** along a ~**59deg**-from-+X diagonal in `(x,z)` (slope dz/dx ~ 1.67), over roughly
  x[-1651.7, -1628.1], z[-933.3, -893.2]. It **meanders +-~2u** off a straight fit (RMS resid 1.14u),
  so you FOLLOW the thread; a linear fit is useless (dead-end #8 restated for placement).
- **Perpendicular thickness = ~f32 dust**: at a fixed x-column the genuine z is one sliver, median
  **~8 f32-ULP (~4.9e-4u)**, range 1-16 ULP (~6e-5..1e-3u). This is the precision a TAS must hit
  perpendicular to the thread.
- **Continuity**: ~**84%** of consecutive f32 x-columns carry a genuine sliver (short 1-few-column
  gaps; runs up to ~35 columns), and adjacent columns' slivers OVERLAP/touch. So unlike the kaze
  linear-approach dust (disjoint per-f32-column stripes), the Tetra-placement set is a CONNECTED
  thread -- targetable as a curve with ~46u of along-freedom.
- The clip **landing `new` drifts** monotonically ~0.001u along the thread (12 distinct f32 values);
  the shipped target `new=(-1727.1728515625, -990.4632568359375)` is reproduced bit-exact only on a
  ~1-2u sub-segment. **Any** thread point clips (Link falls, proc 39) -- the target-`new` pin matters
  only to reproduce the exact shipped landing, not to clip.

**Verdict:** a valid Tetra placement is a **line, not a lottery point** -- ~46u of along-slack -- but
perpendicular you must be f32-precise (~5e-4u). At the shipped entry the thread sits **57-100u from the
nearest floor wall** (the seam walls themselves; all other nearby polys are overhead terrain at
Y~500 that a floor actor never touches).

### Wall-brace: relocating the thread onto wallB (entry-variation)

Bracing Tetra against a wall would pin the hard perpendicular coordinate for free (WallCorrect ejects
her to a fixed distance; the TAS just walks her into the wall). Shifting the ROLL ENTRY moves the
whole thread: a **perp- entry shift** (perpendicular to the roll facing) walks the thread toward
wallB (+Z, z=-990.256), and at entry ~**perp -1.3u** from the shipped entry the thread's corner-ward
tip reaches **exactly the wallB brace locus** (fB = TET_R = 50, i.e. z = -940.25562 -- verified: any
deeper placement is CrrPos-ejected to that z, so fB=50 IS the wall). Braced-genuine placements
(genuine AND at z=-940.25562) exist across a band of entries; `new` stays bit-exact on the shipped
target throughout.

**But there is NO usable slide RANGE -- bracing only removes one coordinate, and this is fundamental.**
The along-wall window = (thread thickness ~5e-4u) / sin(crossing angle), so a range wide enough to be
useful (~0.1u) needs the thread within ~0.3deg of PARALLEL to the wall at the brace distance. It never
is:
- **wallB (reachable): near-PERPENDICULAR crossing.** Near the brace point the thread's LOCAL angle is
  **75-82deg** vs wallB's 0deg (it meanders; 59deg was the global mean). So the braced-genuine window
  is just **2-3 f32-ULP (~0.0001-0.0002u in x) at ALL in-window facings** (swept 40805-40880; the angle
  never rotates toward 0). The genuine x shifts ~1:1 with the entry shift -- trade Link's roll-entry
  for Tetra's x, but each is a point. Bracing on wallB pins the perpendicular (z) coordinate for free
  yet the along-wall (x) still needs f32 precision: **2D-f32 -> 1D-f32, not a range.**
- **wallA (near-PARALLEL, ~78-82deg -> the wall that COULD give a range): UNREACHABLE.** The genuine
  thread's corner-ward tip is pinned at x~-1650 (fA~76) at EVERY Link entry tried (9 directions:
  perp/roll/axis shifts +-1.5-3u) -- closest approach fA=75.7, still ~25u short of the wallA brace
  (fA=50, x~-1677.66). The tip pin is an acceptance-geometry limit (where Tetra must sit to steer the
  lunge), not a knob not-yet-turned.

**Bottom line for the TAS:** Tetra can be placed AGAINST wallB (z pinned by the wall) but the along-wall
x is still an f32 point; no Link knob (entry position, facing across the seam-gap window) opens a slide
range. Untried knobs that MIGHT move the tip toward wallA (unproven, likely small): a curved walk-up
(nonzero `m351C` turn-lean at roll entry) and the thrust/roll timing -- both change the push/roll
geometry, but the tip pin looks geometric, so expectations are low.

## Dust DENSITY prices the search -- screen it before minting (2026-07-17)

Reachability (`SeamGeo.roll_reachable`) says a clip EXISTS from a standable `old`; it does not say
the focused search can FIND one inside its 2-minute budget. Fine-scan the dust (0.02 along x
0.0002 perp over the reach band, `pred_genuine`) and compare: the delivered 152-corner counted
**1409** samples (70% of along rows, 0.41u perp band -- one ~80s draw), the delivered mirror
**360** (17% rows, 0.021u band), while the z-mirror 97-corner's **84** (13% rows, slivers
<=0.0006u) defeated 8 independent knob-family draws (dead-end #39). Pick novel targets by density,
not reachability alone.

**Density is necessary but NOT sufficient (session 56, dead-end #40): the cost driver is the
chaotic crawl cloud's PERP SPREAD, not the dust count alone.** A ~7x run()-throughput upgrade
(lazy cruise-pose defer + fixpoint cross-hint + a Phase-B worker pool, all bit-identical -- gate
`tests/test_solver_fastpose.py`) bought ~1.2M exact 97m candidates across 7 draws, still 0 hits.
Measured on the top bracket: the byte-nudge cloud around a razor-close center (score 5.4e-4) lands
median **~1.9u** in perp from the nearest genuine column -- ~99.8% of candidates never enter the
razor band. Price a target by expected NEAR-BAND YIELD (the solver now prints it per draw), not
raw dust count.

**The perp spread was mostly a RANKING artifact, and the ranker was along-blind (session 57,
dead-end #41 -- overturns how #40 read the cloud).** Two structural bugs: Phase A ranked the
CRAWL-LESS arc trajectory while Phase B always added the K=3 crawl start, which displaces the
center ~1.15u of perp (the m2 magnitude family steers centers smoothly, -1.15..-3.2 on the 97m)
-- the "razor-close" brackets belonged to a family Phase B never evaluated; and the B2 ranker
measured perp distance to a 1e-3-ROUNDED column set with no along term, putting candidates 3-12u
of along from any real dust at the top of the drill order. Both fixed in the `solve_focused`
restructure: Phase A' ranks crawl-INCLUDED centers (arc x A_proj x the full derived m2 family,
pooled) by TRUE 2D distance to the exact sliver point cloud (`_dust2d`, disk-cached per seam;
`_dust_dist`, perp x200), with brackets consumed ROUND-ROBIN across arc families -- a center point
is noise at the cloud's ~1-2u chaotic scale, so a dense seam is priced by family BREADTH and a
thin seam by nearest-band-first order (greedy alone lost the 152 re-solve; breadth restored it:
3 clips in 111s vs the old structure's 1 in 80s, mirror 2 in 112s, all via B2 fines). Also
measured: a 1-frame FINE is NOT a local refiner in the roll form (children land median ~3.5u of
along from the parent -- chaotic like the nudge), so Phase B2 is extra independent draws, never a
last-mile closer. On the 97m the restructure lifted near-band yield (d_true < 0.02) from ~0 to
~4.5 per 110s draw (best child 0.00121); at ~0.2-0.4 expected hits/draw the thin seam still needs
several independent draw families, or a denser corner.

**The screen is now room-wide tooling, and it works (session 58): `harness/rollstab/seam_screen.py`**
ranks every enumerated corner seam by the density metric plus two delivery constraints the picks
must respect -- `link_y` on the walkable floor, and approach CORRIDOR length >= ~1000u (the
settle-until-frozen mint walk must genuinely end at the ~580u rest; teleporting to it resets the
cam leash, dead-end #42). Its first pick, the 157-corner S=(9689.14, -150.31) (1480 samples, 50%
rows, **0.33u band**, corridor 1400u), went mint -> REST BIT-EXACT -> **2 wall-faithful clips in
one default 112s draw** -> live 0-ULP clean-DTM clip, same session -- while the 97m (84 samples,
0.018u band) sat at 0 across ~15 cumulative draws. A WIDE perp band is the strongest single
predictor: the chaotic crawl cloud lands near-band candidates cheaply when the band is ~0.3u.

**Two screen gaps the 467/824 picks exposed (session 60) -- check both live before minting.**
The screen's `corridor` measures WALL clearance along the aim line, NOT floor coverage: the
467-corner read 1020u "clear" over a pit edge (floor ends d2S ~1050; parks beyond it fall OOB),
and its settle needed the full 42-frame cap (~722u, csangle never froze), so park = rest(580) +
settle had no floor -- unmintable (dead-end #43; settle travel is per-seam, budget the measured
value). And an approach corridor can carry a fixed, ROAD-triggered camera-trigger band (the 824
corner: csangle dips ~-300 s16 over d2S 588..384 and recovers) that fires or not depending on
the CAM's track: the default aim-derived pan target was the one track that clipped it, while
every probed alternate stayed frozen. The original fix was `mint.cam_screen` (probe alternate
`target_csangle`s at the park, pick a frozen one, pass `mint_online(target_csangle=)`) -- measured
per seam, never tuned (dead-end #44). With it the 824 delivered in one default draw. Also learned
there: the ~580u rest envelope is mostly PHYSICS for the roll (A-press runway ~506u + cap walk
~74u), so a short-corridor seam is not fixable by a smaller A_proj.

**The cam gate is now the csangle-INVARIANT probe (session 70, `mint.cam_clean_screen`), not the
trial-pan hunt (dead-end #56).** Live RE proved csangle is bit-frozen in free space under a centered
horizontal C-stick; the only mover is `bumpCheck` camera-arm wall collision. So a park is screened
by an invariant -- walk the seam bearing with a fixed stick + centered horizontal C-stick and assert
csangle holds -- rather than trial-and-error over pan tracks (which re-aimed each frame and
confounded a drift with the chase it induced). `novel_deliver` stage 4 probes the DEFAULT aim target
first, accepts it if CLEAN, and flags a DIRTY corridor with its first-drift frame/pos; the ROAD-band
alternates remain the fallback. See [`mechanics/camera.md`](../mechanics/camera.md).

**The whole recipe is ONE COMMAND now (session 61): `harness/rollstab/novel_deliver.py`** chains
geo -> band_dense re-check -> park-floor probe -> cam-target screen -> `mint_online` -> the REST
gate -> dust2d prebuild -> `solve_focused` (with the documented c3m knob-family retries on a
0-hit draw) -> `deliver ship` -> the per-seam test scaffold, aborting at the first RED stage
(per-seam resume state under `_generated/`). Its first run delivered the 151-corner
seam_0915_0918 live 0-ULP (default draw 0 hits, the c3m=0.78 family 1 clip -- the 152m pricing
repeated). The cam-target lesson it forced (dead-end #45): the settle travel is per-(seam,
TARGET) leash geometry (332..688u across one seam's five frozen targets), so pick the frozen
target with the SMALLEST measured settle -- a large-settle target parks the mint past the floor.

**Read the DENSE band, not the raw span (session 59).** The screen's `band` = full perp-column
span, which a single outlier column inflates: the 152m (the 152's z-mirror, polys 465x474)
screened `band` 0.458u but its dense cluster is **0.026u** (mirror-class) plus one stray column
at +0.322 -- and the default-knob `solve_focused` draw found 0 there. The screen now also reports
`band_dense` (largest contiguous column cluster's span); price a pick by THAT. A mirror-class
dense band is still deliverable, just not always on the first knob family: the documented
`c3m=0.78` start-crawl family gave the 152m **6 wall-faithful clips in one 111s draw** (delivered
live 0-ULP same session) after two 0-hit default draws -- when a thin-dense-band seam draws 0,
vary the documented knob families before concluding anything.

## Rooms beyond kaze r11

The pipeline is room-agnostic (`mesh=`/`prefix=`/`base=`), three rooms are live-proven, and the
room-level screening axes (floor quality, armed one-shot auto-events, boat/tidal non-rooms, the
anchor-lattice re-roll via frozen cam targets) have their own page:
[seam-clip-rooms.md](seam-clip-rooms.md) (dead-ends #46-#52).

## The sim is bit-exact FROM REST -- plan sequences need no live calibration

The from-rest model (`harness/rollstab/rest.rest_state`) matches live 0-ULP from row 0
through walk entry, cruise, arcs, partial-magnitude dips, and the roll. The terms that closed it
(decomp-grounded; full list + code pointers in `harness/rollstab/README.md`): the WAIT(4) rest
blend with procWait's per-frame re-init (the f31 frame round-trip), the anchor's STORED delayed
foot poses (a translated anchor keeps the pre-mint position's rounding noise), the end-of-frame
draw position (setWorldMatrix runs post-integration), Link's world Y in the pose base, the MOVE
turn lean (setMoveSlantAngle's m351C), and dtm_make's 255->254 stick delivery calibration --
plans must sim the DELIVERED bytes, never the raw plan bytes.

The mid-run K0 calibration this replaces patched only the state a cruise can see (m3598 == 0
hides the toe stream), which is why its dips missed live; historical detail in the session 8-10
handoffs.

## Knobs (from rest)

- **Start crawl** (the 1D approach): K<=3 partial-magnitude sticks (msd 0.52..0.889, bearing F)
  in the first rows, while speed is low -- each partial shifts the whole downstream trajectory
  along-track by a fine quantum, densely filling the A-press 17u phase grid.
- **Bearing arcs** (hold an off-bearing stick 1-3 frames, facing returns to F): gross lateral
  shift of the roll line, several units of reach.
- **Partial-magnitude fines** (1 frame): anim-phase roll-drift classes (discrete perp steps) and
  speed dips (dense along/z fill). Both quantize; combos fill combinatorially.
- **A-press threshold**: the along/z phase on a 17u grid.

Dead ends recorded so nobody repeats them: two-segment pursuit walks (perp treads quantize with a
dead band exactly over the window), per-move-set live bias correction (arc-dependent, not
transferable), a from-rest roll as an anim canonicalizer (does not resync), anchor-z transfer
aiming (live reseeding flips the press frame; the landing is chaotic), K0 mid-run calibration
(see above). Full research log:
[history/seam-clip-dead-ends.md](../history/seam-clip-dead-ends.md); run protocol in
`harness/rollstab/README.md`.
