"""Weapons, and every other thing a man holds that can be taken off him.

THE ENGINE TRACKED NO WEAPONS, so a Disarm rolled to hit and took nothing
away (6E2 p.62's whole consequence was missing) and Takeaway could not be
offered at all. This module is where a held thing lives now: in its owner's
hand, in somebody else's, or on the ground at a point on the map.

WHAT COUNTS. 6E1 p.379: "An Accessible Focus is one that's easily taken away
from the character ... An Accessible Focus can be hit by a Grab or other
nonranged attack ... Some common examples of Accessible Foci include most
weapons, shields, magic wands, and the like." An Inaccessible Focus "can't be
hit with a Grab or otherwise attacked for purposes of taking it away from a
character while that character is in combat". So the thing that can be taken
is a purchase bought with HD's FOCUS modifier at OAF or IAF --- a gun, a club,
a shield, a ray-gun Multipower --- whether it sits in his powers or his
equipment, and it is the PURCHASE that is taken, with everything under it: a
Multipower bought OAF is one blaster, and every slot goes with it. A slot that
carries its own Accessible Focus inside a framework that does not is its own
object. RULING: two separate purchases each bought OAF are two objects, since
a build records no "these are the same gun".

WHERE IT IS. The log says, through one event kind, ``WeaponMoved``, which
carries where the thing ended up --- a holder, or a point on the ground ---
never a delta, so a replay folds the same place (the durations pattern,
`session/effects.py`). Nothing moved is in its owner's hand.

WHAT BEING WITHOUT IT DOES. A weapon out of its owner's hand is OFF for him,
for every reader: `apply_event` folds the out-of-hand set into his build the
way a Dispel's is (`actions/dispel.py`, `HeroWithPowersOff`), so his attacks,
defences and movement are read without it and nothing else needs telling.

RULING, labelled: a weapon in somebody else's hand is useless to him. 6E1
p.382 lets a player make a Focus Personal ("only the character can use it - if
someone else Grabs it, it's useless to that person") or Universal, says "the
cost is identical", and HD records no choice. Handing one man's power to
another would also mean re-costing it on his STR and his sheet, which this
engine does not do. So the man holding it denies it to its owner and fights
with it no better than without it. Its owner gets it back by taking it back
(Disarm or Takeaway against the holder) or picking it up off the ground.

NOT MODELLED: a Knocked Out man letting go ("he usually lets go of the Focus",
6E1 p.379: usually, the GM's call); breaking a Focus by attacking it; Fast
Draw's Zero Phase pick-up (6E2 p.62); a weapon flying into or through a wall
(it lands on the line of the blow, inside the map's bounds).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: 6E1 p.379: the Foci that can be taken away in combat.
ACCESSIBLE_FOCI = frozenset({"OAF", "IAF"})

#: What moved a weapon --- the ``cause`` a ``WeaponMoved`` records.
DISARMED = "disarm"            # 6E2 p.62: knocked flying
TAKEN = "takeaway"             # 6E2 p.69 / 6E1 p.379: wrenched away
PICKED_UP = "pick_up"          # 6E2 p.25, p.62: recovered off the ground
CAUSES = frozenset({DISARMED, TAKEN, PICKED_UP})


@dataclass(frozen=True)
class Weapon:
    """One Accessible Focus a combatant owns."""

    owner_id: str
    #: The focus purchase's own object id --- an identity, never a name.
    weapon_id: str
    name: str
    #: HD's FOCUS option: "OAF" or "IAF".
    focus: str
    #: This purchase's id and every purchase under it (a Multipower's slots).
    power_ids: frozenset[str]


@dataclass(frozen=True)
class OnGround:
    """Lying where it landed; ``position`` is None in a fight with no map."""

    position: Any


@dataclass(frozen=True)
class InHand:
    holder_id: str


# ---------------------------------------------------------------------------
# What a man owns
# ---------------------------------------------------------------------------

def _focus_of(purchase) -> str | None:
    """The purchase's OWN Accessible Focus option, or None.

    ``inherited=False``: a slot of an OAF Multipower is part of the pool's
    object, not an object of its own.
    """
    from kirby_cost.model.modifiers import find_modifier

    from kirby_combat.power_modifiers import _option

    try:
        focus = find_modifier(purchase, "FOCUS", inherited=False)
    except (AttributeError, TypeError):      # a stub with no modifier tree
        return None
    if focus is None:
        return None
    option = _option(focus)
    return option if option in ACCESSIBLE_FOCI else None


def _children(purchase) -> list:
    out: list = []
    for attr in ("sub_powers", "objects", "powers"):
        nested = getattr(purchase, attr, None)
        if isinstance(nested, list):
            out.extend(nested)
    return out


def _ids_under(purchase) -> frozenset[str]:
    ids: set[str] = set()
    stack = [purchase]
    seen: set[int] = set()
    while stack:
        p = stack.pop()
        if id(p) in seen:
            continue
        seen.add(id(p))
        pid = getattr(p, "id", None)
        if pid not in (None, ""):
            ids.add(str(pid))
        stack.extend(_children(p))
    return frozenset(ids)


def _label(purchase) -> str:
    for attr in ("name", "alias", "display", "xmlid"):
        value = getattr(purchase, attr, None)
        if value:
            return str(value)
    return str(getattr(purchase, "id", "weapon"))


def accessible_foci(combatant) -> list[Weapon]:
    """Every Accessible Focus he OWNS, held or not.

    Read off his build as bought (``dispel.original_hero``), in the identity
    he is in (6E1 p.388: what he bought Only In Hero ID is not with him out
    of it). A combatant rebuilt from a snapshot has no build to read and owns
    nothing takeable, the stance `actions/dispel.py` takes for the same
    reason; a flat stat block has no build either.
    """
    from kirby_combat.actions.dispel import original_hero
    from kirby_combat.identity import in_play

    if getattr(combatant, "snapshot", None) is not None:
        return []
    state = getattr(combatant, "state", None)
    hero = getattr(combatant, "hero", None)
    if state is None or hero is None:
        return []
    build = original_hero(hero)
    owner = str(combatant.id)
    out: list[Weapon] = []
    seen: set[int] = set()

    def walk(purchases: Iterable[Any]) -> None:
        for p in purchases or []:
            # A slot is reachable both under its framework and in the
            # build's own list; it is one object.
            if id(p) in seen:
                continue
            seen.add(id(p))
            if not in_play(p, in_hero_id=state.in_hero_id):
                continue
            focus = _focus_of(p)
            if focus is not None and getattr(p, "id", None) not in (None, ""):
                out.append(Weapon(
                    owner_id=owner, weapon_id=str(p.id), name=_label(p),
                    focus=focus, power_ids=_ids_under(p),
                ))
                continue          # the whole purchase goes as one object
            walk(_children(p))

    walk(getattr(build, "powers", None))
    walk(getattr(build, "equipment", None))
    return out


# ---------------------------------------------------------------------------
# Where everything is, folded from the log
# ---------------------------------------------------------------------------

def locations(session: "CombatSession") -> dict[tuple[str, str], InHand | OnGround]:
    """(owner, weapon) -> where it is, for every weapon the log has moved.

    A weapon absent from the map is where it started: in its owner's hand.
    """
    from kirby_world.scene import Position

    out: dict[tuple[str, str], InHand | OnGround] = {}
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "WeaponMoved":
            continue
        key = (evt.owner_id, evt.weapon_id)
        if evt.holder_id:
            out[key] = InHand(evt.holder_id)
        else:
            out[key] = OnGround(
                Position(evt.x, evt.y, evt.z) if evt.on_map else None)
    return out


def out_of_hand_ids(session: "CombatSession", combatant_id: str) -> frozenset[str]:
    """The power ids of his own weapons that are not in his hand now.

    What `dispel.fold_dispel` leaves out of his build.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        return frozenset()
    where = locations(session)
    off: set[str] = set()
    for w in accessible_foci(combatant):
        place = where.get((w.owner_id, w.weapon_id))
        if place is not None and place != InHand(combatant_id):
            off |= w.power_ids
    return frozenset(off)


