"""HERO System 6E action classes and attack resolution."""
from __future__ import annotations

from kirby_combat.actions.killing import KillingAttackAction
from kirby_combat.actions.ranged import RangedAttackAction
from kirby_combat.actions.strike import StrikeAction
from kirby_combat.models import AttackInput, AttackResult
from kirby_combat.template import CombatTemplate


def resolve_attack(attack: AttackInput, template: CombatTemplate) -> AttackResult:
    """Resolve a single attack, picking the right action class automatically.

    Routing logic:
    - ``damage_type == "killing"`` -> KillingAttackAction
    - ``range_m is not None``      -> RangedAttackAction
    - otherwise                    -> StrikeAction
    """
    power = attack.power

    if power.damage_type == "killing":
        action = KillingAttackAction()
    elif power.range_m is not None:
        action = RangedAttackAction()
    else:
        action = StrikeAction()

    return action.resolve(attack, template)


__all__ = [
    "resolve_attack",
    "KillingAttackAction",
    "RangedAttackAction",
    "StrikeAction",
]
