"""An Area Flash and an Area Entangle: everyone in it, from one roll.

`enumeration.py` offers a Flash or an Entangle with the BUILD's power on
the offer, and its resolver (`loop/resolvers._resolve_flash`,
`_resolve_entangle`) blinds or binds the one man named. Bought with Area Of
Effect, the book says otherwise:

  * 6E1 p.321: an Area Of Effect power "affects all the characters in the
    area ... it affects them all the same", one roll against the target
    point, DCV 3 (6E2 p.42).
  * Flash, 6E1 p.228: "he rolls the Flash dice and counts the Normal Damage
    BODY"; an Explosion "loses 1d6 of effect per 2m out from the center"
    (also p.325). And p.326's Kasdrevan: a Selective or Nonselective Flash
    makes "an Attack Roll (with all applicable modifiers) against each
    target in the radius. Any target hit by this second roll is Flashed."
  * Entangle, 6E1 p.220: "An Entangle Explosion loses 1 BODY and 1 PD/1 ED
    for each 2m out from the center" (p.325 says the same).

So the use is made exactly as an Area attack's is --- `area_attack.area_use`,
the one place an Area is rolled, scattered, filled, paid for and written
down --- and each man in it is Flashed or Entangled through the same
`Flash.apply` / `Entangle.apply` the one-target resolvers use, with the one
BODY roll every victim shares.

NOT BUILT, and so not offered (`area_effect_unbuilt`): a Constant or Damage
Over Time Flash or Entangle (a Constant Area Entangle's "BODY of the most
recent roll made prior to his entering", p.220, needs a zone of its own),
and any Area part `power_modifiers` cannot read.

RULING, labelled: a Flash of several Sense Groups blinds the first, as the
one-target resolver does (`_resolve_flash`).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from kirby_combat.power_modifiers import AreaShape, AreaTargeting

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import ResolvedAction


def area_effect_unbuilt(power: Any) -> list[str]:
    """Why a shaped Flash or Entangle cannot be carried out, or []."""
    from kirby_combat.attack_shapes import shape_of

    area, constant, dot = shape_of(power)
    out: list[str] = []
    if constant or dot is not None:
        out.append("Constant or Damage Over Time Flash or Entangle")
    if area is not None:
        out.extend(area.unbuilt)
        if area.shape in (AreaShape.SURFACE, AreaShape.ANY):
            out.append(f"{area.shape.value} Flash or Entangle")
    return out


def is_area_effect(power: Any) -> bool:
    from kirby_combat.attack_shapes import shape_of

    return shape_of(power)[0] is not None


def _view(actor, power):
    """The power as an attack view: its Area, its range, its END."""
    from kirby_combat.hero_view import _build_attack_power

    return _build_attack_power(power, hero=getattr(actor, "hero", None))


def _per_target_hit(session, actor, victim, view, dice_to_hit, template):
    """6E1 p.326: "a separate Attack Roll against every target in the area
    ... at that target's normal DCV; the character suffers any relevant
    modifiers to his OCV, such as the Range Modifier"."""
    from kirby_combat.actions.recording import _fold_session_cvs
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit

    positions = getattr(getattr(session, "scene", None), "combatant_positions", None) or {}
    a, v = positions.get(actor.id), positions.get(victim.id)
    distance = (math.dist((a.x, a.y, a.z), (v.x, v.y, v.z))
                if a is not None and v is not None and view.is_ranged else None)
    attack = AttackInput(attacker=session.combatants[actor.id], target=victim,
                         power=view, distance_m=distance, aim=None,
                         dice=DiceValues(to_hit=dice_to_hit))
    return resolve_to_hit(_fold_session_cvs(session, attack, None), template)


