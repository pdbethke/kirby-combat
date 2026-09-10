# What the O.K. Corral does not reach

The shootout exists to FLEX the engine, not to reproduce 1881. Its seed is
chosen for how many distinct rule paths it exercises, and this file is the
other half of that measurement: what the fights never touch.

Regenerate with `python scripts/coverage.py --seeds 20 --baseline docs/coverage-tactic.json`.
Figures below are that script's output over seeds 1-20, 235 Phases, all 20
fights decided.

**These are DOCTRINE's numbers.** `TacticChooser` is the deterministic
fallback, not the model this platform exists to run; see "The measurement
this file cannot yet make" at the bottom.

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

## The measurement this file cannot yet make

Everything above is `TacticChooser`, which is doctrine and a fallback.
The question that matters is whether a MODEL reaches more, because the
two answers call for opposite repairs: if a model also takes three kinds
of sixty-two, the fault is in what the Brief SHOWS it, and no amount of
chooser work will help.

`scripts/coverage.py --chooser deliberate` runs exactly that comparison
and was blocked on 2026-09-10 by the model provider, not by code:

    Google AI error (429): "Your prepayment credits are depleted"

Auth reached the provider, so the local token path is fine; the container
is wired to Google AI alone and every other model name 404s. Worth
knowing before re-running: a model run that cannot reach its provider
does NOT fail --- `ModelChooser` falls back to doctrine by design and
records a note --- so it produces a baseline identical to this one and
looks like a finished experiment. The tell is speed.
