# Fast Acceleration Roll Brute Force

1. Pause at the desired starting state and save it to slot 5.
2. Load `Fast Acceleration Roll.py` in Dolphin's Python script loader.
3. Press **Start / restart search**.

The default base slot is 5 and the verified-best slot is 4. Both are editable.
The script reloads the base before every trial, so slot 5 is never modified.

The direction controls expose every direction that can produce this fast
family: **Target-walk left SIDE gate** and **Target-walk right SIDE gate**.
Enable either one or both. Straight forward selects the slower forward
acceleration bucket, while backward is outside this launch family.
These labels follow Link's internal target-walk direction: positive heading
offsets select `DIR_LEFT`, and negative offsets select `DIR_RIGHT`.

The simulator exhaustively ranks clean full-magnitude main-stick inputs that
enter the SIDE acceleration bucket. Both turn directions are interleaved so a
queued camera sample cannot hide the useful side of the threshold. Each gate is
combined with one- and two-row L timing. During replay, the main stick remains
held and is corrected against live camera yaw. C-stick `(128,100)` is held to
suppress target-camera movement.

TWW's game counter is 30 Hz while the controller stream is sampled at 60 Hz.
Each authored row is explicitly submitted on both input samples; only the
search/measurement state advances when the 30 Hz game counter changes.

The script never presses A. It measures `mNormalSpeed` after the first ATN
acceleration plus three following acceleration frames. A result near 15.4 is a
failed forward-bucket path; a result near 16.94 is the intended fast family.
Every measured improvement is saved immediately to slot 4, then slot 5 is
reloaded for the next candidate. If the trial budget is exhausted, slot 4
retains the best measured acceleration state.

Do not run another controller-writing Dolphin script during the search. The
script supports the JP `GZLJ` memory layout, including header-edited variants.
