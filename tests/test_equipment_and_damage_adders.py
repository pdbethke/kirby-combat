"""Carried weapons count, and damage adders are read.

TWO DEFECTS, FOUND BY TRYING TO RUN A FIGHT WITH A REAL CHARACTER.

1. NOTHING READ `hero.equipment`. A grep for `.equipment` across
   `kirby_combat/` found ONE reference, in a serialization stub. So a
   character whose weapon is carried rather than innate fought BARE-HANDED,
   and nothing complained -- a combatant with no attacks is a legal
   combatant. HERO Designer's own "Lawman (Armed)" carries a Colt
   Peacemaker, a Winchester '73, a Coach Gun, a Bowie Knife and Handcuffs.
   `attacks` returned []. The loader had parsed all six correctly; only
   `HeroCombatant.attacks` never looked.

2. DAMAGE ADDERS WERE IGNORED. HD buys the fractional part of an attack as
   an ADDER, not a level: a 1d6+1 pistol is one level plus PLUSONEPIP, and
   a half-die knife is ZERO levels plus PLUSONEHALFDIE. Reading only
   `levels * level_value` under-counted every such attack and rounded the
   ones bought entirely out of adders down to NOTHING. Measured over a
   random 120-character sample: 50 attack powers carry one, including a
   Black Mamba's Bite and a hunting dog's Bite -- both 0d6, attacks that
   could not hurt anything.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import _compute_damage_dice


class _Power:
    """A power in the shape `_compute_damage_dice` reads."""

    def __init__(self, levels=0, level_value=1.0, adders=()):
        self.levels = levels
        self.level_value = level_value
        self.assigned_adders = [type("A", (), {"xmlid": x})() for x in adders]


# ---- Damage adders ----

def test_levels_alone_still_read_as_before():
    assert _compute_damage_dice(_Power(levels=8), "ENERGYBLAST") == (8, False, False)


def test_a_half_die_adder_adds_a_half_die():
    """A knife bought as ZERO levels plus PLUSONEHALFDIE is ½d6, not 0d6."""
    assert _compute_damage_dice(
        _Power(levels=0, adders=("PLUSONEHALFDIE",)), "HKA",
    ) == (0, True, False)


def test_a_pip_adder_sets_plus_one():
    assert _compute_damage_dice(
        _Power(levels=1, adders=("PLUSONEPIP",)), "RKA",
    ) == (1, False, True)


def test_both_adders_together():
    assert _compute_damage_dice(
        _Power(levels=2, adders=("PLUSONEHALFDIE", "PLUSONEPIP")), "RKA",
    ) == (2, True, True)


def test_two_halves_make_a_whole_die():
    """A power that already rounded to a half from its levels goes up a
    full die rather than carrying two halves."""
    assert _compute_damage_dice(
        _Power(levels=3, level_value=0.5, adders=("PLUSONEHALFDIE",)), "RKA",
    ) == (2, False, False)


def test_minus_one_pip_is_deliberately_not_handled():
    """`AttackPower` carries `half_die` and `plus_one` and has no way to
    say "minus one pip". It appears ONCE in the whole corpus against 345
    PLUSONEHALFDIE and 197 PLUSONEPIP, so the cost of leaving it is one
    weapon reading a pip high -- against a new field on a shared
    dataclass. Pinned so the choice is visible rather than forgotten."""
    assert _compute_damage_dice(
        _Power(levels=1, adders=("MINUSONEPIP",)), "RKA",
    ) == (1, False, False)


def test_adders_are_read_from_either_field_name():
    """Synthetic and loaded powers spell the list differently."""
    p = _Power(levels=0)
    p.assigned_adders = []
    p.adders = [type("A", (), {"xmlid": "PLUSONEHALFDIE"})()]
    assert _compute_damage_dice(p, "HKA") == (0, True, False)


def test_an_unrelated_adder_changes_nothing():
    assert _compute_damage_dice(
        _Power(levels=4, adders=("CHARGES", "OAF")), "RKA",
    ) == (4, False, False)


# ---- Equipment as attacks ----

class _Hero:
    def __init__(self, powers=(), equipment=()):
        self.name = "Test"
        self.powers = list(powers)
        self.equipment = list(equipment)
        self.skills, self.talents, self.perks = [], [], []
        self.complications = []

    def characteristic_value(self, xmlid): return {"STR": 10}.get(xmlid.upper(), 10)
    def temporal_characteristic(self, xmlid, ctx=None): return self.characteristic_value(xmlid)


def _weapon(xmlid: str, name: str, levels: int):
    p = _Power(levels=levels)
    p.xmlid, p.name = xmlid, name
    p.sub_powers = []
    return p


def _combatant(hero):
    from kirby_combat.hero_view import HeroCombatant, HeroCombatState

    return HeroCombatant(
        id="t", hero=hero,
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )


def test_a_carried_weapon_is_an_attack():
    c = _combatant(_Hero(equipment=[_weapon("RKA", "Colt Peacemaker", 1)]))
    assert [a.name for a in c.attacks] == ["Colt Peacemaker"]


def test_a_character_with_only_equipment_is_not_unarmed():
    """The defect exactly: `attacks` was empty and the character fought
    bare-handed."""
    assert _combatant(_Hero(equipment=[_weapon("RKA", "Winchester", 2)])).attacks


def test_innate_powers_come_first():
    """`attack_view` returns the first match for an xmlid, so a pistol must
    not shadow the power a character was built around."""
    c = _combatant(_Hero(
        powers=[_weapon("RKA", "Heat Vision", 3)],
        equipment=[_weapon("RKA", "Pistol", 1)],
    ))
    assert [a.name for a in c.attacks] == ["Heat Vision", "Pistol"]


def test_non_attack_equipment_is_ignored():
    """Handcuffs and a holster are not attacks."""
    c = _combatant(_Hero(equipment=[
        _weapon("RKA", "Pistol", 1), _weapon("FAST_DRAW", "Holster", 0),
    ]))
    assert [a.name for a in c.attacks] == ["Pistol"]


def test_a_hero_with_no_equipment_attribute_still_works():
    """Not every build shape carries the list."""
    hero = _Hero(powers=[_weapon("RKA", "Blast", 2)])
    del hero.equipment
    assert [a.name for a in _combatant(hero).attacks] == ["Blast"]
