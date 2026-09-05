# Changelog

## 0.11.0 — 2026-09-05

**The Objects Table has one home, and it is not here.** Requires
`kirby-terrain>=0.1.0`.

### Changed

`kirby_combat.breakables.object_table` is DELETED. `OBJECT_DURABILITY` and
`ObjectDurability` are still importable from `kirby_combat` exactly as before —
they are now re-exported from `kirby-terrain`, the dependency-free leaf that
owns what terrain IS.

**Migration: none for supported callers.** `from kirby_combat import
OBJECT_DURABILITY` is unchanged. Only the deep path
`kirby_combat.breakables.object_table` is gone, and `tests/test_import_surface.py`
has always said anything outside `__all__` is internal.

The table was added here on 2026-09-04 and moved out a day later, which is
worth explaining rather than hiding: it belongs beside the geometry and object
model that describe terrain, not inside the engine that fights on it. A
transcribed rulebook table with two homes is exactly the drift this codebase
has a history of — "5 STR to the die" once lived in three places across two
repositories, agreeing only by luck.

`tests/breakables/test_object_table.py` no longer tests the table's contents;
kirby-terrain's suite pins all 18 rows against the book. It now tests IDENTITY —
that this package's name and kirby-terrain's name are the same object — plus a
guard that fails if a second definition ever reappears here.

## 0.10.0 — 2026-09-04

