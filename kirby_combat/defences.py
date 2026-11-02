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


#: Every offer kind is one of two things: a THREAT, which acts on a man and
#: has a row in the table, or a known NON-THREAT (a move, a defence, a
#: Hold ...). `enumeration.ALL_ACTION_KINDS` is the registry of kinds the
#: engine can offer; a test holds that each is in exactly one of the two
#: sets, so a new kind fails loudly until someone classifies it.

#: Mental powers that act on a man (6E1 p.150): rolled OMCV against DMCV.
#: Mind Scan and Telepathy are among them: both roll MCV against the
#: target's DMCV and act on him (Mind Scan 6E1 p.263; Telepathy as cited
#: in `mental/telepathy.py`; both resolve in `loop.resolvers`).
MENTAL_KINDS = frozenset({
    "mental_blast", "mind_control", "mental_entangle", "mental_illusion",
    "mind_scan", "telepathy",
})
DARKNESS_KINDS = frozenset({"darkness_zone"})
FLASH_KINDS = frozenset({"flash"})
#: Rolled to hit against the target's DCV. The first group is what the
#: reaction menu already treats as an attack on a man
#: (`loop.reactions.REACTABLE_KINDS`, less Flash, which has its own row).
#: The rest resolve elsewhere but are rolled against DCV all the same:
#: Grab 6E2 p.66, Throw 6E2 p.83, Move By / Move Through 6E2 p.72, Spread
#: 6E2 p.52 (a single-target attack with fewer dice). Drain and Dispel are
#: Adjustment Powers, attack-rolled like any other ranged power (RULING:
#: the book's adjustment rows do not list a defence).
DCV_KINDS = frozenset({
    "attack", "strike", "maneuver", "trip", "disarm", "push",
    "throw_object", "move_strike", "reposition_strike",
    "rapid_fire", "multiple_attack", "sweep",
    "autofire", "autofire_spray", "entangle", "attack_entangle", "haymaker",
    "grab", "throw", "move_by", "move_through", "spread", "reposition_push",
    "drain", "dispel",
})
#: Hand-to-hand attacks: the ones a Block answers (6E2 p.59). One list,
#: read by the reaction menu too.
HTH_KINDS = frozenset({
    "strike", "maneuver", "trip", "disarm", "sweep", "haymaker",
    "grab", "throw", "move_by", "move_through",
})
#: Offers that do not act on a man as a threat: movement, defences, Holds,
#: help, constructs and scenery, social play. RULING for the grouping: the
#: book does not classify offers, the engine does.
NON_THREAT_KINDS = frozenset({
    "aid", "heal", "attack_construct", "force_wall", "image_decoy",
    "block", "dodge", "charm", "persuasion", "conversation", "trading",
    "climb", "climb_fast", "coordinate", "disengage", "escape_attack",
    "escape_ego", "escape_str", "escape_teleport", "hide", "hold",
    "move", "half_move", "move_to_cover",
    "pickup", "pick_up_weapon", "reallocate", "reconfigure_vpp", "recover",
    "release_held", "reposition", "reposition_vantage", "set", "stabilize",
    "stand_up", "change_identity", "change_identity_instant",
    "raise_damage_shield", "snap_out_of_rage",
})

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
#: Presence Attack: nothing answers it. RULING: no table row gives one, and
#: the only defence the book names is PRE itself (6E1 p.178), which is not
#: an Abort.
_PRESENCE = frozenset({Defence.NONE})


def threatens_a_man(kind: str) -> bool:
    """Whether ``kind`` is a threat, so that `answers_to` has a row for it.

    False for a known non-threat (a move, a Hold ...). Raises ValueError for
    a kind in neither set, so a new kind cannot be silently ignored."""
    if kind in NON_THREAT_KINDS:
        return False
    if kind in _THREAT_KINDS:
        return True
    raise ValueError(
        f"threatens_a_man: {kind!r} is in neither the threat nor the "
        "non-threat kinds; classify it in kirby_combat/defences.py")


def is_hth(kind: str, view: Any) -> bool:
    """Is this offer hand-to-hand (so a Block answers it, 6E2 p.59)? By its
    kind, else by its view: a power with no range is a melee one."""
    if kind in HTH_KINDS:
        return True
    if view is None:
        return False
    return not _ranged(view)


def _ranged(view: Any) -> bool:
    # The same reading `loop.reactions._is_hth` makes of a view's range.
    return bool(getattr(view, "is_ranged", (getattr(view, "range_m", 0) or 0) > 0))


_THREAT_KINDS = (PRESENCE_KINDS | MENTAL_KINDS | DARKNESS_KINDS | FLASH_KINDS
                 | DCV_KINDS)


def answers_to(view: Any, *, kind: str) -> frozenset[Defence]:
    """The defences that answer ``view``, an offer of ``kind``.

    Call `threatens_a_man` first: this raises ValueError for a kind that is
    not a threat (a move, a Hold ...) or is not classified at all, because a
    silent fallback would advise a man to Dodge something nobody has
    classified."""
    area = view is not None and is_area_attack(view)
    out: set[Defence] = set()
    if kind in PRESENCE_KINDS:
        return _PRESENCE
    if kind in DCV_KINDS:
        out |= _SINGLE
        if is_hth(kind, view):
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
            f"answers_to: no defence row fits the kind {kind!r}; call "
            "threatens_a_man(kind) first, and classify a new kind in "
            "kirby_combat/defences.py")
    if area:
        out |= _AREA
        out -= {Defence.DODGE, Defence.BLOCK}
    return frozenset(out)
