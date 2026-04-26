"""Breakables — objects and structures as Combatants."""
from kirby_combat.breakables.object_combatant import (
    ObjectCombatant, MATERIAL_DEFAULTS,
)
from kirby_combat.breakables.structure import (
    StructuralGraph, StructuralLink, CollapseEvent, CascadeResult,
    cascade_destruction, make_environmental_event_payload,
)

__all__ = [
    "ObjectCombatant", "MATERIAL_DEFAULTS",
    "StructuralGraph", "StructuralLink", "CollapseEvent", "CascadeResult",
    "cascade_destruction", "make_environmental_event_payload",
]
