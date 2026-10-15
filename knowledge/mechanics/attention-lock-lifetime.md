# Attention lock-on lifetime (NONE / LOCK / RELEASE)

**Answers:** How long does a lock-on target keep driving the ATN_ACTOR procs after L is let go? Which
check ends the lock - the front-of-player cone, the target existing, or the reticle fade? Why does a
roll keep exiting into the untarget brakeslide even after the target has swung out of frame?
**Status:** validated live 0-ULP; the state machine is gated offline by
[`tests/test_atn_actor.py`](../../tests/test_atn_actor.py).
**Source:** decomp `d_attention.cpp` `judgementStatusHd` (804-844) / `judgementLostCheck` (751) /
`chaseAttention` (563) / `runDrawProc` (653); sim
[`tww_sim/land/attention.py`](../../tww_sim/land/attention.py) + its native twin
[`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx) (`_atn_update`).

---

`dAttention_c` holds three states - NONE, LOCK, RELEASE - and `LockonTruth()` is true in both LOCK
and RELEASE. That truth IS `mpAttnActorLockOn != NULL`, which is what `checkNextMode` reads to route
a roll exit into the ATN_ACTOR procs (9 moving / 8 stopped) instead of MOVE. So the RELEASE tail is
the whole reason [the untarget brakeslide](brakeslide-ebs.md) exists: L is already gone when it runs.

## Each state consults a DIFFERENT gate

This is the part that is easy to get wrong, because all three read like "is the target still there".

| State | What ends it | Decomp |
|-------|--------------|--------|
| NONE | nothing; the L rising edge ACQUIRES via `chaseAttention()` (cone + distance) | 810 |
| LOCK | `judgementLostCheck()` - `chaseAttention()` again, so leaving the front cone drops it THAT frame | 816 |
| RELEASE | `LockonTarget(0) == NULL \|\| !AttnFlag_40000000` - the frozen list entry, or the reticle fade completing | 837 |

RELEASE never calls `chaseAttention`. A target that swings out of the front cone mid-fade keeps the
lock until the fade runs out, and the list cannot change underneath it either: `stockAttention` only
runs in the NONE branch, so `LockonTarget(0)` stays whatever LOCK froze. For an actor that does not
despawn, RELEASE is therefore a pure countdown.

The fade length is the reticle `YJ_DELETE` anim, **end 10 / rate 1.0**, i.e. 10 frames - an
animation constant, not a tuned latency (`attention.DEFAULT_FADE_FRAMES`). `runDrawProc` clears
`AttnFlag_40000000` when it completes.

## Why the distinction is load-bearing

Gate RELEASE on the cone and a swinging target drops the lock several frames early, so a roll exits
into MOVE_TURN (24) where the game takes ATN_ACTOR_MOVE (9) - a different proc, a different speed
tail, a different facing. The console spends the full fade locked, takes its brakeslide frame, and
only then falls to MOVE. The symptom is a proc mismatch at a known frame, and the fix is one gate,
not a timing constant.

Purely additive to the land sim: with no locked target the machine can never leave NONE, so `locked`
is always False and every single-actor golden is byte-identical.

## See also

- [brakeslide-ebs.md](brakeslide-ebs.md) - the untarget brakeslide this tail dispatches.
- [tetra-follow.md](tetra-follow.md) - the acquisition side: `dist_table[0xAB]`'s distance/cone
  geometry, which is what `chaseAttention` tests.
- [talk-eat.md](talk-eat.md) - the same lists read for the A-button ACTION entry instead of a lock.