**The dice moved out.** `kirby_combat.dice` is gone; the roller now ships as
the standalone [`kirby-dice`](https://github.com/pdbethke/kirby-dice) package,
item 6 of the carve-out program. Requires `kirby-dice>=0.1.0`.

### Removed — BREAKING

`kirby_combat.dice` no longer exists, and `DiceRoller`, `RandomRoller` and
`FakeRoller` are no longer re-exported from `kirby_combat`.

**Migration:** `from kirby_combat.dice import RandomRoller` becomes
`from kirby_dice import RandomRoller`. Nothing else changes — same classes,
same behaviour.

There is deliberately **no compatibility shim**. A re-export would leave two
names for one thing, and a consumer that kept using the old one would go on
depending on this package for something it no longer owns.

The extraction is not about size — the package is under 100 lines. It is
about what a dice module is for. Bill Bame's attribution, missing entirely
until 2026-08-28, now has a module of its own and a release guard that fails
the build if it ever stops shipping. And "here is the RNG, here are its
fairness tests, here is the seed" is something a standalone package can be
and a private helper inside a combat engine cannot.

### Removed — BREAKING, and unrelated to the move

`roll_half_die()` is gone from `DiceRoller`, `RandomRoller` and `FakeRoller`,
along with `FakeRoller(half_die_results=...)`.

It had **no callers anywhere** — not in this package, not in kirby-api. Half
dice are, and always were, resolved elsewhere: the caller rolls one extra whole
d6 and `resolution/damage.py` reads the last value of the batch, converting it
to `STUN += raw // 2` and `BODY += 1 if raw >= 5`. The two definitions did not
agree — `roll_half_die` mapped 1-2 to 1, 3-4 to 2, 5-6 to 3, a different
distribution entirely — so anyone who reached for the obvious-looking API would
have silently changed damage. This is exactly the second-copy-of-the-arithmetic
problem `tests/test_dice_have_one_source.py` exists to prevent; it slipped
through because the duplicate lived inside the dice package rather than being
compared against kirby-cost.

Nothing to migrate: no caller existed. The live path is unchanged.

### Added

`RandomRoller.seed` — the seed the roller rolls from, always a real number.

An unseeded `RandomRoller()` used to draw from OS entropy, so the seed never
existed as a value and a fight could not be replayed once fought. It now
chooses its own seed with `secrets.randbits(64)` (unguessable, so recordable
does not mean predictable) and hands it back. Record `roller.seed` alongside a
fight and `RandomRoller(seed=<recorded>)` reproduces it die for die.

`tests/test_dice_fairness.py` — 20 seeded, deterministic tests the roller has
never had: chi-square uniformity over 60,000 rolls, independence of consecutive
rolls across all 36 ordered pairs, mean within five sigma of 3.5, range and
face coverage, and the seed-replay property above. Two of them guard the
guards: a loaded die must trip the uniformity assertion, and unseeded rollers
must not all share one seed.

The dice package went from 82% to **100%** coverage before moving out;
`roller.py` was the worst-covered file in the engine at 71%, and the gap was
entirely the dead method. All of that work — the fairness suite, the seed,
the 100% — travelled with the package to kirby-dice 0.1.0.

Suite here: 1404 passed (the 28 dice tests now live in kirby-dice).

## 0.9.0 — 2026-09-02

**Combat now fights the character on the sheet.** It read the CHARACTERISTICS
section alone, so every characteristic bought as a POWER was invisible to it.
Requires kirby-cost >= 0.6.0.

### Changed — this moves numbers, for 325 of 794 corpus characters

`combat_stats()` reads the TEMPORAL characteristic (base plus whatever is
currently applying) instead of the base sheet value. Measured across the whole
corpus, main vs this release:

| | characters |
|---|---|
| identical | 469 |
| changed | 325 |
| unexplained | **0** |

Of the 325: **319** buy a characteristic as a power that HD counts toward the
total (`AFFECTS_TOTAL="Yes"`) — Gorgon fought at PD 15 where his sheet says 35
— and **6** carry purchases limited to their Hero identity (6E1 p.386), which
combat had been ignoring entirely. White Wolf fought as a civilian: DEX 10
instead of 25, SPD 2 instead of 6. Ravel goes from SPD 2 to SPD 5.

Every mover was classified; none is unaccounted for. A character with no
characteristic-granting powers and no conditional purchases is byte-identical.

### Added
- **Identity is combat state.** `HeroCombatState.in_hero_id` (default True — a
  character in a fight is in costume unless someone says otherwise), on the
  wire in both directions, so a recorded fight knows which identity it was
  fought in.
- **Pushing** (6E2 p135-136), as a temporal contribution: 1 END per Character
  Point Pushed. It needed nothing beyond declaring a `Contribution`, which is
  what the design was meant to demonstrate.
- Drains and Aids are `Contribution`s weighed in the same list as a
  character's own purchases, rather than deltas subtracted afterwards.

### Fixed
- **A slot fights with the modifiers its pool carries.** `_has_modifier` /
  `_modifier_levels` were a flat scan doing neither recursion into containers
  nor inheritance from an enclosing purchase, so ARMORPIERCING, PENETRATING,
  HARDENED, IMPENETRABLE and DOESBODY were all under-reported for any power
  inside a Power Framework. Both now delegate to `kirby_cost.model.modifiers`.
- **A Drain is applied once across a snapshot round trip.** The snapshot
  recorded already-drained stats alongside the drains dict, and rehydration
  applied them again: Ravel read DEX 15 live and 11 after a round trip. Since
  replay folds forward from a captured snapshot, every recorded fight
  containing a Drain replayed with wrong numbers. Snapshots written before this
  release still replay — the pre-adjustment value is reconstructed by adding
  the recorded adjustment back.
- **rPD/rED track CURRENT PD/ED** rather than a frozen quantity of points
  (6E1 p149: an Advantage bought for a character's PD or ED applies to that PD
  or ED). An Aid on PD now raises rPD; the purchased ceiling still binds.

### Performance
- `combat_stats()` prices the stat block from ONE walk of the purchases instead
  of one per characteristic: **1.53 ms → 0.138 ms**, and 3.00 → 0.281 ms with a
  Drain active. Nothing is cached — Drains, Aids and identity flips have to
  compose live — the walk is simply paid once.

## 0.8.1 — 2026-08-31

### Fixed
- **`resolve_move_strike` no longer loses every leap-strike onto an elevated
  target to a fall.** The composite aims the close at a point one Reach short
  of the target; when the target stands on a rooftop that point hangs in the
  air beside the roof. The mid-air retry that exists precisely for this case
  — re-running the close at the target's own, supported square — was gated on
  the short-of attempt having been REFUSED or landed out of reach. A leap to
  that mid-air point is neither: it is within both the horizontal and the
  vertical capacity and it does arrive in reach, so `movement_reach` reports
  it reachable and simply attaches a fall. The retry therefore never fired,
  the phase was spent falling, and `reason="fell"` came back instead of a
  `StrikePlan`. The retry now fires whenever the short-of attempt was not
  clean — refused, short, OR fallen — since falling is what an unsupported
  destination looks like from outside `movement_reach`. This restores the
  pre-migration kirby-api behaviour, which retried when the point one metre
  short was unsupported.
- **A retry is a rescue, never a replacement.** The retried close is adopted
  only when it is itself clean (reachable, no fall, arrives in reach); a
  retry that is refused, lands short, or falls in turn leaves the original
  outcome standing. So no actor collects a strike it did not earn, and a
  genuine fall that no retry can lift is still reported as `reason="fell"`
  with `fell=True`, from the landing its own close produced.

## 0.8.0 — 2026-08-31

The reach rule as a first-class engine surface, and the close-and-strike
composite that consumes it.

### Changed
- **BEHAVIOUR CHANGE — base Hand-To-Hand Reach corrected from 2m to 1m
  (6E2 p56, 6E2 p40, 6E1 p231).** 6E2 p56 sets a character's base Reach at
  one metre, not two; 6E2 p40's Range Modifier table and 6E1 p231 corroborate
  the same boundary. Any consumer that measured HTH range against the old 2m
  figure — including anything that inferred adjacency from distance — will
  see melee reach halved after this upgrade. `hero_view._base_reach_m`
  still adds 1m per level of Stretching on top of the corrected base.

### Added
- **The reach rule as an engine surface (`kirby_combat/actions/reach.py`,
  6E2 p56).** `within_reach(distance_m, reach_m)` applies the rule to a
  measured distance and returns a `ReachVerdict` — `in_reach`, `distance_m`,
  `reach_m`, and `shortfall_m` — rather than a bare bool, so a failed close
  can say how short it fell instead of failing silently. 6E2 p36 gives the
  same boundary from the other side (combat outside Reach is Ranged Combat);
  6E2 p40's Range Modifier table gives the reach band its own row.
- **Close-and-strike composite (`kirby_combat/actions/move_strike.py`,
  6E2 p56).** `resolve_move_strike(...)` returns a `MoveStrikeOutcome` built
  from a `StrikePlan`, and settles, in order: (1) the close, resolved through
  the scene-aware `movement_reach` path so per-mode legality holds (running
  is same-elevation only, leaping has a vertical capacity, flight is free
  3D, and an illegal or over-long move clamps short rather than failing
  loudly); (2) the reach rule from this release, applied at the LANDING
  position rather than the position the action was chosen from — the check
  whose earlier absence let a martial throw resolve between combatants six
  metres apart in elevation; (3) refusal of a free strike when the close
  itself was refused (an unmodelled mode, a mode that cannot operate here, a
  Stunned combatant); (4) perception, gated at the landing position too, so
  an attacker who closed but still cannot perceive the target strikes blind
  per 6E2 p9/p127 rather than at full CV. With `scene=None` the close falls
  back to a straight line clamped to the movement budget and `mode` is
  ignored — no elevation, walls, or support are modelled in that path; only
  the reach rule still bites.

## 0.7.0 — 2026-08-28

The sense-affecting family, Presence Attack consequences, and a front door.

### Added
- **Inability to sense an opponent (6E2 p.9 / p.127)** — the CV penalty is
  now real, and it is PER-OPPONENT. `cv_modifiers` grew a second seam for
  opponent-dependent conditions plus an additive `*_delta` channel, because
  6E2 p.9's mitigated case is a flat -1 DCV that no factor can express.
  `effective_dcv/ocv/dmcv_for` take optional `against=` / `combat_type=`;
  omitting them returns exactly the previous behaviour.
- **`kirby_combat/sense_penalties.py`** — owns that rule, the
  Targeting/Nontargeting distinction, and the Nontargeting PER Roll that
  mitigates it (a Half Phase Action, expiring at the holder's next Phase via
  a driver call, following `HeldAction`'s precedent).
- **Darkness (`actions/darkness.py`, 6E1 p.188)** — an Attack Roll against
  DCV 3 places a field that is impenetrable, not merely harder to see
  through; Nightvision does not help. Converges on the same CV predicate as
  Flash rather than reimplementing it. One zone per Sense Group.
- **Images (`actions/images.py`, 6E1 p.238-239)** — placement at DCV 3,
  Line-Of-Sight perception, and disbelief tracked PER OBSERVER. A spotted
  Image does not disappear. Built by composing existing primitives against a
  point, so a Sight Image is correctly imperceptible inside a Sight Darkness
  with no special case.
- **Presence Attack consequences (6E2 p.138-139)** — a landed PA now costs
  the target something. Five tiers with `yields` / `half_phase` /
  `no_action` / DCV factor, held forward via `PresenceApplied` /
  `PresenceFaded` and folded in `session/effects.py`. `IN_COMBAT_DICE_MODIFIER`
  and `STUNNED_IMMUNE_REASON` moved in from a consumer.
- **A public API.** `__all__` went from 3 names to 80, covering the whole
  measured consumer surface, pinned by `tests/test_public_api.py`. Purely
  additive: every deep import path still works.
- **`examples/raw_orion.py`** — 6E2 p.9's worked example, asserted.
- Attribution for **Bill Bame**, whose work the dice roller is based on in
  part. It was missing entirely.

### Fixed
- `Flash.modifiers` reported a blinded character after a Flash to ANY Sense
  Group, including Hearing. 6E2 p.9 counts only TARGETING Senses. Superseded
  rather than deleted; the new predicate reads the character's real senses.
- Presence Attack durations were 12/24/36/48/60 segments, preserving only
  the book's ordering. 6E2 p.18 gives a Turn as 12 seconds and 12 Segments,
  so they convert exactly: 12/60/300/1200/3600 — up to 60x longer.
- `perception.per_roll_target` raised `AttributeError` for any
  `StatBlockCombatant`, having read `observer.hero` unconditionally.
- The inability-to-sense rule silently did nothing for `StatBlockCombatant`,
  which has no `senses()` — i.e. for every example script and much of the
  suite. Now falls back to 6E2 p.9's normal human.
- `_fold_cv_factors`'s "a 0.0 factor applies last" branch had no producer and
  was untested by construction. It now has two.

### Notes
- **0.4.0, 0.5.0 and 0.6.0 have no entries in this file.** They shipped
  without them; the gap is recorded rather than reconstructed from memory.
  0.6.0 was published by local twine rather than by tag, so the `v0.6.0` tag
  does not mark its contents.


## 0.3.0 — 2026-04-25

Phase 2 Plan 2 (engine advanced). Tier-4 parallel systems for mental
combat, vehicles, mass combat, breakables, presence attacks, GM tooling
engine layer, and full session serialization round-trip.

### Added
- Mental combat pipeline (OMCV vs DMCV, no range/LoS gating per 6E1 p105)
- Mind Control with degree ladder (ego_push / simple / contrary / violent)
  and EGO Roll breakout per 6E1 p101
- Telepathy with degree ladder (surface_thoughts / specific_memories /
  deep_thoughts / subconscious) and mental-awareness gating per 6E1 p116
- Mental Illusion with degree ladder + disbelief mechanics per 6E1 p109
- Mental Blast (STUN-only, vs Mental Defense, no BODY/KB) per 6E1 p105
- Mental Entangle (Works Against EGO + Mental Paralysis variant)
  with EGO-based escape
- Vehicles (Combatant subtype, HDC-shaped) with size, movement_inches,
  passengers, capacity-by-size table
- Passenger mechanics: cover from vehicle, firing ports, shared fate on
  vehicle destruction, rescue from crashed vehicle
- Ramming (extreme move-through): DC = round(SIZE * v / 12); +1 DC at
  >60 m/seg; attacker takes half DC self-damage per 6E Vehicles p33
- Driving rolls and maneuvers (STRAIGHT/SHARP_TURN/SWERVE/BOOTLEG_TURN/
  BARREL_ROLL); terrain and velocity modifiers
- Mass combat: Unit (pack-of-N), morale ladder
  (FRESH/STEADY/SHAKEN/ROUTING/BROKEN), aggregate damage / count loss,
  25%-casualty morale check
- Aggregate resolution: attack_vs_unit, aoe_vs_unit, attack_vs_individual,
  unit_attack_dc_bonus
- Breakables: ObjectCombatant with material defaults
  (paper/glass/wood/stone/metal/steel/concrete) and hdc_source_xml field
- Structure integrity cascade: load-bearing destruction propagates via
  StructuralGraph; combatants on collapsed surfaces flagged for falling
- Presence attacks: PRE/5 base dice + situational bonus, less PRE Defense;
  effects ladder (no_effect / hesitation / impressed / fear / cower)
  per 6E2 p139
- GM tooling engine layer:
  - Tier 1 overrides (stun adjust, status apply) — no justification
  - Tier 2 overrides (dice override, retroactive abort) — justification REQUIRED
  - Tier 3 overrides (spawn/despawn, scene mutation) — justification REQUIRED
- GM attack-on-behalf-of mechanics (NPC actions or absent-PC actions
  authored by the GM, flowing through normal pipeline)
- Combatant spawn/despawn mid-session via Tier 3 GMOverride; spawning in
  an active segment skips the immediate phase
- Serialization: to_dict (JSON-safe with __type__ discriminator) and
  from_dict (type-dispatched, subclass-preserving) with round-trip parity
  tests (representative events, every CombatEvent subclass, hypothesis
  property test on Combatant, complex Scene, Vehicle with passengers,
  Unit with morale Enum)

### HDC round-trip compatibility
- Vehicle, ObjectCombatant carry HDC-source-preserving fields for Plan 3
  import/export. Vehicle's field shape mirrors HDC vehicle XML (NAME,
  SIZE, BODY, DEF, PD, ED, STUN, SPD, DEX, STR, MOVEMENT).

### Fixed
- `from_dict` now skips `init=False` fields (events have init=False `kind`
  Literal) and resolves forward-ref string field types via the type
  registry (handles `Unit.morale -> UnitMorale` enum coercion).

### Tests
- 569 passing (up from 450 at end of Plan 1)
- 96% line coverage across `kirby_combat/`
- All new subsystems >85% (most >93%)

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
