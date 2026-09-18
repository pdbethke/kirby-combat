"""status_emission — THE ONE DOOR a condition goes through to reach the log.

WHAT WAS WRONG WITH IT (measured 2026-09-18, Krackle's checkpoint gate).
This module held a pure diff (``status_deltas``) and one convenience
wrapper, ``apply_event_with_deltas``, that handed the diff back to a
caller to persist "if it wants to". **Nothing in the engine called that
wrapper, and nothing anywhere emitted a ``StatusEffectsChanged``** -- so
no condition this engine produces ever reached the log as a row.
Knocked out, stunned, prone, held, entangled, flashed: a viewer reading
the record could not know a man had gone down.

``record_status_changes`` below is the door that closes it. It is the
ONE emitter: it diffs the RULE (``statuses.statuses_for``) against the
RECORD (``CombatSession.statuses``, folded by ``apply_event`` out of
these very rows) and emits one ``StatusEffectsChanged`` per combatant
whose set has moved. ``loop/run.py::run_phase`` -- this engine's one step
door -- calls it on every exit, so every Phase that changes a condition
writes the change down.

The wrapper is deleted. A door nothing goes through is not a door.

CONTROLLER OVERRIDE (2026-08-27, status-emission Task 4), KEPT because it
is still the reason the emission is not *inside* ``apply_event``: the
original task brief asked for this to be wired *inside* ``apply_event`` --
diff before/after per combatant, on every call, and append the resulting
``StatusEffectsChanged`` events to the same log entry as the event just
applied. That was rejected before this module was written:

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
could -- **for a session whose logs are complete.** A consumer can
regenerate the same stream retroactively from a recorded combat only when
both snapshots come from a session the engine built end-to-end (every
event replayed through ``apply_event``), or from a session rehydrated
*with* its full ``event_log`` and ``timeline.aborted_this_phase``. It is
NOT true of kirby-api's live rehydrate path, which supplies neither (see
``kirby_combat.statuses.statuses_for``'s Preconditions section for the
exact lines and the resulting failure mode). "Publish live combat
sequences" is the goal this was built for; it is reachable today only via
the first two shapes above, not via kirby-api's current rehydration.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    EventAuthor, StatusEffectsChanged, make_author_engine,
)
from kirby_combat.statuses import statuses_for

if TYPE_CHECKING:
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
    whether/how to persist or publish the result. The engine's own
    caller is `record_status_changes` below, which is the one door
    between this diff and the log.

    Preconditions (inherited from ``statuses_for``, called twice per
    combatant here): both `before` and `after` must be sessions whose
    ``event_log`` carries the *complete* history and whose
    ``timeline.aborted_this_phase`` has been populated by every abort
    applied so far. A session engine-built end-to-end via `apply_event`
    satisfies this by construction. kirby-api's rehydrated session does
    not -- see ``kirby_combat.statuses.statuses_for``'s own Preconditions
    section for the exact lines and the resulting failure mode (a diff
    across two such sessions can miss a real transition, e.g. an
    Entangle-then-Escape reads as no change at all).

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
    `statuses_for` folds SEVEN log-scanning sources -- `Entangle`/`Flash`/
    `Grab`/`HeldAction` (unchanged since this was first written), plus
    `ActionResolved.result_payload["status_changes"]` (Stunned/Dead/a
    payload-derived Knocked Out), `SegmentAdvanced` (Stunned's clear edge,
    6E2 p.107), and `RecoveryTaken` (the payload-derived Knocked Out's
    clear edge, 6E2 p.131) -- plus the `is_ko` property and
    `timeline.aborted_this_phase`, neither log-scanning. It does not read
    `StatusEffectsChanged` at all (that event kind appears nowhere in
    `statuses_for`'s body; see `kirby_combat/statuses.py`). So computing
    and even appending a `StatusEffectsChanged` event never changes what
    a later `statuses_for` call returns, and a second `status_deltas` pass
    across the same before/after pair (or across a session that now
    additionally contains the emitted events) finds nothing new. There is
    no fixed point to chase because the emitted event is not one of the
    inputs the derivation reads.

    Cost (stated, not solved -- YAGNI, no cache added here): each of
    `statuses_for`'s seven log-scanning sources (`is_entangled`,
    `is_grabbed`, `is_flashed`, `HeldAction.get_pending`, `_is_stunned`,
    `_is_dead`, `_is_knocked_out_from_payload`) is O(events), so
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


def record_status_changes(
    session: "CombatSession",
    *,
    author: EventAuthor | None = None,
    timestamp: datetime | None = None,
    id_factory: Callable[[int, str], str] | None = None,
) -> tuple["CombatSession", list[StatusEffectsChanged]]:
    """THE ONE EMITTER: write down every condition that has changed.

    Compares, for each combatant, the RULE --- ``statuses_for``, which is
    what makes a condition true --- against the RECORD, ``session
    .statuses``, which ``apply_event`` folds out of the rows this
    function emits. Where they differ, one ``StatusEffectsChanged`` is
    emitted and applied, and they agree again.

    Returns ``(session, events)``. A fight in which nothing changed
    returns the session it was handed and an empty list --- a row saying
    "still knocked out" is noise the record does not need, the same
    principle ``record_vitals_change`` applies to a zero delta.

    THE DIFF IS AGAINST THE FOLD, not against a `before` session. Two
    sessions is what ``status_deltas`` above takes, and it is the right
    shape for a consumer publishing a transition it already holds both
    sides of; it is the wrong shape here, because the question this
    function answers is "does the record still say what the rule says",
    and the record is one object.

    WHY IT CANNOT LOOP. ``statuses_for`` reads
    ``StatusEffectsChanged`` in exactly one place --- Prone's clear edge,
    which fires only on a row that names ``PRONE`` in ``removed``, and
    this function emits a removal only when the rule has ALREADY stopped
    saying Prone. So an emitted row can never be what makes the next
    diff non-empty; a second call over the same session emits nothing.

    Cost: one ``statuses_for`` per combatant, which is O(events) each ---
    the same order as one ``status_deltas`` call, half the calls. It runs
    once per Phase, not once per event.
    """
    if author is None:
        author = make_author_engine()
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    if id_factory is None:
        id_factory = _default_id_factory

    emitted: list[StatusEffectsChanged] = []
    for combatant_id in sorted(session.combatants):
        rule = statuses_for(session, combatant_id)
        record = session.statuses[combatant_id]
        if rule == record:
            continue
        sequence = len(session.event_log) + 1
        event = StatusEffectsChanged(
            id=id_factory(sequence, combatant_id),
            session_id=session.id,
            sequence=sequence,
            timestamp=timestamp,
            author=author,
            combatant_id=combatant_id,
            added=rule - record,
            removed=record - rule,
        )
        session = apply_event(session, event)
        emitted.append(event)

    return session, emitted
