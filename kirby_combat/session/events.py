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
    | AbortDeclared
    | HeldActionDeclared
    | HeldActionReleased
    | AdjustmentApplied
    | AdjustmentFaded
    | EntangleApplied
    | EntangleEscape
    | FlashApplied
    | FlashRecovered
    | EnvironmentalTriggered
    | ConstructDamaged
    | ConstructSpawned
    | GMOverride
    | SessionEnded
)
