"""HERO System 6E knockback calculation.

Per 6E2 p116 §DETERMINING KNOCKBACK:
    - Attacker rolls a fixed 2d6 (modified by attack/target type by adding or
      removing dice — Killing Attack +1d6 (more KB), fully-Resistant target
      +1d6, Hardened/Resistant +1d6, etc.) and subtracts the SUM from BODY rolled.
    - Result × 2m = knockback distance in meters.
    - Knockback Resistance is meters subtracted from the FINAL distance,
      NOT from BODY before the calculation.

Per 6E2 p118 §Knockback Damage, the impact damage dice depend on what the
target slams into (the page's own three-line table):
    - Open ground: ¼ × meters in d6.
    - A structure, KB ≤ 2 × (PD + BODY): ½ × meters in d6, capped at PD + BODY,
      and the target STOPS.
    - A structure, KB > 2 × (PD + BODY): PD + BODY dice; the structure shatters
      and the target continues through the hole.

CORRECTED 2026-10-26. This module had the comparison inverted: it compared
HALF the meters against the threshold and let a SMALL knockback pass through
a wall while a large one stopped dead. The book's Mechanon example (22m into
a 6 PD / 2 BODY wall -> 8d6 and through; into 6 PD / 6 BODY -> 11d6 and
stops) is the regression test.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.models import KnockbackResult
from kirby_combat.template import CombatTemplate


@dataclass(frozen=True)
class ImpactTarget:
    """A structure the target may slam into. None means open ground.

    6E2 p118: "Regardless of the amount of Knockback rolled, the most dice of
    Knockback damage a character can take when he hits a structure equals the
    PD + BODY of the structure. If he's Knocked Back for more meters than two
    times (2x) the structure's PD + BODY, he takes PD + BODY dice of damage,
    the structure (or part thereof) shatters, and he continues through the
    hole (otherwise, he stops)."

    ``breakable=False`` is a structure that cannot shatter (an authored
    indestructible wall): the cap still applies, and he always stops.
    """
    pd: int           # object's resistant PD
    body: int         # object's resistant BODY
    breakable: bool = True   # if False, the structure never shatters

    @property
    def threshold_m(self) -> int:
        """Meters of knockback above which the structure shatters: 2*(PD+BODY)."""
        return 2 * (self.pd + self.body)


def does_knockback(power) -> bool:
    """Can this power knock anybody back at all (6E2 p.116)?

    "You should limit Knockback to attacks that do damage by directly
    striking the target - for example, punches, Blasts, Killing Attacks"
    -- so physical and energy damage against PD or ED. "Attacks that don't
    inflict BODY damage (such as Mental Blasts and Attack Powers bought
    with the AVAD Advantage) usually don't cause Knockback." And No
    Knockback (6E1 p.147) "never does Knockback".

    Does Knockback (+1/4, HD's DOESKB; 6E1 p.335) "enables an Attack Power
    that normally doesn't do Knockback to do Knockback. The attacker should
    count the Normal Damage BODY on the effect dice (even if the attack
    doesn't do BODY damage)" -- which is the BODY `compute_damage` counts
    for every normal attack, AVAD included.
    """
    if getattr(power, "no_knockback", False):
        return False
    if getattr(power, "does_knockback", False):
        return True
    if (getattr(power, "defense_type", "") or "").lower() not in ("pd", "ed"):
        return False
    if getattr(power, "avad", False) and not getattr(power, "avad_does_body", False):
        return False
    return True


def knockback_body(power, body_rolled: int, bonus: int) -> int:
    """The BODY the Knockback roll is subtracted from (6E2 p.116).

    The BODY rolled plus any BODY added for Knockback purposes (an Autofire
    burst's +1 per further hit, 6E1 p.329), doubled for Double Knockback:
    6E1 p.336, "the amount of BODY is doubled for the purposes of
    determining Knockback before the Knockback Roll is made (If the Power
    ... allows the character to add points of BODY for Knockback purposes,
    add those points of BODY before applying the doubling ...)".
    """
    total = int(body_rolled) + int(bonus)
    return total * 2 if getattr(power, "double_knockback", False) else total


def compute_impact_damage_dice(distance_m: float, impact_target: ImpactTarget | None) -> tuple[int, bool]:
    """Compute (impact damage dice, target_passed_through) per 6E2 p118.

    Distance travelled before the impact does not matter (6E2 p.118: "there's
    no 'deceleration'"): ``distance_m`` is the whole knockback rolled.
    """
    if distance_m <= 0:
        return (0, False)

    if impact_target is None:
        # Ground impact: 1d6 per 4m.
        return (int(distance_m) // 4, False)

    cap = impact_target.pd + impact_target.body
    if impact_target.breakable and distance_m > impact_target.threshold_m:
        return (cap, True)
    # "1d6 Normal Damage for every full 2m of Knockback taken", capped.
    return (min(int(distance_m) // 2, cap), False)


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
        # 6E2 p.116: "If the result is 0, the defender is Knocked Down."
        # RULING: only a BODY-minus-roll of exactly 0 knocks him down. A
        # positive result that Knockback Resistance cancels leaves him
        # standing -- the Power exists to keep a man on his feet, and the
        # page's Knockdown sentence is about the roll, not the remainder.
        knocked_down = body - kb_roll == 0
        audit.append(
            "Knocked Down (BODY - KB roll = 0, 6E2 p116)." if knocked_down
            else "Knockback fully resisted (distance ≤ 0).")
        return KnockbackResult(
            dice=len(knockback_dice),
            distance_m=0.0,
            damage_dice=0,
            resisted=True,
            target_passed_through=False,
            knocked_down=knocked_down,
            audit=audit,
        )

    # Impact damage per 6E2 p118: depends on what the target slams into.
    damage_dice, passed_through = compute_impact_damage_dice(distance, impact_target)
    if impact_target is None:
        audit.append(
            f"Impact damage (open ground, ¼ × m per 6E2 p118): {int(distance)}//4 = {damage_dice}d6"
        )
    elif passed_through:
        audit.append(
            f"Impact damage (structure shattered: {int(distance)}m > 2x(PD+BODY)"
            f" = {impact_target.threshold_m}m): PD+BODY = {damage_dice}d6; target "
            f"continues through"
        )
    else:
        audit.append(
            f"Impact damage (structure, ½ × m capped at PD+BODY "
            f"{impact_target.pd}+{impact_target.body}): {damage_dice}d6; target stops"
        )

    return KnockbackResult(
        dice=len(knockback_dice),
        distance_m=float(distance),
        damage_dice=damage_dice,
        resisted=False,
        target_passed_through=passed_through,
        audit=audit,
    )
