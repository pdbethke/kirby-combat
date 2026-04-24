"""CombatSession state machine and related types."""
from kirby_combat.session.timeline import (
    Timeline,
    ActingSlot,
    HeldAction,
    build_acting_order_for_segment,
)

__all__ = ["Timeline", "ActingSlot", "HeldAction", "build_acting_order_for_segment"]

from kirby_combat.session.events import (
    CombatEvent, EventAuthor,
    SessionStarted, SegmentAdvanced, ActionDeclared, ActionResolved,
    RecoveryTaken, MovementResolved, StatusChanged, AbortDeclared,
    HeldActionDeclared, HeldActionReleased,
    AdjustmentApplied, AdjustmentFaded,
    EntangleApplied, EntangleEscape, FlashApplied, FlashRecovered,
    EnvironmentalTriggered, GMOverride, SessionEnded,
    make_author_combatant, make_author_gm, make_author_engine,
)

__all__ += [
    "CombatEvent", "EventAuthor",
    "SessionStarted", "SegmentAdvanced", "ActionDeclared", "ActionResolved",
    "RecoveryTaken", "MovementResolved", "StatusChanged", "AbortDeclared",
    "HeldActionDeclared", "HeldActionReleased",
    "AdjustmentApplied", "AdjustmentFaded",
    "EntangleApplied", "EntangleEscape", "FlashApplied", "FlashRecovered",
    "EnvironmentalTriggered", "GMOverride", "SessionEnded",
    "make_author_combatant", "make_author_gm", "make_author_engine",
]
