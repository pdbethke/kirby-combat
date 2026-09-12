# What the O.K. Corral does not reach

The shootout exists to FLEX the engine, not to reproduce 1881. Its seed is
chosen for how many distinct rule paths it exercises, and this file is the
other half of that measurement: what the fights never touch.

Regenerate with `python scripts/coverage.py --seeds 20 --baseline docs/coverage-tactic.json`.
Figures below are that script's output over seeds 1-20, 235 Phases, all 20
fights decided.

**These are DOCTRINE's numbers.** `TacticChooser` is the deterministic
fallback, not the model this platform exists to run; see "The measurement,
made: doctrine vs a model" at the bottom.

## The headline

**Three of sixty-two action kinds are ever chosen.**

| kind | chosen | offered |
|---|---|---|
| `attack` | 153 | 775 |
| `move_to_cover` | 42 | 140 |
| `disengage` | 40 | 235 |

Everything else in the engine is offered and refused.

## Offered and never taken

Both columns are now counted the same way --- every menu of every Phase,
recorded off the chooser itself rather than off one opening menu --- so
they can honestly be set beside each other.

| kind | offers | chosen |
|---|---|---|
| `rapid_fire` | 4675 |
| `attack_construct` | 3960 |
| `move_strike` | 931 |
| `presence_attack` | 791 |
| `move` | 791 |
| `block` | 791 |
| `coordinate` | 633 |
| `move_through` | 632 |
| `move_by` | 632 |
| `set` | 235 |
| `hold` | 235 |
| `hide` | 235 |
| `dodge` | 235 |
| `haymaker` | 195 |
| `presence_attack_group` | 191 |
| `multiple_attack` | 187 |
| `spread` | 142 |
| `stabilize` | 78 |
| `climb_fast` | 63 |
| `climb` | 63 |
| `trip` | 18 |
| `strike` | 18 |
| `grab` | 18 |
| `disarm` | 18 |
| `recover` | 13 |

Three of these are worth naming.

**`rapid_fire`, at 4,675 offers, is the most-offered action in the game**
and has never once been taken. So is `attack_construct` at 3,960: every
building and barrel in the lot is a legal target on every Phase.

**`stabilize` is offered 78 times and taken never.** That is the action
built for 6E2 p.109 --- a Paramedics roll that stops a dying man losing a
BODY a Turn --- and Doc Holliday carries Paramedics 11- for it. Men bleed
to death in these fights (`status:Dead` is among the rule paths reached)
while somebody who could have saved them shoots instead.

**`hide` is offered 235 times and taken never**, and it is the only route
to 6E2 p.52's Surprised. A rule wired into the engine cannot fire in this
benchmark because nothing ever chooses the manoeuvre that causes it.

## Rules that fire, and rules that do not

Twenty-one distinct rule paths are reached: `bleed:bleed_out`, `bleed:wound`, `cover-penalty`, `loc:Arm`, `loc:Chest`, `loc:Foot`, `loc:Hand`, `loc:Head`, `loc:Leg`, `loc:Shoulder`, `loc:Stomach`, `loc:Thigh`, `loc:Vitals`, `loc:roll`, `moved`, `recovery`, `shot-hit-cover`, `status:Dead`, `status:Dying`, `status:Knocked Out`, `status:Stunned`.

Never reached in twenty fights:

- **Surprised** (6E2 p.52) --- needs `hide`, never chosen.
- **The Range Modifier** --- every shot in the lot is inside 8 m, so the
  penalty is always zero. The table is exercised only by unit tests.
- **Penetrating / Armor Piercing** --- no weapon here has either.

The Corral cannot test any of those. That is a limit of the SCENE, not of
the engine, and the honest fix is a second benchmark laid out for range
and concealment rather than stretching this one.

## The measurement, made: doctrine vs a model

Made 2026-09-10 against a current frontier model, the same six seeds
each, 89 of 89 decisions answered by the model and none fallen back.
Which model, and how to reach one, belongs to `kirby-ai` --- this engine
owns no network hop and this file must not name one (see
`tests/test_vocabulary.py`).

