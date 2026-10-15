# Test-owned DTM anchors

Savestate anchors for the live DTM validators (`harness/dtm/run_dtm.py`). Each test (or test
group) owns its starting slate here, so a run never depends on Dolphin savestate **slot 9** —
which other processes (and the editor) silently overwrite, and which we learned had quietly
drifted from its documented facing.

## Naming convention (load-bearing)

```
<test-or-group>@<isokey>.sav
```

- `<isokey>` is the iso basename without extension. The runner resolves it to
  `$TWW_ISOS_DIR/<isokey>.iso` (set it for your machine), so the image to
  boot is baked into the anchor name — no more `TWW-JP.iso` vs `twwgz.iso` confusion.
- Example: `cruise_cold@twwgz.sav` → boots `…/ISOs/twwgz.iso`.

`run_dtm` parses the `@<isokey>` tag automatically; you never pass `game=` unless overriding.

## These files are NOT committed

They are dumps of copyrighted game RAM (~27 MB), so `.gitignore` excludes `*.sav`. Only this
README is tracked. Regenerate an anchor locally:

```
# set up the slate (loadstate / writename / charge / reorient ...), then:
python harness/dtm/capture_anchor.py name=arrow_charged iso=twwgz
```

It prints the captured controllable values (v / anim / air / state / facing) — record those
as the test's expected endpoint.

## Anchors

| anchor | slate | notes |
|--------|-------|-------|
| `cruise_cold@twwgz.sav` | cold start, v=0, state 54, COLD_ANIM | shared cruise baseline (was `cruise_pump300k_rec.dtm.sav`) |
| `land_flatwalk@twwgz.sav` | flat wall-free room, idle (state 5, pos_z 764) | land-movement gate (`run_land_tests`): walk + ATN + roll |

## Movie-active fixtures (DTM playback)

Some techs are **dense frame-perfect input** that the `advanceseq` pipe can jitter (bug#2), so
they are locked by replaying a **recorded movie** instead. The fixture is a *movie-active*
savestate: loading it (`savestate` action `load`) restores the movie at frame 0, and plain
`advance` frame-steps let the recording drive the inputs (the faithful delivery).

- `wiggle_ebs_roll@twwgz.dtm.sav` — the wiggle-EBS-into-roll chain (roll@26 → roll-EBS/wiggle
  preserving ~−23 with facing held forward → L+Up cancel → 2nd roll@24.088 → stop @ pos_z 2341.62).
  The **inputs** live in the committed companion `wiggle_ebs_roll@twwgz.dtm.sav.dtm` (a small `.dtm`);
  the **`.dtm.sav`** is copyrighted RAM (~46 MB, gitignored, dev-local). `run_land_tests`'
  `wiggle_ebs_roll` case SKIPS when the `.dtm.sav` is absent. To (re)create it: load the movie in
  Dolphin at frame 0, then `python ../../../tools/dolphin_mem.py savestate savefile
  tests/dolphin/anchors/wiggle_ebs_roll@twwgz.dtm.sav`.
