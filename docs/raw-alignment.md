# RAW alignment — the book's own examples, executed

The HERO System rulebooks teach through named worked examples: Andarra
recovering from being Stunned, Starburst flying past Ogre, Orion fighting
blind. Each states exact numbers, which makes them the sharpest available test
of whether an engine implements the rules or merely resembles them.

**This page ships no rules text.** Each entry names a page, describes the
book's scenario in our own words, and shows what Kirby produces from those
inputs. Open your own copy and check us.

Every example is backed by a script in `examples/`. The scripts **assert** the
book's numbers rather than printing them, and `tests/test_examples.py` requires
each to exit 0. So this page cannot drift from the engine: if the engine stops
agreeing with a book example, the suite goes red.

Two things this page deliberately does not do.

It does not claim the engine reproduces every example in the books — only those
listed here, and it says where it is approximate.

And it does not treat a worked example as automatically authoritative over the
rule it illustrates. **They sometimes disagree** (see Move By). Where they do,
the engine follows the rule and this page documents the divergence, because
silently matching a self-contradictory example would mean encoding a mistake
and calling it fidelity.

---

## Recovering from being Stunned — 6E2 p.107

**Script:** `examples/raw_andarra.py` · **Verdict:** rule and example agree; conformance asserted

**The book's scenario, paraphrased.** A character with DEX 20 and SPD 3 is
Stunned by an attack in Segment 6. Her next Phase falls in Segment 8, and she
must spend it recovering. She recovers when her DEX comes up in that Segment —
at which point she gets her full DCV back and her Placed Shot modifiers return
to normal — but she still cannot take any other Action until her next Phase in
Segment 12. The book is explicit that she *may* Abort her Segment 12 Phase
during Segments 8 (after her DEX), 9, 10 or 11.

**What Kirby does with those inputs** (`python examples/raw_andarra.py`):

```
Segment 6 — Stunned by an attack

Segment 7    {stunned}                  DCV 5 (base 9)   Abort allowed: False
Segment 8    {recoveringFromStunned}    DCV 5 (base 9)   Abort allowed: False
Segment 9    {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 10   {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 11   {— none —}                 DCV 9 (base 9)   Abort allowed: True
Segment 12   {— none —}                 DCV 9 (base 9)   Abort allowed: True
```

Segments 9, 10 and 11 — the ones the book names — are asserted by the script.

**Where this is approximate, stated plainly.** The book restores her DCV
*partway through* Segment 8, at her DEX. Kirby derives conditions by folding an
event log, which carries no intra-Segment DEX position, so its edge is the end
of Segment 8 rather than DEX 20 within it. The engine therefore over-penalises
her for the post-DEX remainder of one Segment. That case is printed and
labelled, never asserted, because asserting it would claim a fidelity the
engine does not have.

**Why this example is on the page at all.** An earlier version of this engine
got it wrong — refusing the Aborts the book grants in Segments 9–11 and halving
the DCV it restores — because the design cited 6E2 p.39 and p.106 for a claim
that lives on p.107. The whole test suite was green throughout. Running the
example, rather than citing the page, is what caught it.

---

## Fighting an opponent you cannot perceive — 6E2 p.9

**Script:** `examples/raw_orion.py` · **Verdict:** rule and example agree; conformance asserted

**The book's scenario, paraphrased.** Orion is blinded by a Flash and can
perceive nobody with a Targeting Sense. He is halved on both OCV and DCV
hand-to-hand; at Range his OCV drops to zero and his DCV is halved. He then
spends a Half Phase Action on a Hearing PER Roll against one attacker, Durak,
and makes it — and against Durak **only** he is at -1 DCV and half OCV
hand-to-hand, and at full DCV and half OCV at Range. Against everyone else the
unmitigated numbers still stand, until the benefit lapses at the start of his
next Phase.

**What Kirby produces**, giving Orion 8 OCV / 8 DCV (the page states ratios and
a flat modifier, not his CVs):

| | HTH OCV | HTH DCV | Ranged OCV | Ranged DCV |
|---|---|---|---|---|
| Before the Flash | 8 | 8 | 8 | 8 |
| Blinded, vs anyone | 4 | 4 | 0 | 4 |
| Blinded, vs **Durak** after the Hearing PER Roll | 4 | **7** | **4** | **8** |
| Blinded, vs everyone else, same Segment | 4 | 4 | 0 | 4 |
| After the benefit lapses | 4 | 4 | 0 | 4 |

**Why this example is worth executing.** Read the third and fourth rows
together: the same combatant, in the same Segment, at DCV 7 against one
opponent and DCV 4 against another. Three things follow, and each breaks a
design that treats "blind" as one global CV factor.

- The penalty is **per-opponent**. A `(session, combatant_id) -> factors` seam
  cannot express two answers at once.
- The mitigation is a **flat -1**, not a second halving. Halving twice gives 2
  where the book gives 7.
- The mitigation is **asymmetric**: full DCV at Range, but only -1 in
  hand-to-hand — and Ranged OCV comes off zero while HTH OCV stays halved.

**Two defects this script found that the tests did not.** It was written second
by design, not last, on the theory that running the book catches what per-item
review misses. Both faults it caught were the same shape: the rule worked for a
build-backed combatant and silently did nothing for a `StatBlockCombatant`,
which has no `senses()` — so the penalty never applied to the combatant type
every example and much of the suite uses, and asking one for a PER roll raised
`AttributeError`. Fixed at the source and pinned in
`tests/test_sense_penalties.py`.

---

## Move By — 6E2 p.72

**Script:** `examples/raw_starburst.py` · **Verdict:** the page's example contradicts the page's own rule; the engine follows the RULE

**The rule, paraphrased.** A Move By does half the attacker's STR damage plus
one d6 per 10m of velocity. The page adds a parenthetical instruction: halve
the character's STR *before* working out its damage, specifically to avoid
having to halve a half-die. The attacker takes one third of the damage done.

**The example, paraphrased.** A flying character with STR 15 and 30m of Flight
Move Bys a villain from 10m away, ending 20m past him. The book computes the
damage as (½ × 3d6) + 3d6 = 4½d6.

**These do not agree**, because the example halves the *dice* — the very thing
the parenthetical exists to prevent:

| | STR → damage | Result |
|---|---|---|
| **The rule** — halve STR *first* | STR 15 → 7 → 7/5 = **1 DC** | 1 + 3 = **4 DC** |
| **The example** — halve the *dice* | STR 15 → 3d6 → ½ × 3d6 = **1½d6** | 1½ + 3 = **4½d6** |

**Kirby follows the rule: 4 DC.** Everything else in the example matches
exactly — 20m past the target, and the attacker taking one third.

If you are checking Kirby against the book by hand, this is the one place on
this page where the engine will look wrong and is not.

---

## Not yet reproducible

Honest gaps, listed so the absence is visible rather than implied:

| Example | Page | Needs |
|---|---|---|
| Aborting to Dodge | 6E2 p.24 | a driver that spends the aborted Phase |
| Adding damage to a weapon | 6E2 p.101 | turns on a GM ruling rather than a rule; not mechanically reproducible |

Orion fighting blind used to head this table. It was the acceptance criterion
for the sense-affecting-powers spec, and it now has an entry of its own above.
