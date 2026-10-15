"""Seam geometry + clip acceptance for the kaze r11 roll-stab sandbox.

This is now a THIN, instance-backed shim over the general `seamgeo.SeamGeo` (the standard roll/wall
clip abstraction): it instantiates a SeamGeo from the kaze r11 geo fixture + the seam's frozen camera
yaw, and re-exports the module-level names (`F`, `TRIS`, `genuine_clip`, `pred_genuine`, ...) that the
solver/deliver/rest code imports as `G`. The roll facing `F` and the cut lunge are DERIVED, not pasted
(see `seamgeo` -- F from the interior bisector + csangle, the lunge from the CUT_F root translate at F).

  * genuine_clip(old, new)   -- the cut segment old->new crosses the seam: CrrPos NOT blocked,
                                old in front of both wall planes, new behind at least one.
  * seg_blocked(a, b)        -- a roll-approach segment fires the game's wall collision.
  * pred_genuine(old)        -- genuine_clip against the REAL cut endpoint at `old` (bit-identical
                                to the sim's cut `new`) -- the pure-geometry dust test used by
                                maps/rankers.

Anchor seeds live next to their savestates as tests/dolphin/anchors/<anchor>.seed.json.
"""
import os, json
# >>> repo bootstrap: locate tww_sim/ package root
_rb = os.path.dirname(os.path.abspath(__file__))
while _rb != os.path.dirname(_rb) and not os.path.exists(os.path.join(_rb, 'pyproject.toml')):
    _rb = os.path.dirname(_rb)
import sys
if _rb not in sys.path:
    sys.path.insert(0, _rb)

from harness.rollstab.seamgeo import SeamGeo, A_BTN, B_BTN, KROLL

ANCHOR_DIR = os.path.join(_rb, 'tests', 'dolphin', 'anchors')


def load_seed(anchor):
    """Load a named anchor, an explicit seed path, or an already-decoded seed dict."""
    if isinstance(anchor, dict):
        return anchor
    if os.path.isfile(anchor):
        with open(anchor) as f:
            return json.load(f)
    with open(os.path.join(ANCHOR_DIR, anchor + '.seed.json')) as f:
        return json.load(f)


# Back-compat single-seam shim. Both SeamGeo inputs come from STATE (what a live Dolphin feed supplies),
# not pasted literals: the geo fixture is built from live DZB RAM, csangle is read from the anchor.
GEO = json.load(open(os.path.join(_rb, 'fixtures', 'kaze_r11_geo.json')))
_CANON_ANCHOR = 'kaze_r11_rollstab_sheathed@twwgz'      # the shipped kaze roll seam anchor
CSANGLE = load_seed(_CANON_ANCHOR)['csangle'] & 0xFFFF  # from the anchor's RAM snapshot, not pasted

_SEAM = SeamGeo(GEO, CSANGLE)
SEAM = _SEAM     # public handle: the kaze r11 SeamGeo instance (the solver's default `seam`)

# --- module-level re-exports (backward-compatible with the pre-SeamGeo `G` surface) -----------
F = _SEAM.F
LUNGE = _SEAM.LUNGE
wA, wB = _SEAM.wA, _SEAM.wB
BARRIER = _SEAM.BARRIER
TRIS = _SEAM.TRIS
LINK_Y = _SEAM.LINK_Y
S = _SEAM.S
DIRX, DIRZ = _SEAM.DIRX, _SEAM.DIRZ
PX, PZ = _SEAM.PX, _SEAM.PZ

p32 = _SEAM.p32
in_front = _SEAM.in_front
seg_blocked = _SEAM.seg_blocked
genuine_clip = _SEAM.genuine_clip
pred_genuine = _SEAM.pred_genuine
perp = _SEAM.perp
along = _SEAM.along
