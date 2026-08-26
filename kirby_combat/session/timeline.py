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
    pre_tiebreak: int
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


def _tie_key(c: StatBlockCombatant) -> tuple[int, int]:
    """The 6E2 p.21 tie ladder: highest INT first, then highest PRE.

    Quoting p.21: "the GM may dispense with the DEX Roll ... the character
    with the highest INT acts first (if their INTs are also tied, use PRE)".

    Note this is the book's *alternative* to a contested DEX Roll, not the
    default -- Task 3 adds the roll and makes this one setting of a
    campaign TieRule. Until then it stays the engine's behaviour, because
    it is what the engine already did (badly) and a deterministic order is
    what the test suite depends on.

    Read through combat_stats(): the flat and HD-shaped participants answer
    differently off the participant itself.
    """
    stats = c.combat_stats()
    return (stats.int_, stats.pre)


def build_acting_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
) -> list[ActingSlot]:
    """Build the acting order for one segment.

    Combatants without a phase in this segment (per SPD chart) are excluded.
    Ordering: highest DEX first; ties broken by higher INT, then by higher
    PRE (6E2 p.21: "the character with the highest INT acts first (if their
    INTs are also tied, use PRE)"); remaining ties broken stably by
    combatant_id.
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
            int_tiebreak, pre_tiebreak = _tie_key(c)
            slots.append(
                ActingSlot(
                    combatant_id=c.id,
                    segment=segment,
                    dex_at_phase=stats.dex,
                    int_tiebreak=int_tiebreak,
                    pre_tiebreak=pre_tiebreak,
                    has_acted=False,
                )
            )
    # Sort by DEX desc, then INT desc, then PRE desc, then stable id asc
    slots.sort(key=lambda s: (-s.dex_at_phase, -s.int_tiebreak,
                             -s.pre_tiebreak, s.combatant_id))
    return slots
