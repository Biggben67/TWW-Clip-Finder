# GZLJ01 (twwgz.iso, JP) function addresses — from framework.map

**Answers:** What is the JP/GZLJ01 live address of `<function>`? Why don't the decomp comment
addresses match the running game?
**Status:** reference (JP `framework.map`).
**Source:** JP `framework.map` (a local TWW decomp/extract). Live-verified against Dolphin.

---

⚠️ The decomp `tww/.inc` comment addresses are a DIFFERENT version (US/GZLE01).
The LIVE game is JP/GZLJ01. Use THESE (from the JP `framework.map`, a local TWW decomp/extract)
for any live breakpoint. Example mismatch: procSwimWait_init decomp=0x8013DB24 vs JP=0x8013a8a4.

| Function | JP addr | size | source |
|----------|---------|------|--------|
| daPy_lk_c::execute | 0x8011e750 | 0x14a0 | d_a_player_main.o |
| daPy_lk_c::setNormalSpeedF | 0x80105ae0 | 0x218 | d_a_player_main.o |
| daPy_lk_c::setSpeedAndAngleSwim | 0x801399e4 | 0x2c8 | d_a_player_main.o |
| daPy_lk_c::checkNextModeSwim | 0x80139cac | 0x94 | |
| daPy_lk_c::changeSwimProc | 0x80139d40 | 0x1f0 | |
| daPy_lk_c::setSwimMoveAnime | 0x8013a2b0 | 0x108 | |
| daPy_lk_c::getSwimTimerRate | 0x8013a3b8 | 0x80 | |
| daPy_lk_c::setSwimTimerStartStop | 0x8013a438 | 0x15c | |
| daPy_lk_c::procSwimUp_init | 0x8013a594 | 0x204 | |
| daPy_lk_c::procSwimUp | 0x8013a798 | 0x10c | |
| daPy_lk_c::procSwimWait_init | 0x8013a8a4 | 0x1b8 | |
| daPy_lk_c::procSwimWait | 0x8013aa5c | 0x1b0 | |
| daPy_lk_c::procSwimMove_init | 0x8013ac0c | 0xd4 | |
| daPy_lk_c::procSwimMove | 0x8013ace0 | 0x2f0 | |
| daPy_lk_c::setFrameCtrl | 0x80107c2c | 0x60 | |
| J3DFrameCtrl::init(s) | 0x802ed358 | 0x30 | J3DAnimation.cpp |
| J3DFrameCtrl::checkPass(f) | 0x802ed388 | 0x5a0 | J3DAnimation.cpp |
| J3DFrameCtrl::update() | 0x802ed928 | 0x43c | J3DAnimation.cpp |
| cLib_addCalc(Pf,f,f,f,f) | 0x80250074 | 0xc0 | c_lib.cpp |
| cM_scos(s) | 0x800ecfe8 | 0x1c | |
| cM_ssin(s) | 0x800ed004 | 0x1c | |

## Breakpoint mechanism (fork Python scripting, no rebuild needed for break-mode)
- `debug.set_breakpoint(addr)` → break_on_hit=TRUE, log_on_hit=FALSE (PAUSES core on hit; does NOT log regs).
- `debug.set_memory_breakpoint({At/Start/End, BreakOnRead, BreakOnWrite, LogOnHit, BreakOnHit, Condition})` — full flags (data watchpoint only, not instr fetch).
- On code-BP hit: CheckBreakPoints logs GPR3-12+LR to MEMMAP iff log_on_hit; CheckAndHandleBreakPoints emits CodeBreakpoint event then CPU().Break().
- `event.on_codebreakpoint(cb)` cb(addr); `event.on_memorybreakpoint(cb)` cb(is_write, addr, value); `registers.read_gpr(n)/read_fpr(n)`.
- To non-pausing call-trace a code addr (log_on_hit=true, break_on_hit=false) the single-arg debug.set_breakpoint is insufficient → would need a small rebuild to expose flags, OR use on_codebreakpoint+resume.

## Collision geometry (DZB) — JP/GZLJ01, live-verified 2026-07-06

For the collision model see [mechanics/collision.md](../mechanics/collision.md). The manager `dBgS`
is a fixed global; its 256-slot registry enumerates every loaded room/movable-BG collision mesh.

| What | Address / offset | type |
|------|------------------|------|
| `dBgS` manager | static `0x803B93A8` ( = `g_dComIfG_gameInfo 0x803B8108` + `0x12A0`) | — |
| `cBgS::m_chk_element[256]` | `dBgS + 0x00`, stride `0x14`: `cBgW* +0x00`, `flags +0x04` (bit0 = in use) | — |
| `cBgW`: mFlags | `+0x6C` (`GLOBAL_e=0x20` static room, `MOVE_BG_e=0x01` movable) | u8 |
| `cBgW`: `pm_vtx_tbl` (WORLD verts) / `pm_bgd` | `+0x90` / `+0x94` | ptr |
| `cBgD_t`: v_num / v_tbl / t_num / t_tbl | `+0x00 / +0x04 / +0x08 / +0x0C` | s32,ptr |
| `cBgD_t`: g_num / g_tbl / ti_num / ti_tbl | `+0x20 / +0x24 / +0x28 / +0x2C` | s32,ptr |
| `cBgD_Vtx_t` (vertex) | 12 B: f32 `x,y,z` | f32×3 |
| `cBgD_Tri_t` (triangle) | 10 B: u16 `vtx0,vtx1,vtx2,id,grp` | u16×5 |
| `dBgS_LinkAcch` (current floor tri) | `[0x803BD910]` → polyIndex `+0x554`, bgIndex `+0x556`, roof `+0x594` | u16 |

