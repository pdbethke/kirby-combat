# RAW alignment — the book's own examples, executed

The HERO System rulebooks work through named examples: Andarra recovering from
being Stunned, Starburst flying past Ogre, Lazer aborting to Dodge. Those
examples state exact numbers, which makes them the sharpest available test of
whether an engine implements the rules or merely resembles them.

Every example here is backed by a script in `examples/`. The scripts **assert**
the book's numbers rather than printing them, and `tests/test_examples.py`
requires each to exit 0 with empty stderr. So this page cannot drift from the
engine: if the engine stops agreeing with a book example, the suite goes red.

Two things this page deliberately does not do.

It does not claim the engine reproduces every example in the books. It
reproduces the ones listed here, and says where it is approximate.

And it does not treat a worked example as automatically authoritative over the
rule it illustrates. **They sometimes disagree** — see Starburst. Where they
do, the engine follows the rule and this page documents the divergence, because
silently matching a self-contradictory example would mean encoding a mistake
and calling it fidelity.

---

## Andarra recovers from being Stunned — 6E2 p.107

**Script:** `examples/raw_andarra.py` · **Verdict:** rule and example agree; conformance asserted

> "In the character's next full Phase after becoming Stunned, he recovers from
> being Stunned when his DEX occurs in the Segment. He regains his full DCV
> (and Placed Shot modifiers return to normal), but he still cannot act until
> his next Phase — recovering from being Stunned is all he can do that Phase.
> However, after recovering from being Stunned, a character may, if he wishes,
> Abort to a defensive Action (even in the same Segment in which he recovers
> from being Stunned).
>
> **Example:** Andarra (DEX 20, SPD 3) is Stunned by an attack on Segment 6.
> She must use her Phase on Segment 8 to recover; she recovers on DEX 20 (so an
> enemy attacking her in Segment 8 with, say, DEX 15 would have to hit her at
> her full DCV). Andarra cannot take any other Action until her next Phase on
> Segment 12, but may Abort her Phase in Segment 12 in Segments 8 (after her
> DEX occurs), 9, 10, or 11 if she so desires."

Running `python examples/raw_andarra.py`:

```
Segment 6 — Andarra is Stunned by an attack

Segment 7    {stunned}                  DCV 5 (base 9)   Abort allowed: False
Segment 8    {recoveringFromStunned}    DCV 5 (base 9)   Abort allowed: False
             (book restores full DCV partway through this Segment, at her DEX
              — reported, not asserted; see the approximation note below)
Segment 9    {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 10   {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 11   {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 12   {— none —}                 DCV 9 (base 9)   Abort allowed: True
```

Segments 9, 10 and 11 — the ones the book names explicitly — are asserted.

**Where this is approximate, stated plainly.** The book restores Andarra's DCV
*partway through* Segment 8, at her DEX. Kirby derives conditions by folding an
event log, which carries no intra-Segment DEX position, so its edge is the end
of Segment 8 rather than DEX 20 within it. The engine therefore over-penalises
her for the post-DEX remainder of one Segment. That case is printed and
labelled, never asserted, because asserting it would claim a fidelity the
engine does not have.

**Why this example is on the page at all.** An earlier version of this engine
got it wrong — refusing the Aborts the book grants by name in Segments 9–11 and
halving the DCV it restores — because the design cited 6E2 p.39 and p.106 for a
claim that lives on p.107. The suite was green throughout. Running the page,
rather than citing it, is what caught it.

---

## Starburst does a Move By — 6E2 p.72

**Script:** `examples/raw_starburst.py` · **Verdict:** the example contradicts the page's own rule; the engine follows the RULE

The rule:

> "A successful Move By does half of the character's regular STR damage plus
> (velocity/10)d6 Normal Damage to the target (in other words, (STR/2) +
> (vel/10)d6)... **(Halve a character's STR before determining the STR damage
> he does with a Move By; that eliminates potential problems with trying to
> halve a half-die of damage.)** However, the character himself takes one-third
> of the STUN and BODY damage done to the target."

The example, four sentences later:

> "**Example:** Starburst (Flight 30m) is 10m away from Ogre. He does a Move By
> on the villain and ends up 20m away from Ogre at the end of the Maneuver. The
> villain takes ½ of Starburst's STR damage plus 30/10 = 3d6 for Starburst's
> velocity. Starburst has a 15 STR, so the villain takes (½ x 3d6) + 3d6 =
> 4½d6 of damage."

These do not agree:

| | STR → damage | Result |
|---|---|---|
| **The rule** — halve STR *first* | STR 15 → 7 → 7/5 = **1 DC** | 1 + 3 = **4 DC** |
| **The example** — halve the *dice* | STR 15 → 3d6 → ½ × 3d6 = **1½d6** | 1½ + 3 = **4½d6** |

The parenthetical exists precisely to forbid the second method — "that
eliminates potential problems with trying to halve a half-die of damage" — and
the example then halves a die anyway.

**Kirby follows the rule: 4 DC.** Everything else matches exactly — 20m past
the target, and the attacker taking one third.

If you are checking Kirby against the book by hand, this is the one place in
this document where the engine will look wrong and is not.

---

## Not yet reproducible

Honest gaps, listed so the absence is visible rather than implied:

| Example | Page | Needs |
|---|---|---|
| **Orion** fights blind | 6E2 p.9 | the ½ OCV / ½ DCV penalties for an unperceived opponent — the sense-affecting-powers spec |
| **Lazer** aborts to Dodge | 6E2 p.24 | a driver that spends the aborted Phase |
| **Matterhorn**'s dagger | 6E2 p.101 | turns on a GM ruling rather than a rule; not mechanically reproducible |

Orion is the acceptance criterion for the sense-affecting-powers work: when
that lands, this page should gain an entry asserting 6E2 p.9's table.
