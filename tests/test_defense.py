"""Tests for defense aggregation — TDD first pass."""
from __future__ import annotations

import pytest

from kirby_combat.models import AttackPower, DefenseItem
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.resolution.defense import compute_defense


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_power(defense_type: str = "pd", armor_piercing: int = 0) -> AttackPower:
    return AttackPower(
        xmlid="BLAST",
        name="Test Blast",
        damage_dice=6,
        half_die=False,
        plus_one=False,
        damage_type="normal",
        defense_type=defense_type,
        range_m=50.0,
        uses_str=False,
        str_min=0,
        armor_piercing=armor_piercing,
        penetrating=0,
        increased_stun_mult=0,
    )


def _make_combatant(**overrides) -> "HeroCombatant":
    defaults = dict(
        id="c1",
        name="Test Char",
        ocv=5, dcv=5, omcv=3, dmcv=3, spd=4, dex=13,
        ego=10, str_=20, con=15, pre=10, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0,
        max_stun=30, max_body=10, max_end=30,
        current_stun=30, current_body=10, current_end=30,
        knockback_resistance=0,
    )
    defaults.update(overrides)
    return synthetic_combatant(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBaseDefenseOnly:
    def test_base_pd_only(self):
        """PD=10, no resistant → total=10, resistant=0."""
        target = _make_combatant(pd=10)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.total_defense == 10
        assert profile.resistant_defense == 0
        assert profile.non_resistant_defense == 10

    def test_resistant_pd(self):
        """PD=10, rPD=5 → total=10, resistant=5."""
        target = _make_combatant(pd=10, rpd=5)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.total_defense == 10
        assert profile.resistant_defense == 5

    def test_ed_vs_energy(self):
        """ED=15, rED=10 → total=15, resistant=10."""
        target = _make_combatant(ed=15, red=10)
        power = _make_power(defense_type="ed")
        profile = compute_defense(target, power)
        assert profile.total_defense == 15
        assert profile.resistant_defense == 10

    def test_wrong_defense_type_gives_zero(self):
        """PD attack vs a target with only ED does not apply ED."""
        target = _make_combatant(ed=20, red=10)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.total_defense == 0
        assert profile.resistant_defense == 0


class TestDefenseItems:
    def test_defense_items_stack(self):
        """PD=10, rPD=5 + ForceField(pd=5,rpd=5) + Armor(pd=3,rpd=3) → total=18, resistant=13."""
        target = _make_combatant(pd=10, rpd=5, defenses=[
            DefenseItem(name="Force Field", pd=5, rpd=5),
            DefenseItem(name="Armor", pd=3, rpd=3),
        ])
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.total_defense == 18
        assert profile.resistant_defense == 13

    def test_items_with_wrong_type_do_not_stack(self):
        """ED items do not add to PD totals."""
        target = _make_combatant(pd=5, defenses=[
            DefenseItem(name="Energy Armor", ed=10, red=10),
        ])
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.total_defense == 5
        assert profile.resistant_defense == 0


class TestArmorPiercing:
    def test_armor_piercing_halves_defense(self):
        """PD=20, AP attack → total=10 (integer division)."""
        target = _make_combatant(pd=20)
        power = _make_power(defense_type="pd", armor_piercing=1)
        profile = compute_defense(target, power)
        assert profile.total_defense == 10

    def test_armor_piercing_halves_resistant(self):
        """rPD=5, AP attack → resistant=2 (integer division)."""
        target = _make_combatant(pd=10, rpd=5)
        power = _make_power(defense_type="pd", armor_piercing=1)
        profile = compute_defense(target, power)
        assert profile.resistant_defense == 2

    def test_armor_piercing_odd_total(self):
        """PD=21, AP attack → total=10 (floor division)."""
        target = _make_combatant(pd=21)
        power = _make_power(defense_type="pd", armor_piercing=1)
        profile = compute_defense(target, power)
        assert profile.total_defense == 10


class TestKnockbackResistance:
    def test_knockback_resistance_target_only(self):
        """Target KB resist 10 with no items → total 10."""
        target = _make_combatant(knockback_resistance=10)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.knockback_resistance == 10

    def test_knockback_resistance_stacks_with_items(self):
        """Target KB resist 10 + item KB resist 5 → total 15."""
        target = _make_combatant(knockback_resistance=10, defenses=[
            DefenseItem(name="KB Resist Boots", knockback_resistance=5),
        ])
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.knockback_resistance == 15


class TestAggregateExtras:
    def test_damage_reduction_aggregated(self):
        """damage_reduction_pct sums across items."""
        target = _make_combatant(defenses=[
            DefenseItem(name="DR Field", damage_reduction_pct=25),
        ])
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.damage_reduction_pct == 25

    def test_damage_negation_aggregated(self):
        """damage_negation sums across items."""
        target = _make_combatant(defenses=[
            DefenseItem(name="Negation", damage_negation=3),
        ])
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert profile.damage_negation == 3


class TestAuditTrail:
    def test_audit_is_populated(self):
        """Audit list must contain at least one entry."""
        target = _make_combatant(pd=10, rpd=5)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert len(profile.audit) > 0

    def test_defense_tags_populated(self):
        """defense_tags list must contain at least one tag."""
        target = _make_combatant(pd=10)
        power = _make_power(defense_type="pd")
        profile = compute_defense(target, power)
        assert len(profile.defense_tags) > 0
