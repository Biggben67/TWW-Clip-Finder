# View-frustum culling (what gets drawn)

**Answers:** How does TWW decide which actors are drawn vs culled? What frustum does it test —
FOV/near/far? Why is the culling far different from the render far? What per-actor volume is tested?
How do I see it live?
**Status:** validated — J3DUClipper ported bit-exact (`tww_sim/core/camera/frustum.py`); the port's 4
planes match the game's live `mDoLib_clipper` planes to f32 epsilon, and the per-actor `clip_box`
verdict matched the game's own `fopAcCnd_NODRAW_e` for **60/60** box-culled actors, 0 mismatches.
**Source:** decomp `JSystem/J3DU/J3DUClipper.cpp`, `f_op/f_op_actor_mng.cpp fopAcM_cullingCheck`,
`d/d_camera.cpp` view_setup; live GZLJ01 2026-07-05. Addresses: [reference/addresses](../reference/addresses.md).

---

## The model

Per frame the camera builds a **view frustum** and each cullable actor is drawn only if its cull
volume is inside it. The test is `J3DUClipper` (`mDoLib_clipper` singleton):

- **4 side planes** built from vertical **FOV-Y**, **aspect**, and **near** (`calcViewFrustum`): the
  near-face corners' cross products, normalized. Side planes depend only on `near`, not `far`.
- **near / far** are scalar depth bounds tested against camera-space `-z`.
- **cull test** transforms the actor's volume by `viewMtx · cullMtx` into camera space:
  - **box**: 8 AABB corners; culled only if all 8 fall outside one single plane (conservative).
  - **sphere**: center vs the 6 planes with the radius as slack.

`clip_*` returns "outside" (TRUE) = **culled**. This is a purely per-actor **frustum** test — not
distance-based and not room-based at this layer (room/scene visibility is a separate load/exec gate).

## The culling far is NOT the render far

The projection matrix uses the stage's render far (e.g. **400000**), but the cull frustum's far is
the stage **cull point** — `dStage_stagInfo_GetCullPoint()` = `mSchbitEnableAndFarPlane & 0xFFFF`, a
u16 (e.g. **20000**). So actors are culled well before the render far. Per-actor `cullSizeFar`
scales it: effective far = `cullSizeFar · cullPoint` when `cullSizeFar > 0` (e.g. sea barrels set
`cullSizeFar = 8000/cullPoint` to always cull at 8000).

## Per-actor cull volume (`fopAc_ac_c`)

`cullType` (`+0x1BF`) selects the volume: **boxes** `0x00–0x0E` (0–13 are preset boxes from
`l_cullSizeBox[]`, `0x0E` = CUSTOM at `+0x230`/`+0x23C`), **spheres** `0x0F–0x17`. `cullMtx` (`+0x22C`)
is the actor's local→world matrix (null ⇒ box coords are world-absolute). The game records the
outcome in `actor_condition` (`+0x1C8`) as `fopAcCnd_NODRAW_e = 0x04`; only actors whose
`actor_status` (`+0x1C4`) has `fopAcStts_CULL_e = 0x100` are tested.

## Seeing it live

- **In-Dolphin viewer** — `tww-python-scripts/cull_viewer.py`: a floating 3D orbit window drawing the
  frustum + every actor's cull box colored by CULLED/VISIBLE, re-rendered each frame; a disagreement
  with the game's `NODRAW` flag is drawn magenta. Runs the shared scanner via `dolphin.memory`.
- **Host-side** — `python -m harness.capture.capture_cull actors` prints the live cull table;
  `harness/capture/capture_cull.py::full_snapshot` is the reader-agnostic scanner both use.
- **Offline** — `tww_sim/core/camera/frustum.py` (`build_frustum`, `clip_box`, `clip_sphere`); guard
  `tests/test_frustum_clip.py`.

## See also

- [camera.md](camera.md) (the camera the frustum comes from; note `csangle` is yaw only) ·
  [reference/addresses.md](../reference/addresses.md) · [model/anim-engine.md](../model/anim-engine.md)
