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
        Entangle, counted_body, entangle_default_defenses,
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
                )
            results.append((victim_id, result))
    return ResolvedAction(
        session=s, kind=action.kind, action_id=action.action_id,
        result=results, events=list(s.event_log[before:]),
    )
