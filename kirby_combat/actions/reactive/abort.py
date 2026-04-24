"""Abort machinery — the shared state change for all reactive defenses."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared, make_author_combatant


def is_aborting(session: CombatSession, combatant_id: str) -> bool:
    """True if the combatant has declared an abort this phase."""
    return combatant_id in session.timeline.aborted_this_phase


def mark_aborting(
    session: CombatSession,
    combatant_id: str,
    *,
    to_action: str,
) -> tuple[CombatSession, AbortDeclared]:
    """Declare an abort for `combatant_id`. Emits AbortDeclared.

    Returns the new session (with the event appended and timeline updated) and
    the event itself.

    Raises ValueError if the combatant has already aborted this phase.
    """
    from kirby_combat.session.apply import apply_event

    if is_aborting(session, combatant_id):
        raise ValueError(
            f"combatant {combatant_id!r} has already aborted this phase"
        )

    evt = AbortDeclared(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id,
        to_action=to_action,
    )
    return apply_event(session, evt), evt