| | doctrine | model |
|---|---|---|
| Phases | 69 | 89 |
| **kinds chosen** | **3 of 62** | **4 of 62** |
| `attack` | 45 | 61 |
| `move_to_cover` | 12 | 18 |
| `disengage` | 12 | 9 |
| `reposition_strike` | 0 | 1 |

**THE CHOOSER IS NOT THE BOTTLENECK.** Swapping a deterministic catalogue
for a frontier model moved the count by one kind out of sixty-two. Both
spend about nine actions in ten on `attack`. `move_strike` is offered 310
times and taken by neither; `hide` 89 times and taken by neither, which
keeps 6E2 p.52's Surprised unreachable no matter who is deciding.

The two differences worth naming, neither of them large:

* The model finds `reposition_strike` --- move to a vantage, then shoot ---
  once in 89 decisions. Doctrine never does. It is the only kind either
  reached that the other did not.
* The model fights LONGER: 89 Phases against 69, and disengages less (9
  against 12). It is more willing to stay in a fight it is losing.

So the repair is in what the Brief SHOWS and how offers are WORDED, not
in what is deciding. An offer that reads "Close to within reach via
Running, then strike" does not say the shot gets easier, and nothing on
the page says that hiding is what causes Surprise. A reader who does not
already know the rules cannot see the point of either, and it turns out
neither can a model that does.

### Reproducing it

    python scripts/coverage.py --seeds 6 --chooser model

`--chooser model` needs the three environment variables `kirby-ai`
defines for reaching a provider; the script names them when they are
missing. Their values, and the provider itself, live over there.

**Check the ANSWERED line before believing any of it.** A chooser that
cannot reach its provider does not fail --- it falls back to doctrine,
records the reason, and returns a baseline identical to the doctrine one.
The first run here came back in seconds picking exactly doctrine's three
kinds, and was 0 of 9 answered: every call a 403, because
`MedialibClient` sends `X-Tenant: kirby` and a token minted without a
matching `tenant` claim is refused with "Cannot access a different
tenant". A curl WITHOUT that header succeeds, which is exactly why
hand-testing said the path was fine.

Two provider-side traps cost an hour and are written up where they
belong, in the deployment notes rather than here: a reasoning model can
spend its whole output budget thinking and return EMPTY content on a
small `max_tokens`, and the production wrapper pins its model with no
environment override.

## What stating the payoff bought: nothing

Recorded 2026-09-10, because a negative result that is not written down
gets re-attempted.

The measurement above pointed at the page, so two offers were rewritten
to state what taking them is worth --- `attack` gained the number it
needs on 3d6, and `hide` gained the sentence that hiding is the only way
to cause 6E2 p.52's Surprised, at half DCV. Then the same six seeds, run
again against the same model.

| | before | after |
|---|---|---|
| kinds chosen | 4 of 62 | 4 of 62 |
| `attack` | 61 | 65 |
| `move_to_cover` | 18 | 20 |
| `disengage` | 9 | 11 |
| `reposition_strike` | 1 | 1 |
| **`hide`** | **0 of 89 offers** | **0 of 97 offers** |

Nothing moved. Telling a model, in the rules' own terms and with the page
cited, that an action buys half the target's DCV did not make it choose
that action once in ninety-seven Phases.

So "the page does not say what things buy" is now largely disconfirmed
too, and the remaining explanations are worth separating:

1. **The scene.** Nine men inside four metres of open ground. Hiding
   costs a whole Phase, every enemy is already adjacent, and Doc holds a
   coach gun needing 14-. Surprise at half DCV does not pay for a Phase
   there. **A chooser declining `hide` at the O.K. Corral may simply be
   right**, and this benchmark cannot tell the difference between a
   correct refusal and a blind one.
2. **The menu.** 71 offers a Phase, of which `rapid_fire` and
   `attack_construct` are about half --- and reading them shows why they
   are refused: they are mostly offers to shoot SCENERY. That is a
   composition problem, not a wording one.

Explanation 1 is the one this file has been circling since the beginning:
the Corral cannot exercise range, concealment or elevation because it has
none of them. The next useful move is a SECOND scenario built for those,
not further edits to this page --- and now there is an instrument that
will say whether it worked.

## The second benchmark: the long street

