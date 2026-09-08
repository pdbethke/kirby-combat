"""What a combatant is carrying, folded from the fight's own log.

`enumerate_actions` offers `throw_object` only when told `actor_holding`
and `held_construct_id`. Both are parameters and nothing populated them,
so `pickup` resolved, the log recorded it, and the next Phase's menu had
no idea --- Power Lad lifted the same freight wagon eleven times and never
threw it.

Same gap `slot_allocation` had until `allocation_for` assembled it: a
fact that lives in the log, which the caller was expected to track by
hand and never did.

ABSOLUTE, NOT A DELTA. The latest pickup or throw wins, which is the
discipline every other fold in this engine holds to --- `active_slots`,
the presence tiers, the status folds. A delta is unrecoverable the moment
one is missed.
"""
from __future__ import annotations

from typing import Any

#: Resolutions that change what is in somebody's hands.
_TAKES = "pickup"
_RELEASES = frozenset({"throw_object", "release_held"})


def held_object(session: Any, combatant_id: str) -> str | None:
    """The object this combatant is holding, or None.

    Attribution needs both halves of the pair the resolvers emit ---
    `ActionDeclared` carries who, `ActionResolved` carries what, joined on
    `declaration_event_id`.
    """
    log = list(getattr(session, "event_log", None) or [])
    mine: set[str] = set()
    holding: str | None = None
    for event in log:
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared":
            if getattr(event, "combatant_id", "") == combatant_id:
                mine.add(getattr(event, "id", ""))
        elif kind == "ActionResolved":
            if getattr(event, "declaration_event_id", "") not in mine:
                continue
            payload = getattr(event, "result_payload", None) or {}
            action = payload.get("kind")
            if action == _TAKES:
                holding = payload.get("object_id") or None
            elif action in _RELEASES:
                holding = None
    return holding
