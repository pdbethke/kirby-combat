"""A Darkness field, as the log records it.

`actions/darkness.py` puts a field on the board (`DarknessPlaced`, one per
Sense Group); `DarknessEnded` takes one USE's fields down together. Both
are folded by `apply_event`. A field's identity is its use: the ids one
`darkness` ActionResolved names in ``construct_ids``.

How long a field stays up --- END or a Charge each Phase, Line Of Sight,
the Framework slot, Stunned at the end of a Segment, a Recovery, turning it
off --- is the Constant-power lifetime it shares with Images: `kept_up`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class DarknessField:
    """One use's fields, as the board holds them now."""

    #: The first construct id of the use.
    id: str
    construct_ids: tuple[str, ...]
    owner_id: str
    #: The middle of the footprint, at its floor, in scene coordinates.
    centre: tuple[float, float, float]


def darkness_fields(session, *, owner_id: str | None = None) -> list[DarknessField]:
    """Every Darkness field on the board now, one per use, in the order they
    went up."""
    scene = getattr(session, "scene", None)
    if scene is None:
        return []
    live = {c.obj_id: c for c in (scene.constructs or [])
            if c.kind == "darkness_zone"}
    out: list[DarknessField] = []
    for event in session.event_log:
        if event.kind != "ActionResolved":
            continue
        payload = event.result_payload or {}
        if payload.get("type") != "darkness" or not payload.get("hit"):
            continue
        ids = tuple(i for i in payload.get("construct_ids") or () if i in live)
        if not ids:
            continue
        owner = payload["attacker_id"]
        if owner_id is not None and owner != owner_id:
            continue
        first = live[ids[0]]
        pts = first.polygon_xy or []
        out.append(DarknessField(
            id=ids[0], construct_ids=ids, owner_id=owner,
            centre=(sum(p[0] for p in pts) / len(pts),
                    sum(p[1] for p in pts) / len(pts),
                    float(first.elevation_range_m[0])),
        ))
    return out


def end_field(session, construct_ids, owner_id: str, reason):
    """Take one use's fields down, through the log. ``reason`` is an
    `upkeep.UpkeepEnd`."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import DarknessEnded, make_author_engine

    return apply_event(session, DarknessEnded(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        construct_ids=list(construct_ids), reason=reason.value,
        source_combatant=owner_id,
    ))
