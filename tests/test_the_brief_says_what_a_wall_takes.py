"""The page says how hard a wall is, not just how much of it there is.

`Terrain.sightings` reported "BODY 8 to break through" and stopped. BODY
is how MUCH there is to chew through; DEF is whether you can bite at all,
and under 6E2 p.172 an object takes BODY damage reduced by its DEF, so an
attack that does not beat DEF does nothing to it forever.

Without DEF on the page, a reader weighing "shoot the wall" against
"shoot the man" is missing the half of the arithmetic that decides it. A
2d6 killing attack averages 7 BODY: against the Harwood House's DEF 4
that is 3 a hit and the wall goes in three Phases, and against a DEF 8
stone bank it is nothing, ever, and the fighter who tries will still be
trying when the fight ends. Those two walls read IDENTICALLY on the old
page.

Measured: five men spent 127 of 781 decisions shooting buildings, and
nothing they could read told them whether it was working.

This derives nothing --- `Wall.def_value` and `Wall.body` are both already
on the scene. It is the same defect as the terrain section itself, which
existed for a long time while the page it belonged on said nothing about
the ground.
"""
from __future__ import annotations

from kirby_combat.brief import Terrain
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)


class _Guy:
    def __init__(self, ident):
        self.id = ident


def _terrain(*walls):
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"tom": Position(2.0, 5.0, 0.0),
                             "virgil": Position(9.0, 5.0, 0.0)},
    )

    class _Session:
        pass

    session = _Session()
    session.scene = scene
    return Terrain(session, _Guy("tom"), [_Guy("virgil")])


def _wall(ident, *, body, def_value):
    return Wall(id=ident, name=ident,
                segment=(Position(5.0, 0.0, 0.0), Position(5.0, 10.0, 0.0)),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value)


def test_a_wall_reports_both_what_stops_you_and_how_much_there_is():
    sighting = _terrain(_wall("harwood", body=8, def_value=4)).sightings[0]
    assert "DEF 4" in sighting
    assert "BODY 8" in sighting


def test_two_walls_that_used_to_read_alike_no_longer_do():
    """The whole point. A pistol takes the first in three Phases and will
    never touch the second."""
    board, bank = _terrain(_wall("boarding-house", body=8, def_value=4),
                           _wall("bank", body=8, def_value=8)).sightings
    assert board != bank


def test_a_wall_with_no_stats_says_nothing_it_cannot_back_up():
    """`body` and `def_value` are optional on a Wall, and an absent number
    must not render as a zero --- "DEF 0" is an invitation."""
    sighting = _terrain(_wall("smoke", body=None, def_value=None)).sightings[0]
    assert "DEF" not in sighting
    assert "BODY" not in sighting
