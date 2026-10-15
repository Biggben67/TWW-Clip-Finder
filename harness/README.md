# harness/ — the live-Dolphin research & validation layer

Everything here drives a **running Dolphin** via `dolphin_mem` (in the sibling `../tools/`, reached
through the `# locate tools/` sys.path bootstrap). It is optional dev tooling — the pure-offline
`tww_sim` package never imports it.

## Before you touch Dolphin

Read **[`../tools/DOLPHIN_CONTROL.md`](../../tools/DOLPHIN_CONTROL.md)** — the single source of truth
for every `dolphin_mem.py` command and named address. It opens with an
[answer-first "I want to… → command" jump table](../../tools/DOLPHIN_CONTROL.md#i-want-to--command-jump-table).

## What's here

| Subpackage | Role |
|------------|------|
| `capture/` | Read live game state (per-frame internals, stick/omega grid dumps, land walk golden). |
| `validate/` | Sim-vs-live checks (cruise, arrow, coldstart, plans). |
| `dtm/` | Movie authoring/playback — **`run_dtm.py`** is the generalized clean-DTM validator (inputs + expected → author/play/compare v/anim/air/facing; trustworthy vs the `advanceseq` pipe per [bug#2](../KNOWLEDGE.md)); `capture_anchor.py` mints anchors. |
| `search/` | Live-grounded planning (cruise-pump search, pump insertion/scan). |
| `anim/` | J3D animation probes (foot/blend/speedF, chain, entry). |

Shared: `dolphin_env.py` (per-machine paths + one-call warm-up `ensure_running`), `live.py`
(`wnamed` write helper).

## The one hard rule

A clean-DTM-synced Dolphin test is **immutable** — never edit a locked test, its seq, expected
values, or golden to make it pass. A "wrong" sim result is almost always a **seed mismatch** (seed
with the anchor's exact logged mRate), not the test. See
[`../tests/dolphin/README.md`](../tests/dolphin/README.md#locked-tests-are-immutable-hard-rule).
