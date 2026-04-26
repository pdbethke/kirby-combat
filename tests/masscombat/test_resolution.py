"""Mass combat resolution — aggregate attacks, morale cycling."""
import pytest

from kirby_combat.masscombat.unit import Unit, UnitMorale
from kirby_combat.masscombat.resolution import (
    attack_vs_unit, aoe_vs_unit, attack_vs_individual_from_unit,
    unit_attack_dc_bonus, declare_offensive, cycle_morale,
)


def _make_unit(count=20, morale=UnitMorale.STEADY) -> Unit:
    return Unit.from_archetype(
        id="u1", name="Goons", archetype_combatant_id="thug",
        count=count, morale=morale,
        body_per=10, stun_per=15, dex=10,
    )


def test_attack_vs_unit_aggregates_damage_across_members():
    u = _make_unit(count=20)
    r = attack_vs_unit(u, body_damage=40)
    assert r.body_dealt == 40
    assert r.new_unit.count == 16


def test_attack_vs_individual_from_unit_uses_archetype_stats():
    u = _make_unit(count=20)
    snap = attack_vs_individual_from_unit(u)
    assert snap == {"dex": 10, "body_per": 10, "stun_per": 15}


def test_unit_attacks_aggregate_dc_scales_with_count():
    assert unit_attack_dc_bonus(_make_unit(count=4)) == 0
    assert unit_attack_dc_bonus(_make_unit(count=10)) == 2
    assert unit_attack_dc_bonus(_make_unit(count=30)) == 5


def test_area_of_effect_vs_unit_hits_proportional_members():
    u = _make_unit(count=20)
    r = aoe_vs_unit(u, body_damage_per_member=2)   # 40 BODY total
    assert r.body_dealt == 40
    assert r.new_unit.count == 16


def test_morale_check_triggered_when_25_pct_loss_reached():
    u = _make_unit(count=20)
    r = attack_vs_unit(u, body_damage=50)   # drops 5 members = 25%
    assert r.morale_check_triggered is True


def test_rout_prevents_subsequent_offensive_declarations():
    u = _make_unit(count=20, morale=UnitMorale.ROUTING)
    assert declare_offensive(u) is False
    # cycle_morale on a failed check while already routing -> BROKEN
    u2 = cycle_morale(u, succeeded=False)
    assert u2.morale == UnitMorale.BROKEN
