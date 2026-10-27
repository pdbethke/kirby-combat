"""A martial maneuver made as part of a Full Move ("FMove").

Flying Tackle, Passing Strike / Throw / Disarm, Charge, Flying Grab, Sacrifice
Lunge: HD's builder marks each with the HERO System Martial Arts element
``FMove`` --- the maneuver is performed at the end of, or during, a Full Move.
6E2 has the mechanic in its own words: a Move By is "a Full Move past his
target" and a Move Through runs into him (6E2 p.72), both resolved at
the end of the charge with the damage the velocity buys. So an FMove maneuver
is the charge of `actions/velocity_maneuvers.py` around the maneuver's own
blow (`martial_resolution.blow`).

THE RULE, element by element:

* THE CHARGE: to within reach of him on the real map, on his full combat
  Running --- the ruling `velocity_maneuvers` already makes ("velocity is his
  full combat Running, the speed he can reach", 6E2 p.72: he "doesn't
  necessarily have to travel his Full Move to get the damage for his full
  velocity"). A charge that cannot end in contact is refused, exactly as the
  menu refuses to offer it.
* THE BLOW is the maneuver's: its OCV on the roll, its DCV until his next
  Phase, its damage (STR + DCs, plus +1d6 per full 10m of velocity for
  ``+v/10``, 6E2 p.101), its Grab or Disarm. RULING: the maneuver's own CV
  modifiers REPLACE Move By's -2/-2 and Move Through's -v/10/-3, as a Martial
  Maneuver's modifiers replace the Combat Maneuver it improves on ("They
  function identically ... but with different modifiers", 6E2 p.93).
* NO RECOIL. Move By and Move Through hurt the attacker (6E2 p.72) because
  they ARE the collision; HD's elements for these maneuvers name no damage to
  the attacker, and none is invented. Flying Tackle's cost is its own "You
  Fall".
* THE FOLLOW-THROUGH, from the elements: a maneuver that takes hold (a Grab)
  or puts him down too (You Fall) ends where it hit, as a Move Through that
  hits may "stop where he hit the target" (6E2 p.73); every other one is a
  Move By, and "Hit or miss, the character finishes at the end of his movement
  path" (6E2 p.72). One that misses runs on, as a Move Through that misses
  "keeps traveling in a straight line through the point where the target was
  standing" (6E2 p.72).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.actions.maneuver_effects import MartialEffect

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import ResolvedAction

#: Tolerance on "within reach" after a clamped move, in metres.
_REACH_EPS = 1e-6


def stops_at_contact(effect: MartialEffect) -> bool:
    """Whether a landed FMove maneuver ends where it hit (see the docstring)."""
    return effect.grab or effect.actor_falls


def resolve_fmove(session, actor, action: "LegalAction", mv, effect: MartialEffect,
                  *, template, roller) -> "ResolvedAction":
    from kirby_combat.actions.martial_resolution import blow
    from kirby_combat.actions.velocity_maneuvers import _point_beyond
    from kirby_combat.loop.registry import ResolvedAction, _events_since
    from kirby_combat.loop.resolvers import _move_capacity, _recorded, _stop_at_reach
    from kirby_combat.placement import move_toward
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    start_session = session
    target_id = action.target_id
    velocity = _move_capacity(actor, "running")
    scene = session.scene
    here = position_of(scene, actor.id) if scene is not None else None
    there = position_of(scene, target_id) if scene is not None else None
    moved_m = 0.0
    if here is not None and there is not None:
        reach = float(mv.reach_m)
        contact = _stop_at_reach(here, there, reach)
        charged, outcome = move_toward(session, actor.id, contact,
                                       mode="running", distance_m=velocity)
        if outcome is None or not outcome.reachable or distance_3d(
                outcome.landing, there) > reach + _REACH_EPS:
            return _recorded(session, actor, action, None, {
                "kind": action.kind, "target_id": target_id, "hit": False,
                "maneuver_id": mv.maneuver_id, "out_of_reach": True,
                "stun_dealt": 0, "body_dealt": 0,
                "note": f"{mv.name} cannot end in contact from here",
            })
        session = charged
        moved_m = distance_3d(here, outcome.landing)

    target = session.combatants[target_id]
    me = session.combatants[actor.id]
    session, result = blow(session, me, target, action, mv, effect,
                           template=template, roller=roller, velocity_mps=velocity)

    if here is not None and there is not None and not (
            result.hit and stops_at_contact(effect)):
        left = max(0.0, velocity - moved_m)
        if left > 0.0:
            now_at = position_of(session.scene, actor.id)
            beyond = _point_beyond(now_at, there, left)
            session, _ = move_toward(session, actor.id, beyond,
                                     mode="running", distance_m=left)
    return ResolvedAction(
        session=session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(start_session, session),
    )
