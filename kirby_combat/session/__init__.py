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
    EnvironmentalTriggered, ConstructDamaged, ConstructSpawned,
    GMOverride, SessionEnded,
    make_author_combatant, make_author_gm, make_author_engine,
)

__all__ += [
    "CombatEvent", "EventAuthor",
    "SessionStarted", "SegmentAdvanced", "ActionDeclared", "ActionResolved",
    "RecoveryTaken", "MovementResolved", "StatusChanged", "AbortDeclared",
    "HeldActionDeclared", "HeldActionReleased",
    "AdjustmentApplied", "AdjustmentFaded",
    "EntangleApplied", "EntangleEscape", "FlashApplied", "FlashRecovered",
    "EnvironmentalTriggered", "ConstructDamaged", "ConstructSpawned",
    "GMOverride", "SessionEnded",
    "make_author_combatant", "make_author_gm", "make_author_engine",
]

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.apply import apply_event
from kirby_combat.session.rewind import rewind_to_sequence

__all__ += ["CombatSession", "apply_event", "rewind_to_sequence"]