@dataclass(frozen=True)
class WeaponsInPlay:
    """Who is holding what, and what is lying on the ground.

    Assembled by the loop (enumeration holds no session) the way
    ``slot_allocation`` and ``spent_charges`` are.
    """

    #: holder id -> every Accessible Focus in his hands: his own that he has
    #: kept, and anybody else's he has taken.
    held: dict[str, tuple[Weapon, ...]]
    on_ground: tuple[tuple[Weapon, Any], ...]

    def held_by(self, combatant_id: str) -> tuple[Weapon, ...]:
        return self.held.get(combatant_id, ())


def weapons_in_play(session: "CombatSession") -> WeaponsInPlay:
    where = locations(session)
    held: dict[str, list[Weapon]] = {}
    ground: list[tuple[Weapon, Any]] = []
    for combatant in session.combatants.values():
        for w in accessible_foci(combatant):
            place = where.get((w.owner_id, w.weapon_id), InHand(w.owner_id))
            if isinstance(place, InHand):
                held.setdefault(place.holder_id, []).append(w)
            else:
                ground.append((w, place.position))
    return WeaponsInPlay(
        held={k: tuple(v) for k, v in held.items()}, on_ground=tuple(ground))


def find_weapon(session: "CombatSession", owner_id: str, weapon_id: str) -> Weapon | None:
    owner = session.combatants.get(owner_id)
    if owner is None:
        return None
    return next((w for w in accessible_foci(owner) if w.weapon_id == weapon_id), None)


