"""Abort machinery — the shared state change for all reactive defenses."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared, make_author_combatant


def is_aborting(session: CombatSession, combatant_id: str) -> bool:
    """True while an Abort locks him out (6E2 p.24): from the declaration
    until the Phase he gave up has passed."""
    return combatant_id in session.timeline.aborted_this_phase


def abort_windows(
    session: CombatSession, combatant_id: str,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Which Phase an Abort declared now gives up, and when its bonus ends.

    6E2 p.24, "HOW TO ABORT AN ACTION". The Phase given up is THIS
    Segment's if he has one here and has not yet used it ("he still had
    his full Phase left in Segment 5 and could use it to Abort to Dodge"),
    and otherwise his next one (Lazer, attacked in Segment 6, gives up
    Segment 8). The bonus lasts "until his next Phase after that".

    Both read his SPD as it stands NOW, and are recorded on the event, so
    a later Drain does not move a window already opened.
    """
    from kirby_combat.session.timeline import next_phase
    from kirby_combat.tables import segments_for_spd

    timeline = session.timeline
    phases = segments_for_spd(
        session.combatants[combatant_id].combat_stats().spd)
    used_this_segment = any(
        slot.combatant_id == combatant_id and slot.has_acted
        and slot.segment == timeline.segment
        for slot in timeline.acting_order
    )
    aborted = next_phase(
        phases, timeline.turn, timeline.segment,
        inclusive=not used_this_segment,
    )
    bonus_until = next_phase(phases, *aborted, inclusive=False)
    return aborted, bonus_until


def mark_aborting(
    session: CombatSession,
    combatant_id: str,
    *,
    to_action: str,
) -> tuple[CombatSession, AbortDeclared]:
    """Declare an abort for `combatant_id`. Emits AbortDeclared.

    Returns the new session (with the event appended and timeline updated) and
    the event itself.

    Raises ValueError if the combatant has already aborted this phase, OR
    (6E2 p.106, "Stunning": "The character remains Stunned and can take no
    Action until his next Phase (he cannot even Abort to a defensive
    Action). A character who's Stunned or recovering from being Stunned
    can take no Actions...") if the combatant is currently Stunned or
    recovering from being Stunned. The WIDER window (not merely the
    narrower ``stunned`` status id) is deliberate: the quoted second
    sentence generalizes "can take no Actions" -- which an Abort
    declaration is -- to both states explicitly, matching
    ``statuses.py::stunned_or_recovering_for``'s own docstring and the
    identical window `cv_modifiers.py` uses for the DCV/DMCV penalty.

    No new parameter: `session` and `combatant_id` were already this
    function's inputs, so the Stunned check reads `statuses_for` on them
    directly rather than growing the signature. This is the single choke
    point for every reactive-abort path in the engine -- `Dodge.declare`,
    `Block.declare`, `dive_for_cover.py`, and
    `actions/recording.py::resolve_block_in_session` all call THIS
    function rather than emitting `AbortDeclared` themselves -- so denying
    it here denies Abort-to-Dodge and Abort-to-Block (and Dive for Cover)
    in one place, matching the rule's own "he cannot even Abort to a
    defensive Action" (no carve-out by which defensive Action).

    Denial style: raises ValueError, matching the sibling precondition
    failure two lines below (`is_aborting`) -- both are "this Action is
    not legal for this combatant right now" refusals at the same call
    site, and every existing caller already has to handle mark_aborting
    raising.
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.statuses import stunned_or_recovering_for

    if is_aborting(session, combatant_id):
        raise ValueError(
            f"combatant {combatant_id!r} has already aborted this phase"
        )
    if stunned_or_recovering_for(session, combatant_id):
        raise ValueError(
            f"combatant {combatant_id!r} is Stunned (or recovering from "
            "being Stunned) and cannot Abort to a defensive Action "
            "(6E2 p.106)"
        )

    (aborted_turn, aborted_segment), (bonus_turn, bonus_segment) = (
        abort_windows(session, combatant_id))
    evt = AbortDeclared(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id,
        to_action=to_action,
        aborted_turn=aborted_turn,
        aborted_segment=aborted_segment,
        bonus_until_turn=bonus_turn,
        bonus_until_segment=bonus_segment,
    )
    return apply_event(session, evt), evt
