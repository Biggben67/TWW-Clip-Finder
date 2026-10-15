# Native Slash Route Finder

Launch `Slash Clip Solver.cmd` from TWW Sim. Select the seam, StateSaves
folder, base and final slots (5 and 10 by default), JP ISO, and Walking/Rolling/Both.
The final slot's `.dtm` must contain the user's recorded route.

Leave the original movie active and paused in read-only playback. Do not stop
playback: Capture loads a copy of the base slot paired with the final slot's full
DTM. It advances by TWW's game frame counter (including lag VIs), checks the final
pose/speed/action bit-for-bit against the final slot, and restores the user's
paused state even on failure. No original slots or movies are changed and no
injected-input fallback or Dolphin restart is used.

The Python application reuses the existing Dolphin capture, controller decoding,
settings, seam selection, and full source DTM patching. Candidate movement, sword
animation, foot IK, camera updates, and CrrPos run in a persistent Release C++ worker,
batched across up to 16 CPU threads. Each CPU lane reuses its collision world.
No Dolphin reloads occur during candidate search. Settings are saved on close.
Comma separated XYZ coordinates can be pasted into any seam coordinate field (From the collision viewer script).
 
Before mutating inputs, native replay must reproduce the captured approach's
XYZ, speed, facing, action, camera yaw, camera eye and center, and lower-body
animation clocks/blend ratios as identical f32 values. Local refinement also
validates the recorded slash entry. Raw movie polls must
match the captured game-controller samples at their measured timestamps.
The finder rejects a drifting
import instead of applying a fitted coordinate offset. Acceptance requires an
actual native sword transition, uncorrected crossing, and three following frames
remaining behind a crossed wall. Exported movies are simulation candidates, not
live verified results. An accepted route is replayed again on one CPU lane before
export. The full original movie and matching base savestate are preserved.

The search first refines the recorded route, then tests coherent alternative
camera paths, segmented walking approaches, target-launch recipes, roll launch
timings and later slash windows. Longer routes can extend beyond the recording;
the exporter preserves its prefix and controller lanes, refusing extensions if
another controller is still active. Every slash entry is evaluated, so a
preparatory slash cannot hide a later crossing.
Local slash timing changes move the B press as well, including the measured
sword-equip delay. Walking and Rolling selections are strict; choose Both to
allow either type. Replanned suffixes replace every owned controller field,
including hidden intra-update button edges, and use a four-poll gameplay clock
when all recorded CPAD samples verify it. VI spacing alone is not a game clock.

Near misses receive coupled main/C-stick refinement using replay-measured
sensitivities. Estimates only propose inputs; acceptance always replays native
movement and collision. The float32 band on both sides of the ideal vertex ray
is searched, rather than assuming the clippable dust is exactly ray zero.
The evaluation cap is shared across search windows, with reserved fine-search
budget. A final quarter of the budget is reserved to concentrate precision work
on the strongest route after comparing the alternatives. Saved results retain
their control-row mapping and route identity and
are reused as replay-tested seeds on the next search.
Cancel remains available during native batches. Unsupported candidates are
counted in the log/result JSON. A worker failure stops the run explicitly instead
of being mislabeled as an exhausted search. No result does not prove impossibility.

## Current Limits

- JP player layout/HIO only; custom game IDs do not imply other regions are supported.
- The entire active BG registry is imported, including stationary MoveBG actors,
  world-space vertices/planes, runtime collision lists, bounds, priorities and BG IDs.
  Geometry or registration changes during the recorded route are rejected:
  animated BG motion and moving-floor carry are not implemented.
- FOLLOW, MANUAL and SUBJECT camera-state import. Unimported camera targets and
  other initial camera algorithms are rejected. Passing one recorded route is
  not validation of every possible camera mode or room interaction.
- Idle-turn uses the JP caller chain's inherited PPC f27 value (zero), not an
  uninitialized host variable. The unchanged caller register was checked in the
  ROM, and a modified real-room idle-turn route matches Dolphin's animation clocks.
  MOVE_TURN (24) and SLIP (25), including recovery, are implemented.
- Replanning starts at the earliest bit-exact imported anchor. On the GanonA
  regression this preserves the already-started sidehop, but varies its camera
  and the ground route after landing. It does not yet replace the initial
  first-person exit/hop and is not a complete arbitrary-room path planner.
- The engine's unported action transitions reject a candidate. Sword-contact/clank
  actors remain boundary stubs; test exported movies in Dolphin.

## Build

The source also lives in the requested TWW Engine clone under `finder/`.
With the MSVC developer environment loaded:

```powershell
cmake -S finder -B build-finder -G Ninja -DCMAKE_BUILD_TYPE=Release -DTWW_ENGINE_SOURCE=.
cmake --build build-finder --target tww_slash_worker
```

Use an absolute path for `TWW_ENGINE_SOURCE` when configuring from another directory.
Alternatively, run `finder/build.cmd` to locate Visual Studio, build in Release mode,
and install the worker into `finder/bin`. The included executable needs no compiler
to run; the existing TWW Sim Python runtime is still used for capture and the GUI.
The worker needs the observation/import hooks added to `engine/session.*`,
`J3DFrameCtrl`, and `mDoExt_MtxCalcOldFrame`, sword-equip/common-proc boundary fixes,
the common sword HIO table, and JP idle-turn/MOVE_TURN/SLIP behavior in `d_a_player_main.cpp`.
The compiled executable is installed at `TWW Engine/finder/bin/tww_slash_worker.exe`.

## Validation

`python -m harness.validate.native_slash_smoke --worker <exe> --iso <JP ISO>
--output <directory>` exercises walking and rolling sword transitions on a synthetic
floor and compares all output frames across CPU thread counts. This is an engine
smoke/throughput test, not proof of a real clip. No Dolphin state is changed.

`python -m harness.validate.native_camera_route --output <capture-directory>
--worker <exe> --iso <JP ISO>` checks six suffix windows in the captured GanonA
regression route. Run the focused Python regressions with:

```powershell
python -m pytest tests/test_native_route.py tests/test_native_route_playback.py tests/test_recorded_route.py tests/test_smart_route_gui.py
```

`python -m harness.validate.native_movement_paths --worker <exe> --iso <JP ISO>
--output <directory>` exercises direction reversal, brakeslide recovery and
animation clocks on one and ten CPU lanes. Optional `--trace <capture.json>
--batch <batch.json>` rechecks a captured-room candidate batch.

`harness.validate.native_live_movement` is a bounded diagnostic, not live brute
force. It explicitly edits/readbacks the runtime movie buffer because read-only
savestate loads retain existing inputs. It confirms consumed CPAD inputs before
comparing movement/animation, restores edited rows, and restores the paused state.
