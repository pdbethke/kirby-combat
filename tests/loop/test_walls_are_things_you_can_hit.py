"""The buildings were never in the fight.

`construct_from_wall` projects an authored `Wall` into a `Construct` ---
carrying its DEF, its BODY, its geometry and its cover level. It is
complete, it is correct, it is exported from `kirby_combat.scene`, and
NOTHING IN THIS ENGINE CALLS IT.

So `attack_construct`, which iterates `constructs`, could not see a single
building, barrel or packing crate in the O.K. Corral --- and `smash_cover`,
a tactic in the catalogue whose whole purpose is destroying the thing
somebody is hiding behind, has never had anything to smash.

Tenth of the same shape in a week: computed, correct, delivered nowhere.

PeterB: "throw a wagon at a house that ike is hiding in and collapse it".
This is the first of the four things that needs --- and three of the four
already exist.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.side import Side


def _lot(*walls):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 12.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (12, -2), (12, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[],
        ambient=AmbientConditions(light_level=4),
        combatant_positions={"lad": Position(2.0, 2.0, 0.0),
                             "ike": Position(4.0, 4.0, 0.0)},
    )


def _house(id_="harwood", body=8, def_value=4):
    return Wall(id=id_, name="Harwood House",
                segment=(Position(3.0, 1.0, 0.0), Position(3.0, 5.0, 0.0)),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value)


def _menu(scene):
    """As the loop assembles it: scene-derived facts are computed by the
    caller and passed in, which is how `slot_allocation` and the abort
    flag already reach enumeration."""
    from kirby_combat.scene.construct import constructs_in

    actor = fighter("lad", side=Side.named("x"))
    return enumerate_actions(
        actor, [fighter("ike", side=Side.named("y"))],
        has_scene=True, scene=scene, movement=list(actor.movement_view()),
        constructs=constructs_in(scene) or None,
    )


def test_a_building_can_be_attacked():
    """A wall with DEF and BODY is a thing in the fight, not scenery."""
    menu = _menu(_lot(_house()))
    assert [a.target_id for a in menu if a.kind == "attack_construct"] == ["harwood"]


def test_an_indestructible_wall_is_still_scenery():
    """`def_value=None` is the engine's word for "legacy / indestructible",
    and those must not become targets."""
    menu = _menu(_lot(_house(def_value=None)))
    assert not [a for a in menu if a.kind == "attack_construct"]


def test_a_lot_with_no_walls_offers_nothing_to_smash():
    assert not [a for a in _menu(_lot()) if a.kind == "attack_construct"]


def test_the_projection_carries_what_the_wall_knew():
    """DEF, BODY and cover are what make it worth shooting."""
    from kirby_combat.scene import construct_from_wall

    c = construct_from_wall(_house(body=8, def_value=4))
    assert (c.body, c.def_value, c.cover_level) == (8, 4, 4)
    assert c.destructible