Built 2026-09-10, because the conclusion above was that the SCENE was the
limit and not the page. The Corral keeps what it is good at --- a
knife-range brawl where cover, Hit Locations and bleeding all bite --- and
this is a different fight whose every feature exists to make one
previously-unreachable rule reachable.

  * **Forty-five metres between the sides at the start**, which is 6E2's
    -6 OCV band, with -4 and -2 bands to cross on the way in.
  * **A rifle that outranges a revolver four to one**, so "can I even
    reach" is a question somebody has to answer.
  * **Rooftops at 4.5m** and building fronts you can climb to reach them.
  * **Cover taller than a standing man**, which the Corral has none of ---
    everything there is chest-high and shot over.

Measured over six seeds each, doctrine:

| | corral | street |
|---|---|---|
| Phases | 69 | 362 |
| kinds chosen | 3 | 4 |
| rule paths | 20 | 23 |

**Street-only paths: `range-penalty`, `shot-across-height`, `loc:Head`.**
The Range Modifier had never once fired in a benchmark before this; every
shot at the Corral is inside 8m, so the table was exercised only by unit
tests. Beck shoots down from the feed-store roof at three different
people and two shoot back up at him.

Between them the two scenes reach 23 distinct paths, and nothing the
Corral reaches is lost.

### It did not work the first time, and the reason is worth keeping

The first layout had all four furnishings, both roofs and five climbable
fronts --- and offered `move_to_cover`, `hide`, `climb` and
`reposition_vantage` **zero times in six fights**. Two engine constants
decide what a fighter is even shown:

  * `CLIMB_FACE_REACH_M = 1.0` --- you must be within a METRE of a face to
    climb it. Ida started two metres off the stable front, so both roofs
    were decoration.
  * Cover must be inside a Half Move, 6m. The nearest furnishing was 8m
    from the posse.

And doctrine never moves --- `move` is offered 914 times and taken zero ---
so nothing came into reach later either. **A scene has to put its
affordances where the rules can see them**, and "the file contains a
rooftop" is not "anybody can get to one".

The probe could not see that either, which is the other half of the
lesson: it had no marker for height, so a scene with unused rooftops
measured identically to one without any. `shot-across-height` exists now.
It took two attempts to wire --- a combatant carries no position (the
SCENE does), and `loop.resolvers` imports `resolve_attack_in_session` by
name at import time, so patching the defining module intercepts nothing.

### Still not reached, by either scene

`hide` and `climb` are now OFFERED on the street and still taken zero
times by doctrine, so 6E2 p.52's Surprised remains unreached. That is now
a chooser question rather than a scene one, and for the first time the
two can be told apart.

## Two mechanical improvements, neither of which moved a decision

Recorded 2026-09-10 alongside the first negative result, because the
pattern is now the finding.

| change | expected | measured |
|---|---|---|
| offers state their payoff | more kinds chosen | 4 of 62 -> 4 of 62 |
| menu halved (one target per object) | more kinds chosen | 3 of 62 -> 3 of 62 |

The second is worth spelling out. Folding a furnishing's four projected
edges back into one target cut `attack_construct` from 10,853 offers to
3,613 and `rapid_fire` from 11,762 to 4,522; the page a chooser reads
went from 71 offers a Phase to 52 and from ~17,600 characters to ~9,800.
Half the input, and the model chose the same three kinds: `attack`,
`move_to_cover`, `disengage`.

Both changes were worth making on other grounds --- one is a correctness
fix I had introduced that morning, the other halves the cost of every
decision --- but neither is evidence about tactics, and neither should be
sold as one.

**What the model HAS done that doctrine cannot** is find an engine
defect. It chose `dodge` for a Stunned combatant, which 6E2 p.106
forbids, which enumeration was not gating, and which `mark_aborting`
answers with a `ValueError` that escapes `on_unresolvable="skip"` and
kills the fight. `TacticChooser` picks `dodge` zero times in 362 Phases,
so doctrine could have run that scene forever without meeting it.

So the honest read after a day of this: a model driving the benchmark is
valuable right now as a FUZZER --- it reaches states doctrine never
does --- and not yet as evidence that the engine's tactical breadth is
usable. Those are different claims and the instrument can tell them
apart, which is the thing that actually changed today.

## The page was telling the model our answer

