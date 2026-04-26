"""Tests for kirby_combat.resolution.damage.compute_damage."""
import pytest

from kirby_combat.models import AttackPower, DiceValues
from kirby_combat.template import CombatTemplate
from kirby_combat.resolution.damage import compute_damage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_power(
    damage_type: str = "normal",
    half_die: bool = False,
    plus_one: bool = False,
    increased_stun_mult: int = 0,
) -> AttackPower:
    return AttackPower(
        xmlid="BLAST",
        name="Test Blast",
        damage_dice=6,
        half_die=half_die,
        plus_one=plus_one,
        damage_type=damage_type,
        defense_type="pd",
        range_m=50.0,
        uses_str=False,
        str_min=0,
        armor_piercing=0,
        penetrating=0,
        increased_stun_mult=increased_stun_mult,
    )


def make_template(
    killing_stun_mult_base: int = 1,
    killing_stun_mult_fixed: int | None = None,
) -> CombatTemplate:
    return CombatTemplate(
        name="Test Template",
        killing_stun_mult_base=killing_stun_mult_base,
        killing_stun_mult_fixed=killing_stun_mult_fixed,
    )


def make_dice(damage: list[int], stun_multiplier: list[int] | None = None) -> DiceValues:
    return DiceValues(
        damage=damage,
        stun_multiplier=stun_multiplier or [],
    )


# ---------------------------------------------------------------------------
# Normal damage tests
# ---------------------------------------------------------------------------

class TestNormalDamage:
    def test_normal_damage_10d6(self):
        """dice [5,1,3,6,2,4,6,3,1,2] → STUN=33, BODY=10"""
        power = make_power(damage_type="normal")
        dice = make_dice([5, 1, 3, 6, 2, 4, 6, 3, 1, 2])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 33
        assert result.body == 10
        assert result.damage_type == "normal"

    def test_normal_damage_body_counting(self):
        """dice [1,1,1,6,6,6] → STUN=21, BODY=6 (1s→0, 6s→2 each = 0+0+0+2+2+2=6)"""
        power = make_power(damage_type="normal")
        dice = make_dice([1, 1, 1, 6, 6, 6])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 21
        assert result.body == 6

    def test_normal_damage_body_middle_values(self):
        """Values 2-5 each count as 1 BODY."""
        power = make_power(damage_type="normal")
        # 2=1 BODY, 3=1 BODY, 4=1 BODY, 5=1 BODY → 4 BODY, STUN=14
        dice = make_dice([2, 3, 4, 5])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 14
        assert result.body == 4


# ---------------------------------------------------------------------------
# Killing damage tests
# ---------------------------------------------------------------------------

class TestKillingDamage:
    def test_killing_damage_3d6(self):
        """dice [4,3,5], stun_mult [4] → BODY=12, ½d6 mult=2, STUN=24

        Per 6E2 p100: STUN multiplier is ½d6 (range 1-3). Raw d6=4 → half_die=2.
        """
        power = make_power(damage_type="killing")
        dice = make_dice([4, 3, 5], stun_multiplier=[4])
        template = make_template(killing_stun_mult_base=1)

        result = compute_damage(power, dice, template)

        assert result.body == 12
        assert result.stun_multiplier == 2  # half_die((4+1)//2)=2; base 1 + (2-1) = 2
        assert result.stun == 24
        assert result.damage_type == "killing"

    def test_killing_damage_fixed_stun_mult(self):
        """fixed mult=3, dice [3,4,2] → BODY=9, STUN=27"""
        power = make_power(damage_type="killing")
        dice = make_dice([3, 4, 2])
        template = make_template(killing_stun_mult_fixed=3)

        result = compute_damage(power, dice, template)

        assert result.body == 9
        assert result.stun_multiplier == 3
        assert result.stun == 27

    def test_killing_damage_increased_stun_mult(self):
        """increased_stun_mult=1 adds to the computed multiplier (per 6E1 p244).

        Raw d6=2 → half_die = (2+1)//2 = 1. base 1 + (1-1) + 1 increased = 2.
        """
        power = make_power(damage_type="killing", increased_stun_mult=1)
        dice = make_dice([3, 3, 3], stun_multiplier=[2])
        template = make_template(killing_stun_mult_base=1)

        result = compute_damage(power, dice, template)

        assert result.body == 9
        assert result.stun_multiplier == 2   # half_die=1; base 1 + (1-1) + 1 increased = 2
        assert result.stun == 18

    def test_killing_damage_minimum_mult_is_1(self):
        """Stun multiplier cannot go below 1.

        Raw d6=1 → half_die=1; base 1 + (1-1) = 1. Floors at 1.
        """
        power = make_power(damage_type="killing")
        dice = make_dice([3], stun_multiplier=[1])
        template = make_template(killing_stun_mult_base=1)

        result = compute_damage(power, dice, template)

        assert result.stun_multiplier >= 1

    def test_killing_stun_mult_is_half_die_round_up_per_6e2_p100(self):
        """Per 6E2 p100: STUN multiplier is ½d6, range 1-3.

        Raw d6 → half_die mapping: 1→1, 2→1, 3→2, 4→2, 5→3, 6→3.
        With base=1, multiplier = base + (half_die - 1) → 1, 1, 2, 2, 3, 3.
        """
        power = make_power(damage_type="killing")
        template = make_template(killing_stun_mult_base=1)

        expected = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
        for raw_d6, expected_mult in expected.items():
            dice = make_dice([3], stun_multiplier=[raw_d6])
            result = compute_damage(power, dice, template)
            assert result.stun_multiplier == expected_mult, (
                f"raw d6={raw_d6} should map to ½d6={expected_mult}, "
                f"got {result.stun_multiplier}"
            )