def resolve_area_effect(session, actor, action: "LegalAction", *, template,
                        roller, kind: str) -> "ResolvedAction":
    """Flash or Entangle everyone in the Area (see the module docstring)."""
    from kirby_combat.actions.area_attack import area_use, explosion_dice_lost
    from kirby_combat.actions.entangle import (
        Entangle, both_take_damage, counted_body, entangle_default_defenses,
        transparency_of,
    )
    from kirby_combat.actions.flash import Flash
    from kirby_combat.loop.registry import ResolvedAction
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.perception import flash_groups

    if kind not in ("flash", "entangle"):
        raise ValueError(f"no Area effect for kind {kind!r}")
    power = action._attack_view
    target = session.combatants.get(action.target_id)
    if power is None or target is None:
        from kirby_combat.loop.registry import UnresolvableAction

        raise UnresolvableAction(action.kind, action.action_id)
    view = _view(actor, power)
    spec = view.area
    before = len(session.event_log)
    dice_count = max(1, int(getattr(power, "levels", 0) or 0))
    attack = AttackInput(
        attacker=session.combatants[actor.id], target=target, power=view,
        distance_m=None, aim=None,
        dice=DiceValues(to_hit=roller.roll_dice(3),
                        damage=roller.roll_dice(dice_count)),
    )
    placed = area_use(session, attack, template, roller=roller,
                      declaration_event_id=None, action_type=kind,
                      combat_type=None)
    s = placed.session
    results = []
    if placed.failed is None:
        rolled = sorted(attack.dice.damage)
        per_target = spec.targeting in (AreaTargeting.SELECTIVE,
                                        AreaTargeting.NONSELECTIVE)
        groups = sorted(flash_groups(power)) or ["sight"]
        for victim_id, distance in placed.victims:
            victim = s.combatants[victim_id]
            if per_target:
                hit = _per_target_hit(s, actor, victim, view,
                                      roller.roll_dice(3), template)
                if not hit.hit:
                    results.append((victim_id, None))
                    continue
            lost = (explosion_dice_lost(distance, killing=False)
                    if spec.explosion else 0)
            if kind == "flash":
                # 6E1 p.228: "loses 1d6 of effect per 2m"; the largest die
                # first (p.325).
                kept = rolled[: max(0, len(rolled) - lost)]
                s, result = Flash.apply(
                    s, attacker_id=actor.id, target_id=victim_id,
                    sense_group=groups[0], body_dealt=counted_body(kept),
                    flash_defense=int(victim.combat_stats().flash_defense or 0),
                )
            else:
                pd, ed = entangle_default_defenses(dice_count)
                pd = int(getattr(power, "entangle_pd", 0) or pd)
                ed = int(getattr(power, "entangle_ed", 0) or ed)
                # 6E1 p.220: "loses 1 BODY and 1 PD/1 ED for each 2m".
                body = max(0, counted_body(rolled) - lost)
                if body <= 0:
                    results.append((victim_id, None))
                    continue
                s, result = Entangle.apply(
                    s, attacker_id=actor.id, target_id=victim_id,
                    entangle_body=body, entangle_pd=max(0, pd - lost),
                    entangle_ed=max(0, ed - lost),
                    transparency=transparency_of(power),
                    both_take_damage=both_take_damage(power),
                )
            results.append((victim_id, result))
    return ResolvedAction(
        session=s, kind=action.kind, action_id=action.action_id,
        result=results, events=list(s.event_log[before:]),
    )


# ---------------------------------------------------------------------------
# An Area Drain (6E1 p.143, p.197, p.321)
# ---------------------------------------------------------------------------

def area_drain_unbuilt(power: Any) -> list[str]:
    """Why a shaped Drain cannot be carried out, or [].

    Built: an Instant Radius, Cone or Line Drain bought against
    characteristics. 6E1 p.143: "If an Adjustment Power has this Advantage,
    it affects everyone in the area equally".

    Not built, so not offered: a Constant or Damage Over Time Drain (no
    zone carries an Adjustment), a Surface or Any Area one (as for Flash and
    Entangle above), an Explosion (6E1 p.325 writes how an Explosion loses
    effect for damage, Flash and Entangle, and for nothing else), and a
    Drain bought against a power type rather than a characteristic (each
    victim's powers are his own; which of them the one roll reaches is not
    something an Area use can name).
    """
    from kirby_combat.adjustments import characteristic_targets

    out = area_effect_unbuilt(power)
    from kirby_combat.attack_shapes import shape_of

    area = shape_of(power)[0]
    if area is not None and area.explosion:
        out.append("Explosion Drain (6E1 p.325 defines no Explosion for it)")
    if characteristic_targets(power) is None:
        out.append("Area Drain against a power rather than a characteristic")
    return out


