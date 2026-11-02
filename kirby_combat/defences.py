"""Which defences answer which threat (squad tactics spec 1c).

One table, read by the reaction menu (what a man is OFFERED) and, in time,
by the threat picture (what he is TOLD), so the offer and the advice cannot
disagree.

Dodge and Block act on the defender's DCV or on the blow. An Area Of Effect
attack is rolled against the target point, which has DCV 3 (6E1 p.321), so
his DCV plays no part and neither does anything that adds to it. Being an
area therefore removes DODGE and BLOCK from whatever else the power is.
RULING: when a power fits more than one row (an area Flash, an area Mental
Blast) the answers are the union of the rows, minus DODGE and BLOCK when it
is an area. The book states each row; it does not state the union.

COVER, SPACING, DISTANCE and MOVE_OUT are not actions the book names as
Abortable defences; they are what the table advises, each labelled RULING
below. DIVE_FOR_COVER is the one book action among them (6E2 p.87).
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from kirby_combat.actions.area_attack import is_area_attack
from kirby_combat.pre_attacks.in_the_phase import PRESENCE_KINDS


class Defence(str, Enum):
    #: 6E2 p.55 / p.93: +3 DCV against all attacks.
    DODGE = "dodge"
    #: 6E2 p.59: stop a hand-to-hand attack outright.
    BLOCK = "block"
    #: 6E2 p.87: move up to half, prone at the point; the area's own answer.
    DIVE_FOR_COVER = "dive_for_cover"
    #: RULING: put something between him and the attacker.
    COVER = "cover"
    #: RULING: stand apart from his own side so one area catches fewer.
    SPACING = "spacing"
    #: RULING: be beyond the power's range.
    DISTANCE = "distance"
    #: RULING: leave the area a Darkness fills.
    MOVE_OUT = "move_out"
    #: No defence answers it.
    NONE = "none"


#: The offers that are a mental power (6E1 p.150): rolled OMCV against DMCV.
MENTAL_KINDS = frozenset({
    "mental_blast", "mind_control", "mind_scan", "mental_entangle",
    "telepathy", "mental_illusion",
})
DARKNESS_KINDS = frozenset({"darkness", "darkness_zone"})
FLASH_KINDS = frozenset({"flash"})
#: Rolled to hit against the target's DCV: everything the reaction menu
#: already treats as an attack on a man (`loop.reactions.REACTABLE_KINDS`,
#: less Flash, which has its own row).
DCV_KINDS = frozenset({
    "attack", "strike", "maneuver", "trip", "disarm", "push",
    "throw_object", "move_strike", "reposition_strike",
    "rapid_fire", "multiple_attack", "sweep",
    "autofire", "autofire_spray", "entangle", "haymaker",
})
_HTH_KINDS = frozenset({"strike", "maneuver", "trip", "disarm", "sweep", "haymaker"})

#: Single-target, against DCV. DODGE 6E2 p.55/p.93; DIVE_FOR_COVER 6E2 p.87;
#: COVER and DISTANCE are RULINGs.
_SINGLE = frozenset({Defence.DODGE, Defence.DIVE_FOR_COVER, Defence.COVER,
                     Defence.DISTANCE})
#: BLOCK, hand-to-hand only: 6E2 p.59.
_HTH = frozenset({Defence.BLOCK})
#: Area Of Effect: rolled against the point, DCV 3 (6E1 p.321). RULING for
#: SPACING, DISTANCE and COVER (cover that blocks the line to the point).
_AREA = frozenset({Defence.DIVE_FOR_COVER, Defence.SPACING, Defence.DISTANCE,
                   Defence.COVER})
#: Flash: cover that blocks sight, or distance (6E1 p.228; the answers are
#: a RULING).
_FLASH = frozenset({Defence.COVER, Defence.DISTANCE})
#: Darkness: step out of it (6E1 p.140; the answer is a RULING).
_DARKNESS = frozenset({Defence.MOVE_OUT})
#: Mental, against DMCV, where range applies (6E1 p.150; DMCV is untouched by
#: Dodge or Block). RULING: LOS-only powers have no range to open.
_MENTAL_RANGED = frozenset({Defence.DISTANCE})
#: Presence Attack: nothing answers it. RULING (6E1 p.150's Dodge/Block
#: exclusion applies, and no table row gives one).
_PRESENCE = frozenset({Defence.NONE})


def _ranged(view: Any) -> bool:
    # The same reading `loop.reactions._is_hth` makes of a view's range.
    return bool(getattr(view, "is_ranged", (getattr(view, "range_m", 0) or 0) > 0))


def answers_to(view: Any, *, kind: str) -> frozenset[Defence]:
    """The defences that answer ``view``, an offer of ``kind``.

    Raises ValueError for a kind that fits no row: a silent fallback would
    advise a man to Dodge something nobody has classified."""
    area = view is not None and is_area_attack(view)
    out: set[Defence] = set()
    if kind in PRESENCE_KINDS:
        return _PRESENCE
    if kind in DCV_KINDS:
        out |= _SINGLE
        if kind in _HTH_KINDS or (view is not None and not _ranged(view)):
            out |= _HTH
    elif kind in FLASH_KINDS:
        # A one-target Flash rolls to hit (6E1 p.228), so a Dodge is read.
        out |= _FLASH | _SINGLE
    elif kind in DARKNESS_KINDS:
        out |= _DARKNESS
    elif kind in MENTAL_KINDS:
        if view is not None and _ranged(view):
            out |= _MENTAL_RANGED
        elif not area:
            return frozenset({Defence.NONE})
    else:
        raise ValueError(
            f"answers_to: no defence row fits the kind {kind!r}; classify it "
            "in kirby_combat/defences.py")
    if area:
        out |= _AREA
        out -= {Defence.DODGE, Defence.BLOCK}
    return frozenset(out)
