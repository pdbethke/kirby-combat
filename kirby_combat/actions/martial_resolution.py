"""A martial maneuver, carried out: the roll, and what it does when it lands.

`actions/maneuver_effects.py` decides WHAT a maneuver does before a die is
rolled (a `MartialEffect`); this module DOES it, and is what the `maneuver`
resolver (`loop/resolvers.py`) hands every offer to. One Attack Roll at the
maneuver's OCV through the one attack door (`resolve_attack_in_session`), the
maneuver's DCV held until his next Phase (6E2 p.68, through
`martial_arts.MANEUVER_DCV_DELTA`), and then the effect:

* a Strike's damage, Target Falls and You Fall (6E2 p.93-94);
* a Grab --- with its free Squeeze when the maneuver does damage (6E2 p.64);
* a Disarm: the STR contest and the weapon knocked 1d6+1m (6E2 p.62);
* Grab Weapon (Takeaway, Disarming Throw): the weapon wrenched away (6E2 p.69,
  6E1 p.379);
* Shove: the man pushed 1m per 5 STR, hurt only by a wall (6E2 p.81);
* Martial Flash: a Flash on the Sense Group it was bought against (6E1 p.228);
* Must Follow Grab: Crush is a Squeeze, Grappling Throw a Throw, of the man
  he is holding, in a later Phase --- "an Attack Action (it doesn't
  automatically succeed, requires an Attack Roll" (6E2 p.64);
* Must Follow Block: refused unless his last Block of THIS attacker succeeded
  and he has not acted since (`reactive.blocking.block_follow_ups`);
* FMove: `actions/martial_fmove.py`, the charge around this same blow.

THE GRAB'S CV, AT THE MANEUVER'S DOOR TOO. 6E2 p.64-66 (Western Hero p.104):
the Grabber and his victim are at 1/2 DCV, full OCV between them and 1/2 OCV
against anybody else (`grappling.grab_cv`). The plain attack and the Throw
applied it; a martial maneuver did not, so a Crush on a held man was rolled
against his full DCV. Every maneuver here takes it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.actions.maneuver_effects import (
    ManeuverDamage, MartialEffect, MustFollow, maneuver_power,
)

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import ResolvedAction


def _unresolvable(action):
    from kirby_combat.loop.registry import UnresolvableAction

    return UnresolvableAction(action.kind, action.action_id)


def martial_attack(session, actor, target, power, *, action, template, roller,
                   ocv_modifier: int, action_type: str, payload_extras,
                   damage_taken_factor: float):
    """One Attack Roll for a maneuver, through the one attack door.

    `_maneuver_attack`'s composition (`loop/resolvers.py`), plus the Grab's
    CV for this pair (see the module docstring).
    """
    from kirby_combat.loop.resolvers import (
        _attack_dice, _grab_cv, _range_to, _with_half_die,
    )
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput
    from kirby_combat.sense_penalties import HTH

    grab = _grab_cv(session, actor, target)
    attack = AttackInput(
        attacker=actor, target=target, power=power,
        distance_m=_range_to(session, actor, target), aim=None,
        dice=_attack_dice(roller, max(0, _with_half_die(power, int(power.damage_dice)))),
        ocv_modifier=ocv_modifier + grab.ocv_delta,
        grab_ocv_factor=grab.ocv_factor, grab_dcv_factor=grab.dcv_factor,
        damage_taken_factor=damage_taken_factor,
    )
    return resolve_attack_in_session(
        session, attack, template, action_type=action_type, roller=roller,
        combat_type=HTH, payload_extras=payload_extras,
    )


def base_payload(actor, target, mv, effect: MartialEffect, result) -> dict:
    """The keys every maneuver row carries --- the PR #5 row, unchanged."""
    from kirby_combat.actions.grab import Grab
    from kirby_combat.actions.martial_arts import MANEUVER_DCV_DELTA
    from kirby_combat.statuses import FELL

    hit = bool(result.hit)
    fell = []
    if hit and effect.target_falls:
        fell.append(target.id)
    # JUDGEMENT: the thrower goes down when the throw is made. 6E2 p.94
    # describes Sacrifice Throw's fall as part of the throw landing ("the
    # victim ... must land within 2m of the Thrower - and the Thrower himself
    # ends up prone"); it says nothing of a miss.
    if hit and effect.actor_falls:
        fell.append(actor.id)
    strength = int(actor.combat_stats().str_)
    payload = {
        "maneuver_id": mv.maneuver_id,
        "maneuver_ocv_delta": int(mv.ocv),
        "maneuver_dc_bonus": effect.damage_classes,
        "target_falls": effect.target_falls,
        "is_prone_after": target.id in fell,
        FELL: fell,
        # 6E2 p.68: a Grab that lands puts the grabber at 1/2 DCV, which
        # "replaces the -2 DCV penalty, it's not in addition to it".
        MANEUVER_DCV_DELTA: (None if (effect.grab and hit) else int(mv.dcv)),
    }
    if effect.grab:
        # THE ROW `Grab.is_grabbed` FOLDS, written on the attack's own row:
        # one Attack Roll took hold, so there is one row.
        payload.update({
            "type": "grab", "success": hit,
            "attacker_id": actor.id,
            "attacker_str": strength + effect.str_bonus,
            "target_str": int(target.combat_stats().str_),
            Grab.HOLDING_STR_BONUS: effect.str_bonus,
        })
    return payload


