"""Adjustment powers — Aid, Drain, Transfer, Suppress, Absorption."""
import pytest

from kirby_combat.resolution.adjustments import (
    compute_aid,
    compute_drain,
    compute_transfer,
    compute_suppress,
    compute_absorption,
    AdjustmentOutcome,
)


def test_aid_adds_active_points_divided_by_cost_to_stat():
    # Aid 3d6 rolls 13 BODY → 13 active points for a 1-char-point stat = +13 STR
    out = compute_aid(
        active_points_rolled=13,
        points_per_level=1,         # STR costs 1 CP / point in 6E
        target_max_boost_cp=40,
    )
    assert out.delta == 13
    assert out.fade_rate_per_turn == 5   # default 5 per turn


def test_aid_clamped_by_max_boost():
    out = compute_aid(active_points_rolled=60, points_per_level=1, target_max_boost_cp=40)
    assert out.delta == 40


def test_drain_removes_points_and_fades_back():
    out = compute_drain(
        active_points_rolled=20,
        points_per_level=1,
        target_current_value=30,
    )
    assert out.delta == -20
    # Delta is negative; fade returns the stat over time
    assert out.fade_rate_per_turn == 5


def test_drain_cannot_reduce_stat_below_zero():
    out = compute_drain(active_points_rolled=50, points_per_level=1, target_current_value=10)
    assert out.delta == -10


def test_transfer_couples_drain_on_target_with_aid_on_attacker():
    # Transfer 2d6 rolls 8 BODY → 8 active points transferred
    from_delta, to_delta = compute_transfer(
        active_points_rolled=8, points_per_level=1,
        source_current_value=20, target_max_boost_cp=15,
    )
    assert from_delta == -8        # drained from source
    assert to_delta == 8           # aided to attacker


def test_suppress_sets_stat_to_value_temporarily_not_delta():
    # Suppress is an ongoing reduction — the stat is at (current - active) while
    # attacker pays END. Not tested here via fade; no AdjustmentFaded event.
    out = compute_suppress(active_points_rolled=15, points_per_level=1,
                           target_current_value=25)
    assert out.delta == -15
    assert out.fade_rate_per_turn == 0    # does not fade while attacker sustains
    assert out.is_sustained is True


def test_absorption_converts_incoming_damage_to_stat_increase():
    # Absorption: up to its rolled active-point cap, damage taken is converted
    # to an Aid-like boost. Fade is per-turn per 6E.
    out = compute_absorption(
        incoming_damage=12,
        absorption_max_cp=20,
        points_per_level=1,
        target_max_boost_cp=20,
    )
    assert out.delta == 12         # all 12 absorbed
    assert out.fade_rate_per_turn == 5


def test_absorption_capped_at_power_max():
    out = compute_absorption(
        incoming_damage=30,
        absorption_max_cp=20,
        points_per_level=1,
        target_max_boost_cp=20,
    )
    assert out.delta == 20          # capped
