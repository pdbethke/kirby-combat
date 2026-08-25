"""Timeline — SPD-chart phase resolution + acting order for a segment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from kirby_combat.models import StatBlockCombatant
from kirby_combat.tables import segments_for_spd


@dataclass
class ActingSlot:
    """One combatant's slot in a single segment's acting order."""
    combatant_id: str
    segment: int
    dex_at_phase: int
    int_tiebreak: int
    has_acted: bool = False


@dataclass
class HeldAction:
    """A declared 'I act when X happens' slot."""
    combatant_id: str
    declared_at_sequence: int
    trigger_description: str
    for_action_type: str | None  # None = TBD when released


@dataclass
class Timeline:
    """Mutable timeline state for a CombatSession."""
    turn: int
    segment: int
    acting_order: list[ActingSlot]
    current_slot_index: int
    held_actions: list[HeldAction] = field(default_factory=list)
    aborted_this_phase: set[str] = field(default_factory=set)


def _combatant_int(c: StatBlockCombatant) -> int:
    """HERO characters don't have INT as a first-class field in our model
    today. We use EGO as the DEX-tie breaker per 6E convention (EGO tiebreak
    when INT unset); if both match, stable order by combatant_id.

    Read through combat_stats(), never off the participant: the flat shape
    answered `.ego` directly and the HD-shaped one does not, which is the
    difference the no-op shim was hiding.
    """
    stats = c.combat_stats()
    return getattr(stats, "int_", getattr(stats, "ego", 10))


def build_acting_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
) -> list[ActingSlot]:
    """Build the acting order for one segment.

    Combatants without a phase in this segment (per SPD chart) are excluded.
    Ordering: highest DEX first; ties broken by higher INT (EGO fallback);
    remaining ties broken stably by combatant_id.
    """
    slots: list[ActingSlot] = []
    for c in combatants:
        # Read via combat_stats() once per combatant, not `.dex`/`.spd`
        # directly: those flat attributes only exist on the
        # StatBlockCombatant shape, and reading them here is exactly the
        # no-op shim this task removes (session/ must work for the HD-shaped
        # participant too).
        stats = c.combat_stats()
        if segment in segments_for_spd(stats.spd):
            slots.append(
                ActingSlot(
                    combatant_id=c.id,
                    segment=segment,
                    dex_at_phase=stats.dex,
                    int_tiebreak=_combatant_int(c),
                    has_acted=False,
                )
            )
    # Sort by DEX desc, then INT desc, then stable id asc
    slots.sort(key=lambda s: (-s.dex_at_phase, -s.int_tiebreak, s.combatant_id))
    return slots
