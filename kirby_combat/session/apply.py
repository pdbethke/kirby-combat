"""apply_event — total dispatcher from (session, event) to new session."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, CombatEvent, SegmentAdvanced,
)
from kirby_combat.talents.lightning_reflexes import restriction_for_slot


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

    if kind == "ActionDeclared":
        assert isinstance(event, ActionDeclared)
        _enforce_lightning_reflexes_phase_restriction(session, event)
        return replace(session, event_log=new_log, updated_at=now)

    # Declaration events don't mutate snapshot.
    if kind in {"HeldActionDeclared"}:
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
    #   - ConstructDamaged / ConstructSpawned: audit-only; construct state
    #     lives in the driver, not the engine session (Plan 2)
    # Rewind correctness depends on this — combatant stat mutations in apply
    # would force log replay to mirror combatant state, which is more brittle.
    if kind in {
        "ActionResolved", "RecoveryTaken", "MovementResolved",
        "StatusChanged", "HeldActionReleased",
        "AdjustmentApplied", "AdjustmentFaded",
        "EntangleApplied", "EntangleEscape",
        "FlashApplied", "FlashRecovered",
        "EnvironmentalTriggered", "GMOverride",
        "ConstructDamaged", "ConstructSpawned",
    }:
        return replace(session, event_log=new_log, updated_at=now)

    raise TypeError(f"unhandled event kind: {kind!r}")


def _enforce_lightning_reflexes_phase_restriction(
    session: CombatSession, event: ActionDeclared,
) -> None:
    """6E1 p.116(c): "he may only execute the specific Action or maneuver
    he purchased Lightning Reflexes for... no movement, acrobatics, or
    other Actions" in a Phase where he elects the bonus.

    THE SEAM THIS TASK ADDED: before this task, ``apply_event`` performed
    no action-legality validation at all -- ``ActionDeclared`` was a pure
    passthrough (see this module's history / the task-8 report). This is
    the enforcement point, deliberately as small as the rule requires:
    it looks for a *resolved* ``ActingSlot`` (``session.timeline.
    acting_order``, this segment, this combatant -- populated by whoever
    ran ``resolve_acting_order`` for the segment and stored the result on
    the timeline) and, if one exists and `restriction_for_slot` says it is
    restricted, raises when ``event.action_type`` disagrees.

    HONEST LIMIT: nothing in this codebase currently writes a resolved
    order onto ``session.timeline.acting_order`` during a live combat (no
    driver wires ``resolve_acting_order``'s output back onto the
    session) -- so in today's actual call paths this check is always a
    no-op (the loop below finds no matching slot and returns silently).
    The mechanism is real and is exercised directly in
    ``tests/session/test_apply.py`` by constructing a session whose
    timeline already carries a resolved slot, which is the shape a future
    driver would produce; wiring a driver to populate ``acting_order`` is
    out of this task's scope.
    """
    for slot in session.timeline.acting_order:
        if slot.combatant_id != event.combatant_id:
            continue
        if slot.segment != session.timeline.segment:
            continue
        restriction = restriction_for_slot(slot)
        if restriction is not None and restriction != event.action_type:
            raise ValueError(
                f"{event.combatant_id} elected Lightning Reflexes for "
                f"{restriction!r} this Phase (6E1 p.116): may not also "
                f"declare {event.action_type!r}"
            )
        return
