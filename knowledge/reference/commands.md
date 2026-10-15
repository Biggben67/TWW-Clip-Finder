# Tool commands

**Answers:** How do I run the sim / planner? How do I A/B a reboost live? How do I validate a plan
against Dolphin?
**Status:** reference.
**Source:** `tww_sim/`, `harness/`, `../tools/dolphin_mem.py`. Read [`../tools/DOLPHIN_CONTROL.md`]
before driving Dolphin.

---

## Offline (no Dolphin)

```bash
# Simulate an action sequence (one action = one game frame). ess|chg|neu, ess:<rawY>.
python -m tww_sim.swim.sim seq "ess,20;chg,1;chg,1" v=-1630 air=900 anim=17.9 [every=N] [viz=out.html]

# Closed-loop reboost (fires a boost when anim enters [LO,HI]); see strategy/reboost.md.
python -m tww_sim.swim.sim essloop frames=150 trig=13,16 boost=4 v=-1630 air=900 anim=17.9

# Beam-search the optimal ESS/charge schedule (prints schedule + a seq string).
python -m tww_sim.swim.optimize frames=N v=-1630 air=900 anim=18.148 [beam=K] [viz=opt.html]

# Plan the minimum-frame route to a destination.
python -c "from tww_sim.swim import plan_min_frames; print(plan_min_frames(dest=200000, v=0.0, anim=0.06392288208007812, air=900)['frames'])"
```

`viz=out.html` emits a self-contained animated top-down viewer (play/scrub, efficiency-colored
trail, boost markers).

`plan_min_frames` prunes off-peak speed dumps by default (`speed_gate=0.98`; see
[model/planner](../model/planner.md#search)). For a real cold start, pass `cold_start=True,
cold_mrate=<logged move0 mRate>` and a full-precision `anim` so the build is bit-exact live.

## Live (needs Dolphin + slate) — `dolphin_mem.py`

```bash
# Open-loop scripted stick sequence in ONE process (attach once). Segments stickX,stickY,frames.
python dolphin_mem.py seq "128,110,150" [loops=K] [read=a,b,c] [every=N]
#   reboost example: seq "128,110,20;128,255,1;128,0,1" loops=7
# Closed-loop ESS with phase-triggered boost (reads anim each frame):
python dolphin_mem.py essloop frames=N trig=LO,HI [boost=B] [cooldown=1] [every=0]
```
`net` = start→end Euclidean (TAS progress); `path` = summed per-frame |Δ|. `substickY=0` (free-cam)
is forced each frame so the auto-cam doesn't flip.

## Live validation — DTM (the faithful delivery path)

The `advanceseq` pipe jitters on dense transitions ([bug#2](../history/resolved-bugs.md)); a cleanly
**authored** DTM played via the movie system is bit-exact. Use `harness/dtm/run_dtm.py` (generalized
clean-DTM validator: inputs + expected → author/play/compare v/anim/air/state/facing) and
`harness/dtm/capture_anchor.py` to mint anchors.

```bash
python tests/dolphin/run_tests.py     # live sim-vs-Dolphin gate (baselines)
pytest                                 # offline unit + golden suite
```

## See also

- [model/planner](../model/planner.md) · [strategy/reboost](../strategy/reboost.md) ·
  `../tools/DOLPHIN_CONTROL.md` (the dolphin_mem command source of truth).