def resolve_area_drain(session, actor, action: "LegalAction", *, template, roller):
    """Drain everyone in the Area, from one Attack Roll and one Effect Roll.

    6E1 p.197's Drain, made as an Area use (`area_attack.area_use`: the roll
    at the target point, DCV 3, the scatter, who is in it, END): "it affects
    everyone in the area equally" (6E1 p.143), so the one Effect Roll is
    each victim's, less HIS Power Defense (p.197), halved against a defence
    (p.143). A Selective or Nonselective Area rolls again against each one
    (6E1 p.326). Returns (session, payload) as `resolve_aid_or_drain` does.
    """
    from kirby_combat.actions.adjust import (
        STANDARD_FADE_PER_TURN, apply_adjustment, fade_interval_turns,
    )
    from kirby_combat.actions.area_attack import area_use
    from kirby_combat.adjustments import (
        characteristic_targets, halved_for, roll_effect,
    )
    from kirby_combat.models import AttackInput, DiceValues

    power = action._attack_view
    target = session.combatants.get(action.target_id)
    if power is None or target is None:
        from kirby_combat.loop.registry import UnresolvableAction

        raise UnresolvableAction(action.kind, action.action_id)
    view = _view(actor, power)
    spec = view.area
    attack = AttackInput(
        attacker=session.combatants[actor.id], target=target, power=view,
        distance_m=None, aim=None, dice=DiceValues(to_hit=roller.roll_dice(3)),
    )
    placed = area_use(session, attack, template, roller=roller,
                      declaration_event_id=None, action_type="drain",
                      combat_type=None)
    s = placed.session
    payload: dict = {"kind": "drain", "area": True, "target_id": target.id,
                     "hit": bool(placed.to_hit is not None and placed.to_hit.hit),
                     "victims": {}}
    if placed.failed is not None or not placed.victims:
        return s, payload
    elements = characteristic_targets(power)
    rolled = roll_effect(power, roller)
    payload["rolled"] = rolled
    interval = fade_interval_turns(power)
    per_target = spec.targeting in (AreaTargeting.SELECTIVE, AreaTargeting.NONSELECTIVE)
    for victim_id, _distance in placed.victims:
        victim = s.combatants[victim_id]
        if per_target:
            hit = _per_target_hit(s, actor, victim, view, roller.roll_dice(3), template)
            if not hit.hit:
                payload["victims"][victim_id] = {"hit": False}
                continue
        power_defense = int(victim.combat_stats().power_defense)
        through = max(0, rolled - power_defense)
        drained = {}
        for element in elements:
            points = halved_for(element, through)
            if points:
                s, moved = apply_adjustment(
                    s, actor.id, victim_id, element, -points,
                    fade_rate_per_turn=STANDARD_FADE_PER_TURN,
                    fade_interval_turns=interval,
                )
                drained[element.stat] = {"character_points": -points, "points_moved": moved}
        payload["victims"][victim_id] = {"hit": True, "power_defense": power_defense,
                                         "drained": drained}
    return s, payload


# ---------------------------------------------------------------------------
# An Area Mind Control (6E1 p.154)
# ---------------------------------------------------------------------------

#: 6E1 p.154: "Characters target Area Of Effect Mental Powers using OMCV
#: against DMCV 3."
AREA_MENTAL_DMCV = 3


