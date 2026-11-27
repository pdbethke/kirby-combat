"""Draw a weapon, put one away, or let one fall.

THE RULES. 6E1 p.76 (Fast Draw): "A character with Fast Draw can draw a
weapon as a Zero Phase Action instead of the usual Half Phase Action (see
6E2 23)." So drawing is a Half Phase, and a Zero Phase with Fast Draw.

RULINGS (Peter, 2026-11-27), where the book is silent:
  * DROPPING a weapon in hand is a Zero Phase Action. It lands at his feet,
    a `WeaponMoved` like a Disarm's, and `pick_up_weapon` gets it back.
  * HOLSTERING is a Half Phase, like drawing; a Zero Phase with Fast Draw.
  * Fast Draw needs NO roll to draw (the page names a roll only for Clips).
  * Fast Draw is taken as the Skill, whichever weapon group the sheet
    bought it for: HD records the group as the Skill's input and this
    engine does not yet match it against a weapon's Familiarity.

A draw needs as many free hands as the weapon (`grips.hands_needed`): Doc
Holliday cannot draw his Colt with his shotgun in both hands, and has to
let the shotgun go first --- which is the real gunfight, and why the
Zero Phase drop matters.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction, _events_since, resolves

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

DRAW, FAST_DRAW = "draw_weapon", "fast_draw_weapon"
HOLSTER, FAST_HOLSTER = "holster_weapon", "fast_holster_weapon"
DROP = "drop_weapon"
KINDS = frozenset({DRAW, FAST_DRAW, HOLSTER, FAST_HOLSTER, DROP})

FAST_DRAW_SKILL = "FASTDRAW"


def has_fast_draw(actor: Any) -> bool:
    value = getattr(actor, "skill_roll_value", None)
    return callable(value) and value(FAST_DRAW_SKILL) is not None


def _legal(**kw):
    from kirby_combat.enumeration import LegalAction

    return LegalAction(**kw)


def hand_offers(session: "CombatSession", actor: Any) -> list:
    """Draw each holstered weapon he has the hands for; holster or drop each
    weapon in his hand. Only for a man whose grips were stated: without them
    the fight never said where anything is."""
    from kirby_combat.grips import (
        HOLSTERED, _purchase, free_hands, grip_of, hands_needed, stated_grips,
    )
    from kirby_combat.weapons import accessible_foci

    stated = stated_grips(session, actor.id)
    if not stated:
        return []
    fast = has_fast_draw(actor)
    names = {w.weapon_id: w.name for w in accessible_foci(actor)}
    free = free_hands(session, actor.id)
    out: list = []
    for weapon_id in stated:
        grip = grip_of(session, actor.id, weapon_id)
        name = names.get(weapon_id, weapon_id)
        if grip == HOLSTERED:
            if len(free) < hands_needed(_purchase(actor, weapon_id)):
                continue
            kind = FAST_DRAW if fast else DRAW
            out.append(_legal(
                action_id=f"{kind}:{weapon_id}", kind=kind, target_id=None,
                power_xmlid=None, power_name=name,
                summary=(f"Draw your {name}: "
                         + ("a Zero Phase Action with Fast Draw (6E1 p.76)" if fast
                            else "a Half Phase Action (6E2 p.23)"))))
        elif grip is not None:
            kind = FAST_HOLSTER if fast else HOLSTER
            out.append(_legal(
                action_id=f"{kind}:{weapon_id}", kind=kind, target_id=None,
                power_xmlid=None, power_name=name,
                summary=(f"Put your {name} away: "
                         + ("a Zero Phase Action with Fast Draw" if fast else "a Half Phase Action"))))
            out.append(_legal(
                action_id=f"{DROP}:{weapon_id}", kind=DROP, target_id=None,
                power_xmlid=None, power_name=name,
                summary=(f"Let your {name} fall at your feet: a Zero Phase Action; "
                         f"picking it up again is a Half Phase (6E2 p.25)")))
    return out


def _weapon_id(action) -> str:
    return action.action_id.split(":", 1)[1]


def _grip_changed(session, actor_id: str, weapon_id: str, hands: str):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import GripChanged, make_author_combatant

    return apply_event(session, GripChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(actor_id), combatant_id=actor_id,
        weapon_id=weapon_id, hands=hands))


@resolves(DRAW, FAST_DRAW)
def _resolve_draw(session, actor, action, *, template, roller) -> ResolvedAction:
    """Into his free hand(s): both for a Two-Handed weapon, else the right
    if it is free (the pickup ruling, `grips`)."""
    from kirby_combat.grips import BOTH, HOLSTERED, LEFT, RIGHT, _purchase, free_hands, grip_of, hands_needed

    weapon_id = _weapon_id(action)
    if grip_of(session, actor.id, weapon_id) != HOLSTERED:
        raise UnresolvableAction(action.kind, action.action_id)
    free = free_hands(session, actor.id)
    if hands_needed(_purchase(actor, weapon_id)) == 2:
        if len(free) < 2:
            raise UnresolvableAction(action.kind, action.action_id)
        hands = BOTH
    else:
        if not free:
            raise UnresolvableAction(action.kind, action.action_id)
        hands = RIGHT if RIGHT in free else LEFT
    after = _grip_changed(session, actor.id, weapon_id, hands)
    return ResolvedAction(session=after, kind=action.kind, action_id=action.action_id,
                          result=None, events=_events_since(session, after))


@resolves(HOLSTER, FAST_HOLSTER)
def _resolve_holster(session, actor, action, *, template, roller) -> ResolvedAction:
    from kirby_combat.grips import HOLSTERED, grip_of

    weapon_id = _weapon_id(action)
    if grip_of(session, actor.id, weapon_id) in (None, HOLSTERED):
        raise UnresolvableAction(action.kind, action.action_id)
    after = _grip_changed(session, actor.id, weapon_id, HOLSTERED)
    return ResolvedAction(session=after, kind=action.kind, action_id=action.action_id,
                          result=None, events=_events_since(session, after))


@resolves(DROP)
def _resolve_drop(session, actor, action, *, template, roller) -> ResolvedAction:
    """At his feet (ruling): on the ground where he stands, or on no map."""
    from kirby_combat.grips import HOLSTERED, grip_of
    from kirby_combat import weapons as W
    from kirby_world.occupancy import position_of

    weapon_id = _weapon_id(action)
    if grip_of(session, actor.id, weapon_id) in (None, HOLSTERED):
        raise UnresolvableAction(action.kind, action.action_id)
    weapon = W.find_weapon(session, actor.id, weapon_id)
    if weapon is None:
        raise UnresolvableAction(action.kind, action.action_id)
    scene = getattr(session, "scene", None)
    here = position_of(scene, actor.id) if scene is not None else None
    after = W.move_weapon(session, weapon, by_id=actor.id, cause=W.DROPPED,
                          holder_id=None, position=here)
    return ResolvedAction(session=after, kind=action.kind, action_id=action.action_id,
                          result=None, events=_events_since(session, after))
