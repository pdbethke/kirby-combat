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
class _BaseEvent:
    id: str
    session_id: str
    sequence: int
    timestamp: datetime
    author: EventAuthor


# ---------------------------------------------------------------------------
# Concrete event types (discriminated by class; each has a `kind` Literal)
# ---------------------------------------------------------------------------

@dataclass
class SessionStarted(_BaseEvent):
    kind: Literal["SessionStarted"] = field(default="SessionStarted", init=False)
    scene_id: str = ""
    combatant_ids: list[str] = field(default_factory=list)


@dataclass
class SegmentAdvanced(_BaseEvent):
    kind: Literal["SegmentAdvanced"] = field(default="SegmentAdvanced", init=False)
    from_segment: int = 0
    to_segment: int = 0
    to_turn: int = 0


@dataclass
class ActingOrderResolved(_BaseEvent):
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
class PhaseSpent(_BaseEvent):
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
    #: "acted" (he used it), "down" (unconscious or worse, 6E1 p.421) or
    #: "left" (out of the scene's bounds, so no longer in the fight).
    reason: str = "acted"


@dataclass
class ActionDeclared(_BaseEvent):
    kind: Literal["ActionDeclared"] = field(default="ActionDeclared", init=False)
    combatant_id: str = ""
    action_type: str = ""
    targets: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResolved(_BaseEvent):
    kind: Literal["ActionResolved"] = field(default="ActionResolved", init=False)
    declaration_event_id: str = ""
    result_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class VitalsChanged(_BaseEvent):
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
class RecoveryTaken(_BaseEvent):
    kind: Literal["RecoveryTaken"] = field(default="RecoveryTaken", init=False)
    combatant_id: str = ""
    stun_recovered: int = 0
    end_recovered: int = 0


@dataclass
class BleedingSuffered(_BaseEvent):
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
class MovementResolved(_BaseEvent):
    kind: Literal["MovementResolved"] = field(default="MovementResolved", init=False)
    combatant_id: str = ""
    from_pos: dict[str, float] | None = None
    to_pos: dict[str, float] | None = None
    velocity_mps: float = 0.0
    move_type: str = ""


@dataclass
class StatusChanged(_BaseEvent):
    kind: Literal["StatusChanged"] = field(default="StatusChanged", init=False)
    combatant_id: str = ""
    from_status: str = ""
    to_status: str = ""
    reason: str = ""


@dataclass
class StatusEffectsChanged(_BaseEvent):
    """Delta view of a combatant's condition set at one change point.

    `StatusChanged` (above) carries a scalar from/to pair for narration
    ("went from Stunned to Knocked Out"). Conditions are not scalar — a
    combatant can be Entangled AND Flashed in two sense groups AND
    Knocked Out at once, and each id toggles independently (this is how
    Foundry's per-effect toggle API works). This event carries exactly
    that: the ids added and the ids removed at this change point. It is
    plumbing, not a rule — the status set itself is derived elsewhere
    (`kirby_combat.statuses.statuses_for`), never from this event.
    """
    kind: Literal["StatusEffectsChanged"] = field(default="StatusEffectsChanged", init=False)
    combatant_id: str = ""
    added: frozenset[str] = field(default_factory=frozenset)
    removed: frozenset[str] = field(default_factory=frozenset)


@dataclass
class AbortDeclared(_BaseEvent):
    kind: Literal["AbortDeclared"] = field(default="AbortDeclared", init=False)
    combatant_id: str = ""
    to_action: str = ""


@dataclass
class BlockPriorityGained(_BaseEvent):
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
class HeldActionDeclared(_BaseEvent):
    kind: Literal["HeldActionDeclared"] = field(default="HeldActionDeclared", init=False)
    combatant_id: str = ""
    trigger_condition: str = ""
    for_action: str | None = None


@dataclass
class HeldActionReleased(_BaseEvent):
    kind: Literal["HeldActionReleased"] = field(default="HeldActionReleased", init=False)
    held_event_id: str = ""
    trigger_observed: str = ""


@dataclass
class AdjustmentApplied(_BaseEvent):
    kind: Literal["AdjustmentApplied"] = field(default="AdjustmentApplied", init=False)
    target_id: str = ""
    stat: str = ""
    delta: int = 0
    fade_rate_per_turn: int = 5
    source_event_id: str = ""


@dataclass
class AdjustmentFaded(_BaseEvent):
    kind: Literal["AdjustmentFaded"] = field(default="AdjustmentFaded", init=False)
    target_id: str = ""
    stat: str = ""
    remaining_delta: int = 0


@dataclass
class EntangleApplied(_BaseEvent):
    kind: Literal["EntangleApplied"] = field(default="EntangleApplied", init=False)
    target_id: str = ""
    entangle_body: int = 0
    entangle_pd: int = 0
    entangle_ed: int = 0
    #: Levels of "Cannot Be Escaped With Teleportation" (+1/4 each) on the
    #: source Entangle (6E1 p220). 0 = teleport escape works normally.
    no_teleport_levels: int = 0


@dataclass
class EntangleEscape(_BaseEvent):
    kind: Literal["EntangleEscape"] = field(default="EntangleEscape", init=False)
    target_id: str = ""
    method: str = ""                      # "casual_str" | "full_str" | "break_out"
    damage_to_entangle_body: int = 0
    escaped: bool = False


@dataclass
class FlashApplied(_BaseEvent):
    kind: Literal["FlashApplied"] = field(default="FlashApplied", init=False)
    target_id: str = ""
    sense_group: str = ""
    segments: int = 0


@dataclass
class FlashRecovered(_BaseEvent):
    kind: Literal["FlashRecovered"] = field(default="FlashRecovered", init=False)
    target_id: str = ""
    sense_group: str = ""
    segments_remaining: int = 0


@dataclass
class PresenceApplied(_BaseEvent):
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
class PresenceActionLost(_BaseEvent):
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
class PresenceFaded(_BaseEvent):
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
class EnvironmentalTriggered(_BaseEvent):
    kind: Literal["EnvironmentalTriggered"] = field(default="EnvironmentalTriggered", init=False)
    hazard_id: str = ""
    affected_combatants: list[str] = field(default_factory=list)
    effect: dict[str, Any] = field(default_factory=dict)


@dataclass
class GMOverride(_BaseEvent):
    kind: Literal["GMOverride"] = field(default="GMOverride", init=False)
    tier: int = 1
    target_event_id: str | None = None
    patch: dict[str, Any] = field(default_factory=dict)
    justification: str = ""

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"GMOverride.tier must be 1, 2, or 3 — got {self.tier}")


@dataclass
class ConstructDamaged(_BaseEvent):
    kind: Literal["ConstructDamaged"] = field(default="ConstructDamaged", init=False)
    construct_id: str = ""
    body_rolled: int = 0
    def_value: int = 0
    body_through: int = 0
    body_after: int = 0
    destroyed: bool = False
    by_combatant: str = ""


@dataclass
class ConstructSpawned(_BaseEvent):
    kind: Literal["ConstructSpawned"] = field(default="ConstructSpawned", init=False)
    construct_id: str = ""
    construct_kind: str = "force_wall"
    def_value: int | None = None
    body: int | None = None
    source_combatant: str = ""


@dataclass
class SessionEnded(_BaseEvent):
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
    | StatusChanged
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
    | PresenceFaded
    | EnvironmentalTriggered
    | ConstructDamaged
    | ConstructSpawned
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
