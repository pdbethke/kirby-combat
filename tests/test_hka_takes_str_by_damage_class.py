"""STR on a Killing attack adds Damage Classes, and a Killing DC is a pip.

6E2 p.99: Killing Damage costs 15 Active Points a die, so a DC (5 points)
is +1, two are 1/2d6, three are 1d6. 6E1 p.137: each 5 STR adds a DC to a
STR-using attack, no more than the attack's own DCs (the Doubling Rule).

kirby-cost counted Killing damage in half-die steps until 0.8.0, so a 1d6
HKA with STR 5 was built at 1 1/2d6 (book: 1d6+1) and a 1d6+1 knife lost its
pip. This pins the attack the combat engine actually builds, through
`_build_attack_power` -- the live path every attack view takes.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import _build_attack_power


class _Adder:
    def __init__(self, xmlid):
        self.xmlid = xmlid


class _HKA:
    """An HKA as the loader hands it over: levels, level_value, adders."""
    xmlid = "HKA"
    name = "Claws"
    parent = None
    assigned_modifiers: list = []

    def __init__(self, levels, adders=()):
        self.levels = levels
        self.level_value = 1.0
        self.assigned_adders = [_Adder(a) for a in adders]
        self.id = "claws"


def _dice(power, strength):
    ap = _build_attack_power(power, str_for_augmentation=strength)
    return ap.damage_dice, ap.half_die, ap.plus_one


@pytest.mark.parametrize("strength,expected", [
    (0, (1, False, False)),
    (5, (1, False, True)),      # 1d6+1, not 1 1/2d6
    (10, (1, True, False)),     # 1 1/2d6, not 2d6
    (15, (2, False, False)),
    (30, (2, False, False)),    # the Doubling Rule: 3 DC of STR at most
])
def test_a_1d6_hka(strength, expected):
    assert _dice(_HKA(1), strength) == expected


def test_a_knife_keeps_its_pip():
    """1d6+1 (4 DC) with STR 10 (2 DC) is 6 DC: 2d6."""
    assert _dice(_HKA(1, ["PLUSONEPIP"]), 10) == (2, False, False)
