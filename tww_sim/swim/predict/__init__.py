"""Bit-exact position (world x/z) and camera-yaw predictors for superswimming.

These build on :mod:`tww_sim.swim.sim` to predict full trajectory + camera steering, not just
v/anim/air. The ``swim_predict*`` modules form an evolution chain
(``swim_predict_full`` → ``swim_predict_exact`` → ``swim_exact``; ``swim_predict_complicated``
is the variant exercised by ``tests/test_complicated.py``). They are kept as separate modules
pending a verified consolidation pass (see README follow-ups).
"""
