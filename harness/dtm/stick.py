"""Controller stick bytes as delivered by recorded DTMs."""


_DTM_CAL = {255: 254, 0: 1}


def dtm_stick(stick):
    """Apply the game's endpoint calibration to an authored main stick."""
    return (_DTM_CAL.get(stick[0], stick[0]), _DTM_CAL.get(stick[1], stick[1]))