# ---------------------------------------------------------------------------
# Half-die and plus-one tests
# ---------------------------------------------------------------------------

class TestHalfDieAndPlusOne:
    def test_half_die(self):
        """2d6+½d6 normal, dice [4,3,5] → STUN=9 (4+3+2), BODY=3 (1+1+1)

        First two values are the full d6s, third is the half-die value.
        Half-die STUN = 5//2 = 2. Half-die BODY: 5>=5 → 1.
        """
        power = make_power(damage_type="normal", half_die=True)
        dice = make_dice([4, 3, 5])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 9   # 4 + 3 + (5//2=2) = 9
        assert result.body == 3   # 1 + 1 + 1(5>=5) = 3

    def test_half_die_low_value(self):
        """Half-die value < 5 → 0 BODY from that half die."""
        power = make_power(damage_type="normal", half_die=True)
        # Full dice: [3, 2], half-die value: 3
        dice = make_dice([3, 2, 3])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 6   # 3 + 2 + (3//2=1) = 6
        assert result.body == 2   # 1 + 1 + 0(3<5) = 2

    def test_plus_one(self):
        """2d6+1 normal, dice [4,3] → STUN=8 (4+3+1), BODY=2"""
        power = make_power(damage_type="normal", plus_one=True)
        dice = make_dice([4, 3])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert result.stun == 8   # 4 + 3 + 1 = 8
        assert result.body == 2   # 1 + 1 = 2

    def test_killing_half_die(self):
        """Killing damage with half_die: BODY uses same half-die logic.

        Raw STUN-mult d6=2 → ½d6 = 1; multiplier = base 1 + (1-1) = 1.
        """
        power = make_power(damage_type="killing", half_die=True)
        # Full dice: [3, 4], half-die: 5 → BODY = 3+4+(5//2=2) = 9
        dice = make_dice([3, 4, 5], stun_multiplier=[2])
        template = make_template(killing_stun_mult_base=1)

        result = compute_damage(power, dice, template)

        assert result.body == 9   # 3 + 4 + 2 = 9
        assert result.stun == 9   # 9 × 1 = 9

    def test_killing_plus_one(self):
        """Killing damage with plus_one: +1 to BODY.

        Raw STUN-mult d6=3 → ½d6 = 2; multiplier = base 1 + (2-1) = 2.
        """
        power = make_power(damage_type="killing", plus_one=True)
        dice = make_dice([3, 4], stun_multiplier=[3])
        template = make_template(killing_stun_mult_base=1)

        result = compute_damage(power, dice, template)

        assert result.body == 8   # 3 + 4 + 1 = 8
        assert result.stun == 16  # 8 × 2 = 16


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_audit_is_populated(self):
        """DamageResult.audit should have entries documenting the calculation."""
        power = make_power(damage_type="normal")
        dice = make_dice([3, 4, 5])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert len(result.audit) > 0
        # At least one entry should mention STUN
        assert any("STUN" in entry for entry in result.audit)

    def test_killing_audit_mentions_multiplier(self):
        """Killing audit trail should document the STUN multiplier."""
        power = make_power(damage_type="killing")
        dice = make_dice([3, 4, 5], stun_multiplier=[3])
        template = make_template()

        result = compute_damage(power, dice, template)

        assert any("mult" in entry.lower() or "multiplier" in entry.lower()
                   for entry in result.audit)
