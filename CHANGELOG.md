# Changelog

## 0.18.5 — 2026-09-18

**Positions and statuses are in the log, and the one-writer gate covers
them.** Task A7 made a fighter's vitals fold only through `apply_event`.
Two fields were left outside it, and Krackle's checkpoint gate — a replay
of recorded fights against this engine's own `state?at` — measured both.

*Where a man stands.* `apply_event` treated `MovementResolved` as
log-only while `scene/placement.py::commit_move` wrote the landing onto
`scene.combatant_positions` in place beside it. A session rebuilt from
its rows — and therefore `state_view` and `rewind_to_sequence` — put
every fighter at his starting placement for ever: all fourteen
checkpoints of a recorded fight had Wyatt at (3.1, 3.7) although he moved
at sequence 7. `apply_event` folds the row now and `commit_move` writes
nothing, so the live path and the replayed path move a man in the same
one place. `rewind_to_sequence` seeded its fresh session from the
FINISHED Scene, which is the same defect from the other end — a rewind to
sequence 1 showed the fight's last placement — so `CombatSession` carries
`initial_scene`, the board as the fight found it, exactly as it already
carried `initial_combatants`.

*What condition he is in.* Nothing in this engine ever emitted a
`StatusEffectsChanged`: its only door,
`status_emission.apply_event_with_deltas`, had no caller anywhere, and
`StatusChanged` had no producer at all. Knocked out, stunned, prone,
held, entangled, flashed — none of it reached the log, so a viewer
reading the rows could not know a man had gone down.
`status_emission.record_status_changes` is the one emitter now: it diffs
the RULE (`statuses.statuses_for`) against the RECORD
(`CombatSession.statuses`, folded by `apply_event` out of these rows) and
writes down what moved. `run_phase` — this engine's one step door —
calls it on every exit, so the rows are among the events a Phase hands
back. `session/state_view.py` reads the folded record rather than
deriving a second answer.

*The gate.* `tests/session/test_apply_is_the_only_writer.py` (renamed
from `..._of_vitals.py`) walks the engine by AST for two more properties:
nothing outside the fold decides where a combatant is standing, and
nothing outside it writes `CombatSession.statuses`. The placement gate is
keyed PER ROUTE rather than per file — mutating a position map, calling
`place_combatant`, building a board with `replace(..., combatant_positions=)`,
and installing one with `replace(..., scene=)` are four separate
allow-lists — so a module that may bring a wall down is not thereby
allowed to move a fighter. Both gates carry their own negative controls
and assert their allow-lists whole.

**Wire changes.**

* `MovementResolved.from_pos` and `.to_pos` now carry `facing` alongside
  `x`/`y`/`z` — the four numbers `scene.Position` holds. Facing was
  dropped on the wire, so a replay could put a man on the right spot
  pointing the wrong way, which a board draws.
* `StatusChanged` is **deleted**. It was a scalar `from_status`/
  `to_status` pair standing beside `StatusEffectsChanged` with no
  producer anywhere in the engine and exactly one consumer — Prone's
  clear edge in `statuses._is_prone`, which now reads `PRONE` in a
  `StatusEffectsChanged.removed`. A combatant getting to his feet is
  still a consumer's explicit act. The event union is 29 kinds, and
  `kirby_combat/schema/events.json` is regenerated.
* `CombatSession` gains `initial_scene` and `statuses`. A session built
  with events already on it, a Scene, and no `initial_scene` raises —
  the same refusal `initial_combatants` already makes, for the same
  reason.
* `Scene` gains `snapshot()` (the board as it stands, positions copied)
  and `with_position()` (the what-if board). `move_strike` and `Images`
  both built an altered board themselves — one through
  `dataclasses.replace`, one through a hand-rolled `__slots__` proxy —
  and now ask the Scene, which is where the position map lives.
* `status_emission.apply_event_with_deltas` is **deleted** and replaced
  by `record_status_changes`. The pure diff `status_deltas` is unchanged.

## 0.18.4 — 2026-09-18

