"""HERO System 6E knockback calculation.

Per 6E2 p116 §DETERMINING KNOCKBACK:
    - Attacker rolls a fixed 2d6 (modified by attack/target type by adding or
      removing dice — Killing Attack +1d6 (more KB), fully-Resistant target
      +1d6, Hardened/Resistant +1d6, etc.) and subtracts the SUM from BODY rolled.
    - Result × 2m = knockback distance in meters.
    - Knockback Resistance is meters subtracted from the FINAL distance,
      NOT from BODY before the calculation.
"""
from __future__ import annotations

from kirby_combat.models import KnockbackResult
from kirby_combat.template import CombatTemplate


def compute_knockback(
    body: int,
    knockback_dice: list[int],
    *,
    kb_resistance_m: int = 0,
    knockback_multiplier: float = 1.0,
    template: CombatTemplate | None = None,
) -> KnockbackResult:
    """Calculate knockback per 6E2 p116.

    Args:
        body: BODY rolled by the attack.
        knockback_dice: list of d6 values (each 1..6) — caller rolls 2d6 base
            plus any bonus/penalty dice from attack type or environment.
            E.g., a vanilla Energy Blast against a non-resistant target rolls
            2d6 (2 values); a Killing Attack adds a die (3 values); see
            6E2 p117 modifiers table.
        kb_resistance_m: Meters of Knockback Resistance the target has.
            Subtracted from the final distance, not from BODY.
        knockback_multiplier: Campaign-level scale factor on KB distance
            (normally 1.0; house rules may double it, etc.).
        template: Active combat template. If template.use_knockback is False,
            knockback is suppressed entirely.

    Returns:
        A :class:`~kirby_combat.models.KnockbackResult` describing the outcome.
        damage_dice is the GROUND-impact default (¼ × meters per 6E2 p118);
        callers can override based on what the target slams into using
        compute_impact_damage_dice() (Fix 3).
    """
    audit: list[str] = []

    # Rule: knockback disabled at campaign level
    if template is not None and not template.use_knockback:
        audit.append("Knockback disabled by template.")
        return KnockbackResult(dice=0, distance_m=0.0, damage_dice=0, resisted=True, audit=audit)

    kb_roll = sum(knockback_dice)
    audit.append(
        f"KB dice rolled: {knockback_dice} → sum={kb_roll} (per 6E2 p116, 2d6 + modifiers)"
    )

    # BODY − KB-roll, floored at 0
    delta = max(0, body - kb_roll)
    meters_before_resistance = delta * 2 * knockback_multiplier
    audit.append(
        f"BODY({body}) − KB-roll({kb_roll}) = {delta}; ×2m × mult({knockback_multiplier}) "
        f"= {meters_before_resistance}m before KB-resistance"
    )

    # Apply KB resistance to FINAL distance (not to BODY)
    distance = max(0.0, meters_before_resistance - kb_resistance_m)
    audit.append(
        f"KB resistance {kb_resistance_m}m subtracted from final → distance={distance}m"
    )

    if distance <= 0:
        audit.append("Knockback fully resisted (distance ≤ 0).")
        return KnockbackResult(
            dice=len(knockback_dice),
            distance_m=0.0,
            damage_dice=0,
            resisted=True,
            audit=audit,
        )

    # Default impact-damage dice: open-ground impact = ¼ × meters (6E2 p118).
    # Callers that know the impact surface should override via compute_impact_damage_dice.
    damage_dice = int(distance) // 4
    audit.append(
        f"KB impact damage dice (ground default per 6E2 p118): int({distance}) // 4 = {damage_dice}"
    )

    return KnockbackResult(
        dice=len(knockback_dice),
        distance_m=float(distance),
        damage_dice=damage_dice,
        resisted=False,
        audit=audit,
    )
