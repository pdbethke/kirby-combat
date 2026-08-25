"""Tests for HERO System 6E to-hit resolution."""
from __future__ import annotations
import pytest
from kirby_combat.models import (
    AttackInput,
    AttackPower,
    CombatSkillLevel,
    DiceValues,
)
from kirby_combat.template import CombatTemplate, RAW_SUPERHEROIC, RAW_HEROIC
from kirby_combat.resolution.to_hit import resolve_to_hit
from fixtures.synthetic_hero import synthetic_combatant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_combatant(ocv: int = 6, dcv: int = 6, **kwargs) -> "HeroCombatant":
    defaults = dict(
        id="test",
        name="Tester",
        ocv=ocv,
        dcv=dcv,
        omcv=3,
        dmcv=3,
        spd=4,
        dex=13,
        ego=10,
        str_=10,
        con=13,
        pre=10,
        rec=4,
        pd=4,
        ed=4,
        rpd=0,
        red=0,
        md=0,
        power_defense=0,
        flash_defense=0,
        max_stun=30,
        max_body=10,
        max_end=30,
        current_stun=30,
        current_body=10,
        current_end=30,
    )
    defaults.update(kwargs)
    return synthetic_combatant(**defaults)


def make_power(range_m: float | None = None) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST",
        name="Energy Blast",
        damage_dice=6,
        half_die=False,
        plus_one=False,
        damage_type="normal",
        defense_type="ed",
        range_m=range_m,
        uses_str=False,
        str_min=0,
        armor_piercing=0,
        penetrating=0,
        increased_stun_mult=0,
    )