def holder_of(session: "CombatSession", weapon: Weapon) -> str | None:
    """Who has it in hand, or None when it is on the ground --- or when its
    owner owns no such thing (a hand-built offer is not taken on trust)."""
    if find_weapon(session, weapon.owner_id, weapon.weapon_id) != weapon:
        return None
    place = locations(session).get((weapon.owner_id, weapon.weapon_id),
                                   InHand(weapon.owner_id))
    return place.holder_id if isinstance(place, InHand) else None


def on_ground(session: "CombatSession", weapon: Weapon) -> bool:
    """Is it lying on the ground (and does its owner own it)?"""
    if find_weapon(session, weapon.owner_id, weapon.weapon_id) != weapon:
        return False
    return isinstance(locations(session).get((weapon.owner_id, weapon.weapon_id)),
                      OnGround)


def ground_position(session: "CombatSession", weapon: Weapon):
    place = locations(session).get((weapon.owner_id, weapon.weapon_id))
    if not isinstance(place, OnGround):
        raise ValueError(f"{weapon.name!r} is not on the ground")
    return place.position


# ---------------------------------------------------------------------------
# Moving one
# ---------------------------------------------------------------------------

def move_weapon(
    session: "CombatSession", weapon: Weapon, *, by_id: str, cause: str,
    holder_id: str | None, position,
) -> "CombatSession":
    """Record where ``weapon`` is now: in ``holder_id``'s hand, or on the
    ground at ``position`` (None in a fight with no map)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import WeaponMoved, make_author_combatant

    if cause not in CAUSES:
        raise ValueError(f"unknown weapon move cause {cause!r}; one of {sorted(CAUSES)}")
    if holder_id is not None and position is not None:
        raise ValueError("a weapon is in a hand or on the ground, not both")
    on_map = holder_id is None and position is not None
    return apply_event(session, WeaponMoved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(by_id),
        owner_id=weapon.owner_id, weapon_id=weapon.weapon_id,
        weapon_name=weapon.name, holder_id=holder_id or "",
        on_map=on_map,
        x=float(position.x) if on_map else 0.0,
        y=float(position.y) if on_map else 0.0,
        z=float(position.z) if on_map else 0.0,
        cause=cause, by_id=by_id,
    ))


# ---------------------------------------------------------------------------
# The two contests
# ---------------------------------------------------------------------------

def str_body(roller, strength: int) -> tuple[int, list[int]]:
    """1d6 per 5 STR, counted as Normal Damage BODY (6E2 p.62, p.66)."""
    from kirby_combat.resolution.damage import _body_for_normal_die

    dice = max(0, int(strength) // 5)
    faces = list(roller.roll_dice(dice)) if dice else []
    return sum(_body_for_normal_die(v) for v in faces), faces


def disarm_contest(roller, *, attacker_str: int, defender_str: int) -> dict:
    """6E2 p.62: "each rolls 1d6 per 5 points of STR and counts the Normal
    Damage BODY. If the attacker's BODY total is higher or the rolls tie, the
    Disarm succeeds"."""
    a, a_faces = str_body(roller, attacker_str)
    d, d_faces = str_body(roller, defender_str)
    return {"attacker_str": int(attacker_str), "defender_str": int(defender_str),
            "attacker_body": a, "defender_body": d,
            "attacker_dice": a_faces, "defender_dice": d_faces,
            "won": a >= d}


