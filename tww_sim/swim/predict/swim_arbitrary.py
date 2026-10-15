"""swim_arbitrary.py - bit-exact v/anim/air for ARBITRARY main-stick directions.

GAP 2 fix. The base SwimState prices the per-frame speed gain through the discrete
'ess'/'neu'/'chg' action token (stick_to_action only recognizes sx==128). For random
main-stick directions (sx != 128) that token mis-classifies the frame and v diverges.

The TRUE per-frame gain is the SAME for every swim-input frame (setSpeedAndAngleSwim,
d_a_player_swim.inc ~27-41): there is NO chg/ess distinction in the game -- each frame
with stick deflection computes

    m34E8  = mMainStickAngle(sx,sy) + 0x8000 + camAngle           (s16)
    d_turn = snap to m34E8 if |m34E8 - facing| > 0x6000           (DIR_BACKWARD cone)
             else cLib gradual chase toward m34E8 (cap ARROW_TURN_RATE)
    gain   = mStickDistance * 3 * cM_scos(d_turn)                 (mStickDistance via /54 gate)

and applies it to potential_speed with a 1-frame lag (the gain computed on frame f lands
on frame f+1, replacing that frame's own gain). The facing snap/turn also lands next frame.

This subclass keeps EVERYTHING ELSE from SwimState (cold-start scramble via ColdStartSwimState,
anim advance, air, neutral physics, the state 54<->55 transition lag). It only replaces the
token-driven gain with the actual-stick gain, by driving the base machinery through a thin
shim: we pass the real (sx,sy) each frame and let _swim_facing / _chg_stick read it.

USAGE (drop-in for ColdStartSwimState in swim_predict_full):
    s = ArbitrarySwimState(v=v0, anim=anim0, air=air0, mrate=mrate0)
    s.state = st0; s._entry_tax = False; s.cam = cam0; s.facing = facing0
    for (sx, sy) in mainsticks:
        s.set_stick(sx, sy)
        d, tag = s.step(s.action_for(sx, sy))
"""
from __future__ import annotations
import math
from .. import sim as S
from ..coldstart import ColdStartSwimState
from . import stick_angle as SA


class ArbitrarySwimState(ColdStartSwimState):
    """SwimState that prices the speed gain from the ACTUAL per-frame main stick, not the
    discrete ess/neu/chg token. Inherits the logged-mRate cold start unchanged."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stick = (128, 128)        # the real main stick for the frame being stepped

    def set_stick(self, sx, sy):
        self._stick = (int(sx), int(sy))

    def action_for(self, sx, sy):
        """Token routing for the base step(). Per the decomp, EVERY deflected swim-input frame
        prices its speed gain the same way (gain = mStickDistance*3*cM_scos(d_turn), applied with
        a 1-frame lag) -- there is no chg/ess distinction in the game. So we route every deflected
        frame as 'chg' (the path that applies the gain with the correct 1-frame charge lag and
        does the cold-start entry scheduling) and let the overridden _swim_facing supply the exact
        per-frame gain. Neutral stick -> 'neu'.

        Verified bit-exact (v=0.0) on the charge build (cap_randcharge, gen_charge) AND the clean
        ESS cruise/steer captures (cap_full*): in cruise the per-frame gain is small and the
        1-frame lag washes out, so the uniform 'chg' routing matches the validated cruise path
        with no regression. (The old snap-cone chg/ess split mis-priced the snap<->non-snap
        boundary on mixed alternations -- e.g. gen_fullsx -- with a spurious post-burst transient.)"""
        return 'neu' if SA.angle_s16(sx, sy) is None else 'chg'

    # --- override the gain source: use the REAL stick + the EXACT (table) stick angle ---
    def _swim_facing(self, sx=None, sy=None):
        """Mirrors swim.sim.SwimState._swim_facing EXACTLY, except (a) it uses the real
        per-frame stick (self._stick, not the cardinal token the base would pass), and (b) it
        takes the stick angle from the live-exact table (SA.angle_s16) instead of the
        atan2+dead-zone closed form (only good to ~0.86deg). Schedules the facing snap/turn for
        next frame and returns gain = mStickDistance*3*cM_scos(d_turn)."""
        rsx, rsy = self._stick
        a = SA.angle_s16(rsx, rsy)
        if a is None:                                   # neutral stick: no swim input, no turn
            return 0.0
        m = (a + 0x8000 + self.cam) & 0xFFFF            # m34E8 (s16)
        d = S.s16_signed(m - self.facing)
        if abs(d) > 0x6000:                             # 135 deg backward cone -> instant snap
            d_turn = d
        else:                                           # aligned -> gradual chase
            cap = S.deg_to_s16(S.ARROW_TURN_RATE)
            d_turn = max(-cap, min(cap, d))
        self._pending_facing = (self.facing + d_turn) & 0xFFFF
        # gain magnitude = closed-form /54 (deadzone 15); LIVE bit-exact, == the table's
        # stick_dist/value column too. See tests/test_partial_magnitude.py.
        mag = math.hypot(S._deadzone(rsx), S._deadzone(rsy))   # /54 gate (== ess_decay norm)
        md = min(mag / 54.0, 1.0)
        return S.f32(md * 3.0 * S.cM_scos_s16(d_turn))
