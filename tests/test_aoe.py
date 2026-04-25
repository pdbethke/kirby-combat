"""Area of Effect targeting + Explosion advantage tests."""
import math
import pytest

from kirby_combat.actions.area_of_effect import AreaOfEffect, AoEOutcome


def test_aoe_radius_hits_combatants_within_circle():
    positions = {"alice": (5, 5), "bob": (10, 5), "carol": (50, 50)}
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(7, 5), radius_m=4,
        combatant_positions=positions,
    )
    # alice is 2m away, bob is 3m away → both hit. carol is far → not hit.
    assert set(out.affected_targets) == {"alice", "bob"}
    assert "carol" not in out.affected_targets


def test_aoe_radius_excludes_combatants_beyond_radius():
    positions = {"alice": (0, 0), "bob": (10, 0)}
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=5,
        combatant_positions=positions,
    )
    assert "alice" in out.affected_targets
    assert "bob" not in out.affected_targets       # 10m away, radius 5m


def test_aoe_radius_full_dc_for_all_targets_no_explosion():
    positions = {"alice": (0, 0), "bob": (3, 4)}     # bob 5m from origin
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=10,
        combatant_positions=positions,
    )
    assert out.per_target_dc["alice"] == 10
    assert out.per_target_dc["bob"] == 10


def test_aoe_radius_target_dcv_is_3():
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=5,
        combatant_positions={"alice": (0, 0)},
    )
    assert out.target_dcv_for_aoe == 3


def test_aoe_phase_cost_full():
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=5,
        combatant_positions={"alice": (0, 0)},
    )
    assert out.phase_cost == "full"


# ---- Explosion ----

def test_explosion_dc_falls_off_with_distance():
    # Explosion: -1 DC per 2m from epicenter
    positions = {"alice": (0, 0), "bob": (4, 0), "carol": (10, 0)}
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=15,
        combatant_positions=positions, explosion=True,
    )
    assert out.per_target_dc["alice"] == 10        # at epicenter
    assert out.per_target_dc["bob"] == 8           # 4m / 2 = -2 → 8
    assert out.per_target_dc["carol"] == 5         # 10m / 2 = -5 → 5


def test_explosion_dc_clamped_at_zero():
    positions = {"alice": (100, 0)}
    out = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=200,
        combatant_positions=positions, explosion=True,
    )
    assert out.per_target_dc["alice"] == 0


# ---- Cone ----

def test_cone_hits_combatants_in_arc():
    # Cone facing east (direction=0), 60° total (half_angle=π/6), length 10m
    # alice at (5, 0): directly ahead → hit
    # bob at (5, 1): slightly above → angle ~11°, within 30° → hit
    # carol at (5, 6): too far off-axis → angle ~50°, miss
    positions = {"alice": (5, 0), "bob": (5, 1), "carol": (5, 6)}
    out = AreaOfEffect.compute_cone(
        base_dc=8, origin=(0, 0), direction_rad=0,
        half_angle_rad=math.pi / 6, length_m=10,
        combatant_positions=positions,
    )
    assert "alice" in out.affected_targets
    assert "bob" in out.affected_targets
    assert "carol" not in out.affected_targets


def test_cone_excludes_combatants_beyond_length():
    positions = {"alice": (5, 0), "bob": (15, 0)}
    out = AreaOfEffect.compute_cone(
        base_dc=8, origin=(0, 0), direction_rad=0,
        half_angle_rad=math.pi / 6, length_m=10,
        combatant_positions=positions,
    )
    assert "alice" in out.affected_targets
    assert "bob" not in out.affected_targets


def test_cone_does_not_hit_combatant_behind_origin():
    positions = {"alice": (-5, 0)}
    out = AreaOfEffect.compute_cone(
        base_dc=8, origin=(0, 0), direction_rad=0,
        half_angle_rad=math.pi / 6, length_m=10,
        combatant_positions=positions,
    )
    assert "alice" not in out.affected_targets


# ---- Line ----

def test_line_hits_combatants_near_segment():
    # Line from (0,0) to (10, 0), width 2m → catches anyone within 1m perpendicular
    positions = {"alice": (5, 0.5), "bob": (5, 3), "carol": (5, 0)}
    out = AreaOfEffect.compute_line(
        base_dc=8, start=(0, 0), end=(10, 0), width_m=2,
        combatant_positions=positions,
    )
    assert "alice" in out.affected_targets    # 0.5m away (within 1m)
    assert "carol" in out.affected_targets    # on the line
    assert "bob" not in out.affected_targets  # 3m away (beyond 1m)


def test_line_excludes_combatants_beyond_endpoints():
    # Line (0,0)-(10,0). Bob at (15, 0) is 5m past the end; should not be hit.
    positions = {"alice": (5, 0), "bob": (15, 0)}
    out = AreaOfEffect.compute_line(
        base_dc=8, start=(0, 0), end=(10, 0), width_m=2,
        combatant_positions=positions,
    )
    assert "alice" in out.affected_targets
    assert "bob" not in out.affected_targets


# ---- Selective ----

def test_selective_filter_removes_excluded_targets():
    positions = {"alice": (0, 0), "bob": (3, 0), "carol": (5, 0)}
    full = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=10,
        combatant_positions=positions,
    )
    filtered = AreaOfEffect.selective_filter(full, excluded_ids={"alice"})
    assert "alice" not in filtered.affected_targets
    assert "alice" not in filtered.per_target_dc
    assert "bob" in filtered.affected_targets
    assert "carol" in filtered.affected_targets


def test_selective_filter_with_no_exclusions_returns_equivalent_outcome():
    positions = {"alice": (0, 0)}
    full = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(0, 0), radius_m=5,
        combatant_positions=positions,
    )
    filtered = AreaOfEffect.selective_filter(full, excluded_ids=set())
    assert set(filtered.affected_targets) == set(full.affected_targets)
    assert filtered.per_target_dc == full.per_target_dc
