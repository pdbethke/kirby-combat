"""CombatEvent union — every state change in a session."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


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
class RecoveryTaken(_BaseEvent):
    kind: Literal["RecoveryTaken"] = field(default="RecoveryTaken", init=False)
    combatant_id: str = ""
    stun_recovered: int = 0
    end_recovered: int = 0


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
    | ActionDeclared
    | ActionResolved
    | RecoveryTaken
    | MovementResolved
    | StatusChanged
    | StatusEffectsChanged
    | AbortDeclared
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
