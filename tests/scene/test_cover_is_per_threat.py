"""Cover you can use against SOME of them is still cover.

`cover_available` first returned the WORST level against any threat, on
the reasoning that "cover that only works against one of three shooters
is not cover you can rely on". That reads well and is wrong twice.

It is wrong about the RULES: resolution applies cover per shooter-target
pair (`_cover_against` in actions/recording.py), so a barrel really does
cost the man in front of it -2 OCV while costing the man who flanked it
nothing. Scoring the barrel 0 described a game the engine does not play.

And it is wrong about the FIGHT it was measured on. Nine men in a 5.5m
lot means every piece of cover is flanked by somebody, so every feature
scored 0 and the offer never appeared -- on a map furnished with barrels,
a trough and packing crates specifically to give them something to hide
behind.

What a chooser needs is not one pessimistic number but the shape of the
trade: how much cover, against how many of them. So `cover_available`
returns the BEST level the spot gives against any single threat, and
`cover_breakdown` says how many threats it actually covers, which is what
the offer quotes.
"""
from __future__ import annotations

import pytest

from kirby_combat.scene.cover import cover_available, cover_breakdown
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)


def _scene():
    """A barrel at x=5. One threat west of it, one east (flanking)."""
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-20.0, -20.0, 0.0, 20.0, 20.0, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[Wall(
            id="barrel", name="Barrel",
            segment=(Position(5.0, -1.5, 0.0), Position(5.0, 1.5, 0.0)),
            height_m=1.2, blocks_los=False, blocks_movement=True,
            cover_level=2, body=4, def_value=2, climb_difficulty=0)],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={},
    )


def test_a_flanked_barrel_still_counts():
    """Two threats, the barrel between the actor and one of them. The
    old rule scored this 0 and the feature was never offered."""
    scene = _scene()
    here = Position(10.0, 0.0, 0.0)
    threats = [Position(0.0, 0.0, 0.0),      # barrel is between us
               Position(10.0, 10.0, 0.0)]    # clear shot, flanking
    _spot, level = cover_available(scene.walls[0], here, threats, scene)
    assert level == 2


def test_the_breakdown_says_how_many_it_covers():
    scene = _scene()
    here = Position(10.0, 0.0, 0.0)
    threats = [Position(0.0, 0.0, 0.0), Position(10.0, 10.0, 0.0)]
    spot, level = cover_available(scene.walls[0], here, threats, scene)
    covered, total = cover_breakdown(scene.walls[0], spot, threats, scene)
    assert (covered, total) == (1, 2)


def test_a_feature_that_shields_nobody_is_still_declined():
    """The point of measuring was never to offer everything --- a wall
    behind you helps against nobody and must stay off the menu."""
    scene = _scene()
    here = Position(0.0, 0.0, 0.0)          # barrel is BEHIND the threat
    threats = [Position(10.0, 10.0, 0.0)]
    _spot, level = cover_available(scene.walls[0], here, threats, scene)
    assert level == 0


def test_no_threats_means_no_cover_question():
    scene = _scene()
    here = Position(10.0, 0.0, 0.0)
    spot, level = cover_available(scene.walls[0], here, [], scene)
    assert (spot, level) == (here, 0)