Measured 2026-09-10, and it reframes most of what is above.

Five real decision points were captured from a fight, held FIXED, and
replayed under four pages with the identical menu. Twenty trials each.

| arm | attack | disengage | move_to_cover | move_strike | push |
|---|---|---|---|---|---|
| A the Brief as it was | 8 | 8 | 4 | 0 | 0 |
| B + a line saying they are bunched | 8 | 8 | 4 | 0 | 0 |
| C + the point-of-view render | 8 | 8 | 4 | 0 | 0 |
| **D minus our doctrine hint** | **15** | 1 | 0 | **3** | **1** |

A, B and C are not merely similar. They are IDENTICAL, trial for trial ---
adding a whole rendered image changed not one decision. D changes
everything.

**The Brief ends with "What your doctrine says, best first:" --- the
TacticChooser catalogue's own ranked answer --- eleven lines above the
menu.** Remove it and the model stops agreeing with doctrine.

`move_strike` is the tell. It is offered 931 times across six fights and
was taken ZERO times all week by either chooser; without the hint it is
picked three times in twenty. `push` likewise --- and legitimately: the
one that took it was an unarmed man Pushing his bare STR strike, which
6E2 p.135 allows because STR costs END.

### What this invalidates

**"The chooser is not the bottleneck" (475fd0d6) is now unsafe.** That
conclusion rested on a model reaching the same three kinds as doctrine ---
while being shown doctrine's recommendation. The agreement was
substantially circular.

It also explains the two null results above. Stating an offer's payoff
and halving the menu both moved nothing because neither competed with an
explicit ranked recommendation sitting above the list.

### What it does NOT show

That removing the hint is BETTER. D concentrates harder on `attack` (15 of
20 against 8) and abandons `move_to_cover` entirely; more variety is not
the same as better play, and this benchmark still cannot grade a decision
as right or wrong. Five situations and four trials can show an effect this
large and nothing subtle.

### What to do about it

The hint is not obviously wrong to include --- a GM briefing a player
offers advice. But it must be a MEASURED choice, so the doctrine section
needs the same off switch the formation line has, and every
model-versus-doctrine number in this file should be re-taken with it
off before any of them is trusted.

## Re-taken with the hint off

The probe above used five fixed decision points. This is the same thing
at fight scale, six seeds, 80 of 80 decisions answered by the model and
none fallen back.

| corral, model | hint ON (89 Phases) | hint OFF (80 Phases) |
|---|---|---|
| **kinds chosen** | **4 of 62** | **5 of 62** |
| `attack` | 61 | 64 |
| `move_to_cover` | 18 | **0** |
| `disengage` | 9 | 9 |
| `reposition_strike` | 1 | 0 |
| `move_strike` | 0 | **5** |
| `move_through` | 0 | **1** |
| `strike` | 0 | **1** |

`move_strike` --- offered 931 times across a week and taken zero times by
anything --- is picked five times once the page stops printing our answer.
`move_through` and `strike` are first-ever picks too. And `move_to_cover`
goes 18 to 0: that was doctrine's recommendation being echoed back, not
the model's judgement.

**The hint-ON figure predates the flag being recorded**, so the baseline
file cannot prove it was on. It is asserted from the fact that nothing
set `KIRBY_BRIEF_NO_DOCTRINE` until 2026-09-11. Every baseline written
since records both switches.

### And it broke the engine again

The street re-take did not finish. It died on:

    TypeError: apply_event() takes 2 positional arguments but 3 were given
      loop/resolvers.py, in _resolve_recover

`_resolve_recover` passed a stray argument, so it raised on EVERY call it
had ever received --- `recover` was registered, enumerated and unrunnable.
It survived because nothing ever chose it: doctrine never does, and a
model shown doctrine's hint agreed with doctrine.

**That is two engine defects found the same way in two days** --- `dodge`
for a Stunned combatant, and this --- both in kinds doctrine never picks.
A benchmark driven only by its own catalogue re-tests the catalogue's
habits. Turning the hint off is what reached them, which is a better
argument for the model-driven runs than any tactical number in this file.

## The street, hint off — and Surprised finally fires

Three fights, 275 of 275 decisions answered by the model, none fallen
back.

