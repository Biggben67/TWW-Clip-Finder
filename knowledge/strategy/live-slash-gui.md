# Live slash clip GUI

Launch `launch_slash_clip_gui.cmd`. This tool targets the standard CUT_F seam clip reached either
from a full-speed roll or directly from a walk.

## Workflow

1. Run JP Wind Waker in Dolphin and enter the room containing the seam.
2. Draw the sword, release the stick, wait for Link to return to WAIT, and pause Dolphin.
3. Put Link on the same floor as the target seam. A rolling search must start within 1400 units; a
   walking search must start within 380 units.
4. Enter the seam X/Y/Z. Y identifies the vertical seam edge; the prepared setup preserves Link's
   captured walkable-floor Y. Pasting `586.023132, 17.303171, -1413.401733` into any seam
   coordinate box fills X, Y, and Z together.
5. Set the wrapping unsigned-s16 facing range. It defaults to 0-65535; narrow it only when you want to constrain the resulting slash angle.
6. Select Rolling slash, Walking slash, or Walking Setup and scan. Walking Setup enters first
   person and settles the camera. Its exported input holds C-down to exit, taps perfect down for one
   frame, waits for WAIT_TURN to settle, then holds perfect up and slashes at normal speed 17.
7. For every accepted candidate, the finder exports one complete DTM, its matching `.dtm.sav`
   start state, and the `.dtm.sav.dtm` companion required by deep-session savestates. It does not
   restart Dolphin or play the movie.

The JP ISO is only needed once if `_generated/anim/link_anim_cuts.json` is absent. The GUI extracts
CUT_F/CUT_A root motion from the user's own disc and caches it locally. `DTM game ID` is a separate
six-character movie-header field. It defaults to `GZLJ01` and accepts any six printable ASCII
characters, including custom IDs such as `GZLJ11`.
The GUI restores its search fields from `_generated/live_slash_gui_settings.json`. It saves the seam,
mode, angle range, budget, result count, ISO path, and DTM game ID when a scan starts or the window
closes. The Dolphin PID is not persisted because it is process-specific.

Before capturing its room anchor, the finder checks Dolphin's movie state. An active recording is saved under _generated/live_slash_states/pre_search_recording_*.dtm and stopped so the generated start/end savestates are standalone; active playback is rejected.

## What is proved

The live adapter reads Link's position, floor Y, shape/travel angles, camera angle, state, normal
speed, forward speed, stick distance, animation phase/rates, foot smoothing fields, equipped item,
health, and WAIT pose mode from JP MEM1. It rejects a snapshot unless Dolphin is paused and Link is a
zero-speed WAIT with the sword drawn.

Critical health is rejected before search. At life `<= 6`, `checkRestHPAnime` can select the
low-health WAIT sequence; this changes the first walk-entry pose and translates the downstream roll.
The current exact from-rest runway model is validated only for the steady WAITS blend
(`m34C3=2` and MOVE0 rate `1.1`), so accepting a low-health or unfinished idle transition would
produce a false simulated candidate.

The room collision is not taken from an ISO cache. The GUI reads the current cBgW/DZB tables from
Dolphin and reconstructs `WallCorrect` group, octree, block, and polygon visitation order. It resolves
the requested vertical seam, builds the local ordered CrrPos barrier, and uses the existing exact f32
`SeamGeo` acceptance and wall-faithful trajectory re-simulation.

A result contains every main-stick byte, C-stick byte, and A/B edge by frame, plus the measured
old/new position and slash facing. Walking Setup holds C-down through the normalized turnaround,
approach, and slash.
A candidate is emitted only when the slash segment crosses the seam and the approach reaches that
exact f32 old position with live-order walls enabled. It records `dtm_path`, `start_savestate`,
`dtm_game_id`, and `transition_frame`.

Walking Setup additionally replays the complete normalized input timeline through the ControlPipe
from the exported source state. The accepted CUT_F transition must match exact seam dust in live
Dolphin memory. On genuine slopes, the finder reads normal speed, projected `speedF`, travel angle,
floor Y, and the full GroundCross mesh from Dolphin instead of assuming flat-ground speed 17. The
offline foot/waist ramp-animation tier can still report `SlopeNotModeled`; that does not replace or
weaken the exact live movement gate.

The one-frame perfect-down input enters WAIT_TURN. The finder does not begin the forward approach
until Dolphin reports that turn settled back to WAIT. WAIT_TURN resets the carried walk animation;
live regression probes from multiple first-person animation offsets reached the same speed-cap
position, facing, travel angle, projected speed, and animation frame bit-for-bit.

The exported DTM still requires manual playback confirmation. Starting a movie cleanly through the
pipe would require stopping/restarting a running Dolphin instance, which this GUI deliberately does
not do. The finder never presents a ControlPipe replay as proof that Dolphin's movie-delivery path
was tested.

## Exactness boundary

The reliable input contract begins at a paused stationary WAIT. Arbitrary mid-walk, mid-turn, or
mid-roll snapshots are deliberately rejected: their delayed controller and foot-pose history is not
fully represented by position/speed/angle alone. The finder preserves that hidden state in the
exported start savestate and authors the complete timeline at seed 0 with four controller polls per
simulated game frame. Walking Setup uses the input pipe only for live movement calibration and the
exact CUT_F gate. Exporting does not start a movie or alter Dolphin's process identity.

For a rolling search, the angle range is an active search domain. The planner enumerates the DTM-stable full-stick facings nearest the seam corridor, ranks them by the number of exact f32 old/new positions that genuinely cross the seam, then checks up to 32 ranked candidates until it finds three physically valid runways. A candidate is skipped if teleporting to its 580-unit anchor does not settle on valid floor, preserve the requested slash facing, or produce a 17-speed slash.

Each valid anchor is translated perpendicular to the approach until its measured baseline slash is centered on one exact old/new witness from that facing's displacement dust. The solver then runs the documented roll families ranked against that exact witness; final acceptance still evaluates the actual old/new segment rather than trusting the rank target. Near misses are not reported: the planner may invert their exact input streams onto neighboring f32 dust positions, but it accepts the result only after recapturing the teleported WAIT state and passing both the ordered-wall replay and `wall_faithful` gate.

Exact-facing density results are persisted in `_generated/live_slash_facing_cache.json`. The cache key
includes the complete seam geometry, camera angle, roll speed, and candidate aim. Repeating a seam
therefore skips the density screen, while a changed geometry or camera is recomputed automatically.
Prepared-anchor trajectories and final wall checks are never reused. The GUI budget is per-family; reducing it shortens first-time trajectory searches but can miss sparse solutions.
Geometric displacement is necessary but not sufficient. A facing can have exact seam-crossing old/new pairs while no unobstructed roll trajectory reaches those pairs on the room floor. In that case the GUI must return no setup; increasing the time budget cannot repair an invalid runway, though it can help a valid but sparse input family.

The portable bundle includes the CPython 3.12 `_collc` collision accelerator used by the exact-facing and dust screens. Without that binary the Python fallback remains correct but can turn a seconds-long screen into a many-minute operation.
