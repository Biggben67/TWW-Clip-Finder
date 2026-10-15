"""Offline guardrails that keep the tww_sim SOURCE tree on-structure — the code-side companion to
`test_kb_hygiene.py` (which guards the knowledge base). Deterministic, no Dolphin, no LLM; runs in
the normal pytest gate and as a tracked pre-commit check.

Catches the two code-drift modes a past audit found:
  * STALE PACKAGE REFERENCES — `superswim.<mod>` / `superswim_<mod>` / `superswim/<path>` left in
    comments/docstrings after the superswim->tww_sim rename (hard fail). The bare tech-name word
    ("superswimming", "straight superswims") is legitimate vocabulary and is NOT matched.
  * OVERSIZED MODULES — a `tww_sim/**.py` past the single-module size cap (hard fail), mirroring the
    KB page cap. Bloat buries logic; a new proc/mechanic gets a new file (see tww_sim/CLAUDE.md).

Plus SOFT warnings (never fail) when a module or KB truth page is approaching its cap — a nudge to
split before the hard gate trips.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "tww_sim"
KB = REPO / "knowledge"

# Skip regenerable / build artifacts; only hand-written source is guarded.
_EXCLUDE_PARTS = {"__pycache__", "_generated", "build", ".eggs"}

# A stale package/module ref = `superswim` + separator + an identifier char. This matches
# `superswim.anim` / `superswim_sim` / `superswim/sim.py` but NOT a sentence-ending "superswim.".
_STALE_REF = re.compile(r"superswim[._/][A-Za-z0-9_]")

# Single-module hard size cap (lines), mirroring the KB truth-page cap. Post-split every land file
# is well under; a new proc/mechanic gets a NEW file, not another method bolted onto a monolith.
MODULE_SIZE_CAP = 800

# Grandfathered oversized modules: PRE-EXISTING debt, not a license to grow. Each value is a hard
# CEILING (current size) so the file can only SHRINK; split it to remove the entry (empty is the goal).
MODULE_SIZE_ALLOWLIST = {}

# Soft-warn thresholds (advisory, never fail): approaching the module cap / the KB 250-line cap.
MODULE_SOFT = 650
KB_SOFT = 200
KB_TRUTH_DIRS = ("mechanics", "model", "strategy", "reference")


def _src_files(*exts) -> list[Path]:
    out = []
    for ext in exts:
        for p in PKG.rglob(f"*.{ext}"):
            if not (_EXCLUDE_PARTS & set(p.parts)):
                out.append(p)
    return sorted(out)


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _nlines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8").splitlines())


def test_no_stale_package_refs():
    """No stale superswim.* package/module references survive in tracked tww_sim source."""
    failures = []
    for p in _src_files("py", "pyx"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if _STALE_REF.search(line):
                failures.append(f"{_rel(p)}:{i}: {line.strip()}")
    assert not failures, (
        "Stale superswim.* refs (rename to tww_sim.*/tww_sim.core.*):\n  " + "\n  ".join(failures))


def test_no_oversized_modules():
    """No tww_sim/**.py exceeds the single-module size cap (allowlisted files may not grow past
    their frozen ceiling). Shrink don't grow: SPLIT, do not re-add here (needs --no-verify)."""
    failures = []
    for p in _src_files("py"):
        rel = _rel(p)
        cap = MODULE_SIZE_ALLOWLIST.get(rel, MODULE_SIZE_CAP)
        n = _nlines(p)
        if n > cap:
            how = "grew past its frozen ceiling" if rel in MODULE_SIZE_ALLOWLIST else "exceeds the cap"
            failures.append(f"{rel}: {n} lines {how} ({cap}) - split into single-topic modules")
    assert not failures, "Oversized modules:\n  " + "\n  ".join(failures)


def test_soft_size_warnings():
    """Advisory only (always passes): flag modules/KB truth pages approaching their cap so they get
    split BEFORE the hard gate trips."""
    for p in _src_files("py"):
        rel = _rel(p)
        if rel in MODULE_SIZE_ALLOWLIST:
            continue
        n = _nlines(p)
        if MODULE_SOFT <= n <= MODULE_SIZE_CAP:
            warnings.warn(f"{rel}: {n} lines - nearing the {MODULE_SIZE_CAP}-line module cap; consider splitting")
    for d in KB_TRUTH_DIRS:
        for p in (KB / d).rglob("*.md"):
            if "_eval" in p.parts:
                continue
            n = _nlines(p)
            if KB_SOFT <= n <= 250:
                warnings.warn(f"{_rel(p)}: {n} lines - nearing the 250-line KB page cap; consider splitting")
