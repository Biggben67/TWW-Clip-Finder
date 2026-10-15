# "The `body_chn` rotation contributes nothing to the Co centre"

> **status: historical** - this records a claim that was measured, written down, gated, and wrong,
> because the only capture available to test it could not see the term. Current truth is
> [mechanics/link-co-centre.md](../mechanics/link-co-centre.md). Kept for the lesson, which is about
> what a live gate proves when its fixture sits inside a quantization bucket.

## What was claimed

Porting `daPy_lk_c::setCollision`'s root/neck midpoint, the early roll frames read a residual against
the live `mCyl`. It was root-caused to the missing `setWorldMatrix` base z-tilt by `shape_angle.z` --
correctly -- and the fix was gated bit-exact against a purpose-made live capture
(`fixtures/hyrule_roll_lean.json`: Link rolling pinned at a wall, so only the pose and the lean move
the centre). The module then recorded the OTHER lean path as ruled out:

> the `jointBeforeCB` root tilt (`m34F2`/`m34F4`) is 0 outside damage/ice-slip, and its `body_chn`
> rotation (`-mBodyAngle.z`) contributes nothing to the centre (verified live: base-lean-only is 0 ULP
> on every settled roll frame; **adding the `body_chn` quat breaks it**).

Both halves of that parenthesis are true statements about that capture. Neither generalizes.

## What it actually is

The twist is real -- `foot_fk.FootFK.body_co_center` has applied it since the FK port, live-gated the
whole time -- and it takes the **POST-update** lean, one update ahead of the base tilt. Adding it with
the OLD lean does break the fit, which is exactly what the "breaks it" half had measured.

## Why the live gate could not see it

`euler_to_quat` halves the angle and reads `jmaSinTable[(u16)angle >> 4]`, so a small twist rounds to
the identity. Past the two exempt entry frames the lean capture never exceeds **28 BAM**, which is
inside that bucket: feeding the twist there is a bit-exact no-op, in both directions. The capture was
built to isolate the lean and it succeeded -- at a lean an order of magnitude below the one that
matters. A roll entered off a curving walk carries a `m351C >> 1` base lean of a few hundred BAM, and
there the term is worth **~0.35 u** of Co centre.

## What it cost

The twist was absent from `body_cyl.roll_co_chain_consts`, the baked per-frame chain the native
`ShoveCtx` sweeps (`harness/rollstab/fast_shove.py`) -- so a push-entry search scored every candidate
roll at a Co centre that was wrong for the first ~5 frames of the roll, by an amount that scales with
that candidate's own turn lean. A centre error does not stay put: the plow re-derives each contact
frame's overlap from the previous push, so a fraction of a unit at the centre leaves the pushed actor
a comparable distance off at the frame that decides the clip -- against a razor a single f32 ULP of
her position settles. A console delivery went out on a hit scored that way and did not clip; naming
the term and re-scoring invalidated most of that pass as false positives.

## The lessons

- **A live gate proves the model on the fixture's own regime, not past it.** Record the regime the
  capture covers next to the claim -- here, "max lean 28" was the whole caveat and it was not written
  down. `tests/test_body_cyl.py` now asserts the capture's own lean bound, so a future capture with a
  real lean makes the gate demand the term directly instead of quietly permitting it, and a companion
  case pins the term's SHAPE at a lean big enough to move the midpoint.
- **"Adding X breaks it" is a claim about X's inputs too.** The twist was tried and rejected with the
  wrong lean; the rejection got recorded as being about the twist.
- **Two engines that never meet will disagree.** The baked chain and the composite stepper were each
  checked against something, and nothing compared their per-frame output, so a term present in one and
  absent from the other stayed invisible for as long as both were only checked separately.
  `tests/test_shove_fast.py` now diffs the chain-consts decomposition against `roll_co_center` and the
  native engine against the Python coupled one, bit for bit.

## See also

- [co-centre-two-ports.md](co-centre-two-ports.md) - the next mistake on the same quantity: the two
  ports of the centre disagreeing by 1-2 ULP, and why neither was wrong.