**The scene is in the published schema.** A viewer that renders a fight's
map has always hand-written its geometry types against `to_dict(scene)`'s
shape, and it drifted in five places: `Wall.segment` read as `start`/`end`
rather than two `Position` objects, a polygon read as flat coordinates
rather than `[x, y]` pairs, `elevation_range_m` missed entirely, a
hazard's `effect` read as a scalar rather than the object it is, and
`ambient.light_level` missed too. `serialization.json_schema()` now walks
`Scene` the same way it already walks `SessionStateView` — `Wall`,
`Surface`, `Hazard`, `HazardEffect`, `Furnishing`, `Construct`,
`ConstructEffect`, `AmbientConditions`, `SceneBounds` and `Position` all
get `$defs`, derived from `scene/` as authored, not retyped by hand.
`Scene.encounter` is the one field walked out on purpose — it types as
the full internal fight (`Encounter.sessions: list[CombatSession]`) that
`SessionStateView` already publishes as its own flat projection, and
walking it here would grow a second, un-flattened copy of that same
graph. Added to `FREE_FORM_PAYLOADS` for that reason, next to the four
`Any` payload bags it now sits beside.

## 0.18.3 — 2026-09-18

State view carries `spd`/`dex` (and `max_*`) as build facts. Krackle's SPD
ribbon and DEX ordering need SPD and DEX; they are bought-on-the-sheet build
facts, like `invisible`, not folds of the log — so `CombatantStateView` now
carries `spd: int` and `dex: int`, read through `combat_stats()`, the one
door every characteristic already goes through. `max_stun`/`max_body`/
`max_end` were checked and were already there, read the same way. No default:
a combatant with no SPD raises, same as every other characteristic.

## 0.18.2 — 2026-09-18

**A viewer generates its event types from the engine, and checks its fold
against the engine's.** A consumer that renders these fights has always
hand-written the event shapes, which is a copy of a contract nothing checks —
the same defect this package's own type registry had when six of twenty-eight
events could be written and never read back. `serialization.json_schema()`
walks `EVENT_CLASSES`, which is `get_args(CombatEvent)` — the union itself,
and the same derivation the registry and the round-trip gate read — and emits
a 2020-12 JSON Schema document: a top-level `oneOf` over one `$def` per event
kind, each pinning `kind` to a `const`, so a generator on the other side turns
it into a union an exhaustive switch narrows. It describes the WIRE `to_dict`
writes, not the Python behind it: `__type__` on every object, an ISO
`date-time` string for a `datetime`, an array for a tuple or a set. A field
whose type has no JSON Schema meaning RAISES rather than being skipped — a
field quietly left out is a field the consumer discovers is missing by reading
it off a real row.

**The state a viewer checks itself against.** `state_view(session)` publishes
the shape `rewind_to_sequence` exposes: the clock, the status, the last
sequence on the log, whose Phase is next, and for each fighter his vitals,
where he stands and which way he faces, what condition he is in, whether his
build carries Invisibility, and who he can perceive. NOTHING ON IT IS A NEW
RULE. Every field is read through a door this engine already had —
`classify_health`, `is_down`, `Side.of`, `position_of`, `statuses_for`,
`concealment.is_invisible`, `concealment.perceives` and `next_actor_id` — so a
viewer's fold can be compared against the engine's field by field instead of
trusted. In particular a viewer's fog is now the engine's own answer rather
than the viewer's opinion about who sees whom, which used to fail OPEN and
show everyone.

**`perceives` goes through `concealment.perceives`, which is the one door.**
That function is documented as the one place the log's hiding and the build's
Invisibility are handed to `perception.perceive` together, "so callers do not
each assemble the arguments and each forget a different one" — and it now
carries the observer's Flash and the normal-human grounding for a flat stat
block as well, which a caller reaching it still had to remember on its own.
`sense_penalties.cannot_perceive` reaches `perceive` without the concealment
arguments at all, so it does not fold Invisibility even partly: the power is
skipped entirely. A view built on it would have published an Invisible fighter
as seen by every enemy on the board while claiming to be the engine's answer.
So what `perceives` folds, exactly: a Flash on the observer's Sense Group, a
Darkness field on the ray, the target's Invisibility, a Hidden target's
opposed Stealth contest, and the walls. It is NOT always a read — `perceive`
rolls for an Invisible target's Fringe within 2 m and for a Hidden target's
Stealth contest, and those two pair kinds are a roll rather than a projection.
Invisibility is not side-aware in 6E and is not made so here: an ally is as
blind to it as an enemy.

