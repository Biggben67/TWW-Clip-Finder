# `JMAEulerToQuat`'s half-angle is SIGNED - the negated-quaternion trap

**Answers:** Why must the euler-to-quat half-angle be sign-extended to s16 before halving? Why is a
"mathematically equivalent" negated quaternion NOT bit-equivalent? Where does this bite (late
`FRONT_ROLL` poses, an actor-push Co centre)? How was it found?
**Status:** validated 0-ULP against live console RAM (the `m_old_fdata` quat store, TWW JP). Gate:
[`tests/test_rollstab_rest.py`](../../tests/test_rollstab_rest.py)`::test_rest_roll_pose_bitexact`.
**Source:** [`tww_sim/core/anim/quat.py`](../../tww_sim/core/anim/quat.py) (`euler_to_quat`) and its
Cython mirror [`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) (`_half`); decomp
`JSystem/JMath/JMath.cpp:41` + `JMATrigonometric.h`.

---

## The rule

`JMAEulerToQuat(s16 x, s16 y, s16 z, ...)` takes **s16** parameters and halves them with C's `x / 2`,
which truncates toward zero **on the signed value**. An animated rotation that arrives as a raw u16
`>= 0x8000` is a NEGATIVE angle: halving it unsigned gives `+16580` where the game gets `-16188`.

Those two half-angles differ by exactly `0x8000` (180 deg), so `JMASCos`/`JMASSin`
(`jmaCosTable[u16(v) >> jmaSinShift]`, `jmaSinShift = 4`, 4096 entries) land **2048 entries apart** and
both `cos_0` and `sin_0` come back with the opposite sign. Every quaternion component then flips sign,
which is why the error hides: `q` and `-q` are the same rotation, and `mtx_quat` only ever uses
components in PAIRS (`2(yz - wx)` and friends), so a pure negation is bit-neutral through it.

**What is not neutral is the table.** `jmaSinTable[i] = (f32) sin(2*pi*i / size)`: each entry is rounded
independently, so `|jmaCosTable[i]|` and `|jmaCosTable[i + 2048]|` are NOT the same float. The two
representatives differ by tens of ULP on whichever components are cancellation-prone.

## Why it stayed invisible, and what it cost

The damage is invisible in the large matrix elements and concentrated in the small ones, which are
differences of near-equal products. Live example (`rollf`, joint 0, anim frame 11.0, rotation.x = u16
33160 = s16 -32376):

| | unsigned half (wrong) | signed half (console) |
|---|---|---|
| half-angle / table index | +16580 / 1036 | **-16188 / 3084** |
| `w` | -1.800199784e-02 | **+1.800208539e-02** (47 ULP apart in magnitude) |
| `m12 = 2(yz - wx)`, with `\|x\| ~ 1` | 0.035189457 | **0.035189632** |

That 1.7e-7 in `m12` moved the NECK joint's world z by 1 ULP, hence the root/neck midpoint
`daPy_lk_c::setCollision` uses as the push Co centre
([mechanics/link-co-centre.md](../mechanics/link-co-centre.md)), hence `cM3d_Cross_CylCyl`'s depth
([mechanics/actor-push.md](../mechanics/actor-push.md)). It also caused a late-`FRONT_ROLL` drawn-pose
drift that sat open for weeks: the roll is exactly where a joint rotation crosses into negative s16, and
the suspects chased in the meantime were the thigh lean and the foot lift.

## How it was found (the method, not the answer)

The same shape as any 0-ULP hunt here, and worth reusing: invert the f32 bin boundary at the first
diverging frame to BOUND the required change, eliminate every other term against live RAM, then solve
for the one input that reproduces the console's bits rather than guessing a shape. The final step was a
two-variable brute force over `cos_0`/`sin_0` in ULP space, which returned a UNIQUE solution (`c0` 47
ULP away, `s0` unchanged) - the fingerprint of a table-index error, not an arithmetic one.

Related: [fp-faithfulness](fp-faithfulness.md) (which ops fuse), [anim-engine](anim-engine.md) (where
the euler-to-quat step sits in the pose pipeline), [anim-frame-is-f32](anim-frame-is-f32.md) (the same
"two representatives of one value" shape at the frame ctrl). The same signed-s16 trap was hit once
before, on the `jointBeforeCB` body twist (`foot_fk._local_from_old`'s `_sx`); sign-extending inside
`euler_to_quat` now covers every caller.
