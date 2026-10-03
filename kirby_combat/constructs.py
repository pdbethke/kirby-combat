"""What a fight has done to the things in a place.

A `Construct` is frozen, and a place does not keep a ledger of what happened
to it --- the fight does, in its event log. So the fold lives here, and the
place is handed the totals: `kirby_world.construct.constructs_in(scene,
damage=...)`.

`constructs_in(scene, session)` keeps the signature it always had, so callers
and anyone importing it from `kirby_combat.scene.construct` are unaffected.
"""
from __future__ import annotations

from kirby_world.construct import Construct
from kirby_world.construct import constructs_in as _place_constructs


def damage_taken(session, obj_id: str) -> int:
    """BODY this construct has lost so far in this fight.

    `Construct` is frozen and its own contract says so: "a Construct's
    `body` is the CURRENT body for one resolution; damage flows out as
    events and back via DRIVER HYDRATION on the next step." The driver was
    kirby-api. When the turn loop became the driver it never hydrated, and
    every shot landed on a brand new building --- the Harwood House took
    0, 2, 6 and 0 BODY across four shots against a BODY of 8 and reported
    `destroyed=False` every time. Nothing could ever be knocked down.

    Folded from the log, absolute rather than a delta, like every other
    fold in this engine.
    """
    return damage_by_object(session).get(obj_id, 0)


def damage_by_object(session) -> dict[str, int]:
    """BODY lost by every object the log has seen hit, in one pass. The
    one fold; `damage_taken` reads from it."""
    totals: dict[str, int] = {}
    for event in list(getattr(session, "event_log", None) or []):
        if getattr(event, "kind", "") != "ActionResolved":
            continue
        payload = getattr(event, "result_payload", None) or {}
        if payload.get("kind") not in ("attack_construct", "throw_object"):
            continue
        obj_id = payload.get("target_id")
        totals[obj_id] = totals.get(obj_id, 0) + int(payload.get("body_dealt", 0) or 0)
    return totals


def constructs_in(scene, session=None) -> list[Construct]:
    """Everything in this scene an attack can be aimed AT, hydrated with what
    this fight has already done to it (rubble dropped). Without a session,
    the constructs as authored. See `kirby_world.construct.constructs_in`."""
    damage = None if session is None else damage_by_object(session)
    return _place_constructs(scene, damage=damage)
