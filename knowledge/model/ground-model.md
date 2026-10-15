# The floors-mode ground model (Phase G)

**Answers:** How does the sim follow a sloped floor (`LandState(floors=)`)? What is the tier
structure (zero atan cell vs the unported ramp)? Which per-frame ground terms exist (the
gravity dip + GroundCross snap, the speedF slope scale, m35B8, m35C4, field_0x030) and where
does each come from in the decomp? What must an anchor seed carry for a bit-exact from-rest run?
**Status:** live-validated 0-ULP on the GanonA r0 micro-incline corridor: the full 28-row REST
gate (pos, pos_y, frame ctrls, m359C) is bit-exact (`tests/test_ganona_rest.py`, session 66).
Flat paths (`floors=None`) are byte-identical by construction. The ~10-deg ramp tier is
UNPORTED and raises `SlopeNotModeled` (refuse-don't-guess).
**Source:** `tww_sim/land/floors.py` (+ hooks in `land/state.py`, `core/anim/foot_speedf.py`,
`core/anim/foot_fk.py`); decomp `d_a_player_main.cpp` (line refs below).

## The tier fact that shapes everything

`cM_atan2s` truncates `ratio*1024`, so any slope under ~1/1024 (~0.056 deg) has
`getGroundAngle` **exactly 0**. On such a "zero atan cell" every angle-driven term (the speedF
cos scale, the uphill x0.85, the m34E2 anim-rate cos, the m34E0 waist tilt, the leg-IK
*angles*) is exactly zero, and only the **y-value** terms below are load-bearing. A slope that
leaves the cell raises `SlopeNotModeled` rather than approximating.

## The per-frame ground terms (game execute order)

1. **Gravity dip + GroundCross snap** (`GroundState.crrpos_ground`; d_bg_s_acch.cpp:122):
   `speed_y += gravity`, `pos_y += speed_y`, then snap up to the MAX plane-cross over the
   candidate floor polys (probe pos.y+60, walls excluded by ny >= 0.014). pos_y follows the
   floor plane.
2. **speedF slope scale** (`gnd_spz` / `speedf_r3`; posMoveFromFootPos :2408-2417):
   `sp7C.z *= cM_scos(r3)`, `r3 < 0 -> *= 0.85` (uphill), with r3 = getGroundAngle of the
   PREVIOUS CrrPos poly along travel. Exactly identity on the zero cell.
3. **setStepsOffset, the m35C4 walk base-Y lift** (`GroundState.steps_offset`; :9524, called
   :11528 only when the anim mode m34C3 is 1/4/9/10, i.e. NOT during WAIT(2), where m35C4
   freezes): first `cLib_addCalc(m35C4, 0, 0.5, 25, 5)` (min step 5.0 == exact 0 at walk
   magnitudes), then probe the floor **one speedF ahead** of pos:
   - ahead-floor HIGHER: **`current.pos.y = dVar5`** (an uphill pos.y snap-ahead!) and
     `m35C4 -= 0.7*rise`;
   - else: `m35C4 += 0.7 * (old.pos.y - pos.y)` when >= 0. At cruise on a downhill corridor
     m35C4 holds ~0.7 x one frame's dy (~4.9e-3 on the GanonA incline).
   `setWorldMatrix` (:9561) then builds the draw base at **pos.y + m35C4 + m3608** (m3608 == 0
   on this tier), so the drawn pose, m37B4, AND footBgCheck's r30[1][3] all ride m35C4. This
   was the s66 m359C residual's root cause: exactly 0 on flat, invisible until the incline.
4. **footBgCheck: m35B8 + field_0x030** (`GroundState.foot_bg_check`; :8712, gated on the
   old-frame flag, runs after setWorldMatrix): the two delayed-foot midpoints (stored
   mFootData t1) probe the floor (world point = fresh base x local midpoint, probe pos.y+30.1,
   accept < 60.2; the 10u/5-frame probe-freeze hysteresis arms only in the WAIT-family modes).
   - **m35B8**: `cLib_addCalc(m35B8, lower_sp18 - pos.y, 0.5, 7.5, 2.5)`, baked
     `base y += / m37B4 y -=` at the draw.
   - **field_0x030** (:8809-8823): the plant foot (lower sp18) gets 0; the NON-plant foot gets
     `0.3f * (its sp18 - r30[1][3])` whenever that clearance > 0 (or idle). This is **UNGATED**
     (the 0.1 floor lives inside `setLegAngle`, which only zeroes the leg *angles*). Consumed
     by `jointBeforeCB` (:276/:282) as `mTranslate.x -= field_0x030` at the R/LCLOTCH joints:
     a per-leg lift that shifts the drawn foot pose at ~1e-3 magnitudes on the incline and
     therefore feeds m359C (the plant-toe delta). Recomputed fresh each frame (never chased).

## Anchor seeding (bit-exact from rest)

`mint.capture_rest` captures, and `rest.rest_state` threads via `gnd_seed=`:
`rest_m35B8` (chased), `rest_foot024`/`rest_foot001` (probe-freeze hysteresis, history-
dependent), `rest_waist` (last drawn WAIST world translate, footBgCheck's r31 input), and
`rest_m35C4` (frozen during WAIT since setStepsOffset is not called there; 0.0 at a clean
settled rest). `field_0x030` needs NO seed: it is recomputed from the seeded t1/waist on the
first frame. JP RAM offsets: the decomp's US field-name offsets shift -0xD8 (m35B8 +0x34E0,
m35C4 +0x34EC; table in `harness/rollstab/mint.py`).

## Gates

- Offline: `tests/test_floors_ground.py` - flat-mesh step-identical equivalence, micro-incline
  plane-following (uphill rows sit at the *ahead* cross per setStepsOffset), ramp REFUSES.
- Live: `tests/test_ganona_rest.py` - the GanonA corridor REST golden, 28/28 rows 0-ULP
  including m359C and pos_y. Goldens are live-captured, never edited (SESSION_PROMPT hard rule).

Related: [land-sim](land-sim.md) (position accumulation), [anim-engine](anim-engine.md) (foot
FK), [fp-faithfulness](fp-faithfulness.md) (op-order rules),
[mechanics/collision](../mechanics/collision.md) (GroundCross/DZB).
