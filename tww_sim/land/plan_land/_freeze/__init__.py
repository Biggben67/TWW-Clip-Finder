"""plan_land/_freeze - the C-up-cancel FLOAT-PERFECT freeze reach variants.

`dispatch.reach_freeze` is the public entry; it branches to `roll` (fewest-frame analytic roll
approach), `min_frames` (fewest-frame start-crawl), or `robust` (always-succeeds 3-phase drill).
"""
