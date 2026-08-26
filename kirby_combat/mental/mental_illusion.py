"""Mental Illusion — degree + disbelief mechanics.

6E1 pg 109: Mental Illusion projects a sensory hallucination into the target's
mind. Margin over EGO determines fidelity. The illusion lasts until the target
makes a successful EGO Roll vs the illusion's effect total when given a reason
to disbelieve (i.e., the illusion contradicts reality).

Mental Illusion does not directly damage STUN/BODY. Damage from an illusory
attack within an illusion is treated separately per 6E1 p110 (psychosomatic).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import StatBlockCombatant
from kirby_combat.tables import mental_illusion_degree


@dataclass
class MentalIllusionResult:
    target_id: str
    target_ego: int
    effect_total: int
    margin: int
    degree: str
    audit: list[str] = field(default_factory=list)


@dataclass
class DisbeliefResult:
    target_id: str
    roll: int
    target_number: int           # disbelief succeeds if roll <= TN
    success: bool
    illusion_ended: bool
    audit: list[str] = field(default_factory=list)


def resolve_mental_illusion(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    effect_dice_values: list[int],
) -> MentalIllusionResult:
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mental Illusion"
        )
    total = sum(effect_dice_values)
    margin = total - target.ego
    degree = mental_illusion_degree(total, target.ego)
    audit = [
        f"Mental Illusion: effect_dice sum={total} vs EGO={target.ego} -> "
        f"margin={margin} -> degree={degree}"
    ]
    return MentalIllusionResult(
        target_id=target.id, target_ego=target.ego,
        effect_total=total, margin=margin, degree=degree,
        audit=audit,
    )


def attempt_disbelief(
    target: StatBlockCombatant,
    illusion_effect_total: int,
    ego_roll_dice: list[int],
    contradiction_observed: bool,
) -> DisbeliefResult:
    """Target rolls 3d6; success if roll <= EGO + bonus from contradiction.

    Per 6E1 p109, the target only gets a disbelief check when given reason
    to doubt the illusion. The check is an EGO Roll versus the illusion's
    effect total: target rolls 3d6, must roll <= EGO_roll - (effect - EGO).
    Practically: TN = (9 + EGO/5) - max(0, illusion_effect_total - EGO).
    """
    if len(ego_roll_dice) != 3:
        raise ValueError(f"EGO roll needs 3d6, got {len(ego_roll_dice)}")
    audit: list[str] = []
    if not contradiction_observed:
        audit.append("No contradiction; no disbelief attempt allowed")
        return DisbeliefResult(
            target_id=target.id, roll=sum(ego_roll_dice),
            target_number=0, success=False, illusion_ended=False,
            audit=audit,
        )
    roll = sum(ego_roll_dice)
    from kirby_cost.engine.rolls import characteristic_roll
    base_tn = characteristic_roll(target.ego)
    illusion_margin = max(0, illusion_effect_total - target.ego)
    target_number = base_tn - illusion_margin
    success = roll <= target_number
    audit.append(
        f"Disbelief check: EGO Roll TN={target_number} (base {base_tn} - illusion margin {illusion_margin}); "
        f"roll={roll} -> {'SUCCESS' if success else 'FAIL'}"
    )
    return DisbeliefResult(
        target_id=target.id, roll=roll,
        target_number=target_number, success=success,
        illusion_ended=success, audit=audit,
    )
