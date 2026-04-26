"""Mind Control — degree ladder + EGO+N effect rolls.

6E1 pg 101: Mind Control rolls effect dice (typically 1d6 per 5 Active Points
worth of Mind Control). Compare total to target's EGO; the margin (total - EGO)
determines what tier of command the controller can issue.

The target gets one EGO roll per phase (11 + EGO/5) to break free.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import Combatant
from kirby_combat.tables import mind_control_degree


@dataclass
class MindControlResult:
    """Result of a Mind Control resolution."""
    target_id: str
    target_ego: int
    effect_total: int
    margin: int                         # effect_total - target_ego
    degree: str                         # one of: none, ego_push, simple, contrary, violent
    audit: list[str] = field(default_factory=list)


@dataclass
class MindControlState:
    """Active Mind Control state on a target."""
    target_id: str
    degree: str
    effect_total: int


def resolve_mind_control(
    attacker: Combatant,
    target: Combatant,
    effect_dice_values: list[int],
) -> MindControlResult:
    """Roll effect dice; classify against target's EGO via degree ladder."""
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mind Control"
        )
    total = sum(effect_dice_values)
    margin = total - target.ego
    degree = mind_control_degree(total, target.ego)
    audit = [
        f"Mind Control: effect_dice sum={total} vs EGO={target.ego} -> "
        f"margin={margin} -> degree={degree}"
    ]
    return MindControlResult(
        target_id=target.id, target_ego=target.ego,
        effect_total=total, margin=margin, degree=degree,
        audit=audit,
    )


def can_break_out_with_ego_roll(target: Combatant, ego_roll_dice: list[int]) -> bool:
    """Target rolls 3d6 against (9 + EGO/5). Roll <= TN succeeds.

    6E1 pg 41 — Characteristic Rolls are made on 3d6, and the target number is
    9 + (Characteristic / 5). With EGO=10, TN = 11; with EGO=20, TN = 13.

    Per 6E1 p101 Mind Control: "the target may attempt an EGO Roll each Phase
    as a Free Action" to break free.
    """
    if len(ego_roll_dice) != 3:
        raise ValueError(f"EGO roll needs 3d6, got {len(ego_roll_dice)}")
    roll = sum(ego_roll_dice)
    target_number = 9 + target.ego // 5
    return roll <= target_number
