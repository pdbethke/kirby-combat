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


#: 6E2 p.138's Presence Attack Modifiers table: "In combat, -1d6". Every PA
#: resolved during a fight takes it, so a driver resolving one inside a combat
#: session adds this unconditionally. It lives here, beside `base_pre_dice`,
#: because it is a rule about how many dice you roll -- not a driver setting.
IN_COMBAT_DICE_MODIFIER = -1

#: Why a Stunned target is immune, quotable in an audit trail. The rule itself
#: is enforced by `resolve_presence_attack`'s `target_stunned` branch.
STUNNED_IMMUNE_REASON = (
    "target is Stunned or recovering from being Stunned and cannot be "
    "affected by Presence Attacks (6E2 p.106)"
)


def base_pre_dice(attacker: StatBlockCombatant) -> int:
    """PRE/5 dice (round normally) per 6E2 p138."""
    return attacker.pre // 5


def resolve_presence_attack(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    dice_values: list[int],
    bonus_dice_from_situation: int = 0,
    target_pre_defense: int = 0,
    target_stunned: bool = False,
) -> PresenceAttackResult:
    """Resolve one Presence Attack.

    `target_stunned`, new in Task 3 of ``conditions-must-bite``, defaults
    to ``False`` so every existing caller (none of which pass it) gets
    today's behaviour back unchanged. 6E2 p.106: "A character who's
    Stunned or recovering from being Stunned... cannot be affected by
    Presence Attacks." This function stays a pure resolver of the values
    it's handed -- it takes no `CombatSession` and does not derive
    Stunned itself; a session-aware caller (this engine's own recording
    layer, or kirby-api's driver) is expected to read
    ``statuses.stunned_or_recovering_for`` and pass the bool in, exactly
    the same shape as `target_pre_defense` already being a caller-supplied
    number rather than something this function looks up.
    """
    base_dice = base_pre_dice(attacker)
    total_dice = base_dice + bonus_dice_from_situation
    # PRE Defense reduces incoming dice 1-for-1 (6E2 p138)
    effective_dice = max(0, total_dice - target_pre_defense)

    if target_stunned:
        # 6E2 p.106: a Stunned (or recovering) target cannot be affected
        # at all -- forced to "no_effect" regardless of the roll, and no
        # dice are consumed/tallied since nothing about the attack is
        # actually applied to the target.
        roll_total = 0
        effect = "no_effect"
        audit = [
            f"PRE Attack: PRE={attacker.pre}/5={base_dice} base; "
            f"+{bonus_dice_from_situation} situational; "
            f"-{target_pre_defense} PRE Def -> {effective_dice} effective dice",
            "Target is Stunned (or recovering from being Stunned) -- "
            "cannot be affected by Presence Attacks (6E2 p.106) -> "
            "effect=no_effect",
        ]
        return PresenceAttackResult(
            attacker_id=attacker.id, target_id=target.id,
            base_dice=base_dice, bonus_dice=bonus_dice_from_situation,
            total_dice=total_dice, target_pre_defense=target_pre_defense,
            effective_dice=effective_dice, roll_total=roll_total,
            target_pre=target.pre, effect=effect, audit=audit,
        )

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
