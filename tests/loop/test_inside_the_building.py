"""Being IN the house, not beside it.

Spec: `kirby/docs/superpowers/specs/2026-09-08-interiors-design.md`.

`caught_under` uses proximity --- two metres of a wall's line --- because
that was the only question the scene model could answer. So a man
sheltering in the middle of Fly's Studio, ten metres from any wall of it,
was untouched when the building came down on him, and a man leaning on
the outside was crushed.

NOT A NEW CONCEPT. `constructs_containing` already walks a polygon and an
elevation range and returns what a position is inside; `scene/hazards.py`
already computes on_enter transitions off it. What was missing is that no
BUILDING was a volume --- a `Wall` is a segment with a height, so a house
is four unrelated lines and its inside is nothing at all.

The footprint is a second VIEW of the building, exactly as `constructs_in`
made walls a second view of what can be hit without moving them out of
`scene.walls`.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.collapse import caught_under
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _studio():
    """A shack ten metres square, with an inside."""
    return Construct(
        obj_id="studio", kind="wall",
        segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
        polygon_xy=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        elevation_range_m=(0.0, 4.0),
        height_m=4.0, blocks_los=True, blocks_movement=True,
        cover_level=4, def_value=1, body=4,
    )


def _session(**positions):
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-5.0, -5.0, 0.0, 25.0, 25.0, 25.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-5, -5), (25, -5), (25, 25), (-5, 25)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
        constructs=[_studio()],
    )
    return CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter(k, side=Side.named("x")) for k in positions],
    ).start()


def test_a_man_in_the_middle_of_the_room_is_under_it():
    """Ike, sheltering. Five metres from every wall, and the roof is
    still coming down on him."""
    session = _session(ike=(5.0, 5.0))
    assert "ike" in caught_under(session, _studio())


def test_a_man_leaning_on_the_outside_is_still_caught():
    """Proximity has not gone --- the edge of a collapse is real. Both
    questions are true; the engine could only ask one."""
    session = _session(doc=(-1.0, 5.0))
    assert "doc" in caught_under(session, _studio())


def test_a_man_in_the_street_is_not():
    session = _session(wyatt=(20.0, 20.0))
    assert "wyatt" not in caught_under(session, _studio())


def test_a_building_with_no_footprint_still_falls_on_its_neighbours():
    """Every scene authored before interiors existed keeps working: with
    no polygon there is no inside, and proximity answers alone."""
    from dataclasses import replace

    session = _session(ike=(5.0, 5.0), doc=(0.5, 5.0))
    flat = replace(_studio(), polygon_xy=None)
    caught = caught_under(session, flat)
    assert "doc" in caught, "the man against the wall is still caught"
    assert "ike" not in caught, "and nobody has an inside to be in"
