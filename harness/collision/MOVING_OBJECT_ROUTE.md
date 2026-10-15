# Moving Object Drop Finder

Run `launch_moving_object_drop_gui.cmd`. Pause the original movie in read-only
playback, provide its initial/final savestate slots and paste the seam into any
coordinate box. The finder captures the original route and restores the paused
state. It does not restart Dolphin or teleport Link.

The carried actor determines whether the release model is a bomb or small pot.
Heavy/large pots, throws, active old-pose morphs at release and unported player
transitions are rejected explicitly. The native movement, camera, lower animation
clocks, held prop pose, pending Co push and first post-release background correction
must reproduce the recorded route before search begins.
Small pots transition from carry to wait on the release frame: background
correction runs then, but gravity/movement starts on their next execution.
Captures record the pot's mode to distinguish execution before versus after Link,
even when wall correction leaves the held position unchanged.

Search changes both main/C-stick axes and the B edge, tests other speed/steering
and camera schedules, then refines coupled controls around the float32 seam band.
Timings receive a cheap initial screen before the budget is concentrated on
promising approaches. Camera plans include short horizontal/vertical pulses;
analog mutations span several adjacent frames and both sticks. Refinement keeps
distinct heading, speed and push families, and explores coupled three-axis changes
when single-byte probes stall. It does not stop just because the best ray stalls.
Normalized duplicate routes use a bounded per-family replay cache; the final
single-worker export check always bypasses it.
Owned moving-drop exports align to the beginning of the original four-poll input
blocks, not an arbitrary matching poll inside a held input. The slash finder's
existing timing path is unchanged. Extra opening lag before the first gameplay
update is included in the verified poll-phase search.
The immutable prefix is preserved up to the earliest bit-exact carried-movement
anchor. CPU worker count controls native batch concurrency. Cancellation stops
the worker without exporting unverified inputs.

Settings are separate from the slash finder in
`_generated/moving_object_route/settings.json`. Search results retain the best
route and several alternate near paths for another seed only when starting state, collision, movie/poll timing
and carried actor identity match. A no-hit result means the budget was exhausted,
not that the seam is impossible.

An accepted first push transition is replayed again on one CPU worker before
exporting `moving_object_clip.dtm`, its matching `.dtm.sav` and `.inputs.json`.
The GUI also checks each simulated hit once in Dolphin: controller samples,
movement/camera/animation clocks, held-object pose, release push, endpoint and
available following frames must agree. A live rejection sends that candidate back
to the search rather than exporting it. Temporary P1 movie edits are read back
and restored, along with the user's paused state; this does not restart Dolphin.
The authentic movie's controller lane and poll spans are retained, including
other controllers/GBA data. No near miss is exported as a clip.

Offline callers prove the **first push transition** in simulation unless they
supply a live verifier. GUI results include `live_verified`, `retention_verified`
and the bounded `retention_frames` actually observed, not a claim of unlimited
retention. Multi-frame prop interaction after the first transition has not been
ported. The small-pot baseline has been tested live; the bomb branch still
requires an equivalent live route check, enforced automatically during capture.
