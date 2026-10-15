# What a corner clip costs, stated as contact instead of depth

**Answers:** How much overlap does my cut frame need, and where exactly must the pushed actor be
standing? Why is a small aligned push worth more than a large crooked one? How do I rank a raw sweep row
before the geometry has been solved? Which aim is cheapest to clip on?
**Status:** derived on a flooded-Hyrule Tetra corner and checked against the one clip that corner is
known to give - the requirement predicts its contact to 1.2 u and 0.8 deg.
**Source:** the clip geometry ([../mechanics/seam-clip.md](../mechanics/seam-clip.md)) plus the push
model [`tww_sim/core/cc_push.py`](../../tww_sim/core/cc_push.py) and the animated centre
[`tww_sim/core/anim/body_cyl.py`](../../tww_sim/core/anim/body_cyl.py).

---

## The inversion

A depth law reads a configuration and reports what it is worth. A search needs the other direction: what
would be **enough**. At a zero-residual solution every term is pinned by the aim and the brace, so the
answer is analytic.

`resid = 0` says the cut segment `base_vec + push` is parallel to `old -> S` (the vertex ray). That
single constraint does all the work:

1. **The perpendicular push is not free and not a cost.** It must exactly cancel `base`'s own
   perpendicular component, `g = -|base| sin(delta)`, where `delta` is the facing's angle off the ray.
   In exchange it **rotates the ray**, which lets `old` sit nearer the vertex - which is how a clip can
   cut from 49.3812 u where its no-push razor is stuck at 49.6161.
2. **The parallel push must reach the floor**: `f = |S - old| + depth/kappa - |base| cos(delta)`.
3. **The push direction says where she stands.** `|push| = share * cross_len`, and the pusher is shoved
   directly away from her, so `t = c - (R_sum - cross_len) * push_hat` about the animation-posed Co
   centre `c` ([../mechanics/link-co-centre.md](../mechanics/link-co-centre.md)).
   [Whether that spot exists](placement-standability.md) is a hard constraint, so the useful push has a
   floor from the GEOMETRY as well as from the depth: aim the push too far off the ray and the only place
   she could be standing is inside a wall.

Walk `old` along the brace locus, walk the push up from `f`, take the first placeable spot, and the
minimum over the locus is that aim's requirement.

## What it says on a real corner

The corner-most brace `CrrPos` can park Link on is **49.2546** u from the vertex and the lunge `|base|`
is **49.2202**, so **the cut is 0.0345 u short before the depth floor is even considered**. Every clip
there is bought with contact; no aiming trick pays for it alone.

Per aim (each an s16 facing, one sine-table cell apart), the required overlap:

| facing | required `cross_len` | aim off the ray | its brace |
|---|---|---|---|
| 40914 | **0.3939** | 4.9 deg | 49.2546 (corner-most) |
| 40901 | 0.4097 | 16.7 deg | 49.2546 |
| 40939 | 0.4338 | 25.2 deg | 49.2546 |
| 40841 (the delivered one) | **0.8037** | 34.2 deg | 49.3885 |
| 40795 | 1.1268 | 34.5 deg | 49.5227 |

Two things fall out. The requirement is **monotone in the brace**, which is mechanism rather than
coincidence: a facing that points at the corner braces corner-most and needs the push only for the
0.0345 u the lunge is short, while one pointing a fraction of a degree off must also spend perpendicular
push steering the ray back onto the vertex. And the clip that was actually delivered sits on an
**expensive** aim - the cheapest asks less than half of what it does.

**The requirement is thrust-independent**: across the dispatchable steps it agrees to under 1%. So an
earlier step is not refused because it needs more; it is refused because the animation-posed Co centre is
not touching her on its cut frame ([../mechanics/cut-frame-co-swing.md](../mechanics/cut-frame-co-swing.md)).

## Ranking a raw row

The scalar a sweep can rank before any Newton depends on the **push vector alone**:

    ray   = |base| * m_hat + push
    depth = kappa(ray) * (|ray| - |S - old(ray)|)

because `resid = 0` fixes the brace from the ray direction. A large misaligned push pays twice - it
rotates the ray *and* slides `old` down the wall - so **a small aligned push outranks a big crooked
one**. On the delivered clip it returns +0.3195 against a measured +0.2533: an **upper bound**, since it
grants the ideal brace for that ray. A negative is therefore a proof and a positive is only a lead.

Two cheaper-looking scalars are wrong, and both get tried first:

- **the raw row's own depth** ignores the other genuineness clauses. It happily returns +13.6 for a row
  with Link 86 u out and the endpoint behind some far wall.
- **comparing push MAGNITUDES against the requirement** ignores direction. It scores a 7.4 u overlap
  pointing anywhere at +6.5.

And the bound itself owes one clause it cannot check: it is a function of the PUSH, so the brace it
reports is the one the solution WOULD use, not the one the row is at. A row whose own Link is 107 u out
still scores its push (+0.0955), and solving it leaves him 107 u out (-41). **Screen rows on their own
`|S - old|` first.**

## The conjunction, which is where the refusal lives

Neither half is the constraint; the pair is. Banding a swept space (placement x entry x seed motion) by
`|resid|` and taking the best achievable depth in each band, the trade is **monotone in the distance to
the solution** - every unit of residual left un-zeroed buys depth:

| `\|resid\|` band | cheap aim (needs 0.394) | delivered aim (needs 0.804) |
|---|---|---|
| <= 0.05 | **-0.0363**, no contact at all | **+0.0399**, 0.65 u of contact |
| <= 0.5 | -0.0020 | +0.1564 |
| <= 2 | +0.0841 | +0.3910 |
| <= 10 | +0.2205 | +0.5121 |

The acceptance band for a real clip is ~1e-4, 500x tighter than the tightest column here. So the push
that would pay is real and it is *near* the curve, not on it: at the cheap aim the near-solution rows
have **no contact**, and the best achievable depth there is exactly the no-push value, the 0.0345 u the
lunge is short.

Note which aim wins the conjunction: **not the cheap one**. The cheap aim asks for less than half the
overlap, but the spot it asks for is 4.9 deg off the ray, which puts her essentially ON Link's roll line,
where [the plow ejects her hardest](../mechanics/plow-ejection-equilibrium.md). The delivered aim's 34 deg
costs more overlap and lets her stand off the line. **The optimum over an aim window is therefore
interior**, and the two aims above are its ends.

## See also

- [../mechanics/seam-clip.md](../mechanics/seam-clip.md) - the corner clip this prices.
- [../mechanics/actor-push.md](../mechanics/actor-push.md) ·
  [../mechanics/push-magnitude.md](../mechanics/push-magnitude.md) - where a push comes from and how big
  one frame of it can be.
- [placement-standability.md](placement-standability.md) - the clause that makes a required placement
  deliverable rather than merely evaluable.
- [../mechanics/plow-ejection-equilibrium.md](../mechanics/plow-ejection-equilibrium.md) - why the
  cheapest-looking aim is the hardest to stand for.
