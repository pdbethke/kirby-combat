"""Mass combat — Unit aggregation + aggregate resolution."""
from kirby_combat.masscombat.unit import Unit, UnitMorale
from kirby_combat.masscombat.resolution import (
    UnitAttackResult, attack_vs_unit, aoe_vs_unit,
    attack_vs_individual_from_unit, unit_attack_dc_bonus,
    declare_offensive, cycle_morale,
)

__all__ = [
    "Unit", "UnitMorale",
    "UnitAttackResult", "attack_vs_unit", "aoe_vs_unit",
    "attack_vs_individual_from_unit", "unit_attack_dc_bonus",
    "declare_offensive", "cycle_morale",
]
