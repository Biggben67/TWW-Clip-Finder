"""Offline guardrails that keep the knowledge base compliant with its own reorg guidelines —
so documentation stays fresh and on-structure WITHOUT a periodic human audit.

Deterministic, no Dolphin, no LLM. Runs in the normal pytest gate. Companion to
`test_kb_links.py` (link/anchor integrity). Between them they mechanically catch the drift a
full KB audit used to find:

  * truth pages missing the `Answers:/Status:/Source:` triage header
  * `history/` pages not flagged `status: historical`
  * ORPHAN pages — a page that exists but is unreachable from the hub (the discoverability bug
    the weak-agent doc-eval kept surfacing)
  * truth pages growing past the single-topic size cap (bloat → bury facts)
  * a `Source:` code reference whose file no longer exists (rename/delete = stale doc)
  * DEPRECATED-IN-PLACE claims on truth pages (strikethrough, "obsolete/deprecated/superseded"
    headings, or a `status: historical` line) — those must be MIGRATED to `knowledge/history/`,
    not annotated in place.

What this CANNOT check (content is actually correct/current) is the job of the change-scoped
doc-eval (`knowledge/_eval/`), which runs only over pages that changed.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KB = REPO / "knowledge"
HUB = KB / "README.md"

# Truth layers carry the `Answers:/Status:/Source:` template; history/ uses a `status: historical`
# banner instead; reference/ is lookup but still templated.
TRUTH_DIRS = {"mechanics", "model", "strategy", "reference"}

# Single-topic size cap for truth pages (history/ is frozen narrative → exempt).
# EMPTY BY DESIGN: a new oversized truth page means SPLIT it, do NOT re-add here (needs --no-verify).
SIZE_CAP = 250
SIZE_ALLOWLIST = set()  # was {land-movement.md}; split into 7 single-topic pages 2026-07-07

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
_STRIKE = re.compile(r"~~[^~]+~~")
_OBSOLETE_HEADING = re.compile(r"^#{1,6}\s+.*\b(obsolete|deprecated|superseded)\b", re.IGNORECASE | re.MULTILINE)
_STATUS_HISTORICAL = re.compile(r"status:\s*historical", re.IGNORECASE)
# repo-relative code path (optionally with a single {a,b,c} brace group), e.g.
# tww_sim/land/plan_land.py, tww_sim/core/anim/{fk,quat}.py, tww_sim/core/anim/_anmc.pyx
_CODEPATH = re.compile(
    r"\b((?:tww_sim|tests|harness|viz|fixtures)/[\w./-]*(?:\{[\w,]+\})?[\w./-]*\.(?:pyx|pxi|py))")


def _kb_pages() -> list[Path]:
    return [p for p in sorted(KB.rglob("*.md")) if "_eval" not in p.parts]


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _category(p: Path) -> str:
    parts = p.relative_to(KB).parts
    return parts[0] if len(parts) > 1 else ""


def _preamble(text: str) -> str:
    """Header region: everything before the first `## ` section heading or `---` separator."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("## ") or ln.strip() == "---":
            return "\n".join(lines[:i])
    return text


def _expand_braces(token: str) -> list[str]:
    m = re.search(r"\{([\w,]+)\}", token)
    if not m:
        return [token]
    return [token[: m.start()] + opt + token[m.end():] for opt in m.group(1).split(",")]


def test_truth_pages_have_triage_header():
    """Every mechanics/model/strategy/reference page opens with Answers:/Status:/Source:."""
    failures = []
    for p in _kb_pages():
        if _category(p) not in TRUTH_DIRS:
            continue
        head = _preamble(p.read_text(encoding="utf-8"))
        for field in ("**Answers:**", "**Status:**", "**Source:**"):
            if field not in head:
                failures.append(f"{_rel(p)} missing {field} in its header")
    assert not failures, "Truth pages missing triage header:\n  " + "\n  ".join(failures)


def test_history_pages_marked_historical():
    """history/ pages must carry a `status: historical` banner (not current truth)."""
    failures = [
        _rel(p) for p in _kb_pages()
        if _category(p) == "history" and not _STATUS_HISTORICAL.search(p.read_text(encoding="utf-8"))
    ]
    assert not failures, "history/ pages missing `status: historical`:\n  " + "\n  ".join(failures)


def test_no_orphan_pages():
    """Every KB page must be reachable from the hub (README) via intra-KB links.

    An orphan page exists but the index never points at it — exactly the discoverability failure
    the doc-eval keeps catching. Add a hub/question-index entry (or a cross-link) to fix.
    """
    pages = {p.resolve() for p in _kb_pages()}
    seen: set[Path] = set()
    stack = [HUB.resolve()]
    while stack:
        cur = stack.pop()
        if cur in seen or not cur.exists():
            continue
        seen.add(cur)
        for raw in _LINK.findall(cur.read_text(encoding="utf-8")):
            path_part = raw.strip().split("#", 1)[0]
            if not path_part or path_part.startswith(("http://", "https://", "mailto:")):
                continue
            tgt = (cur.parent / path_part).resolve()
            if tgt.suffix == ".md" and KB.resolve() in tgt.parents:
                stack.append(tgt)
    orphans = sorted(_rel(p) for p in pages - seen)
    assert not orphans, (
        "Orphan KB pages (exist but unreachable from README hub — add a question-index entry):\n  "
        + "\n  ".join(orphans)
    )


def test_truth_pages_under_size_cap():
    """Truth pages stay single-topic (<= SIZE_CAP lines) unless explicitly grandfathered."""
    failures = []
    for p in _kb_pages():
        if _category(p) not in TRUTH_DIRS or _rel(p) in SIZE_ALLOWLIST:
            continue
        n = len(p.read_text(encoding="utf-8").splitlines())
        if n > SIZE_CAP:
            failures.append(f"{_rel(p)} is {n} lines (> {SIZE_CAP}); split it or add to SIZE_ALLOWLIST")
    assert not failures, "Oversized truth pages (bloat buries facts):\n  " + "\n  ".join(failures)


def test_source_code_references_exist():
    """Every repo-relative code path named in a page must still exist (rename/delete = stale doc)."""
    failures = []
    for p in _kb_pages():
        text = p.read_text(encoding="utf-8")
        for token in _CODEPATH.findall(text):
            for cand in _expand_braces(token):
                if not (REPO / cand).exists():
                    failures.append(f"{_rel(p)} references missing code path: {cand}")
    assert not failures, "Stale code references in KB (fix the path or the doc):\n  " + "\n  ".join(failures)


def test_no_deprecated_in_place_on_truth_pages():
    """Overturned claims must be MIGRATED to knowledge/history/, not deprecated in place.

    Flags strikethrough, obsolete/deprecated/superseded headings, or a `status: historical` line
    on a truth page. Move the claim to history/ (tag `status: historical`) and leave the truth page
    with only the current answer.
    """
    failures = []
    for p in _kb_pages():
        if _category(p) not in TRUTH_DIRS:
            continue
        text = p.read_text(encoding="utf-8")
        if _STRIKE.search(text):
            failures.append(f"{_rel(p)} has strikethrough — migrate the struck claim to history/")
        if _OBSOLETE_HEADING.search(text):
            failures.append(f"{_rel(p)} has an obsolete/deprecated/superseded heading — migrate to history/")
        if _STATUS_HISTORICAL.search(text):
            failures.append(f"{_rel(p)} has a `status: historical` line — that content belongs in history/")
    assert not failures, "Deprecated-in-place content on truth pages:\n  " + "\n  ".join(failures)
