# Changelog

## 0.2.0 — 2026-04-25

Phase 2 Plan 1 (engine foundation). RAW-verified against the Codex 6E
corpus; see `feat:` and `fix:` commits for per-rule citations.

### Added
- `CombatSession` state machine with per-action event log and rewind
- `DiceRoller` protocol + `RandomRoller` (default) + `FakeRoller` (tests)
- SPD chart + Timeline with DEX/EGO-tiebroken acting order
- Reactive defenses: Dodge, Block, Abort
- Tactical modifiers: Haymaker, Set, Brace, Dive for Cover, Pulling Punch, Held Action
- Movement base + Running, Leaping, Flight, Swimming, Teleportation, Tunneling
- Move-By, Move-Through, Grab, Throw
- Multiple Attack, Sweep, Rapid Fire, Autofire, Area of Effect
- Scene data model (3D geometry, terrain, walls, hazards)
- Falling with support check, 1d6/2m formula, landing on intermediate surfaces
- Cover resolution from walls + surfaces
- Line-of-sight gating for ranged attacks (with Indirect carve-out)
- Hazard triggers and environmental events
- Recovery (Phase 12, post-12, Full Recovery)
- Adjustment powers: Aid, Drain, Transfer, Suppress, Absorption with fade
- Entangle + casual/full STR escape
- Flash + per-phase sense-group recovery
- Persistent-effect derivation in `session/effects.py` (Adjustment / Entangle / Flash)
- Martial Arts with the 6E maneuver table (16 entries from 6E2 p93)
- Trigger power activation (event predicate + charges + recharge)
- Held Action release polish (predicate-driven release, in-place resolution, next-phase expiry)
- AoE + Scene integration (wall-blocking, Indirect bypass, hazard-along-path triggers)

### Changed
- Dice rolling: engine now rolls by default via `DiceRoller` protocol;
  tests inject `FakeRoller`. Reverses Phase 1 Decision #4.

### Fixed (RAW alignment per Codex audit, 2026-04-25)
- Killing Attack STUN multiplier corrected from 1d6 to ½d6 per 6E2 p100
- Knockback formula rewritten per 6E2 p116-118 (2d6 vs BODY, KB resistance
  on meters, surface-aware impact damage)
- Move-By damage uses (STR/2) + (vel/10)d6 per 6E2 p72
- Move-By/Through attacker self-damage fractions (1/3, 1/2, full) per 6E2 p72
- Block resolves vs attacker's OCV (not opposed margin) per 6E2 p59
- Autofire: single-target one-roll-margin/2-hits + multi-target line penalty
  per 6E2 p44
- Grab requires Attack Roll at -1 OCV per 6E2 p67
- Pulling A Punch: -1 OCV per 5 DCs pulled, halves BODY only per 6E2 p89
- Throw distance via 6E1 STR/THROWING TABLE
- Dive for Cover: ½ DCV prone at destination per 6E2 p87, with -1/2m
  distance penalty
- Brace: +2 OCV that only offsets Range Modifier per 6E2 p62
- Body Shot OCV penalty -1 per 6E1 p465
- Cover OCV mapping per 6E2 p45 §BEHIND COVER MODIFIERS (6 buckets)
- Flash Ranged attacks at 0 OCV per 6E2 p127
- Move-Through OCV divisor /10 in 6E (was 5E /5)
- Entangle modifiers: 0 DCV / ½ OCV per Dorman/6E2 (not -2 each)

### Tests
- 450 passing (up from 107 at end of Phase 1)
- 96% coverage on `session/`, `scene/`, `resolution/` combined

### Unchanged
- Phase 1 attack pipeline (to-hit, damage, defense, knockback, status). The
  107 Phase-1 tests remain green throughout the Phase 2 work.

## 0.1.0 — Phase 1
Initial attack resolution engine.