| street, model | hint ON | hint OFF |
|---|---|---|
| **kinds chosen** | **3 of 62** | **6 of 62** |
| `attack` | 139 | 225 |
| `move` | 0 | **20** |
| `hide` | 0 | **17** |
| `dodge` | 0 | **6** |
| `move_to_cover` | 6 | 5 |
| `recover` | 0 | **2** |
| `disengage` | 6 | 0 |

**`surprised` is in the rule paths reached.** This file has said five
separate times that 6E2 p.52's Surprised cannot fire in any benchmark ---
"a rule wired into the engine cannot fire", "unreachable no matter who is
deciding". It fires now, and the whole chain is what fired: `hide` chosen
17 times, `_resolve_hide` recording who lost track of whom, `concealment`
reading that back, `is_surprised` agreeing, and the attack resolving at
half DCV.

The marker only trips when `Surprise.applies` is true --- the dataclass's
`__bool__` returns it --- so this is a real Surprised attack and not a
Surprise object that declined.

`move` likewise: offered 914 times across the week and taken zero times
by anything, chosen 20 times here. The model closes distance when nobody
tells it not to.

### What this does and does not settle

It settles that the engine's tactical breadth is REACHABLE, which no
measurement before this had shown. Three kinds became six; a rule wired
two days ago and declared unreachable four times fired.

It does not settle that the choices are GOOD. `attack` still takes 225 of
275, `disengage` collapses to zero, and nothing here grades a decision as
right or wrong. Three fights, one scene, one model.

And it does not make the doctrine hint wrong to include --- a GM briefing
a player does offer advice. It makes it a CHOICE that has to be measured,
which until 2026-09-11 it never was: the switch existed, unused, with a
comment saying it was there for exactly this.


---

## 2026-09-11 — grading the decision, not just counting it

This document ended, until today, on: "It does not settle that the
choices are GOOD ... nothing here grades a decision as right or wrong."
`kirby_combat.critique` closes that. Three deterministic graders, each
indicting only what is provably wrong and never endorsing anything:

* **futile** — an attack whose BEST possible roll gets 0 STUN and 0 BODY
  through the target's defenses, and therefore every roll for the rest of
  the fight. Asks `compute_defense` and the resolver's own
  `killing_damage` / `normal_damage`; a second damage calculation here
  would drift from the resolver silently.
* **scenery** — terrain attacked while an offer against a combatant was
  on the menu. NOT flagged when scenery is all there is.
* **wasted** — Recover at full STUN and END, which restores nothing and
  costs the Phase.

### What the first graded pass found

| run | decisions | bad |
|---|---|---|
| doctrine, corral, 6 fights | 69 | **0** |
| doctrine, street, 3 fights | 193 | **0** (see the correction below) |
| model, corral, hint ON, 6 fights | 81 | **0** |
| model, corral, hint OFF, 6 fights | 80 | **0** |

**The first finding was the GRADER's, not doctrine's.** This first read
"doctrine shoots buildings --- three Phases on the street attacking
terrain while a man was on the menu", which would have been an engine
defect. Tracing it to a tactic showed the opposite:

    T3 S12  deputy
      picked   : [attack:construct:east-saloon:...]  kind=attack_construct
      tactic   : 'smash_cover'   fell_back=False
      basis    : cover the enemy is using is worth more destroyed than ignored
      men      : ['haymaker->None']

The only non-scenery attack offer was a `haymaker` naming NOBODY, and the
tactic that fired was `smash_cover` --- deliberately stripping the cover
an unreachable enemy is hiding behind. Doctrine was right. The grader
counted a target-less maneuver as "a man was available", and an offer now
counts as a man only if it NAMES one who is in the fight.

Two lessons, both cheap here and expensive later: a grader's first
finding deserves the same scepticism as any other measurement, and
`docs/gaps.md` is where a retracted finding has to be written down, not
quietly dropped. Doctrine's real score on both scenes is **0 of 262**.

**Removing the doctrine hint cost the frontier model nothing in quality.**
Four action kinds became five with zero bad decisions either way, so the
extra variety measured on 2026-09-11 is clean variety, not noise.

### What this still does not settle

