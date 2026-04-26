"""apply_event — total dispatcher from (session, event) to new session."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    CombatEvent, SegmentAdvanced,
)


def apply_event(session: CombatSession, event: CombatEvent) -> CombatSession:
    """Apply one event, returning the new session state.

    Raises ValueError if event.sequence is not the next expected sequence.
    Raises TypeError on unknown event kinds.
    """
    expected = len(session.event_log) + 1
    if getattr(event, "sequence", None) != expected:
        raise ValueError(
            f"event sequence mismatch: expected {expected}, got {getattr(event, 'sequence', None)}"
        )

    new_log = [*session.event_log, event]
    now = datetime.now(timezone.utc)

    kind = getattr(event, "kind", None)

    if kind == "SessionStarted":
        return replace(session, event_log=new_log, status="active", updated_at=now)

    if kind == "SessionEnded":
        return replace(session, event_log=new_log, status="ended", updated_at=now)

    if kind == "SegmentAdvanced":
        assert isinstance(event, SegmentAdvanced)
        new_timeline = replace(
            session.timeline,
            segment=event.to_segment,
            turn=event.to_turn,
        )
        return replace(session, event_log=new_log, timeline=new_timeline, updated_at=now)

    # Declaration events don't mutate snapshot.
    if kind in {"ActionDeclared", "HeldActionDeclared"}:
        return replace(session, event_log=new_log, updated_at=now)

    if kind == "AbortDeclared":
        from kirby_combat.session.events import AbortDeclared as _AD
        assert isinstance(event, _AD)
        new_aborted = set(session.timeline.aborted_this_phase)
        new_aborted.add(event.combatant_id)
        new_timeline = replace(session.timeline, aborted_this_phase=new_aborted)
        return replace(session, event_log=new_log, timeline=new_timeline, updated_at=now)

    # These events persist to the log; per-event semantics live in derivation
    # helpers rather than mutating Combatant fields:
    #   - Adjustment / Entangle / Flash:  kirby_combat/session/effects.py
    #   - Recovery / status / movement:   resolved at action time, not on apply
    #   - GMOverride / EnvironmentalTriggered: structural log entries only
    # Rewind correctness depends on this — combatant stat mutations in apply
    # would force log replay to mirror combatant state, which is more brittle.
    if kind in {
        "ActionResolved", "RecoveryTaken", "MovementResolved",
        "StatusChanged", "HeldActionReleased",
        "AdjustmentApplied", "AdjustmentFaded",
        "EntangleApplied", "EntangleEscape",
        "FlashApplied", "FlashRecovered",
        "EnvironmentalTriggered", "GMOverride",
    }:
        return replace(session, event_log=new_log, updated_at=now)

    raise TypeError(f"unhandled event kind: {kind!r}")
