"""Which rows of the record concern one fighter.

A consumer asking "what happened to Talisman" had to know which keys of
which event kinds name a man --- `combatant_id` on most, `target_id` and
`targets` on an action, `victims` and `fell` inside an attack's result,
`caused_by` on a vital. That is the engine's knowledge of its own events,
and kirby-api is not allowed a second opinion about a payload, so the
engine answers it.

RULING: a row concerns him when it names him as the one acting, the one
acted on, or the one who caused a change. A row that merely lists everyone
(the acting order, a Segment advancing) is not something that happened to
him and is left out.
"""
from __future__ import annotations

from typing import Any

#: The keys under which an event, or an action's result, names a man it
#: happened to or who did it.
_NAMING_KEYS = frozenset({
    "combatant_id", "target_id", "caused_by", "attacker_id",
    "targets", "victims", "fell",
    # A squad's leader, named by `SquadLeaderNamed`.
    "leader_id",
})


def _names(value: Any, combatant_id: str) -> bool:
    if isinstance(value, str):
        return value == combatant_id
    if isinstance(value, (list, tuple, set, frozenset)):
        return combatant_id in value
    return False


def _payload_names(payload: Any, combatant_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    for key, value in payload.items():
        if key in _NAMING_KEYS and _names(value, combatant_id):
            return True
        if isinstance(value, dict) and _payload_names(value, combatant_id):
            return True
    return False


def involves(event: Any, combatant_id: str) -> bool:
    """Does this row name him as actor, target, or cause?"""
    for key in _NAMING_KEYS:
        if _names(getattr(event, key, None), combatant_id):
            return True
    return _payload_names(getattr(event, "result_payload", None), combatant_id)


def events_involving(session: Any, combatant_id: str) -> list[Any]:
    """The rows of ``session``'s record that concern ``combatant_id``, in order.

    Raises KeyError for a combatant the fight does not have: an empty answer
    would read as "nothing happened to him".
    """
    if combatant_id not in session.combatants:
        raise KeyError(f"{combatant_id!r} is not in session {session.id!r}")
    return sorted((e for e in session.event_log if involves(e, combatant_id)),
                  key=lambda e: e.sequence)