A clean sweep is not a good chooser. These graders cannot see a shot
declined in favour of a worse one, a target chosen badly among several
viable ones, or a Phase spent well. "Nothing provable was wrong" is the
whole claim.

---

## 2026-09-11 (later) — the doctrine hint causes bad decisions

The graders' first VALIDATED finding, traced before it was believed.

A local 35B on the corral, six fights, the doctrine hint ON: **5 scenery
findings in 80 decisions**. With the hint OFF, across 127 decisions on the
corral and 188 on the street: **zero**.

Every one of the five is the same shape --- RAPID FIRE with a Colt
revolver at a wall of **DEF 8, BODY 30**, while fifteen or sixteen offers
against a standing Earp were on the menu:

    T1 S12  frank_mclaury
      picked : [rapid_fire:harwood-house:gun-colt-revolver:3]
      reason : "The doctrine prioritizes fighting from cover and
                destroying enemy protection; attacking the nearby
                Harwood house wall chips its BODY, eroding their co..."
      MEN (16): attack->wyatt_earp, move_strike->wyatt_earp,
                attack->virgil_earp, ...

**The reasons name the doctrine.** Three of the five cite it explicitly
--- "the doctrine prioritizes sustained fire to erode cover", "aligning
with the doctrine to chip away at enemy cover". `smash_cover` is sound
doctrine and doctrine itself applies it correctly: on the street,
`TacticChooser` fired it three times with NO shot at a man available.
The model reads the same advice and applies it with sixteen men
shootable.

So this is not "the model is worse". It is the hint being **misapplied**,
and it is visible only because the grader was pointed at the arm that had
the hint. The variety table said the hint-ON arm was merely narrower
(5 kinds vs 9); it was also the only arm making provably bad decisions.

Not futile, though close: a Colt gets at most 4 BODY per hit through DEF
8, against BODY 30. `futile` cannot see it --- constructs are not in
`situation.enemies`, so `_target_of` returns None and the grader declines.
Grading an attack on TERRAIN is the obvious next extension.

### Retraction carried forward

An earlier note today said a local model went the OPPOSITE way from the
cloud models --- that removing the hint collapsed it onto `attack` and
lost `hide`. That came from five fixed situations, three trials, fifteen
decisions, calling the provider directly. Run through real fights it does
what the cloud models do, more so: corral 5 kinds -> 9, street 4 -> 10.
The small harness was wrong and the claim is withdrawn.

---

## 2026-09-11 (later still) — the corral finding replicates; terrain futility finds nothing

Two independent clean runs of the same four arms, local 35B. The model is
non-deterministic, so the fights diverge and the decision counts differ;
the finding does not.

| arm | run A | run B |
|---|---|---|
| corral, hint ON  | **5 of 80** | **5 of 70** |
| corral, hint OFF | 0 of 127 | 0 of 118 |
| street, hint ON  | 0 of 73  | 0 of 68  |
| street, hint OFF | 0 of 188 | 0 of 130 |

Variety holds across both: corral 4-5 kinds with the hint, 8-9 without;
street 4 with, 8-10 without.

So on the corral the doctrine hint costs roughly **7% of decisions**, and
removing it costs nothing measurable. On the street it costs nothing
either way --- whatever makes the corral different (nine men inside four
metres, buildings on every side) is not yet isolated.

### A NULL result, recorded as one

Extending `futile` to terrain found **zero** findings across all four
arms. That is the correct answer and was predicted before the run: the
Harwood house is DEF 8 BODY 30 and a Colt gets 4 BODY through at best ---
slow, not impossible. The grader is exercised only by its unit tests
here, which is worth saying out loud rather than letting an unfired
grader read as a clean bill.

Every attack on terrain in these fights was `scenery` and none was
`futile`. The two graders are measuring different things and both
answers are right.

---

## 2026-09-12 — Beam: a bullet does not widen

First defect found by asking "what is OFFERED in a western and never
taken, and should it have been offered at all?"

`spread` was offered 95 times across both benchmarks and taken zero
times. It should never have been offered to most of them. The HERO
System Equipment Guide p.69 lists the limitations every firearm is built
with:

    "Beam: Bullets can't be Spread, and only make relatively small
     'punctures'..."

