"""swim_coldstart.py - bit-exact COLD-START scramble for the superswim sim.

Imports swim.sim READ-ONLY (does NOT modify it). A SwimState subclass that fixes the
ONE cold-start inaccuracy: the base sim assumes the swim-initiation scramble oldframe is
`f32(self.anim + 1.0)`, which is slate-phase-dependent and WRONG at the current slate.

THE VALIDATED RULE (live-pinned on slot 10, 3 cold-starts, err +0.00000 each):
  The cold start has exactly ONE state-54 entry-tax frame on the charge input, then the
  state 54->55 scramble frame. The scramble oldframe is:

      oldframe = f32( f32(anim_seed + mRate_seed) + neutral_anim_rate(air_seed - 1) )
      scramble_anim = f32( f32(oldframe * 26.0) * 23.0 )

  - advance1 (entry-tax frame): display advances by the LOGGED controller rate `mRate`
    (read live @ move0_mrate = anim-chain base 0x803AD860 +0x2F60). This rate carries
    pre-seed AIR HISTORY (e.g. mRate 0.547222 at air-written 900 reflects air~882) and
    CANNOT be recomputed from air -> it must be LOGGED at the seed.
  - advance2 (scramble frame): neutral_anim_rate(air_seed - 1). This IS computable (the air
    decremented by the entry-tax frame) -> no logging needed.

  The base sim's f32(anim_seed + 1.0) gives oldframe 9.9417 vs the true 9.98892 ->
  scramble 5945.14 vs live 5973.37 (err -28), x598-amplified into the run_tests anim fails.

USAGE:
    from swim_coldstart import ColdStartSwimState
    s = ColdStartSwimState(v=v0, anim=anim0, air=air0, mrate=mrate0)  # mrate0 read LIVE
    s.state = st0; s._entry_tax = False
    for a in actions: s.step(a)
"""
from __future__ import annotations
from . import sim as S


class ColdStartSwimState(S.SwimState):
    """SwimState whose cold-start scramble uses the LOGGED seed mRate instead of +1.0.

    Pass the live-logged controller rate as `mrate` (== move0_mrate at the seed frame, the
    same instant air/speed are written in the run_tests-style seeding). All other behaviour
    is inherited verbatim from swim.sim.SwimState -- only the cold-start scramble
    oldframe is corrected. Warm pumps are untouched (they already log nothing / recompute).
    """

    def __init__(self, *args, mrate=None, **kwargs):
        super().__init__(*args, **kwargs)
        # The logged MOVE0 controller rate at the seed (history-dependent; must be measured
        # live, not recomputed from air). None -> fall back to the base +1.0 behaviour.
        self._mrate_seed = None if mrate is None else S.f32(mrate)

    def step(self, action):
        # Snapshot the pre-step display anim and air so we can recompute the cold-start
        # oldframe exactly as the base sim stashes it (state 54, desired 55, not warm).
        anim_pre = self.anim
        air_pre = self.air
        scramble_was_none = (self._scramble_oldframe is None)
        warm_pre = self._warm

        ret = super().step(action)

        # If THIS frame just stashed a cold-start oldframe (None -> set, and it was the
        # cold-start branch, i.e. not warm at frame start), overwrite it with the logged-mRate
        # value. The base set it to f32(anim_pre + 1.0); the live-exact rule is
        # f32(f32(anim_pre + mRate_seed) + neutral_anim_rate(air_pre - 1)).
        if (self._mrate_seed is not None and scramble_was_none
                and self._scramble_oldframe is not None and not warm_pre):
            disp_after_tax = S.f32(anim_pre + self._mrate_seed)
            self._scramble_oldframe = S.f32(disp_after_tax
                                            + S.neutral_anim_rate(air_pre - 1))
            # Also fix the entry-tax frame's DISPLAYED anim: the base sim advanced it by
            # neutral_anim_rate(air) (the SWIMWAIT neutral rate), but the live MOVE0 controller
            # advances by the LOGGED mRate on this frame (display 8.94170 -> 9.48892, not 9.43892).
            # Display-only (the scramble below uses _scramble_oldframe, not self.anim), but keeps
            # the per-frame anim bit-exact on the entry-tax frame too.
            self.anim = disp_after_tax
        return ret
