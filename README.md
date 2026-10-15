# TWW Clip Finder

Seam Clip tools for The Wind Waker (JP)
- Bomb & Pot Push **finder**
- Moving Bomb & Pot Push movement **solver**
- Slash clip movement **solver**

## Requirements

- Windows x64. The `runtime/` folder provides Python and Tk. No system Python or
  compiler is needed to run the included launchers.
- Your own Japanese Wind Waker `.iso` (`GZLJ01`).
- [Zelda TAS Edition Dolphin]([(https://github.com/Biggben67/Dolphin-Zelda-TAS-Edition-/releases/latest)]) with its control pipe enabled for live state and
  recorded route searches.

Keep the folder together when moving it. On first launch, choose your ISO in
the file dialog. The launcher extracts the required animations and skeleton
into the `_generated/anim/` directory before opening the GUI.
Later launches reuse that cache unless the selected ISO changes. You can set
`TWW_ISO` to the ISO's path to skip the prompt. The chosen path is saved
only in `_generated/portable_iso.json` and is prefilled in the finders.

If a ZIP download reports a missing `_tkinter` module, check that
`runtime/DLLs/_tkinter.pyd` is present. An older package omitted the bundled
Python `.pyd` modules; download a new ZIP after the packaging fix. Windows may
also warn about unsigned executables. Verify the download source and review the
exact security warning; do not disable Defender or add a blanket exclusion.

## Finders

| Launcher | Purpose |
| --- | --- |
| `Bomb Push Finder.cmd` | Search stationary bomb or small pot B drop setups at a seam |
| `Moving Push Solver.cmd` | Capture a recorded pot/bomb route and search moving B drop clips, including optional OoB seam landing and roll parameters. |
| `Slash Clip Solver.cmd` | Capture a recorded route and refine walking, rolling, or mixed slash clips. |

For the static finder, enter the seam coordinates and choose live room collision
or an ISO offline room. For the moving finders, select the seam, input
your original route with starting and ending Dolphin savestates, and keep the
original movie paused in read-only playback. The C++ worker is bundled at
`TWW Engine/finder/bin/tww_slash_worker.exe`. The moving finders extract their
additional model and animation files from your ISO as the search starts.

Results, search caches, local settings, and captured routes stay in `_generated/`.
The finders do not guarantee that every seam has a solution. Verify exported
movies in Dolphin using the matching start state before relying on them.

## Building and Testing

Source code is in `tww_sim/`, `harness/`, `native/`, and `TWW Engine/`.
`_build_native.py` and `TWW Engine/build.bat`

```text
python -m pip install -e ".[test]"
python -m pytest tests/test_drop_push_gui.py tests/test_drop_push_clip.py
```

## What Is and Is Not Published

The `.gitignore` excludes `_generated/`, extracted collision fixtures, recorded
movies, savestates, game archives/models/animations, and specific machine
configuration. Do not force add these files. The source tree retains small
**numeric** lookup tables used for bit exact simulation, including console
trigonometry and empirically measured controller/camera responses. They are
not visual, audio, level, or animation assets. Removing them without replacing
their exact values would change the solver's behavior. If your publication
standard excludes *all* game-derived numerical data as well, do not publish
those tables or the prebuilt worker until you have a replacement strategy.

Review `git status` and the staged file list before the first push. If any
excluded data was ever committed in another repository, ignoring it now does
not remove it from that repository's history.

## Credits and Licenses

The Python simulation and bundled TWW engine carry MIT licenses in `LICENSE`
and `TWW Engine/LICENSE`; see `TWW Engine/NOTICE` for decompilation provenance.
The bundled Python runtime has its own notices in `runtime/LICENSE.txt`.
