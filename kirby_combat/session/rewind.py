"""Rewind — truncate event log and replay from sequence 0."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession


def rewind_to_sequence(session: CombatSession, target_sequence: int) -> CombatSession:
    """Return a new session with events > target_sequence removed.

    target_sequence=0 returns a session with empty event_log in setup status.
    target_sequence >= len(event_log) is a no-op.
    """
    from kirby_combat.session.apply import apply_event

    if target_sequence >= len(session.event_log):
        return session

    kept = [e for e in session.event_log if e.sequence <= target_sequence]

    fresh = CombatSession.create(
        id=session.id,
        combatants=list(session.combatants.values()),
        scene=session.scene,
        template=session.template,
        dice_roller=session.dice_roller,
    )
    for e in kept:
        fresh = apply_event(fresh, e)

    return replace(fresh, updated_at=datetime.now(timezone.utc))
