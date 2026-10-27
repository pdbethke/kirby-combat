"""Move By and Move Through, carried out: the run, the hit, the recoil.

Until this module the `move_by` / `move_through` resolvers computed the
maneuver's damage class and wrote it in a payload. Nobody moved, nobody
rolled to hit, the target lost nothing and the attacker felt nothing. The
deleted api driver did more (`_resolve_velocity_maneuver`): it gated the
charge on reaching the target, rolled to hit at the maneuver's OCV, and took
a fraction of the damage off the attacker. It also made three errors this
module corrects:

  * it took the fraction of the STUN and BODY that got THROUGH THE
    TARGET'S defenses and applied it to the attacker with no defenses of
    his own. 6E2 p.73's example runs the other way: Starburst rolls "23
    STUN, 8 BODY. Ogre takes full damage ... and Starburst takes half the
    damage - 11 STUN, 4 BODY (he can apply his PD to reduce it, of
    course)". The fraction is of the ROLL, and his defenses apply;
  * it never moved anybody. 6E2 p.72: a Move By is "a Full Move past his
    target ... Hit or miss, the character finishes at the end of his
    movement path"; a Move Through that misses "keeps traveling in a
    straight line through the point where the target was standing";
  * Move Through's attacker always took half. 6E2 p.72: "If the attack did
    no Knockdown or Knockback, then the attacker takes the full damage
    instead".

THE RULE, 6E2 p.72. Move By: (STR/2) + (v/10)d6, -2 OCV / -2 DCV, the
attacker takes one-third. Move Through: STR + (v/6)d6, -v/10 OCV, -3 DCV,
the attacker takes half (full with no Knockback). "Halve a character's STR
before determining the STR damage he does with a Move By" --- halved STR
goes through the cost engine's `strike_dice`, which keeps the half die a
remainder buys (6E2 p.72's own example halves 3d6 to 1 1/2d6 instead; the
rule text is followed, per the engine's standing preference). The DCV
penalty holds until his next Phase, through the same key a martial
maneuver's does (`martial_arts.MANEUVER_DCV_DELTA`).

THE REFUSAL. A charge that cannot end in contact (walls, distance, a drop)
is refused at resolution exactly as enumeration refuses to offer it: he
does not run and does not swing. This is the driver's
`_velocity_charge_refusal`, kept.

RULINGS, labelled: velocity is his full combat Running, the speed he can
reach (6E2 p.72: he "doesn't necessarily have to travel his Full Move to get
the damage for his full velocity"); a Move Through that hits stops where it
hit (6E2 p.73's third follow-through option, "stop where he hit the
target"); the recoil fraction rounds down; and with Knockback switched off
by the campaign the attacker takes half, because "no Knockback" on p.72
describes an immovable target ("it's like running into a wall"), not a
campaign that does not measure it. Knockdown is not modelled, so only a
Knockback that moved the target counts as one.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import ResolvedAction

#: 6E2 p.72: "attacker takes 1/3 damage" / "attacker takes ½ or full damage".
MOVE_BY_RECOIL = 1.0 / 3.0
MOVE_THROUGH_RECOIL = 0.5
MOVE_THROUGH_RECOIL_NO_KNOCKBACK = 1.0
MOVE_BY_OCV = -2
MOVE_BY_DCV = -2
MOVE_THROUGH_DCV = -3
#: Tolerance on "within reach" after a clamped move, in metres.
_REACH_EPS = 1e-6


def damage_dice(*, strength: int, velocity_mps: float, through: bool) -> tuple[int, bool]:
    """(full d6, half d6) for the maneuver, per 6E2 p.72."""
    from kirby_cost.engine.damage import strike_dice

    if through:
        full, half = strike_dice(max(0, int(strength)))
        return full + math.floor(max(0.0, velocity_mps) / 6.0), half
    full, half = strike_dice(max(0, int(strength)) // 2)
    return full + math.floor(max(0.0, velocity_mps) / 10.0), half


def _point_beyond(here, there, total_m: float):
    """The point ``total_m`` from ``here`` along the line through ``there``."""
    from kirby_world.scene import Position

    dx, dy = there.x - here.x, there.y - here.y
    length = math.hypot(dx, dy)
    if length == 0.0:
        return there
    k = total_m / length
    return Position(here.x + dx * k, here.y + dy * k, there.z)


def resolve_velocity_maneuver(session, actor, action: "LegalAction", *,
                              template, roller, through: bool) -> "ResolvedAction":
    from kirby_combat.actions.martial_arts import MANEUVER_DCV_DELTA
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction, _events_since
    from kirby_combat.loop.resolvers import (
        _attack_dice, _move_capacity, _reach_of, _recorded, _stop_at_reach,
    )
    from kirby_combat.models import AttackInput, AttackPower
    from kirby_combat.placement import move_toward
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    start_session = session
    target_id = action.target_id
    if not target_id or target_id not in session.combatants:
        raise UnresolvableAction(action.kind, action.action_id)
    velocity = _move_capacity(actor, "running")
    name = "Move Through" if through else "Move By"

    # THE CHARGE. To within reach of him, on the real map, with his Full Move.
    scene = session.scene
    here = position_of(scene, actor.id) if scene is not None else None
    there = position_of(scene, target_id) if scene is not None else None
    moved_m = 0.0
    if here is not None and there is not None:
        reach = _reach_of(actor, action)
        contact = _stop_at_reach(here, there, reach)
        charged, outcome = move_toward(session, actor.id, contact,
                                       mode="running", distance_m=velocity)
        if outcome is None or not outcome.reachable or distance_3d(
                outcome.landing, there) > reach + _REACH_EPS:
            return _recorded(session, actor, action, None, {
                "kind": action.kind, "target_id": target_id, "hit": False,
                "out_of_reach": True, "stun_dealt": 0, "body_dealt": 0,
                "note": f"the {name} cannot end in contact from here",
            })
        session = charged
        moved_m = distance_3d(here, outcome.landing)

    # THE BLOW.
    stats = actor.combat_stats()
    strength = int(stats.str_)
    full, half = damage_dice(strength=strength, velocity_mps=velocity,
                             through=through)
    str_used = strength if through else strength // 2
    power = AttackPower(
        xmlid="MOVE_THROUGH" if through else "MOVE_BY", name=name,
        damage_dice=full, half_die=half, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=None,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0,
        # 6E2 p.133: STR costs 1 END per 10 points used, the price of any
        # 10 Active Points. The movement's own END is the move's.
        active_points=str_used, is_ranged=False,
    )
    ocv = -math.floor(velocity / 10.0) if through else MOVE_BY_OCV
    dcv = MOVE_THROUGH_DCV if through else MOVE_BY_DCV
    target = session.combatants[target_id]
    me = session.combatants[actor.id]
    attack = AttackInput(
        attacker=me, target=target, power=power, distance_m=None, aim=None,
        dice=_attack_dice(roller, full + (1 if half else 0)),
        ocv_modifier=ocv,
    )
    session, result = resolve_attack_in_session(
        session, attack, template, action_type="strike", roller=roller,
        payload_extras=lambda _r: {
            "maneuver": action.kind, "velocity_mps": velocity,
            MANEUVER_DCV_DELTA: dcv,
        },
    )

    # THE RECOIL: a fraction of what was ROLLED, against his own defenses.
    if result.hit and result.damage is not None:
        if through:
            knocked = (result.knockback is not None
                       and not result.knockback.resisted
                       and result.knockback.distance_m > 0)
            fraction = (MOVE_THROUGH_RECOIL
                        if knocked or not template.use_knockback
                        else MOVE_THROUGH_RECOIL_NO_KNOCKBACK)
        else:
            fraction = MOVE_BY_RECOIL
        session = _recoil(session, actor.id, power, result, fraction,
                          template=template)

    # THE FOLLOW-THROUGH. A Move By ends at the end of his path, hit or
    # miss; a Move Through that missed runs on through where the man stood.
    if here is not None and there is not None and (not through or not result.hit):
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


def _recoil(session, attacker_id, power, result, fraction, *, template):
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.resolution.defense import compute_defense
    from kirby_combat.resolution.status import determine_status_changes
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant
    from kirby_combat.vitals import record_vitals_change

    me = session.combatants[attacker_id]
    stun_rolled = int(int(result.damage.stun) * fraction)
    body_rolled = int(int(result.damage.body) * fraction)
    defense = compute_defense(me, power)
    stun = max(0, stun_rolled - int(defense.total_defense))
    body = max(0, body_rolled - int(defense.total_defense))
    if defense.damage_reduction_pct > 0:
        keep = (100 - defense.damage_reduction_pct) / 100.0
        stun, body = int(stun * keep), int(body * keep)
    if stun or body:
        session, _ = record_vitals_change(session, attacker_id, stun=-stun,
                                          body=-body, reason="maneuver_recoil")
    status = determine_status_changes(
        stun_before=me.current_stun, stun_after=me.current_stun - stun,
        body_before=me.current_body, body_after=me.current_body - body,
        con=adjusted_con(session, me), max_body=me.max_body,
    )
    last = next((e for e in reversed(session.event_log)
                 if getattr(e, "kind", "") == "ActionResolved"), None)
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(attacker_id),
        declaration_event_id=getattr(last, "declaration_event_id", "") or "",
        result_payload={
            "kind": "maneuver_recoil", "target_id": attacker_id,
            "fraction": fraction, "stun_rolled": stun_rolled,
            "body_rolled": body_rolled, "stun_dealt": stun,
            "body_dealt": body, "status_changes": status,
        },
    ))
