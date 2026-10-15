# TWW Sim Portable

Seam Clip tools for The Wind Waker (JP)
- Bomb & Pot Push **finder**
- Moving Bomb & Pot Push movement **solver**
- Slash clip movement **solver**

## Requirements

- Windows x64. The `runtime/` folder provides Python and Tk. No system Python or
  compiler is needed to run the included launchers.
- Your own Japanese Wind Waker `.iso` (`GZLJ01`).
- [Zelda TAS Edition Dolphin]([url](https://github.com/Biggben67/Dolphin-Zelda-TAS-Edition-/releases/latest)) with its control pipe enabled for live-state and
  recorded-route searches. Dolphin and its games are not bundled.

Keep the folder together when moving it. On first launch, choose your ISO in
the file dialog. The launcher extracts the required Link animations and skeleton
into the **ignored local** `_generated/anim/` directory before opening the GUI.
Later launches reuse that cache unless the selected ISO changes. You can set
`TWW_ISO` to the ISO's absolute path to skip the dialog. The chosen path is saved
only in `_generated/portable_iso.json` and is prefilled in the finders.

## Finders

| Launcher | Purpose |
| --- | --- |
| `Bomb Push Finder.cmd` | Search stationary bomb or small-pot B-drop setups at a seam; optionally teleport Link to a result. |
| `Moving Push Solver.cmd` | Capture a recorded pot/bomb route and search moving B-drop clips, including optional OoB seam landing and roll constraints. |
| `Slash Clip Solver.cmd` | Capture a recorded route and refine walking, rolling, or mixed slash clips with the C++ worker. |

For the static finder, enter the seam coordinates and choose live room collision
or an ISO-backed offline room. For the moving finders, select the seam, bracket
your original route with starting and ending Dolphin savestates, and keep the
original movie paused in read-only playback. The C++ worker is bundled at
`TWW Engine/finder/bin/tww_slash_worker.exe`. The moving finders extract their
additional model and animation files from your ISO as the search starts.

Results, search caches, local settings, and captured routes stay in `_generated/`.
The finders do not guarantee that every seam has a solution. Verify exported
movies in Dolphin using the matching start state before relying on them.

## Building and Testing

Source code lives in `tww_sim/`, `harness/`, `native/`, and `TWW Engine/`.
`_build_native.py` and `TWW Engine/build.bat` rebuild native components when a
compatible C++ toolchain is installed. For development with a separate Python:

```text
python -m pip install -e ".[test]"
python -m pytest tests/test_drop_push_gui.py tests/test_drop_push_clip.py
```

Some older offline tests use local game-collision fixtures or live captures;
these are intentionally not included in the public source tree. They must be
regenerated from your own game or supplied locally before running those tests.

## What Is and Is Not Published

The `.gitignore` excludes `_generated/`, extracted collision fixtures, recorded
movies, savestates, game archives/models/animations, and machine-specific
configuration. Do not force-add these files. The source tree retains small
**numeric** lookup tables used for bit-exact simulation, including console
trigonometry and empirically measured controller/camera responses. They are
not visual, audio, level, or animation assets; removing them without replacing
their exact values would change the solver's behavior. If your publication
standard excludes *all* game-derived numerical data as well, do not publish
those tables or the prebuilt worker until you have a replacement strategy.

Review `git status` and the staged file list before the first push. If any
excluded data was ever committed in another repository, ignoring it now does
not remove it from that repository's history.

## Credits and Licenses

The Python simulation and bundled TWW engine carry MIT licenses in `LICENSE`
and `TWW Engine/LICENSE`; see `TWW Engine/NOTICE` for decompilation provenance.
The bundled Python runtime has its own notices in `runtime/LICENSE.txt`. This
project is unofficial and is not affiliated with Nintendo.
