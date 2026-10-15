# Extended ESS

Load `Extended ESS.py` in Dolphin's Python script loader, then enable its
checkbox. Hold your ESS input while brakesliding with the manual/free camera
active. Do not run another controller-writing script at the same time.

The script changes only C-stick X. Your main stick, buttons, triggers, and
C-stick Y remain yours. Both left and right ESS are supported. It waits while
targeting, outside negative-speed MOVE, or outside settled manual camera mode.
It does not enter free camera automatically or change your ESS side.

## Controller

- Reads the current player and camera pointers, velocity, facing, travel angle,
  camera yaw/target, maximum speed, and live per-room camera style parameters.
- Reads the actual queued PADStatus from RAM, then evaluates each distinct
  horizontal camera pulse followed by five neutral-camera frames.
- Compares against six neutral-camera frames from the same projected state.
  A pulse must save speed overall without losing more at any evaluated frame.
  Ties leave C-X neutral. No later corrective pulses are assumed.
- Uses a 16-angle-unit clearance constraint (about 0.088 degrees), but never
  sacrifices speed to reach it. If neutral already has less clearance, the
  candidate is compared against that clearance instead. The old 1024-unit
  penalty that rewarded retreating from the threshold has been removed.
- Displays predicted pulse loss, neutral loss, and saving; saves the selected
  prediction in version-3 diagnostic traces.
- Rejects predicted turnaround transitions and facing snaps over 120 degrees.
- Replans every game frame, reissuing the same input on duplicate VI callbacks.
- Does not invent a two-frame queue or wait two frames before taking control.
  The live pipe trace shows the already-polled input acting on the next game
  update. This replaces the previous, incorrect queue assumption.
- Carries the measured controlled-yaw offset rather than treating view-cache
  yaw and the committed/control yaw as identical.

This is bounded predictive control, not proof of an absolute optimal input
stream or permanent speed preservation. Animation-derived displacement,
collision, slopes, moving platforms, heavy/carry states, events, and other
camera modes are not modeled here. Actual state is reread each game frame.
Two consecutive material prediction mismatches stop assistance and save
`Extended ESS diagnostics.json` beside the script; toggle Enabled
off/on after checking the state and input timing to retry. A prediction guard
can detect a discrepancy after it occurs, not undo a lost-speed frame.

The script does not write game memory, rewind, or use savestate slots. It
supports the JP `GZLJ` memory layout, including GZLJ01 and GZLJ11; changing a
different region's header does not make that region compatible.

## Files and Tests

Keep `extended_ess_core.py` next to the script and the existing `tww_sim`
package available on the Python path. No new package installation is required
in this machine's existing TWW script folder. Reloading the GUI script also
reloads its helper so Dolphin does not retain an older solver in memory.

Sources used: `setSpeedAndAngleNormal` and `setNormalSpeedF` in the TWW decomp;
`tww_sim/land/procs/move.py`; binary-derived manual-camera yaw in
`tww_sim/core/camera/land_cam.py` and `cam_bezier.py`.

Offline regression suite: `tests/test_extended_ess.py`, including comparisons
against the existing movement integrator, delayed closed-loop trials, and
mocked Dolphin callback/input ownership tests. A captured M2tower pulse trace
also verifies the player update and camera target against live memory. It
exposes controlled-camera corrections of 40 angle units, with larger changes
later in the room. The user-saved 96-state trace is also covered: the new policy
is checked against neutral at every predicted prefix, and an independent
96-frame model rollout from its start is checked against a neutral rollout.
These are model comparisons, not live counterfactual measurements. The latest
end-to-end Dolphin script has not yet passed a live replay. Camera obstruction
and other unmodeled corrections can still invalidate predictions.
