"""Collision dimensions and weights for supported droppable props."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropSpec:
    name: str
    label: str
    radius: float
    height: float
    weight: int
    shape: str
    source: str
    caveat: str = ""


# Tsubo type 0 is the small 30x60 pot; type 1 is the large 50x100 pot.
# Bombs use the radius-30 Co sphere from d_a_bomb3.inc.
PROP_SPECS = {
    "pot_small": PropSpec(
        "pot_small", "Tsubo small pot/skull", 30.0, 60.0, 0xC8, "cyl",
        "d_a_tsubo.cpp type0: m10=0xC8, mAcchCirRad=0x1E, m70=0x3C",
    ),
    "pot_large": PropSpec(
        "pot_large", "Tsubo large pot/barrel", 50.0, 100.0, 0xC8, "cyl",
        "d_a_tsubo.cpp type1: m10=0xC8, mAcchCirRad=0x32, m70=0x64",
    ),
    "bomb": PropSpec(
        "bomb", "Bomb", 30.0, 60.0, 0xC8, "sphere",
        "d_a_bomb3.inc l_sph_src radius=30, create_init mStts.Init(200,0xFF)",
    ),
}
