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

Working, and tested at 1179 tests. It is a **library**: no server, no I/O, no
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
- **Perception** — sense groups, Invisibility, Stealth against PER, Mind Scan,
  Combat Sense and Danger Sense; an attacker it cannot perceive is one a
  combatant cannot target
- **Initiative** — DEX order with Lightning Reflexes, Fast Draw, and Block's
  "acts first regardless of relative DEX"
- **Conditions** — a canonical status vocabulary derived from live state and
  the event log, emitted as gained/lost deltas

**The session layer** adds a SPD-chart timeline, an event log, per-action
rewind, and `to_dict` / `from_dict` round-trip for a whole encounter.

**The setting layer** puts a place around the fight: `Campaign` → `World` →
`Scene` → `Encounter`, where a Scene is somewhere that exists whether or not
anyone is fighting in it — a base, a house, five occupants doing their chores.
**Time is a mechanic here, not a loop counter.** An `Encounter` drives the
clock across every session in a Scene: `advance_segment` walks Segments 1-12,
wraps the Turn, fires the Post-Segment 12 Recovery for everyone (6E2 p.131,
"even Stunned ones"), and writes a `SegmentAdvanced` event to each session's
log. Because elapsed time is recorded rather than merely tracked, the log can
answer "has a Phase passed for this character?" — which is what makes a
condition like Stunned clear on its own. Combat in one room and a countdown in
another advance on the same Segments.

**Outcomes are recorded, not just computed.** Attack and Block resolution and
the passage of time all leave events in the log, so a fight replays from that
log alone and conditions like Stunned and Dead derive from history rather than
being recalculated. The pure resolvers stay pure: recording entry points sit
beside them and are opt-in.

## Usage

Combatants are plain objects — nothing here needs a character file. This
snippet runs as-is:

```python
from kirby_combat.models import (
    AttackInput, AttackPower, DiceValues, StatBlockCombatant,
)
from kirby_combat.resolution.to_hit import resolve_to_hit
from kirby_combat.template import RAW_SUPERHEROIC

def fighter(id_, name, **over):
    """A combatant with workable defaults; override what matters."""
    base = dict(ocv=8, dcv=8, omcv=3, dmcv=3, spd=4, dex=18, ego=10, str_=15,
                con=20, pre=15, rec=8, pd=8, ed=8, rpd=0, red=0, md=0,
                power_defense=0, flash_defense=0, max_stun=40, max_body=12,
                max_end=40, current_stun=40, current_body=12, current_end=40)
    return StatBlockCombatant(id=id_, name=name, **{**base, **over})

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

Eight runnable demos, none of which need anything installed beyond the package:

| | |
|---|---|
| `examples/rooftop_brawl.py` | a narrated fight — SPD phases, abort to Dodge, knockback off a roof, falling damage, Post-Segment 12 recovery, and a rewind |
| `examples/mental_duel.py` | the OMCV/DMCV pipeline — mental to-hit, Mental Blast against Mental Defense, Mind Control measured against EGO |
| `examples/bring_the_house_down.py` | scenery as combatants — destroy a support column and watch the collapse cascade and drop everyone standing above it |
| `examples/hold_the_line.py` | Presence attacks on the effects ladder, and twenty thugs resolved as one Unit with morale |
| `examples/the_house.py` | a Scene with no combat in it — a house, five occupants, chores on a clock; the setting layer standing on its own |
| `examples/one_turn.py` | the time mechanic alone — one full Turn, Segment by Segment, with the SPD chart deciding who acts when |
| `examples/status_stream.py` | conditions as a live feed — gained/lost deltas a client can render on a token |
| `examples/replay_a_fight.py` | a fight reconstructed from its event log alone, and shown to agree with the state the engine held |

```bash
.venv/bin/python examples/rooftop_brawl.py
```

## RAW alignment

Every game-mechanical commit cites a specific page or section in 6E1 / 6E2
(or in Dorman's MIT-licensed `dmdorman/hero6e-foundryvtt` reference port,
where Dorman's behavior is the source of truth). The Codex retrieval system
backs this — values are verified against the corpus rather than memory.

That is a claim, so [`docs/raw-alignment.md`](docs/raw-alignment.md) makes it
checkable: the rulebooks' own **named worked examples**, run against the
engine. Each is a script in `examples/` that **asserts** the book's numbers,
and `tests/test_examples.py` requires every one to exit 0 — so the page cannot
drift from what the engine actually does. It also records where the engine is
approximate, and one case (Move By, 6E2 p.72) where the book's worked example
contradicts the rule it illustrates and Kirby follows the rule.

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

The table itself has since landed: terrain with its own PD and ED, elevation
and concealment that move OCV and DCV, and line of sight worked out from where
a character is actually standing — see `kirby_combat/scene/`. Perception now
governs targeting, so a combatant cannot attack what it cannot perceive.

What's still to come: sense-affecting powers (Flash, Darkness, Images) as a
first-class layer over the sense groups; Stunned *enforced* rather than only
recorded, which touches acting order; and mental Stunned, which has no
recording path yet. Kirby plays characters; it does not create them. Character
creation stays in Hero Designer.

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