def resolve_martial(session, actor, action: "LegalAction", mv, effect: MartialEffect,
                    *, template, roller) -> "ResolvedAction":
    """Carry out one decoded maneuver. See the module docstring."""
    from kirby_combat.loop.registry import ResolvedAction, _events_since

    if action.target_id not in session.combatants:
        raise _unresolvable(action)
    target = session.combatants[action.target_id]

    if effect.fmove:
        from kirby_combat.actions.martial_fmove import resolve_fmove

        return resolve_fmove(session, actor, action, mv, effect,
                             template=template, roller=roller)
    if effect.must_follow is MustFollow.GRAB:
        new_session, result = _on_the_held_man(
            session, actor, target, action, mv, effect,
            template=template, roller=roller)
    elif effect.must_follow is MustFollow.BLOCK:
        from kirby_combat.actions.reactive.blocking import block_follow_ups

        if target.id not in block_follow_ups(session, actor.id):
            raise _unresolvable(action)
        new_session, result = blow(session, actor, target, action, mv, effect,
                                   template=template, roller=roller, velocity_mps=0.0)
    else:
        new_session, result = blow(session, actor, target, action, mv, effect,
                                   template=template, roller=roller, velocity_mps=0.0)
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


def blow(session, actor, target, action, mv, effect: MartialEffect, *,
         template, roller, velocity_mps: float):
    """The maneuver's Attack Roll and everything it does on a hit, for every
    family but the held man's (``_on_the_held_man``). Returns (session,
    result); FMove calls it at the end of the charge with his velocity."""
    from kirby_combat import weapons as W

    strength = int(actor.combat_stats().str_)
    power = maneuver_power(mv, effect, strength=strength, velocity_mps=velocity_mps)
    weapon = None
    if effect.disarm or effect.grab_weapon:
        weapon = getattr(action, "_weapon", None)
        if weapon is None or W.holder_of(session, weapon) != target.id:
            raise _unresolvable(action)

    outcome: dict = {}

    def payload(result) -> dict:
        p = base_payload(actor, target, mv, effect, result)
        if velocity_mps:
            p["velocity_mps"] = float(velocity_mps)
        if weapon is not None:
            p.update({"weapon_owner_id": weapon.owner_id,
                      "weapon_id": weapon.weapon_id, "weapon_name": weapon.name})
        if effect.disarm:
            p["disarm_str"] = strength + effect.str_bonus
            if result.hit:
                # 6E2 p.62: the Attack Roll first, then the STR contest.
                # Martial Disarm's bonus is "only for purposes of determining
                # the outcome of the Disarm STR Versus STR Contest" (p.94).
                contest = W.disarm_contest(
                    roller, attacker_str=strength + effect.str_bonus,
                    defender_str=int(target.combat_stats().str_))
                p["disarm_contest"] = contest
                outcome["disarmed"] = contest["won"]
        if effect.grab_weapon:
            p["takeaway_str"] = strength + effect.str_bonus
            if result.hit:
                contest = W.wrench_contest(
                    roller, attacker_str=strength + effect.str_bonus,
                    defender_str=int(target.combat_stats().str_))
                p["takeaway_contest"] = contest
                outcome["taken"] = contest["won"]
        if effect.shove and result.hit:
            p.update(outcome.get("shove_row", {}))
        return p

    shove_move = None
    if effect.shove:
        shove_move, power = _shove_plan(session, actor, target, power, effect)
        outcome["shove_row"] = shove_move["row"] if shove_move else {
            "shove_m": 0.0, "shoved_into": None}

    # A Martial Flash's power carries no damage dice: the roll is to hit, and
    # its Flash dice are rolled after it lands (`_flash`).
    new_session, result = martial_attack(
        session, actor, target, power, action=action, template=template,
        roller=roller, ocv_modifier=int(mv.ocv),
        action_type="grab" if effect.grab else "strike",
        payload_extras=payload, damage_taken_factor=1.0,
    )
    if weapon is not None and outcome.get("disarmed"):
        new_session, _landing = W.knock_away(
            new_session, weapon, attacker_id=actor.id, target_id=target.id,
            roller=roller)
    if weapon is not None and outcome.get("taken"):
        new_session = W.move_weapon(new_session, weapon, by_id=actor.id,
                                    cause=W.TAKEN, holder_id=actor.id, position=None)
    if shove_move is not None and result.hit:
        new_session = _carry_out_shove(new_session, target.id, shove_move,
                                       roller=roller, template=template)
    if effect.damage is ManeuverDamage.FLASH and result.hit:
        new_session = _flash(new_session, actor, target, effect, roller=roller)
    return new_session, result


