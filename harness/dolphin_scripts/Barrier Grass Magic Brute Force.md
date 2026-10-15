# Barrier Grass Magic Brute Force

This Dolphin TAS Edition script searches sword draw and put-away timings for the
three-small-magic outcome after the Barrier Skip slash clip.

## Setup

1. Play the existing GameCube DTM and save its immutable starting state to slot
   5 at input row 368265.
2. Keep the existing movement and three grass slashes in the movie. The sword
   must be usable by row 370097.
3. Load `Barrier Grass Magic Brute Force.py`, check **Enabled**, and click
   **Start / restart search**.

The script first replays an unmodified baseline to learn exactly which input
rows have negative `mNormalSpeed`. Every later trial restores the original DTM
rows and adds isolated sword toggles only to that learned set. It uses B only
when the sword is sheathed and A only when it is drawn. A final negative-speed
opportunity is reserved to leave the sword drawn and settled by row 370097.
Generated sword pulses are forbidden on displayed input rows 368481 through
369089, inclusive. A delayed live pulse waits until its entire held-input block
can be placed outside that interval.

Success requires three new live `PROC_ITEM` actors with item type 9 (small
magic). The successful movie state is associated with and saved to slot 10.

Before each randomized trial, every original A/B press on a baseline
negative-potential-speed row is cleared. The script then authors a fresh
alternating put-away/draw sequence and verifies each edit by reading the DTM
row back immediately.

The default no-drop timeout is row 370281. If all three small-magic actors are
not present on that row, the script immediately restores slot 5 and begins the
next trial.

The GUI accepts the combined movie row numbers displayed by Dolphin. When a
Tingle Tuner GBA controller is present, those rows contain interleaved GameCube
and GBA polls. The script automatically maps them to controller 1's GC-record
indexes for `dolphin_dtm.get_gc` and `set_gc`; it never edits the GBA stream.
