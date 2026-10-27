"""Dodge — +3 DCV vs all attacks this phase. Aborts next-phase action."""
from __future__ import annotations

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting




class Dodge:
    """Reactive Dodge. Fire-and-forget; read `dcv_bonus` at attack time."""

    name: str = "dodge"

    @staticmethod
    def declare(session: CombatSession, combatant_id: str) -> tuple[CombatSession, AbortDeclared]:
        """Declare a Dodge for this combatant. Marks them as aborting."""
        return mark_aborting(session, combatant_id, to_action="dodge")

    @staticmethod
    def dcv_bonus(session: CombatSession, combatant_id: str) -> int:
        """Return +3 while his Dodge is standing, else 0.

        6E2 p.24: what he aborted to lasts "until his next Phase after"
        the one he gave up --- longer than the lockout, which is why this
        reads the Abort's own window rather than `is_aborting`. The window
        is closed by `apply_event`; his latest Abort is the only one held,
        so a Block declared after a Dodge ends the Dodge.
        """
        window = session.timeline.aborts.get(combatant_id)
        if window is None or window.to_action != "dodge":
            return 0
        # MARTIAL DODGE FEEDS THE PLAIN DODGE (6E2 p.93: +5 against the
        # plain maneuver's +3). Read off his own sheet at the moment the
        # bonus is asked for; see `actions/reactive/martial.py`.
        from kirby_combat.actions.reactive.martial import dodge_maneuver

        return dodge_maneuver(session.combatants[combatant_id]).dcv
