"""TDD tests for variable Multipower slot dice scaling (6E1 p405)."""
from __future__ import annotations

from kirby_combat.resolution.damage import scale_variable_slot_dice


def test_variable_slot_scales_dice_by_assigned_reserve():
    """Assigning 40 of 60 AP to a 12d slot → 8d (floor(12 * 40/60))."""
    assert scale_variable_slot_dice(base_dice=12, active_points=60, assigned_points=40) == 8


def test_full_assignment_is_unchanged():
    """Assigning exactly the slot's AP → unchanged base dice."""
    assert scale_variable_slot_dice(base_dice=12, active_points=60, assigned_points=60) == 12


def test_none_or_zero_active_is_safe():
    """Zero active_points (unknown/unset) → return base_dice unchanged (safe fallback)."""
    assert scale_variable_slot_dice(base_dice=10, active_points=0, assigned_points=0) == 10


def test_over_assignment_is_clamped_to_base():
    """Assigning more than active_points still returns base_dice (full assignment)."""
    assert scale_variable_slot_dice(base_dice=8, active_points=40, assigned_points=60) == 8


def test_zero_assigned_gives_zero_dice():
    """Assigning 0 points → 0 dice (slot not used)."""
    assert scale_variable_slot_dice(base_dice=12, active_points=60, assigned_points=0) == 0


def test_fractional_truncates_to_floor():
    """Partial assignment truncates to whole dice (floor)."""
    # 12 * 30/60 = 6.0 exactly → 6
    assert scale_variable_slot_dice(base_dice=12, active_points=60, assigned_points=30) == 6
    # 10 * 33/60 = 5.5 → floor → 5
    assert scale_variable_slot_dice(base_dice=10, active_points=60, assigned_points=33) == 5
