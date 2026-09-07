"""The 2d6-1 rung of the killing-damage ladder.

HERO's killing dice do not go up in whole dice. The ladder runs
1d6, 1d6+1, 1.5d6, 2d6-1, 2d6 -- and HD buys the four fractional rungs as
ADDERS on a power whose LEVELS says only the die count below them.

The 2d6-1 rung is `MINUSONEPIP`, whose ALIAS in the file is the giveaway:
"+1d6 -1". It ADDS a die and takes back a pip. Reading the name as
"one pip less than the levels" loses most of a die.

Found on the O.K. Corral: the Colt Peacemaker is RKA LEVELS=1 plus
MINUSONEPIP -- 2d6-1 -- and came through as 1d6. Five of the nine men on
that lot carried one, so the benchmark was being fought at half power by
the side that carried them.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from kirby_combat.hero_view import _compute_damage_dice
from kirby_combat.models import AttackPower
from kirby_combat.resolution.damage import compute_damage
from kirby_combat.template import CombatTemplate


class _Adder:
    def __init__(self, xmlid): self.xmlid = xmlid


class _Power:
    """The shape `_compute_damage_dice` reads: levels, level_value, adders."""
    def __init__(self, levels, adders=(), level_value=1.0):
        self.levels = levels
        self.level_value = level_value
        self.assigned_adders = [_Adder(a) for a in adders]


def test_minus_one_pip_adds_a_die_and_takes_back_a_pip():
    """LEVELS=1 + MINUSONEPIP is 2d6-1, not 1d6."""
    full, half, plus_one, minus_one = _compute_damage_dice(
        _Power(1, ["MINUSONEPIP"]), "RKA")
    assert (full, half, plus_one, minus_one) == (2, False, False, True)


def test_the_whole_ladder_reads_in_order():
    """1d6, 1d6+1, 1.5d6, 2d6-1 -- each rung distinct, each above the last."""
    rungs = [
        ((1, ()), (1, False, False, False)),                 # 1d6
        ((1, ("PLUSONEPIP",)), (1, False, True, False)),     # 1d6+1
        ((1, ("PLUSONEHALFDIE",)), (1, True, False, False)), # 1.5d6
        ((1, ("MINUSONEPIP",)), (2, False, False, True)),    # 2d6-1
        ((2, ()), (2, False, False, False)),                 # 2d6
    ]
    for (levels, adders), expected in rungs:
        assert _compute_damage_dice(_Power(levels, adders), "RKA") == expected


def _gun(minus_one: bool) -> AttackPower:
    return AttackPower(
        xmlid="RKA", name="Colt Peacemaker", damage_dice=2, half_die=False,
        plus_one=False, minus_one=minus_one, damage_type="killing",
        defense_type="pd", range_m=100.0, uses_str=False, str_min=10,
        armor_piercing=0, penetrating=0, increased_stun_mult=0, is_ranged=True)


class _Dice:
    def __init__(self, damage, stun_multiplier): 
        self.damage = damage
        self.stun_multiplier = stun_multiplier


def test_a_killing_attack_loses_one_body_to_the_pip():
    """2d6-1 rolling 4 and 5 is 8 BODY, not 9."""
    template = CombatTemplate.default_6e_superheroic()
    dice = _Dice([4, 5], [3])
    with_pip = compute_damage(_gun(True), dice, template)
    without = compute_damage(_gun(False), dice, template)
    assert without.body - with_pip.body == 1
    assert with_pip.body == 8


def test_the_pip_cannot_drive_damage_below_zero():
    """A minimum roll must not produce negative BODY."""
    template = CombatTemplate.default_6e_superheroic()
    result = compute_damage(_gun(True), _Dice([0], [1]), template)
    assert result.body >= 0
