"""Mental Entangle — Entangle variant defended by MD, escape via EGO.

Variant of Entangle (6E1 p102) with the following Advantages typically:
- Works Against EGO (defended by Mental Defense, not PD/ED)
- Mental Paralysis (target cannot move, often cannot use mental powers)

Escape uses an EGO contest rather than STR vs Entangle BODY.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import Combatant


@dataclass
class MentalEntangleState:
    """An active mental entangle effect on a target."""
    target_id: str
    entangle_body: int           # remaining BODY of the entangle
    initial_body: int
    blocks_mental_powers: bool = True
    blocks_physical_powers: bool = False


@dataclass
class MentalEntangleResult:
    target_id: str
    body_dealt_to_entangle: int
    md_applied: int              # how much MD reduced incoming damage
    state: MentalEntangleState
    audit: list[str] = field(default_factory=list)


@dataclass
class MentalEscapeResult:
    target_id: str
    method: str                  # "ego_contest"
    roll: int
    target_number: int
    success: bool
    body_reduced: int            # how much BODY removed from entangle
    audit: list[str] = field(default_factory=list)


def apply_mental_entangle(
    attacker: Combatant,
    target: Combatant,
    body_dice_values: list[int],
) -> MentalEntangleResult:
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mental Entangle"
        )
    raw_body = sum(body_dice_values)
    # Mental Entangle's BODY is reduced by Mental Defense per Works Against EGO advantage
    body_after_md = max(0, raw_body - target.md)
    state = MentalEntangleState(
        target_id=target.id,
        entangle_body=body_after_md,
        initial_body=body_after_md,
        blocks_mental_powers=True,
        blocks_physical_powers=False,
    )
    audit = [
        f"Mental Entangle: BODY {raw_body} - MD {target.md} = {body_after_md}",
        "State: paralysis blocks mental powers; physical powers still usable",
    ]
    return MentalEntangleResult(
        target_id=target.id, body_dealt_to_entangle=body_after_md,
        md_applied=target.md, state=state, audit=audit,
    )


def attempt_mental_escape(
    target: Combatant,
    state: MentalEntangleState,
    ego_roll_dice: list[int],
) -> MentalEscapeResult:
    """Target rolls 3d6 EGO Roll; success removes BODY equal to EGO/5 from entangle."""
    if len(ego_roll_dice) != 3:
        raise ValueError(f"EGO roll needs 3d6, got {len(ego_roll_dice)}")
    roll = sum(ego_roll_dice)
    from kirby_cost.engine.rolls import characteristic_roll
    target_number = characteristic_roll(target.ego)
    success = roll <= target_number
    body_reduced = (target.ego // 5) if success else 0
    audit = [
        f"Mental Escape: EGO Roll TN={target_number} roll={roll} "
        f"-> {'SUCCESS' if success else 'FAIL'}",
    ]
    if success:
        audit.append(f"Removed {body_reduced} BODY from mental entangle")
    return MentalEscapeResult(
        target_id=target.id, method="ego_contest", roll=roll,
        target_number=target_number, success=success,
        body_reduced=body_reduced, audit=audit,
    )


def can_use_mental_powers(state: MentalEntangleState) -> bool:
    """A mentally entangled combatant cannot use mental powers."""
    return not state.blocks_mental_powers or state.entangle_body == 0


def can_use_physical_powers(state: MentalEntangleState) -> bool:
    """A mentally entangled combatant CAN still use physical powers (paralysis is mental)."""
    return not state.blocks_physical_powers