**Being unseen is published PAIRWISE and nowhere else.** `perceives` is per
observer, which is the granularity the engine's own Hide contest resolves at —
"being unseen is not a property of the hider: one enemy may lose you while
another keeps you in view". There is deliberately no flattened `hidden` flag
beside it: a global "unseen by somebody" would answer the same question at a
second granularity and a consumer could not recover the pairwise truth. What
IS published per combatant is `invisible`, the build fact, which is true of
the character rather than of a pair.

**`state_view(session, *, roller)` — the roller is required and has no
default, because this is a playback surface.** Two reads of the same sequence
must agree, and `perceive` builds its own `RandomRoller` when handed none, so a
view that seeded itself would answer differently every call for the two rolled
pair kinds and a replay would not replay. The caller supplies the roller —
derived from the sequence it is asking about, if it wants the same board
twice — and a caller that has not thought about it gets a `TypeError` rather
than a silent reseed. `concealment.perceives` takes the roller through for the
same reason and likewise defaults nothing.

A combatant who is not on the map reads `position: None`, never the origin,
which would put an absent man adjacent to whoever stands at (0, 0, 0).

The derived document is committed and shipped: `kirby_combat/schema/events.json`
is carried in the wheel, `python -m kirby_combat.schema` prints it, and
`tests/serialization/test_json_schema.py` fails if the file and the derivation
disagree in shape. The version stamped on the document is checked against
`pyproject.toml`'s `[project] version` rather than against the environment
that generated it — an artefact derived from a stale editable install carries
the wrong version, and comparing it against that same environment would agree
whenever both were wrong. `scripts/check_release.py` repeats the check against
the built wheel, at the last door before publication. The document's `$id` is
a URN, not a URL: a standalone library does not name a deployment host it
knows nothing about. `json_schema`, `state_view`, `SessionStateView`, `CombatantStateView`
and `PositionView` are on the import surface, demonstrated by
`examples/the_schema_a_viewer_generates_from.py`.

**THIS RELEASE IS THE SCHEMA AND THE STATE VIEW, AND NOTHING ELSE.** The
harness follow-ons under discussion — a situation on `PhaseResult`, the
session-ended event's shape, a public event base class and a progress
predicate — are deliberately NOT here; they are a separate release, so nothing
downstream waits on them.

## 0.18.1 — 2026-09-17

**A round-tripped combatant can fight.** `serialization/to_dict` projects a
`HeroCombatant` to a flat snapshot and `from_dict` rebuilds it around a stub
hero with no powers, no skills, no martial arts and no equipment — and every
view on `HeroCombatant` is derived from exactly those. `attacks` walks
`hero.powers` and `hero.equipment`; `csls` walks `hero.skills`;
`defense_view`, `senses`, `movement_view`, `maneuver_view`, `framework_view`,
`is_mentalist`, `has_combat_sense`, `has_self_contained_breathing` and
`skill_roll_value` each walk one of them. So a rebuilt combatant reported
NOTHING through any of them: measured on the kirby-api harness, Drago's three
RKAs went in and none came back, and a rebuilt fight did no damage. It also
came back on no side — `side` was never written to the wire at all, so a
rebuilt roster was a free-for-all in which the two men who had been allies now
had to kill each other.

The code meant to prevent this assigned `_snapshot_override_attacks` and
`_snapshot_override_defenses`, which nothing in the engine ever read, and
monkeypatched `combat_stats` onto the instance, which `dataclasses.replace`
drops — so a rebuilt combatant also lost its resistant defenses the first time
it spent a point of END.

Replaced with ONE door: `hero_view.CombatantSnapshot` holds every derived
view, `CombatantSnapshot.of(live)` records them off a live combatant, and each
view returns the recorded value when a snapshot is present. The resolvers are
untouched and unaware — they go on reading `c.attacks`, `c.csls`, `c.senses()`
and see the same values either way. Everything hanging off `state` stays live:
STUN, BODY, END, statuses, and Drains and Aids on characteristics, which
`combat_stats` goes on applying. `skill_roll_value` now reads a new
`skill_rolls()`; `can_swim` now reads a new `swimming_m()`, so the
`cannot_swim` status stays live on a rebuilt man rather than being frozen into
the verdict.

