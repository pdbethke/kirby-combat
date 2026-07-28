"""Derived wall-top strips — the standable-structures half of the
supported-vantages spec (§1)."""
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
    wall_top_surface,
)
from kirby_combat.scene.falling import is_supported_at, resolve_fall

GROUND = Surface(
    id="g", name="ground",
    polygon_xy=[(-25.0, -25.0), (25.0, -25.0), (25.0, 25.0), (-25.0, 25.0)],
    elevation_m=0.0, surface_type="ground",
)


def _wall(width: float = 1.0, height: float = 8.0) -> Wall:
    return Wall(
        id="w1", name="stone wall",
        segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
        height_m=height, walkable_width_m=width,
    )


def _scene(*walls: Wall) -> Scene:
    return Scene(
        id="s", name="test",
        bounds=SceneBounds(-25.0, -25.0, -5.0, 25.0, 25.0, 15.0),
        surfaces=[GROUND], walls=list(walls), hazards=[],
        ambient=AmbientConditions(),
    )


def test_zero_width_wall_derives_no_strip():
    """A chain-link fence / force wall / low parapet is not a walkway."""
    assert wall_top_surface(_wall(width=0.0)) is None


def test_strip_sits_at_the_wall_top():
    s = wall_top_surface(_wall(width=1.0, height=8.0))
    assert s is not None
    assert s.elevation_m == 8.0
    assert s.is_supporting is True
    assert s.id == "w1:top"


def test_narrow_strip_is_precarious_and_wide_one_is_not():
    assert wall_top_surface(_wall(width=1.0)).is_precarious is True
    assert wall_top_surface(_wall(width=3.0)).is_precarious is False


def test_supporting_surfaces_adds_strips_without_mutating_authored_list():
    sc = _scene(_wall())
    assert {s.id for s in sc.supporting_surfaces()} == {"g", "w1:top"}
    assert [s.id for s in sc.surfaces] == ["g"]   # authored list untouched


def test_supported_on_the_strip_but_not_beside_or_above_it():
    sc = _scene(_wall(width=1.0, height=8.0))
    # On the strip: the wall runs along y=-5, half-width 0.5.
    assert is_supported_at(Position(-9.0, -5.0, 8.0), sc) is True
    # 0.9 m to the side — off the 1 m strip.
    assert is_supported_at(Position(-9.0, -5.9, 8.0), sc) is False
    # Directly above it — exact-elevation rule still applies.
    assert is_supported_at(Position(-9.0, -5.0, 8.5), sc) is False


def test_a_wall_with_no_walkable_width_supports_nothing():
    sc = _scene(_wall(width=0.0, height=8.0))
    assert is_supported_at(Position(-9.0, -5.0, 8.0), sc) is False


def test_fall_lands_on_the_strip_rather_than_the_ground():
    """resolve_fall must see derived strips too, or a character dropping
    past a wall top would tunnel through it to the ground."""
    sc = _scene(_wall(width=1.0, height=8.0))
    fall = resolve_fall("c1", Position(-9.0, -5.0, 12.0), sc)
    assert fall.landed_at.z == 8.0
    assert fall.fall_distance_m == 4.0
