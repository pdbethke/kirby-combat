"""Telepathy — degree ladder, mental awareness gating.

6E1 pg 116: Telepathy reads thoughts. Effect roll vs target's EGO determines
how deep the reader can go. Target is unaware unless they have Mental
Awareness (or are themselves a mentalist) per 6E1 p116.

Telepathy does not damage STUN/BODY.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import Combatant
from kirby_combat.tables import telepathy_degree


@dataclass
class TelepathyResult:
    target_id: str
    target_ego: int
    effect_total: int
    margin: int
    degree: str                  # surface_thoughts | specific_memories | deep_thoughts | subconscious | none
    target_is_aware: bool
    audit: list[str] = field(default_factory=list)


def resolve_telepathy(
    attacker: Combatant,
    target: Combatant,
    effect_dice_values: list[int],
    target_has_mental_awareness: bool = False,
) -> TelepathyResult:
    """Roll effect dice; classify against EGO; flag awareness."""
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Telepathy"
        )
    total = sum(effect_dice_values)
    margin = total - target.ego
    degree = telepathy_degree(total, target.ego)

    # Target only knows the telepath is poking around if they themselves are
    # a mentalist or have explicit Mental Awareness (6E1 p116).
    target_is_aware = bool(target.is_mentalist or target_has_mental_awareness)

    audit = [
        f"Telepathy: effect_dice sum={total} vs EGO={target.ego} -> "
        f"margin={margin} -> degree={degree}; target_aware={target_is_aware}"
    ]
    return TelepathyResult(
        target_id=target.id, target_ego=target.ego,
        effect_total=total, margin=margin, degree=degree,
        target_is_aware=target_is_aware, audit=audit,
    )