**BREAKING (wire format).** A combatant snapshot must now carry its views.
`from_dict` raises `ValueError` naming the missing keys on a snapshot recorded
by 0.18.0 or earlier, rather than rebuilding a man who does nothing — an empty
`attacks` list is a legal combatant, which is why nothing complained. Re-record
such a combatant from the canonical character with `HeroCombatant.from_build`.

**`PresenceActionLost` can be read back off the wire.** It is a `_BaseEvent`
subclass that `pre_attacks/presence_effects.py` emits and `apply_event` folds,
and it was absent from the `CombatEvent` union — so the registry `from_dict`
derives from the union never knew the name, and a fight in which a Presence
Attack cost a man his Phase could be written and never read back
(`unknown type 'PresenceActionLost'`). Same shape as the six `VitalsChanged`
was in, one level up: `EVENT_CLASSES` guards the registry against the union
and could not guard the union against the classes. The round-trip gate now
DERIVES its set as every `_BaseEvent` subclass the events module declares, so
the union, the registry and the folder cannot disagree again.

Fixture fix, found by the new gate: `_SyntheticCombatant` shadowed the
`defenses` property while the base `defenses` *is* `defense_view()`, so a
synthetic combatant answered `[Vest]` through one door and `[]` through the
other. It overrides `defense_view` now.

Known, and left as a strict xfail rather than papered over:
`enumeration.enumerate_actions` reaches past the combatant's public surface
into `actor.hero` at 21 sites (it says so in its own comment), so a rebuilt
corpus character's menu loses the actions read straight off HEALING and AID
powers — for which no view on `HeroCombatant` exists. The combatant itself
round-trips; this is a second door in the enumerator.

## 0.18.0 — 2026-09-17

**Mental Defense applies to mental attacks.** `resolution/defense.py`'s
`_DEFENSE_MAP` had `"md"` and no `"mental"`, while `hero_view` returns
`"mental"` for any power whose build says `DEFENSE="MENTAL"` — so every mental
attack fell through to the unknown-type branch, which returned a
`DefenseProfile` of all zeroes, and a Mental Blast took full damage against any
Mental Defense at all. Both spellings now resolve to the target's MD (6E2's
Mental Combat; Mental Defense still does not apply against physical or energy
attacks, which is why it is its own row). An unrecognised `defense_type` now
RAISES instead of silently applying no defense: an all-zero profile with a line
in the audit is how this defect survived with no test failing.

`CombatSession` built with events already on it and no `initial_combatants`
raises. The combatants such a session holds are the men the fight *left*, and
`rewind_to_sequence` replays into the men it *found* — inferring one from the
other is a guess that silently makes every later rewind return a session more
hurt than the fight ever got. A session with an empty log still infers: it has
not been in a fight.

**`PhaseResult.events` is every event the call wrote.** It was assembled from
the sub-calls — the skips, the resolver's events, the spend — and the clock's
events were not among them: `ActingOrderResolved` (from `Encounter.run_segment`),
`SegmentAdvanced` (from `advance_segment`) and the free Post-Segment 12
`RecoveryTaken` all went into the log and none came back. A consumer persists
what it is handed, so its own log had holes; measured over eight Phases, four
steps lost events outright, one returned three of its nine, and replaying what
had been persisted raised `event sequence mismatch: expected 2, got 3` on the
second step. `run_phase` records the log length at entry and returns the tail at
exit — one measurement, not a second account of the Phase that can disagree with
the record.

**A Block's "acts first" is in the record.** 6E2 p.60's priority — a successful
blocker acts before that attacker in the next Segment they share, "even if [the
attacker] does not attack again" — was carried on `Encounter.acts_first`, a
field, and by no event at all. It was the last piece of fight state a consumer
could not rebuild: rehydrating the Encounter from a session's own timeline
between steps left the mapping empty, so the blocker won his Block in the live
fight and lost his priority in the replayed one. `BlockPriorityGained` now
carries it, `apply_event` folds it onto `Timeline.block_priority`, and
`Encounter.run_segment` reads it from there (`Encounter.acts_first` remains an
explicit override, merged on top; `carried_block_priority()` is the one
reading). The SPEND needs no event: an `ActingOrderResolved` containing both men
*is* the shared Segment the rule names, so `apply_event` drops the entry when it
applies that order.

