"""Hide is offered next to cover --- measured to the cover, not its middle.

THE DEFECT THIS PINS. `_actor_has_cover` found a surface's position by
slicing `polygon_xy` as a flat `[x0, y0, x1, y1, ...]` list, but `Surface`
stores `(x, y)` tuples. The slice summed tuples, raised TypeError, and the
`except Exception` around the call turned that into "no cover". So no
Surface ever offered Hide: a man standing in a forest could not hide in it.

And the point it was trying to compute was the wrong one. A surface was
measured at its centroid and a wall at its midpoint, so a man in the
corner of a forty-metre wood, or at the end of a long wall, was "not
adjacent" to the cover he was standing in or against. Adjacency is the
distance to the NEAREST part of the feature, and inside a surface is zero.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.enumeration import _actor_has_cover
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)

MAN = synthetic_combatant(id="man", name="man")


def _scene(at: Position, *, surfaces=(), walls=()) -> Scene:
    return Scene(
        id="sc", name="sc",
        bounds=SceneBounds(-100, -100, -10, 100, 100, 50),
        surfaces=list(surfaces), walls=list(walls), hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={"man": at},
    )


def _wood(cover_level: int = 2) -> Surface:
    """A forty-metre square wood, centred on the origin."""
    return Surface(
        id="wood", name="wood", elevation_m=0.0, surface_type="forest",
        polygon_xy=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
        cover_level=cover_level,
    )


def test_standing_in_the_middle_of_a_wood_is_cover():
    assert _actor_has_cover(MAN, _scene(Position(0, 0, 0), surfaces=[_wood()]))


def test_standing_in_the_corner_of_a_wood_is_cover():
    """Twenty-five metres from the centroid, and inside the trees."""
    assert _actor_has_cover(MAN, _scene(Position(18, 18, 0), surfaces=[_wood()]))


def test_standing_just_outside_the_treeline_is_cover():
    assert _actor_has_cover(MAN, _scene(Position(21.5, 0, 0), surfaces=[_wood()]))


def test_open_ground_well_away_from_the_wood_is_not():
    assert not _actor_has_cover(
        MAN, _scene(Position(30, 0, 0), surfaces=[_wood()]))


def test_a_surface_with_no_cover_level_is_not_cover():
    assert not _actor_has_cover(
        MAN, _scene(Position(0, 0, 0), surfaces=[_wood(cover_level=0)]))


def _long_wall() -> Wall:
    return Wall(
        id="w", name="wall", height_m=2.0,
        segment=(Position(-20, 0, 0), Position(20, 0, 0)),
    )


def test_the_end_of_a_long_wall_is_cover():
    """Nineteen metres from the midpoint, one metre from the wall."""
    assert _actor_has_cover(MAN, _scene(Position(19, 1, 0), walls=[_long_wall()]))


def test_three_metres_off_a_wall_is_not():
    assert not _actor_has_cover(
        MAN, _scene(Position(0, 3, 0), walls=[_long_wall()]))