Surface class from face-normal Y (`cBgW_CheckB*`): `ny ≥ 0.5` ground, `ny < −0.8` roof, else wall.
The slot index **is** the `cBgS_PolyInfo` `mBgIndex`, so the floor `(bgIndex, polyIndex)` indexes
straight back into `m_chk_element[bgIndex]`'s mesh. Read WORLD verts from `cBgW+0x90`, not the DZB
`m_v_tbl` (they differ for movable BG). Live reader: `tww-python-scripts/ww/collision_geo.py`.

## Culling / camera object (JP/GZLJ01, live-verified 2026-07-05)

For the view-frustum culling model see [mechanics/culling.md](../mechanics/culling.md). All camera
fields hang off `camera_class = [[0x803AD380]+0x34]` (JP view_class layout == US `f_op_view.h`):

| What | Address / offset | type |
|------|------------------|------|
| `camera_class` base | `[[0x803AD380]+0x34]` | ptr |
| view near / far / fovy / aspect | `+0xC8 / +0xCC / +0xD0 / +0xD4` | f32 |
| view eye / center / up | `+0xD8 / +0xE4 / +0xF0` (cXyz each) | f32 |
| view matrix (world→camera, 3×4) | `+0x140` | f32×12 |
| `mDoLib_clipper` singleton | static `0x80398bfc` | — |
| clipper planes / fovy / aspect / near / **far(cull point)** | `+0x04 (Vec×4) / +0x4C / +0x50 / +0x54 / +0x58` | f32 |
| actor list head | `0x803654CC` → node: next `+0x00`, actor `+0x0C` | ptr |
| `fopAc_ac_c`: pid / cullType / status / condition | `+0x08(u16) / +0x1BF(u8) / +0x1C4(u32) / +0x1C8(u32)` | — |
| `fopAc_ac_c`: pos / cullMtx / boxMin / boxMax / cullSizeFar | `+0x1F8 / +0x22C(MtxP) / +0x230 / +0x23C / +0x248` | — |

Bits: `fopAcStts_CULL_e=0x100` (in status → cullable); `fopAcCnd_NODRAW_e=0x04` (in condition →
culled this frame). The cull point is `mSchbitEnableAndFarPlane & 0xFFFF` (u16), not the render far.

<a id="land-player-fields"></a>
## Land player movement fields (JP/GZLJ01)

The per-frame land-movement fields ([land movement](../mechanics/land-movement.md)) hang off the
player class `daPy_lk_c = [0x803AD860]` (== the live actor's `+0xD8`). They are exposed as
`dolphin_mem` **named reads** (registered in `tools/tww_jp_ref.*`, so scripts read them by name rather
than restating the raw offsets here); the ones the land captures/log use:

| Named read | Field | Meaning |
|------------|-------|---------|
| `potential_speed` | `mNormalSpeed` | signed speed relative to facing (see [walk-run](../mechanics/walk-run.md)) |
| `travel_angle` | `current.angle.y` | velocity direction (s16) |
| `shape_angle_y` | `shape_angle.y` | visual facing (s16) |
| `target_angle` | `m34E8` | stick world target = `m34DC(stick) + csangle` |
| `csangle` | camera yaw | `dCam_getControledAngleY`; the camera-relative offset |
| `anim_frame` | `[0x803AD860]+0x2F64` | active proc's frame controller (e.g. roll frame ctrl) |

Resolve exact offsets from the named-read registry (`build_tww_ref.py` output) rather than hardcoding
them; the registry is the single source so a layout change updates every script at once.

## Decomp function map (`tww/src/d/actor/d_a_player_swim.inc`, included into `d_a_player_main.cpp`)

These are the US/GZLE01 decomp symbols (logic identical to JP; use the JP table above for live
breakpoints). Where they appear in the mechanics:

| Function | What it owns | Mechanics page |
|----------|--------------|----------------|
| `setSpeedAndAngleSwim` | speed gain, arrow-angle cos penalty, stick handling | [charging](../mechanics/charging.md), [arrow](../mechanics/arrow.md) |
| `getDirectionFromAngle` (d_a_player_main.cpp:2278) | the 0x6000/0x2000 snap thresholds | [turnaround](../mechanics/turnaround.md) |
| `changeSwimProc` | swim entry: air=900, `mNormalSpeed *= 0.75` | [model/planner](../model/planner.md) (balloon) |
| `getSwimTimerRate` | `1 − air/900`, the air term | [animation](../mechanics/animation.md) |
| `setSwimTimerStartStop` / `setSwimMoveAnime` | anim frame-controller rate + the ×598 scramble | [pumps](../mechanics/pumps.md) |
| `procSwimUp` / `procSwimWait` / `procSwimMove` | the swim state procs (state 54/55) | [neutral](../mechanics/neutral.md), [ess](../mechanics/ess.md) |
| head-bob magnitude (d_a_player_main.cpp:2424-2428) | `field_0x60=0.4`, `field_0x7C=0.35` | [animation](../mechanics/animation.md) |

HIO tunables (`m_HIO->mSwim.m.field_0x..`) hold the magic constants (max speed, rates); see
[constants](constants.md). Not all are resolved to names in the decomp yet.