**No row is edited after it is applied.** The Trip resolver (6E2 p.67) ran its
attack through `apply_event` and then `dataclasses.replace`d the payload on
`event_log[-1]` to stamp `kind="trip"`, the house-rule Acrobatics save and
`is_prone_after`. A consumer that persists rows as they are emitted stored the
row *before* that edit, `statuses._is_prone` folds exactly those keys, and the
replayed fight had a man standing whom the live fight had prone.
`resolve_attack_in_session` takes a `payload_extras` callback — called with the
finished `AttackResult`, merged into the payload *before* the `ActionResolved`
is built — so a maneuver labels its own row without ever reaching back into the
log. A test walks the engine by AST and fails on any index-assignment into an
event log or any `replace(..., event_log=...)` outside `session/apply.py` and
`session/rewind.py`; it flags the old resolver verbatim.

**Every event deserialises, because the union says so.** `from_dict`'s type
registry and `tests/serialization/test_roundtrip.py`'s coverage gate each kept a
hand-written list of event classes, and both went stale together: six of the
twenty-eight — `VitalsChanged`, `BleedingSuffered`, `PresenceApplied`,
`PresenceFaded`, `ConstructDamaged`, `ConstructSpawned` — were unregistered, so
`from_dict(to_dict(e))` raised `TypeError: unknown type` on the row that now
carries every point of STUN, BODY and END. A consumer persisting rows as JSON
could not replay one point of damage. Both now read
`kirby_combat.session.events.EVENT_CLASSES`, which is `get_args(CombatEvent)`;
the gate is parametrised over it and compares field by field, with a negative
control that a class outside the union does not round-trip.
`EVENT_KINDS` maps a `kind` string to its class. One real bug fell out of the
derived gate: a `tuple[int, ...]` field (`BleedingSuffered.dice`, 6E2 p.115)
came back as a list.

**One door steps a fight.** `run_phase` now takes the `Encounter` and owns the
clock as well as the Phase:

```python
run_phase(encounter, chooser, *, roller,
          on_unresolvable="raise", campaign=None, until=None) -> PhaseResult
```

It resolves the Segment's acting order when the fight is carrying none, and
when the order is spent it advances the Segment (and the Turn, and with it 6E2
p.131's free Post-Segment 12 Recovery, p.109's bleeding, the Adjustment fade
and `SegmentAdvanced`) until it finds a Segment somebody can act in. The
template is resolved from the Encounter and the campaign, so the `template=`
argument is gone; `roller` serves both the resolvers and 6E2 p.21's
zero-argument tie-break. `PhaseResult.encounter` carries the fight forward and
`PhaseResult.session` is a view of it.

`actor_id is None` now means ONE thing: the fight is decided by `until`
(default: last side standing), and nothing further is emitted. It used to also
mean "this Segment is spent, advance it yourself" — so a consumer stepping a
fight one Phase at a time could not finish one, and `run_encounter` held a
second copy of the advance. `run_encounter` is now a loop over `run_phase`
plus the guards a driver owns (`max_turns`, the stalemate counter, the
verdict); a test reads its body by AST to keep it that way. A whole Turn with
no actor and no verdict raises rather than returning quietly.

The stalemate counter now reads the AMOUNT on a `VitalsChanged` /
`RecoveryTaken` / `BleedingSuffered` rather than the kind alone: a man at full
STUN takes a free Recovery of nothing every Turn, and once the advance moved
inside `run_phase` that was resetting the counter every twelve Segments.

**The log rebuilds the fight.** `apply_event` is now the ONLY writer of a
combatant's STUN, BODY and END. Every resolver used to change the combatant
beside the event that described the change — an attack folded its damage onto
`session.combatants` and logged an `ActionResolved` whose payload was a
free-form dict; the END an attack, a move or a Push cost was taken off the
fighter and logged nowhere at all — so a consumer that persists the rows and
rebuilds the fight by replaying them rebuilt a fight in which nobody had been
hit. Measured: two Phases in, a fighter stood at 27 STUN in the fight that ran
and 50 in the fight replayed from its log.

