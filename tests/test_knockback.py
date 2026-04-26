"""Tests for knockback calculation per 6E2 p116 and p118."""
from __future__ import annotations

import pytest

from kirby_combat.models import KnockbackResult
from kirby_combat.template import CombatTemplate, RAW_SUPERHEROIC
from kirby_combat.resolution.knockback import (
    compute_knockback,
    compute_impact_damage_dice,
    ImpactTarget,
)


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


# ---------------------------------------------------------------------------
# Impact damage by surface (Fix 3) — 6E2 p118
# ---------------------------------------------------------------------------


def test_knockback_ground_impact_quarter_meters(default_template: CombatTemplate) -> None:
    """Per 6E2 p118: open-ground impact = ¼ × meters in d6.

    BODY=15, KB-roll=[3,2]=5 → delta=10 → 20m. Ground impact: 20//4 = 5 dice.
    """
    result = compute_knockback(
        body=15,
        knockback_dice=[3, 2],
        kb_resistance_m=0,
        template=default_template,
        impact_target=None,
    )
    assert not result.resisted
    assert result.distance_m == 20.0
    assert result.damage_dice == 5
    assert result.target_passed_through is False


def test_knockback_object_breakable_half_meters(default_template: CombatTemplate) -> None:
    """Per 6E2 p118: breakable object impact = ½ × meters in d6 if KB ≤ 2*(PD+BODY).

    BODY=15, KB-roll=[3,2]=5 → delta=10 → 20m. half_meters=10.
    Object: PD=4, BODY=8. threshold = 2*12 = 24. 10 ≤ 24 → breakable.
    Damage = 10 dice; target passes through.
    """
    target = ImpactTarget(pd=4, body=8, breakable=True)
    result = compute_knockback(
        body=15,
        knockback_dice=[3, 2],
        kb_resistance_m=0,
        template=default_template,
        impact_target=target,
    )
    assert not result.resisted
    assert result.damage_dice == 10
    assert result.target_passed_through is True


def test_knockback_object_immovable_pd_plus_body_dice(default_template: CombatTemplate) -> None:
    """Per 6E2 p118: immovable object impact = PD + BODY dice; target stops.

    Object PD=10, BODY=20 (granite wall). breakable=False → immovable.
    Damage = 10 + 20 = 30 dice regardless of distance.
    """
    target = ImpactTarget(pd=10, body=20, breakable=False)
    result = compute_knockback(
        body=15,
        knockback_dice=[3, 2],
        kb_resistance_m=0,
        template=default_template,
        impact_target=target,
    )
    assert not result.resisted
    assert result.damage_dice == 30   # PD + BODY
    assert result.target_passed_through is False


def test_knockback_breakable_overwhelmed_treated_as_immovable(default_template: CombatTemplate) -> None:
    """If half_meters > 2*(PD+BODY), the breakable object resists fully (RAW: too much KB to break)."""
    # BODY=30, KB-roll=[1,1]=2 → delta=28 → 56m. half_meters=28.
    # Object: PD=2, BODY=2. threshold = 2*4 = 8. 28 > 8 → object resists.
    target = ImpactTarget(pd=2, body=2, breakable=True)
    result = compute_knockback(
        body=30,
        knockback_dice=[1, 1],
        kb_resistance_m=0,
        template=default_template,
        impact_target=target,
    )
    assert result.damage_dice == 4   # PD + BODY
    assert result.target_passed_through is False


# ---------------------------------------------------------------------------
# compute_impact_damage_dice helper
# ---------------------------------------------------------------------------


def test_compute_impact_damage_dice_ground():
    """Ground impact: ¼ × meters."""
    assert compute_impact_damage_dice(20.0, None) == (5, False)
    assert compute_impact_damage_dice(0.0, None) == (0, False)


def test_compute_impact_damage_dice_breakable_within_threshold():
    """Breakable object: ½ × meters if half_meters ≤ 2*(PD+BODY)."""
    target = ImpactTarget(pd=4, body=8, breakable=True)   # threshold = 24
    # 20m → half=10 ≤ 24 → breakable.
    assert compute_impact_damage_dice(20.0, target) == (10, True)


def test_compute_impact_damage_dice_immovable():
    """Immovable: PD + BODY dice, no pass-through."""
    target = ImpactTarget(pd=10, body=20, breakable=False)
    assert compute_impact_damage_dice(50.0, target) == (30, False)
