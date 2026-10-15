# Seam-clip handoff template (copy to a dated file each session end)

> Save the FILLED copy as
> `_notes/seam-clip-live-validation-handoff-<YYYY-MM-DD>-session<N>.md` (handoffs are
> gitignored, local session state). Keep it a DELTA over the README + the previous
> handoff, not a re-explanation.

---

# Handoff: <topic>, SESSION <N> (<absolute date>)

One line: what changed this session / where it leaves things.

## Current state (the truth right now)
Pipeline status; what's bit-exact; what's shipped (cite commits); what's blocked; and
whether the pure-sim / no-calibration objective is any closer (does a live-calibration
workaround still exist?). If seam-clip behavior changed, the README ## Status section
must already reflect this (the pre-commit gate enforces it).

## Done & proven this session
- <change> (commit <hash>): what + HOW verified. 0-ULP? which gate/test?

## Tried and RULED OUT, do not repeat without new evidence
- <approach>: failed because <root cause>. Retry only if <condition changes>.
(Also APPEND each of these to knowledge/history/seam-clip-dead-ends.md, the persistent
ledger; this handoff section is just this session's delta.)

## Next step (the single most promising thing)
Exact commands / files to run. What "done" looks like for it.

## Artifacts / anchors touched
Files, anchors (kept vs deleted + why), _generated data, scratchpad location.
