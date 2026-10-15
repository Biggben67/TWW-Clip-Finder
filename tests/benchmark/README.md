# Planner benchmark — re-plan, record, DTM-verify

> **See also — land-sim throughput:** `perf_land.py` is a separate, self-contained tool that times
> raw `LandState.step` throughput with the anim engine active (the real per-frame hot path), and
> carries a bit-exact trajectory *fingerprint* so any non-bit-identical change fails loudly. Use it to
> measure micro-opt / Cython work (the native `core/anim/_anmc` accelerator):
> ```bash
> python tests/benchmark/perf_land.py             # time the default 2000-frame workload
> python tests/benchmark/perf_land.py profile=1   # cProfile the hot path (top 30)
> python tests/benchmark/perf_land.py fingerprint=1   # print the correctness fingerprint only
> ```
> The rest of this doc is the *planner-quality* harness (`run_benchmark.py`), a different concern.

**What this is.** A regression + data-collection harness that *re-runs the planner* on real
destinations, records a fully-reproducible result per plan, and (live) verifies each plan
against Dolphin so the recorded frame counts are **base truths**, not just sim claims.

**Why it exists.** `pytest`/golden and `test_planner` either REPLAY fixed seqs or only re-plan
tiny 3k/20k cold cases — none re-run the planner on the big dests, so a change that emits a
*worse plan* is invisible to them (e.g. `speed_gate=0.98` gave 200k = 561 vs known-best 555;
the suite stayed green). This harness re-plans and checks **frames + search work**.

## Quick start

```bash
python tests/benchmark/run_benchmark.py                 # smoke tier (fast pump cases)
python tests/benchmark/run_benchmark.py tier=full       # real dests (200k pump ~8 min)
python tests/benchmark/run_benchmark.py tier=smoke,full # everything
python tests/benchmark/run_benchmark.py name=cold_pump_50k assert=1 save=1
```
Then promote to base truth (needs a configured Dolphin — see below):
```bash
python tests/benchmark/verify_dtm.py                    # DTM-verify un-verified records
python tests/benchmark/verify_dtm.py name=cold_pump_50k tol=0.02
```
Inspect the accumulated dataset:
```bash
python tests/benchmark/analyze.py                       # latest record per case
python tests/benchmark/analyze.py history=cold_pump_50k # a case across git revs
python tests/benchmark/analyze.py reproduce=1           # replay latest, check determinism
python tests/benchmark/analyze.py verified=1            # only DTM base truths
```

## The pieces

| file | role |
|------|------|
| `cases.py` | canonical case defs (name → full planner params) + `known_best` table + tiers |
| `record.py` | the record schema: build / append / load / `reproduce()`; captures git sha + env |
| `run_benchmark.py` | run cases → append records → table → optional `assert=1` gate |
| `verify_dtm.py` | replay a plan's seq through the clean-DTM runner; fill the `dtm` block |
| `analyze.py` | dependency-free rollups over `results.jsonl` |
| `results.jsonl` | **committed** append-only dataset — one record per planned swim |

## Tiers

Tiers are **runtime buckets** (which cases run + the `max_frontier` they run at), not a
difference in what's recorded — every run appends the same rich record.

- **smoke** — fast pump-mode cases (small dests) at `max_frontier=1000`. Run after any planner
  change. Small dests still exercise the pump path (frontier saturation; and dips where present
  — 50k pump has them) and converge at 1000 (50k pump=280, 50k no-pump=282), so they catch the
  dip-pruning regression class cheaply (~10-30s/case).
- **full** — the real destinations in pump mode at `max_frontier=8000` — **the "8-min run" that
  actually produces the shipped optimum**. The hardest cases need it: at 1000 they land 1 frame
  short (200k pump 556@1000 vs 555@8000; 100k no-pump 402 vs 401). This is the base-truth
  producer. Slow (200k pump ~8 min). Run before shipping or when chasing frames / search speed.
  `known_best` is asserted here.
