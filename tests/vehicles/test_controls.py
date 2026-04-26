"""Driving rolls and vehicle maneuvers."""
import pytest

from kirby_combat.vehicles.controls import (
    driving_roll, swerve_to_avoid, Maneuver,
)


def test_driving_roll_base_is_combat_driving_or_transport_familiarity():
    # Skill 11-, no modifiers, roll 11 -> success
    r = driving_roll(base_skill=11, dice=[4, 4, 3], maneuver=Maneuver.STRAIGHT)
    assert r.target_number == 11
    assert r.success is True


def test_bumpy_terrain_adds_negative_modifier_to_driving_roll():
    r = driving_roll(base_skill=11, dice=[4, 4, 3], bumpy_terrain=True)
    assert r.target_number == 9
    assert r.terrain_modifier == -2


def test_failed_driving_roll_causes_loss_of_control():
    r = driving_roll(base_skill=11, dice=[5, 5, 5])     # 15 vs 11
    assert r.success is False
    assert r.loss_of_control is True


def test_swerve_maneuver_allows_abort_to_avoid_collision():
    r = driving_roll(base_skill=11, dice=[3, 3, 3], maneuver=Maneuver.SWERVE)
    s = swerve_to_avoid(r)
    assert s.succeeded is True
    assert s.avoided_collision is True


def test_sharp_turn_at_high_velocity_reduces_success():
    # Sharp turn (-2), velocity 60 (-2) -> base 11 -> TN 7
    r = driving_roll(base_skill=11, dice=[3, 3, 3], maneuver=Maneuver.SHARP_TURN,
                     velocity_m_per_segment=60.0)
    assert r.target_number == 7
    assert r.success is False  # 9 > 7
