# The A-press is only a roll above a stick threshold

**Answers:** Why did my A-press not roll on console when the sim rolled? What deflection does a roll
need? What does the game do with an A-press that is too shallow? Which searches owe this gate?
**Status:** validated live, from both sides. One console delivery pressed A at stick magnitude 0.5705
and Link did not roll; another at 0.889 rolled. The value between them is the shipped HIO constant, not
a fit.
**Source:** `daPy_lk_c::setDoStatusBasic` (`d_a_player_main.cpp:2220` ATTACK, `:2218` PUT_AWAY),
`checkNextActionFromButton` (`:4318`, which reaches `procFrontRoll_init`), `daPy_HIO_basic_c0::m`
(`d_a_player_HIO_data.inc:4`, `field_0x1C`).
Code: [`tww_sim/land/hio.py`](../../tww_sim/land/hio.py) (`ATTACK_MSD_MIN`),
[`tww_sim/land/state.py`](../../tww_sim/land/state.py) (the dispatch + `attack_blocked`), and the
native twin [`_anmc.pyx`](../../tww_sim/core/anim/_anmc.pyx). Canonical value:
[reference/constants.md#land-movement](../reference/constants.md#land-movement).

---

## The gate

An A-press does not reach `procFrontRoll_init` directly. It reaches it only through a **do-status**,
and `setDoStatusBasic` decides that status from the stick:

    fVar1 = mBasic.field_0x1C                                  # 0.75; * mMove.field_0x80 (0.5) if heavy
    ...
    else if (mStickDistance > fVar1)   dComIfGp_setDoStatus(dActStts_ATTACK_e);      # :2220

and `checkNextActionFromButton` turns **only** `dActStts_ATTACK_e` into a roll (`:4318`). So the roll
needs three things, not two: a grounded locomoting proc (`MOVE`/`ATN_MOVE`), L off, **and
`mStickDistance > 0.75`**.

At or below 0.75 the same press takes the branch above it and becomes `dActStts_PUT_AWAY_e` (`:2218`)
- Link **sheathes the sword** and keeps walking. Nothing rolls, nothing is pushed.

| deflection | status | proc |
|-----------|--------|------|
| `msd > 0.75` | `dActStts_ATTACK_e` | `FRONT_ROLL` |
| `msd <= 0.75` | `dActStts_PUT_AWAY_e` | the walk continues, sword goes away |
| L held, stick off-forward | `dActStts_JUMP_e` | sidehop / backflip |

The threshold cuts **between two deliverable byte pairs** - `(181,157)` decodes to 0.749943 and
`(74,102)` to 0.750400 - so it is a real edge in the input alphabet. No byte pair decodes to exactly
0.75, so the strictness of `>` is taken from the decomp and cannot be settled by delivery.

## What the model does with a refused press

The sheathe is not modelled (it is a proc of its own). `LandState` latches **`attack_blocked`**
instead, the same way a wall-suppressed roll latches `sidle_blocked`: the roll does not fire, the flag
is sticky, and a planner rejects the input stream rather than believing a roll happened. Both dispatch
sites of the native `LandCore` carry the same gate - otherwise a search and its own reference disagree
about which candidates exist.

## Why a search owes it

The other stick floor in the land model is `msd > 0.05`, the **locomotion** test ("is the stick pushed
at all"), which appears all over `checkNextMode`. Using that one for the roll makes every aim look
rollable, and the mistake is durable because an aim's magnitude is otherwise irrelevant to a roll: the
roll's speed comes from the pre-roll `speedF`, and `_roll_init` snaps facing to the latched target
whatever the deflection. So the false claim ("magnitude does not matter to a roll") is true about the
roll and false about **getting** the roll.

The practical consequence for any input alphabet keyed on a decoded angle: an angle's cheapest
representative byte pair is typically a shallow interior one, so filtering to pairs that actually
dispatch changes which pair represents an angle - and can remove an angle entirely, when no pair
reaching it clears 0.75.

**Rule:** an input a search emits must be checked against the dispatch it assumes, not only against the
physics that follows it. A confirmation pass that "confirms with a real A-press" confirms nothing if the
engine it replays on shares the missing gate. The overturned "every aim in the window fires the
roll" is [history/aim-alphabet-whole-grid.md](../history/aim-alphabet-whole-grid.md); the prune a planner
owes at the dispatch frame is
[strategy/search-prune-the-dispatch.md](../strategy/search-prune-the-dispatch.md).

## See also

- [land-movement.md](land-movement.md) - the land index; the roll's own physics.
- [roll.md](roll.md) - what the roll does once it fires.
- [talk-eat.md](talk-eat.md) - the *other* thing that eats an A-press: a talkable NPC in range.
- [roll-cut-thrust-floor.md](roll-cut-thrust-floor.md) - the roll's own cut window, the gate on the B
  that follows.