THE BUILD DATA ALREADY SAID SO. The corral arsenal carries `BEAM` on
every pistol, revolver and rifle. `hero_view` parsed `REDUCEDEND`,
`NORANGEMODIFIER` and `CHARGES` and never read this one, `AttackPower`
had no field for it, and enumeration offered Spreading to anything
ranged. The dominant defect class again: a modifier the build declares,
carried nowhere, read by nothing.

Fixed: `AttackPower.beam`, parsed in `hero_view` beside the modifiers it
already read, gating the `spread` offer.

### What the arsenal turns out to know

| weapon | BEAM | may Spread |
|---|---|---|
| Pistol, Revolver, Rifle, Derringer | True | no |
| **Shotgun** | **False** | **yes** |

After the fix the street offers `spread` **zero** times, and the corral
offers it 43 times to exactly one weapon: Doc Holliday's **coach gun**.
A shotgun is the one firearm that genuinely does widen, and the imported
data had drawn that line correctly all along --- nothing in the engine
was reading it.

### The rest of the western list, unresolved

Offered and never chosen, still unexamined: `block` (1388 --- suspicious
in a gunfight, Block is an HTH maneuver), `coordinate` (1355),
`set` (520), `haymaker` (502 --- suspicious with a revolver),
`move_by` (360), `stabilize` (94), `climb`/`climb_fast` (58),
`grab`/`trip` (7), `reposition_vantage` (6).

Never offered at all and plausible in a western: `pickup`,
`throw_object`, `escape_str`, `escape_attack`, `release_held`, `sweep`,
`reposition`, `reposition_push`.

---

## 2026-09-12 — Block wore the abort gate and never the reach gate

Second defect from the same question. `block` was offered **1,388 times**
across the two western benchmarks and taken zero times, because for most
of those offers it was not a legal thing to do.

6E2 p.59, twice over:

    "Blocks only affect Ranged attacks with the GM's permission,
     according to special rules (see below)."

    "A character can normally Block any HTH Combat attack, including
     Disarms, Chokes, Grabs/Grab Bys, Move Bys/Throughs, sword blows,
     most No Range attacks..."

`_melee_gate` already decides reach for melee attacks, Move By, Move
Through, Coordinate and Spreading. The Block offer never asked it, so a
man forty metres from a rifle was invited to block it.

The comment directly above the offer site reads: "Block reaches
`mark_aborting` too, so it wears the same gate. Gating one defence and
not the others is how this class of defect survived its first fix." It
wore the ABORT gate. It never wore the REACH one.

Gated on `'direct'` --- not `'close'`, because a Block is declared
against an attack already coming and there is no half-move to reach the
attacker first.

| | before | after |
|---|---|---|
| corral | ~1,340 | **4** |
| street | ~48 | **0** |

The four survivors are correct: the corral is fought at four metres and
men do close.

MISSILE DEFLECTION is the "special rules" the page defers to, and this
engine has no concept of it --- nothing in the package names it and no
western character buys it. The gate is reach alone, and that limit is
recorded in the test rather than left to be rediscovered.

## 2026-09-12 — Haymaker with a revolver: the engine was RIGHT

Listed as suspicious in the western to-do: `haymaker` offered 502 times
to men holding guns. The book settles it against me, 6E2 p.71:

    "Firearms: A character can Haymaker a gunshot, unless the GM forbids
     him to. This could represent carefully aiming to hit the most
     vulnerable part of a target."

No change made. Recorded because a suspicion that was checked and
dismissed is worth as much to the next reader as one that was confirmed
--- and because the offer count alone looked exactly like the two real
defects beside it.

---

## 2026-09-12 — a man on his own cannot Coordinate

Third from the same question. `coordinate` was offered **1,355 times**
across the western benchmarks and taken zero times.

6E2 p.46:

    "A character cannot 'Coordinate' with himself."

    "To Coordinate attacks, the characters must attack on the same DEX
     on the same Phase... Faster characters may have to Hold their
     Actions to wait for comrades who have lower DEXs."

The offer was gated on `alive_enemies and allow_coordinate`, and
`allow_coordinate` is a parameter defaulting True that **nothing in this
package ever sets**. So the only condition it ever really tested was
that somebody was left to shoot at.

