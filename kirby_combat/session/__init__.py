"""CombatSession state machine and related types."""
from kirby_combat.session.timeline import (
    Timeline,
    ActingSlot,
    ActionIntent,
    HeldAction,
    build_acting_order_for_segment,
    build_provisional_order_for_segment,
    resolve_acting_order,
    consume_block_priority,
)

__all__ = [
    "Timeline",
    "ActingSlot",
    "ActionIntent",
    "HeldAction",
    "build_acting_order_for_segment",
    "build_provisional_order_for_segment",
    "resolve_acting_order",
    "consume_block_priority",
]

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

# status_deltas / apply_event_with_deltas (kirby_combat.session.status_emission)
# are deliberately NOT re-exported here: that module imports
# kirby_combat.statuses, which imports kirby_combat.actions, which imports
# kirby_combat.template, which imports kirby_combat.session.tie_rule --
# re-entering this very package while it is still initializing. Importing
# status_emission eagerly from this __init__ makes that a circular import
# (proved: it broke `CombatTemplate` import with a partial-module error).
# Callers import it directly: `from kirby_combat.session.status_emission
# import status_deltas, apply_event_with_deltas`.
