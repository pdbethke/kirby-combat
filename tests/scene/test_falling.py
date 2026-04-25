"""Falling — support check + damage + landing."""
import pytest

from kirby_combat.scene import Scene, SceneBounds, Surface, Position, AmbientConditions
from kirby_combat.scene.falling import (
    is_supported_at,
    compute_falling_damage,
    resolve_fall,
    FallingResult,
)


def _scene_with_rooftop() -> Scene:
    return Scene(
        id="s1", name="Building",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
            Surface(id="roof", name="Roof",
                    polygon_xy=[(5, 5), (15, 5), (15, 15), (5, 15)],
                    elevation_m=12.0, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
        ],
        walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def test_supported_on_rooftop():
    s = _scene_with_rooftop()
    assert is_supported_at(Position(10, 10, 12.0), s) is True


def test_not_supported_above_rooftop_edge():
    s = _scene_with_rooftop()
    # At (3, 10, 12) — outside rooftop polygon, above ground
    assert is_supported_at(Position(3, 10, 12.0), s) is False


def test_supported_on_ground_default():
    s = _scene_with_rooftop()
    assert is_supported_at(Position(3, 10, 0.0), s) is True


def test_falling_damage_formula_6e_one_d6_per_2m():
    # HERO 6E1 pg 432: 1d6 per 2m fallen, normal damage vs PD.
    assert compute_falling_damage(fall_distance_m=2) == 1
    assert compute_falling_damage(fall_distance_m=4) == 2
    assert compute_falling_damage(fall_distance_m=10) == 5
    assert compute_falling_damage(fall_distance_m=1) == 0   # less than 2m — no damage


def test_falling_damage_capped_at_20d6_for_terminal_velocity():
    assert compute_falling_damage(fall_distance_m=100) == 20
    assert compute_falling_damage(fall_distance_m=1000) == 20


def test_resolve_fall_from_rooftop_to_ground():
    s = _scene_with_rooftop()
    # Combatant pushed off the rooftop edge at (3, 10, 12) — above ground only
    result = resolve_fall(
        combatant_id="alice",
        from_pos=Position(3, 10, 12),
        scene=s,
        gravity_scale=1.0,
    )
    assert isinstance(result, FallingResult)
    assert result.landed_at.z == 0.0                     # landed on ground
    assert result.fall_distance_m == 12.0
    assert result.damage_dice == 6                       # 12m / 2 = 6d6


def test_resolve_fall_onto_intermediate_supporting_surface():
    # Two-level building: rooftop at z=12, balcony at z=5, ground at z=0.
    s = Scene(
        id="s1", name="Two-Story",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface("ground", "Ground", [(0, 0), (20, 0), (20, 20), (0, 20)],
                    0.0, "ground", 0, True),
            Surface("balcony", "Balcony", [(0, 0), (20, 0), (20, 6), (0, 6)],
                    5.0, "ground", 0, True),
            Surface("roof", "Roof", [(5, 8), (15, 8), (15, 18), (5, 18)],
                    12.0, "rooftop", 0, True),
        ],
        walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    # Pushed off rooftop at (10, 17, 12); below at (10, 17, 5) — balcony ends at y=6
    # so NOT caught by balcony (outside balcony polygon at y=17). Lands on ground z=0.
    result = resolve_fall(
        combatant_id="bob",
        from_pos=Position(10, 17, 12),
        scene=s,
        gravity_scale=1.0,
    )
    assert result.landed_at.z == 0.0
    assert result.fall_distance_m == 12.0
    # Now pushed at (10, 3, 12) — directly above balcony (balcony y range 0-6).
    # Lands on balcony at z=5.
    result2 = resolve_fall(
        combatant_id="bob",
        from_pos=Position(10, 3, 12),
        scene=s,
        gravity_scale=1.0,
    )
    assert result2.landed_at.z == 5.0
    assert result2.fall_distance_m == 7.0                # 12 - 5