Measured on the corral before the fix: **12 of 187 offers went to a man
with no standing ally** --- the last Cowboy alive, invited to coordinate
with the dead. `run.py` passes fallen allies deliberately so a chooser
knows who it has lost; that list was reading as a partner.

    corral, offered to a man with no standing ally:  12  ->  0

The remaining 175 all have a living partner, so the fix is exact rather
than a blanket reduction. (Total offers move 187 -> 175 rather than
187 -> 165: removing offers changes what `FirstLegalChooser` takes when
doctrine falls through, so the fights themselves diverge slightly. The
count that matters is the zero.)

### The other half is a KNOWN HOLE, not an assumption

6E2 p.46 also requires the partners to "attack on the same DEX on the
same Phase". `enumerate_actions` takes no `segment` argument and holds no
phase table, so it cannot ask. That gate belongs to the driver --- which
the offer's own comment already says "resolves roll + join + execution
semantics". Written down here so the next reader finds a hole rather
than a claim.

### Score so far on the western list

| kind | offers | verdict |
|---|---|---|
| `spread` | 95 | **defect** — Beam ignored (Equipment Guide p.69) |
| `block` | 1,388 | **defect** — reach gate never applied (6E2 p.59) |
| `coordinate` | 1,355 | **defect** — no ally required (6E2 p.46) |
| `haymaker` | 502 | **correct** — 6E2 p.71 permits it with a gun |

Three of four suspicions were real, and the fourth was worth checking.

---

## 2026-09-12 — Set: a Phase spent aiming that bought nothing

Fourth from the same question, and the worst of them. `set` was offered
520 times across the western benchmarks and taken zero times. **Five
things were wrong with it at once.**

6E2 p.81:

    "This Combat Maneuver represents the effects of taking extra time to
     aim at a target with a Ranged attack, thereby improving one's
     accuracy. Set does not work with HTH Combat attacks. An attacker who
     wants to Set must spend a Full Phase aiming at the target (this is
     known in some genres as 'drawing a bead')... A character who has Set
     on a target receives a +1 OCV to all attacks against that target
     until he loses his Set. A character must Set on a specific target
     (either an individual or an object); he can't just Set until a
     target presents itself."

| # | defect |
|---|---|
| 1 | offered with `target_id=None` --- "he can't just Set until a target presents itself" |
| 2 | offered unconditionally, including to an actor with only HTH attacks |
| 3 | **`Set.ocv_bonus` was read by NOTHING but its own unit test** |
| 4 | the bonus ignored the target, where the rule grants it only against the man aimed at |
| 5 | the summary said "telegraphed strike" (melee flavour) and "+1 OCV next phase" (the rule says "until he loses his Set") |

**(3) is this repo's dominant defect class in its purest form.** The
resolver declared the Set; no attack resolution ever asked for the
bonus. A man could spend a Full Phase drawing a bead and be no more
accurate for it. The one test that touched `ocv_bonus` called it
directly, so the suite was green throughout.

Fixed: per-target offer gated on having a Ranged attack, a target-aware
`ocv_bonus`, the bonus folded into `AttackInput.ocv_modifier` in the
driver (a Set is a session fact and the resolver takes no session), and
an honest summary.

One PRE-EXISTING test asserted the defect --- "Even a healthy actor with
no enemies still gets dodge / set" --- and has been corrected with the
citation rather than worked around.

### Still not chosen

`set` is now offered 188 times on the corral and 472 on the street and
taken zero times by doctrine. That is now a DOCTRINE gap, not an offer
defect: no tactic in the catalogue recommends drawing a bead, and for a
rifleman at 40m with a -6 range penalty it is sometimes the best thing
available. Worth a tactic; not a rules bug.

### Score on the western list

| kind | offers | verdict |
|---|---|---|
| `spread` | 95 | **defect** — Beam ignored (Equip. Guide p.69) |
| `block` | 1,388 | **defect** — reach gate never applied (6E2 p.59) |
| `coordinate` | 1,355 | **defect** — no ally required (6E2 p.46) |
| `set` | 520 | **defect x5** — no target, no ranged gate, bonus delivered nowhere (6E2 p.81) |
| `haymaker` | 502 | **correct** — permitted with a gun (6E2 p.71) |
