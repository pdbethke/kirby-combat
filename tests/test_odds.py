"""`kirby_combat.odds` prices an attack by the resolver's own rules.

The seam: for a few dice, every one of the 6^n rolls is handed to the attack
door's damage step (`damage_taken`) and averaged, and `average_through`
must agree exactly. Its shortcut (one roll per (total, Normal BODY) pair)
is only correct if nothing the damage step reads depends on anything else
about the faces; brute force says whether it does.
"""
from __future__ import annotations

import itertools

import pytest
from fixtures.synthetic_hero import synthetic_combatant

from kirby_combat import odds
from kirby_combat.models import AttackPower, DefenseItem, DiceValues
from kirby_combat.resolution.damage_taken import damage_taken
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _gun(dice=3, *, killing=False, pen=0, ap=0, half=False):
    return AttackPower(
        xmlid="RKA" if killing else "ENERGYBLAST", name="gun",
        damage_dice=dice, half_die=half, plus_one=False,
        damage_type="killing" if killing else "normal",
        defense_type="ed", range_m=50.0, uses_str=False, str_min=0,
        armor_piercing=ap, penetrating=pen, increased_stun_mult=0,
        is_ranged=True, source_id="gun")


def _man(*, ed=10, red=0, armour=0, dcv=5):
    return synthetic_combatant(
        id="t", name="t", ocv=5, dcv=dcv, omcv=3, dmcv=3, spd=4, dex=13,
        ego=10, str_=10, con=15, pre=10, rec=5, pd=10, ed=ed, rpd=0, red=red,
        md=0, power_defense=0, flash_defense=0, max_stun=30, max_body=10,
        max_end=30, current_stun=30, current_body=10, current_end=30,
        defenses=[DefenseItem(name="plate", ed=armour, red=armour,
                              is_resistant=True)] if armour else [])


def _brute(power, target):
    n = power.damage_dice + (1 if power.half_die else 0)
    mults = range(1, 7) if power.damage_type == "killing" else [None]
    stun = body = 0.0
    count = 0
    for faces in itertools.product(range(1, 7), repeat=n):
        for m in mults:
            t = damage_taken(power, target, DiceValues(
                damage=list(faces), stun_multiplier=[m] if m else []), TEMPLATE)
            stun += t.stun
            body += t.body
            count += 1
    return stun / count, body / count


@pytest.mark.parametrize("power,target", [
    (_gun(3), _man(ed=8)),
    (_gun(3, pen=1), _man(ed=40)),
    (_gun(2, killing=True), _man(ed=5, armour=3)),
    (_gun(2, killing=True, pen=1), _man(ed=30, armour=30)),
    (_gun(3, ap=1), _man(ed=12)),
    (_gun(2, half=True), _man(ed=4)),
])
def test_average_through_is_the_resolvers_average(power, target):
    got = odds.average_through(power, target, TEMPLATE)
    stun, body = _brute(power, target)
    assert got.stun == pytest.approx(stun)
    assert got.body == pytest.approx(body)


def test_a_penetrating_blast_always_gets_stun_through():
    """6E1 p.344: one STUN per Normal BODY on the dice, whatever the ED ---
    on average 1 a die (4 faces of 6 give 1, a 6 gives 2)."""
    through = odds.average_through(_gun(4, pen=1), _man(ed=200), TEMPLATE)
    assert through.stun == pytest.approx(4.0)
    assert through.body == 0.0


def test_the_dice():
    assert odds.chance_of_rolling(10) == pytest.approx(0.5)
    rolls = odds.damage_rolls(4)
    assert sum(p for _, p in rolls) == pytest.approx(1.0)
    assert sum(p * sum(r) for r, p in rolls) == pytest.approx(14.0)


def test_a_burst_of_one_is_one_shot():
    me, him = _man(), _man(dcv=4)
    one = odds.expected(me, him, _gun(4), shots=1, distance_m=5.0, template=TEMPLATE)
    burst = odds.expected(me, him, _gun(4), shots=1, distance_m=5.0, template=TEMPLATE)
    assert burst == one and one.hits == pytest.approx(one.chance_to_hit)


def test_more_shots_land_more_hits_on_an_easy_man():
    me, him = _man(), _man(dcv=1)
    one = odds.expected(me, him, _gun(4), shots=1, distance_m=5.0, template=TEMPLATE)
    five = odds.expected(me, him, _gun(4), shots=5, distance_m=5.0, template=TEMPLATE)
    assert five.hits > 1.5 * one.hits and five.stun > 1.5 * one.stun
