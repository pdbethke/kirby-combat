"""Damage Reduction and Damage Negation stop the class they were bought for.

6E1 p.185: Damage Reduction is bought "separately for each type of attack
(Physical, Energy or Mental)" (Main6E.hdt's own definition text), and Damage
Negation's DCs are bought per class on its PHYSICAL / ENERGY / MENTAL Adders.

THE DEFECT. `hero_view._power_to_defense_item` read `power.input_value` ---
the api's COLUMN name --- and a loaded power carries `input`. Every class came
back empty, and `resolution/defense.py` applies an empty class to every
attack: Ravel's 50% Physical and 50% Energy Damage Reduction also halved a
Mental Blast. Damage Negation read the same wrong field and took its DCs from
OPTIONID digits it does not have.
"""
from __future__ import annotations

import pytest
from kirby_cost.io.build_json import build_from_json

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import AttackPower
from kirby_combat.resolution.defense import compute_defense
from tests.corpus import require_authored, require_template


def _attack(defense_type: str, *, killing: bool = False) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Probe", damage_dice=6, half_die=False,
        plus_one=False, damage_type="killing" if killing else (
            "mental" if defense_type == "mental" else "normal"),
        defense_type=defense_type, range_m=50.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="probe", is_ranged=True,
    )


def _ravel() -> HeroCombatant:
    return HeroCombatant.from_build(require_authored("Ravel"), id="ravel")


def test_ravels_damage_reduction_names_its_classes():
    """His build: 50% Resistant DR, INPUT "Physical", and the same vs Energy."""
    classes = sorted(d.damage_class for d in _ravel().defenses
                     if d.damage_reduction_pct)
    assert classes == ["energy", "physical"]


@pytest.mark.parametrize("defense_type, want", [
    ("pd", 50), ("ed", 50), ("mental", 0),
])
def test_ravels_damage_reduction_stops_only_what_he_bought_it_against(
        defense_type, want):
    """The Mental case is the defect: it read 50% on origin/main."""
    profile = compute_defense(_ravel(), _attack(defense_type))
    assert profile.damage_reduction_pct == want


# --- Damage Negation, per-class Adders (no corpus character carries one) ---

BASE = {
    "name": "Negator", "template": "builtIn.Superheroic6E.hdt",
    "base_points": 400, "disad_points": 0, "experience": 0,
    "characteristics": [], "skills": [], "perks": [], "talents": [],
    "martial_arts": [], "disadvantages": [], "equipment": [],
}


def _adder(xmlid: str, levels: int) -> dict:
    return {"xmlid": xmlid, "levels": levels, "base_cost": 0.0,
            "level_cost": 5.0, "level_value": 1.0, "required": True,
            "selected": True}


@pytest.fixture
def negator():
    require_template()
    power = {
        "id": "dn1", "xmlid": "DAMAGENEGATION", "levels": 0,
        "base_cost": 0.0, "alias": "Damage Negation", "name": "Dense",
        "adders": [_adder("PHYSICAL", 2), _adder("ENERGY", 1),
                   _adder("MENTAL", 0)],
    }
    return HeroCombatant.from_build(build_from_json(dict(BASE, powers=[power])),
                                    id="negator")


def test_damage_negation_is_one_defense_per_class_bought(negator):
    got = sorted((d.damage_class, d.damage_negation) for d in negator.defenses
                 if d.damage_negation)
    assert got == [("energy", 1), ("physical", 2)]


@pytest.mark.parametrize("defense_type, want", [
    ("pd", 2), ("ed", 1), ("mental", 0),
])
def test_damage_negation_negates_only_its_own_class(negator, defense_type, want):
    assert compute_defense(negator, _attack(defense_type)).damage_negation == want


def test_a_damage_reduction_naming_no_class_raises():
    """No default: an unknown class applied to everything IS the defect."""
    from kirby_combat.hero_view import _damage_reduction_class

    class _DR:
        name = "Odd"
        input = "Sonic"

    with pytest.raises(ValueError, match="names no damage class"):
        _damage_reduction_class(_DR(), "LVL50RESISTANT")


def test_mental_option_is_mental_whatever_the_input_says():
    """Three corpus rows read INPUT "Energy" on HD's LVL75MENTAL option."""
    from kirby_combat.hero_view import _damage_reduction_class

    class _DR:
        name = "Mind Shield"
        input = "Energy"

    assert _damage_reduction_class(_DR(), "LVL75MENTAL") == "mental"


def test_the_page_names_the_class():
    """The Brief (PR #9) said "vs any class" for every corpus DR, because
    the class was never read."""
    from kirby_combat.brief_detail import reductions

    assert reductions(_ravel()) == [
        "Damage Reduction 50% vs Physical attacks (resistant)",
        "Damage Reduction 50% vs Energy attacks (resistant)",
    ]
