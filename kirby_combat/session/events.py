"""CombatEvent union — every state change in a session."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, get_args

if TYPE_CHECKING:
    from kirby_combat.session.timeline import ActionIntent


# ---------------------------------------------------------------------------
# Author
# ---------------------------------------------------------------------------

AuthorType = Literal["combatant", "gm", "engine"]


@dataclass(frozen=True)
class EventAuthor:
    """Who caused this event."""
    type: AuthorType
    id: str


def make_author_combatant(combatant_id: str) -> EventAuthor:
    return EventAuthor(type="combatant", id=combatant_id)


def make_author_gm(user_id: str) -> EventAuthor:
    return EventAuthor(type="gm", id=user_id)


def make_author_engine() -> EventAuthor:
    return EventAuthor(type="engine", id="engine")


# ---------------------------------------------------------------------------
# Base event shape
# ---------------------------------------------------------------------------

@dataclass
class BaseEvent:
    id: str
    session_id: str
    sequence: int
    timestamp: datetime
    author: EventAuthor


# ---------------------------------------------------------------------------
# Concrete event types (discriminated by class; each has a `kind` Literal)
# ---------------------------------------------------------------------------

@dataclass
class SessionStarted(BaseEvent):
    kind: Literal["SessionStarted"] = field(default="SessionStarted", init=False)
    scene_id: str = ""
    combatant_ids: list[str] = field(default_factory=list)


@dataclass
class SegmentAdvanced(BaseEvent):
    kind: Literal["SegmentAdvanced"] = field(default="SegmentAdvanced", init=False)
    from_segment: int = 0
    to_segment: int = 0
    to_turn: int = 0


@dataclass
class ActingOrderResolved(BaseEvent):
    """Who acts, in what order, in one Segment of one fight.

    THE LOOP'S OWN DECISION, WHICH NEVER REACHED THE RECORD. The order is
    resolved once per Segment --- 6E2 p.18-21: the characters who have a
    Phase this Segment act in DEX order, ties broken by the campaign's tie
    rule --- and until this event existed it was written straight onto
    ``Timeline.acting_order`` and nowhere else. A consumer that persists
    only the log (which is what "the log is the record" has to mean) could
    replay every point of damage and still not know whose Phase it was, so
    a fight rebuilt by replay carried an empty order and nobody to act.

    ``order`` is the resolved sequence of combatant ids, first to last.
    The per-slot values a resolved ``ActingSlot`` also carries --- DEX at
    the Phase, the tie-break ladder, the Lightning Reflexes grants --- are
    DERIVED from the combatants and the Segment, so ``apply_event``
    rebuilds them rather than recording them twice. This event carries the
    decision, not the arithmetic behind it.

    ``intents`` IS part of the decision, not derived from anything. A
    declared ``ActionIntent`` changes what the order MEANS as well as how
    it sorted: a man who elected Lightning Reflexes for one named Action
    may not then do something else in that Phase (6E1 p.116(c)), and
    ``apply_event`` enforces exactly that off ``ActingSlot.intent``. Left
    out of this event, a replayed fight would ACCEPT a declaration the
    live fight refuses --- the rule enforced at one door and not the
    other. Keyed by combatant id; a combatant who declared nothing is
    simply absent.
    """

    kind: Literal["ActingOrderResolved"] = field(
        default="ActingOrderResolved", init=False)
    order: list[str] = field(default_factory=list)
    segment: int = 0
    turn: int = 0
    intents: dict[str, "ActionIntent"] = field(default_factory=dict)


@dataclass
class PhaseSpent(BaseEvent):
    """One combatant's slot in this Segment's order, used up.

    The other half of the same gap: an order that replay can restore still
    hands the same combatant every Phase forever if the SPEND is not in
    the log too. Emitted wherever the loop consumes a slot --- including
    the Phases nobody would call an action: a man held by a Presence
    Attack, a man with no legal action, and a chosen kind the registry
    cannot yet resolve each spend a Phase just as surely as a punch does.

    ``reason`` says WHICH of those it was. Two of them are not decisions
    the loop made at all but consequences of the man's condition --- he is
    down (6E1 p.421), or he has left the field --- and a consumer that
    folds no stats at all must still land on the same next actor as the
    fight that ran. That is only possible if the skip is in the log
    saying why.
    """

    kind: Literal["PhaseSpent"] = field(default="PhaseSpent", init=False)
    combatant_id: str = ""
    segment: int = 0
    turn: int = 0
    #: "acted" (he used it), "down" (unconscious or worse, 6E1 p.421),
    #: "left" (out of the scene's bounds, so no longer in the fight),
    #: "aborted" (he already spent it on an Abort, 6E2 p.24), "stunned"
    #: (he spent it recovering from being Stunned, 6E2 p.107) or "entranced"
    #: (lost in an EGO+30 Mental Illusion, 6E1 p.251).
    reason: str = "acted"


@dataclass
class ActionDeclared(BaseEvent):
    kind: Literal["ActionDeclared"] = field(default="ActionDeclared", init=False)
    combatant_id: str = ""
    action_type: str = ""
    targets: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResolved(BaseEvent):
    kind: Literal["ActionResolved"] = field(default="ActionResolved", init=False)
    declaration_event_id: str = ""
    result_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class VitalsChanged(BaseEvent):
    """STUN, BODY or END moving on one combatant --- the whole of it.

    THE CHANGE WAS NEVER IN THE RECORD. Every resolver in this engine
    changed a combatant BESIDE the event that described what happened:
    `actions/recording.py` folded an attack's damage onto
    `session.combatants` and then logged an `ActionResolved` whose
    `result_payload` was a free-form dict; the END an attack, a move or a
    Push cost was taken off the fighter and logged nowhere at all. A
    consumer that persists the rows and rebuilds the fight by replaying
    them --- which is what "the log is the record" has to mean ---
    therefore rebuilt a fight in which nobody had ever been hit.
    Measured: two Phases in, a fighter stood at 27 STUN in the fight that
    ran and 50 in the fight replayed from its log.

    So the change itself is an event, and `apply_event` is the only thing
    that writes a vital. The deltas are SIGNED and they are DELTAS, not
    resulting values: `stun=-14` is fourteen STUN taken off him,
    `end=-5` is a Push paid for (6E2 p.133). That is the opposite
    discipline from `AdjustmentFaded.remaining_delta` and
    `PresenceFaded.segments_remaining`, which carry absolutes, and
    deliberately so --- those fold a running effect forward and this
    records a transaction. `apply_vitals_delta` clamps nothing in either
    direction, which is what keeps how far below zero a man fell
    readable (6E1 p.421), so a caller that owes a bounded amount bounds
    it before emitting and the number in the log is the number that
    happened.

    `reason` is for the reader, not the fold: "damage", "end_spent",
    "collapse". The rules-bearing losses have their own typed events and
    keep them --- `RecoveryTaken` (6E2 p.130/p.131) and
    `BleedingSuffered` (6E2 p.109/p.115) both already carried their
    numbers in typed fields and both now fold through the same one door.
    """

    kind: Literal["VitalsChanged"] = field(default="VitalsChanged", init=False)
    combatant_id: str = ""
    stun: int = 0
    body: int = 0
    end: int = 0
    reason: str = ""


@dataclass
class RecoveryTaken(BaseEvent):
    kind: Literal["RecoveryTaken"] = field(default="RecoveryTaken", init=False)
    combatant_id: str = ""
    stun_recovered: int = 0
    end_recovered: int = 0


@dataclass
class BleedingSuffered(BaseEvent):
    """BODY (and, under the optional rules, STUN) lost between Phases.

    6E2 p.109's bleeding to death is 1 BODY at the end of each Turn for
    anyone at or below 0 BODY; p.115's optional Bleeding rules take STUN
    per Turn from any wound, and a further BODY on a six. Both are losses
    nobody chose and no attack caused, so neither has an ActionResolved
    to hang off --- and a man who quietly got worse between Segments,
    with nothing in the log, is indistinguishable from a bookkeeping
    error to a reader and invisible to a replay.
    """

    kind: Literal["BleedingSuffered"] = field(
        default="BleedingSuffered", init=False)
    combatant_id: str = ""
    body_lost: int = 0
    stun_lost: int = 0
    #: "bleed_out" (p.109) or "wound" (p.115) --- two different rules that
    #: both take BODY, and a reader must be able to tell which fired.
    rule: str = ""
    dice: tuple[int, ...] = ()


@dataclass
class MovementResolved(BaseEvent):
    """Where a man went — and, since 0.18.5, WHAT APPLIES IT.

    `apply_event` folds this onto `session.scene.combatant_positions`,
    which makes it the one writer of where anybody stands. It used to be
    log-only, and `scene/placement.py::commit_move` wrote the landing
    onto the Scene beside it: a session rebuilt from its rows put every
    fighter at his starting placement for ever. Measured on a recorded
    fight — all fourteen checkpoints had Wyatt at (3.1, 3.7) although he
    moved at sequence 7.

    `from_pos` and `to_pos` carry `x`, `y`, `z` AND `facing` — radians,
    0 = east, the same four numbers `scene.Position` holds. Facing was
    dropped from the wire until 0.18.5, so a replay could put a man on
    the right spot pointing the wrong way, which a board draws.

    `to_pos is None` is not a missing value: it means this row records a
    movement that CHOSE NO DESTINATION (`MovementAction.resolve` spends
    END for a distance), so the fold moves nobody.
    """
    kind: Literal["MovementResolved"] = field(default="MovementResolved", init=False)
    combatant_id: str = ""
    from_pos: dict[str, float] | None = None
    to_pos: dict[str, float] | None = None
    velocity_mps: float = 0.0
    move_type: str = ""


@dataclass
class StatusEffectsChanged(BaseEvent):
    """THE ONE DOOR a condition goes through to reach the log.

    Conditions are not scalar — a combatant can be Entangled AND Flashed
    in two sense groups AND Knocked Out at once, and each id toggles
    independently (this is how Foundry's per-effect toggle API works).
    This event carries exactly that: the ids added and the ids removed at
    this change point.

    THE SECOND DOOR IS GONE (0.18.5). `StatusChanged` — a scalar
    `from_status`/`to_status` pair — stood beside this one with no
    producer anywhere in the engine and exactly one consumer, Prone's
    clear edge in `kirby_combat.statuses._is_prone`. Two shapes for one
    fact, one of them unreachable, is the shape this engine has paid for
    repeatedly; the clear edge now reads THIS event (`PRONE` in
    `removed`) and the scalar event is deleted. A combatant getting to
    his feet is still a consumer's explicit act, which is the whole
    reason that edge exists.

    `apply_event` folds it onto `CombatSession.statuses`, and
    `session/state_view.py` reads that folded set rather than deriving a
    second one. The RULE for what a condition is stays in
    `kirby_combat.statuses.statuses_for`, which is what
    `status_emission.record_status_changes` — the one emitter — diffs to
    decide that a row is owed.
    """
    kind: Literal["StatusEffectsChanged"] = field(default="StatusEffectsChanged", init=False)
    combatant_id: str = ""
    added: frozenset[str] = field(default_factory=frozenset)
    removed: frozenset[str] = field(default_factory=frozenset)


@dataclass
class AbortDeclared(BaseEvent):
    kind: Literal["AbortDeclared"] = field(default="AbortDeclared", init=False)
    combatant_id: str = ""
    to_action: str = ""
    #: The Phase he gave up (6E2 p.24, "HOW TO ABORT AN ACTION"). He can
    #: neither abort again nor act until it has passed, and when it comes
    #: round he does nothing in it.
    aborted_turn: int = 0
    aborted_segment: int = 0
    #: His next Phase after that one: what he aborted to (the Dodge's DCV)
    #: lasts until he takes it. Fixed HERE, at declaration, rather than
    #: re-derived from SPD when the clock moves, so a replayed log expires
    #: the abort at the same moments as the fight that ran even if his SPD
    #: was Drained in between.
    bonus_until_turn: int = 0
    bonus_until_segment: int = 0


@dataclass
class BlockPriorityGained(BaseEvent):
    """A successful Block earning its blocker the right to act first.

    6E2 p.60, "ACTING FIRST": a character who Blocks an attack
    successfully "acts before that attacker in the next Phase in which
    they both act, even if [the attacker] does not attack again."

    NOT IN THE RECORD UNTIL NOW, and the only piece of fight state that
    was not. It was carried on `Encounter.acts_first` --- a field --- and
    a consumer that persists the rows and rebuilds the Encounter from the
    session's own timeline between steps held an empty mapping: the
    blocker won his Block in the live fight and lost his priority in the
    replayed one, so the two fights resolved the next shared Segment in
    different orders with nothing saying why.

    THE SPEND NEEDS NO EVENT OF ITS OWN. The rule spends the priority in
    the next Segment where both men have a Phase, which is exactly what
    `ActingOrderResolved` already records --- `apply_event` drops the
    entry when it applies an order containing both ids. A second event
    would be a second statement of one rule.
    """

    kind: Literal["BlockPriorityGained"] = field(
        default="BlockPriorityGained", init=False)
    blocker_id: str = ""
    attacker_id: str = ""


@dataclass
class HeldActionDeclared(BaseEvent):
    kind: Literal["HeldActionDeclared"] = field(default="HeldActionDeclared", init=False)
    combatant_id: str = ""
    trigger_condition: str = ""
    for_action: str | None = None


@dataclass
class HeldActionReleased(BaseEvent):
    kind: Literal["HeldActionReleased"] = field(default="HeldActionReleased", init=False)
    held_event_id: str = ""
    trigger_observed: str = ""


@dataclass
class AdjustmentApplied(BaseEvent):
    """An Aid, a Drain (6E1 p.169, p.197) landing on one stat of one target.

    ``delta`` is CHARACTER POINTS, signed: + for an Aid, - for a Drain. 6E1
    p.137 applies an Adjustment "to the Active Points of a Characteristic or
    Power", and the 5-points-per-Turn fade (6E1 p.141) comes off those, so
    that is the unit the fold walks. ``stat`` is the characteristic's xmlid
    ("DEX") or ``"POWER:<source id>"`` for one attack power's dice.

    ``cost_per_point`` is what one point of ``stat`` cost on the TARGET's
    build when this landed (DEX 2, SPD 10, STUN 0.5; a power's Active Points
    per 1d6), so the log alone turns points into a characteristic and a
    replay needs no build to price it. 0 only on rows written before it was
    recorded, which `adjustments.live_adjustments` keeps and does not apply.
    """
    kind: Literal["AdjustmentApplied"] = field(default="AdjustmentApplied", init=False)
    target_id: str = ""
    stat: str = ""
    delta: int = 0
    fade_rate_per_turn: int = 5
    source_event_id: str = ""
    cost_per_point: float = 0.0


@dataclass
class AdjustmentFaded(BaseEvent):
    kind: Literal["AdjustmentFaded"] = field(default="AdjustmentFaded", init=False)
    target_id: str = ""
    stat: str = ""
    remaining_delta: int = 0


@dataclass
class EntangleApplied(BaseEvent):
    kind: Literal["EntangleApplied"] = field(default="EntangleApplied", init=False)
    target_id: str = ""
    entangle_body: int = 0
    entangle_pd: int = 0
    entangle_ed: int = 0
    #: Levels of "Cannot Be Escaped With Teleportation" (+1/4 each) on the
    #: source Entangle (6E1 p220). 0 = teleport escape works normally.
    no_teleport_levels: int = 0
    #: A Mental Paralysis (6E1 p.219): escaped with EGO not STR, defended by
    #: ``entangle_md`` instead of PD/ED, and a separate Entangle from any
    #: physical one ("physical Entangles don't add to Mental Paralysis
    #: Entangles, and vice-versa"). The False default exists only so a log
    #: written before 0.22 still reads; every emitter states it
    #: (`Entangle.apply` / `Entangle.apply_mental_paralysis`).
    mental_paralysis: bool = False
    #: The Mental Paralysis's Resistant Mental Defense (6E1 p.219); 0 for a
    #: physical Entangle, whose defenses are ``entangle_pd``/``entangle_ed``.
    entangle_md: int = 0


@dataclass
class EntangleEscape(BaseEvent):
    kind: Literal["EntangleEscape"] = field(default="EntangleEscape", init=False)
    target_id: str = ""
    method: str = ""                      # "casual_str" | "full_str" | "full_ego" | "teleport" | "attack"
    damage_to_entangle_body: int = 0
    escaped: bool = False
    #: Which Entangle he is escaping: a Mental Paralysis (6E1 p.219) or the
    #: physical one. Default as on `EntangleApplied`, for older logs only.
    mental_paralysis: bool = False


@dataclass
class FlashApplied(BaseEvent):
    kind: Literal["FlashApplied"] = field(default="FlashApplied", init=False)
    target_id: str = ""
    sense_group: str = ""
    segments: int = 0


@dataclass
class FlashRecovered(BaseEvent):
    kind: Literal["FlashRecovered"] = field(default="FlashRecovered", init=False)
    target_id: str = ""
    sense_group: str = ""
    segments_remaining: int = 0


@dataclass
class PresenceApplied(BaseEvent):
    """A Presence Attack tier landing on a target (6E2 p.139).

    ``segments`` is the tier's full duration at the moment it lands. The
    fold in ``session/effects.py`` reads it forward; nothing inverts it.
    """
    kind: Literal["PresenceApplied"] = field(default="PresenceApplied", init=False)
    target_id: str = ""
    attacker_id: str = ""
    tier: str = ""
    segments: int = 0


@dataclass
class PresenceActionLost(BaseEvent):
    """The one Full Phase a Presence Attack costs its target (6E2 p.139).

    ITS OWN CLOCK, because the tier has two. At PRE+20 the book says
    "will not act for 1 Full Phase and is at half DCV; about 5 Minutes":
    the DCV penalty runs the tier's duration and the LOST ACTION is a
    single Phase. Folding them together would delete a combatant from the
    whole fight on one good shout -- `awed` is five minutes and
    `overwhelmed` an hour -- which is not the rule.

    Recorded rather than counted in the timeline so it survives replay,
    like every other effect here.
    """
    kind: Literal["PresenceActionLost"] = field(
        default="PresenceActionLost", init=False)
    target_id: str = ""


@dataclass
class PresenceFaded(BaseEvent):
    """Time passing on a Presence effect.

    ``segments_remaining`` is the RESULTING value, absolute — never a delta
    to subtract. That is what lets ``presence_state`` fold forward and is the
    same contract ``FlashRecovered.segments_remaining`` and
    ``AdjustmentFaded.remaining_delta`` already hold to. A delta here would
    have to be inverted to read state backwards, and this project has already
    proved inversion cannot be made correct (END clamps at 0 on spend).
    """
    kind: Literal["PresenceFaded"] = field(default="PresenceFaded", init=False)
    target_id: str = ""
    segments_remaining: int = 0


@dataclass
class BreakoutRolled(BaseEvent):
    """A target's Breakout Roll against a continuing-effect Mental Power.

    6E1 p.151: "Starting on the target's next Phase after being
    successfully attacked with a continuing-effect Mental Power, he may
    attempt to break free from the Power. These attempts are subconscious
    and take no time". p.152 prices it: EGO Roll, -1 per 5 points the
    effect beat its minimum, and later attempts at +1 after a Turn, +2
    after a Minute and so on up the Time Chart.

    ``effect_id`` is the id of the ``ActionResolved`` that established the
    effect --- Mind Control or a Mind Scan lock --- which is where the
    effect itself is recorded (see `kirby_combat/mental/continuing.py`).
    ``turn``/``segment`` is when the roll was made: the Time Chart counts
    from the FIRST attempt, so the fold needs the clock of each one.
    """
    kind: Literal["BreakoutRolled"] = field(default="BreakoutRolled", init=False)
    target_id: str = ""
    effect_id: str = ""
    roll: int = 0
    target_number: int = 0
    bonus: int = 0
    broke_free: bool = False
    turn: int = 0
    segment: int = 0


@dataclass
class PresenceYielded(BaseEvent):
    """An impressed man stepping back behind the one who impressed him.

    6E2 p.139, at PRE: "He hesitates enough so that the attacker may act
    before him that Phase." Applying it moves the target's first unspent
    slot in this Segment's acting order to just after the attacker's, so a
    fight replayed from its log hands the Phases out in the same order.
    Written by `pre_attacks/in_the_phase.py`.
    """
    kind: Literal["PresenceYielded"] = field(default="PresenceYielded", init=False)
    target_id: str = ""
    attacker_id: str = ""
    turn: int = 0
    segment: int = 0


@dataclass
class RageRolled(BaseEvent):
    """A roll against an Enraged/Berserk complication (6E1 p.424-425).

    ``roll_kind`` is ``"go"`` (his chance to give in to fury, rolled every
    Phase the circumstance holds) or ``"recover"`` (his chance to calm
    down). ``succeeded`` is the roll made: a made "go" roll puts him in a
    rage, a made "recover" roll ends it. ``target_id`` is who a rage that
    begins here is locked on ("" when there is nobody to lock on).
    ``reason`` says why the roll was owed: the circumstance class for a
    "go" roll, the recovery occasion for a "recover" roll.
    Folded by `kirby_combat/rage.py::rage_state`.
    """
    kind: Literal["RageRolled"] = field(default="RageRolled", init=False)
    combatant_id: str = ""
    complication_id: str = ""
    roll_kind: str = ""
    roll: int = 0
    target_number: int = 0
    succeeded: bool = False
    berserk: bool = False
    target_id: str = ""
    reason: str = ""
    turn: int = 0
    segment: int = 0


@dataclass
class RageTargeted(BaseEvent):
    """A raging man turning on a new target after finishing the last.

    6E1 p.424 (Enraged): having failed to recover, he "vents his anger on
    other targets ... starting with the targets most closely related to his
    original target"; p.425 (Berserk): he "attacks the nearest visible
    target".
    """
    kind: Literal["RageTargeted"] = field(default="RageTargeted", init=False)
    combatant_id: str = ""
    target_id: str = ""
    reason: str = ""


@dataclass
class LingeringAttackApplied(BaseEvent):
    """An attack that goes on hurting after it lands.

    Two Advantages make one hit into many, and the deleted api driver kept
    both in a JSON column on the combatant row (`continuous_effects`), so a
    fight rebuilt from its log had never been poisoned:

      * Constant (HD's CONTINUOUS), 6E1 p.129: "the target takes damage ...
        in every Segment in which the attacker has a Phase (on the
        attacker's DEX) until the attacker turns off the Power, stops
        maintaining it ... or loses LOS to the target."
      * Damage Over Time, 6E1 p.330-333: ``increments`` doses,
        ``interval_segments`` apart, the first "one time period after the
        character uses the attack", whatever the attacker does after.

    ``mode`` is a `kirby_combat.lingering.LingeringMode` value. Each later
    dose is an ``ActionResolved`` whose ``declaration_event_id`` is THIS
    event's id and whose payload carries ``lingering_id`` and the resulting
    ``increments_remaining`` (absolute, never a delta --- the house pattern,
    see `session/effects.py`). ``applied_turn``/``applied_segment`` is when
    it landed: the Damage Over Time clock counts from here.
    """
    kind: Literal["LingeringAttackApplied"] = field(
        default="LingeringAttackApplied", init=False)
    attacker_id: str = ""
    target_id: str = ""
    power_source_id: str = ""
    power_name: str = ""
    mode: str = ""
    increments: int | None = None
    interval_segments: int | None = None
    applied_turn: int = 0
    applied_segment: int = 0


@dataclass
class LingeringAttackEnded(BaseEvent):
    """A lingering attack stopped, and why (`lingering.LingeringEnd`).

    A Damage Over Time ends by running out of doses; a Constant attack ends
    when its attacker stops paying, is Stunned or Knocked Out (6E1 p.347),
    loses Line Of Sight (6E1 p.129), switches the slot off (6E1 p.400) or
    uses the power again. ``lingering_id`` is the `LingeringAttackApplied`.
    """
    kind: Literal["LingeringAttackEnded"] = field(
        default="LingeringAttackEnded", init=False)
    lingering_id: str = ""
    reason: str = ""


@dataclass
class EnvironmentalTriggered(BaseEvent):
    kind: Literal["EnvironmentalTriggered"] = field(default="EnvironmentalTriggered", init=False)
    hazard_id: str = ""
    affected_combatants: list[str] = field(default_factory=list)
    effect: dict[str, Any] = field(default_factory=dict)


@dataclass
class GMOverride(BaseEvent):
    kind: Literal["GMOverride"] = field(default="GMOverride", init=False)
    tier: int = 1
    target_event_id: str | None = None
    patch: dict[str, Any] = field(default_factory=dict)
    justification: str = ""

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"GMOverride.tier must be 1, 2, or 3 — got {self.tier}")


@dataclass
class ConstructDamaged(BaseEvent):
    kind: Literal["ConstructDamaged"] = field(default="ConstructDamaged", init=False)
    construct_id: str = ""
    body_rolled: int = 0
    def_value: int = 0
    body_through: int = 0
    body_after: int = 0
    destroyed: bool = False
    by_combatant: str = ""


@dataclass
class ConstructSpawned(BaseEvent):
    kind: Literal["ConstructSpawned"] = field(default="ConstructSpawned", init=False)
    construct_id: str = ""
    construct_kind: str = "force_wall"
    def_value: int | None = None
    body: int | None = None
    source_combatant: str = ""


@dataclass
class BarrierRaised(BaseEvent):
    """A Barrier put up in the fight (6E1 p.167) --- and what applies it.

    THE WALL WAS NEVER IN THE RECORD. `_resolve_force_wall` appended a
    `Wall` to `session.scene.walls` IN PLACE and logged an `ActionResolved`
    beside it, the same mutate-then-log shape `MovementResolved` was taken
    out of in 0.18.5. A fight rebuilt from its rows, a `rewind_to_sequence`
    and a Krackle replay all started from the authored scene and had no
    wall: the shot it was raised to stop went through on the replay.

    `apply_event` folds this onto `session.scene.walls`, so it is the one
    writer of a raised Barrier. `start`/`end` carry ``x``, ``y``, ``z`` ---
    the two ends of the wall's footprint, as `scene.Wall.segment` holds
    them. The BODY and DEFs are the Barrier's own; damage to it is folded
    from the log like any other construct's (`constructs.damage_by_object`).
    """
    kind: Literal["BarrierRaised"] = field(default="BarrierRaised", init=False)
    wall_id: str = ""
    name: str = ""
    start: dict[str, float] = field(default_factory=dict)
    end: dict[str, float] = field(default_factory=dict)
    height_m: float = 0.0
    body: int = 0
    def_value: int = 0
    ed_value: int = 0
    source_combatant: str = ""


@dataclass
class PowerDispelled(BaseEvent):
    """One of the target's powers stops working (6E1 p.195).

    `apply_event` folds it into the target's build (`actions/dispel.py`):
    every reader of his powers reads them without this one until a
    `PowerRestarted` for it.
    """
    kind: Literal["PowerDispelled"] = field(default="PowerDispelled", init=False)
    target_id: str = ""
    power_id: str = ""
    power_xmlid: str = ""
    source_combatant: str = ""


@dataclass
class PowerRestarted(BaseEvent):
    """He turns a dispelled power back on --- a Zero Phase Action at the
    start of his Phase (6E2 p.20; 6E1 p.195: "The victim of a Dispel may
    'restart' the Dispelled power")."""
    kind: Literal["PowerRestarted"] = field(default="PowerRestarted", init=False)
    combatant_id: str = ""
    power_id: str = ""


@dataclass
class SessionEnded(BaseEvent):
    kind: Literal["SessionEnded"] = field(default="SessionEnded", init=False)
    reason: str = ""


# ---------------------------------------------------------------------------
# Union alias — every concrete event type
# ---------------------------------------------------------------------------

CombatEvent = (
    SessionStarted
    | SegmentAdvanced
    | ActingOrderResolved
    | PhaseSpent
    | ActionDeclared
    | ActionResolved
    | VitalsChanged
    | RecoveryTaken
    | BleedingSuffered
    | MovementResolved
    | StatusEffectsChanged
    | AbortDeclared
    | BlockPriorityGained
    | HeldActionDeclared
    | HeldActionReleased
    | AdjustmentApplied
    | AdjustmentFaded
    | EntangleApplied
    | EntangleEscape
    | FlashApplied
    | FlashRecovered
    | PresenceApplied
    # `PresenceActionLost` was declared beside the others, emitted by
    # `pre_attacks/presence_effects.py` and folded by `apply_event` --- and
    # left out of this union, so the registry `from_dict` derives from it
    # never knew the name. A fight in which a Presence Attack cost a man his
    # Phase could be written and never read back: `unknown type
    # 'PresenceActionLost'`. Same shape as the six `VitalsChanged` was in,
    # one level up --- `EVENT_CLASSES` guards the registry against the union
    # and could not guard the union against the classes. That derivation is
    # `tests/serialization/test_roundtrip.py`'s
    # `_event_classes_the_module_defines`.
    | PresenceActionLost
    | PresenceFaded
    | BreakoutRolled
    | PresenceYielded
    | RageRolled
    | RageTargeted
    | LingeringAttackApplied
    | LingeringAttackEnded
    | EnvironmentalTriggered
    | ConstructDamaged
    | ConstructSpawned
    | BarrierRaised
    | PowerDispelled
    | PowerRestarted
    | GMOverride
    | SessionEnded
)

#: EVERY concrete event class, derived from the union above rather than
#: written out again. Two consumers need the list -- `serialization/
#: from_dict.py`'s type registry and the round-trip gate that guards it --
#: and both of them used to keep a hand-written copy. `VitalsChanged` was
#: added to the union, to `apply_event` and to the package's `__all__`,
#: and was still unreadable off the wire, because the copy in the registry
#: was not updated and the copy in the test could not notice: it listed
#: the same classes the registry did. Six of the 28 were missing.
#:
#: A list of where a property holds is not a guard on the property. This
#: is the derivation both of them now read.
EVENT_CLASSES: tuple[type, ...] = get_args(CombatEvent)

#: `kind` -> the class that carries it. The `kind` field is a Literal with
#: an `init=False` default on every event, so it can be read off the class
#: without building one.
EVENT_KINDS: dict[str, type] = {
    cls.__dataclass_fields__["kind"].default: cls for cls in EVENT_CLASSES
}
