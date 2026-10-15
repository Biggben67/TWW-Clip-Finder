# Camera steering (csangle)

**Answers:** How does the camera yaw affect movement? What's the per-frame camera-rate law? How do
you steer finely with the C-stick? Is omega speed-dependent?
**Status:** validated (live RE + exact integer recurrence in `tww_sim/core/camera/camera_exact.py`;
the ω lookup is now the complete 65536-cell grid, offline-locked by `tests/test_omega_table_integrity.py`).
F32-precision of the internal ω and the auto-flip envelope are open.
**Source:** live RE 2026-06-28; grid completed 2026-07-01; decomp symbols below. Research log: [history/camera-predict-history](../history/camera-predict-history.md).

---

> **Land is a different regime.** This page is the SWIM (subject-camera) yaw law. On land the
> camera runs `manualCamera` (C-stick-commanded target, cushioned chase; L presses blip the
> follow camera for 1 frame) - see [land-camera.md](land-camera.md).

## Why the camera matters

The stick is camera-relative, so rotating the camera rotates Link's entire travel axis:

```
world_travel_angle = stick_angle + csangle + 0x8000          (halfword, 0x10000 = 360°)
```

`csangle` is the camera yaw. It is a **fine lateral-steering lever** - [ESS](ess.md) gives only
coarse ~45° [snap](turnaround.md) control; the camera gives sub-degree control. Live chain:
`0x803AD380 → +0x34 → +0x2B0` (u16); named `csangle` in `dolphin_mem`.

## The per-frame law (k = 0.5)

The C-stick X commands an angular **velocity** (not a target angle), first-order smoothed with
factor **0.5**, integrated into the yaw, with a **1-frame input→camera lag**:

```
omega_t   = omega_{t-1} + (omega_cmd(substickX) − omega_{t-1}) · 0.5
csangle_t = csangle_{t-1} + omega_t
```

Steady state for a full deflection = **±3.0°/frame** (±546 hw). Evidence (full-right hold, successive
gaps halve → k = 0.5): `272, 409, 478, 512, 529, 537, 542 → 546`.

### Exact integer recurrence (bit-exact)

`camera_exact.py` models the stored s16 yaw exactly (the smoothing above is the float view of this):

```
target += omega_cmd(csx, csy)            # 1-frame input lag
yaw    += int((s16)(target − yaw) / 2)   # C integer divide, truncates toward 0
csangle = (yaw + 0x8000) & 0xFFFF
```
- `omega_cmd` is a **live 65536-cell lookup** of the full (csx 0..255, csy 0..255) grid,
  **speed-independent** (verified) and genuinely **2-D** - csy modulates the horizontal rate (e.g.
  csx=255: csy 32..220 → +546, but csy=255 → 199, csy=0 → 173). No off-grid gaps. The integer
  truncating divide reproduces both the build ramp and the release tail - a `round(omega)` model cannot.
- **Rest state:** with neutral C-stick, `target == yaw − 1` (a fixed −1 offset holds yaw still, since
  `int(−1/2) == 0`).
- `omega_cmd` is **asymmetric**: saturation `csx ≥ 175 → +546`, `csx ≤ 81 → −547` (= ±3.0°/frame,
  |d| ≥ 47). E.g. csx 160 (+32) → +18 but csx 96 (−32) → −19. The true low-side deadzone (→ 0)
  begins at **csx 113** (csx 109..112 give −1) - `camera_exact.py`'s "109..148 → 0" comment is a
  ±1 edge approximation; the 2-D table carries the exact values.

## omega_cmd(substickX) - the steering band

| substickX | Δ from 128 | omega_cmd (hw/fr) | deg/fr |
|-----------|-----------|-------------------|--------|
| ≤ 149 | ≤ 21 | 0 (deadzone) | 0 |
| 154 | 26 | 6 | 0.033 |
| 162 | 34 | 26 | 0.143 |
| 170 | 42 | 105 | 0.577 |
| ≥ 176 | ≥ 48 | 546 (saturated) | 3.0 |

**Fine-control band = substickX ~150–170** (0.01–0.58°/frame) - where deliberate steering lives.
Wide deadzone to ~149, then a steep ~doubling-every-4-units ramp, fully saturated by ~176.

