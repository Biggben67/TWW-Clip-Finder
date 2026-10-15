"""Roll-stab seam-clip solver harness (kaze r11 sandbox; see README.md in this package).

Pure-sim, bit-exact-vs-live planning of the roll-stab (FRONT_ROLL -> B-edge CUT_F) seam clip:
`rest` builds the from-rest bit-exact sim (input = the anchor seed json alone, no calibration)
plus the one-off live verification gate, `mint` makes anchors + captures their rest seed fields,
`solver` searches the input knobs against the f32 "dust" acceptance (exact per-candidate
geometry), `deliver` ships the plan as a clean DTM and confirms per-frame live.
"""