`VitalsChanged(combatant_id, stun, body, end, reason)` is the new typed event
for damage and for an END spend; the deltas are signed and are deltas, not
resulting values. `RecoveryTaken` (6E2 p.130, p.131) and `BleedingSuffered`
(6E2 p.109, p.115) keep their names and their typed fields and are folded by
the same dispatcher — no fold parses a free-form dict. A change addressed to a
combatant the session does not know raises rather than passing in silence, and
an unknown event kind still raises. `vitals.record_vitals_change` is the one
emitter; `vitals.apply_vitals_delta` is now called by `apply_event` alone, and
a test walks the engine by AST to keep it that way.

`CombatSession.initial_combatants` records the men as the fight found them.
`rewind_to_sequence` replays into those rather than into the current
combatants: with a real fold there is no inverse to walk back to, and seeding
a rewind with the men as the fight LEFT them would replay its damage on top of
itself.

**The loop is in the log.** The two decisions the turn loop made in memory and
told nobody about now reach the record: `ActingOrderResolved` (who acts, in
what order, in which Segment — emitted by `Encounter.run_segment`, the one
place an order is resolved) and `PhaseSpent` (a slot consumed — emitted
wherever the loop spends one, including `next_actor_id`'s skip, which moved to
`resolve_next_actor` — asking whose Phase it is no longer changes the fight). The order carries the
declared intents that produced it (6E1 p.116(c)'s Lightning Reflexes election is
enforced off them) and a spend carries a `reason` — `"acted"`, or `"down"` /
`"left"` for a slot its owner was in no condition to use, which the loop used to
consume in silence. `apply_event` restores the acting order, the intents and the
spent flags from them, so a fight rebuilt by replaying its log alone stands where
the original stood, picks the same man to act, and refuses the same
declarations. Before this, a
consumer that persisted only the events could rehydrate a fight and find
nobody able to act.

**One door for health.** `classify_health(combatant) -> "healthy" | "wounded" |
"critical"` (exported from `kirby_combat`) is now the single statement of the
engine's own judgement about how badly hurt a fighter is — half STUN is
wounded, a quarter or any BODY at zero is critical, the same rung the Recover
offer reads. The two tactics that gated on it (`take_cover_when_hurt`,
`reposition_when_spotted`) each held a private copy of the arithmetic; both
copies and their constants are gone. Three more have followed them:
`enumerate_actions`' Recover offer (which alone was written as
`current_stun < max_stun // 2`, so at an odd STUN total it really did disagree
with the percentage the tactics read — 22 of 45 was "wounded" to one and
"healthy" to the other; it asks `health.stun_percent` now and stays on the STUN
rung specifically, because the full ladder also calls a man at 0 BODY critical
and 6E2 p.130 prices a Recovery in STUN and END),
`stand_and_take_it`'s `_STUN_HEALTHY_PCT`, and the
percentage the two hurt-tactics printed in their rationale, which is now
`health.stun_percent` — the number the ladder itself is cut from.

**`Brief.render(..., extra_doctrine=())`.** A caller's own advice for this
fight is appended after the engine's lines, under the same
"What your doctrine says, best first:" heading and at the same indent, and is
governed by exactly the same one-way suppression (`KIRBY_BRIEF_NO_DOCTRINE`, or
`doctrine=False`, removes the extras too). With extras and no doctrine of its
own, the section opens with the extras alone. Nothing else on the page changes.

`CombatTemplate.by_name(name)` resolves a stored template name
(`"6e-superheroic"`, `"6e-heroic"`) and raises `KeyError` naming the known
ones. No default argument: a fight whose rules were lost must not quietly be
run under someone else's.

## 0.17.0 — 2026-09-17

131 commits since 0.16.0 (2026-09-07 to 2026-09-13): 59 features, 62 fixes.
Highlights, from the commit subjects:

- feat: firing into melee — the held man can take the bullet
- feat: a Grab costs both men their DCV
- feat: a grabbed man can struggle — the grapple chain closes
- feat: tactics can measure reach; grappling; a Grab that led nowhere
- feat: doctrine can disarm — and a prop that cost six action kinds
- feat: doctrine stops letting men bleed to death
- feat: a scene can say what may be picked up
- feat: futility grades an attack on TERRAIN too
- feat: grade the decision, not just count it
- feat: the doctrine hint is the caller's call, not a global
- feat: a baseline records WHICH PAGE it measured
- feat: the Brief says what SHAPE the enemy is in

