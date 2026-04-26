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
- **Phase 2 Plan 2** (v0.3.0): Engine advanced. Mental combat pipeline
  (Mind Control / Telepathy / Mental Illusion / Mental Blast / Mental
  Entangle), vehicles (HDC-shaped Combatant subtype with passengers,
  ramming, driving rolls), mass combat (Unit aggregation + morale
  cycling), breakables (objects + structure cascade), Presence attacks,
  GM tooling engine layer (Tier 1/2/3 overrides, GM-on-behalf-of
  attacks, spawn/despawn), serialization (to_dict / from_dict with
  round-trip parity). 569 tests, 96% coverage.

### engine-advanced subsystems

| Module | Purpose |
|---|---|
| `kirby_combat/mental/` | OMCV/DMCV pipeline + the five mental powers |
| `kirby_combat/vehicles/` | Vehicle (Combatant subtype), passengers, ramming, controls |
| `kirby_combat/masscombat/` | Unit (pack-of-N) and aggregate resolution |
| `kirby_combat/breakables/` | ObjectCombatant + structure integrity cascade |
| `kirby_combat/pre_attacks/` | Presence attacks with effects ladder |
| `kirby_combat/gm/` | Tier 1/2/3 GMOverride helpers + GM attack + spawn/despawn |
| `kirby_combat/serialization/` | `to_dict` / `from_dict` for full session round-trip |

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
