"""Presence attacks — PRE/5 dice + situational bonuses + effects ladder.

6E2 p138-139: Presence attacks resolve as PRE/5 d6 dice (round normally).
Situational modifiers add or subtract dice. The roll's BODY (or simple total)
is compared to the target's PRE; the margin determines the effect tier.

Citation: 6E2 p139 (PRE Attack effects table). Note: target's PRE Defense
reduces incoming PRE-attack dice as if it were Resistant Defense.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import StatBlockCombatant
from kirby_combat.tables import _CANNOT_ACT, presence_attack_effect


@dataclass
class PresenceAttackResult:
    attacker_id: str
    target_id: str
    base_dice: int
    bonus_dice: int
    total_dice: int
    target_pre_defense: int          # PRE Defense subtracts dice
    effective_dice: int              # max(0, total_dice - PRE def in dice equivalent)
    roll_total: int                  # sum of dice values
    target_pre: int
    effect: str                      # 6E2 p138 table: no_effect | impressed |
    #                                very_impressed | awed | cowed | overwhelmed
    audit: list[str] = field(default_factory=list)


def base_pre_dice(attacker: StatBlockCombatant) -> int:
    """PRE/5 dice (round normally) per 6E2 p138."""
    return attacker.pre // 5


def resolve_presence_attack(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    dice_values: list[int],
    bonus_dice_from_situation: int = 0,
    target_pre_defense: int = 0,
) -> PresenceAttackResult:
    base_dice = base_pre_dice(attacker)
    total_dice = base_dice + bonus_dice_from_situation
    # PRE Defense reduces incoming dice 1-for-1 (6E2 p138)
    effective_dice = max(0, total_dice - target_pre_defense)

    # Caller passes pre-rolled dice values; we tally the first `effective_dice`
    if effective_dice > len(dice_values):
        raise ValueError(
            f"presence attack expected {effective_dice} dice values, "
            f"got {len(dice_values)}"
        )
    roll_total = sum(dice_values[:effective_dice])
    effect = presence_attack_effect(roll_total, target.pre)

    audit = [
        f"PRE Attack: PRE={attacker.pre}/5={base_dice} base; "
        f"+{bonus_dice_from_situation} situational; "
        f"-{target_pre_defense} PRE Def -> {effective_dice} effective dice",
        f"Roll total={roll_total} vs target PRE={target.pre} -> effect={effect}",
    ]

    return PresenceAttackResult(
        attacker_id=attacker.id, target_id=target.id,
        base_dice=base_dice, bonus_dice=bonus_dice_from_situation,
        total_dice=total_dice, target_pre_defense=target_pre_defense,
        effective_dice=effective_dice, roll_total=roll_total,
        target_pre=target.pre, effect=effect, audit=audit,
    )


def can_act_after(effect: str) -> bool:
    """Whether the target can still act after this Presence Attack result.

    Preserves the previous MEANING under the corrected 6E2 p138 names: only
    the worst tiers stop a target outright. RAW is stricter — at "awed"
    (PRE+20) the target "will not act for 1 Full Phase" (6E2 p139) — but
    consuming the table's mechanical consequences is separate work from
    correcting the table.
    """
    return effect not in _CANNOT_ACT
