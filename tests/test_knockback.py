"""Tests for knockback calculation (Task 7)."""
from __future__ import annotations

import pytest

from kirby_combat.models import DiceValues, KnockbackResult
from kirby_combat.template import CombatTemplate, RAW_SUPERHEROIC
from kirby_combat.resolution.knockback import compute_knockback


@pytest.fixture
def default_template() -> CombatTemplate:
    return RAW_SUPERHEROIC


@pytest.fixture
def dice_6() -> DiceValues:
    """Six knockback dice: [3, 2, 4, 1, 5, 2] → sum=17."""
    return DiceValues(knockback=[3, 2, 4, 1, 5, 2])


def test_basic_knockback(default_template: CombatTemplate, dice_6: DiceValues) -> None:
    """12 BODY, 0 resistance → effective=12, kb_dice=6, distance=17m, damage_dice=8."""
    result = compute_knockback(
        body_dealt=12,
        kb_resistance=0,
        knockback_multiplier=1.0,
        dice=dice_6,
        template=default_template,
    )
    assert not result.resisted
    assert result.dice == 6
    assert result.distance_m == 17.0
    assert result.damage_dice == 8   # int(17) // 2 = 8


def test_knockback_with_resistance(default_template: CombatTemplate, dice_6: DiceValues) -> None:
    """12 BODY, 10 resistance → effective=2, kb_dice=max(1,1)=1, uses first die (3)."""
    result = compute_knockback(
        body_dealt=12,
        kb_resistance=10,
        knockback_multiplier=1.0,
        dice=dice_6,
        template=default_template,
    )
    assert not result.resisted
    assert result.dice == 1
    assert result.distance_m == 3.0   # dice.knockback[0] = 3, × 1.0
    assert result.damage_dice == 1    # int(3) // 2 = 1


def test_knockback_fully_resisted(default_template: CombatTemplate, dice_6: DiceValues) -> None:
    """5 BODY, 20 resistance → effective=−15 ≤ 0 → resisted."""
    result = compute_knockback(
        body_dealt=5,
        kb_resistance=20,
        knockback_multiplier=1.0,
        dice=dice_6,
        template=default_template,
    )
    assert result.resisted
    assert result.distance_m == 0.0
    assert result.dice == 0


def test_knockback_disabled(dice_6: DiceValues) -> None:
    """Template with use_knockback=False → always resisted, distance=0."""
    no_kb_template = CombatTemplate(name="No KB", use_knockback=False)
    result = compute_knockback(
        body_dealt=30,
        kb_resistance=0,
        knockback_multiplier=1.0,
        dice=dice_6,
        template=no_kb_template,
    )
    assert result.resisted
    assert result.distance_m == 0.0
    assert result.dice == 0


def test_knockback_doubled_house_rule(default_template: CombatTemplate, dice_6: DiceValues) -> None:
    """multiplier=2.0, 12 BODY → 6 dice, sum=17 × 2.0 → 34m, damage_dice=17."""
    result = compute_knockback(
        body_dealt=12,
        kb_resistance=0,
        knockback_multiplier=2.0,
        dice=dice_6,
        template=default_template,
    )
    assert not result.resisted
    assert result.dice == 6
    assert result.distance_m == 34.0
    assert result.damage_dice == 17  # int(34) // 2 = 17