def area_mind_control_unbuilt(power: Any) -> list[str]:
    """Why a shaped Mind Control cannot be carried out, or [].

    Built: an Instant Radius, Cone or Line Mind Control (8 corpus views).
    Not built: Constant / Damage Over Time / Surface / Any Area (as for
    Flash above), an Explosion (no page says how a mental effect falls off),
    and a power with an Activation Roll (the Area use here is rolled on
    OMCV, and the Activation Roll goes with the physical use's door).
    """
    from kirby_combat.attack_shapes import shape_of
    from kirby_combat.hero_view import _activation_roll

    out = area_effect_unbuilt(power)
    area = shape_of(power)[0]
    if area is not None and area.explosion:
        out.append("Explosion Mind Control (no page defines its fall-off)")
    if _activation_roll(power) is not None:
        out.append("Activation Roll on an Area Mind Control")
    return out


def resolve_area_mind_control(session, actor, action: "LegalAction", *,
                              template, roller) -> "ResolvedAction":
    """Mind Control everyone in the Area with ONE order (6E1 p.154).

    "Characters target Area Of Effect Mental Powers using OMCV against DMCV
    3. A character doesn't need to have Line Of Sight on all possible
    targets in the Area Of Effect ... he need only have LOS to the target
    point", and "the effect must be the same for everyone in the Area Of
    Effect" --- one order, and (as every Area's one damage roll, 6E1 p.321)
    one Effect Roll, each victim's EGO + the order and his Mental Defense
    against it (`resolve_mind_control_in_session`). The use is placed like
    any Area (`area_attack.area_use`, scatter on a miss included) with the
    OMCV roll handed in as its Attack Roll. A Selective or Nonselective Area
    rolls again, OMCV against each victim's own DMCV (6E1 p.326).
    """
    from kirby_combat.actions.area_attack import area_use
    from kirby_combat.cv_modifiers import effective_omcv_for
    from kirby_combat.enumeration import _src_id
    from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction
    from kirby_combat.mental.attack_roll import mental_attack_roll
    from kirby_combat.mental.mental_combat import resolve_mental_to_hit
    from kirby_combat.mental.recording import resolve_mind_control_in_session
    from kirby_combat.models import AttackInput, DiceValues

    power = action._attack_view
    target = session.combatants.get(action.target_id)
    if power is None or target is None or action.order is None:
        raise UnresolvableAction(action.kind, action.action_id)
    before = len(session.event_log)
    view = _view(actor, power)
    spec = view.area
    me = session.combatants[actor.id]
    to_hit = resolve_mental_to_hit(
        me, target, roller.roll_dice(3),
        ocv_modifier=effective_omcv_for(session, actor.id) - int(me.omcv),
        dcv_modifier=AREA_MENTAL_DMCV - int(target.dmcv),
    )
    attack = AttackInput(attacker=me, target=target, power=view, distance_m=None,
                         aim=None, dice=DiceValues(), fixed_to_hit=to_hit)
    placed = area_use(session, attack, template, roller=roller,
                      declaration_event_id=None, action_type="mind_control",
                      combat_type=None)
    s = placed.session
    results = []
    if placed.failed is None and placed.victims:
        levels = int(getattr(power, "levels", 0) or 0)
        effect = roller.roll_dice(max(1, levels))
        per_target = spec.targeting in (AreaTargeting.SELECTIVE,
                                        AreaTargeting.NONSELECTIVE)
        for victim_id, _distance in placed.victims:
            victim = s.combatants[victim_id]
            roll = (mental_attack_roll(s, s.combatants[actor.id], victim, roller)
                    if per_target else to_hit)
            if not roll.hit:
                results.append((victim_id, None))
                continue
            s, result = resolve_mind_control_in_session(
                s, s.combatants[actor.id], victim, list(effect),
                order=action.order, source_id=_src_id(power), to_hit=roll,
                declaration_event_id=placed.decl_id,
            )
            results.append((victim_id, result))
    return ResolvedAction(
        session=s, kind=action.kind, action_id=action.action_id,
        result=results, events=list(s.event_log[before:]),
    )