# ---------------------------------------------------------------------------
# Shove (6E2 p.81)
# ---------------------------------------------------------------------------

def _shove_plan(session, actor, target, power, effect: MartialEffect):
    """Where the Shove would put him, and the damage a wall would do.

    6E2 p.81: "the victim is moved back 1m for every 5 points of STR the
    Shoving character uses ... Shoving does no damage to a target unless he's
    Shoved into a surface such as a wall. In that case, he takes the
    attacker's STR damage, but cannot take more damage than the PD + BODY of
    the object he collides with." The maneuver's [STRDC] is STR "to Shove":
    it moves him further and hurts no harder (as Martial Grab's STR "does not
    add to damage done", 6E2 p.94).

    Planned BEFORE the roll, as `_throw_grabbed` plans its throw, because the
    damage the roll carries depends on whether there is a wall.

    NOT MODELLED: the target resisting with STR or Flight, or dropping to the
    ground on a DEX roll (p.81) --- each is the victim's own choice, which the
    loop does not ask him for; Knockback Resistance reducing the distance is
    "At the GM's option".
    """
    from dataclasses import replace

    from kirby_combat.actions.movement.knockback_movement import (
        away_from, resolve_forced_movement,
    )
    from kirby_world.occupancy import position_of

    strength = int(actor.combat_stats().str_)
    metres = float((strength + effect.str_bonus) // 5)
    scene = session.scene
    start = position_of(scene, target.id) if scene is not None else None
    source = position_of(scene, actor.id) if scene is not None else None
    no_damage = replace(power, name="Shove", damage_dice=0, half_die=False,
                        uses_str=False, no_knockback=True)
    if start is None or source is None or metres <= 0:
        return None, no_damage
    moved = resolve_forced_movement(
        combatant_id=target.id, start=start,
        direction_xy=away_from(source, start), distance_m=metres,
        scene=scene, gravity_scale=float(scene.ambient.gravity_scale),
        airborne=False,
    )
    wall = moved.wall_collision
    shove_power = no_damage
    if wall is not None:
        strike = actor.str_strike_view()
        dice, half = int(strike.damage_dice), bool(strike.half_die)
        if wall.pd is not None:
            cap = int(wall.pd) + int(wall.body)
            if dice >= cap:
                dice, half = cap, False
        shove_power = replace(strike, name="Shove", damage_dice=dice,
                              half_die=half, no_knockback=True,
                              source_id=power.source_id)
    return {
        "start": start, "moved": moved,
        "row": {"shove_m": float(moved.distance_traveled_m),
                "shoved_into": wall.wall_id if wall is not None else None},
    }, shove_power


def _carry_out_shove(session, target_id, plan, *, roller, template):
    from kirby_combat.impact import _record_move, fall

    moved = plan["moved"]
    session = _record_move(session, target_id, plan["start"], moved.travel_end,
                           move_type="shoved", distance_m=moved.distance_traveled_m)
    if moved.fall is not None:
        session, _landed = fall(session, target_id, moved.travel_end,
                                roller=roller, template=template, landing=moved.fall)
    return session


# ---------------------------------------------------------------------------
# Martial Flash (6E1 p.228)
# ---------------------------------------------------------------------------

def _flash(session, actor, target, effect: MartialEffect, *, roller):
    """6E1 p.228: "he rolls the Flash dice and counts the Normal Damage BODY.
    The total number of BODY rolled, minus the target's Flash Defense (if
    any), is the number of Segments the target's Sense(s) is (are) disabled."
    1d6 per DC (kirby-cost ``Maneuver.flash_dc``)."""
    from kirby_combat.actions.flash import Flash
    from kirby_combat.resolution.damage import _body_for_normal_die

    faces = roller.roll_dice(max(0, int(effect.damage_classes)))
    body = sum(_body_for_normal_die(v) for v in faces)
    session, _result = Flash.apply(
        session, attacker_id=actor.id, target_id=target.id,
        sense_group=effect.flash_sense, body_dealt=body,
        flash_defense=int(target.combat_stats().flash_defense or 0),
    )
    return session


# ---------------------------------------------------------------------------
# Must Follow Grab: Crush and Grappling Throw (6E2 p.64)
# ---------------------------------------------------------------------------

def _on_the_held_man(session, actor, target, action, mv, effect: MartialEffect,
                     *, template, roller):
    """A Squeeze (Crush) or a Throw (Grappling Throw) of the man he holds.

    6E2 p.64: "If the Grabber wants to Squeeze, Slam, or Throw his victim in a
    later Phase, doing so is an Attack Action (it doesn't automatically
    succeed, requires an Attack Roll, and so forth) ... If the Attack Roll for
    a Squeeze or Slam fails, the victim takes no damage but remains Grabbed."
    A Squeeze "does regular STR damage ... the character retains his hold";
    a Throw "requires him to let go of the victim".

    * CRUSH is the Squeeze, with the maneuver's DCs (its "[NORMALDC]"). The
      hold stays, hit or miss. A Martial Grab's holding STR does not add
      (p.64: "It doesn't increase the damage done by Squeezing").
    * GRAPPLING THROW ("[NORMALDC] Strike; Target Falls; Must Follow Grab")
      is a Throw: RULING, the hold ends hit or miss, as the plain Throw of a
      held man rules (`resolvers._throw_grabbed`); he falls where he stood,
      since the maneuver throws him down rather than across the room.
    """
    from kirby_combat.actions.grab import RELEASED, Grab

    if Grab.is_grabbed(session, target.id) != (True, actor.id):
        raise _unresolvable(action)
    strength = int(actor.combat_stats().str_)
    power = maneuver_power(mv, effect, strength=strength, velocity_mps=0.0)

    def payload(result) -> dict:
        p = base_payload(actor, target, mv, effect, result)
        if effect.crush:
            p["squeeze"] = True
        else:
            # The row `Grab.is_grabbed` folds as the end of the hold.
            p.update({"type": RELEASED, "attacker_id": actor.id,
                      "target_id": target.id, "thrown_down": bool(result.hit)})
        return p

    return martial_attack(
        session, actor, target, power, action=action, template=template,
        roller=roller, ocv_modifier=int(mv.ocv), action_type="strike",
        payload_extras=payload, damage_taken_factor=1.0,
    )
