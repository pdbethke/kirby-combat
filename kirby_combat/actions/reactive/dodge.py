"""Dodge — +3 DCV vs all attacks this phase. Aborts next-phase action."""
from __future__ import annotations

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting


_DODGE_DCV_BONUS = 3


class Dodge:
    """Reactive Dodge. Fire-and-forget; read `dcv_bonus` at attack time."""

    name: str = "dodge"

    @staticmethod
    def declare(session: CombatSession, combatant_id: str) -> tuple[CombatSession, AbortDeclared]:
        """Declare a Dodge for this combatant. Marks them as aborting."""
        return mark_aborting(session, combatant_id, to_action="dodge")

    @staticmethod
    def dcv_bonus(session: CombatSession, combatant_id: str) -> int:
        """Return +3 if the combatant is currently dodging this phase, else 0.

        A combatant is "currently dodging" if their most recent AbortDeclared
        event in the log has to_action == "dodge" AND they are still in
        aborted_this_phase (i.e., segment hasn't cycled past their phase).
        """
        from kirby_combat.session.events import AbortDeclared as _AD
        if combatant_id not in session.timeline.aborted_this_phase:
            return 0
        # Find the most recent AbortDeclared for this combatant.
        for evt in reversed(session.event_log):
            if isinstance(evt, _AD) and evt.combatant_id == combatant_id:
                return _DODGE_DCV_BONUS if evt.to_action == "dodge" else 0
        return 0
