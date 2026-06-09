"""Object-damage resolver — break a destructible Construct via DEF + BODY
(HERO 6E2 p176-177). A focused pure unit, NOT a branch inside resolve_attack:
a construct has no OCV/DCV/defenses/knockback/status, and a deliberate attack on
an immobile construct auto-hits. Reuses compute_damage for BODY (never re-rolls
dice by hand). Spec 2026-06-09 §1.2.
"""
from __future__ import annotations

from dataclasses import dataclass, replace  # noqa: F401  # replace used by Task 4
from typing import Iterable  # noqa: F401  # Iterable used by Task 4

from kirby_combat.models import AttackPower, DiceValues
from kirby_combat.template import CombatTemplate
from kirby_combat.resolution.damage import compute_damage
from kirby_combat.scene import Construct


@dataclass(frozen=True)
class ConstructDamageResult:
    obj_id: str
    body_rolled: int
    def_value: int
    body_through: int
    body_before: int
    body_after: int
    destroyed: bool
    audit: list[str]


def apply_attack_to_construct(
    power: AttackPower,
    dice: DiceValues,
    construct: Construct,
    template: CombatTemplate,
) -> ConstructDamageResult:
    """Apply one attack to a destructible construct. Raises ValueError if the
    construct is not destructible (no DEF/BODY)."""
    if not construct.destructible:
        raise ValueError(f"construct {construct.obj_id!r} is not destructible")
    dmg = compute_damage(power, dice, template)
    body_rolled = dmg.body
    body_through = max(0, body_rolled - construct.def_value)
    body_before = construct.body
    body_after = body_before - body_through
    destroyed = body_after <= 0
    audit = [
        f"{body_rolled} BODY rolled vs DEF {construct.def_value} "
        f"-> {body_through} through; BODY {body_before}->{max(0, body_after)}"
        + (" (DESTROYED)" if destroyed else "")
    ]
    return ConstructDamageResult(
        obj_id=construct.obj_id, body_rolled=body_rolled, def_value=construct.def_value,
        body_through=body_through, body_before=body_before,
        body_after=max(0, body_after), destroyed=destroyed, audit=audit,
    )
