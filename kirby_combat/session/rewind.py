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

    # THE MEN AS THE FIGHT FOUND THEM, not as it left them. This seeded
    # the replay with `session.combatants`, which was harmless only while
    # `apply_event` folded no vitals: now that it does, seeding with the
    # current combatants would replay every point of damage on top of the
    # damage already done -- a rewind to sequence 1 would return a
    # session more hurt than the fight ever got.
    #
    # AND THE BOARD AS THE FIGHT FOUND IT, for exactly the same reason,
    # one field over. This seeded the replay with `session.scene` -- the
    # placement the fight ENDED in -- and `apply_event` folds
    # `MovementResolved` now, so a rewind to sequence 1 returned a
    # session in which nobody had moved yet and everybody was standing
    # where they finished. Measured: all three fighters on one spot at
    # `SessionStarted`.
    fresh = CombatSession.create(
        id=session.id,
        combatants=list((session.initial_combatants or session.combatants).values()),
        scene=(session.initial_scene.snapshot()
               if session.initial_scene is not None else None),
        template=session.template,
        dice_roller=session.dice_roller,
    )
    for e in kept:
        fresh = apply_event(fresh, e)

    return replace(fresh, updated_at=datetime.now(timezone.utc))
