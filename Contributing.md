# Contributing to tww_sim

Short, repo-specific conventions. The source of truth for mechanics/strategy/model is the knowledge
base under [`knowledge/`](knowledge/) — start at [`knowledge/README.md`](knowledge/README.md).
(Session handoffs are local working notes under `_notes/`, not tracked in the repo.)

## Keep the knowledge base current

Treat docs like code. **A behavior change isn't done until the owning `knowledge/` page is updated**
(and its `Status:`/`Source:` header). When a finding is overturned, MOVE the old claim into
`knowledge/history/` (tag `status: historical`) rather than leaving it on a truth page. Keep one
canonical value per constant in `knowledge/reference/constants.md` and link to it. New pages follow
the template in `knowledge/README.md`. The offline `pytest` gate includes `tests/test_kb_links.py`
(every relative link + `#anchor` must resolve); the deeper weak-agent doc-eval lives under
`knowledge/_eval/` — re-run it when a topic's pages change substantially.

## Setup

```bash
pip install -e ".[test]"                                 # editable install + pytest
git config blame.ignoreRevsFile .git-blame-ignore-revs   # skip bulk-move commits in blame
git config core.hooksPath .githooks                      # enable the tracked pre-commit hook
```

The pre-commit hook (`.githooks/`) is tracked, so `core.hooksPath` wires it for every clone — no
per-file copy needed.

## Tests — run both before and after any `tww_sim/swim/sim.py` or `tww_sim/land/land.py` change

```bash
pytest                              # offline unit + golden suite (no Dolphin), runs anywhere/CI
python tests/dolphin/run_tests.py   # live sim-vs-Dolphin accuracy (needs Dolphin + booted ISO)
```

After a *deliberate, live-verified* behavior change, refresh the goldens with
`python -m tests.golden_regen`, then re-run the Dolphin gate. A golden diff with no intended change
is a regression — investigate, don't regenerate. See `tests/dolphin/` for the live harness.

## Style

- **Code:** match the surrounding style; 4-space indent, ~100-char lines (`.editorconfig`). No
  autoformatter — the dense, hand-aligned physics code is intentional.
- **Comments:** follow [`STYLE.md`](STYLE.md) — `#`-only and terse for inline rationale, docstrings
  for longer prose, explain *why* not *what*, `TODO/FIXME/HACK/NOTE/WARNING` tags verbatim, no
  change-log narration or restate-the-code filler. When a comment grows past ~2 lines, promote the
  explanation to the knowledge base with a one-line pointer (STYLE.md §2). The pre-commit hook flags
  added `#` blocks over two lines; bypass a genuine exception with `git commit --no-verify`.

## Commits, branches, PRs

See [`STYLE.md`](STYLE.md) §6. In short:

- **Subject:** `Component: Imperative, sentence-case summary` (e.g. `Sim: Fix warm-pump f32 order`).
  No `feat:`/`fix:` prefixes, no trailing period, no co-author trailers. Bodies optional — only when
  the *why* is non-obvious; never restate the diff.
- **Branches:** `author/topic-in-kebab-case` (e.g. `dmiller/repo-reorg`). No ticket numbers.
- **PR title:** same `Component: Summary` form; body = what changed and why, no padding.
