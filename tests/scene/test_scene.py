"""Scene construction + combatant positioning."""
import pytest

from kirby_combat.scene import (
    Scene, SceneBounds, Surface, Wall, Hazard, Position, AmbientConditions,
    HazardEffect,
)


def test_scene_minimal_construction():
    s = Scene(
        id="s1", name="Empty Room",
        bounds=SceneBounds(min_x=0, min_y=0, min_z=0, max_x=10, max_y=10, max_z=5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    assert s.id == "s1"
    assert s.bounds.max_x == 10


def test_surface_with_polygon_and_elevation():
    surf = Surface(
        id="floor", name="Ground Floor",
        polygon_xy=[(0, 0), (10, 0), (10, 10), (0, 10)],
        elevation_m=0.0, surface_type="ground",
        cover_level=0, is_supporting=True,
    )
    assert surf.is_supporting is True


def test_wall_with_height_and_los_blocking():
    w = Wall(
        id="w1", name="Brick",
        segment=(Position(x=0, y=0, z=0), Position(x=10, y=0, z=0)),
        height_m=3.0,
        blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    assert w.blocks_los is True
    assert w.height_m == 3.0


def test_hazard_definition():
    h = Hazard(
        id="fire1", name="Spreading Fire",
        polygon_xy=[(5, 5), (7, 5), (7, 7), (5, 7)],
        elevation_range_m=(0.0, 2.0),
        trigger="on_enter",
        effect=HazardEffect(damage_dice=2, damage_type="energy"),
    )
    assert h.trigger == "on_enter"
    assert h.effect.damage_dice == 2


def test_position_defaults_facing_east():
    p = Position(x=1.0, y=2.0, z=0.0)
    assert p.facing == 0.0      # east = 0 radians convention


def test_place_combatant_sets_position():
    s = Scene(
        id="s1", name="Empty",
        bounds=SceneBounds(0, 0, 0, 10, 10, 5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    s2 = s.place_combatant("alice", Position(x=3, y=4, z=0))
    assert s2.combatant_positions["alice"] == Position(x=3, y=4, z=0)
    assert s.combatant_positions == {}   # original unchanged


def test_place_combatant_out_of_bounds_raises():
    s = Scene(
        id="s1", name="Empty",
        bounds=SceneBounds(0, 0, 0, 10, 10, 5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    with pytest.raises(ValueError, match="out of bounds"):
        s.place_combatant("alice", Position(x=20, y=0, z=0))


def test_wall_top_surface_and_mode_requires_support_are_exported_from_scene_package():
    """The branch's main import surface — the two symbols a consumer actually
    needs to call — must be importable from `kirby_combat.scene`, matching
    every other scene symbol's export."""
    import kirby_combat.scene as scene_pkg

    assert "wall_top_surface" in scene_pkg.__all__
    assert "mode_requires_support" in scene_pkg.__all__
    assert callable(scene_pkg.wall_top_surface)
    assert callable(scene_pkg.mode_requires_support)


def test_is_climbable_is_exported_from_scene_package():
    """whole-branch review MINOR 3: the consuming service needs
    `is_climbable`, same as `wall_top_surface`/`mode_requires_support`."""
    import kirby_combat.scene as scene_pkg

    assert "is_climbable" in scene_pkg.__all__
    assert callable(scene_pkg.is_climbable)
