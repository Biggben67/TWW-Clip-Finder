#!/usr/bin/env python3
"""Select the doc-eval questions whose owning page changed — so the eval is CHANGE-SCOPED, never
a full audit.

Compares the KB against the last-eval marker (`knowledge/_eval/.last_eval_commit`) and prints only
the bank questions in `questions.md` whose `page:` is among the changed files. A `/kb-eval-changed`
run then fans out weak Haiku Tier-B agents over just those questions.

Usage:
  python knowledge/_eval/select_changed.py            # questions for pages changed since the marker
  python knowledge/_eval/select_changed.py --since HEAD~5
  python knowledge/_eval/select_changed.py --all      # every question (full audit; avoid routinely)
  python knowledge/_eval/select_changed.py --set-marker   # record current HEAD as "last eval"

No third-party deps (regex parse + `git`), so it runs anywhere the repo does.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUESTIONS = REPO / "knowledge" / "_eval" / "questions.md"
MARKER = REPO / "knowledge" / "_eval" / ".last_eval_commit"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def _set_marker() -> None:
    head = _git("rev-parse", "HEAD")
    MARKER.write_text(head + "\n", encoding="utf-8")
    print(f"marker set to {head}")


def _changed_paths(since: str | None) -> set[str]:
    base = since or (MARKER.read_text(encoding="utf-8").strip() if MARKER.exists() else "HEAD")
    tracked = _git("diff", "--name-only", base, "--", "knowledge", "tests/dolphin", "harness").splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard", "knowledge").splitlines()
    return {p.strip() for p in (*tracked, *untracked) if p.strip()}


def _parse_questions() -> list[dict]:
    """Extract entries from the multi-block YAML bank without a YAML dependency."""
    entries: list[dict] = []
    cur: dict | None = None
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*-\s+id:\s*(\S+)", line)
        if m:
            if cur:
                entries.append(cur)
            cur = {"id": m.group(1).strip().strip('"'), "hazard": False}
            continue
        if cur is None:
            continue
        for key in ("question", "page", "category"):
            km = re.match(rf"\s+{key}:\s*(.+)", line)
            if km:
                cur[key] = km.group(1).strip().strip('"')
        if re.match(r"\s+hazard:\s*true", line):
            cur["hazard"] = True
    if cur:
        entries.append(cur)
    return entries


def _page_to_repo_path(page: str) -> str:
    """`mechanics/x.md` -> `knowledge/mechanics/x.md`; `tests/..`/`harness/..` kept as-is;
    `../tools/..` -> `tools/..` (sibling repo — won't match this repo's diff, which is fine)."""
    page = page.strip()
    if page.startswith("../"):
        return page[3:]
    if page.startswith(("tests/", "harness/")):
        return page
    return f"knowledge/{page}"


def main() -> int:
    try:  # the bank uses unicode (α, ≈, →); force UTF-8 so a cp1252 console doesn't crash mid-print
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    if "--set-marker" in args:
        _set_marker()
        return 0
    show_all = "--all" in args
    since = None
    if "--since" in args:
        since = args[args.index("--since") + 1]

    entries = _parse_questions()
    if show_all:
        selected = entries
        note = f"ALL {len(entries)} questions (full audit)"
    else:
        changed = _changed_paths(since)
        selected = [e for e in entries if _page_to_repo_path(e.get("page", "")) in changed]
        base = since or (MARKER.read_text(encoding="utf-8").strip()[:12] if MARKER.exists() else "HEAD (uncommitted only; no marker yet)")
        note = f"{len(selected)} question(s) on {len({e.get('page') for e in selected})} changed page(s) since {base}"

    print(f"# change-scoped doc-eval selection: {note}\n")
    if not selected:
        print("(no changed pages map to bank questions — nothing to re-check)")
        return 0
    for e in selected:
        flag = " [HAZARD]" if e.get("hazard") else ""
        cat = f" ({e['category']})" if e.get("category") else ""
        print(f"- [{e['id']}]{flag}{cat}  page={e.get('page','?')}")
        print(f"    Q: {e.get('question','?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
