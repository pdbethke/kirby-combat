"""Shared test fixtures for kirby-combat."""
import pytest

from kirby_combat.models import AttackPower, DefenseItem
from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate


@pytest.fixture
def superhero_template():
    return CombatTemplate(name="Test Superheroic")


@pytest.fixture
def blaster():
    return Combatant(
        id="blaster", name="Blaster",
        ocv=8, dcv=7, omcv=5, dmcv=5,
        spd=6, dex=26, ego=15, str_=20, con=25, pre=20, rec=10,
        pd=10, ed=15, rpd=5, red=10, md=5,
        power_defense=0, flash_defense=0,
        max_stun=50, max_body=15, max_end=50,
        current_stun=50, current_body=15, current_end=50,
        attacks=[
            AttackPower(
                xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
            AttackPower(
                xmlid="RKA", name="Killing Blast", damage_dice=3,
                half_die=False, plus_one=True,
                damage_type="killing", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
        defenses=[DefenseItem(name="Force Field", pd=5, ed=5, rpd=5, red=5)],
    )


@pytest.fixture
def brick():
    return Combatant(
        id="brick", name="Brick",
        ocv=6, dcv=4, omcv=0, dmcv=0,
        spd=4, dex=18, ego=10, str_=60, con=30, pre=20, rec=15,
        pd=25, ed=15, rpd=15, red=5, md=0,
        power_defense=0, flash_defense=0,
        max_stun=60, max_body=20, max_end=60,
        current_stun=60, current_body=20, current_end=60,
        knockback_resistance=10,
    )
