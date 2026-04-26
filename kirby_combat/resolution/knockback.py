"""HERO System 6E knockback calculation.

Per 6E2 p116 §DETERMINING KNOCKBACK:
    - Attacker rolls a fixed 2d6 (modified by attack/target type by adding or
      removing dice — Killing Attack +1d6 (more KB), fully-Resistant target
      +1d6, Hardened/Resistant +1d6, etc.) and subtracts the SUM from BODY rolled.
    - Result × 2m = knockback distance in meters.
    - Knockback Resistance is meters subtracted from the FINAL distance,
      NOT from BODY before the calculation.

Per 6E2 p118 §Knockback Damage, the impact damage dice depend on what the
target slams into:
    - Open ground: ¼ × meters in d6.
    - Breakable object/wall (KB ≤ 2 × (PD + BODY)): ½ × meters in d6, target passes through.
    - Immovable object/wall (KB > 2 × (PD + BODY)): PD + BODY dice, target stops.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.models import KnockbackResult
from kirby_combat.template import CombatTemplate


@dataclass(frozen=True)
class ImpactTarget:
    """An object the target may slam into. None means open ground.

    Per 6E2 p118:
        - breakable=True + (KB ≤ 2×(PD+BODY)): the target breaks through; impact
          damage = ½ × meters in d6.
        - breakable=False (immovable wall): target stops at the object;
          impact damage = PD + BODY dice.
        - breakable=True but KB > 2×(PD+BODY): treated as immovable for damage
          purposes (the object resists the full force).
    """
    pd: int           # object's resistant PD
    body: int         # object's resistant BODY
    breakable: bool = True   # if False, target hits an immovable wall

    @property
    def threshold_dice(self) -> int:
        """Dice count above which the breakable object is overwhelmed (RAW: 2*(PD+BODY))."""
        return 2 * (self.pd + self.body)


def compute_impact_damage_dice(distance_m: float, impact_target: ImpactTarget | None) -> tuple[int, bool]:
    """Compute (impact damage dice, target_passed_through) per 6E2 p118.

    Args:
        distance_m: The knockback distance (post-resistance) in meters.
        impact_target: The surface/object the target slams into. None = open ground.

    Returns:
        (damage_dice, target_passed_through).
        target_passed_through is True iff the target broke through a breakable
        object; False for ground impacts and for immovable walls.
    """
    if distance_m <= 0:
        return (0, False)

    if impact_target is None:
        # Ground impact: ¼ × meters
        return (int(distance_m) // 4, False)

    half_meters = int(distance_m) // 2
    if impact_target.breakable and half_meters <= impact_target.threshold_dice:
        # Breakable object: ½ × meters in d6, target passes through.
        return (half_meters, True)

    # Immovable object (or breakable but the KB is too small to break through):
    # PD + BODY dice, target stops.
    return (impact_target.pd + impact_target.body, False)


def compute_knockback(
    body: int,
    knockback_dice: list[int],
    *,
    kb_resistance_m: int = 0,
    knockback_multiplier: float = 1.0,
    template: CombatTemplate | None = None,
    impact_target: ImpactTarget | None = None,
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
        impact_target: What the target slams into at the end of the knockback
            path. None means open ground (default). Per 6E2 p118 the impact
            damage dice depend on the surface (ground=¼m, breakable=½m,
            immovable=PD+BODY).

    Returns:
        A :class:`~kirby_combat.models.KnockbackResult` describing the outcome.
        ``damage_dice`` is the appropriate impact damage per 6E2 p118 based on
        the supplied ``impact_target``.
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
            target_passed_through=False,
            audit=audit,
        )

    # Impact damage per 6E2 p118: depends on what the target slams into.
    damage_dice, passed_through = compute_impact_damage_dice(distance, impact_target)
    if impact_target is None:
        audit.append(
            f"Impact damage (open ground, ¼ × m per 6E2 p118): {int(distance)}//4 = {damage_dice}d6"
        )
    elif impact_target.breakable and (int(distance) // 2) <= impact_target.threshold_dice:
        audit.append(
            f"Impact damage (breakable object, ½ × m): {int(distance)}//2 = {damage_dice}d6; "
            f"target passes through"
        )
    else:
        audit.append(
            f"Impact damage (immovable object, PD+BODY = {impact_target.pd}+{impact_target.body}"
            f" = {damage_dice}d6); target stops"
        )

    return KnockbackResult(
        dice=len(knockback_dice),
        distance_m=float(distance),
        damage_dice=damage_dice,
        resisted=False,
        target_passed_through=passed_through,
        audit=audit,
    )
