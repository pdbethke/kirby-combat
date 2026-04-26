"""Mental combat pipeline — OMCV vs DMCV to-hit.

Parallel to kirby_combat.resolution.to_hit but uses OMCV/DMCV and does not
apply range penalties or line-of-sight gating by default (6E1 pg 105).
Specific limitations (e.g., "Requires LoS") are applied by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import Combatant


@dataclass
class MentalToHitResult:
    hit: bool
    roll: int
    target_number: int
    margin: int
    effective_ocv: int          # OMCV after modifiers
    effective_dcv: int          # DMCV after modifiers
    range_penalty: int          # always 0 for mental attacks
    audit: list[str] = field(default_factory=list)


def resolve_mental_to_hit(
    attacker: Combatant,
    target: Combatant,
    dice_values: list[int],
    distance_m: float | None = None,
    ocv_modifier: int = 0,
    dcv_modifier: int = 0,
) -> MentalToHitResult:
    """3d6 mental to-hit using OMCV vs DMCV.

    Target number = 11 + attacker.omcv - target.dmcv + modifiers. Roll <= TN hits.
    No range penalty. No LoS gating at this layer.
    """
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use mental combat"
        )
    if len(dice_values) != 3:
        raise ValueError(f"mental to-hit needs 3d6, got {len(dice_values)}")

    audit: list[str] = []
    roll = sum(dice_values)
    eff_ocv = attacker.omcv + ocv_modifier
    eff_dcv = target.dmcv + dcv_modifier
    target_number = 11 + eff_ocv - eff_dcv
    hit = roll <= target_number
    margin = target_number - roll

    audit.append(
        f"Mental to-hit: 3d6={roll} vs TN=11+{eff_ocv}-{eff_dcv}={target_number} -> "
        f"{'HIT' if hit else 'MISS'} (margin {margin})"
    )

    return MentalToHitResult(
        hit=hit, roll=roll, target_number=target_number,
        margin=margin, effective_ocv=eff_ocv, effective_dcv=eff_dcv,
        range_penalty=0, audit=audit,
    )
