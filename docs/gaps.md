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
