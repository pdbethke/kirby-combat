"""A solid floor blocks line of sight.

has_line_of_sight passed only scene.walls; scene.surfaces was never consulted,
so every floor, rooftop and platform in the game was transparent to sight.

Found by PeterB watching the demo replay once the terrain rendered correctly:
A ground observer stands at (0,13,0) and a rooftop figure at (0,13,6) on the URBAN_ROOFTOP whose
polygon covers (0,13). Six metres of concrete between them, and the engine
said they could see each other.

6E1 p150: "LOS means the character has direct perception of or can perceive
any part of the target with a Targeting Sense." APG p66, on breaking a
mentalist's LOS: "all the victim has to do is move to a position where there's
an obstacle (a wall, a large [object])". A solid floor defeats direct
perception the same way a wall does.
"""
from __future__ import annotations

import pytest

from kirby_combat.resolution.line_of_sight import has_line_of_sight
from kirby_combat.scene.scene import (
    AmbientConditions,
    Position,
    Scene,
    SceneBounds,
    Surface,
)

GROUND_POLY = [(-25.0, -25.0), (25.0, -25.0), (25.0, 25.0), (-25.0, 25.0)]
ROOF_POLY = [(-25.0, 5.0), (10.0, 5.0), (10.0, 25.0), (-25.0, 25.0)]


def _scene(*surfaces: Surface) -> Scene:
    return Scene(
        id="s", name="urban_rooftop",
        bounds=SceneBounds(-25, -25, -5, 25, 25, 20),
        surfaces=list(surfaces), walls=[], hazards=[],
        ambient=AmbientConditions(4, 1.0),
    )


def _ground(**kw) -> Surface:
    return Surface(id="g", name="ground", elevation_m=0.0,
                   surface_type="ground", polygon_xy=GROUND_POLY, **kw)


def _roof(**kw) -> Surface:
    return Surface(id="r", name="rooftop", elevation_m=6.0,
                   surface_type="rooftop", polygon_xy=ROOF_POLY, **kw)


def test_a_ground_observer_cannot_see_through_the_roof_above() -> None:
    """The regression that prompted this, with its real coordinates."""
    scene = _scene(_ground(), _roof())
    ground_observer = Position(x=0.0, y=13.0, z=0.0)    # under the roof
    rooftop_figure = Position(x=0.0, y=13.0, z=6.0)  # on it, directly above
    assert not has_line_of_sight(scene, ground_observer, rooftop_figure)
    assert not has_line_of_sight(scene, rooftop_figure, ground_observer), "symmetric"


def test_two_combatants_on_the_same_roof_see_each_other() -> None:
    """The surface they are BOTH standing on must not blind them."""
    scene = _scene(_ground(), _roof())
    a = Position(x=0.0, y=13.0, z=6.0)
    b = Position(x=5.0, y=20.0, z=6.0)
    assert has_line_of_sight(scene, a, b)


def test_two_combatants_on_the_ground_are_unaffected() -> None:
    scene = _scene(_ground(), _roof())
    a = Position(x=0.0, y=-10.0, z=0.0)
    b = Position(x=5.0, y=-20.0, z=0.0)
    assert has_line_of_sight(scene, a, b)


def test_no_block_when_the_ray_misses_the_polygon() -> None:
    """Below the roof's footprint is not the same as below the roof."""
    scene = _scene(_ground(), _roof())
    below = Position(x=0.0, y=-20.0, z=0.0)   # y=-20 is outside ROOF_POLY
    above = Position(x=0.0, y=-20.0, z=6.0)
    assert has_line_of_sight(scene, below, above)


def test_a_flier_above_the_roof_sees_someone_standing_on_it() -> None:
    scene = _scene(_ground(), _roof())
    on_roof = Position(x=0.0, y=13.0, z=6.0)
    flier = Position(x=0.0, y=13.0, z=12.0)
    assert has_line_of_sight(scene, on_roof, flier)


def test_a_flier_cannot_see_through_the_roof_to_the_ground() -> None:
    scene = _scene(_ground(), _roof())
    flier = Position(x=0.0, y=13.0, z=12.0)
    under = Position(x=0.0, y=13.0, z=0.0)
    assert not has_line_of_sight(scene, flier, under)


def test_a_fall_through_surface_does_not_block() -> None:
    """is_supporting=False means you fall through it — so can a ray."""
    scene = _scene(_ground(), _roof(is_supporting=False))
    ground_observer = Position(x=0.0, y=13.0, z=0.0)
    rooftop_figure = Position(x=0.0, y=13.0, z=6.0)
    assert has_line_of_sight(scene, ground_observer, rooftop_figure)


def test_a_degenerate_surface_never_blocks() -> None:
    """Bad data must not blind the board."""
    bad = Surface(id="b", name="bad", elevation_m=3.0, surface_type="rooftop",
                  polygon_xy=[(0.0, 0.0), (1.0, 1.0)])
    scene = _scene(_ground(), bad)
    a = Position(x=0.0, y=0.0, z=0.0)
    b = Position(x=0.0, y=0.0, z=6.0)
    assert has_line_of_sight(scene, a, b)


def test_indirect_still_bypasses_everything() -> None:
    """6E1 p339 Indirect aims around obstacles; that gate precedes this one."""
    scene = _scene(_ground(), _roof())
    ground_observer = Position(x=0.0, y=13.0, z=0.0)
    rooftop_figure = Position(x=0.0, y=13.0, z=6.0)
    assert has_line_of_sight(scene, ground_observer, rooftop_figure, indirect_advantage=True)
