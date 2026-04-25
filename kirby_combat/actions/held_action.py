"""Held Action — phase consumed; releases on trigger (6E2 pg 73)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    HeldActionDeclared,
    HeldActionReleased,
    make_author_combatant,
    make_author_engine,
)


class HeldAction:
    """Held Action — combatant holds their phase until a trigger fires.

    Phase is consumed on declare. The original DEX/OCV are preserved (used
    at release time per the normal action resolution flow).
    """

    name: str = "held_action"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
        *,
        trigger_condition: str,
        for_action: str | None = None,
    ) -> tuple[CombatSession, HeldActionDeclared]:
        """Record a held action with its trigger condition.

        Phase is consumed. The combatant waits until trigger_condition is met
        before acting.

        Args:
            session: Current combat session.
            combatant_id: The combatant holding their action.
            trigger_condition: Human-readable description of the trigger.
            for_action: Optional action type the combatant intends to take
                when the trigger fires (e.g. "strike", "blast").

        Returns:
            (new_session, HeldActionDeclared event)
        """
        from kirby_combat.session.apply import apply_event

        evt = HeldActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            trigger_condition=trigger_condition,
            for_action=for_action,
        )
        return apply_event(session, evt), evt

    @staticmethod
    def release(
        session: CombatSession,
        held_event_id: str,
        *,
        trigger_observed: str,
    ) -> tuple[CombatSession, HeldActionReleased]:
        """Release a previously declared held action when its trigger fires.

        Args:
            session: Current combat session.
            held_event_id: The id of the HeldActionDeclared event to release.
            trigger_observed: Human-readable description of the trigger that fired.

        Returns:
            (new_session, HeldActionReleased event)

        Raises:
            ValueError: If held_event_id does not reference a known pending held action.
        """
        from kirby_combat.session.apply import apply_event

        # Validate that the held_event_id references an existing, un-released declaration.
        pending_ids = {e.id for e in HeldAction.get_pending_all(session)}
        if held_event_id not in pending_ids:
            raise ValueError(
                f"No pending held action with id {held_event_id!r}"
            )

        evt = HeldActionReleased(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            held_event_id=held_event_id,
            trigger_observed=trigger_observed,
        )
        return apply_event(session, evt), evt

    @staticmethod
    def get_pending(session: CombatSession, combatant_id: str) -> list[HeldActionDeclared]:
        """Return all un-released HeldActionDeclared events for this combatant.

        An event is "released" if there exists a HeldActionReleased with
        held_event_id == declared.id anywhere in the log after the declaration.
        """
        # Collect all released event ids.
        released_ids: set[str] = {
            evt.held_event_id
            for evt in session.event_log
            if isinstance(evt, HeldActionReleased)
        }

        return [
            evt
            for evt in session.event_log
            if (
                isinstance(evt, HeldActionDeclared)
                and evt.combatant_id == combatant_id
                and evt.id not in released_ids
            )
        ]

    @staticmethod
    def get_pending_all(session: CombatSession) -> list[HeldActionDeclared]:
        """Return all un-released HeldActionDeclared events for any combatant."""
        released_ids: set[str] = {
            evt.held_event_id
            for evt in session.event_log
            if isinstance(evt, HeldActionReleased)
        }

        return [
            evt
            for evt in session.event_log
            if isinstance(evt, HeldActionDeclared) and evt.id not in released_ids
        ]
