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

    THE SEAM THIS ADDED: before this, ``apply_event`` performed no
    action-legality validation at all -- ``ActionDeclared`` was a pure
    passthrough (see this module's history). This is the enforcement
    point, deliberately as small as the rule requires:
    it looks for a *resolved* ``ActingSlot`` (``session.timeline.
    acting_order``, this segment, this combatant -- populated by whoever
    ran ``resolve_acting_order`` for the segment and stored the result on
    the timeline) and, if one exists and `restriction_for_slot` says it is
    restricted, raises when ``event.action_type`` disagrees.

    HONEST LIMIT (WIRED -- was a documented no-op): ``Encounter.
    run_segment`` (``kirby_combat/encounter.py``) is now the "whoever" this
    docstring used to say did not exist -- it resolves one scene-wide
    order via ``resolve_acting_order`` and writes each session's slice of
    it onto that session's ``Timeline.acting_order``. A ``CombatSession``
    that has been through ``Encounter.run_segment`` for the current
    Segment therefore DOES carry a matching resolved slot here, and this
    check fires for real, through that path --
    ``tests/session/test_apply.py::
    test_lightning_reflexes_restriction_fires_through_driver_built_session``
    proves it by building its session with ``run_segment`` rather than by
    hand.

    STILL INERT, precisely: a session that has never been run through
    ``Encounter.run_segment`` (or any other future caller that populates
    ``acting_order``) still starts with an empty ``acting_order``, so the
    loop below finds no matching slot and this remains a silent no-op for
    it --
    ``test_lightning_reflexes_restriction_is_inert_without_the_driver``
    proves that half too, with the identical scenario. The mechanism was
    always real; what changed is that a real call path now feeds it.
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
