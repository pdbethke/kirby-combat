"""The things a man keeps up on the board: Darkness fields and Images.

Both are Constant powers that leave something in the scene (6E1 p.188
Darkness, "Duration: constant"; p.238 Images, "Duration: constant ... Costs
END: yes"), so both last exactly as long as a Constant power does. This is
where that lifetime is decided, once, for both. What it costs and what the
slot must hold is `upkeep`, which every maintained power shares.

WHEN EACH ONE COMES DOWN (6E1 unless marked):

  * At the start of his Phase (p.130: END is "paid when the character's
    Phase begins, before he does anything else"), each one he keeps:
      - its power must still be his (else POWER_NOT_ON_BUILD);
      - its Framework slot must still hold the reserve (p.402, SLOT_SWITCHED);
      - he must see it (p.129, "maintain a Line Of Sight to the location of
        the Power", LOST_LINE_OF_SIGHT);
      - he pays for it, a Charge or its END (p.129, p.369, p.403;
        NO_CHARGES / NO_END).
    Each pays for itself. p.129's Sapphire keeps two uses of one Constant
    power going and pays "END to maintain each use ... 20 END per Phase";
    p.188: "A character may maintain more than one Darkness field at once,
    provided he pays the END cost for all fields." Nothing limits how many
    he keeps up but what he can pay.
  * At the end of a Segment in which he is Stunned or Knocked Out (p.347,
    6E2 p.107), all of his come down (OWNER_STUNNED). Not at his next
    Phase: a man who recovered before the Segment ended "won't still be
    Stunned at the end of the Segment" and keeps them (6E2 p.107).
  * When he takes a Recovery, all of his (6E2 p.131: he "cannot even
    maintain a Constant Power", RECOVERED).
  * When he turns one off, a Zero Phase Action (6E2 p.20, DROPPED): one
    offer per thing he keeps up, so he chooses which.

A Darkness field is ONE USE's fields (one per Sense Group,
`darkness_fields`); an Image is one projected Image (`actions/images.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from kirby_combat.upkeep import (
    UpkeepEnd,
    pay_for_the_phase,
    sees,
    slot_still_allocated,
    stunned_or_out,
)


class KeptKind(str, Enum):
    DARKNESS = "darkness"
    IMAGE = "image"


#: The drop offer's kind, per thing kept up (6E2 p.20).
DROP_KIND = {KeptKind.DARKNESS: "drop_darkness", KeptKind.IMAGE: "drop_image"}


@dataclass(frozen=True)
class KeptUp:
    """One thing a man keeps up, as the board holds it now."""

    kind: KeptKind
    #: A Darkness use's first construct id; an Image's id.
    id: str
    owner_id: str
    #: Where Line Of Sight is drawn to (6E1 p.129): a field's footprint
    #: middle at its floor; an Image's point.
    location: tuple[float, float, float]
    #: A Darkness use's constructs, one per Sense Group. Empty for an Image.
    construct_ids: tuple[str, ...] = ()


def kept_up(session, *, owner_id: str | None = None) -> list[KeptUp]:
    """Everything kept up now --- his, or everyone's --- Darkness first,
    each kind in the order it went up."""
    from kirby_combat.actions.images import Images
    from kirby_combat.darkness_fields import darkness_fields

    out = [KeptUp(KeptKind.DARKNESS, f.id, f.owner_id, f.centre, f.construct_ids)
           for f in darkness_fields(session, owner_id=owner_id)]
    out += [KeptUp(KeptKind.IMAGE, i.image_id, i.caster_id,
                   tuple(float(v) for v in i.position))
            for i in Images.active(session)
            if owner_id is None or i.caster_id == owner_id]
    return out


def power_of(session, item: KeptUp) -> Any | None:
    """The build power that keeps ``item`` up, or None when he no longer
    has it."""
    from kirby_combat.enumeration import darkness_power, images_power
    from kirby_combat.identity import build_in_play

    owner = session.combatants.get(item.owner_id)
    if owner is None:
        return None
    find = darkness_power if item.kind is KeptKind.DARKNESS else images_power
    return find(build_in_play(owner))


def end_kept(session, item: KeptUp, reason: UpkeepEnd):
    """Take ``item`` down, through the log: `DarknessEnded` for a field, an
    ``image_ended`` row for an Image."""
    if item.kind is KeptKind.DARKNESS:
        from kirby_combat.darkness_fields import end_field

        return end_field(session, item.construct_ids, item.owner_id, reason)
    from kirby_combat.actions.images import Images

    return Images.dismiss(session, image_id=item.id, reason=reason.value)


def maintain_kept_up(session, actor_id: str, *, template, roller):
    """At the start of his Phase, each thing he keeps up: keep it, or let it
    go. Maintaining takes no Action (6E1 p.129). Stunned and Knocked Out
    are not asked here: that is the end of the Segment's question
    (`kept_up_at_segment_end`, 6E2 p.107)."""
    for item in kept_up(session, owner_id=actor_id):
        power = power_of(session, item)
        if power is None:
            session = end_kept(session, item, UpkeepEnd.POWER_NOT_ON_BUILD)
            continue
        if not slot_still_allocated(session, actor_id, power):
            session = end_kept(session, item, UpkeepEnd.SLOT_SWITCHED)
            continue
        if not sees(session, actor_id, item.location):
            session = end_kept(session, item, UpkeepEnd.LOST_LINE_OF_SIGHT)
            continue
        session, unpaid = pay_for_the_phase(session, actor_id, power,
                                            template=template)
        if unpaid is not None:
            session = end_kept(session, item, unpaid)
    return session


def kept_up_at_segment_end(session):
    """6E1 p.347 / 6E2 p.107: everything whose keeper is Stunned or Knocked
    Out as the Segment ends comes down."""
    for item in kept_up(session):
        if stunned_or_out(session, item.owner_id):
            session = end_kept(session, item, UpkeepEnd.OWNER_STUNNED)
    return session


def after_a_recovery(session, actor_id: str):
    """6E2 p.131: a man who Recovers "cannot even maintain a Constant Power"."""
    for item in kept_up(session, owner_id=actor_id):
        session = end_kept(session, item, UpkeepEnd.RECOVERED)
    return session


def drop(session, actor_id: str, kind: KeptKind, item_id: str):
    """He turns one off (6E2 p.20). Raises KeyError when he keeps no such
    thing up, so a stale offer is refused rather than passing quietly."""
    for item in kept_up(session, owner_id=actor_id):
        if item.kind is kind and item.id == item_id:
            return end_kept(session, item, UpkeepEnd.DROPPED)
    raise KeyError(f"{actor_id!r} keeps no {kind.value} {item_id!r} up")