**Breaking:** `refactor!: the engine takes a build, never a file`.

`Brief.render(*, doctrine=...)`: the doctrine-hint section is the caller's call
(kirby-ai 0.2.x depends on this).

## 0.16.0 — 2026-09-07

**The engine can execute what it offers.** Resolvable action kinds go from
**4 to 45 of 51** — and the fights that ran before this release were wrong
in two ways nobody could see.

### Fixed

**The loop never read the Scene, so melee was never gated.** `CombatSession`
has always carried a `scene`, and `run_phase` called `enumerate_actions`
with `has_scene` defaulting to False — so `_melee_gate` returned "direct"
for every enemy and a fight offered strike, grab, disarm and trip
UNCONDITIONALLY. Combatants could punch each other from across the map.
Measured on two fighters and one map: 15 kinds in the void, melee gone at
20m, melee back at 1m.

**Nothing ever wrote a position, so a fight on a map was frozen.**
`movement_reach` decided moves completely — clamped by walls, surfaces and
capacity, with any fall — and `MovementAction.resolve` built its
`MovementResolved` with `from_pos` and `to_pos` **both hardcoded to None**.
`scene.combatant_positions` was read by the range gate, line of sight,
cover and Images placement, and written nowhere outside a test fixture.
Everyone attacked from where they started, forever.

These two hid each other: melee was ungated *and* nobody could close the
distance. Neither raised, because a stationary fight offering illegal melee
is still a valid fight — the same shape as every other defect this
carve-out has surfaced.

**`advance_segment` left a stale acting order behind**, `has_acted` flags
and all, so a Segment 3 order still described Segment 6.

### Added

`kirby_combat.scene.placement` — `commit_move`, `move_toward`,
`position_of`. Its own module on purpose: deciding where someone can go is
a rule, recording that they went there is a different one, and folding the
second into `movement_reach` would make a pure "could I get there?" query
mutate the world.

**41 newly reachable action kinds.** The rules were already written, tested
and correct; what was missing was a caller. `actions/images.py` — 480 lines
— had exactly one importer, its own test file. The engine states the mental
Attack Roll once; the parked driver wrote it out at four separate lines.
Every one of those suites was green the whole time, which is why
`registered_kinds()` is pinned by a test: only that number can tell the
difference between a rule that works and a rule that is reached.

`loop/registry.py` splits into mechanism (the decorator, the dispatch, the
raise) and `loop/resolvers.py` (the work), since the resolver list is what
grows and the dispatch should not.

`perception.images_groups` joins `flash_groups` and `darkness_groups` as
the third occupant of one shape.

### Known limits, stated

- **`AdjustmentFaded` has no emitter anywhere in the engine.** The class
  exists, `apply_event` passes it, `session/effects.py` folds it, and
  nothing constructs one — so an Aid or Drain never fades, where 6E says
  both should at 5 AP per Turn. This predates the wiring; wiring made it
  reachable, which is the first step to fixing it.
- **6 kinds remain unwired, and none is wiring.** `disarm`, `trip` and
  `spread` have no engine rule at all; `coordinate`, `reallocate` and
  `reconfigure_vpp` need machinery that does not exist yet.
- The count is **51**, not 52. `debris` is a Construct kind, not a
  LegalAction kind; an earlier regex over-counted and an AST walk settled
  it.

## 0.15.0 — 2026-09-06

**A Phase can be written down.** The third and last gap between the engine
and a fight it can run alone — damage application and the turn loop closed
the first two in 0.14.0.

### Added

`kirby_combat.Brief` and `kirby_combat.CombatantLine`, with
`PhaseSituation.brief()` as the entry point. A written description of one
Phase: who is acting, what shape they are in, who is standing where, and
what they may legally do.

The equivalent builder in the parked wrapper is 160-odd lines that —
measured 2026-09-06 — touch the database **zero** times. It was already a
pure function of engine state; only its location was wrong.