## The steering primitive

Tap the C-stick a few frames, then return to neutral: net axis rotation = **∫ω**, and there is **no
snapback** - Link locks onto the rotated axis and continues with steady lateral drift. The release
tail adds ≈ (last ω) of extra rotation (Σ ω·0.5ⁿ). A 5-frame `sx=166` tap then neutral → +253 hw =
+1.39°, locked. This holds *during* a swim (rotation law identical standing or moving); Link's
facing follows csangle with a lag.

## The MANUAL (no-L) cam does NOT move csangle - only C-stick pan + wall collision do

**Scope: this is the MANUAL / free-behind cam with NO L pressed** (the regime the seam-clip
approach walks in). The L-target / recenter **auto cam** is a DISTINCT mode (`lockonCamera`
d_camera.cpp:3348; the DMC recenter `mAngleY = getDMCAngle(mMainStickAngle)` :902) that **DOES
change csangle** - it swings/recenters the camera behind Link. That mode is NOT characterized here
and is not used by the roll-stab approach (pressing L would lock a target and rotate the camera).
Do not read the "frozen" result below as applying to auto-cam / L-target.

Live-proven (session 69, 5 experiments in the open flat arena, centered C-stick, **no L**): walking
Link straight, through a full 90° turn, around a big continuous arc, or with a sustained
main-stick-X deflection leaves **csangle (`mAngleY`) bit-frozen** every time. There is **no
free-space behind-Link facing/position follow that feeds csangle in the manual cam.** Decomp
grounding: `dCamera_c::Run` sets
`mAngleY = mDirection.U().Inv()` (d_camera.cpp:905) and **csangle == the horizontal
`bearing(eye → center)` exactly** (verified live, diff 0 hw). `followCamera`'s behind-follow (blend
weight `m3B8`, gated on `mStickMainPosXLast`, :3082) moves the **view** direction/center, not the
controlled csangle the [stick decode](turnaround.md) reads. ⇒ the sim's `CameraManual` is
**free-space-complete**; nothing more to model there.

The **one** thing that shifts csangle with no C-stick input is `bumpCheck` (:893, every frame right
before the mAngleY write): the camera-arm **wall collision** that pushes the eye *laterally*
(changing the eye→center bearing). This is environmental and per project steer is **detected, not
modeled** - `harness/rollstab/cam_clean.py` probes it (a centered-C-stick approach walk must hold
csangle; any drift = contamination). Live: open arena CLEAN (0 drift); a GanonA straight-corridor
walk DIRTY (+20 hw at f11) with the arm length *unchanged* - the push is lateral, so csangle-drift
is the primary signal and arm-compression only a secondary "arm touching a wall" warning. Probe the
**intended approach bearing**, not just "forward" (the shipped GanonA clip's aim line stays clean
where the straight-down-corridor path does not). `getDMCAngle` (:902) can drive csangle off the
main stick in DMC mode, but it disengages for a normal walking approach (:897).

This invariant is now the mint's **primary camera gate** (session 70): `mint.cam_clean_screen`
parks on the seam aim line, freezes the cam at the aim csangle, and walks the bearing with a fixed
stick + centered horizontal C-stick, accepting a park only when the walk holds csangle. It replaces
the empirical `cam_screen` trial-pan hunt (which re-aimed each frame and confounded a drift with the
chase it induced) as `novel_deliver` stage 4.

## Plugging into planning

To move ΔZ laterally over a cruise, apply a tap of size X at frame F; lateral displacement is the
time-integral of `speed·sin(Δheading)`. **Frozen-camera plans stay bit-exact**: they hold
substickX = 128 (centered) ⇒ omega_cmd = 0 ⇒ csangle constant ⇒ zero regression.

`LandState` DRIVES `csangle` per-frame from the LAND camera (`tww_sim/core/camera/__init__.py` `CameraManual`
= a bit-exact port of `dCamera_c::manualCamera`): `LandState.step(sx,sy,buttons,triggerL,csx,csy)`
advances it and sets `self.csangle` before the stick target; a centered C-stick holds it frozen
(regression bit-exact - 13/13 live land tests). `SwimState` still holds `self.cam` constant (the
SWIM subject cam is a different engine; swim steering not yet wired).

