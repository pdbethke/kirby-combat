"""status_deltas — an opt-in, pure diff surface for publishing status change.

CONTROLLER OVERRIDE (2026-08-27, status-emission Task 4): the original task
brief asked for this to be wired *inside* ``apply_event`` -- diff before/after
per combatant, on every call, and append the resulting ``StatusEffectsChanged``
events to the same log entry as the event just applied. That was rejected
before this module was written:

- ``apply_event`` enforces ``event.sequence == len(session.event_log) + 1``
  (``kirby_combat/session/apply.py``) and raises ``ValueError`` on a mismatch.
- kirby-api calls ``apply_event`` once per event it applies
  (``kirby-api/kirby/combat/services/session_service.py``) and numbers its
  own events as ``row.last_sequence + 1`` (``kirby-api/.../websocket.py``).
  If ``apply_event`` silently appended extra events, the log would grow by
  more than one per call and kirby-api's sequence bookkeeping would desync
  from the engine's, breaking the very next ``apply_event`` call with a
  sequence mismatch it did not cause.

So this module is deliberately **outside** ``apply_event``: a pure function
callers opt into. ``apply_event`` itself is untouched -- signature, body,
and sequence contract identical to before this file existed.

Why a pure diff is the honest model, not a workaround: status is *derived*
(``kirby_combat.statuses.statuses_for`` folds the event log), so the delta
between two sessions is fully determined by their logs. A pure comparison
cannot desync from that derivation the way a stored/mirrored status set
could, and it means a consumer can regenerate the same stream retroactively
from a recorded combat -- exactly the "publish live combat sequences" goal.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from kirby_combat.session.events import (
    EventAuthor, StatusEffectsChanged, make_author_engine,
)
from kirby_combat.statuses import statuses_for

if TYPE_CHECKING:
    from kirby_combat.session.apply import apply_event as _apply_event_type  # noqa: F401
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.events import CombatEvent


def _default_id_factory(sequence: int, combatant_id: str) -> str:
    """Default event-id generator: unique, human-scannable, no collisions
    across a batch (sequence is unique within one ``status_deltas`` call;
    the uuid suffix guards against two calls at the same wall-clock moment
    for the same combatant producing the same id)."""
    return f"status-{combatant_id}-{sequence}-{uuid.uuid4().hex[:8]}"


def status_deltas(
    before: "CombatSession",
    after: "CombatSession",
    *,
    session_id: str,
    start_sequence: int,
    author: EventAuthor | None = None,
    timestamp: datetime | None = None,
    id_factory: Callable[[int, str], str] | None = None,
) -> list[StatusEffectsChanged]:
    """Compute the `StatusEffectsChanged` events between two session states.

    For every combatant id present in *either* session, compares
    ``statuses_for(before, cid)`` with ``statuses_for(after, cid)``. A
    combatant whose set is unchanged (including a combatant absent from
    both, which cannot occur, or present-and-identical) produces **no**
    event. A combatant whose set changed produces exactly one
    `StatusEffectsChanged` carrying every id that appeared (`added`) and
    every id that disappeared (`removed`) between the two snapshots --
    simultaneous changes (e.g. Entangled AND Knocked Out both starting at
    once) collapse into that one event's `added`/`removed` frozensets,
    never split across several events for the same combatant.

    Nothing is appended to any log by this function. It is a pure
    computation over two ``CombatSession`` values; the caller decides
    whether/how to persist or publish the result (see
    `apply_event_with_deltas` below for the common "apply one event, get
    its deltas back" shape -- itself just this function plus a call to
    the untouched `apply_event`).

    Combatants present in only one session -- deliberate handling:
    A combatant can be added mid-fight (a summoned construct, a
    reinforcement) or -- there is no removal path in this engine today,
    but nothing here assumes one won't exist later -- dropped from
    ``after``. Rather than raising ``KeyError`` (``statuses_for`` indexes
    ``session.combatants[combatant_id]`` directly and would raise), this
    function treats the side that lacks the combatant as contributing the
    empty status set. Concretely: a combatant only in ``after`` gets a
    `StatusEffectsChanged` whose `added` is its *entire* current status
    set and whose `removed` is empty (it is "arriving" with those
    conditions already true); a combatant only in ``before`` gets the
    mirror image (`removed` = its entire former set, `added` empty, as
    "departing"). A combatant with an empty status set on the side that
    lacks it and an empty status set on the side that has it (e.g. it
    joined with no conditions at all) produces no event, same as any
    other unchanged pair -- there is nothing to report.

    Recursion is a non-issue (confirmed by reading `statuses.py`):
    `statuses_for` folds only the *condition* event kinds --
    `Entangle`/`Flash`/`Grab`/`HeldAction` sources, plus the `is_ko`
    property and `timeline.aborted_this_phase` -- and does not read
    `StatusEffectsChanged` at all (that event kind appears nowhere in
    `statuses_for`'s body; see `kirby_combat/statuses.py`). So computing
    and even appending a `StatusEffectsChanged` event never changes what
    a later `statuses_for` call returns, and a second `status_deltas` pass
    across the same before/after pair (or across a session that now
    additionally contains the emitted events) finds nothing new. There is
    no fixed point to chase because the emitted event is not one of the
    inputs the derivation reads.

    Cost (stated, not solved -- YAGNI, no cache added here): each of
    `statuses_for`'s four log-scanning sources (`is_entangled`,
    `is_grabbed`, `is_flashed`, `HeldAction.get_pending`) is O(events), so
    one `statuses_for` call is O(events) and this function calls it twice
    (`before`, `after`) per combatant, i.e. O(2 * combatants * events) for
    one `status_deltas` call. Fine for the combats this engine runs
    (short logs, called once per state transition a caller chooses to
    publish, not per tick); measure before adding a cache.

    Sequence/id/timestamp design (so a caller never has to guess this
    module's numbering scheme):

    - `start_sequence`: the sequence number the *first* emitted event
      should carry. Events are emitted in a deterministic order (sorted
      by combatant id, so two calls over identical inputs produce an
      identical list) and numbered consecutively from there:
      `start_sequence`, `start_sequence + 1`, ... This mirrors
      `apply_event`'s own "next sequence" contract (`session/apply.py`)
      without this function reading or mutating any session's
      `event_log` itself -- the caller supplies the number because only
      the caller knows what "next" means for *their* log (see
      `apply_event_with_deltas` for the one built-in answer to that).
    - `id_factory`: `(sequence, combatant_id) -> str`. Defaults to
      `_default_id_factory` (a readable `status-{combatant_id}-{sequence}
      -{random suffix}` string) but callers with their own event-id
      scheme (a DB sequence, a ULID generator) pass their own factory
      instead of this module inventing ids that collide with theirs.
    - `timestamp`: applied to every event this call produces (they are
      conceptually simultaneous -- all observed at the same `after`
      snapshot). Defaults to `datetime.now(timezone.utc)` if omitted.
    - `author`: defaults to `make_author_engine()` since the delta is
      computed, not declared by a combatant or GM.
    """
    if author is None:
        author = make_author_engine()
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    if id_factory is None:
        id_factory = _default_id_factory

    combatant_ids = sorted(set(before.combatants) | set(after.combatants))

    events: list[StatusEffectsChanged] = []
    sequence = start_sequence
    for combatant_id in combatant_ids:
        before_statuses = (
            statuses_for(before, combatant_id)
            if combatant_id in before.combatants
            else frozenset()
        )
        after_statuses = (
            statuses_for(after, combatant_id)
            if combatant_id in after.combatants
            else frozenset()
        )
        if before_statuses == after_statuses:
            continue

        added = after_statuses - before_statuses
        removed = before_statuses - after_statuses
        events.append(
            StatusEffectsChanged(
                id=id_factory(sequence, combatant_id),
                session_id=session_id,
                sequence=sequence,
                timestamp=timestamp,
                author=author,
                combatant_id=combatant_id,
                added=added,
                removed=removed,
            )
        )
        sequence += 1

    return events


def apply_event_with_deltas(
    session: "CombatSession",
    event: "CombatEvent",
    *,
    author: EventAuthor | None = None,
    timestamp: datetime | None = None,
    id_factory: Callable[[int, str], str] | None = None,
) -> tuple["CombatSession", list[StatusEffectsChanged]]:
    """Apply one event via the untouched `apply_event`, then compute the
    `StatusEffectsChanged` deltas it produced.

    Convenience only -- does **not** change `apply_event` in any way (it
    calls it exactly once, unmodified) and does **not** append the
    returned deltas to the new session's `event_log`. If a caller wants
    them persisted, that is a second, explicit `apply_event` call per
    delta (each needs its own next-sequence number, which is exactly why
    `status_deltas`' `start_sequence` is a required keyword rather than
    something this function guesses): the deltas are handed back for the
    caller to decide, matching the "no event for an unchanged combatant,
    nothing appended unless the caller does it" contract `status_deltas`
    itself documents.

    The returned deltas' `start_sequence` is `event.sequence + 1` -- the
    next slot after the event that was just applied, so a caller who does
    choose to append them keeps a contiguous, gap-free sequence.
    """
    from kirby_combat.session.apply import apply_event

    before = session
    after = apply_event(session, event)
    deltas = status_deltas(
        before,
        after,
        session_id=session.id,
        start_sequence=event.sequence + 1,
        author=author,
        timestamp=timestamp,
        id_factory=id_factory,
    )
    return after, deltas