def make_attack(
    attacker: "HeroCombatant | None" = None,
    target: "HeroCombatant | None" = None,
    power: AttackPower | None = None,
    dice_to_hit: list[int] | None = None,
    distance_m: float | None = None,
    aim: str | None = None,
    ocv_modifier: int = 0,
    dcv_modifier: int = 0,
) -> AttackInput:
    return AttackInput(
        attacker=attacker or make_combatant(ocv=6),
        target=target or make_combatant(dcv=6),
        power=power or make_power(),
        distance_m=distance_m,
        aim=aim,
        dice=DiceValues(to_hit=dice_to_hit or []),
        ocv_modifier=ocv_modifier,
        dcv_modifier=dcv_modifier,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicResolution:
    def test_basic_hit(self):
        """OCV 8, DCV 6, roll [3,4,4]=11. Need 13 (8+11-6). Hit by 2."""
        attacker = make_combatant(ocv=8)
        target = make_combatant(dcv=6)
        attack = make_attack(attacker=attacker, target=target, dice_to_hit=[3, 4, 4])
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.hit is True
        assert result.roll == 11
        assert result.target_number == 13
        assert result.margin == 2

    def test_basic_miss(self):
        """OCV 6, DCV 8, roll [4,4,4]=12. Need 9 (6+11-8). Miss by 3."""
        attacker = make_combatant(ocv=6)
        target = make_combatant(dcv=8)
        attack = make_attack(attacker=attacker, target=target, dice_to_hit=[4, 4, 4])
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.hit is False
        assert result.roll == 12
        assert result.target_number == 9
        assert result.margin == -3

    def test_exact_roll_equals_target_number_is_hit(self):
        """Roll exactly equals target number — that's a hit in HERO."""
        attacker = make_combatant(ocv=6)
        target = make_combatant(dcv=6)
        # target number = 6 + 11 - 6 = 11; roll exactly 11
        attack = make_attack(attacker=attacker, target=target, dice_to_hit=[3, 4, 4])
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.hit is True
        assert result.margin == 0

    def test_default_roll_when_empty_dice(self):
        """Empty dice list defaults roll to 11."""
        attack = make_attack(dice_to_hit=[])
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.roll == 11


class TestRangePenalty:
    def test_range_penalty_applied(self):
        """20m range, OCV 8. Penalty should be -4. Effective OCV = 4."""
        attacker = make_combatant(ocv=8)
        power = make_power(range_m=100.0)  # ranged power
        attack = make_attack(attacker=attacker, power=power, distance_m=20.0)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.range_penalty == -4
        assert result.effective_ocv == 4  # 8 + (-4)

    def test_no_range_penalty_for_hth(self):
        """HTH attack (range_m=None) — no penalty even with distance."""
        attacker = make_combatant(ocv=8)
        power = make_power(range_m=None)  # hand-to-hand power
        attack = make_attack(attacker=attacker, power=power, distance_m=20.0)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.range_penalty == 0
        assert result.effective_ocv == 8

    def test_no_range_penalty_when_distance_none(self):
        """Ranged power but distance not provided — no penalty."""
        power = make_power(range_m=50.0)
        attack = make_attack(power=power, distance_m=None)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.range_penalty == 0

    def test_zero_distance_no_penalty(self):
        """Ranged power at 0m distance (point blank) — no penalty."""
        power = make_power(range_m=50.0)
        attack = make_attack(power=power, distance_m=0.0)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.range_penalty == 0


class TestHitLocation:
    def test_hit_location_aimed_head(self):
        """Aim at Head (-8 OCV), use_hit_locations=True."""
        attacker = make_combatant(ocv=10)
        target = make_combatant(dcv=6)
        attack = make_attack(attacker=attacker, target=target, aim="Head")
        result = resolve_to_hit(attack, RAW_HEROIC)  # RAW_HEROIC has use_hit_locations=True

        assert result.hit_location_penalty == -8
        assert result.effective_ocv == 2  # 10 + (-8)

    def test_hit_location_ignored_when_template_off(self):
        """Aim is set but template has use_hit_locations=False — penalty not applied."""
        attack = make_attack(attacker=make_combatant(ocv=10), aim="Head")
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.hit_location_penalty == 0
        assert result.effective_ocv == 10

    def test_no_aim_no_hit_location_penalty(self):
        """No aim specified — no hit location penalty even with use_hit_locations=True."""
        attack = make_attack(attacker=make_combatant(ocv=10), aim=None)
        result = resolve_to_hit(attack, RAW_HEROIC)

        assert result.hit_location_penalty == 0

    def test_bodyshot_minus_1_penalty_per_6e1_p465(self):
        """Per 6E1 p465 §Combat Modifiers: Body Shot is -1 OCV (not 0)."""
        attack = make_attack(attacker=make_combatant(ocv=8), aim="BodyShot")
        result = resolve_to_hit(attack, RAW_HEROIC)

        assert result.hit_location_penalty == -1
        assert result.effective_ocv == 7


class TestOcvModifier:
    def test_ocv_modifier_applied(self):
        """+2 OCV modifier from maneuver raises effective OCV."""
        attacker = make_combatant(ocv=6)
        attack = make_attack(attacker=attacker, ocv_modifier=2)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.effective_ocv == 8

    def test_negative_ocv_modifier(self):
        """-3 OCV modifier (e.g. haymaker) lowers effective OCV."""
        attacker = make_combatant(ocv=8)
        attack = make_attack(attacker=attacker, ocv_modifier=-3)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.effective_ocv == 5

    def test_dcv_modifier_applied(self):
        """+2 DCV modifier (e.g. target is partially behind cover) raises effective DCV."""
        target = make_combatant(dcv=6)
        attack = make_attack(target=target, dcv_modifier=2)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.effective_dcv == 8


class TestCombatSkillLevels:
    def test_ocv_csl_bonus_applied(self):
        """CSL allocated to OCV adds to effective OCV."""
        attacker = make_combatant(ocv=6, csls=[CombatSkillLevel(levels=2, applies_to="ocv")])
        attack = make_attack(attacker=attacker)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.csl_bonus == 2
        assert result.effective_ocv == 8

    def test_any_csl_bonus_applied(self):
        """CSL allocated to 'any' adds to effective OCV."""
        attacker = make_combatant(ocv=6, csls=[CombatSkillLevel(levels=3, applies_to="any")])
        attack = make_attack(attacker=attacker)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.csl_bonus == 3
        assert result.effective_ocv == 9

    def test_dc_csl_not_applied_to_ocv(self):
        """CSL allocated to 'dc' does NOT contribute to OCV."""
        attacker = make_combatant(ocv=6, csls=[CombatSkillLevel(levels=4, applies_to="dc")])
        attack = make_attack(attacker=attacker)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.csl_bonus == 0
        assert result.effective_ocv == 6

    def test_dcv_csl_not_applied_to_ocv(self):
        """CSL allocated to 'dcv' does NOT contribute to OCV."""
        attacker = make_combatant(ocv=6, csls=[CombatSkillLevel(levels=2, applies_to="dcv")])
        attack = make_attack(attacker=attacker)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.csl_bonus == 0

    def test_mixed_csls(self):
        """Mix of OCV and DC CSLs — only ocv/any count."""
        attacker = make_combatant(
            ocv=6,
            csls=[
                CombatSkillLevel(levels=2, applies_to="ocv"),
                CombatSkillLevel(levels=3, applies_to="dc"),
                CombatSkillLevel(levels=1, applies_to="any"),
            ],
        )
        attack = make_attack(attacker=attacker)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.csl_bonus == 3  # 2 (ocv) + 1 (any)
        assert result.effective_ocv == 9


class TestAuditTrail:
    def test_audit_is_list_of_strings(self):
        attack = make_attack()
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        assert isinstance(result.audit, list)
        assert all(isinstance(s, str) for s in result.audit)

    def test_audit_non_empty(self):
        attack = make_attack(
            attacker=make_combatant(ocv=8),
            target=make_combatant(dcv=6),
            dice_to_hit=[3, 4, 4],
        )
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        assert len(result.audit) >= 1

    def test_audit_mentions_range_penalty(self):
        power = make_power(range_m=100.0)
        attack = make_attack(power=power, distance_m=20.0)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        audit_text = " ".join(result.audit).lower()
        assert "range" in audit_text

    def test_audit_mentions_hit_location_penalty(self):
        attack = make_attack(attacker=make_combatant(ocv=10), aim="Head")
        result = resolve_to_hit(attack, RAW_HEROIC)
        audit_text = " ".join(result.audit).lower()
        assert "head" in audit_text or "location" in audit_text


class TestTargetNumber:
    def test_target_number_formula(self):
        """target_number = effective_ocv + 11 - effective_dcv"""
        attacker = make_combatant(ocv=7)
        target = make_combatant(dcv=5)
        attack = make_attack(attacker=attacker, target=target)
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)

        assert result.target_number == 7 + 11 - 5  # 13

    def test_result_fields_populated(self):
        """Sanity: all ToHitResult fields are populated after resolution."""
        attack = make_attack()
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        assert result.roll is not None
        assert result.target_number is not None
        assert isinstance(result.hit, bool)
        assert result.margin == result.target_number - result.roll