### The C-stick → yaw-rate law is per-camera-STYLE - LAND is a full analytic port (bit-exact)
The two cameras use *different* engines. The **swim** (subject) cam's rate is the live-captured
`omega_table_full.csv`. The **land** free/behind cam is `dCamera_c::manualCamera`, and its rate is
NOT a scalar multiple of the swim table (truncation: swim `(166,0)=3` but land `=8`, not
`3·2.6685`). So land is ported analytically (`tww_sim/core/camera/cam_bezier.py` +
`camera_manual.py`), **validated 33/33 bit-exact vs live** (1-D + 2-D off-axis):

    ratio      = rationalBezierRatio(_16276·mStickCPosX, _9006=2)   # ±1 saturated at |stick|≥0.75
    cam_target = trunc(182.0444·(Degree(cam_target) + f32(ratio·scale)))   # cSGlobe::Val azimuth
    cam_yaw   += int((s16)(cam_target − cam_yaw)/2) ; csangle = cam_yaw + 0x8000

- `ratio` is the S-curve `dCamMath::rationalBezierRatio` (double precision, Newton `frsqrte` sqrt;
  Nonmatching in decomp → ported from the disassembly). Consts `d_cam_param::_4103..4113`.
- `mStickCPosX` = PADClamp(substick: min15/max59/xy31) → `/42` → `CStick::update` unit-circle clamp
  (`cam_bezier.cstick_normalize`, analytic, bit-exact incl. the 2-D axis coupling).
- `scale` = `styles[mCurStyle].styleParam[24]` (deg/frame), a **clean per-style constant**: LAND
  walk (MM83, style 61) = **8.0**; the swim subject cam ≈ 3 (styleParam[20]). Override only in the
  swim attention-lock branch. `styles` base `0x803485ac`, stride `0x84`, name @ `+0x80`.
- `dCamera_c` struct base (live) = `[[0x803AD380]+0x34]+0x244`; `mStickCPosXLast`@+0x16C,
  `mCurStyle`@+0x510, `mAngleY`(csangle)@+0x6C, `cam_target`@+0x3AE, `cam_yaw`@+0x0E.
- Neutral (csx=128 → ratio 0) is an identity round-trip for all 65536 targets → frozen-cam exact.
- The camera arm runs `lineBGCheck` each frame, so a pillar the arm swings into can redirect
  `cam_target` (environment, not the rate law).

## Decomp grounding (JP/GZLJ01)

`dCamera_c::Run` @ 0x80160260 (writer at +0x7ac, a Write16 = s16 - our u16 reads are exact);
`dCamera_c::CalcSubjectAngle` @ 0x8016cf54; `dCamera_c::subjectCamera` @ 0x8016d3a4;
`dCamMath::rationalBezierRatio` @ 0x800aca94 (the omega_cmd S-curve, Nonmatching in the decomp - hence
RE'd live, not decompiled). Full address list: [reference/addresses](../reference/addresses.md).

## Open

- **PLANNED - port the SWIM (subject) camera to analytic, like land.** The land free/behind cam is
  now a full bit-exact port, but the SWIM camera is a *different engine* (`dCamera_c::CalcSubjectAngle`
  @ 0x8016cf54, a BOUNDED angle offset, not this rate law), still served by the captured
  `omega_table_full.csv` (off-grid cells raise, not universal; steering not wired into `SwimState`).
  Porting `CalcSubjectAngle` would make swim C-stick fully analytic for any `(csx,csy)`. Scoped for a
  later session.
- **F32 precision** of the internal ω velocity (we read the s16 *output* exactly; ω is upstream).
- **Auto-flip envelope** - the speed/hold-length that triggers the auto-camera flip (the "hold
  C-stick down" convention guards against it); steering must stay in a non-flipping band.
- Negative fine-band symmetry sweep.

See [history/camera-predict-history](../history/camera-predict-history.md) for the full RE log and
[history/camera-model-history](../history/camera-model-history.md) for the omega-grid completion.

## See also

- [Turnaround](turnaround.md) (`m34E8 = stick_angle + 0x8000 + csangle`) · [Arrow](arrow.md)
  (`move_bearing = camAngle − facing`) · [model/predictors](../model/predictors.md).