- **grid** — breadth/curve-fitting data at `max_frontier=1000` (BASELINE, sim-only): dense pump &
  no-pump curves 1k–1.5M, refill curves, the drowning boundary, `refill_until` sensitivity, and the
  **frontier-convergence sweep** (`*_f####` cases). Key finding: mf=2000 is the dominant frontier —
  optimal in 10/10 swept dests, ~4× faster than 8000, and at 400k *better* (812 vs 814). Frontier→frames
  is non-monotone (the A* prune isn't admissible), so a sweep beats one large frontier. See
  `knowledge/model/planner.md`.
- **refill** — the air-refill regime (200k–600k, the real TAS range) at `max_frontier=1000` for
  feasibility. `refill_pump_200k..600k` model a "pinned-back" free build (air pinned to 900 while
  `-x <= REFILL_UNTIL`) then one fresh-budget cruise; `cold_pump_500k_nodrown` documents the
  drowning boundary (non-refill → NOREACH). These are SIM predictions (`known_best=None`,
  BASELINE), not yet DTM-verified — the refill model is a user-specified 1-D approximation.

`max_frontier` is the runtime↔optimality lever (see `cases.py` `_TIER_FRONTIER`). The same case
recorded at both caps is left in the dataset on purpose — the frames-vs-frontier tradeoff is
exactly the kind of pattern the dataset exists to expose.

We benchmark the **pump (optimal) mode** because that's what ships; the no-pump cases are
recorded too (they exercise the shared cruise-DP core) but 50k no-pump = 282 ≠ the 280 optimum,
so no-pump is data, not the quality gate.

## Verdicts

| verdict | meaning |
|---------|---------|
| `PASS` | `frames == known_best` |
| `IMPROVED` | `frames < known_best` → a new base truth; update `cases.py` **after DTM-verifying** |
| `REGRESS` | `frames > known_best` → planner regression (nonzero exit under `assert=1`) |
| `BASELINE` | no `known_best` yet — recorded, establishes the number |

## Known live desyncs (`xfail_live`)

Some plans are optimal in the sim but do **not** reproduce live (the sim mis-models something —
usually a pump/dip landing on an anim phase the ×598 scramble mispredicts). Such a case is marked
`xfail_live=True` in `cases.py` with a `note`, and its `known_best` stays `None` (the sim frame
count is an artifact, not a base truth). It is an **expected** DTM failure, tracked until fixed —
when it starts *passing* verification, that's the signal the underlying bug is resolved: clear the
flag and set `known_best` to the verified frames.

Current: **`cold_pump_300k`** — sim says 705 fr (47 dips) reaching 300k; Dolphin reaches only
~282852 (17k short, live v=−524 vs sim −804). pump 50k/100k/200k/400k all verify bit-exact — only
300k diverges. The verified 300k base truth is the no-pump plan (711). See
`knowledge/history/open-questions.md` and memory `superswim-pump-300k-desync`.

## Base truth = DTM-verified

A record is only a **base truth** once `verify_dtm.py` has confirmed it live: it replays the
plan's seq as a clean-cadence DTM (movie playback, not the advanceseq pipe → no bug#2 jitter),
reads Dolphin's end-state at movie exhaustion, and compares to the sim's predicted end-state.
Frame count can't disagree (the movie is exactly that many frames); what's verified is the
**physics** — a clean v/anim/air/state match is the bit-exact claim that the plan really does
what the sim says. The result lands in the record's `dtm` block (`verified`, live endpoint,
deltas, anchor, tolerance).

**Seed must match the anchor.** These cold cases seed the cold anchor
(`tests/dolphin/anchors/cruise_cold@twwgz.sav`, v0/state54, logged mRate **0.5**) — the same
seed `cases.py` uses. `verify_dtm.py` refuses a plan whose seed doesn't match a known anchor
(a mismatch is the phantom-failure trap the locked-DTM HARD RULE warns about — see
`tests/dolphin/README.md`). Requires `dolphin.local.json` (paths) + the iso; each plan boots
TWW and plays its movie (~1–3 min/case).

## The record (schema v2)

One JSON object per line in `results.jsonl`. Self-contained: `planner` + `params` fully
determine the plan (no RNG), so `record.reproduce()` replays it and checks frames + seq.

- **provenance** — `schema_version`, `name`, `tier`, `timestamp`, `git_sha`, `git_dirty`, `env`
- **recipe** — `planner`, `params` (complete kwargs)
- **outcome** — `frames`, `reached`, `seq` (RLE action string)
- **stats** — `nodes_expanded` (successors GENERATED — the real work metric, ≠ `frontier_sum`
  which is states RETAINED), `nodes_gate_pruned`, `nodes_dominated`, `nodes_capped`,
  `frontier_max`, `frontier_peak_layer`, `frontier_sum`, `layers`, `capped_layers`, `ungated_retries`
- **derived** — `dips`/`pumps`, `chg`/`neu`/`ess` counts, `peak_v`, `end_v`, `expansions_per_action`;
  **sub-frame arrival** (`overshoot` = units past dest on the final frame, `last_step` = final-frame
  displacement, `arrival_subframe` = fraction of the last frame at which dest was crossed, in [0,1] —
  ~0 means the plan barely earned its last frame, a hair more speed could shave it); `wall_s`
- **gate** — `known_best`, `delta`, `verdict`
- **dtm** — live verification block (`null` until verified)

## Adding a case

Add a `_case(name, tier, dest, allow_pump, known_best, **overrides)` entry to `CASES` in
`cases.py`. Leave `known_best=None` for a new target; run it, DTM-verify it, then set
`known_best` to the verified frame count. Never lower `known_best` to a *worse* number to make
a run pass — that's the anti-pattern this harness exists to catch.
```
