"""Unit — pack-of-N combatants abstraction for mass combat."""
import pytest

from kirby_combat.masscombat.unit import Unit, UnitMorale


def test_unit_creation_from_archetype():
    u = Unit.from_archetype(
        id="goons-1", name="Street Thugs",
        archetype_combatant_id="thug-template",
        count=20,
        morale=UnitMorale.STEADY,
    )
    assert u.count == 20
    assert u.aggregate_body_pool == 20 * 10
    assert u.morale == UnitMorale.STEADY


def test_unit_takes_damage_reduces_count_proportionally():
    u = Unit(
        id="u1", name="Goons",
        archetype_combatant_id="thug",
        count=20, initial_count=20,
        aggregate_body_pool=200, morale=UnitMorale.STEADY,
        archetype_body_per=10, archetype_stun_per=15, archetype_dex=10,
    )
    u2 = u.take_aggregate_damage(body=40)
    assert u2.count == 16
    assert u2.aggregate_body_pool == 160


def test_unit_morale_check_on_25_pct_casualties():
    u = Unit(
        id="u1", name="Goons",
        archetype_combatant_id="thug",
        count=20, initial_count=20,
        aggregate_body_pool=200, morale=UnitMorale.STEADY,
        archetype_body_per=10, archetype_stun_per=15, archetype_dex=10,
    )
    u = u.take_aggregate_damage(body=50)
    assert u.needs_morale_check is True


def test_unit_routs_on_failed_morale():
    u = Unit(
        id="u1", name="Goons",
        archetype_combatant_id="thug",
        count=20, initial_count=20,
        aggregate_body_pool=200, morale=UnitMorale.STEADY,
        archetype_body_per=10, archetype_stun_per=15, archetype_dex=10,
    )
    # STEADY -> SHAKEN -> ROUTING
    u = u.fail_morale_check()
    u = u.fail_morale_check()
    assert u.morale == UnitMorale.ROUTING


def test_routing_unit_cannot_act_offensively():
    u = Unit(
        id="u1", name="Goons",
        archetype_combatant_id="thug",
        count=20, initial_count=20,
        aggregate_body_pool=200, morale=UnitMorale.ROUTING,
        archetype_body_per=10, archetype_stun_per=15, archetype_dex=10,
    )
    assert u.can_act_offensively() is False


def test_destroyed_unit_has_zero_count():
    u = Unit(
        id="u1", name="Goons",
        archetype_combatant_id="thug",
        count=20, initial_count=20,
        aggregate_body_pool=200, morale=UnitMorale.STEADY,
        archetype_body_per=10, archetype_stun_per=15, archetype_dex=10,
    )
    u = u.take_aggregate_damage(body=9999)
    assert u.count == 0
    assert u.is_destroyed() is True
