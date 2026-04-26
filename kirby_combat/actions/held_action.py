"""Held Action — phase consumed; releases on trigger (6E2 p61 §HOLD AN ACTION).

Per 6E2 p61: a character may declare 'I'll wait until X happens' on his phase,
giving up his current Phase to act when X does happen. The held action expires
when the holder's NEXT phase begins (he can't hold across his own phase
indefinitely) — at which point the saved phase is lost.

This module adds three capabilities on top of the basic declare/release:
    * `release_on_event` — match a CombatEvent against a held action's
      trigger predicate and release if it matches.
    * `release_with_resolution` — release + immediately resolve the held
      action as a normal action this segment (the released action runs).
    * `expire_for_combatant_next_phase` — drop pending held actions when
      the owner's next phase begins, per 6E2 p61.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared,
    ActionResolved,
    CombatEvent,
    HeldActionDeclared,
    HeldActionReleased,
    make_author_combatant,
    make_author_engine,
)


@dataclass(frozen=True)
class HeldReleaseResolution:
    """Result of release_with_resolution — release plus the new declaration."""
    released: HeldActionReleased
    new_declaration: ActionDeclared
    new_resolution: ActionResolved


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

    # ------------------------------------------------------------------ release_on_event
    @staticmethod
    def release_on_event(
        session: CombatSession,
        observed_event: CombatEvent,
        *,
        match: Callable[[HeldActionDeclared, CombatEvent], bool],
    ) -> tuple[CombatSession, list[HeldActionReleased]]:
        """Release every pending held action whose trigger matches `observed_event`.

        `match(held, event)` is a predicate the caller supplies. The default
        notion of "matching" is intentionally pluggable — game-flow code may
        want exact-string match, regex, or a richer event-shape match.

        Returns the new session (with one HeldActionReleased per match
        appended in declaration order) and the list of released events.
        """
        from kirby_combat.session.apply import apply_event

        released_events: list[HeldActionReleased] = []
        s = session
        for held in HeldAction.get_pending_all(session):
            if not match(held, observed_event):
                continue
            evt = HeldActionReleased(
                id=str(uuid.uuid4()),
                session_id=s.id,
                sequence=len(s.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine(),
                held_event_id=held.id,
                trigger_observed=getattr(observed_event, "kind", "") or "",
            )
            s = apply_event(s, evt)
            released_events.append(evt)
        return s, released_events

    # ------------------------------------------------------------------ release_with_resolution
    @staticmethod
    def release_with_resolution(
        session: CombatSession,
        held_event_id: str,
        *,
        trigger_observed: str,
        action_type: str,
        targets: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> tuple[CombatSession, HeldReleaseResolution]:
        """Release a held action AND emit ActionDeclared + ActionResolved.

        Models 'released held action resolves like a normal action this
        segment' — the held action 'becomes' a normal action right after
        the trigger fires. Caller supplies the action_type/targets/parameters
        of what the held character is now doing.

        Returns (new_session, HeldReleaseResolution(released, declared, resolved)).
        """
        from kirby_combat.session.apply import apply_event

        # Find the holding combatant for the declaration we're about to emit
        held = next(
            (e for e in HeldAction.get_pending_all(session) if e.id == held_event_id),
            None,
        )
        if held is None:
            raise ValueError(f"No pending held action with id {held_event_id!r}")

        s, released_evt = HeldAction.release(
            session, held_event_id, trigger_observed=trigger_observed,
        )

        declared_evt = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(held.combatant_id),
            combatant_id=held.combatant_id,
            action_type=action_type,
            targets=list(targets or []),
            parameters=dict(parameters or {}),
        )
        s = apply_event(s, declared_evt)

        resolved_evt = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(held.combatant_id),
            declaration_event_id=declared_evt.id,
            result_payload=dict(result_payload or {}),
        )
        s = apply_event(s, resolved_evt)

        return s, HeldReleaseResolution(
            released=released_evt,
            new_declaration=declared_evt,
            new_resolution=resolved_evt,
        )

    # ------------------------------------------------------------------ expire_for_combatant_next_phase
    @staticmethod
    def expire_for_combatant_next_phase(
        session: CombatSession, combatant_id: str,
    ) -> tuple[CombatSession, list[HeldActionReleased]]:
        """Expire all of `combatant_id`'s pending held actions.

        Per 6E2 p61: a held action expires when the holder's next phase
        begins. This is modelled as a HeldActionReleased event with
        trigger_observed="phase_expired" — the held action is consumed
        without resolution.

        Returns (new_session, list-of-expiry-events).
        """
        from kirby_combat.session.apply import apply_event

        s = session
        emitted: list[HeldActionReleased] = []
        for held in HeldAction.get_pending(session, combatant_id):
            evt = HeldActionReleased(
                id=str(uuid.uuid4()),
                session_id=s.id,
                sequence=len(s.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine(),
                held_event_id=held.id,
                trigger_observed="phase_expired",
            )
            s = apply_event(s, evt)
            emitted.append(evt)
        return s, emitted
