"""HERO System 6E knockback calculation."""
from __future__ import annotations

from kirby_combat.models import DiceValues, KnockbackResult
from kirby_combat.template import CombatTemplate


def compute_knockback(
    body_dealt: int,
    kb_resistance: int,
    knockback_multiplier: float,
    dice: DiceValues,
    template: CombatTemplate,
) -> KnockbackResult:
    """Calculate knockback from an attack.

    Args:
        body_dealt: BODY damage that penetrated defenses.
        kb_resistance: Target's total knockback resistance (from defenses + powers).
        knockback_multiplier: Campaign-level scale factor on KB distance
            (normally 1.0; house rules may double it, etc.).
        dice: Pre-rolled dice values; ``dice.knockback`` supplies the KB dice pool.
        template: Active combat template controlling optional rules.

    Returns:
        A :class:`~kirby_combat.models.KnockbackResult` describing the outcome.
    """
    audit: list[str] = []

    # Rule: knockback disabled at campaign level
    if not template.use_knockback:
        audit.append("Knockback disabled by template.")
        return KnockbackResult(dice=0, distance_m=0.0, damage_dice=0, resisted=True, audit=audit)

    effective = body_dealt - kb_resistance
    audit.append(f"Effective BODY for KB: {body_dealt} − {kb_resistance} = {effective}")

    if effective <= 0:
        audit.append("Knockback fully resisted (effective ≤ 0).")
        return KnockbackResult(dice=0, distance_m=0.0, damage_dice=0, resisted=True, audit=audit)

    kb_dice = max(effective // 2, 1)
    audit.append(f"KB dice: max({effective} // 2, 1) = {kb_dice}")

    raw_distance = sum(dice.knockback[:kb_dice])
    distance = raw_distance * knockback_multiplier
    audit.append(
        f"KB distance: sum({dice.knockback[:kb_dice]}) × {knockback_multiplier} = {distance}m"
    )

    damage_dice = int(distance) // 2
    audit.append(f"KB impact damage dice: int({distance}) // 2 = {damage_dice}")

    return KnockbackResult(
        dice=kb_dice,
        distance_m=float(distance),
        damage_dice=damage_dice,
        resisted=False,
        audit=audit,
    )
