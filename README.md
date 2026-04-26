# kirby-combat

Pure-Python combat engine for the HERO System 6th Edition, designed as the
authoritative back-end for [Kirby](https://kirby.productbinder.io) — the
HERO System VTT in the Kirby product line.

Zero runtime dependencies (stdlib only). Strict TDD. RAW-aligned against
the official 6E2 / 6E1 books, with per-rule citations on every behavioral
commit.

## Status

- **Phase 1** (v0.1.0): Attack pipeline (to-hit / damage / defense /
  knockback / status). 107 tests.
- **Phase 2 Plan 1** (v0.2.0): Engine foundation. CombatSession + event
  log + rewind, reactive defenses, tactical modifiers, movement, AoE,
  Scene data model, falling, cover, line-of-sight, hazards, recovery,
  adjustments, entangle, flash, martial arts, triggers, held actions.
  450 tests passing. 96% coverage on `session/`, `scene/`, `resolution/`.
- **Phase 2 Plan 2** (next): mental combat, vehicles, mass combat,
  breakables, PRE attacks, GM tools, serialization.

## Usage

```python
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import RandomRoller

session = CombatSession.create(
    id="encounter-1",
    combatants=[hero, villain],
    scene=warehouse_scene,
    template=CombatTemplate.default_6e_superheroic(),
    dice_roller=RandomRoller(),
).start()
```

See `examples/` for runnable demos.

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

## License

MIT. The combat-mechanics derivation is independent NDA-clean work — no
proprietary HERO Designer source enters this repo. See `LICENSE`.
