"""Move-By and Move-Through velocity attack math."""
import pytest

from kirby_combat.actions.move_by import MoveBy, MoveByOutcome
from kirby_combat.actions.move_through import MoveThrough, MoveThroughOutcome


# ---- Move-By ----

def test_move_by_dc_str_plus_velocity_over_10():
    # Per 6E2 p72: damage = (STR/2) + (vel/10)d6.
    # STR=50 → STR/2=25 → str_dc=5; velocity=20m → vel_dc=2; total 7.
    out = MoveBy.compute(attacker_str=50, velocity_mps=20.0)
    assert out.damage_dc == 7


def test_move_by_dc_floors_velocity_division():
    # STR=25 → STR/2=12 → str_dc=2; velocity=15m → vel_dc=1; total 3.
    out = MoveBy.compute(attacker_str=25, velocity_mps=15.0)
    assert out.damage_dc == 3


def test_move_by_dc_zero_velocity_uses_str_only():
    # STR=30 → STR/2=15 → str_dc=3.
    out = MoveBy.compute(attacker_str=30, velocity_mps=0.0)
    assert out.damage_dc == 3


def test_move_by_damage_per_6e2_p72():
    """Per 6E2 p72: damage = (STR/2) + (vel/10)d6 — STR halved BEFORE conversion."""
    # STR=60 (a typical mid-tier brick) → STR/2=30 → str_dc=6
    # vel=30m → vel_dc=3
    # Total: 9 DCs
    out = MoveBy.compute(attacker_str=60, velocity_mps=30.0)
    assert out.damage_dc == 9


def test_move_by_modifiers_minus_2_ocv_minus_2_dcv():
    out = MoveBy.compute(attacker_str=30, velocity_mps=20.0)
    assert out.ocv_modifier == -2
    assert out.dcv_modifier == -2


def test_move_by_records_phase_cost_half():
    out = MoveBy.compute(attacker_str=30, velocity_mps=20.0)
    assert out.phase_cost == "half"


def test_move_by_distance_past_target_is_half_remaining_movement():
    # When caller declares total movement of 30m and target is at 12m, the
    # attacker continues past the target. Engine reports remaining distance
    # the caller should resolve.
    out = MoveBy.compute(attacker_str=30, velocity_mps=20.0,
                          total_movement_m=30, distance_to_target_m=12)
    assert out.distance_past_target_m == 18.0  # 30 - 12


def test_move_by_attacker_takes_one_third_self_damage():
    """Per 6E2 p72: Move-By attacker takes 1/3 of damage done to target."""
    out = MoveBy.compute(attacker_str=30, velocity_mps=20.0)
    assert out.attacker_self_damage_fraction == pytest.approx(1.0 / 3.0)


# ---- Move-Through ----

def test_move_through_dc_str_plus_velocity_over_6():
    # STR=30 (STR_DC=6), velocity=18m → DC = 6 + 3 = 9
    out = MoveThrough.compute(attacker_str=30, velocity_mps=18.0)
    assert out.damage_dc == 9


def test_move_through_dc_floors_velocity_division():
    # STR=30, velocity=20m → 20/6 = 3.33 → floor 3 → DC = 6 + 3 = 9
    out = MoveThrough.compute(attacker_str=30, velocity_mps=20.0)
    assert out.damage_dc == 9


def test_move_through_attacker_takes_same_dc_self_damage():
    """Legacy field: kept for back-compat (replaced by attacker_self_damage_fraction)."""
    out = MoveThrough.compute(attacker_str=30, velocity_mps=18.0)
    assert out.attacker_self_damage_dc == out.damage_dc


def test_move_through_attacker_takes_half_self_damage_normally_full_when_no_kb():
    """Per 6E2 p72: Move-Through attacker takes 1/2 of damage done normally.

    If the target resisted Knockback (immovable wall, KB-resistance ≥ KB
    distance, or attacker opts in), the attacker takes the FULL damage instead.
    """
    # Default case (target took knockback)
    out_normal = MoveThrough.compute(attacker_str=30, velocity_mps=18.0)
    assert out_normal.attacker_self_damage_fraction == 0.5

    # No-KB case (target resisted) → attacker takes full
    out_no_kb = MoveThrough.compute(
        attacker_str=30, velocity_mps=18.0, target_resisted_kb=True,
    )
    assert out_no_kb.attacker_self_damage_fraction == 1.0


def test_move_through_ocv_penalty_scales_with_velocity():
    # velocity_m / 10 = OCV penalty (negative). 20m → -2 OCV.
    out = MoveThrough.compute(attacker_str=30, velocity_mps=20.0)
    assert out.ocv_modifier == -2


def test_move_through_zero_velocity_zero_ocv_penalty():
    out = MoveThrough.compute(attacker_str=30, velocity_mps=0.0)
    assert out.ocv_modifier == 0
    assert out.damage_dc == 6        # STR-only


def test_move_through_dcv_penalty_minus_3():
    out = MoveThrough.compute(attacker_str=30, velocity_mps=20.0)
    assert out.dcv_modifier == -3


def test_move_through_knockback_is_velocity_based_flag():
    out = MoveThrough.compute(attacker_str=30, velocity_mps=20.0)
    assert out.knockback_basis == "velocity"


def test_move_through_phase_cost_full():
    out = MoveThrough.compute(attacker_str=30, velocity_mps=20.0)
    assert out.phase_cost == "full"


# ---- Edge cases ----

def test_negative_str_clamped_to_zero_dc():
    """A combatant with STR 0 still has a valid (zero-damage) move-by."""
    out = MoveBy.compute(attacker_str=0, velocity_mps=20.0)
    assert out.damage_dc == 2          # 0 + 2 from velocity


def test_negative_velocity_treated_as_zero():
    out = MoveThrough.compute(attacker_str=30, velocity_mps=-5.0)
    assert out.ocv_modifier == 0
    assert out.damage_dc == 6           # STR-only