Two other homes were considered and rejected. `kirby-ai` looked obvious and
is wrong by its own charter: it owns the network hop and the policy around
it, explicitly not content, rules or rows. A module of its own would hold
one class with no second occupant. The engine, meanwhile, already renders
itself to text and always has — `LegalAction.summary` is a readable label
and `Tactic.narrative_summary` is "the one-liner shown to whatever picks
one". A Brief is those, gathered into a page.

It names nothing about what might read it, and `tests/test_vocabulary.py`
enforces that. Same seam as `Chooser`: the engine asks, and never learns
what answered.

Each offer is listed as `[action_id] summary`. The summary is for the
reader; the bracketed token is the contract, and is exactly what
`validate_choice` checks. Enemy numbers are shown as freely as the actor's,
deliberately — the anti-metagaming line in this system is drawn by
PERCEPTION, not by hiding stat blocks from whoever is choosing.

A Brief reads state and changes none.

## 0.14.0 — 2026-09-06

**The engine can run a fight.** Damage lands, the turn loop lives here, and
sides are objects.

### Added

`kirby_combat.loop` — the turn loop (sub-project D of the driver carve-out).
Whose Phase it is (6E2 p.18), who acts first (6E2 p.19-21), when the Turn
wraps and the free Post-Segment 12 Recovery fires (6E2 p.131), and when the
fight is decided (6E1 p.421) are all rules, and every one of them lived in a
web service's driver until now — 258 lines of database-bound "whose Phase is
it" and 38 more of SQL-backed "is it over".

- `Chooser` — the one thing the engine does not decide. `FirstLegalChooser`
  (deterministic, makes the loop testable) and `TacticChooser` (picks by
  `classify_role` and `tactics_for`). A pick outside the menu raises at the
  seat.
- A resolver registry. **52 action kinds are enumerable; 4 are resolvable.**
  An unregistered kind RAISES rather than skipping silently, and
  `registered_kinds()` is pinned by a test — so each resolver that migrates
  out of the parked driver moves a number rather than disappearing into a
  silence. `on_unresolvable="skip"` records the kind; a skip is never
  invisible.
- `run_phase` / `run_encounter`, with `until=` to replace last-side-standing
  and a `max_turns` guard that reports rather than loops.

`kirby_combat.Side` and `kirby_combat.Roster`. A side is an object: `Side.named`
folds case and spacing into one identity, so `"Golden"` and `"golden"` are one
army **by construction** rather than by validation — as strings they made a
fifth army in a four-army battle, changing who won, with nothing to look at.
`side=None` means a side of one, so an N-way free-for-all works under the same
rule as a team battle. `Roster` replaces four module-level helpers that all
took the same session; `Verdict` replaces a `(bool, Side | None)` tuple.

`kirby_combat.apply_vitals_delta` — one fold for every STUN/BODY/END change.

`side` on both combatant shapes.

### Fixed

**`resolve_attack_in_session` now applies its damage.** It computed
`stun_dealt`, recorded it on the event log, and left `current_stun` untouched,
so every consumer subtracted by hand — the parked driver at 15 separate call
sites, none clamping, none handling both combatant shapes. A fight could
resolve one exchange and then repeat it forever against a target that never
got hurt. Nothing is clamped: `is_ko` is `current_stun <= 0`, and 6E reads how
far below zero a character went.

**`advance_segment` left a stale acting order behind.** Each `ActingSlot`
carries the Segment it was resolved for and nothing cleared the list, so a
Segment 3 order — `has_acted` flags and all — still described Segment 6.
Nothing caught it because nothing consumed `acting_order` in a loop; the
driver tracked its cursor in the database. `apply_event` now clears it on
`SegmentAdvanced`.

**`enumerate_actions` crashed with a bare `AttributeError` on a
`StatBlockCombatant`.** It reads `actor.hero` at 21 sites, so it needs a
build-backed combatant — but a stat block is a first-class participant
everywhere else (vehicles and objects subclass it; `resolve_attack` takes
either shape). It now raises a `TypeError` naming the limitation at the
boundary. Widening enumeration to flat stat blocks is real work and is not
smuggled in behind a `getattr` default that would return a shorter menu.

### Removed

`kirby_combat.loop.sides` — replaced by `kirby_combat.roster`.

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
