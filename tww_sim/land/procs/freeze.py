#!/usr/bin/env python3
"""_FreezeMixin: the SUBJECTIVITY (C-up-cancel) freeze API for the chained-freeze tech.

enter_freeze / hold_freeze / resume_walk drive the freeze programmatically (the planner searches on
it); the fully input-driven form lives in state.step. Native-aware: delegates to the fused LandCore
when present. procSubjectivity_init/procSubjectivity/procMove_init (d_a_player_main.cpp 5948/6210).
"""
from __future__ import annotations
from ..constants import SUBJECTIVITY, MOVE


class _FreezeMixin:
    # --- SUBJECTIVITY freeze (B-cancel chained-freeze): C-up -> WAITS/WALK blend -> B-cancel -> resume
    # with the anim phase carried. Live 0-ULP. Decomp/why: knowledge/mechanics/land-movement.md.
    def enter_freeze(self):
        """procSubjectivity_init (d_a_player_main.cpp:5948): mNormalSpeed=0 (freeze) + the WAITS/WALK
        idle blend with the walk phase preserved. Call AFTER the approach has decelerated Link to the
        freeze position (the reach_freeze cancel tail leaves it there). Position holds from here.
        Runs natively (fused LandCore) when present -- the chained-freeze planner searches at C speed."""
        if self._foot is None:
            raise RuntimeError("enter_freeze needs the anim foot engine")
        if self._core is not None:
            self._core.enter_freeze()
            self._sync_from_core()
            return
        self.nspeed = 0.0
        self.speedF = 0.0
        self.state = SUBJECTIVITY
        self._foot.enter_subjectivity(self.msd, low_life=self._check_rest_hp_anime())
        self.visited.add(self.state)

    def hold_freeze(self):
        """One SUBJECTIVITY (or post-B WAIT) hold frame: position frozen, the WAITS anim advances at
        1.1/frame (procSubjectivity only setBodyAngleToCamera). Each hold frame shifts the carried
        resume phase -- the chained planner's lever for tuning the re-walk-from-rest trajectory."""
        if self._core is not None:
            self._core.hold_freeze()
            self._sync_from_core()
            return
        self.speedF = 0.0
        self._foot.step_subjectivity(self.msd)

    def resume_walk(self):
        """Exit the freeze into MOVE (procMove_init, 6210): setBlendMoveAnime re-triggers the
        oldframe-morf and, because m34C3=2, PRESERVES the carried WAITS phase. After this, step() with
        a forward stick walks from rest bit-exactly (the 2-frame input latency still applies)."""
        if self._core is not None:
            self._core.resume_walk()
            self._sync_from_core()
            return
        self.state = MOVE
        self.nspeed = 0.0
        self._foot._pending_morf = self.MOVE_REENTRY_MORF
