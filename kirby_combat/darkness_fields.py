"""A Darkness field is kept up, or it comes down (6E1 p.188).

`actions/darkness.py` puts a field on the board (`DarknessPlaced`). This
module is how long it stays there. Until 0.33.4 nothing ever took one down:
0.33.3 made a field outlive the Phase it was cast in, and so made it last
the whole fight.

THE RULES, page by page:

  * 6E1 p.188: Darkness is Constant and Costs END; "a Darkness field
    remains in existence as long as the character pays the END for it".
  * 6E1 p.129-130: a Constant power's END is "paid when the character's
    Phase begins, before he does anything else", and "the character must
    maintain a Line Of Sight to the location of the Power".
  * 6E1 p.347 / 6E2 p.107: a Constant power "turns off at the end of the
    Segment whenever the character is asleep, Stunned, or Knocked Out" ---
    and NOT if he recovered from being Stunned before the Segment ended
    ("his Constant Powers won't turn off, since he won't still be Stunned at
    the end of the Segment", 6E2 p.107). So the Stun/KO check is made at the
    end of the Segment against how he is THEN, never at his next Phase
    against what happened since (`standing_areas.owner_out_since`, whose
    since-scan would take a field down in exactly the case p.107 excepts).
  * 6E2 p.131: a man who takes a Recovery "cannot even maintain a Constant
    Power".
  * 6E2 p.20: "turning off a Power" is a Zero Phase Action, "at the
    beginning of his Phase or after he's performed his first Half Phase
    Action" --- the `drop_darkness` offer.

THE RECORD: `DarknessPlaced` (one per Sense Group) puts a field up and
`DarknessEnded` takes ONE USE's fields down together; both are folded by
`apply_event`. A field's identity is its use: the ids one `darkness`
ActionResolved names in ``construct_ids``.

RULINGS (each labelled where it is made):

  * He keeps ONE field up at a time: `enumeration.has_live_own_darkness`
    suppresses a second. 6E1 p.188 allows more ("A character may maintain
    more than one Darkness field at once, provided he pays the END cost for
    all fields"); the one-field limit predates this module and is kept as a
    menu ruling, not a rule. Dropping it (Zero Phase) puts the offer back.
  * He stops rather than burn STUN for END (6E2 p.133 permits it), as
    `lingering.maintain_constant_attacks` and the standing areas rule.
  * Line Of Sight is to the middle of the field's footprint, at its floor.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DarknessEnd(str, Enum):
    """Why a field came down (`DarknessEnded.reason`)."""

    DROPPED = "dropped"                               # 6E2 p.20
    NO_END = "could_not_pay_end"                      # 6E1 p.188, p.129
    LOST_LINE_OF_SIGHT = "lost_line_of_sight"         # 6E1 p.129
    OWNER_STUNNED = "owner_stunned_or_out"            # 6E1 p.347, 6E2 p.107
    RECOVERED = "owner_took_a_recovery"               # 6E2 p.131
    POWER_NOT_ON_BUILD = "power_not_on_build"


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


def end_field(session, darkness: DarknessField, reason: DarknessEnd):
    """Take one use's fields down, through the log."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import DarknessEnded, make_author_engine

    return apply_event(session, DarknessEnded(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        construct_ids=list(darkness.construct_ids), reason=reason.value,
        source_combatant=darkness.owner_id,
    ))


def _power_of(session, owner_id: str) -> Any | None:
    from kirby_combat.enumeration import darkness_power
    from kirby_combat.identity import build_in_play

    owner = session.combatants.get(owner_id)
    return None if owner is None else darkness_power(build_in_play(owner))


def _sees_it(session, darkness: DarknessField) -> bool:
    """6E1 p.129: "maintain a Line Of Sight to the location of the Power"."""
    from kirby_world.geometry import line_of_sight_clear
    from kirby_world.scene import Position

    here = session.scene.combatant_positions.get(darkness.owner_id)
    if here is None:
        return False
    return line_of_sight_clear(here, Position(*darkness.centre),
                               session.scene.walls or [])


def maintain_darkness(session, actor_id: str, *, template, roller):
    """At the start of his Phase (6E1 p.130: "before he does anything else"),
    every field he keeps: is the power still his, can he see it, can he pay
    --- then pay, or let it go. Maintaining takes no Action (6E1 p.129).

    Stunned and Knocked Out are NOT asked here: that is the end of the
    Segment's question (`darkness_at_segment_end`, 6E2 p.107)."""
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_available, end_cost

    for darkness in darkness_fields(session, owner_id=actor_id):
        power = _power_of(session, actor_id)
        if power is None:
            session = end_field(session, darkness, DarknessEnd.POWER_NOT_ON_BUILD)
            continue
        if not _sees_it(session, darkness):
            session = end_field(session, darkness, DarknessEnd.LOST_LINE_OF_SIGHT)
            continue
        cost = end_cost(power)
        left = end_available(session, actor_id, power=power, template=template)
        if cost and left is not None and left < cost:
            # RULING: he stops rather than burn STUN for END (module doc).
            session = end_field(session, darkness, DarknessEnd.NO_END)
            continue
        session = _spend_attack_end(session, session.combatants[actor_id], cost,
                                    template, power=power)
    return session


def darkness_at_segment_end(session):
    """6E1 p.347 / 6E2 p.107: every field whose caster is Stunned or Knocked
    Out as the Segment ends goes down.

    The ``stunned`` status, NOT `statuses.stunned_or_recovering_for`: that
    window runs on through the Segment of his recovery Phase, and a man who
    has recovered "won't still be Stunned at the end of the Segment", so his
    Constant powers stay on (6E2 p.107)."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.statuses import statuses_for

    for darkness in darkness_fields(session):
        owner = session.combatants.get(darkness.owner_id)
        if owner is None or is_down(owner) or (
                {"stunned", "knockedOut"} & statuses_for(session, darkness.owner_id)):
            session = end_field(session, darkness, DarknessEnd.OWNER_STUNNED)
    return session


def after_a_recovery(session, actor_id: str):
    """6E2 p.131: a man who Recovers "cannot even maintain a Constant Power"."""
    for darkness in darkness_fields(session, owner_id=actor_id):
        session = end_field(session, darkness, DarknessEnd.RECOVERED)
    return session