def wrench_contest(roller, *, attacker_str: int, defender_str: int) -> dict:
    """Wrenching a Grabbed Focus away. 6E2 p.69 sends a Grab of a weapon to
    "normal Grab rules"; 6E1 p.379 states them for a Focus: it "is knocked
    free if the attacker rolls more BODY for his attack than the defender
    rolls BODY for his Strength". MORE: a tie leaves it where it is, which is
    also the Grab's own tie rule (6E2 p.66, the holder keeps his hold)."""
    a, a_faces = str_body(roller, attacker_str)
    d, d_faces = str_body(roller, defender_str)
    return {"attacker_str": int(attacker_str), "defender_str": int(defender_str),
            "attacker_body": a, "defender_body": d,
            "attacker_dice": a_faces, "defender_dice": d_faces,
            "won": a > d}


def disarm_landing(session: "CombatSession", attacker_id: str, target_id: str,
                   metres: float):
    """Where a Disarmed weapon lands: 6E2 p.62, "goes flying 1d6+1 meters in
    the direction of the strike (attacker's choice, within reach)".

    RULING: the attacker's choice is straight on along the line of the blow,
    from him through the man he disarmed --- away from them both and the one
    direction a chooser never has to be asked for. It stops at the map's
    bounds. None in a fight with no map.
    """
    import math

    from kirby_world.occupancy import position_of
    from kirby_world.scene import Position

    scene = getattr(session, "scene", None)
    if scene is None:
        return None
    here = position_of(scene, attacker_id)
    there = position_of(scene, target_id)
    if here is None or there is None:
        return None
    dx, dy = there.x - here.x, there.y - here.y
    length = math.hypot(dx, dy)
    ux, uy = (dx / length, dy / length) if length else (1.0, 0.0)
    x, y = there.x + ux * metres, there.y + uy * metres
    b = scene.bounds
    x = min(max(x, float(b.min_x)), float(b.max_x))
    y = min(max(y, float(b.min_y)), float(b.max_y))
    return Position(x, y, there.z)


def knock_away(session: "CombatSession", weapon: Weapon, *, attacker_id: str,
               target_id: str, roller) -> tuple["CombatSession", dict]:
    """The Disarm's consequence: the weapon flies 1d6+1m (6E2 p.62)."""
    metres = float(sum(roller.roll_dice(1)) + 1)
    landing = disarm_landing(session, attacker_id, target_id, metres)
    session = move_weapon(session, weapon, by_id=attacker_id, cause=DISARMED,
                          holder_id=None, position=landing)
    return session, {
        "weapon_owner_id": weapon.owner_id, "weapon_id": weapon.weapon_id,
        "weapon_name": weapon.name, "flew_m": metres,
        "landing": ([landing.x, landing.y, landing.z]
                    if landing is not None else None),
    }


__all__ = [
    "ACCESSIBLE_FOCI", "DISARMED", "TAKEN", "PICKED_UP",
    "Weapon", "OnGround", "InHand", "WeaponsInPlay",
    "accessible_foci", "locations", "out_of_hand_ids", "weapons_in_play",
    "find_weapon", "holder_of", "on_ground", "ground_position", "move_weapon",
    "disarm_contest", "wrench_contest", "disarm_landing", "knock_away",
    "str_body",
]
