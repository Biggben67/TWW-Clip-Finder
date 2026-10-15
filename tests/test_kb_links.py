"""Offline guard: every in-repo relative link + anchor in the knowledge base resolves.

Catches the most common documentation rot (moved/renamed pages, stale #anchors) mechanically —
no Dolphin, no LLM — as part of the offline pytest gate. Links that leave the repo (e.g.
../tools/...) and external URLs are skipped, since their target isn't guaranteed in every clone.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN = sorted((REPO / "knowledge").rglob("*.md")) + [
    REPO / "KNOWLEDGE.md",
    REPO / "README.md",
]

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")          # [text](target)
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
_EXPLICIT_ANCHOR = re.compile(r'<a\s+id="([^"]+)"')


def _slug(heading: str) -> str:
    """GitHub-flavored-markdown heading -> anchor: lowercase, drop punctuation
    (keep word chars / spaces / hyphens), spaces -> hyphens. Consecutive hyphens are NOT
    collapsed (matches GitHub), so ' — ' -> '--'."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def _anchors(text: str) -> set[str]:
    return {_slug(h) for h in _HEADING.findall(text)} | set(_EXPLICIT_ANCHOR.findall(text))


def test_kb_links_resolve():
    failures: list[str] = []
    for md in SCAN:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")
        for raw in _LINK.findall(text):
            target = raw.strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")
            # Same-file anchor.
            if not path_part:
                if anchor and anchor not in _anchors(text):
                    failures.append(f"{md.relative_to(REPO)} -> #{anchor} (no such anchor in self)")
                continue
            resolved = (md.parent / path_part).resolve()
            # Skip links that escape the repo (their target isn't guaranteed in every clone).
            if REPO not in resolved.parents and resolved != REPO:
                continue
            if not resolved.exists():
                failures.append(f"{md.relative_to(REPO)} -> {path_part} (missing)")
                continue
            if anchor and resolved.is_file() and resolved.suffix == ".md":
                if anchor not in _anchors(resolved.read_text(encoding="utf-8")):
                    failures.append(f"{md.relative_to(REPO)} -> {path_part}#{anchor} (no such anchor)")
    assert not failures, "Broken knowledge-base links/anchors:\n  " + "\n  ".join(failures)
