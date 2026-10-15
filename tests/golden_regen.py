"""Regenerate the offline golden traces from the CURRENT sim at HEAD.

This is the DELIBERATE, INTENTIONAL refresh mechanism for the characterization
goldens in tests/golden/. It is never run automatically on test failure -- a golden
test failure means the sim's behavior changed; you only regenerate after you have
confirmed (e.g. via the live Dolphin gate run_tests.py / validate_coldstart.py) that
the new behavior is the correct one.

Usage:
    python -m tests.golden_regen          # from the repo root
"""
from tests.golden_harness import regen_all

if __name__ == "__main__":
    regen_all()