class TestCanonFloatStats:
    """Combatants built from canon HDC/build-doc imports carry
    whole-valued float stats (the cost engine's characteristic_value()
    returns float, e.g. OCV=8.0). resolve_to_hit must not crash on the
    {margin:+d} audit format and must return an int margin."""

    class _FloatStatAttacker:
        """Duck-typed attacker/target with engine-float stats, as seen
        before hero_view's int boundary (and from any external caller
        that feeds floats directly)."""

        def __init__(self, ocv: float, dcv: float) -> None:
            self.ocv = ocv
            self.dcv = dcv
            self.csls: list = []

    def test_float_ocv_dcv_resolve_and_int_margin(self):
        attacker = self._FloatStatAttacker(ocv=8.0, dcv=6.0)
        target = self._FloatStatAttacker(ocv=6.0, dcv=5.0)
        attack = make_attack(
            attacker=attacker, target=target, dice_to_hit=[3, 4, 4],
        )
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        # TN = 8 + 11 - 5 = 14, roll 11 → hit by 3
        assert result.hit is True
        assert result.margin == 3
        assert isinstance(result.margin, int)
        assert "(margin: +3)" in result.audit[-1]

    def test_float_stats_miss_margin_is_negative_int(self):
        attacker = self._FloatStatAttacker(ocv=4.0, dcv=4.0)
        target = self._FloatStatAttacker(ocv=4.0, dcv=9.0)
        attack = make_attack(
            attacker=attacker, target=target, dice_to_hit=[4, 4, 4],
        )
        result = resolve_to_hit(attack, RAW_SUPERHEROIC)
        # TN = 4 + 11 - 9 = 6, roll 12 → miss by 6
        assert result.hit is False
        assert result.margin == -6
        assert isinstance(result.margin, int)
        assert "(margin: -6)" in result.audit[-1]
