"""Presence checks for the disc-extracted animation banks.

Link's and Tetra's animation keyframes are extracted from the game disc into the gitignored
`_generated/anim/` (see `harness/anim/parse_bck.py`), because they are game data and are not
distributable. A clean clone therefore has none of them, and anything that needs one must SKIP
rather than fail -- several modules load a bank at import time, so an unguarded one takes the whole
collection down with a FileNotFoundError instead of reporting a skip.

Call `require(...)` at module scope, above the library imports that would trigger the load.
"""
import os

import pytest

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_generated", "anim")


def _has(name):
    return os.path.exists(os.path.join(_DIR, name))


#: The CUT (sword thrust) keyframes -- the roll-stab lunge's root translate.
CUTS = _has("link_anim_cuts.json")
#: The walk/dash foot banks, including the sword-drawn WALKS/DASHS set.
WALK_DASH = _has("link_anim_walk_dash.json")
#: Tetra's (Zl1) banks, for the look-at head.
ZL1 = _has("zl1_anims.json")


def require(present, what):
    """Skip the whole module unless `present`. Safe to call before any library import."""
    if not present:
        pytest.skip("%s not present: extracted from the game disc into the gitignored"
                    " _generated/anim/ (regenerate with harness/anim/parse_bck.py)" % what,
                    allow_module_level=True)
