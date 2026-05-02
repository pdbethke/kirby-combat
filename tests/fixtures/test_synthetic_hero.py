"""Tests for the synthetic_combatant test helper itself.

Confirms the helper produces a HeroCombatant whose flat-field reads
match the kwargs passed in — the contract that lets us mass-migrate
``Combatant(...)`` → ``synthetic_combatant(...)`` across the test
suite without behavioural drift.
"""
from __future__ import annotations

from kirby_combat.hero_view import HeroCombatant
from .synthetic_hero import synthetic_combatant


def test_returns_hero_combatant():
    c = synthetic_combatant(id="t", name="Test")
    assert isinstance(c, HeroCombatant)


def test_flat_kwargs_round_trip_via_properties():
    c = synthetic_combatant(
        id="hero", name="Hero",
        ocv=10, dcv=8, omcv=4, dmcv=4, spd=5,
        dex=20, ego=15, str_=25, con=20, pre=18, rec=8,
        pd=10, ed=10, rpd=4, red=4, md=5,
        power_defense=2, flash_defense=2,
        max_stun=50, max_body=14, max_end=50,
        current_stun=42, current_body=12, current_end=37,
        knockback_resistance=2, is_npc=True,
    )
    # All read paths line up: legacy-shaped flat property reads
    assert c.id == "hero"
    assert c.name == "Hero"
    assert c.ocv == 10
    assert c.dcv == 8
    assert c.spd == 5
    assert c.str_ == 25
    assert c.pd == 10
    assert c.rpd == 4
    assert c.red == 4
    assert c.md == 5
    assert c.power_defense == 2
    assert c.max_stun == 50
    assert c.current_stun == 42
    assert c.current_body == 12
    assert c.current_end == 37
    assert c.knockback_resistance == 2
    assert c.is_npc is True

    # combat_stats() returns the same effective values
    s = c.combat_stats()
    assert s.ocv == 10
    assert s.rpd == 4
    assert s.md == 5
    assert s.max_stun == 50

    # state carries vitals
    assert c.state.current_stun == 42
    assert c.state.current_body == 12


def test_default_current_vitals_track_max():
    """When ``current_*`` aren't passed, default to max — same as legacy."""
    c = synthetic_combatant(id="t", name="t", max_stun=30, max_body=10, max_end=20)
    assert c.current_stun == 30
    assert c.current_body == 10
    assert c.current_end == 20


def test_attacks_and_defenses_are_explicit():
    """The legacy Combatant carried attacks/defenses as flat lists.
    Our synthetic preserves that even though base HeroCombatant
    derives them from hero.powers."""
    from kirby_combat.models import AttackPower, DefenseItem

    blast = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=20,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )
    armor = DefenseItem(name="Armor", rpd=4, red=4, is_resistant=True)

    c = synthetic_combatant(
        id="t", name="Test",
        attacks=[blast], defenses=[armor],
    )
    assert c.attacks == [blast]
    assert c.defenses == [armor]
