"""apply_event — total dispatcher from (session, event) to new session."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActingOrderResolved, ActionDeclared, BleedingSuffered,
    BlockPriorityGained, CombatEvent, PhaseSpent, RecoveryTaken,
    SegmentAdvanced, VitalsChanged,
)
from kirby_combat.session.timeline import restore_acting_order
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
        # The resolved acting order describes ONE Segment -- every ActingSlot
        # carries the `segment` it was built for -- so leaving the Segment
        # invalidates it. Clearing it here, rather than in
        # `Encounter.advance_segment`, keeps any consumer that applies this
        # event coherent, including one replaying a log.
        #
        # This is timeline bookkeeping, not a combatant stat mutation: it
        # does not put this dispatcher in the business the comment further
        # down rules out. The `has_acted` flags are the sharp edge -- a
        # surviving order would carry them into the next Segment and skip a
        # combatant who had only acted in the previous one.
        new_timeline = replace(
            session.timeline,
            segment=event.to_segment,
            turn=event.to_turn,
            acting_order=[],
            current_slot_index=0,
        )
        return replace(session, event_log=new_log, timeline=new_timeline, updated_at=now)

    if kind == "ActingOrderResolved":
        assert isinstance(event, ActingOrderResolved)
        # THE LOOP'S DECISION, APPLIED. Whoever resolved the order emitted
        # this; applying it is what puts the order on the timeline, so a
        # session rebuilt by replaying its log stands in the same Segment
        # with the same people waiting to act as the session that ran.
        #
        # The clock moves with it: the order describes ONE Segment (every
        # slot carries the Segment it was built for) and the Lightning
        # Reflexes guard below matches a slot against
        # `timeline.segment`, so an order arriving without its Segment
        # would be an order nothing could match.
        new_timeline = replace(
            session.timeline,
            segment=event.segment,
            turn=event.turn,
            acting_order=restore_acting_order(
                session.combatants, event.order, event.segment,
                event.intents),
            current_slot_index=0,
            # AND THE BLOCK PRIORITY IS SPENT HERE. 6E2 p.60 gives the
            # successful blocker priority "in the next Phase in which they
            # both act", so an order containing both men IS the spend ---
            # applied AFTER the order was built from it, which is the
            # order `Encounter.run_segment` does these in. No second event
            # for the spend: it would be a second statement of one rule,
            # and the rule is already written down here.
            block_priority={
                blocker: attacker
                for blocker, attacker
                in session.timeline.block_priority.items()
                if not (blocker in set(event.order)
                        and attacker in set(event.order))
            },
        )
        return replace(session, event_log=new_log, timeline=new_timeline, updated_at=now)

    if kind == "PhaseSpent":
        assert isinstance(event, PhaseSpent)
        # The FIRST unspent slot for this combatant, which is exactly what
        # the loop's own marking does -- a combatant with two Phases in
        # one Segment (SPD changes mid-Turn, 6E2 p.20) spends them in
        # order, and a spend event is not addressed to a particular one.
        #
        # A new slot rather than a flag flipped in place: this dispatcher
        # returns a new session, and a slot mutated here would also be
        # spent in the session the caller still holds.
        new_order = list(session.timeline.acting_order)
        for index, slot in enumerate(new_order):
            if slot.combatant_id == event.combatant_id and not slot.has_acted:
                new_order[index] = replace(slot, has_acted=True)
                break
        else:
            # Nothing to spend. Silence here would be the same failure as
            # an order naming a stranger: the replay carries on, one Phase
            # richer than the fight that ran, and nothing says so.
            raise ValueError(
                f"{event.combatant_id!r} has no unspent slot in Segment "
                f"{session.timeline.segment} to spend (order: "
                f"{[(s.combatant_id, s.has_acted) for s in new_order]})"
            )
        new_timeline = replace(session.timeline, acting_order=new_order)
        return replace(session, event_log=new_log, timeline=new_timeline, updated_at=now)

    if kind == "VitalsChanged":
        assert isinstance(event, VitalsChanged)
        return _fold_vitals(
            session, new_log, now, event.combatant_id,
            stun=event.stun, body=event.body, end=event.end,
        )

    if kind == "RecoveryTaken":
        assert isinstance(event, RecoveryTaken)
        # 6E2 p.130's Recovery and p.131's free Post-Segment 12 Recovery,
        # both of them. The event has carried the two numbers in typed
        # fields since it was written and the STUN and END were put back
        # on the combatant BESIDE it, by `Encounter.advance_segment` and
        # by the `recover` resolver -- so a replayed fight never got its
        # wind back. Signs are the event's own: a Recovery GIVES.
        return _fold_vitals(
            session, new_log, now, event.combatant_id,
            stun=event.stun_recovered, end=event.end_recovered,
        )

    if kind == "BleedingSuffered":
        assert isinstance(event, BleedingSuffered)
        # 6E2 p.109 (bleeding to death) and p.115 (the optional wound
        # Bleeding), which is why the event says which rule fired. Both
        # fields are stated as LOSSES, so the fold negates them; the
        # event stays readable as "he lost 1 BODY" rather than "-1".
        return _fold_vitals(
            session, new_log, now, event.combatant_id,
            body=-event.body_lost, stun=-event.stun_lost,
        )

    if kind == "BlockPriorityGained":
        assert isinstance(event, BlockPriorityGained)
        # 6E2 p.60. Onto the timeline, so a fight rebuilt from its rows
        # carries the advantage the fight that ran earned --- see the
        # event's own docstring for the divergence this closes.
        new_timeline = replace(
            session.timeline,
            block_priority={
                **session.timeline.block_priority,
                event.blocker_id: event.attacker_id,
            },
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

    # These events persist to the log and change no combatant stat --- not
    # because stat changes are forbidden here (they are this dispatcher's
    # job now, see `VitalsChanged` above), but because each of these
    # genuinely describes something else:
    #   - Adjustment / Entangle / Flash / Presence: a running effect, folded
    #     forward by kirby_combat/session/effects.py rather than stored
    #   - ActionResolved: the OUTCOME of an action -- what was rolled, what
    #     got through, who was Stunned by it. The STUN and BODY it cost now
    #     ride on their own `VitalsChanged`, emitted beside it, so no fold
    #     has to parse a free-form `result_payload`
    #   - MovementResolved: where a man went. Its END is a `VitalsChanged`
    #     for the same reason
    #   - StatusEffectsChanged: audit-only delta view; the status set itself
    #     is derived from the log by kirby_combat.statuses.statuses_for, so
    #     applying this event must never be what makes a status true
    #   - GMOverride / EnvironmentalTriggered: structural log entries only
    #   - ConstructDamaged / ConstructSpawned: audit-only; construct state
    #     lives in the driver, not the engine session (Plan 2)
    if kind in {
        "ActionResolved", "MovementResolved",
        "StatusChanged", "StatusEffectsChanged", "HeldActionReleased",
        "AdjustmentApplied", "AdjustmentFaded",
        "EntangleApplied", "EntangleEscape",
        "FlashApplied", "FlashRecovered",
        "PresenceApplied", "PresenceFaded", "PresenceActionLost",
        "EnvironmentalTriggered", "GMOverride",
        "ConstructDamaged", "ConstructSpawned",
    }:
        return replace(session, event_log=new_log, updated_at=now)

    raise TypeError(f"unhandled event kind: {kind!r}")


def _fold_vitals(
    session: CombatSession, new_log, now, combatant_id: str,
    *, stun: int = 0, body: int = 0, end: int = 0,
) -> CombatSession:
    """THE ONE WRITER of a combatant's STUN, BODY and END.

    Every event that moves a vital lands here, and nothing outside
    `apply_event` writes one --- which is the whole of what makes a fight
    rebuilt from its rows the same fight. The arithmetic itself, and the
    two combatant shapes it has to dispatch between, stay in
    `kirby_combat.vitals.apply_vitals_delta`; this is the seam between
    the log and that fold, not a second copy of it.

    A combatant the session does not know RAISES. Silence here is the
    failure this whole line of work exists to remove: a replay one man's
    damage lighter than the fight that ran, with nothing saying so. It is
    the same refusal `PhaseSpent` makes for a stranger in the acting
    order.
    """
    from kirby_combat.vitals import apply_vitals_delta

    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        raise ValueError(
            f"{combatant_id!r} is not a combatant in session {session.id!r}: "
            f"known combatants are {sorted(session.combatants)}"
        )
    new_combatants = dict(session.combatants)
    new_combatants[combatant_id] = apply_vitals_delta(
        combatant, stun=stun, body=body, end=end,
    )
    return replace(
        session, event_log=new_log, combatants=new_combatants, updated_at=now,
    )


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

    INERT IN EXACTLY ONE CASE, now. A session whose ``acting_order`` is
    empty -- one that has never had an order resolved for it -- has no
    slot to match, so this stays a silent no-op for it;
    ``test_lightning_reflexes_restriction_is_inert_without_the_driver``
    proves that half with the identical scenario. An order is empty before
    the first resolution and again after ``SegmentAdvanced`` clears it,
    which is not the guard sleeping: until an order is resolved for the
    new Segment, nobody has a Phase in it to be restricted in.

    THE SECOND CASE IS GONE (2026-09-17). It used to be the one that
    mattered: a consumer whose only clock was ``SegmentAdvanced`` above
    left ``acting_order`` holding the PREVIOUS Segment's slots, every one
    of them failing ``slot.segment != session.timeline.segment``, so the
    guard woke for one Segment after each resolution and slept until the
    next. ``ActingOrderResolved`` closes it at both ends: the order and
    its Segment arrive together and ``SegmentAdvanced`` clears the old
    one, so a consumer that replays the log has the same order, the same
    Segment and the same declared intents as the fight that ran --- which
    is what makes this guard refuse, in a replayed fight, exactly what it
    refuses in a live one.
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
