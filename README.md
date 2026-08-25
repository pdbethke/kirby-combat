<p align="center">
  <img src="docs/kirby-vtt.jpg" alt="Kirby VTT — a comic panel in the Kirby style: a caped, armoured figure lettered KV bursting forward through exploding stars and crackling energy." width="900">
</p>

# kirby-combat

Pure-Python combat engine for the HERO System 6th Edition, designed as the
authoritative back-end for [Kirby](https://kirbyvtt.org) — the
HERO System VTT in the Kirby product line.

One runtime dependency, [kirby-cost](https://github.com/pdbethke/kirby-cost),
and that is deliberate: anything deriving a cost, a number of dice or a roll
belongs there, and this package acts on the numbers it is given rather than
deriving its own. It was optional once, imported behind `try`/`except`, and
that optionality is exactly what let the same dice arithmetic grow a second
home here — three copies of "5 STR to the die" across two repositories,
agreeing only by luck.

Strict TDD. RAW-aligned against the official 6E2 / 6E1 books, with per-rule
citations on every behavioral commit.

## Status

Working, and tested at 980 tests. It is a **library**: no server, no I/O, no
API layer. The virtual tabletop consumes it as a dependency, never the other
way round — nothing here reaches back up.

**What it resolves**

- **Attacks** — strike, killing, ranged, haymaker, autofire, rapid fire,
  multiple attack, sweep, area of effect, pulling a punch
- **Grappling** — grab, throw, entangle
- **Tactics** — brace, set, dive for cover, held actions, triggers
- **Reactions** — abort, block, dodge
- **Movement** — running, leaping, flight, swimming, teleportation,
  tunnelling, and knockback as its own resolver
- **Mental combat** — the OMCV/DMCV pipeline: Mental Blast, Mind Control,
  Telepathy, Mental Illusion, Mental Entangle
- **The scene** — surfaces with their own PD/ED, walls, hazards, cover,
  line of sight, elevation, falling
- **Vehicles** — passengers, ramming, driving rolls
- **Mass combat** — a mob as one Unit with a shared BODY pool and morale
- **Breakables** — scenery with BODY, and structural collapse that cascades
- **Presence attacks** — intimidation as a mechanic, on an effects ladder
- **GM tooling** — three override tiers, attacks on behalf of, spawn/despawn

**The session layer** adds a SPD-chart timeline, an event log, per-action
rewind, and `to_dict` / `from_dict` round-trip for a whole encounter.

## Usage

Combatants are plain objects — nothing here needs a character file. This
snippet runs as-is:

```python
from kirby_combat.models import AttackInput, AttackPower, Combatant, DiceValues
from kirby_combat.resolution.to_hit import resolve_to_hit
from kirby_combat.template import RAW_SUPERHEROIC

def fighter(id_, name, **over):
    """A combatant with workable defaults; override what matters."""
    base = dict(ocv=8, dcv=8, omcv=3, dmcv=3, spd=4, dex=18, ego=10, str_=15,
                con=20, pre=15, rec=8, pd=8, ed=8, rpd=0, red=0, md=0,
                power_defense=0, flash_defense=0, max_stun=40, max_body=12,
                max_end=40, current_stun=40, current_body=12, current_end=40)
    return Combatant(id=id_, name=name, **{**base, **over})

blast = AttackPower(
    xmlid="ENERGYBLAST", name="Energy Blast",
    damage_dice=10, half_die=False, plus_one=False,
    damage_type="normal", defense_type="ed",
    range_m=200, uses_str=False, str_min=0,
    armor_piercing=0, penetrating=0, increased_stun_mult=0,
)

result = resolve_to_hit(AttackInput(
    attacker=fighter("hero", "Hero", ocv=9),
    target=fighter("villain", "Villain", dcv=7),
    power=blast,
    distance_m=20.0,
    aim=None,
    dice=DiceValues(to_hit=[2, 3, 3], damage=[3] * 10,
                    hit_location=[], stun_multiplier=[], knockback=[]),
), RAW_SUPERHEROIC)
print(result.hit, result.margin)   # True 1  — a hit, by 1
```

`CombatSession` sits on top when you want a timeline, an event log and
rewind rather than one-shot resolution — see `examples/rooftop_brawl.py`.

## Examples

Four runnable demos, none of which need anything installed beyond the package:

| | |
|---|---|
| `examples/rooftop_brawl.py` | a narrated fight — SPD phases, abort to Dodge, knockback off a roof, falling damage, Post-Segment 12 recovery, and a rewind |
| `examples/mental_duel.py` | the OMCV/DMCV pipeline — mental to-hit, Mental Blast against Mental Defense, Mind Control measured against EGO |
| `examples/bring_the_house_down.py` | scenery as combatants — destroy a support column and watch the collapse cascade and drop everyone standing above it |
| `examples/hold_the_line.py` | Presence attacks on the effects ladder, and twenty thugs resolved as one Unit with morale |

```bash
.venv/bin/python examples/rooftop_brawl.py
```

## RAW alignment

Every game-mechanical commit cites a specific page or section in 6E1 / 6E2
(or in Dorman's MIT-licensed `dmdorman/hero6e-foundryvtt` reference port,
where Dorman's behavior is the source of truth). The Codex retrieval system
backs this — values are verified against the corpus rather than memory.

## Tests

```bash
.venv/bin/pytest tests/ -q
.venv/bin/pytest tests/ --cov=kirby_combat --cov-report=term-missing
```

## Where this is going

This is one of three engines behind [Kirby](https://kirbyvtt.org), a virtual
tabletop for the HERO System in active development:

- **[kirby-cost](https://github.com/pdbethke/kirby-cost)** — reads a HERO 6E
  build and costs it, validated against Hero Designer
- **[kirby-sheet](https://github.com/pdbethke/kirby-sheet)** — renders a
  character to JSON, text, HTML, PDF, or back to `.hdc`
- **[kirby-combat](https://github.com/pdbethke/kirby-combat)** — the combat
  engine: attacks, movement, mental combat, vehicles, mass combat,
  destructible terrain

What's still to come is the table itself — terrain with its own PD and ED,
elevation and concealment that move OCV and DCV, and line of sight worked out
from where a character is actually standing. Kirby plays characters; it does
not create them. Character creation stays in Hero Designer.

Progress and notes at [kirbyvtt.org](https://kirbyvtt.org).

## License

PolyForm Noncommercial License 1.0.0 — the same terms as
[kirby-cost](https://github.com/pdbethke/kirby-cost) and
[kirby-sheet](https://github.com/pdbethke/kirby-sheet). Source-available and
free for personal, non-commercial use; not OSI-approved open source.

Relicensed from MIT at **0.4.0**. Versions 0.3.x were published under MIT and
those grants stand — MIT cannot be withdrawn from a release already made. This
applies from 0.4.0 onward.

The combat-mechanics derivation is independent work: no proprietary HERO
Designer source enters this repository. Not affiliated with or endorsed by
DOJ, Inc. d/b/a Hero Games; **HERO System™** is their trademark.
