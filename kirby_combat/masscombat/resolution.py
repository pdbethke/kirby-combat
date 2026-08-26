"""Aggregate resolution for mass combat — attacks vs/from Units."""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.masscombat.unit import Unit, UnitMorale
from kirby_combat.models import StatBlockCombatant


@dataclass
class UnitAttackResult:
    target_id: str
    body_dealt: int
    new_unit: Unit
    morale_check_triggered: bool
    audit: list[str] = field(default_factory=list)


def attack_vs_unit(unit: Unit, body_damage: int) -> UnitAttackResult:
    """Apply aggregate body damage to a unit; flag morale check if 25%+ lost."""
    new_unit = unit.take_aggregate_damage(body_damage)
    audit = [
        f"Unit {unit.id}: -{body_damage} BODY -> count {unit.count}->{new_unit.count}"
    ]
    return UnitAttackResult(
        target_id=unit.id, body_dealt=body_damage,
        new_unit=new_unit,
        morale_check_triggered=new_unit.needs_morale_check,
        audit=audit,
    )


def aoe_vs_unit(unit: Unit, body_damage_per_member: int) -> UnitAttackResult:
    """AoE hits all members of the unit; aggregate damage = damage * count."""
    aggregate = body_damage_per_member * unit.count
    return attack_vs_unit(unit, aggregate)


def attack_vs_individual_from_unit(unit: Unit) -> dict[str, int]:
    """Treat a single unit member as an individual using archetype stats.

    Returns the stat snapshot used for the attack roll.
    """
    return {
        "dex": unit.archetype_dex,
        "body_per": unit.archetype_body_per,
        "stun_per": unit.archetype_stun_per,
    }


def unit_attack_dc_bonus(unit: Unit) -> int:
    """A massed unit attacks with extra DC scaling with count.

    Per generic mass-combat conventions: +1 DC per 5 members above 5,
    capped at +5 (a 30+ unit). Below 5 members no bonus.
    """
    if unit.count < 5:
        return 0
    return min(5, (unit.count - 5) // 5 + 1)


def declare_offensive(unit: Unit) -> bool:
    """Routing/Broken units cannot declare offensive actions."""
    return unit.can_act_offensively()


def cycle_morale(unit: Unit, succeeded: bool) -> Unit:
    """Apply morale check outcome.

    On success, morale stays the same (or in 6E we model 'recovers one tier'
    only via explicit rally; this helper just doesn't change it).
    On failure, drop one tier.
    """
    if succeeded:
        return unit
    return unit.fail_morale_check()
