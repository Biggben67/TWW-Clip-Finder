# TWW Sim Portable

For current installation, launcher, and source-publication guidance, see
[README.md](README.md). This file is retained for older links.

This folder contains the TWW simulation code, the C++ engine source and compiled
Windows worker, the bundled Python/Tk runtime, and the three seam-clip GUIs.
Keep the folder together when moving it; the launchers and bundled worker do not
require an installed Python, CMake, or C++ compiler.

## Launch

- `Bomb Push Finder.cmd`: static bomb/pot push finder.
- `Moving Push Solver.cmd`: recorded-route moving bomb/pot drop finder.
- `Slash Clip Solver.cmd`: recorded-route walking/rolling slash finder.

Run a launcher from any working directory. The moving finders use the relative
`TWW Engine/finder/bin/tww_slash_worker.exe` path by default. Their settings and
search results are written inside this folder under `_generated/`.

## External inputs

- The live-state and recorded-route workflows still need a running compatible
  Dolphin instance with its control pipe enabled. Dolphin is not bundled.
- Choose your own Wind Waker JP disc image in the GUI. Game images are not bundled.
- For a recorded route, select your Dolphin `StateSaves` folder and the starting
  and ending slots. Those user files are not copied into this package.

The first launcher run extracts Link animation data from the user's ISO into
the ignored `_generated/` directory. Additional room collision is read from
Dolphin or the selected disc image. Search output stays local in `_generated/`.

## Source and rebuilds

`harness/`, `tww_sim/`, `native/`, and `TWW Engine/` contain the simulation and
engine code. `tests/` and `fixtures/` are included for development. Building a
new C++ worker requires a compiler and CMake, but running the bundled worker
does not. The original project licenses are in `LICENSE` and `TWW Engine/LICENSE`.
