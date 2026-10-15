"""tww_sim.core.anim - the ported J3D under-body animation engine that drives land walk speedF.

Pure-offline, FMA-faithful port of Link's foot-chain animation pipeline (the subsystem that
posMoveFromFootPos reads to produce the walk/dash position speed `speedF`). No Dolphin dependency;
imports only tww_sim.core.fp / tww_sim.core.mathlib. It powers the bit-exact land-walk position in
tww_sim.land when the (copyrighted, gitignored) keyframe data is present under _generated/anim/.

Modules:
  j3d_eval  -- BCK keyframe eval (Hermite, s16/f32), calc_transform per joint/frame.
  quat      -- euler->quat, QuatLerp blend, PSMTXQuat (the foot-chain local-matrix path).
  fk        -- forward kinematics (PSMTXConcat/MultVec) -> model-local foot toe; data loader.
  anim_state-- setBlendMoveAnime/setMoveAnime/J3DFrameCtrl state machine (which anims, frames,
               ratio, m3598) driven by mNormalSpeed.
  foot_fk   -- stateful foot-FK driver with the oldframe-morf blend; toe+heel both feet.

Data (link_anim_walk_dash.json, link_skeleton.json) is generated from the game's own Link.arc/
LkAnm.arc by harness/anim/parse_bck.py + parse_bmd.py and lives in gitignored _generated/anim/ --
it is NOT shipped. When absent, tww_sim.land falls back to its calibrated speedF stand-in.
"""
