"""Tests for knockback calculation per 6E2 p116."""
from __future__ import annotations

import pytest

from kirby_combat.models import KnockbackResult
from kirby_combat.template import CombatTemplate, RAW_SUPERHEROIC
from kirby_combat.resolution.knockback import compute_knockback


@pytest.fixture
def default_template() -> CombatTemplate:
    return RAW_SUPERHEROIC


def test_basic_knockback_2d6_subtracted_from_body(default_template: CombatTemplate) -> None:
    """Per 6E2 p116: attacker rolls 2d6, sum subtracted from BODY, result × 2m.

    BODY=12, KB-roll=[3,2]=5 → delta=7, distance=14m. Default ground impact: 14//4=3 dice.
    """
    result = compute_knockback(
        body=12,
        knockback_dice=[3, 2],
        kb_resistance_m=0,
        template=default_template,
    )
    assert not result.resisted
    assert result.dice == 2
    assert result.distance_m == 14.0
    assert result.damage_dice == 3   # int(14)//4 = 3 (ground impact, ¼ × meters)


def test_knockback_resistance_subtracted_from_final_meters(default_template: CombatTemplate) -> None:
    """Per 6E2 p116: KB Resistance is meters subtracted from FINAL distance, not BODY.

    BODY=12, KB-roll=[3,2]=5 → 7×2 = 14m before resistance.
    KB resistance 6m → 14-6 = 8m.
    """
    result = compute_knockback(
        body=12,
        knockback_dice=[3, 2],
        kb_resistance_m=6,
        template=default_template,
    )
    assert not result.resisted
    assert result.distance_m == 8.0
    assert result.damage_dice == 2   # int(8)//4 = 2


def test_knockback_resistance_can_zero_out_distance(default_template: CombatTemplate) -> None:
    """KB resistance ≥ pre-resistance distance → 0m, resisted."""
    result = compute_knockback(
        body=10,
        knockback_dice=[3, 2],   # delta = 5; meters = 10
        kb_resistance_m=20,       # > 10
        template=default_template,
    )
    assert result.resisted
    assert result.distance_m == 0.0


def test_knockback_kb_roll_meets_or_exceeds_body(default_template: CombatTemplate) -> None:
    """KB-roll ≥ BODY → no knockback (delta floors at 0)."""
    result = compute_knockback(
        body=4,
        knockback_dice=[3, 2],   # 5 >= 4 → delta 0 → 0m
        kb_resistance_m=0,
        template=default_template,
    )
    assert result.resisted
    assert result.distance_m == 0.0


def test_knockback_modifier_dice_killing_attack(default_template: CombatTemplate) -> None:
    """Per 6E2 p117: Killing Attacks add +1d6 to the KB-roll (more dice = LESS distance).

    BODY=15, KB-roll = [3,2,4] (3 dice = 2d6 base + 1d6 KA modifier) → 9; delta=6 → 12m.
    """
    result = compute_knockback(
        body=15,
        knockback_dice=[3, 2, 4],
        kb_resistance_m=0,
        template=default_template,
    )
    assert not result.resisted
    assert result.dice == 3
    assert result.distance_m == 12.0


def test_knockback_disabled_by_template() -> None:
    """Template with use_knockback=False → always resisted, distance=0."""
    no_kb_template = CombatTemplate(name="No KB", use_knockback=False)
    result = compute_knockback(
        body=30,
        knockback_dice=[1, 1],
        kb_resistance_m=0,
        template=no_kb_template,
    )
    assert result.resisted
    assert result.distance_m == 0.0
    assert result.dice == 0


def test_knockback_doubled_house_rule(default_template: CombatTemplate) -> None:
    """multiplier=2.0, BODY=12, KB-roll=[3,2]=5 → delta=7 → 7×2×2.0 = 28m."""
    result = compute_knockback(
        body=12,
        knockback_dice=[3, 2],
        kb_resistance_m=0,
        knockback_multiplier=2.0,
        template=default_template,
    )
    assert not result.resisted
    assert result.distance_m == 28.0
    # int(28)//4 = 7 dice (ground default)
    assert result.damage_dice == 7
